import distance
from pyspark.sql import SparkSession
from pyspark.sql.functions import udf, col
from pyspark.sql.types import DoubleType

# 初始化 SparkSession
spark = SparkSession.builder.appName("EditDistanceExample").getOrCreate()


# 定义编辑距离的 UDF
def edit_distance(str1, str2):
    if str1 is None or str2 is None:
        return 1.0
    return float(distance.levenshtein(str1, str2))


edit_distance_udf = udf(edit_distance, DoubleType())

# 创建一个包含两列的 DataFrame
data = [("John", "Jon"), ("Smith", "Smyth"), ("Kate", "Cate")]
columns = ["Name1", "Name2"]
df = spark.createDataFrame(data, columns)

# 应用 UDF 来计算编辑距离，并创建一个新列
df_with_distance = df.withColumn("EditDistance", edit_distance_udf(col("Name1"), col("Name2")))

# 显示结果
df_with_distance.show()

# 停止 SparkSession
spark.stop()
