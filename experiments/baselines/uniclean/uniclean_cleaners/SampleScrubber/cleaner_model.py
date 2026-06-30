"""Module: UniOpModel
    一个统一的清洗算子结构，为后续加入的清洗算子提供统一的接口。提供了算子的统一结构、算子的运算模式和清洗参数的统一结构。
"""
import datetime
import logging

import numpy as np

from SampleScrubber.util.format import formatString


class CleanerModel(object):
    """清洗算子的基本包装类。
    """

    def __init__(self, domain=None, source=None, target=None, msg=None):
        """
        初始化方法，定义 source、target 和 domain 属性集，以及其他相关属性。

        输入:
        - domain: 涉及到的属性域空间，默认为空集合。
        - source: 源属性集，默认为空集合。
        - target: 目标属性集，默认为空集合。
        - msg: 算子的消息字符串。

        输出:
        - 初始化对象的 source、target、domain、quality_history、msg、cleanerList 和 fixValueRules 参数。
        """
        self.source = source if source else set()
        self.target = target if target else set()
        self.domain = domain if domain else set()
        self.quality_history = {}  # 用于记录最新的运算情况
        self.msg = msg
        self.cleanerList = []
        self.fixValueRules = {}

    def quality(self, df):
        """
        质量评估公共接口方法，封装评估特定数据库实例的质量函数。

        输入:
        - df: 一个 Spark DataFrame。

        输出:
        - 返回每行数据的质量评估值。
        """
        return self._quality_null(df, self._quality(df))

    def _quality(self, df):
        """
        抽象方法，需在子类中实现具体质量评估逻辑。

        输入:
        - df: 一个 Spark DataFrame。

        输出:
        - 返回每行数据的质量评估值。
        """
        raise NotImplementedError("未实现该算子的质量函数")

    def _quality_null(self, df, qfn):
        """
        处理空值情况的质量评估方法。

        输入:
        - df: 一个 Spark DataFrame。
        - qfn: 每行数据的质量评估值数组。

        输出:
        - 更新后的质量评估值数组，考虑了空值情况。
        """
        for col in self.domain:
            for i in range(len(df)):
                if not bool(df.iloc[i][col]):
                    qfn[i] = 1
        return qfn

    def __str__(self):
        """
        返回清洗算子的消息字符串。

        输出:
        - 算子的消息字符串。
        """
        try:
            return self.msg
        except:
            return '无法获取该清洗算子的消息'

    def __add__(self, other):
        """
        加法运算符重载，用于合并两个质量函数。

        输入:
        - other: 另一个 CleanerModel 对象。

        输出:
        - 返回一个新的 CleanerModel 对象，表示两个质量函数的平均值。
        """
        uom = CleanerModel()

        def new_quality(df):
            self_value = self.quality(df)
            other_value = other.quality(df)
            result = (self_value + other_value) / 2
            uom.quality_history = {
                "left": (self.msg, np.mean(self_value)),
                "operator": "+",
                "right": (other.msg, np.mean(other_value)),
                "result": np.mean(result)
            }
            uom.msg = str(uom.quality_history).replace("\'", "")
            return result

        uom.quality = new_quality
        uom.cleanerList = self.cleanerList
        uom.cleanerList.append(other)
        uom.target = self.target.union(other.target)
        uom.source = self.source.union(other.source)
        uom.domain = self.domain.union(other.domain)
        uom.fixValueRules = self.fixValueRules.copy()
        uom.fixValueRules.update(other.fixValueRules)
        uom.msg = str(self) + '+' + str(other)
        return uom

    def __mul__(self, other):
        """
        乘法运算符重载，用于按位比较或乘积两个质量函数。

        输入:
        - other: 可以是一个数字（表示权重）或另一个 CleanerModel 对象。

        输出:
        - 返回一个新的 CleanerModel 对象，表示按位比较或乘积两个质量函数的结果。
        """
        uom = CleanerModel()
        try:
            fother = float(other)

            def new_quality(df):
                self_value = self.quality(df)
                result = fother * self_value
                uom.quality_history = {
                    "left": (self.msg, np.mean(self_value)),
                    "operator": "*",
                    "right": (str(fother), fother),
                    "result": np.mean(result)
                }
                uom.msg = str(uom.quality_history).replace("\'", "")
                return result

            uom.quality = new_quality
            uom.cleanerList = self.cleanerList
            uom.domain = self.domain
            uom.fixValueRules = self.fixValueRules.copy()
            uom.msg = self.msg + '*' + str(fother)
            uom.target = self.target
            uom.source = self.source

        except:
            def new_quality(df):
                self_value = self.quality(df)
                other_value = other.quality(df)
                result = np.maximum(self_value, other_value)
                uom.quality_history = {
                    "left": (self.msg, np.mean(self_value)),
                    "operator": "^",
                    "right": (other.msg, np.mean(other_value)),
                    "result": np.mean(result)
                }
                uom.msg = str(uom.quality_history).replace("\'", "")
                return result

            uom.cleanerList = self.cleanerList
            # 更新清洗信号以及其他参数
            uom.cleanerList.append(other)
            uom.quality = new_quality
            uom.domain = self.domain.union(other.domain)
            uom.fixValueRules = self.fixValueRules.copy()
            uom.fixValueRules.update(other.fixValueRules)
            uom.target = self.target.union(other.target)
            uom.source = self.source.union(other.source)
            uom.msg = self.msg + '^' + str(other.msg)

        return uom


