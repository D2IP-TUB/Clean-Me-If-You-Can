import distance
from pyspark.sql import functions as F


def edit(target, source):
    # 计算 Levenshtein 距离
    return float(distance.levenshtein(target, source)) if target is not None and source is not None else 1.0


def max_by_column(df1, df2, index_column, column1, column2):
    df1 = df1.withColumnRenamed(column1, column1 + "_1")
    df2 = df2.withColumnRenamed(column2, column2 + "_2")
    combined_df = df1.join(df2, index_column)
    # combined_df.show()
    result_df = combined_df.withColumn("qfn", F.when(F.col(column1 + "_1") > F.col(column2 + "_2"),
                                                     F.col(column1 + "_1")).otherwise(F.col(column2 + "_2")))
    return result_df.select(index_column, "qfn")
