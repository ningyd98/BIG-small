"""Reconstruct initial freeze inputs from immutable evidence, never summary flags."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import struct
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from cloud_edge_robot_arm.datasets.rgbd.models import content_digest
from cloud_edge_robot_arm.research.pilot import derive_tcap
from cloud_edge_robot_arm.research.pilot_audit import audit_pilot, physical_sample, read_json
from cloud_edge_robot_arm.research.protocol import (
    STRATA,
    OpportunitySeed,
    ProtocolSpec,
    file_hash,
)
from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot


def _inside(directory: Path, relative: str) -> Path:
    name = Path(relative)
    if name.is_absolute() or ".." in name.parts or name == Path("."):
        raise ValueError("evidence path must be relative and cannot traverse")
    root = directory.absolute()
    if root.resolve() != root or root.is_symlink():
        raise ValueError("evidence root cannot follow symlinks")
    path = root / name
    for ancestor in (path, *path.parents):
        if ancestor == root:
            break
        if ancestor.is_symlink():
            raise ValueError("evidence symlinks are forbidden")
    if not path.resolve().is_relative_to(root):
        raise ValueError("evidence path escapes its root")
    return path


def _read_frame(directory: Path) -> Any:
    """Reconstruct calibrated registered observation from the original payloads."""
    from cloud_edge_robot_arm.vision.capture import CapturedFrame
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    metadata = read_json(_inside(directory, "observation.json"))
    if not isinstance(metadata, Mapping):
        raise ValueError("raw observation metadata must be an object")
    fields = {name: metadata[name] for name in RGBDObservation.model_fields if name in metadata}
    for field, filename in (
        ("rgb_png_base64", "rgb.png"),
        ("depth_float32_base64", "depth.f32"),
        ("valid_mask_base64", "valid_mask.u8"),
    ):
        fields[field] = base64.b64encode(_inside(directory, filename).read_bytes()).decode()
    observation = RGBDObservation.model_validate(fields)
    if (observation.width, observation.height) != (320, 240) or not all(
        (
            observation.episode_id,
            observation.scene_id,
            observation.calibration_version,
        )
    ):
        raise ValueError("probe requires complete 320x240 calibrated episode identity")
    if metadata["rgb_sha256"] != observation.evidence()["rgb_sha256"] or (
        metadata["depth_sha256"] != observation.evidence()["depth_sha256"]
    ):
        raise ValueError("registered image hashes do not reproduce")
    raw_ids = _inside(directory, "instance_geom_ids.i32").read_bytes()
    if len(raw_ids) != 320 * 240 * 4:
        raise ValueError("instance pixels do not cover the registered observation")
    passes = metadata["pass_state_hashes"]
    physics = metadata["physics_state_hash"]
    if not isinstance(passes, list) or len(passes) != 3 or set(passes) != {physics}:
        raise ValueError("raw RGB/depth/instance passes are not synchronized")
    labels = {int(key): value for key, value in metadata["instance_labels"].items()}
    return CapturedFrame(
        observation, struct.unpack("<76800i", raw_ids), labels, physics, tuple(passes)
    )


def _model_evidence(settings: Mapping[str, Any]) -> dict[str, Any]:
    """Rebuild the adapter's model snapshot from recorded effective settings."""
    return {
        name: settings[name]
        for name in (
            "provider",
            "model",
            "endpoint_hash",
            "weight_digest",
            "quantization",
            "image_size",
            "generation_parameters",
            "timeout_s",
            "coordinate_system",
            "grasp_profile",
        )
    }


def _model_evidence_hash(settings: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(_model_evidence(settings), sort_keys=True).encode()
    ).hexdigest()


