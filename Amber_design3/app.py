import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import json
import os
import time 

# --- RESTORED IMPORTS ---
from zip_module import load_city_zip_data, get_zip_coordinates
from dataprep import load_data, make_city_view_data, RATIO_COL, AFFORDABILITY_THRESHOLD, apply_income_filter, AFFORDABILITY_CATEGORIES, AFFORDABILITY_COLORS, classify_affordability, make_zip_view_data
from ui_components import income_control_panel, persona_income_slider, render_affordability_summary_card

st.markdown("""
    <style>
        .css-1aumxhk { font-size: 14px; }  
        .css-1l0j7j4 { font-size: 14px; }  
        .block-container { padding-top: 1rem; padding-bottom: 1rem; } 
    </style>
""", unsafe_allow_html=True)

# ---------- Global config ----------
st.set_page_config(page_title="Design 3 – Price Affordability Finder", layout="wide")
st.title("Design 3 – Price Affordability Finder")

# --- HTML INTRO BLOCK ---
st.markdown(
    """
    <div style="border-top: 1px solid #e6e6e6; padding: 10px 0; margin-bottom: 20px;">
    Use this tool to allow users to compare cities by <strong> PTI (price-to-income ratio) </strong> and select metro areas of interest to explore ZIP-code level details.<br>
    <strong>PTI Ratio: </strong>
    <span style="background-color: #f0f2f6; padding: 2px 6px; border-radius: 4px;">
            <strong>Median Sale Price / Household Income</strong>
    </span><br>
    <small>Lower ratios indicate better affordability. 
    In this dashboard, cities with a ratio &le; 3.0 are classified as <strong>"Affordable"</strong>.
    Those with a ratio between 3.1 to 4.0 inclusive are classified as <strong>"Moderately Unaffordable"</strong>.
    Those with a ratio between 4.1 to 5.0 inclusive are classified as <strong>"Seriously Unaffordable"</strong>.
    Those with a ratio between 5.1 to 8.9 inclusive are classified as <strong>"Severely Unaffordable"</strong>.
    Those with a ratios &ge; 9.0 are classified as <strong>"Impossibly Unaffordable"</strong></small>.
    </div>
    """,
    unsafe_allow_html=True
)

# Inject CSS
st.markdown(
    """
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css">
    <style>
    [data-testid="stAlert"] { display: none !important; }
    </style>
    """,
    unsafe_allow_html=True
)

MAX_ZIP_RATIO_CLIP = 15.0

# ---------- Function Definitions ----------
def year_selector(df: pd.DataFrame, key: str):
    years = sorted(df["year"].unique())
    if not years:
        return None
        
    # 1. Render the label manually with bigger font
    st.markdown("""
        <div style="font-size: 18px; font-weight: 600; margin-bottom: 5px;">
            Select Year
        </div>
    """, unsafe_allow_html=True)
    
    # 2. Render the selectbox with the label visible
    return st.selectbox(
        "Select Year", 
        years, 
        index=len(years) - 1, 
        key=key, 
        label_visibility="visible" 
    )

@st.cache_data(ttl=3600*24)
def get_data_cached():
    return load_data()

# ---------- Layout Setup ----------

# 1. Calculation Pre-requisites
final_income, persona = income_control_panel()
max_affordable_price = AFFORDABILITY_THRESHOLD * final_income
df_filtered_by_income = apply_income_filter(df, final_income)

# Calculate Histories
df_history = calculate_median_ratio_history(df)
df_prop_history = calculate_category_proportions_history(df)

# =====================================================================
#   LAYOUT SETUP
# =====================================================================

# Adjust the layout structure for a more logical flow

header_row_main, header_row_year = st.columns([4, 1])  # Middle Header
main_col_left, main_col_right = st.columns([2, 3])  # Main Content

# =====================================================================
#   SECTION 1: HEADER & YEAR SELECTION
# =====================================================================

# Render year selection widget at the top
with header_row_year:
    selected_year = year_selector(df, key="year_main_selector") 

