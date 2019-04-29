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

from loggerHelper import *

SECOND = "SECOND"
MINUTE = "MINUTE"
INVALID_CACHE_ID = -100
DEFAULT_CYCLE_TIME = 60

class MyTimeStamp():
    def __init__(self):
        return 0
    
    @classmethod
    def getAppendTime(cls):
        return datetime.datetime.now().strftime("%Y_%m_%d_%H_%M")
    
    # Used to get the timestamp with seconds or minutes
    # By default, it is by minute
    @classmethod
    def getDateAndTime(cls, time_granularity=""):
        if (SECOND == time_granularity):
            return (datetime.datetime.now().strftime("%Y-%m-%d"), datetime.datetime.now().strftime("%H:%M:%S"))
        elif (MINUTE == time_granularity):
            return (datetime.datetime.now().strftime("%Y-%m-%d"), datetime.datetime.now().strftime("%H:%M"))
        else:
            return (datetime.datetime.now().strftime("%Y-%m-%d"), datetime.datetime.now().strftime("%H:%M:%S"))

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

# Used to config/prepare cache environment
class casAdmin():
    set_cache_volume = set()
    set_cache_instance = set()
    refresh_lock = threading.Lock()

    @classmethod 
    def cfgCacheCorePair(cls, cacheDev, coreDev, cacheMode = "wb"):
        cls.refresh_lock.acquire()

        cls.refreshCacheVolumeSet()
        cacheID = casAdmin.getAvailableCacheID()
        cls.cfgCacheInstance(cacheID, cacheDev, coreDev, cacheMode)
        cls.refreshCacheVolumeSet()

        cls.refresh_lock.release()
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
        (ret, output) = cls.getOutPutOfCmd(addCoreCmd)
        return ret

    @classmethod
    def startCache(cls, cacheID, cacheDev):
        startCacheCmd = "casadm -S -i {0} -d {1} --force".format(cacheID, cacheDev)
        (ret, output) = cls.getOutPutOfCmd(startCacheCmd)
        return ret
    
    @classmethod
    def setCacheMode(cls, cacheID, cacheMode):
        setCacheModeCmd = "casadm -Q -c {0} -i {1}".format(cacheMode, cacheID)
        cls.getOutPutOfCmd(setCacheModeCmd)
        return 0

    @classmethod
    def stopCacheInstance(cls, cacheID):
        cls.refresh_lock.acquire()
        stop_cache = "casadm -T -i {0} -n".format(cacheID)
        (ret, output) = cls.getOutPutOfCmd(stop_cache)
        cls.refreshCacheVolumeSet()
        cls.refresh_lock.release()
        return ret
    
    @classmethod
    def reCfgCacheCorePair(cls, cacheDev, coreDev, cacheMode = "wb"):
        cls.stopCacheInstance(cls.getIdByCacheDev(cacheDev))
        cls.cfgCacheCorePair(cacheDev, coreDev, cacheMode)
        return 0
    
    @classmethod
    def isCacheCoreClear(cls, cacheDev, coreDev):
        check_cmd = "casadm -L -o csv | egrep \"{0}|{1}\"".format(cacheDev, coreDev)
        (ret, output) = cls.getOutPutOfCmd(check_cmd)
        if (0 == ret):
            return False
        else:
            return True
    
    @classmethod
    def getAvailableCacheID(cls):
        cache_id_list = set()
        (instance_list, volume_list) = cls.fetchCacheVolumeSet()
        for instance in instance_list:
            cache_id_list.add(int(instance.cacheID))
        cache_id_list = sorted(cache_id_list)
        cur_cache_id = 1
        while (cur_cache_id in cache_id_list):
            cur_cache_id = cur_cache_id + 1
        return cur_cache_id
    
    @classmethod
    def getIdByCacheDev(cls, cacheDev):
        (cache_instance_list, cache_volume_list) = cls.fetchCacheVolumeSet()
        for cache_instance in cache_instance_list:
            if (cache_instance.cacheDisk == cacheDev):
                return cache_instance.cacheID
        return INVALID_CACHE_ID

    
    @classmethod
    def getIntelDiskByCoreDev(cls, coreDev):
        (cache_instance_list, cache_volume_list) = cls.fetchCacheVolumeSet()
        for cache_volume in cache_volume_list:
            if (cache_volume.coreDisk == coreDev):
                return cache_volume.casDisk
        return ""
        
    @classmethod
    def getCoreSizeInGib(cls, coreDev):
        coreDev_noPre = coreDev.replace("/dev/", "")
        cmd_str = "lsblk {0} -b -o NAME,SIZE|grep \"{1} \"".format(coreDev, coreDev_noPre)
        (ret, output) = cls.getOutPutOfCmd(cmd_str)
        words = cls.getWordsOfLine(output)
        return (int(words[1])/1024/1024/1024)

    @classmethod
    def getCacheSizeInGib(cls, cacheDev):
        cacheID = cls.getIdByCacheDev(cacheDev)
        cmd_str = "casadm -P -i {0}| grep \"Cache Size\"".format(cacheID)
        (ret, output) = cls.getOutPutOfCmd(cmd_str)
        if (0 == ret):
            words = cls.getWordsOfLine(output)
            if (6 < len(words)):
                return int(float(words[6]))
        return 0
    
    @classmethod
    def getOutPutOfCmd(cls, commandStr):
        try:
            output = subprocess.check_output(commandStr, shell=True)
            return (0, output.strip(" ").rstrip(" \n"))
        except:
            logMgr.info("**Exception** {0}".format(commandStr))
            return (1, "")
   
    @classmethod
    def getWordsOfLine(cls, line, delimiters = ""):
        if delimiters:
            words = re.split(delimiters, line)
        else:
            words = re.split(",| ", line)
        
        valid_words = []
        for word in words:
            if word:
                valid_words.append(word)
        return valid_words

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
    def dumpRawCasList(cls, output_str, dumpDir):
        dump_file = os.path.join(dumpDir, "casadmL_{0}.csv".format(MyTimeStamp.getAppendTime()))
        outF = open(dump_file, "w")
        outF.writelines(output_str)
        outF.close()
        return 0
    
    # Get raw information from casadm cmd
    @classmethod
    def getRawCasList(cls):
        get_cache_core_list = 'casadm -L -o csv'
        stats_output = subprocess.check_output(get_cache_core_list, shell=True)
        # print stats_output
        return stats_output

    @classmethod
    def parseRawCasList(cls, output_str):
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
        return (cls.set_cache_instance, cls.set_cache_volume)
    
    @classmethod
    def refreshCacheVolumeSet(cls, dumpDir = ""):
        cls.set_cache_instance = set()
        cls.set_cache_volume = set()
        raw_output_str = cls.getRawCasList()
        if dumpDir:
            cls.dumpRawCasList(raw_output_str, dumpDir)
        cls.parseRawCasList(raw_output_str)
        cls.set_cache_volume = sorted(cls.set_cache_volume)
        cls.set_cache_instance = sorted(cls.set_cache_instance)
        return (cls.set_cache_instance, cls.set_cache_volume)

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
    def hasPartionOnDev(cls, devName):
        check_cmd = "lsblk {0} | egrep \"disk|part\" | wc -l".format(devName)
        (ret, output) = cls.getOutPutOfCmd(check_cmd)
        if (0 == ret):
            if (1 < int(output)):
                return True
        else:
            return False
    
    @classmethod 
    def blockDeviceExist(cls, devName):
        check_cmd = "lsblk {0}".format(devName)
        (ret, output) = cls.getOutPutOfCmd(check_cmd)
        if (0 == ret):
            return True
        else:
            return False
    
    @classmethod
    def getFieldCachePerf(cls, cacheID, fieldName):
        check_cmd = "casadm -P -i {0} -o csv".format(cacheID)
        (ret, output) = cls.getOutPutOfCmd(check_cmd)
        if (0 != ret):
            return ""
        lines = output.splitlines()
        if (2 != len(lines)):
            return ""
        headerS = cls.getWordsOfLine(lines[0], ",")
        dataS   = cls.getWordsOfLine(lines[1], ",")
        index = 0
        for head in headerS:
            if (fieldName == head):
                # print "Found Value {0} for field {1} at index {2}".format(dataS[index], fieldName, index)
                return dataS[index]
            index += 1
        return ""