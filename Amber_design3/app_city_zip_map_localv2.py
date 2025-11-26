import os
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import pgeocode
import random
import json
# import requests
import geopandas as gpd


LOCAL_TESTING = True

if not LOCAL_TESTING:
    from databricks import sql
    from databricks.sdk.core import Config

# -------- Streamlit Page Config --------
st.set_page_config(
    page_title="City ZIP Code Rent Explorer",
    layout="wide"
)

# -------- Settings --------
TABLE_NAME = "workspace.data511.house_ts"
GEO_TABLE = "workspace.data511.zip_geo"

CITY_NAMES = {
    "ATL": "Atlanta, GA",
    "ATX": "Austin, TX",
    "BOS": "Boston, MA",
    "BWI": "Baltimore, MD",
    "CHI": "Chicago, IL",
    "CIN": "Cincinnati, OH",
    "CLT": "Charlotte, NC",
    "DAL": "Dallas, TX",
    "DC": "Washington, DC",
    "DEN": "Denver, CO",
    "DET": "Detroit, MI",
    "HOU": "Houston, TX",
    "LA": "Los Angeles, CA",
    "LV": "Las Vegas, NV",
    "MIA": "Miami, FL",
    "MSP": "Minneapolis, MN",
    "NY": "New York, NY",
    "ORL": "Orlando, FL",
    "PDX": "Portland, OR",
    "PGH": "Pittsburgh, PA",
    "PHL": "Philadelphia, PA",
    "PHX": "Phoenix, AZ",
    "RIV": "Riverside, CA",
    "SA": "San Antonio, TX",
    "SAC": "Sacramento, CA",
    "SD": "San Diego, CA",
    "SEA": "Seattle, WA",
    "SF": "San Francisco, CA",
    "STL": "St. Louis, MO",
    "TPA": "Tampa, FL",
}

