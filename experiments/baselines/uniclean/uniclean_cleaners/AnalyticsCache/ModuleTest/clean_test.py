#这个是一键端的启动脚本
import time

import logsetting
from AnalyticsCache.ModuleTest.handleSparkRule import transformRules
from AnalyticsCache.handle_rules import applyRules
from SampleScrubber.cleaner.multiple import AttrRelation
from SampleScrubber.cleaner.single import Pattern
from AnalyticsCache.cleaner_associations_cycle import associations_classier, discover_cleaner_associations, PreParamClassier
from AnalyticsCache.get_cleaner_excute_info import cleaner_grouping, sort_opinfo_by_weights, generate_plantuml_corrected, \
    getSingle_opinfo
from AnalyticsCache.handle_rules import getOpWeights
from AnalyticsCache.get_planuml_graph import PlantUML

from SampleScrubber.cleaner_model import NOOP
def Clean(cleanners,file_load,save_path):
    # 初始化和分析清洗器
    print("初始化清洗器和分析依赖关系...")
    Edges, singles, multis = PreParamClassier(cleanners)
    source_sets, target_sets, explain, pic, processing_order = discover_cleaner_associations(Edges)

    print("执行层级和目标模型分类...")
    levels, models,nodes = associations_classier(multis, source_sets, target_sets)
    print("执行层级 (并行组):", levels)
    print("目标模型分类:", models)
    editRuleDict={}
    editRuleLists = []
    editRules = NOOP()  # 初始化无操作规则
    for level_index, level in enumerate(nodes):
        print(f"\n处理第 {level_index + 1} 层级, 包含节点: {level}")

        for node in level:
            if node in models and models[node]:
                for model in models[node]:
                    sset = model.source
                    tset=model.target
                    print(f"  抽样处理：源属性 {sset} -> 目标属性 {tset}")
                    print(f"  执行清洗算子: {str(model)}")

                # sample_df,data = Generate_Sample(file_load, sset, [node], 0.3, save_path=save_path)
                sample_df=[]
                # print(f"  抽样数据行数: {sample_df.shape[0]}")
                editRule=NOOP()
                editRuleList=[]
                # preCleaners = [single for single in singles if
                #                any(attr_set in sset + [node] for attr_set in single.domain)]
                # _, output, _, _ = customclean(sample_df, precleaners=preCleaners)

                # editRule, output, editRuleList, _ = customclean(output, cleaners=[models[node]], partition=sset)

                print(f"  关联块内挖掘的清洗规则: {editRule}")

                editRules *= editRule  # 累积应用的清洗规则
                editRuleLists.extend(editRuleList)
                editRuleDict[str(node)]=editRuleList

    print("\n累积的编辑规则:", editRuleDict)


    print("\n清洗规则溯源分析:")
    # opInfo = readOpInfo(op_path)
    grouped_opinfo = cleaner_grouping(nodes, models)
    single_opinfo = getSingle_opinfo(singles)
    group_weights = getOpWeights(editRuleDict, grouped_opinfo)
    print(group_weights)
    print("\n清洗流程展示:")
    sorted_dict = sort_opinfo_by_weights(grouped_opinfo, group_weights)

    # dependencies = [[cleaner['name'] for cleaner in group] for group in grouped_opinfo]
    # 更新后的依赖关系，分开定义执行顺序和parallel关系

    # 生成调整后的 PlantUML 文本,并且绘制 plantuml
    OpPlantuml = generate_plantuml_corrected(single_opinfo, grouped_opinfo, sorted_dict)
    # print(plantuml_text)
    PlantUML().process_str(OpPlantuml)
    print("\n绘制清洗流程图:","Plantuml.svg")

    print("\n应用挖掘到的编辑规则和清洗流程:")
    sparkEditRules = transformRules(editRuleLists)
    return sparkEditRules


cleanners = [
    Pattern('gender', "[M|F]", "genderPattern"),
    Pattern('areacode', "[0-9]{3}","areacodePattern"),
    Pattern('state', "[A-Z]{2}", "statePattern"),
    AttrRelation(["zip"], ["areacode"], "ZipToAreacodeFD"),
    AttrRelation(['state'], ["zip"], "StateToZipFD"),
    AttrRelation(['zip'], ["state"], "ZipToStateFD"),
    AttrRelation(['areacode'], ["state"], "AreacodeToStateFD"),
    AttrRelation(["zip"], ["city"], "ZiptoCityFD"),
    AttrRelation(["zip"], ["attr1"], "Ziptoattr1"),
    AttrRelation(["attr1"], ["attr2"], "attr1toattr2"),
    AttrRelation(["attr1"], ["attr2"], "attr1toattr21"),
    AttrRelation(["fname", "lname"], ["gender"], "NameToGenderFD")
]
file_load = 'TestDataset/standardData/tax_200k/dirty_ramdon_0.5/dirty_tax.csv'
save_path = 'TestDataset/CoreSetOutput/tax_200k_clean_core'
#以上为输入部分


if __name__ == '__main__':
    print("Logs saved in " + logsetting.logfilename);
    # 使用 time.time() 计时
    start_time = time.perf_counter()
    rules=Clean(cleanners,file_load, save_path)
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    print(f"执行时间: {elapsed_time:.4f} 秒")
    data=applyRules(rules, file_load)