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

from statsHelper import *
import logging
 
logging.basicConfig(level=logging.DEBUG,
                    filename='running.log',
                    datefmt='%Y/%m/%d %H:%M:%S',
                    format='%(asctime)s - %(name)s - %(levelname)s - %(lineno)d - %(module)s - %(message)s')
logger = logging.getLogger(__name__)

# This time is be long enough to make FIO exit due to "--size" limit is hit 
RUNNING_TO_END = 36000
DEFAULT_CYCLE_TIME = 60


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
        # self.setParm("runtime", 20)
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

# Used to config/prepare cache environment
class casAdmin():
    @classmethod 
    def cfgCacheCorePair(cls, cacheDev, coreDev, cacheMode = "wb"):
        cacheID = casAdmin.getAvailableCacheID()
        cls.cfgCacheInstance(cacheID, cacheDev, coreDev, cacheMode)
        return 0
    
    @classmethod
    def cfgCacheInstance(cls, cacheID, cacheDev, coreDev, cacheMode):
        cls.startCache(cacheID, cacheDev)
        cls.addCore(cacheID, coreDev)
        cls.setCacheMode(cacheID, cacheMode)
        return 0
    
    @classmethod
    def addCore(cls, cacheID, coreDev):
        addCoreCmd = "casadm -A -i {0} -d {1}".format(cacheID, coreDev)
        cls.getOutPutOfCmd(addCoreCmd)
        return 0

    @classmethod
    def startCache(cls, cacheID, cacheDev):
        startCacheCmd = "casadm -S -i {0} -d {1} --force".format(cacheID, cacheDev)
        cls.getOutPutOfCmd(startCacheCmd)
        return 0
    
    @classmethod
    def setCacheMode(cls, cacheID, cacheMode):
        setCacheModeCmd = "casadm -Q -c {0} -i {1}".format(cacheMode, cacheID)
        cls.getOutPutOfCmd(setCacheModeCmd)
        return 0

    @classmethod
    def stopCacheInstance(cls, cacheID):
        stop_cache = "casadm -T -i {0} -n".format(cacheID)
        cls.getOutPutOfCmd(stop_cache)
        return 0
    
    @classmethod
    def reCfgCacheCorePair(cls, cacheDev, coreDev, cacheMode = "wb"):
        cls.stopCacheInstance(cls.getIdByCacheDev(cacheDev))
        cls.cfgCacheCorePair(cacheDev, coreDev, cacheMode)
        return 0
    
    @classmethod
    def isCacheCoreClear(cls, cacheDev, coreDev):
        check_cmd = "casadm -L -o csv | egrep \"{0}|{1}\"".format(cacheDev, coreDev)
        try:
            output = cls.getOutPutOfCmd(check_cmd)
        except Exception, e:
            return True
        
        return False
    
    @classmethod
    def getAvailableCacheID(cls):
        cache_id_list = set()
        (instance_list, volume_list) = SetOfCacheVolume.fetchCacheVolumeSet()
        for instance in instance_list:
            cache_id_list.add(int(instance.cacheID))
        cache_id_list = sorted(cache_id_list)
        cur_cache_id = 1
        while (cur_cache_id in cache_id_list):
            cur_cache_id = cur_cache_id + 1
        return cur_cache_id
    
    @classmethod
    def getIdByCacheDev(cls, cacheDev):
        cmd_str = "casadm -L -o csv | grep \"cache,\" | grep \"{0}\"".format(cacheDev)
        output = cls.getOutPutOfCmd(cmd_str)
        words = cls.getWordsOfLine(output)
        return int(words[1])
    
    @classmethod
    def getIntelDiskByCoreDev(cls, coreDev):
        cmd_str = "casadm -L -o csv | grep \"{0}\" | grep intelcas".format(coreDev)
        output = cls.getOutPutOfCmd(cmd_str)
        words = cls.getWordsOfLine(output)
        #print "output {0}".format(output)
        #print "words {0}".format(words)
        return words[5]

    @classmethod
    def getCoreSize(cls, coreDev):
        coreDev_noPre = coreDev.replace("/dev/", "")
        cmd_str = "lsblk {0} -b -o NAME,SIZE|grep \"{1} \"".format(coreDev, coreDev_noPre)
        output = cls.getOutPutOfCmd(cmd_str)
        words = cls.getWordsOfLine(output)
        return "{0}G".format((int(words[1])/1024/1024/1024))

    @classmethod
    def getCacheSize(cls, cacheDev):
        cacheID = cls.getIdByCacheDev(cacheDev)
        cmd_str = "casadm -P -i {0}| grep \"Cache Size\"".format(cacheID)
        output = cls.getOutPutOfCmd(cmd_str)
        words = cls.getWordsOfLine(output)
        return "{0}G".format(int(float(words[6])))
    
    @classmethod
    def getOutPutOfCmd(cls, commandStr):
        output = subprocess.check_output(commandStr, shell=True)
        return output.strip(" ").rstrip(" \n")
    
    @classmethod
    def getWordsOfLine(cls, line):
        words = re.split(",| ", line)
        valid_words = []
        for word in words:
            if word:
                valid_words.append(word)
        return valid_words

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