import os
import shutil
import tempfile
import time
import uuid

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import BooleanType
from pyspark.sql.window import Window


def _materialize(df: DataFrame) -> DataFrame:
    """Break Spark lineage by spilling to a temp parquet file.

    Deep join/window chains in block_sample can exhaust the driver heap
    when count()/collect() triggers a single mega-stage evaluation.
    """
    tmp_dir = os.path.join(
        tempfile.gettempdir(),
        "uniclean_block_sample",
        uuid.uuid4().hex,
    )
    os.makedirs(tmp_dir, exist_ok=True)
    df.write.mode("overwrite").parquet(tmp_dir)
    spark = SparkSession.getActiveSession()
    if spark is None:
        spark = df._jdf.sparkSession()
    return spark.read.parquet(tmp_dir)


def _bounded_count(df: DataFrame, upper_bound: int) -> int:
    """Return exact row count when <= upper_bound, else upper_bound + 1."""
    return df.limit(upper_bound + 1).count()


def Generate_Sample(TotalData, sset, tset, models=None, save_path=None, single_max=30000000):
    """
    从 Spark 数据集生成样本并转存为 Pandas DataFrame。

    参数:
    - file_load: 字符串，CSV 文件的路径。
    - sset: 源属性集列表，例如 ['zip'],
    - tset: 目标属性集列表，例如 ['city']
    - p: 浮点数，核心集占总数据集比例。
    - save_path: 字符串，保存结果的路径，如果为 None，则不保存。
    """

    # # 进行抽样
    start_time = time.time()
    # 读取数据，仅包含必要的列
    required_columns = list(set(sset + tset + ['index']))  # 移除重复项
    data = TotalData.select(required_columns)
    sampled_data, error_threshold = block_sample(data, models, single_max=single_max)
    # 保存数据
    if save_path:
        block_path = os.path.join(save_path, "sample_data.csv")
        sampled_data.write.csv(block_path, header=True, mode='overwrite')
        print(f"Sample data saved to: {block_path}")

    # # 计时并打印抽样所需时间
    print(f"核心样本抽取时间（秒）: {time.time() - start_time}")

    return sampled_data,error_threshold


