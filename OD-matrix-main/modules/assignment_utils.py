import numpy as np

def controlled_rounding(hourly_OD):
    hourly_OD_int = np.rint(hourly_OD).astype(int)
    return hourly_OD_int

def stochastic_assignment_old(hourly_OD_det, node_ids, G, noise_std=0.05):
    """
    Add stochastic noise to deterministic hourly OD matrices.
    hourly_OD_det: dict of {hour: 2D numpy array} or pandas DataFrame
    Returns a dict of the same structure with stochastic OD matrices.
    """
    hourly_OD_stoch = {}

    for hour, OD in hourly_OD_det.items():
        OD_array = np.array(OD, dtype=float)  # ensure it's a numeric array
        noise = np.random.normal(0, noise_std, size=OD_array.shape)
        OD_noisy = OD_array * (1 + noise)
        # Ensure no negative trips
        OD_noisy[OD_noisy < 0] = 0
        hourly_OD_stoch[hour] = OD_noisy

    return hourly_OD_stoch


def stochastic_assignment123(hourly_OD_det, nodes_sel, G):

    hourly_OD_stoch = {}

    for hour, OD in hourly_OD_det.items():

        OD = np.asarray(OD)

        noise = np.random.normal(0, 0.05, size=OD.shape)

        OD_stoch = OD * (1 + noise)

        OD_stoch = np.clip(OD_stoch, 0, None)

        hourly_OD_stoch[hour] = OD_stoch

    return hourly_OD_stoch


import numpy as np

def stochastic_assignment(hourly_OD_det, nodes_sel, G,
                          sigma=0.5,
                          redistribution=0.2):
    """
    Strong stochastic OD assignment

    Parameters:
    - sigma: noise intensity (0.3–0.7 recommended)
    - redistribution: share of flow randomly redistributed (0–0.3)

    Returns:
    - hourly_OD_stoch: dict of OD matrices
    """

    hourly_OD_stoch = {}

    for hour, OD in hourly_OD_det.items():

        OD = np.asarray(OD, dtype=float)
        n = OD.shape[0]

        # -----------------------------
        # 1. LOG-NORMAL NOISE (REALISTIC)
        # -----------------------------
        noise = np.random.lognormal(mean=0.0, sigma=sigma, size=OD.shape)
        OD_stoch = OD * noise

        # -----------------------------
        # 2. REDISTRIBUTE FLOWS (KEY)
        # -----------------------------
        for i in range(n):

            row_sum = OD_stoch[i].sum()
            if row_sum == 0:
                continue

            # portion to redistribute
            redist_amount = redistribution * row_sum

            # remove from original
            OD_stoch[i] *= (1 - redistribution)

            # redistribute randomly
            probs = np.random.dirichlet(np.ones(n))
            OD_stoch[i] += redist_amount * probs

        # -----------------------------
        # 3. REMOVE EXTREME SPARSITY
        # -----------------------------
        OD_stoch += 0.01 * OD_stoch.mean()

        # -----------------------------
        # 4. PRESERVE ROW TOTALS (IMPORTANT)
        # -----------------------------
        for i in range(n):

            original = OD[i].sum()
            new = OD_stoch[i].sum()

            if new > 0:
                OD_stoch[i] *= (original / new)

        # -----------------------------
        # 5. CLEAN
        # -----------------------------
        OD_stoch = np.clip(OD_stoch, 0, None)

        hourly_OD_stoch[hour] = OD_stoch

    return hourly_OD_stoch