def AssociationsClassier(multi, source_sets, target_sets):
    from collections import defaultdict, deque

    # 构建图和入度表
    graph = defaultdict(list)
    indegree = defaultdict(int)
    all_nodes = set()
    targets_in_use = set()  # 用于记录所有出现在 target_sets 中的节点

    # 填充图和入度表，同时记录使用的 target
    for sources, targets in zip(source_sets, target_sets):
        for target in targets:
            targets_in_use.add(target)  # 记录出现的 target
            all_nodes.add(target)
            for source in sources:
                all_nodes.add(source)
                graph[source].append(target)
                indegree[target] += 1

    # 过滤出只在 target_sets 中出现的 nodes
    filtered_nodes = {node for node in all_nodes if node in targets_in_use or any(node in src for src in source_sets)}

    # 使用拓扑排序找出可以并行的级别
    queue = deque([node for node in filtered_nodes if indegree[node] == 0])
    levels = []  # 存储可以并行的层级

    while queue:
        current_level = []
        for _ in range(len(queue)):
            node = queue.popleft()
            current_level.append(node)
            for adjacent in graph[node]:
                if adjacent in filtered_nodes:  # 确保仅考虑过滤后的节点
                    indegree[adjacent] -= 1
                    if indegree[adjacent] == 0:
                        queue.append(adjacent)
        levels.append(current_level)

    # 根据过滤后的结果创建模型
    models = {node: [] for node in targets_in_use}
    for cleaner in multi:
        target = cleaner['target']  # cleaner.target 是单一目标属性
        if target in models:  # 确保只创建使用中的 target 的模型
            models[target].append(cleaner)

    return levels, models

# 示例调用
multi = [
    {'cleaner': 'Cleaner1', 'sources': ['gender'], 'target': 'zip'},
    {'cleaner': 'Cleaner2', 'sources': ['zip'], 'target': 'city'},
    {'cleaner': 'Cleaner3', 'sources': ['areacode', 'zip'], 'target': 'state'},
    {'cleaner': 'Cleaner4', 'sources': ['fname', 'lname'], 'target': 'gender'}
]
source_sets = [['gender'], ['zip'], ['areacode', 'zip'], ['fname', 'lname']]
target_sets = [['zip'], ['city'], ['state'], ['gender']]
levels, models = AssociationsClassier(multi, source_sets, target_sets)
print("Execution Levels (Parallel Groups):", levels)
print("Models by Target:", models)
