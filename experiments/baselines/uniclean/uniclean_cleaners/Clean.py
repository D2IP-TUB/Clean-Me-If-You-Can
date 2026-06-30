import os
import time

import pandas as pd
from AnalyticsCache.cleaner_associations_cycle import associations_classier, discover_cleaner_associations, \
    PreParamClassier
from AnalyticsCache.get_cleaner_excute_info import sort_opinfo_by_weights, generate_plantuml_corrected, \
    getSingle_opinfo, cleaner_grouping
from AnalyticsCache.get_planuml_graph import PlantUML
from AnalyticsCache.handle_rules import getOpWeights, transformRulesToSpark, transformKnowledgeToSpark, get_detected_cells
from CoreSetSample.mapping_samplify import Generate_Sample
from SampleScrubber.cleaner_model import NOOP
from SampleScrubber.param_selector import customclean


def CleanonLocal(spark, cleanners, data, table_path, batch_size=500, single_max=30000):
    current = 'Tmp1'
    print("初始化清洗器和分析依赖关系...")
    Edges, singles, multis = PreParamClassier(cleanners)

    print("处理单属性清洗算子：")
    for single in singles:
        print(f"处理单属性清洗算子：{single}")
        # 获取当前单属性的域 (例如: "domain" 属性表示当前算子的目标属性)
        target_column = single.domain

        # 从 Spark DataFrame 中选择目标列，并将其转换为 pandas DataFrame
        sample_df = data.select(target_column).distinct().toPandas()

        if sample_df.empty:
            print(f"属性 {target_column} 的数据为空，跳过清洗。")
            continue

        print(f"抽样属性 {target_column} 的数据块大小: {sample_df.shape[0]}")

        # 调用 customclean 进行清洗操作
        preCleaners = [single]
        _, output, editRuleList, _ = customclean(sample_df, precleaners=preCleaners)

        if editRuleList:
            # 如果有清洗操作规则，应用到 Spark DataFrame 上
            print(f"应用 {target_column} 的清洗规则，编辑规则数量: {len(editRuleList)}")
            data, _ = transformRulesToSpark(editRuleList, data, batch_size=batch_size)
        else:
            print(f"属性 {target_column} 没有可应用的清洗规则。")

    source_sets, target_sets, explain, processing_order, plt = discover_cleaner_associations(Edges)
    print("执行层级和目标模型分类...")
    levels, models, nodes = associations_classier(multis, source_sets, target_sets)
    print("执行层级 (并行组):", levels)
    print("目标模型分类:", models)

    editRuleDict = {}  # 用于统计溯源权重
    editRules = NOOP()  # 初始化无操作规则
    nextClean = True

    level_clean_status = {}
    clean_attempts = {}  # 新增：记录每个节点的清洗次数

    while nextClean:
        nextClean = False

        for level_index, level in enumerate(nodes):
            # 如果该层级还未记录过清洗状态，则初始化
            if level_index not in level_clean_status:
                level_clean_status[level_index] = {node: False for node in level}
            if level_index not in clean_attempts:
                clean_attempts[level_index] = {node: 0 for node in level}

            print(f"\n处理第 {level_index + 1} 层级, 包含节点: {level}")
            editRuleLists = []  # 获取当前层级的清洗操作列表

            for node in level:
                # 只处理该层级中挖掘不到操作的节点
                if level_clean_status[level_index][node]:
                    print(f"  跳过已清洗结束的节点: {node}")
                    continue

                clean_attempts[level_index][node] += 1  # 增加清洗次数

                if clean_attempts[level_index][node] > 3:  # 超过3次则标记为完成
                    print(f"  当前节点 {node} 清洗次数超过限制，标记为完成")
                    level_clean_status[level_index][node] = True
                    continue

                editRule = NOOP()
                editRuleList = []

                if node in models and models[node]:
                    print(f"  当前节点: {node} 存在可用清洗信号")
                    sset = set()
                    tset = set()
                    for m in models[node]:
                        sset = sset.union(m.source)
                        tset = tset.union(m.target)
                    sset = list(sset)
                    tset = list(tset)
                    print(f"  抽样处理：源属性 {sset} -> 目标属性 {node}")
                    sample_Block_df, error_threshold = Generate_Sample(data, sset, tset, models=models[node])
                    sample_df = sample_Block_df.toPandas()
                    print(f"数据块大小: {sample_df.shape[0]}")
                    if sample_df.shape[0] < single_max:
                        preCleaners = [single for single in singles if single.domain in (sset + [node])]
                        _, output, _, _ = customclean(sample_df, precleaners=preCleaners)
                        # 对块内算子加权计算
                        blockModels = None
                        weights = [1] * len(models[node])
                        for model, weight in zip(models[node], weights):
                            if blockModels is None:
                                blockModels = model * weight
                            else:
                                blockModels += model * weight
                        partition = [list(model.source) for model in models[node]]
                        print('分块属性')
                        print(partition)
                        editRule1, output, editRuleList, _ = customclean(output, cleaners=[blockModels],
                                                                         partition=partition,
                                                                         error_threshold=error_threshold)
                        editRule *= editRule1
                    else:
                        print(f"数据块大小超过阈值，逐个执行模型")
                        for m in models[node]:
                            print(f"处理模型: {m}")
                            # 提取当前模型的源和目标属性
                            sset = list(m.source)
                            tset = list(m.target)
                            sample_Block_df, error_threshold = Generate_Sample(data, sset, tset, models=[m],
                                                                               single_max=single_max)
                            sample_df = sample_Block_df.toPandas()
                            if sample_df.shape[0] == 0:
                                print(f"模型 {m} 处理后无数据")
                                continue
                            preCleaners = [single for single in singles if single.domain in (sset + [node])]
                            _, output, _, _ = customclean(sample_df, precleaners=preCleaners)
                            blockModels = m  # 直接使用单个模型
                            partition = [list(m.source)]
                            editRule1, output, editRuleList1, _ = customclean(output, cleaners=[blockModels],
                                                                              partition=partition,
                                                                              error_threshold=error_threshold)
                            editRule *= editRule1
                            editRuleList.extend(editRuleList1)
                else:
                    print(f"  当前节点: {node} 无可用清洗信号")

                editRuleLists.extend(editRuleList)
                editRules *= editRule

                if len(editRuleList) == 0:
                    print(f"  当前节点: {node} 无清洗操作")
                    level_clean_status[level_index][node] = True
                else:
                    print(f"  当前节点: {node} 有{len(editRuleList)}个清洗操作")
                if str(node) in editRuleDict:
                    if isinstance(editRuleDict[str(node)], list):
                        editRuleDict[str(node)].extend(editRuleList)
                    else:
                        editRuleDict[str(node)] = editRuleList  # 假设之前不是列表，现在重置为新列表
                else:
                    editRuleDict[str(node)] = editRuleList  # 键不存在，创建新键并赋值为新列表

            print(f"{level}的清洗完成")
            print("\n本层累积的编辑规则数:", str(len(editRuleLists)))

            if editRuleLists:  # 有编辑规则
                nextClean = True
                # data, _ = transformRulesToSpark(editRuleLists, data, batch_size=batch_size)
                # print("正在写入数据")
                # path = table_path + 'Tmp'
                # data.coalesce(1).write.mode('overwrite').csv(path, header=True)
                # print("写入数据大小：" + str(data.count()))
                # os.system('sync')  # 刷新缓存
                # data.unpersist()
                # spark.catalog.clearCache()
                # print("重新读取最新清洗的数据", str(path))
                # data = spark.read.csv(path, header=True, inferSchema=True)
                # print("读入数据大小" + str(data.count()))
                # data.persist()
                # print(f"数据清洗后变动，重新进行节点:{level}的清洗")
                while True:
                    # 按批次处理规则
                    data, remaining_rules = transformRulesToSpark(editRuleLists, data, batch_size=batch_size, maxhandle=3000)
                    print("正在写入数据...")
                    # 定义临时路径
                    if current == 'Tmp1':
                        path = table_path + 'Tmp2'
                        current = 'Tmp2'
                    else:
                        path = table_path + 'Tmp1'
                        current = 'Tmp1'
                    # 写入数据到文件系统 (avoid coalesce(1) to prevent OOM; repartition to bounded count)
                    data.repartition(8).write.mode('overwrite').csv(path, header=True)
                    print("写入数据大小：" + str(data.count()))
                    os.system('sync')  # 刷新缓存
                    data.unpersist()
                    spark.catalog.clearCache()
                    print("重新读取最新清洗的数据", str(path))
                    data = spark.read.csv(path, header=True, inferSchema=True)
                    print("读入数据大小" + str(data.count()))
                    data.persist()
                    # print(f"数据清洗后变动，重新进行节点:{level}的清洗")

                    # 如果没有剩余规则，退出循环
                    if not remaining_rules:
                        print("所有规则处理完成")
                        break

                    print(f"有剩余的清洗操作没有应用，继续处理 {len(remaining_rules)} 个清洗操作")
                    editRuleLists = remaining_rules  # 使用剩余规则继续处理

                print(f"数据清洗后变动，重新进行节点 {level} 的清洗")
                break
            else:
                print("本层没有可以进行的清洗操作，进行下一层")
    print("\n清洗规则溯源分析:")
    grouped_opinfo = cleaner_grouping(nodes, models)
    single_opinfo = getSingle_opinfo(singles)
    group_weights = getOpWeights(editRuleDict, grouped_opinfo)
    print("\n清洗流程展示:")
    sorted_dict = sort_opinfo_by_weights(grouped_opinfo, group_weights)

    OpPlantuml = generate_plantuml_corrected(single_opinfo, grouped_opinfo, sorted_dict)
    PlantUML().process_str(OpPlantuml, directory=table_path)
    plt.savefig(rf"{table_path}/acplt.png", format="png")
    print("关联图存储到:", rf"{table_path}/acplt.png")
    print("\n绘制清洗流程图:", "CleanerPlantuml.svg")

    return data


