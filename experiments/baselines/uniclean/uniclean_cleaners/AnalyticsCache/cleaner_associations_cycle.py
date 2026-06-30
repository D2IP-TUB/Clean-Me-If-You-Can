from collections import defaultdict, deque
from typing import List, Tuple, Dict, Set
import networkx as nx

from AnalyticsCache.get_cleaner_excute_info import draw_hierarchical_dependency_graph


def PreParamClassier(cleanners):
    # 初始化边缘列表和两种清洗器分类
    edges = []  # 用于存储边缘的列表
    single = []  # 存储单域清洗器
    multi = []  # 存储多域清洗器
    # 分类清洗器
    for cleaner in cleanners:
        if isinstance(cleaner.domain, set):
            # 如果清洗器的域是集合类型，则归类为多域清洗器
            multi.append(cleaner)
            for t in cleaner.target:
                s = cleaner.source.copy()
                if t in s:
                    s.remove(t)
                edges.append((s, [t]))
        else:
            # 否则归类为单域清洗器
            single.append(cleaner)
    return edges, single, multi


# 1. 构建依赖关系图
def build_dependency_graph(edges: List[Tuple[List[str], List[str]]]) -> nx.DiGraph:
    """从元组对构建依赖关系图"""
    graph = nx.DiGraph()
    for source, target in edges:
        for s in source:
            for t in target:
                graph.add_edge(s, t)
    return graph

# 2. 识别关键点
def identify_key_points(graph: nx.DiGraph) -> List[str]:
    """识别入度为0的关键点"""
    return [node for node in graph if graph.in_degree(node) == 0]

# 3. 合并环上的节点
def merge_cycles(graph: nx.DiGraph) -> nx.DiGraph:
    """合并图中的环节点"""
    node_mapping = {node: {node} for node in graph.nodes}
    while True:
        try:
            cycles = list(nx.simple_cycles(graph))
        except nx.NetworkXNoCycle:
            break
        if not cycles:
            break
        for cycle in cycles:
            cycle_nodes = set(cycle)
            merged_node = ','.join(sorted(cycle_nodes))
            node_mapping[merged_node] = set()
            for node in cycle_nodes:
                node_mapping[merged_node].update(node_mapping.pop(node))
            # Create a new graph with the merged node
            new_graph = nx.DiGraph()
            for node in graph.nodes:
                if node not in cycle_nodes:
                    new_graph.add_node(node)
            new_graph.add_node(merged_node)
            for u, v in graph.edges:
                if u in cycle_nodes and v in cycle_nodes:
                    continue
                if u in cycle_nodes:
                    new_graph.add_edge(merged_node, v)
                elif v in cycle_nodes:
                    new_graph.add_edge(u, merged_node)
                else:
                    new_graph.add_edge(u, v)
            graph = new_graph
            break
    return graph, node_mapping

# 4. 基于关键点划分图
def partition_graph(graph: nx.DiGraph, key_points: List[str]) -> List[Tuple[List[str], str]]:
    """基于关键点划分图"""
    partitions = []
    for key in key_points:
        dependent_nodes = nx.descendants(graph, key) | {key}
        for node in dependent_nodes:
            if graph.out_degree(node) > 0:
                targets = list(graph.successors(node))
                partitions.append((targets, node))
    return partitions

# 5. 确定处理顺序
def determine_processing_order(partitions: List[Tuple[List[str], str]]) -> List[Tuple[List[str], str]]:
    """确定处理顺序"""
    return sorted(partitions, key=lambda x: x[1])



# 8. 识别并分割出连通图
def find_connected_components(graph: nx.DiGraph) -> List[nx.DiGraph]:
    """识别并分割出连通图"""
    return [graph.subgraph(c).copy() for c in nx.weakly_connected_components(graph)]

# 9. 对连通图进行拓扑排序，检测循环依赖
def topological_sort_with_cycles(graph: nx.DiGraph) -> Tuple[List[str], bool]:
    """对连通图进行拓扑排序，检测循环依赖"""
    try:
        return list(nx.topological_sort(graph)), False  # No cycle
    except nx.NetworkXUnfeasible:
        return [], True  # Cycle detected