def verify_role_probe_evidence(directory: Path) -> dict[str, Any]:
    """Read exact role wire/frames and redo nominal parsing/grounding, without HTTP.

    Byte integrity and reproduced nominal checks do not authenticate remote
    weights or accept edge/physical performance. Missing/suppressed wire is unavailable.
    """
    errors: list[str] = []
    reconstructed: dict[str, Any] | None = None
    try:
        from scripts.probe_rgbd_model import _pixel_hit
        from scripts.probe_rgbd_roles import can_accept_role_probe, summarize_role_request

        from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
        from cloud_edge_robot_arm.research.cost_ledger import RequestCost
        from cloud_edge_robot_arm.vision.messages import build_visual_messages
        from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter, VisualDecision
        from cloud_edge_robot_arm.vision.role_models import RoleModelBundle, RoleProviderSnapshot

        path = _inside(directory, "role-probe-report.json")
        raw = path.read_bytes()
        if _inside(directory, "role-probe-report.sha256").read_text().strip() != (
            hashlib.sha256(raw).hexdigest()
        ):
            raise ValueError("role report content hash mismatch")
        report = json.loads(raw)
        if not isinstance(report, dict) or report.get("schema_version") != "ced.role-probe.v1":
            raise ValueError("unsupported role report schema")
        if (
            report.get("status") != "PASS"
            or report.get("scope") == "SOFTWARE_ONLY"
            or (
                report.get("physical_acceptance") is not False
                or report.get("edge_acceptance") is not False
                or report.get("dispatch") is not False
            )
        ):
            raise ValueError("nominal probe cannot claim physical/edge/software acceptance")
        if read_json(_inside(directory, "roles-frozen.json")) != report["bundle"]:
            raise ValueError("role snapshot differs from the original probe")
        cloud = RoleProviderSnapshot(**report["bundle"]["cloud_snapshot"])
        assert cloud.model_id is not None
        bundle = RoleModelBundle(
            cloud,
            report["bundle"]["edge_provider_id"],
            report["bundle"]["edge_provider_hash"],
            report["bundle"]["device_pipeline_hash"],
        )
        settings = report["request_settings"]
        reconstructed = json.loads(json.dumps(report))
        rebuilt_attempts = []
        attempts = report["attempts"]
        if (
            not isinstance(attempts, list)
            or len(attempts) != report["probe_config"]["warm_runs"] + 1
        ):
            raise ValueError("role probe first/warm attempt coverage is incomplete")
        for index, attempt in enumerate(attempts):
            relative = f"attempt-{index:02d}"
            case = _inside(directory, relative)
            if read_json(_inside(case, "attempt.json")) != attempt or (
                attempt.get("index") != index
                or attempt.get("phase") != ("first" if index == 0 else "warm")
            ):
                raise ValueError("persisted probe attempt identity/content differs")
            request_raw = _inside(case, "request.raw").read_bytes()
            response_raw = _inside(case, "response.raw").read_bytes()
            if any(len(value) > 2_000_000 for value in (request_raw, response_raw)):
                raise ValueError("wire payload exceeds the original transport bound")
            if any(
                hashlib.sha256(value).hexdigest() != attempt[f"{name}_sha256"]
                for name, value in (("request", request_raw), ("response", response_raw))
            ):
                raise ValueError("wire payload hash drift")
            body, response = json.loads(request_raw), json.loads(response_raw)
            if read_json(_inside(case, "request.json")) != body or (
                read_json(_inside(case, "response.json")) != response
            ):
                raise ValueError("parsed wire convenience artifact differs from original bytes")
            frame = _read_frame(case)
            request = InitialPlanningRequest(
                request_id=f"cloud-role-probe-{index:02d}",
                user_instruction=report["probe_config"]["instruction"],
                scene=SceneSummary(
                    scene_version=1,
                    updated_at=datetime.fromisoformat(str(frame.observation.captured_at)),
                ),
                observation=frame.observation,
            )
            messages = build_visual_messages(
                request.user_instruction,
                frame.observation,
                image_size=tuple(settings["image_size"]),
                coordinate_system=settings["coordinate_system"],
                decision_schema=VisualDecision.model_json_schema(),
            )
            from cloud_edge_robot_arm.vision.planner import compatible_messages

            expected_body = {
                "model": settings["model"],
                "messages": compatible_messages(messages),
                "temperature": settings["generation_parameters"]["temperature"],
                "max_tokens": settings["generation_parameters"]["num_predict"],
                "response_format": {"type": "json_object"},
            }
            if body != expected_body:
                raise ValueError("actual wire does not bind the frozen frame/prompt/settings")
            offline = RGBDPlannerAdapter(
                base_url="http://127.0.0.1:11434",
                model=cloud.model_id,
                provider="openai_compatible",
            )
            draft = offline._ground_response(
                request,
                response,
                0,
                frame.observation,
                messages,
                tuple(settings["image_size"]),
                settings["coordinate_system"],
                settings["grasp_profile"],
            )
            evidence = draft.observation_evidence or {}
            target_hit, target_check = _pixel_hit(
                frame, evidence.get("original_pixel_target"), "object_geom"
            )
            destination_hit, destination_check = _pixel_hit(
                frame, evidence.get("original_pixel_destination"), "target_region_geom"
            )
            saved_evidence = dict(attempt["observation_evidence"])
            saved_evidence.pop("cloud_snapshot_hash", None)
            saved_evidence.pop("valid_decision_latency_ms", None)
            compared = dict(evidence)
            compared.pop("valid_decision_latency_ms", None)
            compared["model_snapshot"] = _model_evidence(settings)
            compared["model_snapshot_hash"] = _model_evidence_hash(settings)
            if (
                saved_evidence != compared
                or attempt["parsed_json"] != draft.parsed_json
                or (
                    attempt["target_offline_check"] != target_check
                    or attempt["destination_offline_check"] != destination_check
                )
            ):
                raise ValueError("response parsing/grounding does not reproduce from raw RGB-D")
            costs = attempt["cost_ledger"]
            sent = [RequestCost.model_validate(item) for item in costs["requests"]]
            if len(sent) != 1 or any(
                r.status != "SUCCESS"
                or r.model_role != "PLANNER"
                or r.provider_version != _model_evidence_hash(settings)
                or (
                    r.provider_location != "REMOTE_SERVICE"
                    or r.sent_at is None
                    or r.serialized_sent_bytes != len(request_raw)
                    or r.serialized_received_bytes != len(response_raw)
                )
                for r in sent
            ):
                raise ValueError("actual probe wire counts do not join the settled request ledger")
            rebuilt = dict(
                attempt,
                artifact_directory=str(case),
                parsed=draft.parse_error is None,
                grounded=draft.observed_scene is not None,
                target_hit=target_hit,
                destination_hit=destination_hit,
                transport_two_images=True,
                request_summary=summarize_role_request(body),
                expected_request_summary=summarize_role_request(expected_body),
            )
            rebuilt_attempts.append(rebuilt)
        reconstructed["attempts"] = rebuilt_attempts
        reconstructed["capture"] = {"synchronized": True, "image_size": [320, 240]}
        if not can_accept_role_probe(reconstructed):
            raise ValueError("reconstructed nominal role probe gate rejected source/settings/wire")
        reconstructed["bundle_hash"] = bundle.digest()
    except (OSError, ValueError, KeyError, TypeError, IndexError, struct.error) as exc:
        errors.append(f"role probe unavailable: {type(exc).__name__}: {exc}")
    return {
        "schema_version": "ced.role-probe-reader.v1",
        "available": not errors,
        "errors": errors,
        "physical_acceptance": False,
        "edge_acceptance": False,
        "scope": "NOMINAL_PROBE_ONLY",
        "report": reconstructed if not errors else None,
    }


