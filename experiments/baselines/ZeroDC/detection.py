import pandas as pd
import time
from sentence_transformers import SentenceTransformer, export_optimized_onnx_model
from sklearn.cluster import KMeans
import numpy as np
from sklearn.metrics import mutual_info_score
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain_openai import ChatOpenAI
import re
import ast
import traceback
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from sklearn.cluster import DBSCAN
from langchain_core.embeddings import Embeddings
from typing import List
import os
import onnxruntime as ort

os.environ['LOKY_MAX_CPU_COUNT'] = '4' 

# =============================================================================
# 全局变量 (用于收集反馈日志)
# =============================================================================
feedback_logs = {}  # 结构: {col_name: [{iter: 1, samples: [...]}, ...]}
# Columns whose initial LLM rules could not be parsed. The job continues;
# update_rules may still recover a rule set from feedback.
skipped_initial_rules = {}  # col_name -> error string

# Number of feedback rounds per column. Each round labels 1 suspected-dirty + 1 suspected-clean cell,
# i.e. 2*ROUNDS labelled cells per column (upstream default: 5 -> 10 cells/column). Set via --rounds.
ROUNDS = 5

# =============================================================================
# 模块 1: 采样与聚类辅助函数
# =============================================================================

def random_sample(dirty_table, tuple_num):
    return dirty_table.sample(n=tuple_num).index.tolist()

def cluster_by_tuple_sample(embeddings_matrix, cluster_num):
    embeddings_matrix_tuple = embeddings_matrix.reshape(len(embeddings_matrix), -1)
    kmeans = KMeans(n_clusters=cluster_num, random_state=0).fit(embeddings_matrix_tuple)
    centroids = kmeans.cluster_centers_ 
    labels = kmeans.labels_
    
    outlier_scores = []
    for i in range(len(embeddings_matrix)):
        cluster_id = labels[i]
        distance = np.linalg.norm(embeddings_matrix_tuple[i] - centroids[cluster_id])
        outlier_scores.append((i, cluster_id, distance))
    
    most_outlier_indices = []
    center_indices = [] 
    
    for cluster_id in range(len(centroids)):
        cluster_samples = [(idx, dist) for idx, cid, dist in outlier_scores if cid == cluster_id]
        if cluster_samples:
            most_outlier = max(cluster_samples, key=lambda x: x[1])
            most_outlier_indices.append(most_outlier[0])
            center_sample = min(cluster_samples, key=lambda x: x[1])
            center_indices.append(center_sample[0])
    
    return most_outlier_indices, center_indices

def cluster_by_cell_sample_kmeans(embeddings_matrix, col_idx):
    col_embeddings = embeddings_matrix[:, col_idx, :]
    embeddings_matrix_cell = col_embeddings.reshape(len(col_embeddings), -1)
    if len(embeddings_matrix_cell) == 0:
        return [], []

    distinct_embedding_count = len(np.unique(embeddings_matrix_cell, axis=0))
    optimal_k = min(10, len(embeddings_matrix_cell), distinct_embedding_count)
    kmeans = KMeans(n_clusters=optimal_k, random_state=0).fit(embeddings_matrix_cell)
    centroids = kmeans.cluster_centers_ 
    labels = kmeans.labels_
    
    most_outlier_indices = []
    center_indices = []
    outlier_scores = []
    
    for i in range(len(embeddings_matrix_cell)):
        cluster_id = labels[i]
        distance = np.linalg.norm(embeddings_matrix_cell[i] - centroids[cluster_id])
        outlier_scores.append((i, cluster_id, distance))
        
    for cluster_id in range(len(centroids)):
        cluster_samples = [(idx, dist) for idx, cid, dist in outlier_scores if cid == cluster_id]
        if cluster_samples:
            most_outlier = max(cluster_samples, key=lambda x: x[1])
            most_outlier_indices.append(most_outlier[0])
            center_sample = min(cluster_samples, key=lambda x: x[1])
            center_indices.append(center_sample[0])
            
    return most_outlier_indices, center_indices

# =============================================================================
# 模块 2: LLM 初始化与 Prompt 加载
# =============================================================================

def load_prompts(*file_paths: str) -> tuple:
    return tuple(open(path, 'r', encoding='utf-8').read() for path in file_paths)

def initialize_llm(
    model_name,
    openai_api_base,
    openai_api_key,
    temperature,
    request_timeout=60,
):
    return ChatOpenAI(
        model_name=model_name,
        openai_api_base=openai_api_base,
        openai_api_key=openai_api_key,
        temperature=temperature,
        request_timeout=request_timeout,
        # The rule-generation loops already retry and also validate the response.
        max_retries=0,
    )


