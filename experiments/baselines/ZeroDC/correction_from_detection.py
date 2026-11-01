import argparse
import json
import os
import time

import numpy as np
import pandas as pd
from langchain_core.output_parsers import JsonOutputParser

import correction as base


def load_detection_feedback(feedback_log_path, dirty_data, clean_data, detection):
    with open(feedback_log_path, 'r', encoding='utf-8') as f:
        feedback_log = json.load(f)

    dirty_rows_by_column = {}
    clean_rows = []
    seen_dirty = set()
    seen_clean = set()

    for column, iterations in feedback_log.items():
        if column not in dirty_data.columns:
            continue
        dirty_rows_by_column[column] = []
        col_idx = dirty_data.columns.get_loc(column)
        for iteration in iterations:
            for sample in iteration.get('samples', []):
                row_idx = sample.get('row_idx')
                if not isinstance(row_idx, int) or row_idx < 0 or row_idx >= len(dirty_data):
                    continue

                sample_type = sample.get('type')
                is_dirty_label = str(dirty_data.iat[row_idx, col_idx]) != str(clean_data.iat[row_idx, col_idx])
                if is_dirty_label:
                    key = (column, row_idx)
                    if key in seen_dirty:
                        continue
                    if int(detection.at[row_idx, column]) != 1:
                        detection.at[row_idx, column] = 1
                    dirty_rows_by_column[column].append(row_idx)
                    seen_dirty.add(key)
                elif sample_type in {'dirty_sample', 'clean_sample'}:
                    key = row_idx
                    if key in seen_clean:
                        continue
                    clean_rows.append(row_idx)
                    seen_clean.add(key)

    dirty_rows_by_column = {column: rows for column, rows in dirty_rows_by_column.items() if rows}
    representative_rows = sorted({row for rows in dirty_rows_by_column.values() for row in rows})
    return dirty_rows_by_column, representative_rows, clean_rows, detection