class Language(object):
    """
    基本的修复语言参数类，定义可以在数据帧上执行的操作。
    """

    def __init__(self, runfunc, reward=1, provenance=[]):
        """
        参数:
            runfn: 函数，表示算子的运行函数，将在数据帧上应用。
            reward: 整数，表示算子对修复的贡献度。
            provenance: 列表，表示算子的来源。
        """
        self.runfunc = lambda df: runfunc(df)  ## df表示数据帧
        self.reward = reward#清洗操作的成本
        if provenance != []:
            self.provenance = provenance  # 记录算子来源
        self.quality_history = {}  # 字典，用来记录最新的运算情况

    def set_reward(self, r):
        self.reward = r

    def run(self, df):
        """
        执行算子，记录单个算子运行时间，并返回结果数据帧。
        """
        op_start_time = datetime.datetime.now()  ## 记录操作开始时间
        df_copy = df.copy(deep=True)
        result,opLists = self.runfunc(df_copy)
        logging.debug(
            'Running ' + self.name + ' took ' + str((datetime.datetime.now() - op_start_time).total_seconds()))
        return result,opLists

    def __mul__(self, other):
        """
            定义可组合的数据帧上操作。重写操作符，将两个操作组合成一个新的操作
        """
        new_runfunc = lambda df, a=self, b=other: b.runfunc(a.runfunc(df))
        new_op = Language(new_runfunc, provenance=self.provenance + other.provenance)
        new_op.name = (self.name + "\n" + other.name).strip()
        new_op.reward = self.reward + other.reward
        return new_op

    def __pow__(self, b):
        """
            自身迭代的运算
        """
        op = self
        for i in range(b):
            op *= self
        return op

    def __str__(self):
        return self.name

    __repr__ = __str__


class ParametrizedLanguage(Language):
    """
    参数化操作类，表示带参数的操作，可以在数据帧上执行。
    """

    # 参数属性常量
    DOMAIN = 0
    REPAIRVALUE = 1
    PREDICATE = 2
    OPINFORMATION = 3
    FORMAT = 4

    def __init__(self, runfunc, params, reward=0):
        """
        参数:
        runfunc: 在数据帧上每行应用的逻辑
        params: 修复的基本参数。
        reward:修复的个数
        """
        self.CheckParams(params)
        super(ParametrizedLanguage, self).__init__(runfunc, reward)

    def CheckParams(self, params):
        """
        判断参数是否有效。
            ValueError，如果参数无效。
        """
        try:
            self.paramDescriptor  # 判断是否有参数描述集
        except:
            raise NotImplemented("Language does not have paramDescriptor")

        for p in params:
            if p not in self.paramDescriptor:
                raise ValueError("Parameter " + str(p) + " not defined")

            if self.paramDescriptor[p] not in range(5):
                raise ValueError("Parameter " + str(p) + " has an invalid descriptor")


class Uniop(ParametrizedLanguage):
    """
    修复操作元语言，完备性的覆盖所有清洗操作
    """

    paramDescriptor = {'domain': ParametrizedLanguage.DOMAIN,
                       'repairvalue': ParametrizedLanguage.REPAIRVALUE,
                       'predicate': ParametrizedLanguage.PREDICATE,
                       'opinformation': ParametrizedLanguage.OPINFORMATION,
                       }

    def __init__(self, domain, repairvalue, predicate, opinformation):
        """
        初始化替换算子。

        参数:
        domain: str，要替换值的列名
        predicate: tuple，一个元组，包含用于查找值的条件
        repairvalue: str，要替换的值
        opinformation: str，清洗来源信息
        """
        # 基本的谓词函数，用于判断是否满足修复条件
        # predicate 现在是 (column_list, tuple_list) 形式
        basic_predicate = lambda row: tuple(row[col] for col in predicate[0]) in predicate[1]and (
                row['index'] in predicate[2])

        # basic_predicate = lambda row: (row[predicate[0]] in predicate[1]) and (
        #         row['index'] in predicate[2])

        self.domain = domain
        self.predicate = predicate
        self.repairvalue = repairvalue
        self.opinformation = opinformation
        self.name = 'Uniop(df,' + formatString(domain) + ',' + formatString(repairvalue) + ',' + str(
            predicate[0:2]) + ','

        def runfunc(df, domain=domain, predicate=basic_predicate, v=repairvalue):
            def __internal(row):
                # 如果满足查找条件，则替换为指定值，否则保持原值不变
                if predicate(row):
                    return v
                else:
                    return row[domain]

            df[domain] = df.apply(lambda row: __internal(row), axis=1)  # 遍历行应用结果
            return df,[]

        self.provenance = [self]
        super(Uniop, self).__init__(runfunc, ['domain', 'repairvalue', 'predicate', 'opinformation'], reward=1)


class NOOP(Language):
    """
        空操作
    """

    def __init__(self):
        def runfunc(df):  # 对数据空操作
            return df,[]

        self.name = "NOOP"
        self.provenance = [self]
        reward = 0
        super(NOOP, self).__init__(runfunc, reward=reward,provenance=self.provenance)