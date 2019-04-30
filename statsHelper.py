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

from adminHelper import *
from loggerHelper import *

'''
This script is supposed to use only standard python 2.7 library,
because our CAS code only expects the standard python 2.7.
And it is limited to generate raw CSV files with raw data.
The futher analysis against those raw csv files will be done by
advanced python scripts with more advanced libraries.
'''

# This class is used to do our own time working
class CasPerfStats:
    def __init__(self, interval_seconds, cycle_num, dataDir, finish = threading.Event()):
        self.dump_header = True
        self.timeStarted = MyTimeStamp.getAppendTime()
        self.interval = interval_seconds
        self.cycles = cycle_num
        self.dataDir    = dataDir
        self.finish = finish

    def startCollectStats(self, cacheID = INVALID_CACHE_ID):
        cycles = self.cycles
        self.filterCacheID = cacheID
        while (cycles):
            if (self.finish.isSet()):
                logMgr.info("Got FIO finish notification, Exit CAS Stats Collection")
                return 0
            time_seconds_now = datetime.datetime.now().time().second
            seconds_to_wait = (self.interval - (time_seconds_now % self.interval))
            # print "Wait {0}".format(seconds_to_wait)
            cycle_run = Timer(seconds_to_wait, self.getCycleStats, ())
            cycle_run.start()
            cycle_run.join()
            cycles -= 1
        logMgr.info("Exit CAS Stats Collection")
        return 0

    def getDumpFilePath(self):
        return os.path.join(self.dataDir, "casPerfStats_{0}.csv".format(self.timeStarted))

    def dumpOneDataLine(self, line, cache_id):
        (date_str, time_str) = MyTimeStamp.getDateAndTime(SECOND)
        new_line = "{0}, {1}, {2}, {3}\n".format(date_str, time_str, cache_id, line)
        outF = open(self.getDumpFilePath(), "a")
        outF.writelines(new_line)
        outF.close()
        return 0
    
    def getRawStats(self, cache_id, core_id):
        stats_cmd = 'casadm -P -i {0} -j {1} -o csv'.format(cache_id, core_id)
        stats_output = subprocess.check_output(stats_cmd, shell=True)
        return stats_output

    def resetPerfStat(self, cache_id, core_id):
        reset_cmd = 'casadm -Z -i {0} -j {1}'.format(cache_id, core_id)
        stats_output = subprocess.check_output(reset_cmd, shell=True)
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
            new_header = "{0},{1},{2},{3}\n".format("Date", "Time", "Cache Id", lines[0])
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
        (cache_inst_list, cache_volume_list) = casAdmin.fetchCacheVolumeSet()
        for cache_volume in cache_volume_list:
            if (INVALID_CACHE_ID == self.filterCacheID):
                pass
            elif (self.filterCacheID == cache_volume.cacheID):
                pass
            else:
                continue
            
            raw_info = self.getRawStats(cache_volume.cacheID, cache_volume.coreID)
            self.resetPerfStat(cache_volume.cacheID, cache_volume.coreID)
            self.parseRawStats(raw_info, cache_volume.cacheID)
        return 0


