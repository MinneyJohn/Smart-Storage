#! /usr/bin/python3

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
This script is supposed to use only standard python 3.6 library,
because our CAS code only expects the standard python 3.6.
And it is limited to generate raw CSV files with raw data.
The futher analysis against those raw csv files will be done by
advanced python scripts with more advanced libraries.
'''

class cycleStatsCollector:
    def __init__(self, cycleTime, runTime, dataDir, kwargs = {}):
        self._cycleTime = cycleTime
        self._runTime   = runTime
        self._dataDir   = dataDir
        self._csvFile   = ""
        self._hasHeader = False
        self._kwargs    = kwargs
        #self.handleKwargs(self._kwargs)
        
        # This is the args for parsing one line 
        self._kwargs_parse = {} 

    # No need to redefine
    def start(self):
        self.handleKwargs(self._kwargs)
        self.getCsvFile()
        runTask = scheduleTask(self.cycleRun, self._cycleTime, self._runTime)
        return runTask.start()
    
    # When parsing each line, may need extra, this is the kwargs for
    def setParseKwargs(self, kwargs):
        self._kwargs_parse = kwargs

    # No Need to redefine
    def cycleRun(self):
        lines = self.getCycleOutPut()
        self.parseCycleValues(lines)
        return 0

    # No need to redefine
    def getCsvFile(self):
        if "" == self._csvFile:
            self._csvFile = os.path.join(self._dataDir, \
                                        "{0}_{1}.csv".\
                                        format(self.__class__.__name__, 
                                                MyTimeStamp.getAppendTime()) )
        return self._csvFile      
    
    # No need to redefine
    def parseCycleValues(self, lines):
        if (False == self.validateCycleOutPut(lines)):
            return False

        if (False == self._hasHeader and self.generateHeader(lines)):
            self._hasHeader = True

        for line in lines:
            csvLine = self.parseOneLine(line)    
            if csvLine:
                outF = open(self.getCsvFile(), "a")
                outF.writelines(csvLine)
                outF.close()
        


    # Please define if necessary
    def validateCycleOutPut(self, lines):
        return True

    # Please define
    def getCycleOutPut(self):
        return ""

    # Please define
    # Assumption: The header is supposed to be able to generated from one cylce's output
    def generateHeader(self, lines):
        return False

    # Please define
    # Return String: the CSV line will be written into CSV file
    def parseOneLine(self, line):
        return ""
    
    # Please define is necessary
    def handleKwargs(self, kwargs):
        return 0

class casPerfStats(cycleStatsCollector):
    def getRawStats(self, cache_id, core_id): # class specific function
        stats_cmd = 'casadm -P -i {0} -j {1} -o csv'.format(cache_id, core_id)
        (ret, output) = casAdmin.getOutPutOfCmd(stats_cmd)
        if 0 == ret:
            return output
        else:
            return ""
        
    def resetPerfStat(self, cache_id, core_id):
        reset_cmd = 'casadm -Z -i {0} -j {1}'.format(cache_id, core_id)
        (ret, output) = casAdmin.getOutPutOfCmd(reset_cmd)
        if 0 == ret:
            return output
        else:
            return ""
    
    def handleKwargs(self, kwargs):
        if "cacheID" in kwargs:
            self._filterCacheID = kwargs['cacheID']
        else:
            self._filterCacheID = INVALID_CACHE_ID
        
    def parseOneLine(self, line):
        if "cacheID" not in self._kwargs_parse:
            return ""

        cacheID = self._kwargs_parse['cacheID']
        (dateStr, timeStr) = MyTimeStamp.getDateAndTime(SECOND)
        new_line = "{0}, {1}, {2}, {3}\n".format(dateStr, timeStr, cacheID, line)
        return new_line
    
    def generateHeader(self, lines):
        new_header = "{0},{1},{2},{3}\n".format("Date", "Time", "Cache Id", lines[0])
        outF = open(self.getCsvFile(), "w+")
        outF.writelines(new_header)
        outF.close()
        return True
        
    def validateCycleOutPut(self, lines):
        if (1 >= len(lines)):
            return False
        if (False == lines[0].startswith("Core Id,Core Device,Exported Object")):
            return False

        return True

    def getCycleOutPut(self):
        raw_info = ""

        (cache_inst_list, cache_volume_list) = casAdmin.fetchCacheVolumeSet()
        for cache_volume in cache_volume_list:
            if (INVALID_CACHE_ID == self._filterCacheID):
                pass
            elif (self._filterCacheID == cache_volume.cacheID):
                pass
            else:
                continue
            
            raw_info = self.getRawStats(cache_volume.cacheID, cache_volume.coreID)
            
            # Set kwargs for one line parsing
            self.setParseKwargs({'cacheID': cache_volume.cacheID})

            self.resetPerfStat(cache_volume.cacheID, cache_volume.coreID)
        return raw_info.splitlines()

class mysqlBufferPoolStats(cycleStatsCollector):
    mySqlFileDir = "/var/lib/mysql-files/"
    headerFile = ""
            
    def convertHeaderToCSV(self, rawFile):
        fh = open(rawFile, "r")
        lines = fh.read().splitlines()
        header_str = ""
        for line in lines:
            if (header_str):
                header_str = "{0},{1}".format(header_str, line)
            else:
                header_str = line
        header_str = "{0}, {1}, {2}\n".format("Date", "Time", header_str)
        fh.close()

        fh = open(rawFile, "w+")
        fh.write(header_str)
        fh.close()

    def handleKwargs(self, kwargs):
        if "instID" in kwargs:
            self._instID = kwargs['instID']
        else:
            self._instID = INVALID_MYSQL_ID
        
        if "pwd" in kwargs:
            self._pwd = kwargs['pwd']
        else:
            self._pwd = ""
        
    def getCycleOutPut(self):
        cycleFile = os.path.join(self.__class__.mySqlFileDir, "bufferPoolStatsCycle.csv")
        if (os.path.exists(cycleFile)):
            os.remove(cycleFile) # Have to remove for SQL to generate it
        
        (dateStr, timeStr) = MyTimeStamp.getDateAndTime(SECOND)

        sock = mySqlCfg.queryOpt(self._instID, "socket")
        port = mySqlCfg.queryOpt(self._instID, "port")
        queryStsm = "SELECT * FROM information_schema.INNODB_BUFFER_POOL_STATS "\
                    " INTO OUTFILE '{0}' FIELDS TERMINATED BY ','".format(cycleFile)
        (ret, output) = mySqlInst.executeSqlStsm(self._instID, queryStsm, self._pwd)
        if ret:
            return ret
        # Read cycle number from the csv file
        cycleFle_fh = open(cycleFile, "r")
        cycle_lines = cycleFle_fh.read().splitlines()
        cycleFle_fh.close()
        os.remove(cycleFile)
        return cycle_lines
    
    def parseOneLine(self, line):
        (dateStr, timeStr) = MyTimeStamp.getDateAndTime(SECOND)
        return("{0}, {1}, {2}\n".format(dateStr, timeStr, line))
            
    def generateHeader(self, lines):
        tmpHeaderFileName = os.path.join(self.__class__.mySqlFileDir, \
                                        "bufferPoolStatsHeader.{0}.csv"\
                                        .format(MyTimeStamp.getAppendTime()))
        targetHeaderFileName = os.path.join(logMgr.getDataDir(), "bufferPoolStatsHeader.csv")

        headerStsm = "SELECT column_name FROM information_schema.columns WHERE table_schema = 'information_schema' "\
                     " AND table_name = 'INNODB_BUFFER_POOL_STATS' INTO OUTFILE '{0}'"\
                     .format(tmpHeaderFileName)
        (ret, output) = mySqlInst.executeSqlStsm(self._instID, headerStsm, self._pwd)
        if (1 == ret):
            return False
        shutil.move(tmpHeaderFileName, targetHeaderFileName)
        # os.rename(tmpHeaderFileName, targetHeaderFileName)
        self.convertHeaderToCSV(targetHeaderFileName)

        header_fh = open(targetHeaderFileName, "r")
        header_lines = header_fh.read().splitlines()
        header_fh.close()

        csvFile_fh = open(self.getCsvFile(), "a+")
        for line in header_lines:
            csvFile_fh.write("{0}\n".format(line))
        csvFile_fh.close()

        return True

class longRunStatsCollector():
    def __init__(self, cycleTime, runTime, dataDir, kwargs = {}):
        self._cycleTime = cycleTime
        self._runTime   = runTime
        self._dataDir   = dataDir
        self._kwargs    = kwargs
        self._csvFile   = ""
        self._hasHeader = False

        # Args for parsing one line
        self._kwargs_parse = {}

    def start(self):
        self.handleKwargs(self._kwargs)
        self.getCsvFile()
        (ret, runningThread) = longTask(self.runStats, align = self._cycleTime).start()
        return (ret, runningThread)
    
    def handleKwargs(self, kwargs):
        return 0

    def getCsvFile(self):
        if "" == self._csvFile:
            self._csvFile = os.path.join(self._dataDir, \
                                        "{0}_{1}.csv".\
                                        format(self.__class__.__name__, 
                                                MyTimeStamp.getAppendTime()) )
        return self._csvFile     
    
    def generateRunCommand(self):
        return cmd
    
    def parseOneLine(self, line):
        return ""

    def setParseKwargs(self, kwargs):
        self._kwargs_parse = kwargs

    def generateHeader(self, line):
        return False

    def runStats(self):
        runCmd = self.generateRunCommand()

        process = subprocess.Popen(shlex.split(runCmd), stdout=subprocess.PIPE)
        while True:
            line = process.stdout.readline().decode()
            if line == '' and process.poll() is not None:
                logMgr.debug("Finish of {0}".format(runCmd))
                break
            if line:
                if (False == self._hasHeader and self.generateHeader(line)):
                    self._hasHeader = True

                csvLine = self.parseOneLine(line)
                if csvLine:
                    outF = open(self.getCsvFile(), "a")
                    outF.writelines(csvLine)
                    outF.close()

        rc = process.poll()
        
        logMgr.debug("Time Up, Exit {0}".format(runCmd))
        return rc

class ioStats(longRunStatsCollector):   
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
            if cache_id == cache_instance.cacheID:
                cacheDisk = cache_instance.cacheDisk
                
        return "{0} {1} {2}".format(coreDisk, casDisk, cacheDisk)
    
    def handleKwargs(self, kwargs):
        if "devList" in kwargs:
            self._devList = kwargs['devList']
        else:
            self._devList = ""
        
        if "cacheID" in kwargs:
            self._cacheID = kwargs['cacheID']
        else:
            self._cacheID = INVALID_CACHE_ID
        
        self._hitCycle = 0
            
    def generateHeader(self, line):
        if line:
            if line.startswith('Device:'):
                header = line.replace('Device:', 'Device')
                header = re.sub("\s+", ",", header)
                new_header = "{0}, {1}, {2}\n".format("Date", "Time", header)
                outF = open(self.getCsvFile(), "w+")
                outF.writelines(new_header)
                outF.close()
                return True
        return False

    def parseOneLine(self, line):
        if "devList" in self._kwargs_parse:
            devList = self._kwargs_parse['devList']
        else:
            return ""

        if line.startswith('Device:'):
            self._hitCycle += 1
        
        if (1 >= self._hitCycle): # Only record since 2 cycles
            return ""
    
        words = line.split()
        if len(words) and (words[0] in devList):
            line = re.sub("\s+", ",", line)
            (dateStr, timeStr) = MyTimeStamp.getDateAndTime(SECOND)
            new_line = "{0},{1},{2}\n".format(dateStr, timeStr, line)
            return new_line
        return ""
    
    def generateRunCommand(self):
        if (self._devList): # Specify cache,core pair
            self._devToCollect = self._devList
        elif (INVALID_CACHE_ID != self._cacheID): # Specify cache ID
            self._devToCollect = self.getDevListByCacheId(self._cacheID)
        else: # Default
            self._devToCollect = self.getAllDev()

        iostatCmd = 'iostat -xmtd {0} {1} {2}'.format(self._devToCollect, 
                                                        self._cycleTime, 
                                                        int(self._runTime / self._cycleTime))
        
        # Set kwargs for one line parsing
        self.setParseKwargs({'devList': self._devToCollect})
        return iostatCmd


'''
root@sm114 Smart-Storage]# mpstat 2 2
Linux 3.10.0-862.el7.x86_64 (sm114.lab7217.local)       07/08/2019      _x86_64_        (88 CPU)

