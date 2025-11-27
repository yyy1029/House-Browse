"""
Data loading and preparation helpers for Design 3 (house price-to-income dataset).
"""

from typing import Optional

import pandas as pd
import numpy as np

CSV_URL = "https://github.com/yyy1029/House-Browse/releases/download/v1.0/HouseTS.csv"

# Shared with app.py
RATIO_COL = "price_to_income_ratio"          # city-level price-to-income ratio
RATIO_COL_ZIP = "price_to_income_ratio_zip"  # zip-level price-to-income ratio
AFFORDABILITY_THRESHOLD = 5.0                # example threshold for affordability


def load_data() -> pd.DataFrame:
    """
    Load HouseTS CSV and compute base fields.

    Required columns in CSV:
    - city
    - year
    - median_sale_price (or Median Sale Price)
    - per_capita_income (or Per Capita Income)
    """
    df = pd.read_csv(CSV_URL)

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])

    if "city" not in df.columns:
        raise KeyError("Input CSV must contain a 'city' column.")

    df["city_clean"] = df["city"]

    # Rename core columns if needed
    rename_map = {}
    if "median_sale_price" in df.columns:
        rename_map["median_sale_price"] = "Median Sale Price"
    if "per_capita_income" in df.columns:
        rename_map["per_capita_income"] = "Per Capita Income"
    df = df.rename(columns=rename_map)

    if "Median Sale Price" not in df.columns or "Per Capita Income" not in df.columns:
        raise KeyError(
            "Input CSV must contain 'Median Sale Price' and 'Per Capita Income', "
            "or columns that can be renamed to these."
        )

    df["monthly_income_pc"] = df["Per Capita Income"] / 12.0

    return df


def make_city_view_data(
    df: pd.DataFrame,
    annual_income: float,
    year: Optional[int] = None,
    budget_pct: float = 30.0,
) -> pd.DataFrame:
    """
    Aggregate data to city level for a given year.

    Outputs one row per city with:
    - Median Sale Price
    - Per Capita Income
    - price_to_income_ratio (Median Sale Price / Per Capita Income)
    - affordable (ratio <= AFFORDABILITY_THRESHOLD)
    - user-related fields (for UI display only)
    """
    if year is None:
        year = int(df["year"].max())

    # Only used for UI profile card (max rent), not for ratio computation
    max_rent = annual_income * (budget_pct / 100.0) / 12.0

    tmp = df[df["year"] == year].copy()

    agg_dict = {
        "Median Sale Price": "median",
        "Per Capita Income": "median",
    }
    if "Total Population" in tmp.columns:
        agg_dict["Total Population"] = "sum"

    city_agg = (
        tmp.groupby("city", as_index=False)
        .agg(agg_dict)
        .rename(columns={"city": "city_clean"})
    )

    denom = city_agg["Per Capita Income"].replace(0, np.nan)
    city_agg[RATIO_COL] = city_agg["Median Sale Price"] / denom

    city_agg["affordable"] = city_agg[RATIO_COL] <= AFFORDABILITY_THRESHOLD

    city_agg["user_max_rent"] = max_rent
    city_agg["budget_pct"] = budget_pct
    city_agg["year"] = year
    city_agg["user_income"] = annual_income

    return city_agg.sort_values("city_clean").reset_index(drop=True)


def make_city_history(df: pd.DataFrame, city_name: str) -> pd.DataFrame:
    """
    Return year-level history for a selected city:
    - Median Sale Price
    - Per Capita Income
    - price_to_income_ratio_by_year
    """
    tmp = df[df["city"] == city_name].copy()

    if tmp.empty:
        return tmp

    denom = tmp["Per Capita Income"].replace(0, np.nan)
    tmp["price_to_income_ratio_by_year"] = tmp["Median Sale Price"] / denom

    hist = (
        tmp.groupby("year", as_index=False)
        .agg(
            {
                "Median Sale Price": "median",
                "Per Capita Income": "median",
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
    """
    if year is None:
        year = int(df["year"].max())

    tmp = df[(df["city"] == city_name) & (df["year"] == year)].copy()

    if tmp.empty:
        return tmp

    if "zipcode" not in tmp.columns:
        raise KeyError("Data must contain a 'zipcode' column for ZIP-level view.")

    zip_agg = (
        tmp.groupby("zipcode", as_index=False)
        .agg(
            {
                "Median Sale Price": "median",
                "Per Capita Income": "median",
            }
        )
    )

    denom = zip_agg["Per Capita Income"].replace(0, np.nan)
    zip_agg[RATIO_COL_ZIP] = zip_agg["Median Sale Price"] / denom

    zip_agg["affordable"] = zip_agg[RATIO_COL_ZIP] <= AFFORDABILITY_THRESHOLD

    return zip_agg.sort_values("Median Sale Price")
