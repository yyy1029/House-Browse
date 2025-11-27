# app.py

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import json
import os

from streamlit_plotly_events import plotly_events

from zip_module import load_city_zip_data, get_zip_coordinates
from dataprep import load_data, make_city_view_data, RATIO_COL, AFFORDABILITY_THRESHOLD
from ui_components import income_control_panel

# ---------- Global config ----------
st.set_page_config(page_title="Design 3 – Affordability Finder", layout="wide")
st.title("Design 3 – Affordability Finder")

# For ZIP map clipping
MAX_ZIP_RATIO_CLIP = 15.0


# ---------- Load data ----------
@st.cache_data
def get_data():
    return load_data()


df = get_data()

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
        ["City name", "Price-to-income ratio", "Median sale price", "Per capita income"],
        key="sort_main",
    )


# ---------- Prepare city-level data ----------
city_data = make_city_view_data(
    df,
    annual_income=final_income,
    year=selected_year,
    budget_pct=30,
)

# Build gap_for_plot (distance to threshold, signed)
gap = city_data[RATIO_COL] - AFFORDABILITY_THRESHOLD
dist = gap.abs()
city_data["gap_for_plot"] = np.where(city_data["affordable"], dist, -dist)

if "city_clean" not in city_data.columns:
    city_data["city_clean"] = city_data["city"]

# ---------- Sort city-level data ----------
if sort_option == "Price-to-income ratio":
    sorted_data = city_data.sort_values(RATIO_COL, ascending=True)
elif sort_option == "Median sale price":
    sorted_data = city_data.sort_values("Median Sale Price", ascending=False)
elif sort_option == "Per capita income":
    sorted_data = city_data.sort_values("Per Capita Income", ascending=False)
else:  # City name
    sorted_data = city_data.sort_values("city_clean")

# Only for profile card display
max_rent = final_income * 0.3 / 12.0


# ---------- Main layout: left (profile + bar) / right (map) ----------
main_left, main_right = st.columns([1.1, 1.6])

