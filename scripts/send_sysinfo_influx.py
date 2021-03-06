#!/usr/bin/env python3
import re
import datetime
import functools
import time
import subprocess
import sys
import pprint
import argparse
import platform
import traceback
import json
from getpass import getpass

from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBClientError

if sys.version_info.major < 3:
    raise SystemExit("You must run this program with python version 3.")

import psutil
import os
import copy

from collections import ChainMap, namedtuple
from typing import List, Dict, Set


def _prefixed(nt: namedtuple, prefix):
    """Convert a named tuple into a dict with prefixed names."""
    result = {}
    for key, value in nt._asdict().items():
        result[prefix + key] = value
    return result


def _split_tags_and_fields(values, tag_names: Set[str] = set([])):
    tags = {}
    fields = {}
    for key, value in values.items():
        if key in tag_names:
            tags[key] = value
        else:
            fields[key] = value
    return dict(fields=fields, tags=tags)


def _parse(nt: namedtuple, prefix: str, tag_names: Set[str] = set([])):
    return _split_tags_and_fields(_prefixed(nt, prefix), tag_names)


def _prefixed_items_from_list(items: List[namedtuple], item_prefix, prefix, tag_names: Set[str] = set([])):
    """Convert a named tuple into a dict with prefixed names."""
    result = {}
    for index, nt in enumerate(items):
        result["%s%d" % (item_prefix, index)] = _parse(nt, prefix, tag_names)
    return result


def _prefixed_items_from_dict(values: Dict[str, namedtuple], item_prefix, prefix, tag_names: Set[str] = set([]),
                              cumulative=False):
    """Convert a named tuple into a dict with prefixed names."""
    result = {}
    for key, nt in values.items():
        item_key = "%s%s" % (item_prefix, key)
        item = _parse(nt, prefix, tag_names)
        if cumulative:
            item = _cumulative_diff(item, item_key)
        result[item_key] = item
    return result


_prev_values = {}


def _cumulative_diff(item, key):
    """Return a version that converts cumulative field values to their differences."""
    global _prev_values
    if key in _prev_values:
        # Subsequent item, return difference from previous
        prev = _prev_values[key]
        _prev_values[key] = item

        result = copy.deepcopy(item)
        for fname in result["fields"]:
            result["fields"][fname] -= prev["fields"][fname]

        return result
    else:
        # First item, no difference, return zeros.
        _prev_values[key] = item
        result = copy.deepcopy(item)
        fields = result["fields"]
        for fname in fields:
            fields[fname] = 0
        return result


try:
    _gla = os.getloadavg
except AttributeError:
    _gla = None


def get_load_stats():
    global _gla
    if _gla:
        load = _gla()
        return {
            "load": {
                "fields": {
                    "load_1min": load[0],
                    "load_5min": load[1],
                    "load_15min": load[2],
                },
                "tags": {},
            }
        }
    else:
        return {}


_has_cpu_info = None


def get_cpu_stats():
    global _has_cpu_info
    if _has_cpu_info is None:
        _has_cpu_info = psutil.cpu_freq() is not None
    if not _has_cpu_info:
        return {}
    fields = dict(
        count_physical=psutil.cpu_count(False),
        count_logical=psutil.cpu_count(True),
    )
    fields.update(_prefixed(psutil.cpu_freq(False), "freq_"))
    fields.update(psutil.cpu_stats()._asdict())

    result = {"cpu": {"fields": fields, "tags": {}}}

    result.update(_prefixed_items_from_list(psutil.cpu_freq(True), "cpu", "freq_"))

    return result


def get_vm_stats():
    return dict(virtual_memory=_parse(psutil.virtual_memory(), ""))


def get_swap_stats():
    return dict(swap=_parse(psutil.swap_memory(), ""))


def get_disk_io_stats():
    result = {}
    disk = _parse(psutil.disk_io_counters(perdisk=False, nowrap=True), "")
    result["disk"] = _cumulative_diff(disk, "disk")
    result.update(_prefixed_items_from_dict(
        psutil.disk_io_counters(perdisk=True, nowrap=True),
        item_prefix="disk_", prefix="", cumulative=True
    ))
    return result


def get_net_io_stats():
    result = {}
    net = _parse(psutil.net_io_counters(pernic=False, nowrap=True), "")
    result["net"] = _cumulative_diff(net, "net")
    result.update(_prefixed_items_from_dict(
        psutil.net_io_counters(pernic=True, nowrap=True),
        item_prefix="net_", prefix="", cumulative=True))
    return result


