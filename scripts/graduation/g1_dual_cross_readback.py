"""Independently read the first-refusal packets, restored poses, depth and hand projection."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import mujoco
import numpy as np
from scripts.graduation import proposal_camera as camera
from scripts.graduation.g1_mount_geometry import bits
from scripts.graduation.g1_mount_screen_verify import independent_areas, measurement, raw_frame
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

from cloud_edge_robot_arm.vision.observations import RGBDObservation

PLAN = "85666eed1724a2c2280690de8ec55d35fe79b3d636982e35dd366d48e6534885"
ROLES = {"previous": "previous_accepted_feedback", "refused": "rejected_feedback"}


def require_feedback(original, actual):
    if original["label"] != "MOVE_ABOVE/feedback" or any(
        actual[k] != original[k] for k in ("frame_id", "label", "physics_step", "checksum_sha256")
    ):
        raise ValueError("feedback points to a different acquisition or consumer")


def classify_pose(valid, verified):
    if set(valid) != {"X", "Y"} or any(type(v) is not bool for v in valid.values()):
        raise ValueError("two separate installation decisions required")
    if not verified:
        return "unverified"
    if valid["X"] == valid["Y"]:
        return "both" if valid["X"] else "neither"
    return "X_only" if valid["X"] else "Y_only"


def original_records(plan, case):
    directory = Path(plan["prior_private"]) / "trials" / case["case"] / "instance"

    def load(name):
        path = directory / name
        return pinned(ROOT / path, plan["input_sha256"][str(path)])

    index = load("pixel-index.json")
    audit = load("online-audit.json")
    truth = load("offline-truth.json")
    action = load("run.json")["actions"][0]
    sources = case["original_feedback"]
    feedback = [r for r in index["frames"] if r["label"] == "MOVE_ABOVE/feedback"]
    (servo,) = [e for e in audit if e.get("phase") == "servo" and e.get("skill") == "MOVE_ABOVE"]
    accepted = servo["visual_samples"]
    if not (
        len(accepted) + 1 == len(feedback)
        and action["servo_terminal_reason"] == case["servo_terminal_reason"]
        and action["executor_entered"]
        and index["episode"] == truth["episode"] == case["episode"]
    ):
        raise ValueError("original MOVE_ABOVE control evidence differs")
    for accepted_row, packet in zip(accepted, feedback[:-1], strict=True):
        if (accepted_row["observation_id"], accepted_row["checksum_sha256"]) != (
            packet["frame_id"],
            packet["checksum_sha256"],
        ):
            raise ValueError("accepted feedback is not the original RGB-D")
    require_feedback(sources[ROLES["previous"]], feedback[-2])
    require_feedback(sources[ROLES["refused"]], feedback[-1])
    terminal = sources["separate_terminal_capture"]
    if (
        index["frames"][-1]["frame_id"] != terminal["frame_id"]
        or terminal["frame_id"] == feedback[-1]["frame_id"]
        or terminal["physics_step"] != feedback[-1]["physics_step"]
        or feedback[-1]["physics_step"] - feedback[-2]["physics_step"] != 8
        or accepted[-1]["target_pose"] != case["actual_last_accepted_target"]
    ):
        raise ValueError("invalid terminal, command or feedback interval")
    snapshots = {}
    for step in range(feedback[-2]["physics_step"], feedback[-1]["physics_step"] + 1):
        state = truth["samples"][step]
        raw = json.dumps(state, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        if (
            hashlib.sha256(raw).hexdigest() != case["dense_previous_through_refusal"][str(step)]
            or state["physics_step"] != step
            or state["episode_id"] != case["episode"]
        ):
            raise ValueError("foreign or missing dense state between two original acquisitions")
        snapshots[step] = state
    return snapshots


def installation_counts(frame, mount, state, role, cross):
    seg = role["segmentation"]
    path = cross / "segmentation" / seg["file"]
    if sha(path) != seg["sha256"]:
        raise ValueError("different instance raster")
    obj = np.eye(4)
    obj[:3, :3] = np.asarray(state["object_geom_rotation_row_major"]).reshape(3, 3)
    obj[:3, 3] = state["object_geom_position_m"]
    translation = np.eye(4)
    translation[:3, 3] = mount["object_T_marker_translation_m"]
    area = independent_areas(
        frame, obj @ translation, np.load(path, allow_pickle=False), seg["labels"], bits()
    )
    result, _ = measurement(frame, mount)
    return {"usable": result["usable"], "areas": area}


def readback(cross, public, output):
    plan = pinned(public / "plan.json", PLAN)
    cap = read(cross / "capture-seal.json")
    roles = pinned(cross / "roles.json", cap["roles_sha256"])["roles"]
    frames = pinned(cross / "pixels/index.json", cap["index_sha256"])["frames"]
    mounts = {side: m for side, m in zip(("Y", "X"), plan["single_mounts"], strict=True)}
    models = {
        s: mujoco.MjModel.from_xml_path(str(ROOT / m["asset_path"])) for s, m in mounts.items()
    }
    results, counts = [], {role: Counter() for role in ROLES}
    for case in plan["source_cases"]:
        states = original_records(plan, case)
        original_side = case["source_side"]
        for label, lookup in ROLES.items():
            original = case["original_feedback"][lookup]
            original_frame = RGBDObservation.model_validate(
                pinned(ROOT / original["packet_file"], original["packet_sha256"])
            )
            true_flags, _ = measurement(original_frame, mounts[original_side])
            if (
                true_flags["usable"] != (label == "previous")
                or original_frame.frame_id != original["frame_id"]
            ):
                raise ValueError("original usable/rejected measurement mismatch")
            step = original["physics_step"]
            state = states[step]
            row = {
                "case": case["case"],
                "source_side": original_side,
                "role": label,
                "physics_step": step,
                "source_frame_id": original_frame.frame_id,
                "measurements": {},
            }
            verified = True
            valid = {}
            for side, mount in mounts.items():
                info = {}
                for variant in ("normal", "hand_hidden"):
                    f, digest, role = raw_frame(
                        cross, roles, frames, f"{case['case']}/{label}/{side}/{variant}"
                    )
                    if (
                        f.sim_time_s != state["sim_time_s"]
                        or f.calibration_version != original_frame.calibration_version
                    ):
                        raise ValueError("unpaired source clock or camera")
                    if variant == "normal":
                        fk = camera.restore(models[side], mujoco.MjData(models[side]), state)
                        if side == original_side:
                            fk.update(camera.compare(original_frame, f))
                        verified &= all(0 <= v <= camera.CHECK_LIMITS[k] for k, v in fk.items())
                        info["source_residuals"] = fk
                        rec = installation_counts(f, mount, state, role, cross)
                        valid[side] = rec["usable"]
                        if side == original_side:
                            verified &= rec["usable"] == true_flags["usable"]
                    else:
                        flags, _ = measurement(f, mount)
                        rec = {"usable": flags["usable"]}
                    info[variant] = {**rec, "rgbd_file_sha256": digest}
                row["measurements"][side] = info
            bucket = classify_pose(valid, verified)
            row["bucket"] = bucket
            counts[label][bucket] += 1
            results.append(row)
    combined = counts["previous"] + counts["refused"]
    write(
        output,
        {
            "schema": "g1.first-refusal.independent-stop-readback.v1",
            "plan_sha256": PLAN,
            "capture_seal_sha256": sha(cross / "capture-seal.json"),
            "poses": results,
            "by_role": {k: dict(c) for k, c in counts.items()},
            "total": dict(combined),
            "complementary": combined["X_only"] > 0 and combined["Y_only"] > 0,
            "online_motion_steps": 0,
            "formal_claims": 0,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("cross", "public", "output"):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    readback(args.cross, args.public, args.output)
