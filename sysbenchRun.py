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

BENCH_CASE_TO_CLASS = {"default":          mysqlHelper.defaultBench,
                        "disk":            mysqlHelper.benchOneBlockDevice,
                        "intelcas":        mysqlHelper.benchCAS,
                        "disklist":        mysqlHelper.benchMultipleBlkDevice}
BENCH_CASE_LIST = ["default", "disk", "intelcas", "disklist"]

def getBenchKwargs(benchCase, args):
    return {
        "default"       : {},
        "disk"          : {'blkDev': args.blkDev},
        "intelcas"      : {'caching': args.caching, 'core': args.core},
        "disklist"      : {'blkList': args.blkList},
    } [benchCase]
    

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
    arg_parser.add_argument('-blkDev', metavar='blockDevice', required=False, default='',
                            help="Specify block device you want to bench\n")
    arg_parser.add_argument('-caching', metavar='cachingDev', required=False, default='',
                            help="The caching device for intelcas\n")
    arg_parser.add_argument('-core', metavar='coreDev', required=False, default='',
                            help="The core device for intelcas\n")
    arg_parser.add_argument('-blkList', metavar='blklist', required=False, default='',
                            help="The list of block drives to bench\n")
    arg_parser.add_argument('-debug', help="Enable debug mode\n", action="store_true")
        

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
    
    if "disk" == args.bench:
        if "" == args.blkDev:
            print("Please specify the blockdevice if you want to bench\n")
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
    logMgr.setDebug(args.debug)
    logMgr.info("\n\n")

    print("Benchmark is running in progress..............")
    print("You can get your log and perf data in: {0}".format(logMgr.getDataDir()))
    taskCfg.showOpt()

    dbName = taskCfg.queryOpt("sysbench", "DB_NAME")
    pwd = taskCfg.queryOpt("sysbench", "PWD")
    if "" == dbName:
        dbName = "sbtest"
    if "" == pwd:
        pwd = "intel123"
    db = mysqlHelper.dataBase(int(args.inst), dbName, pwd, int(args.tables), int(args.rows))

    benchTask = BENCH_CASE_TO_CLASS[args.bench](db, int(args.time))
    benchTask.startBench(kwargs = getBenchKwargs(args.bench, args))

    logMgr.info("Successfully to complete the benchmark\n")
    logMgr.info("You can get your performance data from: {0}\n".format(logMgr.getDataDir()))
    exit(0)