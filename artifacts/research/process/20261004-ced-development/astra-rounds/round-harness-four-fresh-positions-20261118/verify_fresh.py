"""Independently audit the four preregistered MuJoCo development slots."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import struct
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

from cloud_edge_robot_arm.harness.checkout import sha256_file, verify_checkout
from cloud_edge_robot_arm.harness.config import HarnessConfig, load_config, strict_json
from cloud_edge_robot_arm.harness.evidence import EpisodeExpectation, verify_evidence
from cloud_edge_robot_arm.research.sol_molmo_offline_regression import FrozenCase, load_observation
from cloud_edge_robot_arm.research.sol_molmo_scenarios import sample_component_scene
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    PhysicalSample,
    evaluate_evidence,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.role_models import configuration_hash

ROUND = Path(__file__).resolve().parent
ROOT = ROUND.parents[5]
PREALLOCATION_SHA256 = "b68f756ff5570fc6886c5f8e50771a549eb73464bb539e3716a957ed1e116ec8"
SEEDS = tuple(range(2026111801, 2026111805))
COUNTER_LIMITS = {
    "cloud_requests": 1, "cloud_request_reservations": 1, "local_generations": 4,
    "local_generations_completed": 4, "model_loads": 1,
}
FREEZE_SCHEMA = "bigsmall.development.four-fresh-freeze.v1"
SUCCESSOR_STAGE = "verification/v5-5103e7f4"
SUCCESS_SKILLS = (
    "MOVE_ABOVE", "APPROACH", "GRASP", "LIFT", "MOVE_TO_REGION", "PLACE", "RELEASE",
    "RETREAT", "RETREAT",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read(path: Path) -> Any:
    return strict_json(path.read_bytes())


def write_new(path: Path, value: Any) -> None:
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        output.write(data)
        output.flush()
        import os

        os.fsync(output.fileno())


def read_allocation(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == PREALLOCATION_SHA256, "preallocation bytes changed")
    allocation = strict_json(data)
    require(isinstance(allocation, dict), "invalid four-slot preallocation")
    episodes = allocation["episodes"]
    require(tuple(row["seed"] for row in episodes) == SEEDS, "unknown slot order")
    for row in episodes:
        expected = sample_component_scene(row["seed"], "development")
        require(row == {"id": f"fresh-{row['seed']}"} | expected, "unknown slot or sampled pose")
    return allocation


def read_freeze(path: Path, expected_sha256: str) -> dict[str, Any]:
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == expected_sha256, "freeze receipt SHA256 mismatch")
    receipt = strict_json(data)
    require(
        isinstance(receipt, dict)
        and receipt.get("schema") == FREEZE_SCHEMA
        and receipt.get("preallocation_sha256") == PREALLOCATION_SHA256
        and {f"fresh-{seed}" for seed in SEEDS} == set(receipt.get("slots", {})),
        "freeze receipt does not cover the four registered slots",
    )
    return receipt


def verify_frozen_sources(checkout: Path, freeze: dict[str, Any]) -> None:
    commit = freeze["commit"]
    require(bool(re.fullmatch(r"[0-9a-f]{40}", commit)), "freeze commit is malformed")
    tree = subprocess.check_output(
        ["git", "rev-parse", commit + "^{tree}"], cwd=checkout, text=True,
    )
    require(tree.strip() == freeze["tree"], "freeze commit/tree mismatch")
    for relative, digest in freeze["product_sources"].items():
        path = checkout / relative
        require(
            path.resolve() == path
            and path.is_relative_to(checkout)
            and sha256_file(path) == digest,
            f"freeze source changed at {relative}",
        )


def check_slot_directories(native: Path, slots: list[dict[str, Any]]) -> None:
    names = {slot["id"] for slot in slots}
    for path in native.glob("fresh-*"):
        require(path.name in names and path.is_dir() and not path.is_symlink(), "unknown slot path")


def slot_config_path(root: Path, freeze: dict[str, Any], identity: str) -> Path:
    stage = freeze.get("staging", "")
    require(stage in {"", SUCCESSOR_STAGE}, "freeze configuration staging is unregistered")
    path = root / stage / "configs" / f"{identity}.json"
    require(path.resolve() == path, "freeze configuration staging is redirected")
    return path


def check_pose(
    slot: dict[str, Any], config: HarnessConfig,
    assignment: dict[str, Any], applied: dict[str, Any],
) -> dict[str, Any]:
    request = {key: value for key, value in slot.items() if key != "id"}
    seed = slot["seed"]
    require(
        config.seed == seed and type(assignment["seed"]) is int and assignment["seed"] == seed,
        "registered seed differs from configuration or assignment",
    )
    require(
        config.scene_split == slot["split"] == "development",
        "registered development split changed",
    )
    require(
        assignment["component_scene"] == request == applied["requested_scene"]
        and applied["scope"] == "OFFLINE_INITIAL_PHYSICS_AUDIT_NOT_ONLINE_MODEL_INPUT",
        "requested pose or split differs from preallocation",
    )
    position = applied["object_position_m"]
    quaternion = applied["object_quaternion_wxyz"]
    require(
        isinstance(position, list) and len(position) == 3
        and isinstance(quaternion, list) and len(quaternion) == 4
        and all(
            type(value) in {float, int} and math.isfinite(value) for value in position + quaternion
        ),
        "applied pose is not a finite 3D position and quaternion",
    )
    wanted = slot["object_position_m"]
    require(all(
        math.isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-12)
        for actual, expected in zip(position, wanted, strict=True)
    ), "applied position differs from preregistered pose")
    yaw = slot["object_yaw_rad"]
    expected_q = (math.cos(yaw / 2), 0, 0, math.sin(yaw / 2))
    sign = 1 if quaternion[0] >= 0 else -1
    require(all(
        math.isclose(sign * actual, expected, rel_tol=1e-6, abs_tol=1e-12)
        for actual, expected in zip(quaternion, expected_q, strict=True)
    ), "applied yaw or upright orientation differs from preregistered pose")
    applied_yaw = 2 * math.atan2(sign * quaternion[3], sign * quaternion[0])
    return {
        "condition": slot["condition"],
        "occlusion": "INTENDED_CONDITION_ONLY",
        "requested_position_m": wanted,
        "applied_position_m": position,
        "position_error_m": [
            actual - expected for actual, expected in zip(position, wanted, strict=True)
        ],
        "requested_yaw_rad": yaw,
        "applied_yaw_rad": applied_yaw,
        "yaw_error_rad": math.remainder(applied_yaw - yaw, 2 * math.pi),
        "applied_quaternion_wxyz": quaternion,
        "tolerance": {"relative": 1e-6, "absolute": 1e-12},
    }


def check_sources(
    role: dict[str, Any], source_index: dict[str, Any], frozen: dict[str, str],
    slot_freeze: dict[str, Any],
) -> int:
    require(
        configuration_hash(role) == slot_freeze["role_binding_sha256"],
        "role binding differs from freeze",
    )
    bundle = role["bundle"]
    cloud = bundle["cloud_snapshot"]
    edge = role["edge_snapshot"]
    device = role["device_source_hashes"]
    require(
        configuration_hash(bundle) == role["bundle_hash"]
        and configuration_hash(edge) == bundle["edge_provider_hash"]
        and configuration_hash(device) == bundle["device_pipeline_hash"],
        "role bundle hash or role group digest differs",
    )
    checked = set()
    for group in (cloud["source_hashes"], edge["source_hashes"], device, source_index["files"]):
        require(isinstance(group, dict) and bool(group), "role source group empty")
        for path, digest in group.items():
            require(frozen.get(path) == digest, f"role or entry source SHA differs at {path}")
            checked.add(path)
    return len(checked)


def check_budget(result: dict[str, Any], indexed_counts: dict[str, int]) -> dict[str, int]:
    for key, ceiling in COUNTER_LIMITS.items():
        value = result.get(key)
        require(type(value) is int and 0 <= value <= ceiling, f"invalid resource budget at {key}")
        require(value == indexed_counts.get(key), f"resource budget differs from indexed {key}")
    require(
        result["cloud_requests"] <= result["cloud_request_reservations"]
        and result["local_generations_completed"] <= result["local_generations"],
        "inconsistent model resource budget",
    )
    return {key: result[key] for key in COUNTER_LIMITS}


def read_index(
    entry: Path, *, expected: EpisodeExpectation | None = None,
) -> tuple[dict[str, Any], FrozenCase]:
    summary = verify_evidence(entry, expected=expected)
    data = (entry / "evidence-manifest.json").read_bytes()
    require(
        hashlib.sha256(data).hexdigest() == summary["manifest_sha256"],
        "episode index changed between audit and read",
    )
    manifest = strict_json(data)
    indexed = {row["path"]: row for row in manifest["files"]}
    return summary, FrozenCase(entry, indexed, {})


def read_frame(
    entry: Path, indexed: dict[str, Any], folder: str, episode_id: str,
) -> RGBDObservation:
    case = FrozenCase(entry, indexed, {})
    metadata = case.json(folder + "/observation.json")
    observation = load_observation(case, folder)
    require(
        observation.episode_id == episode_id
        and metadata["observation_id"] == observation.observation_id
        and metadata["checksum_sha256"] == observation.checksum_sha256,
        "observed frame identity differs from its indexed episode",
    )
    return observation


def _frame_calibration(observation: RGBDObservation) -> None:
    values = struct.pack("<20d", *observation.intrinsics, *observation.camera_to_world)
    require(
        observation.source == "mujoco_camera"
        and observation.calibration_version == hashlib.sha256(values).hexdigest()[:16],
        "observed frame has invalid MuJoCo calibration",
    )


def _legacy_verifier() -> Any:
    path = ROOT / "artifacts/research/process/20261117-grasp-lift-stop/verify_workers.py"
    spec = importlib.util.spec_from_file_location("frozen_worker_audit", path)
    if spec is None or spec.loader is None:
        raise ValueError("retained worker verifier unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_model_evidence(
    case: FrozenCase, result: dict[str, Any], freeze: dict[str, Any],
) -> dict[str, Any]:
    names = case.files
    started = [
        name for name in names
        if re.fullmatch(r"raw/molmo/request-\d{4}/generation-started.json", name)
    ]
    completed = [
        name for name in names
        if re.fullmatch(r"raw/molmo/request-\d{4}/generation-completed.json", name)
    ]
    for sequence, paths, label in (
        ("started", started, "generation_calls_started"),
        ("completed", completed, "generation_calls_completed"),
    ):
        values = [case.json(path)[label] for path in sorted(paths)]
        require(
            values == list(range(1, len(values) + 1)), f"invalid generation {sequence} evidence",
        )
    require(
        {name.rsplit("/", 1)[0] for name in completed}.issubset(
            name.rsplit("/", 1)[0] for name in started
        ),
        "completed generation lacks a bound started record",
    )
    initial = case.json("raw/molmo/initial.json")
    require(
        initial["model"] == "allenai/Molmo2-ER" and initial["precision"] == "BF16"
        and initial["generation_limit"] == 4
        and initial["asset_manifest_sha256"] == freeze["asset_manifest_sha256"],
        "Molmo model/precision/asset/budget differs from freeze",
    )
    load_path = "raw/molmo/load-started.json"
    loads = case.json(load_path)["model_loads_started"] if load_path in names else 0
    request_exists = "raw/cloud/request.json" in names
    response_path = "raw/cloud/response.json"
    response = case.json(response_path) if response_path in names else None
    costs = case.json("costs.json")
    cloud = [request for request in costs["requests"] if request["is_cloud_model"] is True]
    require(costs["summary"]["cloud_model_requests"] == len(cloud), "cloud cost ledger differs")
    if request_exists:
        require(
            case.json("raw/cloud/request.json")["model"] == "gpt-6.1-sol",
            "cloud request model differs",
        )
    if response is not None:
        require(
            request_exists and response.get("model") == "gpt-6.1-sol",
            "cloud response model differs",
        )
    observed = {
        "cloud_requests": len(cloud), "cloud_request_reservations": int(request_exists),
        "local_generations": len(started), "local_generations_completed": len(completed),
        "model_loads": loads,
    }
    budget = check_budget(result, observed)
    return budget | {
        "usage": None if response is None else response.get("usage"),
        "ledger": [{key: row[key] for key in (
            "provider_version", "status", "serialized_sent_bytes", "serialized_received_bytes",
            "monetary_cost",
        )} for row in cloud],
        "billed_cost": None,
    }


def check_component(
    case: FrozenCase, result: dict[str, Any], episode: dict[str, Any],
) -> dict[str, Any]:
    legacy = _legacy_verifier()
    actions = episode["actions"]
    physical = [
        PhysicalSample(**{key: legacy.PREVIOUS.tuples(value) for key, value in row.items()})
        for row in case.json("component/physical-evidence.json")
    ]
    score = evaluate_evidence(physical, CompletionCriteria("object", "target_region"))
    require(
        score.success == result["physical_success"] == episode["physical_success"],
        "physical rescoring differs from archived result",
    )
    for key in ("measured_lift_m", "hold_s", "placed_stable_s"):
        require(math.isclose(
            getattr(score, key), episode["independent_physical_outcome"][key],
        ), f"physical rescoring differs at {key}")
    commands = case.json("component/commands.json")
    accepted = sum(
        row["type"] == "joint_target" and row.get("accepted") is True for row in commands
    )
    complete = result["component_success"] is True
    if actions:
        try:
            continuous = legacy.PREVIOUS.check_joint_commands(commands, actions)
        except ValueError as exc:
            if complete or str(exc) != "insufficient continuous command/handoff evidence":
                raise
            continuous = {"status": "PARTIAL_HOFF_EVIDENCE", "accepted_joint_targets": accepted}
    else:
        require(accepted == 0, "ordinary joint target without a recorded action")
        continuous = {"status": "NO_ORDINARY_JOINT_TARGETS", "accepted_joint_targets": 0}
    directories = {
        name.removesuffix("/observation.json")
        for name in case.files
        if name.startswith("component/servo-frames/") and name.endswith("/observation.json")
    }
    frames = {}
    for folder in sorted(directories):
        observation = read_frame(case.root, case.files, folder, result["episode_id"])
        _frame_calibration(observation)
        require(observation.observation_id not in frames, "duplicate recorded servo observation")
        frames[observation.observation_id] = observation
    require(
        legacy.paired_frames(case.root / "component/servo-frames") == frames.keys(),
        "servo frame index coverage differs from raw folder",
    )
    safety = [row for row in episode["safety_checks"] if row["phase"] == "SERVO"]
    require(all(
        row["verdict"]["allowed"] is True and row["observation_id"] in frames for row in safety
    ), "recorded servo safety evidence is unbound or rejected")
    details = []
    for action in actions:
        servo = action.get("visual_servo", {})
        for record in servo.get("visual_samples", []):
            frame = frames.get(record["observation_id"])
            require(
                frame is not None and frame.checksum_sha256 == record["checksum_sha256"]
                and frame.calibration_version == record["calibration_version"]
                and frame.sim_time_s == record["sim_time_s"],
                "accepted servo sample does not bind its archived paired frame",
            )
        latencies = [row["sample_and_ik_s"] for row in servo.get("control_samples", [])]
        require(
            all(0 <= value <= 0.1 for value in latencies), "accepted servo sample exceeded 100ms",
        )
        details.append({
            "skill": action["skill"],
            "step_id": action["step_id"],
            "start_step": action["start_step"],
            "controller_return_step": action["controller_return_step"],
            "continuation": action["continuation"],
            "vertical_clearance": "vertical_clearance" in action,
            "control_samples": len(latencies),
            "max_sample_and_ik_ms": max(latencies, default=0) * 1000,
            "servo_terminal_reason": servo.get("terminal_reason"),
        })
    marker = None
    if "after/marker-validation.json" in case.files:
        final = read_frame(case.root, case.files, "after", result["episode_id"])
        _frame_calibration(final)
        marker = case.json("after/marker-validation.json")
        require(
            marker["observation_id"] == final.observation_id
            and marker["observation_checksum_sha256"] == final.checksum_sha256
            and marker == episode["marker_frames"][-1] == result["marker_after"],
            "terminal marker does not bind the archived final frame",
        )
    if complete:
        require(
            episode["diagnostic_complete"] is True and score.success
            and result["worker_status"] == "SUCCEEDED"
            and tuple(action["skill"] for action in actions) == SUCCESS_SKILLS
            and details[-2]["vertical_clearance"] and not details[-1]["vertical_clearance"]
            and not details[-2]["continuation"] and details[-1]["continuation"]
            and marker is not None and marker["status"] == "OBSERVED"
            and marker["physics_step"] > details[-1]["controller_return_step"],
            "completed task lacks normal chain, two retreat phases or final marker",
        )
    return {
        "physical": asdict(score),
        "command_continuity": continuous,
        "actions": details,
        "servo_frame_count": len(frames),
        "servo_safety_checks": len(safety),
        "terminal_marker_status": None if marker is None else marker["status"],
    }


def audit_slot(
    root: Path, checkout: Path, freeze: dict[str, Any], freeze_sha: str, slot: dict[str, Any],
) -> dict[str, Any]:
    identity = slot["id"]
    expected = freeze["slots"][identity]
    prefix = {"id": identity, "seed": slot["seed"]}
    receipts = root / "receipts"
    start_path = receipts / f"{identity}-started.json"
    end_path = receipts / f"{identity}-finished.json"
    entry = root / "native" / identity
    if not start_path.exists():
        require(
            not end_path.exists() and not entry.exists(),
            "slot has raw bytes without a launch receipt",
        )
        return prefix | {"audit_status": "NOT_LAUNCHED", "occupancy": {"cloud": 0, "local": 0}}
    start = read(start_path)
    binding = prefix | {
        "preallocation_sha256": PREALLOCATION_SHA256,
        "freeze_sha256": freeze_sha,
        "config_sha256": expected["config_sha256"],
    }
    require(
        all(start.get(key) == value for key, value in binding.items()),
        "slot start binding differs",
    )
    if not end_path.exists():
        return prefix | {
            "audit_status": "LAUNCHED_UNKNOWN", "occupancy": {"cloud": 1, "local": 4},
            "observed_counters": None, "reason": "no final launch receipt",
        }
    end = read(end_path)
    require(
        all(end.get(key) == value for key, value in binding.items())
        and end["started_sha256"] == sha256_file(start_path),
        "slot final receipt differs from its launch binding",
    )
    stdout = receipts / f"{identity}.stdout"
    stderr = receipts / f"{identity}.stderr"
    require(
        sha256_file(stdout) == end["stdout_sha256"] and sha256_file(stderr) == end["stderr_sha256"],
        "slot launcher logs differ from final receipt",
    )
    try:
        launcher = read(stdout)
    except ValueError:
        launcher = {}
    exit_fields = {
        "returncode": end["returncode"],
        **{
            key: launcher[key]
            for key in ("wrapper_exit_code", "episode_exit_code", "wrapper_stop_reason", "signal")
            if key in launcher
        },
    }
    if launcher.get("status") == "NOT_STARTED" and not entry.exists():
        return prefix | {
            "audit_status": "PRE_DELEGATION_BLOCKED", "occupancy": {"cloud": 0, "local": 0},
            "launcher_status": launcher["status"],
        } | exit_fields
    if launcher.get("status") == "INCOMPLETE_UNKNOWN" or not entry.exists():
        return prefix | {
            "audit_status": "LAUNCHED_UNKNOWN", "occupancy": {"cloud": 1, "local": 4},
            "observed_counters": None,
            "launcher_status": launcher.get("status"),
        } | exit_fields
    cfg_path = slot_config_path(root, freeze, identity)
    require(sha256_file(cfg_path) == expected["config_sha256"], "slot config diverges from freeze")
    config = load_config(cfg_path)
    source = verify_checkout(checkout, config)
    native = launcher.get("native_python", {})
    require(
        launcher["source"]["git_revision"] == freeze["commit"]
        and launcher["source"]["files"] == source.files
        and launcher["planned_configuration"] == config.model_dump(mode="json")
        and launcher["planned_configuration_sha256"] == config.fingerprint()
        and launcher["model_asset_manifest_sha256"] == freeze["asset_manifest_sha256"]
        and native.get("status") == "READY_TO_DELEGATE"
        and native.get("executable_sha256") == freeze["native_python_sha256"]
        and native.get("registered_overlay", {}).get("sha256") == freeze["overlay_sha256"]
        and native.get("r545_admission", {}).get("status") == "IMPORT_AND_CPU_ABI_PASS",
        "launcher configuration or native runtime differs from freeze",
    )
    summary, case = read_index(entry, expected=EpisodeExpectation(source, config, True))
    require(
        launcher["evidence"]["manifest_sha256"] == summary["manifest_sha256"],
        "launcher and independent evidence indices differ",
    )
    result = case.json("result.json")
    episode = case.json("component/episode.json")
    applied = case.json("component/scene-application.json")
    role = case.json("role-binding.json")
    job = case.json("worker/job.json")
    runtime_job = case.json("worker/runtime_job.json")
    require(
        result["source_snapshot_status"] == "COMPLETE" and result["changed_source_paths"] == []
        and result["episode_id"] == episode["episode_id"] and isinstance(result["episode_id"], str)
        and result["job_id"] == job["job_id"] and job == runtime_job
        and job["source_tree_hash"] == role["bundle_hash"] and job["seed"] == slot["seed"]
        and job["attempt"] == 1 and job["timeout_seconds"] == 120
        and job["status"] == result["worker_status"] == runtime_job["status"]
        and job["hardware_write_operations"] == []
        and job["real_controller_contacted"] is False and job["hardware_motion_observed"] is False
        and applied == episode["scene_application"]
        and launcher["status"] == result["status"] and launcher["episode"] == summary["episode"],
        "worker, raw evidence, and launcher do not bind one frozen slot",
    )
    pose = check_pose(slot, config, case.json("scene-assignment.json"), applied)
    sources = check_sources(
        role, case.json("source-hashes.json"), freeze["product_sources"], expected,
    )
    models = check_model_evidence(case, result, freeze)
    return prefix | {
        "audit_status": "VERIFIED",
        "occupancy": {
            "cloud": models["cloud_request_reservations"], "local": models["local_generations"],
        },
        "observed_counters": models,
        "manifest_sha256": summary["manifest_sha256"],
        "manifest_file_count": summary["file_count"],
        "source_files_checked": sources,
        "role_bundle_sha256": role["bundle_hash"],
        "pose": pose,
        "job_id": job["job_id"],
        "episode_id": result["episode_id"],
        "worker_status": result["worker_status"],
        "component_success": result["component_success"],
        "physical_success": result["physical_success"],
        "terminal_reason": result["terminal_reason"],
        "elapsed_s": result["elapsed_s"],
        "launch_wall_s": end["wall_s"],
    } | exit_fields | check_component(case, result, episode)


def batch_report(rows: list[dict[str, Any]], freeze_sha: str) -> dict[str, Any]:
    return {
        "scope": "SAME_CANDIDATE_FOUR_MUJOCO_DEVELOPMENT_SLOTS",
        "preallocation_sha256": PREALLOCATION_SHA256,
        "freeze_sha256": freeze_sha,
        "preallocated": len(SEEDS),
        "component_completed": sum(row.get("component_success") is True for row in rows),
        "physical_successful": sum(row.get("physical_success") is True for row in rows),
        "verified_slots": sum(row["audit_status"] == "VERIFIED" for row in rows),
        "total_cloud_slots_occupied": sum(row["occupancy"]["cloud"] for row in rows),
        "total_local_generations_occupied": sum(row["occupancy"]["local"] for row in rows),
        "total_billed_cost": None,
        "hardware_dispatch": False,
        "formal_research": "NOT_ACCEPTED",
        "qualified_groups_added": 0,
        "b0_selection_started": False,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--checkout", type=Path, default=ROOT)
    parser.add_argument("--freeze-receipt", type=Path, required=True)
    parser.add_argument("--freeze-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, checkout = args.raw_root.resolve(strict=True), args.checkout.resolve(strict=True)
    output = args.output.resolve()
    require(
        not any(output.is_relative_to(root / name) for name in ("native", "configs", "receipts"))
        and output != args.freeze_receipt.resolve(),
        "audit output overlaps a protected input",
    )
    slots = read_allocation(ROUND / "preallocation.json")["episodes"]
    freeze = read_freeze(args.freeze_receipt, args.freeze_sha256)
    verify_frozen_sources(checkout, freeze)
    check_slot_directories(root / "native", slots)
    rows = []
    for slot in slots:
        try:
            row = audit_slot(root, checkout, freeze, args.freeze_sha256, slot)
        except (OSError, ValueError, KeyError, AssertionError, TypeError) as exc:
            row = {"id": slot["id"], "seed": slot["seed"], "audit_status": "AUDIT_REJECTED",
                   "occupancy": {"cloud": 1, "local": 4}, "reason": str(exc)}
        rows.append(row)
    write_new(output, batch_report(rows, args.freeze_sha256))
    return 2 if any(row["audit_status"] == "AUDIT_REJECTED" for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
