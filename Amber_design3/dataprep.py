# """
# Data loading and preparation helpers for Design 3 (house price-to-income dataset).
# """

# from typing import Optional

# import pandas as pd
# import numpy as np

# CSV_URL = "https://github.com/yyy1029/House-Browse/releases/download/v1.0/HouseTS.csv"

# # Shared with app.py
# RATIO_COL = "price_to_income_ratio"          # city-level price-to-income ratio
# RATIO_COL_ZIP = "price_to_income_ratio_zip"  # zip-level price-to-income ratio
# AFFORDABILITY_THRESHOLD = 5.0                # example threshold for affordability


# def load_data() -> pd.DataFrame:
#     """
#     Load HouseTS CSV and compute base fields.

#     Required columns in CSV:
#     - city
#     - year
#     - median_sale_price (or Median Sale Price)
#     - per_capita_income (or Per Capita Income)
#     """
#     df = pd.read_csv(CSV_URL)

#     if "date" in df.columns:
#         df["date"] = pd.to_datetime(df["date"])

#     if "city" not in df.columns:
#         raise KeyError("Input CSV must contain a 'city' column.")

#     df["city_clean"] = df["city"]

#     # Rename core columns if needed
#     rename_map = {}
#     if "median_sale_price" in df.columns:
#         rename_map["median_sale_price"] = "Median Sale Price"
#     if "per_capita_income" in df.columns:
#         rename_map["per_capita_income"] = "Per Capita Income"
#     df = df.rename(columns=rename_map)

#     if "Median Sale Price" not in df.columns or "Per Capita Income" not in df.columns:
#         raise KeyError(
#             "Input CSV must contain 'Median Sale Price' and 'Per Capita Income', "
#             "or columns that can be renamed to these."
#         )

#     df["monthly_income_pc"] = df["Per Capita Income"] / 12.0

#     return df


# def make_city_view_data(
#     df: pd.DataFrame,
#     annual_income: float,
#     year: Optional[int] = None,
#     budget_pct: float = 30.0,
# ) -> pd.DataFrame:
#     """
#     Aggregate data to city level for a given year.

#     Outputs one row per city with:
#     - Median Sale Price
#     - Per Capita Income
#     - price_to_income_ratio (Median Sale Price / Per Capita Income)
#     - affordable (ratio <= AFFORDABILITY_THRESHOLD)
#     - user-related fields (for UI display only)
#     """
#     if year is None:
#         year = int(df["year"].max())

#     # Only used for UI profile card (max rent), not for ratio computation
#     max_rent = annual_income * (budget_pct / 100.0) / 12.0

#     tmp = df[df["year"] == year].copy()

#     agg_dict = {
#         "Median Sale Price": "median",
#         "Per Capita Income": "median",
#     }
#     if "Total Population" in tmp.columns:
#         agg_dict["Total Population"] = "sum"

#     city_agg = (
#         tmp.groupby("city", as_index=False)
#         .agg(agg_dict)
#         .rename(columns={"city": "city_clean"})
#     )

#     denom = city_agg["Per Capita Income"].replace(0, np.nan)
#     city_agg[RATIO_COL] = city_agg["Median Sale Price"] / denom

#     city_agg["affordable"] = city_agg[RATIO_COL] <= AFFORDABILITY_THRESHOLD

#     city_agg["user_max_rent"] = max_rent
#     city_agg["budget_pct"] = budget_pct
#     city_agg["year"] = year
#     city_agg["user_income"] = annual_income

#     return city_agg.sort_values("city_clean").reset_index(drop=True)


# def make_city_history(df: pd.DataFrame, city_name: str) -> pd.DataFrame:
#     """
#     Return year-level history for a selected city:
#     - Median Sale Price
#     - Per Capita Income
#     - price_to_income_ratio_by_year
#     """
#     tmp = df[df["city"] == city_name].copy()

