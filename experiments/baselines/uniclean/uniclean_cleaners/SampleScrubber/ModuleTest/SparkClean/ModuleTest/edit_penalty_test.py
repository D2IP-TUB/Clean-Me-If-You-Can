import numpy as np
from pyspark.sql import functions as F
from pyspark.sql.functions import udf, col
from pyspark.sql.types import DoubleType

from SampleScrubber.ModuleTest.SparkClean.util.cleanudf import edit


# os.environ['PYSPARK_PYTHON'] = "D:\python37\python.exe"  # 放Python的位置


class DataModel(object):
    """一个约束的对象是将数据规则转换为质量函数的基本包装类。
    domain -- 属性集合
    """

    def __init__(self, domain=set()):

        self.domain = domain
        # 这是处理域未关闭时的约束的特殊情况代码
        self.domainParams = {}  # domainParams是一个字典
        try:
            self.domainParams['ExtDict'] = self.codebook  # codebook是一个字典，键是属性名，值是属性的值域
        except:
            pass

    def quality_func(self, df):
        """评估特定数据库实例的质量函数。
                0.0     如果seq1 == seq2
                1.0     如果len(seq1) == 0或len(seq2) == 0
            df -- a spark dataframe
        """
        return self._quality_func(df)

    def _quality_func(self, df):
        raise NotImplementedError("未实现质量函数")  # 抛出异常：未实现的质量函数

    def __str__(self):
        try:
            return self.msg
        except:
            return '无法获取该约束的消息'

    # 下面的方法实现了质量函数的基本运算代数方法

    def __add__(self, other):
        """__add__ 两个质量函数的和"""
        dm = DataModel()
        dm.quality_func = lambda df: (self.quality_func(df) + other.quality_func(df)) / 2  # 两个质量函数的平均值
        dm.domain = self.domain.union(other.domain)  # 两个质量函数的属性集合的并集
        dm.domainParams = self.domainParams.copy()
        dm.domainParams.update(other.domainParams)  # 合并other字典的参数
        return dm

    def __mul__(self, other):
        """__mul__ 两个质量函数的乘积或按位比较"""
        try:
            fother = float(other)  # other是质量评估的结果，可能是矩阵也可能是float
            dm = DataModel()  # c是一个约束对象
            dm.quality_func = lambda df: fother * self.quality_func(df)
            dm.domain = self.domain.union(other.domain)
            try:
                dm.msg = self.msg
            except:
                pass
            dm.domainParams = self.domainParams.copy()  # 属性合并
            dm.domainParams.update(other.domainParams)
            return dm
        except:  # 按位比较
            dm = DataModel()
            dm.quality_func = lambda df: np.maximum(self.quality_func(df), other.quality_func(df))
            dm.domain = self.domain.union(other.domain)
            dm.domainParams = self.domainParams.copy()
            dm.domainParams.update(other.domainParams)
            try:
                dm.msg = self.msg
            except:
                pass
            return dm


class EditPenalty(DataModel):
    """EditPenalty 代表在质量评估中的惩罚，惩罚对数据集的修改。
     将数据变化与当前数据集进行比较并对更改进行评分获取编辑惩罚值。
    """

    def __init__(self, source, metric={}, w2vModel=None):
        """构造函数接受一个数据集和一个字典，将属性映射到相似度度量。
        source -- a dataframe
        metric -- 度量，一个字典映射，将属性映射到相似度度量，包括三种相似度度量方式：['jaccard', 'semantic', 'edit'].
        w2vModel -- 语义相似度（'semantic'）模型
        """
        self.source = source
        for col_name in self.source.columns:
            if col_name == 'index':
                continue
            self.source = self.source.withColumnRenamed(col_name, col_name + "_source")
        # 默认设置为‘edit’相似度
        self.metric = {s: 'edit' for s in source.columns}
        # 默认不使用语义相似度
        semantic = False
        for m in metric:  # m是属性名
            self.metric[m] = metric[m]
            if metric[m] == 'semantic':
                semantic = True
        self.word_vectors = w2vModel
        if semantic and w2vModel is None:
            raise ValueError("如果您使用语义相似度，请提供一个word2vec模型")
        self.cache = {}

    def _quality_func(self, df):
        if len(self.source.columns) != len((df.columns)):
            raise ValueError("两个数据集的列名或列数不相同")
        df_joined_by_index = df.join(self.source, "index")
        # quality_udf = udf(edit, DoubleType())
        for col_name in df.columns:
            if (col_name == 'index'):
                continue
            metric = self.metric.get(col_name, 'edit')  # 使用self.metric字典来获取与给定的col_name对应的值，如果找不到对应的键，则返回字符串'edit'
            if metric == 'edit':
                quality_udf = udf(edit, DoubleType())
            # elif metric == 'jaccard':
            #     quality_udf = udf(self.jaccard, DoubleType())
            # elif metric == 'semantic':
            #     quality_udf = udf(self.semantic, DoubleType())
            else:
                raise ValueError(f"未知的相似度度量方式: {metric}")
            # 应用UDF来计算质量得分
            df_joined_by_index = df_joined_by_index.withColumn(f"{col_name}_Equality",
                                                               quality_udf(col(col_name), col(col_name + "_source")))
        # sum_columns = [col(c) for c in df_joined_by_index.columns if "_Equality" in c]
        sum_columns = [col(c) for c in df_joined_by_index.columns if "_Equality" in c]

        # 计算这些列的和并除以列的数量
        average_sum = sum(sum_columns) / len(sum_columns)
        # 计算这些特定列的总和
        # total_sum = df_joined_by_index.select([_sum(c) for c in sum_columns]).first()
        # df_joined_by_index.show()
        # # 提取总和值
        # total_sum_value = sum(total_sum)
        return df_joined_by_index


