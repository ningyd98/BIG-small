"""Independently read the raw native duration comparison and its stopped boundaries."""

import argparse
import gzip
from collections import Counter
from pathlib import Path

from preflight import HERE, PLAN, PLAN_PATH, ROOT, inputs, original_slot, require
from scripts.graduation.g1_complete_cv_handoff import binding_error
from scripts.graduation.perception_io import read, sha, write

from cloud_edge_robot_arm.vision.observations import RGBDObservation

RAW = ROOT / PLAN["raw_root"]
CAPTURE = RAW / "capture-01"
PADS = {frozenset((finger, "object_geom")) for finger in ("left_finger_geom", "right_finger_geom")}
CLOCKED = {"FEEDBACK", "HOLD_ENTRY", "HOLD"}


def joined_rows(folder, gate_rows, registration):
    index_path = folder / "rgbd-index.json"
    index = read(index_path)
    receipt = read(folder / "sensor-receipt.json")
    physics = read(folder / "offline-physics.json")
    require(
        receipt["registration_sha256"] == sha(CAPTURE / "registration.json")
        and receipt["index_sha256"] == sha(index_path)
        and receipt["scene_id"] == index["scene_id"]
        and receipt["episode_id"] == index["episode_id"]
        and not physics["unexpected_step_events"]
        and len(index["rows"]) == len(physics["frame_labels"]) == len(gate_rows),
        "capture or native contact ledger differs",
    )
    entries = {}
    for gate, row, label in zip(gate_rows, index["rows"], physics["frame_labels"], strict=True):
        raw = folder / row["file"]
        require(sha(raw) == row["file_sha256"], "nature of indexed optical packet changed")
        frame = RGBDObservation.model_validate_json(gzip.decompress(raw.read_bytes()))
        robot = row["robot"]
        require(
            frame.frame_id == gate["frame_id"] == label["frame_id"] == robot["frame_id"]
            and frame.frame_id not in entries
            and frame.checksum_sha256
            == gate["checksum_sha256"]
            == label["checksum_sha256"]
            == robot["checksum_sha256"]
            and frame.scene_id == receipt["scene_id"]
            and frame.episode_id == receipt["episode_id"]
            and frame.sim_time_s == robot["sim_time_s"] == robot["camera_encoder_sim_time_s"]
            and gate["step"] == label["physics_step"] == robot["physics_step"]
            and abs(frame.sim_time_s - gate["step"] / PLAN["command"]["physics_hz"]) <= 1e-9
            and gate["gate_finish_ns"] >= gate["capture_begin_ns"]
            and (row["skill"], row["phase"]) == (gate["skill"], gate["phase"])
            and gate["tcp_position_m"] == robot["tcp_position_m"]
            and robot["native_last_command_seq"] == gate["native_last_command_seq"]
            and frame.model_dump(include=set(registration["camera"]), mode="json")
            == registration["camera"],
            "exposure or standalone physics label does not bind",
        )
        if gate["phase"] != "POST":
            h = robot["handoff"]
            require(
                binding_error(h, gate["skill"], gate["phase"], frame) is None
                and h["current_step"] == gate["step"]
                and h["last_command_seq"] == gate["native_last_command_seq"],
                "native handoff does not bind",
            )
        entries[frame.frame_id] = {
            "robot": robot,
            "physical_bilateral": PADS.issubset(map(frozenset, label["touching"])),
            "workpiece_z_m": label["center_m"][2],
        }
    known_camera_steps = Counter((c["step"], c["time_s"]) for c in receipt["camera_calls"])
    observed_steps = Counter(
        (r["robot"]["physics_step"], r["robot"]["sim_time_s"]) for r in entries.values()
    )
    require(not (observed_steps - known_camera_steps), "unrecorded native shutter")
    return receipt, entries


def relative_height(row, start):
    return row["tcp_position_m"][2] - start


def evidence(row, entries, start):
    label = entries[row["frame_id"]]
    gate = row["current"]
    motion = gate.get("short_motion") or {}
    return {
        "step": row["step"],
        "status": row["status"],
        "reason": row["reason"],
        "tcp_lift_m": relative_height(row, start),
        "workpiece_center_z_m": label["workpiece_z_m"],
        "physical_bilateral": label["physical_bilateral"],
        "optical_relation": gate.get("payload_observation", {}).get("relation"),
        "speed_class": motion.get("speed_class"),
        "minimum_gap_m": motion.get("minimum_gap_m"),
        "unmatched_pixels_uv": gate.get("depth", {}).get("unmatched_pixels_uv"),
        "checksum_sha256": row["checksum_sha256"],
    }


