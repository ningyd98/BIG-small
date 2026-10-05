"""Read-only verification and independent replay of RGB-D teacher trajectories."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from pydantic import TypeAdapter, ValidationError

from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec, TrajectoryFrame, content_digest
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    PhysicalSample,
    evaluate_evidence,
)

if __package__:
    from scripts.generate_rgbd_trajectories import (
        TrajectorySmokeConfig,
        _assignments,
        _protocol_snapshot,
    )
else:
    from generate_rgbd_trajectories import (  # type: ignore[import-not-found,no-redef]
        TrajectorySmokeConfig,
        _assignments,
        _protocol_snapshot,
    )


def _same_outcome(recorded: dict[str, Any], replayed: dict[str, Any]) -> bool:
    try:
        return content_digest(recorded) == content_digest(replayed)
    except (TypeError, ValueError):
        return False


def validate_trajectory_dataset(root: Path) -> dict[str, Any]:
    """Validate the frozen producer protocol and replay every physical outcome."""
    report: dict[str, Any] = {
        "schema_version": "rgbd.trajectory.validation.v1",
        "dataset": str(root.resolve()),
        "valid": False,
        "accepted": False,
        "assigned": 0,
        "published": 0,
        "physical_success": 0,
        "execution_verified": 0,
        "control_positive_success": False,
        "control_negative_success": None,
        "status_counts": {},
        "safety_event_counts": {},
        "errors": [],
    }
    errors: list[str] = report["errors"]
    try:
        manifest = cast(dict[str, Any], json.loads((root / "manifest.json").read_text()))
    except (OSError, ValueError) as exc:
        errors.append(f"manifest unreadable: {exc}")
        return report
    if manifest.get("schema_version") != "rgbd.trajectory.manifest.v1":
        errors.append("manifest schema version is unsupported")
        return report
    protocol = _protocol_snapshot()
    protocol_hash = content_digest(protocol)
    if (
        manifest.get("protocol_hash") != protocol_hash
        or content_digest(manifest.get("protocol")) != protocol_hash
    ):
        errors.append("trajectory protocol/version differs from current teacher and scoring code")
        return report
    config = manifest.get("config")
    asset_hash = manifest.get("asset_sha256")
    if not isinstance(config, dict) or not isinstance(asset_hash, str):
        errors.append("manifest config or asset hash is missing")
        return report
    model_path = config.get("model_path")
    if not isinstance(model_path, str):
        errors.append("manifest robot model path is missing")
        return report
    try:
        current_asset_hash = hashlib.sha256(Path(model_path).read_bytes()).hexdigest()
    except OSError as exc:
        errors.append(f"robot asset unreadable: {exc}")
        return report
    if asset_hash != current_asset_hash:
        errors.append("robot asset SHA256 differs from manifest")
    expected_config_hash = content_digest({
        "config": config, "asset": asset_hash, "protocol_hash": protocol_hash,
    })
    if manifest.get("config_hash") != expected_config_hash:
        errors.append("manifest config/protocol hash mismatch")
    assignments = manifest.get("assignments")
    requested = manifest.get("requested_episodes")
    if not isinstance(assignments, list) or not isinstance(requested, int):
        errors.append("manifest assignments are malformed")
        return report
    report["assigned"] = requested
    if len(assignments) != requested:
        errors.append("manifest assignment count differs from requested episodes")
    try:
        planned_assignments = _assignments(
            TrajectorySmokeConfig.model_validate(config), asset_hash
        )
    except (ValidationError, ValueError) as exc:
        errors.append(f"manifest config cannot reproduce planned scenes: {exc}")
        return report
    if len(planned_assignments) != requested:
        errors.append("manifest requested episode count differs from planned scenes")
    if manifest.get("status") != "COMPLETE":
        errors.append("manifest is not COMPLETE")

    statuses: Counter[str] = Counter()
    safety_events: Counter[str] = Counter()
    physical_adapter = TypeAdapter(PhysicalSample)
    criteria = CompletionCriteria("object", "target_region")
    root_resolved = root.resolve()
    for expected_index, assignment in enumerate(assignments):
        prefix = f"episode {expected_index}"
        if not isinstance(assignment, dict) or assignment.get("index") != expected_index:
            errors.append(f"{prefix}: assignment index is missing or out of order")
            continue
        planned = (
            planned_assignments[expected_index]
            if expected_index < len(planned_assignments)
            else {}
        )
        if any(
            assignment.get(key) != planned.get(key)
            for key in (
                "case", "scene_source", "seed", "group_id", "scene_hash", "scene"
            )
        ):
            errors.append(f"{prefix}: planned scene assignment differs from manifest")
        relative_path = f"episodes/{expected_index:04d}/episode.json.gz"
        if assignment.get("episode_path") != relative_path:
            errors.append(f"{prefix}: episode path is missing or noncanonical")
            continue
        episode_path = root / relative_path
        if not episode_path.resolve().is_relative_to(root_resolved):
            errors.append(f"{prefix}: episode path escapes dataset root")
            continue
        try:
            compressed = episode_path.read_bytes()
            if hashlib.sha256(compressed).hexdigest() != assignment.get("sha256"):
                errors.append(f"{prefix}: episode SHA256 mismatch")
                continue
            payload = cast(dict[str, Any], json.loads(gzip.decompress(compressed)))
        except (OSError, ValueError, gzip.BadGzipFile) as exc:
            errors.append(f"{prefix}: episode unreadable: {exc}")
            continue
        report["published"] += 1
        if (
            payload.get("protocol_hash") != protocol_hash
            or payload.get("assignment_index") != expected_index
            or payload.get("case") != assignment.get("case")
            or payload.get("scene_source") != assignment.get("scene_source")
            or payload.get("group_id") != assignment.get("group_id")
            or payload.get("scene") != assignment.get("scene")
            or payload.get("source") != "GROUND_TRUTH_TEACHER"
        ):
            errors.append(f"{prefix}: protocol or scene identity mismatch")
            continue
        try:
            scene = SceneSpec.model_validate(payload["scene"])
        except (ValidationError, KeyError) as exc:
            errors.append(f"{prefix}: scene is invalid: {exc}")
            continue
        if (
            scene.scene_hash != assignment.get("scene_hash")
            or scene.group_id != assignment.get("group_id")
            or scene.asset_family_hash != asset_hash
        ):
            errors.append(f"{prefix}: scene hash or asset identity mismatch")
        try:
            frames = [TrajectoryFrame.model_validate(item) for item in payload["frames"]]
        except (ValidationError, KeyError, TypeError) as exc:
            errors.append(f"{prefix}: trajectory frame invalid: {exc}")
            continue
        for frame in frames:
            if (
                frame.observation.scene_id != scene.group_id
                or frame.next_observation.scene_id != scene.group_id
                or frame.action.details.get("physics_steps", 0) <= 0
                or frame.action.details.get("teacher_source") != "GROUND_TRUTH_TEACHER"
            ):
                errors.append(
                    f"{prefix}: trajectory frame source or executed-step evidence invalid"
                )
            if (
                "target_pose" in frame.action.details
                and frame.action.details.get("resolved_target_source") != "GROUND_TRUTH_TEACHER"
            ):
                errors.append(f"{prefix}: teacher target source is missing")
        for previous, current in zip(frames, frames[1:], strict=False):
            if (
                previous.next_observation.checksum_sha256
                != current.observation.checksum_sha256
                or previous.next_observation.frame_id != current.observation.frame_id
            ):
                errors.append(f"{prefix}: trajectory observation chain is broken")
        episode_ids = {
            episode_id
            for frame in frames
            for episode_id in (frame.observation.episode_id, frame.next_observation.episode_id)
        }
        if len(episode_ids) > 1:
            errors.append(f"{prefix}: trajectory spans multiple episodes")
        try:
            samples = [physical_adapter.validate_python(item)
                       for item in payload["physical_samples"]]
        except (ValidationError, KeyError, TypeError) as exc:
            errors.append(f"{prefix}: physical sample invalid: {exc}")
            continue
        if not samples or any(
            current.physics_step != previous.physics_step + 1
            or current.sim_time_s <= previous.sim_time_s
            or current.episode_id != previous.episode_id
            for previous, current in zip(samples, samples[1:], strict=False)
        ):
            errors.append(f"{prefix}: physical samples are not continuous")
            continue
        if episode_ids and episode_ids != {samples[0].episode_id}:
            errors.append(f"{prefix}: physical and image episode IDs differ")
        if frames and payload.get("outcome") is not None and not math.isclose(
            frames[-1].next_observation.sim_time_s, samples[-1].sim_time_s,
            rel_tol=0.0, abs_tol=1e-6,
        ):
            errors.append(f"{prefix}: final action and physics time are not aligned")
        outcome = payload.get("outcome")
        if outcome is not None and not isinstance(outcome, dict):
            errors.append(f"{prefix}: physical outcome is malformed")
            continue
        if outcome is not None:
            start_step = payload.get("evaluation_start_step")
            if not isinstance(start_step, int):
                errors.append(f"{prefix}: evaluation_start_step is missing")
                continue
            replayed = evaluate_evidence(
                samples, criteria, evaluation_start_step=start_step
            )
            if replayed.status == "INCOMPLETE" and replayed.failure_reason in {
                "NONCONTIGUOUS_EVIDENCE", "INVALID_PHYSICAL_EVIDENCE",
            }:
                errors.append(f"{prefix}: physical samples are not continuous or valid")
            if not _same_outcome(outcome, asdict(replayed)):
                errors.append(f"{prefix}: independent physical outcome replay mismatch")
            if payload.get("status") != replayed.status:
                errors.append(f"{prefix}: payload replay status mismatch")
            physical_success = replayed.success
        else:
            physical_success = False
            if payload.get("status") != "INFRASTRUCTURE_ERROR":
                errors.append(f"{prefix}: missing physical outcome outside infrastructure error")
        expected_verified = bool(physical_success and frames)
        if (
            payload.get("physical_success") != physical_success
            or payload.get("execution_verified") != expected_verified
            or assignment.get("physical_success") != physical_success
            or assignment.get("execution_verified") != expected_verified
            or assignment.get("status") != payload.get("status")
        ):
            errors.append(f"{prefix}: success/verified/status labels disagree with replay")
        statuses[str(payload.get("status"))] += 1
        safety_events.update(outcome.get("safety_events", []) if outcome else [])
        report["physical_success"] += int(physical_success)
        report["execution_verified"] += int(expected_verified)
        if expected_index == 0:
            report["control_positive_success"] = physical_success
        if expected_index == 1:
            report["control_negative_success"] = physical_success

    report["status_counts"] = dict(statuses)
    report["safety_event_counts"] = dict(safety_events)
    report["valid"] = not errors
    report["accepted"] = (
        report["valid"]
        and report["published"] == report["assigned"]
        and report["control_positive_success"]
        and report["control_negative_success"] is False
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = validate_trajectory_dataset(args.dataset)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
