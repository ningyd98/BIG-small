"""Fail-closed formal evidence from calibrated pixels and complete backend traces.

Normal isolated pool assignment lists plus ``_evidence`` metadata are accepted.
Metadata contains ``protocol_version`` (default ced.research.v2), all prior
``history_roots``, complete ``excluded_groups``, formal ``opportunity_sources``
and ordered recovery ``recovery_sources`` (at most five attempts per group).
A partial pool remains INCOMPLETE. v2 requires selection/foundation/power 120
apiece, formal 2400, recovery 200 and OOD 300, canonical ordinal IDs/strata,
full assignment hashes and the fixed candidate schedule. v1 is diagnostic only.

Opportunity bundles contain capture.json, rgb.png, depth.npy and instances.npy;
old uncalibrated bundles receive UNKNOWN and cannot complete evidence. Formal
applicability additionally requires observation.json (existing RGBDObservation,
320x240 optical-z little-endian float32), context.json (rgbd.raw-episode.v2),
physical-observations.json, candidate-actions.json, commands.json and
actuator-provenance.json. Capture metadata binds full assignment, raw physics
step/hash, render state (time/qpos/qvel/act/ctrl), all three identical render-pass
hashes, assigned calibration, original geom-ID-to-name mapping and the fixed
candidate. Pixels/depth must locate object_geom in the recorded oriented box.
Only a bounded MOVE_TCP candidate with complete recorded arm execution and the
backend's exact full reference collision scope can produce VALID or INVALID.
Unverifiable context or applicability remains UNKNOWN/INCOMPLETE.

Recovery bundles contain attempt.json, raw physical-observations.json,
fault-events.json, teacher-actions.json, commands.json and actuator-provenance.json.
Raw physics must cover reset step/time0 through the separately bound terminal,
with every step present. Typed actual action results/command-sequence ranges join
original backend dispatch records and targets to every pre-step actuator output.
Actual motion fault start/end and measured displacement precede the supported T5
teacher sequence. Independent success and scoped safety are reconstructed, never
inferred from action markers. ``write_recovery_source`` adapts detached parent
observer hooks without executing simulation. Failure/exclusion/incomplete source
attempts remain hash-bound; only the first successful ordinal may be selected.

API/CLI roles protect label consumers; arbitrary filesystem readers still need
orchestration isolation. Source-role freezing must bind the manifest externally:
self-reported hashes establish byte integrity, not measurement authenticity.
This module runs no physical/model/cloud experiments and reports no online G4.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import shutil
import struct
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any, Literal

import numpy as np
import yaml

from cloud_edge_robot_arm.contracts import ActionResult
from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec, canonical_json, content_digest
from cloud_edge_robot_arm.research.protocol import STRATA, OpportunitySeed, file_hash
from cloud_edge_robot_arm.simulation.mujoco.backend import PhysicsStepObservation
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    evaluate_evidence,
    sample_physical_observation,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation

RULES_PATH = Path(__file__).resolve().parents[3] / "configs/research/recovery_faults.yaml"
OPPORTUNITY_FILES = ("capture.json", "rgb.png", "depth.npy", "instances.npy")
OPPORTUNITY_CONTEXT_FILES = (
    "observation.json",
    "context.json",
    "physical-observations.json",
    "candidate-actions.json",
    "commands.json",
    "actuator-provenance.json",
)
POOL_SIZES_V1 = {"foundation": 120, "power": 120, "formal": 2400, "recovery": 200, "ood": 300}
POOL_SIZES_V2 = {**POOL_SIZES_V1, "selection": 120}
ARM_GEOMS = ("base", "link1", "link2", "link3", "link4", "link5", "link6", "hand")
COLLISION_SCOPE = tuple(
    (a, b) for i, a in enumerate(ARM_GEOMS) for b in ARM_GEOMS[i + 2 :]
) + tuple((a, b) for a in ARM_GEOMS[:6] for b in ("left_finger_geom", "right_finger_geom"))
TEACHER_SEQUENCE = (
    "MOVE_ABOVE",
    "APPROACH",
    "GRASP",
    "LIFT",
    "OBSERVE",
    "MOVE_TO_REGION",
    "PLACE",
    "RELEASE",
    "OBSERVE",
)
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
RECOVERY_FILES = (
    "attempt.json",
    "physical-observations.json",
    "fault-events.json",
    "teacher-actions.json",
    "commands.json",
    "actuator-provenance.json",
)


def _nonstandard_number(value: str) -> Any:
    raise ValueError(f"nonfinite/nonstandard JSON number: {value}")


def _read(path: Path) -> Any:
    return json.loads(path.read_text(), parse_constant=_nonstandard_number)


def _write(path: Path, value: Any) -> None:
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("symlink destination is forbidden")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        stream.write(canonical_json(value) + "\n")


def _inside(directory: Path, relative: str) -> Path:
    requested = directory / relative
    if (
        Path(relative).is_absolute()
        or ".." in Path(relative).parts
        or any(parent.is_symlink() for parent in (requested, *requested.parents))
    ):
        raise ValueError("symlink or escaping raw evidence path")
    candidate = requested.resolve()
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
                value = [
                    json.loads(line, parse_constant=_nonstandard_number)
                    for line in path.read_text().splitlines()
                    if line.strip()
                ]
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
    ids: set[str] = set()
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
            if not isinstance(row["assignment_id"], str) or not SAFE_ID.fullmatch(
                row["assignment_id"]
            ):
                raise ValueError("unsafe assignment identity")
            ordinal = len([identity for identity in ids if identity.startswith(name + "-")])
            if (
                row["assignment_id"] != f"{name}-{ordinal + 1:04d}"
                or row.get("stratum_id") != STRATA[ordinal % len(STRATA)]
            ):
                raise ValueError("assignment identity/stratum differs from locked ordinal")
            allowed = {
                "movement_speed_m_s": (0.0, 0.02, 0.04),
                "noise_m": (0.0, 0.002, 0.005),
                "invalid_fraction": (0.0, 0.1, 0.3),
                "occlusion_fraction": (0.0, 0.2, 0.4),
            }
            perturbation = row.get("perturbation", {})
            if set(perturbation) != set(allowed) or any(
                type(perturbation[k]) not in (int, float) or perturbation[k] not in values
                for k, values in allowed.items()
            ):
                raise ValueError("assignment perturbations do not match locked protocol")
            seen.add(scene.group_id)
            ids.add(row["assignment_id"])
        if rows:
            for stratum in STRATA:
                layer = [row for row in rows if row["stratum_id"] == stratum]
                if len(layer) < 3:
                    continue
                for parameter, choices in allowed.items():
                    prefix = [row["perturbation"][parameter] for row in layer[:3]]
                    if set(prefix) != set(choices) or any(
                        row["perturbation"][parameter] != prefix[index % 3]
                        for index, row in enumerate(layer)
                    ):
                        raise ValueError("locked balanced perturbation cycle differs")


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


def _candidate(row: dict) -> dict:
    target = _scene(row).scene_parameters["target"]["position"]
    return {
        "candidate_id": f"candidate-{row['assignment_id']}",
        "action_type": "MOVE_TCP",
        "object_id": "object",
        "target_position_m": [target[0], target[1], 0.16],
        "radius_m": 0.02,
        "timeout_s": 8.0,
    }


def _lock(pools: dict, version: str) -> dict:
    if version not in {"rgbd.research.v1", "ced.research.v2"}:
        raise ValueError("unsupported explicit protocol version")
    sizes = POOL_SIZES_V2 if version == "ced.research.v2" else POOL_SIZES_V1
    if set(pools) - set(sizes):
        raise ValueError("unknown protocol pool names")
    return {
        "schema_version": "rgbd.pool-lock.v2",
        "protocol_version": version,
        "required_pool_sizes": sizes,
        "assignments": {
            name: {row["assignment_id"]: content_digest(row) for row in rows}
            for name, rows in pools.items()
        },
        "candidates": {row["assignment_id"]: _candidate(row) for row in pools.get("formal", [])},
    }


def _topology_complete(pools: dict, version: str) -> bool:
    sizes = POOL_SIZES_V2 if version == "ced.research.v2" else POOL_SIZES_V1
    return set(pools) == set(sizes) and all(
        len(pools[name]) == count
        and [row["assignment_id"] for row in pools[name]]
        == [f"{name}-{i + 1:04d}" for i in range(count)]
        for name, count in sizes.items()
    )


def _camera_rotation(quaternion: Any) -> np.ndarray:
    w, x, y, z = _vector(quaternion, 4)
    if abs(w * w + x * x + y * y + z * z - 1) > 1e-6:
        raise ValueError("invalid assigned camera quaternion")
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def _render_hash(state: dict) -> str:
    time = _finite(state["time_s"])
    digest = hashlib.sha256(struct.pack("<d", time))
    for name in ("qpos", "qvel", "act", "ctrl"):
        values = np.asarray(state[name], dtype="<f8")
        if values.ndim != 1 or not np.isfinite(values).all():
            raise ValueError("invalid capture raw physics arrays")
        digest.update(struct.pack("<I", values.size))
        digest.update(values.tobytes())
    return digest.hexdigest()


def _label(
    bundle: Path, row: dict, rules: dict
) -> tuple[Literal["VALID", "INVALID", "UNKNOWN"], dict, dict]:
    capture = _read(bundle / "capture.json")
    scene = _scene(row)
    candidate = _candidate(row)
    if capture.get("group_id") != scene.group_id or capture.get("scene_hash") != scene.scene_hash:
        raise ValueError("opportunity raw source identity mismatch")
    proof = {
        "rule_version": "rgbd.opportunity.v1",
        "sensor_and_identity_sufficient": False,
        "geometry_safe": False,
        "within_validity": False,
        "geometry_applicable": False,
        "raw_capture_path": "capture.json",
        "scope": "full-step reference arm MOVE_TCP only",
        "unknown_reason": None,
    }
    try:
        if any(not (bundle / name).is_file() for name in OPPORTUNITY_CONTEXT_FILES):
            raise ValueError("missing calibrated physical-context/candidate execution evidence")
        if capture.get("assignment_hash") != content_digest(row) or (
            capture.get("action_spec") != candidate
        ):
            raise ValueError("candidate/context assignment does not bind locked schedule")
        observation = RGBDObservation.model_validate(_read(bundle / "observation.json"))
        if (observation.width, observation.height) != (320, 240) or (
            observation.source != "mujoco_camera"
            or observation.scene_id != scene.group_id
            or observation.episode_id != capture.get("episode_id")
            or observation.frame_id != capture.get("frame_id")
        ):
            raise ValueError("unregistered capture dimensions/source/context")
        depth = np.load(bundle / "depth.npy", allow_pickle=False)
        instances = np.load(bundle / "instances.npy", allow_pickle=False)
        if (
            depth.shape != (240, 320)
            or depth.dtype != np.dtype("<f4")
            or (instances.shape != depth.shape or not np.issubdtype(instances.dtype, np.integer))
        ):
            raise ValueError("unregistered metric float32 depth/instance payload")
        if (bundle / "rgb.png").read_bytes() != base64.b64decode(observation.rgb_png_base64) or (
            depth.tobytes() != base64.b64decode(observation.depth_float32_base64)
        ):
            raise ValueError("capture RGB-D payload is not observation-bound")
        camera = scene.scene_parameters["camera"]
        focal = 120 / math.tan(math.radians(camera["fovy"]) / 2)
        intrinsics = (focal, focal, 159.5, 119.5)
        transform = np.eye(4)
        transform[:3, :3] = _camera_rotation(camera["quaternion"]) @ np.diag([1, -1, -1])
        transform[:3, 3] = _vector(camera["position"])
        calibration = hashlib.sha256(
            np.asarray((*intrinsics, *transform.ravel()), dtype="<f8").tobytes()
        ).hexdigest()[:16]
        if (
            not np.allclose(observation.intrinsics, intrinsics, atol=1e-9, rtol=0)
            or not np.allclose(observation.camera_to_world, transform.ravel(), atol=1e-9, rtol=0)
            or observation.calibration_version != calibration
        ):
            raise ValueError("capture calibration does not match assigned optical-z camera")
        context = _read(bundle / "context.json")
        observations = _trace(bundle, row, context)
        step = _integer(capture["physics_step"])
        raw = observations[step]
        if (
            raw.episode_id != observation.episode_id
            or raw.sim_time_s != observation.sim_time_s
            or capture.get("captured_at_s") != raw.sim_time_s
            or capture.get("physical_observation_hash") != content_digest(asdict(raw))
        ):
            raise ValueError("capture physical step/context identity mismatch")
        state = capture["render_state"]
        state_hash = _render_hash(state)
        if (
            state["time_s"] != raw.sim_time_s
            or capture.get("physics_state_hash") != state_hash
            or capture.get("pass_state_hashes") != [state_hash] * 3
            or not np.allclose(state["qpos"][:7], raw.joint_positions_rad, atol=1e-9)
            or not np.allclose(state["qpos"][7:9], raw.finger_positions_m, atol=1e-9)
            or not np.allclose(state["qpos"][9:12], raw.object_position_m, atol=1e-9)
            or not np.allclose(state["qvel"][:7], raw.joint_velocities_rad_s, atol=1e-9)
            or not np.allclose(state["qvel"][9:12], raw.object_linear_velocity_m_s, atol=1e-9)
        ):
            raise ValueError("render pass state does not reproduce raw physics context")
        labels = capture["instance_labels"]
        targets = [int(key) for key, name in labels.items() if name == "object_geom"]
        if len(targets) != 1 or capture["object_instance_id"] != targets[0]:
            raise ValueError("semantic target instance mapping is not unique")
        mask = instances == targets[0]
        pixels = int(mask.sum())
        valid = mask & (depth > 0) & (depth < 10)
        fraction = int(valid.sum()) / pixels if pixels else 0.0
        sensor_sufficient = (
            pixels >= rules["minimum_object_pixels"]
            and fraction >= rules["minimum_valid_depth_fraction"]
        )
        if not sensor_sufficient:
            proof["unknown_reason"] = "insufficient raw object pixels/metric depth"
        ys, xs = np.nonzero(valid)
        values = depth[ys, xs]
        optical = np.stack(((xs - 159.5) * values / focal, (ys - 119.5) * values / focal, values))
        world = transform[:3, :3] @ optical + transform[:3, 3:4]
        rotation = np.asarray(raw.object_geom_rotation_row_major).reshape(3, 3)
        local = rotation.T @ (world - np.asarray(raw.object_geom_position_m)[:, None])
        extent = np.asarray(raw.object_half_extent_m)[:, None]
        tolerance = 0.005 + 3 * row["perturbation"]["noise_m"]
        if np.any(np.abs(local) > extent + tolerance):
            raise ValueError("target pixels/depth disagree with assigned physical object")
        proof["sensor_and_identity_sufficient"] = sensor_sufficient
        submitted = _finite(capture["submitted_at_s"])
        proof["within_validity"] = (
            0 <= submitted - raw.sim_time_s <= rules["opportunity_validity_s"]
        )
        actions = _read(bundle / "candidate-actions.json")
        if (
            len(actions) != 1
            or actions[0].get("action_type") != "MOVE_TCP"
            or actions[0].get("candidate_spec") != candidate
            or type(actions[0].get("start_step")) is not int
            or actions[0]["start_step"] < step
            or actions[0]["start_step"] >= len(observations)
            or observations[-1].physics_step != actions[0].get("end_step")
            or submitted != observations[actions[0]["start_step"]].sim_time_s
        ):
            raise ValueError("candidate execution interval/schedule is not capture-bound")
        _execution(bundle, observations, actions, actions[0]["start_step"], "OFFLINE_CANDIDATE")
        if observations[-1].sim_time_s - raw.sim_time_s > candidate["timeout_s"] or not np.allclose(
            observations[-1].tcp_position_m, candidate["target_position_m"], atol=0.005, rtol=0
        ):
            raise ValueError("complete bounded candidate path does not reach fixed target")
        outcome = evaluate_evidence(
            [
                sample_physical_observation(r, CompletionCriteria("object", "target_region"))
                for r in observations
            ],
            CompletionCriteria("object", "target_region"),
            evaluation_start_step=step,
        )
        proof["geometry_applicable"] = outcome.safety_assessment != "PARTIAL"
        proof["geometry_safe"] = not outcome.safety_violation
        if not proof["geometry_applicable"]:
            raise ValueError("whole-action arm collision scope is incomplete")
        proof.update(
            object_pixels=pixels,
            valid_depth_fraction=fraction,
            physical_context_hash=content_digest(context),
            candidate_hash=content_digest(candidate),
        )
        return (
            "UNKNOWN"
            if not sensor_sufficient
            else ("VALID" if proof["geometry_safe"] and proof["within_validity"] else "INVALID"),
            proof,
            candidate,
        )
    except (ValueError, KeyError, OSError, TypeError, IndexError) as exc:
        proof["unknown_reason"] = str(exc)
        # Never let a partial identity/calibration/geometry contract feed legacy VALID rules.
        proof["sensor_and_identity_sufficient"] = False
        return "UNKNOWN", proof, candidate


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


class IncompleteEvidence(ValueError):
    """An available raw bundle lacks a verifiable complete collector contract."""


def _finite(value: Any) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("nonfinite/invalid raw numeric value")
    return float(value)


def _integer(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("raw step/ordinal must be a nonnegative strict integer")
    return value


def _trace(bundle: Path, row: dict, header: dict) -> list[PhysicsStepObservation]:
    if header.get("schema_version") != "rgbd.raw-episode.v2":
        raise IncompleteEvidence("reset-terminal collector contract is missing")
    scene = _scene(row)
    if (
        header.get("assignment_hash") != content_digest(row)
        or header.get("group_id") != scene.group_id
        or header.get("scene_hash") != scene.scene_hash
    ):
        raise ValueError("raw collector full assignment identity mismatch")
    observations = [_observation(item) for item in _read(bundle / "physical-observations.json")]
    terminal = _integer(header["terminal_step"])
    dt = _finite(header["physics_dt_s"])
    if (
        not 0 < dt <= 0.005
        or header.get("reset_step") != 0
        or (header.get("reset_sim_time_s") != 0 or len(observations) != terminal + 1)
    ):
        raise IncompleteEvidence("reset/terminal physical prefix or tail is missing")
    if any(
        r.physics_step != index
        or abs(r.sim_time_s - index * dt) > 1e-9
        or r.episode_id != header["episode_id"]
        for index, r in enumerate(observations)
    ):
        raise IncompleteEvidence("raw physical episode is not reset-complete full-step continuous")
    if (
        not observations
        or header.get("reset_observation_hash") != content_digest(asdict(observations[0]))
        or header.get("terminal_observation_hash") != content_digest(asdict(observations[-1]))
        or (abs(_finite(header["terminal_sim_time_s"]) - observations[-1].sim_time_s) > 1e-9)
    ):
        raise IncompleteEvidence("collector reset/terminal binding does not reproduce")
    expected_pairs = set(COLLISION_SCOPE)
    for raw in observations:
        pairs = [(a, b) for a, b, _ in raw.self_collision_distances_m]
        if len(pairs) != len(expected_pairs) or set(pairs) != expected_pairs:
            raise IncompleteEvidence("whole reference-arm collision scope is incomplete")
    return observations


def _execution(
    bundle: Path,
    observations: list[PhysicsStepObservation],
    actions: list[dict],
    start_step: int,
    source: str,
) -> None:
    commands = _read(bundle / "commands.json")
    provenance = _read(bundle / "actuator-provenance.json")
    if provenance.get("schema_version") != "rgbd.actuator-provenance.v1":
        raise IncompleteEvidence("typed command-to-actuator-step provenance is missing")
    episode = observations[0].episode_id
    if provenance.get("episode_id") != episode:
        raise ValueError("actuator provenance has foreign episode identity")
    action_by_id = {}
    previous_end = start_step
    first_sequence = commands[0].get("backend_record", {}).get("command_seq", 1) if commands else 1
    sequence_cursor = _integer(first_sequence)
    for action in actions:
        identity = action.get("action_id")
        if (
            not isinstance(identity, str)
            or not SAFE_ID.fullmatch(identity)
            or identity in action_by_id
            or action.get("episode_id") != episode
            or action.get("source") != source
            or _integer(action["start_step"]) != previous_end
            or _integer(action["end_step"]) <= previous_end
        ):
            raise ValueError("typed action dispatch intervals/identities do not join")
        result = ActionResult.model_validate_json(canonical_json(action["result"]), strict=True)
        if (
            result.action_id != identity
            or result.action_type != action["action_type"]
            or result.success is not True
            or result.error_code is not None
            or result.details.get("physics_steps") != action["end_step"] - action["start_step"]
            or result.started_at.tzinfo is None
            or result.finished_at.tzinfo is None
            or (
                source == "GROUND_TRUTH_TEACHER"
                and result.details.get("teacher_source") != "GROUND_TRUTH_TEACHER"
            )
        ):
            raise ValueError("actual action result does not reproduce typed dispatch interval")
        if (
            _integer(action["command_seq_start"]) != sequence_cursor
            or _integer(action["command_seq_end"]) < sequence_cursor
        ):
            raise ValueError("actual action command ranges are not contiguous half-open ranges")
        sequence_cursor = action["command_seq_end"]
        previous_end = action["end_step"]
        action_by_id[identity] = action
    if previous_end != observations[-1].physics_step:
        raise IncompleteEvidence("teacher/candidate dispatch does not cover terminal trajectory")
    controller = provenance["controller_parameters"]
    targets = _vector(controller["initial_joint_targets_rad"], 7)
    fingers = _vector(controller["initial_finger_targets_m"], 2)
    gains = _vector(controller["actuator_gains"], 7)
    ranges = np.asarray(controller["actuator_ctrl_ranges"], dtype=float)
    if (
        ranges.shape != (7, 2)
        or not np.isfinite(ranges).all()
        or np.any(ranges[:, 0] >= ranges[:, 1])
        or np.any(gains <= 0)
        or controller.get("actuator_delay_steps") != 0
    ):
        raise IncompleteEvidence("unsupported or incomplete reference controller parameters")
    command_by_id: dict[str, dict] = {}
    command_steps: list[int] = []
    for command in commands:
        identity = command.get("command_id")
        if (
            not isinstance(identity, str)
            or not SAFE_ID.fullmatch(identity)
            or identity in command_by_id
            or command.get("episode_id") != episode
        ):
            raise ValueError("typed command identity/source is missing or duplicated")
        step = _integer(command["physics_step"])
        if (
            step >= len(observations)
            or abs(_finite(command["sim_time_s"]) - observations[step].sim_time_s) > 1e-9
        ):
            raise ValueError("command timestamp/physics step does not join")
        if command_steps and step < command_steps[-1]:
            raise ValueError("command dispatch order differs from physical sequence")
        command_steps.append(step)
        joined_action = action_by_id.get(command.get("action_id"))
        end_ok = bool(
            joined_action
            and (
                step <= joined_action["end_step"]
                if command.get("type") == "hold_current_joints"
                else step < joined_action["end_step"]
            )
        )
        if (
            joined_action is None
            or step < joined_action["start_step"]
            or not end_ok
            or (command.get("source") != source)
        ):
            raise ValueError("unrelated command outside its typed action dispatch")
        backend = command["backend_record"]
        if (
            backend.get("type") != command.get("type")
            or backend.get("accepted") is not True
            or command.get("accepted") is not True
            or backend.get("after_emergency_stop")
            or _finite(backend["sim_time_s"]) != observations[step].sim_time_s
        ):
            raise ValueError("command is not an accepted matching backend dispatch")
        if (
            backend.get("episode_id") != episode
            or backend.get("physics_step") != step
            or type(backend.get("command_seq")) is not int
            or backend["command_seq"] <= 0
            or backend["command_seq"]
            in {r["backend_record"]["command_seq"] for r in command_by_id.values()}
        ):
            raise ValueError("actual backend command sequence/episode/step does not join")
        if command["type"] in {"joint_target", "hold_current_joints"}:
            target = _vector(command["target_positions_rad"], 7)
            if not np.array_equal(target, _vector(backend["target_positions_rad"], 7)) or (
                not np.array_equal(
                    np.clip(target, -2.8, 2.8), _vector(backend["applied_target_positions_rad"], 7)
                )
            ):
                raise ValueError("typed targets differ from actual backend dispatch")
            if command["type"] == "hold_current_joints" and not np.allclose(
                target, observations[step].joint_positions_rad, atol=1e-9, rtol=0
            ):
                raise ValueError("hold target is not the actual measured joint state")
        elif command["type"] == "gripper":
            if (
                type(command.get("target_open")) is not bool
                or backend.get("target_open") is not command["target_open"]
            ):
                raise ValueError("invalid gripper command target")
            if joined_action["action_type"] not in {"GRASP", "RELEASE"} or (
                command["target_open"] != (joined_action["action_type"] == "RELEASE")
            ):
                raise ValueError("gripper target does not implement teacher action semantics")
        else:
            raise IncompleteEvidence("unsupported backend command semantics")
        if (
            not joined_action["command_seq_start"]
            <= backend["command_seq"]
            < joined_action["command_seq_end"]
        ):
            raise ValueError("actual command sequence is outside its action dispatch range")
        command_by_id[identity] = command
    if [command["backend_record"]["command_seq"] for command in commands] != list(
        range(first_sequence, sequence_cursor)
    ):
        raise ValueError("actual backend command sequence has a missing or unassigned dispatch")
    for action in actions:
        matched = [r for r in commands if r["action_id"] == action["action_id"]]
        kind = action["action_type"]
        if kind == "OBSERVE":
            if matched:
                raise ValueError("dwell action contains unexpected actuator dispatch")
        elif kind in {"GRASP", "RELEASE"}:
            if not matched or any(r["type"] != "gripper" for r in matched):
                raise ValueError("teacher gripper action lacks its command")
        elif kind in {"MOVE_ABOVE", "APPROACH", "LIFT", "MOVE_TO_REGION", "PLACE", "MOVE_TCP"}:
            if (
                not matched
                or not any(r["type"] == "joint_target" for r in matched)
                or any(r["type"] not in {"joint_target", "hold_current_joints"} for r in matched)
            ):
                raise ValueError("teacher motion action lacks its joint targets")
            before = observations[action["start_step"]]
            after = observations[action["end_step"]]
            if np.allclose(before.joint_positions_rad, after.joint_positions_rad, atol=1e-6):
                raise ValueError("motion dispatch has no observed arm progression")
        else:
            raise ValueError("unsupported typed teacher/candidate action")
    controls = provenance["steps"]
    if len(controls) != len(observations) - 1:
        raise IncompleteEvidence("actuator provenance is not reset-terminal full-step complete")
    joint_id = gripper_id = None
    cursor = 0
    for index, control in enumerate(controls, start=1):
        if (
            _integer(control["physics_step"]) != index
            or abs(_finite(control["sim_time_s"]) - observations[index - 1].sim_time_s) > 1e-9
        ):
            raise ValueError("actuator/physical step alignment differs")
        while cursor < len(commands) and commands[cursor]["physics_step"] < index:
            command = commands[cursor]
            if command["type"] in {"joint_target", "hold_current_joints"}:
                targets = np.clip(_vector(command["target_positions_rad"], 7), -2.8, 2.8)
                joint_id = command["command_id"]
            else:
                fingers = np.full(2, 0.039 if command["target_open"] else 0.0)
                gripper_id = command["command_id"]
            cursor += 1
        if (
            control.get("episode_id") != episode
            or not np.array_equal(_vector(control["actuator_gains"], 7), gains)
            or not np.array_equal(np.asarray(control["actuator_ctrl_ranges"], dtype=float), ranges)
        ):
            raise ValueError("actual per-step controller gain/range/episode scope differs")
        active = next(
            (a["action_id"] for a in actions if a["start_step"] < index <= a["end_step"]), None
        )
        if (
            control.get("action_id") != active
            or control.get("joint_command_id") != joint_id
            or control.get("gripper_command_id") != gripper_id
            or not np.allclose(
                _vector(control["applied_joint_targets_rad"], 7), targets, atol=1e-9, rtol=0
            )
            or not np.allclose(
                _vector(control["finger_control_targets_m"], 2), fingers, atol=1e-9, rtol=0
            )
        ):
            raise ValueError("dispatch command targets do not join actual actuator steps")
        q = _vector(control["pre_joint_positions_rad"], 7)
        if not np.allclose(q, observations[index - 1].joint_positions_rad, atol=1e-9, rtol=0):
            raise ValueError("actuator pre-state differs from raw physical history")
        expected = np.clip(
            q
            + np.clip(targets - q, -0.1, 0.1)
            + _vector(control["pre_gravity_bias_nm"], 7) / gains,
            ranges[:, 0],
            ranges[:, 1],
        )
        if not np.allclose(_vector(control["control_rad"], 7), expected, atol=1e-9, rtol=0):
            raise ValueError("actuator control does not implement reference controller targets")


def _recovery(bundle: Path, row: dict, fault: dict, rules: dict) -> tuple[list[dict], dict]:
    attempt = _read(bundle / "attempt.json")
    scene = _scene(row)
    if attempt["group_id"] != scene.group_id or attempt["scene_hash"] != scene.scene_hash:
        raise ValueError("recovery raw source identity mismatch")
    observations = _trace(bundle, row, attempt)
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
    start_step, end_step = _integer(first["physics_step"]), _integer(last["physics_step"])
    start_time, end_time = _finite(first["sim_time_s"]), _finite(last["sim_time_s"])
    start, finish = by_step[start_step], by_step[end_step]
    if (
        abs(start.sim_time_s - start_time) > 1e-9
        or abs(finish.sim_time_s - end_time) > 1e-9
        or finish.physics_step <= start.physics_step
    ):
        raise ValueError("fault injection timestamps do not align with physical evidence")
    duration = finish.sim_time_s - start.sim_time_s
    if last["reason"] == "scheduled_end":
        if abs(duration - params["duration_s"]) > 0.005:
            raise ValueError("fault injection duration differs from locked schedule")
    elif last["reason"] != "finger_contact" or duration > params["duration_s"] + 0.005:
        raise ValueError("unproved fault injection termination")
    if last["reason"] == "finger_contact" and not any(
        "object_geom" in pair and ("left_finger_geom" in pair or "right_finger_geom" in pair)
        for raw in observations[max(0, end_step - 1) : end_step + 1]
        for pair in raw.contact_pairs
    ):
        raise ValueError("fault finger-contact termination has no independent contact basis")
    displacement = (finish.object_position_m[1] - start.object_position_m[1]) * params[
        "direction_y"
    ]
    if displacement < rules["minimum_measured_displacement_m"]:
        raise ValueError("fault injection has no independently measured defect")
    recovery_start = by_step[attempt["recovery_start_step"]]
    if recovery_start.physics_step < finish.physics_step:
        raise ValueError("teacher recovery must start after measured fault interval")
    actions = _read(bundle / "teacher-actions.json")
    if any(a.get("result", {}).get("success") is False for a in actions):
        raise ValueError("actual T5 teacher action dispatch failed")
    if tuple(a.get("action_type") for a in actions) != TEACHER_SEQUENCE:
        raise IncompleteEvidence("exact supported T5 teacher dispatch/action sequence is missing")
    _execution(bundle, observations, actions, recovery_start.physics_step, rules["teacher_source"])
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
    if any(parent.is_symlink() for parent in (destination, *destination.parents)):
        raise ValueError("symlink archive destination is forbidden")
    destination.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for name in names:
        if not (source / name).exists():
            raise IncompleteEvidence(f"raw collector source payload is missing: {name}")
        path = _inside(source, name)
        target = destination / name
        with path.open("rb") as original, target.open("xb") as archived:
            shutil.copyfileobj(original, archived)
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
    version = metadata.get("protocol_version", "ced.research.v2")
    lock = _lock(clean_pools, version)
    if any(parent.is_symlink() for parent in (output, *output.parents)):
        raise ValueError("symlink evidence output destination is forbidden")
    output.mkdir(parents=True, exist_ok=False)
    _write(output / "pool-lock.json", lock)
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
        names = OPPORTUNITY_FILES + tuple(
            name for name in OPPORTUNITY_CONTEXT_FILES if (Path(source) / name).is_file()
        )
        hashes = _archive(Path(source), bundle, names)
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
            except (ValueError, KeyError, OSError, TypeError, IndexError) as exc:
                status = "INCOMPLETE" if isinstance(exc, IncompleteEvidence) else "FAILED"
                entry.update(status=status if eligible else "EXCLUDED", reason=str(exc))
                entry["payload_hashes"] = {
                    name: file_hash(bundle / name)
                    for name in RECOVERY_FILES
                    if (bundle / name).is_file()
                }
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
            "protocol_version": version,
            "pool_lock_hash": content_digest(lock),
        },
    )
    return verify_protocol_evidence(output)


def verify_protocol_evidence(directory: Path) -> dict:
    """Fail closed on incomplete topology, partial provenance and missing payload hashes."""
    errors: list[str] = []
    opportunities: list[dict] = []
    proven = 0
    version = "ced.research.v2"
    topology = False
    complete = False
    try:
        manifest = _read(_inside(directory, "protocol-evidence.json"))
        if (
            manifest.get("schema_version") != "rgbd.protocol-evidence.v1"
            or manifest.get("offline_only") is not True
            or type(manifest.get("required_recovery_groups")) is not int
            or manifest["required_recovery_groups"] != 200
        ):
            raise ValueError("unsupported protocol evidence schema/flags/denominator")
        all_entries = list(directory.rglob("*"))
        if any(p.is_symlink() for p in all_entries):
            raise ValueError("symlink archived payload is forbidden")
        actual_paths = {
            str(p.relative_to(directory))
            for p in all_entries
            if p.is_file() and p != directory / "protocol-evidence.json"
        }
        hashes = manifest["payload_hashes"]
        mandatory = {
            "evidence-pools.json",
            "evidence-rules.json",
            "excluded-groups.json",
            "pool-lock.json",
            "source-registry.json",
            "opportunities.json",
            "recovery-faults.json",
            "generation-attempts.json",
            "missing-opportunities.json",
        }
        if set(hashes) != actual_paths or not mandatory <= set(hashes):
            raise ValueError("payload hash coverage is not complete and exact")
        for relative, digest in hashes.items():
            if not isinstance(digest, str) or not DIGEST.fullmatch(digest):
                raise ValueError("invalid archived payload digest syntax")
            if file_hash(_inside(directory, relative)) != digest:
                errors.append(f"archived payload hash drift: {relative}")
        rules = _read(directory / "evidence-rules.json")
        if rules != yaml.safe_load(RULES_PATH.read_text()):
            raise ValueError("fault/eligibility rules differ from preregistered source")
        pools = _read(directory / "evidence-pools.json")
        excluded = set(_read(directory / "excluded-groups.json"))
        _pool_check(pools, excluded)
        version = manifest["protocol_version"]
        locked = _read(directory / "pool-lock.json")
        expected = _lock(pools, version)
        if locked != expected or manifest.get("pool_lock_hash") != content_digest(locked):
            raise ValueError("full assignment/candidate pool lock does not reproduce")
        topology = _topology_complete(pools, version)
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
        applicable = True
        for item in opportunities:
            try:
                identity = item["assignment_id"]
                seed = OpportunitySeed.model_validate(item["seed"])
                if identity in seen or identity not in formal:
                    raise ValueError("duplicate/outside-formal opportunity identity")
                seen.add(identity)
                expected_bundle = f"raw/{identity}/opportunity"
                if item.get("raw_bundle") != expected_bundle or (
                    item.get("access_role") != "offline_evaluation"
                ):
                    raise ValueError("opportunity archive identity/access scope mismatch")
                bundle = _inside(directory, expected_bundle + "/capture.json").parent
                label, proof, action = _label(bundle, formal[identity], rules)
                names = OPPORTUNITY_FILES + tuple(
                    name for name in OPPORTUNITY_CONTEXT_FILES if (bundle / name).is_file()
                )
                paths = {
                    str((bundle / name).relative_to(directory)): file_hash(bundle / name)
                    for name in names
                }
                if (
                    seed.group_id != formal[identity]["scene"]["group_id"]
                    or seed.opportunity_id != f"opportunity-{identity}"
                    or seed.observation_hash != content_digest(paths)
                    or item["payload_hashes"] != paths
                ):
                    raise ValueError("opportunity source identity/hash mismatch")
                if (
                    seed.oracle_label != label
                    or item["independent_label_evidence"] != proof
                    or seed.action_spec != action
                ):
                    raise ValueError("opportunity label does not recompute from raw evidence")
                applicable = applicable and proof["geometry_applicable"]
            except (ValueError, KeyError, OSError, TypeError, IndexError) as exc:
                errors.append(f"opportunity: {exc}")
        missing = _read(directory / "missing-opportunities.json")
        if len(missing) != len(set(missing)) or set(missing) != set(formal) - seen:
            errors.append("missing opportunity denominator mismatch")
        attempts = _read(directory / "generation-attempts.json")
        if any(entry.get("assignment_id") not in recovery for entry in attempts):
            raise ValueError("foreign attempt identity outside recovery assignments")
        first_success: dict[str, dict] = {}
        for identity, (index, row) in recovery.items():
            entries = [a for a in attempts if a["assignment_id"] == identity]
            if not entries or len(entries) > rules["maximum_attempts_per_group"]:
                raise ValueError("missing recovery attempts or generation bound exceeded")
            ordinals = [entry.get("attempt") for entry in entries]
            if any(type(number) is not int for number in ordinals) or ordinals not in (
                [0],
                list(range(1, len(entries) + 1)),
            ):
                raise ValueError("attempt ordinals must be unique, ordered and consecutive")
            eligible = _eligible(row, rules)
            for entry in entries:
                if entry["eligible"] is not eligible or entry["fault"] != _fault(index, rules):
                    raise ValueError("recovery eligibility/fixed fault does not reproduce")
                if entry["attempt"] == 0:
                    expected_status = "INCOMPLETE" if eligible else "EXCLUDED"
                    if (
                        entry.get("raw_bundle")
                        or entry.get("payload_hashes")
                        or (entry["status"] != expected_status)
                    ):
                        raise ValueError(
                            "unattempted recovery record has invalid raw/status fields"
                        )
                    continue
                relative = f"raw/{identity}/attempt-{entry['attempt']}"
                if entry.get("raw_bundle") != relative or "payload_hashes" not in entry:
                    raise ValueError("attempt raw bundle identity/hash fields are mandatory")
                bundle = directory / relative
                expected_hashes = {
                    name: file_hash(_inside(directory, relative + "/" + name))
                    for name in RECOVERY_FILES
                    if (bundle / name).is_file()
                }
                if entry["payload_hashes"] != expected_hashes:
                    raise ValueError("recovery attempt payload hash drift")
                try:
                    if not eligible:
                        raise ValueError("preregistered scene eligibility failed")
                    if set(expected_hashes) != set(RECOVERY_FILES):
                        raise IncompleteEvidence("raw attempt files are missing")
                    _recovery(bundle, row, entry["fault"], rules)
                    status = "PROVEN"
                except (ValueError, KeyError, OSError, TypeError, IndexError) as exc:
                    status = "INCOMPLETE" if isinstance(exc, IncompleteEvidence) else "FAILED"
                    if not eligible:
                        status = "EXCLUDED"
                if entry["status"] != status:
                    raise ValueError("recovery attempt result does not independently reproduce")
                if status == "PROVEN" and identity not in first_success:
                    first_success[identity] = entry
        faults = _read(directory / "recovery-faults.json")
        if {item["assignment_id"] for item in faults} != set(first_success) or (
            len(faults) != len(first_success)
        ):
            raise ValueError(
                "selected recoverability proof identity set differs from first successes"
            )
        for item in faults:
            identity = item["assignment_id"]
            index, row = recovery[identity]
            selected = first_success[identity]
            if (
                item["group_id"] != row["scene"]["group_id"]
                or item["fault"] != _fault(index, rules)
                or item["raw_bundle"] != selected["raw_bundle"]
            ):
                raise ValueError("recovery proof must select first successful attempt ordinal")
            bundle = _inside(directory, item["raw_bundle"] + "/attempt.json").parent
            samples, proof = _recovery(bundle, row, item["fault"], rules)
            relative = item["raw_bundle"] + "/physical-evidence.json"
            if item["recoverability_evidence_path"] != relative:
                raise ValueError("recovery evidence path is not its selected attempt")
            evidence = _inside(directory, relative)
            if (
                file_hash(evidence) != item["recoverability_evidence_hash"]
                or canonical_json(_read(evidence)) != canonical_json(samples)
                or canonical_json(item["proof"]) != canonical_json(proof)
            ):
                raise ValueError("independent recovery physics/proof does not recompute")
            proven += 1
        complete = bool(
            version == "ced.research.v2"
            and topology
            and registry["history_roots"]
            and registry["entries"]
            and not missing
            and set(seen) == set(formal)
            and applicable
            and proven == 200
        )
    except (ValueError, KeyError, OSError, TypeError, IndexError) as exc:
        errors.append(f"protocol evidence: {exc}")
    status = "INVALID" if errors else "COMPLETE" if complete else "INCOMPLETE"
    return {
        "schema_version": "rgbd.protocol-evidence-audit.v2",
        "status": status,
        "protocol_version": version,
        "topology_complete": topology,
        "required_formal_groups": 2400,
        "required_recovery_groups": 200,
        "valid": status == "COMPLETE",
        "integrity_valid": not errors,
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


def write_recovery_source(
    *,
    row: dict,
    observations: list[Any],
    action_events: list[dict],
    backend_commands: list[dict],
    actuator_steps: list[Any],
    fault_events: list[dict],
    recovery_start_step: int,
    output: Path,
) -> dict:
    """Serialize detached parent-owned hooks; no stepping, rendering or model inference.

    The caller collects reset + every physics/actuator step, including injection
    and settling before invoking T5. ``teacher.physical_observer`` contributes its
    entry snapshot once plus every step; callers must not double-count entry.
    ``action_observer`` emits actual result and 1-based half-open command ranges.
    ``backend.observe_actuator_steps`` emits next-step IDs with PRE-step time.
    Collect commands from ``backend.command_records`` after the terminal action.
    Do not fill unavailable hook fields: absent measurements remain INCOMPLETE.
    """
    raw = [
        asdict(value) if isinstance(value, PhysicsStepObservation) else dict(value)
        for value in observations
    ]
    controls = [
        asdict(value) if not isinstance(value, dict) else dict(value) for value in actuator_steps
    ]
    if not raw or not controls:
        raise IncompleteEvidence("detached reset/actuator source records are missing")
    episode = raw[0]["episode_id"]
    actions = []
    for event in action_events:
        result = event["result"]
        if hasattr(result, "model_dump"):
            result = result.model_dump(mode="json")
        actions.append(
            {
                "action_id": result["action_id"],
                "action_type": result["action_type"],
                "episode_id": event["episode_id"],
                "source": "GROUND_TRUTH_TEACHER",
                "start_step": event["start_step"],
                "end_step": event["end_step"],
                "command_seq_start": event["command_seq_start"],
                "command_seq_end": event["command_seq_end"],
                "result": result,
            }
        )
    commands = []
    for backend in backend_commands:
        matches = [
            action
            for action in actions
            if action["command_seq_start"] <= backend["command_seq"] < action["command_seq_end"]
        ]
        if len(matches) != 1:
            raise IncompleteEvidence("backend command has no unique actual teacher dispatch")
        action = matches[0]
        command = {
            "command_id": f"command-{backend['command_seq']}",
            "action_id": action["action_id"],
            "episode_id": backend["episode_id"],
            "source": "GROUND_TRUTH_TEACHER",
            "physics_step": backend["physics_step"],
            "sim_time_s": backend["sim_time_s"],
            "type": backend["type"],
            "accepted": backend["accepted"],
            "backend_record": dict(backend),
        }
        if backend["type"] in {"joint_target", "hold_current_joints"}:
            command["target_positions_rad"] = backend.get("target_positions_rad")
        elif backend["type"] == "gripper":
            command["target_open"] = backend.get("target_open")
        commands.append(command)
    for control in controls:
        step = control["physics_step"]
        control["action_id"] = next(
            (a["action_id"] for a in actions if a["start_step"] < step <= a["end_step"]), None
        )
        previous = [c for c in commands if c["physics_step"] < step and c["accepted"]]
        control["joint_command_id"] = next(
            (
                c["command_id"]
                for c in reversed(previous)
                if c["type"] in {"joint_target", "hold_current_joints"}
            ),
            None,
        )
        control["gripper_command_id"] = next(
            (c["command_id"] for c in reversed(previous) if c["type"] == "gripper"), None
        )
    dt = raw[1]["sim_time_s"] - raw[0]["sim_time_s"] if len(raw) > 1 else 0.0
    header = {
        "schema_version": "rgbd.raw-episode.v2",
        "assignment_hash": content_digest(row),
        "group_id": row["scene"]["group_id"],
        "scene_hash": row["scene_hash"],
        "episode_id": episode,
        "reset_step": raw[0]["physics_step"],
        "reset_sim_time_s": raw[0]["sim_time_s"],
        "terminal_step": raw[-1]["physics_step"],
        "terminal_sim_time_s": raw[-1]["sim_time_s"],
        "physics_dt_s": dt,
        "reset_observation_hash": content_digest(raw[0]),
        "terminal_observation_hash": content_digest(raw[-1]),
        "recovery_start_step": recovery_start_step,
    }
    first = controls[0]
    provenance = {
        "schema_version": "rgbd.actuator-provenance.v1",
        "episode_id": episode,
        "controller_parameters": {
            "actuator_gains": first["actuator_gains"],
            "actuator_ctrl_ranges": first["actuator_ctrl_ranges"],
            "initial_joint_targets_rad": first["applied_joint_targets_rad"],
            "initial_finger_targets_m": first["finger_control_targets_m"],
            "actuator_delay_steps": 0,
        },
        "steps": controls,
    }
    if any(parent.is_symlink() for parent in (output, *output.parents)):
        raise ValueError("symlink raw collector destination is forbidden")
    output.mkdir(parents=True, exist_ok=False)
    for name, value in {
        "attempt.json": header,
        "physical-observations.json": raw,
        "teacher-actions.json": actions,
        "commands.json": commands,
        "actuator-provenance.json": provenance,
        "fault-events.json": fault_events,
    }.items():
        _write(output / name, value)
    return header
