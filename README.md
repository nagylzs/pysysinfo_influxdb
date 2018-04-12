# sysinfo_influxdb
Periodically send system information into influxdb

Inspired by https://github.com/novaquark/sysinfo_influxdb with the following differences:

* Uses python3 + psutil, so it also works under Windows


Installation
============

* Make sure that you have python 3 installed. This program won't work with python 2.
* You will also need pipenv. If you don't have it then try this:

    sudo pip3 install pipenv

* Then you can install this program and all requirements by:


    git clone https://github.com/nagylzs/pysysinfo_influxdb.git
    cd pysysinfo_influxdb
    pipenv install


(work in progress...)
