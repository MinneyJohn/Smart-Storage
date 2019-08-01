#! /usr/bin/python3

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

BASE_JOB_FILE = "base.fio"

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

BENCH_CACHING_ONLY = 1
BENCH_CORE_ONLY    = 2
BENCH_CAS_ONLY     = 3
BENCH_ALL          = 4

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
'''
Design Points:
 1. Though "wallstone" can be used to do jobs one by one, 
    I determined to NOT use this flag. As I'd like to keep 
    the job file seperate in case the user my want to run 
    the job file by themselves. Without the "wallstone" flag,
    the logic for rerun manually is more clear
2. The sub section should be indentified by the block device.
    Eg. sdb, nvme0n1, intelcas1-1
'''
class fioJob():
    def __init__(self, jobName, baseJobFile):
        self.jobName = jobName
        self.jobCfg  = configparser.ConfigParser(allow_no_value=True)
        self.jobFile = os.path.join(logMgr.getDataDir(), "{0}.{1}.fio"\
                        .format(jobName, MyTimeStamp.getAppendTime())) 
        
        self.jobCfg.read(baseJobFile)
        
    # Used to get FIO setting from task.cnf
    @classmethod
    def getSetting(cls, work, opt):
        if taskCfg.queryOpt(work, opt):
            return taskCfg.queryOpt(work, opt)
        else:
            return taskCfg.queryOpt('fio_global', opt)
    
    @classmethod
    def getWorkloadList(cls):
        worklist = []
        jobSettingStr = cls.getSetting('read', 'rwlist')
        words = jobSettingStr.split(",")
        for word in words:
            worklist.append(word)
        return worklist

    @classmethod
    def getNumJobList(cls, work):
        numjobList = []
        numjobListStr = cls.getSetting(work, 'numjoblist')
        if "" == numjobListStr:
            return [8]
        else:
            words = numjobListStr.split(",")
            for word in words:
                numjobList.append(int(word))
            return numjobList
    
    @classmethod
    def getRunTime(cls, work):
        timeStr = cls.getSetting(work, 'time')
        if "" == timeStr:
            return 600
        else:
            return int(timeStr)
            
    @classmethod
    def getBsList(cls, work):
        bsList = []
        bsListStr = cls.getSetting(work, 'bslist')
        if "" == bsListStr:
            return ['4k']
        else:
            words = bsListStr.split(",")
            for word in words:
                bsList.append(word)
            return bsList
    
    @classmethod
    def getIoDepthList(cls, work):
        iodepthList = []
        iodepthListStr = cls.getSetting(work, 'iodepthlist')
        if "" == iodepthListStr:
            return [8]
        else:
            words = iodepthListStr.split(",")
            for word in words:
                iodepthList.append(int(word))
            return iodepthList

    def saveJobFile(self):
        with open(self.jobFile, "w") as configfile:
            logMgr.debug("Save the fio job to {0}".format(self.jobFile))
            # By default, configParse will add space when doing write, but FIO does NOT accept it
            self.jobCfg.write(configfile, space_around_delimiters=False)
            configfile.close()

    def setGlobalOpt(self, optName, optValue = None):
        self.jobCfg.set('global', optName, str(optValue))
        
    def setSubOpt(self, subName, optName, optValue = None):
        self.jobCfg.set(subName, optName, str(optValue))
        
    def addOneSub(self, subName):
        self.jobCfg.add_section(subName)
        #return 0
    
    def getGlobalOpt(self, optName):
        return self.jobCfg.get('global', optName, fallback="NOT_EXIST")
    
    # Try to get opt value from sub job section, or return global
    def getSubOpt(self, subName, optName):
        subValue = self.jobCfg.get(subName, optName, fallback="NOT_EXIST")
        if "NOT_EXIST" == subValue:
            return self.getGlobalOpt(optName)
        else:
            return subValue

    # This is used to get the interested devices for FIO stats
    def getBlkDeviceList(self):
        deviceList = ""
        for section in self.jobCfg.sections():
            if "global" == section:
                continue
            else:
                if casAdmin.isIntelCasDisk(section):
                    (cachingDev, coreDev) = casAdmin.getCachingCoreByCasDevice(section)
                    deviceList = "{0} {1} {2} {3}".format(section, cachingDev, coreDev, deviceList)
                else:
                    deviceList = "{0} {1}".format(section, deviceList)
        return deviceList
    
    def isCasDiskJob(self):
        section = ""
        for section in self.jobCfg.sections():
            if "global" == section:
                continue
            else:
                break
        baseName = os.path.basename(section)
        if baseName.startswith("intelcas"):
            return True
        else:
            return False

    def run(self):    
        # Step 1: Save the job file for reference
        self.saveJobFile()

        # Step 2: Start stats collection for both iostat and cas perf
        fioFinishEvent = threading.Event()
        bCasDisk = self.isCasDiskJob()
    
        runTime = int(self.getGlobalOpt('runtime'))
        fioDriveStats = fioIOStats(DEFAULT_CYCLE_TIME, runTime + 120, logMgr.getDataDir(), \
                                    caseName = self.jobName, kwargs = {'fioJob': self})
        (ret, iostatThread) = fioDriveStats.start()
        if ret:
            logMgr.info("**ERROR** Failed to start thread to collect iostat for FIO job")
            exit(1)

        if True == bCasDisk:
            casPerf = casPerfStats(DEFAULT_CYCLE_TIME, runTime + 70, logMgr.getDataDir(), finish = fioFinishEvent)
            (ret, casPerfThread) = casPerf.start()
            if (ret):
                logMgr.info("**ERROR** Fail to start thread for cas perf stats")
                exit(1)
    
        # Step 3: Start FIO job
        fioCmd = "fio {0}".format(self.jobFile)
        logMgr.info("Starting fio job: {0}".format(fioCmd))
        sysAdmin.getOutPutOfCmd(fioCmd)
        logMgr.info("End of fio job: {0}".format(fioCmd))

        # Step 4: Wait for stats collection to complete
        fioFinishEvent.set()
        iostatThread.join()

        if True == bCasDisk:
            casPerfThread.join()

        return 0

