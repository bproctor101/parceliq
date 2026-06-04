#!/usr/bin/env python3
"""
gis_pipeline.py — Programmatic GIS Pipeline for ParcelIQ
=========================================================
Replaces the manual QGIS workflow: downloads parcel + zoning layers
from ArcGIS REST APIs, performs spatial join in Python, and exports
a CSV ready for normalize_city.py.

Usage:
  python gis_pipeline.py <city_name>                   # Single city
  python gis_pipeline.py <city_name> --dry-run          # Preview only
  python gis_pipeline.py --list                          # Show all cities & status
  python gis_pipeline.py --batch                         # Run all 'ready' cities
  python gis_pipeline.py --batch --county "Santa Clara"  # Run one county

Requirements: geopandas, requests, pyproj, shapely
"""

import os
import sys
import json
import time
import math
import argparse
import warnings
import requests
import geopandas as gpd
import pandas as pd
from shapely.geometry import shape, Point

warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
REGISTRY_PATH = os.path.join(SCRIPT_DIR, 'city_registry.json')
CITIES_DIR = os.path.join(PROJECT_DIR, 'data', 'cities')
CACHE_DIR = os.path.join(PROJECT_DIR, 'data', '.gis_cache')

STATEWIDE_ZONING_URL = (
    "https://services8.arcgis.com/Xr1lDrwMv89PhjD9/arcgis/rest/services/"
    "California_Statewide_Zoning_North/FeatureServer/1"
)

# County-level parcel endpoints
COUNTY_PARCELS = {
    "Santa Clara": {
        "url": "https://services8.arcgis.com/fpjs8A5Vtkshblnd/arcgis/rest/services/Santa_Clara_County_Parcels/FeatureServer/0",
    },
    "Alameda": {
        "url": "https://services5.arcgis.com/ROBnTHSNjoZ2Wm1P/arcgis/rest/services/Parcels/FeatureServer/0",
    },
    "Contra Costa": {
        "url": "https://gis.cccounty.us/arcgis/rest/services/CCMAP/Assessment_Parcels_ArcPro/MapServer/0",
    },
}

SQFT_TO_ACRES = 43560.0
TARGET_CRS = "EPSG:4326"  # WGS84 for standardization


