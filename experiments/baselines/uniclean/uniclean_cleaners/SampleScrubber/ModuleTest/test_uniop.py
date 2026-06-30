import datetime
import logging

import pandas as pd


def formatString(s):
    return "'" + s + "'"


class Language(object):
    """
    算子类，定义可以在数据帧上执行的操作。
    操作定义一个单子（monoid）。
    """

    def __init__(self, runfn, depth=1, provenance=[]):
        self.runfn = lambda df: runfn(df)  # df表示数据帧
        self.depth = depth  # 深度
        self.reward = 0
        self.provenance = provenance if provenance != [] else []

    def set_reward(self, r):
        self.reward = r

    def run(self, df):
        op_start_time = datetime.datetime.now()  # 记录操作开始时间

        df_copy = df.copy(deep=True)
        result = self.runfn(df_copy)

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


class Swap(ParametrizedLanguage):
    paramDescriptor = {'column': ParametrizedLanguage.COLUMN,
                       'predicate': ParametrizedLanguage.PREDICATE,
                       'value': ParametrizedLanguage.VALUE,
                       'costfn': ParametrizedLanguage.COSTFN}

    def __init__(self, column, predicate, value, costfn):
        logical_predicate = lambda row: (row[predicate[0]] in predicate[1]) and (
                    tuple(row.dropna().values) in predicate[2])

        self.column = column
        self.predicate = predicate
        self.value = value
        self.costfn = costfn

        def fn(df, column=column, predicate=logical_predicate, v=value):
            def __internal(row):
                if predicate(row):
                    return v
                else:
                    return row[column]

            df[column] = df.apply(lambda row: __internal(row), axis=1)
            return df

        self.name = 'df = swap(df,' + formatString(column) + ',' + formatString(value) + ',' + str(
            predicate[0:2]) + ',' + str(costfn) + ')'
        self.provenance = [self]
        super(Swap, self).__init__(fn, ['column', 'predicate', 'value', 'costfn'])


# 使用示例
data = {
    'a': ['San Francisco', 'New Yorks', 'San Mateo', 'Other City'],
    'b': ['SFO', 'NY', 'SM', 'Other Code']
}
df = pd.DataFrame(data)
print(df)
arg = {'column': 'b',
       'predicate': ('b', {'SFO'},
                     {('San Francisco', 'SFO'), ('New Yorks', 'NY'), ('New York', 'NY'), ('San Francisco', 'SF'),
                      ('San Mateo', 'SM'), ('San Mateo', 'SMO')}),
       'value': 'SJ',
       'costfn': "(源属性: ['a'], 目标属性: ['b'] 并集 源属性: ['b'], 目标属性: ['a'])"}

swap_operation = Swap(**arg)
result_df = swap_operation.run(df)

print(result_df)