def CleanonCloud(spark, cleaners, data, table_name, database_name, batch_size=300, single_max=20000, maxhandle=1000):
    # 初始化和分析清洗器
    print("初始化清洗器和分析依赖关系...")
    Edges, singles, multis = PreParamClassier(cleaners)
    source_sets, target_sets, explain, processing_order = discover_cleaner_associations(Edges)
    print("执行层级和目标模型分类...")
    levels, models, nodes = associations_classier(multis, source_sets, target_sets)
    print("执行层级 (并行组):", levels)
    print("目标模型分类:", models)

    editRuleDict = {}  # 用于统计溯源权重
    editRules = NOOP()  # 初始化无操作规则
    nextClean = True
    tmp_table1 = f"{database_name}.{table_name}_tmp1"
    tmp_table2 = f"{database_name}.{table_name}_tmp2"
    current_tmp_table = tmp_table1
    level_clean_status = {}  # 用于记录每个层级的节点清洗状态
    level_knowledge_status = {}  # 用于记录知识库是否已应用

    while nextClean:
        nextClean = False
        for level_index, level in enumerate(nodes):
            # 如果该层级还未记录过清洗状态，则初始化
            if level_index not in level_clean_status:
                level_clean_status[level_index] = {node: False for node in level}
            if level_index not in level_knowledge_status:
                level_knowledge_status[level_index] = {node: False for node in level}

            print(f"\n处理第 {level_index + 1} 层级, 包含节点: {level}")
            editRuleLists = []  # 获取当前层级的清洗操作列表

            for node in level:
                # 只处理该层级中未完成清洗的节点
                if level_clean_status[level_index][node]:
                    print(f"  跳过已清洗结束的节点: {node}")
                    continue

                # 初始化当前节点的清洗操作
                editRule = NOOP()
                editRuleList = []

                if node in models and models[node]:
                    print(f"  当前节点: {node} 存在可用清洗信号")

                    # 检查知识库是否已应用
                    if not level_knowledge_status[level_index][node]:
                        # **在此处添加 transformKnowledgeToSpark 调用**
                        for cleaner in models[node]:
                            data = transformKnowledgeToSpark(spark, database_name, table_name, data, cleaner)

                        # **写入和读取数据**
                        print("正在写入数据...")
                        next_tmp_table = tmp_table2 if current_tmp_table == tmp_table1 else tmp_table1
                        data.write.mode('overwrite').saveAsTable(next_tmp_table)
                        print(f"写入数据大小：{data.count()}")
                        os.system('sync')  # 刷新缓存
                        data.unpersist()
                        spark.catalog.clearCache()
                        print("重新读取最新清洗的数据...")
                        data = spark.sql(f"SELECT * FROM {next_tmp_table}")
                        print(f"读入数据大小：{data.count()}")
                        data.persist()
                        current_tmp_table = next_tmp_table
                        level_knowledge_status[level_index][node] = True

                    # 定义一个空集合
                    sset = set()
                    tset = set()
                    for m in models[node]:
                        sset = sset.union(m.source)
                        tset = tset.union(m.target)
                    sset = list(sset)  # 转换为列表
                    tset = list(tset)
                    print(f"  抽样处理：源属性 {sset} -> 目标属性 {node}")
                    sample_Block_df, error_threshold = Generate_Sample(
                        data, sset, tset, models=models[node], single_max=single_max
                    )
                    sample_df = sample_Block_df.toPandas()
                    print(f"数据块大小: {sample_df.shape[0]}")

                    preCleaners = [single for single in singles if
                                   any(attr_set in sset + [node] for attr_set in single.domain)]
                    _, output, _, _ = customclean(sample_df, precleaners=preCleaners)

                    blockModels = None
                    weights = [1] * len(models[node])
                    for model, weight in zip(models[node], weights):
                        if blockModels is None:
                            blockModels = model * weight
                        else:
                            blockModels += model * weight
                    partition = [list(model.source) for model in models[node]]
                    editRule1, output, editRuleList, _ = customclean(
                        output, cleaners=[blockModels], partition=partition, error_threshold=error_threshold
                    )
                    editRule *= editRule1
                else:
                    print(f"  当前节点: {node} 无可用清洗信号")

                editRuleLists.extend(editRuleList)
                editRules *= editRule  # 累积应用的清洗规则

                # 如果当前节点没有可用的清洗操作，标记为不需要再处理
                if not editRuleList:
                    level_clean_status[level_index][node] = True  # 标记该节点为无需再处理

                if str(node) in editRuleDict:
                    if isinstance(editRuleDict[str(node)], list):
                        editRuleDict[str(node)].extend(editRuleList)
                    else:
                        editRuleDict[str(node)] = editRuleList  # 假设之前不是列表，现在重置为新列表
                else:
                    editRuleDict[str(node)] = editRuleList  # 键不存在，创建新键并赋值为新列表

            print(f"{level} 的清洗完成")
            print("\n本层累积的编辑规则数:", str(len(editRuleLists)))

            if editRuleLists:  # 有编辑规则
                nextClean = True
                while True:
                    # 处理数据，返回处理后的数据和剩余规则
                    data, remaining_rules = transformRulesToSpark(
                        editRuleLists, data, batch_size=batch_size, maxhandle=maxhandle
                    )
                    print("正在写入数据...")
                    next_tmp_table = tmp_table2 if current_tmp_table == tmp_table1 else tmp_table1
                    data.write.mode('overwrite').saveAsTable(next_tmp_table)
                    print(f"写入数据大小：{data.count()}")
                    os.system('sync')  # 刷新缓存
                    data.unpersist()
                    spark.catalog.clearCache()
                    print("重新读取最新清洗的数据...")
                    data = spark.sql(f"SELECT * FROM {next_tmp_table}")
                    print(f"读入数据大小：{data.count()}")
                    data.persist()
                    current_tmp_table = next_tmp_table

                    if not remaining_rules:
                        print("所有规则处理完成")
                        break  # 所有规则处理完成，退出循环
                    print(f"有剩余的清洗操作没有应用，继续处理 {len(remaining_rules)} 个清洗操作")
                    editRuleLists = remaining_rules  # 使用剩余规则继续处理

                print(f"数据清洗后变动，重新进行节点 {level} 的清洗")
                # 不进行下一个 level 的清洗，重新在本 level 进行清洗
                break
            else:
                print("本层没有可以进行的清洗操作，进行下一层")

    print("\n清洗规则溯源分析:")
    grouped_opinfo = cleaner_grouping(nodes, models)
    group_weights = getOpWeights(editRuleDict, grouped_opinfo)
    print(group_weights)
    return data


