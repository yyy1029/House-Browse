# app_v4.py

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import json
import os
import time 

# --- RESTORED IMPORTS ---
from zip_module import load_city_zip_data, get_zip_coordinates
from dataprep import (
    load_data,
    make_city_view_data,
    RATIO_COL,
    AFFORDABILITY_THRESHOLD,
    apply_income_filter,
    AFFORDABILITY_CATEGORIES,
    AFFORDABILITY_COLORS,
    classify_affordability,
    make_zip_view_data,
)
from ui_components import income_control_panel, persona_income_slider, render_affordability_summary_card

# ---------- Global config ----------
st.set_page_config(page_title="Design 3 – Price Affordability Finder", layout="wide")
st.title("Design 3 – Price Affordability Finder")

# --- HTML INTRO BLOCK ---
st.markdown(
    """
    <div style="border-top: 1px solid #e6e6e6; padding: 10px 0; margin-bottom: 10px;">
    Use this tool to allow users to compare cities by <strong> PTI (price-to-income ratio) </strong> and select metro areas of interest to explore ZIP-code level details.<br>
    <strong>PTI Ratio: </strong>
    <span style="background-color: #f0f2f6; padding: 2px 6px; border-radius: 4px;">
            <strong>Median Sale Price / Median Househould Income</strong>
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
    .block-container { padding-top: 2rem; }
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
        
    st.markdown("""
        <div style="font-size: 20px; font-weight: 700; margin-bottom: 4px; color: #4B0082;">
            Select Year
        </div>
    """, unsafe_allow_html=True)
    
    return st.selectbox(
        "Select Year", 
        years, 
        index=len(years) - 1, 
        key=key, 
        label_visibility="collapsed", 
        help="Choose the year for comparison."
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
#   1. CALCULATION PRE-REQUISITES
# =====================================================================

# Here, the income control panel logic is processed (session_state)
final_income, persona = income_control_panel()
max_affordable_price = AFFORDABILITY_THRESHOLD * final_income
df_filtered_by_income = apply_income_filter(df, final_income)

# Calculate historical data (but it's not displayed yet)
df_history = calculate_median_ratio_history(df)
df_prop_history = calculate_category_proportions_history(df)


# --- Divider ---
st.markdown("""
    <hr style="border: none; border-top: 1px solid #e6e6e6; margin-top: 5px; margin-bottom: 10px;">
    """, unsafe_allow_html=True)


# =====================================================================
#   2. Layout: User Profile (Full Width) and Year Selector with Explanation (Vertical)
# =====================================================================

# First Section: Full Width User Profile
st.markdown("### User Profile & Budget")
with st.container():
    # Render Persona and Income Controls
    persona_income_slider(final_income, persona)
    current_income = st.session_state.get("income_manual_key", final_income)
    current_persona = st.session_state.get("profile_radio_key", persona)
    current_max_affordable = AFFORDABILITY_THRESHOLD * current_income
    render_affordability_summary_card(current_income, current_persona, current_max_affordable)

# Second Section: Year Selector and Explanation Below User Profile
st.markdown("""
    <hr style="border: none; border-top: 1px solid #f0f0f0; margin-top: 5px; margin-bottom: 10px;">
    """, unsafe_allow_html=True)

with st.container():
    # Explanation text and Year Selector now close together
    st.markdown(""" 
        The left column allows users to get an idea of how the PTI (price-to-income) ratio differs across the different metro areas. The right column allows a user income details to figure out zip codes in a specific metro area that are affordable. Adjust the year the data is being displayed using the year selector below.

    """)
    
    # Render Year Selector below the explanation
    selected_year = year_selector(df, key="year_main_selector")

# Default: Use the maximum year if none is selected
if selected_year is None:
    selected_year = df["year"].max()


# =====================================================================
#   3. Main Section
# =====================================================================

st.markdown("""
    <hr style="border: none; border-top: 1px solid #f0f0f0; margin-top: 5px; margin-bottom: 10px;">
    """, unsafe_allow_html=True)

# =====================================================================
#   4. Bar Chart， Map + Snapshot
# =====================================================================

main_col_left, main_col_right = st.columns([3, 4]) 


with main_col_left:
    with st.container(border=True):
        st.markdown("#### Metro Area Affordability Ranking")

        city_data = make_city_view_data(
            df, 
            annual_income=final_income,
            year=selected_year, 
            budget_pct=30,
        )

        if city_data.empty:
            st.warning(f"No data available for {selected_year}.")
        else:
            city_data["affordability_rating"] = city_data[RATIO_COL].apply(classify_affordability)
            gap = city_data[RATIO_COL] - AFFORDABILITY_THRESHOLD
            dist = gap.abs()
            city_data["gap_for_plot"] = np.where(city_data["affordable"], dist, -dist)

            unique_city_pairs = city_data[["city", "city_full"]].drop_duplicates().sort_values("city_full")
            full_to_clean_city_map = pd.Series(
                unique_city_pairs["city"].values,
                index=unique_city_pairs["city_full"]
            ).to_dict()

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
                    sorted_data = plot_data.sort_values("Per Capita Income", ascending=False)
                else: 
                    sorted_data = plot_data.sort_values("city_full") 

                # Color logic
                sorted_data["afford_label"] = sorted_data["affordability_rating"].astype('category')
                ordered_categories = list(AFFORDABILITY_CATEGORIES.keys())
                if 'N/A' in sorted_data["afford_label"].unique():
                    ordered_categories.append('N/A')
                sorted_data["afford_label"] = pd.Categorical(
                    sorted_data["afford_label"],
                    categories=ordered_categories,
                    ordered=True
                )

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
                            "Per Capita Income": ":,.0f",
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


# ---------- 4B. Map + Snapshot ----------
with main_col_right:
    with st.container(border=True):
        st.markdown("#### ZIP-level Map (Select Metro Below)")
        st.markdown("""The map shows whether a region is affordable based on the maximum 
        affordable price calculated in the **Affordability Summary**.""")

       
        if not city_data.empty:
            metro_map_df = city_data[['city', 'city_full']].drop_duplicates()
            metro_display_map = {
                row['city_full']: f"({row['city']}) - {row['city_full']}" 
                for _, row in metro_map_df.iterrows()
            }
            map_city_options_full = sorted(metro_display_map.keys())
            format_metro_func = lambda option: metro_display_map.get(option, option)
        else:
            map_city_options_full = sorted(df["city_full"].unique())
            format_metro_func = lambda x: x

        selected_map_metro_full = st.selectbox(
            "Choose Metro Area for Map:",
            options=map_city_options_full,
            format_func=format_metro_func,
            index=0,
            key="map_metro_select"
        )

        city_clicked_df = df[df['city_full'] == selected_map_metro_full]
        
        if city_clicked_df.empty:
            st.warning("Selected metro area does not exist in the filtered data.")
            city_clicked = None
        else:
            geojson_code = city_clicked_df["city_geojson_code"].iloc[0]
            city_clicked = geojson_code

   
        if city_clicked is None:
            st.info("Select a Metro Area from the dropdown above to view the ZIP-code map.")
        else:
            map_selection_changed = (selected_map_metro_full != st.session_state.last_drawn_city)
            income_changed = (final_income != st.session_state.last_drawn_income)
            should_trigger_spinner = map_selection_changed or income_changed

            st.markdown(f"**Map for {selected_map_metro_full} ({selected_year})**")
            st.markdown("""Red is used for more unaffordable areas, and green is used for affordable areas.  """)
            
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

            # Load Map Data
            df_zip = load_city_zip_data(city_clicked, df_full=df, max_pci=final_income)
            
            if "year" in df_zip.columns:
                df_zip = df_zip[df_zip["year"] == selected_year].copy() 

            if df_zip.empty:
                if should_trigger_spinner: loading_message_placeholder.empty()
                st.error("No ZIP-level data available for this city/year.")
            else:
                df_zip_map = get_zip_coordinates(df_zip) 
                price_col = "median_sale_price"
                income_col = "per_capita_income"

                if df_zip_map.empty or price_col not in df_zip_map.columns:
                    if should_trigger_spinner: loading_message_placeholder.empty()
                    st.error("Map data processing failed.")
                else:
                    if RATIO_COL not in df_zip_map.columns:
                        denom_zip = df_zip_map[income_col].replace(0, np.nan)
                        df_zip_map[RATIO_COL] = df_zip_map[price_col] / denom_zip
                    
                    df_zip_map["affordability_rating"] = df_zip_map[RATIO_COL].apply(classify_affordability)
                    
                    # Map Prices to Color
                    min_price = df_zip_map[price_col].min()
                    max_price = df_zip_map[price_col].max()
                    
                    affordable_mask = df_zip_map[price_col] < max_affordable_price
                    unaffordable_mask = df_zip_map[price_col] >= max_affordable_price
                    
                    df_zip_map["color_value"] = np.nan
                    
                    if affordable_mask.any():
                        affordable_prices = df_zip_map.loc[affordable_mask, price_col]
                        if affordable_prices.min() < max_affordable_price:
                            affordable_range = max_affordable_price - min_price
                            if affordable_range > 0:
                                df_zip_map.loc[affordable_mask, "color_value"] = (
                                    0.5 * (affordable_prices - min_price) / affordable_range
                                )
                            else:
                                df_zip_map.loc[affordable_mask, "color_value"] = 0.25
                    
                    if unaffordable_mask.any():
                        unaffordable_prices = df_zip_map.loc[unaffordable_mask, price_col]
                        if unaffordable_prices.max() >= max_affordable_price:
                            unaffordable_range = max_price - max_affordable_price
                            if unaffordable_range > 0:
                                df_zip_map.loc[unaffordable_mask, "color_value"] = (
                                    0.5 + 0.5 * (unaffordable_prices - max_affordable_price) / unaffordable_range
                                )
                            else:
                                df_zip_map.loc[unaffordable_mask, "color_value"] = 0.75
                    
                    df_zip_map["color_value"] = df_zip_map["color_value"].clip(0, 1)

                    geojson_path = os.path.join(
                        os.path.dirname(__file__),
                        "city_geojson",
                        f"{city_clicked}.geojson", 
                    )

                    if not os.path.exists(geojson_path):
                        if should_trigger_spinner: loading_message_placeholder.empty()
                        st.error(f"GeoJSON file not found for {city_clicked}. Expected path: {geojson_path}")
                    else:
                        with open(geojson_path, "r") as f:
                            zip_geojson = json.load(f)

                        df_zip_map["zip_str_padded"] = df_zip_map["zip_code_int"].astype(str).str.zfill(5)

                        custom_colorscale = [
                            [0.0, "rgb(0, 100, 0)"],      # Dark green (very affordable)
                            [0.3, "rgb(34, 139, 34)"],   # Medium green
                            [0.5, "rgb(144, 238, 144)"],  # Light green (at threshold)
                            [0.5, "rgb(255, 182, 193)"],  # Light red (at threshold)
                            [0.7, "rgb(220, 20, 60)"],   # Medium red
                            [1.0, "rgb(139, 0, 0)"]       # Dark red (very unaffordable)
                        ]
                        
                        fig_map = px.choropleth_mapbox(
                            df_zip_map,
                            geojson=zip_geojson,
                            locations="zip_str_padded", 
                            featureidkey="properties.ZCTA5CE10",
                            color="color_value", 
                            color_continuous_scale=custom_colorscale,
                            range_color=[0, 1],
                            hover_name="zip_code_str",
                            hover_data={
                                price_col: ":,.0f",
                                # income_col: ":,.0f",
                                "zip_str_padded":False,
                                "color_value": False,
                            },
                            mapbox_style="carto-positron",
                            center={
                                "lat": df_zip_map["lat"].mean(),
                                "lon": df_zip_map["lon"].mean(),
                            },
                            zoom=10,
                            height=454,
                        )

                        # Update colorbar with meaningful labels
                        tick_vals = [0.0, 0.25, 0.5, 0.75, 1.0]
                        tick_labels = []
                        for tv in tick_vals:
                            if tv <= 0.5:
                                if affordable_mask.any() and min_price < max_affordable_price:
                                    price_val = min_price + (tv / 0.5) * (max_affordable_price - min_price)
                                else:
                                    price_val = min_price
                            else:
                                if unaffordable_mask.any() and max_price > max_affordable_price:
                                    price_val = max_affordable_price + ((tv - 0.5) / 0.5) * (max_price - max_affordable_price)
                                else:
                                    price_val = max_affordable_price
                            tick_labels.append(f"${price_val:,.0f}")
                        
                        fig_map.update_layout(
                            margin=dict(l=0, r=0, t=0, b=0),
                            coloraxis_colorbar=dict(
                                title="Median Sale Price",
                                tickvals=tick_vals,
                                ticktext=tick_labels,
                            ),
                        )

                        # Add threshold annotation
                        fig_map.add_annotation(
                            text=f"Threshold: ${max_affordable_price:,.0f}",
                            xref="paper", yref="paper",
                            x=0.02, y=0.98,
                            showarrow=False,
                            bgcolor="rgba(255, 255, 255, 0.8)",
                            bordercolor="black",
                            borderwidth=1,
                            font=dict(size=10)
                        )

                        if should_trigger_spinner: loading_message_placeholder.empty() 
                        st.plotly_chart(fig_map, use_container_width=True)
                        st.session_state.last_drawn_city = selected_map_metro_full 
                        st.session_state.last_drawn_income = final_income

        if city_clicked is not None:
            if not city_data.empty:
                city_row = city_data[city_data["city"] == city_clicked] 
                if not city_row.empty:
                    row = city_row.iloc[0]
                    st.markdown(f"#### Metro Area Snapshot: {row['city_full']} ({selected_year})")
                    st.markdown(
                        f"""
                        - Median sale price: **${row['Median Sale Price']:,.0f}**
                        - Median Household income: **${row['Per Capita Income']:,.0f}**
                         """
                    )


# =====================================================================
#   5. Advanced Metro Area Comparisons by Affordability Category
# =====================================================================

st.markdown("---")
st.markdown("### Advanced Metro Area Comparisons by Affordability Category")

with st.expander("Show breakdown by Affordability Rating"):
    if 'sorted_data' in locals() and not sorted_data.empty:
        
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
            
            st.markdown(
                "<hr style='margin: 10px 0; border: none; border-top: 1px dashed #eee;'>",
                unsafe_allow_html=True
            )
    else:
        st.info("No data available to show advanced city comparisons based on current filters.")
