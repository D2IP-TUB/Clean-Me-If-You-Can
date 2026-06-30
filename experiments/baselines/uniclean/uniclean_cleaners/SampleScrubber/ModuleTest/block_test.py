"""
Example 2: Flight data.
验证分块策略和模式匹配修复
"""

import pandas as pd

from SampleScrubber.ModuleTest import logsetting
from SampleScrubber.param_selector import DEFAULT_CONFIG, customclean
from SampleScrubber.cleaner.multiple import AttrRelation
from SampleScrubber.cleaner.single import Date, Pattern
from sysFlowVisualizer.FD import FunctionalDependency

print("Logs saved in " + logsetting.logfilename);
f = open('../../TestDataset/smallDatasets/airplane_small.txt', 'r')
data = []
for line in f.readlines():
    parsed = line.strip().split('\t')
    data.append({str(i): j for i, j in enumerate(parsed)})
df = pd.DataFrame(data)

patterns = [Date("2", "%m/%d/%Y %I:%M %p"),
            Date("3", "%m/%d/%Y %I:%M %p"),
            Pattern("4", '^[a-zA-Z][0-9]+'),
            Date("5", "%m/%d/%Y %I:%M %p"),
            Date("6", "%m/%d/%Y %I:%M %p"),
            Pattern("7", '^[a-zA-Z][0-9]+')]

objects = [FunctionalDependency(["1"], [str(i)]) for i in range(2, 8)]
print(objects)
cleaner = objects[0]
for i in range(1, len(objects)):
    cleaner = cleaner + objects[i]
pd.set_option('display.max_columns', 10)
config = DEFAULT_CONFIG
config['simfunc'] = {'a': 'jaccard'}
# print(df)
df = df.reset_index()
operation, output, _,_= customclean(df, precleaners=patterns, cleaners=objects, partition="1")
print(
    "---------------------------------------------------------------------------------------------------------------------------------------------------")
print(operation, output)
