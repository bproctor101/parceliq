#!/usr/bin/env python3
"""
inject_density.py — Zoning-to-Density Injector for ParcelIQ
============================================================
Reads a {City}_Zoning_Mapped.csv (output of gis_pipeline.py),
looks up min/max density from a per-city JSON dictionary,
and writes the density columns into the CSV.

This is Step 8 of the pipeline — translating the "barcode" (zoning code)
into the actual density rules from the municipal code.

Usage:
  python inject_density.py <city_csv> <density_json>
  python inject_density.py data/cities/Mountain_View_Zoning_Mapped.csv data/density_rules/Mountain_View.json
  python inject_density.py --batch     # inject all cities that have both a CSV and a JSON

JSON format:
{
  "city": "Mountain View",
  "source": "Municipal Code Title 36, Table 36.06",
  "last_updated": "2026-04-16",
  "zones": {
    "R1": {"min_density": 0, "max_density": 15, "description": "Single-Family Residential"},
    "R2": {"min_density": 15, "max_density": 25, "description": "Two-Family Residential"},
    ...
  }
}
"""

import csv
import json
import os
import sys
import re
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
CITIES_DIR = os.path.join(PROJECT_DIR, 'data', 'cities')
DENSITY_DIR = os.path.join(PROJECT_DIR, 'data', 'density_rules')


def detect_zoning_column(headers):
    """Auto-detect which column holds the zoning code."""
    patterns = [
        r'^zoning$', r'^zoning.?$', r'^zone$', r'^zoning.?code',
        r'^zoneclass$', r'^zone.?code', r'^zoning.?report',
        r'^zone_code', r'^ZONING', r'^ZONE'
    ]
    for pattern in patterns:
        for h in headers:
            if re.match(pattern, h, re.IGNORECASE):
                return h
    return None


def normalize_zone_code(code):
    """Normalize a zone code for lookup: strip whitespace, uppercase."""
    if not code:
        return ''
    return str(code).strip().upper()


def inject_density(csv_path, json_path, output_path=None):
    """
    Read a Zoning_Mapped CSV, look up density from JSON, write enriched CSV.
    """
    # Load density dictionary
    with open(json_path, 'r') as f:
        density_data = json.load(f)

    city_name = density_data.get('city', 'Unknown')
    zones = density_data.get('zones', {})

    # Build normalized lookup: UPPERCASE code -> {min, max}
    lookup = {}
    for code, rules in zones.items():
        normalized = normalize_zone_code(code)
        lookup[normalized] = rules

    print(f"\n{'='*60}")
    print(f"  DENSITY INJECTION: {city_name}")
    print(f"  Source: {density_data.get('source', 'N/A')}")
    print(f"  Rules loaded: {len(lookup)} zone codes")
    print(f"{'='*60}")

    # Read CSV
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames)
        rows = list(reader)

    # Detect zoning column
    zone_col = detect_zoning_column(headers)
    if not zone_col:
        print(f"  [!] Could not detect zoning column in: {headers}")
        return False

    print(f"  Zoning column: {zone_col}")

    # Add density columns if not present
    if 'Min_Density' not in headers:
        headers.append('Min_Density')
    if 'Max_Density' not in headers:
        headers.append('Max_Density')

    # Inject density
    matched = 0
    unmatched_codes = set()

    for row in rows:
        raw_code = row.get(zone_col, '')
        normalized = normalize_zone_code(raw_code)

        # Try exact match first
        rules = lookup.get(normalized)

        # Fallback: try stripping (PD) suffix — common in San Jose
        if not rules and '(PD)' in normalized:
            base_code = normalized.replace('(PD)', '').strip()
            rules = lookup.get(base_code)

        # Fallback: try matching just the base code before any dash-suffix
        if not rules and '-' in normalized:
            base = normalized.split('-')[0]
            rules = lookup.get(base)

        if rules:
            row['Min_Density'] = rules.get('min_density', 0)
            row['Max_Density'] = rules.get('max_density', 0)
            matched += 1
        else:
            row['Min_Density'] = ''
            row['Max_Density'] = ''
            if normalized and normalized not in ('', 'NA', 'N/A', 'NONE'):
                unmatched_codes.add(raw_code)

    # Write output
    if not output_path:
        output_path = csv_path  # overwrite in place

    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    total_with_zoning = sum(1 for r in rows if r.get(zone_col, '').strip())
    pct = matched / max(total_with_zoning, 1) * 100

    print(f"\n  Results:")
    print(f"    Total rows:              {len(rows):,}")
    print(f"    Rows with zoning code:   {total_with_zoning:,}")
    print(f"    Density matched:         {matched:,} ({pct:.1f}%)")

    if unmatched_codes:
        print(f"    Unmatched codes ({len(unmatched_codes)}):")
        for code in sorted(unmatched_codes):
            print(f"      - {code}")

    print(f"\n  Output: {output_path}")
    print(f"{'='*60}\n")
    return True


def batch_inject():
    """Find all cities that have both a Zoning_Mapped CSV and a density JSON."""
    print(f"\n[*] Scanning for cities with density rules...")

    processed = 0
    for json_file in sorted(os.listdir(DENSITY_DIR)):
        if not json_file.endswith('.json'):
            continue

        city_slug = json_file.replace('.json', '')
        csv_candidates = [
            os.path.join(CITIES_DIR, f"{city_slug}_Zoning_Mapped.csv"),
            os.path.join(CITIES_DIR, f"{city_slug}_GIS_Raw.csv"),
        ]

        csv_path = None
        for candidate in csv_candidates:
            if os.path.exists(candidate):
                csv_path = candidate
                break

        if not csv_path:
            print(f"  [--] {city_slug}: No matching CSV found. Skipping.")
            continue

        json_path = os.path.join(DENSITY_DIR, json_file)
        inject_density(csv_path, json_path)
        processed += 1

    print(f"\n[*] Batch complete: {processed} cities processed.")


def main():
    parser = argparse.ArgumentParser(
        description='Inject min/max density from municipal code JSON into GIS CSV'
    )
    parser.add_argument('csv_path', nargs='?', help='Path to {City}_Zoning_Mapped.csv')
    parser.add_argument('json_path', nargs='?', help='Path to density rules JSON')
    parser.add_argument('--output', '-o', help='Output path (default: overwrite input)')
    parser.add_argument('--batch', action='store_true', help='Process all cities with density JSONs')

    args = parser.parse_args()

    if args.batch:
        batch_inject()
    elif args.csv_path and args.json_path:
        inject_density(args.csv_path, args.json_path, args.output)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
