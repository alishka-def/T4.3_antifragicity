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

        noise = np.random.lognormal(mean=0.0, sigma=sigma, size=OD.shape)
        OD_stoch = OD * noise

        for i in range(n):
            row_sum = OD_stoch[i].sum()
            if row_sum == 0:
                continue
            redist_amount = redistribution * row_sum
            OD_stoch[i] *= (1 - redistribution)
            probs = np.random.dirichlet(np.ones(n))
            OD_stoch[i] += redist_amount * probs

        OD_stoch += 0.01 * OD_stoch.mean()

        for i in range(n):
            original = OD[i].sum()
            new = OD_stoch[i].sum()
            if new > 0:
                OD_stoch[i] *= (original / new)

        OD_stoch = np.clip(OD_stoch, 0, None)

        hourly_OD_stoch[hour] = OD_stoch

    return hourly_OD_stoch
