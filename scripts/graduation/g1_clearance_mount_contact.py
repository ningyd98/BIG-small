"""Recheck signed distances and forbidden contact on both archived approach trajectories."""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import mujoco
import numpy as np
from scripts.graduation import g1_clearance_mount as mount
from scripts.graduation.g1_clearance_mount_physics import ALLOWED, digest, write

INPUTS = (
    (
        "train-radial15-timing-01",
        1222,
        "92d1115feb5a1367efeb08f945f7e678b40eb349064490488b39b63586d791b1",
        "assets/robots/franka_panda/scene_g1_development_dual_id7_y115_id8_x115_low_bracket_v3.xml",
    ),
    (
        "train-radial30-contact-d02-02",
        1229,
        "f53da7fd5dec6282f6b3decd648afb2fcf2bc1131f2130ab037b0620f0cb7daf",
        mount.PARENT_ASSET,
    ),
)
PAIRS = tuple(
    itertools.product(
        ("left_finger_geom", "right_finger_geom", "hand"),
        tuple(f"g1_dual_id{code}_{part}" for code in (7, 8) for part in mount.PARTS),
    )
)


def box_gap(model, data, first, second):
    """Return a signed separating-axis witness for an inconclusive zero engine query."""
    r, s = (data.geom(g).xmat.reshape(3, 3) for g in (first, second))
    normals = np.vstack((r.T, s.T, np.cross(r.T[:, None, :], s.T[None, :, :]).reshape(9, 3)))
    lengths = np.linalg.norm(normals, axis=1)
    axes = normals[lengths > 1e-10] / lengths[lengths > 1e-10, None]
    delta = data.geom(second).xpos - data.geom(first).xpos
    return float(
        max(
            abs(axes @ delta)
            - abs(axes @ r) @ model.geom(first).size
            - abs(axes @ s) @ model.geom(second).size
        )
    )


def read_trace(model, rows):
    data = mujoco.MjData(model)
    joint_addr = int(model.joint("object_free").qposadr[0])
    resolved = [((a, b), model.geom(a).id, model.geom(b).id) for a, b in PAIRS]
    detail = []
    minima = {"/".join(p): {"gap_m": 2.0, "step": None} for p in PAIRS}
    forbidden = []
    maximum_residual = 0.0
    for step, row in enumerate(rows):
        if row["physics_step"] != step:
            raise ValueError("nonconsecutive native archive")
        data.qpos[:7] = row["joint_positions_rad"]
        data.qpos[7:9] = row["finger_positions_m"]
        data.qpos[joint_addr : joint_addr + 3] = row["object_position_m"]
        mujoco.mju_mat2Quat(
            data.qpos[joint_addr + 3 : joint_addr + 7],
            np.array(row["object_geom_rotation_row_major"]),
        )
        mujoco.mj_forward(model, data)
        residual = np.linalg.norm(data.site("tcp").xpos - row["tcp_position_m"])
        maximum_residual = max(maximum_residual, float(residual))
        pairs = [
            [model.geom(c.geom1).name, model.geom(c.geom2).name]
            for c in data.contact
            if frozenset((model.geom(c.geom1).name, model.geom(c.geom2).name)) not in ALLOWED
        ]
        if pairs:
            forbidden.append(dict(step=step, pairs=pairs))
        gaps, zero_witnesses = [], {}
        for j, ((a, b), ia, ib) in enumerate(resolved):
            gap = float(mujoco.mj_geomDistance(model, data, ia, ib, 2.0, None))
            gaps.append(gap)
            if gap == 0.0:
                gap = box_gap(model, data, a, b)
                zero_witnesses[str(j)] = gap
            if gap < minima[a + "/" + b]["gap_m"]:
                minima[a + "/" + b] = dict(gap_m=gap, step=step)
        detail.append([step, gaps, zero_witnesses])
    if maximum_residual > 2e-4:
        raise ValueError(f"failed to restore native TCP within 0.2 mm: {maximum_residual}")
    return dict(
        states=len(rows),
        minimum_by_pair=minima,
        forbidden=forbidden,
        maximum_tcp_residual_m=maximum_residual,
    ), detail


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    base = a.repo / "experiments/results/g1-visibility-pose-repair-20261124/batches"
    entries = []
    for name, count, expected, original in INPUTS:
        path = base / name / "d02/instance/offline-truth.json"
        if digest(path) != expected:
            raise ValueError("prior failed trajectory differs")
        trace = json.loads(path.read_bytes())
        rows = trace["samples"]
        if count != len(rows) or trace["asset_sha256"] != digest(a.repo / original):
            raise ValueError("wrong previous model or number of physics states")
        for label, asset in (("original", original), ("end-wings", mount.ASSET_PATH)):
            model = mujoco.MjModel.from_xml_path(str(a.repo / asset))
            summary, detail = read_trace(model, rows)
            raw = a.out / (name + "-" + label + ".json.gz")
            write(raw, dict(pair_order=PAIRS, rows=detail))
            entry = dict(
                case=name,
                mount=label,
                asset_sha256=digest(a.repo / asset),
                trace_sha256=expected,
                raw_sha256=digest(raw),
                **summary,
            )
            entries.append(entry)
            print(name, label, summary["forbidden"], flush=True)
    write(
        a.out / "summary.json",
        dict(
            schema="g1.end-wings.historical-contact.v1",
            integrations=0,
            complete_skill_dispatches=0,
            entries=entries,
        ),
    )


if __name__ == "__main__":
    main()
