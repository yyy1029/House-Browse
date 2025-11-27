# dataprep.py
"""
Data loading and preparation helpers for Design 3 (HouseTS dataset).
"""

import pandas as pd
import numpy as np

# CSV_PATH = "HouseTS.csv"（if you want to download the csv on your desktop)
CSV_URL = "https://github.com/yyy1029/House-Browse/releases/download/v1.0/HouseTS.csv"

# 统一的比值列名 & 阈值（和 app 里保持一致）
RATIO_COL = "price_to_income_ratio"        # 城市级：rent / income
RATIO_COL_ZIP = "price_to_income_ratio_zip"
AFFORDABILITY_THRESHOLD = 0.30            # 30% 收入用于租金作为“边界线”


def load_data() -> pd.DataFrame:
    """
    Load HouseTS.csv from GitHub Releases and compute key derived fields.
    """
    df = pd.read_csv(CSV_URL)

    df["date"] = pd.to_datetime(df["date"])
    df["city_clean"] = df["city"]
    # 基于人均年收入得到月收入
    df["monthly_income_pc"] = df["Per Capita Income"] / 12.0

    return df


def make_city_view_data(
    df: pd.DataFrame,
    annual_income: float,
    year: int | None = None,
    budget_pct: float = 30.0,
) -> pd.DataFrame:
    """
    Aggregate data to city level for a given year.

    Returns one row per city with at least:
    - city_clean
    - Median Rent
    - Per Capita Income
    - Total Population
    - monthly_income_city
    - price_to_income_ratio   (rent / per-capita monthly income)
    - affordable              (ratio <= AFFORDABILITY_THRESHOLD)
    - year, user_income, user_max_rent, budget_pct
    """
    if year is None:
        year = int(df["year"].max())

    # 用户层面的“30% 规则”仍然保留，只用于展示（Profile 卡片）
    max_rent = annual_income * (budget_pct / 100.0) / 12.0

    tmp = df[df["year"] == year].copy()

    # aggregate by city
    city_agg = (
        tmp.groupby("city", as_index=False)
        .agg(
            {
                "Median Rent": "median",
                "Per Capita Income": "median",
                "Total Population": "sum",
            }
        )
        .rename(columns={"city": "city_clean"})
    )

    # city-level monthly income
    city_agg["monthly_income_city"] = city_agg["Per Capita Income"] / 12.0

    # 真正的 price-to-income（这里是 rent-to-income）：月租 / 月人均收入
    denom = city_agg["monthly_income_city"].replace(0, np.nan)
    city_agg[RATIO_COL] = city_agg["Median Rent"] / denom

    # 基于 ratio 的可负担判断：比例越低越可负担
    city_agg["affordable"] = city_agg[RATIO_COL] <= AFFORDABILITY_THRESHOLD

    # 保留与用户收入相关的字段，方便前端展示或后续扩展
    city_agg["user_max_rent"] = max_rent
    city_agg["budget_pct"] = budget_pct
    city_agg["year"] = year
    city_agg["user_income"] = annual_income

    return city_agg.sort_values("city_clean").reset_index(drop=True)


def make_city_history(df: pd.DataFrame, city_name: str) -> pd.DataFrame:
    """
    For a selected city, return year-level history:

    - Median Rent
    - Per Capita Income
    - price_to_income_ratio_by_year (rent / per-capita monthly income)
    """
    tmp = df[df["city"] == city_name].copy()

    tmp["monthly_income_city"] = tmp["Per Capita Income"] / 12.0
    denom = tmp["monthly_income_city"].replace(0, np.nan)
    tmp["price_to_income_ratio_by_year"] = tmp["Median Rent"] / denom

    hist = (
        tmp.groupby("year", as_index=False)
        .agg(
            {
                "Median Rent": "median",
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
    year: int | None = None,
    budget_pct: float = 30.0,
) -> pd.DataFrame:
    """
    Zip-level view inside a city for a given income & year.

    返回每个 ZIP 的：
    - Median Rent
    - Per Capita Income
    - price_to_income_ratio_zip  (rent / per-capita monthly income)
    - affordable (ratio <= AFFORDABILITY_THRESHOLD)
    """
    if year is None:
        year = int(df["year"].max())

    tmp = df[(df["city"] == city_name) & (df["year"] == year)].copy()

    if tmp.empty:
        return tmp

    zip_agg = (
        tmp.groupby("zipcode", as_index=False)
        .agg(
            {
                "Median Rent": "median",
                "Per Capita Income": "median",
            }
        )
    )

    # ZIP 级月收入
    zip_agg["monthly_income_zip"] = zip_agg["Per Capita Income"] / 12.0
    denom = zip_agg["monthly_income_zip"].replace(0, np.nan)
    zip_agg[RATIO_COL_ZIP] = zip_agg["Median Rent"] / denom

    # 基于 price-to-income 的可负担判断
    zip_agg["affordable"] = zip_agg[RATIO_COL_ZIP] <= AFFORDABILITY_THRESHOLD

    return zip_agg.sort_values("Median Rent")