#     if tmp.empty:
#         return tmp

#     denom = tmp["Per Capita Income"].replace(0, np.nan)
#     tmp["price_to_income_ratio_by_year"] = tmp["Median Sale Price"] / denom

#     hist = (
#         tmp.groupby("year", as_index=False)
#         .agg(
#             {
#                 "Median Sale Price": "median",
#                 "Per Capita Income": "median",
#                 "price_to_income_ratio_by_year": "median",
#             }
#         )
#         .sort_values("year")
#     )
#     return hist


# def make_zip_view_data(
#     df: pd.DataFrame,
#     city_name: str,
#     annual_income: float,
#     year: Optional[int] = None,
#     budget_pct: float = 30.0,
# ) -> pd.DataFrame:
#     """
#     Produce ZIP-level price-to-income ratio for a given city & year.
#     """
#     if year is None:
#         year = int(df["year"].max())

#     tmp = df[(df["city"] == city_name) & (df["year"] == year)].copy()

#     if tmp.empty:
#         return tmp

#     if "zipcode" not in tmp.columns:
#         raise KeyError("Data must contain a 'zipcode' column for ZIP-level view.")

#     zip_agg = (
#         tmp.groupby("zipcode", as_index=False)
#         .agg(
#             {
#                 "Median Sale Price": "median",
#                 "Per Capita Income": "median",
#             }
#         )
#     )

#     denom = zip_agg["Per Capita Income"].replace(0, np.nan)
#     zip_agg[RATIO_COL_ZIP] = zip_agg["Median Sale Price"] / denom

#     zip_agg["affordable"] = zip_agg[RATIO_COL_ZIP] <= AFFORDABILITY_THRESHOLD

#     return zip_agg.sort_values("Median Sale Price")
# Updated code to add back zip code filtering when adjusting income slider
# dataprep.py

# --- File: dataprep.py (Final Fix for Bar Chart Data) ---
import pandas as pd
import numpy as np
import os
import streamlit as st
from typing import Optional

# --- Define Constants at the TOP LEVEL ---
LOCAL_CSV_PATH = "HouseTS.csv"
CSV_URL = "https://github.com/yyy1029/House-Browse/releases/download/v1.0/HouseTS.csv"
RATIO_COL = "price_to_income_ratio"
RATIO_COL_ZIP = "price_to_income_ratio_zip"
AFFORDABILITY_THRESHOLD = 3.0
AFFORDABILITY_CATEGORIES = {
    "Affordable": (None, 3.0), "Moderately Unaffordable": (3.0, 4.0), 
    "Seriously Unaffordable": (4.0, 5.0), "Severely Unaffordable": (5.0, 8.9), 
    "Impossibly Unaffordable": (8.9, None),
}
AFFORDABILITY_COLORS = {
    "Affordable": "#4CAF50", "Moderately Unaffordable": "#FFC107", 
    "Seriously Unaffordable": "#FF9800", "Severely Unaffordable": "#E57373", 
    "Impossibly Unaffordable": "#B71C1C",
}

def classify_affordability(ratio: float) -> str:
    """Classifies a price-to-income ratio."""
    if pd.isna(ratio): return "N/A"
    
    sorted_categories = sorted(AFFORDABILITY_CATEGORIES.items(), 
                               key=lambda item: item[1][1] if item[1][1] is not None else float('inf'))

    for category, (lower, upper) in sorted_categories:
        if category == "Affordable":
            if ratio <= upper: return category
        elif lower is not None and upper is None:
            if ratio > lower: return category
        elif lower is not None and upper is not None:
            if lower < ratio <= upper: return category
            
    return "Uncategorized"

