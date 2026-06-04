#!/usr/bin/env python3
"""
normalize_city.py — Universal GIS CSV Normalizer for ParcelIQ
=============================================================
Replaces per-city scripts (normalize_san_jose.py, normalize_milpitas.py, etc.)
with a single smart normalizer that auto-detects column mappings.

Usage:
  python normalize_city.py <input_csv> <city_name> [--output <path>] [--dry-run] [--no-confirm]

Examples:
  python normalize_city.py data/cities/Fremont_Zoning_Mapped.csv Fremont
  python normalize_city.py data/cities/Oakland_GIS.csv Oakland --dry-run
  python normalize_city.py data/cities/Cupertino_Raw.csv Cupertino --no-confirm
"""

import csv
import os
import sys
import re
import argparse
from collections import OrderedDict

# ─────────────────────────────────────────────────────────────
# TARGET SCHEMA — the 8 columns every city must map into
# ─────────────────────────────────────────────────────────────
TARGET_HEADERS = [
    'city',
    'site_address',
    'parcel_id',
    'gp_designation',
    'zoning_code',
    'min_density',
    'max_density',
    'total_acreage'
]

# ─────────────────────────────────────────────────────────────
# ALIAS PATTERNS — regex patterns that match known column names
# Order matters: first match wins. Patterns are case-insensitive.
# Built from: San Jose, Milpitas, HEI statewide, and common
#             ArcGIS/county assessor export conventions.
# ─────────────────────────────────────────────────────────────
ALIAS_PATTERNS = OrderedDict({
    'parcel_id': [
        r'^apn$',
        r'^apn.?(?:pq|gis|aca)$',    # Hayward: APN_PQ, APN_GIS, APN_ACA
        r'^apn.?(?:left|right)$',     # Moraga: APN_left from spatial join
        r'^assessor.?parcel.?num',
        r'^parcel.?(?:id|number|num|no)',
        r'^gis.?parcel.?id',          # Sunnyvale: GIS_PARCEL_ID
        r'^pcl.?concat',              # Fremont: PCL_CONCAT
        r'^acct$',                     # Sunnyvale: Acct
        r'^pin$',
        r'^parcel$',
        r'^apn.?(?:number|num|no|id)',
        r'^tax.?(?:parcel|id|lot)',
        r'^blklot$',
    ],
    'total_acreage': [
        r'^parcel.?in.?acres',       # Cupertino: PARCEL_IN_ACRES (parcel-level, preferred)
        r'^parcel.?size.?\(?acres',
        r'^lot.?size.?ac',
        r'^lot.?acres',
        r'^total.?acreage',
        r'^gis.?acres',
        r'^net.?acres',
        r'^gross.?acres',
        r'^acreage$',                 # Zone-level fallback (e.g. Fremont)
        r'^acres$',
        r'^area.?acres',
        # Square-feet columns (will need conversion flag)
        r'^shape.?area$',
        r'^shape__area$',
        r'^st_area',
        r'^sq.?ft',
        r'^area.?sq',
        r'^lot.?size.?sf',
    ],
    'zoning_code': [
        r'^zoning$',
        r'^zoning.?$',          # Hayward: "ZONING_" (trailing underscore)
        r'^zoning.?(?:code|designation|class|dist)',
        r'^zoning.?desc',       # "Zoning Description" — Milpitas uses this
        r'^zoning.?report',     # Hayward: "ZONING_REPORT"
        r'^current.?zoning',
        r'^zn.?code',
        r'^zoneclass$',         # Mountain View: "ZONECLASS"
        r'^zone.?class',
        r'^zone.?dist',         # Fremont: ZONE_DIST
        r'^land.?use.?zone',
        r'^zone$',              # bare "Zone" — last resort (too generic)
    ],
    'gp_designation': [
        r'^gp.?(?:land.?use|designation)',
        r'^general.?plan',
        r'^current.?general.?plan',
        r'^gp$',
        r'^land.?use$',
        r'^land.?use.?designation',
        r'^land.?use.?desc',
        r'^gen.?plan',
    ],
    'max_density': [
        r'^max.?(?:density|du|den|dens)',
        r'^max.?du.?(?:ac|acre)',
        r'^maximum.?density',
        r'^max_du_acre',
        r'^du.?max',
        r'^density.?max',
        r'^max.?(?:units|dwelling)',
    ],
    'min_density': [
        r'^min.?(?:density|du|den|dens)',
        r'^min.?du.?(?:ac|acre)',
        r'^minimum.?density',
        r'^min_du_acre',
        r'^du.?min',
        r'^density.?min',
        r'^min.?(?:units|dwelling)',
    ],
    'site_address': [
        r'^(?:site.?)?address',
        r'^street.?address',
        r'^p.?st.?address',     # Hayward: P_ST_ADDRESS
        r'^location',
        r'^feature.?name',
        r'^situs$',
        r'^situs.?addr',
        r'^situs.?house',       # Mountain View: SITUS_HOUSE_NUMBER
        r'^property.?addr',
        r'^site.?addr',
        r'^physical.?addr',
    ],
    # 'city' is almost never a source column — it's injected from the CLI arg.
    # But just in case:
    'city': [
        r'^(?:city|jurisdiction|muni|municipality)$',
    ],
})

