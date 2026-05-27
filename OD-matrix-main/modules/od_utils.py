import numpy as np
import networkx as nx
import pandas as pd

# =========================================================
# 1. DISTANCE MATRIX
# =========================================================
def compute_distance_matrix(nodes_sel, G):

    node_ids = [str(n) for n in nodes_sel]

    n = len(node_ids)
    D = np.zeros((n, n))

    print(f"Computing distances for {n} nodes...")

    for i, source in enumerate(node_ids):

        if source not in G:
            continue

        lengths = nx.single_source_dijkstra_path_length(
            G,
            source,
            weight="length"
        )

        for j, target in enumerate(node_ids):
            D[i, j] = lengths.get(target, np.inf)

    return D

import numpy as np

def entropy_gravity_od(pop, D, beta, total_trips, noise_sigma=0.4):
    """
    Realistic entropy-gravity OD model
    """

    pop = np.asarray(pop, dtype=float)
    D = np.asarray(D, dtype=float)

    n = len(pop)

    # -----------------------------
    # 1. GRAVITY CORE
    # -----------------------------
    OD = np.zeros((n, n))

    for i in range(n):
        for j in range(n):

            if i == j:
                continue

            impedance = np.exp(-beta * D[i, j])

            OD[i, j] = pop[i] * pop[j] * impedance

    # -----------------------------
    # 2. ENTROPY NOISE (KEY FIX)
    # -----------------------------
    noise = np.random.lognormal(
        mean=0.0,
        sigma=noise_sigma,
        size=(n, n)
    )

    OD = OD * noise

    # -----------------------------
    # 3. REMOVE EXTREME SPARSITY
    # -----------------------------
    OD += 0.01 * OD.mean()

    # -----------------------------
    # 4. NORMALIZATION
    # -----------------------------
    sum_od = OD.sum()

    if sum_od > 0:
        OD = OD / sum_od * total_trips

    return OD


def build_base_od(pop, D, beta=0.5):     # NEW 
    pop = np.asarray(pop, dtype=float)
    D = np.asarray(D, dtype=float) / 1000  # 🔥 convert to km

    n = len(pop)
    OD = np.zeros((n, n))

    for i in range(n):
        for j in range(n):

            if i == j:
                continue

            # gravity with proper decay
            impedance = np.exp(-beta * D[i, j])

            OD[i, j] = pop[i] * pop[j] * impedance

    # normalize to probability matrix
    total = OD.sum()
    if total > 0:
        OD = OD / total

    return OD

def apply_production_attraction(OD, pop): # NEW 

    pop = np.asarray(pop, dtype=float)

    # productions (origins)
    O = pop * 2.5   # trips per capita

    # attractions (destinations)
    D = pop * (0.5 + 0.5 * np.random.rand(len(pop)))  
    # adds asymmetry

    return ipf_balance(OD, O, D, iters=10)

def generate_hourly_od_realistic(pop, D, hourly_profiles, total_daily_trips):

    # -----------------------------
    # 1. BASE STRUCTURE (ONCE)
    # -----------------------------
    base = build_base_od(pop, D, beta=0.5)

    # -----------------------------
    # 2. ADD REALISM (flows not symmetric)
    # -----------------------------
    base = apply_production_attraction(base, pop)

    # -----------------------------
    # 3. ADD LIGHT NOISE (stable)
    # -----------------------------
    noise = np.random.lognormal(mean=0, sigma=0.15, size=base.shape)
    base = base * noise

    base = base / base.sum()

    # -----------------------------
    # 4. HOURLY DISTRIBUTION
    # -----------------------------
    hourly_OD = {}

    for h in range(24):

        factor = hourly_profiles.get(f"hour_{h}", 1.0)

        trips_h = total_daily_trips * factor

        hourly_OD[f"hour_{h}"] = base * trips_h

    return hourly_OD

def generate_hourly_od_entropy(pop, D, beta, hourly_profiles, total_daily_trips):

    OD_base = entropy_gravity_od(pop, D, beta, total_daily_trips)

    hourly_OD = {}

    for h in range(24):

        factor = hourly_profiles.get(f"hour_{h}", 1.0)

        hourly_OD[f"hour_{h}"] = OD_base * factor

    return hourly_OD

