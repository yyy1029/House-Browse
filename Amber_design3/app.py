# app.py

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import json
import os

from zip_module import load_city_zip_data, get_zip_coordinates
from dataprep import load_data, make_city_view_data
from ui_components import income_control_panel

# ---------- Global config ----------
st.set_page_config(page_title="Design 3 – Affordability Finder", layout="wide")
st.title("Design 3 – Affordability Finder")

# price-to-income
RATIO_COL = "price_to_income_ratio"           
AFFORDABILITY_THRESHOLD = 0.30            
MAX_ZIP_RATIO_CLIP = 0.80                 


# ---------- Load data ----------
@st.cache_data
def get_data():
    return load_data()

df = get_data()

# ---------- Sidebar: persona + income ----------
final_income, persona = income_control_panel()

# ========== year selector ==========
def year_selector(df: pd.DataFrame, key: str):
    years = sorted(df["year"].unique())
    return st.selectbox("Year", years, index=len(years) - 1, key=key)

top_col1, top_col2 = st.columns([1, 2])
with top_col1:
    selected_year = year_selector(df, key="year_main")

with top_col2:
    sort_option = st.selectbox(
        "Sort cities by",
        ["City name", "Price-to-income ratio", "Median rent", "Per capita income"],
        key="sort_main",
    )

# —— city selector —— 
cities = sorted(df["city"].unique())
selected_city = st.selectbox(
    "Select a city",
    options=cities,
    index=0,
    key="city_main",
)

# ========== ZIP  ==========
df_zip = load_city_zip_data(selected_city)
if "year" in df_zip.columns:
    df_zip = df_zip[df_zip["year"] == selected_year]


df_zip_map = get_zip_coordinates(df_zip)


if not df_zip_map.empty:
    
    if "monthly_income" not in df_zip_map.columns and "per_capita_income" in df_zip_map.columns:
        df_zip_map["monthly_income"] = df_zip_map["per_capita_income"] / 12.0

    denom = df_zip_map["monthly_income"].replace(0, np.nan)
    df_zip_map[RATIO_COL] = df_zip_map["median_rent"] / denom

   
    df_zip_map["ratio_for_map"] = df_zip_map[RATIO_COL].clip(0, MAX_ZIP_RATIO_CLIP)


geojson_path = os.path.join(
    os.path.dirname(__file__),
    "city_geojson",
    f"{selected_city}.geojson",
)

if not os.path.exists(geojson_path):
    st.error(f"❌ GeoJSON file not found: {geojson_path}")
    st.stop()

with open(geojson_path, "r") as f:
    zip_geojson = json.load(f)


if not df_zip_map.empty:
    fig_map = px.choropleth_mapbox(
        df_zip_map,
        geojson=zip_geojson,
        locations="zip_code_int",
        featureidkey="properties.ZCTA5CE10",  
        color="ratio_for_map",
        color_continuous_scale="RdYlGn_r",   
        range_color=[0, MAX_ZIP_RATIO_CLIP],
        hover_name="zip_code_str",
        hover_data={
            "median_rent": ":,.0f",
            "monthly_income": ":,.0f",
            RATIO_COL: ":.2f",
        },
        mapbox_style="carto-positron",
        center={
            "lat": df_zip_map["lat"].mean(),
            "lon": df_zip_map["lon"].mean(),
        },
        zoom=10,
        height=600,
    )

    fig_map.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        coloraxis_colorbar=dict(
            title="Rent-to-income ratio",
            tickformat=".2f",
        ),
    )

    st.subheader("ZIP-level rent price-to-income ratio")
    st.plotly_chart(fig_map, use_container_width=True)
else:
    st.info("No ZIP-level data available for this city/year.")


# ---------- Prepare city-level data ----------
city_data = make_city_view_data(
    df,
    annual_income=final_income,    
    year=selected_year,
    budget_pct=30,
)


city_data["monthly_income_pc"] = city_data["Per Capita Income"] / 12.0
denom_city = city_data["monthly_income_pc"].replace(0, np.nan)
city_data[RATIO_COL] = city_data["Median Rent"] / denom_city


city_data["affordable"] = city_data[RATIO_COL] <= AFFORDABILITY_THRESHOLD


gap = city_data[RATIO_COL] - AFFORDABILITY_THRESHOLD
dist = gap.abs()
city_data["gap_for_plot"] = np.where(city_data["affordable"], dist, -dist)


if "city_clean" not in city_data.columns:
    city_data["city_clean"] = city_data["city"]

# ---------- Sort ----------
if sort_option == "Price-to-income ratio":
    sorted_data = city_data.sort_values(RATIO_COL, ascending=True)
