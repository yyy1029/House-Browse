# zip_module.py

from __future__ import annotations
import os
import re
import pandas as pd
import numpy as np
import pgeocode
from dataprep import CSV_URL  # ✅ 自动使用你 dataprep 里的 GitHub CSV 地址

# ===== Settings =====
TABLE_NAME = "workspace.data511.house_ts"
LOCAL_TESTING = True  # 如果以后接 Databricks，可改为 False


# ===== Helper: SQL or CSV =====
def sql_query(query: str, csv_path: str = CSV_URL) -> pd.DataFrame:
    """
    LOCAL_TESTING=True:
      - 直接读取 GitHub Releases 上的 CSV（通过 dataprep.CSV_URL）
      - 标准化列名：zipcode→zip_code，Per Capita Income→per_capita_income，Median Rent→median_rent
      - 支持根据 SQL 语句中 city='XXX' 的条件过滤
    LOCAL_TESTING=False:
      - 走 Databricks SQL 查询
    """
    if LOCAL_TESTING:
        # ✅ 直接读取线上 CSV（pandas 可自动识别 URL）
        df_full = pd.read_csv(csv_path)

        # 列名标准化
        rename_map = {
            "zipcode": "zip_code",
            "Per Capita Income": "per_capita_income",
            "Median Rent": "median_rent",
        }
        for old, new in rename_map.items():
            if old in df_full.columns:
                df_full = df_full.rename(columns={old: new})

        # 生成 zip_code_str
        if "zip_code" in df_full.columns:
            df_full["zip_code_str"] = df_full["zip_code"].astype(str).str.zfill(5)
        elif "zipcode" in df_full.columns:
            df_full["zip_code_str"] = df_full["zipcode"].astype(str).str.zfill(5)

        # 从 SQL 中提取城市过滤条件
        match = re.search(r"WHERE\s+city\s*=\s*'(\w+)'", query, flags=re.IGNORECASE)
        city_abbr = match.group(1) if match else None

        if city_abbr:
            return df_full[df_full.get("city") == city_abbr].copy()
        return df_full.copy()

    # ===== Databricks 分支 =====
    try:
        from databricks import sql
        from databricks.sdk.core import Config
    except Exception as e:
        raise RuntimeError(
            "LOCAL_TESTING=False 但未安装 databricks 依赖，请先安装 databricks-sdk。"
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


# ===== Loader: 按城市取 ZIP 粒度 =====
def load_city_zip_data(city_abbr: str, *, csv_path: str = CSV_URL) -> pd.DataFrame:
    """
    返回指定城市的 ZIP 粒度数据。
    输出列包括：
      - zip_code / zip_code_str
      - median_rent
      - per_capita_income
      - year（若有）
    """
    query = f"""
        SELECT
            city,
            zipcode AS zip_code,
            YEAR(date) AS year,
            MEDIAN(median_rent) AS median_rent,
            MEDIAN(per_capita_income) AS per_capita_income,
            COUNT(*) AS n_records
        FROM {TABLE_NAME}
        WHERE city = '{city_abbr}'
        GROUP BY city, zipcode, YEAR(date)
        ORDER BY median_rent DESC
    """

    df = sql_query(query, csv_path=csv_path).copy()

    # 兜底处理列名
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


# ===== Geo: 补经纬度 & 可负担性指标 =====
def get_zip_coordinates(df_zip: pd.DataFrame) -> pd.DataFrame:
    """
    用 pgeocode 为 ZIP 记录补经纬度，并计算：
      monthly_income = per_capita_income / 12
      affordability_ratio = median_rent / (0.3 * monthly_income)
      affordability_norm = clip(ratio, 0~2)/2 ∈ [0,1]
      zip_code_int = int(zip_code_str)
    """
    if df_zip is None or df_zip.empty:
        return df_zip.copy()

    out = df_zip.copy()

    # zip_code_str
    if "zip_code_str" not in out.columns:
        if "zip_code" in out.columns:
            out["zip_code_str"] = out["zip_code"].astype(str).str.zfill(5)
        elif "zipcode" in out.columns:
            out["zip_code_str"] = out["zipcode"].astype(str).str.zfill(5)
        else:
            raise KeyError("输入数据缺少 zip_code / zipcode 字段。")

    # 列名统一
    if "median_rent" not in out.columns and "Median Rent" in out.columns:
        out = out.rename(columns={"Median Rent": "median_rent"})
    if "per_capita_income" not in out.columns and "Per Capita Income" in out.columns:
        out = out.rename(columns={"Per Capita Income": "per_capita_income"})

    # pgeocode 查经纬度
    nomi = pgeocode.Nominatim("us")
    geo = nomi.query_postal_code(out["zip_code_str"].tolist())

    out["lat"] = geo["latitude"].values
    out["lon"] = geo["longitude"].values
    out = out.dropna(subset=["lat", "lon"]).copy()

    # 指标计算
    out["zip_code_int"] = out["zip_code_str"].astype(int)
    out["monthly_income"] = out["per_capita_income"] / 12.0
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