# =========================================================
# 2. GRAVITY MODEL CORE
# =========================================================
def gravity_matrix(pop, D, beta):

    pop = np.asarray(pop, dtype=float)
    D = np.asarray(D, dtype=float)
    D = D / 1000  # meters → km     # NEW
    n = len(pop)
    M = np.zeros((n, n))

    for i in range(n):
        for j in range(n):

            if i == j:
                continue

            M[i, j] = pop[i] * pop[j] * np.exp(-beta * D[i, j])

    return M

def normalize_matrix(M):

    total = M.sum()

    if total > 0:
        return M / total

    return M

# =========================================================
# 3. IPF BALANCING (optional but useful)
# =========================================================
def ipf_balance(M, O, D, iters=20):

    M = M.copy()

    O = np.asarray(O, dtype=float)
    D = np.asarray(D, dtype=float)

    for _ in range(iters):

        row = M.sum(axis=1)
        row[row == 0] = 1
        M *= (O / row)[:, None]

        col = M.sum(axis=0)
        col[col == 0] = 1
        M *= (D / col)[None, :]

    return M


def generate_hourly_OD_realistic(pop, D, beta, hourly_profiles):

    pop = np.asarray(pop, dtype=float)
    D = np.asarray(D, dtype=float)

    n = len(pop)

    # -----------------------------------
    # 1. total daily trips (realistic)
    # -----------------------------------
    trips_per_capita = 2.5
    total_trips_day = np.sum(pop) * trips_per_capita
    print(f"nb of trips: {total_trips_day}")
    # -----------------------------------
    # 2. gravity structure
    # -----------------------------------
    M = gravity_matrix(pop, D, beta)

    # normalize into probability matrix
    P = normalize_matrix(M)

    # -----------------------------------
    # 3. build hourly OD
    # -----------------------------------
    hourly_OD = {}

    for h in range(24):

        factor = hourly_profiles.get(f"hour_{h}", 1.0)

        hourly_total = total_trips_day * factor

        OD_h = P * hourly_total

        hourly_OD[f"hour_{h}"] = OD_h

    return hourly_OD

# =========================================================
# 4. HOURLY OD GENERATION (OLD VERSION)
# =========================================================
def generate_hourly_OD123(pop, D, beta, hourly_profiles):

    pop = np.asarray(pop, dtype=float)
    D = np.asarray(D, dtype=float)

    # -----------------------------
    # gravity base matrix
    # -----------------------------
    base = gravity_matrix(pop, D, beta)

    total = base.sum()
    if total > 0:
        base = base / total

    # -----------------------------
    # hourly expansion
    # -----------------------------
    hourly_OD = {}

    total_pop = np.sum(pop)

    for h in range(24):

        factor = hourly_profiles.get(f"hour_{h}", 1.0)

        hourly_OD[f"hour_{h}"] = base * factor * total_pop

    return hourly_OD



def scale_hourly_od_to_total(hourly_OD, target_daily_trips):
    """
    Scales OD so total daily trips match target value.
    """

    # -----------------------------
    # compute current total
    # -----------------------------
    current_total = 0.0

    for OD in hourly_OD.values():
        current_total += np.sum(OD)

    if current_total == 0:
        raise ValueError("OD is empty — cannot scale")

    # -----------------------------
    # scaling factor
    # -----------------------------
    scale = target_daily_trips / current_total

    # -----------------------------
    # apply scaling
    # -----------------------------
    scaled_OD = {}

    for hour, OD in hourly_OD.items():
        scaled_OD[hour] = OD * scale

    print(f"✅ OD scaled")
    print(f"   current total = {current_total:,.0f}")
    print(f"   target total  = {target_daily_trips:,.0f}")
    print(f"   scale factor  = {scale:.4f}")

    return scaled_OD


import pandas as pd
import numpy as np


import pandas as pd
import numpy as np
import geopandas as gpd
from shapely.geometry import Point

import pandas as pd
import numpy as np