# Columns whose raw values are in square feet (not acres)
SQFT_AREA_PATTERNS = [
    r'^shape.?area$',
    r'^shape__area$',
    r'^st_area',
    r'^sq.?ft',
    r'^area.?sq',
    r'^lot.?size.?sf',
]

SQFT_TO_ACRES = 43560.0


# ─────────────────────────────────────────────────────────────
# AUTO-MAPPER
# ─────────────────────────────────────────────────────────────
def auto_map_columns(source_headers):
    """
    Given a list of source CSV headers, returns:
      mapping:  { target_field: source_column_name }
      unmapped: [ source columns that didn't match anything ]
      is_sqft:  bool — True if the matched acreage column is in sq ft
    """
    mapping = {}
    used_sources = set()
    is_sqft = False

    # Clean headers (strip BOM, whitespace)
    cleaned = [h.strip().strip('\ufeff') for h in source_headers]

    for target_field, patterns in ALIAS_PATTERNS.items():
        for pattern in patterns:
            for i, src_col in enumerate(cleaned):
                if src_col in used_sources:
                    continue
                if re.match(pattern, src_col, re.IGNORECASE):
                    mapping[target_field] = source_headers[i]  # original name
                    used_sources.add(src_col)

                    # Check if this is a sq-ft area column
                    if target_field == 'total_acreage':
                        for sqft_pat in SQFT_AREA_PATTERNS:
                            if re.match(sqft_pat, src_col, re.IGNORECASE):
                                is_sqft = True
                    break
            if target_field in mapping:
                break  # move to next target field

    unmapped_sources = [h for h in source_headers
                        if h.strip().strip('\ufeff') not in used_sources]
    missing_targets = [t for t in TARGET_HEADERS if t not in mapping and t != 'city']

    return mapping, unmapped_sources, missing_targets, is_sqft


# ─────────────────────────────────────────────────────────────
# DISPLAY MAPPING FOR USER REVIEW
# ─────────────────────────────────────────────────────────────
def print_mapping_report(mapping, unmapped, missing, is_sqft, city_name):
    print(f"\n{'='*60}")
    print(f"  AUTO-MAPPING REPORT — {city_name}")
    print(f"{'='*60}")
    print(f"\n  Target Field          <--  Source Column")
    print(f"  {'-'*22}      {'-'*30}")

    for target in TARGET_HEADERS:
        if target == 'city':
            src = f'(injected: "{city_name}")'
        elif target in mapping:
            src = mapping[target]
            if target == 'total_acreage' and is_sqft:
                src += '  [sq ft -> will convert to acres]'
        else:
            src = '** NOT FOUND **'
        print(f"  {target:<22}  <--  {src}")

    if unmapped:
        print(f"\n  Ignored source columns ({len(unmapped)}):")
        for col in unmapped:
            print(f"    - {col}")

    if missing:
        print(f"\n  [!] WARNING — Missing target fields: {missing}")
        print(f"      These will be empty in the output.")

    if is_sqft:
        print(f"\n  [i] Area conversion: sq ft / {SQFT_TO_ACRES:,.0f} = acres")

    print()


