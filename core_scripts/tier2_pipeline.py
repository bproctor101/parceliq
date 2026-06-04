import os
import csv

def run_tier2_pipeline(input_dir, output_file):
    """
    Scans input_dir for files ending in _normalized.csv and merges them.
    Standardizes based on expected headers and saves to output_file.
    """
    print(f"[*] Starting Tier 2 Pipeline...")
    print(f"[*] Scanning directory: {input_dir}")
    
    expected_headers = [
        'city', 
        'site_address', 
        'parcel_id', 
        'gp_designation', 
        'zoning_code', 
        'min_density', 
        'max_density', 
        'total_acreage'
    ]
    
    all_data = []
    found_files = [f for f in os.listdir(input_dir) if f.endswith('_normalized.csv')]
    
    if not found_files:
        print("[!] No files ending in _normalized.csv found.")
        return

    for filename in found_files:
        file_path = os.path.join(input_dir, filename)
        print(f"[*] Processing: {filename}")
        
        try:
            with open(file_path, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                
                # Header check
                if not reader.fieldnames:
                    print(f"[-] Warning: {filename} is empty or unreadable. Skipping.")
                    continue
                
                # Check for expected headers (using your specified names or checking overlap)
                # Note: User mentioned Min_Density_du_ac, but previous script used min_density
                # To be robust, we'll check against our standard schema
                missing = [h for h in expected_headers if h not in reader.fieldnames]
                if missing:
                    print(f"[-] Warning: {filename} is missing expected columns: {missing}")
                
                # Read rows
                file_rows = 0
                for row in reader:
                    # Clean and normalize row
                    norm_row = {h: row.get(h, '') for h in expected_headers}
                    all_data.append(norm_row)
                    file_rows += 1
                
                print(f"[+] Added {file_rows} records from {filename}")
                
        except Exception as e:
            print(f"[!!] Error reading {filename}: {e}. Skipping.")

    if not all_data:
        print("[!] No data collected. Master file not created.")
        return

    try:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, mode='w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=expected_headers)
            writer.writeheader()
            writer.writerows(all_data)
        
        print(f"\n[SUCCESS] Tier 2 Master Database created!")
        print(f"[+] Output: {output_file}")
        print(f"[+] Total Records: {len(all_data)}")
    except Exception as e:
        print(f"[!] Failed to write master file: {e}")

if __name__ == "__main__":
    # Internal paths relative to workspace
    INPUT_DIR = "projects/CRERAG/data/cities"
    OUTPUT_FILE = "projects/CRERAG/data/master_gis_normalized.csv"
    
    run_tier2_pipeline(INPUT_DIR, OUTPUT_FILE)