def _normalize_generated_code(code_string: str) -> str:
    code_string = re.sub(r'^```python\s*', '', code_string.strip())
    code_string = re.sub(r'^```\s*', '', code_string)
    code_string = re.sub(r'\s*```$', '', code_string)

    # Some responses escape the JSON newlines twice, leaving literal ``\n``
    # sequences after deserialization. They cannot be parsed as Python code.
    return code_string.replace('\\r\\n', '\n').replace('\\n', '\n')


def _validate_rule_dict(result: dict) -> dict:
    if not isinstance(result, dict):
        raise ValueError(f"Expected a JSON object, got {type(result).__name__}")

    normalized_rules = {}
    for rule_number, (key, code_string) in enumerate(result.items(), start=1):
        expected_key = f"fun{rule_number}"
        if key != expected_key:
            raise ValueError(f"Expected rule key '{expected_key}', got '{key}'")
        if not isinstance(code_string, str):
            raise ValueError(f"Rule '{key}' must contain Python source code")

        code_string = _normalize_generated_code(code_string)
        try:
            tree = ast.parse(code_string)
        except SyntaxError as exc:
            raise ValueError(f"Rule '{key}' has invalid Python syntax: {exc}") from exc

        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
        if len(functions) != 1 or functions[0].name != key:
            raise ValueError(f"Rule '{key}' must define exactly one function named '{key}'")

        function_args = functions[0].args
        positional_args = function_args.posonlyargs + function_args.args
        if (
            len(positional_args) != 1
            or positional_args[0].arg != 'df'
            or function_args.vararg is not None
            or function_args.kwarg is not None
        ):
            raise ValueError(f"Rule '{key}' must accept exactly one argument named 'df'")
        if any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(tree)):
            raise ValueError(f"Rule '{key}' must not contain imports")

        normalized_rules[key] = code_string

    return normalized_rules


def parse_rule_response(raw_result: str) -> dict:
    if not raw_result or not raw_result.strip():
        raise ValueError("Empty response from LLM")

    candidates = re.findall(
        r'```(?:json)?\s*([\s\S]*?)\s*```', raw_result, flags=re.IGNORECASE
    )
    stripped_result = raw_result.strip()
    candidates.append(stripped_result)

    first_brace = stripped_result.find('{')
    last_brace = stripped_result.rfind('}')
    if first_brace >= 0 and last_brace > first_brace:
        candidates.append(stripped_result[first_brace:last_brace + 1])

    last_error = None
    seen_candidates = set()
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate or candidate in seen_candidates:
            continue
        seen_candidates.add(candidate)

        for parser in (json.loads, ast.literal_eval):
            try:
                return _validate_rule_dict(parser(candidate))
            except (ValueError, SyntaxError) as exc:
                last_error = exc

    raise ValueError(f"Could not parse valid rules: {last_error}")

# =============================================================================
# 模块 3: 统计特征计算 (互信息)
# =============================================================================

def calc_mi_2(df, target_column):
    def calculate_mi_optimized(column, target_column, df):
        if column == target_column:
            return mutual_info_score(df[target_column], df[column])
        else:
            count = df.groupby([target_column, column])[target_column].transform('size')
            filtered_df = df[count >= 2]
            if filtered_df.empty:
                return 0
            A = filtered_df[target_column].reset_index(drop=True)
            B = filtered_df[column].reset_index(drop=True)
            return mutual_info_score(A, B)

    # Columns are already processed concurrently by the outer executor. Starting a
    # process pool here causes severe oversubscription and can fail on Windows when
    # joblib creates its worker pipes.
    mutual_info_list = [
        calculate_mi_optimized(col, target_column, df) for col in df.columns
    ]
    max_mutual_info = max(mutual_info_list) if mutual_info_list else 0
    normalized_mi = [mi / max_mutual_info if max_mutual_info != 0 else 0 for mi in mutual_info_list]
    return normalized_mi

# =============================================================================
# 模块 4: 动态代码执行引擎
# =============================================================================

def find_defined_function_name(code_string):
    try:
        tree = ast.parse(code_string)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                return node.name
        return None
    except SyntaxError:
        return None

