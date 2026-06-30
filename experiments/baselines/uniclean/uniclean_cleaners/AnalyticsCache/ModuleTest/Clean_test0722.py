import os
from SampleScrubber.ModuleTest.SparkClean.spark_rule_model import Uniop as SparkRule
from AnalyticsCache.ModuleTest.transform_rules_test import spark
from AnalyticsCache.cleaner_associations_cycle import associations_classier, discover_cleaner_associations, \
    PreParamClassier
from AnalyticsCache.get_cleaner_excute_info import sort_opinfo_by_weights, generate_plantuml_corrected, \
    getSingle_opinfo, cleaner_grouping
from AnalyticsCache.handle_rules import getOpWeights,transformRulesToSpark
from AnalyticsCache.get_planuml_graph import PlantUML

from CoreSetSample.mapping_samplify import Generate_Sample, Generate_BlockSample
from CoreSetSample.ModuleTest.get_patition_block import find_blocks_spark
from SampleScrubber.param_selector import customclean
from SampleScrubber.cleaner_model import NOOP
def transformRules(EditRuleList):
    """
    转换编辑规则列表为 Spark 规则列表。

    参数：
    EditRuleList (list): 编辑规则列表。

    返回：
    list: Spark 规则列表。
    """
    SparkRuleList = []
    for EditRule in EditRuleList:
        column = EditRule.domain
        predicate = EditRule.predicate
        value = EditRule.repairvalue
        costfn = EditRule.name
        uniop = SparkRule(column=column,
                          predicate=predicate,
                          value=value,
                          costfn=costfn)
        SparkRuleList.append(uniop)
    return SparkRuleList


def applyRules(rules, data):
    """
    应用规则处理数据。

    参数：
    rules (list): 规则列表。
    data (pandas.DataFrame): 数据框。

    返回：
    pandas.DataFrame: 处理后的数据框。
    """
    for rule in rules:
        data = rule.run(data)
    return data

def CleanBlockonSingle(cleanners, data, table_name):
    # 初始化和分析清洗器
    nextClean=False
    print("初始化清洗器和分析依赖关系...")
    Edges, singles, multis = PreParamClassier(cleanners)
    source_sets, target_sets, explain, pic, processing_order = discover_cleaner_associations(Edges)
    print("执行层级和目标模型分类...")
    levels, models, nodes = associations_classier(multis, source_sets, target_sets)
    print("执行层级 (并行组):", levels)
    print("目标模型分类:", models)
    editRuleDict = {}  # 用于统计溯源权重
    for level_index, level in enumerate(nodes):
        print(f"\n处理第 {level_index + 1} 层级, 包含节点: {level}")
        editRuleLists = []  # 获取当前层级的清洗操作列表
        editRules = NOOP()  # 初始化无操作规则
        for node in level:
            # 初始化当前节点的清洗操作
            editRule = NOOP()
            editRuleList=[]
            if node in models and models[node]:
                # 定义一个空集合
                sset = set()
                tset = set()
                for m in models[node]:
                    sset = sset.union(m.source)
                    tset = tset.union(m.target)
                sset = list(sset)  # 变成列表
                tset = list(tset)
                print(f"  抽样处理：源属性 {sset} -> 目标属性 {node}")
                sample_Block_df, p_avg = Generate_Sample(data, sset, tset, models=models[node])
                # 在单节点上编排清洗规则
                sample_df = sample_Block_df.toPandas()
                print(f"数据块大小: {sample_df.shape[0]}")
                # sample_df.to_csv('output.csv', index=False)
                preCleaners = [single for single in singles if
                               any(attr_set in sset + [node] for attr_set in single.domain)]
                _, output, _, _ = customclean(sample_df, precleaners=preCleaners)
                #对块内算子加权计算
                blockModels = None
                weights = [1] * len(models[node])
                for model, weight in zip(models[node], weights):
                    if blockModels is None:
                        blockModels = model * weight
                    else:
                        blockModels += model * weight
                partition = []

                for model in models[node]:
                    partition.append(list(model.source))
                editRule1, output, editRuleList, _ = customclean(output, cleaners=[blockModels],
                                                                 partition=partition, error_threshold=p_avg)
                editRule *= editRule1
                editRuleLists.extend(editRuleList)
            # print(f"  当前流程挖掘的清洗规则:"+str(len(editRuleDict)))

            editRules *= editRule  # 累积应用的清洗规则
            editRuleDict[str(node)] = editRuleList

        print("\n本层累积的编辑规则数:", str(len(editRuleLists)))
        if editRuleLists:# 有编辑规则
            nextClean=True
            data = transformRulesToSpark(editRuleLists, data, batch_size=200)
            print("正在写入数据")
            data.coalesce(1).write.mode('overwrite').csv(table_name+'Tmp', header=True)
            print("写入数据大小：" + str(data.count()))
            os.system('sync')  # 刷新缓存
            data.unpersist()
            spark.catalog.clearCache()
            print("重新读取数据")
            data = spark.read.csv(table_name+'Tmp', header=True, inferSchema=True)
            print("读入数据大小" + str(data.count()))
            data.persist()

    print("\n清洗规则溯源分析:")
    grouped_opinfo = cleaner_grouping(nodes, models)
    single_opinfo = getSingle_opinfo(singles)
    group_weights = getOpWeights(editRuleDict, grouped_opinfo)
    print("\n清洗流程展示:")
    sorted_dict = sort_opinfo_by_weights(grouped_opinfo, group_weights)

    # 生成调整后的 PlantUML 文本,并且绘制 plantuml
    OpPlantuml = generate_plantuml_corrected(single_opinfo, grouped_opinfo, sorted_dict)
    # print(plantuml_text)
    PlantUML().process_str(OpPlantuml)
    print("\n绘制清洗流程图:", "Plantuml.svg")

    return nextClean,data


