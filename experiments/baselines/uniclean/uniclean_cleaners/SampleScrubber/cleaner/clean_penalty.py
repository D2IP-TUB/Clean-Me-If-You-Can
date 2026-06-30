import numpy as np
import pandas as pd

from SampleScrubber.cleaner_model import CleanerModel
from SampleScrubber.util import distance


class EditPenalty(CleanerModel):
    """EditPenalty 代表在质量评估中的惩罚，惩罚对数据集的修改。
     将数据变化与当前数据集进行比较并对更改进行评分获取编辑惩罚值。
    """

    def __init__(self, dataset, domain, metric={}, w2vModel=None):
        """构造函数接受一个数据集和一个字典，将属性映射到相似度度量。
        source -- a dataframe
        metric -- 度量，一个字典映射，将属性映射到相似度度量，包括三种相似度度量方式：['jaccard', 'semantic', 'edit'].
        w2vModel -- 语义相似度（'semantic'）模型
        """
        self.source_dataset = dataset
        # 默认设置为‘edit’相似度
        self.metric = {s: 'edit' for s in dataset.columns.values}
        # 默认不使用语义相似度
        semantic = False
        for m in metric:  # m是属性名
            self.metric[m] = metric[m]
            if metric[m] == 'semantic':
                semantic = True
        self.word_vectors = w2vModel
        if semantic and w2vModel is None:
            raise ValueError("如果您使用语义相似度，请提供一个word2vec模型")
        self.cache = {}
        super().__init__(domain=domain)  # 调用父类的构造函数并传递必要的参数
    def _quality(self, df):
        N = df.shape[0]
        p = df.shape[1]
        qfn_a = np.zeros((N,))  # qfn_a是一个质量评估的结果
        if self.source_dataset.shape != df.shape:  # 如果两个数据集的形状不一样，返回一个全1的数组
            return np.ones((N,))
        for i in range(N):
            for j in self.domain:
                target = str(df.iloc[i][j])
                source = str(self.source_dataset.iloc[i][j])  # 注意如果str(None)返回None而不是空字符
                cname = j  # cname是属性名
                # 快速判断一些特殊情况
                if target == source:
                    continue
                elif df.iloc[i][j] is None:
                    continue
                elif self.source_dataset.iloc[i][j] is None:
                    qfn_a[i] = 1.0 / p + qfn_a[i]
                    continue
                elif target == '' and source != target:
                    qfn_a[i] = 1.0 / p + qfn_a[i]
                    continue
                elif source == '' and source != target:
                    qfn_a[i] = 1.0 / p + qfn_a[i]
                    continue

                if self.metric[cname] == 'edit':
                    qfn_a[i] = self.edit(target, source) / p + qfn_a[i]
                elif self.metric[cname] == 'jaccard':
                    qfn_a[i] = self.jaccard(target, source) / p + qfn_a[i]
                elif self.metric[cname] == 'semantic':
                    qfn_a[i] = self.semantic(target, source) / p + qfn_a[i]
                else:
                    raise ValueError('未知的相似度度量方式: ' + self.metric[cname])
        return qfn_a

    def _quality_null(self, df, qfn):
        return qfn

    def edit(self, target, source):
        # 检查 target 和 source 是否为 '__NULL__' 或 NaN
        if target == '__NULL__' or source == '__NULL__' or pd.isna(target) or pd.isna(source):
            return 0  # 当其中之一为 '__NULL__' 或 NaN 时，返回 0
        else:
            return distance.levenshtein(target, source)  # 计算编辑距离  # 否则计算编辑距离

    def jaccard(self, target, source):
        ttokens = set(target.lower().split())
        stokens = set(source.lower().split())
        intersection_len = len(ttokens.intersection(stokens))
        union_len = len(ttokens.union(stokens))
        jaccard_similarity = 1.0 - (intersection_len + 0.0) / (union_len + 0.0)  # jaccard=交集除以并集

        return jaccard_similarity

    def semantic(self, target, source):
        ttokens = set(target.lower().split())
        stokens = set(source.lower().split())

        sim = []

        for t in ttokens:
            t_similarities = [(self.word_vectors.similarity(t, r) + 1.0) / 2 for r in
                              stokens]  # word_vectors.similarity()函数返回的相似度值在-1到1
            sim.extend(t_similarities)

        return 1 - np.mean(sim)  # 计算平均语义相似度
