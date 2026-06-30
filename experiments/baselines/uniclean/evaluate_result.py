from sklearn.metrics import mean_squared_error, jaccard_score
import numpy as np
import os
import sys
import time
import argparse
import pandas as pd

# Helper Functions
def normalize_value(value):
    """Normalize values to string format, removing trailing zeros."""
    try:
        float_value = float(value)
        if float_value.is_integer():
            return str(int(float_value))
        else:
            return str(float_value)
    except ValueError:
        return str(value)

def default_distance_func(value1, value2):
    """Default distance function: 1 if values differ, 0 if identical."""
    return (value1 != value2).sum()

def record_based_distance_func(row1, row2):
    """Distance based on records: returns 1 if any value differs, else 0."""
    for val1, val2 in zip(row1, row2):
        if val1 != val2:
            return 1
    return 0

def calF1(precision, recall):
    """Calculate F1 score."""
    return 2 * precision * recall / (precision + recall + 1e-10)

# Metrics Calculation Functions
def calculate_accuracy_and_recall(clean, dirty, cleaned, attributes, output_path, task_name, index_attribute='index'):
    """
    Calculates the repair accuracy and recall for a specified set of attributes and outputs results to a file,
    while generating difference CSV files.

    :param clean: Clean DataFrame
    :param dirty: Dirty DataFrame
    :param cleaned: Cleaned DataFrame
    :param attributes: Set of specified attributes
    :param output_path: Directory path to save the results
    :param task_name: Task name, used for naming the output file
    :param index_attribute: Attribute to set as the index
    :return: Repair accuracy and recall
    """

    os.makedirs(output_path, exist_ok=True)

    # Define output file paths
    out_path = os.path.join(output_path, f"{task_name}_evaluation.txt")

    # Paths for CSV files recording differences
    clean_dirty_diff_path = os.path.join(output_path, f"{task_name}_clean_vs_dirty.csv")
    dirty_cleaned_diff_path = os.path.join(output_path, f"{task_name}_dirty_vs_cleaned.csv")
    clean_cleaned_diff_path = os.path.join(output_path, f"{task_name}_clean_vs_cleaned.csv")

    # Backup original standard output
    original_stdout = sys.stdout

    # Set the specified attribute as the index
    clean = clean.set_index(index_attribute, drop=False)
    dirty = dirty.set_index(index_attribute, drop=False)
    cleaned = cleaned.set_index(index_attribute, drop=False)

    # Redirect output to file
    with open(out_path, 'w', encoding='utf-8') as f:
        sys.stdout = f  # Redirect sys.stdout to file

        total_true_positives = 0
        total_false_positives = 0
        total_true_negatives = 0

        # Create DataFrames to save different data items
        clean_dirty_diff = pd.DataFrame(columns=['Attribute', 'Index', 'Clean Value', 'Dirty Value'])
        dirty_cleaned_diff = pd.DataFrame(columns=['Attribute', 'Index', 'Dirty Value', 'Cleaned Value'])
        clean_cleaned_diff = pd.DataFrame(columns=['Attribute', 'Index', 'Clean Value', 'Cleaned Value'])

        for attribute in attributes:
            # Ensure all attribute data types are strings and normalized
            clean_values = clean[attribute].apply(normalize_value)
            dirty_values = dirty[attribute].apply(normalize_value)
            cleaned_values = cleaned[attribute].apply(normalize_value)

            # Align indices
            common_indices = clean_values.index.intersection(cleaned_values.index).intersection(dirty_values.index)
            clean_values = clean_values.loc[common_indices]
            dirty_values = dirty_values.loc[common_indices]
            cleaned_values = cleaned_values.loc[common_indices]

            # Correctly repaired data
            true_positives = ((cleaned_values == clean_values) & (dirty_values != cleaned_values)).sum()
            # Incorrectly repaired data
            false_positives = ((cleaned_values != clean_values) & (dirty_values != cleaned_values)).sum()
            # All data that should be repaired
            true_negatives = (dirty_values != clean_values).sum()

            # Record differences between clean and dirty data
            mismatched_indices = dirty_values[dirty_values != clean_values].index
            clean_dirty_diff = pd.concat([clean_dirty_diff, pd.DataFrame({
                'Attribute': attribute,
                'Index': mismatched_indices,
                'Clean Value': clean_values.loc[mismatched_indices],
                'Dirty Value': dirty_values.loc[mismatched_indices]
            })])

            # Record differences between dirty and cleaned data
            cleaned_indices = cleaned_values[cleaned_values != dirty_values].index
            dirty_cleaned_diff = pd.concat([dirty_cleaned_diff, pd.DataFrame({
                'Attribute': attribute,
                'Index': cleaned_indices,
                'Dirty Value': dirty_values.loc[cleaned_indices],
                'Cleaned Value': cleaned_values.loc[cleaned_indices]
            })])

            # Record differences between clean and cleaned data
            clean_cleaned_indices = cleaned_values[cleaned_values != clean_values].index
            clean_cleaned_diff = pd.concat([clean_cleaned_diff, pd.DataFrame({
                'Attribute': attribute,
                'Index': clean_cleaned_indices,
                'Clean Value': clean_values.loc[clean_cleaned_indices],
                'Cleaned Value': cleaned_values.loc[clean_cleaned_indices]
            })])

            total_true_positives += true_positives
            total_false_positives += false_positives
            total_true_negatives += true_negatives
            print("Attribute:", attribute, "Correctly repaired data:", true_positives, "Incorrectly repaired data:", false_positives,
                  "Data that should be repaired:", true_negatives)
            print("=" * 40)

        # Overall repair accuracy
        accuracy = total_true_positives / (total_true_positives + total_false_positives)
        # Overall repair recall
        recall = total_true_positives / total_true_negatives

        # Output final accuracy and recall
        print(f"Repair Accuracy: {accuracy}")
        print(f"Repair Recall: {recall}")

    # Restore standard output
    sys.stdout = original_stdout

    # Save differences to CSV files
    clean_dirty_diff.to_csv(clean_dirty_diff_path, index=False)
    dirty_cleaned_diff.to_csv(dirty_cleaned_diff_path, index=False)
    clean_cleaned_diff.to_csv(clean_cleaned_diff_path, index=False)

    print(f"Difference files saved to:\n{clean_dirty_diff_path}\n{dirty_cleaned_diff_path}\n{clean_cleaned_diff_path}")

    return accuracy, recall