# ─────────────────────────────────────────────────────────────
# ARCGIS REST API CLIENT
# ─────────────────────────────────────────────────────────────
class ArcGISClient:
    """Downloads features from ArcGIS REST API with pagination."""

    def __init__(self, timeout=60, max_retries=3):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'ParcelIQ-Pipeline/1.0'})
        self.timeout = timeout
        self.max_retries = max_retries

    def get_layer_info(self, url):
        """Get layer metadata: fields, max record count, geometry type."""
        params = {'f': 'json'}
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        info = resp.json()
        return {
            'name': info.get('name', 'Unknown'),
            'max_record_count': info.get('maxRecordCount', 1000),
            'fields': [f['name'] for f in info.get('fields', [])],
            'geometry_type': info.get('geometryType', ''),
            'extent': info.get('extent', {}),
            'wkid': info.get('extent', {}).get('spatialReference', {}).get('wkid',
                    info.get('sourceSpatialReference', {}).get('wkid', 4326))
        }

    def get_feature_count(self, url, where="1=1"):
        """Get total feature count for a query."""
        params = {
            'where': where,
            'returnCountOnly': 'true',
            'f': 'json'
        }
        resp = self.session.get(f"{url}/query", params=params, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        return data.get('count', 0)

    def download_features(self, url, where="1=1", out_fields="*",
                          city_name=None, max_features=None):
        """
        Download all features with pagination. Returns a GeoDataFrame.
        Uses resultOffset pagination (preferred) with OID fallback.
        """
        info = self.get_layer_info(url)
        page_size = info['max_record_count']
        total = self.get_feature_count(url, where)

        if total == 0:
            print(f"    [!] No features found for query: {where}")
            return gpd.GeoDataFrame()

        if max_features:
            total = min(total, max_features)

        print(f"    [i] {info['name']}: {total:,} features, page size {page_size}")

        all_features = []
        offset = 0
        page_num = 0

        while offset < total:
            page_num += 1
            remaining = total - offset
            current_page = min(page_size, remaining)

            params = {
                'where': where,
                'outFields': out_fields,
                'returnGeometry': 'true',
                'f': 'geojson',
                'resultOffset': offset,
                'resultRecordCount': current_page,
                'outSR': '4326'  # Request WGS84 output
            }

            for attempt in range(self.max_retries):
                try:
                    resp = self.session.get(
                        f"{url}/query", params=params,
                        timeout=self.timeout
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    features = data.get('features', [])
                    if not features:
                        break

                    all_features.extend(features)
                    pct = min(100, int((offset + len(features)) / total * 100))
                    print(f"    [>] Page {page_num}: {len(features)} features "
                          f"({pct}% complete)", end='\r')
                    break

                except Exception as e:
                    if attempt < self.max_retries - 1:
                        wait = 2 ** attempt
                        print(f"\n    [!] Retry {attempt+1}/{self.max_retries} "
                              f"in {wait}s: {e}")
                        time.sleep(wait)
                    else:
                        print(f"\n    [!!] Failed after {self.max_retries} attempts: {e}")
                        break

            if not data.get('features'):
                break
            offset += len(features)

        print(f"    [+] Downloaded {len(all_features):,} features total")

        if not all_features:
            return gpd.GeoDataFrame()

        # Build GeoDataFrame from GeoJSON features
        geojson = {
            'type': 'FeatureCollection',
            'features': all_features
        }
        gdf = gpd.GeoDataFrame.from_features(geojson, crs="EPSG:4326")
        return gdf


# ─────────────────────────────────────────────────────────────
# SPATIAL JOIN ENGINE
# ─────────────────────────────────────────────────────────────
def spatial_join(parcels_gdf, zoning_gdf, city_name):
    """
    Replicates the QGIS workflow:
    1. Convert parcel polygons to centroids
    2. Join centroids to zoning polygons (within)
    3. Return joined GeoDataFrame
    """
    print(f"  [3] Spatial join...")

    if parcels_gdf.empty or zoning_gdf.empty:
        print("    [!] Empty input — skipping join.")
        return gpd.GeoDataFrame()

    # Ensure same CRS
    if parcels_gdf.crs != zoning_gdf.crs:
        print(f"    [i] Reprojecting zoning from {zoning_gdf.crs} to {parcels_gdf.crs}")
        zoning_gdf = zoning_gdf.to_crs(parcels_gdf.crs)

    # Convert parcels to centroids (the "centroid trick" from your QGIS workflow)
    print(f"    [i] Converting {len(parcels_gdf):,} parcels to centroids...")
    centroids = parcels_gdf.copy()
    centroids['geometry'] = centroids.geometry.centroid

    # Spatial join: centroids within zoning polygons
    print(f"    [i] Joining against {len(zoning_gdf):,} zoning polygons...")
    joined = gpd.sjoin(centroids, zoning_gdf, how='left', predicate='within')

    # Drop the index_right column from sjoin
    if 'index_right' in joined.columns:
        joined = joined.drop(columns=['index_right'])

    # Count matches by checking if any zoning column got populated
    zoning_cols = [c for c in joined.columns if c not in parcels_gdf.columns and c != 'index_right']
    if zoning_cols:
        matched = joined[zoning_cols[0]].notna().sum()
        print(f"    [+] Joined: {len(joined):,} parcels, {matched:,} matched to zones")
    else:
        print(f"    [+] Joined: {len(joined):,} parcels")

    return joined


# ─────────────────────────────────────────────────────────────
# ACREAGE CALCULATOR
# ─────────────────────────────────────────────────────────────
def compute_acreage(gdf):
    """
    If no acreage column exists, compute from geometry.
    Projects to a local CRS (CA State Plane Zone 3) for accurate area.
    """
    # Check if acreage already exists
    acre_cols = [c for c in gdf.columns
                 if any(k in c.lower() for k in ['acre', 'acreage', 'area_ac'])]

    if acre_cols:
        print(f"    [i] Using existing acreage column: {acre_cols[0]}")
        return gdf

    # Check for sq ft columns
    sqft_cols = [c for c in gdf.columns
                 if any(k in c.lower() for k in ['shape_area', 'shape__area', 'st_area', 'sqft'])]

    if sqft_cols:
        col = sqft_cols[0]
        print(f"    [i] Converting {col} (sq ft) to acres")
        gdf['Acreage'] = pd.to_numeric(gdf[col], errors='coerce') / SQFT_TO_ACRES
        return gdf

    # Compute from geometry
    print(f"    [i] Computing acreage from geometry (CA State Plane III)...")
    projected = gdf.to_crs("EPSG:2227")  # CA State Plane Zone 3 (feet)
    gdf['Acreage'] = projected.geometry.area / SQFT_TO_ACRES
    return gdf


# ─────────────────────────────────────────────────────────────
# FIELD DISCOVERY — auto-detect key fields
# ─────────────────────────────────────────────────────────────
def find_field(columns, patterns):
    """Find the first column matching any of the patterns (case-insensitive)."""
    import re
    for pattern in patterns:
        for col in columns:
            if re.match(pattern, col, re.IGNORECASE):
                return col
    return None


APN_PATTERNS = [r'^apn$', r'^parcel.?(?:id|num)', r'^assessor', r'^pin$', r'^blklot$',
                r'^parcelid$', r'^parcelnumber$', r'^parcel_id$', r'^taxparcelid$']

ZONING_PATTERNS = [r'^zoning$', r'^zone$', r'^zoning.?(?:code|desc|class|dist)',
                   r'^zone.?(?:code|class|desc)', r'^zoneclass$', r'^zonedesc$',
                   r'^name$', r'^code$', r'^label$', r'^zoning_final$']

GP_PATTERNS = [r'^gp.?(?:land|desig)', r'^general.?plan', r'^gplu$',
               r'^land.?use', r'^gen.?plan']

AREA_PATTERNS = [r'^acreage$', r'^acres$', r'^area.?acres', r'^shape.?area',
                 r'^shape__area', r'^lot.?size']


# ─────────────────────────────────────────────────────────────
# EXPORT — produce CSV for normalize_city.py
# ─────────────────────────────────────────────────────────────
def export_csv(joined_gdf, city_name, output_dir):
    """Export joined data as {City}_Zoning_Mapped.csv ready for normalize_city.py."""

    city_slug = city_name.replace(' ', '_')
    output_path = os.path.join(output_dir, f"{city_slug}_Zoning_Mapped.csv")

    cols = joined_gdf.columns.tolist()

    # Auto-detect key fields
    apn_field = find_field(cols, APN_PATTERNS)
    zoning_field = find_field(cols, ZONING_PATTERNS)
    gp_field = find_field(cols, GP_PATTERNS)
    area_field = find_field(cols, AREA_PATTERNS)

    print(f"  [4] Exporting CSV...")
    print(f"    [i] Detected fields: APN={apn_field}, Zone={zoning_field}, "
          f"GP={gp_field}, Area={area_field}")

    # Build a clean export DataFrame
    export_df = pd.DataFrame()

    if apn_field:
        export_df['APN'] = joined_gdf[apn_field]
    if area_field:
        export_df['Acreage'] = pd.to_numeric(joined_gdf[area_field], errors='coerce')
    elif 'Acreage' in joined_gdf.columns:
        export_df['Acreage'] = joined_gdf['Acreage']
    if zoning_field:
        export_df['ZONING'] = joined_gdf[zoning_field]
    if gp_field:
        export_df['GP_Land_Use'] = joined_gdf[gp_field]

    # Include ALL original columns as well for completeness
    for col in cols:
        if col not in export_df.columns and col != 'geometry':
            export_df[col] = joined_gdf[col]

    # Drop geometry column if present
    if 'geometry' in export_df.columns:
        export_df = export_df.drop(columns=['geometry'])

    os.makedirs(output_dir, exist_ok=True)
    export_df.to_csv(output_path, index=False)

    print(f"    [+] Saved: {output_path}")
    print(f"    [+] Rows: {len(export_df):,}")

    return output_path


# ─────────────────────────────────────────────────────────────
# MAIN PIPELINE — per city
# ─────────────────────────────────────────────────────────────
def run_city_pipeline(city_name, registry, dry_run=False):
    """Full pipeline for one city: download → join → export."""

    city_cfg = registry['cities'].get(city_name)
    if not city_cfg:
        print(f"[!] City '{city_name}' not found in registry.")
        print(f"    Available: {', '.join(sorted(registry['cities'].keys()))}")
        return False

    if city_cfg.get('status') == 'done':
        print(f"[=] {city_name}: Already processed. Skipping.")
        return True

    print(f"\n{'='*60}")
    print(f"  PIPELINE: {city_name} ({city_cfg['county']} County)")
    print(f"  Status: {city_cfg['status']}")
    print(f"{'='*60}")

    if dry_run:
        print(f"  Zoning: {city_cfg.get('zoning_url', 'N/A')}")
        print(f"  Parcels: {city_cfg.get('parcel_url', 'County default')}")
        print(f"  [DRY RUN] Would download and join. No output.")
        return True

    client = ArcGISClient(timeout=90)

    # ── Step 1: Download Zoning ──
    print(f"\n  [1] Downloading zoning layer...")
    zoning_url = city_cfg.get('zoning_url')

    if zoning_url == 'STATEWIDE_FALLBACK':
        print(f"    [i] Using statewide zoning fallback for {city_name}")
        zoning_url = STATEWIDE_ZONING_URL
        # Filter statewide data to just this city
        where = f"Jurisdiction LIKE '%{city_name}%'"
        zoning_gdf = client.download_features(zoning_url, where=where)
    elif zoning_url:
        zoning_gdf = client.download_features(zoning_url)
    else:
        print(f"    [!] No zoning URL configured for {city_name}")
        return False

    if zoning_gdf.empty:
        print(f"    [!] No zoning data retrieved for {city_name}. Aborting.")
        return False

    print(f"    [+] Zoning columns: {list(zoning_gdf.columns)}")

    # ── Step 2: Download Parcels ──
    print(f"\n  [2] Downloading parcel layer...")
    parcel_url = city_cfg.get('parcel_url')

    if parcel_url:
        # City has its own parcel layer
        parcels_gdf = client.download_features(parcel_url)
    else:
        # Use county parcel layer — filter to city boundary via zoning extent
        county = city_cfg['county']
        county_cfg = COUNTY_PARCELS.get(county)

        if county_cfg:
            print(f"    [i] Using {county} County parcel layer")
            # Get zoning extent to spatially filter county parcels
            bounds = zoning_gdf.total_bounds  # [minx, miny, maxx, maxy]
            # Add small buffer
            buf = 0.005  # ~500m in degrees
            envelope = f"{bounds[0]-buf},{bounds[1]-buf},{bounds[2]+buf},{bounds[3]+buf}"

            # Download parcels within the city's zoning extent
            # Using geometry filter via the REST API
            base_url = county_cfg['url']
            params = {
                'where': '1=1',
                'geometry': envelope,
                'geometryType': 'esriGeometryEnvelope',
                'spatialRel': 'esriSpatialRelIntersects',
                'inSR': '4326',
                'outFields': '*',
                'returnGeometry': 'true',
                'f': 'geojson',
                'outSR': '4326',
                'resultRecordCount': 2000,
                'resultOffset': 0
            }

            # Paginated download with spatial filter
            all_features = []
            offset = 0
            page_num = 0
            while True:
                page_num += 1
                params['resultOffset'] = offset
                try:
                    resp = client.session.get(
                        f"{base_url}/query", params=params, timeout=90
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    features = data.get('features', [])
                    if not features:
                        break
                    all_features.extend(features)
                    print(f"    [>] Page {page_num}: {len(features)} parcels "
                          f"(total: {len(all_features):,})", end='\r')
                    offset += len(features)
                    if len(features) < 2000:
                        break
                except Exception as e:
                    print(f"\n    [!] Error on page {page_num}: {e}")
                    break

            print(f"\n    [+] Downloaded {len(all_features):,} county parcels in city extent")

            if all_features:
                geojson = {'type': 'FeatureCollection', 'features': all_features}
                parcels_gdf = gpd.GeoDataFrame.from_features(geojson, crs="EPSG:4326")
            else:
                parcels_gdf = gpd.GeoDataFrame()
        else:
            print(f"    [!] No parcel source for {county} County. Skipping {city_name}.")
            return False

    if parcels_gdf.empty:
        print(f"    [!] No parcel data retrieved for {city_name}. Aborting.")
        return False

    print(f"    [+] Parcel columns: {list(parcels_gdf.columns)}")

    # ── Step 3: Compute acreage if needed ──
    parcels_gdf = compute_acreage(parcels_gdf)

    # ── Step 4: Spatial Join ──
    joined = spatial_join(parcels_gdf, zoning_gdf, city_name)

    if joined.empty:
        print(f"  [!] Spatial join produced no results. Aborting.")
        return False

    # ── Step 5: Export CSV ──
    output_path = export_csv(joined, city_name, CITIES_DIR)

    print(f"\n  {'='*60}")
    print(f"  DONE: {city_name}")
    print(f"  Next step: python normalize_city.py {output_path} \"{city_name}\"")
    print(f"  {'='*60}\n")

    return True


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────
def load_registry():
    with open(REGISTRY_PATH, 'r') as f:
        return json.load(f)


def list_cities(registry, county_filter=None):
    print(f"\n{'='*70}")
    print(f"  ParcelIQ City Registry — {len(registry['cities'])} cities")
    print(f"{'='*70}")

    by_county = {}
    for city, cfg in sorted(registry['cities'].items()):
        c = cfg['county']
        if county_filter and c.lower() != county_filter.lower():
            continue
        by_county.setdefault(c, []).append((city, cfg))

    for county in sorted(by_county):
        print(f"\n  {county} County:")
        for city, cfg in by_county[county]:
            status = cfg['status']
            icon = {'done': '[done]', 'ready': '[ok]  ',
                    'fallback': '[fb]  ', 'needs_verify': '[??]  '}.get(status, '[--]  ')
            note = cfg.get('note', '')
            zurl = cfg.get('zoning_url', 'N/A')
            if zurl and len(str(zurl)) > 50:
                zurl = zurl[:50] + '...'
            print(f"    {icon} {city:<16} {zurl}")
            if note:
                print(f"           {note}")

    print(f"\n  Legend: [done]=processed  [ok]=endpoint verified  "
          f"[fb]=statewide fallback  [??]=needs testing\n")


def main():
    parser = argparse.ArgumentParser(
        description='ParcelIQ GIS Pipeline — Download, Join, Export',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('city', nargs='?', help='City name (e.g., "Mountain View")')
    parser.add_argument('--list', action='store_true', help='List all cities and status')
    parser.add_argument('--batch', action='store_true', help='Process all ready cities')
    parser.add_argument('--county', help='Filter batch to one county')
    parser.add_argument('--dry-run', action='store_true', help='Preview without downloading')
    parser.add_argument('--include-fallback', action='store_true',
                        help='Include fallback cities in batch mode')

    args = parser.parse_args()
    registry = load_registry()

    if args.list:
        list_cities(registry, args.county)
        return

    if args.batch:
        statuses = ['ready', 'needs_verify']
        if args.include_fallback:
            statuses.append('fallback')

        cities = [
            name for name, cfg in registry['cities'].items()
            if cfg['status'] in statuses
            and (not args.county or cfg['county'].lower() == args.county.lower())
        ]

        print(f"\n[*] Batch processing {len(cities)} cities...")
        results = {}
        for city in sorted(cities):
            try:
                ok = run_city_pipeline(city, registry, dry_run=args.dry_run)
                results[city] = 'OK' if ok else 'FAILED'
            except Exception as e:
                print(f"  [!!] {city} crashed: {e}")
                results[city] = f'ERROR: {e}'

        print(f"\n{'='*60}")
        print(f"  BATCH RESULTS")
        print(f"{'='*60}")
        for city, status in sorted(results.items()):
            print(f"  {city:<20} {status}")
        return

    if args.city:
        run_city_pipeline(args.city, registry, dry_run=args.dry_run)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
