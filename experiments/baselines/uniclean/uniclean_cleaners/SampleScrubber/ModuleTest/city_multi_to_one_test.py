"""
Example 1: 城市缩写数据集清洗.
"""

import logsetting
from SampleScrubber.param_selector import DEFAULT_CONFIG, customclean
from SampleScrubber.cleaner.multiple import  AttrRelation

print("Logs saved in " + logsetting.logfilename);
data = [
    # New York and NY
    {'index': 1, 'a': 'New York', 'b': 'NY', 'c': 'Big Apple'},
    {'index': 2, 'a': 'New York', 'b': 'NY', 'c': 'Big Apple'},
    {'index': 3, 'a': 'New York', 'b': 'NY', 'c': 'Big Apple'},
    {'index': 4, 'a': 'New York', 'b': 'NY', 'c': 'Big Apple'},
    {'index': 5, 'a': 'New York', 'b': 'NY', 'c': 'Big Apple City'},  # 脏

    # San Francisco and SF
    {'index': 6, 'a': 'San Francisco', 'b': 'SF', 'c': 'Bay Area'},
    {'index': 7, 'a': 'San Francisco', 'b': 'SF', 'c': 'Bay Area'},
    {'index': 8, 'a': 'San Francisco', 'b': 'SF', 'c': 'Bay Area'},
    {'index': 9, 'a': 'San Francisco', 'b': 'SF', 'c': 'Bay Area'},
    {'index': 10, 'a': 'San Francisco', 'b': 'SFO', 'c': 'Bay Area Airport'},  # 脏

    # Los Angeles and LA
    {'index': 11, 'a': 'Los Angeles', 'b': 'LA', 'c': 'City of Angels'},
    {'index': 12, 'a': 'Los Angeles', 'b': 'LA', 'c': 'City of Angels'},
    {'index': 13, 'a': 'Los Angeles', 'b': 'LA', 'c': 'City of Angels'},
    {'index': 14, 'a': 'Los Angeles', 'b': 'LA', 'c': 'City of Angels'},
    {'index': 15, 'a': 'Los Angeles', 'b': 'LA', 'c': 'City of Angles'},  # 脏

    # San Jose and SJ
    {'index': 16, 'a': 'San Jose', 'b': 'SJ', 'c': 'Silicon Valley'},
    {'index': 17, 'a': 'San Jose', 'b': 'SJ', 'c': 'Silicon Valley'},
    {'index': 18, 'a': 'San Jose', 'b': 'SJ', 'c': 'Silicon Valley'},
    {'index': 19, 'a': 'San Jose', 'b': 'SJ', 'c': 'Silicon Valley'},
    {'index': 20, 'a': 'San Jose', 'b': 'SJ', 'c': 'Silicon Valley Area'},  # 脏

    # San Mateo and SM
    {'index': 21, 'a': 'San Mateo', 'b': 'SM', 'c': 'Peninsula'},
    {'index': 22, 'a': 'San Mateo', 'b': 'SM', 'c': 'Peninsula'},
    {'index': 23, 'a': 'San Mateo', 'b': 'SM', 'c': 'Peninsula'},
    {'index': 24, 'a': 'San Mateo', 'b': 'SM', 'c': 'Peninsula'},
    {'index': 25, 'a': 'San Mateo', 'b': 'SM', 'c': 'Peninsla'},  # 脏

    # Berkeley and Bk
    {'index': 26, 'a': 'Berkeley', 'b': 'Bk', 'c': 'University City'},
    {'index': 27, 'a': 'Berkeley', 'b': 'Bk', 'c': 'University City'},
    {'index': 28, 'a': 'Berkeley', 'b': 'Bk', 'c': 'University City'},
    {'index': 29, 'a': 'Berkeley', 'b': 'Bk', 'c': 'University City'},
    {'index': 30, 'a': 'Berkeley', 'b': 'Bk', 'c': 'Univ City'}  # 脏
]


import pandas as pd

df = pd.DataFrame(data)  ##将数据加载到一个Pandas DataFrame中
print(df)
constraint1 = [AttrRelation(["a"], ["b"]) * AttrRelation(["b"], ["a"]), AttrRelation(["a", "b"], ["c"])] # 一对一约束

config = DEFAULT_CONFIG
# config['maxSearch'] = 3
# config['simfunc'] = {'a': 'jaccard'}

dcprogram, output, _, _ = customclean(df, cleaners=constraint1, config=config)
print("OpList:")
print(dcprogram)
print("Cleaned data:")
print(output)
