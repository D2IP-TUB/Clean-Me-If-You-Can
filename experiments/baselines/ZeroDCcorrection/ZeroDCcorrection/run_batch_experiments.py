#!/usr/bin/env python3
"""
Batch runner for ZeroDCcorrection experiments on DGov_NTR datasets.
This script creates temporary correction scripts for each configuration and runs them.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path
from experiment_utils import extract_metrics_from_output, aggregate_results


def create_config_script(template_path, config, output_script_path):
    """
    Create a configured runner that invokes the correction script with CLI args.
    """
    content = f'''#!/usr/bin/env python3
import runpy
import sys
sys.argv = [
    {template_path!r},
    "--clean_data_path", {config["clean_data_path"]!r},
    "--dirty_data_path", {config["dirty_data_path"]!r},
    "--detection_path", {config["detection_path"]!r},
    "--output_path", {config["output_path"]!r},
    "--human_repair_num", {str(config["human_repair_num"])!r},
]
runpy.run_path({template_path!r}, run_name="__main__")
'''
    with open(output_script_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Created configured script: {output_script_path}")


def run_experiment(config, correction_template_path, zerodccorrection_base_path):
    """
    Run a single ZeroDCcorrection experiment with given configuration.
    """
    dataset_name = config['dataset']
    human_repair_num = config['human_repair_num']
    
    print(f"\n{'='*80}")
    print(f"Running: {dataset_name} with human_repair_num={human_repair_num}")
    print(f"{'='*80}")
    
    # Create a temporary script with this configuration
    temp_script = os.path.join(zerodccorrection_base_path, f'temp_correction_{dataset_name}_{human_repair_num}.py')
    
    try:
        create_config_script(correction_template_path, config, temp_script)
        
        # Run the script
        cmd = [sys.executable, temp_script]
        print(f"Executing: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, 
                                cwd=zerodccorrection_base_path,
                                capture_output=True, 
                                text=True,
                                timeout=7200)  # 2 hour timeout
        
        print(f"Return code: {result.returncode}")
        if result.returncode != 0:
            print(f"STDERR:\n{result.stderr}")
            return False
        
        print("Experiment completed successfully")
        return True
        
    except subprocess.TimeoutExpired:
        print(f"ERROR: Experiment timed out after 2 hours")
        return False
    except Exception as e:
        print(f"ERROR running experiment: {e}")
        return False
    finally:
        # Clean up temporary script
        if os.path.exists(temp_script):
            os.remove(temp_script)


def main():
    """Main execution function."""
    from pathlib import Path
    _REPO = Path(__file__).resolve().parents[3]
    # Configuration (repo-relative)
    ZERODCCORRECTION_BASE_PATH = str(Path(__file__).resolve().parent)
    DATASETS_PATH = str(_REPO / 'datasets' / 'unrelated_tables' / 'Quintet')
    RESULTS_BASE_PATH = str(_REPO / 'results' / 'zerodccorrection' / 'Quintet_batch')
    CORRECTION_TEMPLATE = os.path.join(ZERODCCORRECTION_BASE_PATH, 'correction_zero_shot.py')

    if not os.path.exists(RESULTS_BASE_PATH):
        os.makedirs(RESULTS_BASE_PATH)

    # Experiment configurations
    HUMAN_REPAIR_NUMS = [0]
    
    # Get datasets
    datasets = sorted([d for d in os.listdir(DATASETS_PATH) 
                       if os.path.isdir(os.path.join(DATASETS_PATH, d))])
    
    print(f"Found {len(datasets)} datasets: {datasets}")
    print(f"Human repair nums to test: {HUMAN_REPAIR_NUMS}")
    print(f"Total experiments: {len(datasets) * len(HUMAN_REPAIR_NUMS)}")
    
    # Prepare experiments
    experiments = []
    for dataset_name in datasets:
        for human_repair_num in HUMAN_REPAIR_NUMS:
            dataset_path = os.path.join(DATASETS_PATH, dataset_name)
            output_path = os.path.join(RESULTS_BASE_PATH, dataset_name, f"human_repair_{human_repair_num}")
            
            experiments.append({
                'dataset': dataset_name,
                'human_repair_num': human_repair_num,
                'clean_data_path': os.path.join(dataset_path, 'clean.csv'),
                'dirty_data_path': os.path.join(dataset_path, 'dirty.csv'),
                'detection_path': os.path.join(dataset_path, 'perfect_error_detection.csv'),
                'output_path': output_path
            })
    
    # Run experiments
    print(f"\n{'='*80}")
    print(f"STARTING BATCH EXPERIMENTS")
    print(f"{'='*80}\n")
    
    results = []
    for i, config in enumerate(experiments, 1):
        print(f"\nExperiment {i}/{len(experiments)}")
        
        success = run_experiment(config, CORRECTION_TEMPLATE, ZERODCCORRECTION_BASE_PATH)
        
        if success:
            # Evaluate results
            corrected_path = os.path.join(config['output_path'], 'corrections.csv')
            
            if os.path.exists(corrected_path):
                metrics = extract_metrics_from_output(config['output_path'])
                
                if metrics:
                    result = {
                        'dataset': config['dataset'],
                        'human_repair_num': metrics['human_repair_num'],
                        'tp': metrics['tp'],
                        'fp': metrics['fp'],
                        'fn': metrics['fn'],
                        'total_errors': metrics['total_errors'],
                        'total_corrections': metrics['total_corrections'],
                        'precision': metrics['precision'],
                        'recall': metrics['recall'],
                        'f1': metrics['f1'],
                        'execution_time': metrics['execution_time']
                    }
                    
                    results.append(result)
                
                print(f"\nResults: P={metrics['precision']:.4f}, R={metrics['recall']:.4f}, F1={metrics['f1']:.4f}")
            else:
                print(f"WARNING: Corrections file not found: {corrected_path}")
        else:
            print(f"FAILED: Experiment did not complete successfully")
    
    # Aggregate results
    if results:
        output_csv = os.path.join(RESULTS_BASE_PATH, 'zerodccorrection_dgov_ntr_batch_results.csv')
        aggregate_results(results, output_csv)
    else:
        print("\nNo experiments completed successfully.")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Run batch ZeroDCcorrection experiments')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print experiment plan without running')
    
    args = parser.parse_args()
    
    if args.dry_run:
        print("DRY RUN MODE - No experiments will be executed")    
    main()
