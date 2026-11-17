"""Rescore the three fixed-scene post-repair runs from their local original bytes."""
from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import math
import subprocess
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    PhysicalSample,
    evaluate_evidence,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation

ROOT = Path(__file__).resolve().parents[4]
SOURCE = "41bb33344c0463a979327d0c78e2acd1088b458f"
PREVIOUS_VERIFIER = ROOT / (
    "artifacts/research/process/20261117-grasp-place-repair/verify_evidence.py"
)
SPEC = importlib.util.spec_from_file_location("original_grasp_verifier", PREVIOUS_VERIFIER)
assert SPEC is not None and SPEC.loader is not None
PREVIOUS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREVIOUS)


def read(path: Path):
    return json.loads(path.read_text())


def paired_frames(folder: Path) -> set[str]:
    ids = set()
    for path in sorted(folder.rglob("observation.json")):
        archived = read(path)
        values = {k: v for k, v in archived.items() if k in RGBDObservation.model_fields}
        for field, file in (
            ("rgb_png_base64", "rgb.png"),
            ("depth_float32_base64", "depth.f32"),
            ("valid_mask_base64", "valid_mask.u8"),
        ):
            values[field] = base64.b64encode((path.parent / file).read_bytes()).decode()
        observation = RGBDObservation.model_validate(values)
        assert observation.observation_id not in ids
        ids.add(observation.observation_id)
    return ids


def verify_worker(entry: Path, command: dict) -> dict:
    component = entry / "component"
    episode = read(component / "episode.json")
    assert command["returncode"] == 0
    assert episode["diagnostic_complete"] and episode["physical_success"]
    assert episode["terminal_reason"] is None
    assert episode["native_action_qualification"] == "UNKNOWN_NOT_GRANTED"
    assert episode["actions"][-1]["skill"] == "RETREAT"
    assert episode["marker_frames"][-1]["status"] == "OBSERVED"
    binding = read(entry / "role-binding.json")
    pins = {}
    for sources in (
        read(entry / "source-hashes.json")["files"],
        binding["edge_snapshot"]["source_hashes"],
        binding["device_source_hashes"],
    ):
        for name, digest in sources.items():
            assert pins.setdefault(name, digest) == digest, name
    assert "src/cloud_edge_robot_arm/simulation/mujoco/skill_robot.py" in pins
    for name, digest in pins.items():
        blob = subprocess.check_output(["git", "show", f"{SOURCE}:{name}"], cwd=ROOT)
        assert sha256(blob).hexdigest() == sha256((ROOT / name).read_bytes()).hexdigest() == digest
    samples = [
        PhysicalSample(**{k: PREVIOUS.tuples(v) for k, v in row.items()})
        for row in read(component / "physical-evidence.json")
    ]
    scored = evaluate_evidence(samples, CompletionCriteria("object", "target_region"))
    assert scored.success and not scored.safety_violation
    for field in ("measured_lift_m", "hold_s", "placed_stable_s"):
        assert math.isclose(getattr(scored, field), episode["independent_physical_outcome"][field])
    continuous = PREVIOUS.check_joint_commands(
        read(component / "commands.json"), episode["actions"],
    )
    ids = paired_frames(component / "servo-frames")
    safety = [row for row in episode["safety_checks"] if row["phase"] == "SERVO"]
    assert safety and all(
        row["verdict"]["allowed"] and row["observation_id"] in ids for row in safety
    )
    feedback = read(component / "robot-feedback.json")
    action_metrics = []
    for row in episode["actions"]:
        controls = row.get("visual_servo", {}).get("control_samples", [])
        if not controls:
            continue
        begin, end = row["start_step"], row["controller_return_step"]
        latency = max(item["sample_and_ik_s"] for item in controls)
        assert latency <= 0.1
        if row["skill"] in ("LIFT", "MOVE_TO_REGION", "PLACE"):
            inside = [s for s in samples if begin < s.physics_step <= end]
            assert len(inside) == end-begin
            assert all(s.left_finger_contact and s.right_finger_contact for s in inside)
        if "vertical_clearance" in row:
            path = VerticalClearancePath(
                **{k: PREVIOUS.tuples(v) for k, v in row["vertical_clearance"].items()}
            )
            peak = path.start_m[2]
            for trace in feedback:
                if begin < trace["physics_step"] <= end:
                    xyz = tuple(trace["tcp_position_m"])
                    path.check_position(xyz, peak_z=peak)
                    peak = max(peak, xyz[2])
        dt = controls[-1]["wall_elapsed_s"] - controls[0]["wall_elapsed_s"]
        action_metrics.append({
            "skill": row["skill"], "samples": len(controls),
            "wall_hz": (len(controls)-1) / dt, "max_sample_ms": 1000 * latency,
        })
    return {
        "worker": command["artifact"], "raw_component": str(component), "wall_s": command["wall_s"],
        "physical": asdict(scored), "frames": len(ids), "bound_source_files": len(pins),
        "continuous_joint_targets": continuous, "actions": action_metrics,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path, help="local worker-checks directory")
    args = parser.parse_args()
    workers = []
    for number in range(1, 4):
        label = f"worker-{number:02d}"
        command = read(args.raw / f"{label}-command.json")
        matches = [
            folder / "worker-run/component/episode.json"
            for folder in (args.raw / label).glob("test_*")
            if not folder.is_symlink() and (folder / "worker-run/component/episode.json").is_file()
        ]
        assert len(matches) == 1, label
        workers.append(verify_worker(matches[0].parents[1], command))
    actions = [a for w in workers for a in w["actions"]]
    print(json.dumps({
        "scope": "FIXED_SCENE_SIMULATION_DEVELOPMENT",
        "runtime_commit": SOURCE,
        "worker_successes": len(workers),
        "paired_frames_checked": sum(row["frames"] for row in workers),
        "min_visual_wall_hz": min(a["wall_hz"] for a in actions),
        "max_visual_wall_hz": max(a["wall_hz"] for a in actions),
        "max_sample_ms": max(a["max_sample_ms"] for a in actions),
        "real_models": "NOT_RUN",
        "hardware": "NOT_RUN",
        "formal_acceptance": "NOT_GRANTED",
        "workers": workers,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
