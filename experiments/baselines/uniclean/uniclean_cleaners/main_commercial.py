# 这个是一键端的启动脚本

from Clean import CleanonLocal

import os
import shutil
import time

import pandas as pd
from pyspark.sql import SparkSession
from pyspark.sql.functions import monotonically_increasing_id, lit

from SampleScrubber.cleaner.multiple import AttrRelation

# 清洗规则
cleaners = [
    AttrRelation(['establishment_date'], ['establishment_time'], '1'),
    AttrRelation(['registered_capital'], ['registered_capital_scale'], '2'),
    AttrRelation(['enterprise_name'], ['industry_third'], '3'),
    AttrRelation(['enterprise_name'], ['industry_second'], '4'),
    AttrRelation(['enterprise_name'], ['industry_first'], '5'),
    AttrRelation(['industry_first'], ['industry_second'], '6'),
    AttrRelation(['industry_second'], ['industry_third'], '7'),
    AttrRelation(['annual_turnover'], ['annual_turnover_interval'], '8'),
    AttrRelation(['latitude', 'longitude'], ['province'], '9'),
    AttrRelation(['latitude', 'longitude'], ['city'], '10'),
    AttrRelation(['latitude', 'longitude'], ['district'], '11'),
    AttrRelation(['enterprise_address'], ['province'], '12'),
    AttrRelation(['enterprise_address'], ['city'], '13'),
    AttrRelation(['enterprise_address'], ['district'], '14'),
    AttrRelation(['enterprise_address'], ['latitude'], '15'),
    AttrRelation(['enterprise_address'], ['longitude'], '16'),
    AttrRelation(['province'], ['city'], '17'),
    AttrRelation(['city'], ['district'], '18'),
    AttrRelation(['enterprise_name'], ['enterprise_type'], '19'),
    AttrRelation(['enterprise_id'], ['enterprise_name'], '20'),
    AttrRelation(['social_credit_code'], ['enterprise_name'], '21')
]

# 本地的表名和文件路径
table_name = 'ai4data_enterprise_bak'
# clean_table_name = 'ai4data_enterprise_bak_anomaly_data_flag'
# dirty_table_name = 'ai4data_enterprise_bak_preH'
# data_name = table_name + '_100w'
# save_table_name = data_name + '_cleaned'
# 本地文件路径

file_load = 'TestDataset/dataOrderAddress.csv'
clean_path = 'TestDataset/dataOrderAddress.csv'
save_path = 'TestDataset/result/'

# 比对的属性集合
attributes = [
    'annual_turnover', 'annual_turnover_interval', 'city', 'district', 'enterprise_address',
    'enterprise_id', 'enterprise_name', 'enterprise_type', 'establishment_date',
    'establishment_time', 'industry_first', 'industry_second', 'industry_third',
    'latitude', 'longitude', 'province', 'registered_capital', 'registered_capital_scale',
    'social_credit_code'
]

# 自定义索引列名
index_name = 'enterprise_id'
single_max = 20000

if __name__ == '__main__':
    spark = SparkSession.builder \
        .appName("LocalDataCleaning") \
        .config("spark.executor.memory", "8g") \
        .config("spark.driver.memory", "8g") \
        .config("spark.executor.memoryOverhead", "8g") \
        .config("spark.sql.shuffle.partitions", "200") \
        .getOrCreate()

    # 加载本地文件数据
    data = spark.read.csv(file_load, header=True, inferSchema=True)

    # 添加数据行的索引
    if 'index' not in data.columns:
        data = data.withColumn("index", monotonically_increasing_id())

    # 持久化 DataFrame
    data.persist()

    elapsed_time = 0
    start_time = time.perf_counter()
    table_path = os.path.join(save_path, table_name)
    if not os.path.exists(table_path):
        os.makedirs(table_path)
    # 清洗数据
    data = CleanonLocal(spark, cleaners, data, table_path, single_max=single_max)

    end_time = time.perf_counter()
    elapsed_time += end_time - start_time
    print(f"清洗总执行时间: {elapsed_time:.4f} 秒")
    data.coalesce(1).write.mode('overwrite').csv(table_path + 'Cleaned', header=True)

    saved_file = None
    for file in os.listdir(table_path + 'Cleaned'):
        if file.endswith('.csv'):
            saved_file = os.path.join(table_path + 'Cleaned', file)
            break

    target_file = os.path.join(table_path, table_name + 'Cleaned.csv')
    os.makedirs(save_path, exist_ok=True)

    if saved_file:
        shutil.move(saved_file, target_file)
    else:
        print("未找到保存的 CSV 文件。")

    # # 保存清洗结果
    # print("完成清洗，保存清洗结果，写入数据大小: " + str(data.count()))
    # data = data.withColumn("cleaned", lit(True))

    # # 将结果保存到本地文件
    # data.coalesce(1).write.mode('overwrite').csv(os.path.join(save_path, save_table_name), header=True)
    #
    # # 性能验证
    # print("验证清洗性能:")
    # clean_data = pd.read_csv(clean_data_path, index_col=index_name)
    # dirty_data = pd.read_csv(dirty_data_path, index_col=index_name)
    # cleaned_data = pd.read_csv(os.path.join(save_path, save_table_name, 'part-*.csv'), index_col=index_name)
    #
    # accuracy, recall = calculate_accuracy_and_recall_spark(clean_data, dirty_data, cleaned_data, attributes, index_name)
    #
    # print(f"修复准确率: {accuracy}")
    # print(f"修复召回率: {recall}")

    spark.stop()