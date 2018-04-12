#!/usr/bin/env python3
from distutils.core import setup

# https://docs.python.org/3/distutils/setupscript.html

setup(
    name='BlindBackup',
    version='2.0',
    description='BlindBackup',
    author='Laszlo Zsolt Nagy',
    author_email='nagylzs@gmail.com',
    url='https://www.mess.hu',
    packages=['blindbackup'],
    install_requires=['psutil', 'influxdb'],
    scripts=["scripts/send_sysinfo_influx.py", ]
)
