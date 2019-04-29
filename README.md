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
* After the test is complete, some CSV files will be generated in /home/john/casBaseLineData/
  
## Collect all CAS related block devices' IOSTAT/CAS Perf data on one machine
The tool *collectStats.py* can be used collect CAS related block devices' IOSTAT/CAS Perf data. 
Example usage:
```
python collectStats.py -C 20 -T 600 -O /root/Smart-Storage/data &
```
This is what the above command will do:
- Will keep collecting the iostat and "casadm -P -i" for 600 (-T) seconds
- Collect the data every 20 (-C) seconds
- The generated data would be put in /root/Smart-Storage/data, need to make sure the directory does exist
- After execution, those  CSVfiles will be generated:
  - -rw-r--r-- 1 root root    435 Mar 24 20:41 casadmL_2019_03_24_20_41.csv
  - -rw-r--r-- 1 root root 175315 Mar 24 20:51 IOStat_2019_03_24_20_41.csv
  - -rw-r--r-- 1 root root 208757 Mar 24 21:03 casPerfStats_2019_03_24_20_41.csv
