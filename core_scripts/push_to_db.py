import csv
import os
import sys

# Target columns as per projects/CRERAG/core_scripts/investor_interface.py
TARGET_COLUMNS = [
    'Address',
    'APN',
    'Total Acreage',
    'Zoning Code',
    'Allowable Density',
    'Maximum Unit Potential'
]

def push_to_db_no_pandas(city_name):
    workspace = os.getcwd()
    input_path = os.path.join(workspace, "projects", "CRERAG", city_name, "data", f"{city_name}_HEI_Normalized.csv")
    output_db_mock = os.path.join(workspace, "projects", "CRERAG", city_name, "data", f"{city_name}_ParcelIQ_DB_Mock.csv")

    if not os.path.exists(input_path):
        print(f"Error: Normalized file not found for {city_name} at {input_path}")
        return

    print(f"[*] Ingesting normalized data for {city_name} via native csv module...")
    
    with open(input_path, mode='r', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        
        db_rows = []
        for row in reader:
            # Map headers to target columns
            addr = row.get('site_address') or row.get('ADDRESS') or 'Unassigned'
            apn = row.get('parcel_id') or row.get('APN') or 'N/A'
            
            try:
                acreage = float(row.get('total_acreage') or 0)
            except ValueError:
                acreage = 0.0
            
            zoning = row.get('zoning_code') or row.get('gp_designation') or 'N/A'
            
            try:
                max_d = float(row.get('max_density') or 0)
                min_d = float(row.get('min_density') or 0)
            except ValueError:
                max_d = 0.0
                min_d = 0.0
                
            allowable_d = f"{int(min_d)} - {int(max_d)} DU/ac"
            max_potential = int(acreage * max_d)
            
            db_rows.append({
                'Address': addr,
                'APN': apn,
                'Total Acreage': round(acreage, 2),
                'Zoning Code': zoning,
                'Allowable Density': allowable_d,
                'Maximum Unit Potential': max_potential
            })

    with open(output_db_mock, mode='w', encoding='utf-8', newline='') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=TARGET_COLUMNS)
        writer.writeheader()
        writer.writerows(db_rows)
        
    print(f"[+] Success: {len(db_rows)} records pushed to {output_db_mock}")
    print("\n--- DB Preview ---")
    for r in db_rows[:5]:
        print(r)

if __name__ == "__main__":
    city = sys.argv[1] if len(sys.argv) > 1 else "Alameda"
    push_to_db_no_pandas(city)
