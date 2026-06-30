import os
import shutil

from pyspark.sql import SparkSession
from pyspark.sql.functions import monotonically_increasing_id, col

from CoreSetSample.ModuleTest.distri_samplify import CleansetRamdonSample

# 创建 SparkSession
spark = SparkSession.builder.appName("flight").getOrCreate()
# 读取数据
file_load = '../../../TestDataset/standardData/flights/dirty_dependencies_0.5/dirty_flights.csv'
data = spark.read.csv(file_load, header=True, inferSchema=True)
p = 0.3  # 核心集占总数据集比例
save_path = '../../../TestDataset/CoreSetOutput/flights_core'
# 构建数据集索引
data = data.withColumn("index", monotonically_increasing_id() + 1)
sampleId, special_points = CleansetRamdonSample(data, save_path, sourceSet=["flight"],
                                                        targetSet=["sched_dep_time"])  # 抽样的id
# 选取抽样的数据
new_data = data.filter(col('index').isin(sampleId))
# new_data.write.mode('overwrite').option("header", "true").csv(save_path+"/sampleddata")
new_data.repartition(1).write.mode('overwrite').option("mapreduce.fileoutputcommitter.marksuccessfuljobs",
                                                       "false").option("header", "true").csv(
    path=save_path + "/sampleddata", encoding="utf-8")
custom_filename = "Sampledata.csv"
target_path = "../../../sysFlowVisualizer/cleanCache"
# 重命名和移动文件
for filename in os.listdir(save_path + "/sampleddata"):
    if filename.startswith("part-") and filename.endswith(".csv"):
        full_file_name = os.path.join(save_path + "/sampleddata", filename)
        if os.path.isfile(full_file_name):
            shutil.move(full_file_name, os.path.join(target_path, custom_filename))
            break

spark.stop()
