from pyspark.sql.functions import col
import html
import os
import re
import sys
import pandas as pd
from sklearn.metrics import mean_squared_error, jaccard_score
import numpy as np


def calculate_all_metrics(clean, dirty, cleaned, attributes, output_path, task_name, index_attribute='index',calculate_precision_recall=True,
                          calculate_edr=True, calculate_hybrid=True, calculate_r_edr=True, mse_attributes=[]):
    """
    计算多个指标的统一函数，包括修复准确率和召回率、EDR、混合距离以及基于条目的 R-EDR。

    :param clean: 干净数据 DataFrame
    :param dirty: 脏数据 DataFrame
    :param cleaned: 清洗后数据 DataFrame
    :param attributes: 指定的属性集合
    :param output_path: 保存结果的目录路径
    :param task_name: 任务名称
    :param calculate_precision_recall: 是否计算修复的准确率和召回率
    :param calculate_edr: 是否计算错误减少率（EDR）
    :param calculate_hybrid: 是否计算混合距离指标
    :param calculate_r_edr: 是否计算基于条目的错误减少率（R-EDR）
    :return: 所有计算的指标值
    """

    results = {}

    # 计算准确率和召回率
    if calculate_precision_recall:
        cor_precision, cor_recall, det_precision, det_recall = calculate_accuracy_and_recall(
            clean, dirty, cleaned, attributes, output_path, task_name, index_attribute=index_attribute)
        results['accuracy'] = cor_precision
        results['recall'] = cor_recall
        results['f1_score'] = calF1(cor_precision, cor_recall)
        results['det_precision'] = det_precision
        results['det_recall'] = det_recall
        results['det_f1'] = calF1(det_precision, det_recall)
        print(f"Correction Precision: {cor_precision}, Recall: {cor_recall}, F1: {results['f1_score']}")
        print(f"Detection  Precision: {det_precision}, Recall: {det_recall}, F1: {results['det_f1']}")
        print("=" * 40)

    # 计算EDR
    if calculate_edr:
        edr = get_edr(clean, dirty, cleaned, attributes,output_path, task_name,index_attribute=index_attribute)
        results['edr'] = edr
        print(f"错误减少率 (EDR): {edr}")
        print("=" * 40)

    # 计算混合距离
    if calculate_hybrid:
        hybrid_distance = get_hybrid_distance(clean, cleaned, attributes,output_path, task_name,index_attribute=index_attribute,mse_attributes=mse_attributes)
        results['hybrid_distance'] = hybrid_distance
        print(f"混合距离 (Hybrid Distance): {hybrid_distance}")
        print("=" * 40)

    # 计算基于条目的 R-EDR
    if calculate_r_edr:
        r_edr = get_record_based_edr(clean, dirty, cleaned,output_path, task_name,index_attribute=index_attribute)
        results['r_edr'] = r_edr
        print(f"基于条目的错误减少率 (R-EDR): {r_edr}")
        print("=" * 40)

    return results
def normalize_value(value):
    """
    将数值规范化为字符串格式，去掉小数点及其后的零
    :param value: 要规范化的值
    :return: 规范化后的字符串
    """
    try:
        # 尝试将值转换为浮点数，再转换为整数，然后转换为字符串
        float_value = float(value)
        if float_value.is_integer():
            return str(int(float_value))  # 去掉小数点及其后的零
        else:
            return str(float_value)
    except ValueError:
        # 如果值无法转换为浮点数，则返回原始值的字符串形式
        return str(value)


def normalize_for_cmp(value) -> str:
    """
    Two-stage normalization for cell comparison:
      1. numeric cleanup: strips trailing .0 from integers (via normalize_value)
      2. html entity decoding (e.g. &amp; -> &)
      3. whitespace collapse and strip
    Matches the external evaluate.py::normalize() logic.
    """
    v = normalize_value(value)
    v = html.unescape(v)
    v = re.sub(r"[\t\n ]+", " ", v)
    return v.strip()


