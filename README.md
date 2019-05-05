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
