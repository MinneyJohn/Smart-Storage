#! /usr/bin/python3

from threading import Timer
import argparse
import shlex

from statsHelper import *
from fioHelper import *
from loggerHelper import *
from adminHelper import *

'''
Here is the mapping from the case name to the case class;
By default, all the test cases will be covered;
But the user can also specify the single test case to cover;
Now only two options:
a) All test cases
b) Or only one single test case
'''
CASE_STR_TO_CLASS = {"all":          baselineCacheCorePair,
                    "rndReadMiss":   caseRandReadMiss,
                    "rndReadHit":    caseRandReadHit,
                    "rndWriteMiss":  caseRandWriteMiss,
                    "rndWriteHit":   caseRandWriteHit,
                    "ReadMiss":      caseSeqReadMiss,
                    "ReadHit":       caseSeqReadHit,
                    "WriteMiss":     caseSeqWriteMiss,
                    "WriteHit":      caseSeqWriteHit,
                    "WriteOverflow": caseWriteOverflow}

validCaseList=["rndReadMiss", "rndReadHit", "rndWriteMiss", "rndWriteHit",
                "ReadMiss", "ReadHit", "WriteMiss", "WriteHit", "WriteOverflow"]

def setupArgsParser():
    global arg_parser
    
    arg_parser.add_argument('-cache', metavar='cacheDev', required=True, help='The device of cache, eg. /dev/nvme')
    arg_parser.add_argument('-core', metavar='coreDev', required=True, help='The device of core, eg. /dev/sdb')
    arg_parser.add_argument('-output', metavar='dir', required=True, help='The dir to contain the perf data, eg. /home/you')
    arg_parser.add_argument('-case', metavar='testCase', required=False, default='all',
                            choices=validCaseList, help="By default, all test cases would be covered. "\
                                                        "Or you can choose one single test caes to run:"\
                                                        "{0}".format(validCaseList))
    return 0

def verifyArgs(args):
    if (False == casAdmin.blockDeviceExist(args.cache) 
        or False == casAdmin.blockDeviceExist(args.core)):
        print "**SORRY** Please make sure {0} and {1} do exist\n".format(args.cache, args.core)
        exit(1)    
    elif (True == casAdmin.hasPartionOnDev(args.cache) 
        or True == casAdmin.hasPartionOnDev(args.core)):
        print "**SORRY** Please make sure {0} and {1} does NOT have partition or CAS configuration\n".format(args.cache, args.core)
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

    # Do Arguments Check
    verifyArgs(args)

    # Fetch args
    cacheDev = args.cache
    coreDev = args.core
    output  = args.output
    case_str = args.case

    # Setup logfile and dataDir
    logMgr.setDataDir(output)
    logFileName = os.path.join(logMgr.getDataDir(), time.strftime("smart-storage-%Y-%m-%d-%Hh-%Mm.log"))
    logMgr.setUpRunningLog(logFileName)
    logMgr.info("\n\n")

    # Print notice msg for the user
    notice_msg = """\nStart doing baseline CAS test using cache {0} and core {1}
The performance CSV files are in {2}
Running log is {3}
Please do NOT do CAS configuration during this test progress"""\
    .format(cacheDev, coreDev, logMgr.getDataDir(), logFileName)

    print notice_msg

    logMgr.info("Entry Point to start CAS baseline test")
    logMgr.info("Caching Device is {0}, Core Device is {1}".format(cacheDev, coreDev))
    logMgr.info("Will cover test case: {0}".format(case_str))
    
    # Used this event to notify stats collection to be able to quit
    fioFinishEvent = threading.Event()

    # Check existing caches
    casAdmin.refreshCacheVolumeSet()
    # casAdmin.showCacheVolumeSet()

    # Prepare Stats Collecting Threads
    casPerfStatsObj = CasPerfStats(DEFAULT_CYCLE_TIME, 
                                    int(RUNNING_TO_END/DEFAULT_CYCLE_TIME), 
                                    logMgr.getDataDir(), 
                                    fioFinishEvent)
    
    # Fetch the test case
    testCase = CASE_STR_TO_CLASS[case_str](cacheDev, coreDev, fioFinishEvent)
    
    # Generate working threads
    thread_collect_cas    = threading.Thread(target=casPerfStatsObj.startCollectStats)
    thread_run_fio_jobs   = threading.Thread(target=testCase.do)
    
    # Start the threads
    thread_collect_cas.start() 
    thread_run_fio_jobs.start()

    # Wait for the thread
    thread_collect_cas.join() 
    thread_run_fio_jobs.join()

    # Stop cache instance to clear the test
    casAdmin.stopCacheInstance(casAdmin.getIdByCacheDev(cacheDev))

    logMgr.info("Exit Point of CAS baseline Test\n\n\n")
    exit(0)