09:51:24 PM  CPU    %usr   %nice    %sys %iowait    %irq   %soft  %steal  %guest  %gnice   %idle
09:51:26 PM  all   37.58    0.00   11.17    0.60    0.00    0.00    0.00    0.00    0.00   50.66
09:51:28 PM  all   38.36    0.00   11.17    0.61    0.00    0.00    0.00    0.00    0.00   49.86
Average:     all   37.97    0.00   11.17    0.60    0.00    0.00    0.00    0.00    0.00   50.26
'''
class cpuUsageStats(longRunStatsCollector):
    def generateHeader(self, line):
        header = ""
        m = re.match(r"(.*)CPU(.*)(usr)(.*)(sys)(.*)", line)
        if m:
            words = line.split()
            N_word = len(words)
            if ("PM" == words[1]):
                words[0] = "Date"
                words[1] = "Time"
            for word in words:
                if ("" == header):
                    header = word
                else:
                    header = "{0}, {1}".format(header, word)
            header = "{0}\n".format(header)
            outF = open(self.getCsvFile(), "w+")
            outF.writelines(header)
            outF.close()
            return True
        return False

    def parseOneLine(self, line):
        m = re.match(r"(.*)(?P<hour>\d+):(?P<min>\d+):(?P<sec>\d+)(\s+)(?P<noon>(PM|AM))(\s+)(all)(.*)", line)
        if (m):
            hour    = int(m.group('hour'))
            minute  = int(m.group('min'))
            second  = int(m.group('sec'))
            if ("PM" == m.group('noon')):
                hour += 12
            (dateStr, timeStr) = MyTimeStamp.getDateAndTime(SECOND)
            timeStr = "{0:02d}:{1:02d}:{2:02d}".format(hour, minute, second)
            words = line.split()
            words[0] = dateStr
            words[1] = timeStr
            csvLine = ""
            for word in words:
                if ("" == csvLine):
                    csvLine = word
                else:
                    csvLine = "{0}, {1}".format(csvLine, word)
            return "{0}\n".format(csvLine)
        return ""

    def generateRunCommand(self):
        mpstatCmd = 'mpstat {0} {1}'.format(self._cycleTime, 
                                            int(self._runTime / self._cycleTime))
        return mpstatCmd