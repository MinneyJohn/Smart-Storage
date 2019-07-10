#! /usr/bin/python

import threading
import time
import re
import string
import datetime
import os
from threading import Timer
import argparse
import configparser
import shutil
import fnmatch
from adminHelper import *
from statsHelper import *

'''
This class is an abstrat of one database
'''    
class dataBase():
    def __init__(self, instID, name, pwd, tables, rows):
        self.instID = instID
        self.name = name
        self.pwd  = pwd
        self.tables = tables
        self.rows = rows
        self.dataDir = mySqlCfg.queryOpt(instID, "datadir")
        self.sock = mySqlCfg.queryOpt(instID, "socket")
        self.port = mySqlCfg.queryOpt(instID, "port")

    def createDB(self):
        logMgr.info("Try to create database {0}".format(self.name))
        createDBSTSM = "CREATE DATABASE {0}".format(self.name)
        mySqlInst.executeSqlStsm(self.instID, createDBSTSM)
        
        logMgr.info("Try to grant access")
        grantAccess = "GRANT ALL ON {0}.* to 'root'@'localhost'".format(self.name)
        mySqlInst.executeSqlStsm(self.instID, grantAccess)
        
        logMgr.info("Try to set password")
        setPwd = "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '{0}'".format(self.pwd)
        mySqlInst.executeSqlStsm(self.instID, setPwd)

    def prepareData(self):
        prepareTask = sysbenchTask(self, "/usr/share/sysbench/oltp_read_write.lua", 0, action = "prepare")
        prepareTask.trigger()
        logMgr.info("Done - Prepare data for database {0}".format(self.name)) 
        return 0

    def getSizeInGB(self):
        size_in_GB = 0
        sizeStsm = "SELECT table_schema dbName, ROUND(SUM(data_length + index_length) / 1024 / 1024 /1024, 2) Size"\
                   " FROM information_schema.tables  WHERE table_schema = \\\"{0}\\\" \G".format(self.name)
        (ret, output) = mySqlInst.executeSqlStsm(self.instID, sizeStsm, self.pwd)
        lines = output.splitlines()
        for line in lines:
            line = line.strip(" ").rstrip(" \n").replace(" ", "")
            if line.startswith("Size:"):
                words = line.split(":")
                if (2 == len(words)):
                    size_in_GB = int(float(words[1]))
            else:
                continue

        return size_in_GB

    # TODO
    def getBlockDevice(self):
        command = "lsblk | grep {0} | awk '{{print $1}}'".format(self.dataDir)
        (ret, blkDevice) = casAdmin.getOutPutOfCmd(command)
        return blkDevice

