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
import configparser
from loggerHelper import *
from adminHelper import *
from statsHelper import *

class rocksDB():
    def __init__(self):
        self.datadir         = ""
        self.LD_LIBRARY_PATH = ""
        self.loadCfg()
        
    # TODO - auto clone/compile zstd/gflags/rocksdb later
    '''
    def getZstdDir(self):
        return ""
    
    def getGflagsDir(self):
        return ""
    '''

    def loadCfg(self):
        logMgr.info("Loading db_bench configuration from task.cnf")
        
        self.installDir      = taskCfg.queryOpt("db_bench_env", "installDir")
        if self.installDir:
            self.LD_LIBRARY_PATH = "{0}:{1}".format(os.path.join(self.installDir, "gflags/.libs"),\
                                                   os.path.join(self.installDir, "zstd/lib"))
            self.db_bench_path   = os.path.join(self.installDir, "rocksdb/db_bench")
        else:
            self.LD_LIBRARY_PATH = taskCfg.queryOpt("db_bench_env", "LD_LIBRARY_PATH")
            self.db_bench_path   = taskCfg.queryOpt("db_bench_env", "db_bench_path")
        
        self.dbBenchCfg      = taskCfg.querySection("db_bench")
        self.datadir         = taskCfg.queryOpt("db_bench", "db")
        self.stats_per_interval = int(taskCfg.queryOpt("db_bench", "stats_per_interval"))
        self.duration           = int(taskCfg.queryOpt("db_bench", "duration"))
        self.benchmarks      = taskCfg.queryOpt("db_bench", "benchmarks")
        self.rawDataFile     = os.path.join(logMgr.getDataDir(), "db_bench.{0}.data".format(MyTimeStamp.getAppendTime()))

        return 0
    
    def doInstall(self):
        repoDir = sysAdmin.cloneRepository("https://github.com/facebook/zstd", self.installDir, "zstd", "v1.1.3")
        if repoDir:
            sysAdmin.buildAndInstallRepo(repoDir, "zstd", self.installDir)
    
        repoDir = sysAdmin.cloneRepository("https://github.com/gflags/gflags", self.installDir, "gflags", "v2.0")
        if repoDir:
            sysAdmin.buildAndInstallRepo(repoDir, "gflags", self.installDir)
    
        repoDir = sysAdmin.cloneRepository("https://github.com/facebook/rocksdb", self.installDir, "rocksdb", "v5.18.3")
        if repoDir:
            sysAdmin.buildAndInstallRepo(repoDir, "rocksdb", self.installDir)  
        
        return 0

    def generateExeCmd(self, bPrepare=False):
        self.loadCfg()
        localRunCfg = self.dbBenchCfg

        # If prepare db, do special setting
        if (True == bPrepare):
            logMgr.info("Will prepare data")
            localRunCfg["benchmarks"]      = "fillseq"
            localRunCfg["use_existing_db"] = "0"
            localRunCfg["threads"]         = "1"
            localRunCfg["open_files"]      = "20480"
        
        cmdStr = ""
        if self.LD_LIBRARY_PATH:
            cmdStr = "ulimit -n 100000 && LD_LIBRARY_PATH={0} {1}".format(self.LD_LIBRARY_PATH, self.db_bench_path)
        else:
            cmdStr = "ulimit -n 100000 && {0}".format(self.db_bench_path)
            
        for optName in localRunCfg:
            if (True == bPrepare and "duration" == optName): # Skip "duration" for prepare db
                continue

            if None == localRunCfg[optName]:
                cmdStr = "{0} --{1}".format(cmdStr, optName)
            else:
                cmdStr = "{0} --{1}={2}".format(cmdStr, optName, localRunCfg[optName])
        
        cmdStr = "{0} > {1} 2>&1".format(cmdStr, self.rawDataFile)
        return cmdStr
    
    def exportResultToCSV(self):
        return 0

    def triggerBenchCmd(self, bPrepare=False):
        sysAdmin.setUlimit(40960)
                    
        cmdStr = self.generateExeCmd(bPrepare)
        logMgr.info("Starting: {0}".format(cmdStr))
        
        (ret, output) = sysAdmin.getOutPutOfCmd(cmdStr)
        if (0 == ret):
            self.exportResultToCSV()
        
        logMgr.info("Ending: {0}".format(cmdStr))
        return ret

    def formCaseNamePrefix(self):
        return self.benchmarks

    def prepareDB(self):
        return self.triggerBenchCmd(bPrepare=True)

    def rundbBench(self):
        dbBenchBackGround = longTask(self.triggerBenchCmd)
        (ret, dbBenchRunning) = dbBenchBackGround.start()
        if ret:
            return ret
        
        blockDevice = sysAdmin.getBlockDevice(self.datadir)
        logMgr.info("The data of rocksdb is on {0}".format(blockDevice))
        
        bCASRunning = False
        (cacheID, coreID) = casAdmin.getCacheCoreIdByDevName(blockDevice)
        if (INVALID_CACHE_ID == cacheID): # non cas device
            ioStat = ioStats(self.stats_per_interval, \
                            self.duration,\
                            logMgr.getDataDir(),\
                            caseName = self.formCaseNamePrefix(),\
                            kwargs = {'devList': blockDevice})
        else: # It is cas device
            ioStat = ioStats(self.stats_per_interval, \
                            self.duration, \
                            logMgr.getDataDir(),\
                            caseName = self.formCaseNamePrefix(),\
                            kwargs = {'cacheID': cacheID})

            # Also start cas perf collection for CAS drives
            casPerf = casPerfStats(self.stats_per_interval, \
                                    self.duration/self.stats_per_interval, \
                                    logMgr.getDataDir(), \
                                    kwargs = {'cacheID': cacheID} )
            bCASRunning = True

        (ret, ioStatGoing) = ioStat.start()
        if (ret):
            return ret

        if (bCASRunning):
            (ret, casPerfGoing) = casPerf.start()
            if (ret):
                return ret
            casPerfGoing.join()
        ioStatGoing.join()
        dbBenchRunning.join()
        return 0