# ─────────────────────────────────────────────────────────────
# NORMALIZATION ENGINE
# ─────────────────────────────────────────────────────────────
def normalize_city(input_path, city_name, output_path=None,
                   dry_run=False, no_confirm=False):
    """
    Main entry point. Reads input CSV, auto-maps columns,
    normalizes to standard schema, writes output.
    """
    if not os.path.exists(input_path):
        print(f"[!] File not found: {input_path}")
        return False

    # --- Read headers ---
    with open(input_path, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            print(f"[!] Empty or unreadable file: {input_path}")
            return False
        source_headers = list(reader.fieldnames)

    # --- Auto-map ---
    mapping, unmapped, missing, is_sqft = auto_map_columns(source_headers)
    print_mapping_report(mapping, unmapped, missing, is_sqft, city_name)

    # --- Confirm with user (unless --no-confirm or --dry-run) ---
    if dry_run:
        print("[DRY RUN] No output file written.")
        return True

    if not no_confirm:
        answer = input("  Proceed with this mapping? [Y/n]: ").strip().lower()
        if answer and answer != 'y':
            print("[*] Aborted by user.")
            return False

    # --- Determine output path ---
    if not output_path:
        base_dir = os.path.dirname(input_path)
        city_slug = city_name.replace(' ', '_')
        output_path = os.path.join(base_dir, f"{city_slug}_normalized.csv")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # --- Process rows ---
    count = 0
    excluded_density = 0
    excluded_empty = 0

    with open(input_path, mode='r', encoding='utf-8-sig') as infile:
        reader = csv.DictReader(infile)

        with open(output_path, mode='w', encoding='utf-8', newline='') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=TARGET_HEADERS)
            writer.writeheader()

            for row in reader:
                # --- Extract max_density and validate ---
                raw_max = ''
                if 'max_density' in mapping:
                    raw_max = row.get(mapping['max_density'], '').strip()

                # Skip rows with non-numeric or empty max_density
                if not raw_max or raw_max.upper() in ('N/A', 'NONE', 'NULL', 'CUSTOM', 'NO MAX', ''):
                    excluded_density += 1
                    continue
                try:
                    max_density_val = float(raw_max)
                except ValueError:
                    excluded_density += 1
                    continue

                # --- Extract min_density ---
                raw_min = '0'
                if 'min_density' in mapping:
                    raw_min = row.get(mapping['min_density'], '0').strip()
                try:
                    float(raw_min)
                except ValueError:
                    raw_min = '0'

                # --- Extract acreage (with sq ft conversion if needed) ---
                raw_acreage = '0'
                if 'total_acreage' in mapping:
                    raw_acreage = row.get(mapping['total_acreage'], '0').strip()
                try:
                    acreage_val = float(raw_acreage)
                    if is_sqft:
                        acreage_val = acreage_val / SQFT_TO_ACRES
                    raw_acreage = str(acreage_val) if not is_sqft else f"{acreage_val:.6f}"
                except ValueError:
                    raw_acreage = '0'

                # --- Extract parcel_id ---
                raw_apn = ''
                if 'parcel_id' in mapping:
                    raw_apn = row.get(mapping['parcel_id'], '').strip()
                if not raw_apn:
                    excluded_empty += 1
                    continue

                # --- Extract optional fields ---
                raw_zoning = ''
                if 'zoning_code' in mapping:
                    raw_zoning = row.get(mapping['zoning_code'], '').strip()

                raw_gp = ''
                if 'gp_designation' in mapping:
                    raw_gp = row.get(mapping['gp_designation'], '').strip()

                raw_address = ''
                if 'site_address' in mapping:
                    raw_address = row.get(mapping['site_address'], '').strip()

                # --- Build normalized row ---
                normalized_row = {
                    'city': city_name.title(),
                    'site_address': raw_address,
                    'parcel_id': raw_apn,
                    'gp_designation': raw_gp,
                    'zoning_code': raw_zoning,
                    'min_density': raw_min,
                    'max_density': raw_max,
                    'total_acreage': raw_acreage,
                }

                writer.writerow(normalized_row)
                count += 1

    # --- Report ---
    print(f"\n{'='*60}")
    print(f"  NORMALIZATION COMPLETE — {city_name}")
    print(f"{'='*60}")
    print(f"  Records written:          {count:,}")
    print(f"  Excluded (bad density):   {excluded_density:,}")
    print(f"  Excluded (no APN):        {excluded_empty:,}")
    print(f"  Output:                   {output_path}")
    print(f"{'='*60}\n")

    return True


