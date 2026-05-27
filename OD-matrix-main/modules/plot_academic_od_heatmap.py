import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns


# =========================================================
# 🧠 ACADEMIC STYLE OD HEATMAP FIGURE (PNAS / NATURE STYLE)
# =========================================================
def plot_academic_od_heatmap(city_name, hourly_OD, save_path=None):

    # -----------------------------
    # TIME WINDOWS (NEW SPEC)
    # -----------------------------
    windows = {
        "Morning peak\n(06–08)": ["hour_7", "hour_8", "hour_9"],
        "Midday activity\n(12–15)": ["hour_12", "hour_13", "hour_14"],
        "Evening peak\n(17–19)": ["hour_17", "hour_18", "hour_19"],
        "off-peak\n(01–06)": ["hour_1", "hour_2", "hour_3", "hour_4", "hour_5", "hour_6"]
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
        mats.append(mat)

    # -----------------------------
    # GLOBAL NORMALIZATION (IMPORTANT FOR SCIENCE FIGURES)
    # -----------------------------
    all_vals = np.concatenate([m.flatten() for m in mats])
    vmax = np.percentile(all_vals, 99)  # robust to outliers

    # -----------------------------
    # FIGURE STYLE (NATURE-LIKE)
    # -----------------------------
    plt.style.use("seaborn-v0_8-white")

    fig, axes = plt.subplots(1, 4, figsize=(18, 5), dpi=300)

    cmap = sns.color_palette("rocket_r", as_cmap=True)

    for ax, mat, title in zip(axes, mats, windows.keys()):

        sns.heatmap(
            np.log1p(mat),
            ax=ax,
            cmap=cmap,
            vmin=0,
            vmax=np.log1p(vmax),
            cbar=False,
            square=True
        )

        ax.set_title(title, fontsize=12, fontweight="bold")

        ax.set_xticks([])
        ax.set_yticks([])

        # thin frame (publication style)
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_linewidth(0.6)

    # -----------------------------
    # GLOBAL TITLE
    # -----------------------------
    fig.suptitle(
        f"Urban Mobility Structure – {city_name}",
        fontsize=14,
        fontweight="bold",
        y=1.02
    )

    plt.tight_layout()

    # -----------------------------
    # SAVE (PUBLICATION QUALITY)
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