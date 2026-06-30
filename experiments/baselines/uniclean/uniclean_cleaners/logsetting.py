import logging
import os
import random
import string
import time

# 创建日志文件路径
timestr = time.strftime("%Y%m%d-%H%M%S")
log_dir = "CleanLogs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# 限制保留的日志文件数量
log_files = sorted([f for f in os.listdir(log_dir) if f.endswith(".log")],
                   key=lambda x: os.path.getmtime(os.path.join(log_dir, x)))
if len(log_files) > 10:
    for old_file in log_files[:-10]:
        os.remove(os.path.join(log_dir, old_file))

# 生成新的日志文件
logfilename = os.path.join(log_dir,
                           f"{timestr}_{''.join(random.choices(string.ascii_uppercase + string.digits, k=10))}.log")
print(f"日志文件: {logfilename}")

# 配置日志
logging.basicConfig(level=logging.INFO, filename=logfilename, filemode='w',
                    format='%(asctime)s - %(levelname)s - %(message)s')
logging.info(f"日志已保存至 {logfilename}")
