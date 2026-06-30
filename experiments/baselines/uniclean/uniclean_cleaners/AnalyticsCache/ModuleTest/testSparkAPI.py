from pyspark.sql import SparkSession
from pyspark.sql.functions import col, when
from functools import reduce


class Uniop:
    def __init__(self, domain, predicate, repairvalue, opinformation):
        self.domain = domain
        self.predicate = predicate
        self.repairvalue = repairvalue
        self.opinformation = opinformation


def transformRulesToSpark(EditRuleList, df):
    """
    转换编辑规则列表并使用 Spark API 修改 DataFrame。

    参数：
    EditRuleList (list): 编辑规则列表。
    df (DataFrame): 要修改的 DataFrame。

    返回：
    DataFrame: 修改后的 DataFrame。
    """
    for EditRule in EditRuleList:
        column = EditRule.domain
        predicate_attrs = EditRule.predicate[0]
        value_sets = EditRule.predicate[1]
        repair_value = EditRule.repairvalue

        conditions = []
        for value_set in value_sets:
            sub_conditions = [col(attr) == val for attr, val in zip(predicate_attrs, value_set)]
            condition = reduce(lambda x, y: x & y, sub_conditions)
            conditions.append(condition)

        final_condition = reduce(lambda x, y: x | y, conditions)

        df = df.withColumn(column, when(final_condition, repair_value).otherwise(col(column)))

    return df


# 示例使用
if __name__ == "__main__":
    spark = SparkSession.builder.appName("Spark Edit Rules").getOrCreate()

    # 示例数据
    data = [("Alice", "USA", "West Coast", 10),
            ("Bob", "UK", "Europe", 20),
            ("Charlie", "USA", "East Coast", 30)]
    columns = ["name", "country", "region", "age"]
    df = spark.createDataFrame(data, columns)

    # 示例 Uniop 对象和规则列表
    arg = {'domain': 'age',
           'predicate': (['country', 'region'], {('USA', 'West Coast',), ('UK', 'Europe',)}, {1, 2, 3, 4}),
           'repairvalue': '-----repair-----',
           'opinformation': "Some cost function"}

    uniop_operation = Uniop(**arg)
    EditRuleList = [uniop_operation]

    # 应用规则
    modified_df = transformRulesToSpark(EditRuleList, df)
    modified_df.show()

    spark.stop()