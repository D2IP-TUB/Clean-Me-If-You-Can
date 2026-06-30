from pyspark.sql import SparkSession, Window
import pyspark.sql.functions as F
from functools import reduce


class Model:
    def __init__(self, source, target):
        self.source = source
        self.target = target


def block_sample(df, sourceSet, targetSet):
    # 对 sourceSet 和 targetSet 进行分组
    group_columns = sourceSet + targetSet

    # 聚合并计算每个 source 组合中的 target 分布情况
    grouped = df.groupBy(*group_columns).count()

    # 对每个 source 组合，计算不同 target 种类的数量
    window_spec_partition = Window.partitionBy(*sourceSet)
    grouped = grouped.withColumn("target_count", F.count(targetSet[0]).over(window_spec_partition))

    # 如果 target_count > 1，则排序并设置抽样数；否则 sample_count 设置为 0
    window_spec_rank = Window.partitionBy(*sourceSet).orderBy("count")
    grouped = grouped.withColumn("rank",
                                 F.when(F.col("target_count") > 1, F.dense_rank().over(window_spec_rank)).otherwise(0)) \
        .withColumn("sample_count", F.when(F.col("rank") > 0, F.col("rank")).otherwise(0))

    # 生成实际的采样数据
    # 根据上面计算的 sample_count 进行采样
    window_spec_target = Window.partitionBy(*group_columns).orderBy(F.rand())
    sampled_data = df.join(grouped, group_columns) \
        .withColumn("row_num", F.row_number().over(window_spec_target)) \
        .filter(F.col("row_num") <= F.col("sample_count")) \
        .drop("count", "target_count", "rank", "sample_count", "row_num")
    # 确保列顺序一致
    sampled_data = sampled_data.select(df.columns)
    # 输出被采样的数据
    return sampled_data


def multi_rule_sample1(df, rules):
    sampled_dfs = [block_sample(df, sourceSet, targetSet) for sourceSet, targetSet in rules]
    final_sampled_df = reduce(lambda df1, df2: df1.union(df2).distinct(), sampled_dfs)
    return final_sampled_df, sampled_dfs


def multi_rule_sample(df, models):
    df_with_sample_counts = df
    for i, model in enumerate(models):
        sourceSet = model.source
        targetSet = model.target
        group_columns = sourceSet + targetSet

        grouped = df.groupBy(*group_columns).count()
        window_spec_partition = Window.partitionBy(*sourceSet)
        grouped = grouped.withColumn(f"target_count_{i}", F.count(targetSet[0]).over(window_spec_partition))
        window_spec_rank = Window.partitionBy(*sourceSet).orderBy("count")
        grouped = grouped.withColumn(f"rank_{i}", F.when(F.col(f"target_count_{i}") > 1,
                                                         F.dense_rank().over(window_spec_rank)).otherwise(0)) \
            .withColumn(f"sample_count_{i}", F.when(F.col(f"rank_{i}") > 0, F.col(f"rank_{i}")).otherwise(0))
        df_with_sample_counts = df_with_sample_counts.join(grouped.select(*group_columns, f"sample_count_{i}"),
                                                           group_columns, "left")

    # 计算最终的采样数量，这里我们可以采用最大值或者其他的策略
    sample_count_columns = [f"sample_count_{i}" for i in range(len(models))]
    df_with_sample_counts = df_with_sample_counts.withColumn("final_sample_count", F.least(*sample_count_columns))

    # 根据最终的采样数量进行采样
    window_spec_final = Window.partitionBy(*df.columns).orderBy(F.rand())
    sampled_df = df_with_sample_counts.withColumn("row_num", F.row_number().over(window_spec_final)) \
        .filter(F.col("row_num") <= F.col("final_sample_count")) \
        .drop("row_num", *sample_count_columns)

    return sampled_df


from pyspark.sql import SparkSession, Window
import pyspark.sql.functions as F


class Model:
    def __init__(self, source, target):
        self.source = source
        self.target = target


