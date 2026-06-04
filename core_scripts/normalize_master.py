#!/usr/bin/env python3
import csv
import os

# Centralized Restructuring: normalize_master.py
# Migrates raw regional data to the master_hei_normalized.csv schema.

def normalize_master(input_path, output_path):
    print(f"[*] Initializing master normalization: {input_path}")
    
    # Standard schema definition
    target_headers = [
        'city', 
        'site_address', 
        'parcel_id', 
        'gp_designation', 
        'zoning_code', 
        'min_density', 
        'max_density', 
        'total_acreage'
    ]

    # Mapping based on master_hei_raw.csv discovery
    mapping = {
        'Jurisdiction': 'city',
        'Site Address/Intersection': 'site_address',
        'Assessor Parcel Number': 'parcel_id',
        'Current General Plan Designation': 'gp_designation',
        'Current Zoning Designation': 'zoning_code',
        'Minimum Density Allowed (units/acre)': 'min_density',
        'Maximum Density Allowed (units/acre)': 'max_density',
        'Parcel Size (Acres)': 'total_acreage'
    }

    if not os.path.exists(input_path):
        print(f"[!] Error: Source file not found at {input_path}")
        return

    try:
        # Create output directory if needed
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        count = 0
        excluded_count = 0
        excluded_non_numeric_max = 0
        
        # Use utf-8-sig to handle potential Byte Order Mark (BOM) in raw file
        with open(input_path, mode='r', encoding='utf-8-sig') as infile:
            reader = csv.DictReader(infile)
            
            with open(output_path, mode='w', encoding='utf-8', newline='') as outfile:
                writer = csv.DictWriter(outfile, fieldnames=target_headers)
                writer.writeheader()
                
                for row in reader:
                    # Strip any hidden whitespace/BOM artifacts from keys
                    row = {k.strip(): v for k, v in row.items() if k}
                    
                    raw_city = row.get('Jurisdiction', '').strip()
                    raw_max_density = row.get('Maximum Density Allowed (units/acre)', '')

                    # Filter: Drop unincorporated areas or missing city data
                    if not raw_city or 'county' in raw_city.lower():
                        excluded_count += 1
                        continue
                    
                    # Proper Capitalization: "los angeles" -> "Los Angeles"
                    raw_city = raw_city.title()

                    # Filter: Drop records with blank or non-numeric max_density
                    try:
                        if not raw_max_density or raw_max_density.strip() == '':
                            excluded_non_numeric_max += 1
                            continue
                        float(raw_max_density)
                    except ValueError:
                        excluded_non_numeric_max += 1
                        continue

                    normalized_row = {}
                    for raw_key, target_key in mapping.items():
                        val = row.get(raw_key, '')
                        if target_key == 'city':
                            val = raw_city
                        # Default empty min_density to 0
                        if target_key == 'min_density' and (val == '' or val is None):
                            val = '0'
                        normalized_row[target_key] = val
                    
                    writer.writerow(normalized_row)
                    count += 1

        print(f"[+] Success: Normalized {count} records to {output_path}")
        print(f"[-] Excluded {excluded_count} unincorporated (County) records.")
        print(f"[-] Excluded {excluded_non_numeric_max} blank/non-numeric max_density records.")

    except Exception as e:
        print(f"[!] Critical Error: {str(e)}")

if __name__ == "__main__":
    RAW_PATH = "projects/CRERAG/master_hei_raw.csv"
    NORMALIZED_PATH = "projects/CRERAG/data/master_hei_normalized.csv"
    normalize_master(RAW_PATH, NORMALIZED_PATH)
