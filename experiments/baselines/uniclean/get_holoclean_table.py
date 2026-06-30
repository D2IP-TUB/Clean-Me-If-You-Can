
# Adapt to Holoclean’s clean data format and transpose
# Encapsulate the function to directly handle input and output file formats
import csv

def transform_csv_file(input_csv: str, output_csv: str):
    """
    Transforms the input CSV file into the clean data format for Holoclean.
    Each row is transposed into multiple rows with the format: (tid, attribute, correct_val).

    Args:
        input_csv (str): Path to the input CSV file.
        output_csv (str): Path to save the transformed output CSV file.
    """
    with open(input_csv, mode='r', encoding='utf-8') as infile, open(output_csv, mode='w', newline='', encoding='utf-8') as outfile:
        reader = csv.DictReader(infile)
        writer = csv.writer(outfile)

        # Write the header for the output file
        writer.writerow(['tid', 'attribute', 'correct_val'])

        tid = 0
        # Iterate through each row in the CSV
        for row in reader:
            for key, value in row.items():
                writer.writerow([tid, key, value])
            tid += 1

    print(f"Transformation complete. Output saved to {output_csv}")

if __name__ == '__main__':
    # Example test case
    test_input_csv = r'4_rayyan/clean_rayyan.csv'
    test_output_csv = r'4_rayyan/rayyan_clean_holoclean.csv'

    # Execute the function to process the CSV file
    transform_csv_file(test_input_csv, test_output_csv)