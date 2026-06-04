import csv
import os

def merge_normalized_files():
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
    
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
    output_path = os.path.join(PROJECT_DIR, 'data', 'master_gis_normalized.csv')
    cities_dir = os.path.join(PROJECT_DIR, 'data', 'cities')

    # Auto-discover all *_normalized.csv files
    files_to_merge = sorted([
        os.path.join(cities_dir, f)
        for f in os.listdir(cities_dir)
        if f.endswith('_normalized.csv')
    ])
    
    print(f"[*] Merging normalized city files into {output_path}")
    
    count = 0
    with open(output_path, mode='w', encoding='utf-8', newline='') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=target_headers)
        writer.writeheader()
        
        for file_path in files_to_merge:
            if not os.path.exists(file_path):
                print(f"[!] Warning: {file_path} not found, skipping.")
                continue
                
            print(f"[*] Reading {file_path}...")
            with open(file_path, mode='r', encoding='utf-8') as infile:
                reader = csv.DictReader(infile)
                for row in reader:
                    writer.writerow(row)
                    count += 1
                    
    print(f"[+] Successfully merged {count} total records.")

if __name__ == "__main__":
    merge_normalized_files()
