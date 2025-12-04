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
        .css-1aumxhk { font-size: 12px; }  /* 影响 selectbox 和 multiselect 字体 */
        .css-1l0j7j4 { font-size: 12px; }  /* 影响标签字体 */
    </style>
""", unsafe_allow_html=True)

# ---------- Global config ----------
st.set_page_config(page_title="Design 3 – Price Affordability Finder", layout="wide")
st.title("Design 3 – Price Affordability Finder")

# --- HTML INTRO BLOCK ---
st.markdown("""
    <div style="border-top: 1px solid #e6e6e6; padding: 10px 0; margin-bottom: 10px;">
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
    """, unsafe_allow_html=True)

# Inject CSS
st.markdown("""
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css">
    <style>
    [data-testid="stAlert"] { display: none !important; }
    /* Optional: Global tightening */
    .block-container { padding-top: 2rem; }
    </style>
""", unsafe_allow_html=True)

MAX_ZIP_RATIO_CLIP = 15.0

# ---------- Function Definitions ----------
def year_selector(df: pd.DataFrame, key: str):
    years = sorted(df["year"].unique())
    if not years:
        return None
        
    # 1. Render the label manually with bigger font
    st.markdown("""
        <div style="font-size: 18px; font-weight: 600; margin-bottom: -15px;">
            Select Year
        </div>
    """, unsafe_allow_html=True)
    
    # 2. Render the selectbox with the label hidden
    return st.selectbox(
        "Select Year", 
        years, 
        index=len(years) - 1, 
        key=key, 
        label_visibility="collapsed" 
    )

@st.cache_data(ttl=3600*24)
def get_data_cached():
    return load_data()

@st.cache_data
def calculate_median_ratio_history(dataframe):
    years = sorted(dataframe["year"].unique())
    history_data = []
    for yr in years:
        city_data_yr = make_city_view_data(dataframe, annual_income=0, year=yr, budget_pct=30)
        if not city_data_yr.empty and RATIO_COL in city_data_yr.columns:
            median_ratio = city_data_yr[RATIO_COL].median()
            history_data.append({"year": yr, "median_ratio": median_ratio})
    return pd.DataFrame(history_data)

@st.cache_data
def calculate_category_proportions_history(dataframe):
    """Calculates the % composition of affordability tiers over time."""
    years = sorted(dataframe["year"].unique())
    history_data = []
    
    def classify_strict(ratio):
        if ratio < 3.0: return "Affordable (<3.0)"
        elif ratio <= 4.0: return "Moderately Unaffordable (3.1-4.0)"
        elif ratio <= 5.0: return "Seriously Unaffordable (4.1-5.0)"
        elif ratio <= 9.0: return "Severely Unaffordable (5.1-9.0)" 
        else: return "Impossibly Unaffordable (>9.0)"

    category_order = [
        "Affordable (<3.0)", 
        "Moderately Unaffordable (3.1-4.0)", 
        "Seriously Unaffordable (4.1-5.0)", 
        "Severely Unaffordable (5.1-9.0)", 
        "Impossibly Unaffordable (>9.0)"
    ]

    for yr in years:
        city_data_yr = make_city_view_data(dataframe, annual_income=0, year=yr, budget_pct=30)
        if not city_data_yr.empty and RATIO_COL in city_data_yr.columns:
            city_data_yr["cat"] = city_data_yr[RATIO_COL].apply(classify_strict)
            counts = city_data_yr["cat"].value_counts(normalize=True) * 100
            for cat in category_order:
                history_data.append({
                    "year": yr,
                    "category": cat,
                    "percentage": counts.get(cat, 0.0)
                })

    return pd.DataFrame(history_data)


# ---------- Load data ----------
df = get_data_cached()
if df.empty:
    st.error("Application cannot run. Base data (df) is empty.")
    st.stop()

# Initialize session state
if 'last_drawn_city' not in st.session_state:
    st.session_state.last_drawn_city = None
if 'last_drawn_income' not in st.session_state: 
    st.session_state.last_drawn_income = 0


# =====================================================================
#   LAYOUT SETUP
# =====================================================================

# 1. Calculation Pre-requisites
final_income, persona = income_control_panel()
max_affordable_price = AFFORDABILITY_THRESHOLD * final_income
df_filtered_by_income = apply_income_filter(df, final_income)

# Calculate Histories
df_history = calculate_median_ratio_history(df)
df_prop_history = calculate_category_proportions_history(df)


# --- CUSTOM DIVIDER TO REPLACE '---' (REMOVES WHITESPACE) ---
st.markdown("""
    <hr style="border: none; border-top: 1px solid #e6e6e6; margin-top: 5px; margin-bottom: 10px;">
    """, unsafe_allow_html=True)

header_row_main, header_row_year = st.columns([4, 1]) # Middle Header
main_col_left, main_col_right = st.columns([2, 3])  # Updated main content layout



# =====================================================================
#   SECTION 2: HEADER & YEAR SELECTION
# =====================================================================

# 1. Render Widget FIRST
with header_row_year:
    selected_year = year_selector(df, key="year_main_selector") 

# --- LOGIC SAFETY CHECK (PREVENTS 'NO OPTIONS' BUG) ---
if selected_year is None:
    selected_year = df["year"].max()

# 2. Render Header Text
with header_row_main:
    st.markdown("""
        <h3 style="margin-top: -5px; padding-top: 0;">
            Bar Chart and User Input ZIP-Code Map
        </h3>
    """, unsafe_allow_html=True)
    st.markdown("""The left column allows users to get an idea of how the PTI (price-to-income) ratio differs across the different 
    metro areas. The right column allows a user income details to figure out zip codes in a specific metro area that are affordable. 
    The colors on the zip code map indicate how affordable that area is relative to the maximum affordable price. **Adjust the year 
    the data is being displayed using the year selector to the right.**""")


# 3. CALCULATE DATA
city_data = make_city_view_data(
    df, 
    annual_income=final_income,
    year=selected_year, 
    budget_pct=30,
)

# 4. Apply Column Fixes
if not city_data.empty:
    city_data["affordability_rating"] = city_data[RATIO_COL].apply(classify_affordability)
    gap = city_data[RATIO_COL] - AFFORDABILITY_THRESHOLD
    dist = gap.abs()
    city_data["gap_for_plot"] = np.where(city_data["affordable"], dist, -dist)


# =====================================================================
#   SECTION 3: MAIN CHARTS (City Bar & Map)
# =====================================================================

# --- LEFT COLUMN: CITY BAR CHART ---
with main_col_left:
    with st.expander("Affordability Ranking", expanded=False):  # expanded=False 
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
            # Get current values from session state (updated by slider/persona changes)
            current_income = st.session_state.get("income_manual_key", final_income)
            current_persona = st.session_state.get("profile_radio_key", persona)
            current_max_affordable = AFFORDABILITY_THRESHOLD * current_income
            render_affordability_summary_card(current_income, current_persona, current_max_affordable)
    
    st.markdown("#### ZIP-level Map (Select Metro Below)")
    st.markdown("""The map shows whether a region is affordable based on the maximum affordable price calculated in the **Affordability Summary**.""")

    # Extract unique pairs of abbreviation ('city') and full name ('city_full')
    if not city_data.empty:
        metro_map_df = city_data[['city', 'city_full']].drop_duplicates()
        metro_display_map = {row['city_full']: f"({row['city']}) - {row['city_full']}" for index, row in metro_map_df.iterrows()}
        map_city_options_full = sorted(metro_display_map.keys())

        def format_metro_func(option):
            return metro_display_map.get(option, option)
                
    else:
        map_city_options_full = sorted(df["city_full"].unique())
        format_metro_func = lambda x: x

    selected_map_metro_full = st.selectbox("Choose Metro Area for Map:", options=map_city_options_full, format_func=format_metro_func, index=0, key="map_metro_select")

    # Map and Snapshot container (below the selector, above the map)
    city_clicked_df = df[df['city_full'] == selected_map_metro_full]
    
    if city_clicked_df.empty:
        st.warning("Selected metro area does not exist in the filtered data.")
        city_clicked = None
    else:
        geojson_code = city_clicked_df["city_geojson_code"].iloc[0]
        city_clicked = geojson_code

    map_col_left, snapshot_col_right = st.columns([4, 1])
    
    # Left column: Map display
    with map_col_left:
        if city_clicked is None:
            st.info("Select a Metro Area from the dropdown above to view the ZIP-code map.")
        else:
            map_selection_changed = (selected_map_metro_full != st.session_state.last_drawn_city)
            income_changed = (final_income != st.session_state.last_drawn_income)
            should_trigger_spinner = map_selection_changed or income_changed

            st.markdown(f"**Map for {selected_map_metro_full} ({selected_year})**")
            st.markdown("""Red is used for more unaffordable areas, and green is used for affordable areas.""")

            if should_trigger_spinner:
                loading_message_placeholder = st.empty()
                loading_message_placeholder.markdown(
                    f'<div style="text-align: center; padding: 20px;">'
                    f'<h3><i class="fas fa-spinner fa-spin"></i> Loading map...</h3>' 
                    f'<p>Preparing map for {selected_map_metro_full}</p>'
                    f'</div>', 
                    unsafe_allow_html=True
                )
                time.sleep(0.5)

            # Load Map Data - use unfiltered df to show all zip codes
            df_zip = load_city_zip_data(city_clicked, df_full=df, max_pci=final_income)

            if "year" in df_zip.columns:
                df_zip = df_zip[df_zip["year"] == selected_year].copy() 

            if df_zip.empty:
                if should_trigger_spinner: loading_message_placeholder.empty()
                st.error("No ZIP-level data available for this city/year.")
            else:
                df_zip_map = get_zip_coordinates(df_zip)
                price_col = "median_sale_price"
                income_col = "household_income"  # Changed from 'per_capita_income' to 'household_income'

                if df_zip_map.empty or price_col not in df_zip_map.columns:
                    if should_trigger_spinner: loading_message_placeholder.empty()
                    st.error("Map data processing failed.")
                else:
                    if RATIO_COL not in df_zip_map.columns:
                        denom_zip = df_zip_map[income_col].replace(0, np.nan)
                        df_zip_map[RATIO_COL] = df_zip_map[price_col] / denom_zip
                    
                    df_zip_map["affordability_rating"] = df_zip_map[RATIO_COL].apply(classify_affordability)

