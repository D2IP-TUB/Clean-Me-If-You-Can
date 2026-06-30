from pyspark.sql import SparkSession
from pyspark.sql import Row
from pyspark.sql.functions import col

# 配置变量
database_name = 'tid_sdi_ai4data'
dirty_table_name = 'ai4data_enterprise_bak'
clean_table_name = 'ai4data_enterprise_bak_anomaly_data_flag'
replace_attributes = ['registered_capital', 'annual_turnover', 'enterprise_address',
                      'social_credit_code', 'establishment_date']


def replace_dirty_with_clean(spark, database_name, dirty_table_name, clean_table_name, replace_attributes):
    # 读取脏数据
    dirty_query = f"SELECT * FROM {database_name}.{dirty_table_name}"
    dirty_data = spark.sql(dirty_query)

    # 读取干净数据中指定的属性
    clean_query = f"SELECT enterprise_id, {', '.join(replace_attributes)} FROM {database_name}.{clean_table_name}"
    clean_data = spark.sql(clean_query)

    # 保留仅在 clean_data 中存在的 enterprise_id 的记录
    dirty_data = dirty_data.join(clean_data.select("enterprise_id"), "enterprise_id", "inner")

    # 替换脏数据中的相应属性
    for attribute in replace_attributes:
        clean_attribute_data = clean_data.selectExpr(f"enterprise_id as clean_enterprise_id", f"{attribute} as clean_{attribute}")
        dirty_data = dirty_data.join(clean_attribute_data, dirty_data.enterprise_id == clean_attribute_data.clean_enterprise_id, 'left') \
            .drop('clean_enterprise_id') \
            .withColumn(attribute, col(f"clean_{attribute}"))

    # 清理临时列
    dirty_data = dirty_data.drop(*[f"clean_{attribute}" for attribute in replace_attributes])

    return dirty_data


if __name__ == '__main__':
    spark = SparkSession.builder \
        .appName("DataCleaning") \
        .config("spark.sql.session.state.builder", "org.apache.spark.sql.hive.UQueryHiveACLSessionStateBuilder") \
        .config("spark.sql.catalog.class", "org.apache.spark.sql.hive.UQueryHiveACLExternalCatalog") \
        .config("spark.sql.extensions", "org.apache.spark.sql.DliSparkExtension") \
        .config("spark.sql.hive.implementation", "org.apache.spark.sql.hive.client.DliHiveClientImpl") \
        .enableHiveSupport() \
        .getOrCreate()

    prehandle_data = replace_dirty_with_clean(spark, database_name, dirty_table_name, clean_table_name, replace_attributes)

    prehandle_data.write.mode('overwrite').saveAsTable(f"{database_name}.{dirty_table_name}_preH")

    spark.stop()