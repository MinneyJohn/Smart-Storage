#! /usr/bin/python

import subprocess
import threading
import time
import re
import string
import datetime
import os
from threading import Timer
import argparse
import shlex

SECOND = "SECOND"
MINUTE = "MINUTE"

'''
This script is supposed to use only standard python 2.7 library,
because our CAS code only expects the standard python 2.7.
And it is limited to generate raw CSV files with raw data.
The futher analysis against those raw csv files will be done by
advanced python scripts with more advanced libraries.
'''

# This class is used to do our own time working
class MyTimeStamp():
    def __init__(self):
        return 0
    
    @classmethod
    def getAppendTime(cls):
        return datetime.datetime.now().strftime("%Y_%m_%d_%H_%M")
    
    # Used to get the timestamp with seconds or minutes
    # By default, it is by minute
    @classmethod
    def getTimeStamp(cls, time_granularity=""):
        if (SECOND == time_granularity):
            return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        elif (MINUTE == time_granularity):
            return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        else:
            return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


# This class is for cache instance
class CacheInstance():
    def __init__(self, cache_id, cache_disk):
        self.cacheID = cache_id
        self.cacheDisk = cache_disk
    
    def __eq__(self, other):
        return (self.cacheID == other.cacheID)

    def __hash__(self):
        return hash(self.cacheID)

    def __str__(self):
        return "{0}, {1}".format(self.cacheID, self.cacheDisk)

# This class is for cache volume which is cache-core pair
class CacheVolume():
    def __init__(self, cache_id, core_id, core_disk, cas_disk):
        self.cacheID = cache_id
        self.coreID = core_id
        self.coreDisk = core_disk
        self.casDisk = cas_disk
    
    def __eq__(self, other):
        return (self.cacheID == other.cacheID and self.coreID == other.coreID)

    def __hash__(self):
        return hash((self.cacheID, self.coreID))

    def __str__(self):
        return "{0}, {1}, {2}, {3}".format(self.cacheID, self.coreID, self.coreDisk, self.casDisk)

# This class is used to fetch the running list of cache and core        
class SetOfCacheVolume:
    set_cache_volume = set()
    set_cache_instance = set()

    def __init__(self):
        return 0

    # /dev/intelcasn-m means device for cache n and core m
    @classmethod
    def getCacheCoreIdByDevName(cls, device_name):
        m = re.match(r"/dev/intelcas(?P<cache_id>\d+)-(?P<core_id>\d+)(\n)*", device_name)
        if (m):
            return (int(m.group('cache_id')), int(m.group('core_id')))
        else:
            print "Not found match"
            return (-1, -1)
    
    @classmethod
    def insertCacheInstance(cls, fields):
        #cls.list_cache_instance.append(CacheInstance(fields[1], fields[2]))
        cls.set_cache_instance.add(CacheInstance(fields[1], fields[2]))
        return 0
    
    @classmethod
    def insertCacheVolume(cls, fields):
        (cache_id, core_id) = cls.getCacheCoreIdByDevName(fields[5])
        if (-1 == cache_id or -1 == core_id):
            return 0
        else:
            # print "Append {0} {1}".format(cache_id, core_id)
            #cls.list_cache_volume.append(CacheVolume(cache_id, core_id, fields[2], fields[5]))
            cls.set_cache_volume.add(CacheVolume(cache_id, core_id, fields[2], fields[5]))
            return 0

    # Dump one line into the file after parsing
    @classmethod
    def dumpRawInfo(cls, output_str):
        dump_file = os.path.join(WORKING_DIR, "casadmL_{0}.csv".format(MyTimeStamp.getAppendTime()))
        outF = open(dump_file, "w")
        outF.writelines(output_str)
        outF.close()
        return 0
    
    # Get raw information from casadm cmd
    @classmethod
    def getRawInfo(cls):
        get_cache_core_list = 'casadm -L -o csv'
        stats_output = subprocess.check_output(get_cache_core_list, shell=True)
        # print stats_output
        return stats_output

    @classmethod
    def parseRawInfo(cls, output_str):
        lines = output_str.splitlines()
        for line in lines:
            words = line.split(',')
            if ('cache' == words[0]):
                cls.insertCacheInstance(words)
            elif ('core' == words[0] and words[5].startswith('/dev/intelcas')):
                cls.insertCacheVolume(words)
            else:
                pass
        return 0

    @classmethod
    def fetchCacheVolumeSet(cls):
        raw_output_str = cls.getRawInfo()
        cls.dumpRawInfo(raw_output_str)
        cls.parseRawInfo(raw_output_str)
        cls.set_cache_volume = sorted(cls.set_cache_volume)
        cls.set_cache_instance = sorted(cls.set_cache_instance)
        return 0

    @classmethod
    def showCacheVolumeSet(cls):
        print "We got those cache instances:"
        for cache_instance in cls.set_cache_instance:
            print cache_instance
        print "We got those cache volumes:"
        for cache_volume in cls.set_cache_volume:
            print cache_volume
        return 0
    
    @classmethod
    def getCacheVolumeSet(cls):
        return cls.set_cache_volume
    
    @classmethod
    def getCacheInstanceSet(cls):
        return cls.set_cache_instance
        

