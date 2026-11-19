"""Plot 5×5 raw optical-Z depth around archived world-Z extrema."""

from argparse import ArgumentParser
from hashlib import sha256
from json import loads
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")

from matplotlib import pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

ROUND = Path(__file__).resolve().parent
INPUT = ROUND / "derived-v2/1804-top-extrema.json"
INPUT_SHA256 = "27228c492ee68d6be4ad717a15f4bd1c5a76662b2b665702d43f34e12e3dbc06"


def read_panel(extreme):
    pixel = extreme["pixel"]
    x, y = pixel["u"], pixel["v"]
    points = {(row["u"], row["v"]): row for row in extreme["neighbors"]}
    u = range(x - 2, x + 3)
    v = range(y - 2, y + 3)
    if len(points) != 25 or set(points) != {(a, b) for a in u for b in v}:
        raise ValueError("archived depth neighborhood must be a unique 5×5 UV square")
    if points[x, y]["depth_float32_m"] != pixel["depth_float32_m"]:
        raise ValueError("archived center and neighborhood depth differ")
    depth_mm = [[1000 * points[a, b]["depth_float32_m"] for a in u] for b in v]
    invalid = [[not points[a, b]["mask_valid"] for a in u] for b in v]
    return u, v, np.ma.array(depth_mm, mask=invalid), pixel


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    payload = INPUT.read_bytes()
    if sha256(payload).hexdigest() != INPUT_SHA256:
        raise ValueError("derived 5×5 archive differs from its verified SHA256")
    cases = loads(payload)
    panels = [
        (f"{seed} · {label}", read_panel(cases[seed][key]))
        for seed in ("1804", "1802")
        for label, key in (
            ("minimum world Z", "min_final_top"),
            ("maximum world Z", "max_final_top"),
        )
    ]
    cmap = matplotlib.colormaps["viridis"].with_extremes(bad="#a7afb8")
    common_depth = np.concatenate([panel[2].compressed() for _, panel in panels])
    low, high = float(common_depth.min()), float(common_depth.max())
    figure, axes = plt.subplots(
        2, 2, figsize=(9.8, 8.2), constrained_layout=True, facecolor="white"
    )
    for ax, (title, (u, v, depth, pixel)) in zip(axes.flat, panels, strict=True):
        image = ax.imshow(depth, cmap=cmap, vmin=low, vmax=high, interpolation="nearest")
        ax.set_xticks(range(5), labels=u)
        ax.set_yticks(range(5), labels=v)
        ax.set_xlabel("u (px)", labelpad=3)
        ax.set_ylabel("v (px)", labelpad=3)
        z_mm = 1000 * pixel["world_z_m"]
        ax.set_title(f"{title}\nWorld Z at ({u[2]}, {v[2]}) = {z_mm:.3f} mm", fontsize=11)
        for j, row in enumerate(depth):
            for i, sample in enumerate(row):
                valid = not np.ma.is_masked(sample)
                color = "white" if valid and (sample - low) / (high - low) < 0.56 else "#121820"
                ax.text(
                    i,
                    j,
                    f"{sample:.3f}" if valid else "invalid",
                    color=color,
                    ha="center",
                    va="center",
                    fontsize=8,
                )
        for width, color in ((3.5, "black"), (1.35, "white")):
            ax.add_patch(Rectangle((1.52, 1.52), 0.96, 0.96, fill=False, lw=width, ec=color))
    figure.colorbar(
        image,
        ax=axes.ravel().tolist(),
        fraction=0.045,
        pad=0.035,
        label="Raw optical depth (mm), shared scale",
    )
    figure.suptitle(
        "Archived 5×5 depth neighborhoods\nOutline = center pixel   •   Gray = invalid mask",
        fontsize=14,
    )
    with args.output.open("xb") as stream:
        figure.savefig(stream, dpi=150, format="png")
    plt.close(figure)


if __name__ == "__main__":
    main()
