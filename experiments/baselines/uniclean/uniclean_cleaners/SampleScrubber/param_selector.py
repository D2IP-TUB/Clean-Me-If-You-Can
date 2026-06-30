"""
模块：ParamSelector
最佳优先搜索根据质量函数和编辑惩罚函数扩展最有希望的节点。
"""
import logging
from datetime import datetime

import numpy as np
import pandas as pd
from gensim.models import KeyedVectors

from SampleScrubber.param_builder import ParamBuilder
from SampleScrubber.cleaner_model import NOOP
from SampleScrubber.cleaner.clean_penalty import EditPenalty

DEFAULT_CONFIG = {
    'maxSearch': 10,
    'editCost': 1,
    'simfunc': {},  # 相似度计算模式
    'w2v': '../../resources/GoogleNews-vectors-negative300.bin'  # 词向量模型
}


def customclean(df, precleaners=[], cleaners=[], partition=None, error_threshold=None, config=None):
    """
    select函数以模式列表和依赖列表的形式作为输入，并返回一个经过清理的实例和一个数据清理程序。

    位置参数:
    df -- Pandas DataFrame
    precleaners -- 预处理算子列表
    cleanners -- 预处理之后的算子列表
    partition -- 用于划分数据集的分块规则
    config -- 配置对象
    """

    if config is None:
        config = DEFAULT_CONFIG
    op = NOOP()

    logging.debug('Starting the select with the following config: ' + str(df.shape) + " " + str(config))

    if needWord2Vec(config):  # 是否需要w2v
        w2v = loadWord2Vec(config['w2v'])

        logging.debug('use word2vec for semantic similarity')

    else:
        w2v = None

    config['model'] = w2v
    positiveOp = []
    negativeOp = []  # 消耗一些计算资源发现不好的 op
    neutralOp = []  # 没那么差的op，但是消耗了很多计算资源去辨别
    bestopList = list()
    pruningModel = None
    score = [0, 0]
    if partition is not None:
        block_indices = find_blocks(df, partition, error_threshold)
        # blocks = set(df[partition].dropna().values)
        for i, indices in enumerate(block_indices):
            block_df = df.loc[indices].copy()
            if block_df.shape[0] < 2:
                continue
            logging.info(f"Processing Block size={block_df.shape[0]}")
            logging.info("Computing Block " + str(i + 1) + " out of " + str(len(block_indices)))
            print("Computing Block " + str(i + 1) + " out of " + str(len(block_indices)))
            print(f"Processing Block size={block_df.shape[0]}")
            # if block_df.shape[0] >= 50:
            #     print(111)
            now = datetime.now()
            op1, cleaned_block, score_1, PositiveOp_1, neutralOp_1, negativeOp_1, bestopList_1 = handlecleaner(block_df,
                                                                                                               precleaners,
                                                                                                               cleaners,
                                                                                                               config,
                                                                                                               error_threshold=error_threshold)
            if not isinstance(op1, NOOP):
                op = op * op1
                score[0] += score_1[0]
                score[1] += score_1[1]
                positiveOp.extend(PositiveOp_1)
                neutralOp.extend(neutralOp_1)
                negativeOp.extend(negativeOp_1)
                bestopList += bestopList_1
                df.loc[indices] = cleaned_block
            logging.info(f"Block processing time: {(datetime.now() - now).total_seconds()} seconds")
            print(f"Block processing time: {(datetime.now() - now).total_seconds()} seconds")
            # print((datetime.now() - now).total_seconds())
    else:
        logging.warning("No partitioning rule specified, processing might be slow")
        op, df, score_1, positiveOp, neutralOp, negativeOp, bestopList = handlecleaner(df, precleaners, cleaners,
                                                                                       config,
                                                                                       error_threshold=error_threshold)
        score[0] += score_1[0]
        score[1] += score_1[1]

    return op, df, bestopList, [positiveOp, neutralOp, negativeOp, score]