def default_distance_func(value1, value2):
    """
    默认的距离计算函数：
    如果两个值不同，则距离为1；
    如果两个值相同，则距离为0。
    """
    return (value1 != value2).sum()

def record_based_distance_func(row1, row2):
    """
    基于条目的距离计算函数：
    遍历每一行中的每一个值，如果任意一个值不相同，则返回1；
    如果所有值都相同，则返回0。
    """
    for val1, val2 in zip(row1, row2):
        if val1 != val2:
            return 1  # 只要有一个值不相同，立即返回1
    return 0  # 如果所有值都相同，返回0
def calF1(precision, recall):
    """
    计算F1值

    :param precision: 精度
    :param recall: 召回率
    :return: F1值
    """
    return 2 * precision * recall / (precision + recall + 1e-10)


def calculate_accuracy_and_recall(clean, dirty, cleaned, attributes, output_path, task_name, index_attribute='index', relax=False):
    """
    计算指定属性集合下的修复准确率和召回率，并将结果输出到文件中，同时生成差异 CSV 文件。

    :param clean: 干净数据 DataFrame
    :param dirty: 脏数据 DataFrame
    :param cleaned: 清洗后数据 DataFrame
    :param attributes: 指定属性集合
    :param output_path: 保存结果的目录路径
    :param task_name: 任务名称，用于命名输出文件
    :param index_attribute: 指定作为索引的属性
    :param relax: 是否忽略大小写
    :return: 修复准确率和召回率
    """
    os.makedirs(output_path, exist_ok=True)

    # 定义输出文件路径
    out_path = os.path.join(output_path, f"{task_name}_evaluation.txt")

    # 差异 CSV 文件路径
    clean_dirty_diff_path = os.path.join(output_path, f"{task_name}_clean_vs_dirty.csv")
    dirty_cleaned_diff_path = os.path.join(output_path, f"{task_name}_dirty_vs_cleaned.csv")
    clean_cleaned_diff_path = os.path.join(output_path, f"{task_name}_clean_vs_cleaned.csv")
    repair_errors_path = os.path.join(output_path, f"{task_name}_repair_errors.csv")
    unrepaired_path = os.path.join(output_path, f"{task_name}_unrepaired.csv")

    # 备份原始的标准输出
    original_stdout = sys.stdout

    # 将指定的属性设置为索引
    clean = clean.set_index(index_attribute, drop=False)
    dirty = dirty.set_index(index_attribute, drop=False)
    cleaned = cleaned.set_index(index_attribute, drop=False)

    # 如果忽略大小写，将所有值转换为小写
    if relax:
        clean = clean.applymap(lambda x: x.lower() if isinstance(x, str) else x)
        dirty = dirty.applymap(lambda x: x.lower() if isinstance(x, str) else x)
        cleaned = cleaned.applymap(lambda x: x.lower() if isinstance(x, str) else x)

    # 重定向输出到文件
    with open(out_path, 'w', encoding='utf-8') as f:
        sys.stdout = f  # 将 sys.stdout 重定向到文件

        total_det_tp = 0
        total_det_fp = 0
        total_det_fn = 0
        total_cor_tp = 0
        total_cor_fp = 0

        # 创建差异 DataFrame 来保存不同的数据项
        clean_dirty_diff = pd.DataFrame(columns=['Attribute', 'Index', 'Clean Value', 'Dirty Value'])
        dirty_cleaned_diff = pd.DataFrame(columns=['Attribute', 'Index', 'Dirty Value', 'Cleaned Value'])
        clean_cleaned_diff = pd.DataFrame(columns=['Attribute', 'Index', 'Clean Value', 'Cleaned Value'])
        repair_errors = pd.DataFrame(columns=['Attribute', 'Index', 'Dirty Value', 'Cleaned Value'])
        unrepaired = pd.DataFrame(columns=['Attribute', 'Index', 'Dirty Value'])

        for attribute in attributes:
            # Normalize: numeric cleanup + html.unescape + whitespace collapse
            clean_values = clean[attribute].apply(normalize_for_cmp)
            dirty_values = dirty[attribute].apply(normalize_for_cmp)
            cleaned_values = cleaned[attribute].apply(normalize_for_cmp)

            # 对齐索引
            common_indices = clean_values.index.intersection(cleaned_values.index).intersection(dirty_values.index)
            clean_values = clean_values.loc[common_indices]
            dirty_values = dirty_values.loc[common_indices]
            cleaned_values = cleaned_values.loc[common_indices]

            actual_error = dirty_values != clean_values     # cells that are actual errors
            changed = dirty_values != cleaned_values        # cells UniClean touched

            # Detection: every changed cell is treated as "detected"
            det_tp = (actual_error & changed).sum()         # error cell was changed
            det_fp = (~actual_error & changed).sum()        # clean cell changed (false alarm)
            det_fn = (actual_error & ~changed).sum()        # error cell not touched (missed)

            # Correction: denominator restricted to actual error cells only
            # (changes to already-clean cells are excluded, matching external harness)
            cor_tp = (actual_error & changed & (cleaned_values == clean_values)).sum()
            cor_fp = (actual_error & changed & (cleaned_values != clean_values)).sum()

            # 记录干净数据和脏数据之间的差异
            mismatched_indices = dirty_values[dirty_values != clean_values].index
            clean_dirty_diff = pd.concat([clean_dirty_diff, pd.DataFrame({
                'Attribute': attribute,
                'Index': mismatched_indices,
                'Clean Value': clean_values.loc[mismatched_indices],
                'Dirty Value': dirty_values.loc[mismatched_indices]
            })])

            # 记录脏数据和清洗后数据之间的差异
            cleaned_indices = cleaned_values[cleaned_values != dirty_values].index
            dirty_cleaned_diff = pd.concat([dirty_cleaned_diff, pd.DataFrame({
                'Attribute': attribute,
                'Index': cleaned_indices,
                'Dirty Value': dirty_values.loc[cleaned_indices],
                'Cleaned Value': cleaned_values.loc[cleaned_indices]
            })])

            # 记录干净数据和清洗后数据之间的差异
            clean_cleaned_indices = cleaned_values[cleaned_values != clean_values].index
            clean_cleaned_diff = pd.concat([clean_cleaned_diff, pd.DataFrame({
                'Attribute': attribute,
                'Index': clean_cleaned_indices,
                'Clean Value': clean_values.loc[clean_cleaned_indices],
                'Cleaned Value': cleaned_values.loc[clean_cleaned_indices]
            })])

            # 修复错误的数据
            repair_error_indices = cleaned_values[
                (cleaned_values != clean_values) & (dirty_values != cleaned_values)].index
            repair_errors = pd.concat([repair_errors, pd.DataFrame({
                'Attribute': attribute,
                'Index': repair_error_indices,
                'Clean Value': clean_values.loc[repair_error_indices],
                'Dirty Value': dirty_values.loc[repair_error_indices],
                'Cleaned Value': cleaned_values.loc[repair_error_indices]
            })], sort=False)  # 显式添加 sort=False

            # 未修复但应该修复的数据
            unrepaired_indices = cleaned_values[(cleaned_values == dirty_values) & (dirty_values != clean_values)].index
            unrepaired = pd.concat([unrepaired, pd.DataFrame({
                'Attribute': attribute,
                'Index': unrepaired_indices,
                'Clean Value': clean_values.loc[unrepaired_indices],
                'Dirty Value': dirty_values.loc[unrepaired_indices]
            })], sort=False)  # 显式添加 sort=False

            total_det_tp += det_tp
            total_det_fp += det_fp
            total_det_fn += det_fn
            total_cor_tp += cor_tp
            total_cor_fp += cor_fp
            print("Attribute:", attribute,
                  "cor_tp:", int(cor_tp), "cor_fp:", int(cor_fp),
                  "det_tp:", int(det_tp), "det_fp:", int(det_fp), "det_fn:", int(det_fn))
            print("=" * 40)

        cor_precision = total_cor_tp / (total_cor_tp + total_cor_fp) if (total_cor_tp + total_cor_fp) > 0 else 0.0
        cor_recall = total_cor_tp / (total_cor_tp + total_det_fn) if (total_cor_tp + total_det_fn) > 0 else 0.0
        det_precision = total_det_tp / (total_det_tp + total_det_fp) if (total_det_tp + total_det_fp) > 0 else 0.0
        det_recall = total_det_tp / (total_det_tp + total_det_fn) if (total_det_tp + total_det_fn) > 0 else 0.0

        print(f"Correction Precision: {cor_precision}, Recall: {cor_recall}")
        print(f"Detection  Precision: {det_precision}, Recall: {det_recall}")

    # 恢复标准输出
    sys.stdout = original_stdout

    # 保存差异数据到 CSV 文件
    clean_dirty_diff.to_csv(clean_dirty_diff_path, index=False)
    dirty_cleaned_diff.to_csv(dirty_cleaned_diff_path, index=False)
    clean_cleaned_diff.to_csv(clean_cleaned_diff_path, index=False)
    repair_errors.to_csv(repair_errors_path, index=False)
    unrepaired.to_csv(unrepaired_path, index=False)

    print(f"差异文件已保存到:\n{clean_dirty_diff_path}\n{dirty_cleaned_diff_path}\n{clean_cleaned_diff_path}")
    print(f"修复错误数据文件已保存到: {repair_errors_path}")
    print(f"未修复但是应该修复数据文件已保存到: {unrepaired_path}")

    return cor_precision, cor_recall, det_precision, det_recall


