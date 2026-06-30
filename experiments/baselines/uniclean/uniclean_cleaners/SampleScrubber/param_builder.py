import logging
from itertools import product

import numpy as np

from SampleScrubber.cleaner_model import Uniop, ParametrizedLanguage, NOOP


class ParamBuilder(object):  # 参数构建
    def __init__(self, df, Cleaner, editPenalty, error_threshold=0.2):
        self.df = df
        self.CleanerObject = Cleaner
        self.editPenalty = editPenalty
        self.error_threshold = error_threshold

    def getOperations(self):
        score = [0, 0]
        operations = []
        op = Uniop
        orig = list(op.paramDescriptor.values())
        orig.remove(ParametrizedLanguage.DOMAIN)
        # 对每个列生成参数组合
        for target_col in list(self.CleanerObject.target):
            for params in product(*[self.paramSampler(index, target_col) for index in orig]):
                args = {k: v for k, v in zip(op.paramDescriptor.keys(), (target_col,) + params)}  # 生成keys字典，将参数放入
                score[0] += 1
                if self.optimizeParams(args):
                    score[1] += 1
                    continue
                operations.append(op(**args))

        if 'ExtEdit' in self.CleanerObject.fixValueRules:
            ExtEditList = self.CleanerObject.fixValueRules['ExtEdit']
            operations.extend(ExtEditList)
        operations.append(NOOP())
        logging.debug("Library generator created " + str(len(operations)) + " operations")
        return operations, score

    def paramSampler(self, index, col):
        if index == ParametrizedLanguage.REPAIRVALUE:
            return self.RepairValueSampler(col)
        elif index == ParametrizedLanguage.PREDICATE:
            return self.predicateSampler()
        elif index == ParametrizedLanguage.OPINFORMATION:
            return self.OpInformationSampler()
        else:
            raise ValueError("Error in: " + index)

    def OpInformationSampler(self):
        result = list()
        result.append(str(self.CleanerObject))
        return result

    def predicateSampler(self):
        predicates = []
        # if self.dataset.types[c] == 'cat': #only take categorical values
        for colList in self.LocateAttrSampler():  # 要防止值互换有混淆的情况
            predicates.extend(
                self.getPredicatesDeterministic(self.CleanerObject.quality, colList))
        logging.debug("Predicate Sampler get " + str(len(predicates)))
        return predicates

    def RepairValueSampler(self, col):
        # 默认的无效值
        invalid_values = [None, "", '__NULL__', '__NAN__', 'empty', np.nan]

        # 如果存在 invalidDict，则从中获取无效值
        if 'invalidDict' in self.CleanerObject.fixValueRules:
            invalid_dict_values = self.CleanerObject.fixValueRules['invalidDict'].get(col, [])
            invalid_values.extend(invalid_dict_values)

        # 对这一列已有值做个聚合，小于self.error_threshold极大概率是错的，不能作为候选值
        try:
            # 筛选满足条件的值：p 列值大于等于阈值，并且不在无效值列表中
            filtered_values = [
                val for val in set(self.df[self.df['p'] >= self.error_threshold][col].values)
                if val not in invalid_values
            ]
        except KeyError:
            # 如果不存在 p 列，则直接使用当前列的所有值，排除无效值
            print(f"列 'p' 不存在，对列 {col} 不过滤，直接选择所有非无效值。")
            filtered_values = [
                val for val in set(self.df[col].values)
                if val not in invalid_values
            ]
        if 'ExtDict' in self.CleanerObject.fixValueRules:
            ext_dict_values = self.CleanerObject.fixValueRules['ExtDict'].get(col, [])
            # 仅保留在 ext_dict_values 中存在的部分
            filtered_values = [val for val in filtered_values if val in ext_dict_values]

        return filtered_values

    def LocateAttrSampler(self):  # 用于定位的属性阈
        LocateList = []
        for cleaner in self.CleanerObject.cleanerList:
            LocateList.append(list(cleaner.source))
        return LocateList

    def optimizeParams(self, args):
        # 对有额外知识库的时候剪枝，或对明显错误的参数剪枝
        for tup in args['predicate'][1]:
            if len(tup) == 0 or any(val is None or val == '' for val in tup):
                return True
        if args['predicate'][1] == '':
            return True
        # if '__NULL__' in list(args['predicate'][1])[0]:
        #     return True
        if not bool(list(args['predicate'][1])[0]):
            return True

            # 检查是否存在外部编辑规则
        if 'ExtEdit' in self.CleanerObject.fixValueRules:
            ExtEditList = self.CleanerObject.fixValueRules['ExtEdit']
            # 遍历外部编辑规则,如果有一样的predicate，则剪掉
            for edit in ExtEditList:
                if edit['predicate'][0] == args['predicate'][0] and edit['predicate'][1] == args['predicate'][1]:
                    return True

        if args['domain'] in args['predicate'][0]:  #没有做任何修改的算子
            domain_index = args['predicate'][0].index(args['domain'])
            for val in args['predicate'][1]:
                if args['repairvalue'] == val[domain_index]:
                    return True

        tuples = args['predicate'][1]  # 取出元组列表

        for tup in tuples:
            # 检查元组中的每个值，判断是否包含 None 或 NaN
            if any(val is None or val != val for val in tup):
                return True
        return (args['repairvalue'] != args['repairvalue']) or (args['repairvalue'] is None) or (
                len(args['predicate'][1]) == 0)

    def getPredicatesDeterministic(self, quality, colList):
        # a = self.error_threshold  # 是一个经验值，可以调整，代表着预测错误概率的阈值
        # 计算质量数组
        # quality_array = quality(self.df)
        # 应用条件逻辑
        # q_array = np.where(quality_array > a, 1, 0)  #大于a说明可能出错
        q_array = np.sign(quality(self.df))
        vals_inside = set()  # 存储错的的值
        tuples_inside = set()  # 存储可能出错的元组索引
        for i in range(len(self.df)):
            val_tuple = tuple(self.df[colList].iloc[i])
            # val = self.df[colList].iloc[i]
            try:
                index = self.df['index'].iloc[i]
            except:
                raise NotImplementedError("数据没有index列作为索引")  # 抛出异常：未实现索引
            if q_array[i] == 1.0:
                if '__NULL__' not in val_tuple:
                    vals_inside.add(val_tuple)
                    tuples_inside.add(index)
        # print(tuples_inside)
        return [(colList, {p}, tuples_inside) for p in vals_inside]
