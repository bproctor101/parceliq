import streamlit as st
import pandas as pd
import os
import sys
import re
import csv

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
    placeholder="Enter location and site parameters (e.g., 'Eureka, density over 10')",
    label_visibility="collapsed"
)

def parse_query_simple(query_text, cities_in_db):
    q = query_text.lower()
    
    # 1. Location Parsing (Regex Word Boundary Matching v1.3.7)
    # Longest Match First + Word Boundaries to prevent substring collisions
    sorted_cities = sorted(cities_in_db, key=len, reverse=True)
    
    target_city = None
    for city in sorted_cities:
        pattern = rf"\b{re.escape(city)}\b"
        if re.search(pattern, query_text, re.IGNORECASE):
            target_city = city
            break
    
    # 2. Density Parsing (Regex Capture Groups)
    target_density = {"min": None, "max": None, "target": None, "type": None}
    
    # Range: density between 0 and 30
    range_match = re.search(r'density.*?\b(\d+)\s*(?:to|and|-)\s*(\d+)\b', q)
    if range_match:
        target_density["min"] = float(range_match.group(1))
        target_density["max"] = float(range_match.group(2))
        target_density["type"] = "range"
    else:
        # Minimum only: density over 30
        min_match = re.search(r'density.*?(?:>|over|above|more than|min|minimum|at least)\s*(\d+)', q)
        if min_match:
            target_density["min"] = float(min_match.group(1))
            target_density["type"] = "min"
        
        # Maximum only: density under 30
        max_match = re.search(r'density.*?(?:<|under|below|less than|max|maximum|up to)\s*(\d+)', q)
        if max_match:
            target_density["max"] = float(max_match.group(1))
            target_density["type"] = "max" if not target_density["type"] else "both"
        
        # 4. Exact Target Density (Final Fallback)
        if not target_density["type"]:
            target_match = re.search(r'density\s*(?:of|is|at|around|for)?\s*(\d+(?:\.\d+)?)', q)
            if target_match:
                target_density["target"] = float(target_match.group(1))
                target_density["type"] = "target"

    # 3. Acreage Parsing (Expanded Regex)
    target_acreage = {"value": None, "type": "any"}
    
    # Minimum Acreage Pattern: more than, at least, larger than, min, etc.
    min_ac_match = re.search(r'(?:>|>=|over|above|more than|at least|minimum|min|larger than|bigger than)\s*(\d+(?:\.\d+)?)\s*acres?', q)
    if min_ac_match:
        target_acreage["value"] = float(min_ac_match.group(1))
        target_acreage["type"] = "min"
    else:
        # Maximum Acreage Pattern: under, below, less than, at most, max, etc.
        max_ac_match = re.search(r'(?:<|<=|under|below|less than|at most|maximum|max|smaller than)\s*(\d+(?:\.\d+)?)\s*acres?', q)
        if max_ac_match:
            target_acreage["value"] = float(max_ac_match.group(1))
            target_acreage["type"] = "max"
            
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
all_cities = pd.concat([master_hei_df['city'], master_gis_df['city']]).unique()
cities_in_db = sorted([str(c).title().strip() for c in all_cities if pd.notna(c)])
unique_cities_display = sorted(list(set(cities_in_db)))

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
                if target_acreage["type"] == "min": acre_label = f"> {target_acreage['value']} ac"
                elif target_acreage["type"] == "max": acre_label = f"< {target_acreage['value']} ac"
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
                    if target_acreage["value"] is not None:
                        acres = pd.to_numeric(df['total_acreage'], errors='coerce').fillna(0)
                        val = target_acreage["value"]
                        if target_acreage["type"] == "min": mask &= (acres >= val)
                        elif target_acreage["type"] == "max": mask &= (acres <= val)
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
st.caption("ParcelIQ v1.3.7 | Advanced NL Query Engine")
