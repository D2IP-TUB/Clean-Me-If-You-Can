from pyspark.sql import SparkSession
from pyspark.sql.functions import col, count, row_number
from pyspark.sql.window import Window
from pyspark.sql.utils import AnalysisException

from SampleScrubber.cleaner.multiple import AttrRelation

# cleaners 列表
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
    AttrRelation(['latitude', 'longitude'], ['enterprise_address'], '22'),
    AttrRelation(['enterprise_address'], ['province'], '12'),
    AttrRelation(['enterprise_address'], ['city'], '13'),
    AttrRelation(['enterprise_address'], ['district'], '14'),
    AttrRelation(['enterprise_address'], ['latitude'], '15'),
    AttrRelation(['enterprise_address'], ['longitude'], '16'),
    AttrRelation(['province'], ['city'], '17'),
    AttrRelation(['city'], ['district'], '18'),
    AttrRelation(['enterprise_name'], ['enterprise_type'], '19'),
    AttrRelation(['social_credit_code'], ['enterprise_name'], '21')
]

# 配置变量
database_name = 'tid_sdi_ai4data'
dirty_table_name = 'ai4data_enterprise_bak_preH'
clean_table_name = 'ai4data_enterprise_bak_anomaly_data_flag'
N = 10000000  # 提取的记录数量

def process_data(spark, database_name, dirty_table_name, clean_table_name, N, cleaners):
    print("开始处理数据...")

    # 读取脏数据并保存所有列
    print(f"从表 {database_name}.{dirty_table_name} 中读取脏数据...")
    dirty_query = f"SELECT * FROM {database_name}.{dirty_table_name} LIMIT {N}"
    dirty_data = spark.sql(dirty_query)
    dirty_count = dirty_data.count()
    print(f"脏数据记录数：{dirty_count}")

    # 将查询结果写入一个新表，保留所有列
    dirty_data_table = f"{dirty_table_name}_1000w"
    print(f"将脏数据写入新表 {database_name}.{dirty_data_table}...")
    dirty_data.write.mode("overwrite").saveAsTable(f"{database_name}.{dirty_data_table}")
    print("脏数据已保存。")

    # 从脏数据中仅选择 enterprise_id，用于连接
    dirty_ids = dirty_data.select("enterprise_id").distinct()
    dirty_ids_count = dirty_ids.count()
    print(f"从脏数据中提取 enterprise_id，共计 {dirty_ids_count} 个唯一值。")

    # 读取干净数据
    print(f"从表 {database_name}.{clean_table_name} 中读取干净数据...")
    clean_data = spark.table(f"{database_name}.{clean_table_name}")
    clean_data_count = clean_data.count()
    print(f"干净数据记录数：{clean_data_count}")

    # 基于 enterprise_id 进行 INNER JOIN 操作
    print("将脏数据和干净数据基于 enterprise_id 进行 INNER JOIN...")
    joined_data = dirty_ids.join(clean_data, on='enterprise_id', how='inner')
    joined_count = joined_data.count()
    print(f"连接后的数据记录数：{joined_count}")

    # 缓存 joined_data，提高后续重复读取效率
    joined_data.cache()
    print("已缓存连接数据 joined_data。")

    # 遍历 cleaners 列表
    for idx, cleaner in enumerate(cleaners, start=1):
        print(f"\n处理第 {idx} 个 cleaner，ID：{cleaner.name}")
        source_attributes = list(cleaner.source)
        target_attribute = list(cleaner.target)[0]  # 获取 target 属性
        print(f"源属性：{source_attributes}，目标属性：{target_attribute}")

        # 检查所需的列是否存在于 clean_data 中
        required_columns = source_attributes + [target_attribute]
        missing_columns = [col for col in required_columns if col not in clean_data.columns]
        if missing_columns:
            print(f"跳过 cleaner {cleaner.name}：缺少列 {missing_columns} 在 clean_data 中")
            continue

        # 生成输出表名
        source_str = '_'.join(source_attributes)
        target_str = target_attribute
        output_table_name = f"{dirty_data_table}_external_knowledge_{source_str}_to_{target_str}"

        try:
            # 从 joined_data 中选择所需的列
            print(f"从连接数据中选择所需的列：{required_columns} ")
            selected_data = joined_data.select(*required_columns)
        except AnalysisException as e:
            print(f"跳过 cleaner {cleaner.name}：选择列时出现错误：{e}")
            continue

        # 排除源属性中包含空值的记录
        print("过滤掉源属性中包含空值的记录...")
        selected_data = selected_data.dropna(subset=source_attributes)
        selected_data_count = selected_data.count()
        print(f"过滤后可用于处理的记录数：{selected_data_count}")

        if selected_data_count == 0:
            print(f"cleaner {cleaner.name} 的数据为空，跳过处理。")
            continue

        # 计算每个源属性组合和目标属性值的出现次数
        print(f"根据源属性 {source_attributes} 和目标属性 {target_attribute} 进行分组并统计...")
        grouped_data = selected_data.groupBy(*(source_attributes + [target_attribute])).agg(count("*").alias("count"))

        # 定义窗口函数，根据源属性分区，按 count 降序排序
        window_spec = Window.partitionBy(*source_attributes).orderBy(col("count").desc())

        # 为每个分区添加行号
        ranked_data = grouped_data.withColumn("rank", row_number().over(window_spec))

        # 选择每个源属性组合中出现次数最多的目标属性值
        reliable_records = ranked_data.filter(col("rank") == 1)

        reliable_count = reliable_records.count()
        print(f"找到 {reliable_count} 条可靠记录。")

        if reliable_count == 0:
            print(f"cleaner {cleaner.name} 未找到可靠记录，跳过保存。")
            continue

        # 将目标属性重命名为 'target_value'
        output = reliable_records.select(*source_attributes, col(target_attribute).alias('target_value'))

        # 将结果保存到指定的 Hive 表
        print(f"将结果保存到表 {database_name}.{output_table_name}...")
        output.write.mode('overwrite').saveAsTable(f"{database_name}.{output_table_name}")
        print(f"已生成表：{database_name}.{output_table_name}")

    # 清除缓存
    joined_data.unpersist()
    print("已清除 joined_data 的缓存。")
    print("数据处理完成。")


if __name__ == '__main__':
    spark = SparkSession.builder \
        .appName("DataProcessing") \
        .config("spark.sql.session.state.builder", "org.apache.spark.sql.hive.UQueryHiveACLSessionStateBuilder") \
        .config("spark.sql.catalog.class", "org.apache.spark.sql.hive.UQueryHiveACLExternalCatalog") \
        .config("spark.sql.extensions", "org.apache.spark.sql.DliSparkExtension") \
        .config("spark.sql.hive.implementation", "org.apache.spark.sql.hive.client.DliHiveClientImpl") \
        .enableHiveSupport() \
        .getOrCreate()

    process_data(
        spark,
        database_name,
        dirty_table_name,
        clean_table_name,
        N,
        cleaners
    )
    spark.stop()