"""Raw-sourced offline opportunities and recovery proofs, never online labels.

``pools`` contains ordinary pool lists plus optional ``_evidence`` metadata:
``history_roots`` (all prior dataset/run metadata trees), ``excluded_groups``,
``opportunity_sources`` (formal assignment ID -> raw bundle directory), and
``recovery_sources`` (recovery assignment ID -> ordered attempt directories).
No simulator runs in this module. Missing raw bundles produce INCOMPLETE.

Opportunity bundles contain capture.json, rgb.png, depth.npy, instances.npy.
Capture metadata records scene/group/episode/frame identities, object instance ID,
capture/submission simulation seconds, TCP position and a fixed MOVE_TCP action
(target_position_m, radius_m). Independently rendered instance IDs and actual
metric depth determine sensor sufficiency; scene distractors define obstacles.
This initial evaluator is scoped to straight TCP paths, not arbitrary arm motions.

Recovery bundles contain attempt.json (identities, recovery_start_step), backend
physical-observations.json (PhysicsStepObservation rows), fault-events.json
(backend TARGET_MOTION_STARTED/FINISHED records), teacher-actions.json (source,
action_type, start_step, end_step), and commands.json (backend command_records).
The generator archives failed attempts too. Only a measured disturbance followed
by a teacher action and independently successful, scoped-safe physics can count.
Offline proof counts are never online G4 performance measurements.
"""

from __future__ import annotations

import json
import math
import shutil
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any, Literal

import numpy as np
import yaml
from PIL import Image

from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec, canonical_json, content_digest
from cloud_edge_robot_arm.research.protocol import OpportunitySeed, file_hash
from cloud_edge_robot_arm.simulation.mujoco.backend import PhysicsStepObservation
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    evaluate_evidence,
    sample_physical_observation,
)

RULES_PATH = Path(__file__).resolve().parents[3] / "configs/research/recovery_faults.yaml"
OPPORTUNITY_FILES = ("capture.json", "rgb.png", "depth.npy", "instances.npy")
RECOVERY_FILES = (
    "attempt.json",
    "physical-observations.json",
    "fault-events.json",
    "teacher-actions.json",
    "commands.json",
)


def _read(path: Path) -> Any:
    return json.loads(path.read_text())


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n")


def _inside(directory: Path, relative: str) -> Path:
    candidate = (directory / relative).resolve()
    if not candidate.is_relative_to(directory.resolve()) or not candidate.is_file():
        raise ValueError("missing or escaping raw evidence path")
    return candidate


def _groups(value: Any) -> set[str]:
    if isinstance(value, dict):
        result = {value["group_id"]} if isinstance(value.get("group_id"), str) else set()
        for child in value.values():
            result.update(_groups(child))
        return result
    if isinstance(value, list):
        return set().union(*(_groups(child) for child in value)) if value else set()
    return {value} if isinstance(value, str) and value.startswith("g-") else set()


