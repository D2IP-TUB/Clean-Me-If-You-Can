import pandas as pd


def getErrorNum(df_1, df_2, set):
    error_num0 = 0
    for i in set:
        try:
            error_num0 += max(df_1[i].compare(df_2[i]).iloc[:]["self"].notnull().sum(),
                              df_1[i].compare(df_2[i]).iloc[:]["other"].notnull().sum())

        except:
            print(i + " is same or dont have " + i)
            continue;
    return error_num0


def getCorrectRepairs(dfclean, dfrepair, dforigin, set):
    # 筛选出dfrepair和dforigin中set集合中的共有列
    dfrepair_subset = dfrepair[set]
    dforigin_subset = dforigin[set]
    dfclean_subset = dfclean[set]

    repair = dfrepair_subset.compare(dforigin_subset, keep_equal=True, keep_shape=True)  # 真正的修复
    origin = dfclean_subset.compare(dforigin_subset, keep_equal=True, keep_shape=True)  # 理想的修复
    error_num0 = getErrorNum(dfclean_subset, dforigin_subset, set)  # 所有正确的修复个数

    # 找到每个属性下面的self，非null部分，就是没修出来的
    graph = repair.compare(origin, keep_shape=True)

    error_num1 = 0
    for i in set:
        try:
            error_num1 += graph[:][i]["self"]["other"].notnull().sum()
        except:
            continue;
    return error_num0 - error_num1


# def getCorrectRepairs(dfclean, dfrepair, dforigin, set):
#     repair = dfrepair.compare(dforigin, keep_equal=True, keep_shape=True)  # 真正的修复
#     origin = dfclean.compare(dforigin, keep_equal=True, keep_shape=True)  # 理想的修复
#     error_num0 = getErrorNum(dfclean, dforigin, set)  # 所有正确的修复个数
#     graph = repair.compare(origin, keep_shape=True)  # 找到每个属性下面的self，非null部分，就是没修出来的
#     error_num1 = 0
#     for i in set:
#         try:
#             error_num1 += graph[:][i]["self"]["other"].notnull().sum()
#         except:
#             continue;
#     return error_num0 - error_num1;


def getHarmonicMean(a, b):
    # a, b = input().split(",")
    a = float(a)
    b = float(b)
    print(2 * a * b / (a + b))


def getErrorValue(df_1, df_2, set):
    result = pd.DataFrame()
    attribute_set = set + ["index"]
    for attribute in attribute_set:
        if attribute == "index":
            continue
        mask = df_1[attribute].compare(df_2[attribute]).iloc[:]["self"].notnull()
        indices = mask.index[mask]
        df1_difference = df_1.loc[indices][[attribute, 'index']]
        df2_difference = df_2.loc[indices][[attribute, 'index']]
        # 选择'a'不相等的行
        # df1_difference = df_1.loc[indices][df_1['areacode'] != df_2['areacode']][attribute_set]
        # df2_difference = df_2.loc[indices][df_1['areacode'] != df_2['areacode']][attribute_set]
        ans = pd.concat([df1_difference, df2_difference], axis=1)
        print(ans)
        if result.empty:
            result = ans
            # separator_df = pd.DataFrame([[attribute,'index']])
            # separator_df = pd.concat([separator_df, separator_df], axis=1)
            # print(separator_df)

            # result = pd.concat([result, ans], axis=0)

    return result
    # # 输出差异值对
    # print("df1中的差异值:")
    # print(df1_difference)
    #
    # print("df2中的差异值:")
    # print(df_clean1_difference)