def find_blocks(df, partition, error_threshold):
    def filter_partition_attributes(df, partition):
        attribute_group_sizes = {}
        removed_attributes = []  # 记录已删除的属性组合
        for attrs in partition:
            group_size = df.groupby(attrs).ngroups
            attribute_group_sizes[tuple(attrs)] = group_size
            print(f"Grouping by {attrs} yields {group_size} groups.")

        total_rows = len(df)
        selected_attributes = list(partition)

        while True:
            group_product = 1
            for attrs in selected_attributes:
                group_product *= attribute_group_sizes[tuple(attrs)]

            print(f"Current group product: {group_product}, Total rows: {total_rows}")

            if group_product <= total_rows:
                break

            # 找到组数最大的属性组合并删除
            max_group_attr = max(selected_attributes, key=lambda attrs: attribute_group_sizes[tuple(attrs)])
            print(f"Removing attribute group {max_group_attr} with {attribute_group_sizes[tuple(max_group_attr)]} groups.")
            removed_attributes.append(max_group_attr)  # 记录被删除的属性
            selected_attributes.remove(max_group_attr)

        print(f"Final selected attributes for partitioning: {selected_attributes}")
        print(f"Removed attributes for potential later use: {removed_attributes}")
        return selected_attributes, removed_attributes

    def initial_block_mapping(df, partition):
        initial_blocks = df.groupby(partition[0]).groups
        block_mapping = {}
        for key, indexes in initial_blocks.items():
            for index in indexes:
                block_mapping[index] = set(indexes)
        return block_mapping

    def update_block_mapping(df, partition, error_threshold, block_mapping):
        updated = False
        has_p = 'p' in df.columns
        for attrs in partition:
            value_to_indexes = df.groupby(attrs).groups
            for indexes in value_to_indexes.values():
                if len(indexes) > 1:
                    connected_indexes = set()
                    for index in indexes:
                        if not has_p or df.loc[index, 'p'] < error_threshold:
                            connected_indexes.update(block_mapping[index])
                    if connected_indexes:
                        for index in connected_indexes:
                            if block_mapping[index] != connected_indexes:
                                block_mapping[index] = connected_indexes
                                updated = True
        return block_mapping, updated

    def further_split_empty_blocks(df, final_blocks, removed_attributes):
        empty_values = ['__NULL__', 'empty', 'null']  # 定义空值的列表
        new_final_blocks = []

        for block in final_blocks:
            all_empty = True
            for index in block:
                # 检查当前块在现有属性组合下是否全为空
                if any(
                    pd.notna(df.loc[index, attr]) and str(df.loc[index, attr]).strip() not in empty_values
                    for attr_group in partition for attr in attr_group
                ):
                    all_empty = False
                    break

            if all_empty:
                if removed_attributes:
                    print(f"Block {block} has all empty values in current attributes. Further splitting with removed attributes.")
                    # 使用被删除的属性组合对这个块进行分组
                    temp_df = df.loc[block]  # 只对当前块的子数据进行操作
                    for attrs in removed_attributes:
                        temp_blocks = temp_df.groupby(attrs).groups.values()
                        new_final_blocks.extend(temp_blocks)
                        print(f"Further split block {block} using {attrs}, creating {len(temp_blocks)} new blocks.")
                        break
            else:
                new_final_blocks.append(block)

        return new_final_blocks

    removed_attributes=[]
    # 检查每个属性组合的组数，并删除乘积超过数据量的最大组组合
    if len(partition) > 1:
        partition, removed_attributes = filter_partition_attributes(df, partition)

    # Step 1: 初步分块
    print("Starting initial block mapping...")
    block_mapping = initial_block_mapping(df, partition)
    if len(partition) > 1:
        # Step 2: 迭代更新块映射直到稳定
        print("Updating block mapping until stable...")
        while True:
            block_mapping, updated = update_block_mapping(df, partition, error_threshold, block_mapping)
            if not updated:
                break

    # 构建最终的块列表
    final_blocks = set(frozenset(indexes) for indexes in block_mapping.values())
    print(f"Initial number of blocks: {len(final_blocks)}")

    # Step 3: 进一步分块对于在现有属性组合下全为空的块
    final_blocks = further_split_empty_blocks(df, final_blocks, removed_attributes)
    print(f"Final number of blocks after further splitting: {len(final_blocks)}")

    # 返回块的索引列表，每个块是索引的集合
    return [list(block) for block in final_blocks]