def get_edr(clean, dirty, cleaned, attributes, output_path, task_name, index_attribute='index', distance_func=default_distance_func):
    """
    Calculates the Error Drop Rate (EDR) for a specified set of attributes and outputs the results to a file.

    :param clean: Clean DataFrame
    :param dirty: Dirty DataFrame
    :param cleaned: Cleaned DataFrame
    :param attributes: Set of specified attributes
    :param output_path: Directory path to save the results
    :param task_name: Task name, used for naming the output file
    :param index_attribute: Attribute to set as the index
    :param distance_func: Distance calculation function, default compares two values (1 for different, 0 for the same)
    :return: Error Drop Rate (EDR)
    """

    # Create output directory
    os.makedirs(output_path, exist_ok=True)

    # Define output file path
    out_path = os.path.join(output_path, f"{task_name}_edr_evaluation.txt")

    # Backup original standard output
    original_stdout = sys.stdout

    # Set the specified attribute as the index
    clean = clean.set_index(index_attribute, drop=False)
    dirty = dirty.set_index(index_attribute, drop=False)
    cleaned = cleaned.set_index(index_attribute, drop=False)

    # Redirect output to file
    with open(out_path, 'w') as f:
        sys.stdout = f  # Redirect sys.stdout to file

        total_distance_dirty_to_clean = 0
        total_distance_repaired_to_clean = 0

        for attribute in attributes:
            # Ensure all attribute data types are strings and normalized
            clean_values = clean[attribute].apply(normalize_value)
            dirty_values = dirty[attribute].apply(normalize_value)
            cleaned_values = cleaned[attribute].apply(normalize_value)

            # Align indices
            common_indices = clean_values.index.intersection(cleaned_values.index).intersection(dirty_values.index)
            clean_values = clean_values.loc[common_indices]
            dirty_values = dirty_values.loc[common_indices]
            cleaned_values = cleaned_values.loc[common_indices]

            # Calculate distance between dirty and clean data
            distance_dirty_to_clean = distance_func(dirty_values, clean_values)
            # Calculate distance between repaired and clean data
            distance_repaired_to_clean = distance_func(cleaned_values, clean_values)

            total_distance_dirty_to_clean += distance_dirty_to_clean
            total_distance_repaired_to_clean += distance_repaired_to_clean

            # Print distance values for each attribute
            print(f"Attribute: {attribute}")
            print(f"Distance (Dirty to Clean): {distance_dirty_to_clean}")
            print(f"Distance (Repaired to Clean): {distance_repaired_to_clean}")
            print("=" * 40)

        # Calculate Error Drop Rate (EDR)
        if total_distance_dirty_to_clean == 0:
            edr = 0
        else:
            edr = (total_distance_dirty_to_clean - total_distance_repaired_to_clean) / total_distance_dirty_to_clean

        # Print final EDR result
        print(f"Total Distance (Dirty to Clean): {total_distance_dirty_to_clean}")
        print(f"Total Distance (Repaired to Clean): {total_distance_repaired_to_clean}")
        print(f"Error Drop Rate (EDR): {edr}")

    # Restore standard output
    sys.stdout = original_stdout

    print(f"EDR result saved to: {out_path}")

    return edr

