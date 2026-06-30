import argparse
import os
import time

from pyspark.sql import SparkSession
from pyspark.sql.functions import monotonically_increasing_id

from AnalyticsCache.getScore import calculate_accuracy_and_recall, calculate_all_metrics
from AnalyticsCache.insert_null import inject_missing_values
from Clean import CleanonLocal, CleanonLocalWithnoSmple
from SampleScrubber.cleaner.multiple import AttrRelation
from SampleScrubber.cleaner.single import Date, Pattern
from util import evaluate_cleaning_performance, save_cleaned_data

# Regular expression pattern # 正则表达式模式
pattern = r"^(0[1-9]|1[0-2]):[0-5][0-9]\s?(AM|PM)$"

# Flight data cleaning rules # flight 数据清洗规则
cleaners = [
    Pattern("sched_dep_time", pattern, '0'),
    Pattern("act_dep_time", pattern, '1'),
    Pattern("sched_arr_time", pattern, '2'),
    Date("sched_dep_time", "%I:%M %p", '5'),
    Date("act_dep_time", "%I:%M %p", '6'),
    Date("sched_arr_time", "%I:%M %p", '7'),
    Date("act_arr_time", "%I:%M %p", '8'),
    AttrRelation(["flight"], ["sched_dep_time"], '3'),
    AttrRelation(["flight"], ["act_dep_time"], '4'),
    AttrRelation(["flight"], ["sched_arr_time"], '9'),
    AttrRelation(["flight"], ["act_arr_time"], '10')
]

# Default parameters # 默认参数
file_load = 'TestDataset/2_flights/dirty_index.csv'
clean_path = 'TestDataset/2_flights/clean_index.csv'
save_path = 'TestDataset/result/'
table_name = 'flight_2test'
attributes = ["sched_dep_time", "act_dep_time", "sched_arr_time", "act_arr_time"]
single_max = 10000

# Add dynamic argument parsing # 添加动态参数解析
def parse_args():
    parser = argparse.ArgumentParser(description="Data cleaning for flights dataset.")
    parser.add_argument('--file_load', type=str, default=file_load, help="Path to the dirty dataset.")
    parser.add_argument('--clean_path', type=str, default=clean_path, help="Path to the clean dataset.")
    parser.add_argument('--save_path', type=str, default=save_path, help="Directory to save cleaned data.")
    parser.add_argument('--table_name', type=str, default=table_name, help="Name of the result table.")
    return parser.parse_args()

def main():
    args = parse_args()

    file_load = args.file_load
    clean_path = args.clean_path
    save_path = args.save_path
    table_name = args.table_name

    # Initialize SparkSession # 初始化 SparkSession
    spark = SparkSession.builder \
        .appName("FlightDataCleaning") \
        .config("spark.executor.memory", "8g") \
        .config("spark.driver.memory", "8g") \
        .config("spark.executor.memoryOverhead", "8g") \
        .config("spark.sql.shuffle.partitions", "200") \
        .getOrCreate()

    # Read data and add index column # 读取数据并添加索引列
    data = spark.read.csv(file_load, header=True, inferSchema=True)
    if 'index' not in data.columns:
        data = data.withColumn("index", monotonically_increasing_id())
    data.persist()

    # Data cleaning and time recording # 数据清洗及时间记录
    start_time = time.perf_counter()
    table_path = os.path.join(save_path, table_name)
    os.makedirs(table_path, exist_ok=True)
    data = CleanonLocalWithnoSmple(spark, cleaners, data, table_path, single_max=single_max)
    elapsed_time = time.perf_counter() - start_time
    print(f"Total cleaning execution time: 清洗总执行时间: {elapsed_time:.4f} 秒")

    # Save cleaned data # 保存清洗后的数据
    save_cleaned_data(data, table_path, table_name)

    # Performance evaluation # 性能评估
    evaluate_cleaning_performance(clean_path, file_load, os.path.join(table_path, f'{table_name}Cleaned.csv'),
                                  elapsed_time, table_path, table_name)

    spark.stop()

if __name__ == '__main__':
    main()