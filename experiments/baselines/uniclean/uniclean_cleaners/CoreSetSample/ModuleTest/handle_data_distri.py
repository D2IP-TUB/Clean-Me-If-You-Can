import math
import os
from math import ceil

import matplotlib.pyplot as plt
import numpy as np
from pyspark.sql import Window
from pyspark.sql.functions import collect_set, struct, row_number
from sklearn.cluster import KMeans
from sklearn.manifold import MDS

"""Module: handleCore
    根据数据集的特征，处理数据集的核心集
"""

# getCoreId 函数用于处理每个数据分割，并生成样本ID。
def getCoreId(data, getGraph, save_path, indexplt, sourceSet=None, targetSet=None):
    # 创建新旧ID的映射
    init_clusters = 10
    error_p = 0.01  # 估计一个数据集的错误率
    minMember = 3
    onlyTargetSet = False
    if sourceSet is None:
        sourceSet = []
        targetSet = data.columns
    index_to_old_id = {}
    # 定义Spark窗口规范以创建从1开始的按需递增索引
    windowSpec = Window.orderBy(sourceSet[0])
    data = data.withColumn("new_index", row_number().over(windowSpec))
    # 初始化距离矩阵
    num_rows = data.count()
    clusters = 0
    distance = np.zeros((num_rows, num_rows))
    sourceLen = 1
    # 遍历所有属性，构建距离矩阵
    # 首先分析 sourceSet
    grouped_data = data.groupBy(*sourceSet).agg(
        collect_set(struct('index', 'new_index')).alias('id_pairs')
    ).collect()

    if (len(grouped_data) <= (num_rows / minMember)):#平均一组至少有一定数量才能挖掘清洗标签
        clusters += len(grouped_data)
        sourceLen = len(grouped_data)
    else: # grouped_data太多了，说明这个sourceset很分散
        onlyTargetSet = True
    distance_matrix = np.ones((num_rows, num_rows))
    # 构造距离矩阵
    for group in grouped_data:
        id_pairs = group['id_pairs']
        for pair in id_pairs:
            old_id = pair['index']
            new_id = pair['new_index']
            index_to_old_id[new_id] = old_id  # 构建映射
            for pair2 in id_pairs:
                distance_matrix[new_id - 1][pair2['new_index'] - 1] = 0  # 将距离矩阵中对应的位置置为 0

    distance += distance_matrix
    maxTargetGroup = 0
    # 下面分析targetSet
    for attribute in targetSet:
        # 分组并收集行号
        grouped_data = data.groupBy(attribute).agg(
            collect_set(struct('index', 'new_index')).alias('id_pairs')).collect()
        # print(grouped_data)
        if onlyTargetSet:
            if (len(grouped_data) <= (num_rows / minMember)):
                maxTargetGroup = max(len(grouped_data), maxTargetGroup)  # 找到最大的组合作为基础组合
            else:
                maxTargetGroup = 0
        clusters += math.ceil(sourceLen * len(grouped_data) * error_p)  # 意外的组合
        distance_matrix = np.ones((num_rows, num_rows))

        # 构造距离矩阵
        for group in grouped_data:
            id_pairs = group['id_pairs']
            for pair in id_pairs:
                old_id = pair['index']
                new_id = pair['new_index']
                index_to_old_id[new_id] = old_id  # 构建映射
                for pair2 in id_pairs:
                    distance_matrix[new_id - 1][pair2['new_index'] - 1] = 0  # 将距离矩阵中对应的位置置为 0

        distance += distance_matrix
    # clusters = int(clusters / len(targetSet))
    clusters += maxTargetGroup
    if clusters > num_rows / minMember:  # 说明数据点都很分散，没必要按照属性分组聚类，只需要提取最关键的特征
        clusters = math.ceil(num_rows * error_p) + 1
    # distance=np.sqrt(distance)
    # print("distance matrix is:")
    # print(distance)
    # 使用MDS和K-means进行样本选择
    return getSampleId(distance, clusters, index_to_old_id, getGraph, save_path, indexplt)