def score(slot, registration, original_reg, cpu):
    folder = CAPTURE / slot["id"]
    gate = read(folder / "clearance-gate.json")
    rows, refs = gate["checks"], gate["references"]
    receipt, labels = joined_rows(folder, rows, registration)
    require(
        receipt["slot"] in registration["slots"]
        and receipt["id"] == slot["id"] == receipt["slot"]["id"]
        and receipt["native_emergency_stop"]
        and [a["skill"] for a in receipt["actions"]] == ["MOVE_ABOVE", "APPROACH", "GRASP", "LIFT"]
        and all(a["controller_called"] for a in receipt["actions"])
        and receipt["physics_steps"] < PLAN["maximum"]["exclusive_total_ticks_per_slot"],
        "native scope or terminal stop differs",
    )
    lift = receipt["actions"][-1]
    original, old_stop = original_slot(slot, original_reg)
    (entry,) = [r for r in rows if (r["skill"], r["phase"]) == ("LIFT", "PRE")]
    record = labels[entry["frame_id"]]["robot"]
    stage_identity = {"entry_frame_id", "entry_checksum_sha256"}
    archived_handoff = original[1]["handoff"]
    require(
        entry["step"] == original[0]["step"] == lift["start_step"]
        and entry["current"]["commanded_target_xyz_m"]
        == original[0]["current"]["commanded_target_xyz_m"]
        and all(
            record[k] == original[1][k]
            for k in (
                "tcp_position_m",
                "tcp_quaternion_wxyz",
                "joint_positions_rad",
                "joint_velocities_rad_s",
                "finger_positions_m",
                "finger_velocities_m_s",
                "sim_time_s",
            )
        )
        and {k: v for k, v in record["handoff"].items() if k not in stage_identity}
        == {k: v for k, v in archived_handoff.items() if k not in stage_identity},
        "experiment began from a different native entry",
    )
    (reference,) = refs
    prior_ref = cpu["cases"][slot["id"]]["slower_reference"]
    require(
        reference["constructed"]
        and reference["step"] == entry["step"]
        and reference["duration_s"]
        == registration["reference_duration_s"]
        == prior_ref["duration_s"]
        and reference["settle_s"] == PLAN["reference_seconds"]["settle"]
        and reference["peak_joint_velocity_rad_s"] == prior_ref["peak_joint_velocity_rad_s"]
        and reference["start_m"] == record["tcp_position_m"]
        and reference["target_m"] == entry["current"]["commanded_target_xyz_m"]
        and reference["orientation_wxyz"] == record["tcp_quaternion_wxyz"]
        and reference["parameters"]
        == {
            "control_steps": PLAN["command"]["control_ticks"],
            "initialize_load_from_feedback": False,
            "max_acceleration": PLAN["command"]["acceleration_m_s2"] / 0.3,
            "max_velocity": PLAN["command"]["tcp_velocity_m_s"] / 0.3,
            "timeout_s": PLAN["command"]["timeout_ms"] / 1000,
        },
        "one real candidate or its construction did not bind",
    )
    samples = [r for r in rows if r["phase"] in CLOCKED]
    released = [r for r in samples if r["released_to_boundary"]]
    denied = [r for r in samples if not r["released_to_boundary"]]
    moves = [r["step"] for r in samples if r["phase"] == "FEEDBACK"]
    holds = [r["step"] for r in samples if r["phase"] == "HOLD"]
    require(
        moves[0] == entry["step"]
        and all(
            b - a == PLAN["command"]["feedback_ticks"]
            for a, b in zip(moves[:-1], moves[1:], strict=True)
        )
        and len(samples) <= PLAN["maximum"]["feedback_per_slot"]
        and len(receipt["camera_calls"])
        <= PLAN["maximum"]["feedback_per_slot"] + PLAN["maximum"]["camera_overhead_per_slot"]
        and all(
            r["status"] == "CLEAR"
            and r["boundary_ns"] >= r["gate_finish_ns"]
            and 0 <= r["before_boundary_ms"] <= PLAN["command"]["maximum_feedback_ms"]
            and 0 <= (r["native_sample_ms"] or 0) <= PLAN["command"]["maximum_feedback_ms"]
            and labels[r["frame_id"]]["physical_bilateral"]
            for r in released
        ),
        "native feedback cadence or boundary authorization differs",
    )
    original_height = old_stop[1]["tcp_position_m"][2] - original[1]["tcp_position_m"][2]
    start_z = entry["tcp_position_m"][2]
    past_original = next(
        (r for r in released if relative_height(r, start_z) >= original_height), None
    )
    if lift["success"]:
        require(
            not denied
            and receipt["termination"] == "native_lift_with_hold_and_post"
            and holds == list(range(lift["hold_start_step"] + 8, lift["end_step"] + 1, 8))
            and lift["end_step"] - lift["hold_start_step"]
            == PLAN["maximum"]["dwell_ticks_per_slot"]
            and rows[-1]["phase"] == "POST"
            and rows[-1]["current"]["relation"] == "held"
            and rows[-1]["step"] == lift["end_step"]
            and labels[rows[-1]["frame_id"]]["physical_bilateral"],
            "native movement or full stationary hold is incomplete",
        )
        refusal = None
        after = []
    else:
        (refusal,) = denied
        require(
            refusal is rows[-1]
            and refusal["status"] in {"UNKNOWN", "BLOCKED"}
            and refusal["step"] == receipt["physics_steps"] == lift["end_step"]
            and receipt["termination"] == "original_current_clearance_refused",
            "first native optical refusal did not close",
        )
        lane = read(folder / "native-commands.json")
        after = [
            r["type"]
            for r in lane
            if r["accepted"] and r["command_seq"] > refusal["native_last_command_seq"]
        ]
        require(
            all(t in {"hold_current_joints", "emergency_stop"} for t in after)
            and "emergency_stop" in after,
            "a new ordinary drive action follows the first refusal",
        )
    return {
        "case": slot["id"],
        "native_physics_steps": receipt["physics_steps"],
        "native_camera_calls": len(receipt["camera_calls"]),
        "reference_projections": dict(
            Counter(read(folder / "reference-projections.json")["passes"])
        ),
        "successful_full_lift": lift["success"],
        "original_stop_lift_m": original_height,
        "new_first_clear_at_or_above_original_stop": (
            evidence(past_original, labels, start_z) if past_original is not None else None
        ),
        "first_refusal": evidence(refusal, labels, start_z) if refusal is not None else None,
        "released_motion_feedback": len([r for r in released if r["phase"] == "FEEDBACK"]),
        "speed_classes": dict(
            Counter(
                (r["current"].get("short_motion") or {}).get("speed_class", "none")
                for r in released
            )
        ),
        "native_hold_feedback": len(holds),
        "accepted_safety_actions_after_refusal": after,
        "max_shutter_to_actual_boundary_ms": max(r["before_boundary_ms"] for r in released),
    }