elif sort_option == "Median rent":
    sorted_data = city_data.sort_values("Median Rent", ascending=False)
elif sort_option == "Per capita income":
    sorted_data = city_data.sort_values("Per Capita Income", ascending=False)
else:  # City name
    sorted_data = city_data.sort_values("city_clean")


max_rent = final_income * 0.3 / 12.0

# ---------- Layout: left profile card + main right ----------
col1, col2 = st.columns([1, 2])

with col1:
    # Profile 
    st.markdown(
        """
        <div style="
            padding: 1.2rem 1.4rem;
            background-color: #f7f7fb;
            border-radius: 12px;
            border: 1px solid #e0e0f0;
            ">
            <h3 style="margin-top:0;margin-bottom:0.6rem;">Profile &amp; budget</h3>
            <p style="margin:0.1rem 0;"><strong>Profile:</strong> {persona}</p>
            <p style="margin:0.1rem 0;"><strong>Annual income:</strong> ${income:,}</p>
            <p style="margin:0.1rem 0;"><strong>Housing budget:</strong> 30% of income</p>
            <p style="margin:0.1rem 0;"><strong>Max affordable rent:</strong> ≈ ${rent:,.0f} / month</p>
            <p style="margin:0.4rem 0 0.1rem 0;"><strong>Selected year:</strong> {year}</p>
            <p style="margin:0.1rem 0;font-size:0.9rem;color:#555;">
                City-level affordability uses <em>rent / per-capita monthly income</em>.
            </p>
        </div>
        """.format(
            persona=persona,
            income=int(final_income),
            rent=max_rent,
            year=selected_year,
        ),
        unsafe_allow_html=True,
    )

with col2:
    st.subheader("Rent price-to-income ratio by city")

    
    fig = px.bar(
        sorted_data,
        x="city_clean",
        y=RATIO_COL,
        color="affordable",
        color_discrete_map={True: "green", False: "red"},
        labels={
            "city_clean": "City",
            RATIO_COL: "Price-to-income ratio (monthly rent / monthly per-capita income)",
        },
        hover_data={
            "city_clean": True,
            "Median Rent": ":,.0f",
            "Per Capita Income": ":,.0f",
            RATIO_COL: ":.2f",
        },
        height=500,
    )

 
    fig.add_hline(
        y=AFFORDABILITY_THRESHOLD,
        line_dash="dash",
        line_color="black",
        annotation_text=f"Threshold = {AFFORDABILITY_THRESHOLD:.2f}",
        annotation_position="top left",
    )

    fig.update_layout(
        xaxis_tickangle=-45,
        margin=dict(l=20, r=20, t=40, b=80),
    )

    st.plotly_chart(fig, use_container_width=True)

# ------------ Split ------------
split = st.button("Split affordability chart")

if split:
    affordable_data = sorted_data[sorted_data["affordable"]].sort_values(RATIO_COL, ascending=True)
    unaffordable_data = sorted_data[~sorted_data["affordable"]].sort_values(RATIO_COL, ascending=False)

    st.subheader(f"More affordable cities (ratio ≤ {AFFORDABILITY_THRESHOLD:.2f})")
    fig_aff = px.bar(
        affordable_data,
        x="city_clean",
        y=RATIO_COL,
        color="affordable",
        color_discrete_map={True: "green", False: "red"},
        labels={
            "city_clean": "City",
            RATIO_COL: "Price-to-income ratio",
        },
        hover_data={
            "city_clean": True,
            "Median Rent": ":,.0f",
            "Per Capita Income": ":,.0f",
            RATIO_COL: ":.2f",
        },
        height=380,
    )
    fig_aff.add_hline(
        y=AFFORDABILITY_THRESHOLD,
        line_dash="dash",
        line_color="black",
    )
    fig_aff.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig_aff, use_container_width=True)

    st.subheader(f"Less affordable cities (ratio > {AFFORDABILITY_THRESHOLD:.2f})")
    fig_unaff = px.bar(
        unaffordable_data,
        x="city_clean",
        y=RATIO_COL,
        color="affordable",
        color_discrete_map={True: "green", False: "red"},
        labels={
            "city_clean": "City",
            RATIO_COL: "Price-to-income ratio",
        },
        hover_data={
            "city_clean": True,
            "Median Rent": ":,.0f",
            "Per Capita Income": ":,.0f",
            RATIO_COL: ":.2f",
        },
        height=380,
    )
    fig_unaff.add_hline(
        y=AFFORDABILITY_THRESHOLD,
        line_dash="dash",
        line_color="black",
    )
    fig_unaff.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig_unaff, use_container_width=True)
