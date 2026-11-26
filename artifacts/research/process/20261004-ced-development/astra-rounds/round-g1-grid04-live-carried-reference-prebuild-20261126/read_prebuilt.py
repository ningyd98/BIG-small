"""Cold-read the actual native attempt and compare it with its frozen predecessor."""

import argparse
import base64
import gzip
import importlib
import io

import mujoco
import numpy as np
from PIL import Image
from run_prebuilt import NEW_ROOT, OUT, PLAN, ROOT, live, patch
from scripts.graduation.perception_io import read, sha, write

readback = importlib.import_module("read_handoff_live")


def compare():
    case = live.CASE
    old = ROOT / PLAN["old_attempt"] / case
    current = OUT / case
    seal = read(OUT / "seal.json")
    resource = read(OUT / "reference-resource.json")
    before = read(old / "clearance-gate.json")["checks"]
    after = read(current / "clearance-gate.json")["checks"]
    receipt = read(current / "sensor-receipt.json")
    require = live.REQUIRE
    require(
        sha(OUT / "reference-resource.json") == seal["sealed_sha256"]["reference-resource.json"]
        and resource["closed"]
        and resource["camera_calls"] == len(receipt["camera_calls"])
        and resource["episode_id"] == receipt["episode_id"]
        and resource["reset_finish_ns"]
        < resource["constructor_start_ns"]
        < resource["constructor_finish_ns"]
        < resource["first_target_ns"]
        and resource["robot_projections"] == seal["reference_projection_calls"]["robot"],
        "resource lifetime or count not bound to actual session",
    )
    left, right = [read(d / "rgbd-index.json")["rows"] for d in (old, current)]
    index = {
        (x["skill"], x["phase"], x["robot"]["physics_step"]): (x, b)
        for x, b in zip(left, before, strict=True)
    }
    comparison = []
    for x, b in zip(right, after, strict=True):
        key = (x["skill"], x["phase"], x["robot"]["physics_step"])
        require(key in index, "unpaired new frame")
        source, old_gate = index[key]
        data = [read_frame(d / row["file"]) for d, row in ((old, source), (current, x))]
        same_rgb = np.array_equal(rgb(data[0]), rgb(data[1]))
        same_depth = data[0]["depth_float32_base64"] == data[1]["depth_float32_base64"]
        same_mask = data[0]["valid_mask_base64"] == data[1]["valid_mask_base64"]
        same_encoders = all(
            source["robot"][name] == x["robot"][name]
            for name in (
                "joint_positions_rad",
                "camera_joint_positions_rad",
                "camera_finger_positions_m",
                "joint_velocities_rad_s",
            )
        )
        a_verdict, b_verdict = old_gate["current"], b["current"]
        if key[1] == "POST":
            same_decision = post_payload(old_gate) == post_payload(b)
        else:
            same_decision = (
                a_verdict.get("depth") == b_verdict.get("depth")
                and a_verdict["status"] == b_verdict["status"]
                and a_verdict.get("reason") == b_verdict.get("reason")
            )
        comparison.append(
            {
                "step": key[-1],
                "phase": key[1],
                "new_frame_id": x["robot"]["frame_id"],
                "rgb_equal": same_rgb,
                "depth_equal": same_depth,
                "mask_equal": same_mask,
                "encoders_equal": same_encoders,
                "decision_equal": same_decision,
            }
        )
    actual_frame = after[-1]
    actual_ms = (actual_frame["gate_finish_ns"] - actual_frame["capture_begin_ns"]) / 1e6
    done = [x for x in after if x.get("released_to_boundary")]
    raw_comp = resource["carried_projections"]
    require(
        len(raw_comp) == seal["reference_projection_calls"]["carried"]
        and all(x["before_next_boundary_ms"] <= PLAN["deadline_ms"] for x in done),
        "actual feedback and projection counts differ",
    )
    for p in raw_comp:
        (matching,) = [x for x in after if x["frame_id"] == p["frame_id"]]
        require(
            p["step"] == matching["step"]
            and p["checksum"] == matching["checksum_sha256"]
            and matching["capture_begin_ns"]
            <= p["projection_start_ns"]
            <= p["projection_finish_ns"]
            <= matching["gate_finish_ns"],
            "reference reused another frame or clock",
        )
    commands = [
        [
            {k: v for k, v in x.items() if k != "episode_id"}
            for x in read(d / "native-commands.json")
        ]
        for d in (old, current)
    ]
    return {
        "frames": comparison,
        "match_counts": {
            key: sum(row[key] for row in comparison)
            for key in (
                "rgb_equal",
                "depth_equal",
                "mask_equal",
                "encoders_equal",
                "decision_equal",
            )
        },
        "native_commands_equal": commands[0] == commands[1],
        "completed_feedback_count": len(done),
        "completed_feedback_capture_to_boundary_max_ms": max(
            (x["before_next_boundary_ms"] for x in done), default=None
        ),
        "constructor_ms": (resource["constructor_finish_ns"] - resource["constructor_start_ns"])
        / 1e6,
        "reset_to_first_ordinary_target_ms": (
            resource["first_target_ns"] - resource["reset_start_ns"]
        )
        / 1e6,
        "post_reset_to_first_ordinary_target_ms": (
            resource["first_target_ns"] - resource["reset_finish_ns"]
        )
        / 1e6,
        "close_ms": resource["close_elapsed_ms"],
        "projection_ms": [
            (p["projection_finish_ns"] - p["projection_start_ns"]) / 1e6 for p in raw_comp
        ],
        "first_refusal_step": actual_frame["step"],
        "first_refusal_status": actual_frame["current"]["status"],
        "first_refusal_reason": actual_frame["current"].get("reason"),
        "first_refusal_capture_through_gate_ms": actual_ms,
        "old_refusal_capture_through_gate_ms": (
            before[-1]["gate_finish_ns"] - before[-1]["capture_begin_ns"]
        )
        / 1e6,
        "refusal_released_to_boundary": actual_frame.get("released_to_boundary", False),
        "native_emergency_stop": receipt["native_emergency_stop"],
        "canonical_seal_sha256": sha(OUT / "seal.json"),
    }


def read_frame(path):
    return live.json.loads(gzip.decompress(path.read_bytes()))


def post_payload(row):
    verdict = row["current"]
    pose = verdict["pose"]
    geometry = None
    if pose is not None:
        live.REQUIRE(
            pose["frame_id"] == row["frame_id"]
            and pose["checksum_sha256"] == row["checksum_sha256"],
            "POST pose bound to a different image",
        )
        geometry = {
            name: pose[name]
            for name in (
                "method",
                "ids",
                "center_m",
                "rotation",
                "center_error_m",
                "rotation_error_rad",
            )
        }
    return verdict["relation"], verdict["evidence"].get("reason"), geometry


def rgb(frame):
    return np.asarray(Image.open(io.BytesIO(base64.b64decode(frame["rgb_png_base64"]))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reader", choices=("final-reader-1", "final-reader-2"))
    args = parser.parse_args()
    with (
        patch.object(live.tail, "OUT", NEW_ROOT),
        patch.multiple(
            mujoco,
            mj_step=live.tail.earlier.deny,
            Renderer=live.tail.earlier.deny,
            mjr_render=live.tail.earlier.deny,
        ),
    ):
        readback.cold(args.reader, PLAN["new_attempt"])
        write(NEW_ROOT / f"paired-{args.reader}.json", compare())


if __name__ == "__main__":
    main()
