# Smart-Storage
Use here to track the code for workload analysis 

## How to Trigger the cmd
*python stats_collect.py -C 20 -T 600 -O /root/Smart-Storage/data &*
- Will keep collecting the iostat and "casadm -P -i" for 600 (-T) seconds
- Collect the data every 20 (-C) seconds
- The generated data would be put in /root/Smart-Storage/data, need to make sure the directory does exist
- After execution, those  CSVfiles will be generated:
  - -rw-r--r-- 1 root root    435 Mar 24 20:41 casadmL_2019_03_24_20_41.csv
  - -rw-r--r-- 1 root root 175315 Mar 24 20:51 IOStat_2019_03_24_20_41.csv
  - -rw-r--r-- 1 root root 208757 Mar 24 21:03 casPerfStats_2019_03_24_20_41.csv
