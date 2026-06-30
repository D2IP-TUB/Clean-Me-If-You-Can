import datetime
import logging
from pyspark.sql.functions import udf, col
from pyspark.sql.types import StringType, IntegerType, StructField, StructType


def formatString(s):
    return "'" + s + "'"


class Language(object):
    def __init__(self, runfn, provenance=[]):
        self.runfn = lambda df: runfn(df)#运行操作
        self.reward = 0#视为操作的成本
        self.provenance = provenance if provenance != [] else []#记录自己的信息

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
        new_op = Language(new_runfn, self.provenance + other.provenance)
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


class ParametrizedLanguage(Language):#规则的参数
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
class Swap(ParametrizedLanguage):#spark 上测试的 swap 规则，支持用于 一个属性定位
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
            locate_index = df.columns.index(predicate[0])
            column_index = df.columns.index(column)
            index_column_index = df.columns.index("index")

            def __internal(*row):
                # 使用索引访问列值
                if row[locate_index] == predicate[1] and row[index_column_index] in predicate[2]:
                    return v
                else:
                    return row[column_index]

            internal_udf = udf(__internal, StringType())
            return df.withColumn(column, internal_udf(*[col(c) for c in df.columns]))

        self.name = 'df = swap(df,' + formatString(column) + ',' + formatString(value) + ',' + str(
            predicate[0:3]) + ',' + str(costfn) + ')'
        self.provenance = [self]
        super(Swap, self).__init__(fn, ['column', 'predicate', 'value', 'costfn'])


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
            # index_column_index = df.columns.index("index")

            def __internal(*row):
                # 使用索引访问列值
                if tuple(row[i] for i in locate_list) in predicate[1]:
                    return v
                else:
                    return row[column_index]
            def __internal2(*row):
                # 使用索引访问列值

                if tuple(row[i] for i in locate_list) in predicate[1]:
                    if row[column_index] != v:
                        return 1
                    else:
                        return 2
                else:
                    return 0
            internal_udf = udf(__internal, StringType())
            df=df.withColumn(column, internal_udf(*[col(c) for c in df.columns]))
            internal_udf2 = udf(__internal2, IntegerType())
            df=df.withColumn('clean', internal_udf2(*[col(c) for c in df.columns]))
            return df

        self.name = 'df = Uniop(df,' + formatString(column) + ',' + formatString(value) + ',' + str(
            predicate[0:]) + ',' + str(costfn) + ')'
        self.provenance = [self]
        super(Uniop, self).__init__(fn, ['column', 'predicate', 'value', 'costfn'])
# class Uniop(ParametrizedLanguage):
#     paramDescriptor = {'column': ParametrizedLanguage.COLUMN,
#                        'predicate': ParametrizedLanguage.PREDICATE,
#                        'value': ParametrizedLanguage.VALUE,
#                        'costfn': ParametrizedLanguage.COSTFN}
#
#     def __init__(self, column, predicate, value, costfn):
#         self.column = column
#         self.predicate = predicate
#         self.value = value
#         self.costfn = costfn
#
#         def fn(df, column=column, predicate=predicate, v=value):
#             # 获取列索引
#             locate_list = []
#             for attr in predicate[0]:
#                 locate_list.append(df.columns.index(attr))
#             column_index = df.columns.index(column)
#
#             def __internal(*row):
#                 if tuple(row[i] for i in locate_list) in predicate[1]:
#                     if row[column_index]!=v:
#                         return v, 1
#                     else:
#                         return row[column_index], 0
#                 else:
#                     return row[column_index], 0
#
#             schema = StructType([
#                 StructField(column, StringType(), True),
#                 StructField('clean', IntegerType(), True)
#             ])
#             internal_udf = udf(__internal, schema)
#
#             df = df.withColumn("temp", internal_udf(*[col(c) for c in df.columns]))
#             df = df.withColumn(column, col("temp." + column)).withColumn("clean", col("temp.clean"))
#             df = df.drop("temp")
#             return df
#
#         self.name = 'df = Uniop(df,' + formatString(column) + ',' + formatString(value) + ',' + str(
#             predicate[0:]) + ',' + str(costfn) + ')'
#         self.provenance = [self]
#         super(Uniop, self).__init__(fn, ['column', 'predicate', 'value', 'costfn'])
class NOOP(Language):
    """
    无操作算子。
    """

    def __init__(self):
        def fn(df):
            return df

        self.name = "NOOP"
        self.provenance = [self]
        self.predicate = None
        super(NOOP, self).__init__(fn)
