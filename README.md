# sysinfo_influxdb
Periodically send system information into influxdb

Inspired by https://github.com/novaquark/sysinfo_influxdb with the following differences:

* Uses python3 + psutil, so it also works under Windows


Installation
============

This is a simple script that is packaged into a single python file. It is designed this way to allow quick and dirty
installation on any machine that has python3 installed, with minimal dependencies. Only external dependencies are
psutil and influxdb. If you prefer to use virtual environments, a pipfile is also provided.

Quick and dirty installation on Debian based systems
----------------------------------------------------

Make sure that you have python 3 installed. This program won't work with python 2.

    sudo apt-get install python3-dev
    sudo apt-get install python3-pip
    sudo python3 -m pip install --upgrade pip
    sudo pip3 install psutil influxdb
    wget https://raw.githubusercontent.com/nagylzs/pysysinfo_influxdb/master/scripts/send_sysinfo_influx.py

Then you are ready to go with "python3 send_sysinfo_influx.py".

Installation on Windows
-----------------------

Basically, yo need to take the same steps:

* Install Python3
* Install psutil and influxdb with pip
* Download the script (or clone the repo) and you are ready to go

Known problems
==============

Some metrics (e.g. cpu/load) may not be available on certain systems. Especially inside virtual machine guests and
docker containers, some files under /procinfo may not be readable. CPU load is known to be unreliable inside
LXC containers.

Planned features
================

* Create a Win32 service so it can be installed on Windows hosts as a service
* Add command line options to write pid files
* Create rc scripts for various systems

![Example output (using Grafana)](example.png)

Usage
=====

In all cases, please consult the manual of your own copy. This readme
may be out of date.

    python3 scripts/send_sysinfo_influx.py --help
    usage: send_sysinfo_influx.py [-h] [-v] [--silent] [--debug] [-n]
                                  [--host HOST] [-p PORT] [-s] [--insecure]
                                  [-d DATABASE] [--create-database] [-u USER]
                                  [--password PASSWORD] [-a] [-e EXTRA_TAGS]
                                  [--docker-stats] [--docker-stats-extra]
                                  [-l LOOP] [-i]

    Collect and send system information to an influxdb database.

    optional arguments:
      -h, --help            show this help message and exit
      -v, --verbose         Be verbose (the default is to be silent)
      --silent              Be silent (do not even print error messages)
      --debug               Print debug messages
      -n, --no-send         Do not actually send data to server. (Useful with
                            --verbose.)
      --host HOST           InfluxDb host
      -p PORT, --port PORT  InfluxDb port
      -s, --ssl             Use HTTPS instead of HTTP.
      --insecure            Do not verify ssl cert (insecure).
      -d DATABASE, --database DATABASE
                            InfluxDb database name, defaults to 'sysinfo'
      --create-database     Try to create database if not exists.
      -u USER, --user USER  InfluxDb username
      --password PASSWORD   InfluxDb password. If you didn't enable
                            authentication, then do not specify this option.
      -a, --ask-password    Ask for InfluxDb password. If you didn't enable
                            authentication, then do not specify this option.
      -e EXTRA_TAGS, --extra-tags EXTRA_TAGS
                            Extra tags to add, defaults to : '{'hostname':
                            'nagy'}'
      --docker-stats        Use 'docker stats' to retrieve docker statistics.
                            Works with 18.03+
      --docker-stats-extra  Use 'docker inspect' to retrieve extra docker
                            statistics. This is CPU intensive.
      -l LOOP, --loop LOOP  Send data in an endless loop, wait the specified
                            number of seconds betweenthe sends. You can break the
                            loop with Ctrl+C or by sending a TERM signal.
      -i, --ignore-errors   Continue the loop even if there is an error.


Notes on --extra tags:

You can specify extra tags with --extra-tags. By default,
it only contains your hostname. Example usage of --extra-tags:


    python3 scripts/send_sysinfo_influx.py --extra-tags '{"your_tag_name":"your_tag_value"}' -n -v

Notes on --socker-stats:

* It was only tested on Linux and Docker 18.03 CE
* The collected data includes these tags: container_id, container_name, common_name.
  The common_name is a name that is constructed from the container name plus the hostname.
  It was added because you cannot specify your own name for replicas of docker services.
  For example, if you create a service called 'nginx' with three replicas, then the corresponding
  three containers will have these names like this: 'nginx.some_random_string_that_makes_it_unique'.
  The random part is added by docker to make the container name unique. If you ever restart or
  delete and recreate the service, then new containers will be created with new unique names.
  But this is not really useful when you want to collect data for a given replica of a given service.
  The common_name tag value will replace the random part with the hostname, so
  'service_name.some_random_string_that_makes_it_unique' becomes 'service_name.hostname'.
  With this trick, you will be able to aggregate data for a given service+hostname pair in a time
  interval which contains docker service restarts/recreations. Be aware that this trick will not work
  properly if you have multiple replicas of a service on a single host machine.



It is a good practice to check your data with "-v -n" before sending them to a live server.
