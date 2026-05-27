import json
import geopandas as gpd
import networkx as nx
import numpy as np
import os

from shapely.geometry import LineString
from modules import zones_utils, od_utils, assignment_utils, validation_utils, plot_academic_od_heatmap

# =========================================================
# 🔥 BUILD OSM-SAFE ROUTING GRAPH (CORE FIX)
# =========================================================
def build_osm_safe_graph(G, city_name):

    print("🔹 Building OSM-safe routing graph...")

    # Convert to directed graph (OSM roads are directional in reality)
    G = G.to_directed()

    # Keep largest strongly connected component
    if not nx.is_strongly_connected(G):

        components = list(nx.strongly_connected_components(G))
        print(f"⚠️ Not strongly connected: {len(components)} components")

        largest_scc = max(components, key=len)
        G = G.subgraph(largest_scc).copy()

        print(f"✅ Kept SCC: {len(G.nodes)} nodes")

    else:
        print("✅ Graph already strongly connected")

    return G


# =========================================================
# 🔥 FILTER OD NODES TO ROUTING CORE
# =========================================================
def filter_od_nodes(G, nodes_sel, city_name):

    print("🔹 Filtering OD nodes to routing core...")

    nodes_sel = [n for n in nodes_sel if n in G]

    if len(nodes_sel) < 2:
        raise ValueError(f"{city_name}: Not enough valid OD nodes in SCC")

    print(f"OD nodes after filter: {len(nodes_sel)}")

    return nodes_sel


