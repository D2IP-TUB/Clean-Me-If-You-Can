import numpy as np
import pandas as pd


def normalize_value(value):
    """
    Normalize a value to string format, removing trailing zeros after the decimal point.

    :param value: The value to normalize
    :return: Normalized string
    """
    try:
        # Attempt to convert the value to a float, then to an integer, and finally to a string
        float_value = float(value)
        if float_value.is_integer():
            return str(int(float_value))  # Remove trailing zeros and decimal point
        else:
            return str(float_value)
    except ValueError:
        # If the value cannot be converted to a float, return it as a string
        return str(value)


def count_inconsistent_entries(dirty_df, clean_df, index_column):
    """
    Count the number of inconsistent entries between dirty and clean data.

    :param dirty_df: Dirty data DataFrame
    :param clean_df: Clean data DataFrame
    :param index_column: The index column used for alignment
    :return: Number of inconsistent entries
    """
    # Align dirty and clean data with the same index
    dirty_df = dirty_df.set_index(index_column).applymap(normalize_value)
    clean_df = clean_df.set_index(index_column).applymap(normalize_value)

    # Initialize a set for inconsistent entry indices
    inconsistent_entry_indices = set()

    # Iterate through all columns to find mismatched cells
    for column in dirty_df.columns:
        # Identify mismatched cells in the current column
        mismatched_indices = dirty_df.index[(dirty_df[column] != clean_df[column])]

        # Add mismatched indices to the set
        inconsistent_entry_indices.update(mismatched_indices)

    # Return the total count of inconsistent entries
    return len(inconsistent_entry_indices)


def generate_change_report(dirty_df, clean_df, index_column, output_file_name):
    """
    Compare changes between dirty and clean data cells and generate a change report CSV file.

    :param dirty_df: Dirty data DataFrame
    :param clean_df: Clean data DataFrame
    :param index_column: The index column used for alignment
    :param output_file_name: The output file name for the change report
    :return: Number of inconsistent cells and generates a change report CSV file
    """
    # Align dirty and clean data with the same index
    dirty_df = dirty_df.set_index(index_column).applymap(normalize_value)
    clean_df = clean_df.set_index(index_column).applymap(normalize_value)

    # Initialize a list to store change information
    changes = []

    # Iterate through all columns to find mismatched cells
    for column in dirty_df.columns:
        # Identify mismatched cells in the current column
        mismatched_indices = dirty_df.index[(dirty_df[column] != clean_df[column])]

        for idx in mismatched_indices:
            changes.append({
                'index': idx,
                'attribute': column,
                'dirty_value': dirty_df.at[idx, column],
                'clean_value': clean_df.at[idx, column]
            })

    # Store the change information in a DataFrame
    change_df = pd.DataFrame(changes)

    # Save the result to a CSV file
    change_df.to_csv(output_file_name, index=False)
    print(f"Change report saved to {output_file_name}")
    # Return the total number of inconsistent cells
    return len(change_df)


def replace_with_empty_if_different(dirty_df, clean_df, index_column):
    """
    Replace inconsistent cells in dirty data with 'empty' if they differ from clean data.

    :param dirty_df: Dirty data DataFrame
    :param clean_df: Clean data DataFrame
    :param index_column: The index column used for alignment
    :return: Processed dirty data DataFrame
    """
    # Align dirty and clean data with the same index
    dirty_df = dirty_df.set_index(index_column).applymap(normalize_value)
    clean_df = clean_df.set_index(index_column).applymap(normalize_value)

    # Iterate through all columns to find mismatched cells
    for column in dirty_df.columns:
        # Identify mismatched cells in the current column
        mismatched_indices = dirty_df.index[(dirty_df[column] != clean_df[column])]

        # Replace inconsistent values in dirty data with 'empty'
        for idx in mismatched_indices:
            dirty_df.at[idx, column] = 'empty'

    # Reset the index to the original index_column
    dirty_df = dirty_df.reset_index()
    # Save the result to a CSV file
    dirty_df.to_csv(r"./dirty_df.csv", index=False)
    return dirty_df


def replace_half_with_clean_value(dirty_df, clean_df, index_column):
    """
    Randomly replace half of the inconsistent cells with clean values, while leaving the other half unchanged.

    :param dirty_df: Dirty data DataFrame
    :param clean_df: Clean data DataFrame
    :param index_column: The index column used for alignment
    :return: Processed dirty data DataFrame
    """
    # Align dirty and clean data with the same index
    dirty_df = dirty_df.set_index(index_column).applymap(normalize_value)
    clean_df = clean_df.set_index(index_column).applymap(normalize_value)

    # Iterate through all columns to find mismatched cells
    for column in dirty_df.columns:
        # Identify mismatched cells in the current column
        mismatched_indices = dirty_df.index[(dirty_df[column] != clean_df[column])]

        # If there are mismatched cells, randomly select half to replace
        if len(mismatched_indices) > 0:
            # Randomly select half of the mismatched indices
            num_to_replace = len(mismatched_indices) // 2
            indices_to_replace = np.random.choice(mismatched_indices, num_to_replace, replace=False)

            # Replace selected inconsistent values with clean values
            for idx in indices_to_replace:
                dirty_df.at[idx, column] = clean_df.at[idx, column]

    # Reset the index to the original index_column
    dirty_df = dirty_df.reset_index()
    # Save the result to a CSV file
    dirty_df.to_csv(r"./dirty_df.csv", index=False)
    return dirty_df


# Example usage (do not modify the above code)
if __name__ == '__main__':
    dirty_df = pd.read_csv('../Data/5_tax/subset_directly_dirty_index_10k.csv')
    clean_df = pd.read_csv('../Data/5_tax/subset_directly_clean_index_10k.csv')

    # Count inconsistent entries
    inconsistent_entries_count = count_inconsistent_entries(dirty_df, clean_df, 'index')
    print(f'There are {inconsistent_entries_count} inconsistent entries between dirty and clean data.')

    # Generate change report
    inconsistent_cells = generate_change_report(dirty_df, clean_df, 'index', "./change.CSV")
    print(f'There are {inconsistent_cells} inconsistent cells between dirty and clean data.')