def _registered_observation(directory: Path) -> Any:
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    metadata = read_json(_inside(directory, "observation.json"))
    fields = {name: metadata[name] for name in RGBDObservation.model_fields if name in metadata}
    fields.update(
        rgb_png_base64=base64.b64encode(_inside(directory, "rgb.png").read_bytes()).decode(),
        depth_float32_base64=base64.b64encode(
            _inside(directory, "depth.f32").read_bytes()
        ).decode(),
    )
    observation = RGBDObservation.model_validate(fields)
    if (observation.width, observation.height) != (320, 240) or not all(
        (
            observation.episode_id,
            observation.calibration_version,
        )
    ):
        raise ValueError("case observation identity/calibration/resolution is incomplete")
    if any(
        metadata[name] != observation.evidence()[name]
        for name in (
            "rgb_sha256",
            "depth_sha256",
            "checksum_sha256",
        )
    ):
        raise ValueError("case observation payload identity drift")
    return observation


def _audit_actuators(case: Path, raw: list[Any], header: Mapping[str, Any]) -> None:
    """Join complete actual backend commands to every recorded pre-step controller output."""
    commands = read_json(_inside(case, "commands.json"))
    controls = read_json(_inside(case, "actuator-steps.json"))
    if (
        not isinstance(commands, list)
        or not isinstance(controls, list)
        or len(controls) != len(raw) - 1
    ):
        raise ValueError("raw command/controller step coverage is incomplete")
    if [c["command_seq"] for c in commands] != list(range(1, len(commands) + 1)):
        raise ValueError("raw backend command prefix/identity is incomplete")
    initial = header["initial_controller_targets"]
    targets = np.asarray(initial["joints_rad"], dtype=float)
    fingers = np.asarray(initial["fingers_m"], dtype=float)
    if (
        targets.shape != (7,)
        or fingers.shape != (2,)
        or not np.isfinite(targets).all()
        or (not np.isfinite(fingers).all() or header.get("actuator_delay_steps") != 0)
    ):
        raise ValueError("unsupported initial controller state/delay")
    for command in commands:
        if type(command["physics_step"]) is not int or not 0 <= command["physics_step"] < len(raw):
            raise ValueError("backend dispatch step is outside recorded episode")
        if (
            command["episode_id"] != raw[0].episode_id
            or abs(command["sim_time_s"] - raw[command["physics_step"]].sim_time_s) > 1e-9
            or command.get("type") not in {"joint_target", "hold_current_joints", "gripper"}
        ):
            raise ValueError("backend command source/time/semantics are incomplete")
    cursor = 0
    for index, control in enumerate(controls, start=1):
        if (
            control["physics_step"] != index
            or control["episode_id"] != raw[0].episode_id
            or abs(control["sim_time_s"] - raw[index - 1].sim_time_s) > 1e-9
        ):
            raise ValueError("actuator/physical step alignment differs")
        while cursor < len(commands) and commands[cursor]["physics_step"] < index:
            command = commands[cursor]
            if command["accepted"]:
                if command["type"] in {"joint_target", "hold_current_joints"}:
                    requested = np.asarray(command["target_positions_rad"], dtype=float)
                    applied = np.asarray(command["applied_target_positions_rad"], dtype=float)
                    if (
                        requested.shape != (7,)
                        or not np.isfinite(requested).all()
                        or (not np.array_equal(applied, np.clip(requested, -2.8, 2.8)))
                    ):
                        raise ValueError("actual accepted joint target does not reproduce")
                    targets = applied
                else:
                    if type(command["target_open"]) is not bool:
                        raise ValueError("gripper target must be an actual boolean")
                    fingers = np.full(2, 0.039 if command["target_open"] else 0.0)
            cursor += 1
        q = np.asarray(control["pre_joint_positions_rad"], dtype=float)
        gain = np.asarray(control["actuator_gains"], dtype=float)
        ranges = np.asarray(control["actuator_ctrl_ranges"], dtype=float)
        bias = np.asarray(control["pre_gravity_bias_nm"], dtype=float)
        actual = np.asarray(control["control_rad"], dtype=float)
        if any(v.shape != (7,) or not np.isfinite(v).all() for v in (q, gain, bias, actual)) or (
            ranges.shape != (7, 2)
            or not np.isfinite(ranges).all()
            or np.any(gain <= 0)
            or np.any(ranges[:, 0] >= ranges[:, 1])
        ):
            raise ValueError("controller vectors/ranges are incomplete or nonfinite")
        expected = np.clip(
            q + np.clip(targets - q, -0.1, 0.1) + bias / gain, ranges[:, 0], ranges[:, 1]
        )
        if not np.allclose(q, raw[index - 1].joint_positions_rad, atol=1e-9, rtol=0) or (
            not np.allclose(actual, expected, atol=1e-9, rtol=0)
            or not np.allclose(control["applied_joint_targets_rad"], targets, atol=1e-9, rtol=0)
            or not np.allclose(control["finger_control_targets_m"], fingers, atol=1e-9, rtol=0)
        ):
            raise ValueError("actual controller outputs do not join dispatch/raw physical state")