def main():
    parser = argparse.ArgumentParser(description='Run correction using detection.py outputs and feedback samples.')
    parser.add_argument('--dataset', default='beers')
    args = parser.parse_args()

    base.human_repair_num = 0
    base.dataset_name = args.dataset

    base.clean_data_path = f'datasets/{base.dataset_name}/{base.dataset_name}_clean.csv'
    base.dirty_data_path = f'datasets/{base.dataset_name}/{base.dataset_name}_dirty.csv'
    base.detection_path = f'datasets/{base.dataset_name}/{base.dataset_name}_final_detection.csv'
    feedback_log_path = f'datasets/{base.dataset_name}/{base.dataset_name}_feedback_log.json'

    if not os.path.exists(base.detection_path):
        raise FileNotFoundError(f'Detection output not found: {base.detection_path}. Run detection.py first.')
    if not os.path.exists(feedback_log_path):
        raise FileNotFoundError(f'Detection feedback log not found: {feedback_log_path}. Run detection.py first.')

    base.output_path = base.get_folder_name(f'runs_{base.dataset_name}_from_detection')

    base.system_message_EC_path = 'prompt_templates/SystemMessage_EC.txt'
    base.human_message_EC_path = 'prompt_templates/HumanMessage_EC.txt'
    base.general_examples_EC_path = 'prompt_templates/general_examples_EC.txt'
    base.system_message_CoT_path = 'prompt_templates/SystemMessage_CoT_with_error_type.txt'
    base.general_examples_CoT_path = 'prompt_templates/examples_CoT_with_error_type.txt'
    base.human_message_CoT_large_path = 'prompt_templates/HumanMessage_CoT_large.txt'
    base.human_message_CoT_small_path = 'prompt_templates/HumanMessage_CoT_small.txt'
    base.system_message_code_generation_path = 'prompt_templates/SystemMessage_code_generation.txt'
    base.human_message_code_generation_path = 'prompt_templates/HumanMessage_code_generation.txt'
    base.system_message_fd_generation_path = 'prompt_templates/SystemMessage_fd_generation.txt'
    base.human_message_fd_generation_path = 'prompt_templates/HumanMessage_fd_generation.txt'

    base.MODEL_NAME_EC = 'gpt-3.5-turbo-0125'
    base.OPENAI_API_BASE_EC = 'https://api.kksj.org/v1'
    base.OPENAI_API_KEY_EC = 'sk-4JIpw1dUVNdTSewSzBLXGiRHmPVvElQy4BkoKjQN2wQsjK8S'
    base.TEMPERATURE_EC = 0.5
    base.MODEL_NAME_CoT = 'gpt-4o-2024-11-20'
    base.OPENAI_API_BASE_CoT = 'https://api.kksj.org/v1'
    base.OPENAI_API_KEY_CoT = 'sk-4JIpw1dUVNdTSewSzBLXGiRHmPVvElQy4BkoKjQN2wQsjK8S'
    base.TEMPERATURE_CoT = 0
    base.MODEL_NAME_Code = 'gpt-4o-2024-11-20'
    base.OPENAI_API_BASE_Code = 'https://api.kksj.org/v1'
    base.OPENAI_API_KEY_Code = 'sk-4JIpw1dUVNdTSewSzBLXGiRHmPVvElQy4BkoKjQN2wQsjK8S'
    base.TEMPERATURE_Code = 0.5
    base.MODEL_NAME_FD = 'gpt-4o-2024-11-20'
    base.OPENAI_API_BASE_FD = 'https://api.kksj.org/v1'
    base.OPENAI_API_KEY_FD = 'sk-4JIpw1dUVNdTSewSzBLXGiRHmPVvElQy4BkoKjQN2wQsjK8S'
    base.TEMPERATURE_FD = 0.5
    base.EMBEDDING_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'all-MiniLM-L6-v2')

    base.clean_data = pd.read_csv(base.clean_data_path, dtype=str, encoding='utf-8')
    base.clean_data.fillna('null', inplace=True)
    base.dirty_data = pd.read_csv(base.dirty_data_path, dtype=str, encoding='utf-8')
    base.dirty_data.fillna('null', inplace=True)
    base.header = base.dirty_data.columns.tolist()
    base.row_count, base.column_count = base.dirty_data.shape
    base.detection = pd.read_csv(base.detection_path).astype(int)

    base.detection_feedback_samples_by_column, base.representative_tuples_list, base.detected_clean_sample_rows, base.detection = load_detection_feedback(
        feedback_log_path,
        base.dirty_data,
        base.clean_data,
        base.detection,
    )

    print('row_count:', base.row_count)
    print('column_count:', base.column_count)
    print('detected dirty value num:', base.detection.sum().sum())
    print('reused dirty sample rows:', len(base.representative_tuples_list))
    print('reused clean sample rows:', len(base.detected_clean_sample_rows))

    base.general_examples_EC_str = base.load_examples(base.general_examples_EC_path)
    base.general_examples_CoT_str = base.load_examples(base.general_examples_CoT_path)
    base.parser = JsonOutputParser(pydantic_object=base.Output)
    base.sys_EC, base.human_EC = base.load_prompts(base.system_message_EC_path, base.human_message_EC_path)
    base.sys_CoT, base.human_CoT_large, base.human_CoT_small = base.load_prompts(
        base.system_message_CoT_path,
        base.human_message_CoT_large_path,
        base.human_message_CoT_small_path,
    )
    base.sys_code_generation, base.human_code_generation = base.load_prompts(
        base.system_message_code_generation_path,
        base.human_message_code_generation_path,
    )
    base.sys_fd_generation, base.human_fd_generation = base.load_prompts(
        base.system_message_fd_generation_path,
        base.human_message_fd_generation_path,
    )

    base.LLM4EC = base.initialize_llm(base.MODEL_NAME_EC, base.OPENAI_API_BASE_EC, base.OPENAI_API_KEY_EC, base.TEMPERATURE_EC)
    base.LLM4CoT = base.initialize_llm(base.MODEL_NAME_CoT, base.OPENAI_API_BASE_CoT, base.OPENAI_API_KEY_CoT, base.TEMPERATURE_CoT)
    base.LLM4Code = base.initialize_llm(base.MODEL_NAME_Code, base.OPENAI_API_BASE_Code, base.OPENAI_API_KEY_Code, base.TEMPERATURE_Code)
    base.LLM4FD = base.initialize_llm(base.MODEL_NAME_FD, base.OPENAI_API_BASE_FD, base.OPENAI_API_KEY_FD, base.TEMPERATURE_FD)

    base.logs = []
    base.corrections = base.dirty_data.copy()
    start_time = time.time()

    print('embedding...')
    emb_start_time = time.time()
    base.embeddingModel = base.myEmbeddings(base.EMBEDDING_MODEL_PATH)
    base.embeddings_matrix, base.embedding_dimension = base.embed_data(base.dirty_data, base.embeddingModel)
    base.embedding_dimension = base.embeddings_matrix.shape[2]
    print('embedding done')
    print(f'embedding time cost {time.time() - emb_start_time}')

    base.dirty_data_human_repaired = base.dirty_data.copy()
    base.detection_human_repaired = base.detection.copy()
    if base.representative_tuples_list:
        base.dirty_data_human_repaired.iloc[base.representative_tuples_list] = base.clean_data.iloc[base.representative_tuples_list]
        base.detection_human_repaired.iloc[base.representative_tuples_list] = 0
        base.corrections.iloc[base.representative_tuples_list] = base.clean_data.iloc[base.representative_tuples_list]
        base.dirty_data_only_repaired = base.clean_data.iloc[base.representative_tuples_list]
        elements_list_only_repaired = base.dirty_data_only_repaired.values.flatten().tolist()
        base.embeddings_only_repaired = base.embeddingModel.embed_documents(elements_list_only_repaired)
        base.embeddings_matrix_only_repaired = base.embeddings_only_repaired.reshape(
            len(base.representative_tuples_list),
            base.column_count,
            base.embedding_dimension,
        )
    else:
        base.dirty_data_only_repaired = base.clean_data.iloc[[]]
        base.embeddings_matrix_only_repaired = np.empty((0, base.column_count, base.embedding_dimension))

    base.retriever_dict = {}
    base.indices_dict = {}
    base.CoE_dict = {}
    base.retrieved_tuples = {}
    base.repair_table()

    end_time = time.time()
    base.logs = sorted(base.logs, key=lambda x: int(x['Index']))
    base.save_logs(base.logs)
    base.corrections.to_csv(os.path.join(base.output_path, 'corrections.csv'), encoding='utf-8', index=False)
    base.cmp_mark(base.clean_data, base.corrections)
    base.calc_p_r_f(base.clean_data, base.dirty_data_human_repaired, base.corrections)
    execution_time = end_time - start_time
    print(f'execution time: {execution_time} seconds')
    with open(os.path.join(base.output_path, 'output.txt'), 'a', encoding='utf-8') as f_output:
        f_output.write(f'Time consumption: {execution_time}\n')


if __name__ == '__main__':
    main()
