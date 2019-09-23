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

import mysqlHelper
import fioHelper
import rocksdbHelper

def setupArgsParser():
    global arg_parser
    
    arg_parser.add_argument('--output', metavar='outputDir', required=True, \
                            help="Output directory to store the log and perf data")   
    arg_parser.add_argument('--debug', help="Enable debug mode\n", action="store_true")
    arg_parser.add_argument('--reinstall', help="Reinstall the rocksdb, gflags and zsds\n", action="store_true")
    return 0

def verifyArgs():
    return 0

'''
This script is supposed to be the entry to trigger db_bench test
'''
if __name__ == "__main__": 
    arg_parser = argparse.ArgumentParser()
    setupArgsParser()
    args = arg_parser.parse_args()

    logMgr.setDataDir(args.output)
    logFileName = os.path.join(logMgr.getDataDir(), time.strftime("dbBench-Run-%Y-%m-%d-%Hh-%Mm.log"))
    logMgr.setUpRunningLog(logFileName)
    logMgr.setDebug(args.debug)
    logMgr.info("\n\n")

    print("dbBench is running in progress..............")
    print("You can get your log and perf data in: {0}".format(logMgr.getDataDir()))
    taskCfg.showOpt("db_bench")

    testRocksDB = rocksdbHelper.rocksDB()
    if True == args.reinstall:
        testRocksDB.doInstall()
    testRocksDB.prepareDB()
    testRocksDB.rundbBench()
    
    exit(0)