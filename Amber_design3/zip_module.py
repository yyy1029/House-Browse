from __future__ import annotations
import os
import pandas as pd
import numpy as np
import pgeocode
from dataprep import CSV_URL  # 使用你的 GitHub CSV URL

TABLE_NAME = "workspace.data511.house_ts"
LOCAL_TESTING = True

def load_city_zip_data(city_abbr: str, *, csv_path: str = CSV_URL) -> pd.DataFrame:

    df_full = pd.read_csv(csv_path)

    rename_map = {
        "zipcode": "zip_code",
        "Per Capita Income": "per_capita_income",
        "median_sale_price": "median_sale_price",
        "Median Rent": "median_rent",  
    }
    for old, new in rename_map.items():
        if old in df_full.columns:
            df_full = df_full.rename(columns={old: new})

 
    if "zip_code" in df_full.columns:
        df_full["zip_code_str"] = df_full["zip_code"].astype(str).str.zfill(5)
    elif "zipcode" in df_full.columns:
        df_full["zip_code_str"] = df_full["zipcode"].astype(str).str.zfill(5)

  
    if "city" in df_full.columns:
        df = df_full[df_full["city"] == city_abbr].copy()
    else:
        df = df_full.copy()

 
    if "year" not in df.columns and "date" in df.columns:
        try:
            df["date"] = pd.to_datetime(df["date"])
            df["year"] = df["date"].dt.year
        except Exception:
            pass

    return df


def get_zip_coordinates(df_zip: pd.DataFrame) -> pd.DataFrame:

    if df_zip is None or df_zip.empty:
        return df_zip.copy()

    out = df_zip.copy()

    
    if "zip_code_str" not in out.columns:
        if "zip_code" in out.columns:
            out["zip_code_str"] = out["zip_code"].astype(str).str.zfill(5)
        elif "zipcode" in out.columns:
            out["zip_code_str"] = out["zipcode"].astype(str).str.zfill(5)
        else:
            raise KeyError("miss zip_code / zipcode")

   
    if "per_capita_income" not in out.columns:
        if "Per Capita Income" in out.columns:
            out = out.rename(columns={"Per Capita Income": "per_capita_income"})
    if "median_sale_price" not in out.columns:
        raise KeyError("miss median_sale_price")

   
    nomi = pgeocode.Nominatim("us")
    geo = nomi.query_postal_code(out["zip_code_str"].tolist())

    out["lat"] = geo["latitude"].values
    out["lon"] = geo["longitude"].values
    out = out.dropna(subset=["lat", "lon"]).copy()

    # -----------------------------------------------------
    # Price-to-Income Ratio
    # -----------------------------------------------------
    out["zip_code_int"] = out["zip_code_str"].astype(int)
    out["price_to_income_zip"] = (
        out["median_sale_price"] / out["per_capita_income"]
    )

   
    out["affordability_norm"] = (
        np.clip(out["price_to_income_zip"], 0, 2) / 2.0
    )

    return out


__all__ = [
    "LOCAL_TESTING",
    "TABLE_NAME",
    "load_city_zip_data",
    "get_zip_coordinates",
]
