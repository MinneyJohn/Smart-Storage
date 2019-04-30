#! /usr/bin/python

import threading
import time
import re
import string
import datetime
import os
from threading import Timer
import argparse

from adminHelper import *
from loggerHelper import *
from statsHelper import *

'''
Why setting it to be 1 now:
a) Now only support single cache intance
b) At first, we have metadata overhead (2X)
c) Also due to write miss, write lock is bottleneck
d) So when times goes, the max write speed is supposed to be at least 4 times
e) So the total average write speed is 2X of the original speed
'''
MAKE_FILL_SAFE_AMPLIFICATION = 0.5

RUNTIME_READ_MISS   = 700
RUNTIME_MIN_PER_CAS = 700
RUNNING_TO_END = 360000 # 100 hours, MAX Running Time

'''
The customer wants to see those information for one caching software
<< Write Back Mode >>
1. Write Performance (Rnd/Seq with different IO Size)
   1.1 Write Hit on Dirty
   1.2 Write Miss with Free/Clean Space
   1.3 Write Miss without Free/Clean Space
2. Read Performance
   2.1 Read Hit 
   2.2 Read Miss 

Case 1.1, compared with RAW cache device performance number
Case 1.2, compared with RAW cache device performance number
Case 1.3, compared with RAW core device performance number

Case 2.1, compared with RAW cache device performance number
Case 2.2, compared with RAW core device performance number

<< Write Through Mode >>
3. Write Performance
   3.1 Write Hit
   3.2 Write Miss   
4. Read Performance
   4.1 Read Hit
   4.2 Read Miss

Case 3.1, compared with RAW core device performance number
Case 3.2, compared with RAW core device performance number
Case 4.1, compared with RAW cache device performance number
Case 4.2, compared with RAW cache device performance number
'''

class jobFIO():
    minT = RUNTIME_MIN_PER_CAS
    def __init__(self):
        self.parmDict = {}
        self.defaultParms()
        
    def setParm(self, parmName, parmValue = ""):
        self.parmDict[parmName] = parmValue
        return 0
    
    # Set default parms common for all jobs, can overwrite
    def defaultParms(self):
        self.setParm("name", "fioTest")
        self.setParm("ioengine", "libaio")
        self.setParm("iodepth", "32")
        self.setParm("numjobs", "16")
        self.setParm("group_reporting")
        self.setParm("direct", 1)
        return 0
    
    def genParmStr(self):
        parmStr = ""
        for k, v in self.parmDict.iteritems():
            if v:
                parmStr = "{0} --{1}={2}".format(parmStr, k, v)
            else:
                parmStr = "{0} --{1}".format(parmStr, k)
        return parmStr

    def runTimeControl(self, runTime):
        if (0 < runTime):
            if (int(runTime) < self.minT):
                runTime = self.minT
            self.setParm("runtime", runTime)
            self.setParm("time_based")

    def execute(self):
        # FOR DEBUG to run VERY fast
        # self.setParm("runtime", 120)
        # self.setParm("time_based")
        
        # Get thread for IOStats
        (ret, ioStatThread) = self.getIOStatsThread()
        # Start thread for IOStats
        if (0 == ret):
            ioStatThread.start()
        
        logMgr.info("Start of {0}".format(self.parmDict["name"]))
        fio_cmd = "fio {0}".format(self.genParmStr())
        logMgr.info(fio_cmd)
        # Start FIO Job
        casAdmin.getOutPutOfCmd(fio_cmd)
        logMgr.info("End of {0}".format(self.parmDict["name"]))

        # Wait for IOStats to finish
        if (0 == ret):
            ioStatThread.join()
        return 0
        
    def getIOStatsThread(self):
        if self.parmDict.has_key("runtime") and self.parmDict.has_key("filename"):
            runTime = self.parmDict["runtime"]
            fileName = self.parmDict["filename"]
        else:
            return (1, "")

        (cacheID, coreID) = casAdmin.getCacheCoreIdByDevName(fileName)
        if (-1 == cacheID):
            return (1, "")

        if self.parmDict.has_key("name"):
            testName = self.parmDict["name"]
            ioStatsJob = IoStats(DEFAULT_CYCLE_TIME, 
                                int(runTime/DEFAULT_CYCLE_TIME) + 2, 
                                logMgr.getDataDir(),
                                testName)
        else:
            ioStatsJob = IoStats(DEFAULT_CYCLE_TIME, 
                                int(runTime/DEFAULT_CYCLE_TIME) + 2, 
                                logMgr.getDataDir())

        thread_collect_iostat = threading.Thread(target=ioStatsJob.startCollectStats,
                                                        kwargs={"cacheID": cacheID})                                    
        return (0, thread_collect_iostat)

