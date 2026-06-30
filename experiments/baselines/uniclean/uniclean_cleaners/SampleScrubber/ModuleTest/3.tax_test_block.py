import time

import pandas as pd

from SampleScrubber.ModuleTest import logsetting
from SampleScrubber.param_selector import DEFAULT_CONFIG, customclean
from SampleScrubber.cleaner.multiple import AttrRelation
from SampleScrubber.cleaner.single import Pattern
from SampleScrubber.util.getNum import getErrorNum, getCorrectRepairs, getErrorValue

print("Logs saved in " + logsetting.logfilename);
# df.compare(df_clean).to_csv("clean_form_data.csv", mode="a" ,index = False, header=False,encoding='gb18030')

set = ["state", "areacode", 'zip']
df1 = pd.read_csv('../../TestDataset/standardData/tax_20k/dirty_dependencies_0.5/dirty_tax.csv')
# df1 = pd.read_csv('../../TestDataset/standardData/tax_20k/tax_20k_clean.csv')
df_clean1 = pd.read_csv('../../TestDataset/standardData/tax_20k/clean.csv')
# 按照name1列进行排序
# df1 = df1.sort_values(by='areacode').sort_values(by='zip')
# df_clean1 = df_clean1.sort_values(by='areacode').sort_values(by='zip')

df_clean1 = df_clean1[0:].reset_index()
df1 = df1[0:].reset_index()
df_clean1['zip'] = df_clean1['zip'].astype(float)
df_clean1['zip'] = df_clean1['zip'].astype(str)
df1['zip'] = df1['zip'].astype(float)
df1['zip'] = df1['zip'].astype(str)
# print(df1['zip'])
# print(df_clean1['zip'])
# error_num00 = getErrorNum(df1[100:200],df_clean1[100:200],set)
# print(error_num00)

df_clean1['areacode'] = df_clean1['areacode'].astype(str)
df1['areacode'] = df1['areacode'].astype(str)
df_clean1['zip'] = df_clean1['zip'].astype(str)
df1['zip'] = df1['zip'].astype(str)
df_clean1['salary'] = df_clean1['salary'].astype(str)
df1['salary'] = df1['salary'].astype(str)
df_clean1['rate'] = df_clean1['rate'].astype(str)
df1['rate'] = df1['rate'].astype(str)

df_clean = df_clean1.copy(deep=True)
df = df1.copy(deep=True)
# print(getErrorValue(df,df_clean,set))

# error_num01 = getErrorNum(df,df_clean,set)
# print(error_num01)


config = DEFAULT_CONFIG

# 开始定义patterns

patterns = []
##定义正则和字典
# patterns += [Pattern('zip',"[1-9][0-9]{4}")]
# patterns += [Pattern('maritalstatus', "[M|S]")]
# patterns += [Pattern('haschild', "[Y|N]")]
# patterns += [Pattern('Address1', "^[0-9].*")]
# patterns += [Pattern('Address1', "^[0-9].*")]

patterns += [Pattern('gender', "[M|F]")]
patterns += [Pattern('areacode', "[0-9][0-9][0-9]")]
patterns += [Pattern('state', "[A-Z]{2}")]

time_start = time.time()
# print(getErrorValue(df,df_clean1,set))
operation, output, _, [_, _, _, _] = customclean(df, precleaners=patterns, config=config)

models2 = []
models2.append(AttrRelation(['zip'], ["state"]) + AttrRelation(['areacode'], ["state"]))
# models2.append(FunctionalDependency(['areacode'], ["state"]))
operation3, output, score3, [positiveOp3, neutralOp3, negativeOp3, bestopList3] = customclean(output, cleaners=models2,
                                                                                              partition=["zip","areacode"],
                                                                                              config=config)

models = []
# models.append(FunctionalDependency( ['zip'], ["state"])+FunctionalDependency(['areacode'], ["state"])+FunctionalDependency(["zip"], ["city"]))
models.append(AttrRelation(["zip"], ["state"]))
operation1, output, score1, [positiveOp1, neutralOp1, negativeOp1, bestopList1] = customclean(output, cleaners=models,
                                                                                              partition=['areacode'],
                                                                                              config=config)

models1 = []
models1.append(AttrRelation(["fname", "lname"], ["gender"]))
operation2, output, score2, [positiveOp2, neutralOp2, negativeOp2, bestopList2] = customclean(output, cleaners=models1,
                                                                                              partition="fname",
                                                                                              config=config)

time_end = time.time()
print("--------------------------------------------------------")
print(operation1 * operation2 * operation3)

print('time cost', time_end - time_start, 's')

total_repair = getErrorNum(output, df1, set)
now_error = getErrorNum(output, df_clean1, set)
total_error = getErrorNum(df1, df_clean1, set)

correct_repairs = getCorrectRepairs(df_clean1, output, df1, set)

precision = correct_repairs / total_repair
recall = correct_repairs / total_error

print("total_repair", total_repair)
print("correct_repair", correct_repairs)
print("now_error", now_error)
print("total_error", total_error)

print("precision", precision)
print(getErrorValue(output, df_clean1, set))
print("recall", recall)
print("F1", 2 * precision * recall / (precision + recall))
# print("total op:"+str(score1[0]+score2[0]))
# print("pruned op:"+str(score1[1]+score2[1]))
# print("positiveOp1:",len(positiveOp1))
# print("neutralOp1:",len(neutralOp1))
# print("negativeOp1:",len(negativeOp1))
# print("positiveOp2:",len(positiveOp2))
# print("neutralOp2:",len(neutralOp2))
# print("negativeOp2:",len(negativeOp2))
# print("positiveOp3:",len(positiveOp3))
# print("neutralOp3:",len(neutralOp3))
# print("negativeOp3:",len(negativeOp3))
output.to_csv('../../TestDataset/cleanresult/tax/result.csv')
