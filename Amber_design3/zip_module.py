from __future__ import annotations
import os
import pandas as pd
import numpy as np
import pgeocode
from dataprep import CSV_URL

TABLE_NAME = "workspace.data511.house_ts"
LOCAL_TESTING = True

def load_city_zip_data(city_abbr: str, *, csv_path: str = CSV_URL) -> pd.DataFrame:
    """直接从 CSV_URL 读取并按 city 过滤，统一列名并补 year。"""
    df_full = pd.read_csv(csv_path)

    rename_map = {
        "zipcode": "zip_code",
        "Per Capita Income": "per_capita_income",
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
    """pgeocode 补经纬度 + 计算 affordability 指标。"""
    if df_zip is None or df_zip.empty:
        return df_zip.copy()

    out = df_zip.copy()

    if "zip_code_str" not in out.columns:
        if "zip_code" in out.columns:
            out["zip_code_str"] = out["zip_code"].astype(str).str.zfill(5)
        elif "zipcode" in out.columns:
            out["zip_code_str"] = out["zipcode"].astype(str).str.zfill(5)
        else:
            raise KeyError("缺少 zip_code / zipcode 字段。")

    if "median_rent" not in out.columns and "Median Rent" in out.columns:
        out = out.rename(columns={"Median Rent": "median_rent"})
    if "per_capita_income" not in out.columns and "Per Capita Income" in out.columns:
        out = out.rename(columns={"Per Capita Income": "per_capita_income"})

    nomi = pgeocode.Nominatim("us")
    geo = nomi.query_postal_code(out["zip_code_str"].tolist())

    out["lat"] = geo["latitude"].values
    out["lon"] = geo["longitude"].values
    out = out.dropna(subset=["lat", "lon"]).copy()

    out["zip_code_int"] = out["zip_code_str"].astype(int)
    out["monthly_income"] = out["per_capita_income"] / 12.0
    denom = (0.3 * out["monthly_income"]).replace(0, np.nan)
    out["affordability_ratio"] = out["median_rent"] / denom
    out["affordability_norm"] = (np.clip(out["affordability_ratio"], 0, 2) / 2.0)

    return out

__all__ = ["LOCAL_TESTING", "TABLE_NAME", "load_city_zip_data", "get_zip_coordinates"]
