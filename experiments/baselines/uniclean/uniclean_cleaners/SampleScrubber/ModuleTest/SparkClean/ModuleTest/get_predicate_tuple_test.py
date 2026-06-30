import numpy as np
from pyspark.sql import functions as F

from SampleScrubber.ModuleTest.SparkClean.spark_rule_model import Swap


def getPredicatesDeterministic1(self, qfn, col, granularity=None):
    # 计算质量函数 qfn 在数据集上的预测
    q_array = qfn(self.df)

    vals_inside = set()  # 存储可能错误的值
    # vals_outside = set()  # 存储对的的值
    tuples_inside = set()  # 存储可能错误元组

    for i in range(self.df.shape[0]):
        val = self.df[col].iloc[i]

        if val != val:  # 处理NaN值
            val = 'NaN'

        if q_array[i] > 0.0:
            vals_inside.add(val)
            tuples_inside.add(tuple(self.df.iloc[i].dropna()))

    def _translateNaN(x):
        if x == 'NaN' or x != x:
            return np.nan
        else:
            return x

    # print(tuples_inside)
    return [(col, set([_translateNaN(p)]), tuples_inside) for p in vals_inside]


def getPredicatesDeterministic2(df, qfn, col, granularity=None):
    # 计算质量函数 qfn 在数据集上的预测
    qfn_df = qfn.withColumnRenamed("qfn_column", "qfn")

    # 创建一个新的 DataFrame，包含原始数据和 qfn 的预测值
    combined_df = df.join(qfn_df, "index")  # 假设 'index' 是用于对齐的列

    # # 替换 NaN 值为字符串 'NaN'
    combined_df = combined_df.withColumn(col, F.when(F.col(col).isNull(), F.lit('NaN')).otherwise(F.col(col)))

    # 收集可能出错的值和元组
    vals_inside_df = combined_df.filter(F.col("qfn") > 0.0).select(col)
    tuples_inside_df = combined_df.filter(F.col("qfn") > 0.0).drop("qfn", 'index')
    tuples_inside_df.show()
    # 收集为0的值
    # vals_outside_df = combined_df.filter(F.col("qfn") == 0.0).select(col)

    # 转换为 Python 集合
    vals_inside = set(vals_inside_df.rdd.flatMap(lambda x: x).collect())
    tuples_inside = set(tuples_inside_df.rdd.flatMap(lambda x: tuple(x)).collect())
    print(tuples_inside)

    # vals_outside = set(vals_outside_df.rdd.flatMap(lambda x: x).collect())
    # 处理 NaN 值
    def _translateNaN(x):
        return np.nan if x == 'NaN' else x

    predicates = [(col, {_translateNaN(val)}, tuples_inside) for val in vals_inside]

    return predicates


def getPredicatesDeterministic(df, qfn, col, granularity=None):
    # 计算质量函数 qfn 在数据集上的预测
    qfn_df = qfn.withColumnRenamed("qfn_column", "qfn")

    # 创建一个新的 DataFrame，包含原始数据和 qfn 的预测值
    combined_df = df.join(qfn_df, "index")  # 假设 'index' 是用于对齐的列

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

    predicates = [(col, {_translateNaN(val)}, indexes_inside) for val in vals_inside]
    return predicates


from pyspark.sql import SparkSession
from pyspark.sql import Row

# os.environ['PYSPARK_PYTHON'] = "D:\python37\python.exe"  # 放Python的位置
# 初始化 SparkSession
spark = SparkSession.builder.appName("example").getOrCreate()

# 创建数据列表
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
# 测试数据
data2 = [
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
df = spark.createDataFrame(data2)
predicates = getPredicatesDeterministic(df, qfnEval, 'a')
print(predicates)
swap_operation = Swap(column='a',
                       predicate=predicates[0],
                       value='aaaaaaa',
                       costfn="Some cost function")

result_df = swap_operation.run(df)
df.show()
# 展示 DataFrame
result_df.show()
