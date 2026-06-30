# 使用示例
from pyspark.sql import SparkSession

from AnalyticsCache.ModuleTest.handleSparkRule import transformRules, applyRules
from SampleScrubber.cleaner_model import Uniop

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

dfspark = spark.createDataFrame(data, ["index", "city", "airport_code", "country", "region"])


# 将 PySpark 数据框转换为 Pandas 数据框
df_pandas = dfspark.toPandas()

# 查看 Pandas 数据框
print(df_pandas)

arg = {'domain': 'airport_code',
       'predicate':(['country','region'], {('USA','West Coast',),('UK','Europe',)}, {1,2,3,4}),
       'repairvalue': '-----repair-----',
       'opinformation': "Some cost function"}

uniop_operation = Uniop(**arg)
result_df = uniop_operation.run(df_pandas)

print(result_df)

# 显示带索引的 DataFrame
dfspark.show()
sparkRule=transformRules([uniop_operation])
data=applyRules(sparkRule,dfspark)
data.show()