class benchDevices():
    def __init__(self, benchName, devicesIn, rwList = []):
        self._deviceList = devicesIn
        self._benchName  = benchName
        if 0 == len(rwList):
            self._rwList = fioJob.getWorkloadList()
        else:
            self._rwList = rwList

    # The child can use here to do some special setting/work before starting one FIO job
    def preWork(self, job):
        return 0
    
    # The child can use here to do some special setting/work after finishing one FIO job
    def postWork(self, job):
        return 0
    
    def startBench(self):
        logMgr.info("Target devices: {0}".format(self._deviceList))
        for workload in self._rwList:
            numJobList  = fioJob.getNumJobList(workload)
            ioDepthList = fioJob.getIoDepthList(workload)
            bsList      = fioJob.getBsList(workload)
            time        = fioJob.getRunTime(workload)
            for numJob in numJobList:
                for ioDepth in ioDepthList:
                    for bs in bsList:
                        jobName = "{0}.{1}.{2}.{3}jobs.{4}depth"\
                                .format(self._benchName, workload, bs, numJob, ioDepth)
                        
                        job = fioJob(jobName, BASE_JOB_FILE)
                        job.setGlobalOpt('numjobs', numJob)
                        job.setGlobalOpt('bs', bs)
                        job.setGlobalOpt('iodepth', ioDepth)
                        job.setGlobalOpt('rw', workload)
                        job.setGlobalOpt('runtime', time)
                        
                        for device in self._deviceList:
                            job.addOneSub(device)
                            job.setSubOpt(device, 'filename', device)
                            job.setSubOpt(device, 'size', "{0}G".format(sysAdmin.getBlockDeviceSize(device)))
                            logMgr.debug("Adding device {0} to fio job".format(device))

                        self.preWork(job)    
                        job.run()
                        self.postWork(job)
        return 0

