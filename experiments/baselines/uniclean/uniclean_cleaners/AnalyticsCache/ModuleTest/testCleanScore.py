# # 读取CSV文件，并设置index列
# clean_data = pd.read_csv('cleanTax200.csv', index_col='index')
# dirty_data = pd.read_csv('dirty_data.csv', index_col='index')
# cleaned_data = pd.read_csv('cleaned_data.csv', index_col='index')
# 读取CSV文件，并设置index列
import pandas as pd

from AnalyticsCache.getScore import calculate_accuracy_and_recall

clean_data = pd.read_csv('../../TestDataset/result/tax100w/tax_1000k_clean.csv', index_col='index')
dirty_data = pd.read_csv('../../TestDataset/result/tax100w/Tax100w_dirty_data.csv', index_col='index')
cleaned_data = pd.read_csv('../../TestDataset/result/Tax100w_2Cleaned/part-00000-e7adcaf1-9a87-4d36-829f-85c6082d9c73-c000.csv', index_col='index')
# clean_data = pd.read_csv('../../TestDataset/result/tax200k/cleanTax200.csv', index_col='index')
# dirty_data = pd.read_csv('../../TestDataset/result/tax200k/dirty_data.csv', index_col='index')
# cleaned_data = pd.read_csv('../../TestDataset/result/tax200k/cleaned_data.csv', index_col='index')

# 指定属性集合
# attributes = ['fname','lname','gender','areacode','phone','city','state','zip','maritalstatus','haschild','salary','rate','singleexemp','marriedexemp','childexemp']
attributes = ['areacode','city','state','zip',]

# 计算修复准确率和召回率
accuracy, recall = calculate_accuracy_and_recall(clean_data, dirty_data, cleaned_data, attributes)

print(f"修复准确率: {accuracy}")
print(f"修复召回率: {recall}")