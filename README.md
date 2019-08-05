# Smart-Storage
All the tools below are developed and verified by Python 3.6.
There are 3 tools set now:
* Tool to do MySQL bench using sysbench
* Tool to do Open CAS bench using FIO
* Tool to collect Intel CAS related drives' stats

## Run Sysbench against MySQL
1. Tools you need to install before running this benchmark:
* MySQL (8.0)
* sysbench
* Python 3
  * I am testing based on Python 3.6
* Also disable SElinux
  * Update /etc/selinux/config, change enforcing to disabled
  * Need one reboot to make the change effective

Configuration before starting the test:
* Prepare your mysql configuration file */etc/my.cnf*
  * Please make sure you have one section for your instance which should be *[mysql@X]*
* Prepare configuration for bench task *task.cnf*

Example of */etc/my.cnf*:
Here is one /etc/my/cnf for the above command example:
```
[root@sm114 2019_07_11_01h_08m]# cat /etc/my.cnf
[mysqld]
datadir=/var/lib/mysql
socket=/var/lib/mysql/mysql.sock
user=mysql
log_error=/var/log/mysqld.log
# Disabling symbolic-links is recommended to prevent assorted security risks
symbolic-links=0
default_authentication_plugin=mysql_native_password
default_password_lifetime=0

[mysqld_safe]
log_error=/var/log/mysqld.log
pid-file=/var/run/mysqld/mysqld.pid

[mysqld_multi]
mysqld=/usr/bin/mysqld_safe
mysqladmin=/usr/bin/mysqladmin

[mysqld@1]
user=mysql
datadir=/mnt/optane-sql
pid-file=/mnt/optane-sql/hostname.pid
socket=/mnt/optane-sql/mysql.sock
port=3309

symbolic-links=0
innodb_file_per_table=1
innodb_read_io_threads=64
innodb_write_io_threads=32
innodb_thread_concurrency=0
innodb_log_file_size=50000M
#innodb_io_capacity=100000
innodb_io_capacity=100000
innodb_log_buffer_size=64M
innodb_buffer_pool_size=50G
innodb_buffer_pool_instances=12
default_authentication_plugin=mysql_native_password
default_password_lifetime=0
innodb_flush_method=O_DIRECT
max_connections=3000
#skip-log-bin
```

Example of *task.cnf* with explanation:
* *THREAD_NUM_LIST=100, 128*: means when running sysbench command, will loop cases for 100 threads and 128 threads
* *STATS_CYCLE=5*: means we'll collect the stats using 5 seconds 
* *DB_NAME=sbtest*: means the name of the database is *sbtest*
* *PWD=intel123*: means the password of the database will be *intel123*
* *WORK_LOAD=/usr/share/sysbench/oltp_read_write.lua*: means we'll run only *read_write*
  * You can specify a list here
* *TABLE_NUM=10*: the test database will be 10 tables
* *ROWS=1000000*: there will be 1000000 rows in each table
* *DYNAMIC_BUFFER_POOL_SIZE=True*: means we'll use dynamic buffer pool size when running the test
  * *BUFFER_CHANGE_STEP*: this is the step to change buffer pool size, starting form min of database size and system physical size
  * *EXTRA_MEM_LIST=10,20*: means we'll add test cases for buffer pool size *10G* and *20G*
```
[sysbench]
THREAD_NUM_LIST=100, 128
STATS_CYCLE=5
DB_NAME=sbtest
PWD=intel123
WORK_LOAD=/usr/share/sysbench/oltp_read_write.lua
TABLE_NUM=10
ROWS=1000000
#DYNAMIC_BUFFER_POOL_SIZE=True
#BUFFER_CHANGE_STEP=0.05
#EXTRA_MEM_LIST=10,20
```

2. Types of benchwork supported now:
* Default Bench Mark
* Beachmark against one single block device
* Benchmark against a list of block devices
* Benchmark for CAS disks

Usage Helper:
```
usage: sysbenchRun.py [-h] --inst sqlInstance --output outputDir --time
                      runTime [--type benchTask] [--disk blockDevice]
                      [--caching cachingDev] [--core coreDev]
                      [--diskset blklist] [--debug] [--skipPrep]
```

Types of Bench Tasks *"--type"*:
```
'default', 'benchDisk', 'benchCAS', 'benchMoreDiskS'
```

3. Default Bench Mark
This is what the default bench mark will do:
* Do some initial setup for MySQL (based on your */etc/my.cnf* file)
* Create one database and fill in the data (you can specify the database size using parameter)
* Run sysbench oltp_read_only, oltp_write_only and oltp_read_write using sysbench

