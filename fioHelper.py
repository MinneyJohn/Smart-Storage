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

    def execute(self):
        # FOR DEBUG 
        # self.setParm("runtime", 10)
        # self.setParm("time_based")
        
        fio_cmd = "fio {0}".format(self.genParmStr())
        logger.info(fio_cmd)
        casAdmin.getOutPutOfCmd(fio_cmd)
        return 0
        

class jobRandWrite(jobFIO):        
    def run(self, devName, size, runTime = ""):
        self.setParm("filename", devName)
        self.setParm("size", size)
        self.setParm("rw", "randwrite")
        self.setParm("bs", "4K")

        if runTime:
            self.setParm("runtime", runTime)
            self.setParm("time_based")
        else:    
            self.setParm("runtime", RUNNING_TO_END)
        
        self.execute()
        return 0

        
class jobRandRead(jobFIO):
    def run(self, devName, size, runTime = ""):
        self.setParm("filename", devName)
        self.setParm("size", size)
        self.setParm("rw", "randread")
        self.setParm("bs", "4K")

        if runTime:
            self.setParm("runtime", runTime)
            self.setParm("time_based")
        else:    
            self.setParm("runtime", RUNNING_TO_END)

        self.execute()
        return 0
    
class jobSeqWrite(jobFIO):
    def run(self, devName, size, runTime = ""):
        self.setParm("filename", devName)
        self.setParm("size", size)
        self.setParm("rw", "write")
        self.setParm("bs", "128K")

        if runTime:
            self.setParm("runtime", runTime)
            self.setParm("time_based")
        else:    
            self.setParm("runtime", RUNNING_TO_END)
        self.execute()
        return 0

class jobSeqRead(jobFIO):
    def run(self, devName, size, runTime = ""):
        self.setParm("filename", devName)
        self.setParm("size", size)
        self.setParm("rw", "read")
        self.setParm("bs", "128K")

        if runTime:
            self.setParm("runtime", runTime)
            self.setParm("time_based")
        else:    
            self.setParm("runtime", RUNNING_TO_END)
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
        
    def do(self):
        # Make sure cache/core is clear
        if False == casAdmin.isCacheCoreClear(self.cacheDev, self.coreDev):
            print "**ERROR** Please make sure {0} and {1} NOT used".format(self.cacheDev, self.coreDev)
            return 1

        # Config Cache Instance
        casAdmin.cfgCacheCorePair(self.cacheDev, self.coreDev)
        
        # Get inteldisk associated with cache/core pair
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)
        cachesize = casAdmin.getCacheSize(self.cacheDev)

        # Do Random Write (Miss)
        logger.info("Start of random write miss")
        jobRandWrite().run(inteldisk, cachesize)
        logger.info("Ending of random write miss")

        # Do Random Write (Hit)
        logger.info("Start of random write hit")
        jobRandWrite().run(inteldisk, cachesize)
        logger.info("Ending of random write hit")

        # Do Random Read (Hit)
        logger.info("Start of random read hit")
        jobRandRead().run(inteldisk, cachesize)
        logger.info("Ending of random read hit")

        # Reconfig
        casAdmin.reCfgCacheCorePair(self.cacheDev, self.coreDev)

        # Get inteldisk associated with cache/core pair
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)
        cachesize = casAdmin.getCacheSize(self.cacheDev)

        # Do Seq Write (Miss)
        logger.info("Start of sequential write miss")
        jobSeqWrite().run(inteldisk, cachesize)
        logger.info("Ending of sequential write miss")

        # Do Seq Write (Hit)
        logger.info("Start of sequential write hit")
        jobSeqWrite().run(inteldisk, cachesize)
        logger.info("Ending of sequential write hit")

        # Do Seq Read (Hit)
        logger.info("Start of sequential read hit")
        jobSeqRead().run(inteldisk, cachesize)
        logger.info("Ending of sequential read hit")

        # Reconfig
        casAdmin.reCfgCacheCorePair(self.cacheDev, self.coreDev)

        # Get inteldisk associated with cache/core pair
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)
        coreSize = casAdmin.getCoreSize(self.coreDev)
        # Do Random Read (Miss), set running to 600s as it is quite a long run
        logger.info("Start of random read miss")
        jobRandRead().run(inteldisk, coreSize, runTime="600")
        logger.info("Ending of random read miss")

        # Reconfig
        casAdmin.reCfgCacheCorePair(self.cacheDev, self.coreDev)

        # Get inteldisk associated with cache/core pair
        inteldisk = casAdmin.getIntelDiskByCoreDev(self.coreDev)
        coreSize = casAdmin.getCoreSize(self.coreDev)
        # Do Seq Read (Miss), set running to 600s as it is quite a long run
        logger.info("Start of seq read miss")
        jobSeqRead().run(inteldisk, coreSize, runTime="600")
        logger.info("Ending of seq read miss")

        self.finish.set()
        logger.info("Ready to notify the finish of FIO tasks")
        return 0