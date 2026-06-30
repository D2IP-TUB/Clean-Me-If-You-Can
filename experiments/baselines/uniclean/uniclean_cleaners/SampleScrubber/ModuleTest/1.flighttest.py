"""
Example 2: Flight data.
Run this example with `python examples/block_test.py` from the `dataclean`
directory.
"""

import time

import pandas as pd

import logsetting
from SampleScrubber.param_selector import customclean, DEFAULT_CONFIG
from SampleScrubber.cleaner.multiple import AttrRelation
from SampleScrubber.cleaner.single import Date
from SampleScrubber.util.getNum import getErrorNum, getCorrectRepairs

print("Logs saved in " + logsetting.logfilename);
df_clean = pd.read_csv('../../TestDataset/standardData/flights/flights_clean.csv')
df_dirty = pd.read_csv('../../TestDataset/standardData/flights/dirty_mix_0.5/dirty_flights.csv')
df_dirty1 = df_dirty.iloc[:].copy(deep=True)
df_clean1 = df_clean.iloc[:].copy(deep=True)
df_clean1 = df_clean1.reset_index()
df_dirty1 = df_dirty1.reset_index()
df_dirty = df_dirty.reset_index()
set = ["sched_dep_time", "act_dep_time", "sched_arr_time", "act_arr_time"]
# set=["flight"]
error_num0 = getErrorNum(df_dirty1, df_clean1, set)
print(error_num0)

patterns = [Date("sched_dep_time", "%I:%M %p"),
            Date("act_dep_time", "%I:%M %p"),
            Date("sched_arr_time", "%I:%M %p"),
            Date("act_arr_time", "%I:%M %p")]
time_start = time.time()
objects = [AttrRelation(["flight"], [str(i)]) for i in
           ["sched_dep_time", "act_dep_time", "sched_arr_time", "act_arr_time"]]
print(objects)
cleaner = objects[0]
for i in range(1, len(objects)):
    cleaner = cleaner + objects[i]
pd.set_option('display.max_columns', 10)
config = DEFAULT_CONFIG
config['simfunc'] = {'a': 'jaccard'}

print("begin clean")
operation, output, bestopList, [positiveOp, neutralOp, negativeOp, score]= customclean(df_dirty1, precleaners=patterns,
                                                                          cleaners=objects, partition="flight")

time_end = time.time()

total_repair = getErrorNum(output, df_dirty, set)
now_error = getErrorNum(output, df_clean1, set)
total_error = getErrorNum(df_dirty, df_clean1, set)
correct_repairs = getCorrectRepairs(df_clean1, output, df_dirty, set)

precision = correct_repairs / total_repair
recall = correct_repairs / total_error
print("score", score)
print(operation, output)
print("total_repair", total_repair)
print("correct_repair", correct_repairs)
print("now_error", now_error)
print("total_error", total_error)

print("precision", precision)
print("recall", recall)
print("F1", 2 * precision * recall / (precision + recall))

t = time_end - time_start
print("time:", t)
print("positiveOp:", positiveOp)
print("neutralOp:", neutralOp)
print("negativeOp:", negativeOp)
output.to_csv('../../TestDataset/cleanresult/flight/flights_repair0.csv')
