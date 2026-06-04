#!/usr/bin/env python3
import csv
import os
import sys

def screen_sites(city_name, min_ac, density_val, den_mode, max_ac=9999.0, min_units=0, assemblage_only="False"):
    workspace_root = os.getcwd()
    city_data_dir = os.path.join(workspace_root, "projects", "CRERAG", city_name, "data")
    input_file = os.path.join(city_data_dir, f"{city_name}_HEI_Normalized.csv")
    output_file = os.path.join(city_data_dir, f"{city_name}_Target_Sites.csv")
    pipeline_file = os.path.join(city_data_dir, f"{city_name}_Appendix_G_Normalized.csv")

    if not os.path.exists(input_file):
        print(f"Error: Normalized data for {city_name} not found.")
        sys.exit(1)

    # Risk Filter logic
    pipeline_ids = set()
    if os.path.exists(pipeline_file):
        with open(pipeline_file, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                pid = row.get('parcel_id', '').strip()
                if pid: pipeline_ids.add(pid)
    
    qualifying_sites = []
    
    try:
        with open(input_file, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # 1. Risk Filter
                pid = row.get('parcel_id', '').strip()
                if pid in pipeline_ids: continue

                # 2. Acreage Logic
                try:
                    ac = float(row.get('total_acreage', 0))
                except: ac = 0.0
                if not (min_ac <= ac <= max_ac): continue
                
                # 3. Yield / Unit Logic
                try:
                    units = int(row.get('unit_capacity', 0))
                except: units = 0
                if units < min_units: continue
                
                # 4. Density Logic
                try:
                    max_d = float(row.get('max_density', 0))
                except: max_d = 0.0
                if max_d == 0 and ac > 0: max_d = units / ac
                
                if den_mode == "min":
                    if max_d < density_val: continue
                else:
                    if max_d > density_val: continue
                
                # 5. Assemblage Logic
                is_assemblage = "," in pid or ";" in pid or "Site" in row.get('site_id', '')
                if assemblage_only == "True" and not is_assemblage: continue
                
                row['screen_density'] = round(max_d, 2)
                qualifying_sites.append(row)

        if qualifying_sites:
            with open(output_file, mode='w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=qualifying_sites[0].keys())
                writer.writeheader()
                writer.writerows(qualifying_sites)
        
        print(f"\n[!] SCREENER COMPLETE: {len(qualifying_sites)} Sites Qualified.")

    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    # Handle extended arguments from interface
    args = sys.argv
    screen_sites(args[1], float(args[2]), int(args[3]), args[4], float(args[5]), int(args[6]), args[7])
