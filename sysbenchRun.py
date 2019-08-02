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

BENCH_CASE_LIST = ["default", "benchDisk", "benchCAS", "benchMoreDiskS"]

def getBenchClass(benchCase):
    return {"default":        mysqlHelper.defaultBench,
            "benchDisk":      mysqlHelper.benchOneBlockDevice,
            "benchCAS":       mysqlHelper.benchCAS,
            "benchMoreDiskS": mysqlHelper.benchMultipleBlkDevice,
        } [benchCase]

def getBenchKwargs(benchCase, args):
    return {
        "default"        : {},
        "benchDisk"      : {'disk': args.disk},
        "benchCAS"       : {'caching': args.caching, 'core': args.core},
        "benchMoreDiskS" : {'diskset': args.diskset},
    } [benchCase]
    

def setupArgsParser():
    global arg_parser
    
    arg_parser.add_argument('--inst', metavar='sqlInstance', required=True, help='The instance ID of mysql to run the test')
    arg_parser.add_argument('--output', metavar='outputDir', required=True, \
                            help="Output directory to store the log and perf data")   
    arg_parser.add_argument('--time', metavar='runTime', required=True, \
                            help="Running time for each sysbench command")
    arg_parser.add_argument('--type', metavar='benchTask', required=False, default='default',
                            choices=BENCH_CASE_LIST, help="You can choose one bench task to run:\n"\
                                                        "{0}".format(BENCH_CASE_LIST))
    arg_parser.add_argument('--disk', metavar='blockDevice', required=False, default='',
                            help="Specify block device you want to bench\n")
    arg_parser.add_argument('--caching', metavar='cachingDev', required=False, default='',
                            help="The caching device for intelcas\n")
    arg_parser.add_argument('--core', metavar='coreDev', required=False, default='',
                            help="The core device for intelcas\n")
    arg_parser.add_argument('--diskset', metavar='blklist', required=False, default='',
                            help="The list of block drives to bench\n")
    arg_parser.add_argument('--debug', help="Enable debug mode\n", action="store_true")
    arg_parser.add_argument('--skipPrep', help="Skip the prepare data phase\n", action="store_true")        

    return 0

def verifyArgs(args):
    try:
        val = int(args.inst)
        val = int(args.time)
    except:
        print("Please make sure inst/time be integer\n")
        exit(1)
    
    if "benchDisk" == args.type:
        if "" == args.disk:
            print("Must specify the blockdevice if you want to bench\n")
            exit(1)
    
    if "benchCAS" == args.type:
        if "" == args.caching or "" == args.core:
            print("Must specify the caching & core device for CAS bench work\n")
            exit(1)
    
    if "bencbenchMoreDiskShCAS" == args.type:
        if "" == args.diskset:
            print("Must specify list of disks you want to bench\n")
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
    taskCfg.showOpt("sysbench")

    dbName = taskCfg.queryOpt("sysbench", "DB_NAME")
    pwd = taskCfg.queryOpt("sysbench", "PWD")
    tables = taskCfg.queryOpt("sysbench", "TABLE_NUM")
    rows   = taskCfg.queryOpt("sysbench", "ROWS")
   
    if "" == tables or "" == rows:
        print("Please specify the tables and rows in your task.cnf")
        exit(1)
    else:
        try:
            tables = int(taskCfg.queryOpt("sysbench", "TABLE_NUM"))
            rows  = int(taskCfg.queryOpt("sysbench", "ROWS"))
        except:
            print("Please make sure tables/rows be integer")
            exit(1)
    
    if "" == dbName:
        dbName = "sbtest"
    if "" == pwd:
        pwd = "intel123"

    db = mysqlHelper.dataBase(int(args.inst), dbName, pwd, int(tables), int(rows))

    benchTask = getBenchClass(args.type)(db, int(args.time), skipPrepare = args.skipPrep)
    benchTask.startBench(kwargs = getBenchKwargs(args.type, args))

    logMgr.info("Successfully to complete the benchmark\n")
    logMgr.info("You can get your performance data from: {0}\n".format(logMgr.getDataDir()))
    exit(0)