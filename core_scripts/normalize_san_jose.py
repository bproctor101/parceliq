import csv
import os

def normalize_san_jose(input_path, output_path):
    print(f"[*] Normalizing San Jose data: {input_path}")
    
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

    # Mapping for San_Jose_Zoning_Mapped.csv:
    # APN -> parcel_id
    # ZONING -> zoning_code
    # Acreage -> total_acreage
    # Min_DU_Acre -> min_density
    # Max_DU_Acre -> max_density
    # City -> San Jose

    if not os.path.exists(input_path):
        print(f"[!] Error: Source file not found at {input_path}")
        return

    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        count = 0
        excluded_non_numeric_max = 0
        
        with open(input_path, mode='r', encoding='utf-8-sig') as infile:
            reader = csv.DictReader(infile)
            
            with open(output_path, mode='w', encoding='utf-8', newline='') as outfile:
                writer = csv.DictWriter(outfile, fieldnames=target_headers)
                writer.writeheader()
                
                for row in reader:
                    raw_max_density = row.get('Max_DU_Acre', '')
                    
                    # Filter: Drop records with blank or non-numeric max_density
                    if not raw_max_density or str(raw_max_density).strip() in ['', 'N/A', 'Custom', 'No Max']:
                        excluded_non_numeric_max += 1
                        continue
                    
                    try:
                        float(raw_max_density)
                    except ValueError:
                        excluded_non_numeric_max += 1
                        continue

                    normalized_row = {
                        'city': 'San Jose',
                        'site_address': '', # Not in raw CSV
                        'parcel_id': row.get('APN', ''),
                        'gp_designation': 'N/A', # San Jose Raw lacks GP
                        'zoning_code': row.get('ZONING', ''),
                        'min_density': row.get('Min_DU_Acre', '0'),
                        'max_density': raw_max_density,
                        'total_acreage': row.get('Acreage', '0')
                    }
                    
                    # Ensure min_density is numeric or 0
                    try:
                        float(normalized_row['min_density'])
                    except ValueError:
                        normalized_row['min_density'] = '0'

                    writer.writerow(normalized_row)
                    count += 1

        print(f"[+] Success: Normalized {count} San Jose records to {output_path}")
        print(f"[-] Excluded {excluded_non_numeric_max} blank/non-numeric max_density records.")

    except Exception as e:
        print(f"[!] Critical Error: {str(e)}")

if __name__ == "__main__":
    MAPPED_PATH = "projects/CRERAG/data/cities/San_Jose_Zoning_Mapped.csv"
    NORMALIZED_PATH = "projects/CRERAG/data/cities/San_Jose_normalized.csv"
    normalize_san_jose(MAPPED_PATH, NORMALIZED_PATH)
