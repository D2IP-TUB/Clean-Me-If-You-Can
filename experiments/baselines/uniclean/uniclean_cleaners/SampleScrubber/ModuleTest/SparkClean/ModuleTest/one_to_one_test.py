import os

from pyspark.sql import Row
from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F


# udf
def max_by_column(df1, df2, index_column, column1, column2):
    df1 = df1.withColumnRenamed(column1, column1 + "_1")
    df2 = df2.withColumnRenamed(column2, column2 + "_2")
    combined_df = df1.join(df2, index_column)
    # combined_df.show()
    result_df = combined_df.withColumn("qfn", F.when(F.col(column1 + "_1") > F.col(column2 + "_2"),
                                                     F.col(column1 + "_1")).otherwise(F.col(column2 + "_2")))
    return result_df.select(index_column, "qfn")


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
        except:  # 比较
            dm = DataModel()
            dm.quality_func = lambda df: max_by_column(
                self.quality_func(df),
                other.quality_func(df),
                "index",  # 假设索引列名为 "index"
                "qfn",  # df1 中用于比较的列名
                "qfn"  # df2 中用于比较的列名
            )
            dm.domain = self.domain.union(other.domain)
            dm.domainParams = self.domainParams.copy()
            dm.domainParams.update(other.domainParams)
            try:
                dm.msg = self.msg
            except:
                pass
            return dm


class new_FunctionalDependency(DataModel):
    """FunctionalDependency 表示两组属性之间的功能依赖关系。功能依赖关系 (A -> B) 意味着对于每个 B 值，存在一个单独的 A 值。
    """

    def __init__(self, source, target):
        """FunctionalDependency 构造函数

        source -- 一个属性名称列表
        target -- 一个属性名称列表
        """

        self.source = source
        self.target = target

        self.domain = set(source + target)
        self.domainParams = {}

    def __str__(self):
        return '(源属性: %s, 目标属性: %s)' % (self.source, self.target)

    def __add__(self, other):
        """__mul__ 按位与运算两个质量函数 """
        if isinstance(self, new_FunctionalDependency):
            self.msg = '(源属性: %s, 目标属性: %s 并集 源属性: %s, 目标属性: %s)' % (
                self.source, self.target, other.source,
                other.target)
        return super(new_FunctionalDependency, self).__add__(other);

    def __mul__(self, other):
        """__mul__ 按位与运算两个质量函数 """
        if isinstance(self, new_FunctionalDependency):
            self.msg = '(源属性: %s, 目标属性: %s 并集 源属性: %s, 目标属性: %s)' % (
                self.source, self.target, other.source,
                other.target)
        return super(new_FunctionalDependency, self).__mul__(other);

    def _quality_func(self, df):
        df = df.withColumn("source_compound", F.struct(*self.source))
        df = df.withColumn("target_compound", F.struct(*self.target))
        # 这里，`source_compound` 和 `target_compound` 将作为新列，每一列都包含了相应属性集合的复合结构。
        windowSpec = Window.partitionBy("source_compound")
        df = df.withColumn("total_targets", F.count("target_compound").over(windowSpec))

        # 使用窗口函数，基于复合列计算每个 `source_compound` 对应的不同 `target_compound` 的数量。
        df = df.withColumn("target_count",
                           F.count("target_compound").over(Window.partitionBy("source_compound", "target_compound")))
        df = df.withColumn("qfn", F.lit(1) - ((F.col("target_count")) / F.col("total_targets")))
        result_df = df.select("qfn", "index")
        df.show()
        total_onetooneqfn = result_df.agg(F.sum("qfn")).first()[0]
        return result_df


def OneToOne(source, target):
    """一个OneToOne依赖是常见的FD对，这是语法糖让结构更明确
    """
    return new_FunctionalDependency(source, target) * new_FunctionalDependency(target, source)  # 双向映射，同时乘法使得它们的类型变了


# 初始化 SparkSession
spark = SparkSession.builder.appName("OneToOneTest").getOrCreate()
os.environ['PYSPARK_PYTHON'] = "D:\python38\python.exe"  # 放Python的位置
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
constraint1 = OneToOne(["a"], ["b"])  # 一对一约束
costEval = constraint1.quality_func(df)
# 获取 quality_func 方法
# efn = editCostObj.quality_func
# df = df.withColumn("a", col("a").substr(1, 4))
# # 应用 quality_func 方法
# editfn = efn(df)

# 显示结果
costEval.show()

# 停止 SparkSession
spark.stop()
