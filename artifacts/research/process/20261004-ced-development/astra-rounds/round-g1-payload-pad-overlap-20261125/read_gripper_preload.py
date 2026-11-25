"""Compare the native gripper effort signal with sealed contact and displacement labels."""

import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
from scripts.graduation.g1_complete_cv_geometry import Model

HERE = Path(__file__).resolve().parent
PLAN = "af9abc72ffaa9b2b3d5e2e92fbcf99559b2f13411dacaa7d22955b1f6d3ce7b2"
FIT_SUMMARY = "0f7b0d90d5514e6de3e4dae1fff0ed8c949ecf5e605718f75a83719c863c6ea6"
ASSET = Path("assets/robots/franka_panda") / (
    "scene_g1_development_dual_id7_minusx130_id8_plusx130_end_wings_v1.xml"
)
ASSET_SHA = "35f50ef8d18a13828541226552678b8ac3fcff4d597794957332f65eb623e1b6"
RAW = Path("experiments/results/g1-payload-pad-overlap-20261125/fit-pad-physics-01")
FINGERS = ("left_finger_act", "right_finger_act")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def calibration(path):
    if sha(path) != ASSET_SHA:
        raise ValueError("finger gains belong to the registered assembly only")
    tree = ElementTree.parse(path)
    actuators = [tree.find(f".//actuator/position[@name='{f}']") for f in FINGERS]
    if any(a is None or a.get("ctrlrange") != "0 0.04" for a in actuators):
        raise ValueError("unexpected finger actuator or travel")
    return np.array([(float(a.get("kp")), float(a.get("kv"))) for a in actuators]).T


def pair_array(pair):
    return [float(v) for v in pair]


def dwell(source, matrix):
    packets = read(source / "rgbd-index.json")["rows"]
    oracle = {
        frame["frame_id"]: frame for frame in read(source / "offline-physics.json")["frame_labels"]
    }
    lift = [row["robot"] for row in packets if row["skill"] == "LIFT" and row["phase"] == "DWELL"]
    if len(lift) != 16 or any(
        b["physics_step"] - a["physics_step"] != 8 for a, b in zip(lift[:-1], lift[1:], strict=True)
    ):
        raise ValueError("unexpected registered dwell clock")
    xyz = np.asarray([r["tcp_position_m"] for r in lift])
    relative = [
        (np.asarray(oracle[row["frame_id"]]["center_m"]) - xyz[i])
        @ matrix(row["tcp_quaternion_wxyz"])
        for i, row in enumerate(lift)
    ]
    return {
        "duration_s": 0.5,
        "distinct_exposures": len(lift),
        "relative_xyz_delta_mm": pair_array(1000 * (relative[-1] - relative[0])),
        "max_tcp_excursion_mm": float(1000 * np.linalg.norm(xyz - xyz[0], axis=1).max()),
    }


def fit_course(root, key, model, gains, matrix):
    case = root / RAW / key
    receipt = read(case / "replay.json")
    source = root / receipt["source_dir"]
    raw = read(case / "transport-contact-manifolds.json.gz")["rows"]
    if len(raw) != 1081 or [raw[0][0], raw[-1][0]] != receipt["transport_range"]:
        raise ValueError("inconsistent native transport duration")
    commands = [r for r in read(source / "native-commands.json") if r["type"] == "gripper"]
    closed = [r for r in commands if r["accepted"] and not r["target_open"]]
    opened = [r for r in commands if r["accepted"] and r["target_open"]]
    if len(closed) != 1 or len(opened) != 1:
        raise ValueError("expected one accepted close and one accepted open")
    if not closed[0]["physics_step"] < raw[0][0] <= raw[-1][0] < opened[0]["physics_step"]:
        raise ValueError("transport is outside the effective close command")

    efforts, projections, offsets = [], [], []
    for tick, _, center, _, q, dq, _, patches in raw:
        tcp, rot, _ = model.forward(q[:7])
        axis = rot[:, 1]
        # The gripper is recorded at the saturated native close setpoint of 0.
        # Only encoder state enters this signed estimate of inward motor effort.
        efforts.append(gains[0] * np.asarray(q[7:9]) + gains[1] * np.asarray(dq[7:9]))
        offsets.append((np.asarray(center) - tcp) @ rot)
        forces = [[p[8] for p in patches if p[0] == side] for side in range(2)]
        if not all(forces):
            raise ValueError(f"fitting truth missing one pad at {tick}")
        # MuJoCo contacts are an independent, offline label. Newton's opposite
        # force on each pad is projected onto its own outward slide axis.
        projections.append(
            [(np.sum(f, axis=0) @ axis) * sense for f, sense in zip(forces, (-1, 1), strict=True)]
        )
    effort, force = np.asarray(efforts), np.asarray(projections)
    delta = effort - force
    shifts = np.asarray(offsets) - offsets[0]
    refusal = receipt["trigger_step"] - raw[0][0]
    duration = (raw[-1][0] - raw[0][0]) / 240
    return {
        "duration_s": duration,
        "native_transport_samples": len(raw),
        "min_encoder_effort_N": pair_array(effort.min(axis=0)),
        "min_pad_force_along_outward_slide_N": pair_array(force.min(axis=0)),
        "signed_effort_minus_projection_min_N": pair_array(delta.min(axis=0)),
        "signed_effort_minus_projection_max_N": pair_array(delta.max(axis=0)),
        "first_refusal": {
            "step": raw[refusal][0],
            "encoder_effort_N": pair_array(effort[refusal]),
            "pad_slide_force_N": pair_array(force[refusal]),
            "wrist_relative_xyz_delta_mm": pair_array(1000 * shifts[refusal]),
        },
        "relative_xyz_delta_mm": pair_array(1000 * shifts[-1]),
        "relative_x_rate_mm_s": float(1000 * shifts[-1, 0] / duration),
        "max_absolute_relative_xyz_change_per_eight_steps_mm": pair_array(
            1000 * np.max(abs(shifts[8:] - shifts[:-8]), axis=0)
        ),
        "lift_dwell": dwell(source, matrix),
    }


def main(root, output):
    if (
        sha(HERE / "plan.json") != PLAN
        or sha(HERE / "pad-physics-fit-results.public.json") != FIT_SUMMARY
    ):
        raise ValueError("fit plan or offline force receipts differ")
    summary = read(HERE / "pad-physics-fit-results.public.json")
    if any(sha(root / name) != expected for name, expected in summary["bindings"].items()):
        raise ValueError("frozen fitting evidence differs")
    unit = importlib.util.spec_from_file_location(
        "sealed_pad_summary", HERE / "pad-physics-summary.py"
    )
    reference = importlib.util.module_from_spec(unit)
    unit.loader.exec_module(reference)
    gains, model = calibration(root / ASSET), Model(root / ASSET)
    rows = {key: fit_course(root, key, model, gains, reference.matrix) for key in summary["cases"]}
    result = {
        "schema": "g1.pad.encoder-effort.fit-readback.v1",
        "plan_sha256": PLAN,
        "offline_force_truth_sha256": FIT_SUMMARY,
        "script_sha256": sha(Path(__file__)),
        "asset_sha256": ASSET_SHA,
        "native_finger_kp_and_kv": gains.tolist(),
        "records": rows,
        "scope": "Offline comparison of encoder effort and named pad slide force in known contact.",
        "qualification": False,
    }
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, allow_nan=False, indent=2, sort_keys=True)
        stream.write("\n")
    print(sum(r["native_transport_samples"] for r in rows.values()), sha(output))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=Path.cwd(), type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    main(args.root.resolve(), args.output)