Here is how to trigger this command:
```
nohup python3 sysbenchRun.py -inst 1 -output /home/john -time 300 &
```

How to use the parameter:
* *-inst 1*: to indicate the test to use mysql *instance 1* to do the test
  * The section of [mysqld@1] in */etc/my.cnf* will be used by *instance 1*
* */home/john*: The directory to store the test result and logs 
* *-time 300*: For each sysbench job, it will run for *300 seconds*

Prepare your configuration file like this:
* Please make sure you have one default section [mysqld]
  * It is used to do initial mysql setup
* Please make sure you have one configuration for one mysql instance [mysqld@X]
  * The configuration of this instance is what you'll use for your test
  * The *datadir* must be created before you running the test
* There should be NO conflict between the default [mysqld] and you instance [mysqld@X] configuration
  * Eg. the page size must be the same
  

4. Bench against one block device
You may also want to see how mysql will perform on one block device, then you can do like this:
```
nohup python3 sysbenchRun.py --inst 1 --output /home/john --time 300 --type benchDisk --disk nvme1n1 --debug &
```

How to use the parameter:
* *--type benchDisk*: used to indicate that you'll run against one disk
* *--disk nvme1n1*: means you'll use device *nvme1n1* to store the database
* Other parameters are the same as default test

5. Run MySQL benchmark for CAS Configuration
The tool *casBaseLine.py* can be used to do a sysbench test for MySQL to see whethre the Intel CAS may help for your mysql performance.

How to use this command:
```
nohup python3 sysbenchRun.py --inst 1 --output /home/john --time 300 --type benchCAS --caching nvme1n1 --core sda &
```

How to use the parameter:
* *--bench benchCAS*: means we'll do an *intelcas* mysql validation
* *--caching nvme1n1*: means we'll use *nvme1n1* as the caching device to do acceleration
* *--core sda*: means we'll use *sda* as the core device which is supposed to be accelerated
In fact, these bench marks will do:
a) Use caching device *nvme1n1* to run MySQL and capture the performance
b) Use core device *sda* to run MySQL and capture the performance
c) Configure Intel CAS drive *intelcas1-1* using *nvme1n1* as caching device and *sda* as core device and then run MySQL on *intelcas1-1* 
d) By comparing the MySQL performance on *nvme1n1*, *sda* and *intelcas1-1*, we can know whether Intel CAS can help.

6. Run bench against multipe block devices
```
nohup python3 sysbenchRun.py --inst 1 --output /home/john -time 300 --type benchMoreDiskS --diskset nvme1n1,sda & 
```

How to understand the parameter:
* *--type benchMoreDiskS*: means we'll trigger bench against a list of disks
* *-diskset nvme1n1,sda*: means we'll trigger bench against two disks: *nvme1n1* and *sda*

7. Advanced Options for running all kinds of bench mark
There are two advanced options to control the benchmark task:
* *-debug*: when enable, will log more debug information during test
* *-skipPrep*: when enable, will skip the phase of preparing data for database, the customer needs to make sure the data is already in *datadir* of the database

## Baseline performance validation against one cache/core pair using CAS
The tool casBaseLine.py can be used to trigger one baseline performance validation against one cache/core pair.

Before running this tool, you need to do:
* Install Open CAS 
* Install fio
* Install Python 3

Configure Your Test:
* Prepare */etc/opencas/opencas.conf*
  * Refer to https://open-cas.github.io/guide_configuring.html for details
  * You should specify the caching device and core devices you want to test
  * Multiple caching devices and cores are supported
* Prepare *task.cnf* in the directory where you download this tool set
  * This file is used to control how your FIO should run


Example of */etc/opencas/opencas.conf*:
* With this conf file, the test will use */dev/nvme2n1* as caching device and */dev/sdc* as the core device
* By default, this test will be do:
  * Run FIO against caching device */dev/nvme2n1*, collect its IOPS/BW
  * Run FIO against core device */dev/sdc*, collect its IOPS/BW
  * Configure device *cas1-1* using caching device */dev/nvme2n1* and core device */dev/sdc*, then run FIO against *cas1-1* and collect its IOPS/BW
```
[caches]
## Cache ID     Cache device                            Cache mode      Extra fields (optional)
1               /dev/nvme2n1 WB

## Core devices configuration
[cores]
## Cache ID     Core ID         Core device
1               1               /dev/sdc
```

