# zip_map.py  (streamlit-cloud compatible version)

import streamlit as st
import numpy as np
import plotly.express as px
import pgeocode
import json
import requests

GEOJSON_URL = "https://raw.githubusercontent.com/OpenDataDE/State-zip-code-GeoJSON/master/us_zips.geojson"

@st.cache_data
def load_zip_geojson():
    response = requests.get(GEOJSON_URL)
    return response.json()

zip_geojson = load_zip_geojson()


def render_zip_map_for_city(zip_df):

    if zip_df.empty:
        st.warning("No ZIP-level data for this city.")
        return

    df = zip_df.copy()

    # Ensure ZIP string exists
    if "zip_code_str" not in df.columns:
        df["zip_code_str"] = df["zipcode"].astype(str).str.zfill(5)

    # ---- geocode ZIPs ----
    nomi = pgeocode.Nominatim("us")
    geo_df = nomi.query_postal_code(df["zip_code_str"].tolist())

    df["lat"] = geo_df["latitude"].values
    df["lon"] = geo_df["longitude"].values
    df = df.dropna(subset=["lat", "lon"])

    if df.empty:
        st.warning("ZIP codes could not be geocoded.")
        return

    df["affordability_ratio"] = df["afford_ratio_zip"]
    df["affordability_norm"] = np.clip(df["affordability_ratio"], 0, 2) / 2

    df["zip_code_int"] = df["zip_code_str"].astype(int)

    center_lat = df["lat"].mean()
    center_lon = df["lon"].mean()

    # ---- draw map ----
    colorscale = [
        [0.0, "red"],
        [0.5, "yellow"],
        [1.0, "green"],
    ]

    fig = px.choropleth_mapbox(
        df,
        geojson=zip_geojson,
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
            tickvals=[0, 0.5, 1],
            ticktext=["0", "1", "2+"],
        ),
    )

    st.plotly_chart(fig, use_container_width=True)