class jobRandWrite(jobFIO):        
    def run(self, devName, size, testName, runTime = 0):
        self.setParm("name", testName)
        self.setParm("filename", devName)
        self.setParm("size", size)
        self.setParm("rw", "randwrite")
        self.setParm("bs", "4K")

        self.runTimeControl(runTime)
        
        self.execute()
        return 0

        
class jobRandRead(jobFIO):
    def run(self, devName, size, testName, runTime = 0):
        self.setParm("name", testName)
        self.setParm("filename", devName)
        self.setParm("size", size)
        self.setParm("rw", "randread")
        self.setParm("bs", "4K")
        self.runTimeControl(runTime)
        self.execute()
        return 0
    
class jobSeqWrite(jobFIO):
    def run(self, devName, size, testName, runTime = 0):
        self.setParm("name", testName)
        self.setParm("filename", devName)
        self.setParm("size", size)
        self.setParm("rw", "write")
        self.setParm("bs", "128K")
        self.runTimeControl(runTime)
        self.execute()
        return 0

class jobSeqRead(jobFIO):
    def run(self, devName, size, testName, runTime = ""):
        self.setParm("name", testName)
        self.setParm("filename", devName)
        self.setParm("size", size)
        self.setParm("rw", "read")
        self.setParm("bs", "128K")
        self.runTimeControl(runTime)
        self.execute()
        return 0

class jobTestRandWrSpeed(jobFIO):
    def run(self, devName, size, testName, runTime):
        self.setParm("name", testName)
        self.setParm("filename", devName)
        self.setParm("size", size)
        self.setParm("rw", "randwrite")
        self.setParm("bs", "4K")
        self.setParm("runtime", runTime)
        self.execute()
        return 0

class resetCacheJob():
    def __init__(self, cacheDev):
        self.cacheID = casAdmin.getIdByCacheDev(cacheDev)
        
    def do(self):
        casAdmin.resetCacheInstance(self.cacheID, self.cacheDev, self.coreDev, self.cacheMode)
        return 0

class cfgCacheJob():
    def __init__(self, cacheDev, coreDev):
        self.cacheID = casAdmin.getAvailableCacheID()
        self.cacheDev = cacheDev
        self.coreDev = coreDev
        
    def do(self):
        casAdmin.cfgCacheInstance(self.cacheID, self.cacheDev, self.coreDev)
        return 0

