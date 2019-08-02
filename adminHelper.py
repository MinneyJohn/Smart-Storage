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
import configparser
import shutil
import fnmatch

from loggerHelper import *

SECOND = "SECOND"
MINUTE = "MINUTE"
INVALID_CACHE_ID = -100
DEFAULT_CYCLE_TIME = 60

# Read Mode for CAS disks
READ_MISS = 0
READ_HIT = 1

# Write Mode for CAS disks
WRITE_MISS = 0
WRITE_HIT  = 2

class MyTimeStamp():
    def __init__(self):
        return 0
    
    @classmethod
    def getAppendTime(cls):
        return datetime.datetime.now().strftime("%Y_%m_%d_%Hh_%Mm")
    
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

    @classmethod
    def getDateAndTimeWithDelta(cls, timeBegin, deltaSeconds):
        newTime = timeBegin + datetime.timedelta(seconds = deltaSeconds)
        return (newTime.strftime("%Y-%m-%d"), newTime.strftime("%H:%M:%S")) 

class casAdmin():
    refresh_lock = threading.Lock()
    cachingSet = {}
    mapping = {}
    casCfg = configparser.ConfigParser(allow_no_value=True)

    # Please notice: this method will only load the casCfg into memory without doing real cas cfg
    @classmethod
    def loadCasCfg(cls, cfgFileIn):
        cls.cachingSet = {}
        cls.mapping = {}

        logMgr.info("Loading {0} into memory for future configuration".format(cfgFileIn))
        # First, touch a fake cfg file as the default intelcas.conf will report no section
        # by configureparser, error is "contains no section headers"
        fakeCfgFile = os.path.join(logMgr.getDataDir(), "fakeIntelCAS.conf")
        with open(fakeCfgFile, "w+") as fakeCfg:
            fakeCfg.write("[fakeSection]\n")
            with open(cfgFileIn, "r") as sysCfg:
                lines = sysCfg.read()
                fakeCfg.write(lines)
                sysCfg.close()
                fakeCfg.close()
        
        cls.casCfg.optionxform = str # do not transfer to lower case
        cls.casCfg.read(fakeCfgFile)

        for section in cls.casCfg.sections():
            if 'caches' == section:
                for opt in cls.casCfg.options(section):
                    words = opt.split()
                    cacheID    = int(words[0])
                    cachingDev = words[1]
                    if cacheID in cls.mapping:
                        logMgr.info("**ERROR** Dup cache ID {0}, NOT allowed".format(cacheID))
                        exit(0)
                    if False == sysAdmin.blockDeviceExist(cachingDev):
                        logMgr.info("**ERROR** Block Device {0} NOT existing".format(cachingDev))
                        exit(0)
                    
                    cachingDev = sysAdmin.getDeviceLogicName(cachingDev)
                    logMgr.debug("Adding {0} as cacheID {1}".format(cachingDev, cacheID))
                    cls.addCacheToCfgTable(cacheID, cachingDev)

            if 'cores' == section:
                for opt in cls.casCfg.options(section):
                    words = opt.split()
                    cacheID = int(words[0])
                    coreID  = int(words[1])
                    coreDev = words[2]

                    if cacheID not in cls.mapping:
                        logMgr.info("**ERROR** Cache ID {0} not existing when inserting core".format(cacheID))
                        exit(0)
                    if coreID in cls.mapping[cacheID]:
                        logMgr.info("**ERROR** Core ID {0} dup for CacheID {1}".format(coreID, cacheID))
                        exit(0)
                    if False == sysAdmin.blockDeviceExist(coreDev):
                        logMgr.info("**ERROR** Block Device {0} NOT existing".format(coreDev))
                        exit(0)

                    coreDev = sysAdmin.getDeviceLogicName(coreDev)
                    logMgr.debug("Adding {0} as coreID {1}, cacheID {2}".format(coreDev, coreID, cacheID))
                    cls.addCoreToCfgTable(cacheID, coreID, coreDev)
        cls.showAll()

    # cfgFile = "/etc/intelcas/intelcas.conf"
    @classmethod
    def initByCasCfg(cls):
        logMgr.info("Starting CAS Configuration")
        for cacheID, cachingDev in cls.cachingSet.items():
            logMgr.debug("Starting Caching {0} using {1}".format(cacheID, cachingDev))
            cls.startCache(cacheID, cachingDev, bSkipTableRefresh=True)
            cls.setCacheMode(cacheID, "wb")
            cls.setCleanPolicy(cacheID, "nop")    
            for coreID, devices in cls.mapping[cacheID].items():
                cls.addCore(cacheID, devices[1], coreIDIn = coreID)
                logMgr.debug("Adding core {0} to coreID {1}".format(devices[1], coreID))
        logMgr.info("End of CAS Configuration")
        return 0
    
    @classmethod
    def recfgByCasCfg(cls, cfgFileIn):
        cls.clearByCasCfg()
        cls.loadCasCfg(cfgFileIn)
        cls.initByCasCfg()

    @classmethod
    def clearByCasCfg(cls):
        logMgr.info("Starting of Clear CAS configuration")
        cls.refresh_lock.acquire()
        for cacheID in cls.mapping:
            logMgr.debug("Stopping Caching {0}".format(cacheID))
            cls.stopCacheInstance(cacheID, bSkipTableUpdate=True)
        cls.refresh_lock.release()
        logMgr.info("End of Clear CAS configuration")

    @classmethod
    def reCfgCacheCorePair(cls, cacheDev, coreDev, cacheMode = "wb"):
        cls.refresh_lock.acquire()
        cls.stopCacheInstance(cls.getIdByCacheDev(cacheDev))
        cls.cfgCacheCorePair(cacheDev, coreDev, cacheMode)
        cls.refresh_lock.release()
        return 0
    
    @classmethod
    def cfgCacheCorePair(cls, cacheDev, coreDev, cacheMode = "wb"):
        cls.refresh_lock.acquire()
        logMgr.info("Start of configure cache instance")
        
        cacheID = cls.getAvailableCacheID()
        cls.cfgCacheInstance(cacheID, cacheDev, coreDev, cacheMode)
        logMgr.info("End of configure cache instance")
        cls.refresh_lock.release()
        return 0

    @classmethod
    def getAllCachingDevices(cls, cacheID_filter = INVALID_CACHE_ID):
        cachingList = []
        for cacheID, cacheDev in cls.cachingSet.items():
            if (INVALID_CACHE_ID != cacheID_filter) and (cacheID != cacheID_filter):
                continue
            else:
                cachingList.append(cacheDev)
        return cachingList

    @classmethod
    def getAllCoreDevices(cls, beforeInit = False, cacheID_filter = INVALID_CACHE_ID):
        coreList = []
        for cacheID, coresDict in cls.mapping.items():
            if (INVALID_CACHE_ID != cacheID_filter) and (cacheID != cacheID_filter):
                continue
            else:           
                for coreID, drives in coresDict.items():
                    coreList.append(drives[1])
        return coreList
    
    @classmethod
    def getAllCasDevices(cls, cacheID_filter = INVALID_CACHE_ID):
        casList = []
        for cacheID, coresDict in cls.mapping.items():
            if (INVALID_CACHE_ID != cacheID_filter) and (cacheID != cacheID_filter):
                continue
            else:
                for coreID, drives in coresDict.items():
                    casList.append(drives[2])
        return casList
    
    @classmethod
    def getCachingCoreByCasDevice(cls, casDevice):
        for cacheID, cores in cls.mapping.items():
            for coreID, devices in cls.mapping[cacheID].items():
                if os.path.basename(casDevice) == os.path.basename(devices[2]):
                    return (devices[0], devices[1])
        return ("", "")

    @classmethod
    def getCasDeviceByCaching(cls, cachingDevice):
        for cacheID, cores in cls.mapping.items():
            for coreID, devices in cls.mapping[cacheID].items():
                if os.path.basename(cachingDevice) == os.path.basename(devices[0]):
                    return devices[2]

    @classmethod
    def getCoreSize(cls, casDevice):
        (cachingDev, coreDev) = cls.getCachingCoreByCasDevice(casDevice)
        return sysAdmin.getBlockDeviceSize(coreDev)

    @classmethod
    def getCachingSize(cls, casDevice):
        (cachingDev, coreDev) = cls.getCachingCoreByCasDevice(casDevice)
        return sysAdmin.getBlockDeviceSize(cachingDev)
    
    @classmethod
    def showAll(cls):
        logMgr.debug("Here is the CAS information in the table")
        for cacheID, cores in cls.mapping.items():
            for coreID, devices in cls.mapping[cacheID].items():
                logMgr.debug("[{0}, {1}] {2} with {3}, {4}"\
                            .format(cacheID, coreID, devices[2], devices[0], devices[1]))
                
    @classmethod
    def cfgCacheInstance(cls, cacheID, cacheDev, coreDev, cacheMode, coreIDIn = INVALID_CACHE_ID):
        cls.startCache(cacheID, cacheDev)
        cls.addCore(cacheID, coreDev, coreIDIn = coreIDIn)
        cls.setCacheMode(cacheID, cacheMode)
        cls.setCleanPolicy(cacheID, "nop")
        return 0
    
    @classmethod
    def addCore(cls, cacheID, coreDev, coreIDIn = INVALID_CACHE_ID):
        if INVALID_CACHE_ID == coreIDIn:
            addCoreCmd = "casadm -A -i {0} -d {1}".format(cacheID, coreDev)
        else:
            addCoreCmd = "casadm -A -i {0} -d {1} -j {2}".format(cacheID, coreDev, coreIDIn)
        (ret, output) = sysAdmin.getOutPutOfCmd(addCoreCmd)
        if 0 == ret:
            if INVALID_CACHE_ID == coreIDIn:
                coreID = cls.getCoreIdByName(coreDev)
            else:
                coreID = coreIDIn

            if (INVALID_CACHE_ID == coreID):
                return INVALID_CACHE_ID
            else:
                cls.addCoreToCfgTable(cacheID, coreID, coreDev)
        return ret
    
    @classmethod
    def getCoreIdByName(cls, coreDev):
        command = "casadm -L -o csv | grep {0}".format(coreDev)
        (ret, output) = sysAdmin.getOutPutOfCmd(command)
        words = sysAdmin.getWordsOfLine(output)
        if 3 < len(words):
            if coreDev == words[2]:
                return (int(words[1]))
        else:
            return INVALID_CACHE_ID

    @classmethod
    def startCache(cls, cacheID, cacheDev, bSkipTableRefresh = False):
        startCacheCmd = "casadm -S -i {0} -d {1} --force".format(cacheID, cacheDev)
        (ret, output) = sysAdmin.getOutPutOfCmd(startCacheCmd)
        if (0 == ret and False == bSkipTableRefresh):
            cls.addCacheToCfgTable(cacheID, cacheDev)
        return ret
    
    @classmethod
    def setCleanPolicy(cls, cacheID, cleanPolicy):
        setCleanPolicyCmd = "casadm -X -n cleaning -i {0} -p {1}".format(cacheID, cleanPolicy)
        (ret, output) = sysAdmin.getOutPutOfCmd(setCleanPolicyCmd)
        return ret

    @classmethod
    def setCacheMode(cls, cacheID, cacheMode):
        setCacheModeCmd = "casadm -Q -c {0} -i {1}".format(cacheMode, cacheID)
        sysAdmin.getOutPutOfCmd(setCacheModeCmd)
        return 0

    @classmethod
    def stopCacheInstance(cls, cacheID, bSkipTableUpdate = False):
        logMgr.info("Start of Stop Cache Instance {0}".format(cacheID))
        stop_cache = "casadm -T -i {0} -n".format(cacheID)
        (ret, output) = sysAdmin.getOutPutOfCmd(stop_cache)
        if False == bSkipTableUpdate:
            cls.removeCacheFromCfgTable(cacheID)
        logMgr.info("End of Stop Cache Instance {0}".format(cacheID))
        return ret
    
    @classmethod
    def removeCacheFromCfgTable(cls, cacheID):
        cls.cachingSet.pop(cacheID, None)
        cls.mapping.pop(cacheID, None)
    
    @classmethod
    def addCacheToCfgTable(cls, cacheID, cacheDev):
        cls.cachingSet[cacheID] = cacheDev
        cls.mapping[cacheID] = {}
        return 0
    
    @classmethod
    def addCoreToCfgTable(cls, cacheID, coreID, coreDev):
        cachingDev = cls.cachingSet[cacheID]
        cls.mapping[cacheID][coreID] = [cachingDev, coreDev,\
                                        sysAdmin.getBlkFullPath("intelcas{0}-{1}".format(cacheID, coreID))]
        return 0
    
    @classmethod
    def isCacheCoreClear(cls, cacheDev, coreDev):
        check_cmd = "casadm -L -o csv | egrep \"{0}|{1}\"".format(cacheDev, coreDev)
        (ret, output) = sysAdmin.getOutPutOfCmd(check_cmd)
        if (0 == ret):
            return False
        else:
            return True
    
    @classmethod
    def getAvailableCacheID(cls):
        cur_cache_id = 1
        while cur_cache_id in cls.cachingSet:
            cur_cache_id = cur_cache_id + 1
        return cur_cache_id
    
    @classmethod
    def getIdByCacheDev(cls, cacheDev):
        for cacheID, curDev in cls.cachingSet.items():
            if curDev == cacheDev:
                return cacheID
        return INVALID_CACHE_ID
    
    # DEBUG - TODO
    @classmethod
    def getOccupySize(cls, casDisk):
        return 0
    
    @classmethod
    def getDirtySize(cls, casDisk):
        (cacheID, coreID) = cls.getCacheCoreIdByDevName(casDisk)
        dirtyBlocks = int(cls.getOneFieldInCacheStats(cacheID, "Dirty [4KiB blocks]", coreID = coreID))
        dirtyInGB = int((dirtyBlocks * 4)/1024/1024)
        return dirtyInGB
    
    @classmethod
    def refreshRunning(cls):
        cls.cachingSet = {}
        cls.mapping    = {}

        get_cache_core_list = 'casadm -L -o csv'
        (ret, stats_output) = sysAdmin.getOutPutOfCmd(get_cache_core_list)
        if ret:
            return ret

        lines = stats_output.splitlines()
        for line in lines:
            words = line.split(',')
            if ('cache' == words[0]):
                cls.addCacheToCfgTable(int(words[1]), words[2])
            elif ('core' == words[0] and words[5].startswith('/dev/intelcas')):
                (cacheID, coreID) = cls.getCacheCoreIdByDevName(words[5])
                cls.addCoreToCfgTable(cacheID, words[1], words[2])
            else:
                pass

        cls.showAll()
        return 0
    
    @classmethod
    def dumpRawCasList(cls, output_str, dumpDir):
        dump_file = os.path.join(dumpDir, "casadmL_{0}.csv".format(MyTimeStamp.getAppendTime()))
        outF = open(dump_file, "w")
        outF.writelines(output_str)
        outF.close()
        return 0
    
    @classmethod
    def getOneFieldInCacheStats(cls, cacheID, fieldName, coreID = INVALID_CACHE_ID):
        if INVALID_CACHE_ID == coreID:
            check_cmd = "casadm -P -i {0} -o csv".format(cacheID)
        else:
            check_cmd = "casadm -P -i {0} -j {1} -o csv".format(cacheID, coreID)
        (ret, output) = sysAdmin.getOutPutOfCmd(check_cmd)
        if (0 != ret):
            return ""
        lines = output.splitlines()
        if (2 != len(lines)):
            return ""
        headerS = sysAdmin.getWordsOfLine(lines[0], ",")
        dataS   = sysAdmin.getWordsOfLine(lines[1], ",")
        index = 0
        for head in headerS:
            if (fieldName == head):
                # print "Found Value {0} for field {1} at index {2}".format(dataS[index], fieldName, index)
                return dataS[index]
            index += 1
        return ""
    
    @classmethod
    def getCacheCoreIdByDevName(cls, casDisk):
        casDisk = sysAdmin.getBlkFullPath(casDisk)
        m = re.match(r"/dev/intelcas(?P<cache_id>\d+)-(?P<core_id>\d+)(\n)*", casDisk)
        if (m):
            return (int(m.group('cache_id')), int(m.group('core_id')))
        else:
            logMgr.debug("Do NOT find the caching/core device ID for blkdev {0}".format(casDisk))
            return (INVALID_CACHE_ID, INVALID_CACHE_ID)
    
    @classmethod
    def isIntelCasDisk(cls, blkDev):
        baseName = os.path.basename(blkDev)
        if baseName.startswith("intelcas"):
            return True
        else:
            return False
    
