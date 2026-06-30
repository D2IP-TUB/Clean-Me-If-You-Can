import os
import shutil

from pyspark import Row
from pyspark.sql import SparkSession
from pyspark.sql.functions import col

from CoreSetSample.ModuleTest.distri_samplify import CleansetRamdonSample

# 创建 SparkSession
spark = SparkSession.builder.appName("City").getOrCreate()

# 原始数据集
original_data = [
    {'a': 'New Yorks', 'b': 'NY', 'index': 1},  # 脏数据
    {'a': 'New York', 'b': 'NY', 'index': 2},
    {'a': 'San Francisco', 'b': 'SF', 'index': 3},
    {'a': 'San Francisco', 'b': 'SF', 'index': 4},
    {'a': 'San Jose', 'b': 'SJ', 'index': 5},
    {'a': 'New York', 'b': 'NY', 'index': 6},
    {'a': 'San Francisco', 'b': 'SFO', 'index': 7},  # 脏数据
    {'a': 'Berkeley City', 'b': 'Bk', 'index': 8},
    {'a': 'San Mateo', 'b': 'SMO', 'index': 9},
    {'a': 'Albany', 'b': 'AB', 'index': 10},
    {'a': 'San Mateo', 'b': 'SM', 'index': 11},  # 脏数据
    {'a': 'San', 'b': 'SMO', 'index': 12},
    {'a': 'San', 'b': 'SMO', 'index': 13}
]

# 将原始数据集复制到1000行
data = []
for i in range(1, 1001):
    item = original_data[(i - 1) % len(original_data)].copy()
    item['index'] = i
    data.append(item)

# 创建DataFrame
rows = [Row(**record) for record in data]
data = spark.createDataFrame(rows)

# 核心集比例
p = 0.03

# 核心集保存路径
save_path = "../../../TestDataset/CoreSetOutput/City_Abbr_core"


# 调用 CleansetRamdonSample 函数进行核心集抽样
sampleId, special_points = CleansetRamdonSample(data, save_path, sourceSet=['a'], targetSet=['b'])

# 选取抽样的数据
new_data = data.filter(col('index').isin(sampleId))
new_data.show()

# 保存抽样数据
new_data.repartition(1).write.mode('overwrite').option("mapreduce.fileoutputcommitter.marksuccessfuljobs", "false").option("header", "true").csv(
    path=save_path + "/sampleddata", encoding="utf-8")

# 自定义文件名并设置目标路径
custom_filename = "Sampledata.csv"
target_path = "../../../sysFlowVisualizer/cleanCache"

# 重命名和移动文件
for filename in os.listdir(save_path + "/sampleddata"):
    if filename.startswith("part-") and filename.endswith(".csv"):
        full_file_name = os.path.join(save_path + "/sampleddata", filename)
        if os.path.isfile(full_file_name):
            shutil.move(full_file_name, os.path.join(target_path, custom_filename))
            break

# 停止 SparkSession
spark.stop()