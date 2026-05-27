import numpy as np
from scipy.spatial import cKDTree


def validate_model(sensor_df, hourly_OD_det, hourly_OD_stoch, hour_cols, nodes_sel):
    results = {
        "hourly_mse_det": [],
        "hourly_mse_stoch": []
    }

    observed = sensor_df[hour_cols].values  # (sensors, 24)

    node_count = hourly_OD_det["hour_0"].shape[0]

    observed = observed[:node_count, :]

    for h in hour_cols:

        OD_det = hourly_OD_det[h]
        OD_stoch = hourly_OD_stoch[h]

        # -----------------------------
        # model prediction = inflow per node
        # -----------------------------
        pred_det = np.sum(OD_det, axis=0)
        pred_stoch = np.sum(OD_stoch, axis=0)

        observed_h = observed[:, int(h.split("_")[1])]

        n = min(len(pred_det), len(observed_h))

        mse_det = np.mean((pred_det[:n] - observed_h[:n]) ** 2)
        mse_stoch = np.mean((pred_stoch[:n] - observed_h[:n]) ** 2)

        results["hourly_mse_det"].append(mse_det)
        results["hourly_mse_stoch"].append(mse_stoch)

    print(f"📊 Avg MSE (Det): {np.mean(results['hourly_mse_det'])}")
    print(f"📊 Avg MSE (Stoch): {np.mean(results['hourly_mse_stoch'])}")

    return results