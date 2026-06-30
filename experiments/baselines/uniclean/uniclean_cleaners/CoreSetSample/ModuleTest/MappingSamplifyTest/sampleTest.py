from pyspark.sql import SparkSession, Window
import pyspark.sql.functions as F
from functools import reduce

def block_sample(df, sourceSet, targetSet):
    group_columns = sourceSet + targetSet
    grouped = df.groupBy(*group_columns).count()
    window_spec_partition = Window.partitionBy(*sourceSet)
    grouped = grouped.withColumn("target_count", F.count(targetSet[0]).over(window_spec_partition))
    window_spec_rank = Window.partitionBy(*sourceSet).orderBy("count")
    grouped = grouped.withColumn("rank", F.when(F.col("target_count") > 1, F.dense_rank().over(window_spec_rank)).otherwise(0)) \
        .withColumn("sample_count", F.when(F.col("rank") > 0, F.col("rank")).otherwise(0))
    window_spec_target = Window.partitionBy(*group_columns).orderBy(F.rand())
    sampled_data = df.join(grouped, group_columns) \
        .withColumn("row_num", F.row_number().over(window_spec_target)) \
        .filter(F.col("row_num") <= F.col("sample_count")) \
        .drop("count", "target_count", "rank", "sample_count", "row_num")
    return sampled_data

def multi_rule_sample(df, rules):
    sampled_dfs = [block_sample(df, sourceSet, targetSet) for sourceSet, targetSet in rules]
    final_sampled_df = reduce(lambda df1, df2: df1.union(df2).distinct(), sampled_dfs)
    return final_sampled_df

# 初始化 SparkSession
spark = SparkSession.builder.appName("MultiRuleSampling").getOrCreate()

# 示例数据
data = [(2, 3, 1), (2, 3, 1), (2, 3, 1), (2, 4, 2), (3, 4, 2), (3, 4, 1)]
columns = ["a", "b", "c"]
df = spark.createDataFrame(data, columns)

# 定义规则
rules = [(["a"], ["c"]), (["b"], ["c"])]

# 进行多规则采样
sampled_df = multi_rule_sample(df, rules)
sampled_df.show()