# 10. 找到每个连通图的起始节点
def find_starting_nodes(graph: nx.DiGraph, sorted_nodes: List[str]) -> List[str]:
    """找到每个连通图的起始节点"""
    in_degree = graph.in_degree()
    return [node for node in sorted_nodes if in_degree[node] == 0]

# 11. 分析依赖关系，返回连通图的信息
def analyze_dependencies(edges: List[Tuple[List[str], List[str]]]) -> Dict[str, Dict]:
    """分析依赖关系，返回连通图的信息"""
    dependency_graph = build_dependency_graph(edges)
    dependency_graph, node_mapping = merge_cycles(dependency_graph)
    connected_components = find_connected_components(dependency_graph)
    analysis = {}
    for i, component in enumerate(connected_components):
        order, has_cycle = topological_sort_with_cycles(component)
        start_nodes = find_starting_nodes(component, order) if not has_cycle else []
        analysis[f"Component_{i + 1}"] = {
            "Topological_Order": order,
            "Has_Cycle": has_cycle,
            "Starting_Nodes": start_nodes
        }
    return analysis, node_mapping

# 12. 将处理顺序转换为指定的格式
def format_combined_processing_order(processing_order: List[Tuple[List[str], str]], node_mapping: Dict[str, Set[str]]) -> List[Tuple[List[Set[str]], List[Set[str]]]]:
    """将处理顺序转换为指定的格式，其中合并相同目标的源点"""
    target_to_sources = {}
    for targets, source in processing_order:
        for target in targets:
            target_to_sources.setdefault(target, set()).add(source)
    formatted_order = []
    for target, sources in target_to_sources.items():
        formatted_order.append((list(map(lambda x: node_mapping[x], sources)), [node_mapping[target]]))
    return sorted(formatted_order, key=lambda x: len(x[0]))

# 13. 分析和可视化依赖关系
def analyze_and_visualize_dependencies(edges: List[Tuple[List[str], List[str]]]):
    """分析和可视化依赖关系"""
    analysis, node_mapping = analyze_dependencies(edges)
    dependency_graph = build_dependency_graph(edges)
    dependency_graph, node_mapping = merge_cycles(dependency_graph)
    key_points = identify_key_points(dependency_graph)
    partitions = partition_graph(dependency_graph, key_points)
    processing_order = determine_processing_order(partitions)
    format_processing_order = format_combined_processing_order(processing_order, node_mapping)
    draw_hierarchical_dependency_graph(dependency_graph, analysis)
    return analysis, format_processing_order
def analyze_and_visualize_dependencies_save_plt(edges: List[Tuple[List[str], List[str]]]):
    """分析和可视化依赖关系"""
    analysis, node_mapping = analyze_dependencies(edges)
    dependency_graph = build_dependency_graph(edges)
    dependency_graph, node_mapping = merge_cycles(dependency_graph)
    key_points = identify_key_points(dependency_graph)
    partitions = partition_graph(dependency_graph, key_points)
    processing_order = determine_processing_order(partitions)
    format_processing_order = format_combined_processing_order(processing_order, node_mapping)
    plt=draw_hierarchical_dependency_graph(dependency_graph, analysis)
    return analysis, format_processing_order,plt
# 生成用户友好的分析结果描述文本
def explain_analysis_results(analysis: Dict[str, Dict], processing_order: List[Tuple[List[Set[str]], List[Set[str]]]]) -> str:
    """生成用户友好的解释文本以描述分析结果和处理顺序"""
    explanation = ""

    # 解释分析结果
    for component, details in analysis.items():
        explanation += f"\n{component}:\n"
        explanation += f"  - Topological Order: {', '.join(details['Topological_Order'])}\n"
        explanation += f"  - Has Cyclic Dependencies: {'Yes' if details['Has_Cycle'] else 'No'}\n"
        explanation += f"  - Starting Nodes: {', '.join(details['Starting_Nodes'])}\n"

    # 解释处理顺序
    explanation += "\nProcessing Order:\n"
    for source_set, target_set in processing_order:
        source_str = ' and '.join([','.join(sorted(s)) for s in source_set])
        target_str = ' and '.join([','.join(sorted(t)) for t in target_set])
        explanation += f"  - When {source_str} are ready, {target_str} can be processed\n"

    return explanation

