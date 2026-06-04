import csv
import os
import sys
import re
import pandas as pd
import math
import json

# --- Configuration & Matrix ---
SANTA_CLARA_MAX_DENSITY_MATRIX = {
    "VLDR": 10.0,
    "LDRE": 19.0,
    "MDRE": 36.0,
    "HDRE": 50.0,
    "NHMX": 36.0
}

def parse_query_intent(query):
    """
    Sprint 10.0: Messy Intent-Based Parser.
    Decouples operators from metrics and handles partial matches gracefully.
    Mapping to simplified JSON schema: {"city": str, "metric": {"operator": str, "value": float}}
    """
    q = query.lower()
    
    # Initialize with 'Any' for all fields to support Partial Matching
    intent = {
        "city": None,
        "acreage": {"operator": "any", "value": None},
        "density": {"operator": "any", "value": None},
        "units": {"operator": "any", "value": None},
        "tier": "both"
    }

    # 1. City Ingestion (Messy/Typo-Tolerant Patterns)
    if any(x in q for x in ["santa clara", "sc", "santaclara", "clara"]): intent["city"] = "Santa_Clara"
    elif any(x in q for x in ["san jose", "sj", "sanjose"]): intent["city"] = "San_Jose"
    elif "fremont" in q: intent["city"] = "Fremont"
    elif "sunnyvale" in q: intent["city"] = "Sunnyvale"

    # 2. Operator Identification Logic
    def get_operator(phrase):
        if any(x in phrase for x in ["more than", "over", ">", "larger", "greater", "min", "at least"]): return ">"
        if any(x in phrase for x in ["less than", "under", "<", "smaller", "max", "at most", "maximum"]): return "<"
        if any(x in phrase for x in ["exactly", "is", "=", "zoned as"]): return "=="
        return ">" # Default intent for standalone numbers

    # 3. Parameter Block Extraction (Acreage vs Density vs Units)
    # Pattern: [Operator (Optional)] + [Value] + [Unit/Context]
    
    # ACREAGE EXTRACTION (3ac, 3 acres, over 3, etc.)
    ac_match = re.search(r'(?P<pre>.*?)(\d+\.?\d*)\s*(?P<unit>acres|acre|ac)', q)
    if ac_match:
        val = float(ac_match.group(2))
        intent["acreage"]["value"] = val
        intent["acreage"]["operator"] = get_operator(ac_match.group('pre'))

    # DENSITY EXTRACTION (30 density, max 30, du/ac, etc.)
    den_match = re.search(r'(?P<pre>.*?)(?P<val>\d+\.?\d*)\s*(?P<unit>du/ac|units/acre|units per acre|density)', q)
    # Alternative: check if "density" or "max density" is at the start of the clause
    if not den_match:
        den_match = re.search(r'(?:density|units/acre)\s*(?P<pre>.*?)(?P<val>\d+\.?\d*)', q)
        
    if den_match:
        val = float(den_match.group('val'))
        # If this value is already taken by acreage, keep searching
        if val != intent["acreage"]["value"]:
            intent["density"]["value"] = val
            intent["density"]["operator"] = get_operator(den_match.group('pre'))

    # UNITS EXTRACTION
    unit_match = re.search(r'(?P<pre>.*?)(?P<val>\d+)\s*(?P<unit>units|homes|apartments|doors)', q)
    if unit_match:
        val = int(unit_match.group('val'))
        if val not in [intent["acreage"]["value"], intent["density"]["value"]]:
            intent["units"]["value"] = val
            intent["units"]["operator"] = get_operator(unit_match.group('pre'))

    return intent

def load_and_filter_waterfall(intent):
    """
    Standard waterfall search adapted for intent-based operators.
    """
    city = intent["city"]
    if not city: return pd.DataFrame(), pd.DataFrame(), {"error": "City missing"}

    # Build Params for legacy loaders
    p = {
        "acreage_min": intent["acreage"]["value"] if intent["acreage"]["operator"] == ">" else 0.0,
        "acreage_max": intent["acreage"]["value"] if intent["acreage"]["operator"] == "<" else 9999.0,
        "density_min": intent["density"]["value"] if intent["density"]["operator"] == ">" else 0.0,
        "density_max": intent["density"]["value"] if intent["density"]["operator"] == "<" else 9999.0,
        "unit_min": intent["units"]["value"] if intent["units"]["operator"] == ">" else 0,
        "unit_max": intent["units"]["value"] if intent["units"]["operator"] == "<" else 999999,
        "tier_pref": "both", "zoning_filter": [], "exclude_zoning": []
    }
    
    # Range handling for exact matches
    if intent["density"]["operator"] == "==":
        p["density_min"] = intent["density"]["value"]
        p["density_max"] = intent["density"]["value"]
    
    # Import legacy loaders
    from investor_interface import load_and_filter_tier1, load_and_filter_tier2
    
    t1 = load_and_filter_tier1(city, p)
    t1_apns = t1['APN'].tolist() if not t1.empty else []
    t2 = load_and_filter_tier2(city, p, t1_apns)
    
    return t1, t2, p

if __name__ == "__main__":
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        intent_data = parse_query_intent(query)
        print(json.dumps(intent_data, indent=2))