def CleanonCloudRandom(spark, cleaners, data, table_name, database_name, batch_size=300, single_max=20000,
                       maxhandle=1000):
    # 初始化和分析清洗器
    print("初始化清洗器和分析依赖关系...")
    Edges, singles, multis = PreParamClassier(cleaners)
    source_sets, target_sets, explain, processing_order = discover_cleaner_associations(Edges)
    print("执行层级和目标模型分类...")
    levels, models, nodes = associations_classier(multis, source_sets, target_sets)
    print("原始执行层级 (并行组):", levels)
    print("目标模型分类:", models)

    # 将 levels 反序以进行反向清洗
    levels = levels[::-1]
    nodes = nodes[::-1]
    print("反序后的执行层级 (并行组):", levels)

    editRuleDict = {}  # 用于统计溯源权重
    editRules = NOOP()  # 初始化无操作规则
    nextClean = True
    tmp_table1 = f"{database_name}.{table_name}_tmp1_random"
    tmp_table2 = f"{database_name}.{table_name}_tmp2_random"
    current_tmp_table = tmp_table1
    level_clean_status = {}  # 用于记录每个层级的节点清洗状态
    level_knowledge_status = {}  # 用于记录知识库是否已应用

    while nextClean:
        nextClean = False
        for level_index, level in enumerate(nodes):
            # 如果该层级还未记录过清洗状态，则初始化
            if level_index not in level_clean_status:
                level_clean_status[level_index] = {node: False for node in level}
            if level_index not in level_knowledge_status:
                level_knowledge_status[level_index] = {node: False for node in level}

            print(f"\n处理反序后的第 {level_index + 1} 层级, 包含节点: {level}")
            editRuleLists = []  # 获取当前层级的清洗操作列表

            for node in level:
                # 只处理该层级中未完成清洗的节点
                if level_clean_status[level_index][node]:
                    print(f"  跳过已清洗结束的节点: {node}")
                    continue

                # 初始化当前节点的清洗操作
                editRule = NOOP()
                editRuleList = []

                if node in models and models[node]:
                    print(f"  当前节点: {node} 存在可用清洗信号")

                    # 检查知识库是否已应用
                    if not level_knowledge_status[level_index][node]:
                        # **在此处添加 transformKnowledgeToSpark 调用**
                        for cleaner in models[node]:
                            data = transformKnowledgeToSpark(spark, database_name, table_name, data, cleaner)

                        # **写入和读取数据**
                        print("正在写入数据...")
                        next_tmp_table = tmp_table2 if current_tmp_table == tmp_table1 else tmp_table1
                        data.write.mode('overwrite').saveAsTable(next_tmp_table)
                        print(f"写入数据大小：{data.count()}")
                        os.system('sync')  # 刷新缓存
                        data.unpersist()
                        spark.catalog.clearCache()
                        print("重新读取最新清洗的数据...")
                        data = spark.sql(f"SELECT * FROM {next_tmp_table}")
                        print(f"读入数据大小：{data.count()}")
                        data.persist()
                        current_tmp_table = next_tmp_table
                        level_knowledge_status[level_index][node] = True

                    # 定义一个空集合
                    sset = set()
                    tset = set()
                    for m in models[node]:
                        sset = sset.union(m.source)
                        tset = tset.union(m.target)
                    sset = list(sset)  # 转换为列表
                    tset = list(tset)
                    print(f"  抽样处理：源属性 {sset} -> 目标属性 {node}")
                    sample_Block_df, error_threshold = Generate_Sample(
                        data, sset, tset, models=models[node], single_max=single_max
                    )
                    sample_df = sample_Block_df.toPandas()
                    print(f"数据块大小: {sample_df.shape[0]}")

                    preCleaners = [single for single in singles if
                                   any(attr_set in sset + [node] for attr_set in single.domain)]
                    _, output, _, _ = customclean(sample_df, precleaners=preCleaners)

                    blockModels = None
                    weights = [1] * len(models[node])
                    for model, weight in zip(models[node], weights):
                        if blockModels is None:
                            blockModels = model * weight
                        else:
                            blockModels += model * weight
                    partition = [list(model.source) for model in models[node]]
                    editRule1, output, editRuleList, _ = customclean(
                        output, cleaners=[blockModels], partition=partition, error_threshold=error_threshold
                    )
                    editRule *= editRule1
                else:
                    print(f"  当前节点: {node} 无可用清洗信号")

                editRuleLists.extend(editRuleList)
                editRules *= editRule  # 累积应用的清洗规则

                # 如果当前节点没有可用的清洗操作，标记为不需要再处理
                if not editRuleList:
                    level_clean_status[level_index][node] = True  # 标记该节点为无需再处理

                if str(node) in editRuleDict:
                    if isinstance(editRuleDict[str(node)], list):
                        editRuleDict[str(node)].extend(editRuleList)
                    else:
                        editRuleDict[str(node)] = editRuleList  # 假设之前不是列表，现在重置为新列表
                else:
                    editRuleDict[str(node)] = editRuleList  # 键不存在，创建新键并赋值为新列表

            print(f"{level} 的清洗完成")
            print("\n本层累积的编辑规则数:", str(len(editRuleLists)))

            if editRuleLists:  # 有编辑规则
                nextClean = True
                while True:
                    # 处理数据，返回处理后的数据和剩余规则
                    data, remaining_rules = transformRulesToSpark(
                        editRuleLists, data, batch_size=batch_size, maxhandle=maxhandle
                    )
                    print("正在写入数据...")
                    next_tmp_table = tmp_table2 if current_tmp_table == tmp_table1 else tmp_table1
                    data.write.mode('overwrite').saveAsTable(next_tmp_table)
                    print(f"写入数据大小：{data.count()}")
                    os.system('sync')  # 刷新缓存
                    data.unpersist()
                    spark.catalog.clearCache()
                    print("重新读取最新清洗的数据...")
                    data = spark.sql(f"SELECT * FROM {next_tmp_table}")
                    print(f"读入数据大小：{data.count()}")
                    data.persist()
                    current_tmp_table = next_tmp_table

                    if not remaining_rules:
                        print("所有规则处理完成")
                        break  # 所有规则处理完成，退出循环
                    print(f"有剩余的清洗操作没有应用，继续处理 {len(remaining_rules)} 个清洗操作")
                    editRuleLists = remaining_rules  # 使用剩余规则继续处理

                print(f"数据清洗后变动，重新进行节点 {level} 的清洗")
                # 不进行下一个 level 的清洗，重新在本 level 进行清洗
                break
            else:
                print("本层没有可以进行的清洗操作，进行下一层")

    print("\n清洗规则溯源分析:")
    grouped_opinfo = cleaner_grouping(nodes, models)
    group_weights = getOpWeights(editRuleDict, grouped_opinfo)
    print(group_weights)
    return data

