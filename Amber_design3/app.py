# app.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import os
import json

from streamlit_plotly_events import plotly_events
from zip_module import load_city_zip_data, get_zip_coordinates
from dataprep import load_data, make_city_view_data
from ui_components import income_control_panel


# ---------- Load data ----------
@st.cache_data
def get_data():
    return load_data()

df = get_data()

st.title("Design 3 – Affordability Finder")


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
        ["City name", "Affordability gap", "Median rent", "Per capita income"],
        key="sort_main",
    )


# ---------- Prepare city-level data ----------
city_data = make_city_view_data(
    df,
    annual_income=final_income,
    year=selected_year,
    budget_pct=30,
)

# gap_for_plot
dist = city_data["afford_gap"].abs()
city_data["gap_for_plot"] = np.where(city_data["affordable"], dist, -dist)

# Sort
if sort_option == "Affordability gap":
    sorted_data = city_data.sort_values("gap_for_plot", ascending=True)
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
    st.subheader("Affordability gap by city")

    # ---- 主城市柱状图（保持你原来的样式） ----
    fig = px.bar(
        sorted_data,
        x="city_clean",
        y="gap_for_plot",
        color="affordable",
        color_discrete_map={True: "green", False: "red"},
        labels={
            "city_clean": "City",
            "gap_for_plot": "Distance from affordability boundary "
                            "(+ affordable, − unaffordable)",
        },
        hover_data={
            "city_clean": True,
            "Median Rent": ":.0f",
            "Per Capita Income": ":.0f",
            "afford_gap": ":.2f",
        },
        height=500,
    )
    fig.update_layout(
        xaxis_tickangle=-45,
        margin=dict(l=20, r=20, t=40, b=80),
    )

    # 先画图
    st.plotly_chart(fig, use_container_width=True)

    # ---- 1. 捕获点击事件：点哪根柱子，就选哪个城市 ----
    clicked = plotly_events(
        fig,
        click_event=True,
        hover_event=False,
        select_event=False,
        key="city_bar_click",
    )

    # ---- 2. 主区域城市选择器（兜底 & 手动切换） ----
    cities_main = sorted(sorted_data["city_clean"].unique())
    _default = st.session_state.get("selected_city", cities_main[0])
    if clicked:
        _default = clicked[0].get("x", _default)

    selected_city = st.selectbox(
        "Select a city",
        options=cities_main,
        index=cities_main.index(_default) if _default in cities_main else 0,
        key="city_main_top",
    )
    st.session_state["selected_city"] = selected_city

    # ---- 3. 在柱状图下方渲染该城市的 ZIP 地图 ----
    try:
        # 取该城市 & 年份的 ZIP 数据
        df_zip = load_city_zip_data(selected_city)
        if "year" in df_zip.columns:
            df_zip = df_zip[df_zip["year"] == selected_year]

        df_zip_map = get_zip_coordinates(df_zip)

        if df_zip_map is None or df_zip_map.empty:
            st.info("No ZIP code data for this city/year.")
        else:
            # 读对应城市的 geojson（例如 city_geojson/CHI.geojson）
            geojson_path = os.path.join(
                os.path.dirname(__file__),
                "city_geojson",
                f"{selected_city}.geojson",
            )
            if not os.path.exists(geojson_path):
                st.warning(f"GeoJSON not found: {geojson_path}")
            else:
                with open(geojson_path, "r") as f:
                    zip_geojson = json.load(f)

                fig_map = px.choropleth_mapbox(
                    df_zip_map,
                    geojson=zip_geojson,
                    locations="zip_code_int",
                    featureidkey="properties.ZCTA5CE10",  # 若不匹配再改
                    color="affordability_norm",
                    color_continuous_scale=[[0.0, "red"], [0.5, "yellow"], [1.0, "green"]],
                    range_color=[0, 1],
                    hover_name="zip_code_str",
                    hover_data={
                        "median_rent": True,
                        "monthly_income": True,
                        "affordability_ratio": ":.2f",
                    },
                    mapbox_style="carto-positron",
                    center={
                        "lat": df_zip_map["lat"].mean(),
                        "lon": df_zip_map["lon"].mean(),
                    },
                    zoom=10,
                    height=600,
                )
                fig_map.update_layout(margin=dict(l=0, r=0, t=0, b=0))
                st.plotly_chart(fig_map, use_container_width=True)
    except Exception as e:
        st.error("Failed to render ZIP map for the selected city.")
        st.exception(e)


# ------------ Split（保持你原来的逻辑和样式）------------
split = st.button("Split affordability chart")

if split:
    affordable_data = sorted_data[sorted_data["affordable"]]
    unaffordable_data = sorted_data[~sorted_data["affordable"]]

    st.subheader("Affordable cities (green, above 0)")
    fig_aff = px.bar(
        affordable_data,
        x="city_clean",
        y="gap_for_plot",
        color="affordable",
        color_discrete_map={True: "green", False: "red"},
        labels={
            "city_clean": "City",
            "gap_for_plot": "Distance from affordability boundary",
        },
        hover_data={
            "city_clean": True,
            "Median Rent": ":.0f",
            "Per Capita Income": ":.0f",
            "afford_gap": ":.2f",
        },
        height=380,
    )
    fig_aff.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig_aff, use_container_width=True)

    st.subheader("Unaffordable cities (red, below 0)")
    fig_unaff = px.bar(
        unaffordable_data,
        x="city_clean",
        y="gap_for_plot",
        color="affordable",
        color_discrete_map={True: "green", False: "red"},
        labels={
            "city_clean": "City",
            "gap_for_plot": "Distance from affordability boundary",
        },
        hover_data={
            "city_clean": True,
            "Median Rent": ":.0f",
            "Per Capita Income": ":.0f",
            "afford_gap": ":.2f",
        },
        height=380,
    )
    fig_unaff.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig_unaff, use_container_width=True)
