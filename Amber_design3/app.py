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

st.markdown(
    """
    Use this tool to **compare cities by house price-to-income ratio**,  
    then **click a bar** to zoom into ZIP-code details for that city.
    """
)

# For ZIP map clipping
MAX_ZIP_RATIO_CLIP = 15.0


# ---------- Load data ----------
@st.cache_data
def get_data():
    return load_data()


df = get_data()

# ---------- Sidebar: persona + income ----------
final_income, persona = income_control_panel()

# ---------- Top controls: year + sort ----------
def year_selector(df: pd.DataFrame, key: str):
    years = sorted(df["year"].unique())
    return st.selectbox("Year", years, index=len(years) - 1, key=key)


controls_col1, controls_col2 = st.columns([1, 2])
with controls_col1:
    selected_year = year_selector(df, key="year_main")

with controls_col2:
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

# city_data already has RATIO_COL and "affordable"
gap = city_data[RATIO_COL] - AFFORDABILITY_THRESHOLD
dist = gap.abs()
city_data["gap_for_plot"] = np.where(city_data["affordable"], dist, -dist)

if "city_clean" not in city_data.columns:
    city_data["city_clean"] = city_data["city"]

# sort
if sort_option == "Price-to-income ratio":
    sorted_data = city_data.sort_values(RATIO_COL, ascending=True)
elif sort_option == "Median sale price":
    sorted_data = city_data.sort_values("Median Sale Price", ascending=False)
elif sort_option == "Per capita income":
    sorted_data = city_data.sort_values("Per Capita Income", ascending=False)
else:  # City name
    sorted_data = city_data.sort_values("city_clean")

# profile max rent (for display only)
max_rent = final_income * 0.3 / 12.0


# =====================================================================
#   SECTION 1 – Profile + dataset summary
# =====================================================================
st.markdown("### 1. Your profile and dataset overview")

sec1_col1, sec1_col2 = st.columns([1.1, 1.2])

with sec1_col1:
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
            <p style="margin:0.1rem 0;"><strong>Max affordable rent:</strong> ≈ ${rent:,.0f} / month</p>
            <p style="margin:0.4rem 0 0.1rem 0;"><strong>Selected year:</strong> {year}</p>
            <p style="margin:0.1rem 0;font-size:0.9rem;color:#555;">
                City affordability here uses
                <em>Median Sale Price / Per Capita Income</em>
                (lower = more affordable at the city level).
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

with sec1_col2:
    total_cities = len(city_data)
    num_affordable = int((city_data["affordable"]).sum())
    median_ratio = city_data[RATIO_COL].median()

    st.markdown(
        f"""
        **Dataset snapshot – {selected_year}**

        - Cities in dataset: **{total_cities}**
        - Cities with price-to-income ratio ≤ **{AFFORDABILITY_THRESHOLD:.1f}**:  
          **{num_affordable}** ({num_affordable / total_cities:,.0%} of all cities)
        - Median city ratio: **{median_ratio:,.2f}**

        You can treat this threshold as a rough cut where  
        house prices above **{AFFORDABILITY_THRESHOLD:.1f}×** local per-capita income  
        start to look less affordable.
        """
    )


# =====================================================================
#   SECTION 2 – City bar chart (click to drill down)
# =====================================================================
st.markdown("### 2. Compare cities by price-to-income ratio")

# Make a label for color legend (more readable than bare True/False)
sorted_data["afford_label"] = np.where(
    sorted_data["affordable"], "Affordable (≤ threshold)", "Less affordable (> threshold)"
)

fig_city = px.bar(
    sorted_data,
    x="city_clean",
    y=RATIO_COL,
    color="afford_label",
    color_discrete_map={
        "Affordable (≤ threshold)": "green",
        "Less affordable (> threshold)": "red",
    },
    labels={
        "city_clean": "City",
        # RATIO_COL: "Price-to-income ratio (Median Sale Price / Per Capita Income)",
        "afford_label": "Affordability (dataset rule)",
    },
    hover_data={
        "city_clean": True,
        "Median Sale Price": ":,.0f",
        "Per Capita Income": ":,.0f",
        RATIO_COL: ":.2f",
    },
    height=520,
)