# -------- Databricks SQL Helper --------
def sql_query(query: str) -> pd.DataFrame:
    if LOCAL_TESTING:
        import re
        # No sampling - just getting columns: 
        df_full = pd.read_csv("HouseTS.csv")

        df_full = df_full.rename(columns={
            "zipcode": "zip_code",
            "Per Capita Income": "per_capita_income",
            "Median Rent": "median_rent"
        })
        # Ensure ZIP codes are strings, zero-padded
        df_full["zip_code_str"] = df_full["zip_code"].astype(str).str.zfill(5)

        # Extract city abbreviation from SQL query (WHERE city = '...')
        match = re.search(r"WHERE city\s*=\s*'(\w+)'", query)
        city_abbr = match.group(1) if match else None

        # Filter by city if provided
        if city_abbr:
            df_filtered = df_full[df_full["city"] == city_abbr].copy()
        else:
            df_filtered = df_full.copy()

        return df_filtered

        # --- REAL SQL mode --- 
    else:
        warehouse_id = os.getenv("DATABRICKS_WAREHOUSE_ID")
        if not warehouse_id:
            raise RuntimeError("DATABRICKS_WAREHOUSE_ID is not configured in app.yaml!")
        cfg = Config()
        with sql.connect(
            server_hostname=cfg.host,
            http_path=f"/sql/1.0/warehouses/{warehouse_id}",
            credentials_provider=lambda: cfg.authenticate,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                return cursor.fetchall_arrow().to_pandas()

        # --- Load full dataset once (dummy or cached real data) ---
        # ny_zips = list(range(10001, 11698))  # overshoots but safe for mock data

        # df_full = pd.DataFrame({
        #     "city": ["NY"] * len(ny_zips),
        #     "zip_code": ny_zips,
        #     "median_rent": np.random.randint(2500, 5500, len(ny_zips)),
        #     "per_capita_income": np.random.randint(50000, 120000, len(ny_zips)),
        #     "year": [2025] * len(ny_zips),
        #     "n_records": np.random.randint(5, 30, len(ny_zips))
        # })

        # # --- Filter to New York only ---
        # # df_ny = df_full[df_full["city"] == "NY"]
        # df_ny = df_full.copy()
        # # Convert to ZIP code strings: 
        # df_ny["zip_code_str"] = df_ny["zip_code"].astype(str).str.zfill(5)

        # if df_ny.empty:
        #     return pd.DataFrame()
        # return df_ny


        # --- Randomly sample up to 20 ZIP codes ---
        # df_ny_sample = df_ny.sample(n=min(20, len(df_ny)), random_state=42)
        # # --- Add ZIP code string column for downstream geocoding ---
        # df_ny_sample["zip_code_str"] = df_ny_sample["zip_code"].astype(str).str.zfill(5)
        # return df_ny_sample


    




# -------- Data Loaders --------
@st.cache_data(ttl=60)
def load_city_zip_data(city_abbr: str) -> pd.DataFrame:
    """Load median rent and per-capita income per ZIP."""
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
    df = sql_query(query)
    # For local testing, ensure correct column names exist
    if LOCAL_TESTING:
        df = df.rename(columns={
            "Median Rent": "median_rent",
            "Per Capita Income": "per_capita_income",
            "zipcode": "zip_code"
        })
        df["zip_code_str"] = df["zip_code"].astype(str).str.zfill(5)

    return df


# def get_zip_coordinates(df_zip: pd.DataFrame) -> pd.DataFrame:
#     """Add latitude and longitude to ZIP code dataframe using pgeocode."""
#     df_zip = df_zip.copy()
#     df_zip["zip_code_str"] = df_zip["zipcode"].astype(str).str.zfill(5)
    
    nomi = pgeocode.Nominatim("us")
    geo_df = nomi.query_postal_code(df_zip["zip_code_str"].tolist())
    
    df_zip["lat"] = geo_df["latitude"].values
    df_zip["lon"] = geo_df["longitude"].values
    df_zip = df_zip.dropna(subset=["lat", "lon"])
    
    # Compute affordability
    df_zip["monthly_income"] = df_zip["per_capita_income"] / 12
    df_zip["affordability_ratio"] = df_zip["median_rent"] / (0.3 * df_zip["monthly_income"])
    
    return df_zip
@st.cache_data(ttl=3600)
def get_zip_coordinates(df_zip: pd.DataFrame) -> pd.DataFrame:
    """Add latitude and longitude to ZIP code dataframe using pgeocode."""
    df_zip = df_zip.copy()
    
    # Use the correct column name
    # df_zip["zip_code_str"] = df_zip["zip_code"].astype(str).str.zfill(5)
    
    nomi = pgeocode.Nominatim("us")
    geo_df = nomi.query_postal_code(df_zip["zip_code_str"].tolist())
    
    df_zip["lat"] = geo_df["latitude"].values
    df_zip["lon"] = geo_df["longitude"].values
    df_zip = df_zip.dropna(subset=["lat", "lon"])
    
    # Compute affordability
    df_zip["monthly_income"] = df_zip["per_capita_income"] / 12
    df_zip["affordability_ratio"] = df_zip["median_rent"] / (0.3 * df_zip["monthly_income"])
    
    return df_zip

# -------- Page Title --------
st.title("🏙ZIP Code Affordability for Selected City")
st.write("ZIP code-level affordability ratios are displayed. Green = affordable, red = not affordable based on previously established rule (rent being 30%% of income)")

# -------- Select City --------
@st.cache_data(ttl=3600)
def get_available_cities():
    query = f"SELECT DISTINCT city FROM {TABLE_NAME} ORDER BY city"
    return sql_query(query)

available_cities = get_available_cities()["city"].tolist()
default_city = random.choice(available_cities) if available_cities else "NY"

with st.sidebar:
    st.header("City Selection")
    selected_city_abbr = st.selectbox(
        "Select a city:",
        options=available_cities,
        index=available_cities.index(default_city) if default_city in available_cities else 0,
        key="city_selectbox",
    )

selected_city_name = CITY_NAMES.get(selected_city_abbr, selected_city_abbr)

# -------- Load & Prepare Data --------
df_zip = load_city_zip_data(selected_city_abbr)
if df_zip.empty:
    st.warning(f"No ZIP code data found for {selected_city_name}.")
    st.stop()

df_zip_map = get_zip_coordinates(df_zip)
if df_zip_map.empty:
    st.warning("No ZIP codes could be geocoded. Please try another city.")
    st.stop()

# Convert ZIP code strings to integers for mapping
df_zip_map["zip_code_int"] = df_zip_map["zip_code_str"].astype(int)
# Normalize / clip affordability ratio for colors
df_zip_map["affordability_norm"] = (np.clip(df_zip_map["affordability_ratio"], 0, 2)/2)
# -------- Map --------

# Load GeoJSON for ZIP code boundaries
center_lat = df_zip_map["lat"].mean()
center_lon = df_zip_map["lon"].mean()

# geojson_url = "https://raw.githubusercontent.com/OpenDataDE/State-zip-code-GeoJSON/master/ny_new_york_zip_codes_geo.min.json"
gdf = gpd.read_file("cb_2018_us_zcta510_500k/cb_2018_us_zcta510_500k.shp")
gdf.to_file("us_zcta5.geojson", driver="GeoJSON")
with open("us_zcta5.geojson", "r") as f:
    zip_geojson = json.load(f)

# Red-Yellow-Green: red <1, yellow =1, green >1
colorscale = [
    [0.0, "red"],       # least affordable
    [0.5, "yellow"],  # borderline
    [1.0, "green"],     # affordable
]
colorbar_config = dict(
    title="Affordability Ratio",
    tickvals=[0.0, 0.25, 0.5, 0.75, 1.0],
    ticktext=["0", "0.5", "1.0", "1.5", "2.0"]
)

# Now pass the geojson correctly
fig_map = px.choropleth_mapbox(
    df_zip_map,
    geojson=zip_geojson,  # <-- this was None before
    locations="zip_code_int",
    featureidkey="properties.ZCTA5CE10",  # ensure this matches the GeoJSON field
    # Use norm instead to accomodate values.. 
    color="affordability_norm",
    color_continuous_scale=colorscale,
    # range_color=[df_zip_map["affordability_norm"].min(), df_zip_map["affordability_norm"].max()],
    range_color = [0, 1],
    hover_name="zip_code_str",
    hover_data={
        "median_rent": True,
        "monthly_income": True,
        "affordability_ratio": ":.2f"
    },
    mapbox_style="carto-positron",
    center={"lat": center_lat, "lon": center_lon},
    zoom=10,
    height=600
)
fig_map.update_layout(margin=dict(l=0, r=0, t=0, b=0),coloraxis_colorbar=colorbar_config)
st.plotly_chart(fig_map, use_container_width=True)

