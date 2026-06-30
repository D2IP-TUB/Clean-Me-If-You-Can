import time

from pyspark.sql.functions import col, collect_list
from pyspark.sql.window import Window

from CoreSetSample.mapping_samplify import block_sample


def find_blocks(df, partition):
    # Step 1: 初步分块，基于partition[0]的值分组，并建立每个组的索引映射
    initial_blocks = df.groupby(partition[0]).groups
    block_mapping = {}
    for key, indexes in initial_blocks.items():
        for index in indexes:
            block_mapping[index] = indexes

    # Step 2: 对每个后续属性进行迭代，根据这些属性的值合并块
    for attr in partition[1:]:
        # 对当前属性进行分组，获取值到索引的映射
        value_to_indexes = df.groupby(attr).groups

        # 遍历每个值对应的索引集合
        for indexes in value_to_indexes.values():
            if len(indexes) > 1:
                # 找到所有通过当前属性值连接的行索引集合
                connected_indexes = set()
                for index in indexes:
                    connected_indexes.update(block_mapping[index])

                # 更新块映射，将所有连接的行索引合并为一个块
                for index in connected_indexes:
                    block_mapping[index] = connected_indexes

    # 构建最终的块列表
    final_blocks = set()
    for indexes in block_mapping.values():
        # 使用frozenset是因为它是hashable的，可以作为集合的元素
        final_blocks.add(frozenset(indexes))

    # 返回块的索引列表，每个块是索引的集合
    return [list(block) for block in final_blocks]


def find_blocks_spark(df, partition):
    preattr = partition[0]
    # 初始分块，基于第一个分区属性
    df = df.withColumn("block_id", col(preattr))

    # 迭代合并块
    for attr in partition[1:]:
        # 为当前属性构建窗口，收集所有相同值的 block_id
        w = Window.partitionBy(attr)
        df = df.withColumn("connected_blocks", collect_list("block_id").over(w))

        # 将 block_id 更新为 connected_blocks 中的最小值
        df = df.withColumn("block_id", col("connected_blocks")[0])
        #重新聚类一下上一个属性，目标是把整体加入到闭包中
        w = Window.partitionBy(preattr)
        df = df.withColumn("connected_blocks", collect_list("block_id").over(w))
        # 将 block_id 更新为 connected_blocks 中的最小值
        df = df.withColumn("block_id", col("connected_blocks")[0])
        preattr = attr
    # # 生成最终的块
    # blocks = df.select("index", "block_id").distinct().groupBy("block_id").agg(
    #     collect_list("index").alias("block_rows"))
    #
    # # 转换每个块为单独的 DataFrame
    #
    # block_dfs = [df.filter(col("index").isin(block["block_rows"])) for
    #              block in blocks.collect()]

    # 获取所有类别

    categories = df.select("block_id").distinct().rdd.flatMap(lambda x: x).collect()

    splits = [df.filter(df.block_id == category) for category in categories]
    return splits

def Generate_BlockSample(TotalData, sset, tset, models=None):
    """
    从 Spark 数据集生成样本并转存为 Pandas DataFrame。

    参数:
    - file_load: 字符串，CSV 文件的路径。
    - sset: 源属性集列表，例如 ['zip'],
    - tset: 目标属性集列表，例如 ['city']
    - p: 浮点数，核心集占总数据集比例。
    - save_path: 字符串，保存结果的路径，如果为 None，则不保存。
    """
    # 读取数据，仅包含必要的列
    required_columns = list(set(sset + tset + ['index']))  # 移除重复项
    data = TotalData.select(required_columns)

    # 进行抽样
    start_time = time.time()

    # if tset!=1:
    #     sampled_data = block_sample_cycle(data, models)
    # else:
    sampled_data = block_sample(data, models)
    block_sample_data = find_blocks_spark(sampled_data, sset)

    # 计时并打印抽样所需时间
    print(f"核心样本抽取时间（秒）: {time.time() - start_time}")

    return block_sample_data
