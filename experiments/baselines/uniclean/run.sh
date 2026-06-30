#!/bin/bash

# chmod +x run.sh
# ./run.sh

# Define datasets_and_rules, their specific mse_attributes, and pre-calculated elapsed times.
# tax/soccer disabled by default (200k rows, ~3.5h each) -- uncomment to enable.
datasets_and_rules=("1_hospital" "2_flights" "3_beers" "4_rayyan")
mse_attributes=("Score" "" "abv ibu" "")
elapsed_times=("108.115330875" "84.591757375" "31.24922154099" "52.377824583")
# datasets_and_rules+=("5_tax" "6_soccer")
# mse_attributes+=("rate" "")
# elapsed_times+=("12589.6389" "11000.0")

# Define base paths (datasets live under datasets_and_rules/original_datasets/<X>/{dirty,clean}.csv)
dirty_base_path="./datasets_and_rules/original_datasets"
clean_base_path="./datasets_and_rules/original_datasets"
cleaned_base_path="./Uniclean_cleaned_data/original_error_cleaned_data"
output_base_path="./Uniclean_results/original_error_results"

# Loop through each dataset and execute the main Python script
for i in "${!datasets_and_rules[@]}"; do
    dataset="${datasets_and_rules[$i]}"
    mse_attr="${mse_attributes[$i]}"
    elapsed_time="${elapsed_times[$i]}"

    echo "Processing dataset: $dataset"

    # Define paths for the current dataset
    # Use the *_index.csv variants which include the 'index' column required by evaluate_result.py
    dirty_path="${dirty_base_path}/${dataset}/dirty_index.csv"
    clean_path="${clean_base_path}/${dataset}/clean_index.csv"
    cleaned_path="${cleaned_base_path}/${dataset}_cleaned_by_uniclean.csv"
    output_path="${output_base_path}/${dataset}"
    log_path="${output_path}/output.log"
    # Create the output directory if it doesn't exist
    mkdir -p "$output_path"

    # Define task-specific settings
    task_name="${dataset}"

    # Construct command with mse_attributes and elapsed_time if they exist
    if [ -n "$mse_attr" ]; then
        python3 evaluate_result.py \
            --dirty_path "$dirty_path" \
            --clean_path "$clean_path" \
            --cleaned_path "$cleaned_path" \
            --output_path "$output_base_path" \
            --task_name "$task_name" \
            --index_attribute "index" \
            --mse_attributes $mse_attr \
            --elapsed_time "$elapsed_time" > "${log_path}"
    else
        python3 evaluate_result.py \
            --dirty_path "$dirty_path" \
            --clean_path "$clean_path" \
            --cleaned_path "$cleaned_path" \
            --output_path "$output_base_path" \
            --task_name "$task_name" \
            --index_attribute "index" \
            --elapsed_time "$elapsed_time" > "${log_path}"
    fi

    # Check if the command was successful
    if [ $? -ne 0 ]; then
        echo "Processing failed for dataset: $dataset"
        exit 1
    fi

    echo "Completed processing for dataset: $dataset"
    echo "--------------------------------------------------"
done

echo "All datasets processed."