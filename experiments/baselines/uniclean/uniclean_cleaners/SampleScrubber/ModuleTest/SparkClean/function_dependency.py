"""
这个模块描述了表示各种多属性关联的约束的类。
"""
from pyspark.sql import Window
from pyspark.sql import functions as F

from SampleScrubber.ModuleTest.SparkClean.cleaner_model import CleanerModel


class FD(CleanerModel):
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
        if isinstance(self, FD):
            self.msg = '(源属性: %s, 目标属性: %s 并集 源属性: %s, 目标属性: %s)' % (
                self.source, self.target, other.source,
                other.target)
        return super(FD, self).__add__(other);

    def __mul__(self, other):
        """__mul__ 按位与运算两个质量函数 """
        if isinstance(self, FD):
            self.msg = '(源属性: %s, 目标属性: %s 并集 源属性: %s, 目标属性: %s)' % (
                self.source, self.target, other.source,
                other.target)
        return super(FD, self).__mul__(other);

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
        # df.show()
        total_onetooneqfn = result_df.agg(F.sum("qfn")).first()[0]
        return result_df


def OneToOne(source, target):
    """一个OneToOne依赖是常见的FD对，这是语法糖让结构更明确
    """
    return FD(source, target) * FD(target, source)  # 双向映射，同时乘法使得它们的类型变了
