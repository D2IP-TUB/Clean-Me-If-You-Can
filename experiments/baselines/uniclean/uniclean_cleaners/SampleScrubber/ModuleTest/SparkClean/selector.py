"""
模块：selector

最佳优先搜索根据指定的成本函数扩展最有希望的节点。
我们考虑了该算法的贪心算法，它删除了前沿节点，这些节点的成本比当前最佳解决方案差gamma倍。
gamma增大，使得该算法渐近一致，而gamma = 1是纯贪心搜索。
"""
from gensim.models.keyedvectors import KeyedVectors
from pyspark.sql import functions as F

from SampleScrubber.ModuleTest.SparkClean.cleaner_model import EditPenalty

# 配置模式
DEFAULT_SOLVER_CONFIG = {}

DEFAULT_SOLVER_CONFIG['dependency'] = {
    'depth': 10,
    'gamma': 5,
    'edit': 3,
    'operations': [Swap],  # 算子选择
    'similarity': {},  # 相似度计算
    'w2v': '../../resources/GoogleNews-vectors-negative300.bin'  # 词向量
}


def solve(df, patterns=[], dependencies=[], partitionOn=None, config=DEFAULT_SOLVER_CONFIG):
    """
    solve函数以模式列表和依赖列表的形式作为输入，并返回一个经过清理的实例和一个数据清理程序。

    位置参数:
    df -- Pandas DataFrame
    patterns -- 单属性的模式约束列表
    dependencies -- 在模式约束之后运行的单个或多个属性约束列表
    partitionOn -- 用于划分数据集的阻塞规则
    config -- 配置对象
    """

    op = NOOP()

    # 获取行数和列数
    num_rows = df.count()
    num_columns = len(df.columns)

    # 构建日志消息
    log_message = f"Starting the search algorithm with the following config: ({num_rows}, {num_columns}) {str(config)}"

    # 使用 logging 打印日志
    logging.debug(log_message)
    # logging.debug('Starting the search algorithm with the following config: ' + str(df.shape) + " " + str(config))

    # if needWord2Vec(config):  # 是否需要w2v
    #     w2vp = loadWord2Vec(config['pattern']['w2v'])
    #     w2vd = loadWord2Vec(config['dependency']['w2v'])
    #
    #     logging.debug('Using word2vec for semantic similarity')
    #
    # else:
    # w2vp = None
    # w2vd = None

    # config['pattern']['model'] = w2vp
    # config['dependency']['model'] = w2vd
    config['dependency']['model'] = None
    # training_set = (set(), set())
    # pruningModel = None
    edit_score = 0
    # logging.warning("You didn't specify any blocking rules, this might be slow")
    # op1, df, edit = patternConstraints(df, patterns, config['pattern'])
    # edit_score = edit_score + edit
    op2, df, edit, _ = dependencyConstraints(df, dependencies, config['dependency'])
    edit_score = edit_score + edit
    # op = op * (op1 * op2)
    op = op * op2
    return op, df, edit_score


def loadWord2Vec(filename):
    """导入word2vec模型"""
    return KeyedVectors.load_word2vec_format(filename, binary=True)


def needWord2Vec(config):
    """判断是否需要word2vec"""
    semantic_in_pattern = 'semantic' in [config['pattern']['similarity'][k] for k in config['pattern']['similarity']]
    semantic_in_dependency = 'semantic' in [config['dependency']['similarity'][k] for k in
                                            config['dependency']['similarity']]
    return semantic_in_pattern or semantic_in_dependency


def dependencyConstraints(df, dependencies, config, pruningModel=None):
    """强制依赖约束"""

    op = NOOP()
    edit = 0
    training = None
    for d in dependencies:
        logging.debug('Enforcing dependency cleaner=' + str(d))

        transform, df, edit_score, training = treeSearch(df, d, config['operations'], depth=config['depth'], \
                                                         inflation=config['gamma'], editCost=config['edit'],
                                                         similarity=config['similarity'], \
                                                         word2vec=config['model'],
                                                         pruningModel=pruningModel)
        op = op * transform
        # edit = edit + edit_score
    return op, df, edit, training


def UpdateCleanBool(clean_bool, lastop, bad_op_cache):
    if not isinstance(lastop, NOOP):
        # 获取上一次操作的一些属性
        repaired_tuple_value = lastop.predicate[1]
        repaired_value = lastop.value
        repaired_column = lastop.column

        # 创建一个新的集合来存储满足条件的操作
        new_clean_bool = set()

        for op in clean_bool:
            if isinstance(op, NOOP):
                new_clean_bool.add(op)
            else:
                if op.name in bad_op_cache:
                    continue
                elif (repaired_column == op.column) and (repaired_tuple_value == op.value):
                    continue
                elif (repaired_column == op.column) and (repaired_value == op.predicate[1]):
                    continue
                elif (repaired_column == op.column) and (repaired_tuple_value == op.predicate[1]):
                    continue
                else:
                    new_clean_bool.add(op)

    # 更新clean_bool集合
    return new_clean_bool