def _audit_ced_reset(raw: list[Any], header: Mapping[str, Any], scene: Mapping[str, Any]) -> None:
    target = scene["scene_parameters"]["target"]
    destination = scene["scene_parameters"]["destination"]
    initial = header["initial_controller_targets"]
    reference_joints = [-0.8, 0, 0, 0, 0, 0, 0]
    if not raw or (
        not np.allclose(raw[0].object_position_m, target["position"], atol=1e-9, rtol=0)
        or not np.allclose(raw[0].object_half_extent_m, target["half_size"], atol=1e-9, rtol=0)
        or not np.allclose(raw[0].joint_positions_rad, reference_joints, atol=1e-9, rtol=0)
        or not np.allclose(initial["joints_rad"], reference_joints, atol=1e-9, rtol=0)
        or not np.allclose(initial["fingers_m"], [0.039, 0.039], atol=1e-9, rtol=0)
        or any(
            not np.allclose(item.region_center_m, destination["position"], atol=1e-9, rtol=0)
            or not np.allclose(
                item.region_half_extent_m, destination["half_size"], atol=1e-9, rtol=0
            )
            for item in raw
        )
    ):
        raise ValueError("raw reset scene/controller geometry differs from full assignment")


def _case_wire_payloads(case: Path, entry: Mapping[str, Any]) -> tuple[bytes, bytes]:
    request = _inside(case, entry["request_path"]).read_bytes()
    response = (
        _inside(case, entry["response_path"]).read_bytes() if entry.get("response_path") else b""
    )
    if (
        hashlib.sha256(request).hexdigest() != entry["request_sha256"]
        or len(request) != entry["serialized_sent_bytes"]
        or len(response) != entry["serialized_received_bytes"]
        or (response and hashlib.sha256(response).hexdigest() != entry["response_sha256"])
    ):
        raise ValueError("actual request/response wire length/hash differs from settled counts")
    return request, response


def _ced_evaluation_start(header: Mapping[str, Any], raw_count: int) -> int:
    start = header["evaluation_start_step"]
    if type(start) is not int or start != 120 or raw_count <= 120:
        raise ValueError("actual collector evaluation must retain the complete tail from step120")
    return start