class IoStats:
    def __init__(self, interval_seconds, cycle_num, dataDir, testName = "", finish = threading.Event()):
        self.dump_header = True
        self.skip_Cycle = True
        self.timeStarted = MyTimeStamp.getAppendTime()
        self.interval = interval_seconds
        self.cycles = cycle_num
        self.finish = finish
        self.dataDir    = dataDir
        self.testName   = testName

    def startCollectStats(self, cacheDev = "", coreDev = "", cacheID = INVALID_CACHE_ID):
        cycles = self.cycles
        interval = self.interval

        # Wait for some seconds for time alignment
        time_seconds_now = datetime.datetime.now().time().second
        seconds_to_wait = (interval - (time_seconds_now % interval))
        time.sleep(seconds_to_wait)
    
        if (cacheDev and coreDev): # Specify cache,core pair
            self.runIoStatToEnd(self.getDevCacheCorePair(cacheDev, coreDev))
        elif (INVALID_CACHE_ID != cacheID): # Specify cache ID
            self.runIoStatToEnd(self.getDevListByCacheId(cacheID))
        else: # Default
            self.runIoStatToEnd(self.getAllDev())
        return 0
    
    def getAllDev(self):
        (cache_instance_list, cache_volume_list) = casAdmin.fetchCacheVolumeSet()
        dev_list = ""

        for cache_volume in cache_volume_list:
            dev_list = "{0} {1} {2}".format(dev_list, cache_volume.coreDisk, cache_volume.casDisk)

        for cache_instance in cache_instance_list:
            dev_list = "{0} {1}".format(dev_list, cache_instance.cacheDisk)

        return dev_list
    
    def getDevListByCacheId(self, cache_id):
        (cache_instance_list, cache_volume_list) = casAdmin.fetchCacheVolumeSet()
        coreDisk = ""
        casDisk = ""
        cacheDisk = ""

        for cache_volume in cache_volume_list:
            if cache_id == cache_volume.cacheID:
                coreDisk = cache_volume.coreDisk
                casDisk  = cache_volume.casDisk
                
        for cache_instance in cache_instance_list:
            print "cache_id {0}, cache_instance.cacheID {1}".format(cache_id, cache_instance.cacheID)
            if cache_id == cache_instance.cacheID:
                cacheDisk = cache_instance.cacheDisk
                
        return "{0} {1} {2}".format(coreDisk, casDisk, cacheDisk)
    
    # Return dev list for (cache, core) pair and its intelcasx-x
    # Will wait until the cache instance configured for cache/core pair
    def getDevCacheCorePair(self, cacheDev, coreDev):
        while (True):
            casDisk = casAdmin.getIntelDiskByCoreDev(coreDev)
            if (casDisk):
                return "{0} {1} {2}".format(cacheDev, coreDev, casDisk)
            else:
                logMgr.info("**WARNING** CAS not configured on {0}, sleep 30s and wait".format(coreDev))
                time.sleep(30)
        
    def getDumpFilePath(self):
        if self.testName:
            return os.path.join(self.dataDir, 
                                "{0}_IOStat_{1}.csv".format(self.testName, self.timeStarted))
        else:
            return os.path.join(self.dataDir, "IOStat_{0}.csv".format(self.timeStarted))

    def dumpOneDataLine(self, line):
        (date_str, time_str) = MyTimeStamp.getDateAndTime(SECOND)
        new_line = "{0},{1},{2}\n".format(date_str, time_str, line)
        outF = open(self.getDumpFilePath(), "a")
        outF.writelines(new_line)
        outF.close()
        return 0
        
    def dumpHeaderLine(self, line):
        new_header = "{0}, {1}, {2}\n".format("Date", "Time", line)
        outF = open(self.getDumpFilePath(), "w+")
        outF.writelines(new_header)
        outF.close()
        self.dump_header = False
        return 0

    # Always pass the 1st cycle data as it NOT average by iostat design
    def parseOneLine(self, line, dev_list):
        # First Cycle
        if (True == self.dump_header and line.startswith('Device:')):
            header = line.replace('Device:', 'Device')
            header = re.sub("\s+", ",", header)
            self.dumpHeaderLine(header)
            return 0
        # Hit beginning of second cylce, not skip anymore
        elif (True == self.skip_Cycle and line.startswith('Device:')):
            self.skip_Cycle = False
            return 0
        # Still not hitting second cycle, skip
        elif (True == self.skip_Cycle):
            # DEBUG
            # logMgr.info("Skip {0}".format(line))
            return 0
        
        words = line.split()
        if len(words) and (words[0] in dev_list):
            line = re.sub("\s+", ",", line)
            self.dumpOneDataLine(line)

        return 0      


    def runIoStatToEnd(self, dev_list):
        iostat_cmd = 'iostat -xmtd {0} {1} {2}'.format(dev_list, self.interval, self.cycles)

        logMgr.info("Starting: {0}".format(iostat_cmd))

        process = subprocess.Popen(shlex.split(iostat_cmd), stdout=subprocess.PIPE)
        while True:
            if self.finish.isSet():
                logMgr.info("Got FIO finish notification, Exit IO Stats Collection")
                return 0
            
            line = process.stdout.readline()
            if '' == line and process.poll() is not None:
                break
            if line:
                line = line.strip()
                self.parseOneLine(line, dev_list)
        rc = process.poll()
        logMgr.info("Time Up, Exit IO Stats Collection")
        return rc
