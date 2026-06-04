#!/usr/bin/env python3
import csv
import os
import sys
import re

def extract_max_density_from_str(text):
    if not text:
        return 0.0
    numbers = re.findall(r'\d+', text)
    if not numbers:
        return 0.0
    return float(max(map(int, numbers)))

def generate_summary(city_name):
    """
    Reads the risk-filtered Target_Sites.csv and formats it into a 
    presentation-ready investor summary with calculated yield.
    """
    workspace_root = os.getcwd()
    city_data_dir = os.path.join(workspace_root, "projects", "CRERAG", city_name, "data")
    input_file = os.path.join(city_data_dir, f"{city_name}_Target_Sites.csv")
    output_file = os.path.join(city_data_dir, f"{city_name}_Investor_Summary.csv")

    if not os.path.exists(input_file) or os.path.getsize(input_file) == 0:
        print(f"Warning: No target sites for {city_name}. Creating empty summary.")
        with open(output_file, mode='w', encoding='utf-8') as f:
             f.write("Address,APN,Total Acreage,Zoning Code & Allowable Density (DU/ac),Maximum Unit Potential\n")
        return

    summary_data = []
    try:
        with open(input_file, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                address = row.get('site_address', 'N/A')
                apn = row.get('parcel_id', 'N/A')
                site_id = row.get('site_id', '')
                if site_id:
                    apn = f"Site {site_id} ({apn})"

                try:
                    raw_acreage = row.get('total_acreage', '0').strip()
                    acreage = float(raw_acreage) if raw_acreage else 0.0
                except:
                    acreage = 0.0
                
                zoning = row.get('zoning_code', '') or site_id
                
                max_d_val = row.get('max_density', '0').strip()
                max_d = float(max_d_val) if max_d_val else 0.0
                
                if max_d != 0:
                    max_density_calc = max_d
                    raw_rule = f"{row.get('min_density','0')}-{max_d} DU/ac"
                else:
                    try:
                        raw_screen = row.get('screen_density', '0').strip()
                        max_density_calc = float(raw_screen) if raw_screen else 0.0
                    except:
                        max_density_calc = 0.0
                    raw_rule = f"{int(max_density_calc)} DU/ac"
                
                if row.get('unit_capacity'):
                    try:
                        raw_cap = row.get('unit_capacity', '0').strip()
                        max_units = int(raw_cap) if raw_cap else int(acreage * max_density_calc)
                    except:
                        max_units = int(acreage * max_density_calc)
                else:
                    max_units = int(acreage * max_density_calc)
                
                zoning_density_str = f"{zoning} ({raw_rule})"
                
                summary_data.append({
                    "Address": address,
                    "APN": apn,
                    "Total Acreage": f"{acreage:.2f}",
                    "Zoning Code & Allowable Density (DU/ac)": zoning_density_str,
                    "Maximum Unit Potential": max_units
                })

        headers = ["Address", "APN", "Total Acreage", "Zoning Code & Allowable Density (DU/ac)", "Maximum Unit Potential"]
        with open(output_file, mode='w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(summary_data)
        print(f"[*] Investor Summary Updated: {len(summary_data)} sites.")
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    generate_summary(sys.argv[1])