# Used to config/prepare cache environment
class sysAdmin():
    @classmethod
    def getBlockDeviceSize(cls, blkDev):
        blkDev = cls.getBlkFullPath(blkDev)
        if blkDev.startswith("/dev/intelcas"):
            return cls.getSizeCasDisk(blkDev)
        else:
            return cls.getSizeNormalDisk(blkDev)

    @classmethod
    def getSizeNormalDisk(cls, blkDev):
        coreDev = cls.getBlkFullPath(blkDev)
        coreDev_noPre = coreDev.replace("/dev/", "")
        cmd_str = "lsblk {0} -b -o NAME,SIZE|grep \"{1} \"".format(coreDev, coreDev_noPre)
        (ret, output) = cls.getOutPutOfCmd(cmd_str)
        words = cls.getWordsOfLine(output)
        return int(int(words[1])/1024/1024/1024)

    @classmethod
    def getSizeCasDisk(cls, blkDev):
        (cacheID, coreID) = casAdmin.getCacheCoreIdByDevName(blkDev)
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
            logMgr.debug("Plan to run: {0}".format(commandStr))
            output = subprocess.check_output(commandStr, shell=True)
            return (0, output.decode().strip(" ").rstrip(" \n"))
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
        
    '''
    [root@sm114 Smart-Storage]# blkid -po udev /dev/nvme1n1
    ID_FS_UUID=3efeab2b-f08a-46bc-aa9d-82186a4dfa58
    ID_FS_UUID_ENC=3efeab2b-f08a-46bc-aa9d-82186a4dfa58
    ID_FS_VERSION=1.0
    ID_FS_TYPE=ext4
    ID_FS_USAGE=filesystem
    '''
    @classmethod
    def getBlkFSType(cls, blkDev):
        fullPath = cls.getBlkFullPath(blkDev)
        command = "blkid -po udev {0} | grep ID_FS_TYPE".format(fullPath)
        (ret, output) = cls.getOutPutOfCmd(command)
        if (0 == ret and output):
            lines = output.splitlines()
            words = lines[0].split("=")
            return words[1]
        return ""
    
    @classmethod
    def getBlkFullPath(cls, blkDev):
        return os.path.join("/dev", os.path.basename(blkDev))

    '''
    [root@sm119 Smart-Storage]# ls -l /dev/disk/by-id/nvme-INTEL_SSDPE2MD016T4_PHFT5523001E1P6JGN-part1
    lrwxrwxrwx 1 root root 15 Jul 22 00:07 /dev/disk/by-id/nvme-INTEL_SSDPE2MD016T4_PHFT5523001E1P6JGN-part1 -> ../../nvme0n1p1
    '''
    @classmethod
    def getDeviceLogicName(cls, blkDev):
        if "by-id" in blkDev:
            command = "ls -l {0}".format(blkDev)
            (ret, output) = cls.getOutPutOfCmd(command)
            if 0 == ret:
                lines = output.splitlines()
                words = lines[0].split()
                return cls.getBlkFullPath(os.path.basename(words[10]))
        else:
            return cls.getBlkFullPath(blkDev)

    '''
    [root@sm114 ~]# mount -l | grep nvme1n1
    /dev/nvme1n1 on /mnt/optane-sql type ext4 (rw,relatime,data=ordered)
    '''
    @classmethod
    def isBlkMounted(cls, blkDev):
        baseDev = os.path.basename(blkDev)
        command = "mount -l | grep {0}".format(baseDev)
        (ret, output) = cls.getOutPutOfCmd(command)
        if ret:
            return False
        if output:
            lines = output.splitlines()
            for line in lines:
                if baseDev in line:
                    words = line.split()
                    if baseDev == os.path.basename(words[0]):
                        return True
        return False
    
    @classmethod
    def mkFS(cls, blkDev, fsType):
        command = "mkfs.{0} {1}".format(fsType, cls.getBlkFullPath(blkDev))
        (ret, output) = cls.getOutPutOfCmd(command)
        return ret

    @classmethod
    def doMount(cls, blkDev, mountPoint):
        command = "mount -o sync {0} {1}".format(cls.getBlkFullPath(blkDev), mountPoint)
        (ret, output) = cls.getOutPutOfCmd(command)
        return ret
    
    @classmethod
    def doUnMount(cls, mountPoint):
        command = "umount {0}".format(mountPoint)
        (ret, output) = cls.getOutPutOfCmd(command)
        return ret
    
    # TODO
    @classmethod
    def getTotalMemory(cls):
        checkCmd = "vmstat -s|grep \"total memory\"|awk '{print $1}'"
        (ret, memory_in_kb) = sysAdmin.getOutPutOfCmd(checkCmd)
        memory_in_GB = int(int(memory_in_kb) / 1024 / 1024)
        logMgr.debug("There are {0}G physical memory in total".format(memory_in_GB))
        return memory_in_GB
    
    '''
    [root@sm114 2019_07_10_22h_14m]# df /mnt/qlc-sql/sbtest
    Filesystem      1K-blocks      Used  Available Use% Mounted on
    /dev/nvme0n1   7442192600 111097936 6956004984   2% /mnt/qlc-sql
    '''
    @classmethod
    def getBlockDevice(cls, dataDir):
        checkCmd = "df {0}".format(dataDir)
        (ret, dfOut) = sysAdmin.getOutPutOfCmd(checkCmd)
        if 0 == ret and dfOut:
            lines = dfOut.splitlines()
            if (2 == len(lines)):
                line = lines[1]
                words = line.split()
                return words[0]
        return ""