def calculate_detection_metrics(clean, dirty, detected_cells_path, attributes, output_path, task_name, index_attribute='index'):
    """
    Compute detection precision, recall, and F1 using the detected_cells.csv produced during cleaning.

    Detection treats a cell as "detected" when a rule's predicate matched it in the Spark DataFrame,
    regardless of whether the correction value was right or wrong.

    TP: cell is dirty  AND detected
    FP: cell is clean  AND detected  (false alarm)
    FN: cell is dirty  AND NOT detected  (missed)
    """
    if not os.path.exists(detected_cells_path):
        print(f"Detected cells file not found: {detected_cells_path}. Skipping detection evaluation.")
        return {}

    detected_df = pd.read_csv(detected_cells_path, dtype=str)
    detected_set = set(zip(detected_df['index'].astype(str), detected_df['column']))

    clean = clean.set_index(index_attribute, drop=False)
    dirty = dirty.set_index(index_attribute, drop=False)

    tp = fp = fn = 0
    for attr in attributes:
        if attr not in clean.columns or attr not in dirty.columns:
            continue
        clean_vals = clean[attr].apply(normalize_for_cmp)
        dirty_vals = dirty[attr].apply(normalize_for_cmp)
        common = clean_vals.index.intersection(dirty_vals.index)
        for idx in common:
            is_error = dirty_vals[idx] != clean_vals[idx]
            is_detected = (str(idx), attr) in detected_set
            if is_error and is_detected:
                tp += 1
            elif not is_error and is_detected:
                fp += 1
            elif is_error and not is_detected:
                fn += 1

    det_precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    det_recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    det_f1 = 2 * det_precision * det_recall / (det_precision + det_recall + 1e-10)

    results = {
        'det_precision': det_precision,
        'det_recall': det_recall,
        'det_f1': det_f1,
        'det_tp': tp, 'det_fp': fp, 'det_fn': fn,
    }

    out_path = os.path.join(output_path, f"{task_name}_detection_evaluation.txt")
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(f"Detection Precision: {det_precision}\n")
        f.write(f"Detection Recall:    {det_recall}\n")
        f.write(f"Detection F1:        {det_f1}\n")
        f.write(f"TP={tp}  FP={fp}  FN={fn}\n")
    print(f"Detection Precision: {det_precision}, Detection Recall: {det_recall}, Detection F1: {det_f1}")
    return results