def get_hybrid_distance(clean, cleaned, attributes, output_path, task_name, index_attribute='index', mse_attributes=[], w1=0.5, w2=0.5):
    """
    Calculates a hybrid distance metric, including MSE and Jaccard distance, and saves the results to a file.

    :param clean: Clean data DataFrame
    :param cleaned: Cleaned data DataFrame
    :param attributes: List of specified attributes
    :param output_path: Path to save results
    :param task_name: Task name for result files
    :param index_attribute: Attribute to use as index
    :param mse_attributes: Attributes for MSE calculation
    :param w1: Weight for MSE
    :param w2: Weight for Jaccard distance
    :return: Weighted hybrid distance
    """

    # Create output directory if it doesn't exist
    os.makedirs(output_path, exist_ok=True)

    # Define output file path
    out_path = os.path.join(output_path, f"{task_name}_hybrid_distance_evaluation.txt")

    # Backup original stdout
    original_stdout = sys.stdout

    # Set the specified attribute as index
    clean = clean.set_index(index_attribute, drop=False)
    cleaned = cleaned.set_index(index_attribute, drop=False)

    # Redirect output to the file
    with open(out_path, 'w') as f:
        sys.stdout = f  # Redirect sys.stdout to file

        total_mse = 0
        total_jaccard = 0
        attribute_count = 0

        for attribute in attributes:
            # Ensure consistent data types and normalize values
            clean_values = clean[attribute].apply(normalize_value).replace('empty', np.nan).dropna()
            cleaned_values = cleaned[attribute].apply(normalize_value).replace('empty', np.nan).dropna()

            # Only calculate MSE if there are valid numeric values
            if attribute in mse_attributes and not clean_values.empty and not cleaned_values.empty:
                try:
                    mse = mean_squared_error(clean_values.astype(float), cleaned_values.astype(float))
                except ValueError:
                    print(f"Check if attribute {attribute} contains numeric data!")
                    mse = np.nan
            else:
                mse = np.nan

            # Only calculate Jaccard if there are valid categorical values
            if not clean_values.empty and not cleaned_values.empty:
                try:
                    # Filter common indices and calculate Jaccard distance
                    common_indices = clean_values.index.intersection(cleaned_values.index)
                    jaccard = 1 - jaccard_score(
                        clean_values.loc[common_indices],
                        cleaned_values.loc[common_indices],
                        average='macro'
                    )
                except ValueError:
                    print(f"Cannot calculate Jaccard distance, as {attribute} is not categorical.")
                    jaccard = np.nan
            else:
                jaccard = np.nan

            # Accumulate non-NaN values
            if not np.isnan(mse):
                total_mse += mse
            if not np.isnan(jaccard):
                total_jaccard += jaccard

            # Only count attributes if at least one distance is valid
            if not np.isnan(mse) or not np.isnan(jaccard):
                attribute_count += 1

            print(f"Attribute: {attribute}, MSE: {mse}, Jaccard: {jaccard}")

        if attribute_count == 0:
            hybrid_distance = None
        else:
            # Calculate weighted hybrid distance
            avg_mse = total_mse / attribute_count if attribute_count > 0 else 0
            avg_jaccard = total_jaccard / attribute_count if attribute_count > 0 else 0
            hybrid_distance = w1 * avg_mse + w2 * avg_jaccard

            print(f"Weighted Hybrid Distance: {hybrid_distance}")

    # Restore original stdout
    sys.stdout = original_stdout

    print(f"Hybrid distance results saved to: {out_path}")

    return hybrid_distance

