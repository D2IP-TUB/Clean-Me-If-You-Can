import pyspark.sql.functions as F
# 创建测试用的 EditPenalty 类（基于之前的实现）
from pyspark.sql import DataFrame
from pyspark.sql import Row
from pyspark.sql import SparkSession
from pyspark.sql.functions import udf
from pyspark.sql.types import DoubleType
from textdistance import Levenshtein
#
# os.environ['PYSPARK_PYTHON'] = "D:\python37\python.exe"  # 放Python的位置


class EditPenalty:
    def __init__(self, source: DataFrame, metric={}):
        """
        构造函数接受一个数据集和一个字典，将属性映射到相似度度量。
        source -- a dataframe
        metric -- 度量，一个字典映射，将属性映射到相似度度量
        """
        self.source = source.cache()  # 缓存原始 DataFrame
        self.metric = metric
        if not metric:
            self.metric = {s: 'edit' for s in source.columns}  # 默认编辑距离

    def edit(str1, str2):
        if str1 is None or str2 is None:
            return 1.0
        m = len(str1)
        n = len(str2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]

        for i in range(m + 1):
            for j in range(n + 1):
                if i == 0:
                    dp[i][j] = j
                elif j == 0:
                    dp[i][j] = i
                elif str1[i - 1] == str2[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])

        return dp[m][n] / max(m, n)

    def jaccard(self, target, source):
        if target is None or source is None:
            return 1.0
        ttokens = set(target.lower().split())
        stokens = set(source.lower().split())
        return Levenshtein.distance(target, source) / max(len(target), len(source)) + (
                len(target) + len(source)) * 0.005

    def _quality_func(self, df):
        # 检查列名和列数是否匹配
        if set(self.source.columns) != set(df.columns):
            raise ValueError("两个数据集的列名或列数不相同")

        # 对于每个指标计算质量得分
        for col_name in df.columns:
            metric = self.metric.get(col_name, 'edit')
            # 提取源数据集中该列的第一个值
            source_value = self.source.select(col_name).first()[0]
            # 定义UDF
            if metric == 'edit':
                quality_udf = udf(self.edit, DoubleType())
            elif metric == 'jaccard':
                quality_udf = udf(self.jaccard, DoubleType())
            else:
                raise ValueError(f"未知的相似度度量方式: {metric}")

            # 应用UDF来计算质量得分
            df = df.withColumn(f"{col_name}_quality", quality_udf(F.col(col_name), F.lit(source_value)))

        # 计算每一行的质量得分
        quality_columns = [f"{c}_quality" for c in df.columns]
        df = df.withColumn("row_quality", F.sum(F.array(*quality_columns)) / len(df.columns))

        return df


# 初始化 SparkSession
spark = SparkSession.builder \
    .appName("EditPenaltyTest") \
    .getOrCreate()

# 创建测试数据
data = [Row(a="apple", b="banana"), Row(a="grape", b="orange")]
source_data = [Row(a="apple", b="orange"), Row(a="grape", b="banana")]

df = spark.createDataFrame(data)
source_df = spark.createDataFrame(source_data)

# 创建 EditPenalty 实例
edit_penalty = EditPenalty(source_df)

# 测试 _quality_func
result_df = edit_penalty._quality_func(df)
result_df.show()

# 停止 SparkSession
spark.stop()