def run_dynamic_checker(code_string: str, df: pd.DataFrame, rule_name: str = None):
    default_result = pd.Series([False] * len(df), index=df.index)
    rule_label = f" '{rule_name}'" if rule_name else ""

    code_string = _normalize_generated_code(code_string)
    
    def fix_quotes(match):
        content = match.group(1)
        if "'" in content and '"' not in content:
            return 'r"' + content + '"'
        return match.group(0)
    
    try:
        code_string = re.sub(r"r'([^']*)'", fix_quotes, code_string)
    except:
        pass 
        
    code_string = code_string.replace(r"r'[^a-zA-Z '\'']'", r"r\"[^a-zA-Z '']\"")
    code_string = code_string.replace(r"r'[^a-zA-Z \'\']'", r"r\"[^a-zA-Z '']\"")

    function_name = find_defined_function_name(code_string)
    if not function_name:
        print(f"Skipping rule{rule_label}: no valid function definition found")
        return default_result

    execution_namespace = {'pd': pd, 'np': np, 're': re}

    try:
        exec(code_string, execution_namespace, execution_namespace)
        if function_name not in execution_namespace or not callable(execution_namespace[function_name]):
             print(f"Skipping rule{rule_label}: function '{function_name}' is not callable")
             return default_result
        checker_function = execution_namespace[function_name]
        results = checker_function(df)
        if not isinstance(results, pd.Series):
            try:
                results = pd.Series(results, index=df.index)
            except Exception as exc:
                print(f"Skipping rule{rule_label}: result cannot be converted to a Series: {exc}")
                return default_result
        if len(results) != len(df):
             print(
                 f"Skipping rule{rule_label}: returned {len(results)} rows, expected {len(df)}"
             )
             return default_result
        if not all(isinstance(x, bool) for x in results):
            try:
                results = results.astype(bool)
            except:
                return default_result
        return results
    except SyntaxError as exc:
        print(f"Skipping rule{rule_label}: syntax error in '{function_name}': {exc}")
        return default_result
    except Exception as e:
        print(f"Skipping rule{rule_label}: execution failed: {e}")
        return default_result


def calculate_detection_metrics(prediction, ground_truth):
    prediction_bool = np.asarray(prediction, dtype=bool)
    ground_truth_bool = np.asarray(ground_truth, dtype=bool)
    if prediction_bool.shape != ground_truth_bool.shape:
        raise ValueError(
            f"Prediction shape {prediction_bool.shape} does not match "
            f"ground-truth shape {ground_truth_bool.shape}"
        )

    tp = int(np.count_nonzero(prediction_bool & ground_truth_bool))
    fp = int(np.count_nonzero(prediction_bool & ~ground_truth_bool))
    tn = int(np.count_nonzero(~prediction_bool & ~ground_truth_bool))
    fn = int(np.count_nonzero(~prediction_bool & ground_truth_bool))

    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    f1_score = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0
    )
    return {
        "TP": tp,
        "FP": fp,
        "TN": tn,
        "FN": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1_score,
    }


def evaluate_rule_set(current_rules: dict, dirty_table: pd.DataFrame, col_name: str):
    rule_keys = [f"fun{i + 1}" for i in range(len(current_rules))]
    single_rule_results = []
    total_rule_result = np.zeros(len(dirty_table), dtype=bool)

    for key in rule_keys:
        if key not in current_rules:
            continue
        result = run_dynamic_checker(
            current_rules[key], dirty_table, f"{col_name}.{key}"
        ).to_numpy(dtype=bool)
        single_rule_results.append(result)
        total_rule_result |= result

    if single_rule_results:
        single_rule_array = np.array(single_rule_results, dtype=bool)
    else:
        single_rule_array = np.empty((0, len(dirty_table)), dtype=bool)

    return {
        "single_rule": single_rule_array,
        "total_rule": total_rule_result,
    }

# =============================================================================
# 模块 5: 主动学习采样策略
# =============================================================================

def select_diverse_indices(candidate_indices, checked_indices, dirty_table: pd.DataFrame, embeddings_matrix: np.ndarray, col_idx: int, col_name: str, sample_num: int):
    if len(candidate_indices) == 0 or sample_num <= 0:
        return []

    checked_values = {dirty_table.iloc[idx, col_idx] for idx in checked_indices}
    available_indices = [
        int(idx) for idx in candidate_indices
        if int(idx) not in checked_indices and dirty_table.iloc[int(idx), col_idx] not in checked_values
    ]
    if not available_indices:
        available_indices = [int(idx) for idx in candidate_indices if int(idx) not in checked_indices]
    if not available_indices:
        return []

    selected = []
    candidate_embeddings = embeddings_matrix[available_indices, col_idx, :]
    selected_reference_indices = [idx for idx in checked_indices if 0 <= idx < len(dirty_table)]

    for _ in range(min(sample_num, len(available_indices))):
        if selected_reference_indices or selected:
            reference_indices = selected_reference_indices + selected
            reference_embeddings = embeddings_matrix[reference_indices, col_idx, :]
            distances = np.linalg.norm(candidate_embeddings[:, None, :] - reference_embeddings[None, :, :], axis=2)
            scores = distances.min(axis=1)
        else:
            centroid = candidate_embeddings.mean(axis=0)
            scores = np.linalg.norm(candidate_embeddings - centroid, axis=1)

        best_pos = int(np.argmax(scores))
        selected.append(available_indices.pop(best_pos))
        candidate_embeddings = np.delete(candidate_embeddings, best_pos, axis=0)
        if len(available_indices) == 0:
            break

    return selected