def handlecleaner(df, precleaners, cleaners, config, error_threshold=0.2):
    op = NOOP()
    score = [0, 0]
    positiveOp = []
    negativeOp = []  # 消耗一些计算资源发现不好的 op
    neutralOp = []  # 没那么差的负例，但是消耗了很多计算资源去辨别
    bestopList = []
    for p in precleaners:
        preLanguage = p.preProcess()
        df,opLists= preLanguage.run(df)
        bestopList += opLists
        op = op * preLanguage
        logging.debug('Enforcing pattern cleaner=' + str(p))
    # print(df)
    for c in cleaners:
        print("begin cleaner" + str(c))
        cleanop, df, score_1, PositiveOp_1, neutralOp_1, negativeOp_1, bestopList_1 = selector(df, c, depth=config[
            'maxSearch'], editCost=config['editCost'], simfunc=config['simfunc'], word2vec=config['model'],
                                                                                               error_threshold=error_threshold)
        if not isinstance(cleanop, NOOP):
            op = op * cleanop
            score[0] = score_1[0] + score[0]
            score[1] = score_1[1] + score[1]
            positiveOp.extend(PositiveOp_1)
            neutralOp.extend(neutralOp_1)
            negativeOp.extend(negativeOp_1)
            bestopList += bestopList_1
    return op, df, score, positiveOp, neutralOp, negativeOp, bestopList


def selector(df, cleaner, depth, editCost, simfunc, word2vec, error_threshold=0.2):
    """selector：对cleaner生成的参数进行选择
        位置参数:
        df -- Pandas DataFrame
        cleaner--清洗算子
        depth--最大搜索深度
        editCost -- 编辑惩罚缩放系数
        simfunc -- 指定要使用的相似度度量函数
        word2vec -- word2vec模型（避免重新加载）
        """
    domain = cleaner.domain
    bestopList = []
    positiveOp = []  # 每轮的最佳op
    EditPenaltytObj = EditPenalty(df.copy(), domain, simfunc, word2vec)
    epq = EditPenaltytObj.quality
    bad_op_cache = set()
    negativeOp = []  # 消耗一些计算资源发现不好的 op
    neutralOp = []  # 没那么差的负例，但是消耗了很多计算资源去辨别
    search_start_time = datetime.now()

    all_operations = set()  # 创建一个集合用于存储所有探索过的操作
    p = ParamBuilder(df, cleaner, EditPenaltytObj, error_threshold=error_threshold)
    clean_bool, score = p.getOperations()
    best = (2.0, NOOP(), df, NOOP(), -1)
    # 初始化最佳结果为一个元组，其中包含一个初始评分（2.0）、初始算子序列（NOOP()）、原始 DataFrame df、最新应用算子（NOOP()和当前存在的不一致
    select_start_time = datetime.now()
    have_search = False
    # qfnEval = cleaner.quality(df)
    # print(qfnEval)
    truth_depth = 0
    for i in range(depth):
        value, op, frame, lastop, error = best
        if not isinstance(lastop, NOOP):
            # 更新缓存区
            bestopList.append(lastop)
        if len(clean_bool) <= 1 or error == 0:
            truth_depth = i + 1
            break
        try:
            logging.debug('select depth=' + str(i))
        except:
            print("不能并行写入文件")
        if not isinstance(lastop, NOOP):
            # 更新缓存区
            clean_bool, prunnum = UpdateCleanBool(clean_bool, lastop, bad_op_cache)
            print("UpdateCleanBool,purned:" + str(prunnum))
            score[1] += prunnum
            # 清空bad_op_cache集合
            bad_op_cache = set()
            have_search = False

        print("clean_bool length:" + str(len(clean_bool)))
        # df = frame
        for j, opbranch in enumerate(clean_bool):
            logging.debug('At op=' + str(i) + ': ' + opbranch.name)
            if not isinstance(opbranch, NOOP):
                all_operations.add(opbranch)
            else:
                continue
            if opbranch.name in bad_op_cache:
                continue
            output,_ = opbranch.run(frame)
            # 评估剪枝
            qfnEval = cleaner.quality(output)
            now_error = np.sum(qfnEval)
            if error <= now_error and error != -1:  #应该让不一致度减少
                negativeOp.append(opbranch)  # 这里属于运行了一次 opbranch，浪费了一次的计算发现不行，所以是有价值的负例
                bad_op_cache.add(opbranch.name)
                score[1] += 1
                print('pruned op=' + str(j) + ': ' + opbranch.name)
                continue
            else:
                positiveOp.append(opbranch)
            # if pruningRules(CoreSetOutput):
            #     logging.debug('Pruned Search Branch=' + str(l) + ' ' + opbranch.name)
            #     continue

            editfn = epq(output)
            cost_average = (np.sum(qfnEval) + editCost * np.sum(editfn)) / output.shape[0]

            # n = (costEval.agg(F.sum("qfn")).first()[0] + editCost * sum(editfn)) / (CoreSetOutput.count())
            if cost_average < best[0]:
                # 对好的规则，花费一些时间，更新这个溯源情况
                if isinstance(op, NOOP):
                    op.name = "Init quaility: " + opbranch.opinformation  # 初始的质量情况
                opbranch.opinformation = cleaner.msg
                opbranch.name = opbranch.name + opbranch.opinformation + ')'
                opbranch.quality_history = cleaner.quality_history
                print('newest best op: ' + opbranch.name)
                # print('cost_average =' + str(cost_average))
                # print('qfnEval = ' + str(np.mean(qfnEval)))
                # logging.debug('selected op=' + str(j) + ': ' + opbranch.name)
                # score = cost_average
                # if  have_search:
                #     best = (cost_average, nextop, output, opbranch, np.sum(qfnEval))
                #     break
                # else:
                nextop = op * opbranch
                best = (cost_average, nextop, output, opbranch, now_error)
                print("now error:", now_error)
                have_search = True
            else:
                neutralOp.append(opbranch)  # 浪费了两次计算的负例（run op 和 计算 qfn)
        if not have_search:
            truth_depth = i + 1
            break
        logging.debug(
            'Search Depth=' + str(i) + " took " + str((datetime.now() - search_start_time).total_seconds()))
    logging.debug('Search  took ' + str((datetime.now() - search_start_time).total_seconds()))
    score[0] *= depth
    score[1] += (score[1] * (depth - truth_depth))
    return best[1], best[2], score, positiveOp, neutralOp, negativeOp, bestopList


