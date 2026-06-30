import os
import shutil
import sys
import time

import argparse
import pandas as pd
from pyspark.sql import SparkSession
from pyspark.sql.functions import monotonically_increasing_id

import logsetting
from AnalyticsCache.getScore import calculate_accuracy_and_recall, calculate_all_metrics
from AnalyticsCache.insert_null import inject_missing_values
from Clean import CleanonLocal, CleanonLocalWithnoSmple
from SampleScrubber.cleaner.multiple import AttrRelation
from util import evaluate_cleaning_performance, save_cleaned_data

# 清洗配置
cleaners = [
    AttrRelation(["HospitalName"], ["ProviderNumber"], '1'),
    AttrRelation(["Condition", "MeasureName"], ["HospitalType"], '2'),
    AttrRelation(["HospitalName", "PhoneNumber", "HospitalOwner"], ["State"], '3'),
    AttrRelation(["HospitalName"], ["ZipCode"], '4'),
    AttrRelation(["HospitalName"], ["PhoneNumber"], '5'),
    AttrRelation(["MeasureCode"], ["MeasureName"], '6'),
    AttrRelation(["MeasureCode"], ["Stateavg"], '7'),
    AttrRelation(["ProviderNumber"], ["HospitalName"], '8'),
    AttrRelation(["MeasureCode"], ["Condition"], '9'),
    AttrRelation(["HospitalName"], ["Address1"], '10'),
    AttrRelation(["HospitalName"], ["HospitalOwner"], '11'),
    AttrRelation(["City"], ["CountyName"], '12'),
    AttrRelation(["ZipCode"], ["EmergencyService"], '13'),
    AttrRelation(["HospitalName"], ["City"], '14')
]
file_load = 'TestDataset/1_hospitals/dirty_index.csv'
clean_path = 'TestDataset/1_hospitals/clean_index.csv'
save_path = 'TestDataset/result/'
table_name = 'hospital_1'
attributes = [
    'Address1', 'City', 'Condition', 'CountyName', 'EmergencyService', 'HospitalName',
    'HospitalOwner', 'HospitalType', 'MeasureCode', 'MeasureName', 'PhoneNumber',
    'ProviderNumber', 'State', 'Stateavg', 'ZipCode'
]
single_max = 10000

# 添加动态参数解析
def parse_args():
    parser = argparse.ArgumentParser(description="Data cleaning for hospitals dataset.")
    parser.add_argument('--file_load', type=str, default=file_load, help="Path to the dirty dataset.")
    parser.add_argument('--clean_path', type=str, default=clean_path, help="Path to the clean dataset.")
    parser.add_argument('--save_path', type=str, default=save_path, help="Directory to save cleaned data.")
    parser.add_argument('--table_name', type=str, default=table_name, help="Name of the result table.")
    parser.add_argument('--missing_token', type=str, default='empty',
                        help="cleaned.csv 与 clean/dirty 共用的缺失值占位字符串，默认 'empty'。")
    return parser.parse_args()

def main():
    args = parse_args()

    file_load = args.file_load
    clean_path = args.clean_path
    save_path = args.save_path
    table_name = args.table_name
    missing_token = args.missing_token

    # 初始化 SparkSession
    spark = SparkSession.builder \
        .appName("DataCleaningApp") \
        .config("spark.executor.memory", "8g") \
        .config("spark.driver.memory", "8g") \
        .config("spark.executor.memoryOverhead", "8g") \
        .config("spark.sql.shuffle.partitions", "200") \
        .getOrCreate()

    print("Logs saved in " + logsetting.logfilename)

    # 读取数据：hospital cleaners 全是 AttrRelation 不依赖数值类型，
    # 用 inferSchema=False 避免数字列(PhoneNumber/ZipCode/...) 把空值变 null，
    # 再 fillna(missing_token) 让 cleaner 内部 Counter(kv[s]) 不会遇到 None 键
    # （部分文件因 null 多触发 KeyError 崩溃）
    data = spark.read.csv(file_load, header=True, inferSchema=False)
    if 'index' not in data.columns:
        data = data.withColumn("index", monotonically_increasing_id())
    fill_cols = [c for c in data.columns if c != 'index']
    if fill_cols:
        data = data.fillna(missing_token, subset=fill_cols)
    data.persist()

    # 数据清洗及时间记录
    start_time = time.perf_counter()
    table_path = os.path.join(save_path, table_name)
    os.makedirs(table_path, exist_ok=True)
    data = CleanonLocalWithnoSmple(spark, cleaners, data, table_path, single_max=single_max)
    elapsed_time = time.perf_counter() - start_time
    print(f"当前清洗总执行时间: {elapsed_time:.4f} 秒")

    # 保存清洗后的数据
    save_cleaned_data(data, table_path, table_name)
    mse_attributes = ['Score']
    # 性能评估
    evaluate_cleaning_performance(clean_path, file_load, os.path.join(table_path, f'{table_name}Cleaned.csv'),
                                  elapsed_time, table_path, table_name, mse_attributes,
                                  missing_token=missing_token)

    spark.stop()

if __name__ == '__main__':
    main()