'''
This class is used for access/change the mysql configuration file my.cnf
'''
class mySqlCfg():
    sqlCfg = configparser.ConfigParser(allow_no_value=True)
    sqlCfg.read("/etc/my.cnf")
    
    @classmethod
    def getSection(cls, instID):
        return "mysqld@{0}".format(instID)

    @classmethod
    def changeOpt(cls, instID, optName, optValue=""):
        section = cls.getSection(instID)
        if optValue:
            cls.sqlCfg[section][optName] = optValue
        else: # For option without value
            cls.sqlCfg[section][optName] = None
        with open("/etc/my.cnf", "w") as configfile:
            cls.sqlCfg.write(configfile)
            configfile.close()
    
    @classmethod
    def removeOpt(cls, instID, optName):
        section = cls.getSection(instID)
        cls.sqlCfg.remove_option(section, optName)
    
    @classmethod
    def showOpt(cls, instID):
        section = cls.getSection(instID)
        for opt in cls.sqlCfg[section]:
            print ("{0}:{1}".format(opt, cls.sqlCfg[section][opt]))
    
    @classmethod
    def queryOpt(cls, instID, optName):
        section = cls.getSection(instID)
        if optName in cls.sqlCfg[section]:
            return cls.sqlCfg[section][optName]
        else:
            return ""

