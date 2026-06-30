from array import array


def levenshtein(seq1, seq2, method=1):
    """计算`seq1`和`seq2`之间的标准化Levenshtein距离。
    归一化的距离将是一个介于0和1之间的浮点数，其中0表示等于和1完全不同。计算遵循以下模式。
    0.0     如果seq1 == seq2
    1.0     如果len(seq1) == 0或len(seq2) == 0
    序列间最短比对长度编辑距离 其他
    """

    if seq1 == seq2:
        return 0.0
    len1, len2 = len(seq1), len(seq2)
    if len1 == 0 or len2 == 0:
        return 1.0
    if len1 < len2:  # minimize the arrays size
        len1, len2 = len2, len1
        seq1, seq2 = seq2, seq1

    return editdistance(seq1, seq2) / float(len1)


"""
test:
    editdistance('1','abc')
    3
    editdistance('1','abcd')
    4
    editdistance('1234234','abcd')
    7
"""


def editdistance(seq1, seq2, max_dist=-1):
    """计算两个序列`seq1`和`seq2`之间的绝对编辑距离。
        编辑距离是将一个序列转换为另一序列所需的最小编辑操作数。允许的编辑操作有：

            * 删除：ABC -> BC, AC, AB
            * 插入：ABC -> ABCD、EABC、AEBC..
            * 替换：ABC -> ABE、ADC、FBC..
    """

    if seq1 == seq2:
        return 0

    len1, len2 = len(seq1), len(seq2)
    if len1 == 0:
        return len2
    if len2 == 0:
        return len1
    if len1 < len2:
        len1, len2 = len2, len1
        seq1, seq2 = seq2, seq1

    column = array('L', range(len2 + 1))

    for x in range(1, len1 + 1):
        column[0] = x
        last = x - 1
        for y in range(1, len2 + 1):
            old = column[y]
            cost = int(seq1[x - 1] != seq2[y - 1])
            column[y] = min(column[y] + 1, column[y - 1] + 1, last + cost)
            last = old
    return column[len2]