def multi_rule_sample2(df, models):
    attrset = set()
    for model in models:
        attrset = attrset.union(set(model.source))
        attrset = attrset.union(set(model.target))
    group_columns = list(attrset)

    # 聚合并计算每个组合中的分布情况
    grouped = df.groupBy(*group_columns).count()

    # 按照聚合块的大小从小到大排序，并使用 dense_rank 确保相等 count 得到相同 rank
    window_spec_partition = Window.orderBy(F.asc("count"))
    grouped = grouped.withColumn("rank", F.dense_rank().over(window_spec_partition))

    # 计算采样数，按照 rank 进行采样，rank 最小的采样一个，以此类推
    grouped = grouped.withColumn("sample_count", F.col("rank"))

    # 生成实际的采样数据
    window_spec_target = Window.partitionBy(*group_columns).orderBy(F.rand())
    sampled_data = df.join(grouped, group_columns) \
        .withColumn("row_num", F.row_number().over(window_spec_target)) \
        .filter(F.col("row_num") <= F.col("sample_count")) \
        .drop("count", "rank", "sample_count", "row_num")

    # 对每个规则生成采样标记
    for model in models:
        sourceSet = model.source
        targetSet = model.target
        group_columns = sourceSet + targetSet

        rule_grouped = df.groupBy(*group_columns).count()
        window_spec_partition = Window.partitionBy(*sourceSet)
        rule_grouped = rule_grouped.withColumn("target_count", F.count(targetSet[0]).over(window_spec_partition))
        window_spec_rank = Window.partitionBy(*sourceSet).orderBy("count")
        # rule_grouped = rule_grouped.withColumn("rank", F.when(F.col("target_count") > 1,
        #                                                       F.dense_rank().over(window_spec_rank)).otherwise(0)) \
        #     .withColumn("sample_count_rule", F.when(F.col("rank") > 0, F.col("rank")).otherwise(0))
        rule_grouped = rule_grouped.withColumn("rank", F.when(F.col("target_count") > 1,
                                                              F.dense_rank().over(window_spec_rank)).otherwise(0)) \
            .withColumn("sample_count_rule", F.when(F.col("rank") > 0, F.col("rank")).otherwise(0))
        sampled_data_rule = df.join(rule_grouped, group_columns).drop("rank", "target_count")
        sampled_data = sampled_data.join(sampled_data_rule.select("id", "sample_count_rule"), on="id", how="left")
        sampled_data.show()

    # 分析并确定最终的采样数量
    sample_count_columns = [F.col(f"sample_count_rule_{i}") for i in range(len(models))]
    sampled_data = sampled_data.withColumn("final_sample_count", F.least(*sample_count_columns))

    # 生成最终的采样数据
    sampled_data = sampled_data.withColumn("row_num",
                                           F.row_number().over(Window.partitionBy(*group_columns).orderBy(F.rand()))) \
        .filter(F.col("row_num") <= F.col("final_sample_count")) \
        .drop("row_num", "final_sample_count", *sample_count_columns)

    return sampled_data


from pyspark.sql import SparkSession, Window
import pyspark.sql.functions as F


class Model:
    def __init__(self, source, target):
        self.source = set(source)
        self.target = set(target)


def sigmoid(x, k=1):
    return (1 / (1 + F.exp(-k * x)))-0.5