def run(out):
    _, original_reg = inputs()
    plan_hash = sha(PLAN_PATH)
    seal_path = CAPTURE / "seal.json"
    seal = read(seal_path)
    registration_path = CAPTURE / "registration.json"
    registration = read(registration_path)
    cpu = RAW / "preflight.json"
    require(
        sha(registration_path) == seal["registration_sha256"]
        and registration["plan_sha256"] == plan_hash
        and registration["driver_sha256"] == sha(HERE / "capture.py")
        and registration["preflight_sha256"] == sha(cpu)
        and registration["camera"] == original_reg["camera"]
        and registration["asset_sha256"] == original_reg["asset_sha256"]
        and registration["slots"] == [s for s in original_reg["slots"] if s["id"] in seal["cases"]]
        and seal["cases"] == [s["id"] for s in PLAN["slots"]],
        "native run or original controls differ from registration",
    )
    files = {p.relative_to(CAPTURE).as_posix() for p in CAPTURE.rglob("*") if p.is_file()}
    require(
        files == set(seal["sealed_sha256"]) | {"seal.json"}, "extra or missing raw capture file"
    )
    for name, pin in seal["sealed_sha256"].items():
        path = (CAPTURE / name).resolve()
        require(path.is_relative_to(CAPTURE) and sha(path) == pin, f"raw file changed: {name}")
    old_cases = read(cpu)
    results = [score(s, registration, original_reg, old_cases) for s in PLAN["slots"]]
    write(
        out,
        {
            "schema": "g1.development.lift-reference-duration.results.v1",
            "baseline": PLAN["baseline"],
            "plan_sha256": plan_hash,
            "capture_seal_sha256": sha(seal_path),
            "sealed_members": len(seal["sealed_sha256"]),
            "preflight_sha256": sha(cpu),
            "cases": results,
            "actual_physics_steps": sum(r["native_physics_steps"] for r in results),
            "actual_camera_calls": sum(r["native_camera_calls"] for r in results),
            **{
                k: PLAN[k]
                for k in (
                    "new_formal",
                    "independent_formal_scoring",
                    "hardware",
                    "remote",
                    "whole_system",
                )
            },
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.output)