# Read Mode: 0 - miss; 1 - hit without warm; 2 - hit with warm;
class benchCasRead(benchDevices):
    def __init__(self, benchName, casCfgFile, casDeviceS, rw, readMode):
        self._mode       = readMode
        self._casDeviceS = casDeviceS
        self._rw         = rw
        self._casCfgFile = casCfgFile

        benchDevices.__init__(self, benchName, casDeviceS, rwList = [rw])

    def preWork(self, job):
        for casDisk in self._deviceList:
            if READ_MISS == self._mode:
                logMgr.info("Reconfig CAS before doing read miss")
                casAdmin.recfgByCasCfg(self._casCfgFile)
                job.setSubOpt(casDisk, 'size', "{0}G".format(casAdmin.getCoreSize(casDisk)))
            else:
                job.setSubOpt(casDisk, 'size', "{0}G".format(casAdmin.getDirtySize(casDisk)))
    
class benchCasWrite(benchDevices):
    def __init__(self, benchName, casCfgFile, casDeviceS, rw, writeMode):
        self._mode       = writeMode
        self._rw         = rw
        self._casCfgFile = casCfgFile
        benchDevices.__init__(self, benchName, casDeviceS, rwList = [rw])
    
    def preWork(self, job):
        if WRITE_MISS == self._mode:
            for casDisk in self._deviceList:
                logMgr.info("Reconfig CAS before doing write miss")
                casAdmin.recfgByCasCfg(self._casCfgFile)
                cachingSize = sysAdmin.getBlockDeviceSize(casDisk)
                job.setSubOpt(casDisk, 'size', "{0}G".format(cachingSize))
                
        elif WRITE_HIT == self._mode:
            for casDisk in self._deviceList:
                dirtySize = casAdmin.getDirtySize(casDisk)
                job.setSubOpt(casDisk, 'size', "{0}G".format(dirtySize))
    
class warmCache():
    def __init__(self, casDeviceS):
        self._casDeviceS = casDeviceS

    def startWarm(self):
        workload = "write"
        benchName = "cas.WarmCache"
        bs = "128K"
        numJob = 1
        ioDepth = 8
        time    = fioJob.getRunTime(workload)

        jobName = "{0}.{1}.{2}.{3}jobs.{4}depth"\
                                .format(benchName, workload, bs, numJob, ioDepth)
                        
        job = fioJob(jobName, BASE_JOB_FILE)
        job.setGlobalOpt('numjobs', numJob)
        job.setGlobalOpt('bs', bs)
        job.setGlobalOpt('iodepth', ioDepth)
        job.setGlobalOpt('rw', workload)
        job.setGlobalOpt('runtime', time)
                        
        for device in self._casDeviceS:
            job.addOneSub(device)
            job.setSubOpt(device, 'filename', device)
            job.setSubOpt(device, 'size', "{0}G".format(sysAdmin.getBlockDeviceSize(device)))

        job.run()
        
        return 0
            