def get_fan_stats():
    result = {}
    for sysname, items in psutil.sensors_fans().items():
        result.update(_prefixed_items_from_list(items, "fan_" + sysname + "_", "", {"label"}))
    return result


def _to_docker_factor(code, original_text=None):
    code = code.strip()
    if code in ['T', 'TB']:
        return 1024 ** 4
    elif code in ['G', 'GB']:
        return 1024 ** 3
    elif code in ['GiB']:
        return 1000 ** 3
    elif code in ['M', 'MB']:
        return 1024 ** 2
    elif code in ['Mi', 'MiB']:
        return 1000 ** 2
    elif code in ['K', 'KB', 'kB']:
        return 1024
    elif code in ['', 'B', '%']:
        return 1
    else:
        # See Issue #1
        raise ValueError("Uknown factor: %s, original_text=%s" % (code, repr(original_text) ))


numeric_const_pattern = r"""(
    [-+]? # optional sign
    (?:
         (?: \d* \. \d+ ) # .1 .12 .123 etc 9.1 etc 98.1 etc
         |
         (?: \d+ \.? ) # 1. 12. 123. etc 1 12 123 etc
    )
    # followed by optional exponent part if desired
    (?: [Ee] [+-]? \d+ ) ?
    )"""
numeric_with_mu = "^" + numeric_const_pattern + r"\s*([^\s]*)$"
float_mu_pat = re.compile(numeric_with_mu, re.VERBOSE)
def _parse_docker_value(s):
    res = float_mu_pat.match(s.strip())
    if res:
        svalue, sfactor_code = res.groups()
        return float(svalue) * _to_docker_factor(sfactor_code ,s)
    else:
        raise Exception("Cannot parse docker value: %s" % repr(s))


def _parse_docker_pair(s):
    idx = s.find("/")
    left, right = s[:idx], s[idx + 1:]
    return _parse_docker_value(left), _parse_docker_value(right)


def get_docker_stats():
    result = []
    cmd = r'''docker stats --all --format "table {{.Container}}|{{.Name}}|{{.CPUPerc}}|{{.MemPerc}}|{{.MemUsage}}|{{.NetIO}}|{{.BlockIO}}|{{.PIDs}}"  --no-stream'''
    lines = subprocess.check_output(cmd, shell=True).decode("UTF-8").split("\n")
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        cid, cname, cpu_perc, mem_perc, mem_usage, net_io, block_io, pid_cnt = line.split("|")
        if "." in cname:
            common_name = cname.split(".")[0]+"."+ default_extra_tags["hostname"]
        else:
            common_name = cname
        memory_used, memory_limit = _parse_docker_pair(mem_usage)
        net_sent, net_received = _parse_docker_pair(net_io)
        block_read, block_written = _parse_docker_pair(block_io)
        item = {
            'tags': {'container_id': cid, 'container_name': cname, 'common_name': common_name },
            'fields': {
                'cpu_percent': _parse_docker_value(cpu_perc),
                'memory_percent': _parse_docker_value(mem_perc),
                'memory_used': memory_used,
                'memory_limit': memory_limit,
                'network_sent': net_sent,
                'network_received': net_received,
                'block_read': block_read,
                'block_written': block_written,
                'pid_cnt': int(pid_cnt)
            }
        }
        if args.docker_stats_extra:
            sinspect = subprocess.check_output("docker inspect %s" % cid, shell=True).decode("UTF-8")
            inspect = json.loads(sinspect)[0]
            for key in inspect["State"]:
                item['tags']["state_%s" % key] = inspect["State"][key]
        result.append(item)
    return result


def get_all_stats():
    return ChainMap(
        get_load_stats(),
        get_cpu_stats(),
        get_vm_stats(),
        get_swap_stats(),
        get_disk_io_stats(),
        get_net_io_stats(),
        get_fan_stats(),
    )


def debug(args, s):
    if args.debug:
        print(s)


def error(args, s):
    if not args.silent:
        sys.stderr.write(s)
        sys.stderr.flush()