def CleanonLocalWithnoSmple(spark, cleanners, data, table_path, batch_size=500, single_max=30000):
    current = 'Tmp1'
    all_detected_cells = []  # Accumulate (index, column) pairs detected across all iterations
    print("初始化清洗器和分析依赖关系...")
    Edges, singles, multis = PreParamClassier(cleanners)

    print("处理单属性清洗算子：")
    for single in singles:
        print(f"处理单属性清洗算子：{single}")
        # 获取当前单属性的域 (例如: "domain" 属性表示当前算子的目标属性)
        target_column = single.domain

        print(f"开始清洗属性 {target_column} 的数据")
        # 将 Spark DataFrame 转换为 Pandas DataFrame
        df_pandas = data.select(target_column).distinct().toPandas()

        if df_pandas.empty:
            print(f"属性 {target_column} 的数据为空，跳过清洗。")
            continue

        print(f"属性 {target_column} 的数据大小: {df_pandas.shape[0]}")

        # 调用 customclean 进行清洗操作
        preCleaners = [single]
        _, output, editRuleList, _ = customclean(df_pandas, precleaners=preCleaners)

        if editRuleList:
            # 如果有清洗操作规则，应用到 Spark DataFrame 上
            print(f"应用 {target_column} 的清洗规则，编辑规则数量: {len(editRuleList)}")
            all_detected_cells.extend(get_detected_cells(editRuleList, data))
            data, _ = transformRulesToSpark(editRuleList, data, batch_size=batch_size)
        else:
            print(f"属性 {target_column} 没有可应用的清洗规则。")

    source_sets, target_sets, explain, processing_order, plt = discover_cleaner_associations(Edges)
    print("执行层级和目标模型分类...")
    levels, models, nodes = associations_classier(multis, source_sets, target_sets)
    print("执行层级 (并行组):", levels)
    print("目标模型分类:", models)

    editRuleDict = {}  # 用于统计溯源权重
    editRules = NOOP()  # 初始化无操作规则
    nextClean = True

    level_clean_status = {}
    clean_attempts = {}  # 新增：记录每个节点的清洗次数

    while nextClean:
        nextClean = False

        for level_index, level in enumerate(nodes):
            # 如果该层级还未记录过清洗状态，则初始化
            if level_index not in level_clean_status:
                level_clean_status[level_index] = {node: False for node in level}
            if level_index not in clean_attempts:
                clean_attempts[level_index] = {node: 0 for node in level}

            print(f"\n处理第 {level_index + 1} 层级, 包含节点: {level}")
            editRuleLists = []  # 获取当前层级的清洗操作列表

            for node in level:
                # 只处理该层级中挖掘不到操作的节点
                if level_clean_status[level_index][node]:
                    print(f"  跳过已清洗结束的节点: {node}")
                    continue

                clean_attempts[level_index][node] += 1  # 增加清洗次数

                if clean_attempts[level_index][node] > 3:  # 超过3次则标记为完成
                    print(f"  当前节点 {node} 清洗次数超过限制，标记为完成")
                    level_clean_status[level_index][node] = True
                    continue

                editRule = NOOP()
                editRuleList = []

                if node in models and models[node]:
                    print(f"  当前节点: {node} 存在可用清洗信号")
                    sset = set()
                    tset = set()
                    for m in models[node]:
                        sset = sset.union(m.source)
                        tset = tset.union(m.target)
                    sset = list(sset)
                    tset = list(tset)

                    # 合并节点（来自环检测，形如 'HospitalName,ProviderNumber'）需 split 还原为真实列；
                    # 单点节点直接当列名。这样既支持双向 FD（环），又避免把合并字符串当 Spark 列名 select。
                    node_cols = node.split(',') if isinstance(node, str) and ',' in node else [node]
                    select_cols = list(dict.fromkeys(['index'] + sset + node_cols))  # 保持顺序去重

                    # 将 Spark DataFrame 转换为 Pandas DataFrame
                    df_pandas = data.select(select_cols).toPandas()
                    print(f"数据块大小: {df_pandas.shape[0]}")

                    preCleaners = [single for single in singles if single.domain in (sset + node_cols)]
                    _, output, _, _ = customclean(df_pandas, precleaners=preCleaners)

                    blockModels = None
                    weights = [1] * len(models[node])
                    for model, weight in zip(models[node], weights):
                        if blockModels is None:
                            blockModels = model * weight
                        else:
                            blockModels += model * weight

                    partition = [list(model.source) for model in models[node]]
                    print("分块属性:")
                    print(partition)
                    editRule1, output, editRuleList, _ = customclean(output, cleaners=[blockModels],
                                                                     partition=partition)
                    editRule *= editRule1
                else:
                    print(f"  当前节点: {node} 无可用清洗信号")

                editRuleLists.extend(editRuleList)
                editRules *= editRule

                if len(editRuleList) == 0:
                    print(f"  当前节点: {node} 无清洗操作")
                    level_clean_status[level_index][node] = True
                else:
                    print(f"  当前节点: {node} 有 {len(editRuleList)} 个清洗操作")

                if str(node) in editRuleDict:
                    if isinstance(editRuleDict[str(node)], list):
                        editRuleDict[str(node)].extend(editRuleList)
                    else:
                        editRuleDict[str(node)] = editRuleList
                else:
                    editRuleDict[str(node)] = editRuleList

            print(f"{level}的清洗完成")
            print("\n本层累积的编辑规则数:", str(len(editRuleLists)))

            if editRuleLists:
                nextClean = True
                all_detected_cells.extend(get_detected_cells(editRuleLists, data))
                data, _ = transformRulesToSpark(editRuleLists, data, batch_size=batch_size)
                break
            else:
                print("本层没有可以进行的清洗操作，进行下一层")
    print("\n清洗规则溯源分析:")
    grouped_opinfo = cleaner_grouping(nodes, models)
    single_opinfo = getSingle_opinfo(singles)
    group_weights = getOpWeights(editRuleDict, grouped_opinfo)
    print("\n清洗流程展示:")
    sorted_dict = sort_opinfo_by_weights(grouped_opinfo, group_weights)

    OpPlantuml = generate_plantuml_corrected(single_opinfo, grouped_opinfo, sorted_dict)
    PlantUML().process_str(OpPlantuml, directory=table_path)
    plt.savefig(rf"{table_path}/acplt.png", format="png")
    print("关联图存储到:", rf"{table_path}/acplt.png")

    # Save detected cells to CSV for separate detection evaluation
    if all_detected_cells:
        detected_df = pd.DataFrame(all_detected_cells, columns=['index', 'column'])
        detected_df = detected_df.drop_duplicates()
        detected_csv_path = os.path.join(table_path, 'detected_cells.csv')
        detected_df.to_csv(detected_csv_path, index=False)
        print(f"Detected cells saved to: {detected_csv_path} ({len(detected_df)} entries)")

    return data