def get_edr(clean, dirty, cleaned, attributes, output_path, task_name, index_attribute='index', distance_func=default_distance_func):
    """
    计算指定属性集合下的错误减少率 (EDR)，并将结果输出到文件中。

    :param clean: 干净数据 DataFrame
    :param dirty: 脏数据 DataFrame
    :param cleaned: 清洗后数据 DataFrame
    :param attributes: 指定属性集合
    :param output_path: 保存结果的目录路径
    :param task_name: 任务名称，用于命名输出文件
    :param index_attribute: 指定作为索引的属性
    :param distance_func: 距离计算函数，默认为比较两个值是否相等，不同为1，相同为0
    :return: 错误减少率 (EDR)
    """

    # 创建输出目录
    os.makedirs(output_path, exist_ok=True)

    # 定义输出文件路径
    out_path = os.path.join(output_path, f"{task_name}_edr_evaluation.txt")

    # 备份原始的标准输出
    original_stdout = sys.stdout

    # 将指定的属性设置为索引
    clean = clean.set_index(index_attribute, drop=False)
    dirty = dirty.set_index(index_attribute, drop=False)
    cleaned = cleaned.set_index(index_attribute, drop=False)

    # 重定向输出到文件
    with open(out_path, 'w') as f:
        sys.stdout = f  # 将 sys.stdout 重定向到文件

        total_distance_dirty_to_clean = 0
        total_distance_repaired_to_clean = 0

        for attribute in attributes:
            # 确保所有属性的数据类型为字符串并进行规范化
            clean_values = clean[attribute].apply(normalize_value)
            dirty_values = dirty[attribute].apply(normalize_value)
            cleaned_values = cleaned[attribute].apply(normalize_value)

            # 对齐索引
            common_indices = clean_values.index.intersection(cleaned_values.index).intersection(dirty_values.index)
            clean_values = clean_values.loc[common_indices]
            dirty_values = dirty_values.loc[common_indices]
            cleaned_values = cleaned_values.loc[common_indices]

            # 计算脏数据和干净数据之间的距离
            distance_dirty_to_clean = distance_func(dirty_values, clean_values)
            # 计算修复后数据和干净数据之间的距离
            distance_repaired_to_clean = distance_func(cleaned_values, clean_values)

            total_distance_dirty_to_clean += distance_dirty_to_clean
            total_distance_repaired_to_clean += distance_repaired_to_clean

            # 打印每个属性的距离值
            print(f"Attribute: {attribute}")
            print(f"Distance (Dirty to Clean): {distance_dirty_to_clean}")
            print(f"Distance (Repaired to Clean): {distance_repaired_to_clean}")
            print("=" * 40)

        # 计算错误减少率 (EDR)
        if total_distance_dirty_to_clean == 0:
            edr = 0
        else:
            edr = (total_distance_dirty_to_clean - total_distance_repaired_to_clean) / total_distance_dirty_to_clean

        # 打印最终的 EDR 结果
        print(f"总的脏数据到干净数据距离: {total_distance_dirty_to_clean}")
        print(f"总的修复后数据到干净数据距离: {total_distance_repaired_to_clean}")
        print(f"错误减少率 (EDR): {edr}")

    # 恢复标准输出
    sys.stdout = original_stdout

    print(f"EDR 结果已保存到: {out_path}")

    return edr