# Horizontal line for dataset threshold
fig_city.add_hline(
    y=AFFORDABILITY_THRESHOLD,
    line_dash="dash",
    line_color="black",
    annotation_text=f"Threshold = {AFFORDABILITY_THRESHOLD:.1f}",
    annotation_position="top left",
)

# Layout tuning for aesthetics
fig_city.update_layout(
    xaxis_tickangle=-45,
    margin=dict(l=20, r=20, t=40, b=80),
    bargap=0.05,
    bargroupgap=0.0,
)

# Make bars nice and thick
fig_city.update_traces(width=0.8)

st.caption("Tip: click a bar to see ZIP-level details for that city below.")

# Draw + listen in one step
clicked = plotly_events(
    fig_city,
    click_event=True,
    hover_event=True,
    select_event=False,
    key=f"bar_chart_city_{selected_year}_{sort_option}",
    override_height=520,
)

if clicked:
    st.session_state.selected_city = clicked[0]["x"]


# Optional: split chart (below main bar)
with st.expander("Show separate charts for more / less affordable cities"):
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
        color="afford_label",
        color_discrete_map={
            "Affordable (≤ threshold)": "green",
            "Less affordable (> threshold)": "red",
        },
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
        height=360,
    )
    fig_aff.add_hline(
        y=AFFORDABILITY_THRESHOLD,
        line_dash="dash",
        line_color="black",
    )
    fig_aff.update_layout(xaxis_tickangle=-45, bargap=0.1)
    st.plotly_chart(fig_aff, use_container_width=True)

    st.subheader(f"Less affordable cities (ratio > {AFFORDABILITY_THRESHOLD:.1f})")
    fig_unaff = px.bar(
        unaffordable_data,
        x="city_clean",
        y=RATIO_COL,
        color="afford_label",
        color_discrete_map={
            "Affordable (≤ threshold)": "green",
            "Less affordable (> threshold)": "red",
        },
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
        height=360,
    )
    fig_unaff.add_hline(
        y=AFFORDABILITY_THRESHOLD,
        line_dash="dash",
        line_color="black",
    )
    fig_unaff.update_layout(xaxis_tickangle=-45, bargap=0.1)
    st.plotly_chart(fig_unaff, use_container_width=True)


# =====================================================================
#   SECTION 3 – ZIP-level map for selected city
# =====================================================================
st.markdown("### 3. Zoom into ZIP-code details")

city_clicked = st.session_state.get("selected_city")

if city_clicked is None:
    st.info("Click a city bar above to see its ZIP-code price-to-income map here.")
else:
    st.markdown(f"#### {city_clicked} – ZIP-level affordability (Price-to-Income)")

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
            df_zip_map["ratio_for_map"] = df_zip_map[RATIO_COL].clip(0, MAX_ZIP_RATIO_CLIP)

            # Layout: left small stats, right map
            map_col1, map_col2 = st.columns([1, 2])

            with map_col1:
                city_row = city_data[city_data["city_clean"] == city_clicked]
                if not city_row.empty:
                    row = city_row.iloc[0]
                    st.markdown(
                        f"""
                        **City snapshot – {city_clicked} ({selected_year})**

                        - Median sale price: **${row['Median Sale Price']:,.0f}**
                        - Per-capita income: **${row['Per Capita Income']:,.0f}**
                        - City price-to-income ratio: **{row[RATIO_COL]:.2f}**
                        - Dataset affordability: **{"✅ Affordable" if row["affordable"] else "⚠️ Less affordable"}**
                        """
                    )
                st.caption(
                    "On the right, ZIPs with lower ratios are more affordable relative "
                    "to local incomes (green), higher ratios are less affordable (red)."
                )

            with map_col2:
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
                        featureidkey="properties.ZCTA5CE10",
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
                        height=520,
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