def CleanBlockonSpark(cleanners, data):
    # 初始化和分析清洗器
    print("初始化清洗器和分析依赖关系...")
    Edges, singles, multis = PreParamClassier(cleanners)
    source_sets, target_sets, explain, pic, processing_order = discover_cleaner_associations(Edges)

    print("执行层级和目标模型分类...")
    levels, models, nodes = associations_classier(multis, source_sets, target_sets)
    print("执行层级 (并行组):", levels)
    print("目标模型分类:", models)
    editRuleDict = {}
    editRuleLists = []
    editRules = NOOP()  # 初始化无操作规则
    for level_index, level in enumerate(nodes):
        print(f"\n处理第 {level_index + 1} 层级, 包含节点: {level}")

        for node in level:
            if node in models and models[node]:
                # 定义一个空集合
                sset = set()
                tset = set()
                for m in models[node]:
                    sset = sset.union(m.source)
                    tset = tset.union(m.target)
                sset = list(sset)  # 变成列表
                tset = list(tset)

                print(f"  抽样和分块处理：源属性 {sset} -> 目标属性 {node}")
                if len(tset) == 1:
                    sample_Block_df = Generate_BlockSample(data, sset, tset)
                else:
                    sample_Block_df = Generate_BlockSample(data, sset, tset, models=models[node])
                editRule = NOOP()
                editRuleList = []
                print(f"  分块数: {len(sample_Block_df)}")
                for blockData in sample_Block_df:
                    sample_df = blockData.toPandas()
                    print(f"数据块大小: {sample_df.shape[0]}")

                    preCleaners = [single for single in singles if
                                   any(attr_set in sset + [node] for attr_set in single.domain)]
                    _, output, _, _ = customclean(sample_df, precleaners=preCleaners)
                    blockmodels = None
                    weights = [1] * len(models[node])
                    for model, weight in zip(models[node], weights):
                        if blockmodels is None:
                            blockmodels = model * weight
                        else:
                            blockmodels += model * weight
                    editRule1, output, editRuleList1, _ = customclean(output, cleaners=[blockmodels])
                    editRule *= editRule1
                    editRuleList.extend(editRuleList1)
                # print(f"  当前流程挖掘的清洗规则: {editRule}")

                editRules *= editRule  # 累积应用的清洗规则
                editRuleLists.extend(editRuleList)
                editRuleDict[str(node)] = editRuleList

    print("\n累积的编辑规则:", str(len(editRuleDict)))

    print("\n清洗规则溯源分析:")
    grouped_opinfo = cleaner_grouping(nodes, models)
    single_opinfo = getSingle_opinfo(singles)
    group_weights = getOpWeights(editRuleDict, grouped_opinfo)
    print(group_weights)
    print("\n清洗流程展示:")
    sorted_dict = sort_opinfo_by_weights(grouped_opinfo, group_weights)

    # 生成调整后的 PlantUML 文本,并且绘制 plantuml
    OpPlantuml = generate_plantuml_corrected(single_opinfo, grouped_opinfo, sorted_dict)
    # print(plantuml_text)
    PlantUML().process_str(OpPlantuml)
    print("\n绘制清洗流程图:", "Plantuml.svg")

    print("\n应用挖掘到的编辑规则和清洗流程:")

    sparkEditRules = transformRules(editRuleLists)
    return sparkEditRules