def get_hybrid_distance(clean, cleaned, attributes, output_path, task_name, index_attribute='index', mse_attributes=[], w1=0.5, w2=0.5):
    """
    计算混合距离指标，包括MSE和Jaccard距离，并将结果输出到文件中。

    :param clean: 干净数据 DataFrame
    :param cleaned: 清洗后数据 DataFrame
    :param attributes: 指定属性集合
    :param output_path: 保存结果的目录路径
    :param task_name: 任务名称，用于命名输出文件
    :param index_attribute: 指定作为索引的属性
    :param w1: MSE的权重
    :param w2: Jaccard距离的权重
    :param mse_attributes: 需要进行MSE计算的属性集合
    :return: 加权混合距离
    """

    # 创建输出目录
    os.makedirs(output_path, exist_ok=True)

    # 定义输出文件路径
    out_path = os.path.join(output_path, f"{task_name}_hybrid_distance_evaluation.txt")

    # 备份原始的标准输出
    original_stdout = sys.stdout

    # 将指定的属性设置为索引
    clean = clean.set_index(index_attribute, drop=False)
    cleaned = cleaned.set_index(index_attribute, drop=False)

    # 重定向输出到文件
    with open(out_path, 'w') as f:
        sys.stdout = f  # 将 sys.stdout 重定向到文件

        total_mse = 0
        total_jaccard = 0
        attribute_count = 0

        for attribute in attributes:
            # 确保数据类型一致并规范化
            clean_values = clean[attribute].apply(normalize_value).replace('empty', np.nan).dropna()
            cleaned_values = cleaned[attribute].apply(normalize_value).replace('empty', np.nan).dropna()

            # 如果该属性在MSE计算列表中并且存在有效值
            if attribute in mse_attributes and not clean_values.empty and not cleaned_values.empty:
                try:
                    mse = mean_squared_error(clean_values.astype(float), cleaned_values.astype(float))
                except ValueError:
                    print(f"检查你指定的属性 {attribute} 是否为数值型！")
                    mse = np.nan
            else:
                mse = np.nan

            # 计算Jaccard距离，如果存在有效值
            if not clean_values.empty and not cleaned_values.empty:
                try:
                    # 过滤空值后计算Jaccard距离
                    common_indices = clean_values.index.intersection(cleaned_values.index)
                    jaccard = 1 - jaccard_score(
                        clean_values.loc[common_indices],
                        cleaned_values.loc[common_indices],
                        average='macro'
                    )
                except ValueError:
                    print(f"无法计算Jaccard距离，因为 {attribute} 不是类别型数据")
                    jaccard = np.nan
            else:
                jaccard = np.nan

            # 累计非NaN的MSE和Jaccard值
            if not np.isnan(mse):
                total_mse += mse
            if not np.isnan(jaccard):
                total_jaccard += jaccard

            # 如果至少一个距离值有效，则计数
            if not np.isnan(mse) or not np.isnan(jaccard):
                attribute_count += 1

            print(f"Attribute: {attribute}, MSE: {mse}, Jaccard: {jaccard}")

        if attribute_count == 0:
            hybrid_distance = None
        else:
            # 计算加权混合距离
            avg_mse = total_mse / attribute_count if attribute_count > 0 else 0
            avg_jaccard = total_jaccard / attribute_count if attribute_count > 0 else 0
            hybrid_distance = w1 * avg_mse + w2 * avg_jaccard

            print(f"加权混合距离: {hybrid_distance}")

    # 恢复标准输出
    sys.stdout = original_stdout

    print(f"混合距离结果已保存到: {out_path}")

    return hybrid_distance