'''
This class is an abstract of one sysbench task:
* Support prepare/run/clear
* Target against one database
* Allow the user to customize the task by setOpt
'''
class sysbenchTask():
    def __init__(self, db, sbTask, time, action="run"):
        self.opt = {}

        self.db     = db
        self.sbTask = sbTask
        self.action = action        
        # As "time" is one parameter of sysbench cmd, so always pull it from opt
        if ("run" == self.action):
            self.opt["time"] = time
        self.opt["report-interval"] = 5

        # Inherit from db
        self.opt["mysql-db"] = db.name
        self.opt["tables"] = db.tables
        self.opt["table_size"] = db.rows
        self.opt["mysql-password"] = db.pwd
        self.opt["mysql-port"] = db.port
        self.opt["mysql-socket"] = db.sock
        
        
        # Default Values
        self.opt["threads"] = 100
        self.opt["db-driver"] = "mysql"
        self.opt["mysql-host"] = "localhost"
        self.opt["mysql-user"] = "root"
        
        # Perf files
        self.resultFile = ""
        self.csvFile = ""
    
    # Let the customer to define their own task
    def setOpt(self, optName, optValue):
        self.opt[optName] = optValue

    def getDumpPath(self):
        if (self.resultFile):
            return self.resultFile

        workShort = os.path.basename(self.sbTask).replace(".lua", "")
        threads = self.opt["threads"]
        timeStamp = MyTimeStamp.getAppendTime()
        fileName = "sysbench.{0}.{1}.{2}thds.{3}".format(self.db.name, workShort, threads, timeStamp)
        self.resultFile = os.path.join(logMgr.getDataDir(), fileName)
        return self.resultFile
    
    def writeHeader(self):
        fh = open(self.getCsvFile(), "w+")
        fh.write("cycle, threads, tps, qps, latency_95%\n")
        fh.close()

    def getCsvFile(self):
        if (self.csvFile):
            return self.csvFile

        dbName = self.db.name
        workShort = os.path.basename(self.sbTask).replace(".lua", "")
        threads = self.opt["threads"]
        timeStamp = MyTimeStamp.getAppendTime()
        fileName = "sysbench.{0}.{1}.{2}thds.{3}.csv".format(self.db.name, workShort, threads, timeStamp)
        self.csvFile = os.path.join(logMgr.getDataDir(), fileName)
        self.writeHeader()
        return self.csvFile
    
    def startSysbenchCmd(self):
        opt_str = ""
        for optName in self.opt:
            opt_str = "{0} --{1}={2}".format(opt_str, optName, self.opt[optName])
        sysbenchCmd = "sysbench {0} {1} {2} > {3}".format(self.sbTask, \
                                                            opt_str, \
                                                            self.action, \
                                                            self.getDumpPath())
        logMgr.info("Starting: {0}".format(sysbenchCmd))
        (ret, output) = casAdmin.getOutPutOfCmd(sysbenchCmd)
        if (0 == ret):
            self.exportResultToCSV()
        return ret
    
    def exportResultToCSV(self):
        fileToWrite = open(self.getCsvFile(), "a+")

        pattern = r"(.*\[)(?P<time>\d+)(s\]thds:)(?P<thread>\d+)(tps:)(?P<tps>\d+\.\d+)"\
                    "(qps:)(?P<qps>\d+\.\d+)(.*lat.*ms,.*:)(?P<lat_95_percent>\d+\.\d+)(err.*)"
        dumpFile = open(self.getDumpPath(), "r")
        lines = dumpFile.read().splitlines()
        dumpFile.close()

        for line in lines:
            line = line.strip(" ").rstrip(" \n").replace(" ", "")
            m = re.match(pattern, line)
            if (m):
                oneCycleLine = "{0},{1},{2},{3},{4}\n"\
                                .format(int(int(m.group('time'))/int(self.opt["report-interval"])),
                                        int(m.group('thread')),
                                        float(m.group('tps')),
                                        float(m.group('qps')),
                                        float(m.group('lat_95_percent')))
                fileToWrite.write(oneCycleLine)
        fileToWrite.close()
        return 0

    def trigger(self):
        bCASRunning = False

        # Step 0: Try to purge bin logs to save space
        mySqlInst.purgeBinLog(self.db.instID, self.db.pwd)

        # Step 1: Start sysbench as a long running task in backgroud
        sbBackGround = longTask(self.startSysbenchCmd())
        (ret, sbRunning) = sbBackGround.start()
        if ret:
            return ret
        
        # Only collect perf data for "run" task
        if ("run" == self.action and self.opt["time"]):
            # Step 2: Start buffer pool collection
            poolBufferStats = mysqlBufferPoolStats(self.opt["report-interval"], \
                                                    self.opt["time"], \
                                                    logMgr.getDataDir(), \
                                                    kwargs = {'instID': self.db.instID, 'pwd': self.db.pwd})
            (ret, bufferPoolGoing) = poolBufferStats.start()
            if (ret):
                return ret
                
            # Step 3: Start iostats collection
            # If it is a CAS drive, also collect caching/core device
            blkDevice = self.db.getBlockDevice()
            (cacheID, coreID) = casAdmin.getCacheCoreIdByDevName(blkDevice)
            if (INVALID_CACHE_ID == cacheID):
                ioStat = ioStats(self.opt["report-interval"], \
                                self.opt["time"], \
                                logMgr.getDataDir(), \
                                kwargs = {'devList': blkDevice})
            else:
                ioStat = ioStats(self.opt["report-interval"], \
                                self.opt["time"], \
                                logMgr.getDataDir(), \
                                kwargs = {'cacheID': cacheID})

                # Also start cas perf collection for CAS drives
                casPerf = casPerfStats(self.opt["report-interval"], \
                                        int(self.opt["time"]/self.opt["report-interval"]), \
                                        logMgr.getDataDir(), \
                                        kwargs = {'cacheID': cacheID} )
                bCASRunning = True

            (ret, ioStatGoing) = ioStat.start()
            if (ret):
                return ret
            
            # Step 4: Start CPU collection
            cpuStats = cpuUsageStats(self.opt["report-interval"], \
                                    self.opt["time"], \
                                    logMgr.getDataDir())
            (ret, cpuStatsGoing) = cpuStats.start()
            if (ret):
                return ret

            # Wait for stats collection to join back
            if (bCASRunning):
                (ret, casPerfGoing) = casPerf.start()
                if (ret):
                    return ret
                casPerfGoing.join()
            cpuStatsGoing.join()
            bufferPoolGoing.join()
            ioStatGoing.join()
        # End for "run" task

        sbRunning.join()
        logMgr.info("End of sysbench Task: {0}\n".format(self.sbTask))
        return 0    
    
