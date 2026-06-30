#!/usr/bin/env python3
"""
Address Validation Pipeline

Simple script to validate addresses from the dataset.

Usage:
    python main.py --csv path/to/file.csv --limit 10
    python main.py --csv ../datasets/clean-full-named.csv --limit 100
    python main.py --csv ../datasets/clean-full-named.csv  # validates all
"""

import csv
import json
import argparse
import sys
import os
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import requests


# ============================================================================
# Configuration
# ============================================================================

# Get API key from environment variable
API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')
if not API_KEY:
    print("❌ Error: GOOGLE_MAPS_API_KEY environment variable not set!")
    print("\nPlease set your API key using:")
    print("  export GOOGLE_MAPS_API_KEY='your-api-key-here'")
    print("\nOr add it to your ~/.bashrc or ~/.bash_profile for persistence:")
    print("  echo 'export GOOGLE_MAPS_API_KEY=\"your-api-key-here\"' >> ~/.bashrc")
    sys.exit(1)

API_URL = "https://addressvalidation.googleapis.com/v1:validateAddress"


# ============================================================================
# Address Validator
# ============================================================================

class AddressValidator:
    """Simple address validator using Google API."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.url = API_URL
        self.headers = {"Content-Type": "application/json"}
    
    def validate(self, address_lines: List[str], region_code: str = None) -> Dict:
        """Validate an address."""
        payload = {"address": {"addressLines": address_lines}}
        if region_code:
            payload["address"]["regionCode"] = region_code.upper()
        
        try:
            response = requests.post(
                self.url,
                headers=self.headers,
                params={"key": self.api_key},
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}


# ============================================================================
# Data Processing
# ============================================================================

def build_address_string(row: Dict) -> str:
    """Build address string from CSV row."""
    parts = []
    if row.get('house_number') and row.get('road'):
        parts.append(f"{row['house_number']} {row['road']}")
    elif row.get('road'):
        parts.append(row['road'])
    
    if row.get('locality'):
        parts.append(row['locality'])
    if row.get('region'):
        parts.append(row['region'])
    if row.get('postcode'):
        parts.append(row['postcode'])
    if row.get('country'):
        parts.append(row['country'])
    
    return ', '.join(parts)


def extract_result(api_response: Dict, original_row: Dict) -> Dict:
    """Extract key information from API response."""
    result = {
        'id': original_row.get('_id', ''),
        'name': original_row.get('name', ''),
        'original_address': build_address_string(original_row),
        'country_code': original_row.get('country_code', '').upper(),
        'status': 'ERROR',
        'formatted_address': '',
        'granularity': '',
        'latitude': '',
        'longitude': '',
        'complete': False,
        'issues': []
    }
    
    if 'error' in api_response:
        result['issues'].append(f"API Error: {api_response['error']}")
        return result
    
    if 'result' not in api_response:
        result['issues'].append("No result from API")
        return result
    
    res = api_response['result']
    
    # Verdict
    if 'verdict' in res:
        verdict = res['verdict']
        granularity = verdict.get('validationGranularity', '')
        result['granularity'] = granularity
        result['complete'] = verdict.get('addressComplete', False)
        
        # Determine status
        if granularity in ['PREMISE', 'SUB_PREMISE']:
            result['status'] = 'VALID'
        elif granularity in ['ROUTE', 'LOCALITY']:
            result['status'] = 'REVIEW'
        else:
            result['status'] = 'INVALID'
        
        # Track issues
        if verdict.get('hasUnconfirmedComponents'):
            result['issues'].append('unconfirmed')
        if verdict.get('hasReplacedComponents'):
            result['issues'].append('replaced')
        if verdict.get('hasSpellCorrectedComponents'):
            result['issues'].append('spell_corrected')
    
    # Formatted address
    if 'address' in res:
        result['formatted_address'] = res['address'].get('formattedAddress', '')
    
    # Geocode
    if 'geocode' in res and 'location' in res['geocode']:
        loc = res['geocode']['location']
        result['latitude'] = loc.get('latitude', '')
        result['longitude'] = loc.get('longitude', '')
    
    return result


# ============================================================================
# Main Pipeline
# ============================================================================

def validate_addresses(csv_path: str, limit: Optional[int] = None, output_dir: str = "output"):
    """
    Main validation pipeline.
    
    Args:
        csv_path: Path to CSV file with addresses
        limit: Number of addresses to validate (None = all)
        output_dir: Directory for output files
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        print(f"❌ Error: File not found: {csv_path}")
        sys.exit(1)
    
    # Create output directory with timestamp for this run
    base_output = Path(output_dir)
    base_output.mkdir(exist_ok=True)
    
    # Create timestamped run folder
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_folder = base_output / f"run_{timestamp}"
    run_folder.mkdir(exist_ok=True)
    
    # Output file paths
    output_csv = run_folder / "validated.csv"
    output_json = run_folder / "api_responses.json"
    output_summary = run_folder / "summary.txt"
    
    print("\n" + "="*80)
    print("ADDRESS VALIDATION PIPELINE")
    print("="*80)
    print(f"Input file:   {csv_path}")
    print(f"Output folder: {run_folder}")
    print(f"Limit:        {limit if limit else 'All records'}")
    print("="*80 + "\n")
    
    # Read addresses
    print("📖 Reading addresses...")
    addresses = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            if limit and idx >= limit:
                break
            addresses.append(row)
    
    print(f"✓ Loaded {len(addresses)} addresses\n")
    
    # Validate addresses
    validator = AddressValidator(API_KEY)
    results = []
    api_responses = []  # Store full API responses
    stats = {'VALID': 0, 'REVIEW': 0, 'INVALID': 0, 'ERROR': 0}
    
    print("🔍 Validating addresses...\n")
    
    for idx, row in enumerate(addresses, 1):
        name = row.get('name', 'Unknown')[:40]
        print(f"[{idx:3d}/{len(addresses)}] {name:<40}", end=" ", flush=True)
        
        # Build address
        address_str = build_address_string(row)
        country_code = row.get('country_code', '')
        
        # Validate
        api_response = validator.validate(
            address_lines=[address_str],
            region_code=country_code
        )
        
        # Store full API response with metadata
        api_responses.append({
            'record_id': row.get('_id', ''),
            'record_name': row.get('name', ''),
            'input_address': address_str,
            'country_code': country_code,
            'api_response': api_response
        })
        
        # Extract results
        result = extract_result(api_response, row)
        results.append(result)
        stats[result['status']] += 1
        
        # Print status
        status_emoji = {
            'VALID': '✅',
            'REVIEW': '⚠️',
            'INVALID': '❌',
            'ERROR': '🔴'
        }
        print(f"{status_emoji[result['status']]} {result['status']}")
    
    # Save full JSON responses
    print(f"\n💾 Saving full API responses to {output_json}...")
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(api_responses, f, indent=2, ensure_ascii=False)
    
    # Save results to CSV
    print(f"💾 Saving CSV results to {output_csv}...")
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['id', 'name', 'original_address', 'country_code', 'status', 
                     'formatted_address', 'granularity', 'latitude', 'longitude', 
                     'complete', 'issues']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            result['issues'] = '; '.join(result['issues']) if result['issues'] else 'none'
            writer.writerows([result])
    
    # Print summary
    summary_text = f"""
{'='*80}
VALIDATION SUMMARY
{'='*80}

Total Processed:    {len(results)}
✅ Valid:           {stats['VALID']:4d} ({stats['VALID']/len(results)*100:.1f}%)
⚠️  Needs Review:   {stats['REVIEW']:4d} ({stats['REVIEW']/len(results)*100:.1f}%)
❌ Invalid:         {stats['INVALID']:4d} ({stats['INVALID']/len(results)*100:.1f}%)
🔴 Errors:          {stats['ERROR']:4d} ({stats['ERROR']/len(results)*100:.1f}%)

Complete Addresses: {sum(1 for r in results if r['complete'])} ({sum(1 for r in results if r['complete'])/len(results)*100:.1f}%)
With Issues:        {sum(1 for r in results if r['issues'])} ({sum(1 for r in results if r['issues'])/len(results)*100:.1f}%)

Output Files:
  • CSV:      {output_csv}
  • JSON:     {output_json}
  • Summary:  {output_summary}

{'='*80}
"""
    
    print(summary_text)
    
    # Save summary
    with open(output_summary, 'w', encoding='utf-8') as f:
        f.write(summary_text)
        f.write("\n\nDETAILED RESULTS:\n")
        f.write("="*80 + "\n\n")
        
        for result in results:
            f.write(f"[{result['id']}] {result['name']}\n")
            f.write(f"  Status:   {result['status']} ({result['granularity']})\n")
            f.write(f"  Original: {result['original_address']}\n")
            f.write(f"  Valid:    {result['formatted_address']}\n")
            if result['latitude'] and result['longitude']:
                f.write(f"  Location: {result['latitude']}, {result['longitude']}\n")
            if result['issues'] and result['issues'] != 'none':
                f.write(f"  Issues:   {result['issues']}\n")
            f.write("\n")
    
    print(f"\n✅ Validation complete! Results saved to:")
    print(f"   • CSV:     {output_csv}")
    print(f"   • JSON:    {output_json}")
    print(f"   • Summary: {output_summary}\n")


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Validate addresses from CSV file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate first 10 addresses
  python main.py --csv ../datasets/clean-full-named.csv --limit 10
  
  # Validate first 100 addresses
  python main.py --csv ../datasets/clean-full-named.csv --limit 100
  
  # Validate all addresses
  python main.py --csv ../datasets/clean-full-named.csv
  
  # Custom output directory
  python main.py --csv data.csv --limit 50 --output results/
        """
    )
    
    parser.add_argument(
        '--csv',
        type=str,
        required=True,
        help='Path to CSV file containing addresses'
    )
    
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Number of addresses to validate (default: all)'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default='output',
        help='Output directory (default: output/)'
    )
    
    args = parser.parse_args()
    
    validate_addresses(
        csv_path=args.csv,
        limit=args.limit,
        output_dir=args.output
    )


if __name__ == "__main__":
    main()
