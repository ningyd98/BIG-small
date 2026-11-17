"""Read-only verification of retained grasp/place repair development evidence."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import math
import os
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]


def read(path: Path) -> Any:
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix == ".gz"
                      else path.read_text())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def tuples(value: Any) -> Any:
    return tuple(tuples(item) for item in value) if isinstance(value, list) else value


def check_joint_commands(commands: list[dict[str, Any]], actions: list[dict[str, Any]]) -> dict:
    """Check one continuous stream, including ordinary action handoffs.

    Explicit hold/estop operations retain their original immediate stop
    semantics; they reset the segment but are never silently inferred at an
    action boundary. The first following target starts the new segment.
    """
    previous = None
    velocity = None
    max_velocity = max_acceleration = 0.0
    checked = handoffs = 0
    previous_action = None
    for row in commands:
        if not row.get("accepted"):
            continue
        if row["type"] in {"hold_current_joints", "emergency_stop"}:
            previous, velocity = None, None
            previous_action = None
            continue
        if row["type"] != "joint_target":
            continue
        matching = [a for a in actions
                    if a["start_step"] <= row["physics_step"] <= a["controller_return_step"]]
        require(bool(matching), "ordinary joint command lacks an action binding")
        action = matching[-1]
        identity = action["step_id"]
        parameters = action["resolved_step"]["parameters"]
        if previous is not None:
            dt = row["sim_time_s"] - previous["sim_time_s"]
            require(dt > 0, "nonmonotonic continuous joint command clock")
            current_velocity = (np.array(row["target_positions_rad"])
                                - np.array(previous["target_positions_rad"])) / dt
            measured_v = float(np.max(np.abs(current_velocity)))
            require(measured_v <= parameters["tcp_velocity"] / 0.3 + 1e-7,
                    f"continuous joint target velocity exceeded at {row['physics_step']}")
            max_velocity = max(max_velocity, measured_v)
            if velocity is not None:
                measured_a = float(np.max(np.abs(current_velocity - velocity))) / dt
                require(measured_a <= parameters["acceleration"] / 0.3 + 1e-7,
                        f"continuous joint target acceleration exceeded at {row['physics_step']}")
                max_acceleration = max(max_acceleration, measured_a)
            checked += 1
            if previous_action is not None and previous_action != identity:
                handoffs += 1
            velocity = current_velocity
        previous, previous_action = row, identity
    require(checked > 10 and handoffs >= 2, "insufficient continuous command/handoff evidence")
    return {"checked_intervals": checked, "ordinary_handoffs": handoffs,
            "max_joint_target_velocity_rad_s": max_velocity,
            "max_joint_target_acceleration_rad_s2": max_acceleration}


def main() -> None:
    from scripts.verify_visual_servo import case_passed

    from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
        CompletionCriteria,
        PhysicalSample,
        evaluate_evidence,
    )
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path)
    args = parser.parse_args()
    process = Path(__file__).resolve().parent
    manifest = read(process / "raw-manifest.json.gz")
    require(manifest["status"] == "FINAL", "raw inventory is not final")
    raw = args.raw_root or Path(manifest["root"])
    for relative, target in manifest.get("symlinks", {}).items():
        link = raw / relative
        require(link.is_symlink() and os.readlink(link) == target,
                f"raw link metadata changed: {relative}")
    for relative, expected in manifest["files"].items():
        require(hashlib.sha256((raw / relative).read_bytes()).hexdigest() == expected,
                f"raw bytes changed: {relative}")
    sources = read(process / "source-manifest.json")
    for relative, expected in sources["files"].items():
        require(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected,
                f"tested source changed: {relative}")
    runs = read(process / "validation-runs.json")
    regression = read(process / "regression-summary.json")
    node_map = raw / regression["full_node_map"]["raw_relative_path"]
    require(hashlib.sha256(node_map.read_bytes()).hexdigest()
            == regression["full_node_map"]["sha256"], "regression node map changed")
    nodes = read(node_map)
    require(len(nodes["nodes"]) == nodes["collected"] == nodes["accounted"] == 7088
            and not nodes["missing"], "regression node accounting is incomplete")
    require(dict(Counter(row["status"] for row in nodes["nodes"].values()))
            == regression["counts"], "regression counts disagree with node map")
    for relative, expected in regression["inputs_sha256"].items():
        require(hashlib.sha256((raw / relative).read_bytes()).hexdigest() == expected,
                f"regression input changed: {relative}")
    frame_count = 0
    ids: set[str] = set()

    def frames(folder: Path) -> None:
        nonlocal frame_count
        for metadata in folder.rglob("observation.json"):
            values = {k: v for k, v in read(metadata).items()
                      if k in RGBDObservation.model_fields}
            for field, name in (("rgb_png_base64", "rgb.png"),
                                ("depth_float32_base64", "depth.f32"),
                                ("valid_mask_base64", "valid_mask.u8")):
                values[field] = base64.b64encode((metadata.parent / name).read_bytes()).decode()
            observation = RGBDObservation.model_validate(values)
            ids.add(observation.observation_id)
            frame_count += 1

    workers = []
    for relative in runs["workers"]:
        folder = raw / relative
        episode = read(folder / "episode.json")
        require(episode["diagnostic_complete"] and episode["physical_success"],
                f"full worker did not complete physically: {relative}")
        require(episode["terminal_reason"] is None
                and episode["actions"][-1]["skill"] == "RETREAT"
                and episode["marker_frames"][-1]["status"] == "OBSERVED",
                f"full worker terminal evidence is incomplete: {relative}")
        require(episode["native_action_qualification"] == "UNKNOWN_NOT_GRANTED",
                "development result was promoted")
        evidence = [PhysicalSample(**{k: tuples(v) for k, v in row.items()})
                    for row in read(folder / "physical-evidence.json")]
        scored = evaluate_evidence(evidence, CompletionCriteria("object", "target_region"))
        require(scored.success, f"independent physical rescore failed: {relative}")
        recorded = episode["independent_physical_outcome"]
        for name in ("measured_lift_m", "hold_s", "placed_stable_s"):
            require(math.isclose(getattr(scored, name), recorded[name], abs_tol=1e-10),
                    f"physical measurement differs: {name}")
        feedback = read(folder / "robot-feedback.json")
        commands = read(folder / "commands.json")
        continuous_commands = check_joint_commands(commands, episode["actions"])
        entry = folder.parent
        entry_sources = read(entry / "source-hashes.json")["files"]
        binding = read(entry / "role-binding.json")
        bound_sources = (entry_sources | binding["device_source_hashes"]
                         | binding["edge_snapshot"]["source_hashes"])
        for name, expected in bound_sources.items():
            require(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected,
                    f"worker source binding no longer matches: {name}")
        frames(folder / "servo-frames")
        actions = []
        for action in episode["actions"]:
            controls = action.get("visual_servo", {}).get("control_samples", [])
            if not controls:
                continue
            require(max(row["sample_and_ik_s"] for row in controls) <= 0.1,
                    "accepted servo sample exceeded the original deadline")
            begin, end = action["start_step"], action["controller_return_step"]
            command_rows = [row for row in commands if row["type"] == "joint_target"
                            and begin <= row["physics_step"] <= end]
            q = np.array([row["target_positions_rad"] for row in command_rows])
            times = np.array([row["sim_time_s"] for row in command_rows])
            dt = np.diff(times)
            require(bool(np.all(dt > 0)), "nonmonotonic joint command clock")
            velocity = np.diff(q, axis=0) / dt[:, None]
            acceleration = np.diff(velocity, axis=0) / dt[1:, None]
            parameters = action["resolved_step"]["parameters"]
            max_v = parameters["tcp_velocity"] / 0.3
            max_a = parameters["acceleration"] / 0.3
            measured_v = float(np.max(np.abs(velocity)))
            measured_a = float(np.max(np.abs(acceleration)))
            require(measured_v <= max_v + 1e-7, "joint target velocity exceeded")
            require(measured_a <= max_a + 1e-7, "joint target acceleration exceeded")
            if "vertical_clearance" in action:
                values = action["vertical_clearance"]
                path = VerticalClearancePath(**{k: tuples(v) for k, v in values.items()})
                peak = path.start_m[2]
                for row in feedback:
                    if begin < row["physics_step"] <= end:
                        xyz = row["tcp_position_m"]
                        path.check_position(tuple(xyz), peak_z=peak)
                        peak = max(peak, xyz[2])
            if action["skill"] in {"LIFT", "MOVE_TO_REGION", "PLACE"}:
                require(all(sample.left_finger_contact and sample.right_finger_contact
                            for sample in evidence if begin < sample.physics_step <= end),
                        "held-object motion contains contact loss")
            visual = action["visual_servo"]["visual_samples"]
            wall = controls[-1]["wall_elapsed_s"] - controls[0]["wall_elapsed_s"]
            actions.append({
                "step_id": action["step_id"], "skill": action["skill"],
                "samples": len(controls), "wall_feedback_hz": (len(controls) - 1) / wall,
                "max_sample_ms": max(row["sample_and_ik_s"] for row in controls) * 1000,
                "max_joint_target_velocity_rad_s": measured_v,
                "max_joint_target_acceleration_rad_s2": measured_a,
                "camera_recoveries": sum("camera_recovery" in row for row in visual),
            })
        checks = [row for row in episode["safety_checks"] if row["phase"] == "SERVO"]
        require(all(row["verdict"]["allowed"] and row["observation_id"] in ids for row in checks),
                "a dynamic safety check lacks accepted paired RGBD")
        workers.append({"raw": relative, "physical": asdict(scored), "actions": actions,
                        "continuous_commands": continuous_commands,
                        "bound_source_files_checked": len(bound_sources)})

    deadline_stops = []
    for relative in runs.get("deadline_stopped_workers", []):
        folder = raw / relative
        episode = read(folder / "episode.json")
        require(not episode["physical_success"], "prior deadline failure was promoted")
        failed = episode["actions"][-1]
        reason = failed["controller_result"]["error"]["details"]["reason"]
        require("sample/IK deadline exceeded" in reason, "prior stop reason changed")
        stopped_at = failed["controller_return_step"]
        commands = read(folder / "commands.json")
        require(any(row["accepted"] and row["type"] == "hold_current_joints"
                    and row["physics_step"] == stopped_at for row in commands),
                "deadline failure lacks immediate hold")
        require(not any(row["accepted"] and row["type"] == "joint_target"
                        and row["physics_step"] >= stopped_at for row in commands),
                "joint target continued after a rejected deadline sample")
        frames(folder / "servo-frames")
        deadline_stops.append({"raw": relative, "reason": reason,
                               "stopped_at_physics_step": stopped_at,
                               "no_later_joint_target": True})

    visual_runs = []
    for relative in runs["visual"]:
        folder = raw / relative
        frames(folder)
        summary = read(folder / "summary.json")
        require(all(case_passed(row) for row in summary["results"]),
                f"standalone visual development gate failed: {relative}")
        visual_runs.append({"raw": relative, "cases": summary["results"]})
    print(json.dumps({
        "evidence_valid": True, "scope": "FIXED_SCENE_DEVELOPMENT_REPEATABILITY",
        "raw_files_checked": len(manifest["files"]), "source_files_checked": len(sources["files"]),
        "raw_symlink_metadata_checked": len(manifest.get("symlinks", {})),
        "segmented_regression_counts": regression["counts"],
        "segmented_regression_all_green": False,
        "paired_frames_reconstructed": frame_count, "workers": workers, "visual": visual_runs,
        "retained_prior_revision_deadline_stops": deadline_stops,
        "paid_external_model_calls": 0, "hardware_dispatch": False,
        "formal_research": "NOT_ACCEPTED", "new_seed_generalization": "NOT_TESTED",
    }, indent=2))


if __name__ == "__main__":
    main()
