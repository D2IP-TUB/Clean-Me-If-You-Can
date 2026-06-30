import glob
import inspect
import os
import sys

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))

parentdir = os.path.dirname(currentdir)

sys.path.insert(0, parentdir)

import logging
import string
import random
import time

timestr = time.strftime("%Y%m%d-%H%M%S")
# 设置日志文件的模式
log_file_pattern = 'logs/*.log'
log_files = sorted(glob.glob(log_file_pattern), key=os.path.getmtime)
# 检查是否超过20个日志文件
if len(log_files) > 10:
    # 保留最新的10个文件，删除其他的
    for file_to_delete in log_files[:-5]:
        os.remove(file_to_delete)
        print(f"Deleted old log file: {file_to_delete}")

logfilename = "logs/" + timestr + '_' + ''.join(
    random.choice(string.ascii_uppercase + string.digits) for _ in range(10)) + '.log'
print(logfilename)
logging.basicConfig(level=logging.DEBUG, filename=logfilename)
logging.warn("Logs saved in " + logfilename)
