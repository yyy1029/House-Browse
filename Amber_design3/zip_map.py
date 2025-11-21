# zip_map.py — use OpenDataDE/State-zip-code-GeoJSON by state

import streamlit as st
import numpy as np
import plotly.express as px
import pgeocode
import requests

CITY_STATE = {
    "ATL": "ga_georgia",
    "ATX": "tx_texas",
    "BOS": "ma_massachusetts",
    "BWI": "md_maryland",
    "CHI": "il_illinois",
    "CIN": "oh_ohio",
    "CLT": "nc_north_carolina",
    "DAL": "tx_texas",
    "DC":  "dc_district_of_columbia",
    "DEN": "co_colorado",
    "DET": "mi_michigan",
    "HOU": "tx_texas",
    "LA":  "ca_california",
    "LV":  "nv_nevada",
    "MIA": "fl_florida",
    "MSP": "mn_minnesota",
    "NY":  "ny_new_york",
    "ORL": "fl_florida",
    "PDX": "or_oregon",
    "PGH": "pa_pennsylvania",
    "PHL": "pa_pennsylvania",
    "PHX": "az_arizona",
    "RIV": "ca_california",
    "SA":  "tx_texas",
    "SAC": "ca_california",
    "SD":  "ca_california",
    "SEA": "wa_washington",
    "SF":  "ca_california",
    "STL": "mo_missouri",
    "TPA": "fl_florida",
}

BASE_URL = "https://raw.githubusercontent.com/OpenDataDE/State-zip-code-GeoJSON/master/"


@st.cache_data(show_spinner=False)
def load_state_geojson(city_code: str):
    """
    根据城市缩写加载对应州的 GeoJSON。
    例如 SEA -> wa_washington_zip_codes_geo.min.json
    """
    state_prefix = CITY_STATE.get(city_code)
    if not state_prefix:
        st.error(f"No state mapping found for city code: {city_code}")
        return None

    url = f"{BASE_URL}{state_prefix}_zip_codes_geo.min.json"
    resp = requests.get(url, timeout=20)

    if not resp.ok:
        st.error(f"Failed to fetch geojson for {city_code} from {url}")
        return None

    try:
        return resp.json()
    except Exception as e:
        st.error(f"Failed to parse geojson for {city_code}: {e}")
        return None


def render_zip_map_for_city(zip_df, city_code: str):
   
    if zip_df.empty:
        st.warning("No ZIP-level data for this city.")
        return

    df = zip_df.copy()

    
    if "zip_code_str" not in df.columns:
        if "zipcode" in df.columns:
            df["zip_code_str"] = df["zipcode"].astype(str).str.zfill(5)
        else:
            st.error("zip_df must contain 'zipcode' column.")
            return

    # ---- geocode ZIPs ----
    nomi = pgeocode.Nominatim("us")
    geo_df = nomi.query_postal_code(df["zip_code_str"].tolist())

    df["lat"] = geo_df["latitude"].values
    df["lon"] = geo_df["longitude"].values
    df = df.dropna(subset=["lat", "lon"])
    if df.empty:
        st.warning("Unable to geocode ZIP codes for this city.")
        return


    if "afford_ratio_zip" not in df.columns:
        st.error("zip_df must contain 'afford_ratio_zip' column.")
        return

    df["affordability_ratio"] = df["afford_ratio_zip"]
    df["affordability_norm"] = np.clip(df["affordability_ratio"], 0, 2) / 2
    df["zip_code_int"] = df["zip_code_str"].astype(int)

    center_lat = df["lat"].mean()
    center_lon = df["lon"].mean()

    # ---- GeoJSON ----
    geojson = load_state_geojson(city_code)
    if geojson is None:
        return

    colorscale = [
        [0.0, "red"],
        [0.5, "yellow"],
        [1.0, "green"],
    ]

    fig = px.choropleth_mapbox(
        df,
        geojson=geojson,
        locations="zip_code_int",
        featureidkey="properties.ZCTA5CE10",
        color="affordability_norm",
        color_continuous_scale=colorscale,
        range_color=[0, 1],
        hover_name="zip_code_str",
        hover_data={
            "Median Rent": True,
            "Per Capita Income": True,
            "affordability_ratio": ":.2f",
        },
        mapbox_style="carto-positron",
        center={"lat": center_lat, "lon": center_lon},
        zoom=10,
        height=600,
    )

    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        coloraxis_colorbar=dict(
            title="Affordability Ratio",
            tickvals=[0.0, 0.5, 1.0],
            ticktext=["0", "1.0", "2.0+"],
        ),
    )

    st.plotly_chart(fig, use_container_width=True)