# ─────────────────────────────────────────────────────────────
# BATCH MODE — normalize all *_Zoning_Mapped.csv in a directory
# ─────────────────────────────────────────────────────────────
def batch_normalize(cities_dir, no_confirm=False):
    """
    Scans cities_dir for files matching *_Zoning_Mapped.csv or *_GIS_Raw.csv,
    extracts city name from filename, and normalizes each.
    """
    candidates = []
    for f in sorted(os.listdir(cities_dir)):
        if f.endswith('_Zoning_Mapped.csv') or f.endswith('_GIS_Raw.csv'):
            # Skip if already has a normalized counterpart
            city_slug = f.replace('_Zoning_Mapped.csv', '').replace('_GIS_Raw.csv', '')
            norm_file = os.path.join(cities_dir, f"{city_slug}_normalized.csv")
            candidates.append((os.path.join(cities_dir, f), city_slug.replace('_', ' ')))

    if not candidates:
        print("[!] No *_Zoning_Mapped.csv or *_GIS_Raw.csv files found.")
        return

    # Prefer Zoning_Mapped over GIS_Raw if both exist for same city
    seen_cities = {}
    for path, city in candidates:
        if city not in seen_cities or 'Zoning_Mapped' in path:
            seen_cities[city] = path

    print(f"\n[*] Found {len(seen_cities)} cities to normalize:")
    for city, path in seen_cities.items():
        print(f"    - {city}: {os.path.basename(path)}")
    print()

    for city, path in seen_cities.items():
        normalize_city(path, city, no_confirm=no_confirm)


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description='Universal GIS CSV Normalizer for ParcelIQ',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Single city:   python normalize_city.py data/cities/Fremont_Zoning_Mapped.csv Fremont
  Batch mode:    python normalize_city.py --batch data/cities/
  Dry run:       python normalize_city.py data/cities/Oakland_GIS.csv Oakland --dry-run
  No prompts:    python normalize_city.py data/cities/Oakland_GIS.csv Oakland --no-confirm
        """
    )

    parser.add_argument('input_csv', nargs='?', help='Path to the city GIS/Zoning CSV')
    parser.add_argument('city_name', nargs='?', help='City name (e.g., "San Jose", "Fremont")')
    parser.add_argument('--output', '-o', help='Custom output path (default: {City}_normalized.csv)')
    parser.add_argument('--dry-run', action='store_true', help='Show mapping without writing output')
    parser.add_argument('--no-confirm', action='store_true', help='Skip confirmation prompt')
    parser.add_argument('--batch', metavar='DIR', help='Batch-normalize all cities in a directory')

    args = parser.parse_args()

    if args.batch:
        batch_normalize(args.batch, no_confirm=args.no_confirm)
    elif args.input_csv and args.city_name:
        normalize_city(args.input_csv, args.city_name,
                       output_path=args.output,
                       dry_run=args.dry_run,
                       no_confirm=args.no_confirm)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