@st.cache_data(ttl=3600*24)
def load_data() -> pd.DataFrame:
    """Loads and standardizes data."""
    script_dir = os.path.dirname(__file__)
    local_file_path = os.path.join(script_dir, LOCAL_CSV_PATH)
    
    df = pd.DataFrame() 
    
    if os.path.exists(local_file_path):
        df = pd.read_csv(local_file_path)
        # st.info("Loaded data from local file: HouseTS.csv")
    else:
        try:
            df = pd.read_csv(CSV_URL)
            st.warning(f"Local file not found. Loaded data from URL: {CSV_URL}")
        except Exception as e:
            st.error(f"🔴 CRITICAL: Failed to load data from local path or URL. Check file path/internet: {e}")
            return pd.DataFrame() 

    if df.empty:
        st.error("🔴 CRITICAL: Data file is empty after loading.")
        return pd.DataFrame()

    # --- Standardize Column Names ---
    df.rename(
        columns={
            "median_sale_price": "median_sale_price",
            "per_capita_income": "per_capita_income",
            "Median Sale Price": "median_sale_price",
            "Per Capita Income": "per_capita_income",
            "city": "city_geojson_code"  # Preserve original code (ATL) here
        },
        inplace=True,
    )
    
    if "city_full" not in df.columns:
        df["city_full"] = df["city_geojson_code"] + " Metro Area"

    df['city_clean'] = df['city_geojson_code'] 

    df["monthly_income_pc"] = df["per_capita_income"] / 12.0

    return df


def apply_income_filter(df: pd.DataFrame, annual_income: float) -> pd.DataFrame:
    """Returns the base DataFrame (no hard filter) for map context."""
    return df.copy() # NOTE: Returns copy of full data for map context


@st.cache_data(ttl=3600*24)
def make_city_view_data(df_full: pd.DataFrame, annual_income: float, year: int, budget_pct: float = 30):
    """Aggregates data for the bar chart."""
    df_year = df_full[df_full['year'] == year].copy()

    # Aggregate by the GeoJSON code ('city_geojson_code')
    city_agg = df_year.groupby("city_geojson_code").agg(
        median_sale_price=("median_sale_price", "median"), 
        per_capita_income=("per_capita_income", "median"), 
        city_full=("city_full", "first"), 
    ).reset_index()

    city_agg[RATIO_COL] = city_agg["median_sale_price"] / (city_agg["per_capita_income"] * 2.51)
    city_agg["affordability_rating"] = city_agg[RATIO_COL].apply(classify_affordability)
    city_agg["affordable"] = city_agg[RATIO_COL] <= AFFORDABILITY_THRESHOLD

    # Rename columns for display in charts/tables
    city_agg.rename(
        columns={
            "median_sale_price": "Median Sale Price", "per_capita_income": "Per Capita Income",
            "city_geojson_code": "city", # 'city' holds the GeoJSON code (e.g., ATL) for bar chart x-axis
        },
        inplace=True,
    )

    return city_agg



def make_city_history(df: pd.DataFrame, city_name: str) -> pd.DataFrame:
    """
    Return year-level history for a selected city:
    """
    # NOTE: This uses the GeoJSON code for filtering
    tmp = df[df["city_geojson_code"] == city_name].copy() 

    if tmp.empty:
        return tmp

    denom = tmp["per_capita_income"].replace(0, np.nan)
    tmp["price_to_income_ratio_by_year"] = tmp["median_sale_price"] / denom

    hist = (
        tmp.groupby("year", as_index=False)
        .agg(
            {
                "median_sale_price": "median",
                "per_capita_income": "median",
                "price_to_income_ratio_by_year": "median",
            }
        )
        .sort_values("year")
    )
    return hist


def make_zip_view_data(
    df: pd.DataFrame,
    city_name: str,
    annual_income: float,
    year: Optional[int] = None,
    budget_pct: float = 30.0,
) -> pd.DataFrame:
    """
    Produce ZIP-level price-to-income ratio for a given city & year.
    (This function is defined but unused, as the logic is in zip_module)
    """
    # This function is a placeholder definition required for app_v2.py imports
    return pd.DataFrame()


