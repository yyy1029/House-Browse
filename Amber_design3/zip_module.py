# from __future__ import annotations
# import os
# import pandas as pd
# import numpy as np
# import pgeocode
# from dataprep import CSV_URL

# TABLE_NAME = "workspace.data511.house_ts"
# LOCAL_TESTING = True


# def load_city_zip_data(city_abbr: str, *, csv_path: str = CSV_URL) -> pd.DataFrame:
#     """
#     Load the full CSV and filter rows to a single city.

#     Ensures:
#     - a zip code string column: zip_code_str
#     - keeps sale price and income columns if present
#     - adds a 'year' column if only 'date' exists
#     """
#     df_full = pd.read_csv(csv_path)

#     # Standardize some column names if needed
#     rename_map = {
#         "zipcode": "zip_code",
#         "Per Capita Income": "per_capita_income",
#         "per_capita_income": "per_capita_income",
#         "Median Sale Price": "median_sale_price",
#         "median_sale_price": "median_sale_price",
#     }
#     for old, new in rename_map.items():
#         if old in df_full.columns:
#             df_full = df_full.rename(columns={old: new})

#     # Ensure zip_code_str exists
#     if "zip_code" in df_full.columns:
#         df_full["zip_code_str"] = df_full["zip_code"].astype(str).str.zfill(5)
#     elif "zipcode" in df_full.columns:
#         df_full["zip_code_str"] = df_full["zipcode"].astype(str).str.zfill(5)

#     # Filter to a single city if city column exists
#     if "city" in df_full.columns:
#         df = df_full[df_full["city"] == city_abbr].copy()
#     else:
#         df = df_full.copy()

#     # Ensure 'year' column exists if only 'date' is present
#     if "year" not in df.columns and "date" in df.columns:
#         try:
#             df["date"] = pd.to_datetime(df["date"])
#             df["year"] = df["date"].dt.year
#         except Exception:
#             pass

#     return df


# def get_zip_coordinates(df_zip: pd.DataFrame) -> pd.DataFrame:
#     """
#     Enrich ZIP-level data with latitude/longitude and compute
#     price_to_income_ratio = median_sale_price / per_capita_income.
#     """
#     if df_zip is None or df_zip.empty:
#         return df_zip.copy()

#     out = df_zip.copy()

#     # Ensure a zip_code_str column
#     if "zip_code_str" not in out.columns:
#         if "zip_code" in out.columns:
#             out["zip_code_str"] = out["zip_code"].astype(str).str.zfill(5)
#         elif "zipcode" in out.columns:
#             out["zip_code_str"] = out["zipcode"].astype(str).str.zfill(5)
#         else:
#             raise KeyError("Missing zip_code / zipcode / zip_code_str column.")

#     # Standardize sale price & income columns
#     if "median_sale_price" not in out.columns and "Median Sale Price" in out.columns:
#         out = out.rename(columns={"Median Sale Price": "median_sale_price"})
#     if "per_capita_income" not in out.columns and "Per Capita Income" in out.columns:
#         out = out.rename(columns={"Per Capita Income": "per_capita_income"})

#     # Lat/lon via pgeocode
#     nomi = pgeocode.Nominatim("us")
#     geo = nomi.query_postal_code(out["zip_code_str"].tolist())

#     out["lat"] = geo["latitude"].values
#     out["lon"] = geo["longitude"].values

#     # Drop rows with missing coordinates
#     out = out.dropna(subset=["lat", "lon"]).copy()

#     # Integer ZIP code
#     out["zip_code_int"] = out["zip_code_str"].astype(int)

#     # Compute price-to-income ratio at ZIP level
#     if "median_sale_price" not in out.columns or "per_capita_income" not in out.columns:
#         # If columns are missing, we just return coordinates without ratios
#         return out

#     denom = out["per_capita_income"].replace(0, np.nan)
#     out["price_to_income_ratio"] = out["median_sale_price"] / denom

