import os
import shutil
import time

from pyspark import StorageLevel
from pyspark.sql import SparkSession
from pyspark.sql.functions import monotonically_increasing_id, col

from CoreSetSample.ModuleTest.distri_samplify import CleansetRamdonSample

# 创建 SparkSession
spark = SparkSession.builder.appName("tax").getOrCreate()

# 读取数据
file_load = '../../../TestDataset/standardData/tax_200k/dirty_ramdon_0.5/dirty_tax.csv'
data = spark.read.csv(file_load, header=True, inferSchema=True)

# 设置核心集保存路径
save_path = '../../../TestDataset/CoreSetOutput/tax_200k_clean_core'

# 构建数据集索引
sset = [['zip'], ['zip', 'areacode'], ['lname', 'fname']]
tset = [['city'], ['state'], ['gender']]

# 确认源集合和目标集合的长度一致
if (len(tset) != len(sset)):
    print("sourceSet and targetSet must have the same length")
    spark.stop()

# 为数据添加索引列
data = data.withColumn("index", monotonically_increasing_id() + 1)
data.persist(StorageLevel.MEMORY_AND_DISK)

# 记录开始时间
time1 = time.time()

# 遍历每对源集合和目标集合
for i in range(0, len(tset)):
    block_path = save_path + "/part" + str(i)
    sourceSet = sset[i]
    targetSet = tset[i]

    # 调用 CleansetRamdonSample 函数进行核心集抽样
    sampleId, special_points = CleansetRamdonSample(data, block_path, sourceSet=sourceSet, targetSet=targetSet)

    # 记录结束时间并计算时间差
    time2 = time.time()
    print("core sample time(s): " + str(time2 - time1))

    # 选取抽样的数据
    new_data = data.filter(col('index').isin(sampleId))

    # 保存抽样数据
    new_data.repartition(1).write.mode('overwrite').option("mapreduce.fileoutputcommitter.marksuccessfuljobs",
                                                           "false").option("header", "true").csv(
        path=block_path + "/sampleddata", encoding="utf-8")

    # 自定义文件名并设置目标路径
    custom_filename = "Sampledata" + str(i) + ".csv"
    target_path = "../../../sysFlowVisualizer/cleanCache"

    # 重命名和移动 CSV 文件
    for filename in os.listdir(block_path + "/sampleddata"):
        if filename.startswith("part-") and filename.endswith(".csv"):
            full_file_name = os.path.join(block_path + "/sampleddata", filename)
            if os.path.isfile(full_file_name):
                shutil.copy(full_file_name, os.path.join(target_path, custom_filename))
                break

    # 自定义文件名并设置目标路径
    custom_filename = "resultGraph" + str(i) + ".png"
    target_path = "../../../sysFlowVisualizer/cleanCache"

    # 重命名和移动 PNG 文件
    for filename in os.listdir(block_path):
        if filename.endswith(".png"):
            full_file_name = os.path.join(block_path, filename)
            if os.path.isfile(full_file_name):
                shutil.copy(full_file_name, os.path.join(target_path, custom_filename))
                break

# 停止 SparkSession
spark.stop()