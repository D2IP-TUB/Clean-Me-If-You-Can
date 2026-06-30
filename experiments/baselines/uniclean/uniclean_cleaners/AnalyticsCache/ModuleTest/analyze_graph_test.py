from AnalyticsCache.cleaner_associations_cycle import analyze_and_visualize_dependencies, associations_classier, \
    discover_cleaner_associations

# 测试整合的代码
edges = [
    (["A", "B"], ["C"]),
    (["C"], ["D"]),
    (["C"], ["E"]),
    (["H"], ["F"]),
    (["H"], ["G"]),
    (["E"], ["B"]),
    (["D"], ["H"])  # 新添加的依赖关系
]

analyze, processing_order = analyze_and_visualize_dependencies(edges)
# pic.axis('off')
# pic.show()

# 测试整合的代码
edges = [
    (["A", "B"], ["C"]),
    (["C"], ["D"]),
    (["C"], ["E"]),
    (["H"], ["F"]),
    (["H"], ["G"]),
    # (["C"], ["B"]),
]

analyze, processing_order = analyze_and_visualize_dependencies(edges)
# pic.axis('off')
# pic.show()


# 测试用例
edges = [
    (["A", "B"], ["C"]),
    (["C"], ["D"]),
    (["C"], ["E"]),
    (["H"], ["F"]),
    (["H"], ["G"]),
    (["E"], ["B"]),
    (["D"], ["H"])  # 新添加的依赖关系
]

# 调用 DiscoverCleanerAssociations 函数进行测试
source_sets, target_sets, explain, processing_order = discover_cleaner_associations(edges)

# 输出解释结果
print(explain)


# 测试 AssociationsClassier
# 假设 multi 是一个包含目标的对象列表，并支持加法操作
class Cleaner:
    def __init__(self, target):
        self.target = target

    def __add__(self, other):
        # 定义合并逻辑，返回一个新的 Cleaner 实例
        return Cleaner(self.target | other.target)


# 创建一个示例的 cleaner 对象列表
multi = [Cleaner({"C"}), Cleaner({"D"}), Cleaner({"E"}), Cleaner({"F"}), Cleaner({"G"})]

levels, models, _ = associations_classier(multi, source_sets, target_sets)

# 输出并行级别和模型
print("并行级别:", levels)
print("模型:", models)