'''
This class is to do control on mysql instance:
* Eg. restart mysql instance
* Do sql query against
* Purge the binlog files
'''
class mySqlInst():    
    @classmethod
    def restart(cls, instID):
        restartCmd = "systemctl restart mysqld@{0}".format(instID)
        (ret, output) = sysAdmin.getOutPutOfCmd(restartCmd)
        return ret
    
    @classmethod
    def stop(cls, instID):
        stopCmd = "systemctl stop mysqld@{0}".format(instID)
        (ret, output) = sysAdmin.getOutPutOfCmd(stopCmd)
        return ret

    @classmethod
    def executeSqlStsm(cls, instID, stsm, pwd=""):
        sock = mySqlCfg.queryOpt(instID, "socket")
        port = mySqlCfg.queryOpt(instID, "port")
        if pwd:
            sqlCmd = "mysql -u root -p{0} -e \"{1}\" --socket={2} --port={3}"\
                    .format(pwd, stsm, sock, port)
        else:
            sqlCmd = "mysql -u root -e \"{0}\" --socket={1} --port={2}"\
                    .format(stsm, sock, port)
        return sysAdmin.getOutPutOfCmd(sqlCmd)

    @classmethod
    def genesis(cls, instID):
        datadir = mySqlCfg.queryOpt(instID, "datadir")
        logMgr.info("Initial mysql instance {0} with dataDir {1}".format(instID, datadir))
        if ("" == datadir):
            return -1

        (ret, output) = sysAdmin.getOutPutOfCmd("sudo mkdir -p {0}".format(datadir))
        if (ret):
            return ret
        
        (ret, output) = sysAdmin.getOutPutOfCmd("sudo rm -fr {0}/*".format(datadir))
        if (ret):
            return ret

        (ret, output) = sysAdmin.getOutPutOfCmd("sudo chmod -R 777 {0}".format(datadir))
        if (ret):
            return ret

        (ret, output) = sysAdmin.getOutPutOfCmd("sudo chown -hR mysql:mysql {0}".format(datadir))
        if (ret):
            return ret

        (ret, output) = sysAdmin.getOutPutOfCmd("sudo mysqld --initialize-insecure --user=mysql --datadir={0}".format(datadir))
        if (ret):
            return ret
        
        time.sleep(5)

        ret = cls.restart(instID)
        if (ret):
            logMgr.info("**ERROR** Failed to restart mysql instance {0}".format(instID))
            return ret

        time.sleep(5)

        logMgr.info("Done of mysqld initial")
        return ret
    
    @classmethod
    def getBinLogBaseName(cls, instID, pwd):
        binLogBase = ""
        getBinBaseStsm = "SHOW GLOBAL VARIABLES like 'log_bin_basename' \G"
        (ret, output) = mySqlInst.executeSqlStsm(instID, getBinBaseStsm, pwd)
        if (0 == ret):
            lines = output.splitlines()
            for line in lines:
                line = line.strip(" ").rstrip(" \n").replace(" ", "")
                if line.startswith("Value:"):
                    words = line.split(":")
                    if (2 == len(words)):
                        binLogBase = words[1]
                else:
                    continue
        return binLogBase

    @classmethod
    def purgeBinLog(cls, instID, pwd):
        binLogBase = cls.getBinLogBaseName(instID, pwd)
        (binFileDir, binFilePattern) = os.path.split(binLogBase)
        
        binLogList = []
        if ("" == binLogBase):
            return
        for fileName in os.listdir(binFileDir):
            if fnmatch.fnmatch(fileName, "{0}.[0-9]*".format(binFilePattern)):
                binLogList.append(fileName)
        binLogList = sorted(binLogList)
        if (3 < len(binLogList)):
            purgeStsm = "PURGE BINARY LOGS TO '{0}'".format(binLogList[-2])
            (ret, output) = mySqlInst.executeSqlStsm(instID, purgeStsm, pwd)
        return

