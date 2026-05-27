import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# =========================================================
# LOAD OD AND PLOT FLOWS
# =========================================================
def plot_city_flows(city_name):

    file = f"outputs/hourly_od_{city_name}.xlsx"

    xls = pd.ExcelFile(file)

    df = xls.parse(xls.sheet_names[0])

    # assume matrix format
    od = df.values

    plt.figure(figsize=(6,6))

    # flatten flows
    flows = []

    n = od.shape[0]

    for i in range(n):
        for j in range(n):
            if od[i, j] > np.percentile(od, 95):
                flows.append((i, j, od[i, j]))

    # normalize
    max_flow = max([f[2] for f in flows]) if flows else 1

    for i, j, f in flows:
        plt.plot([i, j], [i, j], linewidth=1 + 3*(f/max_flow), alpha=0.6)

    plt.title(f"OD Flow Structure: {city_name}")