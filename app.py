import streamlit as st
import pandas as pd
import os
import sys
import re
import csv

# ---------- Password Gate ----------
def check_password():
    """Simple password wall. Set your password in Streamlit Secrets or fallback to hardcoded."""
    correct_password = st.secrets.get("password", "parceliq2026")

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.markdown("### ParcelIQ Access")
    pwd = st.text_input("Enter password to continue:", type="password")
    if pwd:
        if pwd == correct_password:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False

if not check_password():
    st.stop()
# -----------------------------------

# Centralized Master Data Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MASTER_HEI_PATH = os.path.join(BASE_DIR, "data", "master_hei_normalized.csv")
MASTER_GIS_PATH = os.path.join(BASE_DIR, "data", "master_gis_normalized.csv")

# Page Configuration
st.set_page_config(
    page_title="ParcelIQ Investor Portal",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Typography & Branding (The 'I' Issue) + Card Styling
# Note: Strict 'No Emoji' policy preserved.
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Serif:wght@600&family=Inter:wght@400;600&display=swap');

    /* Global Dark Theme Refinement */
    .stApp {
        background-color: #0F172A;
        color: #F8FAFC;
        font-family: 'Inter', sans-serif;
    }

    /* Branding: Strong Serifs for the 'I' */
    .main-title {
        font-family: 'IBM Plex Serif', serif !important;
        font-size: 2.5rem !important;
        font-weight: 700 !important;
        color: #F8FAFC !important;
        margin-bottom: 0.1rem !important;
        letter-spacing: -0.01em !important;
    }

    .sub-header {
        font-family: 'Inter', sans-serif;
        color: #64748B;
        font-size: 1rem;
        margin-bottom: 2rem;
        font-weight: 400;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    /* KPI Cards & Accent Color (Steel Blue / White) */
    div[data-testid="stMetric"] {
        background-color: #1E293B;
        border: 1px solid #334155;
        padding: 15px 20px;
        border-radius: 4px;
    }

    div[data-testid="stMetricLabel"] > div {
        color: #94A3B8 !important;
        font-size: 0.75rem !important;
        text-transform: uppercase;
        letter-spacing: 0.1em;
    }

    div[data-testid="stMetricValue"] > div {
        color: #F8FAFC !important; /* Crisp White */
        font-weight: 500 !important;
    }

    /* Search Bar Polish */
    .stTextInput input {
        background-color: #0F172A !important;
        border: 1px solid #334155 !important;
        color: #F8FAFC !important;
        border-radius: 4px !important;
        padding: 10px 15px !important;
    }
    
    .stTextInput input:focus {
        border-color: #64748B !important;
        box-shadow: none !important;
    }

    /* Button Polish (Muted Slate) */
    div.stButton > button {
        background-color: #334155;
        color: #FFFFFF;
        font-weight: 500;
        border-radius: 4px;
        border: 1px solid #475569;
        padding: 0.5rem 2rem;
        width: auto;
        white-space: nowrap;
    }

    div.stButton > button:hover {
        background-color: #475569;
        color: #FFFFFF;
        border-color: #64748B;
    }

    /* Tabs Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
        background-color: transparent;
    }

    .stTabs [data-baseweb="tab"] {
        height: 40px;
        background-color: transparent;
        border: none;
        color: #64748B;
        font-weight: 500;
    }

    .stTabs [aria-selected="true"] {
        color: #F8FAFC !important;
        border-bottom-color: #F8FAFC !important;
    }
    </style>
    """, unsafe_allow_html=True)

# Typography & Branding Fix
st.markdown('<h1 class="main-title">ParcelIQ: Real Estate Search Engine</h1>', unsafe_allow_html=True)

# Minimalist Subheader
st.markdown('<p class="sub-header">Acquisition & Zoning Intelligence</p>', unsafe_allow_html=True)

# Search Input
query = st.text_input(
    label="Investment Criteria", 
    placeholder="Try: 'Cupertino sites between 3 and 10 acres' or 'city of Eureka density over 10'",
    label_visibility="collapsed"
)

def _normalize_query(q):
    """Pre-process query text: fix typos, standardize units, collapse noise."""
    # Fix common typos (fuzzy tolerance for key words)
    q = re.sub(r'b\w*twe+n', 'between', q)          # betweeen, beetween, btween
    q = re.sub(r'\bacera?ge\b', 'acreage', q)        # acerage, acerge
    q = re.sub(r'\bacreage\b', 'acres', q)            # acreage → acres
    q = re.sub(r'\bacre\b', 'acres', q)               # acre → acres
    q = re.sub(r'\b(\d+(?:\.\d+)?)\s*ac\b', r'\1 acres', q)  # "5 ac" → "5 acres"
    q = re.sub(r'\bsf\b', 'sqft', q)
    q = re.sub(r'\bdu/ac(?:re)?\b', 'duac', q)        # normalize density unit
    q = re.sub(r'\bunits?\s*/?\s*acres?\b', 'duac', q)
    # Collapse repeated conjunctions: "and and", "to to"
    q = re.sub(r'\b(and|to|or)\s+\1\b', r'\1', q)
    # Collapse multiple spaces
    q = re.sub(r'\s+', ' ', q).strip()
    return q


def _has_acreage_context(q):
    """Return True if the query mentions acreage/size in any recognizable way."""
    return bool(re.search(
        r'acres?|acreage|\bac\b|lot\s*size|parcel\s*size|site\s*size|land\s*size|'
        r'(?:big|small|large|tiny|huge)\s+(?:lot|parcel|site|propert)',
        q
    ))


def _parse_acreage(q):
    """
    Robust acreage parser — handles dozens of natural-language phrasings.
    Returns dict with keys: min, max, type (range|min|max|both|None).
    """
    NUM = r'(\d+(?:\.\d+)?)'   # reusable number capture
    SEP = r'\s*(?:to|and|through|thru|-|–|—)\s*'  # range separators
    UNIT = r'(?:\s*acres?)?'   # optional trailing unit
    UNIT_REQ = r'\s*acres?'    # required trailing unit

    result = {"min": None, "max": None, "type": None}

    # ── RANGE PATTERNS (most specific first) ──
    range_patterns = [
        # "between 3 acres and 10 acres" / "between 3 and 10 acres"
        rf'between\s+{NUM}{UNIT}{SEP}{NUM}{UNIT}',
        # "from 3 acres to 10 acres" / "from 3 to 10 acres"
        rf'from\s+{NUM}{UNIT}{SEP}{NUM}{UNIT}',
        # "acres from/between 3 to 10"
        rf'acres?\s*(?:from|between|ranging|of)\s*{NUM}{SEP}{NUM}',
        # "3 acres to 10 acres" / "3 to 10 acres" / "3-10 acres"
        rf'{NUM}\s*acres?{SEP}{NUM}{UNIT}',
        # "3 to 10 acre" (no trailing s)
        rf'{NUM}{SEP}{NUM}\s*acres?',
        # "lot size 3 to 10" / "size between 3 and 10 acres"
        rf'(?:lot\s*|parcel\s*|site\s*|land\s*)?size\s*(?:from|between|of|ranging)?\s*{NUM}{SEP}{NUM}{UNIT}',
        # "size: 3-10 acres"
        rf'size\s*:?\s*{NUM}{SEP}{NUM}{UNIT}',
    ]

    for pat in range_patterns:
        m = re.search(pat, q)
        if m:
            lo, hi = float(m.group(1)), float(m.group(2))
            result["min"], result["max"] = min(lo, hi), max(lo, hi)
            result["type"] = "range"
            return result

    # ── MAXIMUM PATTERNS (checked FIRST so "no more than" isn't stolen by min) ──
    max_patterns = [
        # "no more than / not more than / no larger than" — must be checked before min
        rf'(?<!\w)(?:no|not)\s+(?:more|larger|bigger|greater)\s+than\s*{NUM}{UNIT}',
        # "under/below/less than/at most/maximum/max/smaller than/up to 10 acres"
        rf'(?:<|<=|under|below|less\s+than|at\s+most|maximum|max|smaller\s+than|up\s+to)\s*{NUM}{UNIT}',
        # "10 acres or less" / "10 acres or smaller" / "10 acres max"
        rf'{NUM}{UNIT_REQ}\s+(?:or\s+(?:less|smaller|fewer|under|below)|maximum|max)',
        # "acres under/below 10"
        rf'acres?\s+(?:under|below|less\s+than|at\s+most|<=?)\s*{NUM}',
        # "lots/sites/parcels smaller than 10 acres"
        rf'(?:lot|parcel|site|propert\w+|land)s?\s+(?:smaller|less|under|below)\s+(?:than\s+)?{NUM}{UNIT}',
    ]

    for pat in max_patterns:
        m = re.search(pat, q)
        if m and _has_acreage_context(q):
            result["max"] = float(m.group(1))
            result["type"] = "max"
            break

    # ── MINIMUM PATTERNS ──
    min_patterns = [
        # "over/above/more than/at least/minimum/min/larger than/bigger than 5 acres"
        rf'(?:>|>=|over|above|more\s+than|at\s+least|minimum|min|larger\s+than|bigger\s+than|'
        rf'no\s+(?:less|smaller|fewer)\s+than|exceeding|starting\s+(?:at|from))\s*{NUM}{UNIT}',
        # "5+ acres" / "5 acres or more" / "5 acres or larger" / "5 acres minimum"
        rf'{NUM}\s*\+{UNIT}',
        rf'{NUM}{UNIT_REQ}\s+(?:or\s+(?:more|larger|bigger|greater|above)|minimum|min|\+)',
        # "acres over/above 5"
        rf'acres?\s+(?:over|above|more\s+than|at\s+least|exceeding|>=?)\s*{NUM}',
        # "lots/sites/parcels bigger than 5 acres"
        rf'(?:lot|parcel|site|propert\w+|land)s?\s+(?:bigger|larger|greater|over|above|exceeding)\s+(?:than\s+)?{NUM}{UNIT}',
    ]

    for pat in min_patterns:
        m = re.search(pat, q)
        if m and _has_acreage_context(q):
            # Guard: skip if this match is actually part of "no/not more than"
            start = m.start()
            prefix = q[max(0, start - 6):start].strip()
            if re.search(r'\b(?:no|not)$', prefix):
                continue
            result["min"] = float(m.group(1))
            if result["type"] == "max":
                result["type"] = "both"
            else:
                result["type"] = "min"
            break

    return result


def _parse_density(q):
    """Robust density parser — handles natural-language density queries."""
    target_density = {"min": None, "max": None, "target": None, "type": None}

    # Normalize density-related terms
    dq = re.sub(r'\bdu(?:\/|\s+per\s+)acres?\b', 'density', q)
    dq = re.sub(r'\bunits?\s*(?:/|per)\s*acres?\b', 'density', dq)
    dq = re.sub(r'\bduac\b', 'density', dq)
    dq = re.sub(r'\bdwelling\s+units?\s*(?:/|per)\s*acres?\b', 'density', dq)

    # Range: density between 0 and 30 / density from 10 to 50
    range_match = re.search(r'density\s*(?:between|from|of|ranging)?\s*(\d+(?:\.\d+)?)\s*(?:to|and|through|-|–)\s*(\d+(?:\.\d+)?)', dq)
    if not range_match:
        range_match = re.search(r'between\s+(\d+(?:\.\d+)?)\s*(?:to|and|-)\s*(\d+(?:\.\d+)?)\s*(?:density|du|units?\s*/?\s*ac)', dq)
    if range_match:
        target_density["min"] = float(range_match.group(1))
        target_density["max"] = float(range_match.group(2))
        target_density["type"] = "range"
    else:
        # Minimum only: density over 30
        min_match = re.search(r'density\s*(?:>|>=|over|above|more\s+than|min|minimum|at\s+least|exceeding|starting)\s*(\d+(?:\.\d+)?)', dq)
        if not min_match:
            min_match = re.search(r'(?:>|>=|over|above|more\s+than|at\s+least|minimum|min)\s*(\d+(?:\.\d+)?)\s*(?:density|du|units?\s*/?\s*ac)', dq)
        if min_match:
            target_density["min"] = float(min_match.group(1))
            target_density["type"] = "min"

        # Maximum only: density under 30
        max_match = re.search(r'density\s*(?:<|<=|under|below|less\s+than|max|maximum|up\s+to|at\s+most)\s*(\d+(?:\.\d+)?)', dq)
        if not max_match:
            max_match = re.search(r'(?:<|<=|under|below|less\s+than|at\s+most|maximum|max)\s*(\d+(?:\.\d+)?)\s*(?:density|du|units?\s*/?\s*ac)', dq)
        if max_match:
            target_density["max"] = float(max_match.group(1))
            target_density["type"] = "max" if not target_density["type"] else "both"

        # Exact Target Density (Final Fallback)
        if not target_density["type"]:
            target_match = re.search(r'density\s*(?:of|is|at|around|for|:)?\s*(\d+(?:\.\d+)?)', dq)
            if target_match:
                target_density["target"] = float(target_match.group(1))
                target_density["type"] = "target"

    return target_density


def parse_query_simple(query_text, cities_in_db):
    q_raw = query_text.lower().strip()
    q = _normalize_query(q_raw)

    # 1. Location Parsing (Regex Word Boundary Matching)
    # Handle "city of X" prefix: extract city name after "city of"
    sorted_cities = sorted(cities_in_db, key=len, reverse=True)

    target_city = None
    # First try "city of X" explicit pattern
    city_of_match = re.search(r'city\s+of\s+(\w[\w\s]*?)(?:\s+(?:sites?|lots?|parcels?|properties|between|with|over|under|above|below|density|acres?|zoning|that|where|\d)|\s*$)', q)
    if city_of_match:
        candidate = city_of_match.group(1).strip().title()
        for city in sorted_cities:
            if city.lower() == candidate.lower():
                target_city = city
                break

    # Fallback: longest-match word boundary search
    if not target_city:
        for city in sorted_cities:
            pattern = rf"\b{re.escape(city)}\b"
            if re.search(pattern, query_text, re.IGNORECASE):
                target_city = city
                break

    # 2. Density Parsing
    target_density = _parse_density(q)

    # 3. Acreage Parsing
    target_acreage = _parse_acreage(q)

    return target_city, target_acreage, target_density

@st.cache_data(ttl=60)
def load_csv_data(file_path):
    if not os.path.exists(file_path):
        return pd.DataFrame()
    
    try:
        df = pd.read_csv(file_path, encoding='utf-8-sig')
        if 'city' in df.columns:
            df = df[~df['city'].str.lower().str.contains('county', na=False)]
            df = df[df['city'].notna() & (df['city'] != '')]
            df['city'] = df['city'].str.strip()
        return df
    except Exception as e:
        st.error(f"Data load failure ({os.path.basename(file_path)}): {str(e)}")
        return pd.DataFrame()

# Load as DataFrames
master_hei_df = load_csv_data(MASTER_HEI_PATH)
master_gis_df = load_csv_data(MASTER_GIS_PATH)

# Unique City List for UI and Parsing
# Only show cities that have BOTH Tier 1 (HEI) and Tier 2 (GIS) data fully integrated
hei_cities = set(master_hei_df['city'].dropna().str.strip().str.title().unique()) if not master_hei_df.empty else set()
gis_cities = set(master_gis_df['city'].dropna().str.strip().str.title().unique()) if not master_gis_df.empty else set()
fully_integrated = sorted(hei_cities & gis_cities)
# For query parsing, use all cities (so searches still work); for display, only fully integrated
all_cities = pd.concat([master_hei_df['city'], master_gis_df['city']]).unique()
cities_in_db = sorted([str(c).title().strip() for c in all_cities if pd.notna(c)])
unique_cities_display = fully_integrated

with st.expander("Available City Inventories"):
    st.write(", ".join(unique_cities_display))

col_btn, _ = st.columns([1, 4])
with col_btn:
    run_btn = st.button("Run Analysis")

if run_btn:
    if not query:
        st.warning("Please enter criteria.")
    elif master_hei_df.empty and master_gis_df.empty:
        st.error("No master databases found. Please run normalization.")
    else:
        with st.spinner("Analyzing Centralized Inventories..."):
            try:
                # 1. Progressive Parsing
                target_city, target_acreage, target_density = parse_query_simple(query, cities_in_db)
                
                # 2. Section Header & Metrics
                st.markdown("### Active Search Parameters")
                m1, m2, m3 = st.columns(3)
                m1.metric("Location", target_city.title() if target_city else "Regional Search")
                acre_label = "Any"
                if target_acreage["type"] == "range": acre_label = f"{target_acreage['min']} - {target_acreage['max']} ac"
                elif target_acreage["type"] == "min": acre_label = f"> {target_acreage['min']} ac"
                elif target_acreage["type"] == "max": acre_label = f"< {target_acreage['max']} ac"
                elif target_acreage["type"] == "both": acre_label = f"{target_acreage['min']} - {target_acreage['max']} ac"
                m2.metric("Size Requirement", acre_label)
                den_label = "Any"
                if target_density["type"] == "range": den_label = f"{target_density['min']} - {target_density['max']} DU/ac"
                elif target_density["type"] == "min": den_label = f"> {target_density['min']} DU/ac"
                elif target_density["type"] == "max": den_label = f"< {target_density['max']} DU/ac"
                elif target_density["type"] == "both": den_label = f"{target_density['min']} < D < {target_density['max']}"
                elif target_density["type"] == "target": den_label = f"Target: {target_density['target']} DU/ac"
                m3.metric("Density Target", den_label)
                st.divider()

                # 3. Vectorized Filtering Logic (Pandas)
                def filter_inventory(df):
                    if df.empty: return df
                    mask = pd.Series([True] * len(df), index=df.index)
                    if target_city: mask &= (df['city'].str.lower() == target_city.lower())
                    if target_acreage["type"] is not None:
                        acres = pd.to_numeric(df['total_acreage'], errors='coerce').fillna(0)
                        a = target_acreage
                        if a["type"] in ["range", "both"]: mask &= (acres >= a["min"]) & (acres <= a["max"])
                        elif a["type"] == "min": mask &= (acres >= a["min"])
                        elif a["type"] == "max": mask &= (acres <= a["max"])
                    if target_density["type"] is not None:
                        max_den = pd.to_numeric(df['max_density'], errors='coerce').fillna(0)
                        d = target_density
                        if d["type"] in ["range", "both"]: mask &= (max_den >= d["min"]) & (max_den <= d["max"])
                        elif d["type"] == "min": mask &= (max_den >= d["min"])
                        elif d["type"] == "max": mask &= (max_den <= d["max"])
                        elif d["type"] == "target":
                            min_den = pd.to_numeric(df['min_density'], errors='coerce').fillna(0)
                            target = d["target"]
                            mask &= (min_den <= target) & ((max_den >= target) | (max_den == 0))
                    return df[mask]

                hei_filtered = filter_inventory(master_hei_df)
                gis_filtered = filter_inventory(master_gis_df)

                # 4. Preparation and Clean Display
                tab1, tab2 = st.tabs(["Housing Element Inventory", "General Plan Inventory"])

                def prepare_display_df(df):
                    cols = ['city', 'site_address', 'parcel_id', 'total_acreage', 'zoning_code', 'gp_designation', 'min_density', 'max_density']
                    df_out = df[[c for c in cols if c in df.columns]].copy()
                    
                    # CLEANING: Map common empty-field placeholders to real empty strings
                    # This ensures the Streamlit table doesn't render gray "None" or "N/A"
                    empty_placeholders = {'N/A', 'NONE', 'UNASSIGNED', 'NAN', '0', '0.0', '', ' ', 'NULL'}
                    
                    # Apply cleaning cell-by-cell - force anything in placeholders to true empty string
                    df_out = df_out.apply(lambda col: col.map(lambda x: '' if str(x).strip().upper() in empty_placeholders else str(x).strip()))
                    
                    # Dynamic Hiding: Drop columns if they are empty for the current result set
                    if 'site_address' in df_out.columns and (df_out['site_address'] == '').all():
                        df_out = df_out.drop(columns=['site_address'])
                    if 'gp_designation' in df_out.columns and (df_out['gp_designation'] == '').all():
                        df_out = df_out.drop(columns=['gp_designation'])
                    if 'zoning_code' in df_out.columns and (df_out['zoning_code'] == '').all():
                        df_out = df_out.drop(columns=['zoning_code'])

                    # FINAL CLEANUP: Set to truly empty to ensure Streamlit hides them
                    df_out = df_out.astype(str).replace(['None', 'nan', 'NAN', 'N/A', 'N/A', '0.0', '0', 'Unassigned', 'UNASSIGNED', 'none', 'None', 'NONE', 'gray none', 'gray unassigned'], '')
                    # Final check for San Jose/Milpitas empty Address/GP
                    if 'site_address' in df_out.columns and df_out['site_address'].astype(str).str.upper().str.strip().isin(['', 'NONE', 'UNASSIGNED', 'NAN', 'N/A']).all():
                        df_out = df_out.drop(columns=['site_address'])
                    if 'gp_designation' in df_out.columns and df_out['gp_designation'].astype(str).str.upper().str.strip().isin(['', 'NONE', 'UNASSIGNED', 'NAN', 'N/A']).all():
                        df_out = df_out.drop(columns=['gp_designation'])

                    # Formatting survived numeric columns
                    for col in ['total_acreage', 'min_density', 'max_density']:
                        if col in df_out.columns:
                            # Re-convert to numeric for proper display formatting after string replacement
                            df_out[col] = pd.to_numeric(df_out[col], errors='coerce').fillna(0)
                            if col in ['min_density', 'max_density']:
                                df_out[col] = df_out[col].astype(int)
                            else:
                                df_out[col] = df_out[col].astype(float).round(2)
                    
                    return df_out

                # Column Config
                column_configuration = {
                    "city": st.column_config.TextColumn("City", width="small"),
                    "site_address": st.column_config.TextColumn("Address", width="large"),
                    "parcel_id": st.column_config.TextColumn("APN", width="medium"),
                    "total_acreage": st.column_config.NumberColumn("Acres", format="%.2f", width="small"),
                    "zoning_code": st.column_config.TextColumn("Zoning Code", width="medium"),
                    "gp_designation": st.column_config.TextColumn("GP Designation", width="medium"),
                    "max_density": st.column_config.NumberColumn("Max Den", format="%d", width="small"),
                    "min_density": st.column_config.NumberColumn("Min Den", format="%d", width="small")
                }

                with tab1:
                    if not hei_filtered.empty:
                        st.dataframe(prepare_display_df(hei_filtered), use_container_width=True, hide_index=True, column_config=column_configuration)
                    else:
                        st.info("No matches found in Housing Element Inventory.")

                with tab2:
                    if not gis_filtered.empty:
                        st.dataframe(prepare_display_df(gis_filtered), use_container_width=True, hide_index=True, column_config=column_configuration)
                    else:
                        st.info("No matches found in General Plan Inventory.")
                            
            except Exception as e:
                st.error(f"Error: {str(e)}")

st.markdown("---")
st.caption("ParcelIQ v1.5.0 | Advanced NL Query Engine")
