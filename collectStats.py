#! /usr/bin/python

from threading import Timer
import argparse
import shlex

from statsHelper import *

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
        print "Please create dir \"{0}\" and then rerun\n".format(args.O)
        exit(1)

if __name__ == "__main__": 
    arg_parser = argparse.ArgumentParser()
    setupArgsParser()
    args = arg_parser.parse_args()
    verifyArgs(args)

    CYCLE_TIME = args.C
    RUNNINGT_TIME = args.T
    WORKING_DIR = args.O

    print "\nAm going to collect CAS Perf Stats every {0} seconds;".format(CYCLE_TIME)
    print "Will keep running {0} seconds;".format(RUNNINGT_TIME) 
    print "Generated data would be in {0}.\n".format(WORKING_DIR)
   
    SetOfCacheVolume.fetchCacheVolumeSet()
    SetOfCacheVolume.showCacheVolumeSet()

    casPerfStatsObj = CasPerfStats(CYCLE_TIME, int(RUNNINGT_TIME/CYCLE_TIME), WORKING_DIR)
    ioStatsObj = IoStats(CYCLE_TIME, int(RUNNINGT_TIME/CYCLE_TIME), WORKING_DIR)

    # Create the thread
    t1 = threading.Thread(target=casPerfStatsObj.startCollectStats()) 
    t2 = threading.Thread(target=ioStatsObj.startCollectStats()) 
  
    # Start the thread 
    t1.start() 
    t2.start()
    
    # Wait for the thread
    t1.join()
    t2.join()

    # print "Finished"

    exit(0)