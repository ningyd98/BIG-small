"""Fit the continuous cubic sweep through native tick geometry and endpoint encoder velocities."""

import argparse
import gzip
import json
from pathlib import Path

import numpy as np
from scripts.graduation.g1_complete_cv_calibrate import digest
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import (
    MotionGeometry,
    hermite_rate_limits,
    support_axes,
)
from scripts.graduation.g1_complete_cv_support_domain import FREE_PHASES


def fit(root, asset):
    g = MotionGeometry(Model(asset))
    axes = support_axes()
    private = root / "experiments/results/g1-complete-cv-repair-20261125"
    tables = {}
    sources = {}

    def keep(path):
        sources[str(path.relative_to(root))] = digest(path)

    def add(stage, q, f, dq, df, c, r, v, w):
        if stage not in FREE_PHASES or len(q) < 2:
            return
        q, f, dq, df, c, r, v, w = map(np.asarray, (q, f, dq, df, c, r, v, w))
        r = r.reshape(-1, 3, 3)
        x, dx = g.vertex_velocities(q, f, dq, df, c, r, v, w)
        limit = hermite_rate_limits(x, dx, axes)
        tables[stage] = np.maximum(tables.get(stage, 0.0), limit)

    new_keys = (
        "q_rad",
        "finger_q_m",
        "qvel_rad_s",
        "finger_qvel_m_s",
        "cube_xyz_m",
        "cube_rotation",
        "cube_linear_velocity_m_s",
        "cube_angular_velocity_rad_s",
    )
    old_keys = (
        "joint_positions_rad",
        "finger_positions_m",
        "joint_velocities_rad_s",
        "finger_velocities_m_s",
        "object_geom_position_m",
        "object_geom_rotation_row_major",
        "object_linear_velocity_m_s",
        "object_angular_velocity_rad_s",
    )
    for sub in (
        "mount-brake-02/braking/empty-native.json.gz",
        "mount-brake-03/braking/loaded-native.json.gz",
    ):
        f = private / sub
        keep(f)
        rows = json.loads(gzip.decompress(f.read_bytes()))["frames"]
        for stage in FREE_PHASES:
            rr = [x for x in rows if x["phase"] == stage]
            if rr:
                add(stage, *[[x[k] for x in rr] for k in new_keys])
    for name in ("train-radial15-timing-01", "train-radial30-contact-d02-02"):
        d = (
            root
            / "experiments/results/g1-visibility-pose-repair-20261124/batches"
            / name
            / "d02/instance"
        )
        raw = d / "offline-truth.json"
        actions = d / "run.json"
        keep(raw)
        keep(actions)
        rows = json.loads(raw.read_bytes())["samples"]
        for act in json.loads(actions.read_bytes())["actions"][:2]:
            rr = rows[
                act["dispatch_step"] : min(act.get("end_step", len(rows) - 1) + 1, len(rows) - 1)
            ]
            add(act["skill"], *[[x[k] for x in rr] for k in old_keys])

    def array(stage, q, dq, center, rotation):
        world = (rotation @ dq[:, 12:15, None])[:, :, 0]
        add(stage, q[:, :7], q[:, 7:9], dq[:, :7], dq[:, 7:9], center, rotation, dq[:, 9:12], world)

    for f in [
        private / "mount-brake-02/braking/empty-continuous.npz",
        private / "mount-brake-03/braking/loaded-continuous.npz",
        *sorted((private / "mount-historic-brake-01/braking").glob("*-end-wings-continuous.npz")),
    ]:
        keep(f)
        with np.load(f) as z:
            q, dq, center, r = (z[k] for k in ("qpos", "qvel", "cube_m", "cube_matrix"))
            for i, phase in enumerate(z["stage"]):
                if phase in FREE_PHASES:
                    array(str(phase), q[i], dq[i], center[i], r[i])
    for name in ("fit-a", "fit-b", "fit-c"):
        f = (
            root
            / "experiments/results/g1-skill-handoff-20261125/physical-capture-01"
            / name
            / "normal.npz"
        )
        keep(f)
        with np.load(f) as z:
            q, dq, center, r = (z[k] for k in ("q", "qvel", "centers", "rotation"))
            for phase in FREE_PHASES:
                mask = z["stage"] == phase
                array(phase, q[mask], dq[mask], center[mask, 10], r[mask, 10])
    return dict(
        schema="g1.discrete-physics.hermite.v1",
        sources=sources,
        asset_sha256=digest(asset),
        parts=g.names,
        phases={phase: (np.ceil(limit * 1e6) / 1e6).tolist() for phase, limit in tables.items()},
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--asset", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    with args.out.open("x") as f:
        json.dump(fit(Path.cwd(), args.asset), f, sort_keys=True, indent=2)
        f.write("\n")
