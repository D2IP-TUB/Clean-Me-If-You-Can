#!/bin/bash
# 设置可执行权限： chmod +x run.sh
# 运行方式： ./run.sh

# 开启调试模式，打印当前执行的每一条命令
set -x

# 定义错误比例集合
error_ratios=("0.25" "0.5" "0.75" "1" "1.25" "1.5" "1.75" "2")

# 定义数据集配置（数据集名称、脚本路径、噪声目录、清洁数据路径、表名前缀）
datasets=(
    "1_hospitals:main_hospitals.py:TestDataset/1_hospitals/noise_with_correct_primary_key:TestDataset/1_hospitals/clean_index.csv:hospitals"
    "2_flights:main_flights.py:TestDataset/2_flights/noise_with_correct_primary_key:TestDataset/2_flights/clean_index.csv:flights"
    "3_beers:main_beers.py:TestDataset/3_beers/noise_with_correct_primary_key:TestDataset/3_beers/clean_index.csv:beers"
    "4_rayyan:main_rayyan.py:TestDataset/4_rayyan/noise_with_correct_primary_key:TestDataset/4_rayyan/clean_index.csv:rayyan"
#    "6_soccer:main_soccer.py:TestDataset/6_soccer/noise_with_correct_primary_key:TestDataset/6_soccer/clean_index.csv:soccer"
#    "5_tax:main_tax.py:TestDataset/5_tax/tax_50k/noise_with_correct_primary_key:TestDataset/5_tax/tax_50k/tax_50k_clean_id.csv:tax"
#    "5_tax:main_tax.py:TestDataset/5_tax/noise_with_correct_primary_key:TestDataset/5_tax/tax_200k_clean_index.csv:tax"
)

# 定义结果保存目录
result_dir="TestDataset/result/nosample"
mkdir -p "${result_dir}"

# 遍历每个数据集
for dataset_config in "${datasets[@]}"; do
    # 使用分隔符解析配置
    IFS=":" read -r dataset_name script_path noise_dir clean_path table_name_prefix <<< "${dataset_config}"

    # 遍历错误比例
    for ratio in "${error_ratios[@]}"; do
        # 定义错误数据路径
        file_load="${noise_dir}/dirty_mixed_${ratio}/dirty_${table_name_prefix}_mix_${ratio}.csv"
        # 检查错误数据文件是否存在
        if [ ! -f "${file_load}" ]; then
            # 保存到单独日志文件
            echo "Warning: Dirty data file '${file_load}' does not exist. Skipping ratio '${ratio}' for dataset '${dataset_name}'."
            continue
        fi

        # 定义表名
        table_name="${table_name_prefix}_${ratio//./}"

        # 定义日志文件，包含数据集名称和错误比例
        log_file="${result_dir}/${dataset_name}_ratio_${ratio//./}.log"

        # 运行清洗脚本并将输出保存到对应的日志文件中
        python3 "${script_path}" --file_load "${file_load}" --clean_path "${clean_path}" --save_path "${result_dir}" --table_name "${table_name}" > "${log_file}" 2>&1

        # 检查是否成功完成
        if [ $? -ne 0 ]; then
            echo "Error: Cleaning task failed for dataset: ${dataset_name}, error ratio: ${ratio}. See log: ${log_file}" >> "${log_file}"
            exit 1
        fi

        echo "Cleaning task completed for dataset: ${dataset_name}, error ratio: ${ratio}" >> "${log_file}"
    done
done

# 关闭调试模式
set +x