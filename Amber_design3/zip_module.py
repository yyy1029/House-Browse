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

    # 统一列名
    rename_map = {
        "zipcode": "zip_code",
        "Per Capita Income": "per_capita_income",
        "Median Rent": "median_rent",
    }
    for old, new in rename_map.items():
        if old in df_full.columns:
            df_full = df_full.rename(columns={old: new})

    # 补 zip_code_str
    if "zip_code" in df_full.columns:
        df_full["zip_code_str"] = df_full["zip_code"].astype(str).str.zfill(5)
    elif "zipcode" in df_full.columns:
        df_full["zip_code_str"] = df_full["zipcode"].astype(str).str.zfill(5)

    # 按城市过滤
    if "city" in df_full.columns:
        df = df_full[df_full["city"] == city_abbr].copy()
    else:
        df = df_full.copy()

    # 补 year
    if "year" not in df.columns and "date" in df.columns:
        try:
            df["date"] = pd.to_datetime(df["date"])
            df["year"] = df["date"].dt.year
        except Exception:
            pass

    return df


def get_zip_coordinates(df_zip: pd.DataFrame) -> pd.DataFrame:
    """
    pgeocode 补经纬度 + 计算 ZIP 级 price-to-income 指标：
    price_to_income_ratio = median_rent / (per_capita_income / 12).
    """
    if df_zip is None or df_zip.empty:
        return df_zip.copy()

    out = df_zip.copy()

    # 统一 zip_code_str
    if "zip_code_str" not in out.columns:
        if "zip_code" in out.columns:
            out["zip_code_str"] = out["zip_code"].astype(str).str.zfill(5)
        elif "zipcode" in out.columns:
            out["zip_code_str"] = out["zipcode"].astype(str).str.zfill(5)
        else:
            raise KeyError("缺少 zip_code / zipcode 字段。")

    # 确保租金 & 收入列名统一
    if "median_rent" not in out.columns and "Median Rent" in out.columns:
        out = out.rename(columns={"Median Rent": "median_rent"})
    if "per_capita_income" not in out.columns and "Per Capita Income" in out.columns:
        out = out.rename(columns={"Per Capita Income": "per_capita_income"})

    # 用 pgeocode 查经纬度
    nomi = pgeocode.Nominatim("us")
    geo = nomi.query_postal_code(out["zip_code_str"].tolist())

    out["lat"] = geo["latitude"].values
    out["lon"] = geo["longitude"].values

    # 去掉没有经纬度的行
    out = out.dropna(subset=["lat", "lon"]).copy()

    # 整型 ZIP，方便 geojson 里用 int id
    out["zip_code_int"] = out["zip_code_str"].astype(int)

    # 月人均收入
    out["monthly_income"] = out["per_capita_income"] / 12.0

    # ✅ 真正的 rent-to-income ratio：月租 / 月收入
    denom = out["monthly_income"].replace(0, np.nan)
    out["price_to_income_ratio"] = out["median_rent"] / denom

    # 可选：做一个 0~1 的归一化，用于简单配色（如果不用可以不在前端引用）
    MAX_RATIO_FOR_NORM = 0.8  # 假设 0.8 是比较“极限”的值，可以按数据调整
    out["price_to_income_norm"] = (
        np.clip(out["price_to_income_ratio"], 0, MAX_RATIO_FOR_NORM) / MAX_RATIO_FOR_NORM
    )

    return out


__all__ = ["LOCAL_TESTING", "TABLE_NAME", "load_city_zip_data", "get_zip_coordinates"]