def UpdateCleanBool(clean_bool, lastop, bad_op_cache):
    if not isinstance(lastop, NOOP):
        # 获取上一次操作的一些属性
        predicate_colList = lastop.predicate[0]  #定位属性
        predicate_valueTuple = lastop.predicate[1]  #定位属性的值
        repaired_value = lastop.repairvalue  #被修复的值
        repaired_column = lastop.domain  #要修复的属性

        # 创建一个新的集合来存储满足条件的操作
        new_clean_bool = set()
        old_clean_bool_num = len(clean_bool)
        for op in clean_bool:
            if isinstance(op, NOOP):
                new_clean_bool.add(op)
            else:
                if op.name in bad_op_cache:  #在上一轮中已经证明不行的规则不要
                    continue
                elif predicate_colList == op.predicate[0] and predicate_valueTuple == op.predicate[
                    1] and op.domain in predicate_colList:  # 这是最佳的规则定位的预测属性，不能被修改
                    continue
                elif predicate_colList == op.predicate[0] and predicate_valueTuple == op.predicate[
                    1] and repaired_column == op.domain:  # 这是最佳的规则修复的内容，其余候选肯定不如
                    continue
                else:
                    new_clean_bool.add(op)
        new_clean_bool_num = len(new_clean_bool)
        prunnum = old_clean_bool_num - new_clean_bool_num
        print("pruned: " + str(prunnum))
        # 更新clean_bool集合
        return new_clean_bool, prunnum
    else:
        return clean_bool, 0


def pruningRules(output):
    if output.shape[1] == 0:
        return True

    elif output.shape[0] == 0:
        return True

    return False


def needWord2Vec(config):
    """判断是否需要word2vec"""
    semantic = 'semantic' in [config['simfunc'][k] for k in config['simfunc']]

    return semantic


def loadWord2Vec(filename):
    """导入word2vec模型"""
    return KeyedVectors.load_word2vec_format(filename, binary=True)
