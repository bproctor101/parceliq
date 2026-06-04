import csv
import os

def normalize_milpitas(input_path, output_path):
    print(f"[*] Normalizing Milpitas data: {input_path}")
    
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

    # Mapping for Milpitas_Zoning_Mapped.csv
    # APN -> parcel_id
    # Zoning Description -> zoning_code
    # GP Land Use -> gp_designation
    # Area Acres -> total_acreage
    # Min_Density -> min_density
    # Max_Density -> max_density
    # City is fixed to 'Milpitas'
    # site_address is not explicitly in columns, using Feature Name or empty

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
                    raw_max_density = row.get('Max_Density', '')
                    
                    # Filter: Drop records with blank or non-numeric max_density (like 'N/A')
                    try:
                        if not raw_max_density or str(raw_max_density).strip() in ['', 'N/A']:
                            excluded_non_numeric_max += 1
                            continue
                        float(raw_max_density)
                    except ValueError:
                        excluded_non_numeric_max += 1
                        continue

                    # Proper Capitalization: "los angeles" -> "Los Angeles"
                    raw_city = row.get('city', 'Milpitas').title()

                    normalized_row = {
                        'city': raw_city,
                        'site_address': row.get('Feature Name', ''),
                        'parcel_id': row.get('APN', ''),
                        'gp_designation': row.get('GP Land Use', ''),
                        'zoning_code': row.get('Zoning Description', ''),
                        'min_density': row.get('Min_Density', '0'),
                        'max_density': raw_max_density,
                        'total_acreage': row.get('Area Acres', '0')
                    }
                    
                    # Ensure min_density is numeric or 0
                    try:
                        float(normalized_row['min_density'])
                    except ValueError:
                        normalized_row['min_density'] = '0'

                    writer.writerow(normalized_row)
                    count += 1

        print(f"[+] Success: Normalized {count} Milpitas records to {output_path}")
        print(f"[-] Excluded {excluded_non_numeric_max} blank/non-numeric max_density records.")

    except Exception as e:
        print(f"[!] Critical Error: {str(e)}")

if __name__ == "__main__":
    MAPPED_PATH = "projects/CRERAG/data/GIS/Milpitas_Zoning_Mapped.csv"
    NORMALIZED_PATH = "projects/CRERAG/data/GIS/Milpitas_Normalized.csv"
    normalize_milpitas(MAPPED_PATH, NORMALIZED_PATH)
