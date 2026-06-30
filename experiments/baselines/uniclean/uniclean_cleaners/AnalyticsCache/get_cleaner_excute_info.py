import matplotlib.pyplot as plt
import networkx as nx
from typing import Dict, Tuple


def sort_opinfo_by_weights(grouped_opinfo_dict, group_weights):
    """根据权重对分组操作信息进行排序"""
    sorted_dict = {}

    for level in grouped_opinfo_dict:
        nodes = grouped_opinfo_dict[level]
        for targetNode in nodes:
            weights = group_weights[targetNode]
            weighted_ops = []
            for cleaner in nodes[targetNode]:
                weighted_ops.append((cleaner, weights[nodes[targetNode].index(cleaner)]))

            sorted_ops = sorted(weighted_ops, key=lambda x: x[1], reverse=True)
            sorted_dict[targetNode] = sorted_ops

    return sorted_dict

# 6. 计算节点层级

def compute_node_levels(graph: nx.DiGraph) -> Dict[str, int]:
    """计算图中每个节点的层级（最大深度）"""
    levels = {node: 0 for node in graph}
    for node in nx.topological_sort(graph):
        levels[node] = max([levels[pred] + 1 for pred in graph.predecessors(node)], default=0)
    return levels


# 7. 层次布局
def hierarchical_layout(graph: nx.DiGraph, vertical_gap: float = 1.0, horizontal_gap: float = 2.0) -> Dict[str, Tuple[float, float]]:
    """为图生成层次布局"""
    levels = compute_node_levels(graph)
    level_groups = {}
    for node, level in levels.items():
        level_groups.setdefault(level, []).append(node)
    pos = {}
    for level, nodes in level_groups.items():
        for i, node in enumerate(sorted(nodes)):
            pos[node] = (i * horizontal_gap, -level * vertical_gap)
    return pos
def draw_hierarchical_dependency_graph(dependency_graph, analysis):
    """
    绘制层次依赖图

    参数：
    dependency_graph : networkx.DiGraph
        依赖图
    analysis : dict
        分析结果，包括起始节点的列表

    输出：
    绘制依赖图并显示
    """
    plt.figure(figsize=(15, 11))
    pos = hierarchical_layout(dependency_graph, vertical_gap=2, horizontal_gap=2)  # 调整布局参数
    # 绘制节点
    start_nodes = [node for comp in analysis.values() for node in comp["Starting_Nodes"]]
    end_nodes = [node for node in dependency_graph.nodes() if node not in start_nodes]
    nx.draw_networkx_nodes(dependency_graph, pos, nodelist=end_nodes, node_color='skyblue', node_size=4000)
    # 标签字体
    nx.draw_networkx_labels(dependency_graph, pos, font_size=32)
    # 高亮起始节点
    nx.draw_networkx_nodes(dependency_graph, pos, nodelist=start_nodes, node_color='lightgreen', node_size=3000)
    # 绘制边线条
    nx.draw_networkx_edges(dependency_graph, pos, arrowstyle='->', arrowsize=60, edge_color='gray', width=5)
    plt.title('Hierarchical Dependency Graph', fontsize=20)
    plt.axis('off')
    # plt.show()
    return plt

def getSingle_opinfo(singles):
    """提取单属性清洗器的信息"""
    singleDomain = []
    singlesInfo = []
    for single in singles:
        singleop = dict()
        singleDomain.append(single.domain)
        singleop['name'] = single.name
        singleop['type'] = 'single'
        singleop['attr'] = single.domain
        singleop['format'] = str(single.format)
        singlesInfo.append(singleop)
    return singlesInfo


def cleaner_grouping(processing_order, models):
    """根据处理顺序和模型分组清洗器"""
    groups = {}
    for level_index, level in enumerate(processing_order):
        print(f"\n处理第 {level_index + 1} 层级, 包含节点: {level}")
        group = {}
        for node in level:
            if node in models and models[node]:
                group[node] = models[node]
        if group:  # 仅在 group 非空时添加到 groups
            groups[level_index] = group
    return groups


