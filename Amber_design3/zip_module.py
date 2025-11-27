from __future__ import annotations
import os
import pandas as pd
import numpy as np
import pgeocode
from dataprep import CSV_URL

TABLE_NAME = "workspace.data511.house_ts"
LOCAL_TESTING = True


def load_city_zip_data(city_abbr: str, *, csv_path: str = CSV_URL) -> pd.DataFrame:
    """
    Load the full CSV and filter rows to a single city.

    Ensures:
    - a zip code string column: zip_code_str
    - keeps sale price and income columns if present
    - adds a 'year' column if only 'date' exists
    """
    df_full = pd.read_csv(csv_path)

    # Standardize some column names if needed
    rename_map = {
        "zipcode": "zip_code",
        "Per Capita Income": "per_capita_income",
        "per_capita_income": "per_capita_income",
        "Median Sale Price": "median_sale_price",
        "median_sale_price": "median_sale_price",
    }
    for old, new in rename_map.items():
        if old in df_full.columns:
            df_full = df_full.rename(columns={old: new})

    # Ensure zip_code_str exists
    if "zip_code" in df_full.columns:
        df_full["zip_code_str"] = df_full["zip_code"].astype(str).str.zfill(5)
    elif "zipcode" in df_full.columns:
        df_full["zip_code_str"] = df_full["zipcode"].astype(str).str.zfill(5)

    # Filter to a single city if city column exists
    if "city" in df_full.columns:
        df = df_full[df_full["city"] == city_abbr].copy()
    else:
        df = df_full.copy()

    # Ensure 'year' column exists if only 'date' is present
    if "year" not in df.columns and "date" in df.columns:
        try:
            df["date"] = pd.to_datetime(df["date"])
            df["year"] = df["date"].dt.year
        except Exception:
            pass

    return df


def get_zip_coordinates(df_zip: pd.DataFrame) -> pd.DataFrame:
    """
    Enrich ZIP-level data with latitude/longitude and compute
    price_to_income_ratio = median_sale_price / per_capita_income.
    """
    if df_zip is None or df_zip.empty:
        return df_zip.copy()

    out = df_zip.copy()

    # Ensure a zip_code_str column
    if "zip_code_str" not in out.columns:
        if "zip_code" in out.columns:
            out["zip_code_str"] = out["zip_code"].astype(str).str.zfill(5)
        elif "zipcode" in out.columns:
            out["zip_code_str"] = out["zipcode"].astype(str).str.zfill(5)
        else:
            raise KeyError("Missing zip_code / zipcode / zip_code_str column.")

    # Standardize sale price & income columns
    if "median_sale_price" not in out.columns and "Median Sale Price" in out.columns:
        out = out.rename(columns={"Median Sale Price": "median_sale_price"})
    if "per_capita_income" not in out.columns and "Per Capita Income" in out.columns:
        out = out.rename(columns={"Per Capita Income": "per_capita_income"})

    # Lat/lon via pgeocode
    nomi = pgeocode.Nominatim("us")
    geo = nomi.query_postal_code(out["zip_code_str"].tolist())

    out["lat"] = geo["latitude"].values
    out["lon"] = geo["longitude"].values

    # Drop rows with missing coordinates
    out = out.dropna(subset=["lat", "lon"]).copy()

    # Integer ZIP code
    out["zip_code_int"] = out["zip_code_str"].astype(int)

    # Compute price-to-income ratio at ZIP level
    if "median_sale_price" not in out.columns or "per_capita_income" not in out.columns:
        # If columns are missing, we just return coordinates without ratios
        return out

    denom = out["per_capita_income"].replace(0, np.nan)
    out["price_to_income_ratio"] = out["median_sale_price"] / denom

    # Normalized ratio (0–1) for optional color scaling
    MAX_RATIO_FOR_NORM = 15.0
    out["price_to_income_norm"] = (
        np.clip(out["price_to_income_ratio"], 0, MAX_RATIO_FOR_NORM) / MAX_RATIO_FOR_NORM
    )

    return out


__all__ = ["LOCAL_TESTING", "TABLE_NAME", "load_city_zip_data", "get_zip_coordinates"]