def CleanBlockMix(cleanners, data, save_path, singleMax):
    # 初始化和分析清洗器
    print("初始化清洗器和分析依赖关系...")
    Edges, singles, multis = PreParamClassier(cleanners)
    source_sets, target_sets, explain, pic, processing_order = discover_cleaner_associations(Edges)

    print("执行层级和目标模型分类...")
    levels, models, nodes = associations_classier(multis, source_sets, target_sets)
    print("执行层级 (并行组):", levels)
    print("目标模型分类:", models)
    editRuleDict = {}
    editRuleLists = []
    editRules = NOOP()  # 初始化无操作规则
    for level_index, level in enumerate(nodes):
        print(f"\n处理第 {level_index + 1} 层级, 包含节点: {level}")

        for node in level:
            if node in models and models[node]:
                sset = set()
                tset = set()
                for m in models[node]:
                    sset = sset.union(m.source)
                    tset = tset.union(m.target)
                sset = list(sset)  # 变成列表
                tset = list(tset)

                print(f"  抽样处理：源属性 {sset} -> 目标属性 {node}")
                if len(tset) == 1:
                    sample_Block_df = Generate_Sample(data, sset, tset, save_path=save_path)
                else:
                    sample_Block_df = Generate_Sample(data, sset, tset, models=models[node], save_path=save_path)
                blockonSpark = False
                if sample_Block_df[0].count() > singleMax:
                    blockonSpark = True
                    sample_Block_df = find_blocks_spark(sample_Block_df[0], sset)
                editRule = NOOP()
                editRuleList = []
                print(f"  在 spark 的分块数: {len(sample_Block_df)}")
                for blockData in sample_Block_df:
                    sample_df = blockData.toPandas()
                    print(f"数据块大小: {sample_df.shape[0]}")

                    preCleaners = [single for single in singles if
                                   any(attr_set in sset + [node] for attr_set in single.domain)]
                    _, output, _, _ = customclean(sample_df, precleaners=preCleaners)
                    blockmodels = None
                    weights = [1] * len(models[node])
                    for model, weight in zip(models[node], weights):
                        if blockmodels is None:
                            blockmodels = model * weight
                        else:
                            blockmodels += model * weight
                    if blockonSpark:
                        editRule1, output, editRuleList1, _ = customclean(output, cleaners=[blockmodels])
                    else:
                        editRule1, output, editRuleList1, _ = customclean(output, cleaners=[blockmodels],
                                                                          partition=sset)
                    editRule *= editRule1
                    editRuleList.extend(editRuleList1)
                # print(f"  当前流程挖掘的清洗规则: {editRule}")

                editRules *= editRule  # 累积应用的清洗规则
                editRuleLists.extend(editRuleList)
                editRuleDict[str(node)] = editRuleList

    print("\n累积的编辑规则:", len(editRuleDict))

    print("\n清洗规则溯源分析:")
    grouped_opinfo = cleaner_grouping(nodes, models)
    single_opinfo = getSingle_opinfo(singles)
    group_weights = getOpWeights(editRuleDict, grouped_opinfo)
    print(group_weights)
    print("\n清洗流程展示:")
    sorted_dict = sort_opinfo_by_weights(grouped_opinfo, group_weights)

    # 生成调整后的 PlantUML 文本,并且绘制 plantuml
    OpPlantuml = generate_plantuml_corrected(single_opinfo, grouped_opinfo, sorted_dict)
    # print(plantuml_text)
    PlantUML().process_str(OpPlantuml)
    print("\n绘制清洗流程图:", "Plantuml.svg")

    print("\n应用挖掘到的编辑规则和清洗流程:")
    sparkEditRules = transformRules(editRuleLists)
    return sparkEditRules
