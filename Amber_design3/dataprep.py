import pandas as pd
import numpy as np

CSV_URL = "https://github.com/yyy1029/House-Browse/releases/download/v1.0/HouseTS.csv"


def load_data() -> pd.DataFrame:
    """
    Load HouseTS.csv from GitHub Releases and compute key derived fields.
    """
    df = pd.read_csv(CSV_URL)

    df["date"] = pd.to_datetime(df["date"])
    df["city_clean"] = df["city"]

    if "Per Capita Income" in df.columns:
        df["monthly_income_pc"] = df["Per Capita Income"] / 12.0

    return df

def make_city_view_data(
    df: pd.DataFrame,
    annual_income: float,
    year: int | None = None,
    threshold: float | None = None,
) -> pd.DataFrame:
    """
    Calculate price-to-income ratio at the city level, and affordability.
    """
    if year is None:
        year = int(df["year"].max())

    tmp = df[df["year"] == year].copy()

    city_agg = (
        tmp.groupby("city", as_index=False)
        .agg(
            {
                "Median Rent": "median",
                "Per Capita Income": "median",
                "median_sale_price": "median",  # Sale price used for price-to-income ratio
                "Total Population": "sum",
            }
        )
        .rename(columns={"city": "city_clean"})
    )

    # Monthly income of the city
    city_agg["monthly_income_city"] = city_agg["Per Capita Income"] / 12.0

    # Calculate price-to-income ratio
    city_agg["price_to_income"] = (
        city_agg["median_sale_price"] / city_agg["Per Capita Income"]
    )

    # Set default threshold if not provided (using median of price-to-income ratio)
    if threshold is None:
        threshold = city_agg["price_to_income"].median()

    # Calculate affordability gap (below threshold is affordable)
    city_agg["afford_gap"] = threshold - city_agg["price_to_income"]
    city_agg["affordable"] = city_agg["afford_gap"] >= 0  # affordable if gap >= 0

    # Adding additional details
    city_agg["budget_pct"] = 30.0  # Housing budget percentage (not directly used in price-to-income)
    city_agg["year"] = year
    city_agg["user_income"] = annual_income

    return city_agg.sort_values("city_clean").reset_index(drop=True)

def make_city_history(df: pd.DataFrame, city_name: str) -> pd.DataFrame:
    """
    For a selected city, return year-level history (optional drill-down):
    - Median Rent
    - Per Capita Income
    - Price-to-Income ratio
    """
    tmp = df[df["city"] == city_name].copy()

    tmp["monthly_income_city"] = tmp["Per Capita Income"] / 12.0
    tmp["max_rent_30"] = tmp["monthly_income_city"] * 0.3
    tmp["price_to_income"] = tmp["median_sale_price"] / tmp["Per Capita Income"]

    hist = (
        tmp.groupby("year", as_index=False)
        .agg(
            {
                "Median Rent": "median",
                "Per Capita Income": "median",
                "price_to_income": "median",
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
    threshold: float | None = None,
) -> pd.DataFrame:
    """
    Zip-level view inside a city using price-to-income ratio:
    - price_to_income_zip = median_sale_price / Per Capita Income
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
                "median_sale_price": "median",  # Median sale price for price-to-income ratio
                "Per Capita Income": "median",  # Median per capita income
            }
        )
    )

    zip_agg["price_to_income_zip"] = (
        zip_agg["median_sale_price"] / zip_agg["Per Capita Income"]
    )

    # Set threshold if not provided
    if threshold is None:
        threshold = zip_agg["price_to_income_zip"].median()

    # Calculate affordability gap (price-to-income ratio)
    zip_agg["afford_gap_zip"] = threshold - zip_agg["price_to_income_zip"]
    zip_agg["affordable"] = zip_agg["afford_gap_zip"] >= 0  # affordable if gap >= 0

    return zip_agg.sort_values("median_sale_price")
