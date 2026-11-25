"""Reduce independent real-physics trajectories to axis-resolved development motion allowances."""

import argparse
import gzip
import json
from pathlib import Path

import numpy as np
from scripts.graduation.g1_complete_cv_calibrate import digest
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry, support_axes
from scripts.graduation.g1_complete_cv_support_domain import FREE_PHASES, descending, state_rows


def _peak(table, stage, key, values):
    row = table.setdefault(stage, dict(normal_windows=0, stop_branches=0))
    row[key] = np.maximum(row.get(key, np.zeros_like(values)), values)


def _read(path):
    return json.loads(
        gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
    )


def _signed_peaks(delta, axes):
    # Keep each sampled corner displacement intact in world coordinates.
    return np.array(
        [np.max(delta[:, i].reshape(-1, 3) @ axes.T, axis=0) for i in range(delta.shape[1])]
    )


def fit(root, asset, *, signed=False, domain=False, descent=False):
    g = MotionGeometry(Model(asset))
    local = root / "experiments/results/g1-complete-cv-repair-20261125"
    native = local / "mount-brake-02/braking"
    remaining = local / "mount-brake-03/braking"
    hist = root / "experiments/results/g1-visibility-pose-repair-20261124/batches"
    tables = {}
    axes = support_axes() if signed or domain or descent else None
    domain_states = {}
    domain_speed = {}
    sources = {}

    def normal(stage, q, dq, f, df, center, rot):
        q, dq, f, df, center, rot = map(np.asarray, (q, dq, f, df, center, rot))
        rot = rot.reshape(-1, 3, 3)
        n = len(q) - 8
        if n < 1:
            return
        c, r, _, _ = g.solids(q, f, center, rot)
        vertices = g.vertices(c, r)
        if domain:
            if stage in FREE_PHASES:
                rows = state_rows(g, q, f, dq, df, center)
                domain_states.setdefault(stage, []).extend(rows[::8].round(7).tolist())
                speed = _signed_peaks(240 * np.diff(vertices, axis=0), axes)
                domain_speed[stage] = np.maximum(domain_speed.get(stage, 0), speed)
            return
        if descent:
            if stage != "APPROACH":
                return
            velocity = state_rows(g, q, f, dq, df, center)[:, -3:]
            eligible = descending(velocity[:n])
            count = int(eligible.sum())
            if not count:
                return
            for tick in range(1, 9):
                cc, rr = g.forecast(
                    q[:n][eligible],
                    f[:n][eligible],
                    dq[:n][eligible],
                    df[:n][eligible],
                    center[:n][eligible],
                    rot[:n][eligible],
                    tick / 240,
                    False,
                )
                _peak(
                    tables,
                    stage,
                    "normal",
                    _signed_peaks(vertices[tick : n + tick][eligible] - g.vertices(cc, rr), axes),
                )
                _peak(
                    tables,
                    stage,
                    "velocity_increment",
                    abs(velocity[tick : n + tick][eligible] - velocity[:n][eligible]).max(0),
                )
            tables[stage]["normal_windows"] += count
            return
        relative = (vertices - center[:, None, None, :]) @ rot[:, None]
        for tick in range(1, 9):
            cc, rr = g.forecast(
                q[:n],
                f[:n],
                dq[:n],
                df[:n],
                center[:n],
                rot[:n],
                tick / 240.0,
                stage in ("LIFT", "MOVE_TO_REGION", "PLACE"),
            )
            v = g.vertices(cc, rr)
            actual = vertices[tick : n + tick]
            if signed:
                _peak(tables, stage, "normal", _signed_peaks(actual - v, axes))
                continue
            _peak(tables, stage, "normal", abs(actual - v).max(axis=(0, 2)))
            _peak(
                tables,
                stage,
                "relative_normal",
                abs(
                    relative[tick : n + tick, g.hand_start : g.load_start]
                    - relative[:n, g.hand_start : g.load_start]
                ).max(axis=(0, 2)),
            )
            _peak(
                tables,
                stage,
                "speed_increment",
                np.max(
                    np.maximum(0.0, abs(dq[tick : n + tick]).max(axis=1) - abs(dq[:n]).max(axis=1))
                ),
            )
        tables[stage]["normal_windows"] += n
        _peak(tables, stage, "peak_joint_speed", abs(dq).max(axis=0))

    for p in (native / "empty-native.json.gz", remaining / "loaded-native.json.gz"):
        sources[str(p.relative_to(root))] = digest(p)
        frames = _read(p)["frames"]
        for stage in dict.fromkeys(r["phase"] for r in frames):
            rows = [r for r in frames if r["phase"] == stage]
            normal(
                stage,
                *[
                    [r[k] for r in rows]
                    for k in (
                        "q_rad",
                        "qvel_rad_s",
                        "finger_q_m",
                        "finger_qvel_m_s",
                        "cube_xyz_m",
                        "cube_rotation",
                    )
                ],
            )
    for label in ("train-radial15-timing-01", "train-radial30-contact-d02-02"):
        path = hist / label / "d02/instance"
        p = path / "offline-truth.json"
        sources[str(p.relative_to(root))] = digest(p)
        rows = _read(p)["samples"]
        info = _read(path / "run.json")["actions"]
        for action in info[:2]:
            # Stop before the first forbidden contact; it is tested independently.
            rr = rows[
                action["dispatch_step"] : min(
                    action.get("end_step", len(rows) - 1) + 1, len(rows) - 1
                )
            ]
            normal(
                action["skill"],
                *[
                    [r[k] for r in rr]
                    for k in (
                        "joint_positions_rad",
                        "joint_velocities_rad_s",
                        "finger_positions_m",
                        "finger_velocities_m_s",
                        "object_geom_position_m",
                        "object_geom_rotation_row_major",
                    )
                ],
            )
    by_files = [
        native / "empty-continuous.npz",
        remaining / "loaded-continuous.npz",
        *(local / "mount-historic-brake-01/braking").glob("*-end-wings-continuous.npz"),
    ]
    for p in sorted(by_files):
        sources[str(p.relative_to(root))] = digest(p)
        with np.load(p, allow_pickle=False) as archive:
            data = {k: archive[k] for k in ("stage", "qpos", "qvel", "cube_matrix", "cube_m")}
            for i, stage in enumerate(data["stage"]):
                q = data["qpos"][i]
                cr = data["cube_matrix"][i]
                cp = data["cube_m"][i]
                c, r, _, _ = g.solids(q[:, :7], q[:, 7:9], cp, cr)
                vert = g.vertices(c, r)
                if descent:
                    if stage == "APPROACH":
                        vel = data["qvel"][i, :1]
                        v = state_rows(g, q[:1, :7], q[:1, 7:9], vel[:, :7], vel[:, 7:9], cp[:1])[
                            :, -3:
                        ]
                        if descending(v)[0]:
                            _peak(tables, stage, "stop", _signed_peaks(vert - vert[0], axes))
                            tables[stage]["stop_branches"] += 1
                    continue
                if domain:
                    if stage in FREE_PHASES:
                        speed = _signed_peaks(240 * np.diff(vert, axis=0), axes)
                        domain_speed[stage] = np.maximum(domain_speed.get(stage, 0), speed)
                    continue
                if signed:
                    _peak(tables, stage, "stop", _signed_peaks(vert - vert[0], axes))
                    tables[stage]["stop_branches"] += 1
                    continue
                stop = abs(vert - vert[0]).max(axis=(0, 2))
                _peak(tables, stage, "stop", stop)
                rel = (vert[:, g.hand_start : g.load_start] - cp[:, None, None, :]) @ cr[:, None]
                relative_stop = abs(rel - rel[0]).max(axis=(0, 2))
                _peak(tables, stage, "relative_stop", relative_stop)
                tables[stage]["stop_branches"] += 1
                speed = abs(data["qvel"][i, 0, :7]).max()
                bins = tables[stage].setdefault("brakes", {})
                for ceiling in (0.025, 0.075, 0.15, 0.25, 0.4):
                    if speed <= ceiling:
                        _peak(bins, str(ceiling), "stop", stop)
                        _peak(bins, str(ceiling), "relative_stop", relative_stop)
                        bins[str(ceiling)]["stop_branches"] += 1
    if descent:
        row = tables["APPROACH"]
        return dict(
            schema="g1.simulation.correlated-descent.v1",
            parts=g.names,
            asset_sha256=digest(asset),
            sources=sources,
            normal_windows=row["normal_windows"],
            stop_branches=row["stop_branches"],
            **{
                key: (np.ceil(row[key] * 1e8) / 1e8).tolist()
                for key in ("normal", "stop", "velocity_increment")
            },
        )
    if domain:
        return dict(
            schema="g1.simulation.signed-applicability.v1",
            parts=g.names,
            asset_sha256=digest(asset),
            sources=sources,
            phases={
                stage: dict(
                    states=rows,
                    corner_speed_m_s=(np.ceil(domain_speed[stage] * 1e6) / 1e6).tolist(),
                )
                for stage, rows in domain_states.items()
            },
        )
    if signed:
        return dict(
            schema="g1.simulation.directional-motion.v1",
            asset_sha256=digest(asset),
            sources=sources,
            parts=g.names,
            axes=axes.tolist(),
            physics_ticks=8,
            brake_ticks=240,
            phases={
                stage: dict(
                    normal_windows=row["normal_windows"],
                    stop_branches=row["stop_branches"],
                    normal=(np.ceil(row["normal"] * 1e8) / 1e8).tolist(),
                    stop=(np.ceil(row["stop"] * 1e8) / 1e8).tolist(),
                )
                for stage, row in tables.items()
            },
        )
    for row in tables.values():
        for key in (
            "normal",
            "stop",
            "relative_normal",
            "relative_stop",
            "peak_joint_speed",
            "speed_increment",
        ):
            if key in row:
                row[key] = row[key].round(8).tolist()
        for binrow in row.get("brakes", {}).values():
            for k in ("stop", "relative_stop"):
                binrow[k] = binrow[k].round(8).tolist()
    return dict(
        schema="g1.simulation.empirical-motion.v1",
        asset_sha256=digest(asset),
        sources=sources,
        parts=g.names,
        phases=tables,
        physics_dt_s=1 / 240,
        horizon_ticks=8,
        stop_ticks=240,
        applicability="observed controlled development actuator range; not a hardware bound",
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--asset", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--signed", action="store_true")
    p.add_argument("--domain", action="store_true")
    p.add_argument("--descent", action="store_true")
    a = p.parse_args()
    with a.out.open("x") as stream:
        json.dump(
            fit(Path.cwd(), a.asset, signed=a.signed, domain=a.domain, descent=a.descent),
            stream,
            sort_keys=True,
            allow_nan=False,
            indent=2,
        )
        stream.write("\n")
