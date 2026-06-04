import csv
import os

# Target columns for the Search Engine output
TARGET_COLUMNS = [
    'Address',
    'APN',
    'Total Acreage',
    'GP Designation',
    'Zoning Code',
    'Allowable Density',
    'Maximum Unit Potential'
]

def sync_master_to_db():
    input_path = 'projects/CRERAG/data/master_gis_normalized.csv'
    output_path = 'projects/CRERAG/data/master_gis_db_mock.csv'

    if not os.path.exists(input_path):
        print(f"Error: {input_path} not found.")
        return

    print(f"[*] Syncing {input_path} to query engine mock DB...")
    
    db_rows = []
    
    # Track column population across the entire dataset
    populated_cols = {col: False for col in TARGET_COLUMNS}
    
    # Core valid values (anything else is considered "empty")
    invalid_placeholders = ['N/A', 'NONE', '', 'UNASSIGNED', 'NAN', '0', '0.0']

    # First pass: check which columns are actually populated
    with open(input_path, mode='r', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        for row in reader:
            # Address Check
            val = row.get('site_address', '').strip()
            if val and val.upper() not in invalid_placeholders:
                populated_cols['Address'] = True
            
            # Zoning Check
            val = row.get('zoning_code', '').strip()
            if val and val.upper() not in invalid_placeholders:
                populated_cols['Zoning Code'] = True
                
            # APN Check
            val = row.get('parcel_id', '').strip()
            if val and val.upper() not in invalid_placeholders:
                populated_cols['APN'] = True

            # GP Check
            val = row.get('gp_designation', '').strip()
            if val and val.upper() not in invalid_placeholders:
                populated_cols['GP Designation'] = True

            # Optimization: If all columns are found to be populated, we can stop
            if all(populated_cols.values()):
                break
    
    # Always keep core quantitative data regardless of content
    populated_cols['Total Acreage'] = True
    populated_cols['Allowable Density'] = True
    populated_cols['Maximum Unit Potential'] = True

    # Final list of columns
    final_columns = [col for col in TARGET_COLUMNS if populated_cols[col]]

    # Second pass: Generate output
    with open(input_path, mode='r', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        for row in reader:
            db_entry = {}
            
            # Map values
            apn = row.get('parcel_id') or 'N/A'
            zoning = row.get('zoning_code') or 'N/A'
            gp = row.get('gp_designation') or 'N/A'
            addr = row.get('site_address') or ''
            
            try:
                acreage = float(row.get('total_acreage') or 0)
                max_d = float(row.get('max_density') or 0)
                min_d = float(row.get('min_density') or 0)
            except ValueError:
                acreage, max_d, min_d = 0.0, 0.0, 0.0
                
            allowable_d = f"{min_d} - {max_d} DU/ac"
            max_potential = int(acreage * max_d)
            
            if populated_cols['APN']: db_entry['APN'] = apn
            if populated_cols['Total Acreage']: db_entry['Total Acreage'] = round(acreage, 2)
            if populated_cols['GP Designation']:
                db_entry['GP Designation'] = gp if gp.upper() not in invalid_placeholders else ''
            if populated_cols['Zoning Code']: db_entry['Zoning Code'] = zoning
            if populated_cols['Allowable Density']: db_entry['Allowable Density'] = allowable_d
            if populated_cols['Maximum Unit Potential']: db_entry['Maximum Unit Potential'] = max_potential
            if populated_cols['Address']:
                db_entry['Address'] = addr if addr.upper() not in invalid_placeholders else ''
                
            db_rows.append(db_entry)

    with open(output_path, mode='w', encoding='utf-8', newline='') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=final_columns)
        writer.writeheader()
        writer.writerows(db_rows)
        
    print(f"[+] Success: {len(db_rows)} records synced to {output_path}")
    print(f"[*] Displayed columns: {final_columns}")

if __name__ == "__main__":
    sync_master_to_db()
