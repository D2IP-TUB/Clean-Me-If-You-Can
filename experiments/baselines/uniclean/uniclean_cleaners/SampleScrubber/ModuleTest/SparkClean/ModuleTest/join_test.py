# 假设 df1 和 df2 是你的两个数据集

from pyspark.sql import SparkSession
from pyspark.sql.functions import monotonically_increasing_id, col, udf
from pyspark.sql.types import IntegerType

# os.environ['PYSPARK_PYTHON'] = "D:\python37\python.exe"  # 放Python的位置
spark = SparkSession.builder.appName("EditDistanceExample").getOrCreate()
df1 = spark.createDataFrame([("Alic", 1), ("Bob", 2)], ["name", "value"])
df2 = spark.createDataFrame([("Alice", "F"), ("Bb", "M")], ["name", "gender"])
# 为每个 DataFrame 添加一个行索引
df1_with_index = df1.withColumn("index", monotonically_increasing_id())
df2_with_index = df2.withColumn("index", monotonically_increasing_id())
df1_selected = df1_with_index.select("index", col("name").alias("name_source"))
df2_selected = df2_with_index.select("index", col("name").alias("name_target"))
# 基于索引合并 DataFrame
df_joined_by_index = df1_selected.join(df2_selected, "index")

df_joined_by_index.show()


def edit_distance(str1, str2):
    if str1 is None or str2 is None:
        return None
    return Levenshtein.distance(str1, str2)


edit_distance_udf = udf(edit_distance, IntegerType())

# # 应用 UDF 来计算编辑距离，并创建一个新列
# df_with_distance = df2_with_index.withColumn("EditDistance", edit_distance_udf(df_joined_by_index.col("name_source"), df_joined_by_index.col("name_target")))
# 应用 UDF 来计算编辑距离，并创建一个新列
df_joined_with_distance = df_joined_by_index.withColumn("EditDistance",
                                                        edit_distance_udf(col("name_source"), col("name_target")))
# 显示结果
# df_joined_with_distance.show()

# 将编辑距离结果合并回 df2_with_index
df_with_distance = df2_with_index.join(df_joined_with_distance.select("index", "EditDistance"), on="index", how="left")

# 显示结果
df_with_distance.show()

# 停止 SparkSession
spark.stop()