def treeSearch(df, costFn, operationList, depth, inflation, editCost,
               similarity, word2vec, pruningModel=None):
    """实际运行树搜索的函数

    位置参数:
    df -- Spark DataFrame
    costFn -- 对应的约束
    operations -- 操作列表
    evaluation -- 总评估次数
    inflation -- gamma
    editCost -- 编辑成本缩放系数
    similarity -- 指定要使用的相似度度量的字典
    word2vec -- word2vec模型（避免重新加载）
    """
    # pruningModel = joblib.load('../../testdata/model/pruningmodel.joblib')
    editCostObj = EditPenalty(df, similarity, word2vec)
    efn = editCostObj.quality_func
    # df = df.toPandas()
    edit_score = 0  # 初始化编辑分数为 0。
    # branch_hash = set()  # 创建一个哈希集合用于存储已探索的分支
    # branch_value = hash(str(df.values))
    # branch_hash.add(branch_value)
    bad_op_cache = set()

    search_start_time = datetime.datetime.now()

    all_operations = set()  # 创建一个集合用于存储所有探索过的操作
    p = ParameterSampler(df, costFn, operationList, editCostObj)
    # costEval = costFn.quality_func(df)
    clean_bool = p.getAllOperations()
    best = (2.0, NOOP(), df, NOOP(), -1)  # 初始化最佳结果为一个元组，其中包含一个初始评分（2.0）、一个空操作（NOOP()）和原始 DataFrame df

    for i in range(depth):
        if not clean_bool:  # 剪枝
            break
        level_start_time = datetime.datetime.now()
        logging.debug('Search Depth=' + str(i))
        value, op, frame, lastop, error = best
        if not isinstance(lastop, NOOP):
            # 更新缓存区
            clean_bool = UpdateCleanBool(clean_bool, lastop, bad_op_cache)
            # 清空bad_op_cache集合
            bad_op_cache = set()

        # 考虑深度的惩罚，进行剪枝
        print(clean_bool)
        # df = frame
        for l, opbranch in enumerate(clean_bool):
            logging.debug('Search Branch=' + str(l) + ' ' + opbranch.name)
            if not isinstance(opbranch, NOOP):
                all_operations.add(opbranch)
            # 剪枝坏的操作
            if opbranch.name in bad_op_cache:
                continue
            # 学习方法
            # if pruningModel is not None and not net_predict(pruningModel, opbranch, df):
            #    print("Pruned: ", opbranch)
            #    continue
            # pass
            nextop = op * opbranch
            # 阻止引发错误的转换
            # try:
            output = opbranch.run(frame)
            print('run' + opbranch.name)
            # except:
            #     logging.warn('Error in Search Branch=' + str(l) + ' ' + opbranch.name)
            #     bad_op_cache.add(opbranch.name)
            #     print(1111111111111111111111111111111111111)
            #     continue
            # 评估剪枝
            qfnEval = costFn.quality_func(output)
            now_error = qfnEval.filter(F.col("qfn") > 0.0).count()
            if error == -1:
                error = len(opbranch.predicate[2])
            if error < now_error or error == now_error:
                bad_op_cache.add(opbranch.name)
                logging.debug('Pruned Search Branch=' + str(l) + ' ' + opbranch.name)
                continue
            # if pruningRules(CoreSetOutput):
            #     logging.debug('Pruned Search Branch=' + str(l) + ' ' + opbranch.name)
            #     continue

            editfn = efn(output)
            df_joined_with_qfn = editfn.join(qfnEval, "index")
            sum_columns = [F.col(c) for c in df_joined_with_qfn.columns if "_Equality" in c]
            average_sum = sum(sum_columns) / len(sum_columns)
            combined_with_qfn = df_joined_with_qfn.withColumn("combined", average_sum + F.col("qfn"))
            cost_average = combined_with_qfn.select(F.avg("combined")).first()[0]
            print('cost_average =' + str(cost_average))

            # n = (costEval.agg(F.sum("qfn")).first()[0] + editCost * sum(editfn)) / (CoreSetOutput.count())
            if cost_average < best[0]:
                logging.debug('Promoted Search Branch=' + str(l) + ' ' + opbranch.name)
                edit_score = editfn
                best = (cost_average, nextop, output, opbranch, now_error)
                # lastop=opbranch
                # break;

        logging.debug(
            'Search Depth=' + str(i) + " took " + str((datetime.datetime.now() - level_start_time).total_seconds()))
    logging.debug('Search  took ' + str((datetime.datetime.now() - search_start_time).total_seconds()))

    return best[1], best[2], edit_score, (
        all_operations.difference(set(best[1].provenance)), set(best[1].provenance))


def pruningRules(output):
    if output.count() == 0:
        return True

    elif len(output.columns) == 0:
        return True

    return False