def extract_source_target_sets(processing_order: List[Tuple[List[Set[str]], List[Set[str]]]]):
    """提取处理顺序中的源集合和目标集合"""
    source_sets = []
    target_sets = []
    for sources, targets in processing_order:
        source_sets.append(sources)
        target_sets.append(targets)
    return source_sets, target_sets

def explain_analysis_results_zh(analyze: Dict[str, Dict],
                                processing_order: List[Tuple[List[Set[str]], List[Set[str]]]]):
    """生成用户友好的中文解释文本以描述分析结果和处理顺序"""
    explanation = "分析结果:\n"
    for component, data in analyze.items():
        explanation += f"{component} 拓扑顺序: {data['Topological_Order']}\n"
        explanation += f"{component} 是否存在环: {'是' if data['Has_Cycle'] else '否'}\n"
        explanation += f"{component} 起始节点: {data['Starting_Nodes']}\n"
    explanation += "\n处理顺序:\n"
    for sources, targets in processing_order:
        explanation += f"源: {sources} -> 目标: {targets}\n"
    return explanation

def discover_cleaner_associations(AttrDependencies):
    """分析和可视化属性依赖关系"""
    # 分析和可视化属性依赖
    analyze, processing_order,plt = analyze_and_visualize_dependencies_save_plt(AttrDependencies)
    # 提取源和目标集
    source_sets, target_sets = extract_source_target_sets(processing_order)
    # 解释结果
    explain = explain_analysis_results_zh(analyze, processing_order)

    return source_sets, target_sets, explain, processing_order,plt




def associations_classier(multi, source_sets: List[List[Set[str]]], target_sets: List[List[Set[str]]]):
    """对多域清洗器进行分类"""
    # 构建图和入度表
    graph = defaultdict(list)
    indegree = defaultdict(int)
    all_nodes = set()
    targets_in_use = set()  # 用于记录所有出现在 target_sets 中的节点

    # 填充图和入度表，同时记录使用的 target
    for sources, targets in zip(source_sets, target_sets):
        for target in targets:
            target_node = ','.join(sorted(target))
            targets_in_use.add(target_node)  # 记录出现的 target
            all_nodes.add(target_node)
            for source in sources:
                source_node = ','.join(sorted(source))
                all_nodes.add(source_node)
                graph[source_node].append(target_node)
                indegree[target_node] += 1

    # 过滤出只在 target_sets 中出现的节点
    filtered_nodes = {node for node in all_nodes if node in targets_in_use or any(
        node == ','.join(sorted(list(x))) for x in [item for sublist in source_sets for item in sublist])}

    # 使用拓扑排序找出可以并行的层级
    queue = deque([node for node in filtered_nodes if indegree[node] == 0])
    levels = []  # 存储可以并行的层级
    nodes = []
    # 转换 levels 以包含合并前的节点信息
    while queue:
        current_level = []
        current_nodes = []
        for _ in range(len(queue)):
            node = queue.popleft()
            current_level.append(set(node.split(',')))
            current_nodes.append(node)
            for adjacent in graph[node]:
                if adjacent in filtered_nodes:  # 确保仅考虑过滤后的节点
                    indegree[adjacent] -= 1
                    if indegree[adjacent] == 0:
                        queue.append(adjacent)
        levels.append(current_level)
        nodes.append(current_nodes)

    # 根据过滤后的结果创建模型
    models = defaultdict(list)  # 使用 list 初始化以支持添加 cleaner
    for cleaner in multi:
        for target in cleaner.target:  # cleaner.target可能是复数形式，从而有多个 target
            target_node = target
            for level in levels:
                for group in level:
                    if target_node in group:
                        models[','.join(sorted(group))].append(cleaner)
                        break

    return levels, dict(models), nodes  # 转换回普通字典以清理输出