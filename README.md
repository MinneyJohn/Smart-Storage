# Smart-Storage
## Run Sysbench against MySQL
1. Tools you need to install before running this benchmark:
* MySQL
* sysbench
* Python 3
  * I am testing based on Python 3.6
* Also disable SElinux
  * Update /etc/selinux/config, change enforcing to disabled
  * Need one reboot to make the change effective

2. Types of benchwork supported now:
* Default Bench Mark
* Benchmark against one block device

3. Default Bench Mark
Configuration before starting the bench mark:
* Prepare your mysql configuration file which should be /etc/my.cnf
* Prepare the configuration file *task.cnf* for the benchmark

Prepare your configuration file like this:
* Please make sure you have one default section [mysqld]
  * It is used to do initial mysql setup
* Please make sure you have one configuration for one mysql instance [mysqld@X]
  * The configuration of this instance is what you'll use for your test
  * The *datadir* must be created before you running the test
* There should be NO conflict between the default [mysqld] and you instance [mysqld@X] configuration
  * Eg. the page size must be the same
  
Here is one example I am using now:
```
[root@sm114 2019_07_11_01h_08m]# cat /etc/my.cnf
[mysqld]
datadir=/var/lib/mysql
socket=/var/lib/mysql/mysql.sock
user=mysql
log_error=/var/log/mysqld.log
# Disabling symbolic-links is recommended to prevent assorted security risks
symbolic-links=0
innodb_file_per_table=1
innodb_read_io_threads=64
innodb_write_io_threads=32
innodb_thread_concurrency=0
innodb_log_file_size=1024M
innodb_io_capacity=100000
innodb_log_buffer_size=64M
innodb_buffer_pool_size=32G
innodb_buffer_pool_instances=12
default_authentication_plugin=mysql_native_password
default_password_lifetime=0

innodb_page_size=4096

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

Here is one example of *task.cnf*:
* *THREAD_NUM_LIST* is used to set the threads you are going to loop when running sysbench
* *STATS_CYCLE* is used to set the cycle time to collect perf stats by seconds
* *DB_NAME* is used to as database name for test, *PWD* is the password for the database
* *DYNAMIC_BUFFER_POOL_SIZE* is to indicate whether we'll loop different buffer pool size or NOT
```
[sysbench]
THREAD_NUM_LIST=100, 128
STATS_CYCLE=5
DB_NAME=sbtest
PWD=intel123
DYNAMIC_BUFFER_POOL_SIZE=Fales

#If you want to try multiple threads
#THREAD_NUM_LIST=100,128,256
#DYNAMIC_BUFFER_POOL_SIZE=False
```

Here is how to trigger the test:
```
nohup python sysbenchRun.py -inst 1 -tables 10 -rows 1000000 -output /home/john -time 300 &
```
This is what the test will do:
* Use the mysql configuration for instance 1 which is section [mysqld@1]
* The test database will have 10 tables with 1000000 rows for each
* The test log and perf data will be put in directory */home/john
* For each sysbench command, it will run 300 seconds

4. Bench against one block device
Configuration:
* Do the same mysql and task.cnf same as the default bench
* But make sure the "datadir" for your test mysql instance does NOT exist

Here is how to trigger the test:
```
nohup python sysbenchRun.py -inst 1 -tables 10 -rows 1000000 -output /home/john -time 300 -bench disk -blkDev nvme0n1 &
```
This is what the test will do:
* It will mount device *nvme0n1* to the *datadir* configured in the my.cnf
* Then trigger sysbench against that datadir

## Baseline performance validation against one cache/core pair using CAS
The tool *casBaseLine.py* can be used to trigger one baseline performance validation against one cache/core pair.  
   
How to use this command
```
[root@apss117t Smart-Storage]# python casBaseLine.py -h
usage: casBaseLine.py [-h] -cache cacheDev -core coreDev -output dir
optional arguments:
  -h, --help       show this help message and exit
  -cache cacheDev  The device of cache, eg. /dev/nvme
  -core coreDev    The device of core, eg. /dev/sdb
  -output dir      The dir to contain the perf data, eg. /home/you
```

Example Usage
```
[root@apss117t Smart-Storage]# python casBaseLine.py -cache /dev/nvme0n1p7 -core /dev/sdb6 -output /home/john/casBaseLineData/ &
Start doing baseline CAS test using cache /dev/nvme0n1p7 and core /dev/sdb6
The performance CSV files are in /home/john/casBaseLineData/
Running log is /home/john/casBaseLineData/smart-storage-2019-04-29-02h-33m.log
Please do NOT do CAS configuration during this test progress
Just One Minute, Am estimating the running time................
Estimated Running Time 105 minutes
[root@apss117t Smart-Storage]# ps -ef | grep python
root       46992   36968  0 02:33 pts/0    00:00:00 python casBaseLine.py -cache /dev/nvme0n1p7 -core /dev/sdb6 -output /home/john/casBaseLineData/
```
This is what the above command will do:
* Use */dev/nvme0n1p7* as cache device and */dev/sdb6* as core device to do CAS configure
* Will trigger all kinds of workload against the exposed cached drive (eg. *intelcas1-1)
  * Rand/Seq Read/Write Miss/Hit cases
  * Will also collect IOSTAT and CAS Stats
* After the test is complete, data and logs will be generated in /home/john/casBaseLineData/

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

## Collect CAS related devices' CAS Perf and IOSTAT Data
Example Usage
```
python collectStats.py -C 60 -T 1200 -O /home/john &
```
The above command will try to collect CAS Perf and IOSTAT information for all CAS related device:
* Every 60 seconds per cycle (*-S*)
* Keep running 1200 seconds (*-T*)
* Data will be in /home/john/time-stamp
