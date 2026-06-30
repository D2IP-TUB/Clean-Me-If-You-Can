from collections import Counter
import numpy as np
from SampleScrubber.cleaner_model import CleanerModel


class AttrRelation(CleanerModel):
    """AttrRelation 是两组属性之间的依赖关系，包括了使用最小修复对这个关系进行修复。功能依赖关系 (A -> B) 意味着对于每个 B 属性，可以通过 A 属性进行修复。
    相当于内置了FD，CFD，DC，PFD，MD，RFD（设计在采样那里，宽松认为某个依赖有效）这6类规则类算子，结合外部知识清洗
    """

    def __init__(self, source, target, name, Cpredicate_list=None,ExtDict=None,invalidDict=None,
                 edit_rule=None,DCpredicate_list=None):
        """
        初始化方法，定义 source 和 target 属性集，清洗信号 fixValueRules 及其他相关属性。

        source -- 一个属性名称列表
        target -- 一个属性名称列表
        name -- 关系名称
        condition_func -- 条件函数，判断 source 组成的元组是否满足条件
        ExtDict -- 外部字典，表示对 target 属性可能的值
        edit_rule -- 编辑规则
        invalidDict -- 已发现的异常值
        """
        super().__init__(source=set(source), target=set(target), domain=set(source + target))
        self.name = name
        self.fixValueRules = {}
        self.quality_history = {}
        self.msg = '[FunctionalDependency:(s: %s, t: %s)]' % (self.source, self.target)  # 默认基于功能依赖的最小修复
        if ExtDict is not None:
            self.fixValueRules['ExtDict'] = ExtDict
        if invalidDict is not None:
            self.fixValueRules['invalidDict'] = invalidDict
        if Cpredicate_list is not None:
            self.fixValueRules['Cpredicate_list'] = Cpredicate_list
        if edit_rule is not None:
            self.fixValueRules['edit_rule'] = edit_rule
        if DCpredicate_list is not None:
            self.fixValueRules['DCpredicate_list'] = DCpredicate_list
        self.cleanerList = [self]
        # 通过否定约束的方式实现复杂谓词检测

    def __str__(self):
        return self.msg

    #当前规则下，每行数据错误的概率
    def _quality(self, df):
        """
        计算当前规则下每行数据的错误概率。

        df -- 评估的 DataFrame
        """
        N = df.shape[0]  # 数据的行数
        kv = {}

        # 建立 source 到 target 的映射分组
        for i in range(N):
            s = tuple(df[list(self.source)].iloc[i, :])  # 获取 source 元组
            t = tuple(df[list(self.target)].iloc[i, :])  # 获取 target 元组

            if s in kv:
                kv[s].append(t)  # 保留所有出现的 target，不去重
            else:
                kv[s] = [t]

        qfn_a = np.zeros(N)  # 初始化质量评估数组

        for i in range(N):
            s = tuple(df[list(self.source)].iloc[i, :])  # 获取 source 元组
            t = tuple(df[list(self.target)].iloc[i, :])  # 获取 target 元组
            count = Counter(kv[s])  # 统计每个 target 出现的次数
            normalization = len(kv[s])  # 计算源元组 s 对应的所有 target 的总数

            if len(count.keys()) == 1:
                qfn_a[i] = 0  # 如果只有一个唯一的 target 值，高准确率（无错误）
            else:
                qfn_a[i] = 1 - float(count[t]) / normalization  # 计算 target 的比例，比例小则错误概率高
            if 'ExtDict' in self.fixValueRules:
                dic =self.fixValueRules['ExtDict']
                if t not in dic:
                    qfn_a[i] = 1.0
            if 'invalidDict' in self.fixValueRules:
                dic =self.fixValueRules['invalidDict']
                if t in dic:
                    qfn_a[i] = 1.0
            if 'Cpredicate_list' in self.fixValueRules:
                for cp in self.fixValueRules['Cpredicate_list']:
                    val = cp.get(df).iloc[i]
                    if not cp.eval(val, df):  # 没匹配到，说明不涉及清洗，到错误率设置为0
                        qfn_a[i] = 0.0
                        break
            if 'DCpredicate_list' in self.fixValueRules:
                for dcp in self.fixValueRules['DCpredicate_list']:
                    val = dcp.get(df).iloc[i]
                    if dcp.eval(val, df): #匹配到了，说明违反了否定依赖，错误率为1
                        qfn_a[i] = 1.0
                        break
        return qfn_a  # 返回每行数据的错误概率


class Predicate(CleanerModel):
    """
    一个Predicate是谓词判断的基本结构
    """

    def __init__(self, local_attr, expression):
        """ DCPredicate 构造函数

        local_attr -- 一个属性名称
        expression -- 一个函数映射 fn: domain(local_attr) x df -> {true, false}
        """
        self.local_attr = local_attr
        self.expression = expression

    def get(self, df):
        """将提供的数据帧投影到指定的属性
：
        df -- 一个数据帧
        """
        return df[self.local_attr]

    def eval(self, value, df):
        """评估谓词

        value -- 来自 domain(local_attr) 的一个值
        df -- 一个数据帧
        """
        return self.expression(value, df)
