# Smart-Storage
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
