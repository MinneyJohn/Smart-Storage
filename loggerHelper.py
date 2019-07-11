#! /usr/bin/python

import time
import os
import datetime
import logging

DEBUG_MODE = True

class logMgr():
    logName = ""
    logFile = ""
    dataDir = ""

    @classmethod
    def setUpRunningLog(cls, logFile):
        cls.logName = logFile
        cls.logFile = logFile
        log_setup   = logging.getLogger(cls.logName)
        formatter   = logging.Formatter('%(asctime)s - %(lineno)d - %(module)s %(message)s', datefmt='%m/%d/%Y %H:%M:%S')
        fileHandler = logging.FileHandler(cls.logFile, mode='a')
        fileHandler.setFormatter(formatter)
        log_setup.setLevel(logging.DEBUG)
        log_setup.addHandler(fileHandler)
        
    @classmethod
    def defaultSetUp(cls):
        cls.setUpRunningLog("/tmp/casBaseLine.tmp")
    
    @classmethod
    def info(cls, msg):
        # If logging not set yet, do default setup
        if ("" == cls.logName):
            cls.defaultSetUp()
        logging.getLogger(cls.logName).info(msg)
    
    @classmethod
    def debug(cls, msg):
        global DEBUG_MODE
        if (True == DEBUG_MODE):
            cls.info(msg)
        else:
            pass
    
    @classmethod
    def setDataDir(cls, dataDir):
        time_str = datetime.datetime.now().strftime("%Y_%m_%d_%Hh_%Mm")
        run_dataDir = os.path.join(dataDir, time_str)
        os.mkdir(run_dataDir)
        cls.dataDir = run_dataDir
    
    @classmethod
    def getDataDir(cls):
        if ("" == cls.dataDir):
            cls.setDataDir("/tmp")
        return cls.dataDir