def select_suspicious_clean_indices(candidate_indices, checked_indices, dirty_table: pd.DataFrame, embeddings_matrix: np.ndarray, col_idx: int, sample_num: int):
    if len(candidate_indices) == 0 or sample_num <= 0:
        return []

    checked_values = {dirty_table.iloc[idx, col_idx] for idx in checked_indices}
    available_indices = [
        int(idx) for idx in candidate_indices
        if int(idx) not in checked_indices and dirty_table.iloc[int(idx), col_idx] not in checked_values
    ]
    if not available_indices:
        available_indices = [int(idx) for idx in candidate_indices if int(idx) not in checked_indices]
    if not available_indices:
        return []

    all_values = dirty_table.iloc[:, col_idx].astype(str).str.lower()
    char_counts = {}
    for value in all_values:
        for char in set(value):
            if char.isalnum():
                char_counts[char] = char_counts.get(char, 0) + 1

    candidate_embeddings = embeddings_matrix[available_indices, col_idx, :]
    selected_reference_indices = [idx for idx in checked_indices if 0 <= idx < len(dirty_table)]
    selected = []

    for _ in range(min(sample_num, len(available_indices))):
        if selected_reference_indices or selected:
            reference_indices = selected_reference_indices + selected
            reference_embeddings = embeddings_matrix[reference_indices, col_idx, :]
            distances = np.linalg.norm(candidate_embeddings[:, None, :] - reference_embeddings[None, :, :], axis=2)
            diversity_scores = distances.min(axis=1)
        else:
            centroid = candidate_embeddings.mean(axis=0)
            diversity_scores = np.linalg.norm(candidate_embeddings - centroid, axis=1)

        artifact_scores = []
        for idx in available_indices:
            value = str(dirty_table.iloc[idx, col_idx]).lower()
            chars = [char for char in set(value) if char.isalnum()]
            if chars:
                rarity = max(1 / char_counts.get(char, 1) for char in chars)
            else:
                rarity = 0
            bonus = 0
            if 'x' in value:
                bonus += 0.5
            if re.search(r'[a-z]x[a-z]', value):
                bonus += 0.5
            if re.search(r'\d+x|x\d', value):
                bonus += 0.5
            if 'xx' in value:
                bonus += 0.5
            artifact_scores.append(rarity + bonus)

        artifact_scores = np.array(artifact_scores)
        if artifact_scores.max() > 0:
            artifact_scores = artifact_scores / artifact_scores.max()
        if diversity_scores.max() > 0:
            diversity_scores = diversity_scores / diversity_scores.max()

        scores = diversity_scores + artifact_scores
        best_pos = int(np.argmax(scores))
        selected.append(available_indices.pop(best_pos))
        candidate_embeddings = np.delete(candidate_embeddings, best_pos, axis=0)
        if len(available_indices) == 0:
            break

    return selected


def dirty_check_sample(detection_result, user_check_num: int, dirty_table: pd.DataFrame, embeddings_matrix: np.ndarray, col_idx: int, col_name: str):
    latest_result = detection_result[col_name][-1]["total_rule"]
    dirty_indices = np.where(latest_result)[0]
    checked_indices = dirty_check_idx_list[col_name]

    if len(dirty_indices) == 0:
        candidate_indices = np.arange(len(dirty_table))
    else:
        candidate_indices = dirty_indices

    dirty_check_idx = select_diverse_indices(
        candidate_indices,
        checked_indices,
        dirty_table,
        embeddings_matrix,
        col_idx,
        col_name,
        user_check_num,
    )

    dirty_check_idx_list[col_name].extend(dirty_check_idx)
    return dirty_check_idx

def clean_check_sample(detection_result, user_check_num: int, dirty_table: pd.DataFrame, embeddings_matrix: np.ndarray, col_idx: int, col_name: str):
    latest_result = detection_result[col_name][-1]["total_rule"]
    clean_indices = np.where(~latest_result)[0]
    checked_indices = clean_check_idx_list[col_name]

    if len(clean_indices) == 0:
        candidate_indices = np.arange(len(dirty_table))
    else:
        candidate_indices = clean_indices

    if len(clean_check_idx_list[col_name]) % 5 == 4:
        clean_check_idx = select_suspicious_clean_indices(
            candidate_indices,
            checked_indices,
            dirty_table,
            embeddings_matrix,
            col_idx,
            1,
        )
    else:
        clean_check_idx = select_diverse_indices(
            candidate_indices,
            checked_indices,
            dirty_table,
            embeddings_matrix,
            col_idx,
            col_name,
            user_check_num,
        )

    clean_check_idx_list[col_name].extend(clean_check_idx)
    return clean_check_idx

