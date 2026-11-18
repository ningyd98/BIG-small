"""Audit full optical and command binding in the one completed protocol replay."""

import argparse
import hashlib
import json
import struct
from collections import defaultdict
from pathlib import Path

import numpy as np


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_transform(position, aim):
    forward = np.subtract(aim, position)
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, [0, 1, 0])
    right /= np.linalg.norm(right)
    down = np.cross(forward, right)
    matrix = np.eye(4)
    matrix[:3, :3] = np.column_stack((right, down, forward))
    matrix[:3, 3] = position
    return matrix.ravel()


def main(raw, output):
    episode = raw / "green"
    result = read(episode / "result.json")
    outcome = result["outcome"]
    passed = result["worker_status"] == "SUCCEEDED"
    assert passed == outcome["diagnostic_complete"]
    assert not outcome["independent_physical_outcome"]["safety_violation"]
    assert not result["denied_network_attempts"] and not result["denied_model_load_attempts"]
    assert (
        result["actual_model_loads"],
        result["actual_local_generations"],
        result["network_requests"],
    ) == (0, 0, 0)
    assert (result["local_protocol_replies"], result["cloud_protocol_requests"]) == (4, 1)
    assert (outcome["terminal_reason"] is None) == passed
    assert (int((raw / "green.exit").read_text()) == 0) == passed
    observations = [
        (path, read(path))
        for path in sorted(
            (episode / "component/servo-frames").rglob(
                "observation.json",
            )
        )
    ]
    assert observations
    by_id = {}
    for path, frame in observations:
        values = struct.pack("<20d", *frame["intrinsics"], *frame["camera_to_world"])
        assert frame["calibration_version"] == hashlib.sha256(values).hexdigest()[:16], path
        uid = frame["observation_id"]
        assert uid not in by_id
        by_id[uid] = frame
    groups = defaultdict(list)
    for move in outcome["camera_adjustments"]:
        if move.get("source") == "CURRENT_RGBD_VISIBILITY_RECOVERY":
            groups[move["step_id"], move["physics_step"]].append(move)
    commands = read(episode / "component/commands.json")
    by_step = defaultdict(list)
    for record in commands:
        by_step[record["physics_step"]].append(record)
    recovery_groups = []
    max_ms = 0.0
    for action in outcome["actions"]:
        servo = action.get("visual_servo", {})
        visual_samples = servo.get("visual_samples", [])
        controls = servo.get("control_samples", [])
        assert len(visual_samples) == len(controls)
        for control, accepted in zip(controls, visual_samples, strict=True):
            max_ms = max(max_ms, control["sample_and_ik_s"] * 1000)
            rejected = accepted.get("camera_recovery", [])
            if not rejected:
                continue
            step = control["physics_step"]
            moves = groups[action["step_id"], step]
            assert len(moves) == len(rejected) <= 2
            capture_ids = [e["observation_id"] for e in rejected] + [accepted["observation_id"]]
            frames = [by_id[uid] for uid in capture_ids]
            assert len({frame["sim_time_s"] for frame in frames}) == 1
            assert len({tuple(frame["camera_to_world"]) for frame in frames}) == len(frames)
            transforms = []
            for move, frame in zip(moves, frames[1:], strict=True):
                expected = expected_transform(move["position_m"], move["look_at_m"])
                delta = np.max(np.abs(expected - frame["camera_to_world"]))
                assert delta <= 1e-9
                transforms.append(float(delta))
            camera = [m["command_seq"] for m in by_step[step] if m["type"] == "camera_position"]
            joint = [m["command_seq"] for m in by_step[step] if m["type"] == "joint_target"]
            assert len(camera) == len(moves)
            assert not joint or max(camera) < min(joint)
            recovery_groups.append(
                {
                    "step": action["step_id"],
                    "physics_step": step,
                    "sim_time_s": frames[0]["sim_time_s"],
                    "capture_ids": capture_ids,
                    "camera_command_seqs": camera,
                    "joint_command_seqs": joint,
                    "max_abs_transform_delta": max(transforms),
                    "sample_and_ik_ms": control["sample_and_ik_s"] * 1000,
                }
            )
    assert len(recovery_groups) == len(groups) and max_ms <= 100
    assert all(row["verdict"]["allowed"] for row in outcome["safety_checks"])
    source = raw.parent / "frozen-source"
    old = source / "pre-camera-binding/manifest.json"
    new = source / "post-camera-binding/manifest.json"
    for manifest_path in (old, new):
        manifest = read(manifest_path)
        assert len(manifest["files"]) == 50
        assert all(
            digest(manifest_path.parent / name) == h for name, h in manifest["files"].items()
        )
    paths = [
        "input-receipt.json",
        "fault-red.log",
        "fault-red-final.log",
        "fault-red-final.junit.xml",
        "cpu-final.log",
        "cpu-final.junit.xml",
        "full-replay-command.sh",
        "full-source-sha256.txt",
        "green.log",
        "green.junit.xml",
        "green/result.json",
        "green/component/commands.json",
        "green/component/physical-evidence.json",
        "servo-component.patch",
        "ttl-timeline.json",
    ]
    report = {
        "status": (
            "CAMERA_BINDING_NEGATIVES_AND_FULL_ZERO_API_REPLAY_PASSED"
            if passed
            else "CAMERA_BINDING_CPU_PASSED_FULL_REPLAY_STOPPED_AT_LIFT_TTL"
        ),
        "inputs_rehashed": len(read(raw / "input-receipt.json")["inputs"]),
        "cpu": {
            "expected_red_failures": 7,
            "red_controls_passed": 3,
            "final_passed": 235,
            "renderer_deselected": 3,
        },
        "full": {
            "scope": result["evidence_scope"],
            "worker_status": result["worker_status"],
            "component_status": result["status"],
            "actions": result["executed_actions"],
            "source_skills": list(dict.fromkeys(action["skill"] for action in outcome["actions"])),
            "total_physics_steps": result["physics_steps"],
            "paired_frames_hash_checked": len(by_id),
            "terminal_reason": outcome["terminal_reason"],
            "terminal_servo_reason": outcome["actions"][-1]["visual_servo"]["terminal_reason"],
            "max_accepted_sample_and_ik_ms": max_ms,
            "safety_allows": len(outcome["safety_checks"]),
            "retreat_phases_completed": [
                item["controller_return_step"]
                for item in outcome["actions"]
                if item["skill"] == "RETREAT"
            ],
            "physical": outcome["independent_physical_outcome"],
            "terminal_frames": outcome["marker_frames"][-2:],
            "recovery_groups": recovery_groups,
            "actual_models_loads_generations_api": [0, 0, 0],
            "full_replay_runs": 1,
            "extra_probes": 0,
        },
        "old_historical_semantic_scope": (
            "native fixed02/03 and 44101, prior exact sources retained"
        ),
        "source_manifests": {str(path): digest(path) for path in (old, new)},
        "remaining_unspent_real_runs": [44102, 44103, 44104],
        "remaining_runs_ready": passed,
        "failure_timeline": read(raw / "ttl-timeline.json"),
        "actual_calls_before_restart": {"cloud": 4, "local": 16},
        "formal_research": "NOT_ACCEPTED",
        "qualified_groups_added": 0,
        "hardware": "NOT_STARTED",
        "sha256": {str(raw / name): digest(raw / name) for name in paths},
    }
    with output.open("x") as handle:
        handle.write(json.dumps(report, indent=2) + "\n")
    print(f"{len(by_id)} bound frames, {len(recovery_groups)} recoveries, max {max_ms:.3f} ms")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    main(args.raw, args.output)