# getSampleId 函数使用MDS降维和K-means聚类选择样本ID。
def getSampleId(distances, clusters, index_to_old_id, getGraph, save_path, indexplt):
    # 使用MDS进行降维

    print("begin for mds")
    # 判断是否全为 0
    is_all_zero = np.all(distances == 0)
    if is_all_zero:
        clusters=1
        kmeans = KMeans(n_clusters=clusters, n_init=20)
        embedded_points=distances
        kmeans.fit(distances)
    else:
        mds = MDS(dissimilarity='precomputed', metric=True, normalized_stress='auto')
        embedded_points = mds.fit_transform(distances)
        # 使用K-means聚类
        print("begin for kmeans")
        kmeans = KMeans(n_clusters=clusters, n_init=20)
        kmeans.fit(embedded_points)
    labels = kmeans.labels_
    # 获取每个聚类中的数据点数量
    unique, counts = np.unique(labels, return_counts=True)
    cluster_sizes = dict(zip(unique, counts))

    # 找到最大值和最小值
    min_size = min(cluster_sizes.values())

    p=1.0/min_size
    # print("ok for kmeans")
    # 按照p的比例随机抽取每个聚类的ID
    selected_ids = []
    special_points = []
    for cluster_id in set(labels):  # 遍历每个聚类
        cluster_indices = np.where(labels == cluster_id)[0]  # 找到该聚类的所有点的索引,数组索引是从0开始的
        num_selected = ceil(len(cluster_indices) * p)  # 选取的点的数量
        if num_selected == 1:
            special_points.append(index_to_old_id[int(cluster_indices[0]) + 1])
        selected_indices = np.random.choice(cluster_indices, num_selected, replace=False)
        selected_ids.extend(selected_indices)  # 将选取的点的索引加入到列表中

    # 将选中的样本ID映射回原始ID
    sampleId = [index_to_old_id[int(sample) + 1] for sample in selected_ids]

    # # 打印和可视化结果
    # print("Sample IDs:", sampleId)
    # print("Number of Sample IDs:", len(sampleId))
    # print("Special Sample IDs:", special_points)
    # print("Number of Special Sample IDs:", len(special_points))
    if getGraph:
        showPLT(embedded_points, labels, selected_ids, save_path, indexplt, special_points)
    return sampleId, special_points


def showPLT(embedded_points, labels, group_selected_ids, save_path, indexplt, special_points):
    # 绘制第一张图：基本地聚类结果
    plt.figure()  # 开始一个新的绘图
    plt.scatter(embedded_points[:, 0], embedded_points[:, 1], c=labels, cmap='viridis', s=15)
    plt.colorbar()
    # 绘制聚类之间的连接线(有时候连线太费时了)
    if (len(set(labels)) > 200 or indexplt):
        for i in range(len(embedded_points)):
            for j in range(i + 1, len(embedded_points)):
                if labels[i] == labels[j]:
                    plt.plot([embedded_points[i, 0], embedded_points[j, 0]],
                             [embedded_points[i, 1], embedded_points[j, 1]],
                             'k-', alpha=0.5)
    # # 打印抽取到的ID值
    # print("group Selected IDs(-1):", group_selected_ids)
    # 绘制采样后的点
    sampled_points = embedded_points[group_selected_ids]
    sampled_labels = labels[group_selected_ids]
    plt.scatter(sampled_points[:, 0], sampled_points[:, 1], c=sampled_labels, cmap='viridis', marker='x',
                label='Selected', s=50)
    plt.legend()
    if indexplt:
        # 在图中标注点的索引
        for i, label in enumerate(labels):
            plt.annotate(i + 1, (embedded_points[i, 0], embedded_points[i, 1]), textcoords="offset points",
                         xytext=(0, 10),
                         ha='center', fontsize=8)

        # group_selected_ids = [0, 3, 2, 6, 9]
        # plt.show()
        if not os.path.exists(save_path):
            os.makedirs(save_path)
        plt.savefig(save_path + '/result.png', dpi=500, bbox_inches='tight')  # 解决图片不清晰，不完整的问题
        return 0
    else:
        # # 在图中标注特殊点的索引
        # for i, label in enumerate(labels):
        #     if (i + 1) not in special_points:
        #         continue
        #     plt.annotate(i + 1, (embedded_points[i, 0], embedded_points[i, 1]), textcoords="offset points",
        #                  xytext=(0, 10),
        #                  ha='center', fontsize=8)

        # group_selected_ids = [0, 3, 2, 6, 9]
        # plt.show()
        if not os.path.exists(save_path):
            os.makedirs(save_path)
        plt.savefig(save_path + '/NoIndexResult1.png', dpi=500, bbox_inches='tight')  # 解决图片不清晰，不完整的问题
        return 0


# landmark_mds 函数是一个降维方法，使用landmark点对数据进行MDS降维。
def landmark_mds(distance_matrix, k=2):
    n = distance_matrix.shape[0]  # 数据点数量
    n_landmarks = 60  # landmark点的数量
    # 随机选择一些landmark点
    landmarks = np.random.choice(n, size=n_landmarks, replace=False)
    # 计算landmark点之间的距离
    landmark_distances = distance_matrix[landmarks][:, landmarks]
    # 使用MDS算法降维landmark点
    mds = MDS(n_components=k, dissimilarity='precomputed')
    landmark_embeddings = mds.fit_transform(landmark_distances)
    # 使用landmark点的降维结果对所有数据点进行估计
    embeddings = np.zeros((n, k))
    for i in range(n):
        d = distance_matrix[i][landmarks]
        embeddings[i] = np.linalg.lstsq(landmark_distances, d, rcond=None)[0].dot(landmark_embeddings)
    return embeddings