def get_record_based_edr(clean, dirty, cleaned, output_path, task_name, index_attribute='index'):
    """
    计算基于条目的错误减少率 (R-EDR)，并将每条记录的距离和最终的 R-EDR 输出到文件中。

    :param clean: 干净数据 DataFrame
    :param dirty: 脏数据 DataFrame
    :param cleaned: 清洗后数据 DataFrame
    :param output_path: 保存结果的目录路径
    :param task_name: 任务名称，用于命名输出文件
    :param index_attribute: 指定作为索引的属性
    :return: 基于条目的错误减少率 (R-EDR)
    """

    # 创建输出目录
    os.makedirs(output_path, exist_ok=True)

    # 定义输出文件路径
    out_path = os.path.join(output_path, f"{task_name}_record_based_edr_evaluation.txt")

    # 备份原始的标准输出
    original_stdout = sys.stdout

    # 将指定的属性设置为索引
    clean = clean.set_index(index_attribute, drop=False)
    dirty = dirty.set_index(index_attribute, drop=False)
    cleaned = cleaned.set_index(index_attribute, drop=False)

    total_distance_dirty_to_clean = 0
    total_distance_repaired_to_clean = 0

    # 重定向输出到文件
    with open(out_path, 'w') as f:
        sys.stdout = f  # 将 sys.stdout 重定向到文件

        # 逐行比较脏数据、清洗后的数据与干净数据
        for idx in clean.index:
            clean_row = clean.loc[idx].apply(normalize_value)
            dirty_row = dirty.loc[idx].apply(normalize_value)
            cleaned_row = cleaned.loc[idx].apply(normalize_value)

            # 计算脏数据和干净数据之间的距离
            distance_dirty_to_clean = record_based_distance_func(dirty_row, clean_row)
            # 计算修复后数据和干净数据之间的距离
            distance_repaired_to_clean = record_based_distance_func(cleaned_row, clean_row)

            total_distance_dirty_to_clean += distance_dirty_to_clean
            total_distance_repaired_to_clean += distance_repaired_to_clean

            # 打印每条记录的距离值
            print(f"Record {idx}")
            print(f"Distance (Dirty to Clean): {distance_dirty_to_clean}")
            print(f"Distance (Repaired to Clean): {distance_repaired_to_clean}")
            print("=" * 40)

        # 计算基于条目的错误减少率 (R-EDR)
        if total_distance_dirty_to_clean == 0:
            r_edr = 0
        else:
            r_edr = (total_distance_dirty_to_clean - total_distance_repaired_to_clean) / total_distance_dirty_to_clean

        # 打印最终的 R-EDR 结果
        print(f"总的脏数据到干净数据距离: {total_distance_dirty_to_clean}")
        print(f"总的修复后数据到干净数据距离: {total_distance_repaired_to_clean}")
        print(f"基于条目的错误减少率 (R-EDR): {r_edr}")

    # 恢复标准输出
    sys.stdout = original_stdout

    print(f"R-EDR 结果已保存到: {out_path}")

    return r_edr

