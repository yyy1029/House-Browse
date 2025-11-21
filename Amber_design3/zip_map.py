# zip_map.py
import streamlit as st
import numpy as np
import plotly.express as px
import pgeocode
import geopandas as gpd
import json

def render_zip_map_for_city(zip_df):
    """
    给定一个 city 的 ZIP-level dataframe（来自 make_zip_view_data），
    画出 ZIP affordability 的 choropleth map。
    你可以在 app.py 里调用这个函数。
    """
    if zip_df.empty:
        st.warning("No ZIP-level data for this city.")
        return

    df = zip_df.copy()

    # 确保有 ZIP 字符串列
    if "zip_code_str" not in df.columns:
        df["zip_code_str"] = df["zipcode"].astype(str).str.zfill(5)

    # 用 pgeocode 做经纬度
    nomi = pgeocode.Nominatim("us")
    geo_df = nomi.query_postal_code(df["zip_code_str"].tolist())

    df["lat"] = geo_df["latitude"].values
    df["lon"] = geo_df["longitude"].values
    df = df.dropna(subset=["lat", "lon"])

    if df.empty:
        st.warning("ZIP codes could not be geocoded for this city.")
        return

    # affordability ratio 用你 zip 级别的列名（来自 make_zip_view_data）
    # 你那里叫 afford_ratio_zip
    df["affordability_ratio"] = df["afford_ratio_zip"]
    df["affordability_norm"] = np.clip(df["affordability_ratio"], 0, 2) / 2

    # 计算 map 中心位置
    center_lat = df["lat"].mean()
    center_lon = df["lon"].mean()

    # 读 shapefile（路径按你 teammate 的来，如果放别的地方自己改下）
    gdf = gpd.read_file("cb_2018_us_zcta510_500k/cb_2018_us_zcta510_500k.shp")
    gdf.to_file("us_zcta5.geojson", driver="GeoJSON")
    with open("us_zcta5.geojson", "r") as f:
        zip_geojson = json.load(f)

    # 颜色：红 <1, 黄 ~1, 绿 >1
    colorscale = [
        [0.0, "red"],
        [0.5, "yellow"],
        [1.0, "green"],
    ]
    colorbar_config = dict(
        title="Affordability Ratio",
        tickvals=[0.0, 0.25, 0.5, 0.75, 1.0],
        ticktext=["0", "0.5", "1.0", "1.5", "2.0"],
    )

    # 转成 int 用来匹配 geojson
    df["zip_code_int"] = df["zip_code_str"].astype(int)

    fig_map = px.choropleth_mapbox(
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
    fig_map.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        coloraxis_colorbar=colorbar_config,
    )
    st.plotly_chart(fig_map, use_container_width=True)
