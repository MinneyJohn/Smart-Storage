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
        logMgr.info("Start of configure cache instance")
        cls.refreshCacheVolumeSet()
        cacheID = casAdmin.getAvailableCacheID()
        cls.cfgCacheInstance(cacheID, cacheDev, coreDev, cacheMode)
        cls.refreshCacheVolumeSet()
        logMgr.info("End of configure cache instance")
        cls.refresh_lock.release()
        return 0
    
    @classmethod
    def cfgCacheInstance(cls, cacheID, cacheDev, coreDev, cacheMode):
        cls.startCache(cacheID, cacheDev)
        cls.addCore(cacheID, coreDev)
        cls.setCacheMode(cacheID, cacheMode)
        cls.setCleanPolicy(cacheID, "nop")
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
    def setCleanPolicy(cls, cacheID, cleanPolicy):
        setCleanPolicyCmd = "casadm -X -n cleaning -i {0} -p {1}".format(cacheID, cleanPolicy)
        (ret, output) = cls.getOutPutOfCmd(setCleanPolicyCmd)
        return ret

    @classmethod
    def setCacheMode(cls, cacheID, cacheMode):
        setCacheModeCmd = "casadm -Q -c {0} -i {1}".format(cacheMode, cacheID)
        cls.getOutPutOfCmd(setCacheModeCmd)
        return 0

    @classmethod
    def stopCacheInstance(cls, cacheID):
        cls.refresh_lock.acquire()
        logMgr.info("Start of Stop Cache Instance {0}".format(cacheID))
        stop_cache = "casadm -T -i {0} -n".format(cacheID)
        (ret, output) = cls.getOutPutOfCmd(stop_cache)
        cls.refreshCacheVolumeSet()
        logMgr.info("End of Stop Cache Instance {0}".format(cacheID))
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
            if (cls.getBlkFullPath(cache_instance.cacheDisk) == cls.getBlkFullPath(cacheDev)):
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
            logMgr.debug("Plan to run: {0}".format(commandStr))
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

    # /dev/intelcasn-m means device for cache n and core m
    @classmethod
    def getCacheCoreIdByDevName(cls, device_name):
        m = re.match(r"/dev/intelcas(?P<cache_id>\d+)-(?P<core_id>\d+)(\n)*", device_name)
        if (m):
            return (int(m.group('cache_id')), int(m.group('core_id')))
        else:
            logMgr.debug("Do NOT find the caching/core device ID for blkdev {0}".format(device_name))
            return (INVALID_CACHE_ID, INVALID_CACHE_ID)
    
    @classmethod
    def insertCacheInstance(cls, fields):
        #cls.list_cache_instance.append(CacheInstance(fields[1], fields[2]))
        cls.set_cache_instance.add(CacheInstance(int(fields[1]), fields[2]))
        return 0
    
    @classmethod
    def insertCacheVolume(cls, fields):
        (cache_id, core_id) = cls.getCacheCoreIdByDevName(fields[5])
        if (INVALID_CACHE_ID == cache_id or INVALID_CACHE_ID == core_id):
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
        return stats_output.decode()

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
        print("We got those cache instances:")
        for cache_instance in cls.set_cache_instance:
            print(cache_instance)
        print("We got those cache volumes:")
        for cache_volume in cls.set_cache_volume:
            print(cache_volume)
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
        command = "mount {0} {1}".format(cls.getBlkFullPath(blkDev), mountPoint)
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
        (ret, memory_in_kb) = casAdmin.getOutPutOfCmd(checkCmd)
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
        (ret, dfOut) = casAdmin.getOutPutOfCmd(checkCmd)
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
        (ret, output) = casAdmin.getOutPutOfCmd(restartCmd)
        return ret
    
    @classmethod
    def stop(cls, instID):
        stopCmd = "systemctl stop mysqld@{0}".format(instID)
        (ret, output) = casAdmin.getOutPutOfCmd(stopCmd)
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
        return casAdmin.getOutPutOfCmd(sqlCmd)

    @classmethod
    def genesis(cls, instID):
        datadir = mySqlCfg.queryOpt(instID, "datadir")
        logMgr.info("Initial mysql instance {0} with dataDir {1}".format(instID, datadir))
        if ("" == datadir):
            return -1

        (ret, output) = casAdmin.getOutPutOfCmd("sudo mkdir -p {0}".format(datadir))
        if (ret):
            return ret
        
        (ret, output) = casAdmin.getOutPutOfCmd("sudo rm -fr {0}/*".format(datadir))
        if (ret):
            return ret

        (ret, output) = casAdmin.getOutPutOfCmd("sudo chmod -R 777 {0}".format(datadir))
        if (ret):
            return ret

        (ret, output) = casAdmin.getOutPutOfCmd("sudo chown -hR mysql:mysql {0}".format(datadir))
        if (ret):
            return ret

        (ret, output) = casAdmin.getOutPutOfCmd("sudo mysqld --initialize-insecure --user=mysql --datadir={0}".format(datadir))
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
            if finishEvent.isSet():
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
    
    @classmethod
    def showOpt(cls):
        print("Your bench mark is configured as follows:")
        for section in cls.taskCfg:
            for opt in cls.taskCfg[section]:
                print("{0}: {1}".format(opt, cls.queryOpt(section, opt)))