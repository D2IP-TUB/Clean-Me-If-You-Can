from pathlib import Path
import pandas as pd

# Paths to your CSV files
_FLIGHTS = Path(__file__).resolve().parents[3] / 'datasets' / 'joinable_tables' / 'flights_without_key_errors' / 'joined' / 'flights_oerr'
clean_data_path = str(_FLIGHTS / 'clean.csv')
dirty_data_path = str(_FLIGHTS / 'dirty.csv')
result_data_path = str(_FLIGHTS / 'perfect_error_detection.csv')
# clean_data = pd.read_csv(clean_data_path, dtype=str, encoding='utf-8', keep_default_na=False, na_values=['', ])
# dirty_data = pd.read_csv(dirty_data_path, dtype=str, encoding='utf-8', keep_default_na=False, na_values=['', ])
clean_data = pd.read_csv(clean_data_path, dtype=str, encoding='utf-8')
dirty_data = pd.read_csv(dirty_data_path, dtype=str, encoding='utf-8')
clean_data.fillna('null', inplace=True)
dirty_data.fillna('null', inplace=True)
indicators = (clean_data != dirty_data).astype(int)
print(indicators.sum().sum())
# 保存指示符DataFrame为CSV文件
indicators.to_csv(result_data_path, index=False, encoding='utf-8')
# Read the clean and dirty data
print('Comparison complete. Discrepancies marked in perfect_error_detection.csv.')