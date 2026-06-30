import argparse
import os
import time

from pyspark.sql import SparkSession
from pyspark.sql.functions import monotonically_increasing_id

from AnalyticsCache.getScore import calculate_accuracy_and_recall, calculate_all_metrics
from AnalyticsCache.insert_null import inject_missing_values
from Clean import CleanonLocal
from Clean_test import CleanRamdonCL
from SampleScrubber.cleaner.multiple import AttrRelation
from SampleScrubber.cleaner.single import Pattern, Outlier, Number
from util import evaluate_cleaning_performance, save_cleaned_data

# 清洗规则定义
cleaners = [
    Number("season", None, '0'),
    AttrRelation(["name"], ["surname"], '1'),
    AttrRelation(["name"], ["birthyear"], '2'),
    AttrRelation(["name"], ["birthplace"], '3'),
    AttrRelation(["name", "season"], ["position"], '4'),
    AttrRelation(["team", "city", "season"], ["stadium"], '5'),
    AttrRelation(["manager", "season"], ["team"], '6'),
]

# 默认参数
file_load = 'TestDataset/6_soccer/noise_with_correct_primary_key/dirty_mixed_0.25/dirty_soccer_mix_0.25.csv'
clean_path = 'TestDataset/6_soccer/clean_index.csv'
save_path = 'TestDataset/result/'
table_name = 'soccer200k'
single_max = 10000

# 添加动态参数解析
def parse_args():
    parser = argparse.ArgumentParser(description="Data cleaning for soccer dataset.")
    parser.add_argument('--file_load', type=str, default=file_load, help="Path to the dirty dataset.")
    parser.add_argument('--clean_path', type=str, default=clean_path, help="Path to the clean dataset.")
    parser.add_argument('--save_path', type=str, default=save_path, help="Directory to save cleaned data.")
    parser.add_argument('--table_name', type=str, default=table_name, help="Name of the result table.")
    parser.add_argument('--single_max', type=int, default=single_max, help="Maximum records to process in a single run.")
    return parser.parse_args()

def main():
    args = parse_args()

    file_load = args.file_load
    clean_path = args.clean_path
    save_path = args.save_path
    table_name = args.table_name
    single_max = args.single_max

    # 初始化 SparkSession
    spark = SparkSession.builder \
        .appName("SoccerDataCleaning") \
        .config("spark.executor.memory", "8g") \
        .config("spark.driver.memory", "8g") \
        .config("spark.executor.memoryOverhead", "8g") \
        .config("spark.sql.shuffle.partitions", "200") \
        .getOrCreate()

    # 读取数据并添加索引列
    data = spark.read.csv(file_load, header=True, inferSchema=True)
    if 'index' not in data.columns:
        data = data.withColumn("index", monotonically_increasing_id())
    data.persist()

    # 数据清洗及时间记录
    start_time = time.perf_counter()
    table_path = os.path.join(save_path, table_name)
    os.makedirs(table_path, exist_ok=True)
    data = CleanonLocal(spark, cleaners, data, table_path, single_max=single_max)
    elapsed_time = time.perf_counter() - start_time
    print(f"清洗总执行时间: {elapsed_time:.4f} 秒")

    # 保存清洗后的数据
    save_cleaned_data(data, table_path, table_name)

    # 性能评估
    evaluate_cleaning_performance(clean_path, file_load, os.path.join(table_path, f'{table_name}Cleaned.csv'),
                                  elapsed_time, table_path, table_name)

    spark.stop()


if __name__ == '__main__':
    main()