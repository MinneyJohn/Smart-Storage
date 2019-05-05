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
MAKE_FILL_SAFE_AMPLIFICATION = 1.0 

RUNTIME_READ_MISS   = 700
RUNTIME_MIN_PER_CAS = 700
RUNNING_TO_END = 360000 # 100 hours, MAX Running Time
SECONDS_ALIGNMENT = 60 # Time to align stats and fio job
IOSTAT_RUNTIME_BUFFER = 4 # Buffer minutes for iostat to make sure it is after fio job

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
        logMgr.info("Sleep {0} seconds to align io stats and fio job".format(seconds_to_wait))
        time.sleep(seconds_to_wait)

        logMgr.info("Start of Job {0}".format(self.parmDict["name"]))
        self.setOutPut()
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
        self.runTimeControl(runTime)
        self.execute()
        return 0

class jobSeqRead(jobFIO):
    def run(self, devName, size, testName, runTime = ""):
        self.setParm("name", testName)
        self.setParm("filename", devName)
        self.setParm("size", "{0}G".format(size))
        self.setParm("rw", "read")
        self.setParm("bs", "128K")
        self.runTimeControl(runTime)
        self.execute()
        return 0

# Single job is faster than multiple job for Seq Write
class jobSeqWriteMiss(jobFIO):
    def run(self, devName, size, testName, runTime = 0):
        self.setParm("name", testName)
        self.setParm("filename", devName)
        self.setParm("rw", "write")
        self.setParm("bs", "128K")
        self.setParm("size", "{0}G".format(size))
        self.setParm("iodepth", "4")
        self.setParm("numjobs", "1")

        self.runTimeControl(runTime)
        self.execute()
        return 0    

class jobSeqReadMiss(jobFIO):
    def run(self, devName, size, testName, runTime = 0):
        self.setParm("name", testName)
        self.setParm("filename", devName)
        self.setParm("rw", "write")
        self.setParm("bs", "128K")

        # Need to use "offset_increment" to make multiple seq jobs do IO
        # Against different LBA ranges to simulate the miss workload
        size_per_job = int(size / self.parmDict["numjobs"])
        self.setParm("offset_increment", "{0}G".format(size_per_job))
        self.setParm("size", "{0}G".format(size_per_job))

        self.runTimeControl(runTime)
        self.execute()
        return 0    

# Use Seq Write Miss with single JOB to estimate running time
# As we'll use seq write miss to fill caching device for hit case
class jobTestRandWrSpeed(jobFIO):
    def run(self, devName, size, testName, runTime):
        self.setParm("name", testName)
        self.setParm("filename", devName)
        self.setParm("size", "{0}G".format(size))
        self.setParm("rw", "write")
        self.setParm("bs", "128K")
        self.setParm("iodepth", "4")
        self.setParm("numjobs", "1")
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
                                cacheSize, 
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
    
    def roundedSizeByNumJob(self, size):
        return (size - (size % runningSetup.parmDict["numjobs"]))

    def mergeFioOutPut(self):
        return 0

    def do(self):
        # Make sure cache/core is clear
        if False == casAdmin.isCacheCoreClear(self.cacheDev, self.coreDev):
            print "**ERROR** Please make sure {0} and {1} NOT used".format(self.cacheDev, self.coreDev)
            return 1

        # Config Cache Instance
        casAdmin.cfgCacheCorePair(self.cacheDev, self.coreDev)
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)

        # Get cache/core and rounded cache size for future usage
        cacheSize = casAdmin.getCacheSizeInGib(self.cacheDev)
        coreSize = casAdmin.getCoreSizeInGib(self.coreDev)
        roundedCacheSize = self.roundedSizeByNumJob(cacheSize)

        # Estimate the time for running the test case
        cacheID = casAdmin.getIdByCacheDev(self.cacheDev)
        timeToFill = self.getTimeFillCacheWithWrite(cacheID, inteldisk, cacheSize)
        totalRunTime = self.estimateTotalRunningTime(timeToFill)
        runTimeStr = "Estimated Running Time {0} minutes".format(totalRunTime)
        logMgr.info(runTimeStr)
        print runTimeStr

        # Reconfig and refetch inteldisk
        casAdmin.reCfgCacheCorePair(self.cacheDev, self.coreDev)
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)
        
        # Do Seq Write (Miss)
        logMgr.info("Start of sequential write miss")
        jobSeqWriteMiss().run(inteldisk, 
                                roundedCacheSize, 
                                "SeqWriteMiss",
                                timeToFill)
        logMgr.info("Ending of sequential write miss")

        # Do Seq Write (Hit)
        logMgr.info("Start of sequential write hit")
        jobSeqWrite().run(inteldisk, 
                            roundedCacheSize, 
                            "SeqWriteHit",
                            timeToFill)
        logMgr.info("Ending of sequential write hit")

        # Do Random Write (Hit)
        logMgr.info("Start of random write hit")
        jobRandWrite().run(inteldisk, 
                            roundedCacheSize, 
                            "RandWriteHit",
                            timeToFill)
        logMgr.info("Ending of random write hit")

        # Do Seq Read (Hit)
        logMgr.info("Start of sequential read hit")
        jobSeqRead().run(inteldisk, 
                            roundedCacheSize, 
                            "SeqReadHit",
                            timeToFill)
        logMgr.info("Ending of sequential read hit")

        # Do Random Read (Hit)
        logMgr.info("Start of random read hit")
        jobRandRead().run(inteldisk, 
                            roundedCacheSize, 
                            "RandReadHit",
                            timeToFill)
        logMgr.info("Ending of random read hit")


        # Reconfig
        casAdmin.reCfgCacheCorePair(self.cacheDev, self.coreDev)
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)

        # Do Random Write (Miss)
        logMgr.info("Start of random write miss")
        jobRandWrite().run(inteldisk, 
                            coreSize, 
                            "RandWriteMiss",
                            timeToFill)
        logMgr.info("Ending of random write miss")

        # Reconfig
        casAdmin.reCfgCacheCorePair(self.cacheDev, self.coreDev)
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)
        
        # Do Seq Read (Miss), set running to 600s as it is quite a long run
        logMgr.info("Start of seq read miss")
        jobSeqReadMiss().run(inteldisk, 
                                coreSize, 
                                "SeqReadMiss",
                                RUNTIME_READ_MISS)
        logMgr.info("Ending of seq read miss")

        # Reconfig
        casAdmin.reCfgCacheCorePair(self.cacheDev, self.coreDev)
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)

        # Do Rand Read (Miss), set running to 600s as it is quite a long run
        logMgr.info("Start of random read miss")
        jobRandRead().run(inteldisk, 
                            coreSize, 
                            "RandReadMiss",
                            RUNTIME_READ_MISS)
        logMgr.info("Ending of random read miss")

        self.finish.set()
        logMgr.info("Ready to notify the finish of FIO tasks")
        return 0