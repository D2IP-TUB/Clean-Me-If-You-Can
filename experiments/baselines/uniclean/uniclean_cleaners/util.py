import os
import shutil
import sys
import pandas as pd
from AnalyticsCache.getScore import calculate_accuracy_and_recall, calculate_all_metrics, calculate_detection_metrics
from AnalyticsCache.insert_null import inject_missing_values


def save_cleaned_data(data, table_path, table_name):
    tmp_dir = table_path + 'Cleaned'
    # quoteAll=true forces every field to be quoted so pandas can always parse
    # the output correctly regardless of commas in name/road values.
    # escape='"' uses RFC-4180 doubling instead of Spark's default backslash
    # escaping, which pandas does not recognise by default.
    data.coalesce(4).write.mode('overwrite').option("quoteAll", "true").option("escape", '"').csv(tmp_dir, header=True)
    target_file = os.path.join(table_path, f'{table_name}Cleaned.csv')
    part_files = sorted(
        os.path.join(tmp_dir, f) for f in os.listdir(tmp_dir) if f.endswith('.csv')
    )
    if not part_files:
        print("未找到保存的 CSV 文件。")
        return
    with open(target_file, 'w') as outf:
        for i, pf in enumerate(part_files):
            with open(pf, 'r') as inf:
                lines = inf.readlines()
                if i == 0:
                    outf.writelines(lines)
                else:
                    # skip header line for subsequent parts
                    outf.writelines(lines[1:] if lines else [])
    print(f"清洗结果已保存到: {target_file}")


def _is_intish(s):
    """判断字符串是否是整数形式（不含小数点）。"""
    return bool(s) and s.lstrip('-').isdigit()


def _strip_dot_zero(v):
    """把 '1436.0' → '1436'，非整型 .0 不动。"""
    if isinstance(v, str) and v.endswith('.0') and _is_intish(v[:-2]):
        return v[:-2]
    return v


def normalize_cleaned_against_clean(cleaned_path, clean_path, missing_token='empty'):
    """让磁盘上的 cleaned.csv 与 clean.csv 在格式细节上对齐：
       - 整数列里 Spark 写出的 '1436.0' 还原成 '1436'（仅当 clean 同列里没有 'n.0' 形式）
       - 当 clean 同列不用 missing_token 这种占位（即 clean 里没出现 missing_token 字符串），
         把 cleaned 里 inject_missing_values 写出的 missing_token 改成空字符串，与 clean 形态一致
       不动 cleaned 里 dirty 原本就为空（''）的位置——那是"未填补"而非"占位"。
       不动列名/列序/行数。
    """
    clean = pd.read_csv(clean_path, dtype=str, keep_default_na=False)
    cleaned = pd.read_csv(cleaned_path, dtype=str, keep_default_na=False)
    for col in cleaned.columns:
        if col not in clean.columns:
            continue
        clean_vals = set(clean[col].unique())
        # .0 残留处理
        if not any(v.endswith('.0') and _is_intish(v[:-2]) for v in clean_vals):
            cleaned[col] = cleaned[col].apply(_strip_dot_zero)
        # 占位字符串规整：clean 同列若不用 missing_token，把 cleaned 里写的 missing_token 改成 ''
        if missing_token and missing_token not in clean_vals:
            cleaned[col] = cleaned[col].replace(missing_token, '')
    cleaned.to_csv(cleaned_path, index=False)