# =============================================================================
# 模块 6: 规则生成与更新核心逻辑 (LLM 交互)
# =============================================================================

def get_initial_rules(dirty_table: pd.DataFrame, embeddings_matrix: np.ndarray, col_idx: int, col_name: str):
    outlier_indices, center_indices = cluster_by_cell_sample_kmeans(embeddings_matrix, col_idx)
    mi_list = calc_mi_2(dirty_table, col_name)
    normMI = np.round(mi_list, decimals=1)
    threshold = 0.5
    relevant_column_indices = np.where(normMI >= threshold)[0]
    
    sub_table_outlier = dirty_table.iloc[outlier_indices, relevant_column_indices]
    sub_table_center = dirty_table.iloc[center_indices, relevant_column_indices]
    json_str_outlier = sub_table_outlier.to_json(orient='records')
    json_str_center = sub_table_center.to_json(orient='records')
    
    prompt_rule_generation = ChatPromptTemplate(messages=[
            SystemMessagePromptTemplate.from_template(sys_rule_generation),
            HumanMessagePromptTemplate.from_template(human_rule_generation),
        ]
    )
    chain = prompt_rule_generation | llm_rule_generation
    
    max_retries = 3
    retry_count = 0
    result = None
    last_error = None
    
    while result is None and retry_count < max_retries:
        raw_result = ""
        try:
            raw_result = chain.invoke(
                {
                    "target_column": col_name,
                    "dirty_table": json_str_outlier,
                    "clean_table": json_str_center,
                }
            ).content
            result = parse_rule_response(raw_result)
        except Exception as exc:
            last_error = exc
            retry_count += 1
            preview = " ".join(str(raw_result).split())[:300]
            print(
                f"Failed to generate rules for '{col_name}' "
                f"({retry_count}/{max_retries}): {exc}"
            )
            if preview:
                print(f"  LLM preview: {preview}")
    
    if result is None:
        print(
            f"Skipping column '{col_name}': no valid initial rules after "
            f"{max_retries} attempts ({last_error}). "
            "Other columns continue; update_rules may still recover this one."
        )
        detection_func[col_name] = {}
        skipped_initial_rules[col_name] = str(last_error)
        return

    detection_func[col_name] = result


