#! /usr/bin/python

import time
import logging

logging.basicConfig(level=logging.DEBUG,
                    filename= time.strftime("smart-storage-%Y-%m-%d.log"),
                    datefmt='%Y/%m/%d %H:%M:%S',
                    format='%(asctime)s - %(levelname)s - %(lineno)d - %(module)s - %(message)s')
logger = logging.getLogger(__name__)