#     # Normalized ratio (0–1) for optional color scaling
#     MAX_RATIO_FOR_NORM = 15.0
#     out["price_to_income_norm"] = (
#         np.clip(out["price_to_income_ratio"], 0, MAX_RATIO_FOR_NORM) / MAX_RATIO_FOR_NORM
#     )

#     return out


# __all__ = ["LOCAL_TESTING", "TABLE_NAME", "load_city_zip_data", "get_zip_coordinates"]
# Updated code to add back zip code filtering when adjusting income slider

import streamlit as st
import pandas as pd
import numpy as np
import os
import json
import pgeocode
from dataprep import RATIO_COL, RATIO_COL_ZIP, AFFORDABILITY_CATEGORIES 


# Helper function (copied from dataprep.py)
def classify_affordability_zip(ratio: float) -> str:
    """Classifies a price-to-income ratio using imported constants."""
    if pd.isna(ratio): return "N/A"
    
    sorted_categories = sorted(AFFORDABILITY_CATEGORIES.items(), 
                               key=lambda item: item[1][1] if item[1][1] is not None else float('inf'))

    for category, (lower, upper) in sorted_categories:
        if category == "Affordable":
            if ratio <= upper: return category
        elif lower is not None and upper is not None:
            if lower < ratio <= upper: return category
        elif lower is not None and upper is not None:
            if lower < ratio <= upper: return category
            
    return "Uncategorized"


@st.cache_data(ttl=3600)
def load_city_zip_data(city_geojson_code: str, df_full: pd.DataFrame, max_pci: float) -> pd.DataFrame:
    # ------------------------------------------------------------------------
    # NOTE: max_pci argument kept for compatibility but no longer used for filtering
    # All zip codes are now shown regardless of income
    # ------------------------------------------------------------------------
    """
    Filters the pre-loaded full DataFrame (df_full) to a single city 
    using the GeoJSON code (e.g., ATL). All ZIP codes are included.
    """
    # 1. Filter by City (GeoJSON Code) only - no income filtering
    df_city_zip = df_full[df_full["city_geojson_code"] == city_geojson_code].copy()


    # Ensure the required columns exist for subsequent steps
    required_cols = ["zipcode", "year", "median_sale_price", "per_capita_income", "city_full"]
    for col in required_cols:
        if col not in df_city_zip.columns:
            return pd.DataFrame() 

    # Ensure zip code columns exist
    df_city_zip["zip_code_int"] = df_city_zip["zipcode"].astype(str).str.zfill(5)
    df_city_zip["zip_code_str"] = df_city_zip["zipcode"].astype(str).str.zfill(5)

    return df_city_zip


@st.cache_data(ttl=3600*24)
def get_zip_coordinates(df_zip_data: pd.DataFrame) -> pd.DataFrame:
    """
    Enriches ZIP-level data with coordinates and unconditionally calculates the ratio AND rating.
    """
    if df_zip_data.empty:
        return pd.DataFrame()

    out = df_zip_data.copy()
    
    # Use pgeocode for coordinates
    nomi = pgeocode.Nominatim("us")
    
    # Extract list of zip codes
    zip_list = out["zip_code_str"].tolist()
    
    # Query pgeocode for all ZIPs
    geo_df = nomi.query_postal_code(zip_list)
    
    # Add lat/lon back to DataFrame
    out["lat"] = geo_df["latitude"].values
    out["lon"] = geo_df["longitude"].values

    out = out.dropna(subset=["lat", "lon"]).copy()

    # Calculate ratio using standardized lowercase columns
    price_col = "median_sale_price"
    income_col = "per_capita_income"
    denom = out[income_col].replace(0, np.nan)
    
    out[RATIO_COL] = out[price_col] / denom # Generates 'price_to_income_ratio'
    out["affordability_rating"] = out[RATIO_COL].apply(classify_affordability_zip) # Generates rating
    
    # Ensure zip_code_int exists for Plotly location lookup
    out["zip_code_int"] = out["zip_code_str"].astype(int)
    
    return out
