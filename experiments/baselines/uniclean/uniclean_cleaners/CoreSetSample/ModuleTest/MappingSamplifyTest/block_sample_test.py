# 创建 SparkSession
from pyspark.sql import SparkSession

from CoreSetSample.mapping_samplify import block_sample

spark = SparkSession.builder \
    .appName("Block Sample Aggregation") \
    .getOrCreate()
# # 示例数据
data = [
    {"source_a": 1, "source_b": 1, "target": 1},
    {"source_a": 1, "source_b": 1, "target": 1},
    {"source_a": 1, "source_b": 1, "target": 1},
    {"source_a": 1, "source_b": 1, "target": 1},
    {"source_a": 1, "source_b": 1, "target": 1},
    {"source_a": 2, "source_b": 2, "target": 1},
    {"source_a": 2, "source_b": 2, "target": 1},
    {"source_a": 2, "source_b": 2, "target": 3},
    {"source_a": 2, "source_b": 2, "target": 3},
    {"source_a": 2, "source_b": 2, "target": 4},
    {"source_a": 2, "source_b": 2, "target": 4},
    {"source_a": 2, "source_b": 2, "target": 4},
]

# 创建 DataFrame
df = spark.createDataFrame(data)

# 使用 block_sample 函数进行采样
sourceSet = ["source_a", "source_b"]
targetSet = ["target"]
# sample_data=block_sample_cycle(df, sourceSet)
sample_data=block_sample(df, sourceSet,targetSet)
sample_data.show()


#
#
# # 创建 SparkSession
# spark = SparkSession.builder.appName("tax").getOrCreate()
# # 读取数据
# # file_load = '../../TestDataset/dataABC.csv'
# file_load = '../../TestDataset/standardData/tax_200k/dirty_ramdon_0.5/dirty_tax.csv'
# df = spark.read.csv(file_load, header=True, inferSchema=True)
# df = df.withColumn("index", monotonically_increasing_id() + 1)
# df.persist(StorageLevel.MEMORY_AND_DISK)
# # 调用find_blocks_spark函数
# # df 是已经加载到Spark的DataFrame
# sourceSet = ['zip', 'areacode']
# targetSet = ['state']
# sampled_data = block_sample(df, sourceSet,targetSet)
# sampled_data.show()
# # 使用样例
# # output_path: 目标存储路径
# # temp_folder: 临时存储路径
# output_path = "../../sysFlowVisualizer/cleanCache"
# temp_folder = "./SampleTmp/tax_200k"
# # 生成有效文件名，避免特殊字符
# csv_filename = "_".join(sourceSet + targetSet) + ".csv"
#
# # 保存采样文件
# save_sample(sampled_data, output_path, csv_filename, temp_folder)
#
# # 关闭 SparkSession
# spark.stop()