def main(args):
    d = functools.partial(debug, args)
    e = functools.partial(error, args)
    is_first = False
    while True:
        started = time.time()
        d("Getting stats...")
        stats = get_all_stats()
        now = datetime.datetime.utcnow().isoformat()
        d(now)
        points = []
        for measurement_name, data in stats.items():
            data["measurement"] = measurement_name
            data["time"] = now
            data["tags"].update(default_extra_tags)
            points.append(data)

        if args.docker_stats:
            for data in get_docker_stats():
                data["measurement"] = "docker"
                data["time"] = now
                data["tags"].update(default_extra_tags)
                points.append(data)

        stopped = time.time()
        d("Collected stats in %.3f sec" % (stopped - started))

        if args.verbose:
            pprint.pprint(points)
        if not args.no_send:
            try:
                d("Connecting influxdb...")
                db = InfluxDBClient(
                    host=args.host,
                    port=args.port,
                    ssl=args.ssl,
                    verify_ssl=not args.insecure,
                    username=args.user,
                    password=args.password or "",
                    database=args.database)
                try:
                    if args.create_database and is_first:
                        d("Creating database", args.database)
                        db.create_database(args.database)
                        is_first = False
                    d("Sending results...")
                    db.write_points(points)
                    d("Closing database")
                    db.close()
                except InfluxDBClientError as exc:
                    e("%s %s\n" % (exc.code, exc.content))
                    raise exc
                except Exception:
                    e(traceback.format_exc())
                    raise
                d("Send successful")
            except:
                if args.ignore_errors:
                    e("--ignore-errors specified, will retry after 10 seconds.")
                    time.sleep(10)
                else:
                    raise SystemExit(1)

        else:
            d("Won't send (--no-send specified)")

        if args.loop:
            d("Will wait for --loop=%s" % args.loop)
            time.sleep(args.loop)
            d("Wait complete.")
        else:
            break


default_extra_tags = {"hostname": platform.node()}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Collect and send system information to an influxdb database."
    )
    parser.add_argument("-v", "--verbose", default=False, action="store_true",
                        help="Be verbose (the default is to be silent)")
    parser.add_argument("--silent", default=False, action="store_true",
                        help="Be silent (do not even print error messages)")
    parser.add_argument("--debug", default=False, action="store_true",
                        help="Print debug messages")
    parser.add_argument("-n", "--no-send", default=False, action="store_true",
                        help="Do not actually send data to server. (Useful with --verbose.)")

    parser.add_argument("--host", default="localhost",
                        help="InfluxDb host")
    parser.add_argument("-p", "--port", default=8086, type=int,
                        help="InfluxDb port")
    parser.add_argument("-s", "--ssl", default=False, action="store_true",
                        help="Use HTTPS instead of HTTP.")
    parser.add_argument("--insecure", default=False, action="store_true",
                        help="Do not verify ssl cert (insecure).")
    parser.add_argument("-d", "--database", default="sysinfo",
                        help="InfluxDb database name, defaults to 'sysinfo'")
    parser.add_argument("--create-database", default=False, action="store_true",
                        help="Try to create database if not exists.")
    parser.add_argument("-u", "--user", default="root",
                        help="InfluxDb username")
    parser.add_argument("--password", default=None,
                        help="InfluxDb password. If you didn't enable authentication, then do not "
                             "specify this option.")
    parser.add_argument("-a", "--ask-password", default=False, action="store_true",
                        help="Ask for InfluxDb password. If you didn't enable authentication, then do not "
                             "specify this option.")
    parser.add_argument("-e", "--extra-tags", default=default_extra_tags,
                        help="Extra tags to add, defaults to : '%s' " % default_extra_tags)
    parser.add_argument("--docker-stats", default=False, action="store_true",
                        help="Use 'docker stats' to retrieve docker statistics. Works with 18.03+")
    parser.add_argument("--docker-stats-extra", default=False, action="store_true",
                        help="Use 'docker inspect' to retrieve extra docker statistics. This is CPU intensive.")

    parser.add_argument("-l", "--loop", default=None, type=float,
                        help="Send data in an endless loop, wait the specified number of seconds between"
                             "the sends. You can break the loop with Ctrl+C or by sending a TERM signal.")
    parser.add_argument("-i", "--ignore-errors", default=False, action="store_true",
                        help="Continue the loop even if there is an error.")

    args = parser.parse_args()

    if args.ask_password:
        if args.password is not None:
            parser.error("Conflicting options: cannot use --password and --ask-password at the same time.")
        args.password = getpass()

    if args.loop and args.loop < 0.1:
        parser.error("Loop time must be > 0.1 sec!")

    if not args.loop and args.ignore_errors:
        parser.error("--ignore-errors can only be used together with --loop")

    if args.silent and (args.verbose or args.debug):
        parser.error("--silent should not be combined with --verbose or --debug")

    if isinstance(args.extra_tags, str):
        args.extra_tags = json.loads(args.extra_tags)

    main(args)
