from pyspark.sql import SparkSession

# 创建 Spark 会话
spark = SparkSession.builder \
    .appName("Spark SQL Example") \
    .getOrCreate()

# 读取 JSON 文件到 DataFrame
df = spark.read.json("people.json")

# 注册临时视图
df.createOrReplaceTempView("people")

# 执行 SQL 查询
result = spark.sql("SELECT name, age FROM people WHERE age > 21")

# 显示结果
result.show()

# 停止 Spark 会话
spark.stop()