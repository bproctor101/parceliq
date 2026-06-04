import csv
import os
import sys
import re
import pandas as pd
import math
import json
import numpy as np

# Step 1: Multi-City Zoning Reference Dictionary
CITY_ZONING_RULES = {
    "Santa_Clara": {
        "VLDR": {"min": 0, "max": 10, "label": "0 - 10 DU/ac"},
        "LDRE": {"min": 8, "max": 19, "label": "8 - 19 DU/ac"},
        "MDRE": {"min": 20, "max": 36, "label": "20 - 36 DU/ac"},
        "HDRE": {"min": 37, "max": 50, "label": "37 - 50 DU/ac"},
        "VHDRE": {"min": 51, "max": 100, "label": "51 - 100 DU/ac"},
        "CMX": {"min": 20, "max": 36, "label": "20 - 36 DU/ac"},
        "UCMX": {"min": 37, "max": 50, "label": "37 - 50 DU/ac"},
        "RMX": {"min": 37, "max": 50, "label": "37 - 50 DU/ac"},
        "NHMX": {"min": 10, "max": 25, "label": "10 - 25 DU/ac"},
        "COMMUNITY MIXED USE": {"min": 20, "max": 36, "label": "20 - 36 DU/ac"},
        "LOW DENSITY RESIDENTIAL": {"min": 8, "max": 19, "label": "8 - 19 DU/ac"},
        "MEDIUM DENSITY RESIDENTIAL": {"min": 20, "max": 36, "label": "20 - 36 DU/ac"},
        "HIGH DENSITY RESIDENTIAL": {"min": 37, "max": 50, "label": "37 - 50 DU/ac"},
        "DHRE": {"min": 37, "max": 50, "label": "37 - 50 DU/ac"},
        "VERY HIGH DENSITY RESIDENTIAL": {"min": 51, "max": 100, "label": "51 - 100 DU/ac"},
        "REGIONAL MIXED USE": {"min": 37, "max": 50, "label": "37 - 50 DU/ac"},
        "NEIGHBORHOOD MIXED USE": {"min": 10, "max": 25, "label": "10 - 25 DU/ac"},
    },
    "San_Jose": {}, 
    "Fremont": {},
    "Sunnyvale": {}
}

def preprocess_dataframe(df, city_name):
    df.columns = [c.upper() for c in df.columns]
    rules_dict = CITY_ZONING_RULES.get(city_name, {})
    
    gp_col = 'GP_DESIGNATION' if 'GP_DESIGNATION' in df.columns else 'GENERAL_PLAN'
    if gp_col not in df.columns and 'ZONING_CODE' in df.columns: gp_col = 'ZONING_CODE'
    ac_col = 'TOTAL_ACREAGE' if 'TOTAL_ACREAGE' in df.columns else 'ACRES'
    
    native_min_col = next((c for c in df.columns if 'MIN_DENSITY' in c), None)
    native_max_col = next((c for c in df.columns if 'MAX_DENSITY' in c), None)
    
    if gp_col in df.columns:
        df[gp_col] = df[gp_col].astype(str).str.upper().str.strip()
    if ac_col in df.columns:
        df[ac_col] = pd.to_numeric(df[ac_col], errors='coerce').fillna(0)

    if gp_col in df.columns and rules_dict:
        dict_min = df[gp_col].map(lambda x: rules_dict.get(x, {}).get('min', np.nan))
        dict_max = df[gp_col].map(lambda x: rules_dict.get(x, {}).get('max', np.nan))
    else:
        dict_min = pd.Series([np.nan] * len(df))
        dict_max = pd.Series([np.nan] * len(df))

    if native_min_col:
        df['FINAL_MIN_DENSITY'] = pd.to_numeric(df[native_min_col], errors='coerce').combine_first(dict_min)
    else:
        df['FINAL_MIN_DENSITY'] = dict_min.fillna(0)

    if native_max_col:
        df['FINAL_MAX_DENSITY'] = pd.to_numeric(df[native_max_col], errors='coerce').combine_first(dict_max)
    else:
        df['FINAL_MAX_DENSITY'] = dict_max.fillna(0)

    if city_name == "Santa_Clara" and gp_col in df.columns:
        nhmx_mask = (df[gp_col] == 'NHMX') | (df[gp_col] == 'NEIGHBORHOOD MIXED USE')
        df.loc[nhmx_mask & (df[ac_col] > 1.0) & (df['FINAL_MIN_DENSITY'] < 20), 'FINAL_MIN_DENSITY'] = 20.0
    
    df['ALLOWABLE_DENSITY_LABEL'] = (
        df['FINAL_MIN_DENSITY'].fillna(0).astype(int).astype(str) + 
        " - " + 
        df['FINAL_MAX_DENSITY'].fillna(0).astype(int).astype(str) + 
        " DU/ac"
    )
    df.loc[(df['FINAL_MIN_DENSITY'].isna() | (df['FINAL_MIN_DENSITY'] == 0)) & 
           (df['FINAL_MAX_DENSITY'].isna() | (df['FINAL_MAX_DENSITY'] == 0)), 'ALLOWABLE_DENSITY_LABEL'] = "N/A"

    return df

