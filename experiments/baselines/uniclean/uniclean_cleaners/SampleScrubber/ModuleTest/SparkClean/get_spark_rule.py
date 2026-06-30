from itertools import combinations, product

from SampleScrubber.ModuleTest.SparkClean.cleaner_model import Dataset


class ParameterSampler(object):  # 参数采样器
    def __init__(self, df, costFn, operations, editCostObj, substrThresh=0.1, scopeLimit=3,
                 predicate_granularity=None):
        self.df = df  # 数据帧
        self.quality_func = costFn.quality_func  # 质量评估函数
        self.qfnobject = costFn  # 获取一些规则的对象信息
        self.substrThresh = substrThresh
        self.scopeLimit = scopeLimit
        self.operationList = operations  # 修复操作参数可以用列表
        self.predicate_granularity = predicate_granularity
        self.editCostObj = editCostObj  # 编辑惩罚
        self.predicateIndex = {}
        self.dataset = Dataset(df)

    def getParameterGrid(self):
        parameters = []
        paramset = [(op, sorted(op.paramDescriptor.values()), op.paramDescriptor.values()) for op in self.operationList]
        for op, p, orig in paramset:  # 遍历 paramset 中的每个元素。每个元素是一个包含三个值的元组：操作（op）、参数（p）和原始参数（orig）
            if p[0] == ParametrizedLanguage.COLUMN:  # 检查参数 p 的第一个值是否等于
                # 移除其中一个列参数
                origParam = list(orig)  # 将 orig（原始参数）字典转换为一个列表，并将其存储在 origParam 变量中
                orig = list(orig)
                orig.remove(p[0])  # 从 orig 列表中删除参数 p 的第一个值。
                colParams = []  # 初始化一个空列表 colParams，用于存储列参数。
                for col in self.columnSampler():  # 对规则域内的属性进行分配
                    grid = []  # 初始化一个空列表 grid，用于存储生成的参数值。
                    for pv in orig:
                        # print(pv)
                        grid.append(self.indexToFun(pv, col))  # 对于每个参数值，它使用 indexToFun 方法将其转换为一个函数，并将结果添加到 grid 列表中。
                    augProduct = []
                    for p in product(*grid):
                        v = list(p)
                        v.insert(0, col)
                        augProduct.append(tuple(v))
                    colParams.extend(augProduct)
                parameters.append((op, colParams, origParam))
            else:
                grid = []
                for pv in orig:
                    grid.append(self.indexToFun(pv))
                parameters.append((op, product(*grid), orig))
        return parameters

    def getAllOperations(self):

        parameterGrid = self.getParameterGrid()
        # print(parameterGrid)
        operations = []
        for i, op in enumerate(self.operationList):
            args = {}

            # print(parameterGrid[i][1])

            for param in parameterGrid[i][1]:
                arg = {}
                for j, k in enumerate(op.paramDescriptor.keys()):  # 把之前设置好的枚举型一一对应
                    arg[k] = param[j]
                # optimization
                if self.pruningRules(arg):
                    continue

                operations.append(op(**arg))
        operations.append(NOOP())

        logging.debug("Library generator created " + str(len(operations)) + " operations")

        return operations

    def pruningRules(self, arg):
        # 移除未相关的插补值
        if 'value' in arg:
            if 'predicate' in arg and list(arg['predicate'][1])[0] == None:
                return True

            if 'codebook' in self.qfnobject.domainParams:

                sim = self.qfnobject.threshold
                if self.editCostObj.semantic(str(arg['value']), str(list(arg['predicate'][1])[0])) > sim:
                    return True
            if 'column' in arg and 'predicate' in arg and arg['column'] != arg['predicate'][0]:
                return True
            else:
                return (arg['value'] != arg['value']) or (arg['value'] == None) or (
                        arg['value'] == arg['predicate'][1])
                # or (len(arg['predicate'][1]) == 0)
                # value 是非法值，或者value就是arg['predicate'][1]

            # else:
            #     return (arg['value'] != arg['value']) or (arg['value'] is None)

        if 'substr1' in arg and 'substr2' in arg:
            return (arg['substr1'] == arg['substr2'])

        return False

    def indexToFun(self, index, col=None):
        if index == ParametrizedLanguage.COLUMN:
            return self.columnSampler()
        elif index == ParametrizedLanguage.COLUMNS:
            return self.columnsSampler()
        elif index == ParametrizedLanguage.VALUE:
            return self.valueSampler(col)
        elif index == ParametrizedLanguage.SUBSTR:
            return self.substrSampler(col)
        elif index == ParametrizedLanguage.PREDICATE:
            return self.predicateSampler(col)
        elif index == ParametrizedLanguage.COSTFN:
            return self.costfnSampler()
        else:
            raise ValueError("Error in: " + index)

    def columnSampler(self):
        return list(self.qfnobject.domain)

    def columnsSampler(self):
        columns = self.columnSampler()
        result = []
        for i in range(1, min(len(columns), self.scopeLimit)):
            result.extend([list(a) for a in combinations(columns, i)])

        return result

    # 暴力搜索
    def valueSampler(self, col):
        if 'ExtDict' in self.qfnobject.domainParams:
            return list(self.qfnobject.domainParams['ExtDict'])
        else:
            unique_values_df = self.df.select(col).distinct()
            # 收集所有不重复值到一个列表中
            unique_values_list = [row[col] for row in unique_values_df.collect()]
            return unique_values_list
            # return list(set(self.df[col].values))

    def costfnSampler(self):
        # print(self.qfnobject)
        result = list()
        result.append(str(self.qfnobject))
        return result

    def substrSampler(self, col):
        chars = {}
        # print(self.df[col].values)
        for v in self.df[col].values:
            if v != None:
                for c in set(str(v)):
                    if c not in chars:
                        chars[c] = 0

                    chars[c] += 1

        # print((chars[' ']+0.)/self.df.shape[0])
        # print()

        # print([c for c in chars if not c.isalnum()])
        return ['-', '/']
        # return [c for c in chars if not c.isalnum()]

    """
    # 暴力搜索
    def predicateSampler(self, col):
        columns = self.columnSampler()
        columns.remove(col)
        projection = self.df[columns]
        tuples = set([tuple(x) for x in projection.to_records(index=False)])

        result_list = []
        for t in tuples:
            result_list.append(lambda s, p=t: (s[columns].values.tolist() == list(p)))

        return result_list
    """

    def predicateSampler(self, col):
        all_predicates = []

        for c in self.qfnobject.domain:
            # if self.dataset.types[c] == 'cat': #only take categorical values
            all_predicates.extend(
                self.dataset.getPredicatesDeterministic(self.quality_func, c, self.predicate_granularity))

        logging.debug("Predicate Sampler has " + str(len(all_predicates)))

        return all_predicates
        # return self.dataset.getPredicates(self.qfn, self.predicate_granularity)