def block_sample(df, models):
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

        # 生成实际的采样数据
        # 根据上面计算的 sample_count 进行采样
        window_spec_target = Window.partitionBy(*group_columns).orderBy(F.rand())
        sampled_data = df.join(grouped, group_columns) \
            .withColumn("row_num", F.row_number().over(window_spec_target)) \
            .filter(F.col("row_num") <= F.col("sample_count")) \
            .drop("count", "target_count", "rank", "sample_count", "row_num")
        # 确保列顺序一致
        sampled_data = sampled_data.select(df.columns)
    else:
        k = 1
        # 对 attrSet 进行分组
        attrset = set()
        # 去重
        for model in models:
            attrset = attrset.union(model.source)
            attrset = attrset.union(model.target)
        group_columns = list(attrset)
        # 聚合并计算每个组合中的分布情况
        grouped = df.groupBy(*group_columns).count()

        # 按照聚合块的大小从小到大排序，并使用 dense_rank 确保相等 count 得到相同 rank
        window_spec_partition = Window.orderBy(F.asc("count"))
        grouped = grouped.withColumn("rank", F.dense_rank().over(window_spec_partition))

        # 计算采样数，按照 rank 进行采样，rank 最小的采样一个，以此类推
        grouped = grouped.withColumn("sample_count", F.col("rank"))

        # 生成实际的采样数据
        window_spec_target = Window.partitionBy(*group_columns).orderBy(F.rand())
        df = df.join(grouped, group_columns) \
            .withColumn("row_num", F.row_number().over(window_spec_target)) \
            .filter(F.col("row_num") <= F.col("sample_count")) \
            .drop("count", "rank", "sample_count", "row_num")
        for i, model in enumerate(models):
            sourceSet = model.source
            targetSet = model.target
            group_columns = list(sourceSet.union(targetSet))

            # 对每个 source-target 组合进行聚合，计算 count 和 target_count
            rule_grouped = df.groupBy(*group_columns).count()
            window_spec_partition = Window.partitionBy(*sourceSet)
            rule_grouped = rule_grouped.withColumn(f"target_total_{i}", F.sum("count").over(window_spec_partition)) \
                .withColumn(f"target_count_{i}", F.col("count"))

            # 计算 rank_total_i 和 rank_count_i
            rule_grouped = rule_grouped.withColumn(f"rank_count_{i}", F.dense_rank().over(
                Window.partitionBy(*sourceSet).orderBy(F.desc("count")))) \
                .withColumn(f"rank_total_{i}", F.sum(F.col(f"rank_count_{i}")).over(window_spec_partition))

            # 加入原始数据框
            df = df.join(
                rule_grouped.select(*group_columns, f"target_total_{i}", f"target_count_{i}", f"rank_total_{i}",
                                    f"rank_count_{i}"), group_columns, "left")

        # 根据记录的每个规则的信息计算每行的最终采样概率
        # sample_count_columns = [F.col(f"target_count_{i}") / F.col(f"target_total_{i}") for i in range(len(models))]
        # df = df.withColumn("final_sample_probability", F.mean(F.array(*sample_count_columns)).cast("float"))
        # sample_probability_columns = [F.col(f"target_count_{i}") / F.col(f"target_total_{i}") for i in range(len(models))]
        # final_sample_probability_expr = F.expr("*".join([f"({col})" for col in sample_probability_columns]))
        # df = df.withColumn("final_sample_probability", final_sample_probability_expr.cast("float"))
        sample_probability_columns = [F.col(f"target_count_{i}") / F.col(f"target_total_{i}") for i in
                                      range(len(models))]
        final_sample_probability = sample_probability_columns[0]
        for col in sample_probability_columns[1:]:
            final_sample_probability *= col

        df = df.withColumn("final_sample_probability", final_sample_probability)
        df = df.filter((F.col("final_sample_probability") < 1.0))

        # df = df.withColumn("adjusted_sample_probability", F.log1p(F.col("final_sample_probability")) / F.log1p(F.lit(2.0)))
        # df = df.withColumn("adjusted_sample_probability", F.pow(F.col("final_sample_probability"), 0.5))
        # 对采样概率进行 sigmoid 调整
        df = df.withColumn("adjusted_sample_probability", sigmoid(F.col("final_sample_probability"), k))
        b = df.agg(F.mean("adjusted_sample_probability")).first()[0]
        # 生成实际的采样数据
        df = df.withColumn("rand_val", F.rand())

        # 根据最终采样概率进行过滤
        df = df.filter((F.col("adjusted_sample_probability") < b) | (F.col("rand_val") <= F.col("adjusted_sample_probability")))

        # 删除临时列
        sampled_data = df.drop("rand_val", *[f"target_total_{i}" for i in range(len(models))],
                               *[f"target_count_{i}" for i in range(len(models))], "final_sample_probability",
                               *[f"rank_total_{i}" for i in range(len(models))],
                               *[f"rank_count_{i}" for i in range(len(models))])
    return sampled_data

file_load = 'data.csv'
# scale_factor = 50  # 数据的放大倍数，用于模拟大规模数据的情况
# 以上为输入部分


spark = SparkSession.builder.appName(" CleanSession").getOrCreate()
data = spark.read.csv(file_load, header=True, inferSchema=True)
# 生成一个包含五个相同 DataFrame 的列表
dataframes = [data] * 50


def union_all(df1, df2):
    return df1.unionAll(df2)


# 使用 reduce 高效地合并所有 DataFrame
data = reduce(union_all, dataframes)
# 定义规则
# rules = [(["areacode"], ["state"]), (["zip"], ["state"])]
required_columns = ['areacode', 'zip', 'state', 'id']  # 移除重复项
data = data.select(required_columns)
# 进行多规则采样
# 定义规则
models = [Model(["areacode"], ["state"]), Model(["zip"], ["state"])]

sampled_df = block_sample(data, models)
sampled_df.show()
print(sampled_df.count())
# for df in dfs:
#     df.show()
