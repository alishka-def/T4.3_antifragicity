import numpy as np
import networkx as nx
import pandas as pd


def compute_distance_matrix(nodes_sel, G):
    node_ids = [str(n) for n in nodes_sel]
    n = len(node_ids)
    D = np.zeros((n, n))

    print(f"Computing distances for {n} nodes...")

    for i, source in enumerate(node_ids):
        if source not in G:
            continue
        lengths = nx.single_source_dijkstra_path_length(G, source, weight="length")
        for j, target in enumerate(node_ids):
            D[i, j] = lengths.get(target, np.inf)

    return D


def entropy_gravity_od(pop, D, beta, total_trips, noise_sigma=0.4):
    """
    Realistic entropy-gravity OD model
    """
    pop = np.asarray(pop, dtype=float)
    # beta values (0.003-0.012) are calibrated per KILOMETRE, but the distance
    # matrix D is in metres (graph edge "length"). Convert to km so the decay is
    # applied at the right scale; without this the impedance decays ~1000x too
    # fast and demand collapses onto a few adjacent zone pairs, uncorrelated with
    # population.
    D = np.asarray(D, dtype=float) / 1000.0
    n = len(pop)

    OD = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            impedance = np.exp(-beta * D[i, j])
            OD[i, j] = pop[i] * pop[j] * impedance

    noise = np.random.lognormal(mean=0.0, sigma=noise_sigma, size=(n, n))
    OD = OD * noise

    OD += 0.01 * OD.mean()

    sum_od = OD.sum()
    if sum_od > 0:
        OD = OD / sum_od * total_trips

    return OD


def time_dependent_beta(hour):
    """
    Behavioral model of mobility:
    - Morning: long commuting trips
    - Midday: short local trips
    - Evening: medium trips
    - Night/off-peak: very local
    """
    if 7 <= hour <= 9:
        return 0.003
    elif 12 <= hour <= 14:
        return 0.008
    elif 17 <= hour <= 19:
        return 0.004
    else:
        return 0.012


def generate_hourly_od_entropy(pop, D, hourly_profiles, total_daily_trips):
    hourly_OD = {}

    for h in range(24):
        beta_h = time_dependent_beta(h)
        factor = hourly_profiles.get(f"hour_{h}", 1.0)
        trips_h = total_daily_trips * factor
        hourly_OD[f"hour_{h}"] = entropy_gravity_od(pop, D, beta_h, trips_h)

    return hourly_OD


def scale_hourly_od_to_total(hourly_OD, target_daily_trips):
    """
    Scales OD so total daily trips match target value.
    """
    current_total = 0.0
    for OD in hourly_OD.values():
        current_total += np.sum(OD)

    if current_total == 0:
        raise ValueError("OD is empty — cannot scale")

    scale = target_daily_trips / current_total

    scaled_OD = {}
    for hour, OD in hourly_OD.items():
        scaled_OD[hour] = OD * scale

    print("OD scaled")
    print(f"   current total = {current_total:,.0f}")
    print(f"   target total  = {target_daily_trips:,.0f}")
    print(f"   scale factor  = {scale:.4f}")

    return scaled_OD


def sparsify_top_k(hourly_OD, k=10):
    """
    Keep only top-k destinations per origin for each hourly OD matrix.
    """
    new_hourly = {}

    for h, OD in hourly_OD.items():
        OD = np.array(OD)
        n = OD.shape[0]
        new_OD = np.zeros_like(OD)

        for i in range(n):
            row = OD[i]
            if np.all(row == 0):
                continue
            idx = np.argsort(row)[-k:]
            new_OD[i, idx] = row[idx]

        new_hourly[h] = new_OD

    return new_hourly