def _history(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    entries = []
    for root_name in metadata.get("history_roots", []):
        root = Path(root_name).resolve()
        if not root.exists():
            raise ValueError(f"missing previous-used source root: {root}")
        candidates = (
            [root]
            if root.is_file()
            else sorted(
                p for p in root.rglob("*") if p.suffix in {".json", ".jsonl"} and p.is_file()
            )
        )
        for path in candidates:
            if path.suffix == ".jsonl":
                value = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
            else:
                value = _read(path)
            groups = _groups(value)
            if groups:
                entries.append(
                    {
                        "source": str(path),
                        "source_hash": file_hash(path),
                        "groups": sorted(groups),
                        "value": value,
                    }
                )
    return entries


def _scene(row: dict[str, Any]) -> SceneSpec:
    scene = SceneSpec.model_validate(row["scene"])
    reconstructed = SceneSpec.from_parameters(
        scene.scene_parameters,
        scene.asset_family_hash,
        scene.seed,
    )
    if scene.group_id != reconstructed.group_id or row["scene_hash"] != scene.scene_hash:
        raise ValueError("scene/group source identity does not recompute")
    return scene


def _pool_check(pools: dict, excluded: set[str]) -> None:
    seen = set(excluded)
    ids = set()
    for name, rows in pools.items():
        if name.startswith("_"):
            continue
        if not isinstance(rows, list):
            raise ValueError("protocol pools must be assignment lists")
        for row in rows:
            scene = _scene(row)
            if scene.group_id in seen:
                raise ValueError("previous/excluded group or cross-pool group leakage")
            if row["assignment_id"] in ids:
                raise ValueError("duplicate pool assignment identity")
            if Path(row["assignment_id"]).name != row["assignment_id"]:
                raise ValueError("unsafe assignment identity")
            seen.add(scene.group_id)
            ids.add(row["assignment_id"])


def _vector(value: Any, length: int = 3) -> np.ndarray:
    result = np.asarray(value, dtype=float)
    if result.shape != (length,) or not np.isfinite(result).all():
        raise ValueError("invalid raw geometry vector")
    return result


def _eligible(row: dict[str, Any], rules: dict) -> bool:
    scene = _scene(row)
    for key in ("target", "destination"):
        position = _vector(scene.scene_parameters[key]["position"])
        extent = _vector(scene.scene_parameters[key]["half_size"])
        if (
            np.any(extent <= 0)
            or np.any(position - extent < rules["workspace_min_m"])
            or np.any(position + extent > rules["workspace_max_m"])
            or math.hypot(*position[:2]) + float(np.linalg.norm(extent[:2]))
            > rules["workspace_xy_radius_m"]
        ):
            return False
    return True


def _workspace(point: np.ndarray, radius: float, rules: dict) -> bool:
    return bool(
        np.all(point - radius >= rules["workspace_min_m"])
        and np.all(point + radius <= rules["workspace_max_m"])
        and math.hypot(*point[:2]) + radius <= rules["workspace_xy_radius_m"]
    )


def _intersects(start: np.ndarray, end: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> bool:
    minimum, maximum = 0.0, 1.0
    for axis in range(3):
        delta = end[axis] - start[axis]
        if abs(delta) < 1e-12:
            if not lo[axis] <= start[axis] <= hi[axis]:
                return False
        else:
            a, b = sorted(((lo[axis] - start[axis]) / delta, (hi[axis] - start[axis]) / delta))
            minimum, maximum = max(minimum, a), min(maximum, b)
            if minimum > maximum:
                return False
    return True


def _label(
    bundle: Path,
    row: dict,
    rules: dict,
) -> tuple[Literal["VALID", "INVALID", "UNKNOWN"], dict, dict]:
    capture = _read(bundle / "capture.json")
    scene = _scene(row)
    if capture["group_id"] != scene.group_id or capture["scene_hash"] != scene.scene_hash:
        raise ValueError("opportunity raw source identity mismatch")
    action = capture["action_spec"]
    if action["action_type"] != "MOVE_TCP":
        raise ValueError("unsupported candidate action geometry")
    start, end = _vector(capture["tcp_position_m"]), _vector(action["target_position_m"])
    radius = float(action["radius_m"])
    if not math.isfinite(radius) or not 0 < radius <= 0.1:
        raise ValueError("candidate path radius must be finite and positive")
    depth = np.load(bundle / "depth.npy", allow_pickle=False)
    instances = np.load(bundle / "instances.npy", allow_pickle=False)
    with Image.open(bundle / "rgb.png") as rgb:
        dimensions_match = (
            depth.ndim == 2
            and instances.shape == depth.shape
            and rgb.size == (depth.shape[1], depth.shape[0])
        )
        rgb.verify()
    if not dimensions_match or not np.issubdtype(instances.dtype, np.integer):
        raise ValueError("raw RGB-D/instance dimensions or identity encoding disagree")
    instance_id = capture["object_instance_id"]
    if type(instance_id) is not int or instance_id <= 0:
        raise ValueError("invalid raw object instance identity")
    mask = instances == instance_id
    pixels = int(mask.sum())
    valid = mask & np.isfinite(depth) & (depth > 0) & (depth < 10)
    fraction = int(valid.sum()) / pixels if pixels else 0.0
    sufficient = bool(
        capture.get("episode_id")
        and capture.get("frame_id")
        and pixels >= rules["minimum_object_pixels"]
        and fraction >= rules["minimum_valid_depth_fraction"]
    )
    geometry = _workspace(start, radius, rules) and _workspace(end, radius, rules)
    for obstacle in scene.scene_parameters["distractors"]:
        center = _vector(obstacle["position"])
        extent = _vector(obstacle["half_size"]) + radius
        geometry = geometry and not _intersects(start, end, center - extent, center + extent)
    captured, submitted = float(capture["captured_at_s"]), float(capture["submitted_at_s"])
    if not math.isfinite(captured + submitted) or captured < 0 or submitted < 0:
        raise ValueError("invalid raw opportunity timestamps")
    timely = 0 <= submitted - captured <= rules["opportunity_validity_s"]
    label: Literal["VALID", "INVALID", "UNKNOWN"] = (
        "UNKNOWN" if not sufficient else "VALID" if geometry and timely else "INVALID"
    )
    proof = {
        "rule_version": "rgbd.opportunity.v1",
        "sensor_and_identity_sufficient": sufficient,
        "geometry_safe": bool(geometry),
        "within_validity": timely,
        "object_pixels": pixels,
        "valid_depth_fraction": fraction,
        "age_s": submitted - captured,
        "raw_capture_path": "capture.json",
    }
    return label, proof, action


def _fault(index: int, rules: dict) -> dict:
    return {
        "fault_type": rules["fault_type"],
        "parameters": {
            "speed_m_s": rules["speed_m_s"],
            "duration_s": rules["duration_s"],
            "direction_y": rules["directions_y"][index % len(rules["directions_y"])],
        },
    }


def _observation(row: dict) -> PhysicsStepObservation:
    values = dict(row)
    # Dataclasses do not normalize JSON's lists; the evaluator compares tuple scopes.
    for field in fields(PhysicsStepObservation):
        value = values.get(field.name)
        if isinstance(value, list):
            values[field.name] = tuple(
                tuple(item) if isinstance(item, list) else item for item in value
            )
    observation = PhysicsStepObservation(**values)
    for name, length in {
        "object_position_m": 3,
        "object_geom_position_m": 3,
        "object_geom_rotation_row_major": 9,
        "object_half_extent_m": 3,
        "object_linear_velocity_m_s": 3,
        "object_angular_velocity_rad_s": 3,
        "region_center_m": 3,
        "region_half_extent_m": 3,
        "tcp_position_m": 3,
        "finger_positions_m": 2,
        "finger_velocities_m_s": 2,
        "joint_positions_rad": 7,
        "joint_velocities_rad_s": 7,
    }.items():
        _vector(getattr(observation, name), length)
    for name, count in (("joint_ranges_rad", 7), ("finger_ranges_m", 2)):
        ranges = np.asarray(getattr(observation, name), dtype=float)
        if (
            ranges.shape != (count, 2)
            or not np.isfinite(ranges).all()
            or np.any(ranges[:, 0] >= ranges[:, 1])
        ):
            raise ValueError("invalid raw physics joint/finger ranges")
    if any(
        not math.isfinite(distance) for _, _, distance in observation.self_collision_distances_m
    ):
        raise ValueError("nonfinite raw self-collision distances")
    if any(
        type(getattr(observation, key)) is not bool for key in ("estop_engaged", "gripper_open")
    ):
        raise ValueError("raw physics state flags must be strict booleans")
    for field in fields(observation):
        value = getattr(observation, field.name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not math.isfinite(value):
                raise ValueError("nonfinite raw physics state")
    return observation


def _recovery(bundle: Path, row: dict, fault: dict, rules: dict) -> tuple[list[dict], dict]:
    attempt = _read(bundle / "attempt.json")
    scene = _scene(row)
    if attempt["group_id"] != scene.group_id or attempt["scene_hash"] != scene.scene_hash:
        raise ValueError("recovery raw source identity mismatch")
    observations = [_observation(r) for r in _read(bundle / "physical-observations.json")]
    if not observations or any(r.episode_id != attempt["episode_id"] for r in observations):
        raise ValueError("missing or foreign raw recovery physics")
    target = scene.scene_parameters["target"]
    destination = scene.scene_parameters["destination"]
    if (
        not np.allclose(
            observations[0].object_position_m[:2], target["position"][:2], atol=0.005, rtol=0
        )
        or not np.allclose(
            observations[0].object_half_extent_m, target["half_size"], atol=1e-9, rtol=0
        )
        or any(
            not np.allclose(r.region_center_m, destination["position"], atol=1e-9, rtol=0)
            or not np.allclose(r.region_half_extent_m, destination["half_size"], atol=1e-9, rtol=0)
            for r in observations
        )
    ):
        raise ValueError("raw recovery geometry does not identify the assigned scene")
    if any(r.estop_engaged for r in observations):
        raise ValueError("teacher recovery contains emergency-stop state")
    events = _read(bundle / "fault-events.json")
    starts = [r for r in events if r.get("event") == "TARGET_MOTION_STARTED"]
    finishes = [r for r in events if r.get("event") == "TARGET_MOTION_FINISHED"]
    if len(starts) != 1 or len(finishes) != 1:
        raise ValueError("actual fault injection start/end evidence required")
    first, last = starts[0], finishes[0]
    params = fault["parameters"]
    if any(first.get(k) != v for k, v in params.items()) or first.get("mechanism") != (
        "external horizontal force with velocity feedback; no pose writes"
    ):
        raise ValueError("actual injection differs from preregistered fault")
    by_step = {r.physics_step: r for r in observations}
    start, finish = by_step[first["physics_step"]], by_step[last["physics_step"]]
    if (
        abs(start.sim_time_s - first["sim_time_s"]) > 1e-9
        or abs(finish.sim_time_s - last["sim_time_s"]) > 1e-9
        or finish.physics_step <= start.physics_step
    ):
        raise ValueError("fault injection timestamps do not align with physical evidence")
    duration = finish.sim_time_s - start.sim_time_s
    if last["reason"] == "scheduled_end":
        if abs(duration - params["duration_s"]) > 0.005:
            raise ValueError("fault injection duration differs from locked schedule")
    elif last["reason"] != "finger_contact" or duration > params["duration_s"] + 0.005:
        raise ValueError("unproved fault injection termination")
    displacement = (finish.object_position_m[1] - start.object_position_m[1]) * params[
        "direction_y"
    ]
    if displacement < rules["minimum_measured_displacement_m"]:
        raise ValueError("fault injection has no independently measured defect")
    recovery_start = by_step[attempt["recovery_start_step"]]
    if recovery_start.physics_step < finish.physics_step:
        raise ValueError("teacher recovery must start after measured fault interval")
    actions = _read(bundle / "teacher-actions.json")
    commands = _read(bundle / "commands.json")
    if not actions or any(
        r.get("source") != rules["teacher_source"]
        or not r.get("action_type")
        or not recovery_start.physics_step
        <= r["start_step"]
        < r["end_step"]
        <= observations[-1].physics_step
        for r in actions
    ):
        raise ValueError("missing executed post-fault teacher recovery actions")
    if not any(
        r.get("accepted") is True
        and r.get("type") in {"move_joints", "set_gripper"}
        and not r.get("after_emergency_stop")
        and recovery_start.sim_time_s <= r["sim_time_s"] <= observations[-1].sim_time_s
        for r in commands
    ):
        raise ValueError("teacher recovery lacks accepted post-fault actuator commands")
    criteria = CompletionCriteria("object", "target_region")
    samples = [sample_physical_observation(r, criteria) for r in observations]
    outcome = evaluate_evidence(
        samples, criteria, evaluation_start_step=recovery_start.physics_step
    )
    if observations[-1].sim_time_s - recovery_start.sim_time_s > rules["maximum_recovery_s"]:
        raise ValueError("teacher recovery exceeds preregistered recovery bound")
    if not outcome.success or outcome.safety_assessment != "SCOPED_NO_VIOLATION":
        raise ValueError(f"independent teacher recovery unsuccessful or unsafe: {outcome.status}")
    return [asdict(s) for s in samples], {
        "injection_start_s": start.sim_time_s,
        "injection_end_s": finish.sim_time_s,
        "measured_displacement_m": displacement,
        "recovery_start_s": recovery_start.sim_time_s,
        "independent_outcome": asdict(outcome),
    }


def _archive(source: Path, destination: Path, names: tuple[str, ...]) -> dict[str, str]:
    destination.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name in names:
        path = _inside(source, name)
        shutil.copyfile(path, destination / name)
        hashes[name] = file_hash(destination / name)
    return hashes


def prepare_protocol_evidence(pools: dict, output: Path) -> dict:
    """Archive ordered inputs; generate no successes when physical input is absent."""
    metadata = pools.get("_evidence", {})
    rules = yaml.safe_load(RULES_PATH.read_text())
    histories = _history(metadata)
    previous = set().union(*(set(r["groups"]) for r in histories)) if histories else set()
    excluded = set(metadata.get("excluded_groups", []))
    if not previous <= excluded:
        raise ValueError("all previous-used groups must be in the excluded registry")
    _pool_check(pools, excluded)
    clean_pools = {k: v for k, v in pools.items() if not k.startswith("_")}
    for row in clean_pools.get("recovery", []):
        if (
            len(metadata.get("recovery_sources", {}).get(row["assignment_id"], []))
            > (rules["maximum_attempts_per_group"])
        ):
            raise ValueError("recovery generation attempt bound exceeded")
    output.mkdir(parents=True, exist_ok=True)
    if any(
        (output / name).exists()
        for name in ("protocol-evidence.json", "opportunities.json", "recovery-faults.json")
    ):
        raise FileExistsError("protocol evidence is immutable; choose a fresh output")
    _write(output / "evidence-pools.json", clean_pools)
    _write(output / "excluded-groups.json", sorted(excluded))
    _write(output / "evidence-rules.json", rules)
    registry = []
    for index, history in enumerate(histories):
        relative = f"history/{index:06d}.json"
        _write(output / relative, history.pop("value"))
        registry.append(
            {**history, "archived_path": relative, "archived_hash": file_hash(output / relative)}
        )
    _write(
        output / "source-registry.json",
        {
            "history_roots": metadata.get("history_roots", []),
            "entries": registry,
            "excluded_groups_hash": content_digest(sorted(excluded)),
        },
    )
    opportunities: list[dict[str, Any]] = []
    missing_opportunities: list[str] = []
    attempts: list[dict[str, Any]] = []
    faults: list[dict[str, Any]] = []
    for row in clean_pools.get("formal", []):
        identity = row["assignment_id"]
        source = metadata.get("opportunity_sources", {}).get(identity)
        if source is None:
            missing_opportunities.append(identity)
            continue
        bundle = output / "raw" / identity / "opportunity"
        hashes = _archive(Path(source), bundle, OPPORTUNITY_FILES)
        label, proof, action = _label(bundle, row, rules)
        paths = {
            str((bundle / name).relative_to(output)): digest for name, digest in hashes.items()
        }
        seed = OpportunitySeed(
            opportunity_id=f"opportunity-{identity}",
            group_id=row["scene"]["group_id"],
            observation_hash=content_digest(paths),
            action_spec=action,
            oracle_label=label,
        )
        opportunities.append(
            {
                "seed": seed.model_dump(),
                "assignment_id": identity,
                "payload_hashes": paths,
                "independent_label_evidence": proof,
                "raw_bundle": str(bundle.relative_to(output)),
                "access_role": "offline_evaluation",
            }
        )
    for index, row in enumerate(clean_pools.get("recovery", [])):
        identity = row["assignment_id"]
        fault = _fault(index, rules)
        sources = metadata.get("recovery_sources", {}).get(identity, [])
        eligible = _eligible(row, rules)
        if not sources:
            attempts.append(
                {
                    "assignment_id": identity,
                    "attempt": 0,
                    "eligible": eligible,
                    "status": "INCOMPLETE" if eligible else "EXCLUDED",
                    "reason": "missing physical input",
                    "fault": fault,
                }
            )
        for number, source in enumerate(sources, start=1):
            bundle = output / "raw" / identity / f"attempt-{number}"
            entry = {
                "assignment_id": identity,
                "attempt": number,
                "eligible": eligible,
                "fault": fault,
                "raw_bundle": str(bundle.relative_to(output)),
            }
            try:
                hashes = _archive(Path(source), bundle, RECOVERY_FILES)
                entry["payload_hashes"] = hashes
                if not eligible:
                    raise ValueError("preregistered scene eligibility failed")
                samples, proof = _recovery(bundle, row, fault, rules)
                evidence = bundle / "physical-evidence.json"
                _write(evidence, samples)
                entry.update(status="PROVEN", reason=None)
                # Keep all attempts; first independently successful attempt is fixed.
                if not any(f["group_id"] == row["scene"]["group_id"] for f in faults):
                    faults.append(
                        {
                            "group_id": row["scene"]["group_id"],
                            "assignment_id": identity,
                            "fault": fault,
                            "recoverability_evidence_path": str(evidence.relative_to(output)),
                            "recoverability_evidence_hash": file_hash(evidence),
                            "raw_bundle": str(bundle.relative_to(output)),
                            "proof": proof,
                        }
                    )
            except (ValueError, KeyError, OSError, TypeError) as exc:
                entry.update(status="FAILED" if eligible else "EXCLUDED", reason=str(exc))
            attempts.append(entry)
    _write(output / "opportunities.json", opportunities)
    _write(output / "recovery-faults.json", faults)
    _write(output / "generation-attempts.json", attempts)
    _write(output / "missing-opportunities.json", missing_opportunities)
    # Bind all archived bytes including rejected and incomplete attempts.
    hashes = {
        str(p.relative_to(output)): file_hash(p)
        for p in sorted(output.rglob("*"))
        if p.is_file() and p.name != "protocol-evidence.json"
    }
    _write(
        output / "protocol-evidence.json",
        {
            "schema_version": "rgbd.protocol-evidence.v1",
            "payload_hashes": hashes,
            "offline_only": True,
            "required_recovery_groups": 200,
        },
    )
    return verify_protocol_evidence(output)


def verify_protocol_evidence(directory: Path) -> dict:
    """Recompute labels/injections/outcomes; summary booleans cannot pass the audit."""
    errors: list[str] = []
    opportunities, faults, proven = [], [], 0
    try:
        manifest = _read(directory / "protocol-evidence.json")
        if manifest.get("schema_version") != "rgbd.protocol-evidence.v1":
            raise ValueError("unsupported protocol evidence schema")
        for relative, digest in manifest["payload_hashes"].items():
            if file_hash(_inside(directory, relative)) != digest:
                errors.append(f"archived payload hash drift: {relative}")
        rules = _read(directory / "evidence-rules.json")
        if rules != yaml.safe_load(RULES_PATH.read_text()):
            raise ValueError("fault/eligibility rules differ from preregistered source")
        pools = _read(directory / "evidence-pools.json")
        excluded = set(_read(directory / "excluded-groups.json"))
        _pool_check(pools, excluded)
        registry = _read(directory / "source-registry.json")
        if registry["excluded_groups_hash"] != content_digest(sorted(excluded)):
            raise ValueError("source exclusion registry hash drift")
        for entry in registry["entries"]:
            path = _inside(directory, entry["archived_path"])
            if file_hash(path) != entry["archived_hash"] or _groups(_read(path)) != set(
                entry["groups"]
            ):
                raise ValueError("previous-used source archive does not reproduce")
            if not set(entry["groups"]) <= excluded:
                raise ValueError("previous-used source groups not fully excluded")
        formal = {r["assignment_id"]: r for r in pools.get("formal", [])}
        recovery = {r["assignment_id"]: (i, r) for i, r in enumerate(pools.get("recovery", []))}
        opportunities = _read(directory / "opportunities.json")
        seen = set()
        for item in opportunities:
            try:
                identity = item["assignment_id"]
                seed = OpportunitySeed.model_validate(item["seed"])
                if identity in seen or identity not in formal:
                    raise ValueError("duplicate/outside-formal opportunity identity")
                seen.add(identity)
                bundle = _inside(directory, item["raw_bundle"] + "/capture.json").parent
                label, proof, action = _label(bundle, formal[identity], rules)
                paths = {
                    str((bundle / name).relative_to(directory)): file_hash(bundle / name)
                    for name in OPPORTUNITY_FILES
                }
                if seed.group_id != formal[identity]["scene"]["group_id"] or (
                    seed.observation_hash != content_digest(paths)
                    or item["payload_hashes"] != paths
                ):
                    raise ValueError("opportunity source identity/hash mismatch")
                if (
                    seed.oracle_label != label
                    or item["independent_label_evidence"] != proof
                    or (seed.action_spec != action)
                ):
                    raise ValueError("opportunity label does not recompute from raw evidence")
            except (ValueError, KeyError, OSError, TypeError) as exc:
                errors.append(f"opportunity: {exc}")
        missing = _read(directory / "missing-opportunities.json")
        if set(missing) != set(formal) - seen:
            errors.append("missing opportunity denominator mismatch")
        attempts = _read(directory / "generation-attempts.json")
        for identity, (index, row) in recovery.items():
            entries = [a for a in attempts if a["assignment_id"] == identity]
            if not entries or len(entries) > rules["maximum_attempts_per_group"]:
                errors.append("missing recovery attempts or generation bound exceeded")
                continue
            for entry in entries:
                if entry["eligible"] != _eligible(row, rules) or entry["fault"] != _fault(
                    index, rules
                ):
                    errors.append("recovery eligibility/fixed fault does not reproduce")
                if entry.get("raw_bundle") and entry.get("payload_hashes"):
                    bundle = _inside(directory, entry["raw_bundle"] + "/attempt.json").parent
                    expected_hashes = {name: file_hash(bundle / name) for name in RECOVERY_FILES}
                    if entry["payload_hashes"] != expected_hashes:
                        errors.append("recovery attempt payload hash drift")
                    try:
                        _recovery(bundle, row, entry["fault"], rules)
                        status = "PROVEN" if _eligible(row, rules) else "EXCLUDED"
                    except (ValueError, KeyError, OSError, TypeError):
                        status = "FAILED" if _eligible(row, rules) else "EXCLUDED"
                    if entry["status"] != status:
                        errors.append("recovery attempt result does not independently reproduce")
        faults = _read(directory / "recovery-faults.json")
        seen_faults = set()
        for item in faults:
            try:
                identity = item["assignment_id"]
                index, row = recovery[identity]
                if identity in seen_faults or item["group_id"] != row["scene"]["group_id"]:
                    raise ValueError("duplicate/foreign recovery identity")
                seen_faults.add(identity)
                if item["fault"] != _fault(index, rules) or not _eligible(row, rules):
                    raise ValueError("recovery fault differs from locked eligibility/schedule")
                bundle = _inside(directory, item["raw_bundle"] + "/attempt.json").parent
                samples, proof = _recovery(bundle, row, item["fault"], rules)
                evidence = _inside(directory, item["recoverability_evidence_path"])
                if file_hash(evidence) != item["recoverability_evidence_hash"] or (
                    canonical_json(_read(evidence)) != canonical_json(samples)
                    or canonical_json(item["proof"]) != canonical_json(proof)
                ):
                    raise ValueError("independent recovery physics/proof does not recompute")
                if not any(
                    a["assignment_id"] == identity
                    and a["status"] == "PROVEN"
                    and a.get("raw_bundle") == item["raw_bundle"]
                    for a in attempts
                ):
                    raise ValueError("recovery proof lacks retained successful attempt")
                proven += 1
            except (ValueError, KeyError, OSError, TypeError) as exc:
                errors.append(f"recovery: {exc}")
        complete = bool(
            registry["history_roots"]
            and registry["entries"]
            and formal
            and not missing
            and len(recovery) == 200
            and proven == 200
        )
    except (ValueError, KeyError, OSError, TypeError) as exc:
        errors.append(f"protocol evidence: {exc}")
        complete = False
    status = "INVALID" if errors else "COMPLETE" if complete else "INCOMPLETE"
    return {
        "schema_version": "rgbd.protocol-evidence-audit.v1",
        "status": status,
        "valid": status == "COMPLETE",
        "integrity_valid": not errors,
        "required_recovery_groups": 200,
        "recovery_proven": proven,
        "opportunity_count": len(opportunities),
        "errors": errors,
        "offline_only": True,
        "g4_measured": False,
    }


def load_protocol_opportunities(directory: Path, *, consumer_role: str) -> list[dict]:
    """Only offline formal evaluators may access the truth-bearing manifest."""
    if consumer_role != "offline_evaluation":
        raise PermissionError("formal opportunity labels require offline_evaluation access")
    report = verify_protocol_evidence(directory)
    if not report["integrity_valid"]:
        raise ValueError("formal opportunity raw evidence failed independent verification")
    return [dict(row) for row in _read(directory / "opportunities.json")]