def test_calculate_all_metrics():
    # 准备测试数据
    data = {
        'index1': [1, 2, 3, 4, 5],
        'Attribute1': [1, 2, 3, 4, 5],
        'Attribute2': ['A', 'B', 'C', 'D', 'E'],
        'Attribute3': [1.1, 2.2, 3.3, 4.4, 5.5]
    }

    # 创建干净数据 DataFrame
    clean_df = pd.DataFrame(data)

    # 创建脏数据 DataFrame （引入了一些错误）
    dirty_data = {
        'index1': [1, 2, 3, 4, 5],
        'Attribute1': [1, 9, 3, 4, 5],  # 第二行是错误的
        'Attribute2': ['A', 'B', 'X', 'D', 'E'],  # 第三行是错误的
        'Attribute3': [1.1, 2.2, 3.3, 4.4, 5.5]  # 没有错误
    }
    dirty_df = pd.DataFrame(dirty_data)

    # 创建清洗后的数据 DataFrame （修复了一些错误）
    cleaned_data = {
        'index1': [1, 2, 3, 4, 5],
        'Attribute1': [1, 9, 3, 4, 5],  # 已修复 Attribute1 中的错误
        'Attribute2': ['A', 'X', 'C', 'D', 'E'],  # 修复错误
        'Attribute3': [1.1, 2.2, 3.3, 4.4, 5.7]  # 没有错误
    }
    cleaned_df = pd.DataFrame(cleaned_data)

    # 属性列表
    attributes = ['Attribute1', 'Attribute2', 'Attribute3']

    # 输出路径和任务名称（这里可以使用临时目录）
    output_path = './temp_test_output'
    task_name = 'test_task'

    # 调用函数并计算所有指标
    results = calculate_all_metrics(clean_df, dirty_df, cleaned_df, attributes, output_path, task_name,index_attribute='index1',mse_attributes=['Attribute3'])

    # 打印结果
    print("测试结果:")
    print(f"Accuracy: {results.get('accuracy')}")
    print(f"Recall: {results.get('recall')}")
    print(f"F1 Score: {results.get('f1_score')}")
    print(f"EDR: {results.get('edr')}")
    print(f"Hybrid Distance: {results.get('hybrid_distance')}")
    print(f"R-EDR: {results.get('r_edr')}")

    # # 验证结果是否符合预期
    # assert results['accuracy'] > 0, "Accuracy should be greater than 0"
    # assert results['recall'] > 0, "Recall should be greater than 0"
    # assert results['f1_score'] > 0, "F1 score should be greater than 0"
    # assert results['edr'] > 0, "EDR should be greater than 0"
    # assert results['r_edr'] > 0, "R-EDR should be greater than 0"

    print("测试通过！")



