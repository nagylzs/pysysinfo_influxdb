#!/usr/bin/env python3
import datetime
from dateutil import tz
import sys
import pprint
import argparse
import platform
from getpass import getpass

from pysysinfo_influxdb import get_all_stats
from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBClientError

if sys.version_info.major < 3:
    raise SystemExit("You must run this program with python version 3.")

extra_tags = {"hostname": platform.node()}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Collect and send system information to an influxdb database."
    )
    parser.add_argument("-v", "--verbose", default=False, action="store_true",
                        help="Be verbose (the default is to be silent)")
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

    parser.add_argument("-e", "--extra-tags", default=extra_tags,
                        help="Extra tags to add, defaults to : '%s' " % extra_tags)

    args = parser.parse_args()

    if args.ask_password:
        if args.password is not None:
            parser.error("Conflicting options: cannot use --password and --ask-password at the same time.")
        args.password = getpass()

    def debug(s):
        if args.debug:
            print(s)

    debug("Getting stats...")
    stats = get_all_stats()
    now = datetime.datetime.utcnow().isoformat()
    points = []
    for measurement_name, data in stats.items():
        data["measurement"] = measurement_name
        data["time"] = now
        data["tags"].update(extra_tags)
        points.append(data)
    if args.verbose:
        pprint.pprint(points)
    if not args.no_send:
        debug("Connecting influxdb...")
        db = InfluxDBClient(
            host=args.host,
            port=args.port,
            ssl=args.ssl,
            verify_ssl=not args.insecure,
            username=args.user,
            password=args.password or "",
            database=args.database)
        try:
            if args.create_database:
                debug("Creating database", args.database)
                db.create_database(args.database)
            debug("Sending results...")
            db.write_points(points)
            debug("Closing database")
            db.close()
        except InfluxDBClientError as e:
            sys.stderr.write("%s %s\n" % (e.code, e.content))
            sys.stderr.flush()
            raise SystemExit(1)
        debug("Send successful")
    else:
        debug("Won't send (--no-send specified)")
