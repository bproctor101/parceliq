#!/usr/bin/env python3
import csv
import os
import sys

# SCHEMA_MAP: Normalization dictionary for municipal data headers.
# Keys are known source variants; Values are the CRERAG standard.
SCHEMA_MAP = {
    # Parcel Identification
    "APN": "parcel_id",
    "ASSESSOR'S PARCEL NUMBER": "parcel_id",
    "ASSESSOR PARCEL NUMBER": "parcel_id",
    "ASSESSOR PARCEL NUMBER (APN)": "parcel_id",
    "PARCEL NUMBER": "parcel_id",
    "PARCEL_ID": "parcel_id",
    
    # Location/Address
    "ADDRESS": "site_address",
    "SITE ADDRESS": "site_address",
    "SITE ADDRESS/INTERSECTION": "site_address",
    "LOCATION": "site_address",
    
    # Planning/Zoning
    "ZONING": "zoning_code",
    "ZONING CODE": "zoning_code",
    "ZONING DESIGNATION": "zoning_code",
    "ZONING DESIGNATION (CURRENT)": "zoning_code",
    "ZONGDSGN": "zoning_code",
    "GENERAL PLAN DESIGNATION": "gp_designation",
    "GENERAL PLAN DESIGNATION (CURRENT)": "gp_designation",
    "GPLANCRT": "gp_designation",
    "DESIGNATION": "zoning_code",
    "OVERLAY": "overlay_code",
    "OVERLAY DISTRICT": "overlay_code",
    
    # Capacity/Metrics
    "CAPACITY": "unit_capacity",
    "TOTAL CAPACITY": "unit_capacity",
    "UNITS": "unit_capacity",
    "TOTAL UNITS": "unit_capacity",
    "UNIT CAPACITY": "unit_capacity",
    "ACRES": "total_acreage",
    "ACREAGE": "total_acreage",
    "SITE SIZE": "total_acreage",
    "NET ACREAGE": "total_acreage",
    "PARCEL SIZE (ACRE)": "total_acreage",
    "PARCEL SIZE (ACRES)": "total_acreage",
    "MINIMUM DENSITY": "min_density",
    "MINIMUM DENSITY ALLOWED": "min_density",
    "MINIMUM DENSITY ALLOWED (UNITS/ACRE)": "min_density",
    "MAXIMUM DENSITY": "max_density",
    "MAXIMUM DENSITY ALLOWED": "max_density",
    "MAXIMUM DENSITY ALLOWED (UNITS/ACRE)": "max_density"
}

def normalize_csv(input_path, output_path):
    """
    Reads a source CSV, translates headers based on SCHEMA_MAP, 
    and writes the normalized data to a new file.
    """
    if not os.path.exists(input_path):
        print(f"Error: Input file not found at {input_path}")
        sys.exit(1)

    try:
        with open(input_path, mode='r', encoding='utf-8') as infile:
            csv_reader = csv.reader(infile)
            
            # Find header row (it's often the second or third row in these HCD tables)
            headers = None
            rows_to_keep = []
            try:
                for row in csv_reader:
                    # Clean the row
                    clean_row = [cell.strip() for cell in row]
                    
                    # Look for header markers
                    if any(marker in [c.upper() for c in clean_row] for marker in ["APN", "JURISDICTION NAME", "ASSESSOR PARCEL NUMBER"]):
                        headers = clean_row
                        break
                
                # If we found headers, collect the remaining rows
                if headers:
                    for row in csv_reader:
                        rows_to_keep.append(row)
                else:
                    # Fallback: if no markers found, restart and treat first row as header
                    infile.seek(0)
                    csv_reader = csv.reader(infile)
                    headers = next(csv_reader)
                    for row in csv_reader:
                        rows_to_keep.append(row)

            except StopIteration:
                print("Error: Empty file or headers not found.")
                sys.exit(1)
            
            # Perform Header Translation
            normalized_headers = [SCHEMA_MAP.get(h.strip().upper(), h) for h in headers]
            
            # Write Normalized Data
            with open(output_path, mode='w', encoding='utf-8', newline='') as outfile:
                writer = csv.writer(outfile)
                writer.writerow(normalized_headers)
                for row in rows_to_keep:
                    writer.writerow(row)
        
        print(f"Success: Normalized data written to {output_path}")
    
    except Exception as e:
        print(f"Error during normalization: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 normalize_schema.py <input_csv_path> <output_csv_path>")
        sys.exit(1)
    
    in_file = sys.argv[1]
    out_file = sys.argv[2]
    
    normalize_csv(in_file, out_file)