class benchBufferSize:
    def __init__(self, db, time = 600):
        self.time = time
        self.db   = db

        self.sbTaskList = ["/usr/share/sysbench/oltp_read_write.lua",\
                            "/usr/share/sysbench/oltp_read_only.lua",\
                            "/usr/share/sysbench/oltp_write_only.lua"]
        self.threadsNumList = [100] # TODO
        self.statsCycle = 5 # TODO
    
    def triggerOneSbTask(self, sbTask):
        sbRunTask = sysbenchTask(self.db, sbTask, self.time, action="run")
        for threadNum in self.threadsNumList:
            sbRunTask.setOpt("threads", threadNum)
            sbRunTask.trigger()
            return 0
    
    def triggerAllTask(self):
        for sbTask in self.sbTaskList:
            self.triggerOneSbTask(sbTask)
        return 0

    def getBufferSizeList(self, totalMem, dbSize):
        sizeSet = set()
        start = 0
        end   = int (dbSize * 0.2)
        step  = int (dbSize * 0.2)

        if totalMem > dbSize:
            start = dbSize
        else:
            start = totalMem
        if 0 == end:
            end = 1
        if 0 == step:
            step = 1
        
        curSize = start
        while (curSize >= end):
            sizeSet.add(curSize)
            curSize -= step
        
        logMgr.debug("Will loop those buffer pool size: {0}".format(sizeSet))
        return sorted(sizeSet)

    # TODO
    def getTotalMemory(self):
        checkCmd = "vmstat -s|grep \"total memory\"|awk '{print $1}'"
        (ret, memory_in_kb) = casAdmin.getOutPutOfCmd(checkCmd)
        memory_in_GB = int(int(memory_in_kb) / 1024 / 1024)
        logMgr.debug("There are {0}G physical memory in total".format(memory_in_GB))
        return memory_in_GB

    def startBench(self):
        # Startup the cache instance
        mySqlInst.genesis(self.db.instID)
    
        # Create dataBase
        self.db.createDB()

        # Prepare Data
        self.db.prepareData()

        # Get the valid of buffer pool size list
        totalMem = self.getTotalMemory()
        dbSize = self.db.getSizeInGB()
        logMgr.info("Size of DB is {0}GB, and total physical memory is {1}GB".format(dbSize, totalMem))
        bufferSizeList = self.getBufferSizeList(totalMem, dbSize)

        # Loop sysbench for each buffer size
        for bufferSize in bufferSizeList:
            logMgr.info("Change buffer_pool_size to {0}G".format(bufferSize))
            mySqlCfg.changeOpt(self.db.instID, "innodb_buffer_pool_size", "{0}G".format(bufferSize))
            mySqlInst.restart(self.db.instID)
            self.triggerAllTask()
        
        return 0

class defaultBench():
    def __init__(self, db, time):
        self.db   = db
        self.time = time

        self.sbTaskList = ["/usr/share/sysbench/oltp_read_write.lua",\
                            "/usr/share/sysbench/oltp_read_only.lua",\
                            "/usr/share/sysbench/oltp_write_only.lua"]
        self.threadNum  = 100 # TODO
        
    def startBench(self):
        # Startup the cache instance
        mySqlInst.genesis(self.db.instID)
    
        # Create dataBase
        self.db.createDB()

        # Prepare Data
        self.db.prepareData()

        for sbTask in self.sbTaskList:
            sbRunTask = sysbenchTask(self.db, sbTask, self.time, action="run")
            sbRunTask.setOpt("threads", self.threadNum)
            sbRunTask.trigger()

        return 0