def get_record_based_edr(clean, dirty, cleaned, output_path, task_name, index_attribute='index'):
    """
    Calculates the record-based Error Drop Rate (R-EDR) and outputs each record's distance and the final R-EDR to a file.

    :param clean: Clean DataFrame
    :param dirty: Dirty DataFrame
    :param cleaned: Cleaned DataFrame
    :param output_path: Directory path to save the results
    :param task_name: Task name, used for naming the output file
    :param index_attribute: Attribute to set as the index
    :return: Record-based Error Drop Rate (R-EDR)
    """

    # Create output directory
    os.makedirs(output_path, exist_ok=True)

    # Define output file path
    out_path = os.path.join(output_path, f"{task_name}_record_based_edr_evaluation.txt")

    # Backup original standard output
    original_stdout = sys.stdout

    # Set the specified attribute as the index
    clean = clean.set_index(index_attribute, drop=False)
    dirty = dirty.set_index(index_attribute, drop=False)
    cleaned = cleaned.set_index(index_attribute, drop=False)

    total_distance_dirty_to_clean = 0
    total_distance_repaired_to_clean = 0

    # Redirect output to file
    with open(out_path, 'w') as f:
        sys.stdout = f  # Redirect sys.stdout to file

        # Compare each row of dirty, cleaned, and clean data
        for idx in clean.index:
            clean_row = clean.loc[idx].apply(normalize_value)
            dirty_row = dirty.loc[idx].apply(normalize_value)
            cleaned_row = cleaned.loc[idx].apply(normalize_value)

            # Calculate distance between dirty and clean data
            distance_dirty_to_clean = record_based_distance_func(dirty_row, clean_row)
            # Calculate distance between repaired and clean data
            distance_repaired_to_clean = record_based_distance_func(cleaned_row, clean_row)

            total_distance_dirty_to_clean += distance_dirty_to_clean
            total_distance_repaired_to_clean += distance_repaired_to_clean

            # Print distance values for each record
            print(f"Record {idx}")
            print(f"Distance (Dirty to Clean): {distance_dirty_to_clean}")
            print(f"Distance (Repaired to Clean): {distance_repaired_to_clean}")
            print("=" * 40)

        # Calculate record-based Error Drop Rate (R-EDR)
        if total_distance_dirty_to_clean == 0:
            r_edr = 0
        else:
            r_edr = (total_distance_dirty_to_clean - total_distance_repaired_to_clean) / total_distance_dirty_to_clean

        # Print final R-EDR result
        print(f"Total Distance (Dirty to Clean): {total_distance_dirty_to_clean}")
        print(f"Total Distance (Repaired to Clean): {total_distance_repaired_to_clean}")
        print(f"Record-based Error Drop Rate (R-EDR): {r_edr}")

    # Restore standard output
    sys.stdout = original_stdout

    print(f"R-EDR result saved to: {out_path}")

    return r_edr

def calculate_all_metrics(clean, dirty, cleaned, attributes, output_path, task_name, index_attribute='index', calculate_precision_recall=True, calculate_edr=True, calculate_hybrid=True, calculate_r_edr=True, mse_attributes=[]):
    """Unified function to calculate multiple metrics."""
    results = {}

    if calculate_precision_recall:
        accuracy, recall = calculate_accuracy_and_recall(clean, dirty, cleaned, attributes, output_path, task_name, index_attribute)
        results.update({'accuracy': accuracy, 'recall': recall, 'f1_score': calF1(accuracy, recall)})

    if calculate_edr:
        results['edr'] = get_edr(clean, dirty, cleaned, attributes, output_path, task_name, index_attribute)

    if calculate_hybrid:
        results['hybrid_distance'] = get_hybrid_distance(clean, cleaned, attributes, output_path, task_name, index_attribute, mse_attributes)

    if calculate_r_edr:
        results['r_edr'] = get_record_based_edr(clean, dirty, cleaned, output_path, task_name, index_attribute)

    return results