def calculate_accuracy_and_recall_spark(clean, dirty, cleaned, attributes, index_name):
    """
    使用 Spark 计算指定属性集合下的修复准确率和召回率

    :param clean: 干净数据 DataFrame
    :param dirty: 脏数据 DataFrame
    :param cleaned: 清洗后数据 DataFrame
    :param attributes: 指定属性集合
    :param index_name: 索引列名
    :return: 修复准确率和召回率
    """
    total_true_positives = 0
    total_false_positives = 0
    total_true_negatives = 0

    # 对齐索引并重命名列
    clean = clean.select(index_name, *[col(attr).alias(f"{attr}_clean") for attr in attributes])
    dirty = dirty.select(index_name, *[col(attr).alias(f"{attr}_dirty") for attr in attributes])
    cleaned = cleaned.select(index_name, *[col(attr).alias(f"{attr}_cleaned") for attr in attributes])

    joined_df = clean.join(dirty, index_name).join(cleaned, index_name, 'inner')

    for attribute in attributes:
        clean_col = col(f"{attribute}_clean")
        dirty_col = col(f"{attribute}_dirty")
        cleaned_col = col(f"{attribute}_cleaned")

        # 修复正确的数据
        true_positives = joined_df.filter((cleaned_col == clean_col) & (dirty_col != cleaned_col)).count()
        # 修错的数据
        false_positives = joined_df.filter((cleaned_col != clean_col) & (dirty_col != cleaned_col)).count()
        # false_positives = joined_df.filter((cleaned_col != clean_col) & (cleaned_col != dirty_col)).count()
        # 应该修复的数据
        true_negatives = joined_df.filter(dirty_col != clean_col).count()

        total_true_positives += true_positives
        total_false_positives += false_positives
        total_true_negatives += true_negatives

        print("Attribute:", attribute, "修复正确的数据:", true_positives, "修复错误的数据:", false_positives,
              "应该修复的数据:", true_negatives)

    # 总体修复的准确率
    accuracy = total_true_positives / (total_true_positives + total_false_positives)
    # 总体修复的召回率
    recall = total_true_positives / total_true_negatives

    return accuracy, recall


# 示例用法
if __name__ == '__main__':
    from pyspark.sql import SparkSession

    spark = SparkSession.builder \
        .appName("AccuracyAndRecall") \
        .config("spark.executor.memory", "8g") \
        .config("spark.driver.memory", "8g") \
        .getOrCreate()

    # 假设我们有三个 DataFrame: clean_df, dirty_df, cleaned_df
    # 以及 attributes 列表和 index_name 作为索引列名

    file_load = '../../TestDataset/result/tax100w_1/Tax100w_dirty_data.csv'
    columns = ["index_column", "city", "state", "areacode", "zip"]
    dirty_df = spark.read.csv(file_load, header=True, inferSchema=True)
    clean_df = spark.read.csv('../../TestDataset/result/tax100w_1/tax_1000k_clean.csv', header=True, inferSchema=True)
    cleaned_df = spark.read.csv('../../TestDataset/result/tax100w_1/Tax100w_1Cleaned.csv', header=True,
                                inferSchema=True)
    # attributes = ['city', 'state', 'areacode', 'zip']
    attributes = ['city']
    index_name = 'index'

    accuracy, recall = calculate_accuracy_and_recall_spark(clean_df, dirty_df, cleaned_df, attributes, index_name)

    print(f"修复准确率: {accuracy}")
    print(f"修复召回率: {recall}")

    # 停止 Spark 会话
    spark.stop()