Example of *task.cnf*
* The test will cover FIO workload *read,randread,write,randwrite*
* For *read*, will try FIO with *"numjob=1", "iodepth=8" and "bs=128K"*
* For *randread*, will try FIO with *"numjob=8" and "bs=4k"/"bs=8k"*
```
[fio_global]
rwList=read,write,randread,randwrite,randrw
time=120

[read]
numjobs=1
iodepth=8
bs=128k

[write]
numjobs=1,4
iodepth=8
bs=64k,128k

[randwrite]
numjobs=8
iodepth=8
bs=4k,8k

[randread]
numjobs=8
iodepth=8,16,32
bs=4k,8k

[randrw]
numjobs=8
iodepth=8
bs=4k,8k
rwmixread=70
random_distribution=zipf:1.2
```

Usage Help
```
[root@sm116 Smart-Storage]# python3 casBaseLine.py -h
You are running Open CAS 19.06.00.00000801
You are running Open CAS 19.06.00.00000801
usage: casBaseLine.py [-h] --output dir [--cascfg casCfg] [--case testCase]
                      [--debug]

optional arguments:
  -h, --help       show this help message and exit
  --output dir     The dir to contain the perf data, eg. /home/you
  --cascfg casCfg  The intelcas.conf file to use for test
  --case testCase  By default, all test cases would be covered. Or you can
                   choose one single test caes to run:['all', 'cachingOnly',
                   'coreOnly', 'casOnly']
  --debug          Enable debug mode
```

Default Usage:
```
[root@apss117t Smart-Storage]# python3 casBaseLine.py --output /home/john/
```

This is what the above command will do:
* Configure CAS using */etc/opencas/opencas.conf*
* Run FIO based on *task.cnf*

Here is the log example:
```
[root@apss117t 2019_05_05_22h_31m]# pwd
/home/john/casBaseLineData/2019_05_05_22h_31m
[root@apss117t 2019_05_05_22h_31m]# ls *.log
smart-storage-2019-05-05-22h-31m.log
```

Here is the CSV file for CAS Perf Stats:
```
[root@apss117t 2019_05_05_22h_31m]# ls -ll cas*.csv
-rw-r--r-- 1 root root 38209 May  6 00:07 casPerfStats_2019_05_05_22_31.csv
```

Here is the CSV files for iostat, there is one CSV file each workload:
```
[root@apss117t 2019_05_05_22h_31m]# ls -ll *.csv
-rw-r--r-- 1 root root  4338 May  5 23:53 RandReadHit_IOStat_2019_05_05_23_38.csv
-rw-r--r-- 1 root root  4348 May  5 23:23 RandWriteHit_IOStat_2019_05_05_23_08.csv
-rw-r--r-- 1 root root  3980 May  6 00:07 RandWriteMiss_IOStat_2019_05_05_23_53.csv
-rw-r--r-- 1 root root  4369 May  5 23:38 SeqReadHit_IOStat_2019_05_05_23_23.csv
-rw-r--r-- 1 root root  4421 May  5 23:08 SeqWriteHit_IOStat_2019_05_05_22_53.csv
-rw-r--r-- 1 root root  4304 May  5 22:53 SeqWriteMiss_IOStat_2019_05_05_22_38.csv
-rw-r--r-- 1 root root  1601 May  5 22:38 WriteSpeedCheck_IOStat_2019_05_05_22_32.csv
```

Advanced Parameters:
* *--case testCase*: used to specify only one workload to run
  * cachingOnly, coreOnly, casOnly
* *--debug*: which will enable debug mode with more traces

## Collect CAS related devices' CAS Perf and IOSTAT Data
Tool *collectStats.py* is used to collect Intel CAS related stats:
* Those drives' workload will be collected:
  * Intelcasx-x
  * Caching Devcies
  * Core Devices
* Those data will be collected:
  * *iostat* data
  * Caching Perf Data using *"casadm -P"* 

How to use this tool:
[root@sm116 Smart-Storage]# python3 collectStats.py -h
usage: collectStats.py [-h] -C Cycle_Time -T Running_Time -O Output_Dir

optional arguments:
  -h, --help       show this help message and exit
  -C Cycle_Time    Duration of Monitor Cycle by Seconds
  -T Running_Time  Total Monitor Time by Seconds
  -O Output_Dir    Output Dir

Example Usage
```
python collectStats.py -C 60 -T 1200 -O /home/john &
```
The above command will try to collect CAS Perf and IOSTAT information for all CAS related device:
* Every 60 seconds per cycle (*-S*)
* Keep running 1200 seconds (*-T*)
* Data will be in /home/john/time-stamp