# ========= LEFT: profile + city bar chart =========
with main_left:
    # Profile card
    st.markdown(
        """
        <div style="
            padding: 1.2rem 1.4rem;
            background-color: #f7f7fb;
            border-radius: 12px;
            border: 1px solid #e0e0f0;
            margin-bottom: 1rem;
            ">
            <h3 style="margin-top:0;margin-bottom:0.6rem;">Profile &amp; budget</h3>
            <p style="margin:0.1rem 0;"><strong>Profile:</strong> {persona}</p>
            <p style="margin:0.1rem 0;"><strong>Annual income:</strong> ${income:,}</p>
            <p style="margin:0.1rem 0;"><strong>Housing budget (Rent):</strong> 30% of income (for reference)</p>
            <p style="margin:0.1rem 0;"><strong>Max affordable rent:</strong> ≈ ${rent:,.0f} / month</p>
            <p style="margin:0.4rem 0 0.1rem 0;"><strong>Selected year:</strong> {year}</p>
            <p style="margin:0.1rem 0;font-size:0.9rem;color:#555;">
                City-level affordability uses <em>Median Sale Price / Per Capita Income</em>.
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

    st.subheader("Price-to-income ratio by city")

    # ---- build the figure (样子和你要的那张一样) ----
    fig_city = px.bar(
        sorted_data,
        x="city_clean",
        y=RATIO_COL,
        color="affordable",
        color_discrete_map={True: "green", False: "red"},
        labels={
            "city_clean": "City",
            RATIO_COL: "Price-to-income ratio (Median Sale Price / Per Capita Income)",
        },
        hover_data={
            "city_clean": True,
            "Median Sale Price": ":,.0f",
            "Per Capita Income": ":,.0f",
            RATIO_COL: ":.2f",
        },
        height=500,
    )

    fig_city.add_hline(
        y=AFFORDABILITY_THRESHOLD,
        line_dash="dash",
        line_color="black",
        annotation_text=f"Threshold = {AFFORDABILITY_THRESHOLD:.1f}",
        annotation_position="top left",
    )

    fig_city.update_layout(
        xaxis_tickangle=-45,
        margin=dict(l=20, r=20, t=40, b=80),
    )

    # ---- 用 plotly_events 来“画图 + 捕捉点击”，不再额外 st.plotly_chart ----
    clicked = plotly_events(
        fig_city,
        click_event=True,
        hover_event=False,
        select_event=False,
        key="bar_chart_city",
        override_height=500,
    )
    if clicked:
        # x value is city_clean
        st.session_state.selected_city = clicked[0]["x"]

    # Split chart button（保持不变）
    split = st.button("Split affordability chart")
    if split:
        affordable_data = sorted_data[sorted_data["affordable"]].sort_values(
            RATIO_COL, ascending=True
        )
        unaffordable_data = sorted_data[~sorted_data["affordable"]].sort_values(
            RATIO_COL, ascending=False
        )

        st.subheader(f"More affordable cities (ratio ≤ {AFFORDABILITY_THRESHOLD:.1f})")
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
                "Median Sale Price": ":,.0f",
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

        st.subheader(f"Less affordable cities (ratio > {AFFORDABILITY_THRESHOLD:.1f})")
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
                "Median Sale Price": ":,.0f",
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


# ========= RIGHT: ZIP-level map (zoom-in after click) =========
with main_right:
    st.subheader("ZIP-code price-to-income map")

    city_clicked = st.session_state.get("selected_city")

    if city_clicked is None:
        st.info("Click a city bar on the left to see ZIP-level details here.")
    else:
        st.markdown(f"**{city_clicked} – ZIP-level affordability (Price-to-Income)**")

        # Load ZIP-level data for the clicked city and selected year
        df_zip = load_city_zip_data(city_clicked)
        if "year" in df_zip.columns:
            df_zip = df_zip[df_zip["year"] == selected_year]

        if df_zip.empty:
            st.info("No ZIP-level data available for this city/year.")
        else:
            # Enrich with lat/lon
            df_zip_map = get_zip_coordinates(df_zip)

            # Detect price and income columns
            price_col = None
            income_col = None

            if "median_sale_price" in df_zip_map.columns:
                price_col = "median_sale_price"
            elif "Median Sale Price" in df_zip_map.columns:
                price_col = "Median Sale Price"

            if "per_capita_income" in df_zip_map.columns:
                income_col = "per_capita_income"
            elif "Per Capita Income" in df_zip_map.columns:
                income_col = "Per Capita Income"

            if price_col is None or income_col is None:
                st.error("Sale price or income columns not found in ZIP-level data.")
            else:
                denom_zip = df_zip_map[income_col].replace(0, np.nan)
                df_zip_map[RATIO_COL] = df_zip_map[price_col] / denom_zip
                df_zip_map["ratio_for_map"] = df_zip_map[RATIO_COL].clip(
                    0, MAX_ZIP_RATIO_CLIP
                )

                # Load city GeoJSON
                geojson_path = os.path.join(
                    os.path.dirname(__file__),
                    "city_geojson",
                    f"{city_clicked}.geojson",
                )

                if not os.path.exists(geojson_path):
                    st.error(f"GeoJSON file not found: {geojson_path}")
                else:
                    with open(geojson_path, "r") as f:
                        zip_geojson = json.load(f)

                    fig_map = px.choropleth_mapbox(
                        df_zip_map,
                        geojson=zip_geojson,
                        locations="zip_code_int",
                        featureidkey="properties.ZCTA5CE10",  # adjust if needed
                        color="ratio_for_map",
                        color_continuous_scale="RdYlGn_r",
                        range_color=[0, MAX_ZIP_RATIO_CLIP],
                        hover_name="zip_code_str",
                        hover_data={
                            price_col: ":,.0f",
                            income_col: ":,.0f",
                            RATIO_COL: ":.2f",
                        },
                        mapbox_style="carto-positron",
                        center={
                            "lat": df_zip_map["lat"].mean(),
                            "lon": df_zip_map["lon"].mean(),
                        },
                        zoom=10,
                        height=500,
                    )

                    fig_map.update_layout(
                        margin=dict(l=0, r=0, t=0, b=0),
                        coloraxis_colorbar=dict(
                            title="Price-to-income ratio",
                            tickformat=".1f",
                        ),
                    )

                    st.plotly_chart(
                        fig_map,
                        use_container_width=True,
                        config={"scrollZoom": True},
                    )