class baselineCacheCorePair():
    def __init__(self, cacheDev, coreDev, finish = threading.Event()):
        self.cacheDev = cacheDev
        self.coreDev = coreDev
        self.finish = finish
    
    def getSpeedRandWrMissInMib(self, cacheID, inteldisk, cacheSize):
        testRunTime = 120
        logMgr.info("Start of write speed check, keep {0} seconds".format(testRunTime))
        jobTestRandWrSpeed().run(inteldisk, 
                                "{0}G".format(cacheSize), 
                                "WriteSpeedCheck",
                                testRunTime)
        logMgr.info("Ending of write speed check")
        dirtyBlocks = int(casAdmin.getFieldCachePerf(cacheID, "Dirty [4KiB blocks]"))
        return int((dirtyBlocks * 4)/1024/testRunTime)
    
    def getTimeFillCacheWithWrite(self, cacheID, inteldisk, cacheSize):
        writeSpeedInMb = self.getSpeedRandWrMissInMib(cacheID, inteldisk, cacheSize)
        logMgr.info("1st Minute, Write Speed {0} Mib/s".format(writeSpeedInMb))
        return int((cacheSize * 1024 * MAKE_FILL_SAFE_AMPLIFICATION)/writeSpeedInMb) 
    
    def estimateTotalRunningTime(self, timeToFill):
        if (timeToFill < RUNTIME_MIN_PER_CAS):
            timeToFill = RUNTIME_MIN_PER_CAS
        return int((timeToFill * 6 + RUNTIME_READ_MISS * 3) / 60)

    def do(self):
        # Make sure cache/core is clear
        if False == casAdmin.isCacheCoreClear(self.cacheDev, self.coreDev):
            print "**ERROR** Please make sure {0} and {1} NOT used".format(self.cacheDev, self.coreDev)
            return 1

        # Config Cache Instance
        casAdmin.cfgCacheCorePair(self.cacheDev, self.coreDev)
        
        # Get inteldisk associated with cache/core pair
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)
        cachesize = casAdmin.getCacheSizeInGib(self.cacheDev)
        cacheID = casAdmin.getIdByCacheDev(self.cacheDev)
        timeToFill = self.getTimeFillCacheWithWrite(cacheID, inteldisk, cachesize)
        totalRunTime = self.estimateTotalRunningTime(timeToFill)
        runTimeStr = "Estimated Running Time {0} minutes".format(totalRunTime)
        logMgr.info(runTimeStr)
        print runTimeStr
        
        # Reconfig
        casAdmin.reCfgCacheCorePair(self.cacheDev, self.coreDev)
        # Get inteldisk associated with cache/core pair
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)
        cachesize = casAdmin.getCacheSizeInGib(self.cacheDev)

        # Do Random Write (Miss)
        logMgr.info("Start of random write miss")
        jobRandWrite().run(inteldisk, 
                            "{0}G".format(cachesize), 
                            "RandWriteMiss",
                            timeToFill)
        logMgr.info("Ending of random write miss")

        # Do Random Write (Hit)
        logMgr.info("Start of random write hit")
        jobRandWrite().run(inteldisk, 
                            "{0}G".format(cachesize), 
                            "RandWriteHit",
                            timeToFill)
        logMgr.info("Ending of random write hit")

        # Do Random Read (Hit)
        logMgr.info("Start of random read hit")
        jobRandRead().run(inteldisk, 
                            "{0}G".format(cachesize), 
                            "RandReadHit",
                            timeToFill)
        logMgr.info("Ending of random read hit")

        # Reconfig
        casAdmin.reCfgCacheCorePair(self.cacheDev, self.coreDev)

        # Get inteldisk associated with cache/core pair
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)
        cachesize = casAdmin.getCacheSizeInGib(self.cacheDev)

        # Do Seq Write (Miss)
        logMgr.info("Start of sequential write miss")
        jobSeqWrite().run(inteldisk, 
                            "{0}G".format(cachesize), 
                            "SeqWriteMiss",
                            timeToFill)
        logMgr.info("Ending of sequential write miss")

        # Do Seq Write (Hit)
        logMgr.info("Start of sequential write hit")
        jobSeqWrite().run(inteldisk, 
                            "{0}G".format(cachesize), 
                            "SeqWriteHit",
                            timeToFill)
        logMgr.info("Ending of sequential write hit")

        # Do Seq Read (Hit)
        logMgr.info("Start of sequential read hit")
        jobSeqRead().run(inteldisk, 
                            "{0}G".format(cachesize), 
                            "SeqReadHit",
                            timeToFill)
        logMgr.info("Ending of sequential read hit")

        # Reconfig
        casAdmin.reCfgCacheCorePair(self.cacheDev, self.coreDev)

        # Get inteldisk associated with cache/core pair
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)
        coreSize = casAdmin.getCoreSizeInGib(self.coreDev)
        # Do Random Read (Miss), set running to 600s as it is quite a long run
        logMgr.info("Start of random read miss")
        jobRandRead().run(inteldisk, 
                            "{0}G".format(coreSize), 
                            "RandReadMiss",
                            RUNTIME_READ_MISS)
        logMgr.info("Ending of random read miss")

        # Reconfig
        casAdmin.reCfgCacheCorePair(self.cacheDev, self.coreDev)

        # Get inteldisk associated with cache/core pair
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)
        coreSize = casAdmin.getCoreSizeInGib(self.coreDev)
        # Do Seq Read (Miss), set running to 600s as it is quite a long run
        logMgr.info("Start of seq read miss")
        jobSeqRead().run(inteldisk, 
                            "{0}G".format(coreSize), 
                            "SeqReadMiss",
                            RUNTIME_READ_MISS)
        logMgr.info("Ending of seq read miss")

        self.finish.set()
        logMgr.info("Ready to notify the finish of FIO tasks")
        return 0
