import numpy as np
import networkx as nx

# =========================================================
# 1. DISTANCE MATRIX
# =========================================================
def compute_distance_matrix(nodes_sel, G):

    node_ids = [str(n) for n in nodes_sel]
    n = len(node_ids)
    D = np.zeros((n, n))

    print(f"Computing distances for {n} nodes...")

    for i, source in enumerate(node_ids):

        lengths = nx.single_source_dijkstra_path_length(
            G,
            source,
            weight="length"
        )

        for j, target in enumerate(node_ids):
            D[i, j] = lengths.get(target, np.inf)

    return D


# =========================================================
# 2. BASE GRAVITY MODEL (FIXED)
# =========================================================
def build_base_od(pop, D, beta=0.5):
    """
    Build a stable OD probability matrix (SUM = 1)
    """

    pop = np.asarray(pop, dtype=float)
    D = np.asarray(D, dtype=float) / 1000.0  # 🔥 meters → km

    n = len(pop)
    OD = np.zeros((n, n))

    for i in range(n):
        for j in range(n):

            if i == j:
                continue

            impedance = np.exp(-beta * D[i, j])
            OD[i, j] = pop[i] * pop[j] * impedance

    total = OD.sum()

    if total > 0:
        OD /= total

    return OD


# =========================================================
# 3. IPF BALANCING (REALISM BOOST)
# =========================================================
def ipf_balance(M, O, D, iters=10):

    M = M.copy()
    O = np.asarray(O, dtype=float)
    D = np.asarray(D, dtype=float)

    for _ in range(iters):

        row_sum = M.sum(axis=1)
        row_sum[row_sum == 0] = 1
        M *= (O / row_sum)[:, None]

        col_sum = M.sum(axis=0)
        col_sum[col_sum == 0] = 1
        M *= (D / col_sum)[None, :]

    return M


def apply_production_attraction(base, pop):
    """
    Adds asymmetry (home-work structure)
    """

    pop = np.asarray(pop, dtype=float)

    # productions: people leaving zones
    O = pop * 2.5  # trips per capita

    # attractions: slightly different
    np.random.seed(42)
    D = pop * (0.7 + 0.6 * np.random.rand(len(pop)))

    return ipf_balance(base, O, D)


# =========================================================
# 4. HOURLY OD GENERATION (FINAL MODEL)
# =========================================================
def generate_hourly_od(pop, D, hourly_profiles, total_daily_trips):

    print("🔹 Building base OD structure...")

    base = build_base_od(pop, D, beta=0.5)

    # add asymmetry
    base = apply_production_attraction(base, pop)

    # small noise (controlled)
    noise = np.random.lognormal(mean=0, sigma=0.15, size=base.shape)
    base *= noise
    base /= base.sum()

    hourly_OD = {}

    for h in range(24):

        factor = hourly_profiles.get(f"hour_{h}", 1.0)

        trips_h = total_daily_trips * factor

        hourly_OD[f"hour_{h}"] = base * trips_h

    return hourly_OD


# =========================================================
# 5. OPTIONAL SCALING (KEEP)
# =========================================================
def scale_hourly_od_to_total(hourly_OD, target_daily_trips):

    current_total = sum(np.sum(v) for v in hourly_OD.values())

    if current_total == 0:
        raise ValueError("OD is empty")

    scale = target_daily_trips / current_total

    scaled = {h: v * scale for h, v in hourly_OD.items()}

    print(f"✅ OD scaled")
    print(f"   current total = {current_total:,.0f}")
    print(f"   target total  = {target_daily_trips:,.0f}")
    print(f"   scale factor  = {scale:.4f}")

    return scaled