def save_hourly_od_xlsx_matrix(hourly_OD, zones_gdf, filename="od_matrices.xlsx"):

    # -----------------------------
    # ZONE IDS
    # -----------------------------
    n = len(zones_gdf)
    zone_ids = [f"Z{i}" for i in range(n)]

    # -----------------------------
    # ENSURE CENTROIDS (POINTS)
    # -----------------------------
    centroids = zones_gdf.geometry.centroid

    # -----------------------------
    # CRS: EPSG:3857 (PROJECTED)
    # -----------------------------
    zones_3857 = zones_gdf.copy()
    zones_3857["geometry"] = centroids

    coords_3857 = pd.DataFrame({
        "zone_id": zone_ids,
        "x_3857": zones_3857.geometry.x,
        "y_3857": zones_3857.geometry.y
    })

    # -----------------------------
    # CRS: EPSG:4326 (LAT/LON)
    # -----------------------------
    zones_4326 = zones_3857.to_crs(epsg=4326)

    coords_4326 = pd.DataFrame({
        "zone_id": zone_ids,
        "lon_4326": zones_4326.geometry.x,
        "lat_4326": zones_4326.geometry.y
    })

    # -----------------------------
    # MERGE COORDS
    # -----------------------------
    coords_df = coords_3857.merge(coords_4326, on="zone_id")

    written_any = False

    # -----------------------------
    # WRITE EXCEL
    # -----------------------------
    with pd.ExcelWriter(filename, engine="openpyxl") as writer:

        # -----------------------------
        # COORDINATES SHEET
        # -----------------------------
        coords_df.to_excel(writer, sheet_name="zones_coords", index=False)

        # -----------------------------
        # HOURLY MATRICES
        # -----------------------------
        for hour, OD in hourly_OD.items():

            OD = np.asarray(OD)

            if OD.shape[0] != n:
                print(f"⚠️ Skipping {hour}: shape mismatch {OD.shape} vs {n}")
                continue

            df = pd.DataFrame(
                OD,
                index=zone_ids,
                columns=zone_ids
            )

            df.to_excel(writer, sheet_name=str(hour)[:31])
            written_any = True

        # -----------------------------
        # FALLBACK
        # -----------------------------
        if not written_any:
            pd.DataFrame({"error": ["no valid OD exported"]})\
                .to_excel(writer, sheet_name="fallback")

    print(f"✅ Saved OD matrix with CRS (4326 + 3857) → {filename}")

import numpy as np

def aggregate_rush_hour_od(hourly_OD, hours):
    return np.sum([hourly_OD[h] for h in hours], axis=0)


import matplotlib.pyplot as plt
from scipy.ndimage import gaussian_filter

def plot_od_heatmap(OD, title="OD Heatmap"):
    plt.figure(figsize=(8, 6))
    # plt.show(OD, cmap="hot", interpolation="nearest") 

    OD_smooth = gaussian_filter(OD, sigma=1)
    plt.imshow(OD_smooth, cmap="hot") 

  # plt.imshow(np.log1p(OD), cmap="hot")
    plt.colorbar(label="Trips")
    plt.title(title)
    plt.xlabel("Destination zones")
    plt.ylabel("Origin zones")

    plt.tight_layout()
    plt.show()


import numpy as np

def aggregate_time_windows(hourly_OD):
    """
    Convert 24 hourly OD matrices into 3 behavioral periods
    """

    def sum_hours(hours):
        mats = [np.array(hourly_OD[h], dtype=np.float32) for h in hours]
        return np.sum(mats, axis=0)

    return {
        "morning_rush_7_9": sum_hours(["hour_7", "hour_8"]),
        "lunch_12_15": sum_hours(["hour_12", "hour_13", "hour_14"]),
        "evening_rush_17_19": sum_hours(["hour_17", "hour_18"])
    }


def time_dependent_beta(hour):
    """
    Behavioral model of mobility:
    - Morning: long commuting trips
    - Midday: short local trips
    - Evening: medium trips
    - Night/off-peak: very local
    """
    if 7 <= hour <= 9:
        return 0.003   # long trips
    elif 12 <= hour <= 14:
        return 0.008   # short trips
    elif 17 <= hour <= 19:
        return 0.004   # medium trips
    else:
        return 0.012   # very local


def generate_hourly_od_entropy(pop, D, hourly_profiles, total_daily_trips):

    hourly_OD = {}

    for h in range(24):

        beta_h = time_dependent_beta(h)

        factor = hourly_profiles.get(f"hour_{h}", 1.0)

        trips_h = total_daily_trips * factor

        OD_h = entropy_gravity_od(
            pop,
            D,
            beta_h,
            trips_h
        )

        hourly_OD[f"hour_{h}"] = OD_h

    return hourly_OD
    

def integerize_od_matrix(OD):
    """
    Convert float OD to integer trips while preserving totals.
    Uses stochastic rounding.
    """

    OD = np.asarray(OD)

    # integer part
    OD_int = np.floor(OD).astype(int)

    # fractional part
    remainder = OD - OD_int

    # random draw
    rand = np.random.rand(*OD.shape)

    # add 1 where random < remainder
    OD_int += (rand < remainder).astype(int)

    return OD_int