# =========================================================
# RUN PIPELINE FOR ONE CITY
# =========================================================
def run_city(CONFIG):
    city_name = CONFIG["city_name"]

    print(f"\n==============================")
    print(f"🚀 Processing city: {city_name}")
    print(f"==============================")

    # =========================================================
    # 1. LOAD SENSORS (OPTIONAL)
    # =========================================================
    sensor_gdf = None

    if CONFIG.get("sensors_csv"):
        print("🔹 Loading sensors...")

        sensor_df = gpd.pd.read_csv(CONFIG["sensors_csv"])

        sensor_gdf = gpd.GeoDataFrame(
            sensor_df,
            geometry=gpd.points_from_xy(
                sensor_df[CONFIG["lon"]],
                sensor_df[CONFIG["lat"]]
            ),
            crs=4326
        ).to_crs(3857)

        print(f"Loaded sensors: {len(sensor_gdf)}")

    else:
        print("⚠️ No sensors → validation skipped")

    # =========================================================
    # 2. CITY
    # =========================================================
    print("🔹 Loading city polygon...")
    city_gdf = gpd.read_file(CONFIG["city_shp"]).to_crs(3857)

    # =========================================================
    # 3. GRAPH LOAD
    # =========================================================
    print("🔹 Loading network graph...")
    G = nx.read_graphml(CONFIG["graph"])
    G = nx.relabel_nodes(G, lambda x: str(x))

    for u, v, d in G.edges(data=True):
        d["length"] = float(d.get("length", 1.0))

    for n, d in G.nodes(data=True):
        if "x" not in d or "y" not in d:
            raise ValueError(f"{city_name}: Node {n} missing coords")

    # =========================================================
    # 🔥 OSM-SAFE GRAPH BUILDING (CRITICAL FIX)
    # =========================================================
    G = build_osm_safe_graph(G, city_name)

    # =========================================================
    # 4. FIX EDGE GEOMETRY
    # =========================================================
    print("🔹 Fixing edge geometries...")

    for u, v, k, data in G.edges(keys=True, data=True):
        try:
            x1, y1 = G.nodes[u]["x"], G.nodes[u]["y"]
            x2, y2 = G.nodes[v]["x"], G.nodes[v]["y"]
            data["geometry"] = LineString([(x1, y1), (x2, y2)])
        except:
            data["geometry"] = None

    G.remove_edges_from([
        (u, v, k)
        for u, v, k, d in G.edges(keys=True, data=True)
        if d.get("geometry") is None
    ])

    print(f"Graph: {len(G.nodes)} nodes | {len(G.edges)} edges")

    # =========================================================
    # 5. GDF
    # =========================================================
    import osmnx as ox
    nodes_gdf, _ = ox.graph_to_gdfs(G)
    nodes_gdf = nodes_gdf.to_crs(3857)

    # =========================================================
    # 6. ZONES
    # =========================================================
    print("🔹 Creating zones...")

    zones, pop = zones_utils.create_zones(
        city_gdf,
        CONFIG["cell_size"],
        CONFIG["pop_raster"]
    )

    if np.sum(pop) == 0:
        raise ValueError(f"{city_name}: Empty population raster")

    # =========================================================
    # 7. SNAP
    # =========================================================
    print("🔹 Snapping zones...")

    zones, nodes_sel = zones_utils.snap_zones_to_nodes(
        zones,
        nodes_gdf,
        CONFIG["max_snap_dist"]
    )

    print(f"Raw OD nodes: {len(nodes_sel)}")

    # =========================================================
    # 🔥 FILTER TO OSM-SAFE CORE
    # =========================================================
    nodes_sel = filter_od_nodes(G, nodes_sel, city_name)

    # =========================================================
    # 8. DISTANCES (NO INF GUARANTEE NOW)
    # =========================================================
    print("🔹 Computing distance matrix...")

    D = od_utils.compute_distance_matrix(nodes_sel, G)

    if np.isinf(D).any():
        raise ValueError(f"{city_name}: INF detected (should NEVER happen now)")

    print(f"D OK: {D.shape}")

    # =========================================================
    # 9. OD GENERATION
    # =========================================================
    print("🔹 Generating OD...")

    # beta = od_utils.time_dependent_beta(CONFIG["hourly_profiles"]) # 0.005
    total_trips = CONFIG["total_trips"] # CONFIG.get("total_trips", 350000)   " total_trips"

    # hourly_OD = od_utils.generate_hourly_od_entropy(
    #    pop,
    #    D,
    #    beta,
    #    CONFIG["hourly_profiles"],
    #    total_daily_trips=total_trips
    #)

    hourly_OD = od_utils.generate_hourly_od_entropy(pop, D,  CONFIG["hourly_profiles"], total_daily_trips=total_trips)

    if sum(np.sum(v) for v in hourly_OD.values()) == 0:
        raise ValueError(f"{city_name}: OD collapsed")

    # =========================================================
    # 10. SCALE
    # =========================================================
    # hourly_OD = od_utils.scale_hourly_od_to_total(
    #    hourly_OD,
    #    target_daily_trips=total_trips
    #)
 
   # =========================================================    # NEW 
    # 10. SCALE
    # =========================================================
    hourly_OD = od_utils.scale_hourly_od_to_total(
        hourly_OD,
        target_daily_trips=total_trips
    )

    # =========================================================
    # 🔥 10b. TOP-K SPARSIFICATION (NEW)
    # =========================================================
    print("🔹 Applying top-k sparsification...")

    K = CONFIG.get("top_k", 50)  # configurable per city, 10

    hourly_OD = od_utils.sparsify_top_k(hourly_OD, k=K)


    # =========================================================
    # 🔥 10b. INTEGERIZE (NEW)
    # =========================================================
    print("🔹 Converting OD to integer trips...")

    #### hourly_OD = od_utils.integerize_hourly_od(hourly_OD)   # without htis line 


    # =========================================================
    # 11. ASSIGNMENT
    # =========================================================
    hourly_OD = assignment_utils.stochastic_assignment(
        hourly_OD,
        nodes_sel,
        G,
        sigma=0.2,
        redistribution=0.1
    )

    # =========================================================
    # 12. VALIDATION
    # =========================================================
    validation = None

    if sensor_gdf is not None:
        print("🔹 Validating...")

        hour_cols = [f"hour_{h}" for h in range(24)]

        validation = validation_utils.validate_model(
            sensor_gdf,
            hourly_OD,
            hourly_OD,
            hour_cols,
            nodes_sel
        )

    # =========================================================
    # 13. SAVE
    # =========================================================
    os.makedirs("outputs", exist_ok=True)

    od_utils.save_hourly_od_xlsx_matrix(
        hourly_OD,
        zones,
        filename=f"outputs/hourly_od_{city_name}.xlsx"
    )

    print(f"✅ Finished {city_name}")

    od_utils.plot_academic_od_heatmap(
            city_name,
            hourly_OD,
            save_path="outputs"
            )
    
    od_utils.od_diagnostics(hourly_OD) # NEW 

    return {
        "city": city_name,
        "od": hourly_OD,
        "validation": validation
    }


# =========================================================
# MAIN
# =========================================================
def main(config_path):

    with open(config_path) as f:
        config = json.load(f)

    results = []

    for city in config["cities"]:
        print("\n--------------------------------")

        CONFIG = {**config["defaults"], **city}
        CONFIG.setdefault("lon", "lon")
        CONFIG.setdefault("lat", "lat")

        try:
            results.append(run_city(CONFIG))
        except Exception as e:
            print(f"❌ {city['city_name']} failed: {e}")

    print("\n🎉 ALL CITIES PROCESSED")

    return results


if __name__ == "__main__":
    main("multi-config.json")