# Smart-Storage
## Baseline performance validation against one cache/core pair using CAS
The tool *casBaseLine.py* can be used to trigger one baseline performance validation against one cache/core pair.
Example Usage
```
[root@sm119 Smart-Storage]# python ./casBaseLine.py -cache /dev/nvme0n1 -core /dev/sdb -output /home/john/Smart-Storage/ &
[1] 12735
[root@sm119 Smart-Storage]# ps -ef | grep python
root     12735 12461  0 16:07 pts/0    00:00:00 python ./casBaseLine.py -cache /dev/nvme0n1 -core /dev/sdb -output /home/john/Smart-Storage/
```
This is what the above command will do:
* Use */dev/nvme0n1* as cache device and */dev/sdb* as core device to do CAS configure
* Will trigger all kinds of workload against the exposed cached drive (eg. *intelcas1-1)
  * Rand/Seq Read/Write Miss/Hit cases
  * Will also collect IOSTAT and CAS Stats (based on tool *collectStats.py)
  
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