def integerize_hourly_od(hourly_OD):

    new_hourly = {}

    for h, OD in hourly_OD.items():
        new_hourly[h] = integerize_od_matrix(OD)

    return new_hourly

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

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


import numpy as np

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

            # get top-k indices
            idx = np.argsort(row)[-k:]

            new_OD[i, idx] = row[idx]

        new_hourly[h] = new_OD

    return new_hourly


# =========================================================
# 🧠 ACADEMIC STYLE OD HEATMAP FIGURE (PNAS / NATURE STYLE)
# =========================================================
def plot_academic_od_heatmap(city_name, hourly_OD, save_path=None):

    import numpy as np
    import matplotlib.pyplot as plt
    import seaborn as sns

    # -----------------------------
    # TIME WINDOWS
    # -----------------------------
    windows = {
        "Morning peak\n(07–09)": ["hour_7", "hour_8", "hour_9"],
        "Midday activity\n(12–15)": ["hour_12", "hour_13", "hour_14"],
        "Evening peak\n(17–19)": ["hour_17", "hour_18", "hour_19"],
        "Off peak\n(01–06)": ["hour_1"]
    }

    # -----------------------------
    # AGGREGATE MATRICES
    # -----------------------------
    mats = []
    for _, hours in windows.items():
        mat = np.sum(
            [np.array(hourly_OD[h], dtype=np.float32) for h in hours],
            axis=0
        )

        # 🔥 IMPORTANT: remove weak noise flows
        mat[mat < 1] = 0

        mats.append(mat)

    # -----------------------------
    # GLOBAL NORMALIZATION
    # -----------------------------
    all_vals = np.concatenate([m.flatten() for m in mats if m.size > 0])
    vmax = np.percentile(all_vals, 99)

    log_vmax = np.log1p(vmax)

    # -----------------------------
    # FIGURE STYLE
    # -----------------------------
    plt.style.use("seaborn-v0_8-white")

    fig, axes = plt.subplots(1, 4, figsize=(18, 5), dpi=300)

    cmap = sns.color_palette("rocket_r", as_cmap=True)

    im = None

    # -----------------------------
    # PLOTS
    # -----------------------------
    for i, (ax, mat, title) in enumerate(zip(axes, mats, windows.keys())):

        im = sns.heatmap(
            np.log1p(mat),
            ax=ax,
            cmap=cmap,
            vmin=0,
            vmax=log_vmax,
            cbar=False,
            square=True,
            linewidths=0
        )

        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.set_xticks([])
        ax.set_yticks([])

        # panel label (A, B, C, D)
        ax.text(
            -0.08, 1.05,
            chr(65 + i),
            transform=ax.transAxes,
            fontsize=14,
            fontweight="bold"
        )

        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_linewidth(0.6)

    # -----------------------------
    # HORIZONTAL COLORBAR (CLEAN + BOTTOM)
    # -----------------------------
    cbar = fig.colorbar(
        im.collections[0],
        ax=axes,
        orientation="horizontal",
        fraction=0.04,
        pad=0.18,
        shrink=0.85
    )

    # meaningful tick values (original scale)
    tick_vals = np.array([0, 1, 5, 10, 20, 50, 100, 200])
    tick_vals = tick_vals[tick_vals <= vmax]

    cbar.set_ticks(np.log1p(tick_vals))
    cbar.set_ticklabels(tick_vals)

    cbar.set_label(
        "Trip intensity (log scale; darker = stronger flows)",
        fontsize=10
    )

    # -----------------------------
    # TITLE
    # -----------------------------
    fig.suptitle(
        f"Urban Mobility Structure – {city_name}",
        fontsize=14,
        fontweight="bold",
        y=1.05
    )

    # spacing tuned for journal layout
    plt.subplots_adjust(bottom=0.25, top=0.88, wspace=0.05)

    # -----------------------------
    # SAVE
    # -----------------------------
    if save_path is not None:
        fig.savefig(
            f"{save_path}/{city_name}_OD_academic.png",
            dpi=600,
            bbox_inches="tight"
        )
        fig.savefig(
            f"{save_path}/{city_name}_OD_academic.pdf",
            bbox_inches="tight"
        )

    return fig