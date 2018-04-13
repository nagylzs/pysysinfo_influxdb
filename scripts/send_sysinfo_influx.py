#!/usr/bin/env python3
import datetime
import functools
import time

import sys
import pprint
import argparse
import platform
import traceback
from getpass import getpass

from pysysinfo_influxdb import get_all_stats
from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBClientError, InfluxDBServerError

if sys.version_info.major < 3:
    raise SystemExit("You must run this program with python version 3.")


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
            time.sleep(args.loop)
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

    main(args)
