#! /usr/bin/python

from threading import Timer
import argparse
import shlex

from statsHelper import *
from loggerHelper import *
from adminHelper import *

'''
Used to calculate the cycle values for some columns
Maybe need to define as one class
'''

def setupArgsParser():
    global arg_parser
    
    arg_parser.add_argument('-C', type=int, metavar='Cycle_Time', required=True, help='Duration of Monitor Cycle by Seconds')
    arg_parser.add_argument('-T', type=int, metavar='Running_Time', required=True, help='Total Monitor Time by Seconds')
    arg_parser.add_argument('-O', type=str, metavar='Output_Dir', required=True, help='Output Dir')
    
    return 0

def verifyArgs(args):
    if False == os.path.isdir(args.O):
        print("Please create dir \"{0}\" and then rerun\n".format(args.O))
        exit(1)

if __name__ == "__main__": 
    arg_parser = argparse.ArgumentParser()
    setupArgsParser()
    args = arg_parser.parse_args()
    verifyArgs(args)

    CYCLE_TIME = args.C
    RUNNINGT_TIME = args.T
    WORKING_DIR = args.O

    # Setup logfile and dataDir
    logMgr.setDataDir(WORKING_DIR)
    logFileName = os.path.join(logMgr.getDataDir(), time.strftime("collect-stats-%Y-%m-%d-%Hh-%Mm.log"))
    logMgr.setUpRunningLog(logFileName)
    logMgr.info("\n\n")

    print("Starting Collect Stats, every cycle is {0} seconds, will run for {1} seconds".\
                format(CYCLE_TIME, RUNNINGT_TIME))
    print("Running log file is {0}".format(logFileName))
    print("Data would be saved at {0}".format(logMgr.getDataDir()))

    logMgr.info("Starting Collect Stats, every cycle {0} seconds, run {1} seconds, save to {2}".
                format(CYCLE_TIME, RUNNINGT_TIME, WORKING_DIR))

    
    #casAdmin.refreshCacheVolumeSet()
    #casAdmin.showCacheVolumeSet()

    #casPerf = casPerfStats(CYCLE_TIME, RUNNINGT_TIME, logMgr.getDataDir())
    ioStats = ioStats(CYCLE_TIME, RUNNINGT_TIME, logMgr.getDataDir(), kwargs = {'devList': "nvme1n1"})
    #(ret, casPerfGoing) = casPerf.start()
    #if ret:
    #    exit(0)
    (ret, ioStatsGoing) = ioStats.start()
    if ret:
        exit(0)

    bufferPoolStats = mysqlBufferPoolStats(CYCLE_TIME, RUNNINGT_TIME, logMgr.getDataDir(), \
                                            kwargs = {'instID': 3, 'pwd': 'intel123'})
    (ret, bufferPoolGoing) = bufferPoolStats.start()
    if (ret):
        exit(0)

    # Wait for the thread
    #casPerfGoing.join()
    ioStatsGoing.join()
    bufferPoolGoing.join()

    logMgr.info("End of Collect Stats")
    exit(0)