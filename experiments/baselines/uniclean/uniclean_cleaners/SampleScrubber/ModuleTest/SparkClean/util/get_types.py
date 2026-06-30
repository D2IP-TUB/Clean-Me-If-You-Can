# 定义用于判断分类型属性的阈值和数值型属性的阈值
cat_thresh = 1000
num_thresh = 0.25


def getTypes(data, attrs):
    """
    给定数据以及属性列表，返回一个包含属性数据类型的字典
    """

    type_array = {}

    # 遍历属性列表
    for a in attrs:

        # 判断是否为数值型属性
        if __is_num(data[a]):
            type_array[a] = 'num'
        # 判断是否为分类型属性
        elif __is_cat(data[a]):
            type_array[a] = 'cat'
        else:
            type_array[a] = 'string'

    return type_array


def __is_num(data):
    """
    内部方法，用于判断数据是否为数值型
    """
    float_count = 0.0

    # 遍历数据中的每个元素
    for datum in data:
        try:
            # 尝试将元素解析为浮点数
            float(datum.strip())
            float_count = float_count + 1.0
        except:
            # 如果解析失败，忽略该元素
            pass

    # 计算浮点数元素的比例，判断是否为数值型属性
    return (float_count / len(data) > num_thresh)


def __is_cat(data):
    """
    内部方法，用于判断数据是否为分类型
    默认的判断条件是不同值的个数小于 N/LogN
    """

    counts = {}

    # 遍历数据中的每个元素
    for datum in data:
        d = datum

        # 统计每个不同值的出现次数
        if d not in counts:
            counts[d] = 0

        counts[d] = counts[d] + 1

    # 计算具有重复值的不同值的个数，并总不同值的个数
    totalc = len([k for k in counts if counts[k] > 1]) + 0.0
    total = len([k for k in counts]) + 0.0

    # 判断是否为分类型属性
    return (totalc < cat_thresh) and (totalc / total > 0.2)
