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
import configparser
from loggerHelper import *
from adminHelper import *
from statsHelper import *
import mysqlHelper

BENCH_CASE_TO_CLASS = {"default":          mysqlHelper.defaultBench,
                        "bufferPoolSize":  mysqlHelper.benchBufferSize }
BENCH_CASE_LIST = ["default", "bufferPoolSize"]

def setupArgsParser():
    global arg_parser
    
    arg_parser.add_argument('-inst', metavar='sqlInstance', required=True, help='The instance ID of mysql to run the test')
    arg_parser.add_argument('-tables', metavar='numTables', required=True, help='Number of tables in the database')
    arg_parser.add_argument('-rows', metavar='numRows', required=True, help='Number of rows for each table')
    arg_parser.add_argument('-output', metavar='outputDir', required=True, \
                            help="Output directory to store the log and perf data")   
    arg_parser.add_argument('-time', metavar='runTime', required=True, \
                            help="Running time for each sysbench command")
    arg_parser.add_argument('-cycle', metavar='cycleTime', required=False, default=0, \
                            help="Cycle time to report perf data")
    arg_parser.add_argument('-bench', metavar='benchTask', required=False, default='default',
                            choices=BENCH_CASE_LIST, help="You can choose one bench task to run:\n"\
                                                        "{0}".format(BENCH_CASE_LIST))

    return 0

def verifyArgs(args):
    try:
        val = int(args.inst)
        val = int(args.tables)
        val = int(args.rows)
        val = int(args.time)
        val = int(args.cycle)
    except:
        print("Please make sure inst/tables/rows be integer\n")
        exit(1)
    
    if (False == os.path.isdir(args.output)):
        print("Please make sure dir {0} exist".format(args.output))
        exit(1)

if __name__ == "__main__": 
    arg_parser = argparse.ArgumentParser()
    setupArgsParser()
    args = arg_parser.parse_args()

    # Check the input
    verifyArgs(args)

    logMgr.setDataDir(args.output)
    logFileName = os.path.join(logMgr.getDataDir(), time.strftime("sysbench-Run-%Y-%m-%d-%Hh-%Mm.log"))
    logMgr.setUpRunningLog(logFileName)
    logMgr.info("\n\n")
    
    dbName = taskCfg.queryOpt("sysbench", "DB_NAME")
    pwd = taskCfg.queryOpt("sysbench", "PWD")
    if "" == dbName:
        dbName = "sbtest"
    if "" == pwd:
        pwd = "intel123"
    db = mysqlHelper.dataBase(int(args.inst), dbName, pwd, int(args.tables), int(args.rows))

    benchTask = BENCH_CASE_TO_CLASS[args.bench](db, int(args.time))
    benchTask.startBench()

    exit(0)