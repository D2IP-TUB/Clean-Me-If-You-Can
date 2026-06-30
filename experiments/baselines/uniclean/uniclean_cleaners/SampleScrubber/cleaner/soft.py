import math

import numpy as np

from SampleScrubber.cleaner_model import CleanerModel

"""
    该模块定义了表示统计和数值约束的几个类。
"""


class Parameteric(CleanerModel):
    """Parametric类表示域大致符合高斯分布的约束，它适用于值高于平均值一定标准差的情况。
    """

    def __init__(self, attr, tolerance=5):

        """Parametric约束的构造函数

        attr -- 属性名称
        tolerance -- 标准差的数量
        """

        self.tolerance = tolerance
        self.attr = attr
        self.domain = set([attr])
        self.fixValueRules = {}

        super(Parameteric, self).__init__(self.domain)

    def _quality(self, df):
        N = df.shape[0]
        qfn_a = np.zeros((N,))
        vals = df[self.attr].dropna().values
        mean = np.mean(vals)
        std = np.std(vals)

        for i in range(N):
            val = df[self.attr].iloc[i]
            if np.isnan(val) or np.abs(val - mean) < std * self.tolerance:
                qfn_a[i] = 0.0
            else:
                qfn_a[i] = 1.0
        return qfn_a


class NonParametric(CleanerModel):
    """NonParametric类表示域集中在中位数附近的约束，它适用于值高于中位数绝对偏差的情况。
    """

    def __init__(self, attr, tolerance=5):

        """NonParametric约束的构造函数
        attr -- 属性名称
        tolerance -- 中位数绝对偏差的数量
        """

        self.tolerance = tolerance
        self.attr = attr
        self.domain = {attr}
        self.fixValueRules = {}

        super(NonParametric, self).__init__(self.domain)

    def _quality(self, df):
        N = df.shape[0]
        qfn_a = np.zeros((N,))
        vals = df[self.attr].dropna().values
        mean = np.median(vals)
        std = np.median(np.abs(vals - mean))

        for i in range(N):
            val = df[self.attr].iloc[i]

            if np.isnan(val) or np.abs(val - mean) < std * self.tolerance:
                qfn_a[i] = 0.0
            else:
                qfn_a[i] = 1.0

        return qfn_a


class Correlation(CleanerModel):
    """Correlation类是关于两个属性之间正相关或负相关关系的一个软性提示。
    """

    def __init__(self, attrs, ctype="positive"):
        """Correlation约束的构造函数

        attrs -- 一个属性名称的元组
        ctype -- "positive"或"negative"
        """

        self.ctype = ctype
        self.attrs = attrs
        self.domain = set(attrs)
        self.fixValueRules = {}

        super(Correlation, self).__init__(self.domain)

    def _quality(self, df):
        N = df.shape[0]
        qfn_a = np.zeros((N,))

        x = df[self.attrs[0]].values
        y = df[self.attrs[1]].values

        mx = np.median(x[~np.isnan(x)])  # 删除np中的nan
        my = np.median(y[~np.isnan(y)])

        for i in range(N):
            val1 = df[self.attrs[0]].iloc[i] - mx  # 依次减去中位数
            val2 = df[self.attrs[1]].iloc[i] - my

            if np.isnan(val1) or np.isnan(val2):
                continue

            if self.ctype == 'positive':
                if np.sign(val1 * val2) < 0:
                    qfn_a[i] = np.abs(val1) + np.abs(val2)
            else:
                if np.sign(val1 * val2) > 0:
                    qfn_a[i] = math.abs(val1) + math.abs(val2)

        # normalize
        if np.sum(qfn_a) > 0:
            qfn_a = qfn_a / np.max(qfn_a)

        return qfn_a


class NumericalRelationship(CleanerModel):
    """NumericalRelationship类是关于两个数值属性之间关系的一个软性提示。
    对于偏离该函数值较大的值，该约束会更强烈地触发。
    """

    def __init__(self, attrs, fn, tolerance=5):
        """NumericalRelationship约束的构造函数

        attrs -- 一个属性名称的元组
        fn -- 一个函数 domain(attr[1]) -> domain(attr[2])
        tolerance -- 标准差的数量
        """

        self.tolerance = tolerance
        self.attrs = attrs
        self.domain = set(attrs)
        self.fixValueRules = {}
        self.fn = fn

        super(NumericalRelationship, self).__init__(self.domain)

    def _quality(self, df):
        N = df.shape[0]
        qfn_a = np.zeros((N,))

        x = df[self.attrs[0]].values
        y = df[self.attrs[1]].values

        residuals = []
        for i in range(N):
            val1 = df[self.attrs[0]].iloc[i]
            val2 = df[self.attrs[1]].iloc[i]

            if np.isnan(val1) or np.isnan(val2):
                continue

            pred_val2 = self.fn(val1)
            residual = val2 - pred_val2
            residuals.append(residual)

        mean = np.mean(residuals)
        std = np.std(residuals)

        for i in range(N):
            val1 = df[self.attrs[0]].iloc[i]
            val2 = df[self.attrs[1]].iloc[i]

            if np.isnan(val1) or np.isnan(val2):
                continue

            pred_val2 = self.fn(val1)
            residual = val2 - pred_val2

            if np.abs(residual - mean) > self.tolerance * std:
                qfn_a[i] = np.abs(residual - mean)

        # normalize
        if np.sum(qfn_a) > 0:
            qfn_a = qfn_a / np.max(qfn_a)

        return qfn_a
