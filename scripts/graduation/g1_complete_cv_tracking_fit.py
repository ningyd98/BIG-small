"""Register additional continuous, precontact development trajectories, whole-trace split."""

import argparse
import json
from pathlib import Path

import numpy as np
from scripts.graduation.g1_complete_cv_calibrate import digest
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry, support_axes
from scripts.graduation.g1_complete_cv_motion_fit import _signed_peaks
from scripts.graduation.g1_complete_cv_support_domain import FREE_PHASES, descending, state_rows


def fit(base, asset):
    motion = MotionGeometry(Model(asset))
    axes = support_axes()
    output = {}
    lineage = {}
    for name in ("fit-a", "fit-b", "fit-c"):
        directory = base / name
        source = directory / "normal.npz"
        result = directory / "summary.json"
        info = json.loads(result.read_bytes())
        if info["role"] != "train" or info["forbidden_structural_contact_steps"]:
            raise ValueError("unexpected trajectory in development fit")
        lineage[name] = {f.name: digest(f) for f in (source, result)}
        with np.load(source, allow_pickle=False) as z:
            for phase in FREE_PHASES:
                keep = z["stage"] == phase
                if not np.any(keep):
                    continue
                q, v, c, r = (
                    z["q"][keep],
                    z["qvel"][keep],
                    z["centers"][keep, 10],
                    z["rotation"][keep, 10],
                )
                state = state_rows(motion, q[:, :7], q[:, 7:9], v[:, :7], v[:, 7:9], c)
                cc, rr, _, _ = motion.solids(q[:, :7], q[:, 7:9], c, r)
                vert = motion.vertices(cc, rr)
                n = len(q) - 8
                if n <= 0:
                    continue
                groups = [(phase, np.ones(n, bool))]
                if phase == "APPROACH":
                    groups.append(("DESCENT", descending(state[:n, -3:])))
                for key, indices in groups:
                    if not indices.any():
                        continue
                    row = output.setdefault(
                        key,
                        dict(
                            states=[],
                            windows=0,
                            normal=np.zeros((len(motion.names), len(axes))),
                            velocity_increment=np.zeros(3),
                        ),
                    )
                    row["windows"] += int(indices.sum())
                    if key != "DESCENT":
                        row["states"].extend(state[::8].round(7).tolist())
                    for k in range(1, 9):
                        pc, pr = motion.forecast(
                            q[:n, :7][indices],
                            q[:n, 7:9][indices],
                            v[:n, :7][indices],
                            v[:n, 7:9][indices],
                            c[:n][indices],
                            r[:n][indices],
                            k / 240,
                            False,
                        )
                        dev = vert[k : n + k][indices] - motion.vertices(pc, pr)
                        row["normal"] = np.maximum(row["normal"], _signed_peaks(dev, axes))
                        delta = abs(state[k : n + k, -3:][indices] - state[:n, -3:][indices]).max(0)
                        row["velocity_increment"] = np.maximum(row["velocity_increment"], delta)
    for row in output.values():
        for key in ("normal", "velocity_increment"):
            row[key] = (np.ceil(row[key] * 1e8) / 1e8).tolist()
    return dict(
        schema="g1.precontact.continuous-tracking.v1",
        sources=lineage,
        asset_sha256=digest(asset),
        parts=motion.names,
        phases=output,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", required=True, type=Path)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    a = parser.parse_args()
    with a.out.open("x") as f:
        json.dump(fit(a.directory, a.asset), f, allow_nan=False, sort_keys=True, indent=2)
        f.write("\n")
