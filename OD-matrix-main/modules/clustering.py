import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans


# =========================================================
# LOAD FEATURES
# =========================================================
def load_features(df):

    features = df[[
        "total_od",
        "mean_trip_length",
        "od_entropy"
    ]].copy()

    scaler = StandardScaler()
    X = scaler.fit_transform(features)

    return X, df["city"]


# =========================================================
# CLUSTER CITIES
# =========================================================
def run_clustering(df):

    X, cities = load_features(df)

    kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
    labels = kmeans.fit_predict(X)

    result = pd.DataFrame({
        "city": cities,
        "cluster": labels
    })

    # label interpretation
    mapping = {
        0: "Compact / Efficient",
        1: "Polycentric / Medium",
        2: "Dispersed / Fragmented"
    }

    result["typology"] = result["cluster"].map(mapping)

    return result