class CasPerfStats:
    def __init__(self, interval_seconds, cycle_num):
        self.dump_header = True
        self.timeStarted = MyTimeStamp.getAppendTime()
        self.interval = interval_seconds
        self.cycles = cycle_num

    def startCollectStats(self):
        cycles = self.cycles
        interval = self.interval
        while (cycles):
            time_seconds_now = datetime.datetime.now().time().second
            seconds_to_wait = (interval - (time_seconds_now % interval))
            # print "Wait {0}".format(seconds_to_wait)
            cycle_run = Timer(seconds_to_wait, self.getCycleStats, ())
            cycle_run.start()
            cycle_run.join()
            cycles -= 1
        return 0

    def getDumpFilePath(self):
        return os.path.join(WORKING_DIR, "casPerfStats_{0}.csv".format(self.timeStarted))

    def dumpOneDataLine(self, line, cache_id):
        time_str = MyTimeStamp.getTimeStamp(SECOND)
        new_line = "{0}, {1}, {2}\n".format(time_str, cache_id, line)
        outF = open(self.getDumpFilePath(), "a")
        outF.writelines(new_line)
        outF.close()
        return 0
    
    def getRawStats(self, cache_id, core_id):
        stats_cmd = 'casadm -P -i {0} -j {1} -o csv'.format(cache_id, core_id)
        stats_output = subprocess.check_output(stats_cmd, shell=True)
        return stats_output

    def parseRawStats(self, stats_output, cache_id):
        lines = stats_output.splitlines()
        # Make sure at least 2 lines for valid stats
        if (1 >= len(lines)):
            return 0
        
        # Verify 1st line is the header
        if (False == lines[0].startswith("Core Id,Core Device,Exported Object")):
            return 0
        elif (True == self.dump_header):
            # print "Dump header"
            new_header = "{0},{1},{2}\n".format("TimeStamp", "Cache Id", lines[0])
            outF = open(self.getDumpFilePath(), "w+")
            outF.writelines(new_header)
            outF.close()
            self.dump_header = False
        else:
            pass

        for line in lines[1:]:
            self.dumpOneDataLine(line, cache_id)
        
        return 0

    def getCycleStats(self):
        cache_volume_list = SetOfCacheVolume.getCacheVolumeSet()
        for cache_volume in cache_volume_list:
            # print "Trying to get stats for {0} {1}".format(cache_volume.cacheID, cache_volume.coreID)
            raw_info = self.getRawStats(cache_volume.cacheID, cache_volume.coreID)
            self.parseRawStats(raw_info, cache_volume.cacheID)
        return 0


