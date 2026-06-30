import numpy
import numpy as np
from pyspark.sql.functions import col, when
from pyspark.sql import functions as F
from functools import reduce


def getOpWeights(editRuleDict, groupOpInfo):
    """
    获取每个操作的权重。

    参数：
    editRuleDict (dict): 编辑规则字典。
    groupOpInfo (dict): 操作信息分组字典。

    返回：
    dict: 每个操作的权重字典。
    """
    op_weights_dict = {}
    TotalRule = 0
    for level_index in groupOpInfo:  # 分析每组
        level = groupOpInfo[level_index]
        for targetNode in level:
            group_weight = []
            weight = 0
            for cleaner in level[targetNode]:
                for source in cleaner.source:
                    weight += analyticsRuleDict(editRuleDict[targetNode], source)
                TotalRule += weight
                group_weight.append(weight)
            op_weights_dict[targetNode] = group_weight
    # 对每个子列表中的每个元素除以 TotalRule
    if TotalRule == 0:
        return op_weights_dict
    else:
        # 使用列表解析更新字典
        op_weights = {key: [float(x) / TotalRule for x in values] for key, values in op_weights_dict.items()}
    return op_weights


def analyticsRuleDict(editRuleList, source):
    """
    分析规则字典，计算权重。

    参数：
    editRuleList (list): 编辑规则列表。
    source (str): 源字符串。

    返回：
    int: 权重。
    """
    weight = 0
    for rule in editRuleList:
        if source in rule.predicate[0]:
            weight += 1
    return weight


def transformRulesToSQL(EditRuleList, target_table, source_table):
    """
    转换编辑规则列表为 SQL 语句列表。

    参数：
    EditRuleList (list): 编辑规则列表。

    返回：
    list: SQL 语句列表。
    """
    SQLList = []
    # 复制表并添加 clean 列
    for EditRule in EditRuleList:
        column = EditRule.domain
        predicates = EditRule.predicate[0]
        values = EditRule.predicate[1]
        value = EditRule.repairvalue

        for val_tuple in values:
            condition = " AND ".join([f"{pred} = '{val}'" for pred, val in zip(predicates, val_tuple)])
            sql = f"UPDATE data SET {column} = '{value}' WHERE {condition};"
            SQLList.append(sql)
    return SQLList


from pyspark.sql import functions as F
from functools import reduce
import numpy as np

def transformRulesToSpark(EditRuleList, df, batch_size=300, maxhandle=20000):
    """
    转换编辑规则列表并使用 Spark API 修改 DataFrame。

    参数：
    EditRuleList (list): 编辑规则列表。
    df (DataFrame): 要修改的 DataFrame。
    batch_size (int): 每批处理的规则数量。
    maxhandle (int): 最大可处理规则数量。

    返回：
    DataFrame: 修改后的 DataFrame。
    list: 剩余未处理的规则。
    """
    handled_rules = 0  # 追踪已处理的规则数量
    all_conditions = {}  # 存储每列的条件和修复值

    for i in range(0, len(EditRuleList), batch_size):
        batch = EditRuleList[i:i + batch_size]

        # 将条件合并到字典中
        for EditRule in batch:
            try:
                column = EditRule.domain
                predicate_attrs = EditRule.predicate[0]
                value_sets = EditRule.predicate[1]
                repair_value = EditRule.repairvalue

                # 初始化该列的条件列表
                if column not in all_conditions:
                    all_conditions[column] = []

                # 处理整数类型的值
                value_sets = [
                    tuple(map(lambda x: int(x) if isinstance(x, np.integer) else x, v))
                    for v in value_sets
                ]

                # 生成单一的修复条件
                conditions = []
                for value_set in value_sets:
                    disguised_missing_values = {"__NULL__", "null", "N/A", "empty", ""}

                    # 构建子条件
                    sub_conditions = [
                        (F.col(attr).isNull() | F.col(attr).isin(disguised_missing_values)) if val == "__NULL__"
                        else F.col(attr) == val
                        for attr, val in zip(predicate_attrs, value_set)
                    ]

                    # 合并子条件为一个完整条件
                    if sub_conditions:
                        condition = reduce(lambda x, y: x & y, sub_conditions)
                        conditions.append(condition)

                # 将最终条件与修复值添加到列的条件列表中
                if conditions:
                    final_condition = reduce(lambda x, y: x | y, conditions)
                    all_conditions[column].append((final_condition, repair_value))
                    handled_rules += 1

                    # 检查是否超过 maxhandle 限制
                    if handled_rules >= maxhandle:
                        # 在提前返回之前应用当前收集的规则到 DataFrame
                        df = apply_conditions_to_df(df, all_conditions)
                        remaining_rules = EditRuleList[i + batch_size:]
                        print(f"已处理最大规则数 {maxhandle}，提前返回结果")
                        return df, remaining_rules
            except Exception as e:
                print(f"处理规则 {EditRule} 时出错：{e}")
                continue

    # 如果处理所有规则后，应用条件到 DataFrame
    df = apply_conditions_to_df(df, all_conditions)

    # 触发 action 来 materialize DataFrame
    print(f"读入数据大小：{df.count()}")
    print(f"处理了 {handled_rules} 条规则，更新数据...")
    df = df.persist()
    print("所有编辑规则已更新完成")

    # 所有规则处理完成，返回 DataFrame 和空的剩余规则列表
    return df, []

