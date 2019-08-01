#! /usr/bin/python3

from threading import Timer
import argparse
import shlex

from statsHelper import *
from fioHelper import *
from loggerHelper import *
from adminHelper import *


def getBenchCaseID(benchCaseStr):
    return {
        "all"           : BENCH_ALL,
        "cachingOnly"   : BENCH_CACHING_ONLY,
        "coreOnly"      : BENCH_CORE_ONLY,
        "casOnly"       : BENCH_CAS_ONLY,
    } [benchCaseStr]

validCaseList=["all", "cachingOnly", "coreOnly", "casOnly"]

def setupArgsParser():
    global arg_parser
    
    arg_parser.add_argument('--output', metavar='dir', required=True,\
                            help='The dir to contain the perf data, eg. /home/you')
    arg_parser.add_argument('--cascfg', metavar='casCfg', required=False,\
                            default='/etc/intelcas/intelcas.conf',\
                            help='The intelcas.conf file to use for test')
    arg_parser.add_argument('--case', metavar='testCase', required=False,\
                            default='all', choices=validCaseList,\
                            help="By default, all test cases would be covered. "\
                                "Or you can choose one single test caes to run:"\
                                "{0}".format(validCaseList))
    arg_parser.add_argument('--debug', default=False, help="Enable debug mode\n", action="store_true")
    return 0

def verifyArgs(args):
    if False == os.path.isdir(args.output):
        print("**SORRY** Please make sure dir {0} exist".format(args.output))
        exit(1)

if __name__ == "__main__": 
    arg_parser = argparse.ArgumentParser()
    setupArgsParser()
    args = arg_parser.parse_args()

    # Do Arguments Check
    verifyArgs(args)

    # Fetch args
    output    = args.output
    case_str  = args.case
    cascfg    = args.cascfg
    debugMode = args.debug

    # Setup logfile and dataDir
    logMgr.setDataDir(output)
    logFileName = os.path.join(logMgr.getDataDir(), time.strftime("casBaseLineTest-%Y-%m-%d-%Hh-%Mm.log"))
    logMgr.setUpRunningLog(logFileName)
    logMgr.setDebug(debugMode)
    logMgr.info("\n\n")

    # Print notice msg for the user
    notice_msg = """\nStart doing baseline CAS with cfgfile {0}
The performance CSV files will be stored in {1}
Running log will be {2}
Please do NOT do CAS configuration during this test progress"""\
    .format(cascfg, logMgr.getDataDir(), logFileName)

    print(notice_msg)

    logMgr.info("Entry Point to start CAS baseline test")
    logMgr.info("CAS cfgfile is {0}".format(cascfg))
    logMgr.info("Will cover test case: {0}".format(case_str))
    
    caseID = getBenchCaseID(case_str)
    casBench = casBaseLineBench("/etc/intelcas/intelcas.conf", caseID)
    casBench.startBench()
    
    logMgr.info("Exit Point of CAS baseline Test\n\n\n")
    exit(0)