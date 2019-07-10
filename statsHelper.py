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
            self.parseOneLine(line)    

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
    def parseOneLine(self, line):
        return 0
    
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
            return 1

        cacheID = kwargs['cacheID']
        (dateStr, timeStr) = MyTimeStamp.getDateAndTime(SECOND)
        new_line = "{0}, {1}, {2}, {3}\n".format(dateStr, timeStr, cacheID, line)
        outF = open(self.getCsvFile(), "a")
        outF.writelines(new_line)
        outF.close()
        return 0
    
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
        csvFile_fh = open(self.getCsvFile(), "a+")
        csvFile_fh.write("{0}, {1}, {2}\n".format(dateStr, timeStr, line))
        csvFile_fh.close()
            
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
        return 0

    def setParseKwargs(self, kwargs):
        self._kwargs_parse = kwargs

    def generateHeader(self, line):
        print("In Parent's generateHeader")
        return False

    def runStats(self):
        runCmd = self.generateRunCommand()

        process = subprocess.Popen(shlex.split(runCmd), stdout=subprocess.PIPE)
        while True:
            line = process.stdout.readline().decode()
            if line == '' and process.poll() is not None:
                logMgr.info("Finish of {0}".format(runCmd))
                break
            if line:
                if (False == self._hasHeader and self.generateHeader(line)):
                    self._hasHeader = True

                self.parseOneLine(line)
        rc = process.poll()
        
        logMgr.info("Time Up, Exit {0}".format(runCmd))
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
        print("In Child's generateHeader, {0}".format(line))
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
            return 0

        if line.startswith('Device:'):
            self._hitCycle += 1
        
        if (1 >= self._hitCycle): # Only record since 2 cycles
            return 0
        
        words = line.split()
        if len(words) and (words[0] in devList):
            line = re.sub("\s+", ",", line)
            (dateStr, timeStr) = MyTimeStamp.getDateAndTime(SECOND)
            new_line = "{0},{1},{2}\n".format(dateStr, timeStr, line)
            outF = open(self.getCsvFile(), "a")
            outF.writelines(new_line)
            outF.close()
        return 0
    
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

    
class cpuUsage(longRunStatsCollector):
    def hello(self):
        return 0