import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json

from clustering import load_features, run_clustering
from od_viz import plot_city_flows


# =========================================================
# LOAD DATA
# =========================================================
st.set_page_config(layout="wide")

st.title("🌍 Urban Mobility OD Dashboard")


df = pd.read_csv("outputs/city_comparison.csv")

st.subheader("📊 City Comparison")
st.dataframe(df)


# =========================================================
# METRICS PLOTS
# =========================================================
col1, col2, col3 = st.columns(3)

with col1:
    st.bar_chart(df.set_index("city")["total_od"])

with col2:
    st.bar_chart(df.set_index("city")["mean_trip_length"])

with col3:
    st.bar_chart(df.set_index("city")["od_entropy"])


# =========================================================
# CITY SELECTOR
# =========================================================
city = st.selectbox("Select city", df["city"].values)

st.subheader(f"🧭 OD Flow Map: {city}")

plot_city_flows(city)

st.pyplot(plt.gcf())


# =========================================================
# CLUSTERING
# =========================================================
st.subheader("📊 Urban Typology Clustering")

clusters = run_clustering(df)

st.dataframe(clusters)

st.success("Done")