#! /usr/bin/python

import time
import logging

class logMgr():
    logName = ""
    logFile = ""
    dataDir = ""

    @classmethod
    def setUp(cls, logFile):
        cls.logName = logFile
        cls.logFile = logFile
        log_setup   = logging.getLogger(cls.logName)
        formatter   = logging.Formatter('%(asctime)s - %(lineno)d - %(module)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S')
        fileHandler = logging.FileHandler(cls.logFile, mode='a')
        fileHandler.setFormatter(formatter)
        log_setup.setLevel(logging.DEBUG)
        log_setup.addHandler(fileHandler)
        
    @classmethod
    def defaultSetUp(cls):
        cls.setUp("/tmp/casBaseLine.tmp")
    
    @classmethod
    def info(cls, msg):
        # If logging not set yet, do default setup
        if ("" == cls.logName):
            cls.defaultSetUp()
        logging.getLogger(cls.logName).info(msg)
    
    @classmethod
    def setDataDir(cls, dataDir):
        cls.dataDir = dataDir
    
    @classmethod
    def getDataDir(cls):
        if ("" == cls.dataDir):
            cls.setDataDir("/tmp")
        return cls.dataDir