def generate_plantuml_corrected(singleCleaners, groupCleaners, dependencies):
    """生成 PlantUML 文本以展示清洗器的执行顺序"""
    plantuml_text = "@startuml\n"
    plantuml_text += "!define RectOperator(x) class x << (O, orchid) >>\n\n"
    plantuml_text += "skinparam rectangle {\n"
    plantuml_text += "    BackgroundColor<<O>> LightBlue\n"
    plantuml_text += "    BorderColor Black\n"
    plantuml_text += "    ArrowColor Black\n"
    plantuml_text += "}\n\n"
    plantuml_text += "title Coarse-grained Cleaner Execution Order Recommendation\n\n"
    plantuml_text += "'移除之前的布局设置\n"
    plantuml_text += "hide empty description\n"
    plantuml_text += "hide empty methods\n"
    plantuml_text += "hide empty fields\n\n"

    single_end = "SINGLE_END"
    plantuml_text += f"RectOperator({single_end})\n\n"
    last_single = ''
    for i in range(len(groupCleaners)):
        plantuml_text += f"RectOperator(level_{i+1}_end)\n\n"
    for group, cleaners in groupCleaners.items():
        for targetNode, cleaner_list in cleaners.items():
            for index, cleaner in enumerate(cleaner_list):
                cleanername = cleaner.name
                plantuml_text += f"RectOperator({cleanername})\n"
                plantuml_text += f"{cleanername} : source={''.join(cleaner.source)}\n"
                plantuml_text += f"{cleanername} : target={''.join(cleaner.target)}\n"
    for index, cleaner in enumerate(singleCleaners):
        plantuml_text += f"RectOperator({cleaner['name']})\n"
        plantuml_text += f"{cleaner['name']} : {cleaner['attr']}\n"
        plantuml_text += f"{cleaner['name']} : {cleaner['format']}\n"
        # 单属性cleaner连接到SINGLE_END
        if last_single:
            plantuml_text += f"{last_single} <-right-> {cleaner['name']} : parallel\n"
        last_single = f"{cleaner['name']}"
        plantuml_text += f"{last_single} -down-> {single_end} : next\n"

    first_group_Cleaner = single_end
    for level, groups in groupCleaners.items():
        for targetNode, _ in groups.items():
            sorted_cleaners = dependencies[targetNode]
            plantuml_text += f"{first_group_Cleaner} -down-> {sorted_cleaners[0][0].name} : next\n"
            for i in range(1, len(sorted_cleaners)):
                plantuml_text += f"{sorted_cleaners[i - 1][0].name} -down-> {sorted_cleaners[i][0].name} : next\n"
            plantuml_text += f"{sorted_cleaners[len(sorted_cleaners)-1][0].name} -down-> level_{level+1}_end : next\n"
        first_group_Cleaner = f"level_{level+1}_end"
    plantuml_text += "@enduml"
    return plantuml_text


def explain_cleaners_process(cleaners, dependencies):
    """解释清洗器的处理流程"""
    explanation = "Process Explanation:\n\n"
    explanation += "**1. Single-attribute cleaners** (cleaner type as 'single') are executed first and are parallel to each other. Specifically, this includes:\n"
    single_cleaners = [cleaner["name"] for cleaner in cleaners if cleaner["type"] == "single"]
    for single in single_cleaners:
        explanation += f"   - {single}\n"
    explanation += "Once these single-attribute cleaners are completed, they move to the next stage, collectively marked as 'SINGLE_END'.\n\n"

    explanation += "**2. Multi-attribute cleaners** (cleaner type as 'multi') are executed according to their categories, with cleaners within each category following a specific order, and the categories themselves are parallel to each other. The specific categories and their execution order are as follows:\n"
    for I, group in enumerate(dependencies, start=1):
        explanation += f"   Category {I}:\n"
        for cleaner_name in group:
            explanation += f"      - {cleaner_name}\n"
        explanation += "   Within this category, cleaners are executed in the order listed above.\n\n"

    explanation += "**3. The first cleaner of each multi-attribute cleaner category is connected to the 'SINGLE_END' node**, indicating that these multi-attribute cleaner categories will start executing in parallel after the completion of single-attribute cleaners.\n\n"
    explanation += "**4. The first cleaner of multi-attribute cleaner categories are connected in parallel to each other**, indicating they will start executing simultaneously.\n"

    return explanation