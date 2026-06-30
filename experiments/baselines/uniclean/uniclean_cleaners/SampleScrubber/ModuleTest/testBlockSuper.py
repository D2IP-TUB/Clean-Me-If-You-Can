import pandas as pd


def find_blocks(df, partition, error_threshold):
    # Step 1: 初步分块，基于partition[0]的值分组，并建立每个组的索引映射
    initial_blocks = df.groupby(partition[0]).groups
    block_mapping = {}
    for key, indexes in initial_blocks.items():
        for index in indexes:
            block_mapping[index] = indexes

    # Step 2: 对每个后续属性进行迭代，根据这些属性的值合并块
    for attr in partition[1:]:
        # 对当前属性进行分组，获取值到索引的映射
        value_to_indexes = df.groupby(attr).groups

        # 遍历每个值对应的索引集合
        for indexes in value_to_indexes.values():
            if len(indexes) > 1:
                # 找到所有通过当前属性值连接的行索引集合
                connected_indexes = set()
                for index in indexes:
                    if df.loc[index, 'p'] < error_threshold:
                        connected_indexes.update(block_mapping[index])

                # 更新块映射，将所有连接的行索引合并为一个块
                if connected_indexes:
                    for index in connected_indexes:
                        block_mapping[index] = connected_indexes

    # 构建最终的块列表
    final_blocks = set()
    for indexes in block_mapping.values():
        final_blocks.add(frozenset(indexes))

    # 返回块的索引列表，每个块是索引的集合
    return [list(block) for block in final_blocks]


# 示例数据帧
data = {
    'A': [1, 1, 2, 2, 1],
    'B': [2, 2, 3, 3, 3],
    'C': [3, 4, 3, 4, 3],
    'p': [0.9, 0.05, 0.01, 0.1, 0.8]  # 错误概率列
}
df = pd.DataFrame(data)

# 使用函数进行分块
partition = [['A', 'B'], ['B','C']]
error_threshold = 0.7
blocks = find_blocks(df, partition, error_threshold)
print(blocks)
