import os
import json
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from zip_module import load_city_zip_data, get_zip_coordinates
from dataprep import load_data, make_city_view_data
from ui_components import income_control_panel


# ---------- Load data ----------
@st.cache_data
def get_data():
    return load_data()

df = get_data()

st.title("Design 3 – Price Affordability Finder")

# ---------- Sidebar: persona + income ----------
final_income, persona = income_control_panel()

# ---------- Year selector ----------
def year_selector(df: pd.DataFrame, key: str):
    years = sorted(df["year"].unique())
    return st.selectbox("Year", years, index=len(years) - 1, key=key)

top_col1, top_col2 = st.columns([1, 2])
with top_col1:
    selected_year = year_selector(df, key="year_main")
with top_col2:
    sort_option = st.selectbox(
        "Sort cities by",
        [
            "City name",
            "Price-to-income gap",
            "Price-to-income ratio",
            "Median sale price",
            "Per capita income",
        ],
        key="sort_main",
    )

# ---------- City selector (center, under year/sort) ----------
cities = sorted(df["city"].unique())
selected_city = st.selectbox(
    "Select a city",
    options=cities,
    index=0,
    key="city_main",
)

# ---------- ZIP-level data & map (price-to-income version) ----------
df_zip = load_city_zip_data(selected_city)
if "year" in df_zip.columns:
    df_zip = df_zip[df_zip["year"] == selected_year]

df_zip_map = get_zip_coordinates(df_zip)

# 读该城市的 GeoJSON
geojson_path = os.path.join(
    os.path.dirname(__file__), "city_geojson", f"{selected_city}.geojson"
)
if not os.path.exists(geojson_path):
    st.error(f"❌ GeoJSON file not found: {geojson_path}")
    st.stop()

with open(geojson_path, "r") as f:
    zip_geojson = json.load(f)

# Choropleth map：颜色基于 price_to_income_zip 归一化后的 affordability_norm
fig_map = px.choropleth_mapbox(
    df_zip_map,
    geojson=zip_geojson,
    locations="zip_code_int",
    featureidkey="properties.ZCTA5CE10",
    color="affordability_norm",
    color_continuous_scale=[
        [0.0, "green"],   # 更便宜（price-to-income 低）
        [0.5, "yellow"],
        [1.0, "red"],     # 更贵（price-to-income 高）
    ],
    range_color=[0, 1],
    hover_name="zip_code_str",
    hover_data={
        "median_sale_price": ":,.0f",
        "per_capita_income": ":,.0f",
        "price_to_income_zip": ":.2f",
    },
    mapbox_style="carto-positron",
    center={"lat": df_zip_map["lat"].mean(), "lon": df_zip_map["lon"].mean()},
    zoom=10,
    height=600
)
fig_map.update_layout(margin=dict(l=0, r=0, t=0, b=0))
st.plotly_chart(fig_map, use_container_width=True)

# ---------- Prepare city-level data (price-to-income version) ----------
city_data = make_city_view_data(
    df,
    annual_income=final_income,   # 现在不直接参与 ratio，只保留做 profile 用
    year=selected_year,
)

# 这里假设 dataprep.py 中已经生成：
#   - price_to_income
#   - price_to_income_gap
#   - affordable (True/False, ratio 低于整体 median 为 True)
dist = city_data["price_to_income_gap"].abs()
city_data["gap_for_plot"] = np.where(city_data["affordable"], -dist, dist)

# ---------- Sort ----------
if sort_option == "Price-to-income gap":
    sorted_data = city_data.sort_values("gap_for_plot", ascending=True)
elif sort_option == "Price-to-income ratio":
    sorted_data = city_data.sort_values("price_to_income", ascending=True)
elif sort_option == "Median sale price":
    sorted_data = city_data.sort_values("median_sale_price", ascending=False)
elif sort_option == "Per capita income":
    sorted_data = city_data.sort_values("Per Capita Income", ascending=False)
else:  # City name
    sorted_data = city_data.sort_values("city_clean")

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
            <p style="margin:0.1rem 0;"><strong>Housing budget (Rent):</strong> 30% of income</p>
            <p style="margin:0.1rem 0;"><strong>Max affordable rent:</strong> ≈ ${rent:,.0f} / month</p>
            <p style="margin:0.4rem 0 0.1rem 0;"><strong>Selected year:</strong> {year}</p>
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
    st.subheader("Price-to-income gap by city")

    # Bar chart for Price-to-Income Ratio
    fig = px.bar(
        sorted_data,
        x="city_clean",
        y="gap_for_plot",  # This now uses price_to_income_gap
        color="affordable",
        color_discrete_map={True: "green", False: "red"},
        labels={
            "city_clean": "City",
            "gap_for_plot": "Distance from median price-to-income "
                            "(− more affordable, + less affordable)",
        },
        hover_data={
            "city_clean": True,
            "median_sale_price": ":,.0f",
            "Per Capita Income": ":,.0f",
            "price_to_income": ":.2f",
        },
        height=500,
    )

    fig.update_layout(
        xaxis_tickangle=-45,
        margin=dict(l=20, r=20, t=40, b=80),
    )

    st.plotly_chart(fig, use_container_width=True)

# ------------ Split ------------
split = st.button("Split price-to-income chart")

if split:
    affordable_data = sorted_data[sorted_data["affordable"]]
    unaffordable_data = sorted_data[~sorted_data["affordable"]]

    st.subheader(f"Affordable Cities (Price-to-Income < {AFFORDABILITY_THRESHOLD})")
    fig_aff = px.bar(
        affordable_data,
        x="city_clean",
        y="gap_for_plot",  # This uses price_to_income_gap
        color="affordable",
        color_discrete_map={True: "green", False: "red"},
        labels={"city_clean": "City", "gap_for_plot": "Distance from median price-to-income"},
        hover_data={
            "city_clean": True,
            "median_sale_price": ":,.0f",
            "Per Capita Income": ":,.0f",
            "price_to_income": ":.2f",
        },
        height=380,
    )
    fig_aff.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig_aff, use_container_width=True)

    st.subheader(f"Unaffordable Cities (Price-to-Income ≥ {AFFORDABILITY_THRESHOLD})")
    fig_unaff = px.bar(
        unaffordable_data,
        x="city_clean",
        y="gap_for_plot",  # This uses price_to_income_gap
        color="affordable",
        color_discrete_map={True: "green", False: "red"},
        labels={"city_clean": "City", "gap_for_plot": "Distance from median price-to-income"},
        hover_data={
            "city_clean": True,
            "median_sale_price": ":,.0f",
            "Per Capita Income": ":,.0f",
            "price_to_income": ":.2f",
        },
       