def update_rules(detection_result: dict, dirty_table: pd.DataFrame, embeddings_matrix: np.ndarray, col_idx: int, col_name: str):
    if col_name not in detection_result:
        detection_result[col_name] = []
    
    # 初始化该列的日志
    feedback_logs[col_name] = []

    for iter_num in range(ROUNDS): 
        try:
            current_rules = detection_func.get(col_name, {})
            rule_keys = [f'fun{i+1}' for i in range(len(current_rules))]
            detection_result_iteration = evaluate_rule_set(
                current_rules, dirty_table, col_name
            )
            single_rules_results = list(detection_result_iteration["single_rule"])
            detection_result[col_name].append(detection_result_iteration)
            
            user_check_num_dirty = 1
            user_check_num_clean = 1
            
            dirty_check_idx = dirty_check_sample(detection_result, user_check_num_dirty, dirty_table, embeddings_matrix, col_idx, col_name)
            clean_check_idx = clean_check_sample(detection_result, user_check_num_clean, dirty_table, embeddings_matrix, col_idx, col_name)
            
            valid_dirty_idx = [i for i in dirty_check_idx if i < len(clean_table)]
            valid_clean_idx = [i for i in clean_check_idx if i < len(clean_table)]
            
            dirty_check_ground_truth = clean_table.iloc[valid_dirty_idx, col_idx].astype(str)
            clean_check_ground_truth = clean_table.iloc[valid_clean_idx, col_idx].astype(str)
            
            prompt_rule_update = ChatPromptTemplate(messages=[
                SystemMessagePromptTemplate.from_template(sys_rule_update),
                HumanMessagePromptTemplate.from_template(human_rule_update),
            ])
            chain = prompt_rule_update | llm_rule_update
            
            initial_functions_json = json.dumps(current_rules, ensure_ascii=False)
            human_feedback = []
            
            # 用于收集当前迭代的采样记录
            current_iter_samples = []

            # --- 处理 Dirty 样本反馈 ---
            for list_idx, row_idx in enumerate(valid_dirty_idx):
                is_marked_dirty = detection_result[col_name][-1]["total_rule"][row_idx]
                initial_classification = "dirty" if is_marked_dirty else "clean"
                
                original_value = str(dirty_table.iloc[row_idx, col_idx]) 
                corrected_value = str(dirty_check_ground_truth.iloc[list_idx])
                
                # [已移除] 打印日志
                # print(f"[Col: {col_name} | Iter: {iter_num+1} | Dirty Sample] Original: '{original_value}' -> Corrected: '{corrected_value}'")
                
                # 收集日志
                current_iter_samples.append({
                    "type": "dirty_sample",
                    "row_idx": int(row_idx),
                    "original_value": original_value,
                    "corrected_value": corrected_value
                })

                flagging_function_key = []
                if original_value == corrected_value:
                    if len(single_rules_results) > 0:
                        for rule_idx, rule_result in enumerate(single_rules_results):
                            if rule_result[row_idx]:
                                flagging_function_key.append(rule_keys[rule_idx])

                actual_classification = "dirty" if original_value != corrected_value else "clean"
                
                human_feedback.append({
                    "original_value": original_value,
                    "corrected_value": corrected_value,
                    "initial_classification": initial_classification,
                    "actual_classification": actual_classification,
                    "flagging_function_key": flagging_function_key,
                    "row_context": {}
                })
                
            # --- 处理 Clean 样本反馈 ---
            for list_idx, row_idx in enumerate(valid_clean_idx):
                is_marked_dirty = detection_result[col_name][-1]["total_rule"][row_idx]
                initial_classification = "dirty" if is_marked_dirty else "clean"
                sample_kind = "suspicious_clean_sample" if len(clean_check_idx_list[col_name]) % 5 == 0 else "clean_sample"

                original_value = str(dirty_table.iloc[row_idx, col_idx])
                corrected_value = str(clean_check_ground_truth.iloc[list_idx])    
                
                # [已移除] 打印日志
                # print(f"[Col: {col_name} | Iter: {iter_num+1} | Clean Sample] Original: '{original_value}' -> Corrected: '{corrected_value}'")

                # 收集日志
                current_iter_samples.append({
                    "type": sample_kind,
                    "row_idx": int(row_idx),
                    "original_value": original_value,
                    "corrected_value": corrected_value
                })

                actual_classification = "dirty" if original_value != corrected_value else "clean"
                
                human_feedback.append({
                    "original_value": original_value,
                    "corrected_value": corrected_value,
                    "initial_classification": initial_classification,
                    "actual_classification": actual_classification,
                    "flagging_function_key": [],
                    "row_context": {}
                })
            
            # 将本轮采样记录存入全局字典
            feedback_logs[col_name].append({
                "iteration": iter_num + 1,
                "samples": current_iter_samples
            })

            human_feedback_json = json.dumps(human_feedback, ensure_ascii=False)
            
            max_retries = 3
            retry_count = 0
            json_parse_success = False
            new_rules_dict = {}
            
            while not json_parse_success and retry_count < max_retries:
                try:
                    response = chain.invoke({
                        "target_column": col_name, 
                        "existing_functions": initial_functions_json,
                        "human_feedback": human_feedback_json
                    })
                    raw_result = response.content
                    
                    new_rules_dict = parse_rule_response(raw_result)
                    json_parse_success = True
                        
                except Exception as e:
                    print(f"Error during LLM invocation/parsing for {col_name} (Attempt {retry_count+1}/{max_retries}): {e}")
                    retry_count += 1
            
            if json_parse_success:
                detection_func[col_name] = new_rules_dict
            else:
                print(f"Warning: Failed to update rules for column '{col_name}' in iteration {iter_num+1}. Keeping previous rules.")
                
        except Exception as e:
            print(f"Critical error in update_rules loop for column '{col_name}', iteration {iter_num}: {e}")
            print(traceback.format_exc())
            continue

    # The last feedback round produces one final rule set. Evaluate it so the
    # saved rules and final detection CSV describe the same model state.
    final_rules = detection_func.get(col_name, {})
    detection_result[col_name].append(
        evaluate_rule_set(final_rules, dirty_table, col_name)
    )


def embed_data(dirty_data, embeddingModel):
    elements_list = dirty_data.values.flatten().tolist()
    embeddings = embeddingModel.embed_documents(elements_list)
    embedding_dimension = len(embeddings[0])
    embeddings_matrix = embeddings.reshape(row_count, column_count, embedding_dimension)
    return embeddings_matrix, embedding_dimension

# =============================================================================
# 模块 7: 主程序入口
# =============================================================================