def format_empty_data(csv_file, output_file, missing_value_in_ori_data='empty', missing_value_representation='empty'):
    """Format data with empty values for missing data consistency."""
    df = pd.read_csv(csv_file)
    for col in df.columns:
        if pd.api.types.is_float_dtype(df[col]):
            df[col] = df[col].apply(lambda x: int(x) if pd.notna(x) and x == int(x) else x)
        df[col] = df[col].astype(str)

    df.replace(['', 'nan', 'null', '__NULL__', missing_value_in_ori_data], missing_value_representation, inplace=True)
    df.to_csv(output_file, index=False)

# Main Script
def main():
    parser = argparse.ArgumentParser(description="Calculate data cleaning metrics and save results to log file.")
    parser.add_argument('--dirty_path', type=str, default="./RealWorldDataSet/1_hospital/dirty_index.csv", help="Path to the dirty data CSV file.")
    parser.add_argument('--clean_path', type=str, default="./RealWorldDataSet/1_hospital/clean_index.csv", help="Path to the clean data CSV file.")
    parser.add_argument('--cleaned_path', type=str,default="./Uniclean_cleaned_data/1_hospital_cleaned_by_uniclean.csv", help="Path to the cleaned data CSV file.")
    parser.add_argument('--output_path', type=str, default="./Uniclean_results", help="Directory path to save the results (default: ./results).")
    parser.add_argument('--task_name', type=str, default="1_hospital", help="Task name for result files (default: data_cleaning_task).")
    parser.add_argument('--index_attribute', type=str, default='index', help="Attribute to use as index (default: index).")
    parser.add_argument('--mse_attributes', nargs='*', default=[], help="List of attributes to calculate MSE, if any.")
    parser.add_argument('--elapsed_time', type=float, help="Optional total elapsed time for the task in seconds.")

    args = parser.parse_args()

    start_time = time.time()
    os.makedirs(args.output_path, exist_ok=True)

    if args.elapsed_time is None:
        print("Note: Elapsed time not provided. Calculating time but speed output will not be shown.")

    format_empty_data(args.cleaned_path, args.cleaned_path)

    clean_data = pd.read_csv(args.clean_path)
    dirty_data = pd.read_csv(args.dirty_path)
    cleaned_data = pd.read_csv(args.cleaned_path)
    stra_path = os.path.join(args.output_path, f"{args.task_name}")
    results = calculate_all_metrics(
        clean=clean_data,
        dirty=dirty_data,
        cleaned=cleaned_data,
        attributes=clean_data.columns.tolist(),
        output_path=stra_path,
        task_name=args.task_name,
        index_attribute=args.index_attribute,
        mse_attributes=args.mse_attributes
    )

    elapsed_time = args.elapsed_time
    evaluation_time = time.time() - start_time
    speed = 100 * float(elapsed_time) / clean_data.shape[0] if args.elapsed_time else None

    results_path = os.path.join(stra_path, f"{args.task_name}_total_evaluation.txt")
    with open(results_path, 'w', encoding='utf-8') as f:
        sys.stdout = f
        print(f"{args.task_name} Evaluation Results:")
        for metric, value in results.items():
            print(f"{metric}: {value}")
        print(f"Total Time: {elapsed_time} seconds")
        if speed:
            print(f"Cleaning Speed: {speed} seconds/100 records")
    sys.stdout = sys.__stdout__

    print("Results saved to:", results_path)
    for metric, value in results.items():
        print(f"{metric}: {value}")
    if speed:
        print(f"Cleaning Speed: {speed} seconds/100 records")
    print("===============================================================")
    print(f"evaluation Time: {evaluation_time} seconds")

if __name__ == "__main__":
    main()