from pyspark.sql import SparkSession
from pyspark.sql import Row

# 初始化 SparkSession
spark = SparkSession.builder.appName("EditPenaltyTest").getOrCreate()

# 测试数据
data = [
    Row(index=1, a='New Yorks', b='NY'),
    Row(index=2, a='New York', b='NY'),
    Row(index=3, a='San Francisco', b='SF'),
    Row(index=4, a='San Francisco', b='SF'),
    Row(index=5, a='San Jose', b='SJ'),
    Row(index=6, a='New York', b='NY'),
    Row(index=7, a='San Francisco', b='SFO'),
    Row(index=8, a='Berkeley City', b='Bk'),
    Row(index=9, a='San Mateo', b='SMO'),
    Row(index=10, a='Albany', b='AB'),
    Row(index=11, a='San Mateo', b='SM')
]

# 创建 DataFrame
df = spark.createDataFrame(data)

# 相似度度量设置（示例）
similarity = {'a': 'edit', 'b': 'edit'}

# 初始化 EditPenalty 对象
editCostObj = EditPenalty(df, similarity)

# 获取 quality_func 方法
efn = editCostObj.quality_func
df = df.withColumn("a", col("a").substr(1, 4))
# 应用 quality_func 方法
editfn = efn(df)
data = [
    (10, 0.0),
    (8, 0.0),
    (2, 0.33333333333333337),
    (6, 0.33333333333333337),
    (1, 0.6666666666666667),
    (3, 0.33333333333333337),
    (4, 0.33333333333333337),
    (7, 0.6666666666666667),
    (5, 0.0),
    (11, 0.5),
    (9, 0.5)
]

# 创建 DataFrame
qfnEval = spark.createDataFrame(data, ["index", "qfn"])
df_joined_with_qfn = editfn.join(qfnEval, "index")
sum_columns = [F.col(c) for c in df_joined_with_qfn.columns if "_Equality" in c]
average_sum = sum(sum_columns) / len(sum_columns)
combined_with_qfn = df_joined_with_qfn.withColumn("combined", average_sum + F.col("qfn"))
final_average = combined_with_qfn.select(F.avg("combined")).first()[0]
print(final_average)
# 停止 SparkSession
spark.stop()
# qfn_column = qfnEval.select(qfnEval.columns[0]).withColumnRenamed(qfnEval.columns[0], "qfn_value")
#
# # 为确保行顺序相同，可以使用 zipWithIndex 方法，但在这里我们直接按行顺序合并
# df_joined_with_qfn = editfn.crossJoin(qfn_column)
#
# # 选取包含 "_Equality" 的列
# sum_columns = [F.col(c) for c in df_joined_with_qfn.columns if "_Equality" in c]
#
# # 计算这些列的和并除以列的数量
# average_sum = sum(sum_columns) / len(sum_columns)
#
# # 将得到的结果与 qfn 列相加
# combined_with_qfn = df_joined_with_qfn.withColumn("combined", average_sum + F.col("qfn_value"))
#
# # 计算最终结果列的平均值
# final_average = combined_with_qfn.select(F.avg("combined")).first()[0]
# # 显示结果
# # print(editfn)
# final_average.show()
# # 停止 SparkSession
# spark.stop()
