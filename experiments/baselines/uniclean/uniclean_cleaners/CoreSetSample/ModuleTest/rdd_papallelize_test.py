from pyspark import SparkConf, SparkContext

conf = SparkConf().setMaster("local[*]").setAppName("test_spark")

sc = SparkContext(conf=conf)

# 通过parallelize方法将python对象加载到是【ark内，成为RDD对象

rdd1 = sc.parallelize([1, 2, 3, 4, 5])
rdd2 = sc.parallelize((1, 2, 3, 4, 5))
rdd2 = sc.parallelize("dhskj")
rdd4 = sc.parallelize({1, 2, 3, 4, 5})
rdd5 = sc.parallelize({"key1": "value1", "key2": "value2"})

# 如果需要查看RDD里面有什么内容，需要collect()方法
print(rdd1.collect())
print(rdd2.collect())
print(rdd4.collect())
print(rdd5.collect())

# 读取文件转RDD对象,数据输入spark，就会成为rdd对象。

rdd = sc.textFile("D:/hello.txt")
print(rdd.collect())

sc.stop()
