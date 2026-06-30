from pyspark.sql import Row
from pyspark.sql import SparkSession
from pyspark.sql.functions import monotonically_increasing_id

from SampleScrubber.ModuleTest.SparkClean.function_dependency import OneToOne
from SampleScrubber.ModuleTest.SparkClean.selector import solve, DEFAULT_SOLVER_CONFIG

# os.environ['PYSPARK_PYTHON'] = "/Users/qianzekai/anaconda3/envs/sparkmini/bin/python"  # 放Python的位置
# 初始化 Spark 会话
spark = SparkSession.builder \
    .appName("City Abbreviation Cleaning") \
    .getOrCreate()

# 准备数据
data = [
    {'a': 'New Yorks', 'b': 'NY'},  # 脏元组
    {'a': 'New York', 'b': 'NY'},
    {'a': 'San Francisco', 'b': 'SF'},
    {'a': 'San Francisco', 'b': 'SF'},
    {'a': 'San Jose', 'b': 'SJ'},
    {'a': 'New York', 'b': 'NY'},
    {'a': 'San Francisco', 'b': 'SFO'},  # 脏元组
    {'a': 'Berkeley City', 'b': 'Bk'},
    {'a': 'San Mateo', 'b': 'SMO'},
    {'a': 'Albany', 'b': 'AB'},
    {'a': 'San Mateo', 'b': 'SM'},  # 脏元组
    {'a': 'Santa Monica', 'b': 'SM'},
    {'a': 'Santa Monica', 'b': 'SM'}
]

# 使用 Row 类将字典转换为 DataFrame 行
rows = [Row(**record) for record in data]

# 创建 DataFrame
df_spark = spark.createDataFrame(rows)
df_spark = df_spark.withColumn("index", monotonically_increasing_id())
# 显示 DataFrame
# df_spark.show()
# 剩下的部分保持不变，因为您已经将相关的方法转换为与Spark兼容

constraint1 = OneToOne(["a"], ["b"])  # 一对一约束

config = DEFAULT_SOLVER_CONFIG
config['dependency']['depth'] = 3
config['dependency']['similarity'] = {'a': 'edit'}

dcprogram, output, _ = solve(df_spark, dependencies=[constraint1], config=config)

# 输出结果
print(dcprogram)
# print(CoreSetOutput)
# CoreSetOutput=spark.createDataFrame(CoreSetOutput)
output.show()  # 使用Spark的show方法打印DataFrame
