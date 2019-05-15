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
ToDo:
a) 8K cache line size, how to calcualte dirty data capacity
'''

'''
Why setting it to be 1.3 now:
a) Use seq write to fill caching device
b) We must make sure the caching device can be fullfilled or the following hit cases
c) So enlarge the time to estmated to more 30% for sure
'''
MAKE_FILL_SAFE_AMPLIFICATION = 1.3

RUNTIME_READ_MISS   = 700
RUNTIME_MIN_PER_CAS = 700
RUNNING_TO_END = 360000 # 100 hours, MAX Running Time
SECONDS_ALIGNMENT = 60 # Time to align stats and fio job
IOSTAT_RUNTIME_BUFFER = 3 # Buffer minutes for iostat to make sure it can cover FIO job

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

'''
This class is designed for customer to define how FIO is running
'''
class runningSetup():
    parmDict = {}
    parmDict["iodepth"] = 32
    parmDict["numjobs"] = 8
    parmDict["ioengine"] = "libaio"
    parmDict["group_reporting"] = ""
    parmDict["direct"] = 1

    header_terse = "terse_version_3;fio_version;jobname;groupid;error;"\
                    "read_kb;read_bandwidth;read_iops;read_runtime_ms;"\
                    "read_slat_min;read_slat_max;read_slat_mean;read_slat_dev;"\
                    "read_clat_min;read_clat_max;read_clat_mean;read_clat_dev;"\
                    "read_clat_pct01;read_clat_pct02;read_clat_pct03;read_clat_pct04;"\
                    "read_clat_pct05;read_clat_pct06;read_clat_pct07;read_clat_pct08;"\
                    "read_clat_pct09;read_clat_pct10;read_clat_pct11;read_clat_pct12;"\
                    "read_clat_pct13;read_clat_pct14;read_clat_pct15;read_clat_pct16;"\
                    "read_clat_pct17;read_clat_pct18;read_clat_pct19;read_clat_pct20;"\
                    "read_tlat_min;read_lat_max;read_lat_mean;read_lat_dev;read_bw_min;"\
                    "read_bw_max;read_bw_agg_pct;read_bw_mean;read_bw_dev;write_kb;"\
                    "write_bandwidth;write_iops;write_runtime_ms;write_slat_min;"\
                    "write_slat_max;write_slat_mean;write_slat_dev;write_clat_min;"\
                    "write_clat_max;write_clat_mean;write_clat_dev;write_clat_pct01;"\
                    "write_clat_pct02;write_clat_pct03;write_clat_pct04;write_clat_pct05;"\
                    "write_clat_pct06;write_clat_pct07;write_clat_pct08;write_clat_pct09;"\
                    "write_clat_pct10;write_clat_pct11;write_clat_pct12;write_clat_pct13;"\
                    "write_clat_pct14;write_clat_pct15;write_clat_pct16;write_clat_pct17;"\
                    "write_clat_pct18;write_clat_pct19;write_clat_pct20;write_tlat_min;"\
                    "write_lat_max;write_lat_mean;write_lat_dev;write_bw_min;write_bw_max;"\
                    "write_bw_agg_pct;write_bw_mean;write_bw_dev;cpu_user;cpu_sys;cpu_csw;"\
                    "cpu_mjf;cpu_minf;iodepth_1;iodepth_2;iodepth_4;iodepth_8;iodepth_16;"\
                    "iodepth_32;iodepth_64;lat_2us;lat_4us;lat_10us;lat_20us;lat_50us;"\
                    "lat_100us;lat_250us;lat_500us;lat_750us;lat_1000us;lat_2ms;lat_4ms;"\
                    "lat_10ms;lat_20ms;lat_50ms;lat_100ms;lat_250ms;lat_500ms;lat_750ms;"\
                    "lat_1000ms;lat_2000ms;lat_over_2000ms;disk_name;disk_read_iops;"\
                    "disk_write_iops;disk_read_merges;disk_write_merges;disk_read_ticks;"\
                    "write_ticks;disk_queue_time;disk_util"
    
    @classmethod
    def getRunningSetup(cls, parmName):
        return cls.parmDict[parmName]

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
        for k, v in runningSetup.parmDict.iteritems():
            self.setParm(k, v)
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

    def setOutPut(self):
        outputFile = os.path.join(logMgr.getDataDir(), 
                                "{0}_{1}.fio.summary".\
                                format(self.parmDict["name"], MyTimeStamp.getAppendTime()))
        self.setParm("output", outputFile)
        self.setParm("output-format", "terse")

    def addFioSummaryHeader(self):
        outputFile = self.parmDict["output"]
        fp = open(outputFile, "r")
        line = fp.readline()
        fp.close()
        
        fp = open(outputFile, "w+")
        lines = "{0}\n{1}".format(runningSetup.header_terse, line)
        fp.writelines(lines)
        fp.close()

    def execute(self):
        # FOR DEBUG to run VERY fast
        # self.setParm("runtime", 120)
        # self.setParm("time_based")
        
        # Get thread for IOStats
        (ret, ioStatThread) = self.getIOStatsThread()
        # Start thread for IOStats
        if (0 == ret):
            ioStatThread.start()
        
        # Wait for second 0 to start, align stats and fio running
        time_seconds_now = datetime.datetime.now().time().second
        seconds_to_wait = (SECONDS_ALIGNMENT - (time_seconds_now % SECONDS_ALIGNMENT))
        logMgr.info("")
        logMgr.info("Sleep {0} seconds to align io stats and fio job".format(seconds_to_wait))
        time.sleep(seconds_to_wait)

        logMgr.info("Start of FIO Job {0}".format(self.parmDict["name"]))
        self.setOutPut()
        fio_cmd = "fio {0}".format(self.genParmStr())
        logMgr.info(fio_cmd)
        # Start FIO Job
        casAdmin.getOutPutOfCmd(fio_cmd)
        logMgr.info("End of FIO Job {0}".format(self.parmDict["name"]))
        
        # Add header to FIO summary
        self.addFioSummaryHeader()

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
                                int(runTime/DEFAULT_CYCLE_TIME) + IOSTAT_RUNTIME_BUFFER, 
                                logMgr.getDataDir(),
                                testName)
        else:
            ioStatsJob = IoStats(DEFAULT_CYCLE_TIME, 
                                int(runTime/DEFAULT_CYCLE_TIME) + IOSTAT_RUNTIME_BUFFER, 
                                logMgr.getDataDir())

        thread_collect_iostat = threading.Thread(target=ioStatsJob.startCollectStats,
                                                        kwargs={"cacheID": cacheID})                                    
        return (0, thread_collect_iostat)

class jobRandWrite(jobFIO):        
    def run(self, devName, size, testName, runTime = 0):
        self.setParm("name", testName)
        self.setParm("filename", devName)
        self.setParm("size", "{0}G".format(size))
        self.setParm("rw", "randwrite")
        self.setParm("bs", "4K")

        self.runTimeControl(runTime)
        self.execute()
        return 0
        
class jobRandRead(jobFIO):
    def run(self, devName, size, testName, runTime = 0):
        self.setParm("name", testName)
        self.setParm("filename", devName)
        self.setParm("size", "{0}G".format(size))
        self.setParm("rw", "randread")
        self.setParm("bs", "4K")
        self.runTimeControl(runTime)
        self.execute()
        return 0
    
class jobSeqWrite(jobFIO):
    def run(self, devName, size, testName, runTime = 0):
        self.setParm("name", testName)
        self.setParm("filename", devName)
        self.setParm("size", "{0}G".format(size))
        self.setParm("rw", "write")
        self.setParm("bs", "128K")
        # Single Job for sequential
        self.setParm("iodepth", 16)
        self.setParm("numjobs", 1)

        self.runTimeControl(runTime)
        self.execute()
        return 0

class jobSeqRead(jobFIO):
    def run(self, devName, size, testName, runTime = 0):
        self.setParm("name", testName)
        self.setParm("filename", devName)
        self.setParm("size", "{0}G".format(size))
        self.setParm("rw", "read")
        self.setParm("bs", "128K")
        self.setParm("iodepth", 16)
        self.setParm("numjobs", 1)

        self.runTimeControl(runTime)
        self.execute()
        return 0

# Use Seq Write Miss with single JOB to estimate running time
# As we'll use seq write miss to fill caching device for hit case
class jobTestWriteSpeed(jobFIO):
    def run(self, devName, size, testName, runTime):
        self.setParm("name", testName)
        self.setParm("filename", devName)
        self.setParm("size", "{0}G".format(size))
        self.setParm("rw", "write")
        self.setParm("bs", "128K")
        self.setParm("iodepth", 4)
        self.setParm("numjobs", 1)
        self.setParm("runtime", runTime)
        self.execute()
        return 0

class jobWriteOverflow(jobFIO):
    def run(self, devName, cacheSize, coreSize, name, runTime=0):
        self.setParm("name", name)
        self.setParm("filename", devName)
        self.setParm("size", "{0}G".format(coreSize - cacheSize))
        self.setParm("rw", "write")
        self.setParm("bs", "4K")
        self.setParm("iodepth", 16)
        self.setParm("numjobs", 8)
        self.setParm("offset", "{0}G".format(cacheSize)) # Do NOT touch caching space
        self.runTimeControl(runTime)
        self.execute()
        return 0

'''
Used to fill in caching device for hit case:
a) Am using seq write, with numjobs "1" and iodepth "16"
b) Size is supposed to be normalized of caching device
''' 
class jobFillCachingDevice(jobFIO):
    def run(self, devName, size):
        self.setParm("name", "FillCachingDevice")
        self.setParm("filename", devName)
        self.setParm("size", "{0}G".format(size))
        self.setParm("rw", "write")
        self.setParm("bs", "128K")
        self.setParm("iodepth", 16)
        self.setParm("numjobs", 1)
        self.execute()
        return 0

# Used to estimate time to fill in caching devie
class estimateCacheFullTime():
    numjob  = 1
    iodepth = 16
    runTime = 120

    @classmethod
    def getTime(cls, cacheDev, coreDev):
        casAdmin.cfgCacheCorePair(cacheDev, coreDev)

        cacheID   = casAdmin.getIdByCacheDev(cacheDev)
        inteldisk = casAdmin.getIntelDiskByCoreDev(coreDev)
        cacheSize = casAdmin.getCacheSizeInGib(cacheDev)
        
        logMgr.info("Start of write speed check, keep {0} seconds".format(cls.runTime))
        jobTestWriteSpeed().run(inteldisk, 
                                cacheSize, 
                                "WriteSpeedCheck",
                                cls.runTime)
        logMgr.info("Ending of write speed check")
        dirtyBlocks = int(casAdmin.getFieldCachePerf(cacheID, "Dirty [4KiB blocks]"))
        writeSpeedInMb = int((dirtyBlocks * 4)/1024/cls.runTime)
    
        logMgr.info("For first {0} seconds, Write Speed {1} Mib/s".format(cls.runTime, writeSpeedInMb))
        
        # Stop cache instance
        casAdmin.stopCacheInstance(cacheID)
        return int((cacheSize * 1024 * MAKE_FILL_SAFE_AMPLIFICATION)/writeSpeedInMb) 

class caseRandReadMiss():
    def __init__(self, cacheDev, coreDev, finish = threading.Event()):
        self.cacheDev = cacheDev
        self.coreDev = coreDev
        self.finish = finish
    
    def do(self):
        # Config cache instance
        casAdmin.cfgCacheCorePair(self.cacheDev, self.coreDev)
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)
        # Get cache/core and cache size for future usage
        coreSize = casAdmin.getCoreSizeInGib(self.coreDev)
        
        # Do Rand Read (Miss), set running to 600s as it is quite a long run
        jobRandRead().run(inteldisk, 
                            coreSize, 
                            "RandReadMiss",
                            RUNTIME_READ_MISS)
        
        self.finish.set()
        logMgr.info("Ready to notify the finish of FIO tasks")
        return 0

class caseRandReadHit():
    def __init__(self, cacheDev, coreDev, finish = threading.Event()):
        self.cacheDev = cacheDev
        self.coreDev = coreDev
        self.finish = finish
    
    def do(self):
        # Config Cache Instance
        casAdmin.cfgCacheCorePair(self.cacheDev, self.coreDev)
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)

        # Get cache/core and cache size for future usage
        cacheSize = casAdmin.getCacheSizeInGib(self.cacheDev)
        coreSize = casAdmin.getCoreSizeInGib(self.coreDev)
        
        # Fill in the caching device
        jobFillCachingDevice().run(inteldisk, cacheSize)

        # Do Random Read (Hit)
        jobRandRead().run(inteldisk, 
                            cacheSize, 
                            "RandReadHit",
                            RUNTIME_READ_MISS)
        
        self.finish.set()
        return 0

class caseRandWriteMiss():
    def __init__(self, cacheDev, coreDev, finish = threading.Event()):
        self.cacheDev = cacheDev
        self.coreDev = coreDev
        self.finish = finish
    
    def do(self):
        # Estimate time needed to fill in the caching device
        timeToFill = estimateCacheFullTime.getTime(self.cacheDev, self.coreDev)
        
        # Config cache instance
        casAdmin.cfgCacheCorePair(self.cacheDev, self.coreDev)
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)
        # Get cache/core and cache size for future usage
        cacheSize = casAdmin.getCacheSizeInGib(self.cacheDev)
        
        # Do Random Write (Miss)
        jobRandWrite().run(inteldisk, 
                            cacheSize, 
                            "RandWriteMiss",
                            timeToFill)
        
        self.finish.set()
        logMgr.info("Ready to notify the finish of FIO tasks")
        return 0

class caseRandWriteHit():
    def __init__(self, cacheDev, coreDev, finish = threading.Event()):
        self.cacheDev = cacheDev
        self.coreDev = coreDev
        self.finish = finish
    
    def do(self):
        # Config cache instance
        casAdmin.cfgCacheCorePair(self.cacheDev, self.coreDev)
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)
        # Get cache/core and cache size for future usage
        cacheSize = casAdmin.getCacheSizeInGib(self.cacheDev)
        
        # Fill in the caching device
        jobFillCachingDevice().run(inteldisk, cacheSize)
        
        # Do Random Write (Hit)
        jobRandWrite().run(inteldisk, 
                            cacheSize, 
                            "RandWriteHit",
                            RUNTIME_READ_MISS)
        
        self.finish.set()
        logMgr.info("Ready to notify the finish of FIO tasks")
        return 0

class caseSeqReadMiss():
    def __init__(self, cacheDev, coreDev, finish = threading.Event()):
        self.cacheDev = cacheDev
        self.coreDev = coreDev
        self.finish = finish
    
    def do(self):
        # Config cache instance
        casAdmin.cfgCacheCorePair(self.cacheDev, self.coreDev)
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)
        # Get cache/core and cache size for future usage
        coreSize = casAdmin.getCoreSizeInGib(self.coreDev)
        
        # Do Rand Read (Miss), set running to 600s as it is quite a long run
        jobSeqRead().run(inteldisk, 
                            coreSize, 
                            "SeqReadMiss",
                            RUNTIME_READ_MISS)
        
        self.finish.set()
        logMgr.info("Ready to notify the finish of FIO tasks")
        return 0

class caseSeqReadHit():
    def __init__(self, cacheDev, coreDev, finish = threading.Event()):
        self.cacheDev = cacheDev
        self.coreDev = coreDev
        self.finish = finish
    
    def do(self):
        # Config Cache Instance
        casAdmin.cfgCacheCorePair(self.cacheDev, self.coreDev)
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)

        # Get cache/core and cache size for future usage
        cacheSize = casAdmin.getCacheSizeInGib(self.cacheDev)
        
        # Fill in the caching device
        jobFillCachingDevice().run(inteldisk, cacheSize)

        # Do Random Read (Hit)
        jobSeqRead().run(inteldisk, 
                        cacheSize, 
                        "SeqReadHit",
                        RUNTIME_READ_MISS)
        
        self.finish.set()
        return 0

class caseSeqWriteMiss():
    def __init__(self, cacheDev, coreDev, finish = threading.Event()):
        self.cacheDev = cacheDev
        self.coreDev = coreDev
        self.finish = finish
    
    def do(self):
        # Estimate time needed to fill in the caching device
        timeToFill = estimateCacheFullTime.getTime(self.cacheDev, self.coreDev)
        
        # Config cache instance
        casAdmin.cfgCacheCorePair(self.cacheDev, self.coreDev)
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)
        # Get cache/core and cache size for future usage
        cacheSize = casAdmin.getCacheSizeInGib(self.cacheDev)
        coreSize = casAdmin.getCoreSizeInGib(self.coreDev)
        
        # Do Seq Write (Miss)
        jobSeqWrite().run(inteldisk, 
                            coreSize, 
                            "SeqWriteMiss",
                            timeToFill)
        
        self.finish.set()
        logMgr.info("Ready to notify the finish of FIO tasks")
        return 0

class caseSeqWriteHit():
    def __init__(self, cacheDev, coreDev, finish = threading.Event()):
        self.cacheDev = cacheDev
        self.coreDev = coreDev
        self.finish = finish
    
    def do(self):
        # Config cache instance
        casAdmin.cfgCacheCorePair(self.cacheDev, self.coreDev)
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)
        # Get cache/core and cache size for future usage
        cacheSize = casAdmin.getCacheSizeInGib(self.cacheDev)
        
        # Fill in the caching device
        jobFillCachingDevice().run(inteldisk, cacheSize)
        
        # Do Seq Write (Hit)
        jobSeqWrite().run(inteldisk, 
                            cacheSize, 
                            "SeqWriteHit",
                            RUNTIME_READ_MISS)
        
        self.finish.set()
        logMgr.info("Ready to notify the finish of FIO tasks")
        return 0

class caseWriteOverflow():
    def __init__(self, cacheDev, coreDev, finish = threading.Event()):
        self.cacheDev = cacheDev
        self.coreDev = coreDev
        self.finish = finish
    
    def do(self):
        # Config cache instance
        casAdmin.cfgCacheCorePair(self.cacheDev, self.coreDev)
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)
        # Get cache/core and cache size for future usage
        cacheSize = casAdmin.getCacheSizeInGib(self.cacheDev)
        
        # Fill in the caching device
        jobFillCachingDevice().run(inteldisk, cacheSize)
        
        # Do Seq Write (Hit)
        jobWriteOverflow().run(inteldisk, 
                                cacheSize,
                                coreSize, 
                                "SeqWriteOverflow",
                                RUNTIME_READ_MISS)
        
        self.finish.set()
        logMgr.info("Ready to notify the finish of FIO tasks")
        return 0

class baselineCacheCorePair():
    def __init__(self, cacheDev, coreDev, finish = threading.Event()):
        self.cacheDev = cacheDev
        self.coreDev = coreDev
        self.finish = finish
    
    def estimateTotalRunningTime(self, timeToFill):
        if (timeToFill < RUNTIME_MIN_PER_CAS):
            timeToFill = RUNTIME_MIN_PER_CAS
        return int((timeToFill * 6 + RUNTIME_READ_MISS * 3) / 60)
    
    def mergeFioOutPut(self):
        return 0

    def do(self):
        # Make sure cache/core is clear
        if False == casAdmin.isCacheCoreClear(self.cacheDev, self.coreDev):
            print "**ERROR** Please make sure {0} and {1} NOT used".format(self.cacheDev, self.coreDev)
            return 1

        # Estimate the time for running the test case
        timeToFill = estimateCacheFullTime.getTime(self.cacheDev, self.coreDev)
        
        # Config Cache Instance
        casAdmin.cfgCacheCorePair(self.cacheDev, self.coreDev)
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)
        cacheSize = casAdmin.getCacheSizeInGib(self.cacheDev)
        coreSize = casAdmin.getCoreSizeInGib(self.coreDev)
        
        # Do Seq Write (Miss)
        jobSeqWrite().run(inteldisk, 
                            cacheSize, 
                            "SeqWriteMiss",
                            timeToFill)
        
        # Do Seq Write (Hit)
        jobSeqWrite().run(inteldisk, 
                            cacheSize, 
                            "SeqWriteHit",
                            timeToFill)
        
        # Do Random Write (Hit)
        jobRandWrite().run(inteldisk, 
                            cacheSize, 
                            "RandWriteHit",
                            timeToFill)
        
        # Do Seq Read (Hit)
        jobSeqRead().run(inteldisk, 
                        cacheSize, 
                        "SeqReadHit",
                        timeToFill)
        
        # Do Random Read (Hit)
        jobRandRead().run(inteldisk, 
                            cacheSize, 
                            "RandReadHit",
                            timeToFill)
        
        # Do Write for Overflow
        jobWriteOverflow().run(inteldisk,
                                cacheSize,
                                coreSize,
                                "WriteOverflow",
                                timeToFill)
        
        # Reconfig
        casAdmin.reCfgCacheCorePair(self.cacheDev, self.coreDev)
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)

        # Do Random Write (Miss)
        jobRandWrite().run(inteldisk, 
                            coreSize, 
                            "RandWriteMiss",
                            timeToFill)
        
        # Reconfig
        casAdmin.reCfgCacheCorePair(self.cacheDev, self.coreDev)
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)
        
        # Do Seq Read (Miss), set running to 600s as it is quite a long run
        jobSeqRead().run(inteldisk, 
                        coreSize, 
                        "SeqReadMiss",
                        RUNTIME_READ_MISS)
        
        # Reconfig
        casAdmin.reCfgCacheCorePair(self.cacheDev, self.coreDev)
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)

        # Do Rand Read (Miss), set running to 600s as it is quite a long run
        jobRandRead().run(inteldisk, 
                            coreSize, 
                            "RandReadMiss",
                            RUNTIME_READ_MISS)
        
        self.finish.set()
        logMgr.info("Ready to notify the finish of FIO tasks")
        return 0