def block_sample(df, models, single_max=30000):
    error_threshold = 1
    sample_probability_columns=[]
    for i, model in enumerate(models):
        sourceSet = model.source
        targetSet = model.target
        group_columns = list(sourceSet.union(targetSet))
        # 将 null 值替换为 '__NULL__'，确保它们在 groupBy 中参与计算
        for col in group_columns:
            # df = df.withColumn(col, F.when(F.col(col).isNull(), F.lit("__NULL__")).otherwise(F.col(col)))
            df = df.withColumn(col, F.when((F.col(col).isNull()) | (F.col(col) == "empty"), F.lit("__NULL__")).otherwise(
            F.col(col)))
        # 对每个 source-target 组合进行聚合，计算 count 和 target_count
        rule_grouped = df.groupBy(*group_columns).count()
        window_spec_partition = Window.partitionBy(*sourceSet)
        rule_grouped = rule_grouped.withColumn(f"target_total_{i}", F.sum("count").over(window_spec_partition)) \
            .withColumn(f"target_count_{i}", F.col("count"))
        # 计算非 __NULL__ 值的最大值（排除 __NULL__）
        rule_grouped = rule_grouped.withColumn(f"max_target_count_{i}",
                                               F.max(F.when(F.col(list(targetSet)[0]) != '__NULL__', F.col("count"))).over(
                                                   window_spec_partition))

        # rule_grouped = rule_grouped.withColumn(f"target_total_{i}", F.sum("count").over(window_spec_partition)) \
        #     .withColumn(f"target_count_{i}", F.col("count")).withColumn(f"max_target_count_{i}",
        #                                                                 F.max(F.col("count")).over(
        #                                                                     window_spec_partition))
        # 计算每个 source 下最大的 target 数目占总数的比例
        rule_grouped = rule_grouped.withColumn(f"max_target_rate_{i}", F.col(f"max_target_count_{i}") / F.col(f"target_total_{i}"))
        # 找到最小的比例
        error_threshold = min(rule_grouped.agg(F.min(f"max_target_rate_{i}")).collect()[0][0],error_threshold)

        # 计算 rank_total_i 和 rank_count_i
        rule_grouped = rule_grouped.withColumn(f"rank_count_{i}", F.dense_rank().over(
            Window.partitionBy(*sourceSet).orderBy(F.desc("count")))) \
            .withColumn(f"rank_total_{i}", F.sum(F.col(f"rank_count_{i}")).over(window_spec_partition))

        # 加入原始数据框
        df = df.join(
            rule_grouped.select(*group_columns, f"target_total_{i}", f"target_count_{i}", f"rank_total_{i}",
                                f"rank_count_{i}"), group_columns, "left")
        if len(models) > 1:
            df = _materialize(df)
        # 根据条件函数计算采样概率
        # 定义UDF
        if 'condition_func' in model.fixValueRules:
            condition_func_udf = F.udf(lambda *source_attrs: model.fixValueRules['condition_func'](tuple(source_attrs)), BooleanType())

            # 创建条件列
            condition_col = condition_func_udf(*[F.col(col) for col in sourceSet])
            sample_probability_column = F.when(condition_col, 1.0).otherwise(F.col(f"target_count_{i}") / F.col(f"target_total_{i}"))
        else:
            sample_probability_column = F.col(f"target_count_{i}") / F.col(f"target_total_{i}")

        # 根据记录的每个规则的信息计算每行的最终采样概率
        sample_probability_columns.append(sample_probability_column)

    final_sample_probability = sample_probability_columns[0]
    for col in sample_probability_columns[1:]:
        final_sample_probability *= col
    df = df.withColumn("p", final_sample_probability)
    df = _materialize(df)
    # 去重
    if len(models) == 1:
        model = models[0]
        sourceSet = model.source
        targetSet = model.target
        # 对 sourceSet 和 targetSet 进行分组
        group_columns = list(sourceSet.union(targetSet))

        # 聚合并计算每个 source 组合中的 target 分布情况
        grouped = df.groupBy(*group_columns).count()

        # 对每个 source 组合，计算不同 target 种类的数量
        window_spec_partition = Window.partitionBy(*sourceSet)
        targetSetlist = list(targetSet)
        grouped = grouped.withColumn("target_count", F.count(targetSetlist[0]).over(window_spec_partition))

        # 如果 target_count > 1，则排序并设置抽样数；否则 sample_count 设置为 0
        window_spec_rank = Window.partitionBy(*sourceSet).orderBy("count")
        grouped = grouped.withColumn("rank",
                                     F.when(F.col("target_count") > 1, F.dense_rank().over(window_spec_rank)).otherwise(
                                         0)) \
            .withColumn("sample_count", F.when(F.col("rank") > 0, F.col("rank")).otherwise(0))

        # 根据上面计算的 sample_count 进行去重
        window_spec_target = Window.partitionBy(*group_columns).orderBy(F.rand())
        df = df.join(grouped, group_columns) \
            .withColumn("row_num", F.row_number().over(window_spec_target)) \
            .filter(F.col("row_num") <= F.col("sample_count")) \
            .drop("count", "target_count", "rank", "sample_count", "row_num")
    else:
        attr_set = set()
        for model in models:
            attr_set = attr_set.union(model.source)
            attr_set = attr_set.union(model.target)
        group_columns = list(attr_set)
        # 聚合并计算每个组合中的分布情况
        grouped = df.groupBy(*group_columns).count()

        # 按照聚合块的大小从小到大排序，并使用 dense_rank 确保相等 count 得到相同 rank
        window_spec_partition = Window.orderBy(F.asc("count"))
        grouped = grouped.withColumn("rank", F.dense_rank().over(window_spec_partition))
        grouped = grouped.withColumn("sample_count", F.col("rank"))

        # 生成实际的采样数据
        window_spec_target = Window.partitionBy(*group_columns).orderBy(F.rand())
        df = df.join(grouped, group_columns) \
            .withColumn("row_num", F.row_number().over(window_spec_target)) \
            .filter(F.col("row_num") <= F.col("sample_count")) \
            .drop("count", "rank", "sample_count", "row_num")

    df = _materialize(df)
    #开始采样
    df = df.filter((F.col("p") < 1.0))
    # 生成实际的采样数据
    df = df.withColumn("rand_val", F.rand())
    df = _materialize(df)
    # 打印每列的非空值数量（bounded count avoids a full-table scan）
    print("存在不一致的数据大小为：")
    count = _bounded_count(df, single_max)
    print(count)
    if count != 0:
        if len(models) == 1:
            if count > single_max:
                model = models[0]
                sourceSet = model.source
                # 按多个列进行排序，并取前 single_max 行
                df = df.orderBy([F.col(col) for col in sourceSet]).limit(single_max)
        else:
            if count > single_max:
                # Step 1: 遍历 models，收集每个 model 的 source 属性（属性集合的列表）
                source_columns = []
                for model in models:
                    source_columns.append(model.source)  # 假设 model.source 是属性集合
                # Step 2: 遍历 source_columns，找到不同值组合最少的属性集合
                min_count = float("inf")  # 设置一个初始的最大值
                min_source_set = None  # 用于保存最小组合的属性集合
                for source_set in source_columns:
                    # 统计每个属性集合的不同值组合数量
                    distinct_count = df.select([F.col(col) for col in source_set]).distinct().count()
                    print(f"属性集合 {source_set} 的不同值组合数量: {distinct_count}")
                    # 找到最小的组合数量
                    if distinct_count < min_count:
                        min_count = distinct_count
                        min_source_set = source_set

                # Step 3: 找到数据量最少的属性集合后进行处理
                if min_source_set:
                    print(f"数据量最少的属性集合是: {min_source_set}，数量为: {min_count}")
                    # 按该属性集合进行排序，并取前 single_max 行
                    df = df.orderBy([F.col(col) for col in min_source_set]).limit(single_max)
                # 进一步处理，比如根据 p 和 rand_val 进行过滤
            df = df.filter(
                    (F.col("p") < error_threshold) | (F.col("rand_val") <= F.col("p"))
                )
    # 删除临时列
    sampled_data = df.drop("rand_val", *[f"target_total_{i}" for i in range(len(models))],
                           *[f"target_count_{i}" for i in range(len(models))], "final_sample_probability",
                           *[f"rank_total_{i}" for i in range(len(models))],
                           *[f"rank_count_{i}" for i in range(len(models))])
    return sampled_data, error_threshold

def save_sample(df: DataFrame, output_path: str, csv_filename: str, temp_folder: str):
    """
    将给定的 DataFrame 保存为 CSV ，复制到目标文件夹。

    :param df: 要保存的 DataFrame
    :param output_path: 保存的目标文件夹
    :param csv_filename: CSV 文件的自定义文件名
    :param temp_folder: 用于临时保存的文件夹路径
    """
    # 保存 CSV 文件，repartition 为 1 以获得单一输出文件
    df.repartition(1).write.mode('overwrite').option("mapreduce.fileoutputcommitter.marksuccessfuljobs", "false") \
        .option("header", "true").csv(path=os.path.join(temp_folder, "sampleddata"), encoding="utf-8")

    # 找到并复制生成的 CSV 文件到目标文件夹，并重命名
    for filename in os.listdir(os.path.join(temp_folder, "sampleddata")):
        if filename.startswith("part-") and filename.endswith(".csv"):
            full_file_name = os.path.join(temp_folder, "sampleddata", filename)
            if os.path.isfile(full_file_name):
                shutil.copy(full_file_name, os.path.join(output_path, csv_filename))
                break
