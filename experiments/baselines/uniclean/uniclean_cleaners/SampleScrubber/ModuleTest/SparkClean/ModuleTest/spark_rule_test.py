import datetime
import logging

from pyspark.sql import SparkSession
from pyspark.sql.functions import udf, col
from pyspark.sql.types import StringType


def formatString(s):
    return "'" + s + "'"


class Language(object):
    def __init__(self, runfn, depth=1, provenance=[]):
        self.runfn = lambda df: runfn(df)
        self.depth = depth
        self.reward = 0
        self.provenance = provenance if provenance != [] else []

    def set_reward(self, r):
        self.reward = r

    def run(self, df):
        op_start_time = datetime.datetime.now()
        result = self.runfn(df)
        logging.debug(
            'Running ' + self.name + ' took ' + str((datetime.datetime.now() - op_start_time).total_seconds()))
        return result

    def __mul__(self, other):
        new_runfn = lambda df, a=self, b=other: b.runfn(a.runfn(df))
        new_op = Language(new_runfn, self.depth + other.depth, self.provenance + other.provenance)
        new_op.name = (self.name + "\n" + other.name).strip()
        new_op.reward = self.reward + other.reward
        return new_op

    def __pow__(self, b):
        op = self
        for i in range(b):
            op *= self
        return op

    def __str__(self):
        return self.name

    __repr__ = __str__


class ParametrizedLanguage(Language):
    COLUMN = 0
    VALUE = 1
    SUBSTR = 2
    PREDICATE = 3
    COLUMNS = 4
    COSTFN = 5

    def __init__(self, runfn, params):

        self.validateParams(params)
        super(ParametrizedLanguage, self).__init__(runfn)

    def validateParams(self, params):
        try:
            self.paramDescriptor
        except:
            raise NotImplemented("Must define a parameter descriptor")

        for p in params:
            if p not in self.paramDescriptor:
                raise ValueError("Parameter " + str(p) + " not defined")

            if self.paramDescriptor[p] not in range(6):
                raise ValueError("Parameter " + str(p) + " has an invalid descriptor")


class Uniop(ParametrizedLanguage):
    paramDescriptor = {'column': ParametrizedLanguage.COLUMN,
                       'predicate': ParametrizedLanguage.PREDICATE,
                       'value': ParametrizedLanguage.VALUE,
                       'costfn': ParametrizedLanguage.COSTFN}

    def __init__(self, column, predicate, value, costfn):
        self.column = column
        self.predicate = predicate
        self.value = value
        self.costfn = costfn

        def fn(df, column=column, predicate=predicate, v=value):
            # 获取列索引
            locate_list=[]
            for attr in (predicate[0]):
                locate_list.append(df.columns.index(attr))
            column_index = df.columns.index(column)
            index_column_index = df.columns.index("index")

            def __internal(*row):
                # 使用索引访问列值
                if tuple(row[i] for i in locate_list) in predicate[1]:
                    return v
                else:
                    return row[column_index]

            internal_udf = udf(__internal, StringType())
            return df.withColumn(column, internal_udf(*[col(c) for c in df.columns]))

        self.name = 'df = Uniop(df,' + formatString(column) + ',' + formatString(value) + ',' + str(
            predicate[0:]) + ',' + str(costfn) + ')'
        self.provenance = [self]
        super(Uniop, self).__init__(fn, ['column', 'predicate', 'value', 'costfn'])


# 使用示例
spark = SparkSession.builder.appName("Example").getOrCreate()
data = [
    (1, "San Francisco", "SFO", "USA", "West Coast"),
    (2, "New York", "JFK", "USA", "East Coast"),
    (3, "London", "LHR", "UK", "Europe"),
    (4, "Los Angeles", "LAX", "USA", "West Coast"),
    (5, "Paris", "CDG", "France", "Europe"),
    (6, "Miami", "MIA", "USA", "East Coast"),
    (7, "Tokyo", "HND", "Japan", "Asia"),
    (8, "San Jose", "SJC", "USA", "West Coast")
]

df = spark.createDataFrame(data, ["index", "city", "airport_code", "country", "region"])
# 给原始 DataFrame 添加索引列
# df_with_index = df.withColumn("index", monotonically_increasing_id())

# 显示带索引的 DataFrame
df.show()
predicate = (['country','region'], {('USA','West Coast',),('UK','Europe',)})


uniop = Uniop(column='airport_code',
                      predicate=predicate,
                      value='-----repair-----',
                      costfn="Some cost function")
print(uniop)
df = uniop.run(df)
df.show()
