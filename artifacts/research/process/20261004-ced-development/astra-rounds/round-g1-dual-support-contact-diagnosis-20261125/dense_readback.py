"""Restore the two d02 trajectories with both archived radial assemblies."""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from collections import Counter
from pathlib import Path

import mujoco
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
geom = importlib.import_module("dense_geometry")

PRIOR = HERE.parent / "round-g1-radial30-contact-20261125"
sys.path.insert(0, str(PRIOR))
registered = importlib.import_module("static_screen")

old = registered.old
ROOT, BASE = old.ROOT, old.BASE
read, write, sha, require = old.read, old.write, old.sha, old.require
PLAN = "3df98fe7e537dce1196aef233dd0dad2fc347c41eae30e0202f06da5f5a102e2"
GEN = {
    15: "f33d25e2ebac4342e32e3878263ab6f92838ed51c715a3b0c28a9777a4dad892",
    30: "5c09e38b82e09a8c52de407bee97775aca8b8a48b4d14a3bfc387ffd626fa212",
}
BATCH = {15: "train-radial15-timing-01", 30: "train-radial30-contact-d02-02"}
TIMES = (896, 912, 1168, 1200, 1216, 1220, 1221, 1224, 1227, 1228)
RIGHT = ("g1_dual_id8_plate", "right_finger_geom")
LEFT = ("g1_dual_id7_crossbar", "left_finger_geom")
FIELDS = (
    "joint_positions_rad",
    "joint_velocities_rad_s",
    "finger_positions_m",
    "finger_velocities_m_s",
    "object_geom_position_m",
    "object_geom_rotation_row_major",
    "object_linear_velocity_m_s",
    "object_angular_velocity_rad_s",
    "tcp_position_m",
    "sim_time_s",
)


