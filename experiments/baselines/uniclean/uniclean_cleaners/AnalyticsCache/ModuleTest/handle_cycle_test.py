import matplotlib.pyplot as plt
import networkx as nx

# 创建有向图
G = nx.DiGraph()

# 添加边
edges = [
    ("A", "B"), ("B", "C"), ("C", "D"), ("C", "E"), ("H", "F"), ("H", "G"), ("G", "H")
]
G.add_edges_from(edges)


# 检测图中的环，并选择一个环进行合并
try:
    cycle = nx.find_cycle(G, orientation='original')
    super_node = '_'.join(sorted(set(cycle[i][0] for i in range(len(cycle)))))
    for edge in cycle:
        # 将环中的每个顶点的入边和出边重定向到新顶点
        in_edges = G.in_edges(edge[0], data=True)
        out_edges = G.out_edges(edge[0], data=True)
        for u, v, d in in_edges:
            if u not in cycle:
                G.add_edge(u, super_node, **d)
        for u, v, d in out_edges:
            if v not in cycle:
                G.add_edge(super_node, v, **d)
        # 移除原顶点
        G.remove_node(edge[0])

    print(f"合并顶点 {cycle} 为 {super_node}")
    print("新图的边:", G.edges(data=True))
except nx.NetworkXNoCycle:
    print("图中无环")

# 可视化新图

nx.draw(G, with_labels=True)
plt.show()