def _audit_ced_case(
    case: Path, assignment: Mapping[str, Any], row: Mapping[str, Any], probe: Mapping[str, Any]
) -> dict[str, Any]:
    from dataclasses import asdict

    from scripts.probe_rgbd_roles import summarize_role_request

    from cloud_edge_robot_arm.research.cost_ledger import RequestCost
    from cloud_edge_robot_arm.research.protocol_evidence import _trace
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
        CompletionCriteria,
        evaluate_evidence,
        sample_physical_observation,
    )
    from cloud_edge_robot_arm.vision.messages import build_visual_messages
    from cloud_edge_robot_arm.vision.planner import VisualDecision

    if (
        read_json(_inside(case, "assignment.json")) != assignment
        or row.get("scope") != "REAL_RUNTIME"
    ):
        raise ValueError("case source/assignment binding is unavailable")
    if read_json(_inside(case, "case-result.json")) != row:
        raise ValueError("case result publication differs from all-original results table")
    header = read_json(_inside(case, "context.json"))
    if header.get("pilot_assignment_hash") != content_digest(assignment) or (
        header.get("role_bundle_hash") != probe["bundle_hash"]
    ):
        raise ValueError("raw episode does not bind the full paired assignment/roles")
    raw = _trace(case, dict(assignment["base_assignment"]), header)
    _audit_ced_reset(raw, header, assignment["base_assignment"]["scene"])
    _audit_actuators(case, raw, header)
    policy = read_json(_inside(case, "policy.json"))
    if (
        policy["device_pipeline"] != "OPENCV"
        or policy["model_snapshot_hash"] != _model_evidence_hash(probe["request_settings"])
        or policy["role_binding"]["bundle"] != probe["bundle"]
        or (
            policy["role_binding"]["edge_snapshot"] != probe["edge_snapshot"]
            or policy["role_binding"]["device_source_hashes"] != probe["device_source_hashes"]
            or policy["role_binding"]["edge_policy"] != probe["edge_policy"]
            or policy["verification_budget"] != probe["edge_policy"]["verification_budget"]
            or policy["supervision_period_s"] != assignment["period_s"]
            or policy["advance_physics_during_wait"] is not True
        )
    ):
        raise ValueError("actual episode policy differs from frozen B0/role/verification boundary")
    start = _ced_evaluation_start(header, len(raw))
    criteria = CompletionCriteria("object", "target_region")
    samples = [sample_physical_observation(item, criteria) for item in raw[start:]]
    if content_digest([asdict(s) for s in samples]) != content_digest(
        read_json(_inside(case, "physical-evidence.json"))
    ):
        raise ValueError("physical samples do not reproduce from reset-complete raw physics")
    physical = evaluate_evidence(samples, criteria, evaluation_start_step=start)
    if content_digest(asdict(physical)) != content_digest(
        read_json(_inside(case, "physical-outcome.json"))
    ):
        raise ValueError("independent physical verdict differs from original raw evaluation")
    episode = read_json(_inside(case, "episode.json"))
    if (
        episode["episode_id"] != raw[0].episode_id
        or episode["physical_success"] != physical.success
        or episode["status"] != row["status"]
    ):
        raise ValueError("episode physical identity/outcome differs")
    success = bool(
        physical.success
        and episode["online_reported_complete"] is True
        and episode["terminal_reason"] is None
    )
    if success != row["success"] or success != episode["success"]:
        raise ValueError("online/independent physical success conjunction differs")
    observations = {}
    for folder in ("frames", "supervision-frames"):
        directory = _inside(case, folder)
        if directory.is_dir():
            for path in sorted(directory.iterdir()):
                observation = _registered_observation(path)
                if observation.episode_id != raw[0].episode_id:
                    raise ValueError("observation belongs to a foreign raw episode")
                observations[observation.observation_id] = observation
    declared = [v for v in episode["verification_records"] if v.get("layer") == "OBSERVATION"]
    if not declared or any(
        v["observation_id"] not in observations
        or (v["checksum_sha256"] != observations[v["observation_id"]].checksum_sha256)
        for v in declared
    ):
        raise ValueError("online observation trace does not reproduce from raw frames")
    settings = probe["request_settings"]
    image_pairs = set()
    for observation in observations.values():
        messages = build_visual_messages(
            "audit",
            observation,
            image_size=tuple(settings["image_size"]),
            coordinate_system=settings["coordinate_system"],
            decision_schema=VisualDecision.model_json_schema(),
        )
        blobs = []
        for message in messages:
            encoded = message.get("images", [])
            if not isinstance(encoded, list) or any(not isinstance(v, str) for v in encoded):
                raise ValueError("registered model images must be base64 strings")
            blobs.extend(encoded)
        images = tuple(hashlib.sha256(base64.b64decode(image)).hexdigest() for image in blobs)
        image_pairs.add(images)
    wire = read_json(_inside(case, "wire-index.json"))
    costs = read_json(_inside(case, "costs.json"))
    requests = [RequestCost.model_validate(value) for value in costs["requests"]]
    sent = [r for r in requests if r.sent_at is not None]
    if len(sent) != len(wire) or any(
        r.status == "IN_FLIGHT"
        or r.provider_location != "REMOTE_SERVICE"
        or r.model_role != "PLANNER"
        or r.provider_version != _model_evidence_hash(settings)
        for r in sent
    ):
        raise ValueError("settled actual request/wire denominator is incomplete")
    for entry in wire:
        request_raw, _ = _case_wire_payloads(case, entry)
        body = json.loads(request_raw)
        summary = summarize_role_request(body)
        if hashlib.sha256(request_raw).hexdigest() != entry["request_sha256"] or (
            summary["model"] != settings["model"]
            or tuple(summary["image_sha256"]) not in image_pairs
            or body["temperature"] != settings["generation_parameters"]["temperature"]
            or body["max_tokens"] != settings["generation_parameters"]["num_predict"]
            or body["response_format"] != {"type": "json_object"}
        ):
            raise ValueError("actual model wire differs from frozen model/current RGB-D")
    if sum(e["serialized_sent_bytes"] for e in wire) != sum(
        r.serialized_sent_bytes for r in sent
    ) or (
        sum(e["serialized_received_bytes"] for e in wire)
        != sum(r.serialized_received_bytes for r in sent)
        or costs["summary"]["cloud_model_requests"] != len(sent)
        or costs["summary"]["application_bytes"]
        != sum(r.serialized_sent_bytes + r.serialized_received_bytes for r in sent)
        or row["costs"] != costs["summary"]
        or row["cloud_requests"] != len(sent)
    ):
        raise ValueError("actual serialized role costs differ from all final publications")
    duration = row["wall_duration_s"]
    if type(duration) not in {int, float} or not math.isfinite(duration) or duration <= 0:
        raise ValueError("measured original wall duration is unavailable")
    return {
        **row,
        "stratum_id": assignment["stratum_id"],
        "success": success,
        "safety_violation": physical.safety_violation,
        "cloud_requests": len(sent),
    }


