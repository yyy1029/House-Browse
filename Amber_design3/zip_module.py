# zip_module.py
from __future__ import annotations
import os
import re
import json
import pandas as pd
import numpy as np
import pgeocode
from typing import Optional

# -------- Settings --------
TABLE_NAME = "workspace.data511.house_ts"  
LOCAL_TESTING = True  


_env_flag = os.environ.get("ZIP_LOCAL_TESTING")
if _env_flag in ("0", "1"):
    LOCAL_TESTING = (_env_flag == "1")


# -------- Databricks / Local Helper --------
def sql_query(query: str, csv_path: str = "HouseTS.csv") -> pd.DataFrame:
    """
    当 LOCAL_TESTING=True 时：
      - 读取本地 CSV（默认 'HouseTS.csv'，需放在项目根目录或传入绝对路径）
      - 自动对列名做一次标准化：zipcode→zip_code，Per Capita Income→per_capita_income，Median Rent→median_rent
      - 根据 query 里的 WHERE city='XXX' 进行过滤（保留同学代码风格）

    当 LOCAL_TESTING=False 时：
      - 通过 Databricks SQL 查询（需要在环境中配置 DATABRICKS_WAREHOUSE_ID 等）
    """
    if LOCAL_TESTING:
        if not os.path.exists(csv_path):
            raise FileNotFoundError(
                f"CSV 文件未找到：{csv_path}。请把 HouseTS.csv 放在项目根目录，或传入正确路径。"
            )

        df_full = pd.read_csv(csv_path)

        # 标准化列名（与同学代码一致）
        rename_map = {
            "zipcode": "zip_code",
            "Per Capita Income": "per_capita_income",
            "Median Rent": "median_rent",
        }
        for old, new in rename_map.items():
            if old in df_full.columns:
                df_full = df_full.rename(columns={old: new})

        # 确保有 zip_code_str
        if "zip_code" in df_full.columns:
            df_full["zip_code_str"] = df_full["zip_code"].astype(str).str.zfill(5)
        elif "zipcode" in df_full.columns:
            df_full["zip_code_str"] = df_full["zipcode"].astype(str).str.zfill(5)

        # 从 SQL 字符串里解析 city='XXX'
        match = re.search(r"WHERE\s+city\s*=\s*'(\w+)'", query, flags=re.IGNORECASE)
        city_abbr = match.group(1) if match else None

        if city_abbr:
            return df_full[df_full.get("city", pd.Series([None]*len(df_full))) == city_abbr].copy()
        return df_full.copy()

    # ---- Databricks 模式 ----
    try:
        from databricks import sql
        from databricks.sdk.core import Config
    except Exception as e:
        raise RuntimeError(
            "LOCAL_TESTING=False 但未安装 databricks 相关依赖。请安装 databricks-sdk 并配置环境变量。"
        ) from e

    warehouse_id = os.getenv("DATABRICKS_WAREHOUSE_ID")
    if not warehouse_id:
        raise RuntimeError("DATABRICKS_WAREHOUSE_ID 未配置。")

    cfg = Config()
    with sql.connect(
        server_hostname=cfg.host,
        http_path=f"/sql/1.0/warehouses/{warehouse_id}",
        credentials_provider=lambda: cfg.authenticate,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchall_arrow().to_pandas()


# -------- Data Loader（按城市取 ZIP 粒度） --------
def load_city_zip_data(city_abbr: str, *, csv_path: str = "HouseTS.csv") -> pd.DataFrame:
    

    df = sql_query(query, csv_path=csv_path).copy()


    if "zip_code_str" not in df.columns:
        if "zip_code" in df.columns:
            df["zip_code_str"] = df["zip_code"].astype(str).str.zfill(5)
        elif "zipcode" in df.columns:
            df["zip_code_str"] = df["zipcode"].astype(str).str.zfill(5)


    if "median_rent" not in df.columns and "Median Rent" in df.columns:
        df = df.rename(columns={"Median Rent": "median_rent"})
    if "per_capita_income" not in df.columns and "Per Capita Income" in df.columns:
        df = df.rename(columns={"Per Capita Income": "per_capita_income"})

    return df


# -------- Geo Enrichment --------
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
            raise KeyError("输入数据缺少 zip_code / zipcode 字段。")

 
    if "median_rent" not in out.columns and "Median Rent" in out.columns:
        out = out.rename(columns={"Median Rent": "median_rent"})
    if "per_capita_income" not in out.columns and "Per Capita Income" in out.columns:
        out = out.rename(columns={"Per Capita Income": "per_capita_income"})


    nomi = pgeocode.Nominatim("us")
    geo = nomi.query_postal_code(out["zip_code_str"].tolist())

    out["lat"] = geo["latitude"].values
    out["lon"] = geo["longitude"].values
    out = out.dropna(subset=["lat", "lon"]).copy()

    # 衍生字段
    out["zip_code_int"] = out["zip_code_str"].astype(int)
    out["monthly_income"] = out["per_capita_income"] / 12.0
    # 防止除零
    denom = (0.3 * out["monthly_income"]).replace(0, np.nan)
    out["affordability_ratio"] = out["median_rent"] / denom
    out["affordability_norm"] = (np.clip(out["affordability_ratio"], 0, 2) / 2.0)

    return out


__all__ = [
    "LOCAL_TESTING",
    "TABLE_NAME",
    "sql_query",
    "load_city_zip_data",
    "get_zip_coordinates",
]
