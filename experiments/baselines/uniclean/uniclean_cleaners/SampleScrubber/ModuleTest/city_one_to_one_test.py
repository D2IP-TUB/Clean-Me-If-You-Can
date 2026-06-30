"""
Example 1: 城市缩写数据集清洗.
"""

import logsetting
from SampleScrubber.param_selector import DEFAULT_CONFIG, customclean
from SampleScrubber.cleaner.multiple import AttrRelation

print("Logs saved in " + logsetting.logfilename);
data = [{'a': 'New Yorks', 'b': 'NY','index': 1},  # 脏
        {'a': 'New York', 'b': 'NY', 'index': 2},
        {'a': 'San Francisco', 'b': 'SF', 'index': 3},
        {'a': 'San Francisco', 'b': 'SF', 'index': 4},
        {'a': 'San Jose', 'b': 'SJ', 'index': 5},
        {'a': 'New York', 'b': 'NY', 'index': 6},
        {'a': 'San Francisco', 'b': 'SFO', 'index': 7},  # 脏
        {'a': 'Berkeley City', 'b': 'Bk', 'index': 8},
        {'a': 'San Mateo', 'b': 'SMO', 'index': 9},
        {'a': 'Albany', 'b': 'AB', 'index': 10},
        {'a': 'San Mateo', 'b': 'SM', 'index': 11},  # 脏
        {'a': 'San', 'b': 'SMO', 'index': 12},
        {'a': 'San', 'b': 'SMO', 'index': 13}
        ]

import pandas as pd

df = pd.DataFrame(data)  ##将数据加载到一个Pandas DataFrame中
print(df)
constraint1 = AttrRelation(["a"], ["b"],'OneToOneAB',ExtDict={'b': ['SF', 'SMO']}) * AttrRelation(["b"], ["a"],'OneToOneBA',ExtDict={'a': ['New York', 'San Francisco']}) * 0.5  # 一对一约束

config = DEFAULT_CONFIG
# config['maxSearch'] = 3
# config['simfunc'] = {'a': 'jaccard'}

dcprogram, output, _, _ = customclean(df, cleaners=[constraint1], config=config)
print("OpList:")
print(dcprogram)
print("Cleaned data:")
print(output)