def evaluate_cleaning_performance(clean_path, dirty_path, cleaned_path, elapsed_time, output_path,table_name,mse_attributes = [], index_col='index', missing_token='empty', col_alias=None):
    """评估清洗效果。

    参数：
        missing_token: 三方共用的缺失值占位字符串。默认 'empty' 兼容原 inject_missing_values 行为。
                       不同数据集 clean.csv 用法不同（如 train/beers 用 'nan'、train/hospital 用 'empty'），
                       应按数据集传入对应值，确保 cleaned.csv 与 clean.csv 缺失表示一致。
        col_alias: dict[str, str]，把 clean/dirty 中的旧列名重命名为新列名（如 train/rayyan 拼写错误的 jounral_abbreviation）。
    """
    print("测评性能开始：")
    inject_missing_values(csv_file=cleaned_path, output_file=cleaned_path, attributes_error_ratio=None,
                          missing_value_in_ori_data='NULL', missing_value_representation=missing_token)
    # 文件级对齐：参照 clean.csv 把 cleaned.csv 的整数列 .0 残留剥掉、缺失占位统一
    normalize_cleaned_against_clean(cleaned_path, clean_path, missing_token=missing_token)
    clean_data = pd.read_csv(clean_path, dtype=str, keep_default_na=False)
    dirty_data = pd.read_csv(dirty_path, dtype=str, keep_default_na=False)
    cleaned_data = pd.read_csv(cleaned_path, dtype=str, keep_default_na=False)
    # 统一索引列名为 'index'，兼容外部数据使用其它名称（如 'ID'）
    if index_col != 'index':
        for df in (clean_data, dirty_data, cleaned_data):
            if index_col in df.columns and 'index' not in df.columns:
                df.rename(columns={index_col: 'index'}, inplace=True)
    # 若 clean/dirty CSV 没有 index 列（如 full/address 数据集），则用行位置作为 index。
    # cleaned_data 可能含 Spark 赋予的 index（monotonically_increasing_id），先按该列排序
    # 以还原原始行序，再统一改为 0-based 顺序整数，确保三方可以按位置对齐。
    if 'index' not in clean_data.columns or 'index' not in dirty_data.columns:
        if 'index' in cleaned_data.columns:
            cleaned_data['index'] = pd.to_numeric(cleaned_data['index'], errors='coerce')
            cleaned_data.sort_values('index', inplace=True)
            cleaned_data.drop(columns=['index'], inplace=True)
        cleaned_data.reset_index(drop=True, inplace=True)
        clean_data.reset_index(drop=True, inplace=True)
        dirty_data.reset_index(drop=True, inplace=True)
        for df in (clean_data, dirty_data, cleaned_data):
            df.insert(0, 'index', range(len(df)))
    # 列重命名（处理上游数据列拼写错误等）
    if col_alias:
        for df in (clean_data, dirty_data, cleaned_data):
            rename_map = {old: new for old, new in col_alias.items() if old in df.columns and new not in df.columns}
            if rename_map:
                df.rename(columns=rename_map, inplace=True)
    # 归一化缺失值表示（仅内存中）：把 NaN / 'nan' / 'NaN' / 'NULL' / 'null' / '' 统一成 missing_token
    # 让三方在同一基准下比较；磁盘上的 cleaned.csv 由 inject_missing_values 已对齐到 missing_token，不再写回
    _missing_tokens = {'nan', 'NaN', 'NULL', 'null', 'None', 'NONE', ''} | {missing_token}
    for df in (clean_data, dirty_data, cleaned_data):
        df.fillna(missing_token, inplace=True)
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str).where(~df[col].astype(str).isin(_missing_tokens), missing_token)
    index_attribute = 'index'
    # 仅评估三方共有的列，避免 cleaned 因清洗器只覆盖部分列而缺列时报 KeyError
    common_cols = (set(clean_data.columns) & set(dirty_data.columns) & set(cleaned_data.columns)) - {index_attribute}
    eval_attrs = [c for c in clean_data.columns if c in common_cols]
    if not eval_attrs:
        eval_attrs = clean_data.columns.tolist()
    results = calculate_all_metrics(clean_data, dirty_data, cleaned_data, eval_attrs, output_path,
                                    table_name, index_attribute=index_attribute, mse_attributes=mse_attributes)

    # Detection evaluation (uses detected_cells.csv written by CleanonLocalWithnoSmple)
    detected_cells_path = os.path.join(output_path, 'detected_cells.csv')
    det_results = calculate_detection_metrics(
        clean_data, dirty_data, detected_cells_path, eval_attrs, output_path, table_name,
        index_attribute=index_attribute
    )
    results.update(det_results)

    results_path = os.path.join(output_path, f"{table_name}_total_evaluation.txt")
    with open(results_path, 'w', encoding='utf-8') as f:
        sys.stdout = f
        print_results(results, elapsed_time, clean_data)
        sys.stdout = sys.__stdout__

    print_results(results, elapsed_time, clean_data)
    print(f"测评结束，详细测评日志见：{output_path}")


def print_results(results, elapsed_time, clean_data):
    print("测试结果:")
    print("--- Correction (restricted to actual error cells) ---")
    print(f"Correction Precision: {results.get('accuracy')}")
    print(f"Correction Recall:    {results.get('recall')}")
    print(f"Correction F1:        {results.get('f1_score')}")
    print("--- Detection (changed cells treated as detected) ---")
    print(f"Detection Precision: {results.get('det_precision')}")
    print(f"Detection Recall:    {results.get('det_recall')}")
    print(f"Detection F1:        {results.get('det_f1')}")
    print("--- Other Metrics ---")
    print(f"EDR: {results.get('edr')}")
    print(f"Hybrid Distance: {results.get('hybrid_distance')}")
    print(f"R-EDR: {results.get('r_edr')}")
    print(f"time(s): {elapsed_time}")
    print(f"speed: {100 * float(elapsed_time) / clean_data.shape[0]} seconds/100num")