"""Registered raw-source reconstruction; no risk, method or execution admission.

Inventories establish consistency against application-owned original files, not
cryptographic measurement authenticity or a full dynamics replay. Risk labels,
INITIAL, wall/simulation clock mapping, calibration and selection replay are
not implemented by this reader. RISK_SUPERVISION therefore remains UNKNOWN.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

import numpy as np

from cloud_edge_robot_arm.contracts import ActionResult
from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec, content_digest
from cloud_edge_robot_arm.research.protocol_evidence import COLLISION_SCOPE, _observation
from cloud_edge_robot_arm.simulation.mujoco.backend import PhysicsStepObservation
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    evaluate_evidence,
    sample_physical_observation,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker
from cloud_edge_robot_arm.vision.runtime_binding import RoleRuntimeBinding

Scope = Literal["RAW_EXECUTION", "RISK_SUPERVISION"]
Status = Literal["VALID", "INVALID", "UNKNOWN"]
Layout = Literal["CED_PILOT_RAW_V2", "MARKER_MOTION_DEVELOPMENT_RAW_V1"]
_MISSING_RISK = (
    "risk_label_source_unavailable",
    "initial_source_audit_unavailable",
    "clock_mapping_unavailable",
    "calibration_source_unavailable",
    "risk_selection_replay_unavailable",
)
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def required_source_paths() -> tuple[str, ...]:
    """Production helpers whose current bytes must match the owner registration."""
    return (
        "src/cloud_edge_robot_arm/research/risk_sources.py",
        "src/cloud_edge_robot_arm/research/protocol_evidence.py",
        "src/cloud_edge_robot_arm/datasets/rgbd/models.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/backend.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/episode_evaluator.py",
        "src/cloud_edge_robot_arm/vision/observations.py",
        "src/cloud_edge_robot_arm/vision/pose_markers.py",
        "src/cloud_edge_robot_arm/vision/runtime_binding.py",
        "src/cloud_edge_robot_arm/vision/role_models.py",
        "src/cloud_edge_robot_arm/contracts/models.py",
    )


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _copied(value: Any) -> Any:
    return _freeze(json.loads(json.dumps(_plain(value), allow_nan=False)))


def _relative(name: str) -> Path:
    path = Path(name)
    if not name or path.is_absolute() or ".." in path.parts or str(path) != name:
        raise ValueError("source relative path is invalid")
    return path


def _hashes(value: Mapping[str, str]) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError("source inventory must be a mapping")
    copied = dict(value)
    for name, digest in copied.items():
        _relative(name)
        if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
            raise ValueError("source checksum is invalid")
    return MappingProxyType(copied)


@dataclass(frozen=True)
class RawCaseRegistration:
    """One assigned original attempt; never inferred from surviving result rows."""

    case_id: str
    relative_directory: str
    layout: Layout
    original_file_hashes: Mapping[str, str]
    assignment: Mapping[str, Any]
    context: Mapping[str, Any]
    expected_counts: Mapping[str, int]
    source_kind: Literal["SOFTWARE_ONLY", "RECORDED_SIMULATION"] = "SOFTWARE_ONLY"
    marker_registration: PoseMarkerRegistration | None = None

    def __post_init__(self) -> None:
        if (
            not self.case_id
            or self.layout not in {"CED_PILOT_RAW_V2", "MARKER_MOTION_DEVELOPMENT_RAW_V1"}
            or self.source_kind not in {"SOFTWARE_ONLY", "RECORDED_SIMULATION"}
        ):
            raise ValueError("unsupported registered case identity/layout/source kind")
        _relative(self.relative_directory)
        object.__setattr__(self, "original_file_hashes", _hashes(self.original_file_hashes))
        for name in ("assignment", "context", "expected_counts"):
            value = getattr(self, name)
            if not isinstance(value, Mapping):
                raise ValueError(f"registered {name} must be a mapping")
            object.__setattr__(self, name, _copied(value))
        if set(self.expected_counts) != {"physics_steps", "commands", "actions", "frames"} or any(
            type(value) is not int or value < 0 for value in self.expected_counts.values()
        ):
            raise ValueError("registered raw counts must be nonnegative strict integers")


@dataclass(frozen=True)
class RiskSourceRegistration:
    artifact_root: Path
    source_root: Path
    current_source_hashes: Mapping[str, str]
    cases: Sequence[RawCaseRegistration]
    criteria: CompletionCriteria
    current_role_binding: RoleRuntimeBinding | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_root", Path(self.artifact_root))
        object.__setattr__(self, "source_root", Path(self.source_root))
        sources = _hashes(self.current_source_hashes)
        if not set(required_source_paths()) <= set(sources):
            raise ValueError("registration omits validating production helper sources")
        object.__setattr__(self, "current_source_hashes", sources)
        cases = tuple(replace(case) for case in self.cases)
        if (
            not cases
            or len({case.case_id for case in cases}) != len(cases)
            or (len({case.relative_directory for case in cases}) != len(cases))
        ):
            raise ValueError("registration requires distinct original assigned attempts")
        object.__setattr__(self, "cases", cases)
        object.__setattr__(self, "criteria", replace(self.criteria))
        binding = self.current_role_binding
        if binding is not None:
            # Reconstruct nested provider/source snapshots, not caller aliases.
            cloud = binding.bundle.cloud_snapshot
            copied_cloud = replace(cloud, source_hashes=dict(cloud.source_hashes))
            bundle = replace(binding.bundle, cloud_snapshot=copied_cloud)
            edge = binding.edge_snapshot
            copied_edge = replace(edge, source_hashes=dict(edge.source_hashes))
            object.__setattr__(
                self,
                "current_role_binding",
                RoleRuntimeBinding(
                    bundle,
                    copied_edge,
                    dict(binding.device_source_hashes),
                    _plain(binding.edge_policy),
                    root=binding.root,
                ),
            )


@dataclass(frozen=True)
class RiskSourceAudit:
    requested_scope: Scope
    verified_scope: Literal["RAW_EXECUTION"] | None
    status: Status
    reasons: tuple[str, ...]
    source_scope: Literal["SOFTWARE_ONLY", "RECORDED_SIMULATION_RAW_ONLY", "MIXED_RAW_ONLY"]
    counts: Mapping[str, int]
    case_results: tuple[Mapping[str, Any], ...]
    original_file_hashes: Mapping[str, str]
    current_source_hashes: Mapping[str, str]
    verified_original_file_hashes: Mapping[str, str] = field(default_factory=dict)
    formal_source_eligible: Literal[False] = False
    schema_version: Literal["ced.risk-source-audit.v1"] = "ced.risk-source-audit.v1"

    def __post_init__(self) -> None:
        for name in (
            "counts",
            "case_results",
            "original_file_hashes",
            "current_source_hashes",
            "verified_original_file_hashes",
        ):
            object.__setattr__(self, name, _copied(getattr(self, name)))
        if self.formal_source_eligible is not False:
            raise ValueError("raw audit never grants formal source eligibility")


def _safe(root: Path, name: str) -> Path:
    # Check root ancestors too: resolving first would hide a registered symlink.
    if any(part.is_symlink() for part in (root, *root.parents)):
        raise ValueError("registered root is symlinked")
    path = root / _relative(name)
    if any(part.is_symlink() for part in (path, *path.parents) if part.is_relative_to(root)):
        raise ValueError("registered payload is symlinked")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("registered payload escapes its root")
    return path


def _inventory(root: Path, expected: Mapping[str, str], *, complete: bool) -> dict[str, str]:
    actual = {}
    if complete:
        paths = sorted(root.rglob("*"))
        if any(path.is_symlink() for path in paths):
            raise ValueError("original inventory contains symlink")
        names = {str(path.relative_to(root)) for path in paths if path.is_file()}
        if names != set(expected):
            raise ValueError("original file inventory coverage changed")
    for name, digest in expected.items():
        payload = _safe(root, name).read_bytes()
        actual[name] = hashlib.sha256(payload).hexdigest()
        if actual[name] != digest:
            raise ValueError("registered original/source checksum changed")
    return actual


def _json(path: Path) -> Any:
    def reject(value: str) -> None:
        raise ValueError(f"nonfinite JSON constant: {value}")

    return json.loads(path.read_bytes(), parse_constant=reject)


def _rows(path: Path) -> list[dict[str, Any]]:
    rows = [_json_value(line) for line in path.read_bytes().splitlines() if line.strip()]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("raw JSONL rows must be objects")
    return rows


def _json_value(payload: bytes) -> Any:
    return json.loads(
        payload,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"nonfinite JSON constant: {value}")
        ),
    )


def _integer(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("raw step/count requires a strict nonnegative integer")
    return value


def _number(value: Any) -> float:
    if type(value) not in {int, float} or not math.isfinite(value):
        raise ValueError("raw finite numeric value required")
    return float(value)


def _physics(rows: Any, case: RawCaseRegistration) -> list[PhysicsStepObservation]:
    if not isinstance(rows, list) or not rows:
        raise ValueError("reset-complete raw physics array is required")
    keys = {field.name for field in fields(PhysicsStepObservation)}
    if any(not isinstance(row, dict) or set(row) != keys for row in rows):
        raise ValueError("raw physics object schema is incomplete or unknown")
    raw = [_observation(row) for row in rows]
    dt = _number(case.context["physics_dt_s"])
    episode = case.context["episode_id"]
    if not 0 < dt <= 0.005 or len(raw) != case.expected_counts["physics_steps"] + 1:
        raise ValueError("registered reset-terminal physics count/dt differs")
    for index, (row, item) in enumerate(zip(rows, raw, strict=True)):
        if (
            _integer(row["physics_step"]) != index
            or item.episode_id != episode
            or (abs(item.sim_time_s - index * dt) > 1e-9)
            or set((a, b) for a, b, _ in item.self_collision_distances_m) != set(COLLISION_SCOPE)
            or (len(item.self_collision_distances_m) != len(COLLISION_SCOPE))
        ):
            raise ValueError("raw reset/terminal/step/episode/collision coverage differs")
    if case.context.get("evaluation_start_step") != 120 or len(raw) <= 120:
        raise ValueError("registered collector evaluation start must be exactly120")
    return raw


def _reset(raw: Sequence[PhysicsStepObservation], case: RawCaseRegistration) -> SceneSpec:
    row = _plain(case.assignment)
    if case.layout == "CED_PILOT_RAW_V2" and "base_assignment" in row:
        row = row["base_assignment"]
        if not isinstance(row, dict):
            raise ValueError("CED base assignment shape is invalid")
    scene = SceneSpec.model_validate(row["scene"] if case.layout == "CED_PILOT_RAW_V2" else row)
    target = scene.scene_parameters["target"]
    destination = scene.scene_parameters["destination"]
    if (
        not np.allclose(raw[0].object_position_m, target["position"], atol=1e-9, rtol=0)
        or (not np.allclose(raw[0].object_half_extent_m, target["half_size"], atol=1e-9, rtol=0))
        or any(
            not np.allclose(item.region_center_m, destination["position"], atol=1e-9, rtol=0)
            or not np.allclose(
                item.region_half_extent_m, destination["half_size"], atol=1e-9, rtol=0
            )
            for item in raw
        )
    ):
        raise ValueError("raw reset/full scene geometry mismatch")
    return scene


def _controls(
    commands: Any, controls: Any, raw: Sequence[PhysicsStepObservation], case: RawCaseRegistration
) -> None:
    if (
        not isinstance(commands, list)
        or not isinstance(controls, list)
        or (len(commands) != case.expected_counts["commands"] or len(controls) != len(raw) - 1)
        or any(not isinstance(row, dict) for row in [*commands, *controls])
    ):
        raise ValueError("command/actuator coverage or shape differs")
    if [_integer(row["command_seq"]) for row in commands] != list(range(1, len(commands) + 1)):
        raise ValueError("raw command prefix is incomplete")
    initial = case.context["initial_controller_targets"]
    targets, fingers = np.asarray(initial["joints_rad"]), np.asarray(initial["fingers_m"])
    if (
        targets.shape != (7,)
        or fingers.shape != (2,)
        or not np.isfinite(targets).all()
        or (
            not np.isfinite(fingers).all()
            or case.context["actuator_delay_steps"] != 0
            or not np.allclose(targets, [-0.8, 0, 0, 0, 0, 0, 0], atol=1e-9, rtol=0)
            or not np.allclose(fingers, [0.039, 0.039], atol=1e-9, rtol=0)
            or not np.allclose(targets, raw[0].joint_positions_rad, atol=1e-9, rtol=0)
            or not np.allclose(raw[0].finger_positions_m, [0.04, 0.04], atol=1e-9, rtol=0)
        )
    ):
        raise ValueError("unsupported initial controller state/delay")
    previous = -1
    for command in commands:
        step = _integer(command["physics_step"])
        if (
            step < previous
            or step >= len(raw)
            or command["episode_id"] != raw[0].episode_id
            or (abs(_number(command["sim_time_s"]) - raw[step].sim_time_s) > 1e-9)
            or command.get("type") not in {"joint_target", "hold_current_joints", "gripper"}
            or (type(command.get("accepted")) is not bool)
        ):
            raise ValueError("command source/time/semantics differ")
        previous = step
    cursor = 0
    for index, control in enumerate(controls, start=1):
        if _integer(control["physics_step"]) != index or (
            control["episode_id"] != raw[0].episode_id
            or abs(_number(control["sim_time_s"]) - raw[index - 1].sim_time_s) > 1e-9
        ):
            raise ValueError("pre-step actuator identity/time differs")
        while cursor < len(commands) and commands[cursor]["physics_step"] < index:
            command = commands[cursor]
            if command["accepted"]:
                if command["type"] == "gripper":
                    if type(command["target_open"]) is not bool:
                        raise ValueError("gripper command must be a strict boolean")
                    fingers = np.full(2, 0.039 if command["target_open"] else 0.0)
                else:
                    requested = np.asarray(command["target_positions_rad"], dtype=float)
                    applied = np.asarray(command["applied_target_positions_rad"], dtype=float)
                    if (
                        requested.shape != (7,)
                        or not np.isfinite(requested).all()
                        or (not np.array_equal(applied, np.clip(requested, -2.8, 2.8)))
                    ):
                        raise ValueError("accepted joint target does not reproduce")
                    targets = applied
            cursor += 1
        q, gains, ranges, bias, actual = (
            np.asarray(control[key], dtype=float)
            for key in (
                "pre_joint_positions_rad",
                "actuator_gains",
                "actuator_ctrl_ranges",
                "pre_gravity_bias_nm",
                "control_rad",
            )
        )
        if any(v.shape != (7,) or not np.isfinite(v).all() for v in (q, gains, bias, actual)) or (
            ranges.shape != (7, 2)
            or not np.isfinite(ranges).all()
            or np.any(gains <= 0)
            or np.any(ranges[:, 0] >= ranges[:, 1])
        ):
            raise ValueError("controller vectors/gains/ranges differ")
        expected = np.clip(
            q + np.clip(targets - q, -0.10, 0.10) + bias / gains, ranges[:, 0], ranges[:, 1]
        )
        if not np.allclose(q, raw[index - 1].joint_positions_rad, atol=1e-9, rtol=0) or (
            not np.allclose(actual, expected, atol=1e-9, rtol=0)
            or not np.allclose(control["applied_joint_targets_rad"], targets, atol=1e-9, rtol=0)
            or not np.allclose(control["finger_control_targets_m"], fingers, atol=1e-9, rtol=0)
        ):
            raise ValueError("controller outputs do not reproduce actual command/physical state")
    if cursor != len(commands):
        raise ValueError("terminal command has no applied actuator step")


def _actions(
    rows: Any,
    commands: Sequence[Mapping[str, Any]],
    raw: Sequence[PhysicsStepObservation],
    case: RawCaseRegistration,
) -> None:
    if (
        not isinstance(rows, list)
        or len(rows) != case.expected_counts["actions"]
        or any(not isinstance(row, dict) for row in rows)
    ):
        raise ValueError("raw action coverage/shape differs")
    ids = set()
    step_cursor, seq_cursor = 120, 1
    for row in rows:
        result = ActionResult.model_validate(row["result"])
        start, end = _integer(row["start_step"]), _integer(row["end_step"])
        first, last = _integer(row["command_seq_start"]), _integer(row["command_seq_end"])
        if (
            result.action_id in ids
            or row["episode_id"] != raw[0].episode_id
            or (
                start != step_cursor
                or first != seq_cursor
                or not start < end < len(raw)
                or not first <= last <= len(commands) + 1
                or result.finished_at <= result.started_at
            )
        ):
            raise ValueError("action identity/range/prefix differs")
        for command in commands[first - 1 : last - 1]:
            step = command["physics_step"]
            if not start <= step <= end or (
                step == end and command["type"] != "hold_current_joints"
            ):
                raise ValueError("action commands lie outside its raw interval")
        ids.add(result.action_id)
        step_cursor, seq_cursor = end, last
    if rows and (step_cursor != len(raw) - 1 or seq_cursor != len(commands) + 1):
        raise ValueError("action terminal/command tail is incomplete")


def _frames(
    directory: Path,
    raw: Sequence[PhysicsStepObservation],
    scene: SceneSpec,
    case: RawCaseRegistration,
    action_rows: Sequence[Mapping[str, Any]],
) -> tuple[int, int]:
    observations: dict[str, RGBDObservation] = {}
    marker_unknown = 0
    for folder in ("frames", "supervision-frames", "raw-frames"):
        base = directory / folder
        if not base.exists():
            continue
        for path in sorted(base.iterdir()):
            if not path.is_dir():
                raise ValueError("registered frame layout differs")
            metadata = _json(path / "observation.json")
            if not isinstance(metadata, dict):
                raise ValueError("observation metadata shape differs")
            values = {key: metadata[key] for key in RGBDObservation.model_fields if key in metadata}
            values.update(
                rgb_png_base64=base64.b64encode((path / "rgb.png").read_bytes()).decode(),
                depth_float32_base64=base64.b64encode((path / "depth.f32").read_bytes()).decode(),
            )
            observation = RGBDObservation.model_validate(values)
            if (
                observation.episode_id != raw[0].episode_id
                or observation.scene_id != scene.group_id
            ):
                raise ValueError("frame episode/scene identity differs")
            if not any(abs(item.sim_time_s - observation.sim_time_s) <= 1e-9 for item in raw):
                raise ValueError("frame has no exact raw physics time")
            if any(
                metadata.get(key) != observation.evidence()[key]
                for key in ("rgb_sha256", "depth_sha256", "checksum_sha256")
            ):
                raise ValueError("original frame bytes/checksums differ")
            if (path / "observation-full.json").exists() and (
                RGBDObservation.model_validate_json((path / "observation-full.json").read_bytes())
                != observation
            ):
                raise ValueError("embedded and original external RGBD bytes differ")
            if (path / "valid_mask.u8").exists() and (
                (path / "valid_mask.u8").read_bytes() != observation.valid_mask_bytes()
            ):
                raise ValueError("frame valid mask bytes differ")
            existing = observations.get(observation.observation_id)
            if existing is not None:
                if existing != observation:
                    raise ValueError("duplicate frame identity has different original bytes")
                continue
            observations[observation.observation_id] = observation
            if case.marker_registration is not None:
                estimate = detect_pose_marker(observation, case.marker_registration)
                marker_unknown += estimate.status == "UNKNOWN"
                saved = _json(path / "marker-estimate.json")
                expected = asdict(estimate)
                expected["captured_at"] = estimate.captured_at.isoformat()
                if content_digest(saved) != content_digest(expected):
                    raise ValueError("marker decoder result does not reproduce")
    if len(observations) != case.expected_counts["frames"]:
        raise ValueError("registered frame count differs")
    if case.layout == "MARKER_MOTION_DEVELOPMENT_RAW_V1" and action_rows:
        expected_times = sorted(
            [raw[120].sim_time_s, *[raw[row["end_step"]].sim_time_s for row in action_rows]]
        )
        actual_times = sorted(observation.sim_time_s for observation in observations.values())
        if len(actual_times) != len(expected_times) or any(
            abs(actual - expected) > 1e-9
            for actual, expected in zip(actual_times, expected_times, strict=True)
        ):
            raise ValueError("marker frames do not cover every original action boundary")
    return len(observations), marker_unknown


def _case(
    directory: Path, case: RawCaseRegistration, registration: RiskSourceRegistration
) -> Mapping[str, Any]:
    if case.layout == "CED_PILOT_RAW_V2":
        context = _json(directory / "context.json")
        if (
            not isinstance(context, dict)
            or context != _plain(case.context)
            or (context.get("schema_version") != "rgbd.raw-episode.v2")
        ):
            raise ValueError("CED collector header differs from registered original/schema")
        raw = _physics(_json(directory / "physical-observations.json"), case)
        assignment = _plain(case.assignment)
        base_assignment = assignment.get("base_assignment", assignment)
        if "base_assignment" in assignment and (
            context.get("pilot_assignment_hash") != content_digest(assignment)
        ):
            raise ValueError("CED full paired assignment identity differs")
        if context.get("assignment_hash") != content_digest(base_assignment) or (
            context.get("reset_step") != 0
            or context.get("reset_sim_time_s") != 0
            or context.get("terminal_step") != len(raw) - 1
            or abs(_number(context["terminal_sim_time_s"]) - raw[-1].sim_time_s) > 1e-9
            or context.get("reset_observation_hash") != content_digest(asdict(raw[0]))
            or context.get("terminal_observation_hash") != content_digest(asdict(raw[-1]))
        ):
            raise ValueError("CED reset/terminal/assignment header does not reproduce")
        controls = _json(directory / "actuator-steps.json")
        actions = (
            _json(directory / "raw-actions.json")
            if (directory / "raw-actions.json").exists()
            else []
        )
    else:
        raw = _physics(_rows(directory / "raw-physics.jsonl"), case)
        controls = _rows(directory / "raw-actuators.jsonl")
        actions = _rows(directory / "raw-actions.jsonl")
    scene = _reset(raw, case)
    if case.layout == "CED_PILOT_RAW_V2" and (
        context.get("group_id") != scene.group_id or context.get("scene_hash") != scene.scene_hash
    ):
        raise ValueError("CED full scene/source identity differs")
    binding = registration.current_role_binding
    if case.source_kind == "RECORDED_SIMULATION" and case.layout == "CED_PILOT_RAW_V2":
        if "base_assignment" not in case.assignment:
            raise FileNotFoundError("actual_full_paired_assignment_unavailable")
        if binding is None:
            raise FileNotFoundError("actual_current_role_binding_unavailable")
        binding._validate_sources(binding.bundle.cloud_snapshot.source_hashes)
        binding._validate_sources(binding.edge_snapshot.source_hashes)
        binding._validate_sources(binding.device_source_hashes)
        if case.context.get("role_bundle_hash") != binding.bundle.digest():
            raise ValueError("CED current role bundle differs from original raw context")
    if case.source_kind == "RECORDED_SIMULATION" and (
        scene.asset_family_hash not in registration.current_source_hashes.values()
    ):
        raise FileNotFoundError("current_registered_asset_source_unavailable")
    if case.marker_registration is not None and (
        scene.asset_family_hash != case.marker_registration.marked_asset_sha256
        or case.marker_registration.marked_asset_sha256
        not in registration.current_source_hashes.values()
    ):
        raise ValueError("marker registration/current asset differs")
    commands = _json(directory / "commands.json")
    if (
        case.layout == "CED_PILOT_RAW_V2"
        and commands
        and not (directory / "raw-actions.json").exists()
    ):
        raise FileNotFoundError("CED_raw_action_ranges_unavailable")
    _controls(commands, controls, raw, case)
    _actions(actions, commands, raw, case)
    if case.layout == "MARKER_MOTION_DEVELOPMENT_RAW_V1":
        declared_actions = _json(directory / "actions.json")
        unframed = _json(directory / "unframed-actions.json")
        if declared_actions != [row["result"] for row in actions] or unframed != []:
            raise ValueError("marker declared actions/unframed scope differs from original ranges")
    samples = [sample_physical_observation(item, registration.criteria) for item in raw]
    outcome = asdict(evaluate_evidence(samples, registration.criteria, evaluation_start_step=120))
    samples_path = directory / "physical-samples.json"
    if samples_path.exists() and content_digest(_json(samples_path)) != content_digest(
        [asdict(item) for item in samples]
    ):
        raise ValueError("physical summary samples do not reproduce raw snapshots")
    summary_path = directory / "summary.json"
    if summary_path.exists():
        summary = _json(summary_path)
        if not isinstance(summary, dict) or not isinstance(summary.get("outcome"), dict):
            raise ValueError("physical outcome summary shape is invalid")
        if content_digest(summary["outcome"]) != content_digest(outcome):
            raise ValueError("physical outcome summary does not reproduce raw snapshots")
    frame_count, marker_unknown = _frames(directory, raw, scene, case, actions)
    return {
        "case_id": case.case_id,
        "status": "VALID",
        "layout": case.layout,
        "source_kind": case.source_kind,
        "physics_steps": len(raw) - 1,
        "commands": len(commands),
        "actions": len(actions),
        "frames": frame_count,
        "marker_unknown_frames": marker_unknown,
        "physical_outcome": _plain(outcome),
        "group_id": scene.group_id,
        "scene_hash": scene.scene_hash,
        "formal_source_eligible": False,
    }


class RiskSourceAuditor:
    """Reread original source inventories on every audit; never consume receipts."""

    def __init__(self, registrations: Mapping[str, RiskSourceRegistration]) -> None:
        self._registrations = MappingProxyType(
            {name: replace(registration) for name, registration in registrations.items()}
        )

    def audit(self, evidence_id: str, *, scope: Scope = "RISK_SUPERVISION") -> RiskSourceAudit:
        if scope not in {"RAW_EXECUTION", "RISK_SUPERVISION"}:
            raise ValueError("unsupported risk source audit scope")
        registration = self._registrations.get(evidence_id)
        counts = {
            "allocated": 0,
            "reconstructed": 0,
            "failed": 0,
            "physical_success": 0,
            "unknown": 0,
        }
        reasons: list[str] = []
        results: list[Mapping[str, Any]] = []
        originals: dict[str, str] = {}
        verified_originals: dict[str, str] = {}
        sources: dict[str, str] = {}
        status: Status = "UNKNOWN"
        verified: Literal["RAW_EXECUTION"] | None = None
        source_scope: Literal["SOFTWARE_ONLY", "RECORDED_SIMULATION_RAW_ONLY", "MIXED_RAW_ONLY"] = (
            "SOFTWARE_ONLY"
        )
        if registration is None:
            reasons.append("evidence_id_not_registered")
        else:
            counts["allocated"] = len(registration.cases)
            # Bind missing/invalid originals too; these are expected registration
            # digests, separately distinguished from successfully reread bytes.
            originals = {
                f"{case.case_id}/{name}": digest
                for case in registration.cases
                for name, digest in case.original_file_hashes.items()
            }
            kinds = {case.source_kind for case in registration.cases}
            if kinds == {"RECORDED_SIMULATION"}:
                source_scope = "RECORDED_SIMULATION_RAW_ONLY"
            elif len(kinds) > 1:
                source_scope = "MIXED_RAW_ONLY"
            try:
                sources = _inventory(
                    registration.source_root, registration.current_source_hashes, complete=False
                )
            except (ValueError, OSError) as error:
                status = "INVALID" if isinstance(error, ValueError) else "UNKNOWN"
                reasons.append(f"current_source_invalid:{error}")
                counts["unknown"] = counts["allocated"]
            else:
                statuses: list[Status] = []
                for case in registration.cases:
                    try:
                        directory = _safe(registration.artifact_root, case.relative_directory)
                        if not directory.is_dir():
                            raise FileNotFoundError("assigned_original_attempt_unavailable")
                        before = _inventory(directory, case.original_file_hashes, complete=True)
                        result = _case(directory, case, registration)
                        after = _inventory(directory, case.original_file_hashes, complete=True)
                        if after != before:
                            raise ValueError("original source changed during audit")
                        verified_originals.update(
                            {f"{case.case_id}/{name}": digest for name, digest in before.items()}
                        )
                        results.append(result)
                        counts["reconstructed"] += 1
                        success = result["physical_outcome"]["success"]
                        counts["physical_success"] += bool(success)
                        counts["failed"] += not success
                        statuses.append("VALID")
                    except (ValueError, TypeError, KeyError, IndexError) as error:
                        statuses.append("INVALID")
                        counts["unknown"] += 1
                        results.append(
                            {
                                "case_id": case.case_id,
                                "status": "INVALID",
                                "reason": str(error),
                                "formal_source_eligible": False,
                            }
                        )
                        reasons.append(f"{case.case_id}:invalid:{error}")
                    except OSError as error:
                        statuses.append("UNKNOWN")
                        counts["unknown"] += 1
                        results.append(
                            {
                                "case_id": case.case_id,
                                "status": "UNKNOWN",
                                "reason": str(error),
                                "formal_source_eligible": False,
                            }
                        )
                        reasons.append(f"{case.case_id}:unavailable:{error}")
                try:
                    if (
                        _inventory(
                            registration.source_root,
                            registration.current_source_hashes,
                            complete=False,
                        )
                        != sources
                    ):
                        raise ValueError("production source changed during audit")
                except (ValueError, OSError) as error:
                    statuses.append("INVALID")
                    reasons.append(f"current_source_changed:{error}")
                status = (
                    "INVALID"
                    if "INVALID" in statuses
                    else ("UNKNOWN" if "UNKNOWN" in statuses else "VALID")
                )
                verified = "RAW_EXECUTION" if status == "VALID" else None
        if scope == "RISK_SUPERVISION":
            if status != "INVALID":
                status = "UNKNOWN"
            reasons.extend(_MISSING_RISK)
        return RiskSourceAudit(
            scope,
            verified,
            status,
            tuple(reasons),
            source_scope,
            counts,
            tuple(results),
            originals,
            sources,
            verified_originals,
        )