def audit_ced_pilot_stage(directory: Path, stage: str) -> dict[str, Any]:
    """Independent complete raw audit; synthetic/metadata-only evidence stays unavailable."""
    errors: list[str] = []
    cases: list[dict[str, Any]] = []
    result: dict[str, Any] = {}
    try:
        from cloud_edge_robot_arm.research.pilot import (
            BUDGET_SELECTION_RULE,
            build_pilot_assignments,
            choose_b0_period,
            stage_source_paths,
        )

        report = read_json(_inside(directory, "summary.json"))
        if (
            stage not in {"selection", "foundation"}
            or not isinstance(report, Mapping)
            or (
                report.get("schema_version") != "ced.pilot-stage.v1"
                or report.get("protocol_version") != "ced.research.v2"
                or report.get("stage") != stage
                or report.get("scope") != "UNVERIFIED"
                or report.get("execution_mode") != "REAL_RUNTIME"
            )
        ):
            raise ValueError("stage requires complete original REAL_RUNTIME sources")
        hashes = read_json(_inside(directory, "source-hashes.json"))
        if not isinstance(hashes, dict) or not hashes:
            raise ValueError("missing immutable runner/source archive")
        if set(hashes) != {str(path) for path in stage_source_paths()}:
            raise ValueError("stage source inventory must retain every collector source")
        for name, expected in hashes.items():
            if (
                file_hash(_inside(directory, "source/" + name)) != expected
                or file_hash(Path(name)) != expected
            ):
                raise ValueError("stage archived/current source hashes differ")
        probe_audit = verify_role_probe_evidence(_inside(directory, "role-probe"))
        if not probe_audit["available"]:
            raise ValueError(f"nominal role probe unavailable: {probe_audit['errors']}")
        probe = probe_audit["report"]
        pools = read_json(_inside(directory, "pools.json"))
        assignments = read_json(_inside(directory, "assignments.json"))
        expected = build_pilot_assignments(
            pools,
            stage,
            role_bundle_hash=probe["bundle_hash"],
            period_s=report.get("b0_period_s") if stage == "foundation" else None,
        )
        if assignments != expected or report["assignment_manifest_hash"] != content_digest(
            expected
        ):
            raise ValueError("complete paired frozen assignment manifest differs")
        records = read_json(_inside(directory, "results.json"))
        rows = {row["assignment_id"]: row for row in records}
        if len(rows) != len(records) or set(rows) != {r["assignment_id"] for r in expected}:
            raise ValueError("all assigned failed/blocked original records are required")
        if read_json(_inside(directory, "selection-rule.json")) != BUDGET_SELECTION_RULE:
            raise ValueError("selection/budget rule differs from fixed design")
        for assignment in expected:
            cases.append(
                _audit_ced_case(
                    _inside(directory, "cases/" + assignment["assignment_id"]),
                    assignment,
                    rows[assignment["assignment_id"]],
                    probe,
                )
            )
        result = {
            "role_bundle_hash": probe["bundle_hash"],
            "cloud_model_snapshot_hash": _model_evidence_hash(probe["request_settings"]),
            "pools": pools,
            "assignment_manifest_hash": content_digest(expected),
            "cases": cases,
            "selected_period_s": report.get("b0_period_s"),
        }
        if stage == "selection":
            diagnostic = choose_b0_period(expected, cases)
            if diagnostic["diagnostic_selected_period_s"] is None:
                raise ValueError("NO_FEASIBLE_BASELINE")
            result["selected_period_s"] = diagnostic["diagnostic_selected_period_s"]
            result["selection_curve"] = diagnostic["periods"]
        result["evidence_hash"] = content_digest(
            {
                "assignments": expected,
                "results": records,
                "source_hashes": hashes,
                "role_probe_hash": file_hash(
                    _inside(directory, "role-probe/role-probe-report.json")
                ),
            }
        )
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        errors.append(f"stage unavailable: {type(exc).__name__}: {exc}")
    return {
        "schema_version": "ced.pilot-stage-audit.v1",
        "available": not errors,
        "errors": errors,
        "accepted_success": sum(r["success"] for r in cases) if not errors else 0,
        "actual_research_status": "NOT_RUN",
        **(result if not errors else {}),
    }