# --- Logic Safety Check ---
if selected_year is None:
    selected_year = df["year"].max()

# Render Header Text
with header_row_main:
    st.markdown("""
        <h3 style="margin-top: -5px; padding-top: 0;">
            Bar Chart and User Input ZIP-Code Map
        </h3>
    """, unsafe_allow_html=True)
    st.markdown("""The left column allows users to get an idea of how the PTI (price-to-income) ratio differs across the different 
    metro areas. The right column allows users to view details about affordable ZIP codes based on the current income. 
    The colors on the ZIP-code map indicate affordability relative to the maximum affordable price. **Adjust the year 
    the data is being displayed using the year selector.**""")


# =====================================================================
#   SECTION 2: DATA CALCULATION
# =====================================================================

# Prepare data for plotting
city_data = make_city_view_data(df, annual_income=final_income, year=selected_year, budget_pct=30)

# Apply Column Fixes
if not city_data.empty:
    city_data["affordability_rating"] = city_data[RATIO_COL].apply(classify_affordability)
    gap = city_data[RATIO_COL] - AFFORDABILITY_THRESHOLD
    dist = gap.abs()
    city_data["gap_for_plot"] = np.where(city_data["affordable"], dist, -dist)


# =====================================================================
#   SECTION 3: CITY BAR CHART
# =====================================================================

# --- LEFT COLUMN: CITY BAR CHART ---
with main_col_left:
    with st.expander("Affordability Ranking", expanded=True):  # expanded=True makes it expanded by default
        st.markdown("#### Metro Area Affordability Ranking")

        if city_data.empty:
            st.warning(f"No data available for {selected_year}.")
        else:
            unique_city_pairs = city_data[["city", "city_full"]].drop_duplicates().sort_values("city_full")
            full_to_clean_city_map = pd.Series(unique_city_pairs["city"].values, index=unique_city_pairs["city_full"]).to_dict()

            selected_full_metros = st.multiselect(
                "Filter Metro Areas on the bar chart below (all selected by default):",
                options=unique_city_pairs["city_full"].tolist(), 
                default=unique_city_pairs["city_full"].tolist(), 
                key="metro_multiselect"
            )
            
            selected_clean_metros = [full_to_clean_city_map[f] for f in selected_full_metros]

            # Sort Option
            sort_option = st.selectbox(
                "Sort metro areas by",
                ["Metro Area Name", "PTI (Price to Income Ratio)", "Median Sale Price", "Household Income"],
                key="sort_bar_chart",
            )
            
            plot_data = city_data[city_data["city"].isin(selected_clean_metros)].copy()
            
            if plot_data.empty:
                st.warning("No cities match your current filter selection.")
            
            else:
                # Sort logic
                if sort_option == "PTI (Price to Income Ratio)":
                    sorted_data = plot_data.sort_values(RATIO_COL, ascending=True)
                elif sort_option == "Median Sale Price":
                    sorted_data = plot_data.sort_values("Median Sale Price", ascending=False)
                elif sort_option == "Household Income":
                    sorted_data = plot_data.sort_values("Household Income", ascending=False)
                else: 
                    sorted_data = plot_data.sort_values("city_full") 

                # Color logic
                sorted_data["afford_label"] = sorted_data["affordability_rating"].astype('category')
                ordered_categories = list(AFFORDABILITY_CATEGORIES.keys())
                if 'N/A' in sorted_data["afford_label"].unique():
                    ordered_categories.append('N/A')
                sorted_data["afford_label"] = pd.Categorical(sorted_data["afford_label"], categories=ordered_categories, ordered=True)

                if not sorted_data.empty:
                    fig_city = px.bar(
                        sorted_data,
                        x="city",
                        y=RATIO_COL,
                        color="afford_label",
                        color_discrete_map=AFFORDABILITY_COLORS,
                        labels={
                            "city": "City",
                            RATIO_COL: "Price-to-income ratio",
                            "afford_label": "Affordability Rating",
                        },
                        hover_data={
                            "city_full": True,
                            "Median Sale Price": ":,.0f",
                            "Household Income": ":,.0f",
                            RATIO_COL: ":.2f",
                            "afford_label": True,
                        },
                        height=520, 
                    )
                    
                    # Threshold lines - add lines for all categories with upper bounds
                    for i, (category, (lower, upper)) in enumerate(AFFORDABILITY_CATEGORIES.items()):
                        if upper is not None:
                            fig_city.add_hline(
                                y=upper,
                                line_dash="dot",
                                line_color="gray",
                                opacity=0.5
                            )

                    fig_city.update_layout(
                        yaxis_title="Price-to-income ratio",
                        xaxis_tickangle=-45,
                        margin=dict(l=20, r=20, t=80, b=80),
                        bargap=0.05,
                        bargroupgap=0.0,
                        legend=dict(
                            orientation="h",
                            yanchor="bottom",
                            y=1.02,
                            xanchor="right",
                            x=1
                        ),
                    )

                    st.plotly_chart(fig_city, use_container_width=True)


