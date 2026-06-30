from AnalyticsCache.cleaner_associations_cycle import discover_cleaner_associations, \
    associations_classier

# # 测试整合的代码
# 测试用例
edges = [
    (["A", "B"], ["C"]),
    (["C"], ["D"]),
    (["C"], ["E"]),
    (["H"], ["F"]),
    (["H"], ["G"]),
    (["E"], ["B"]),
    (["D"], ["H"]), # 新添加的依赖关系
    (["A"], ["M"]),
]

# 调用 DiscoverCleanerAssociations 函数进行测试
source_sets, target_sets, explain, pic, processing_order = discover_cleaner_associations(edges)

pic.axis('off')
pic.show()
print(source_sets)
print(target_sets)
# print('--------')
print(processing_order)

# 创建一个cleaner 对象列表
class Cleaner:
    def __init__(self, target,str):
        self.target = target
        self.str=str

    def __add__(self, other):
        return Cleaner(self.target | other.target)

    def __repr__(self):
        return f"Cleaner({self.str})"


multi = [Cleaner({"C"},'1'), Cleaner({"B"},'2'), Cleaner({"B"},'3'),Cleaner({"D"},'4'), Cleaner({"E"},'5'), Cleaner({"F"},'6'), Cleaner({"G"},'7')]

# 测试 AssociationsClassier
levels, models,nodes = associations_classier(multi, source_sets, target_sets)

# 输出并行级别和模型
print("并行级别:", levels)
print("节点:",  nodes)
print("模型:", models)