def apply_conditions_to_df(df, all_conditions):
    """
    将条件和修复值应用到 DataFrame。

    参数：
    df (DataFrame): 要修改的 DataFrame。
    all_conditions (dict): 每列的条件和修复值。

    返回：
    DataFrame: 修改后的 DataFrame。
    """
    for column, cond_list in all_conditions.items():
        # 为每个修复条件生成 `when` 条件
        column_update = F.when(cond_list[0][0], cond_list[0][1])
        for cond, repair_value in cond_list[1:]:
            column_update = column_update.when(cond, repair_value)
        # 默认保留原始值
        df = df.withColumn(column, column_update.otherwise(F.col(column)))
    return df


def get_detected_cells(EditRuleList, df, index_col='index'):
    """
    Given a list of edit rules and a Spark DataFrame, returns a list of (index_value, column_name)
    pairs for every row whose predicate matches at least one rule for that column.
    This represents cells the system "detected" as potential errors, before any correction is applied.
    """
    all_conditions = {}  # column -> list of OR-able conditions

    for EditRule in EditRuleList:
        try:
            column = EditRule.domain
            predicate_attrs = EditRule.predicate[0]
            value_sets = EditRule.predicate[1]

            if column not in all_conditions:
                all_conditions[column] = []

            value_sets = [
                tuple(map(lambda x: int(x) if isinstance(x, np.integer) else x, v))
                for v in value_sets
            ]

            conditions = []
            for value_set in value_sets:
                disguised_missing_values = {"__NULL__", "null", "N/A", "empty", ""}
                sub_conditions = [
                    (F.col(attr).isNull() | F.col(attr).isin(disguised_missing_values)) if val == "__NULL__"
                    else F.col(attr) == val
                    for attr, val in zip(predicate_attrs, value_set)
                ]
                if sub_conditions:
                    condition = reduce(lambda x, y: x & y, sub_conditions)
                    conditions.append(condition)

            if conditions:
                final_condition = reduce(lambda x, y: x | y, conditions)
                all_conditions[column].append(final_condition)
        except Exception:
            continue

    detected = []
    for column, cond_list in all_conditions.items():
        any_match = reduce(lambda a, b: a | b, cond_list)
        matched_indices = df.filter(any_match).select(index_col).rdd.flatMap(lambda x: x).collect()
        for idx in matched_indices:
            detected.append((idx, column))
    return detected


def transformKnowledgeToSpark(spark, database_name,table_name,df, cleaner):
    """
    将外部知识库表转换为 Spark 操作，并应用于 DataFrame。

    参数：
    spark (SparkSession): Spark 会话对象。
    database_name (str): 数据库名称。
    df (DataFrame): 要修改的 DataFrame。
    cleaner (AttrRelation): 单个 AttrRelation 对象。
    batch_size (int): 每批处理的规则数量。

    返回：
    DataFrame: 修改后的 DataFrame。
    """

    source_attributes = list(cleaner.source)
    target_attribute = list(cleaner.target)[0]  # 假设 target 是单个属性

    # 生成外部知识库表名
    source_str = '_'.join(source_attributes)
    target_str = target_attribute
    knowledge_table_name = f"{table_name}_external_knowledge_{source_str}_to_{target_str}"

    # 检查表是否存在
    table_exists = spark._jsparkSession.catalog().tableExists(database_name, knowledge_table_name)
    if not table_exists:
        print(f"知识库表 {database_name}.{knowledge_table_name} 不存在，跳过该 cleaner。")
        return df

    # 读取知识库表
    knowledge_df = spark.table(f"{database_name}.{knowledge_table_name}")

    # 将知识库表与原始 DataFrame 进行 Join 操作
    join_conditions = [df[attr] == knowledge_df[attr] for attr in source_attributes]
    df = df.join(knowledge_df, on=join_conditions, how='left')

    # 更新目标属性
    df = df.withColumn(target_attribute,
                       when(col('target_value').isNotNull(), col('target_value')).otherwise(col(target_attribute)))

    # 删除临时列
    for attr in source_attributes:
        df = df.drop(knowledge_df[attr])
    df = df.drop('target_value')

    # 触发持久化操作（可根据需要选择是否保留）
    df.count()
    # df.unpersist()
    # df = df.persist()

    print(f"已处理 cleaner: {knowledge_table_name}")
    return df

# 示例调用
# df, remaining_rules = transformRulesToSpark(EditRuleList, df, batch_size=300, maxhandle=2000)