def parse_query_agentic(query):
    """
    Sprint 11.9: Hardened Regex-Based Intent Parser.
    Simulates the LLM Extraction Layer with strict Unit Agnosticism & Range Detection.
    """
    q = query.lower()
    
    intent = {
        "city": "Santa_Clara", 
        "acreage": {"value": None, "condition": "any"},
        "density": {
            "target_value": None, 
            "target_min": None, 
            "target_max": None, 
            "condition": "exact"
        },
        "tier_scope": "BOTH"
    }
    
    # City Extraction
    if "san jose" in q or "sj" in q: intent["city"] = "San_Jose"
    elif "fremont" in q: intent["city"] = "Fremont"
    elif "sunnyvale" in q: intent["city"] = "Sunnyvale"
    elif "santa clara" in q or "sc" in q: intent["city"] = "Santa_Clara"
    
    # Acreage Extraction
    ac_match = re.search(r'(\d+\.?\d*)\s*(?:acres|acre|ac)', q)
    if ac_match:
        intent["acreage"]["value"] = float(ac_match.group(1))
        intent["acreage"]["condition"] = "min" if not any(x in q for x in ["max", "under", "less"]) else "max"

    # UNIT AGNOSTICISM: Handle "density between X and Y"
    # Logic: Look for "density" or "units" followed by numbers
    range_match = re.search(r'(?:density|units|du/ac|allow|between)\s*(?:between|of)?\s*(\d+)\s*(?:-|to|and)\s*(\d+)', q)
    if range_match:
        intent["density"]["target_min"] = float(range_match.group(1))
        intent["density"]["target_max"] = float(range_match.group(2))
        intent["density"]["condition"] = "range"
    else:
        # Up to / Less than range (Maximum)
        max_match = re.search(r'(?:up to|less than|max|maximum|at most)\s*(\d+)', q)
        if max_match:
            intent["density"]["target_value"] = float(max_match.group(1))
            intent["density"]["condition"] = "maximum"
        else:
            # More than / At least (Minimum)
            min_match = re.search(r'(?:at least|more than|min|minimum|over)\s*(\d+)', q)
            if min_match:
                intent["density"]["target_value"] = float(min_match.group(1))
                intent["density"]["condition"] = "minimum"
            else:
                # Exact/Target matching (Unit Agnostic)
                den_match = re.search(r'(?:density|units|at|with)\s*(\d+)', q)
                if den_match:
                    intent["density"]["target_value"] = float(den_match.group(1))
                    intent["density"]["condition"] = "exact"
                else:
                    # Shorthand shorthand (e.g. "30 density")
                    short_match = re.search(r'(\d+)\s*(?:density|du/ac|units)', q)
                    if short_match:
                        intent["density"]["target_value"] = float(short_match.group(1))
                        intent["density"]["condition"] = "exact"
        
    return intent

def apply_vectorized_filters(df, intent):
    """
    Refined Search Filtering logic to handle the multi-key density schema.
    Explicitly casts JSON payload values to float for safety.
    """
    if df.empty: return df
    mask = pd.Series([True] * len(df), index=df.index)
    
    # Acreage Filter
    ac_col = 'TOTAL_ACREAGE' if 'TOTAL_ACREAGE' in df.columns else 'ACRES'
    if intent["acreage"]["value"] is not None:
        val = float(intent["acreage"]["value"])
        if intent["acreage"]["condition"] == "min": mask &= (df[ac_col] >= val)
        else: mask &= (df[ac_col] <= val)

    # Density Filter (Hardened Key Lookup)
    d_intent = intent["density"]
    cond = d_intent.get("condition", "any")
    
    # PRO-TECH FIX: Exclude "N/A" (non-residential) properties when a specific density filter is active
    density_requested = (cond == "range") or (d_intent.get("target_value") is not None)
    if density_requested:
        mask &= (df['ALLOWABLE_DENSITY_LABEL'] != "N/A")

    if cond == "range":
        # Safe float conversion
        t_min = float(d_intent.get("target_min", 0))
        t_max = float(d_intent.get("target_max", 999))
        mask &= (df['FINAL_MIN_DENSITY'] <= t_max) & (df['FINAL_MAX_DENSITY'] >= t_min)
    elif d_intent.get("target_value") is not None:
        target = float(d_intent["target_value"])
        if cond == "exact":
            mask &= (df['FINAL_MIN_DENSITY'] <= target) & (df['FINAL_MAX_DENSITY'] >= target)
        elif cond == "minimum":
            mask &= (df['FINAL_MAX_DENSITY'] >= target)
        elif cond == "maximum":
            mask &= (df['FINAL_MIN_DENSITY'] <= target)

    return df[mask].copy()