if __name__ == "__main__":
    s_time = time.time()
    
    # CLI (all optional; defaults reproduce the original upstream behaviour on datasets/tax).
    # Added for the harness wrapper (experiments/harness/run_zerodc_detection.py).
    import argparse
    _ap = argparse.ArgumentParser()
    _ap.add_argument('--dataset', default='tax')
    _ap.add_argument('--dirty_path', default=None)
    _ap.add_argument('--clean_path', default=None)
    _ap.add_argument('--detection_path', default=None, help='0/1 ground-truth error mask (for metrics)')
    _ap.add_argument('--out_dir', default=None, help='where rules/detection/feedback files are written')
    _ap.add_argument('--model', default=os.getenv('ZERODC_MODEL', 'gpt-4.1'))
    _ap.add_argument('--api_base', default=os.getenv('ZERODC_API_BASE', 'https://api.kksj.org/v1'))
    _ap.add_argument('--api_key_env', default='ZERODC_API_KEY',
                     help='name of the env var holding the API key (key is never hard-coded)')
    _ap.add_argument('--max_workers', type=int, default=8)
    _ap.add_argument('--empty_token', default=None,
                     help="with --keep_empty: replace cells that are exactly '' by this token (ZeroDC's prompts expect 'null')")
    _ap.add_argument('--keep_empty', action='store_true',
                     help="keep empty cells as '' instead of replacing them with the string 'null'")
    _ap.add_argument('--rounds', type=int, default=5,
                     help='feedback rounds per column; each labels 1 dirty + 1 clean cell (2*rounds cells/column)')
    _ap.add_argument('--embed_backend', choices=['onnx', 'torch'], default=os.getenv('ZERODC_EMBED_BACKEND', 'onnx'))
    _args = _ap.parse_args()

    dataset_name = _args.dataset
    ROUNDS = _args.rounds
    dirty_table_path = _args.dirty_path or f"datasets/{dataset_name}/{dataset_name}_dirty.csv"
    clean_table_path = _args.clean_path or f"datasets/{dataset_name}/{dataset_name}_clean.csv"
    detection_result_path = _args.detection_path or f"datasets/{dataset_name}/{dataset_name}_dirty_error_detection.csv"
    out_dir = _args.out_dir or f"datasets/{dataset_name}"
    os.makedirs(out_dir, exist_ok=True)
    _api_key = os.getenv(_args.api_key_env)
    if not _api_key:
        raise SystemExit(f"No API key: set ${_args.api_key_env}")
    
    if _args.keep_empty:
        # Harness mode: cells are read verbatim (empty cell stays '', literal 'NA'/'null' stay as-is),
        # exactly like the other systems' input.
        dirty_table = pd.read_csv(dirty_table_path, encoding='utf-8', dtype=str, keep_default_na=False)
        clean_table = pd.read_csv(clean_table_path, encoding='utf-8', dtype=str, keep_default_na=False)
        if _args.empty_token is not None:
            # Only cells that are exactly '' are replaced (other NA-like strings such as 'NA' stay untouched).
            dirty_table = dirty_table.replace('', _args.empty_token)
            clean_table = clean_table.replace('', _args.empty_token)
    else:
        # Upstream behaviour: empty cells become the string 'null'.
        dirty_table = pd.read_csv(dirty_table_path, encoding='utf-8', dtype=str)
        dirty_table.fillna('null', inplace=True)
        clean_table = pd.read_csv(clean_table_path, encoding='utf-8', dtype=str)
        clean_table.fillna('null', inplace=True)
    detection = pd.read_csv(detection_result_path)
    
    row_count = dirty_table.shape[0]
    column_count = dirty_table.shape[1]
    
    system_message_rule_generation_path = 'prompt_templates/prompt_rule_generation_system.txt'
    human_message_rule_generation_path = 'prompt_templates/prompt_rule_generation_human.txt'
    sys_rule_generation, human_rule_generation = load_prompts(system_message_rule_generation_path, human_message_rule_generation_path)
    
    system_message_rule_update_path = 'prompt_templates/prompt_rule_update_system.txt'
    human_message_rule_update_path = 'prompt_templates/prompt_rule_update_human.txt'
    sys_rule_update, human_rule_update = load_prompts(system_message_rule_update_path, human_message_rule_update_path)
    
    MODEL_NAME_RuleGeneration = _args.model
    OPENAI_API_BASE_RuleGeneration = _args.api_base
    OPENAI_API_KEY_RuleGeneration = _api_key
    TEMPERATURE_RuleGeneration = 0
    llm_rule_generation = initialize_llm(MODEL_NAME_RuleGeneration, OPENAI_API_BASE_RuleGeneration, OPENAI_API_KEY_RuleGeneration, TEMPERATURE_RuleGeneration)
    
    MODEL_NAME_RuleUpdate = _args.model
    OPENAI_API_BASE_RuleUpdate = _args.api_base
    OPENAI_API_KEY_RuleUpdate = _api_key
    TEMPERATURE_RuleUpdate = 0
    llm_rule_update = initialize_llm(MODEL_NAME_RuleUpdate, OPENAI_API_BASE_RuleUpdate, OPENAI_API_KEY_RuleUpdate, TEMPERATURE_RuleUpdate)

    EMBEDDING_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "all-MiniLM-L6-v2")
    available_providers = ort.get_available_providers()
    onnx_provider = (
        "CUDAExecutionProvider"
        if "CUDAExecutionProvider" in available_providers
        else "CPUExecutionProvider"
    )
    print(f"ONNX execution provider: {onnx_provider}")
    if _args.embed_backend == 'torch':
        # CPU-friendly fallback: the bundled model_O4.onnx is an fp16/GPU-optimised graph.
        embedding_model = SentenceTransformer(EMBEDDING_MODEL_PATH, device='cpu')
    else:
        embedding_model = SentenceTransformer(
            EMBEDDING_MODEL_PATH,
            backend="onnx",
            model_kwargs={
                "file_name": "onnx/model_O4.onnx",
                "provider": onnx_provider,
            },
        )
    
    print('embedding...')
    emb_start_time = time.time()
    embeddings = embedding_model.encode(dirty_table.values.flatten().tolist(), normalize_embeddings=True, batch_size=64, show_progress_bar=True, convert_to_numpy=True)
    embedding_dimension = len(embeddings[0])
    embeddings_matrix = embeddings.reshape(row_count, column_count, embedding_dimension)
    emb_end_time = time.time()
    print('embedding done')
    print(f"embedding time cost {emb_end_time-emb_start_time}")
    
    cluster_num = 10
    detection_func = {}
    skipped_initial_rules.clear()
    max_workers = min(_args.max_workers, column_count)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for col_idx, col_name in enumerate(dirty_table.columns):
            future = executor.submit(get_initial_rules, dirty_table, embeddings_matrix, col_idx, col_name)
            futures.append(future)
        for future in as_completed(futures):
            future.result()

    if skipped_initial_rules:
        skip_path = os.path.join(out_dir, "skipped_columns.json")
        print(f"Initial rules skipped for {list(skipped_initial_rules)} -> {skip_path}")
        with open(skip_path, "w", encoding="utf-8") as f:
            json.dump(skipped_initial_rules, f, indent=2, ensure_ascii=False)

    initial_rules_path = os.path.join(out_dir, "initial_rules.json")
    print(f"所有列初始规则生成完毕，正在保存至: {initial_rules_path}")
    
    try:
        with open(initial_rules_path, 'w', encoding='utf-8') as f:
            json.dump(detection_func, f, indent=4, ensure_ascii=False)
        print("初始规则保存成功。")
    except Exception as e:
        print(f"保存初始规则时出错: {e}")
    
    detection_result = {}
    dirty_check_idx_list = {}
    clean_check_idx_list = {}
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for col_idx, col_name in enumerate(dirty_table.columns):
            dirty_check_idx_list[col_name] = []
            clean_check_idx_list[col_name] = []
            detection_result[col_name] = []
            future = executor.submit(update_rules, detection_result, dirty_table, embeddings_matrix, col_idx, col_name)
            futures.append(future)
        for future in as_completed(futures):
            future.result()
            
    final_detection = pd.DataFrame(index=range(row_count), columns=dirty_table.columns)
    
    for col_name in dirty_table.columns:
        if col_name in detection_result:
            last_iteration_result = detection_result[col_name][-1]["total_rule"]
            final_detection[col_name] = last_iteration_result.astype(int)
        else:
            final_detection[col_name] = 0
            
    overall_metrics = calculate_detection_metrics(final_detection, detection)
    precision = overall_metrics["precision"]
    recall = overall_metrics["recall"]
    F1_score = overall_metrics["f1"]
    
    print('总体 precision:', precision, 'recall:', recall, 'F1-score:', F1_score)
    
    # [修改] 保存最终规则结果 (美化格式)
    with open(os.path.join(out_dir, f'{dataset_name}_rules.json'), 'w', encoding='utf-8') as f:
        json.dump(detection_func, f, indent=4, ensure_ascii=False)
        
    final_detection.to_csv(os.path.join(out_dir, f'{dataset_name}_final_detection.csv'), index=False)

    # 保存反馈日志到 JSON
    feedback_log_path = os.path.join(out_dir, f"{dataset_name}_feedback_log.json")
    try:
        with open(feedback_log_path, 'w', encoding='utf-8') as f:
            json.dump(feedback_logs, f, indent=4, ensure_ascii=False)
        print(f"反馈日志已保存至: {feedback_log_path}")
    except Exception as e:
        print(f"保存反馈日志时出错: {e}")
    
    print("\n每列的评估指标:")
    for col_name in dirty_table.columns:
        column_metrics = calculate_detection_metrics(
            final_detection[col_name], detection[col_name]
        )
        col_precision = column_metrics["precision"]
        col_recall = column_metrics["recall"]
        col_F1 = column_metrics["f1"]
            
        print(f"列 '{col_name}': precision: {col_precision:.4f}, recall: {col_recall:.4f}, F1-score: {col_F1:.4f}")
        
    e_time = time.time()
    print(f"total time cost: {e_time-s_time}")