def save_hourly_od_xlsx_matrix(hourly_OD, zones_gdf, filename="od_matrices.xlsx"):
    n = len(zones_gdf)
    zone_ids = [f"Z{i}" for i in range(n)]

    centroids = zones_gdf.geometry.centroid

    zones_3857 = zones_gdf.copy()
    zones_3857["geometry"] = centroids

    coords_3857 = pd.DataFrame({
        "zone_id": zone_ids,
        "x_3857": zones_3857.geometry.x,
        "y_3857": zones_3857.geometry.y
    })

    zones_4326 = zones_3857.to_crs(epsg=4326)

    coords_4326 = pd.DataFrame({
        "zone_id": zone_ids,
        "lon_4326": zones_4326.geometry.x,
        "lat_4326": zones_4326.geometry.y
    })

    coords_df = coords_3857.merge(coords_4326, on="zone_id")

    written_any = False

    with pd.ExcelWriter(filename, engine="openpyxl") as writer:
        coords_df.to_excel(writer, sheet_name="zones_coords", index=False)

        for hour, OD in hourly_OD.items():
            OD = np.asarray(OD)
            if OD.shape[0] != n:
                print(f"Skipping {hour}: shape mismatch {OD.shape} vs {n}")
                continue
            df = pd.DataFrame(OD, index=zone_ids, columns=zone_ids)
            df.to_excel(writer, sheet_name=str(hour)[:31])
            written_any = True

        if not written_any:
            pd.DataFrame({"error": ["no valid OD exported"]})\
                .to_excel(writer, sheet_name="fallback")

    print(f"Saved OD matrix with CRS (4326 + 3857) → {filename}")


def od_diagnostics(hourly_OD):
    for h, OD in hourly_OD.items():
        OD = np.array(OD)
        total = OD.size
        zeros = np.sum(OD == 0)
        sparsity = zeros / total

        print(f"{h}:")
        print(f"  sparsity = {sparsity:.2%}")
        print(f"  max flow = {OD.max():.3f}")
        print(f"  mean flow = {OD.mean():.6f}")
        print()


def plot_academic_od_heatmap(city_name, hourly_OD, save_path=None):
    import matplotlib.pyplot as plt
    import seaborn as sns

    windows = {
        "Morning peak\n(07–09)": ["hour_7", "hour_8", "hour_9"],
        "Midday activity\n(12–15)": ["hour_12", "hour_13", "hour_14"],
        "Evening peak\n(17–19)": ["hour_17", "hour_18", "hour_19"],
        "Off peak\n(01–06)": ["hour_1"]
    }

    mats = []
    for _, hours in windows.items():
        mat = np.sum([np.array(hourly_OD[h], dtype=np.float32) for h in hours], axis=0)
        mat[mat < 1] = 0
        mats.append(mat)

    all_vals = np.concatenate([m.flatten() for m in mats if m.size > 0])
    vmax = np.percentile(all_vals, 99)
    log_vmax = np.log1p(vmax)

    plt.style.use("seaborn-v0_8-white")
    fig, axes = plt.subplots(1, 4, figsize=(18, 5), dpi=300)
    cmap = sns.color_palette("rocket_r", as_cmap=True)
    im = None

    for i, (ax, mat, title) in enumerate(zip(axes, mats, windows.keys())):
        im = sns.heatmap(
            np.log1p(mat), ax=ax, cmap=cmap, vmin=0, vmax=log_vmax,
            cbar=False, square=True, linewidths=0
        )
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.text(-0.08, 1.05, chr(65 + i), transform=ax.transAxes,
                fontsize=14, fontweight="bold")
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_linewidth(0.6)

    cbar = fig.colorbar(
        im.collections[0], ax=axes, orientation="horizontal",
        fraction=0.04, pad=0.18, shrink=0.85
    )
    tick_vals = np.array([0, 1, 5, 10, 20, 50, 100, 200])
    tick_vals = tick_vals[tick_vals <= vmax]
    cbar.set_ticks(np.log1p(tick_vals))
    cbar.set_ticklabels(tick_vals)
    cbar.set_label("Trip intensity (log scale; darker = stronger flows)", fontsize=10)

    fig.suptitle(f"Urban Mobility Structure – {city_name}",
                 fontsize=14, fontweight="bold", y=1.05)
    plt.subplots_adjust(bottom=0.25, top=0.88, wspace=0.05)

    if save_path is not None:
        fig.savefig(f"{save_path}/{city_name}_OD_academic.png", dpi=600, bbox_inches="tight")
        fig.savefig(f"{save_path}/{city_name}_OD_academic.pdf", bbox_inches="tight")

    return fig
