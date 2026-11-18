"""Read-only audit of preallocated actual model trials and their frozen source bytes."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import struct
import subprocess
from dataclasses import asdict
from pathlib import Path

from cloud_edge_robot_arm.harness.evidence import verify_evidence
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    PhysicalSample,
    evaluate_evidence,
)

ROOT = Path(__file__).resolve().parents[4]
PREVIOUS = ROOT / "artifacts/research/process/20261117-grasp-lift-stop/verify_workers.py"
spec = importlib.util.spec_from_file_location("immutable_previous_worker_audit", PREVIOUS)
assert spec and spec.loader
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)


def read(path: Path):
    return json.loads(path.read_bytes())


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_sources(entry: Path, raw: Path) -> tuple[int, str]:
    pins = dict(read(entry / "source-hashes.json")["files"])
    binding = read(entry / "role-binding.json")
    for group in (binding["edge_snapshot"]["source_hashes"], binding["device_source_hashes"]):
        for name, expected in group.items():
            assert pins.setdefault(name, expected) == expected, name
    for label in ("pre-camera-binding", "post-camera-binding"):
        base = raw / "frozen-source" / label
        if all(
            (base / name).is_file() and digest((base / name).read_bytes()) == expected
            for name, expected in pins.items()
        ):
            return len(pins), label
    # The original unsuccessful native run preceded every source edit this turn.
    base_commit = read(
        ROOT / "artifacts/research/process/20261118-real-model-harness/preallocation.json"
    )["base_commit"]
    for name, expected in pins.items():
        content = subprocess.check_output(["git", "show", f"{base_commit}:{name}"], cwd=ROOT)
        assert digest(content) == expected, name
    return len(pins), base_commit


def audit(entry: Path, raw: Path, expected: dict) -> dict:
    indexed = verify_evidence(entry)
    result = read(entry / "result.json")
    assignment = read(entry / "scene-assignment.json")
    assert assignment["seed"] == expected["seed"]
    assert assignment.get("component_scene", {}).get("split") == expected["scene_split"]
    assert result["changed_source_paths"] == [] and result["source_snapshot_status"] == "COMPLETE"
    count, source_label = verify_sources(entry, raw)
    assert result["cloud_requests"] <= 1 and result["local_generations"] <= 4
    assert result["model_loads"] <= 1
    assert result["hardware_dispatch"] is False and result["formal_research"] == "NOT_ACCEPTED"
    assert result["qualified_groups_added"] == 0
    episode = read(entry / "component/episode.json")
    samples = [
        PhysicalSample(**{k: legacy.PREVIOUS.tuples(v) for k, v in row.items()})
        for row in read(entry / "component/physical-evidence.json")
    ]
    scored = evaluate_evidence(samples, CompletionCriteria("object", "target_region"))
    assert scored.success == result["physical_success"]
    for field in ("measured_lift_m", "hold_s", "placed_stable_s"):
        assert math.isclose(getattr(scored, field), episode["independent_physical_outcome"][field])
    assert not scored.safety_violation
    commands = read(entry / "component/commands.json")
    if episode["actions"]:
        try:
            continuity = legacy.PREVIOUS.check_joint_commands(commands, episode["actions"])
        except ValueError as error:
            if (
                result["component_success"] is True
                or str(error) != "insufficient continuous command/handoff evidence"
            ):
                raise
            # The frozen checker has already checked every present interval.
            # An interrupted prefix cannot supply the full-task handoff count.
            continuity = {
                "status": "PARTIAL_HADOFF_EVIDENCE",
                "full_task_handoff_requirement_met": False,
                "accepted_joint_targets": sum(
                    c["type"] == "joint_target" and c.get("accepted") is True for c in commands
                ),
            }
    else:
        assert not any(row["type"] == "joint_target" for row in commands)
        continuity = {"status": "NO_ORDINARY_JOINT_TARGETS", "count": 0}
    ids = legacy.paired_frames(entry / "component/servo-frames")
    for metadata in (entry / "component/servo-frames").rglob("observation.json"):
        frame = read(metadata)
        calibration = digest(struct.pack("<20d", *frame["intrinsics"], *frame["camera_to_world"]))[
            :16
        ]
        assert frame["calibration_version"] == calibration
    checks = [row for row in episode["safety_checks"] if row["phase"] == "SERVO"]
    assert all(row["verdict"]["allowed"] and row["observation_id"] in ids for row in checks)
    latencies = [
        sample["sample_and_ik_s"]
        for action in episode["actions"]
        for sample in action.get("visual_servo", {}).get("control_samples", [])
    ]
    assert all(value <= 0.1 for value in latencies)
    completed = result["component_success"] is True
    if completed:
        assert (
            episode["diagnostic_complete"]
            and scored.success
            and result["worker_status"] == "SUCCEEDED"
        )
        skills = [a["skill"] for a in episode["actions"]]
        assert skills == [
            "MOVE_ABOVE",
            "APPROACH",
            "GRASP",
            "LIFT",
            "MOVE_TO_REGION",
            "PLACE",
            "RELEASE",
            "RETREAT",
            "RETREAT",
        ]
        assert episode["marker_frames"][-1]["status"] == "OBSERVED"
    usage = {}
    response = entry / "raw/cloud/response.json"
    if response.exists():
        cloud = read(response)
        assert cloud.get("model") == "gpt-6.1-sol"
        usage = cloud.get("usage") or {}
    provider_calls = list((entry / "raw/molmo").glob("request-*/generation-completed.json"))
    assert len(provider_calls) == result["local_generations_completed"]
    return {
        "id": expected["id"],
        "seed": expected["seed"],
        "split": expected["scene_split"],
        "status": result["status"],
        "component_success": completed,
        "physical": asdict(scored),
        "terminal_reason": result["terminal_reason"],
        "worker_status": result.get("worker_status"),
        "online_reported_complete": result.get("online_reported_complete"),
        "model_loads": result["model_loads"],
        "local_generations": result["local_generations"],
        "cloud_requests": result["cloud_requests"],
        "cloud_usage": usage,
        "elapsed_s": result["elapsed_s"],
        "source_group": source_label,
        "bound_source_files": count,
        "indexed_file_count": indexed["file_count"],
        "servo_frames": len(ids),
        "safety_checks": len(checks),
        "max_accepted_sample_ik_ms": max(latencies, default=0) * 1000,
        "continuous_targets": continuity,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    planned = read(
        ROOT / "artifacts/research/process/20261118-real-model-harness/preallocation.json"
    )
    rows = []
    for expected in planned["episodes"]:
        entry = args.raw_root / "native" / expected["id"]
        rows.append(
            audit(entry, args.raw_root, expected)
            if (entry / "result.json").exists()
            else {"id": expected["id"], "status": "NOT_RUN"}
        )
    summary = {
        "scope": "BOUNDED_MUJOCO_REAL_MODELS_DEVELOPMENT_NOT_FORMAL",
        "rows": rows,
        "component_completed_count": sum(row.get("component_success", False) for row in rows),
        "physical_success_count": sum(
            row.get("physical", {}).get("success", False) for row in rows
        ),
        "preallocated_count": len(rows),
        "formal_research": "NOT_ACCEPTED",
        "hardware_dispatch": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(
        json.dumps(
            {
                "verified_rows": len(rows),
                "component_completed_count": summary["component_completed_count"],
                "physical_success_count": summary["physical_success_count"],
            }
        )
    )


if __name__ == "__main__":
    main()
