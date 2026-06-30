#!/usr/bin/env bash
# 一键运行 Uniclean 清洗流水线 + 自动测评，覆盖 4 个公开数据集（hospital / flights / beers / rayyan）。
#
# 使用：
#   chmod +x uniclean_cleaners/run_clean.sh
#   ./uniclean_cleaners/run_clean.sh                   # 跑全部 4 个数据集
#   ./uniclean_cleaners/run_clean.sh hospital flights  # 只跑指定子集
#   FORCE=1 ./uniclean_cleaners/run_clean.sh           # 已有结果也强制重跑
#   PYTHON=python3.10 ./uniclean_cleaners/run_clean.sh # 指定解释器
#
# 输出位置：
#   - cleaned 文件：Uniclean_cleaned_data/original_error_cleaned_data/<X>_cleaned_by_uniclean.csv
#   - 清洗日志：  Uniclean_cleaner_workflow_logs/original_error_cleaner_workflow_logs/<X>/clean_run.log
#   - 测评结果：  Uniclean_results/original_error_results/<X>/output.log
#
# 数据集说明：
#   tax / soccer 默认不跑（200k 行，每个 ~3+ 小时），如需启用请编辑下方 DATASETS_DEFAULT 数组。

set -euo pipefail

# 切到仓库根（脚本在 uniclean_cleaners/ 下）
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON="${PYTHON:-python3}"
DATASETS_DIR="datasets_and_rules/original_datasets"
CLEANED_DIR="Uniclean_cleaned_data/original_error_cleaned_data"
LOG_DIR="Uniclean_cleaner_workflow_logs/original_error_cleaner_workflow_logs"
RESULT_DIR="Uniclean_results/original_error_results"

DATASETS_DEFAULT=("1_hospital" "2_flights" "3_beers" "4_rayyan")
# 如需跑大数据集（耗时几小时），取消下行注释：
# DATASETS_DEFAULT+=("5_tax" "6_soccer")

# 数据集名 → main 脚本
script_for() {
    case "$1" in
        1_hospital) echo "uniclean_cleaners/main_hospitals.py" ;;
        2_flights)  echo "uniclean_cleaners/main_flights.py" ;;
        3_beers)    echo "uniclean_cleaners/main_beers.py" ;;
        4_rayyan)   echo "uniclean_cleaners/main_rayyan.py" ;;
        5_tax)      echo "uniclean_cleaners/main_tax.py" ;;
        6_soccer)   echo "uniclean_cleaners/main_soccer.py" ;;
        *) return 1 ;;
    esac
}

# 数据集名 → evaluate_result.py 的 mse_attributes 参数
mse_attrs_for() {
    case "$1" in
        1_hospital) echo "Score" ;;
        3_beers)    echo "abv ibu" ;;
        5_tax)      echo "rate" ;;
        *)          echo "" ;;
    esac
}

if [ "$#" -gt 0 ]; then
    DATASETS=("$@")
else
    DATASETS=("${DATASETS_DEFAULT[@]}")
fi

mkdir -p "$CLEANED_DIR" "$LOG_DIR" "$RESULT_DIR"
SUMMARY="$RESULT_DIR/run_summary.log"
: > "$SUMMARY"

ok=0
fail=0
total=0

for ds in "${DATASETS[@]}"; do
    if ! script="$(script_for "$ds")"; then
        echo "[skip] 未知数据集: $ds"
        continue
    fi
    if [ ! -f "$script" ]; then
        echo "[skip] 入口脚本不存在: $script"
        continue
    fi

    dirty_path="$DATASETS_DIR/$ds/dirty_index.csv"
    clean_path="$DATASETS_DIR/$ds/clean_index.csv"
    if [ ! -f "$dirty_path" ] || [ ! -f "$clean_path" ]; then
        echo "[skip] $ds 缺数据：$dirty_path / $clean_path"
        continue
    fi

    total=$((total + 1))
    cleaned_csv="$CLEANED_DIR/${ds}_cleaned_by_uniclean.csv"
    runtime_dir="$CLEANED_DIR/${ds}_runtime"
    log_dir="$LOG_DIR/$ds"
    mkdir -p "$log_dir"
    clean_log="$log_dir/clean_run.log"

    if [ -f "$cleaned_csv" ] && [ -z "${FORCE:-}" ]; then
        echo "[skip] $ds 已有 cleaned（设 FORCE=1 强制重跑）"
        ok=$((ok + 1))
        continue
    fi

    echo "==== 清洗数据集 $ds ===="
    echo "[run ] $script  → $cleaned_csv  log=$clean_log"

    # Stage 1: 清洗（结果先写到 runtime 目录）
    rm -rf "$runtime_dir"
    if ! "$PYTHON" "$script" \
            --file_load "$dirty_path" \
            --clean_path "$clean_path" \
            --save_path "$CLEANED_DIR/" \
            --table_name "${ds}_runtime" \
            > "$clean_log" 2>&1; then
        echo "FAIL $ds  详见 $clean_log" | tee -a "$SUMMARY"
        fail=$((fail + 1))
        continue
    fi

    # 取出 cleaned.csv 重命名到正式位置
    src_csv="$runtime_dir/${ds}_runtimeCleaned.csv"
    if [ ! -f "$src_csv" ]; then
        echo "FAIL $ds  cleaned 未生成: $src_csv" | tee -a "$SUMMARY"
        fail=$((fail + 1))
        continue
    fi
    cp "$src_csv" "$cleaned_csv"

    echo "OK   $ds  cleaned=$cleaned_csv" | tee -a "$SUMMARY"
    ok=$((ok + 1))
done

echo
echo "==== 清洗阶段汇总：$ok / $total 成功，$fail 失败 ===="
echo "明细见: $SUMMARY"

# Stage 2: 自动测评（调根目录 run.sh）
if [ "$ok" -gt 0 ] && [ -f "run.sh" ]; then
    echo
    echo "==== Stage 2: 调用 ./run.sh 自动测评 ===="
    bash run.sh
    echo "测评结果在: $RESULT_DIR/<dataset>/output.log"
fi

[ "$fail" -eq 0 ]
