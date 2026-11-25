"""Fit full eight-tick/240-stop development sweeps from the locked fitting trajectories."""

import argparse
import json
from pathlib import Path

import numpy as np
from scripts.graduation.g1_complete_cv_calibrate import digest
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry, support_axes
from scripts.graduation.g1_complete_cv_payload import (
    AXES,
    SPEED_CLASSES,
    STAGES,
    object_matrix,
    positive_support,
    snapshot,
    state_features,
)


def measurements(mg, archive, axes):
    with np.load(archive, allow_pickle=False) as z:
        q = z["q"].reshape(-1, 16)
        dq = z["qvel"].reshape(-1, 15)
        contacts = z["contacts"]
        origin = q[0]
        speed = float(abs(dq[0, :7]).max())
        if len(q) != 9 * 241:
            raise ValueError("all possible delays and stop states are required")
        c = q[:, 9:12]
        r = object_matrix(q)
        world, v, rel, rv = snapshot(mg, q, dq, c, r)
        w = positive_support(world, v, world[0], AXES)
        h = positive_support(rel, rv, rel[0], axes)
        return w, h, speed, int(contacts[:, :, -1].sum()), origin


def fit(asset, stops, normal):
    mg = MotionGeometry(Model(asset))
    axes = support_axes()
    source = {}
    tables = {}
    for case in ("fit-a", "fit-b", "fit-c"):
        index = stops / case / "index.json"
        reg = json.loads(index.read_bytes())
        raw = normal / case / "normal.npz"
        if (
            reg["case"] != case
            or reg["role"] != "train"
            or digest(raw) != reg["normal_sha256"]
            or reg["xml_sha256"] != digest(asset)
        ):
            raise ValueError("wrong or incomplete registered trajectory")
        source[case] = dict(stop_index=digest(index), normal=digest(raw))
        with np.load(raw) as z:
            pos = z["q"]
            vel = z["qvel"]
            ctrl = z["ctrl"]
            phase = z["stage"]
            center = z["centers"][:, 10]
            rot = z["rotation"][:, 10]
            for stage in STAGES:
                selected = np.flatnonzero(phase == stage)[::8]
                if not len(selected):
                    continue
                row = tables.setdefault(stage, dict(references=[], classes={}))
                row["references"].extend(
                    state_features(
                        mg,
                        pos[selected],
                        vel[selected],
                        ctrl[selected],
                        center[selected],
                        rot[selected],
                    )
                    .round(7)
                    .tolist()
                )
                for entry in reg["phases"][stage]:
                    file = index.parent / entry["file"]
                    if digest(file) != entry["sha256"]:
                        raise ValueError("physical branch bytes changed")
                    world, relative, v, bad, start = measurements(mg, file, axes)
                    if max(abs(start - pos[entry["step"]])) > 1e-10:
                        raise ValueError("mixed checkpoint")
                    if bad:
                        raise ValueError(
                            f"real forbidden contact in fit {case}/{stage}/{entry['step']}"
                        )
                    for bound in ["all", *[str(k) for k in SPEED_CLASSES if v <= k]]:
                        b = row["classes"].setdefault(
                            bound,
                            dict(
                                world=np.zeros_like(world),
                                relative=np.zeros_like(relative),
                                windows=0,
                                traces=set(),
                            ),
                        )
                        b["world"] = np.maximum(b["world"], world)
                        b["relative"] = np.maximum(b["relative"], relative)
                        b["windows"] += 1
                        b["traces"].add(case)
    for stage in tables.values():
        stage["classes"] = {
            key: dict(
                world=(np.ceil(1e8 * b["world"]) / 1e8).tolist(),
                relative=(np.ceil(1e8 * b["relative"]) / 1e8).tolist(),
                windows=b["windows"],
                traces=sorted(b["traces"]),
            )
            for key, b in stage["classes"].items()
            if len(b["traces"]) >= 2
        }
    return dict(
        schema="g1.loaded-and-free-braking.v1",
        asset_sha256=digest(asset),
        parts=mg.names,
        axes=axes.tolist(),
        phases=tables,
        sources=source,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("asset", "stops", "normal", "out"):
        p.add_argument("--" + k, required=True, type=Path)
    a = p.parse_args()
    r = fit(a.asset, a.stops, a.normal)
    with a.out.open("x") as f:
        json.dump(r, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    print(digest(a.out))
