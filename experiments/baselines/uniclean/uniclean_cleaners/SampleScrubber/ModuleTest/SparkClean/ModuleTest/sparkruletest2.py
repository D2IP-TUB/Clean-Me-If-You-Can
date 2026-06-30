from pyspark.sql import SparkSession
from pyspark.sql.functions import udf, col, monotonically_increasing_id, lit
from pyspark.sql.types import StringType, IntegerType, StructType, StructField

# 初始化 SparkSession
spark = SparkSession.builder \
    .appName("DemoApp") \
    .config("spark.driver.memory", "4g") \
    .config("spark.executor.memory", "4g") \
    .getOrCreate()

# 创建示例 DataFrame
data = spark.createDataFrame(
    [
        ("val1", "val2", "original"),
        ("val1", "other", "original"),
        ("foo", "bar", "original"),
    ],
    ["col1", "col2", "column_name"]
)

# 添加数据行的索引并初始化 clean 列
data = data.withColumn("index", monotonically_increasing_id())
data = data.withColumn("clean", lit(0))

# 显示原始数据
print("Original Data:")
data.show()

class Language(object):
    def __init__(self, runfn, provenance=[]):
        self.runfn = lambda df: runfn(df)
        self.reward = 0
        self.provenance = provenance if provenance != [] else []

    def set_reward(self, r):
        self.reward = r

    def run(self, df):
        result = self.runfn(df)
        return result

    def __mul__(self, other):
        new_runfn = lambda df, a=self, b=other: b.runfn(a.runfn(df))
        new_op = Language(new_runfn, self.provenance + other.provenance)
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
            locate_list = []
            for attr in predicate[0]:
                locate_list.append(df.columns.index(attr))
            column_index = df.columns.index(column)

            def __internal(*row):
                if tuple(row[i] for i in locate_list) in predicate[1]:
                    return (v, 1)
                else:
                    return (row[column_index], 0)

            schema = StructType([
                StructField(column, StringType(), True),
                StructField('clean', IntegerType(), True)
            ])
            internal_udf = udf(__internal, schema)

            new_df = df.withColumn("temp", internal_udf(*[col(c) for c in df.columns]))
            new_df = new_df.withColumn(column, col("temp." + column)).withColumn("clean", col("temp.clean"))
            new_df = new_df.drop("temp")
            return new_df

        self.name = 'df = Uniop(df,' + formatString(column) + ',' + formatString(value) + ',' + str(
            predicate[0:]) + ',' + str(costfn) + ')'
        self.provenance = [self]
        super(Uniop, self).__init__(fn, ['column', 'predicate', 'value', 'costfn'])

# 运行规则的函数
def run_rules(data, rules):
    for rule in rules:
        data = rule.run(data)
    return data

def formatString(s):
    return '"' + str(s) + '"'

# 定义规则列表并运行
rules = [Uniop('column_name', (['col1', 'col2'], {('val1', 'val2')}), 'new_value', 'cost_function')]

# 更新数据
updated_data = run_rules(data, rules)

# 显示更新后的数据
print("Updated Data:")
updated_data.show()

# 过滤出 clean 列值为 1 的那些行
cleaned_rows_df = updated_data.filter(updated_data.clean == 1)

# 显示清理后的行
print("Cleaned Rows:")
cleaned_rows_df.show()