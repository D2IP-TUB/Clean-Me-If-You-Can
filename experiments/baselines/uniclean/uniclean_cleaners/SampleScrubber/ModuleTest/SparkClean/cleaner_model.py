from pyspark.sql.functions import col
from pyspark.sql.functions import udf
from pyspark.sql.types import DoubleType
from SampleScrubber.ModuleTest.SparkClean.util.cleanudf import max_by_column, edit
import numpy as np
import pandas as pd
from pyspark.sql import functions as F



class CleanerModel(object):
    """一个约束的对象是将数据规则转换为质量函数的基本包装类。
    domain -- 属性集合
    """

    def __init__(self, domain=set()):

        self.domain = domain
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
        dm = CleanerModel()
        dm.quality_func = lambda df: (self.quality_func(df) + other.quality_func(df)) / 2  # 两个质量函数的平均值
        dm.domain = self.domain.union(other.domain)  # 两个质量函数的属性集合的并集
        dm.domainParams = self.domainParams.copy()
        dm.domainParams.update(other.domainParams)  # 合并other字典的参数
        return dm

    def __mul__(self, other):
        """__mul__ 两个质量函数的乘积或按位比较"""
        try:
            fother = float(other)  # other是质量评估的结果，可能是矩阵也可能是float
            dm = CleanerModel()  # c是一个约束对象
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
            dm = CleanerModel()
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


class EditPenalty(CleanerModel):
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
        # # 计算这些特定列的总和
        # total_sum = df_joined_by_index.select([_sum(c) for c in sum_columns]).first()
        # print(total_sum)
        # 提取总和值
        # total_sum_value = sum(total_sum)
        return df_joined_by_index


class Dataset:
    """
    数据集类，用于封装 cleaner 对 data 的操作
    """

    def __init__(self, df, provenance=-1):
        self.df = df
        # 推断数据框中各列的数据类型
        # self.types = getTypes(df, df.columns.values)
        self.featurizers = {}

    """
    内部函数，将函数 fn 映射到指定属性上，并创建一个新的数据集
    """

    def _map(self, fn, attr):
        newDf = pd.DataFrame.copy(self.df)
        rows, cols = self.df.shape

        j = newDf.columns.get_loc(attr)
        for i in range(rows):
            newDf.iloc[i, j] = fn(newDf.iloc[i, :])

        return Dataset(newDf, self.qfnList, self.provenance)

    def _sampleRow(self):
        newDf = pd.DataFrame.copy(self.df)
        rows, cols = self.df.shape
        i = np.random.choice(np.arange(0, rows))
        return newDf.iloc[i, :]

    """
    对所有属性执行修复函数列表 fnList，按随机顺序
    """

    def _allmap(self, fnList, attrList):
        dataset = self
        for i, f in enumerate(fnList):
            dataset = dataset._map(f, attrList[i])

        return dataset

    def getPredicatesDeterministic(self, qfn, col, granularity=None):
        # 计算质量函数 qfn 在数据集上的预测
        qfn_df = qfn(self.df).withColumnRenamed("qfn_column", "qfn")

        # 创建一个新的 DataFrame，包含原始数据和 qfn 的预测值
        combined_df = self.df.join(qfn_df, "index")  # 假设 'index' 是用于对齐的列

        # 替换 NaN 值为字符串 'NaN'
        combined_df = combined_df.withColumn(col, F.when(F.col(col).isNull(), F.lit('NaN')).otherwise(F.col(col)))

        # 收集可能出错的值和元组
        vals_inside_df = combined_df.filter(F.col("qfn") > 0.0).select(col)
        tuples_inside_df = combined_df.filter(F.col("qfn") > 0.0).select("index")  # 已保留 'index' 列

        # 收集 index 列的值
        indexes_inside = set(tuples_inside_df.rdd.flatMap(lambda x: x).collect())

        # 收集为0的值
        # vals_outside_df = combined_df.filter(F.col("qfn") == 0.0).select(col)

        # 转换为 Python 集合
        vals_inside = set(vals_inside_df.rdd.flatMap(lambda x: x).collect())

        # tuples_inside = set(tuples_inside_df.rdd.flatMap(lambda x: tuple(x)).collect())
        # vals_outside = set(vals_outside_df.rdd.flatMap(lambda x: x).collect())
        # 处理 NaN 值
        def _translateNaN(x):
            return np.nan if x == 'NaN' else x

        predicates = [(col, _translateNaN(val), indexes_inside) for val in vals_inside]
        return predicates
