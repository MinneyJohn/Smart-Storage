#! /usr/bin/python

from threading import Timer
import argparse
import shlex

from statsHelper import *
from fioHelper import *
from loggerHelper import *

def setupArgsParser():
    global arg_parser
    
    arg_parser.add_argument('-cache', metavar='cacheDev', required=True, help='The device of cache, eg. /dev/nvme')
    arg_parser.add_argument('-core', metavar='coreDev', required=True, help='The device of core, eg. /dev/sdb')
    arg_parser.add_argument('-output', metavar='dir', required=True, help='The dir to contain the perf data, eg. /home/you')

    return 0

def verifyArgs(args):
    if (False == casAdmin.blockDeviceExist(args.cache) 
        or False == casAdmin.blockDeviceExist(args.core)):
        print "**SORRY** Please make sure {0} and {1} do exist\n".format(args.cache, args.core)
        exit(1)    
    elif (True == casAdmin.hasPartionOnDev(args.cache) 
        or True == casAdmin.hasPartionOnDev(args.core)):
        print "**SORRY** Please make sure {0} and {1} does NOT have partition\n".format(args.cache, args.core)
        exit(1)
    elif False == casAdmin.isCacheCoreClear(args.cache, args.core):
        print "**SORRY** Please make sure {0} and {1} NOT being used\n".format(args.cache, args.core)
        exit(1)
    elif False == os.path.isdir(args.output):
        print "**SORRY** Please make sure dir {0} exist".format(args.output)
        exit(1)

if __name__ == "__main__": 
    arg_parser = argparse.ArgumentParser()
    setupArgsParser()
    args = arg_parser.parse_args()
    verifyArgs(args)

    cacheDev = args.cache
    coreDev = args.core
    output  = args.output

    logger.info("\n\n")
    logger.info("Entry Point to start CAS baseline test")
    logger.info("Caching Device is {0}, Core Device is {1}".format(cacheDev, coreDev))
    
    # Used this event to notify stats collection to quit
    fioFinishEvent = threading.Event()

    # Check existing caches
    casAdmin.refreshCacheVolumeSet()
    casAdmin.showCacheVolumeSet()

    # Prepare Stats Collecting Threads
    #casPerfStatsObj = CasPerfStats(DEFAULT_CYCLE_TIME, int(RUNNING_TO_END/DEFAULT_CYCLE_TIME), fioFinishEvent)
    #ioStatsObj = IoStats(DEFAULT_CYCLE_TIME, int(RUNNING_TO_END/DEFAULT_CYCLE_TIME), fioFinishEvent)
    casPerfStatsObj = CasPerfStats(DEFAULT_CYCLE_TIME, int(RUNNING_TO_END/DEFAULT_CYCLE_TIME), output, fioFinishEvent)
    ioStatsObj = IoStats(DEFAULT_CYCLE_TIME, int(RUNNING_TO_END/DEFAULT_CYCLE_TIME), output, fioFinishEvent)

    # Prepare FIO test case
    testCase = baselineCacheCorePair(cacheDev, coreDev, fioFinishEvent)
    
    # Generate working threads
    thread_collect_cas    = threading.Thread(target=casPerfStatsObj.startCollectStats)
    thread_collect_iostat = threading.Thread(target=ioStatsObj.startCollectStats,
                                             kwargs={"cacheDev": cacheDev, 
                                                     "coreDev": coreDev}) 
    thread_run_fio_jobs   = threading.Thread(target=testCase.do)
    
    # Start the threads
    thread_collect_cas.start() 
    thread_collect_iostat.start()
    thread_run_fio_jobs.start()

    # Wait for the thread
    thread_collect_cas.join() 
    thread_collect_iostat.join()
    thread_run_fio_jobs.join()

    logger.info("Exit Point of CAS baseline Test\n\n\n")
    exit(0)