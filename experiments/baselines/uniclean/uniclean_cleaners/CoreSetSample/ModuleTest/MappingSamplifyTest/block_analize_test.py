# 定义测试数据
import pandas as pd
from pyspark import StorageLevel
from pyspark.sql import SparkSession
from pyspark.sql.functions import monotonically_increasing_id

from CoreSetSample.ModuleTest.get_patition_block import find_blocks
from CoreSetSample.ModuleTest.get_patition_block import find_blocks_spark

data = {
    'A': [1, 1, 2, 2, 9],
    'B': [2, 3, 2, 4, 100],
    'C': [5, 6, 7, 5, 5555]
}

df = pd.DataFrame(data)
# 调用find_blocks函数
blocks = find_blocks(df, ['A', 'B', 'C'])
print(blocks)

#下面测试用 spark 分块



# 创建 SparkSession
spark = SparkSession.builder.appName("tax").getOrCreate()
# 读取数据
# file_load = '../../TestDataset/dataABC.csv'
file_load = '../../../TestDataset/standardData/tax_200k/dirty_ramdon_0.5/dirty_tax.csv'
df = spark.read.csv(file_load, header=True, inferSchema=True)
df = df.withColumn("index", monotonically_increasing_id() + 1)
df.persist(StorageLevel.MEMORY_AND_DISK)
# 调用find_blocks_spark函数
# df 是已经加载到Spark的DataFrame
# partition 是一个包含列名的列表，例如 ["col1", "col2"]
# blocks_df = find_blocks_spark(df, ['A', 'B'])
blocks_df = find_blocks_spark(df, ['zip', 'areacode'])
i=1
for block in blocks_df:
    print("Block number: ",i)
    block.show()
    i+=1

splits = df.randomSplit([1.0] * 100)
i=1
for split in splits:
    print("Split number: ", i)
    i+=1
    split.show()