class benchCASDisk():
    def __init__(self, casDeviceS, casCfgFile, rwList = []):
        if 0 == len(rwList):
            self._rwList = fioJob.getWorkloadList()
        else:
            self._rwList = rwList
        
        self._casDeviceS = casDeviceS
        self._casCfgFile = casCfgFile

    def startBench(self):
        # Do real CAS configuration
        casAdmin.initByCasCfg()

        if ("write" in self._rwList) or ("randwrite" in self._rwList):
            if ("randwrite" in self._rwList):
                # Do rand write miss
                benchRndWrite_Miss = benchCasWrite("cas.rndWriteMiss", self._casCfgFile, self._casDeviceS, "randwrite", WRITE_MISS)
                benchRndWrite_Miss.startBench()

                # Do rand write hit
                benchRndWrite_Hit = benchCasWrite("cas.rndWriteHit", self._casCfgFile, self._casDeviceS, "randwrite", WRITE_HIT)
                benchRndWrite_Hit.startBench()

            if ("write" in self._rwList):
                # Do seq write miss
                benchSeqWrite_Miss = benchCasWrite("cas.seqWriteMiss", self._casCfgFile, self._casDeviceS, "write", WRITE_MISS)
                benchSeqWrite_Miss.startBench()
                # Do seq write hit
                benchSeqWrite_Hit = benchCasWrite("cas.seqWriteHit", self._casCfgFile, self._casDeviceS, "write", WRITE_HIT)
                benchSeqWrite_Hit.startBench()
        
        if (("read" in self._rwList) or ("randRead" in self._rwList)):
            warmCacheWork = warmCache(self._casDeviceS)
            warmCacheWork.startWarm()

        if ("read" in self._rwList):
            casSeqRead_Hit = benchCasRead("cas.seqReadHit", self._casCfgFile, self._casDeviceS, 'read', READ_HIT)
            casSeqRead_Hit.startBench()

        if ("randread" in self._rwList):
            casRndRead_Hit = benchCasRead('cas.rndReadHit', self._casCfgFile, self._casDeviceS, 'randread', READ_HIT)
            casRndRead_Hit.startBench()

        # Reconfig CAS
        if ("read" in self._rwList):
            casSeqRead_Miss = benchCasRead('cas.seqReadMiss', self._casCfgFile, self._casDeviceS, 'read', READ_MISS)
            casSeqRead_Miss.startBench()
        
        # Reconfig CAS
        if ("randread" in self._rwList):
            casRndRead_Miss = benchCasRead('cas.rndReadMiss', self._casCfgFile, self._casDeviceS, 'rndread', READ_MISS)
            casRndRead_Miss.startBench()

        '''
        # Reconfig CAS
        casAdmin.redoByCasCfg(casCfg)
        casDevices = []
        casMixReadWrite()
        '''
        
        casAdmin.clearByCasCfg()

class casBaseLineBench():
    def __init__(self, casCfgFile, caseTYPE, rwList = []):
        if 0 == len(rwList):
            self._rwList = fioJob.getWorkloadList()
        else:
            self._rwList = rwList
        self._casCfgFile = casCfgFile
        self._caseTYPE   = caseTYPE
        
    def startBench(self):
        # Load the cfg file, but NOT do CAS configuration YET
        casAdmin.loadCasCfg(self._casCfgFile)

        # Bench Raw Devices
        self._cachingDeviceS  = casAdmin.getAllCachingDevices()
        self._coreDeviceS     = casAdmin.getAllCoreDevices()
        self._casDevieS       = casAdmin.getAllCasDevices()

        if ((self._caseTYPE == BENCH_CACHING_ONLY) or (self._caseTYPE == BENCH_ALL)):
            logMgr.info("Start bench for caching devices")
            benchAllCaching = benchDevices("cachingDevice", self._cachingDeviceS)
            benchAllCaching.startBench()
            logMgr.info("End of bench caching devices")

        if ((self._caseTYPE == BENCH_CORE_ONLY) or (self._caseTYPE == BENCH_ALL)):
            logMgr.info("Start bench for core devices")
            benchAllCore = benchDevices("coreDevice", self._coreDeviceS)
            benchAllCore.startBench()
            logMgr.info("End of bench core devices")
        
        # Bench CAS Devices
        if ((self._caseTYPE == BENCH_CAS_ONLY) or (self._caseTYPE == BENCH_ALL)):
            logMgr.info("Start bench for cas devices")
            benchAllCas = benchCASDisk(self._casDevieS, self._casCfgFile)
            benchAllCas.startBench()
            logMgr.info("End of bench cas devices")

        return 0