# This class is used to run the scheduleTask    
class scheduleTask():
    def __init__(self, function, cycle, totalRun, finishEvent = threading.Event(), args=[], kwargs={}):
        self.func = function
        self.cycle = cycle
        self.totalRun = totalRun
        self.args = args
        self.kwargs = kwargs
        self.finishEvent = finishEvent
        
    def loop(self):
        N_cycles = int(self.totalRun / self.cycle)

        # Run first with alignment with cycle time
        time_seconds_now = datetime.datetime.now().time().second
        firstCycle = (self.cycle - (time_seconds_now % self.cycle))
        timer = threading.Timer(firstCycle, self.func, self.args, self.kwargs)
        timer.start()
        time.sleep(firstCycle)
        N_cycles -=1
     
        while N_cycles:
            if self.finishEvent.isSet():
                logMgr.info("Got finish notification of scheduleTask, Exit")
                break
            timer = threading.Timer(self.cycle, self.func, self.args, self.kwargs)
            timer.start()
            N_cycles -= 1
            time.sleep(self.cycle)

    def start(self, async = True):
        if (True == async): # Default
            loop_thread = threading.Thread(target=self.loop)
            loop_thread.start()
            return (0, loop_thread)
        else:
            self.loop()

class longTask():
    def __init__(self, func, align = 1, args=[], kwargs=None):
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.align = align
    
    def run(self):
        timer = threading.Timer(self.startTime, self.func, args=self.args, kwargs=self.kwargs)
        timer.start()
        return 0

    def start(self, async = True):
        time_seconds_now = datetime.datetime.now().time().second
        self.startTime = (self.align - (time_seconds_now % self.align))
        
        if (True == async):
            logMgr.debug("longTask will sleep {0} seconds for alignment".format(self.startTime))
            time.sleep(self.startTime)
            running_thread = threading.Thread(target=self.func, args=self.args, kwargs=self.kwargs)
            running_thread.start()
            return (0, running_thread)
        else:
            self.run()

class taskCfg():
    taskCfg = configparser.ConfigParser(allow_no_value=True)
    taskCfg.read("task.cnf")
    
    @classmethod
    def queryOpt(cls, section, opt):
        if section in cls.taskCfg:
            if opt in cls.taskCfg[section]:
                optStr = cls.taskCfg[section][opt]
                optStr = re.sub("\s+", "", optStr) # Remove Space
                return optStr
            else:
                return ""
        else:
            return ""
    
    @classmethod
    def showOpt(cls, sectionName = ""):
        print("Your bench mark is configured as follows:")
        for section in cls.taskCfg:
            if (sectionName and (section != sectionName)):
                continue
            for opt in cls.taskCfg[section]:
                print("{0}: {1}".format(opt, cls.queryOpt(section, opt)))