def _initial_v2_spec(directory: Path) -> ProtocolSpec:
    from cloud_edge_robot_arm.research.pilot import BUDGET_SELECTION_RULE
    from cloud_edge_robot_arm.research.protocol_evidence import verify_protocol_evidence
    from cloud_edge_robot_arm.research.resource_plan import verify_resource_plan_receipt

    if not _inside(directory, "resource-plan.json").is_file():
        raise ValueError("initial resource acceptance requires independently compiled full budget")
    resource = verify_resource_plan_receipt(directory)
    foundation = audit_ced_pilot_stage(directory, "foundation")
    if not foundation["available"]:
        raise ValueError(f"foundation unavailable: {foundation['errors']}")
    selection = audit_ced_pilot_stage(_inside(directory, "selection-evidence"), "selection")
    if not selection["available"] or any(
        foundation[name] != selection[name]
        for name in ("pools", "role_bundle_hash", "selected_period_s")
    ):
        raise ValueError("foundation selection source/period/roles/pools are not identical")
    cases = foundation["cases"]
    nominal = [r for r in cases if r["stratum_id"].startswith("STATIC")]
    if (
        sum(r["success"] for r in cases) / 120 < 0.8
        or sum(r["success"] for r in nominal) / 40 < 0.9
        or (sum(r["safety_violation"] for r in cases) / 120 > 0.01)
    ):
        raise ValueError("NO_FEASIBLE_BASELINE; foundation did not reproduce quality")
    evidence_directory = _inside(directory, "protocol-evidence")
    evidence = verify_protocol_evidence(evidence_directory)
    if (
        not evidence["valid"]
        or read_json(_inside(evidence_directory, "evidence-pools.json")) != foundation["pools"]
    ):
        raise ValueError("fixed opportunity/recovery evidence is incomplete or has different pools")
    derived_tcap = derive_tcap([r["wall_duration_s"] for r in cases if r["success"]])
    if (
        resource["tcap_s"] != derived_tcap
        or resource["role_bundle_hash"] != foundation["role_bundle_hash"]
    ):
        raise ValueError("resource plan differs from independently accepted foundation Tcap/roles")
    return ProtocolSpec(
        schema_version="ced.research.v2",
        tcap_s=derived_tcap,
        pool_hashes={name: content_digest(rows) for name, rows in foundation["pools"].items()},
        model_snapshot_hash=foundation["role_bundle_hash"],
        role_bundle_hash=foundation["role_bundle_hash"],
        selected_b0_period_s=selection["selected_period_s"],
        selection_manifest_hash=selection["evidence_hash"],
        budget_selection_rule_hash=content_digest(BUDGET_SELECTION_RULE),
        resource_plan_hash=resource["content_hash"],
        opportunity_hash=content_digest(
            read_json(_inside(evidence_directory, "opportunities.json"))
        ),
        recovery_fault_manifest_hash=content_digest(
            read_json(_inside(evidence_directory, "recovery-faults.json"))
        ),
    )