def digest(x):
    return hashlib.sha256(
        json.dumps(x, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def sources():
    plan = read(HERE / "plan.json", PLAN)
    require(
        sha(HERE / "plan.md") == plan["plan_md_sha256"] and plan["failed_generation"] == GEN[30],
        "incorrect diagnosis plan",
    )
    for k, v in plan["inputs_sha256"].items():
        require(sha(ROOT / k) == v, "changed plan input " + k)
    cases = {}
    models = {}
    files = {}
    for offset, batch in BATCH.items():
        folder = BASE / "batches" / batch / "d02"
        case = old.checked_case(folder)
        lock = BASE / "builds" / GEN[offset] / "runtime-source"
        read(lock / "runtime-build.json", GEN[offset])
        path = lock / case["geometry"]["asset_path"]
        require(
            sha(path) == case["asset_sha256"] == sha(ROOT / case["geometry"]["asset_path"]),
            "wrong physical file",
        )
        model = old.checked_model(path, case["geometry"])
        require(
            len(case["states"]) == {15: 1222, 30: 1229}[offset]
            and len(case["index"]["frames"]) == {15: 146, 30: 147}[offset],
            "wrong population",
        )
        receipt = read(folder / "instance/receipt.json")
        allocation = read(folder / "allocation.json", receipt["allocation_sha256"])
        require(allocation["runtime_build_sha256"] == GEN[offset], "foreign runtime")
        for row in case["index"]["frames"]:
            require(
                sha(folder / "instance" / row["file"]) == row["file_sha256"], "changed RGB-D input"
            )
        cases[offset] = case
        models[offset] = model
        files[offset] = {
            "asset_path": str(path.relative_to(ROOT)),
            "asset_sha256": sha(path),
            "runtime_build_sha256": GEN[offset],
            "receipt_sha256": sha(folder / "instance/receipt.json"),
            "truth_sha256": case["truth_sha256"],
            "index_sha256": case["index_sha256"],
        }
    return cases, models, files


def kinematics(case, model):
    data = mujoco.MjData(model)
    for row in case["states"]:
        residual = old.restore(model, data, row)
        yield row, data, residual


def separation_key(summary, selected):
    return next(r for r in summary["minimum_each_pair"] if tuple(r["pair"]) == selected)


def current_contact_rows(detail, case):
    groups = []
    bypair = Counter()
    steps_by = {}
    ix = {tuple(k): i for i, k in enumerate(detail["pair_order"])}
    for row in detail["states"]:
        step = row["step"]
        contacts = row["reconstructed_contacts"]
        pairs = Counter(
            tuple(sorted(c["pair"])) for c in contacts if c["category"] == "unauthorized"
        )
        if pairs:
            groups.append(
                {
                    "step": step,
                    "pairs": [{"geometries": k, "multiplicity": n} for k, n in pairs.items()],
                }
            )
        for k, n in pairs.items():
            bypair[k] += n
            steps_by.setdefault(k, []).append(step)
    critical = {}
    for step in TIMES:
        if step >= len(detail["states"]):
            continue
        row = detail["states"][step]
        vals = {}
        for label, key in (("left_finger_id7_crossbar", LEFT), ("right_finger_id8_plate", RIGHT)):
            j = ix[key]
            raw = row["raw_signed_mm"][j]
            fb = {v[0]: v for v in row["separation_witness"]}.get(j)
            vals[label] = {
                "raw_mj_geomDistance_mm": raw,
                "certified_mm": fb[1] if fb else raw,
                "method": fb[2] if fb else "mj_geomDistance",
            }
        critical[step] = {
            **vals,
            "reconstructed_contacts": row["reconstructed_contacts"],
            "archive_contact_pairs": case["states"][step]["contact_pairs"],
        }
    return {
        "unauthorized_contact_timesteps": groups,
        "by_geometric_pair": [
            {"geometries": list(k), "states": steps_by[k], "engine_contact_points": n}
            for k, n in bypair.items()
        ],
        "critical": critical,
    }


def fixtures(model):
    names = ["object_geom", *old.PARTS, *geom.ARMS]
    return {
        s: {
            "id": model.geom(s).id,
            "shape": int(model.geom(s).type[0]),
            "body": model.body(int(model.geom(s).bodyid[0])).name,
            "geom_group": int(model.geom(s).group[0]),
            "contype": int(model.geom(s).contype[0]),
            "conaffinity": int(model.geom(s).conaffinity[0]),
            "body_local_position_m": model.geom(s).pos.tolist(),
            "body_local_quaternion_wxyz": model.geom(s).quat.tolist(),
            "half_extent_m": model.geom(s).size.tolist(),
        }
        for s in names
    }


def occupancy(trace, case, model, zones, output):
    zone_keys = list(zones)
    centers = np.array([(low + high) / 2 for low, high in zones.values()])
    half = np.array([(high - low) / 2 for low, high in zones.values()])
    steps = []
    minimum = {}
    overlaps = []
    total_samples = Counter()
    joint_face_counts = Counter()
    worst = Counter()
    for state, d, residual in kinematics(case, model):
        step = state["physics_step"]
        for k, v in residual.items():
            worst[k] = max(worst[k], v)
        boxes = {}
        distances = {}
        labels = {}
        for name in geom.ARMS:
            box = geom.local_box(model, d, name)
            desc = geom.describe(box)
            boxes[name] = desc
            gap, axis = geom.separation(box, centers, half)
            distances[name] = gap.tolist()
            labels[name] = axis.tolist()
            for j, v in enumerate(gap):
                region = zone_keys[j]
                key = name + ";" + region
                if key not in minimum or v < minimum[key]["max_sat_gap_m"]:
                    minimum[key] = {
                        "step": step,
                        "max_sat_gap_m": float(v),
                        "axis_ordinal": int(axis[j]),
                    }
                if v > geom.TOL_M:
                    continue
                cut = geom.intersect(box, *zones[region])
                isface = region.endswith("face")
                classification = (
                    "positive_volume_intersection"
                    if cut["positive_3d_volume"]
                    else "observed_face_intersection"
                    if cut["vertices_m"] and isface
                    else "boundary_or_numeric_uncertainty"
                )
                overlaps.append(
                    {
                        "step": step,
                        "hand": name,
                        "zone": region,
                        "classification": classification,
                        "max_sat_gap_m": float(v),
                        "axis_ordinal": int(axis[j]),
                        **cut,
                    }
                )
                total_samples[key] += 1
                if isface:
                    joint_face_counts[key] += 1
        st = {k: state[k] for k in FIELDS}
        steps.append(
            {
                "step": step,
                "source_state_sha256": digest(state),
                "restored_mujoco_state_sha256": old.MuJoCoRGBDCamera._physics_state_hash(d),
                "recorded_state": st,
                "qpos": d.qpos.tolist(),
                "qvel": d.qvel.tolist(),
                "restored_fk_residual": residual,
                "world_from_object_rotation": d.geom("object_geom").xmat.tolist(),
                "world_object_center_m": d.geom("object_geom").xpos.tolist(),
                "occupancy": boxes,
                "max_separating_axis_gap_m": distances,
                "argmax_axis_ordinal": labels,
            }
        )
    path = output / f"occupation-{trace}.json.gz"
    write(
        path,
        {
            "trajectory": trace,
            "zone_order": zone_keys,
            "object_local_units": "metres",
            "states": steps,
        },
    )
    return {
        "trajectory": trace,
        "samples": len(steps),
        "boxes": len(steps) * len(geom.ARMS),
        "raw_sha256": sha(path),
        "minimum_by_hand_and_zone": minimum,
        "nonseparated_step_counts": dict(total_samples),
        "contact_with_registered_connection_faces": dict(joint_face_counts),
        "all_intersections": overlaps,
        "maximum_fk_residuals": dict(worst),
    }


def angular_difference(a, b):
    r = np.asarray(a).reshape(3, 3).T @ np.asarray(b).reshape(3, 3)
    # atan2 remains stable for the small angles in the synchronized histories.
    s = np.linalg.norm([r[2, 1] - r[1, 2], r[0, 2] - r[2, 0], r[1, 0] - r[0, 1]]) * 0.5
    return float(np.arctan2(s, (np.trace(r) - 1) * 0.5))


def differences(cases):
    out = []
    for a, b in zip(cases[15]["states"], cases[30]["states"], strict=False):
        step = a["physics_step"]
        require(step == b["physics_step"], "asynchronous step join")
        values = {
            k: (np.asarray(b[k]) - a[k]).tolist()
            for k in FIELDS
            if k != "object_geom_rotation_row_major"
        }
        values["object_rotation_difference_rad"] = angular_difference(
            a["object_geom_rotation_row_major"], b["object_geom_rotation_row_major"]
        )
        out.append(
            {
                "step": step,
                "delta_30_minus_15": values,
                "joint_max_abs_rad": max(abs(x) for x in values["joint_positions_rad"]),
                "finger_max_abs_mm": 1000 * max(abs(x) for x in values["finger_positions_m"]),
                "object_center_distance_mm": 1000
                * float(np.linalg.norm(values["object_geom_position_m"])),
                "tcp_distance_mm": 1000 * float(np.linalg.norm(values["tcp_position_m"])),
            }
        )
    return out


def command_trace(case):
    inst = case["folder"] / "instance"
    cmds = read(inst / "backend-commands.json")
    rc = read(inst / "receipt.json")
    run = read(inst / "run.json")
    require(
        sha(inst / "backend-commands.json") == rc["full_commands_sha256"], "wrong backend commands"
    )
    stop = next(c for c in cmds if c["type"] == "emergency_stop" and c["accepted"])
    moves = [
        c
        for c in cmds
        if c["accepted"] and c["type"] not in {"hold_current_joints", "emergency_stop"}
    ]
    return {
        "native_run_sha256": sha(inst / "run.json"),
        "backend_command_sha256": rc["full_commands_sha256"],
        "action_endpoints": [
            {
                k: a.get(k)
                for k in (
                    "skill",
                    "status",
                    "entered_step",
                    "end_step",
                    "dispatch_step",
                    "controller_return_step",
                )
            }
            for a in run["actions"]
        ],
        "command_count": len(cmds),
        "accepted_type_histogram": dict(Counter(c["type"] for c in cmds if c["accepted"])),
        "last_accepted_nonhold_motion": moves[-1],
        "last_events": cmds[-5:],
        "commands_after_emergency_stop": [
            c for c in cmds if c["command_seq"] > stop["command_seq"]
        ],
        "safe_stop_success": run["safe_stop"]["success"],
        "stop": run["stop"],
    }


def worker(output):
    output.mkdir(exist_ok=False)
    cases, models, files = sources()
    zones = {}
    for mount, m in models.items():
        joined = old.radial.compiled_faces(m, mount)
        require(len(joined) == 6, "missing compiled faces")
        zones.update(geom.zones(m, mount))
    matrix = {}
    occupation = {}
    storage = {}
    for tr, case in cases.items():
        occupation[tr] = occupancy(tr, case, models[tr], zones, output)
        for mount, m in models.items():
            name = f"trace{tr}_mount{mount}"
            base = tr == mount
            d = mujoco.MjData(m)
            summary, detail = registered.distance_profile(
                case, cases[mount]["geometry"], m, d, registered.pairs(m), base
            )
            p = output / (name + ".json.gz")
            write(p, detail)
            matrix[name] = {
                "trace": tr,
                "mount": mount,
                "type": "native exact restoration"
                if base
                else "fixed native states / other registered assembly",
                "left_beam": separation_key(summary, LEFT),
                "right_plate": separation_key(summary, RIGHT),
                **summary,
                **current_contact_rows(detail, case),
                "detail_sha256": sha(p),
            }
            print(
                name,
                matrix[name]["left_beam"]["minimum_mm"],
                matrix[name]["right_plate"]["minimum_mm"],
                flush=True,
            )
    compare = differences(cases)
    write(output / "trajectory-control-differences.json.gz", compare)
    write(output / "matrix-summary.json", matrix)
    write(
        output / "occupation-summary.json",
        {
            "zones_bounds_m": {k: [lo.tolist(), hi.tolist()] for k, (lo, hi) in zones.items()},
            "observed_traces": occupation,
            "geometry_masks": {k: fixtures(m) for k, m in models.items()},
        },
    )
    write(
        output / "trajectory-summary.json",
        {
            "shared_physics_steps": len(compare),
            "max_by_metric": {
                k: max(compare, key=lambda r: r[k])["step"]
                for k in (
                    "joint_max_abs_rad",
                    "finger_max_abs_mm",
                    "object_center_distance_mm",
                    "tcp_distance_mm",
                )
            },
            "delta_at_registered_steps": [r for r in compare if r["step"] in TIMES],
            "additional_30_steps_without_15_peer": list(
                range(len(compare), len(cases[30]["states"]))
            ),
            "measurements_sha256": sha(output / "trajectory-control-differences.json.gz"),
            "source": files,
            "native_control": {k: command_trace(c) for k, c in cases.items()},
        },
    )
    for p in sorted(output.iterdir()):
        storage[p.name] = sha(p)
    write(
        output / "seal.json",
        {
            "plan_sha256": PLAN,
            "programs_sha256": {
                p.name: sha(p)
                for p in (
                    Path(__file__),
                    Path(geom.__file__),
                    Path(registered.__file__),
                    Path(old.__file__),
                )
            },
            "mujoco_version": mujoco.__version__,
            "numpy_version": np.__version__,
            "physical_integrations": 0,
            "egl_captures": 0,
            "files_sha256": storage,
        },
    )


if __name__ == "__main__":
    worker(Path(sys.argv[1]))
