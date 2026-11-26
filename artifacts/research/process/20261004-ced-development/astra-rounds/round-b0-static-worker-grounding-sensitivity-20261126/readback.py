"""Check the sealed optical sweep against independent passive originals."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

from cloud_edge_robot_arm.research.freeze_evidence import _read_frame
from cloud_edge_robot_arm.vision.top_grasp import _TCP_ABOVE_ESTIMATED_CENTER_M

HERE = Path(__file__).resolve().parent
PLAN_PATH = HERE / "plan.json"
PLAN = json.loads(PLAN_PATH.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def check_wire(row, width, height):
    pixel = row["pixel"]
    wire = row["normalized_1000"]
    sizes = (width, height)
    require(
        all(
            0 <= p < size
            and 0 <= q <= 1000
            and q == -(-1000 * p // size)
            and p == min(size - 1, q * size // 1000)
            for p, q, size in zip(pixel, wire, sizes, strict=True)
        ),
        "independent normalized wire mismatch",
    )


def check_worker(row):
    top = row["tracker_top_m"]
    require(
        row["worker_grasp_input_m"][:2] == top[:2],
        "planner XYZ substituted for worker ground input",
    )
    require(
        abs(row["worker_grasp_input_m"][2] - top[2] - row["initial_tcp_z_offset_m"]) <= 1e-14
        and abs(row["initial_tcp_z_offset_m"] - row["planner_tcp_m"][2] + top[2]) <= 1e-14,
        "worker anchor offset differs",
    )
    require(row["signed_depth_bound_m"] is None, "unsigned depth bound unexpectedly present")


def extreme(rows, field, references, original):
    points = np.asarray([row[field] for row in rows])
    delta = points[:, None, :] - points[None, :, :]
    pair_distance = np.linalg.norm(delta, axis=2)
    left, right = np.unravel_index(np.argmax(pair_distance), pair_distance.shape)
    errors = np.linalg.norm(points[None, :, :] - references[:, None, :], axis=2)
    target = next(i for i, row in enumerate(rows) if row["pixel"] == original)
    max_row = int(errors[0].argmax())
    threshold = PLAN["design"]["threshold_m"]
    return {
        "candidates": len(rows),
        "anchor_error_mm": float(errors[0, target] * 1000),
        "anchor_bias_xyz_mm": (1000 * (points[target] - references[0])).tolist(),
        "first_frame_max_error_mm": float(errors[0, max_row] * 1000),
        "first_frame_max_error_pixel": rows[max_row]["pixel"],
        "first_frame_over_10mm": int((errors[0] > threshold).sum()),
        "other_frames_max_error_mm": float(errors[1:].max() * 1000),
        "max_pair_distance_mm": float(pair_distance[left, right] * 1000),
        "pair_pixels": [rows[left]["pixel"], rows[right]["pixel"]],
        "worker_or_planner_z_span_mm": float(np.ptp(points[:, 2]) * 1000),
    }


def readback(optical, digest):
    root = Path(PLAN["private_input_directory"])
    cap = root / "capture"
    require(sha(optical) == digest, "unsealed optical sweep")
    for name, expected in PLAN["private_inputs_sha256"].items():
        require(sha(root / name) == expected, f"private input changed: {name}")
    prediction = read(optical)
    require(prediction["plan_sha256"] == sha(PLAN_PATH), "wrong plan binding")
    reg, receipt = read(root / "registration.json"), read(cap / "receipt.json")
    require(prediction["instruction"] == reg["instruction"], "wrong semantic task")
    require(prediction["owner_record_used"] is False, "unregistered owner receipt")
    for name, expected in receipt["files_sha256"].items():
        require(sha(cap / name) == expected, f"raw file changed: {name}")
    timeline = [json.loads(line) for line in (cap / "physical.jsonl").read_bytes().splitlines()]
    require(len(timeline) == PLAN["design"]["physical_states"], "wrong state count")
    by_step = {row["step"]: row for row in timeline}
    h = reg["scene"]["scene_parameters"]["target"]["half_size"][2]
    centers, top_centers = [], []
    masks = []
    for rec, pred in zip(receipt["frames"], prediction["frame_bindings"], strict=True):
        require(all(rec[k] == pred[k] for k in rec), "prediction frame binding changed")
        state = by_step[rec["step"]]
        require(state["sim_time_s"] == rec["sim_time_s"], "physical and frame clocks differ")
        center = np.asarray(state["object_center_m"])
        z_axis = np.asarray(state["object_rotation_row_major"]).reshape(3, 3)[:, 2]
        require(np.linalg.norm(z_axis - [0, 0, 1]) < 1e-8, "upright TCP reference unavailable")
        require(
            any(set(p) == {"object_geom", "table"} for p in state["contacts"]),
            "upright supported TCP reference unavailable",
        )
        centers.append(center)
        top_centers.append(center + h * z_axis)
        actual = _read_frame(cap / rec["folder"])
        require(actual.observation.frame_id == rec["frame_id"], "wrong native instance frame")
        masks.append((actual.instance_ids, actual.instance_labels))
    width, height = 320, 240
    check_wire(
        {
            "pixel": prediction["destination"],
            "normalized_1000": prediction["destination_normalized_1000"],
        },
        width,
        height,
    )
    rows = prediction["candidates"]
    require(len({tuple(row["pixel"]) for row in rows}) == len(rows), "duplicate candidate")
    for row in rows:
        check_wire(row, width, height)
    accepted = [row for row in rows if row["status"] == "ACCEPTED"]
    for row in accepted:
        check_worker(row)

    def label_at(mask, pixel):
        ids, names = mask
        x, y = pixel
        return names.get(ids[y * width + x])

    require(
        all(label_at(mask, prediction["destination"]) == "target_region_geom" for mask in masks),
        "wrong genuine destination",
    )
    actual_targets = [
        row
        for row in accepted
        if all(label_at(mask, row["pixel"]) == "object_geom" for mask in masks)
    ]
    original = prediction["target_anchor"]
    anchor_row = next(row for row in actual_targets if row["pixel"] == original)
    try:
        check_worker(anchor_row | {"worker_grasp_input_m": anchor_row["planner_tcp_m"]})
    except ValueError as error:
        negative = str(error)
        require(
            negative == "planner XYZ substituted for worker ground input",
            "wrong worker-coordinate control failure",
        )
    else:
        raise ValueError("planner XY substitution passes worker reader")

    center_ref = np.asarray(centers)
    tool_ref = center_ref + [0.0, 0.0, _TCP_ABOVE_ESTIMATED_CENTER_M]
    fields = {
        "planner_center_m": center_ref,
        "planner_tcp_m": tool_ref,
        "tracker_top_m": np.asarray(top_centers),
        "worker_grasp_input_m": tool_ref,
    }
    return {
        "optical_sha256": digest,
        "raw_files_verified": len(receipt["files_sha256"]),
        "frames": len(masks),
        "source_states": len(timeline),
        "total_enumerated_pixels": len(rows),
        "accepted_pixels": len(accepted),
        "accepted_native_object_pixels_all_frames": len(actual_targets),
        "rejected": dict(Counter(row["reason"] for row in rows if row["status"] == "REJECTED")),
        "anchor_worker_grasp_xyz_m": anchor_row["worker_grasp_input_m"],
        "metrics_fixture_pixel": {k: extreme(accepted, k, v, original) for k, v in fields.items()},
        "metrics_native_object_pixel": {
            k: extreme(actual_targets, k, v, original) for k, v in fields.items()
        },
        "negative_controls": prediction["negatives"] | {"planner_xy_substitution": negative},
        "actual_owner_pre_horizon_and_motion_bound": None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("optical", type=Path)
    parser.add_argument("digest")
    parser.add_argument("output", type=Path)
    options = parser.parse_args()
    result = readback(options.optical, options.digest)
    with options.output.open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")


if __name__ == "__main__":
    main()