def initial_spec_from_evidence(directory: Path) -> ProtocolSpec:
    report = read_json(directory / "summary.json")
    if isinstance(report, Mapping) and report.get("protocol_version") == "ced.research.v2":
        return _initial_v2_spec(directory)
    if report.get("method_id") != "B0":
        raise ValueError("initial protocol requires actual B0 foundation pilot")
    # A report can claim anything; completeness and quality come from raw artifacts.
    assignments = read_json(directory / "assignments.json")
    if len(assignments) != 120 or Counter(r["stratum_id"] for r in assignments) != (
        Counter({s: 10 for s in STRATA})
    ):
        raise ValueError("foundation requires all 120 balanced preregistered records")
    audit = audit_pilot(directory)
    if not audit["physical_reconstruction_valid"]:
        raise ValueError(f"foundation physical evidence invalid: {audit['errors']}")
    measured = audit["summary"]
    if measured["cost_publication_mismatches"] or measured["inflight_requests"]:
        raise ValueError("foundation request costs are inconsistent or unsettled")
    if (
        measured["blocked"]
        or measured["nominal_success_rate"] < 0.9
        or (
            measured["success_rate_all_assigned"] < 0.8
            or measured["safety_violations"] / 120 > 0.01
        )
    ):
        raise ValueError("NO_FEASIBLE_BASELINE; cannot accept initial protocol")
    pools = read_json(directory / "pools.json")
    expected = {"foundation": 120, "power": 120, "formal": 2400, "recovery": 200, "ood": 300}
    groups: set[str] = set(read_json(directory / "excluded-groups.json"))
    for name, count in expected.items():
        rows = pools.get(name, [])
        if len(rows) != count:
            raise ValueError(f"missing {name} pool evidence")
        for row in rows:
            group = row["scene"]["group_id"]
            if group in groups:
                raise ValueError("cross-pool scene group leakage")
            groups.add(group)
            if not row.get("perturbation"):
                raise ValueError("missing preregistered perturbation schedule")
    if pools["foundation"] != assignments:
        raise ValueError("pilot assignment/pool mismatch")
    source_hashes = read_json(directory / "source-hashes.json")
    for relative, digest in source_hashes.items():
        archived = directory / "source" / relative
        if (
            not archived.is_relative_to(directory)
            or not archived.is_file()
            or (file_hash(archived) != digest)
        ):
            raise ValueError("missing or drifted archived source evidence")
    model = ModelConfigSnapshot(**read_json(directory / "model-probe" / "model-frozen.json"))
    from scripts.probe_rgbd_model import verify_frozen_bundle

    if not verify_frozen_bundle(directory / "model-probe"):
        raise ValueError("model probe evidence is missing or drifted")
    if model.digest() != report.get("model_snapshot_hash"):
        raise ValueError("pilot model snapshot mismatch")
    opportunities = read_json(directory / "opportunities.json")
    if not opportunities:
        raise ValueError("missing fixed opportunity snapshots")
    ids = set()
    for item in opportunities:
        seed = OpportunitySeed.model_validate(item["seed"])
        if seed.opportunity_id in ids or seed.group_id not in {
            row["scene"]["group_id"] for row in pools["formal"]
        }:
            raise ValueError("opportunity identity is duplicate or outside formal pool")
        ids.add(seed.opportunity_id)
        hashes = item["payload_hashes"]
        if not hashes or content_digest(hashes) != seed.observation_hash:
            raise ValueError("opportunity snapshot hash mismatch")
        for relative, digest in hashes.items():
            path = (directory / relative).resolve()
            if not path.is_relative_to(directory.resolve()) or file_hash(path) != digest:
                raise ValueError("opportunity snapshot payload drift")
        # This proof is produced by the independent opportunity evaluator, not online.
        proof = item["independent_label_evidence"]
        expected_label = (
            "UNKNOWN"
            if not proof["sensor_and_identity_sufficient"]
            else ("VALID" if proof["geometry_safe"] and proof["within_validity"] else "INVALID")
        )
        if proof["rule_version"] != "rgbd.opportunity.v1" or seed.oracle_label != expected_label:
            raise ValueError("opportunity independent label mismatch")
    faults = read_json(directory / "recovery-faults.json")
    fault_groups = {row["scene"]["group_id"] for row in pools["recovery"]}
    if len(faults) != 200 or {r["group_id"] for r in faults} != fault_groups:
        raise ValueError("recovery requires all 200 independent frozen faults")
    for item in faults:
        # Full independent successful teacher traces must demonstrate recoverability.
        path = (directory / item["recoverability_evidence_path"]).resolve()
        if (
            not path.is_relative_to(directory.resolve())
            or file_hash(path) != (item["recoverability_evidence_hash"])
        ):
            raise ValueError("recoverability evidence missing or drifted")
        if not item.get("fault"):
            raise ValueError("missing fixed recovery fault parameters")
        from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
            CompletionCriteria,
            evaluate_evidence,
        )

        samples = [physical_sample(row) for row in read_json(path)]
        if (
            not samples
            or not evaluate_evidence(
                samples,
                CompletionCriteria("object", "target_region"),
                evaluation_start_step=samples[0].physics_step,
            ).success
        ):
            raise ValueError("fault recoverability requires independent successful trajectory")
    return ProtocolSpec(
        tcap_s=derive_tcap([r["wall_duration_s"] for r in audit["cases"] if r["success"]]),
        pool_hashes={name: content_digest(rows) for name, rows in pools.items()},
        model_snapshot_hash=model.digest(),
        opportunity_hash=content_digest(opportunities),
        recovery_fault_manifest_hash=content_digest(faults),
    )
