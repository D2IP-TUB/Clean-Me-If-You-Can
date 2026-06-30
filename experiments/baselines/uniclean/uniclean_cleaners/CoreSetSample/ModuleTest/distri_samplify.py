import time

from pyspark.sql import SparkSession
from pyspark.sql.functions import monotonically_increasing_id

from CoreSetSample.ModuleTest.get_patition_block import find_blocks_spark
from CoreSetSample.ModuleTest.handle_data_distri import *


def Generate_Sample(file_load, sset, tset, p, save_path=None):
    """
    从 Spark 数据集生成样本并转存为 Pandas DataFrame。

    参数:
    - file_load: 字符串，CSV 文件的路径。
    - sset: 源属性集列表，例如 ['zip'],
    - tset: 目标属性集列表，例如 ['city']
    - p: 浮点数，核心集占总数据集比例。
    - save_path: 字符串，保存结果的路径，如果为 None，则不保存。
    """
    spark = SparkSession.builder.appName("Sample Extraction").getOrCreate()

    # 读取数据，仅包含必要的列
    required_columns = list(set(sset + tset))  # 移除重复项
    data = spark.read.csv(file_load, header=True, inferSchema=True).select(required_columns)

    # 添加数据行的索引
    data = data.withColumn("index", monotonically_increasing_id())

    # 进行核心集抽样
    start_time = time.time()
    sample_id, special_points = CleansetRamdonSample(data, p, save_path, sourceSet=sset, targetSet=tset)

    # 选择抽样数据
    new_data = data.filter(data['index'].isin(sample_id))

    # 转换为 Pandas DataFrame
    pandas_df = new_data.toPandas()

    # 保存数据
    if save_path:
        block_path = os.path.join(save_path, "sample_data.csv")
        pandas_df.to_csv(block_path, index=False)
        print(f"Sample data saved to: {block_path}")

    # 计时并打印抽样所需时间
    print(f"核心样本抽取时间（秒）: {time.time() - start_time}")

    # 关闭 Spark 会话
    spark.stop()

    return pandas_df

def CleansetRamdonSample(data, save_path, getGraph=False, indexplt=True, sourceSet=None, targetSet=None):
    # 计算分割的数量（每2400行左右的数据一个分割）
    groupLength = 10
    if sourceSet is None:
        sourceSet = []
    if targetSet is None:
        targetSet = data.columns
    num_splits = math.ceil(data.count() / groupLength)  # 分组个数
    splits = data.randomSplit([1.0] * num_splits)
    # 初始化存储所有样本和特殊样本的ID列表
    Total_sampleId = []
    Total_special_sampleId = []
    num_limit = 1
    # 遍历每个分割，获取样本ID
    for i in range(min(num_splits, num_limit)):
        # print("Processing split:", i)
        if i == 0 and getGraph is False:
            sampleId, special_sampleId = getCoreId(splits[i], True, save_path, False, sourceSet=sourceSet,
                                                   targetSet=targetSet)
            Total_sampleId.extend(sampleId)
            Total_special_sampleId.extend(special_sampleId)
        else:
            sampleId, special_sampleId = getCoreId(splits[i], getGraph, save_path, indexplt, sourceSet=sourceSet,
                                                   targetSet=targetSet)
            Total_sampleId.extend(sampleId)
            Total_special_sampleId.extend(special_sampleId)
        # sampleId, special_sampleId = getCoreId(splits[i], p, getGraph, save_path,indexplt)
        # Total_sampleId.extend(sampleId)
        # Total_special_sampleId.extend(special_sampleId)

    # 打印总样本ID和特殊样本ID
    # print("Total Sample IDs:", Total_sampleId)
    # print("Number of Total Sample IDs:", len(Total_sampleId))
    # print("Total Special Sample IDs:", Total_special_sampleId)
    # print("Number of Total Special Sample IDs:", len(Total_special_sampleId))
    return Total_sampleId, Total_special_sampleId
def CleansetBlockSample(data, save_path, getGraph=False, indexplt=True, sourceSet=None, targetSet=None):
    # 计算分割的数量（每2400行左右的数据一个分割）

    groupLength = 1400
    if sourceSet is None:
        sourceSet = []
    if targetSet is None:
        targetSet = data.columns
    splits = find_blocks_spark(data, sourceSet)
    # num_splits = math.ceil(data.count() / groupLength)  # 分组个数
    # splits = data.randomSplit([1.0] * num_splits)
    # 初始化存储所有样本和特殊样本的ID列表
    Total_sampleId = []
    Total_special_sampleId = []
    # 获取所有唯一的属性值

    # num_limit = 1
    # 遍历每个分割，获取样本ID,这里可以并行
    # Todo：可以并行运行
    print(len(splits))
    for i in range(len(splits)):
        print("Processing split:", i)
        if i == 0 and getGraph is False:
            sampleId, special_sampleId = getCoreId(splits[i], True, save_path, False, sourceSet=sourceSet,
                                                   targetSet=targetSet)
            Total_sampleId.extend(sampleId)
            Total_special_sampleId.extend(special_sampleId)
        else:
            sampleId, special_sampleId = getCoreId(splits[i], getGraph, save_path, indexplt, sourceSet=sourceSet,
                                                   targetSet=targetSet)
            Total_sampleId.extend(sampleId)
            Total_special_sampleId.extend(special_sampleId)
        # sampleId, special_sampleId = getCoreId(splits[i], p, getGraph, save_path,indexplt)
        # Total_sampleId.extend(sampleId)
        # Total_special_sampleId.extend(special_sampleId)

    # 打印总样本ID和特殊样本ID
    # print("Total Sample IDs:", Total_sampleId)
    # print("Number of Total Sample IDs:", len(Total_sampleId))
    # print("Total Special Sample IDs:", Total_special_sampleId)
    # print("Number of Total Special Sample IDs:", len(Total_special_sampleId))
    return Total_sampleId, Total_special_sampleId