# --- RIGHT COLUMN: MAP & FILTERS ---
with main_col_right:
    with st.container(border=True):
        # Create two columns within the container
        filter_col_left, map_col_right = st.columns([1, 1])
        
        # Left column: Adjust Map View Filters
        with filter_col_left:
            st.markdown("### User Profile")
            persona_income_slider(final_income, persona)
        
        # Right column: Affordability summary card
        with map_col_right:
            current_income = st.session_state.get("income_manual_key", final_income)
            current_persona = st.session_state.get("profile_radio_key", persona)
            current_max_affordable = AFFORDABILITY_THRESHOLD * current_income
            render_affordability_summary_card(current_income, current_persona, current_max_affordable)
    
        st.markdown("#### ZIP-level Map (Select Metro Below)")
        st.markdown("""The map shows whether a region is affordable based on the maximum affordable price calculated in the **Affordability Summary**.""")

        # Additional map and ZIP code display logic here...

# =====================================================================
#   SECTION 4: OPTIONAL SPLIT CHART (BY CATEGORY)
# =====================================================================
st.markdown("---")
st.markdown("### Advanced Metro Area Comparisons by Affordability Category")

with st.expander("Show breakdown by Affordability Rating"):
    if 'sorted_data' in locals() and not sorted_data.empty:
        # Define the exact order and list of categories to iterate through
        categories_to_plot = [
            "Affordable",
            "Moderately Unaffordable",
            "Seriously Unaffordable",
            "Severely Unaffordable",
            "Impossibly Unaffordable"
        ]
        for cat in categories_to_plot:
            cat_data = sorted_data[sorted_data["affordability_rating"] == cat].copy()
            st.markdown(f"**{cat}**")
            if cat_data.empty:
                st.info(f"No cities in the current selection fall into the '{cat}' category.")
            else:
                cat_data = cat_data.sort_values(RATIO_COL, ascending=True)
                fig_cat = px.bar(
                    cat_data,
                    x="city",
                    y=RATIO_COL,
                    color="affordability_rating",
                    color_discrete_map=AFFORDABILITY_COLORS,
                    labels={"city": "City", RATIO_COL: "Price-to-income ratio"},
                    hover_data={
                        "city_full": True, 
                        "Median Sale Price": ":,.0f", 
                        RATIO_COL: ":.2f",
                        "affordability_rating": False
                    },
                    height=300,
                )
                fig_cat.update_layout(
                    xaxis_tickangle=-45, 
                    bargap=0.2,
                    showlegend=False,
                    margin=dict(l=0, r=0, t=0, b=0)
                )
                st.plotly_chart(fig_cat, use_container_width=True)

            st.markdown("<hr style='margin: 10px 0; border: none; border-top: 1px dashed #eee;'>", unsafe_allow_html=True)
    else:
        st.info("No data available to show advanced city comparisons based on current filters.")