def load_and_filter_tier1(city_name, intent):
    workspace = os.getcwd()
    filename = f"{city_name}_HEI_Normalized.csv"
    path = os.path.join(workspace, "projects", "CRERAG", city_name, "data", filename)
    if not os.path.exists(path): return pd.DataFrame()
    df = pd.read_csv(path)
    df = preprocess_dataframe(df, city_name)
    filtered = apply_vectorized_filters(df, intent)
    res = pd.DataFrame()
    
    # Hide Address Column if unpopulated
    addr_vals = filtered.get('SITE_ADDRESS', filtered.get('ADDRESS', 'Unassigned'))
    if not addr_vals.astype(str).str.upper().str.strip().isin(['UNASSIGNED', 'NONE', 'N/A', '', 'NAN']).all():
        res['Address'] = addr_vals

    res['APN'] = filtered.get('PARCEL_ID', filtered.get('APN', 'N/A'))
    res['Total Acreage'] = filtered.get('TOTAL_ACREAGE', filtered.get('ACRES', 0)).astype(float).round(2)
    
    # Zoning/GP check
    zoning_vals = filtered.get('ZONING_CODE', filtered.get('GP_DESIGNATION', 'N/A'))
    if not zoning_vals.astype(str).str.upper().str.strip().isin(['N/A', 'NONE', '', 'NAN', 'UNASSIGNED']).all():
        res['Zoning Code'] = zoning_vals

    res['Allowable Density'] = filtered.get('ALLOWABLE_DENSITY_LABEL', 'N/A')
    res['Maximum Unit Potential'] = (res['Total Acreage'] * filtered['FINAL_MAX_DENSITY']).fillna(0).apply(math.floor)
    return res

def load_and_filter_tier2(city_name, intent, tier1_apns):
    workspace = os.getcwd()
    filename = f"{city_name}_GIS_Normalized.csv"
    path = os.path.join(workspace, "projects", "CRERAG", city_name, "data", filename)
    if not os.path.exists(path): return pd.DataFrame()
    df = pd.read_csv(path)
    df = preprocess_dataframe(df, city_name)
    apn_key = 'PARCEL_ID' if 'PARCEL_ID' in df.columns else 'APN'
    if apn_key in df.columns: df = df[~df[apn_key].isin(tier1_apns)]
    filtered = apply_vectorized_filters(df, intent)
    res = pd.DataFrame()
    
    # Hide Address Column in Tier 2 if requested
    # res['Address'] = "Unassigned"
    # Logic: Only add it if we actually have data (not true for most GIS)
    if 'SITE_ADDRESS' in filtered.columns and not filtered['SITE_ADDRESS'].isin(['Unassigned', 'N/A', '', None]).all():
        res['Address'] = filtered['SITE_ADDRESS']

    res['APN'] = filtered.get(apn_key, 'N/A')
    res['Total Acreage'] = filtered.get('TOTAL_ACREAGE', filtered.get('ACRES', 0)).astype(float).round(2)
    
    # Check GP Designation
    gp_vals = filtered.get('GP_DESIGNATION', pd.Series(['N/A']*len(filtered)))
    if not gp_vals.astype(str).str.upper().str.strip().isin(['N/A', 'NONE', '', 'NAN']).all():
        res['GP Designation'] = gp_vals
    
    res['Zoning Code'] = filtered.get('ZONING_CODE', 'N/A')
    res['Allowable Density'] = filtered.get('ALLOWABLE_DENSITY_LABEL', 'N/A')
    res['Maximum Unit Potential'] = (res['Total Acreage'] * filtered['FINAL_MAX_DENSITY']).fillna(0).apply(math.floor)
    return res

def process_query(user_text):
    intent = parse_query_agentic(user_text)
    t1 = load_and_filter_tier1(intent["city"], intent)
    t1_apns = t1['APN'].tolist() if not t1.empty else []
    t2 = load_and_filter_tier2(intent["city"], intent, t1_apns)
    return t1, t2, intent