class IoStats:
    def __init__(self, interval_seconds, cycle_num):
        self.dump_header = True
        self.timeStarted = MyTimeStamp.getAppendTime()
        self.interval = interval_seconds
        self.cycles = cycle_num

    def startCollectStats(self):
        cycles = self.cycles
        interval = self.interval

        # Wait for some seconds for time alignment
        time_seconds_now = datetime.datetime.now().time().second
        seconds_to_wait = (interval - (time_seconds_now % interval))
        time.sleep(seconds_to_wait)

        self.runIoStatToEnd(interval, cycles)

        return 0
    
    def getDumpFilePath(self):
        return os.path.join(WORKING_DIR, "IOStat_{0}.csv".format(self.timeStarted))

    def dumpOneDataLine(self, line):
        time_str = MyTimeStamp.getTimeStamp(SECOND)
        new_line = "{0},{1}\n".format(time_str, line)
        outF = open(self.getDumpFilePath(), "a")
        outF.writelines(new_line)
        outF.close()
        return 0
        
    def dumpHeaderLine(self, line):
        new_header = "{0}, {1}\n".format("TimeStamp", line)
        outF = open(self.getDumpFilePath(), "w+")
        outF.writelines(new_header)
        outF.close()
        self.dump_header = False
        return 0

    def parseOneLine(self, line, dev_list):
        if (True == self.dump_header and line.startswith('Device:')):
            header = line.replace('Device:', 'Device')
            header = re.sub("\s+", ",", header)
            self.dumpHeaderLine(header)
            return 0
        
        words = line.split()
        if len(words) and (words[0] in dev_list):
            line = re.sub("\s+", ",", line)
            self.dumpOneDataLine(line)

        return 0      

    def runIoStatToEnd(self, interval, cycles):
        cache_volume_list = SetOfCacheVolume.getCacheVolumeSet()
        cache_instance_list = SetOfCacheVolume.getCacheInstanceSet()
        dev_list = ""

        for cache_volume in cache_volume_list:
            dev_list = "{0} {1}".format(dev_list, cache_volume.coreDisk)
        
        for cache_volume in cache_volume_list:
            dev_list = "{0} {1}".format(dev_list, cache_volume.casDisk)

        for cache_instance in cache_instance_list:
            dev_list = "{0} {1}".format(dev_list, cache_instance.cacheDisk)

        iostat_cmd = 'iostat -xmtd {0} {1} {2}'.format(dev_list, interval, cycles)

        print iostat_cmd

        process = subprocess.Popen(shlex.split(iostat_cmd), stdout=subprocess.PIPE)
        while True:
            line = process.stdout.readline()
            if '' == line and process.poll() is not None:
                break
            if line:
                line = line.strip()
                self.parseOneLine(line, dev_list)
        rc = process.poll()
        print "Ready to exit runIoStatToEnd"
        return rc

'''
Used to calculate the cycle values for some columns
Maybe need to define as one class
'''

def setupArgsParser():
    global arg_parser
    
    arg_parser.add_argument('-C', type=int, metavar='Cycle_Time', required=True, help='Duration of Monitor Cycle by Seconds')
    arg_parser.add_argument('-T', type=int, metavar='Running_Time', required=True, help='Total Monitor Time by Seconds')
    arg_parser.add_argument('-O', type=str, metavar='Output_Dir', required=True, help='Output Dir')
    
    return 0

def verifyArgs(args):
    if False == os.path.isdir(args.O):
        print "Please create dir \"{0}\" and then rerun\n".format(args.O)
        exit(1)

if __name__ == "__main__": 
    arg_parser = argparse.ArgumentParser()
    setupArgsParser()
    args = arg_parser.parse_args()
    verifyArgs(args)

    CYCLE_TIME = args.C
    RUNNINGT_TIME = args.T
    WORKING_DIR = args.O

    print "\nAm going to collect CAS Perf Stats every {0} seconds;".format(CYCLE_TIME)
    print "Will keep running {0} seconds;".format(RUNNINGT_TIME) 
    print "Generated data would be in {0}.\n".format(WORKING_DIR)
   
    SetOfCacheVolume.fetchCacheVolumeSet()
    SetOfCacheVolume.showCacheVolumeSet()

    casPerfStatsObj = CasPerfStats(CYCLE_TIME, int(RUNNINGT_TIME/CYCLE_TIME))
    ioStatsObj = IoStats(CYCLE_TIME, int(RUNNINGT_TIME/CYCLE_TIME))

    # Create the thread
    t1 = threading.Thread(target=casPerfStatsObj.startCollectStats) 
    t2 = threading.Thread(target=ioStatsObj.startCollectStats) 
  
    # Start the thread 
    t1.start() 
    t2.start()
    
    # Wait for the thread
    t1.join()
    t2.join()

    # print "Finished"

    exit(0)