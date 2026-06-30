# 这个是一键端的启动脚本
import os
import shutil
import time
from functools import reduce

import pandas as pd
from pyspark import StorageLevel
from pyspark.sql import SparkSession
from pyspark.sql.functions import monotonically_increasing_id, lit

import logsetting
from AnalyticsCache.getScore import calculate_accuracy_and_recall
from Clean import CleanonLocal
from SampleScrubber.cleaner.multiple import AttrRelation
from SampleScrubber.cleaner.single import Pattern

cleanners = [
    Pattern('gender', "[M|F]", '1'),
    Pattern('areacode', "[0-9]{3}", '2'),
    Pattern('state', "[A-Z]{2}", '3'),
    AttrRelation(['zip'], ["state"], '4'),
    AttrRelation(['areacode'], ["state"], '5'),
    AttrRelation(["zip"], ["city"], '6'),
    AttrRelation(["fname", "lname"], ["gender"], '7')
]
file_load = 'TestDataset/result/tax100w/Tax100w_dirty_data.csv'
save_path = 'TestDataset/result'
table_name = 'Tax100w'
clean_path='TestDataset/result/tax100w/tax_1000k_clean.csv'
# 指定比对的属性集合
attributes = ['city', 'state', 'areacode', 'zip']
# 以上为输入部分


if __name__ == '__main__':

    spark = SparkSession.builder \
        .appName("MyApp") \
        .config("spark.executor.memory", "8g") \
        .config("spark.driver.memory", "8g") \
        .config("spark.executor.memoryOverhead", "8g") \
        .config("spark.sql.shuffle.partitions", "200") \
        .getOrCreate()
    # spark = SparkSession.builder.appName(" CleanSession").getOrCreate()
    print("Logs saved in " + logsetting.logfilename)
    data = spark.read.csv(file_load, header=True, inferSchema=True)
    # print(data.count())
    # # 生成一个包含五个相同 DataFrame 的列表
    # dataframes = [data] * scale_factor
    #
    #
    # def union_all(df1, df2):
    #     return df1.unionAll(df2)
    #
    #
    # # 使用 reduce 高效地合并所有 DataFrame
    # data = reduce(union_all, dataframes)
    # 添加数据行的索引
    # data = data.withColumn("index", monotonically_increasing_id())
    # data = data.withColumn("clean", lit(0))
    # data=data.filter(data.zip == '83465')
    # 使用 time.time() 计时
    # data.filter(data.zip == '83465').show()
    elapsed_time = 0;
    get_rules = True
    while get_rules:
        start_time = time.perf_counter()
        get_rules, data = CleanonLocal(cleanners, data, table_name)
        end_time = time.perf_counter()
        elapsed_time += end_time - start_time
        print(f"当前清洗总执行时间: {elapsed_time:.4f} 秒")

    print("没有发现新的规则，保存清洗结果，写入数据大小: " + str(data.count()))
    # 最终保存 DataFrame 为 CSV 文件
    data.coalesce(1).write.mode('overwrite').csv(table_name+'Clean', header=True)

    # 找到保存的 CSV 文件
    saved_file = None
    for file in os.listdir(table_name+'Clean'):
        if file.endswith('.csv'):
            saved_file = os.path.join(table_name+'Clean', file)
            break
    save_path=save_path+'/'+table_name
    target_file = os.path.join(save_path, table_name+'Clean.csv')
    # 确保目标目录存在
    os.makedirs(save_path, exist_ok=True)

    # 移动并重命名文件
    if saved_file:
        shutil.move(saved_file, target_file)
    else:
        print("未找到保存的 CSV 文件。")

    print(f"验证清洗性能:")
    # 读取CSV文件，并设置index列
    clean_data = pd.read_csv(clean_path, index_col='index')
    dirty_data = pd.read_csv(file_load, index_col='index')
    cleaned_data = pd.read_csv(target_file, index_col='index')

    # 计算修复准确率和召回率
    accuracy, recall = calculate_accuracy_and_recall(clean_data, dirty_data, cleaned_data, attributes)

    print(f"修复准确率: {accuracy}")
    print(f"修复召回率: {recall}")
    # 停止 Spark 会话
    spark.stop()
