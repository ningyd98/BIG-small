"""Streaming reconstruction of complete teacher originals, independent of the live app.

This reader imports no collector factory, opens no runtime database and executes
no backend. Diagnostic source/geometry/physical results are separate from online
condition qualification. None is infinity in the registered nine-group reduction.
"""

from __future__ import annotations

import base64
import hashlib
import itertools
import json
import math
import struct
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from cloud_edge_robot_arm.contracts import ExecutionCheckpoint, RobotState, TaskStep
from cloud_edge_robot_arm.edge.evidence.conditions import (
    ConditionSpec,
    OnlineEvidenceSnapshot,
    evaluate_conditions,
)
from cloud_edge_robot_arm.edge.recovery.lifecycle import checkpoint_digest
from cloud_edge_robot_arm.research.native_archived_tracker import (
    _ArchivedTargetTracker,
    _validated_utc,
)
from cloud_edge_robot_arm.research.native_calibration_collection import (
    canonical,
    detached,
    digest,
    load_json,
    read_protocol,
    regular,
)
from cloud_edge_robot_arm.research.native_collection_grounding import (
    collection_bootstrap_evidence,
    collection_grounding_inputs,
    collection_unknown_row,
    release_reference_registration,
    validate_camera,
    validate_registration_handoff,
)
from cloud_edge_robot_arm.research.native_completion_calibration import (
    CompletionActionAssignmentV2,
    CompletionActionDiagnosticsV2,
    CompletionCalibrationDiagnosticsV2,
    CompletionGroupAssignmentV2,
    joint_completion_calibration_v2,
)
from cloud_edge_robot_arm.research.native_geometry_calibration import (
    full_rigid_geometry_errors,
    original_rgbd_fingerprint,
    reconstruct_truth_endpoint,
)
from cloud_edge_robot_arm.research.native_source_effect_graph import (
    validate_native_command_controls,
    validate_native_source_effect_graph,
)
from cloud_edge_robot_arm.research.raw_episode_v3 import (
    ActionFrameJoinV3,
    ClockDescriptorV3,
    FrameAcquisitionV3,
    RawCommandV3,
    RawEpisodeIdentityV3,
    RawIntervalV3,
    RawPhysicsStepV3,
    TypedActionSpanV3,
    _camera_hash,
    _owner_decode,
    _snapshot,
)
from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration
from cloud_edge_robot_arm.vision.native_completion import completion_metric_v2
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.owner_registration import (
    DeterministicGroundingPolicy,
    StepGroundingBinding,
    VisualOriginalPlan,
    _resolved_parameters,
    bind_step_grounding,
)
from cloud_edge_robot_arm.vision.pose_markers import detect_pose_marker
from cloud_edge_robot_arm.vision.worker_owner import grounded_worker_effect_conditions


@dataclass(frozen=True, slots=True)
class FullHorizonGroupDiagnostics:
    assignment_id: str
    source_complete: bool
    horizon_complete: bool
    geometry_complete: bool
    physical_outcome: dict[str, Any] | None
    diagnostic_score_m: float | None
    group_score: float | None
    actions: tuple[dict[str, Any], ...]
    reasons: tuple[str, ...]
    allocated_frames: int
    reconstructed_frames: int
    total_physics_steps: int
    fingerprints: tuple[str, ...]
    retained_unknown_conditions: tuple[str, ...]
    schema_version: str = "native.full-horizon.group.diagnostics.v1"
    native_qualification: str = "UNKNOWN"
    execution_admitted: bool = False
    legacy_utc_mapping: str = "UNAVAILABLE"
    evidence_scope: str = "READ_ONLY_ORIGINAL_RECONSTRUCTION"


def _require(condition: Any, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def _registered_lease_from_payload(payload):
    from cloud_edge_robot_arm.vision.worker_owner import WorkerLeaseObservation

    names = {f.name for f in fields(WorkerLeaseObservation)} | {"scope"}
    if (
        type(payload) is not dict
        or set(payload) != names
        or payload["scope"] != "WORKER_LEASE_SOURCE_ONLY"
    ):
        raise ValueError("complete registered preparation lease source required")
    values = {n: v for n, v in payload.items() if n != "scope"}
    for name in ("acquired_at", "observed_at", "expires_at"):
        values[name] = datetime.fromisoformat(values[name])
    return WorkerLeaseObservation(**values)


def _registered_preview_semantics(payload):
    result = json.loads(canonical(payload))
    # Only the two known current evaluation readings change during a fresh read.
    del result["evaluated_at"]
    del result["track"]["evaluated_at"]
    return result


def verify_registered_prepared_step(
    protocol: Path,
    prepared: Path,
    *,
    repository,
    source_root: Path,
    output: Path,
) -> dict[str, Any]:
    """重建仍新鲜的准备记录；不回拨时钟，不读作实际动作或完整历史轨迹。"""
    from datetime import UTC

    entered = datetime.now(UTC)

    from cloud_edge_robot_arm.research.native_calibration_collection import (
        fresh_directory,
        save_exclusive,
    )
    from cloud_edge_robot_arm.research.native_collection_application import (
        RegisteredPreparationAdmission,
        registered_preparation_admission,
        registered_preparation_context,
    )
    from cloud_edge_robot_arm.research.native_collection_grounding import (
        bootstrap_registered_collection_tracker_v1,
        registered_collection_grounding_preview_v1,
    )
    from cloud_edge_robot_arm.vision.owner_registration import (
        RegisteredGroundingFrameInputs,
        RegisteredGroundingPolicy,
        RegisteredPreparedStepBinding,
        _aware,
        _current_grounding_context,
        _registered_preparation_deadline,
        prepare_registered_step_binding,
    )
    from cloud_edge_robot_arm.vision.worker_owner import (
        pin_worker_source_inventory,
        read_visual_worker_lease,
    )

    registration = read_protocol(protocol)
    _require(
        registration["schema_version"] == "native.calibration.operational.v6",
        "v6 preparation required",
    )
    sources = registration["source_hashes"]
    pin_worker_source_inventory(source_root, sources, required_paths=frozenset(sources))
    envelope = load_json(prepared)
    _require(
        type(envelope) is dict and set(envelope) == {"schema_version", "content", "content_sha256"},
        "exact preparation record envelope required",
    )
    _require(
        envelope["schema_version"] == "native.registered.prepared-record.v1",
        "preparation record schema",
    )
    content = envelope["content"]
    _require(
        type(content) is dict
        and set(content)
        == {
            "protocol_sha256",
            "source_generation",
            "context",
            "started_at",
            "evaluated_at",
            "finished_at",
            "lease_before",
            "lease_after",
            "preview",
            "inputs",
            "policy",
            "binding",
            "admission",
        },
        "exact preparation content field set required",
    )
    _require(envelope["content_sha256"] == digest(content), "prepared content SHA mismatch")
    _require(
        content["protocol_sha256"] == digest(registration)
        and content["source_generation"] == registration["source_generation"],
        "prepared protocol/source mismatch",
    )
    ctx = registered_preparation_context(content["context"])
    original, cp, observation, state = (
        ctx[n] for n in ("original", "source_checkpoint", "observation", "robot_state")
    )
    _require(dict(original.source_hashes) == sources, "prepared original source differs")
    _require(
        cp.robot_state == state.model_dump(mode="json"),
        "prepared current state differs from checkpoint",
    )
    started, evaluated, finished = (
        _aware(datetime.fromisoformat(content[n]))
        for n in ("started_at", "evaluated_at", "finished_at")
    )
    now = entered
    _require(
        started <= evaluated <= finished <= now
        and 0 <= (now - observation.captured_at).total_seconds() < 5,
        "prepared current frame stale/future or recorded time reversed",
    )
    before, after = (
        _registered_lease_from_payload(content[n]) for n in ("lease_before", "lease_after")
    )
    _require(
        started <= before.observed_at <= after.observed_at <= evaluated,
        "recorded lease source readings differ from preparation boundaries",
    )
    for lease in (before, after):
        _require(
            lease.identity(
                episode_id=original.identity.episode_id,
                task_id=original.identity.task_id,
                plan_id=original.identity.plan_id,
                robot_id=original.identity.robot_id,
            )
            == original.identity,
            "recorded lease epoch/identity mismatch",
        )
    policy = RegisteredGroundingPolicy.from_payload(content["policy"])
    _same(
        policy.to_payload(),
        RegisteredGroundingPolicy.for_original(original, sources).to_payload(),
        "prepared fixed policy changed",
    )
    online = OnlineEvidenceSnapshot(
        observation,
        state,
        {},
        original.contract.plan_version,
        original.contract.command_seq,
        cp.checkpoint_hash,
    )
    _current_grounding_context(
        original,
        original_step_id=cp.current_step_id,
        online=online,
        source_checkpoint=cp,
        current_identity=original.identity,
        owner_revision=ctx["owner_revision"],
        state_generation=ctx["state_generation"],
        now=finished,
    )
    expires = _registered_preparation_deadline(
        original,
        original_step_id=cp.current_step_id,
        observation=observation,
        lease_source=after,
    )
    _require(
        original.registered_at
        <= observation.captured_at
        <= started
        <= evaluated
        <= finished
        < expires,
        "recorded original/frame/lease deadline invalid",
    )
    _require(now < expires, "prepared current original/frame/lease deadline expired")

    def rebuild(inputs, lease, evaluated_at):
        return prepare_registered_step_binding(
            original,
            original_step_id=cp.current_step_id,
            online=online,
            source_checkpoint=cp,
            current_identity=original.identity,
            owner_revision=ctx["owner_revision"],
            state_generation=ctx["state_generation"],
            lease_source=lease,
            grounding_inputs=inputs,
            grounding_policy=policy,
            now=evaluated_at,
        )

    inputs = (
        None
        if content["inputs"] is None
        else RegisteredGroundingFrameInputs.from_payload(content["inputs"])
    )
    binding = (
        None
        if content["binding"] is None
        else RegisteredPreparedStepBinding.from_payload(content["binding"])
    )
    _require((inputs is None) == (binding is None), "prepared input/binding availability differs")
    if binding is not None:
        _require(
            datetime.fromisoformat(binding.to_payload()["created_at"]) == evaluated,
            "prepared binding decision timestamp differs",
        )
        _require(now < binding.valid_until, "prepared binding expired")
        _same(
            binding.to_payload(),
            rebuild(inputs, after, evaluated).to_payload(),
            "prepared candidate/recipe/context differs",
        )
        _require(
            inputs.to_payload()["preview_sha256"] == digest(content["preview"]),
            "prepared preview digest mismatch",
        )
    admission = RegisteredPreparationAdmission.from_payload(content["admission"])
    _same(
        admission.to_payload(),
        registered_preparation_admission(
            original,
            online,
            inputs,
            binding,
            step_id=cp.current_step_id,
            now=evaluated,
            reason=None if binding is not None else content["preview"]["reason"],
        ).to_payload(),
        "prepared admission decision was not reconstructed",
    )
    for value in (content["preview"]["evaluated_at"], content["preview"]["track"]["evaluated_at"]):
        _require(
            observation.captured_at <= _aware(datetime.fromisoformat(value)) <= evaluated,
            "prepared preview recorded timestamp outside observation/preparation",
        )

    def current_lease():
        lease = read_visual_worker_lease(
            repository,
            job_id=original.identity.job_id,
            run_id=original.identity.run_id,
            worker_id=original.identity.worker_id,
            lease_id=original.identity.lease_id,
        )
        _require(
            lease.identity(
                episode_id=original.identity.episode_id,
                task_id=original.identity.task_id,
                plan_id=original.identity.plan_id,
                robot_id=original.identity.robot_id,
            )
            == original.identity,
            "current preparation lease epoch differs",
        )
        return lease

    initial_lease = current_lease()
    after_initial_join = datetime.now(UTC)
    _require(
        initial_lease.observed_at <= after_initial_join < min(expires, initial_lease.expires_at),
        "registered reader initial lease/frame deadline expired",
    )
    tracker = bootstrap_registered_collection_tracker_v1(
        ctx["reference_observation"],
        NativeGeometryRegistration(registration["geometry"]),
        source_root=source_root,
        source_hashes=sources,
    )
    preview = registered_collection_grounding_preview_v1(tracker, observation, state)
    _same(
        _registered_preview_semantics(content["preview"]),
        _registered_preview_semantics(preview.to_payload()),
        "independent current preview geometry/provenance differs",
    )
    fresh_inputs = (
        RegisteredGroundingFrameInputs.from_preview(
            preview, observation, NativeGeometryRegistration(registration["geometry"])
        )
        if preview.status == "DERIVED"
        else None
    )
    _require(
        (inputs is None) == (fresh_inputs is None),
        "independent registered input availability differs",
    )
    if inputs is not None:
        expected, actual = inputs.to_payload(), fresh_inputs.to_payload()
        del expected["preview_sha256"], actual["preview_sha256"]
        _same(expected, actual, "independent registered input source/geometry differs")
    pin_worker_source_inventory(source_root, sources, required_paths=frozenset(sources))
    reason, _ = tracker._provider._recheck_current(observation)
    _require(reason is None, "registered reader final frame stale/invalid: " + str(reason))
    lease = current_lease()
    current_evaluated = datetime.now(UTC)
    current_deadline = min(
        expires,
        _registered_preparation_deadline(
            original,
            original_step_id=cp.current_step_id,
            observation=observation,
            lease_source=lease,
        ),
    )
    _require(
        lease.observed_at <= current_evaluated < current_deadline,
        "registered reader current original/frame/lease deadline expired",
    )
    if binding is not None:
        _require(
            current_evaluated < binding.valid_until,
            "prepared binding expired during reconstruction",
        )
        fresh_binding = rebuild(fresh_inputs, lease, current_evaluated)
        _same(
            fresh_binding.grounded_step.model_dump(mode="json"),
            binding.grounded_step.model_dump(mode="json"),
            "independent current numerical candidate differs",
        )
    reason, final_checked = tracker._provider._recheck_current(observation)
    _require(
        reason is None and current_evaluated <= final_checked < current_deadline,
        "registered reader final source/frame/lease deadline stale or expired",
    )
    if binding is not None:
        _require(
            final_checked < binding.valid_until, "prepared binding expired after reconstruction"
        )
    result = dict(
        status="PREPARED_CANDIDATE_RECONSTRUCTED"
        if binding is not None
        else "PREPARATION_UNKNOWN_RECONSTRUCTED",
        record_sha256=digest(envelope),
        binding_sha256=None if binding is None else binding.digest(),
        source_generation=registration["source_generation"],
        execution_admitted=False,
        native_authority="UNAVAILABLE",
        formal="NOT_ACCEPTED",
        reader_scope="CURRENT_FRAME_SOURCE_CONSISTENCY_ONLY",
    )
    canonical(result)
    publication_check = datetime.now(UTC)
    _require(
        final_checked <= publication_check < current_deadline,
        "registered reader publication deadline expired",
    )
    if binding is not None:
        _require(publication_check < binding.valid_until, "prepared publication binding expired")
    destination = fresh_directory(output)
    save_exclusive(destination / "verification.json", result)
    return result


def _same(left: Any, right: Any, reason: str) -> None:
    _require(canonical(detached(left)) == canonical(detached(right)), reason)


def _path(root: Path, name: str) -> Path:
    _require(
        isinstance(name, str)
        and name
        and not Path(name).is_absolute()
        and ".." not in Path(name).parts,
        "original path escapes assigned root",
    )
    return regular(root / name)


def _sha_file(path: Path) -> str:
    checksum = hashlib.sha256()
    with regular(path).open("rb") as stream:
        while block := stream.read(1 << 20):
            checksum.update(block)
    return checksum.hexdigest()


def _restore_frame(root: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct the exact payload, including null/missing distinctions."""
    frame: object = json.loads(canonical(metadata["frame"]))
    if not isinstance(frame, dict) or any(not isinstance(key, str) for key in frame):
        raise ValueError("original frame must be a string-keyed JSON object")
    payload = frame["observation_payload"]
    if payload is None:
        _require(not metadata["encoded_fields"], "failed frame has encoded replacements")
        return frame
    for field, name in metadata["encoded_fields"].items():
        _require(field not in payload, "encoded field duplicated in metadata")
        value = base64.b64encode(_path(root, name).read_bytes()).decode()
        _require(
            hashlib.sha256(value.encode()).hexdigest() == metadata["encoded_string_sha256"][field],
            "original encoded field hash mismatch",
        )
        payload[field] = value
    _require(
        digest(payload) == metadata["observation_payload_sha256"],
        "full original frame roundtrip mismatch",
    )
    observation = RGBDObservation.model_validate(payload)
    _same(
        observation.model_dump(mode="json"), payload, "original RGBD field set or checksum changed"
    )
    for name, sha in frame["file_hashes"].items():
        _require(_sha_file(_path(root, name)) == sha, "frame original blob changed")
    return frame


def _bracket(value: dict[str, Any], domain: Any, deadline: int) -> None:
    _same(value["domain"], domain, "foreign operational domain")
    lo, hi = value["lower_ns"], value["upper_ns"]
    _require(
        type(lo) is int and type(hi) is int and 0 <= lo <= hi < deadline,
        "operational boundary expired or invalid",
    )


class _Audit:
    def __init__(self, protocol: dict[str, Any], assignment: dict[str, Any], root: Path) -> None:
        self.protocol, self.assignment, self.root = protocol, assignment, root
        self.directory = root / "originals"
        self.reasons: list[str] = []
        self.raw: dict[str, Any] = {}
        self.states: dict[int, Any] = {}
        self.intervals: dict[str, Any] = {}
        self.frames: dict[str, Any] = {}
        self.fingerprints: set[str] = set()
        self.geometry_errors: list[float] = []
        self.actions: list[dict[str, Any]] = []
        self.unknown: set[str] = set()
        self.source_ok = self.horizon_ok = self.geometry_ok = False
        self.physical: dict[str, Any] | None = None
        self.identity: Any = None
        self.original: Any = None
        self.reconstructed = 0
        self.scope = NativeGeometryRegistration(protocol["geometry"])
        self.sequences: list[int] = []
        self.policies: dict[str, Any] = {}
        self.decision_ok = False
        self.boundary_observations: dict[str, RGBDObservation] = {}
        self.tracker_clock_end_utc: datetime | None = None
        self.tracker_clock_end_ns: int | None = None
        self.tracker_clock_keys: set[tuple[str, int | None, str | None]] = set()
        self.registered_collection = (
            protocol.get("schema_version") == "native.calibration.operational.v7"
        )
        self.registered_tracker = None
        self.registered_preview_finished = None

    def action_span(self, payload):
        """按协议版本读取独立span，不跨版本解码或替换全局身份。"""
        if self.registered_collection:
            from cloud_edge_robot_arm.research.raw_episode_v3 import (
                RegisteredCollectionActionSpanV1,
            )

            _same(
                payload.get("identity"),
                self.identity.to_payload(),
                "registered span global identity differs",
            )
            return RegisteredCollectionActionSpanV1.from_payload(payload)
        return TypedActionSpanV3.from_json(
            json.dumps(dict(identity=self.identity.to_payload(), **payload))
        )

    def grounding_binding(self, payload):
        if self.registered_collection:
            from cloud_edge_robot_arm.vision.owner_registration import (
                RegisteredCollectionStepBinding,
            )

            return RegisteredCollectionStepBinding.from_payload(payload)
        return _owner_decode(StepGroundingBinding, payload)

    def issue(self, message: str) -> None:
        if message not in self.reasons:
            self.reasons.append(message)

    def read(self, name: str) -> Any:
        return load_json(_path(self.directory, name))

    def inventory(self) -> None:
        manifest = self.read("inventory.json")
        self.manifest = manifest
        _require(
            manifest["schema_version"]
            == (
                "native.registered.full-horizon.inventory.v1"
                if self.registered_collection
                else "native.full-horizon.inventory.v1"
            ),
            "inventory schema mismatch",
        )
        _same(
            digest(manifest["files"]),
            manifest["inventory_sha256"],
            "original inventory hash mismatch",
        )
        _require(
            len(manifest["files"]) == manifest["file_count"], "original inventory count mismatch"
        )
        names = {
            str(p.relative_to(self.directory)) for p in self.directory.rglob("*") if p.is_file()
        }
        _require(
            names == set(manifest["files"]) | {"inventory.json"}, "unlisted or missing originals"
        )
        count = 0
        for name, row in manifest["files"].items():
            file = _path(self.directory, name)
            _require(
                file.stat().st_size == row["bytes"] and _sha_file(file) == row["sha256"],
                "changed or missing original:" + name,
            )
            count += row["bytes"]
        _require(
            count == manifest["original_bytes"] and count <= self.protocol["settings"]["raw_bytes"],
            "raw byte budget or inventory mismatch",
        )
        self.raw = self.read("partial-originals.json")
        _same(
            self.raw["source_hashes"],
            self.protocol["source_hashes"],
            "original source generation differs",
        )
        _require(
            self.raw["source_scope"]
            == (
                "REGISTERED_MODEL_TEACHER_COLLECTION"
                if self.registered_collection
                else "TEACHER_COLLECTION"
            ),
            "foreign source scope",
        )
        if self.registered_collection:
            _same(
                self.raw["schema_version"],
                "native.registered.full-horizon.originals.v1",
                "registered originals schema differs",
            )

    def source(self) -> None:
        raw = self.raw
        startup = load_json(self.root / "startup.json")
        source = self.read("source-binding.json")
        self.identity = RawEpisodeIdentityV3.from_json(json.dumps(raw["identity"]))
        self.original = _owner_decode(VisualOriginalPlan, self.read("original-plan.json"))
        identity = self.identity
        _same(startup["assignment"], self.assignment, "wrong assigned original group")
        _same(startup["protocol_sha256"], digest(self.protocol), "startup registration changed")
        _same(source["protocol_sha256"], digest(self.protocol), "source registration changed")
        _same(
            source["source_generation"],
            self.protocol["source_generation"],
            "source generation changed",
        )
        _same(
            source["control_source"],
            "PIXELS_PROPRIO_REGISTERED_MODEL"
            if self.registered_collection
            else "PIXELS_PROPRIO_REGISTERED_CONSTANTS",
            "control provenance unavailable",
        )
        _same(source["truth"], "OFFLINE_LABELS_ONLY", "truth leaked into control source")
        _same(identity.owner_identity, self.original.identity, "raw owner differs from original")
        _same(
            identity.source_hashes, self.protocol["source_hashes"], "raw source inventory differs"
        )
        _require(
            identity.assignment_id == self.assignment["assignment_id"]
            and identity.source_kind == "GROUND_TRUTH_TEACHER"
            and identity.model_snapshot_hash is None,
            "legacy source mapping or no-model identity changed",
        )
        _same(
            identity.assignment_hash,
            digest(source["assignment_basis"]),
            "assignment hash base changed",
        )
        _same(
            source["assignment_basis"]["registered_assignment"],
            self.assignment,
            "assigned seed changed",
        )
        _same(
            identity.attempt_id,
            "attempt-" + digest(source["attempt_basis"]),
            "attempt hash base changed",
        )
        metadata = raw["reset_metadata"]
        _require(raw["reset_count"] == 1, "exactly one original RESET required")
        _same(identity.scene_hash, digest(metadata["scenario"]), "scene hash base changed")
        _same(identity.config_hash, digest(metadata["config"]), "config hash base changed")
        _same(
            identity.asset_hash,
            self.protocol["settings"]["marked_asset_sha256"],
            "marked asset changed",
        )
        _same(metadata["asset_hash"], identity.asset_hash, "reset asset mismatch")
        _require(metadata["scenario"]["seed"] == self.assignment["seed"], "reset seed differs")
        _require(metadata["config"]["physics_dt_s"] == 1 / 240, "nonregistered simulation grid")
        _same(identity.role_bundle_hash, digest(self.protocol["role"]), "teacher role changed")
        _same(self.original.role_bundle_hash, identity.role_bundle_hash, "original role differs")
        origin, deadline = startup["origin"], startup["deadline"]
        _same(source["origin"], origin, "origin refreshed at source binding")
        _same(source["deadline"], deadline, "original deadline refreshed")
        _same(deadline["origin"], origin, "deadline original event mismatch")
        _require(
            deadline["budget_ns"] == 1800 * 10**9
            and deadline["deadline_ns"] == origin["lower_ns"] + deadline["budget_ns"],
            "deadline extension",
        )
        self.domain, self.deadline = origin["domain"], deadline["deadline_ns"]
        _bracket(origin, self.domain, self.deadline)
        owner = source["source"]
        lease = owner["lease"]
        for key in ("job_id", "run_id", "worker_id", "lease_id", "attempt"):
            _same(
                lease[key],
                getattr(identity.owner_identity, key),
                "current lease owner mismatch:" + key,
            )
        _require(lease["attempt"] == 1, "assignment retry not permitted")
        _require(
            datetime.fromisoformat(lease["acquired_at"])
            <= datetime.fromisoformat(lease["observed_at"])
            < datetime.fromisoformat(lease["expires_at"]),
            "original UTC lease veto failed",
        )
        _same(
            self.original.contract.completion_criteria,
            ["object_placed", "placement_stable"],
            "completion criteria changed",
        )
        _require(
            [s.skill.value for s in self.original.contract.steps]
            == [row["skill"] for row in self.protocol["actions"]],
            "original eight-action sequence changed",
        )
        _require(
            not any(
                raw[key]
                for key in (
                    "failures",
                    "audit_failures",
                    "observer_failures",
                    "pending_operation_ids",
                )
            ),
            "source has retained failures or pending operations",
        )
        self.source_ok = True

    def physics(self) -> None:
        raw = self.raw
        reset = raw.get("reset")
        if reset is None:
            raise ValueError("original RESET unavailable")
        self.states = {0: reset["physics_state"]}
        _snapshot(self.states[0])
        identity = self.identity.to_payload() if self.identity else None
        descriptor = (
            ClockDescriptorV3.from_json(json.dumps(raw["descriptor"])) if identity else None
        )
        for item in raw["intervals"]:
            row = dict(item)
            if descriptor is not None:
                for side in ("start", "end"):
                    value = row[side]
                    row[side] = (
                        None
                        if value is None
                        else dict(
                            clock_domain_id=descriptor.clock_domain_id,
                            descriptor_hash=descriptor.digest(),
                            sequence=value[0],
                            mono_before_ns=value[1],
                            utc_at=value[2],
                            mono_after_ns=value[3],
                        )
                    )
                RawIntervalV3.from_json(json.dumps(dict(identity=identity, **row)))
            _require(item["interval_id"] not in self.intervals, "duplicate interval")
            self.intervals[item["interval_id"]] = item
            self.sequences.append(item["record_seq"])
        for number, row in enumerate(raw["physics"], 1):
            if identity:
                RawPhysicsStepV3.from_json(json.dumps(dict(identity=identity, **row)))
            state = row["post_state_payload"]
            _snapshot(state)
            _require(
                row["physics_step"] == number == state["physics_step"],
                "missing or reordered original physics",
            )
            _require(
                math.isclose(state["sim_time_s"], number / 240, rel_tol=1e-9, abs_tol=1e-9),
                "wrong physics grid",
            )
            previous = self.states[number - 1]
            _same(row["previous_state_hash"], digest(previous), "previous physics hash mismatch")
            control = row["control_payload"]
            _same(
                control["pre_joint_positions_rad"],
                previous["joint_positions_rad"],
                "control/previous joints mismatch",
            )
            _require(
                control["physics_step"] == number and control["episode_id"] == state["episode_id"],
                "control identity mismatch",
            )
            for target, current, bias, gain, actual, bounds in zip(
                control["applied_joint_targets_rad"],
                control["pre_joint_positions_rad"],
                control["pre_gravity_bias_nm"],
                control["actuator_gains"],
                control["control_rad"],
                control["actuator_ctrl_ranges"],
                strict=True,
            ):
                _require(gain > 0, "invalid actuator gain")
                expected = min(
                    bounds[1],
                    max(bounds[0], current + min(0.1, max(-0.1, target - current)) + bias / gain),
                )
                _require(
                    math.isclose(actual, expected, abs_tol=1e-9),
                    "original control equation mismatch",
                )
            interval = self.intervals[row["physics_interval_id"]]
            _require(
                interval["kind"] == "PHYSICS_STEP"
                and interval["start_step"] == number - 1
                and interval["end_step"] == number,
                "physics source interval mismatch",
            )
            purpose = self.intervals[row["purpose_interval_id"]]
            _require(
                purpose["start_step"] < number <= purpose["end_step"],
                "physical step outside its purpose",
            )
            if number <= 120:
                _require(purpose["kind"] == "SETTLE", "settle purpose mismatch")
            self.states[number] = state
            self.sequences.append(row["record_seq"])
        _require(
            len(self.states) - 1 == raw["total_physics_steps"],
            "actual physical denominator differs",
        )
        for row in raw["commands"]:
            if identity:
                RawCommandV3.from_json(json.dumps(dict(identity=identity, **row)))
            self.sequences.append(row["record_seq"])
            _require(
                row["parent_interval_id"] in self.intervals, "command parent source unavailable"
            )
            _require(
                row["command_payload"]["physics_step"] in self.states,
                "command without current physics",
            )
            if row["command_payload"]["type"] == "emergency_stop":
                _require(
                    self.intervals[row["parent_interval_id"]]["kind"] == "TERMINATION",
                    "STOP is outside termination",
                )
        commands = [row["command_seq"] for row in raw["commands"]]
        _require(
            commands == list(range(1, len(commands) + 1)), "missing or reordered original command"
        )
        self.fingerprints.add("episode:" + self.states[0]["episode_id"])
        validate_native_command_controls(
            raw,
            self.intervals,
            self.states,
            expected_delay_steps=0 if self.identity is not None else None,
        )

    def operations(self) -> None:
        rows = self.raw["operational_events"]
        ledger = self.raw["backend_operation_ledger"]
        _require([r["sequence"] for r in rows] == list(range(1, len(rows) + 1)), "D sequence gap")
        events = {r["operation_id"]: r for r in rows}
        indexed_ledger: dict[int, list[Any]] = {}
        for event in ledger:
            indexed_ledger.setdefault(event["operation_id"], []).append(event)
        _require(len(events) == len(rows), "duplicated source operation")
        _require(
            Counter((r["operation_id"], r["phase"]) for r in ledger)
            == Counter((r["operation_id"], phase) for r in rows for phase in ("BEGIN", "END")),
            "operation ledger gap",
        )
        for row in rows:
            _require(
                row["bracket"] is not None and row["error_type"] is None, "incomplete D operation"
            )
            _bracket(row["bracket"], self.domain, self.deadline)
            _same(row["bracket"]["event_identity"], row["token"], "D event identity mismatch")
            for event in indexed_ledger[row["operation_id"]]:
                _same(event["kind"], row["kind"], "operational kind mismatch")
                _same(
                    event["physics_step"],
                    row["begin_step"] if event["phase"] == "BEGIN" else row["end_step"],
                    "operation physical step mismatch",
                )
        for row in self.read("active-checks.json"):
            _bracket(row["current"], self.domain, self.deadline)
            _same(row["lease_id"], self.identity.owner_identity.lease_id, "guard crossed lease")
        guards = self.raw["guard_events"]
        _require(
            guards
            and guards[-1]["kind"] == "CLOSED"
            and not any("error" in r or "stop_error" in r for r in guards),
            "source guard failed or did not close",
        )
        validate_native_source_effect_graph(
            self.raw,
            self.intervals,
            self.states,
            {aid: self.read(name) for aid, name in self.raw["frame_sources"].items()},
            self.read("active-checks.json"),
            domain=self.domain,
            deadline=self.deadline,
            lease_id=self.identity.owner_identity.lease_id,
        )

    def frame(self, aid: str) -> tuple[Any, Any, Any]:
        metadata = self.read(self.raw["frame_sources"][aid])
        frame = _restore_frame(self.directory, metadata)
        if self.identity:
            FrameAcquisitionV3.from_json(
                json.dumps(dict(identity=self.identity.to_payload(), **frame))
            )
        _require(
            frame["acquisition_id"] == aid and frame["source_acquisition_id"] is None,
            "foreign or transformed frame",
        )
        observation = RGBDObservation.model_validate(frame["observation_payload"])
        validate_camera(observation, self.protocol["geometry"])
        interval = self.intervals[frame["interval_id"]]
        n = interval["start_step"]
        _require(
            interval["end_step"] == n
            and math.isclose(observation.sim_time_s, n / 240, abs_tol=1e-9),
            "frame crossed physical step",
        )
        state = self.states[n]
        _require(observation.episode_id == state["episode_id"], "foreign frame episode")
        _same(
            frame["joined_physics_observation_hash"], digest(state), "frame physical hash mismatch"
        )
        camera = frame["camera_state_payload"]
        _require(set(frame["pass_state_hashes"]) == {_camera_hash(camera)}, "render passes differ")
        _same(
            camera["qpos"][:7], state["joint_positions_rad"], "camera/proprioceptive state mismatch"
        )
        role = metadata["capture_source"]["role"]
        _require(
            role
            in {
                "IMPLICIT_SENSOR_CACHE_UPDATE",
                "REGISTERED_ACTION_BOUNDARY",
                "REGISTERED_PER_PHYSICS_STEP",
            },
            "unknown capture role",
        )
        source = metadata["capture_source"]
        _require(
            source["physics_step"] == n
            and frame["interval_id"] == f"operation-{source['operation_id']}",
            "capture operation join mismatch",
        )
        _same(
            source,
            self.raw["capture_source_roles"][str(source["operation_id"])],
            "capture role ledger differs",
        )
        expected_passes = 2 if role == "IMPLICIT_SENSOR_CACHE_UPDATE" else 3
        _require(
            metadata["pass_count"] == len(frame["pass_state_hashes"]) == expected_passes,
            "registered render count mismatch",
        )
        instances = _path(self.directory, f"frames/{aid}/instances.i32").read_bytes()
        _require(len(instances) == metadata["instance_count"] * 4, "instance byte count differs")
        if expected_passes == 3:
            _require(
                metadata["instance_ids_present"]
                and metadata["instance_labels_present"]
                and metadata["instances_available"]
                and metadata["instance_count"] == observation.width * observation.height,
                "required three-pass instance originals missing",
            )
            ids = set(struct.unpack(f"<{metadata['instance_count']}i", instances))
            _require(all(value >= -1 for value in ids), "unknown negative instance ID")
            _require(
                ids - {-1} <= {int(key) for key in metadata["instance_labels"]},
                "instance label original missing",
            )
        else:
            _require(
                metadata["instance_count"] == 0
                and metadata["instance_labels"] == {}
                and not metadata["instances_available"],
                "implicit capture instances were synthesized",
            )
        self.fingerprints.add(original_rgbd_fingerprint(frame["observation_payload"]))
        if role == "REGISTERED_ACTION_BOUNDARY":
            # Each read still validates the original bytes above. Reuse only their
            # immutable view so the tracker's initial-repeat semantics are preserved.
            if aid in self.boundary_observations:
                cached = self.boundary_observations[aid]
                _same(
                    cached.model_dump(mode="json"),
                    observation.model_dump(mode="json"),
                    "cached original boundary bytes changed",
                )
                observation = cached
            else:
                _require(len(self.boundary_observations) < 10, "unregistered explicit boundary")
                self.boundary_observations[aid] = observation
        return observation, metadata, state

    def render_accounting(self) -> int:
        accounting = self.raw.get("render_accounting", {})
        _require(
            accounting.get("schema_version") == "native.render.accounting.v1"
            and accounting.get("status") == "EXACT"
            and not accounting.get("unknown_operation_ids")
            and accounting.get("unrecorded_attempt_count") == 0,
            "render accounting is unavailable or only a lower bound",
        )
        attempts = accounting["attempts"]
        roles = self.raw["capture_source_roles"]
        _require(
            len(attempts) == accounting["attempt_count"] == len(roles) <= 12976 + 12962
            and len({row["operation_id"] for row in attempts}) == len(attempts),
            "render attempt denominator differs",
        )
        count = 0
        for row in attempts:
            source = roles[str(row["operation_id"])]
            expected = 2 if source["role"] == "IMPLICIT_SENSOR_CACHE_UPDATE" else 3
            _require(
                row["end_seen"] is True
                and row["complete_return"] is True
                and row["returned_pass_count"] == row["expected_pass_count"] == expected
                and row["result_source"] == "CAPTURE_END_RETURNED_PASSES",
                "render attempt lacks complete returned passes",
            )
            count += expected
        _require(
            count == accounting["known_completed_passes"] == accounting["exact_passes"]
            and count == self.raw["render_passes_observed"]
            and accounting["provenance"] == "CAPTURE_END_RETURNED_PASSES_BEFORE_PERSISTENCE",
            "render pass accounting differs",
        )
        return count

    def geometry(self) -> None:
        render_count = self.render_accounting()
        assigned = self.raw["allocated_frames"]
        _require(
            len(set(assigned)) == len(assigned) and set(assigned) == set(self.raw["frame_sources"]),
            "allocated frame missing or duplicated",
        )
        scheduled: list[int] = []
        roles: Counter[str] = Counter()
        observed_ids: set[str] = set()
        failures = []
        for aid in assigned:
            try:
                observation, metadata, state = self.frame(aid)
                _require(
                    observation.observation_id not in observed_ids, "original frame identity reused"
                )
                observed_ids.add(observation.observation_id)
                self.reconstructed += 1
                role = metadata["capture_source"]["role"]
                roles[role] += 1
                if role == "REGISTERED_PER_PHYSICS_STEP":
                    _require(
                        metadata["capture_source"]["sample_slot"] == state["physics_step"],
                        "sample slot differs from physics",
                    )
                    scheduled.append(state["physics_step"])
                else:
                    _require(
                        metadata["capture_source"]["sample_slot"] == len(scheduled),
                        "nonincrementing capture slot changed",
                    )
                _require(
                    metadata["capture_source"]["instances_requested"]
                    is (role != "IMPLICIT_SENSOR_CACHE_UPDATE"),
                    "capture request changed",
                )
                self.frames[aid] = dict(
                    step=state["physics_step"],
                    observation_id=observation.observation_id,
                    checksum_sha256=observation.checksum_sha256,
                    role=role,
                )
                self.sequences.append(metadata["frame"]["record_seq"])
                estimate = detect_pose_marker(observation, self.scope.pose_marker)
                _require(estimate.status == "OBSERVED", "marker unknown:" + estimate.reason)
                transform = np.asarray(self.protocol["geometry"]["marker_to_object"]).reshape(4, 4)
                rotation = (
                    np.asarray(estimate.rotation_marker_to_world).reshape(3, 3)
                    @ transform[:3, :3].T
                )
                center = np.asarray(estimate.marker_center_world_m) - rotation @ transform[:3, 3]
                errors = full_rigid_geometry_errors(
                    self.scope,
                    center.tolist(),
                    rotation.ravel().tolist(),
                    state["object_geom_position_m"],
                    state["object_geom_rotation_row_major"],
                )
                self.geometry_errors.append(errors.joint_geometry_error_m)
            except (ValueError, KeyError, TypeError, OSError) as error:
                failures.append(f"{aid}:{type(error).__name__}:{error}")
        _require(
            scheduled == list(range(1, self.raw["total_physics_steps"] + 1)),
            "required per-step three-pass slot missing",
        )
        _require(
            roles["REGISTERED_ACTION_BOUNDARY"] <= 16
            and roles["IMPLICIT_SENSOR_CACHE_UPDATE"] <= self.protocol["implicit_capture_budget"],
            "original capture budget exceeded",
        )
        _require(sum(roles.values()) == len(assigned), "failed frame remains in denominator")
        _require(
            3 * (roles["REGISTERED_ACTION_BOUNDARY"] + roles["REGISTERED_PER_PHYSICS_STEP"])
            + 2 * roles["IMPLICIT_SENSOR_CACHE_UPDATE"]
            == render_count,
            "actual render count mismatch",
        )
        _require(not failures, "allocated geometry incomplete:" + ";".join(failures[:12]))
        self.geometry_ok = len(self.geometry_errors) == len(assigned) > 0

    def horizons(self) -> None:
        raw = self.raw
        _require(
            len(raw["actions"]) == len(raw["horizons"]) == len(raw["allocated_actions"]) == 8,
            "all eight original actions required",
        )
        cursor = 120
        for action, receipt, registered in zip(
            raw["actions"], raw["horizons"], self.protocol["actions"], strict=True
        ):
            span = self.action_span(action)
            self.sequences.append(action["record_seq"])
            interval = self.intervals[action["interval_id"]]
            _same(span.original_plan.digest(), self.original.digest(), "action original changed")
            _require(span.grounding is not None, "pixel grounding missing from teacher action")
            _require(
                span.disposition == "RETURNED" and span.returned_result["success"] is True,
                "original controller unsuccessful",
            )
            _same(receipt["skill"], registered["skill"], "action order changed")
            _same(
                json.loads(receipt["horizon_json"]),
                registered["horizon"],
                "full horizon recipe changed",
            )
            _same(
                receipt["executed_step_sha256"],
                digest(action["executed_step_payload"]),
                "action payload hash differs",
            )
            _same(
                receipt["original_plan_sha256"], self.original.digest(), "receipt original changed"
            )
            _same(
                json.loads(receipt["controller_result_json"])["action_result"],
                span.returned_result,
                "controller result receipt differs",
            )
            _same(
                span.grounding.grounded_step.model_dump(mode="json"),
                action["executed_step_payload"],
                "executed payload differs from pixel binding",
            )
            _require(
                span.step_id == self.original.contract.steps[len(self.actions)].step_id
                and span.attempt == 1,
                "wrong original step or retry",
            )
            for command in raw["commands"][span.command_seq_start - 1 : span.command_seq_end - 1]:
                _require(
                    command["parent_interval_id"] == span.interval_id,
                    "command outside its exact action",
                )
            _require(
                receipt["dispatch_step"] == interval["start_step"] == cursor,
                "action dispatch ordering mismatch",
            )
            terminal = cursor + registered["horizon"]["total_steps"]
            _require(
                receipt["terminal_step"] == terminal
                and receipt["controller_return_step"] == interval["end_step"] <= terminal
                and receipt["complete"] is True
                and not receipt["reasons"]
                and receipt["failure_type"] is None,
                "incomplete or overrun full horizon",
            )
            hold = self.intervals[receipt["padding_interval_id"]]
            _require(
                hold["kind"] == "HOLD"
                and hold["start_step"] == interval["end_step"]
                and hold["end_step"] == terminal,
                "hold padding mixed with another action",
            )
            mappings = [
                row for row in raw["hold_mappings"] if row["interval_id"] == hold["interval_id"]
            ]
            _require(
                len(mappings) == 1
                and mappings[0]["action_span_id"] == span.span_id
                and mappings[0]["semantic_kind"] == "FULL_HORIZON_HOLD",
                "full HOLD meaning unavailable",
            )
            _require(
                self.frames[receipt["terminal_acquisition_id"]]["step"] == terminal,
                "terminal frame is not at full H",
            )
            before = [
                row
                for row in raw["joins"]
                if row["span_id"] == span.span_id and row["relation"] == "BEFORE_SUBMIT"
            ]
            _require(
                len(before) == 1 and self.frames[before[0]["acquisition_id"]]["step"] == cursor,
                "capture/dispatch source mismatch",
            )
            if receipt["skill"] == "LIFT":
                _require(
                    span.returned_result["details"].get("contact_hold_s", 0) >= 0.5,
                    "original lift tail missing",
                )
            if receipt["skill"] == "RELEASE":
                _require(
                    terminal - interval["end_step"] >= 240, "release open-return tail incomplete"
                )
            self.actions.append(
                dict(
                    skill=receipt["skill"],
                    step_id=span.step_id,
                    capture_step=cursor,
                    dispatch_step=cursor,
                    terminal_step=terminal,
                    controller_return_step=interval["end_step"],
                    complete_horizon=True,
                    metric=None,
                    capture_acquisition_id=before[0]["acquisition_id"],
                    terminal_acquisition_id=receipt["terminal_acquisition_id"],
                )
            )
            cursor = terminal
        _require(
            cursor == self.protocol["physical_budget"] == raw["total_physics_steps"],
            "full physical denominator incomplete",
        )
        for join in raw["joins"]:
            ActionFrameJoinV3.from_json(
                json.dumps(dict(identity=self.identity.to_payload(), **join))
            )
            self.sequences.append(join["record_seq"])
            frame = self.frames[join["acquisition_id"]]
            _require(
                join["observation_id"] == frame["observation_id"]
                and join["checksum_sha256"] == frame["checksum_sha256"],
                "action frame identity changed",
            )
        _require(
            sorted(self.sequences) == list(range(1, len(self.sequences) + 1)),
            "raw record allocation gap",
        )
        self.horizon_ok = True

    def reference(self, reference: dict[str, Any]) -> dict[str, Any]:
        path = reference["path"]
        _same(
            _sha_file(_path(self.directory, path)),
            reference["sha256"],
            "decision original reference changed",
        )
        _same(
            self.manifest["files"][path]["sha256"],
            reference["sha256"],
            "decision reference absent from inventory",
        )
        value: object = self.read(path)
        if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
            raise ValueError("original reference must be a string-keyed JSON object")
        return value

    def consumption(self, row: dict[str, Any]) -> None:
        capture, current = row["capture"], row["consumed"]
        _bracket(capture, self.domain, self.deadline)
        _bracket(current, self.domain, self.deadline)
        _require(
            current["lower_ns"] >= capture["upper_ns"]
            and current["upper_ns"] - capture["lower_ns"] <= 5 * 10**9,
            "original frame consumption expired or reversed",
        )
        _require(
            row["step"] == self.frames[row["acquisition_id"]]["step"],
            "frame consumption S age is nonzero",
        )
        source = row["live_owner"]
        _same(
            source["lease"]["lease_id"],
            self.identity.owner_identity.lease_id,
            "consumption crossed lease",
        )
        _same(source["original_deadline_ns"], self.deadline, "consumption deadline refreshed")
        lease = source["lease"]
        _require(
            datetime.fromisoformat(lease["acquired_at"])
            <= datetime.fromisoformat(lease["observed_at"])
            < datetime.fromisoformat(lease["expires_at"]),
            "consumption UTC lease veto",
        )
        operation = next(
            r
            for r in self.raw["operational_events"]
            if r["acquisition_id"] == row["acquisition_id"]
        )
        _same(capture, operation["bracket"], "consumption does not reference actual acquisition")

    def tracker_clock(
        self,
        row: dict[str, Any],
        observation: RGBDObservation,
        *,
        purpose: str,
        index: int | None = None,
        step_id: str | None = None,
    ) -> datetime:
        """Verify original UTC and operational consumption before archived computation."""
        expected = dict(
            schema_version="native.tracker.clock.v1",
            purpose=purpose,
            index=index,
            step_id=step_id,
            observation_id=observation.observation_id,
            checksum_sha256=observation.checksum_sha256,
            source_generation=self.protocol["source_generation"],
        )
        for name, value in expected.items():
            _same(row[name], value, "original tracker clock differs:" + name)
        key = (purpose, index, step_id)
        _require(
            key not in self.tracker_clock_keys and len(self.tracker_clock_keys) < 27,
            "duplicate or excess tracker clock",
        )
        acquisition = row["acquisition"]
        aid = acquisition["acquisition_id"]
        _same(
            acquisition["path"], self.raw["frame_sources"][aid], "tracker acquisition path differs"
        )
        self.reference(acquisition)
        actual, _, _ = self.frame(aid)
        _same(
            actual.observation_id,
            observation.observation_id,
            "tracker acquisition identity differs",
        )
        _same(
            actual.checksum_sha256, observation.checksum_sha256, "tracker acquisition bytes differ"
        )
        started, evaluated, finished = (
            _validated_utc(datetime.fromisoformat(row[name]))
            for name in ("started_at", "evaluated_at", "finished_at")
        )
        _require(started <= evaluated <= finished, "tracker UTC order reversed")
        _require(
            -0.05 <= (evaluated - observation.captured_at).total_seconds() <= 5,
            "original tracker capture_time_not_fresh",
        )
        _require(
            self.original.contract.issued_at
            <= started
            <= finished
            < self.original.effective_deadline_at,
            "tracker outside original task validity",
        )
        before, after = row["consumption_before"], row["consumption_after"]
        source = self.read("source-binding.json")["source"]
        originals = self.read("capture-consumptions.json")
        for consumption in (before, after):
            self.consumption(consumption)
            _same(consumption["acquisition_id"], aid, "tracker consumption used different frame")
            _require(
                any(canonical(consumption) == canonical(item) for item in originals),
                "tracker consumption missing from originals",
            )
            owner = consumption["live_owner"]
            _same(owner["task_origin"], source["task_origin"], "tracker refreshed worker origin")
            _bracket(owner["current"], self.domain, self.deadline)
            _require(
                owner["current"]["upper_ns"] <= consumption["consumed"]["lower_ns"],
                "tracker owner read reversed",
            )
            lease = owner["lease"]
            for name in ("job_id", "run_id", "worker_id", "lease_id", "attempt", "acquired_at"):
                _same(lease[name], source["lease"][name], "tracker crossed original lease:" + name)
            acquired, expires = (
                _validated_utc(datetime.fromisoformat(lease[name]))
                for name in ("acquired_at", "expires_at")
            )
            _require(acquired <= started <= finished < expires, "tracker outside UTC lease")
        before_utc = _validated_utc(
            datetime.fromisoformat(before["live_owner"]["lease"]["observed_at"])
        )
        after_utc = _validated_utc(
            datetime.fromisoformat(after["live_owner"]["lease"]["observed_at"])
        )
        _require(
            before_utc <= started <= finished <= after_utc,
            "tracker not enclosed by source UTC reads",
        )
        _require(
            before["consumed"]["upper_ns"] <= after["live_owner"]["current"]["lower_ns"],
            "tracker operational consumption order reversed",
        )
        if self.tracker_clock_end_utc is not None:
            _require(self.tracker_clock_end_utc <= started, "tracker calls reversed in UTC")
        if self.tracker_clock_end_ns is not None:
            _require(
                self.tracker_clock_end_ns <= before["live_owner"]["current"]["lower_ns"],
                "tracker calls reversed operationally",
            )
        self.tracker_clock_end_utc = finished
        self.tracker_clock_end_ns = after["consumed"]["upper_ns"]
        self.tracker_clock_keys.add(key)
        return evaluated

    def lifecycle(self) -> None:
        result = load_json(regular(self.root / "collection-result.json"))
        _require(result["final_lifecycle_receipt"] is True, "final lifecycle unavailable")
        _require(
            result["assignment_id"] == self.assignment["assignment_id"], "foreign lifecycle result"
        )
        _same(
            result["source_generation"],
            self.protocol["source_generation"],
            "final generation changed",
        )
        for name in ("collection-body-result.json", "originals/inventory.json"):
            _same(
                result["lifecycle_links"][name],
                _sha_file(_path(self.root, name)),
                "final lifecycle link changed",
            )
        body = load_json(_path(self.root, "collection-body-result.json"))
        _require(not result["failures"] and not body["failures"], "retained lifecycle failure")
        _require(
            result["status"] == body["status"] == "COLLECTION_COMPLETE_WITH_UNRESOLVED_EFFECTS",
            "collection lifecycle did not complete",
        )
        _require(
            result["owner_closure"] == dict(attempted=True, completed=True),
            "operational owner did not close",
        )
        for flag in (
            "backend_initialized",
            "capture_entered",
            "recorder_entered",
            "guard_entered",
            "guard_exited",
            "freeze_completed",
            "recorder_close_completed",
            "capture_close_completed",
            "backend_shutdown_completed",
        ):
            _require(result["progress"].get(flag) is True, "unclosed lifecycle phase:" + flag)
        worker = result["worker_snapshot"]
        _require(
            worker["job"]["status"] == "SUCCEEDED" and not worker["job"]["error_message"],
            "worker publication did not complete",
        )
        _require(
            len(worker["attempts"]) == 1
            and worker["attempts"][0]["attempt"] == 1
            and worker["attempts"][0]["result"] == "SUCCEEDED"
            and worker["attempts"][0]["ended_at"] is not None,
            "sole worker attempt is incomplete",
        )
        _same(
            worker["job"]["job_id"],
            self.identity.owner_identity.job_id,
            "worker outcome belongs to another job",
        )
        _require(
            worker["events"]
            and all(r["job_id"] == worker["job"]["job_id"] for r in worker["events"]),
            "worker event chain unavailable",
        )
        _require(
            result["physics_steps"] == self.raw["total_physics_steps"] == body["physics_steps"],
            "final physics count differs",
        )
        count = self.render_accounting()
        for receipt in (result, body):
            _require(
                receipt["render_count_status"] == "EXACT"
                and receipt["render_passes"] == receipt["render_passes_lower_bound"] == count
                and receipt["render_count_provenance"]
                == "CAPTURE_END_RETURNED_PASSES_BEFORE_SHUTDOWN",
                "final render count differs",
            )
            _same(
                receipt["render_accounting"],
                self.raw["render_accounting"],
                "render accounting changed across lifecycle",
            )

    def registration_bootstraps(self) -> tuple[Any, Any]:
        timeline = self.read("registration-timeline.json")
        _require(
            timeline["schema_version"] == "native.registration.handoff.v1",
            "missing original handoff",
        )
        original = self.original
        for key, expected in dict(
            original_plan_sha256=original.digest(),
            registered_at=original.registered_at.isoformat(),
            identity=original.identity.to_payload(),
            contract_issued_at=original.contract.issued_at.isoformat(),
            task_deadline_at=original.task_deadline_at.isoformat(),
            verification_deadline_at=original.verification_deadline_at.isoformat(),
            source_generation=self.protocol["source_generation"],
        ).items():
            _same(timeline[key], expected, "registration original differs:" + key)
        source = self.read("source-binding.json")
        for key in ("origin", "deadline"):
            _same(timeline[key], source[key], "registration refreshed original " + key)
        for key in ("job_id", "run_id", "worker_id", "lease_id", "attempt", "acquired_at"):
            _same(
                timeline["lease"][key],
                source["source"]["lease"][key],
                "registration crossed source lease",
            )
        observations, bootstraps = [], []
        for key, filename in (
            ("bootstrap", "bootstrap.json"),
            ("dispatch", "dispatch-bootstrap.json"),
        ):
            row = timeline[key]
            aid = row["acquisition"]["acquisition_id"]
            _same(
                row["acquisition"]["path"],
                self.raw["frame_sources"][aid],
                "handoff mixed original acquisition",
            )
            self.reference(row["acquisition"])
            observation, metadata, _ = self.frame(aid)
            _require(
                metadata["capture_source"]["role"] == "REGISTERED_ACTION_BOUNDARY",
                "handoff is not explicit",
            )
            for name, expected in dict(
                observation_id=observation.observation_id,
                checksum_sha256=observation.checksum_sha256,
                captured_at=observation.captured_at.isoformat(),
                sim_time_s=observation.sim_time_s,
            ).items():
                _same(row[name], expected, "handoff acquisition changed:" + name)
            operations = [r for r in self.raw["operational_events"] if r["acquisition_id"] == aid]
            _require(len(operations) == 1, "handoff acquisition event unavailable")
            _same(row["bracket"], operations[0]["bracket"], "handoff event bracket differs")
            _bracket(row["bracket"], self.domain, self.deadline)
            _same(row["bootstrap"]["path"], filename, "mixed B/E bootstrap reference")
            clock_path = (
                "tracker-clock/" + ("bootstrap" if key == "bootstrap" else "dispatch") + ".json"
            )
            _same(row["tracker_clock"]["path"], clock_path, "mixed B/E tracker clock reference")
            clock = self.reference(row["tracker_clock"])
            evaluated = self.tracker_clock(
                clock, observation, purpose="BOOTSTRAP_B" if key == "bootstrap" else "BOOTSTRAP_E"
            )
            if key == "bootstrap":
                _require(
                    datetime.fromisoformat(clock["finished_at"]) <= original.registered_at,
                    "bootstrap tracker initialized after registration",
                )
            else:
                _require(
                    datetime.fromisoformat(timeline["checked_at"])
                    <= datetime.fromisoformat(clock["started_at"]),
                    "dispatch tracker initialized before handoff check",
                )
            evidence = collection_bootstrap_evidence(observation, self.protocol["geometry"])
            tracker = _ArchivedTargetTracker(observation, evidence, evaluated_at=evaluated)
            _same(
                evidence,
                self.reference(row["bootstrap"]),
                "original pixel bootstrap changed:" + key,
            )
            observations.append(observation)
            bootstraps.append((tracker, evidence))
        before, after = observations
        validate_registration_handoff(
            original,
            timeline["lease"],
            before,
            after,
            step_before=timeline["step_before"],
            step_after=timeline["step_after"],
            now=datetime.fromisoformat(timeline["checked_at"]),
        )
        b, e = timeline["bootstrap"], timeline["dispatch"]
        _require(
            b["acquisition"]["acquisition_id"] != e["acquisition"]["acquisition_id"]
            and b["bracket"]["upper_ns"] <= e["bracket"]["lower_ns"],
            "handoff order reversed",
        )
        _same(
            timeline["active_tracker_reference_acquisition_id"],
            e["acquisition"]["acquisition_id"],
            "wrong active tracker",
        )
        for dependency in original.dependencies:
            _same(
                dependency.evidence_ids,
                (before.observation_id,),
                "compiler used different bootstrap",
            )
        _same(
            self.actions[0]["capture_acquisition_id"],
            e["acquisition"]["acquisition_id"],
            "first action used pre-registration frame",
        )
        _same(
            self.raw["decisions"][0]["inputs"]["capture"]["acquisition_id"],
            e["acquisition"]["acquisition_id"],
            "first admission used pre-registration frame",
        )
        return bootstraps[1]

    def registered_preview(self, payload, observation, state):
        """重算原时间的像素/模型计算；不证明过去授权或当前freshness。"""
        from cloud_edge_robot_arm.research.native_archived_tracker import (
            _ArchivedRegisteredCollectionTracker,
        )
        from cloud_edge_robot_arm.research.native_calibration_collection import ROOT
        from cloud_edge_robot_arm.vision.owner_registration import RegisteredGroundingFrameInputs

        if self.registered_tracker is None:
            bootstrap = self.read("registered-tracker-bootstrap.json")
            _same(
                bootstrap["schema_version"],
                "native.registered.tracker-bootstrap.v1",
                "registered bootstrap schema differs",
            )
            _same(
                bootstrap["source_generation"],
                self.protocol["source_generation"],
                "registered bootstrap source differs",
            )
            acquisition = bootstrap["acquisition"]
            timeline = self.read("registration-timeline.json")
            _same(
                acquisition,
                timeline["dispatch"]["acquisition"],
                "registered reference is not dispatch bootstrap",
            )
            self.reference(acquisition)
            reference, _, _ = self.frame(acquisition["acquisition_id"])
            started = _validated_utc(datetime.fromisoformat(bootstrap["started_at"]))
            finished = _validated_utc(datetime.fromisoformat(bootstrap["finished_at"]))
            _require(
                reference.captured_at
                <= started
                <= finished
                < min(
                    self.original.effective_deadline_at,
                    reference.captured_at + timedelta(seconds=5),
                ),
                "registered bootstrap original time invalid",
            )
            self.registered_tracker = _ArchivedRegisteredCollectionTracker(
                reference,
                self.scope,
                source_root=ROOT,
                source_hashes=self.original.source_hashes,
                initialized_at=finished,
            )
            self.registered_preview_finished = finished
        evaluated = _validated_utc(datetime.fromisoformat(payload["track"]["evaluated_at"]))
        finished = _validated_utc(datetime.fromisoformat(payload["evaluated_at"]))
        _require(
            self.registered_preview_finished <= evaluated <= finished,
            "registered preview original sequence reversed",
        )
        rebuilt = self.registered_tracker.preview_at(
            observation, state, evaluated_at=evaluated, finished_at=finished
        )
        _same(rebuilt.to_payload(), payload, "registered preview original pixels/source differ")
        self.registered_preview_finished = finished
        return (
            RegisteredGroundingFrameInputs.from_preview(rebuilt, observation, self.scope)
            if rebuilt.status == "DERIVED"
            else None
        )

    def registered_grounding(self, grounding, observation, state, step, binding, index):
        """严格重建新绑定；所有时效只解释原记录，不发放当前执行权限。"""
        from cloud_edge_robot_arm.vision.owner_registration import (
            RegisteredCollectionStepBinding,
            RegisteredGroundingPolicy,
            prepare_registered_step_binding,
        )

        _same(
            grounding["schema_version"],
            "native.registered.grounding.v1",
            "registered grounding schema differs",
        )
        inputs = self.registered_preview(grounding["registered_preview"], observation, state)
        _require(inputs is not None, "registered grounding has no derived current model/region")
        _same(
            inputs.to_payload(),
            grounding["inputs"],
            "registered inputs differ from reconstructed pixels",
        )
        _same(inputs.digest(), grounding["inputs_sha256"], "registered inputs digest differs")
        policy = RegisteredGroundingPolicy.for_original(self.original, self.original.source_hashes)
        _same(policy.to_payload(), grounding["policy"], "registered collection policy differs")
        _same(policy.digest(), grounding["policy_sha256"], "registered policy digest differs")
        checkpoint = ExecutionCheckpoint.model_validate(grounding["checkpoint"])
        _same(
            checkpoint_digest(checkpoint),
            grounding["checkpoint_sha256"],
            "registered checkpoint hash differs",
        )
        _same(
            checkpoint.robot_state,
            state.model_dump(mode="json"),
            "registered checkpoint proprioception differs",
        )
        clock = grounding["tracker_clock"]
        preview_time = self.tracker_clock(
            clock, observation, purpose="GROUNDING", index=index, step_id=step.step_id
        )
        _same(
            grounding["tracker_evaluated_at"],
            clock["evaluated_at"],
            "registered tracker original time differs",
        )
        created = _validated_utc(datetime.fromisoformat(grounding["binding_now"]))
        final = _validated_utc(datetime.fromisoformat(grounding["final_validation_at"]))
        _require(
            datetime.fromisoformat(clock["started_at"])
            <= checkpoint.created_at
            <= checkpoint.updated_at
            <= preview_time
            <= created
            <= final
            <= datetime.fromisoformat(clock["finished_at"]),
            "registered binding original chronology differs",
        )
        lease = _registered_lease_from_payload(grounding["lease_source"])
        for source in (clock["consumption_before"], clock["consumption_after"]):
            actual = source["live_owner"]["lease"]
            for name in ("job_id", "run_id", "worker_id", "lease_id", "attempt", "acquired_at"):
                _same(
                    lease.to_payload()[name],
                    actual[name],
                    "registered grounding lease changed:" + name,
                )
        _require(
            lease.observed_at <= created <= final < lease.expires_at,
            "registered grounding lease expired",
        )
        online = OnlineEvidenceSnapshot(
            observation,
            state,
            {},
            self.original.contract.plan_version,
            self.original.contract.command_seq,
            checkpoint.checkpoint_hash,
        )
        _same(
            grounding["online"],
            dict(
                robot_state=state.model_dump(mode="json"),
                visual_facts={},
                plan_version=online.plan_version,
                command_seq=online.command_seq,
                context_hash=online.context_hash,
            ),
            "registered online source differs",
        )
        prepared = prepare_registered_step_binding(
            self.original,
            original_step_id=step.step_id,
            online=online,
            source_checkpoint=checkpoint,
            current_identity=self.original.identity,
            owner_revision=index + 1,
            state_generation=index + 1,
            grounding_inputs=inputs,
            grounding_policy=policy,
            lease_source=lease,
            now=created,
        )
        replay = RegisteredCollectionStepBinding.from_prepared(
            prepared, collection_policy_id="registered-model-collection-v1"
        )
        _require(final < replay.valid_until, "registered grounding final original deadline expired")
        _same(
            replay.to_payload(), binding.to_payload(), "registered grounding binding replay differs"
        )
        _same(replay.digest(), grounding["binding_sha256"], "registered binding digest differs")
        _same(
            step.model_dump(mode="json"),
            grounding["grounded_step"],
            "registered grounded payload differs",
        )
        _same(
            step.model_dump(mode="json"),
            replay.grounded_step.model_dump(mode="json"),
            "registered executed payload differs",
        )
        self.policies[step.skill.value] = policy

    def effect_conditions(self, binding):
        if self.registered_collection:
            from cloud_edge_robot_arm.vision.worker_owner import (
                registered_collection_effect_conditions,
            )

            return registered_collection_effect_conditions(self.original, binding)
        return grounded_worker_effect_conditions(self.original, binding)

    def admissions(self) -> None:
        from cloud_edge_robot_arm.edge.safety.models import SafetyContext
        from cloud_edge_robot_arm.vision.execution import research_safety_shield
        from cloud_edge_robot_arm.vision.tracking import _CONDITIONS

        rows = self.raw["decisions"]
        for row in rows:
            self.unknown.update(
                v["condition_name"] for v in row["inputs"]["verdicts"] if v["status"] == "UNKNOWN"
            )
        _require(len(rows) == 17, "complete PRE/POST/TERMINAL decision inventory required")
        tracker, evidence = self.registration_bootstraps()
        shield = research_safety_shield(self.protocol["settings"]["task_timeout_s"])
        config = self.read("shield/config.json")
        expected = _shield_recipe(shield, self.protocol["source_generation"])
        # The source hash is checked separately: legacy policy hashing uses frozenset repr,
        # whose process iteration order is not a portable decision recipe.
        _same(
            {k: v for k, v in config.items() if k != "policy_hash"},
            expected,
            "actual Shield recipe differs",
        )
        _require(
            config["policy_hash"] in _legacy_shield_hashes(config),
            "original Shield policy hash invalid",
        )
        for n, row in enumerate(rows):
            item, recorded = row["inputs"], row["decision"]
            index = min(n // 2, 7)
            phase = "TERMINAL" if n == 16 else "PRE" if n % 2 == 0 else "POST"
            _require(
                item["phase"] == phase
                and item["skill"] == self.protocol["actions"][index]["skill"],
                "decision order changed",
            )
            aid = item["capture"]["acquisition_id"]
            observation, _, physical = self.frame(aid)
            state = RobotState.model_validate(item["robot_state"])
            _same(
                [state.tcp_pose.x, state.tcp_pose.y, state.tcp_pose.z],
                physical["tcp_position_m"],
                "decision proprioception differs",
            )
            _require(
                state.connected and not state.estop_engaged and not state.collision_detected,
                "unsafe original proprioception",
            )
            self.consumption(item["capture"])
            step = TaskStep.model_validate(item["step"])
            binding = self.grounding_binding(item["grounding"])
            _same(
                binding.to_payload(),
                self.raw["actions"][index]["grounding"],
                "decision binding differs from executed action",
            )
            sources = item["shield_source"]
            grounding = self.reference(sources["grounding"])
            if phase == "PRE":
                _same(
                    grounding["acquisition"]["acquisition_id"],
                    aid,
                    "grounding used different pixels",
                )
                self.reference(grounding["acquisition"])
                _same(
                    grounding["original_plan_sha256"],
                    self.original.digest(),
                    "grounding original differs",
                )
                _same(
                    grounding["identity"],
                    self.original.identity.to_payload(),
                    "grounding identity differs",
                )
                _require(
                    grounding["index"] == index and grounding["step_id"] == step.step_id,
                    "grounding order differs",
                )
                ground_state = RobotState.model_validate(grounding["online"]["robot_state"])
                _same(
                    [ground_state.tcp_pose.x, ground_state.tcp_pose.y, ground_state.tcp_pose.z],
                    physical["tcp_position_m"],
                    "grounding proprioception differs",
                )
                if self.registered_collection:
                    self.registered_grounding(
                        grounding, observation, ground_state, step, binding, index
                    )
                else:
                    inputs = collection_grounding_inputs(
                        observation,
                        ground_state,
                        self.protocol["geometry"],
                        tracker=tracker,
                        evidence=evidence,
                        source_hashes=self.original.source_hashes,
                    )
                    _same(
                        inputs.to_payload(),
                        grounding["inputs"],
                        "saved grounding does not come from actual pixels",
                    )
                    _same(
                        inputs.digest(),
                        grounding["inputs_sha256"],
                        "grounding inputs digest differs",
                    )
                    policy = DeterministicGroundingPolicy(**grounding["policy"])
                    expected_policy = DeterministicGroundingPolicy(
                        "rgbd-top-grasp-v1",
                        "worker-rgbd-top-grasp-v1",
                        self.original.source_hashes,
                        min(0.15, self.original.contract.safety_constraints.max_tcp_velocity),
                        0.5,
                        0.10,
                        max(0.16, self.original.contract.safety_constraints.minimum_safe_height),
                    )
                    _same(policy, expected_policy, "nonregistered grounding policy")
                    _same(
                        policy.digest(),
                        grounding["policy_sha256"],
                        "grounding policy digest differs",
                    )
                    checkpoint = ExecutionCheckpoint.model_validate(grounding["checkpoint"])
                    _same(
                        checkpoint_digest(checkpoint),
                        grounding["checkpoint_sha256"],
                        "source checkpoint hash differs",
                    )
                    _same(
                        checkpoint.robot_state,
                        ground_state.model_dump(mode="json"),
                        "checkpoint proprioception differs",
                    )
                    ground_clock = grounding["tracker_clock"]
                    ground_time = self.tracker_clock(
                        ground_clock,
                        observation,
                        purpose="GROUNDING",
                        index=index,
                        step_id=step.step_id,
                    )
                    _same(
                        grounding["tracker_evaluated_at"],
                        ground_clock["evaluated_at"],
                        "grounding tracker time differs from actual source",
                    )
                    _require(
                        datetime.fromisoformat(ground_clock["started_at"])
                        <= datetime.fromisoformat(grounding["binding_now"])
                        <= ground_time
                        and datetime.fromisoformat(ground_clock["started_at"])
                        <= checkpoint.created_at
                        <= checkpoint.updated_at
                        <= ground_time,
                        "grounding checkpoint or binding time outside tracker call",
                    )
                    ground_facts = tracker.facts_at(
                        observation, ground_state, evaluated_at=ground_time
                    )
                    online = OnlineEvidenceSnapshot(
                        observation, ground_state, ground_facts, 1, 1, checkpoint.checkpoint_hash
                    )
                    _same(
                        grounding["online"],
                        dict(
                            robot_state=ground_state.model_dump(mode="json"),
                            visual_facts=ground_facts,
                            plan_version=1,
                            command_seq=1,
                            context_hash=checkpoint.checkpoint_hash,
                        ),
                        "online grounding input differs",
                    )
                    source_step = self.original.contract.steps[index]
                    resolved = _resolved_parameters(
                        source_step, self.original, online, inputs, policy
                    )
                    _same(
                        resolved,
                        step.parameters,
                        "compiled payload differs from pixel/proprioceptive grounding",
                    )
                    replay = bind_step_grounding(
                        self.original,
                        original_step_id=step.step_id,
                        grounded_step=step,
                        online=online,
                        source_checkpoint=checkpoint,
                        current_identity=self.original.identity,
                        owner_revision=index + 1,
                        state_generation=index + 1,
                        grounding_inputs=inputs,
                        grounding_policy=policy,
                        now=datetime.fromisoformat(grounding["binding_now"]),
                    )
                    _same(
                        replay.to_payload(),
                        binding.to_payload(),
                        "grounding binding replay differs",
                    )
                    _same(
                        grounding["binding_sha256"],
                        replay.digest(),
                        "grounding binding digest differs",
                    )
                    _same(
                        grounding["grounded_step"],
                        step.model_dump(mode="json"),
                        "grounded original step differs",
                    )
                    self.policies[step.skill.value] = policy
            admission_clock = item["tracker_clock"]
            admission_time = self.tracker_clock(
                admission_clock,
                observation,
                purpose="ADMISSION_" + phase,
                index=index,
                step_id=step.step_id,
            )
            _same(
                item["capture"],
                admission_clock["consumption_before"],
                "admission capture clock differs",
            )
            _require(
                admission_time
                <= datetime.fromisoformat(item["evaluation_at"])
                <= datetime.fromisoformat(admission_clock["finished_at"]),
                "condition evaluation outside recorded tracker call",
            )
            facts = tracker.facts_at(observation, state, evaluated_at=admission_time)
            _same(facts, item["facts"], "original visual facts differ from pixel replay")
            conditions = (
                self.original.requirements[step.step_id].preconditions
                if phase == "PRE"
                else self.effect_conditions(binding)
            )
            _same(conditions, item["conditions"], "canonical condition requirements changed")
            online = OnlineEvidenceSnapshot(observation, state, facts, 1, 1, self.original.digest())
            when = datetime.fromisoformat(item["evaluation_at"])
            if self.registered_collection:
                from cloud_edge_robot_arm.edge.evidence.conditions import (
                    evaluate_registered_pose_available,
                )

                registered_inputs = self.registered_preview(
                    item["registered_preview"], observation, state
                )
                _same(
                    registered_inputs.to_payload() if registered_inputs is not None else None,
                    item["registered_inputs"],
                    "registered admission model inputs differ",
                )
                pose_time = _validated_utc(
                    datetime.fromisoformat(item["registered_pose_evaluated_at"])
                )
                _require(
                    datetime.fromisoformat(item["capture"]["live_owner"]["lease"]["observed_at"])
                    <= datetime.fromisoformat(item["registered_preview"]["evaluated_at"])
                    <= pose_time
                    <= datetime.fromisoformat(admission_clock["started_at"]),
                    "registered supplemental condition outside original chronology",
                )
                pose = evaluate_registered_pose_available(
                    registered_inputs,
                    observation,
                    target_id=self.original.contract.task_target.object_id,
                    now=pose_time,
                )
                _same(
                    pose, item["registered_pose_verdict"], "registered supplemental verdict differs"
                )
                _require(pose.status.value == "PASS", "registered current pose unavailable")
                _same(
                    recorded["schema_version"],
                    "teacher.registered.collection.admission.v1",
                    "registered admission schema differs",
                )
                _require(
                    recorded["execution_admitted"] is False
                    and recorded["native_qualification"] == "UNKNOWN",
                    "registered admission falsely claims authority",
                )
            verdicts = evaluate_conditions(conditions, online, now=when)
            supplemental = evaluate_conditions(
                [
                    ConditionSpec("target_visible", "object"),
                    ConditionSpec("gripper_holding", "object"),
                    ConditionSpec("gripper_released", "object"),
                    ConditionSpec("robot_in_safe_pose", "object", {"minimum_safe_height": 0.0}),
                ],
                online,
                now=when,
            )
            _same(verdicts, item["verdicts"], "original condition verdict replay differs")
            _same(supplemental, item["supplemental"], "supplemental condition replay differs")
            status = {v.condition_name: v.status.value for v in [*verdicts, *supplemental]}
            source = self.reference(sources["input"])
            output = self.reference(sources["result"])
            _same(
                source["config"]["sha256"],
                _sha_file(self.directory / "shield/config.json"),
                "Shield config reference differs",
            )
            _same(
                output["input_sha256"],
                sources["input"]["sha256"],
                "Shield result belongs to different input",
            )
            _require(
                source["index"] == index and source["step_id"] == step.step_id,
                "Shield step differs",
            )
            _require(
                source["method"] == ("pre_check" if phase == "PRE" else "post_check"),
                "wrong Shield method",
            )
            _same(source["grounding"], sources["grounding"], "Shield grounding reference differs")
            _same(source["acquisition"]["acquisition_id"], aid, "Shield observation differs")
            if phase == "TERMINAL":
                _require(
                    sources["reused_from"] == "POST", "terminal must retain actual POST invocation"
                )
            context = SafetyContext.model_validate(source["context"])
            _same(
                context.parameters, step.parameters, "Shield checked different command parameters"
            )
            _same(
                context.contract.model_dump(mode="json"),
                grounding["executed_contract"],
                "Shield checked different contract",
            )
            _same(
                [context.tcp_x, context.tcp_y, context.tcp_z],
                physical["tcp_position_m"],
                "Shield TCP differs",
            )
            result = getattr(shield, source["method"])(context)
            _require(output["error_type"] is None, "original Shield invocation failed")
            _same(result, output["result"], "Shield original result replay differs")
            _same(result, item["shield"], "admission Shield result differs")
            _require(
                result.allowed
                and (not result.limited_parameters or result.limited_parameters == step.parameters),
                "Shield rejected or changed original command",
            )
            marker = detect_pose_marker(observation, self.scope.pose_marker)
            _require(
                marker.status == "OBSERVED" and status["target_visible"] == "PASS",
                "current visible marker unavailable",
            )
            _same(marker, item["marker"], "marker original changed")
            collection_grounding_inputs(
                observation,
                state,
                self.protocol["geometry"],
                tracker=tracker,
                evidence=evidence,
                source_hashes=self.original.source_hashes,
            )
            nominal = (
                _nominal_release(
                    tracker, observation, state, self.raw["actions"], self.raw["horizons"]
                )
                if phase == "PRE" and step.skill.value == "RELEASE"
                else False
            )
            full = phase != "PRE" and self.actions[index]["complete_horizon"]
            if phase == "TERMINAL":
                _require(
                    status["gripper_released"] == status["robot_in_safe_pose"] == "PASS",
                    "terminal proprioception failed",
                )
            whitelist, unknowns = [], []
            for verdict in verdicts:
                if verdict.status.value == "PASS":
                    continue
                unknowns.append(verdict.condition_name)
                row_name = collection_unknown_row(
                    phase=phase,
                    skill=step.skill.value,
                    condition=verdict.condition_name,
                    verdict=detached(verdict),
                    facts=facts,
                    holding=status["gripper_holding"] == "PASS",
                    tcp_reached=status.get("tcp_at_resolved_target") == "PASS",
                    full_horizon=bool(full),
                    nominal_release=nominal,
                    released=status["gripper_released"] == "PASS",
                    tracker_has_no_held="object_held" not in _CONDITIONS,
                    depth_bound_missing=tracker.depth_error_bound_m is None,
                )
                _require(row_name is not None, "UNKNOWN/FAIL is outside collection whitelist")
                whitelist.append(row_name)
            _require(
                recorded["allowed"] is True and not recorded["reasons"],
                "recorded collection was stopped",
            )
            _same(
                recorded["retained_unknown_conditions"], unknowns, "required UNKNOWN was rewritten"
            )
            _same(recorded["whitelist_rows"], whitelist, "collection admission whitelist differs")
            _same(
                recorded["original_inputs_sha256"],
                digest(item),
                "admission original digest differs",
            )
            _require(
                item["complete_horizon"] is bool(full)
                and item["nominal_collection_position_check"] is nominal,
                "admission common inputs changed",
            )
        for row in self.read("capture-consumptions.json"):
            self.consumption(row)
        _require(
            len(self.tracker_clock_keys) == 27, "complete original tracker clock inventory required"
        )
        self.decision_ok = True

    def physical_outcome(self) -> None:
        from cloud_edge_robot_arm.simulation.mujoco.backend import PhysicsStepObservation
        from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
            CompletionCriteria,
            evaluate_evidence,
            sample_physical_observation,
        )

        criteria = CompletionCriteria("object", "target_region")
        samples = [
            sample_physical_observation(PhysicsStepObservation(**state), criteria)
            for _, state in sorted(self.states.items())
        ]
        outcome = evaluate_evidence(samples, criteria, evaluation_start_step=120)
        self.physical = asdict(outcome)
        # Required hold windows are joined to their own action, not another later interval.
        if len(self.actions) != 8:
            self.physical.update(success=False, registered_windows_complete=False)
            return
        by_step = {s.physics_step: s for s in samples}
        lift = self.actions[3]
        tail = [by_step[n] for n in _holding_steps(lift)]
        baseline = by_step[lift["dispatch_step"]].object_position_m[2]
        lifted = all(
            s.object_position_m[2] - baseline >= 0.05 - 1e-12
            and s.left_finger_contact
            and s.right_finger_contact
            and not s.gripper_open
            and s.object_linear_speed_m_s <= 0.02
            and s.object_angular_speed_rad_s <= 0.5
            for s in tail
        )
        release = self.actions[6]
        tail = [by_step[n] for n in _holding_steps(release)]
        released = len(tail) >= 241 and all(
            s.gripper_open
            and not s.left_finger_contact
            and not s.right_finger_contact
            and s.object_linear_speed_m_s <= 0.02
            and s.object_angular_speed_rad_s <= 0.5
            and abs(s.object_bottom_z_m - s.table_height_m) <= 0.005
            and all(
                abs(s.object_position_m[i] - s.region_center_xy_m[i]) + s.object_half_extent_xy_m[i]
                <= s.region_half_extent_xy_m[i] + 1e-12
                for i in (0, 1)
            )
            for s in tail
        )
        grasp = self.actions[2]
        held = all(
            by_step[n].left_finger_contact
            and by_step[n].right_finger_contact
            and not by_step[n].gripper_open
            for n in range(grasp["controller_return_step"], grasp["terminal_step"] + 1)
        )
        self.physical.update(
            registered_lift_hold=lifted,
            registered_release_stability=released,
            registered_grasp_hold=held,
            registered_windows_complete=lifted and released and held,
            success=outcome.success and lifted and released and held,
        )

    def metrics(self) -> None:
        _require(
            self.geometry_ok and self.horizon_ok and self.decision_ok,
            "full independent metric inputs unavailable",
        )
        geometry = max(self.geometry_errors)
        for action, raw in zip(self.actions, self.raw["actions"], strict=True):
            skill = action["skill"]
            policy = self.policies[skill]
            capture = self.states[action["capture_step"]]
            step = TaskStep.model_validate(raw["executed_step_payload"])
            indices = _holding_steps(action)
            metrics = []
            for n in indices:
                current = self.states[n]
                if skill == "RELEASE":
                    place_reference = reconstruct_truth_endpoint(
                        self.scope,
                        self.policies["PLACE"],
                        "PLACE",
                        self.states[self.actions[5]["capture_step"]],
                    )
                    p, rc, rt, x = _release_points(
                        self.protocol,
                        self.raw["actions"][5],
                        self.raw["horizons"][5],
                        current,
                        correct_place_reference=place_reference,
                    )
                elif skill == "GRASP":
                    p = [capture["tcp_position_m"]]
                    rc = [_contact_reference(self.protocol["geometry"], capture)]
                    rt = [_contact_reference(self.protocol["geometry"], current)]
                    x = [current["tcp_position_m"]]
                else:
                    p = [[step.parameters["target_pose"][k] for k in "xyz"]]
                    rc = [reconstruct_truth_endpoint(self.scope, policy, skill, capture)]
                    rt = (
                        [reconstruct_truth_endpoint(self.scope, policy, skill, current)]
                        if skill in {"MOVE_ABOVE", "APPROACH"}
                        else rc
                    )
                    _require(rc[0] is not None and rt[0] is not None, "truth endpoint unavailable")
                    x = [current["tcp_position_m"]]
                metrics.append(
                    completion_metric_v2(
                        geometric_error_m=geometry,
                        command_points_m=p,
                        capture_reference_points_m=rc,
                        terminal_reference_points_m=rt,
                        actual_points_m=x,
                    )
                )
            worst = max(metrics, key=lambda metric: metric.completion_error_m)
            action.update(
                metric=asdict(worst),
                sampled_steps=list(indices),
                metric_sample_count=len(metrics),
                diagnostic_score_m=worst.completion_error_m,
            )


def _shield_recipe(shield: Any, generation: str) -> dict[str, Any]:
    config = shield.config
    hard = config.hard_limits.model_dump(mode="json")
    policy = config.operational_policy.model_dump(mode="json")
    for values in (hard, policy):
        if values["low_height_exception_skills"] is not None:
            values["low_height_exception_skills"] = sorted(values["low_height_exception_skills"])
    merged = {
        f.name: sorted(config.merged.low_height_exception_skills)
        if f.name == "low_height_exception_skills"
        else detached(getattr(config.merged, f.name))
        for f in fields(config.merged)
    }
    return dict(
        hard_limits=hard,
        operational_policy=policy,
        merged=merged,
        policy_version=config.policy_version,
        rule_count=shield.rule_count,
        source_generation=generation,
    )


def _legacy_shield_hashes(config: dict[str, Any]) -> set[str]:
    """Validate the old process-specific frozenset repr without weakening its recipe."""
    hashes = set()
    hard = dict(config["hard_limits"])
    for order in itertools.permutations(hard["low_height_exception_skills"]):
        hard["low_height_exception_skills"] = (
            "frozenset({" + ", ".join(repr(x) for x in order) + "})"
        )
        payload = json.dumps(
            dict(hard=hard, policy=config["operational_policy"]),
            sort_keys=True,
            separators=(",", ":"),
        )
        hashes.add(hashlib.sha256(payload.encode()).hexdigest()[:16])
    return hashes


def _nominal_release(
    tracker: Any, observation: Any, state: Any, actions: Any, horizons: Any
) -> bool:
    _require(
        len(actions) > 5
        and actions[5]["executed_step_payload"]["skill"] == "PLACE"
        and horizons[5]["complete"] is True,
        "matching successful PLACE unavailable",
    )
    target, _ = tracker._geometry(observation, tracker.target_color, target=True)
    region, _ = tracker._geometry(
        observation, tracker.destination_color, target=False, occlusion_geometry=target
    )
    if target is None or region is None:
        return False
    inside = all(
        target["min"][i] >= region["inner_min"][i] and target["max"][i] <= region["inner_max"][i]
        for i in (0, 1)
    )
    height = abs(
        target["center"][2] - tracker.initial["center"][2] - region["center"][2] + tracker.support_z
    )
    destination = actions[5]["executed_step_payload"]["parameters"]["target_pose"]
    tcp = math.dist(
        [state.tcp_pose.x, state.tcp_pose.y, state.tcp_pose.z], [destination[k] for k in "xyz"]
    )
    return bool(inside and height <= 0.012 and tcp <= 0.02)


def _contact_reference(geometry: dict[str, Any], state: dict[str, Any]) -> list[float]:
    center = np.asarray(state["object_geom_position_m"])
    rotation = np.asarray(state["object_geom_rotation_row_major"]).reshape(3, 3)
    offset = np.asarray(geometry["object_to_tcp"]).reshape(4, 4)[:3, 3]
    return [float(value) for value in center + rotation @ offset]


def read_native_full_horizon_group(
    protocol: Path, *, assignment_id: str, root: Path
) -> FullHorizonGroupDiagnostics:
    registration = read_protocol(protocol)
    if registration["schema_version"] == "native.calibration.operational.v7":
        raise ValueError(
            "registered collection has zero released groups; actual release requires a new run plan"
        )
    if registration["schema_version"] == "native.calibration.operational.v6":
        raise ValueError("v6 preparation has no full-horizon action release or raw action spans")
    assigned = [r for r in registration["assignments"] if r["assignment_id"] == assignment_id]
    _require(len(assigned) == 1, "foreign calibration assignment")
    audit = _Audit(registration, assigned[0], Path(root))
    source_failures = False
    phases = (
        "inventory",
        "source",
        "physics",
        "operations",
        "geometry",
        "horizons",
        "admissions",
        "physical_outcome",
        "metrics",
        "lifecycle",
    )
    for phase in phases:
        try:
            getattr(audit, phase)()
        except (
            ValueError,
            TypeError,
            KeyError,
            OSError,
            IndexError,
            AttributeError,
            ArithmeticError,
        ) as error:
            audit.issue(f"{phase}:{type(error).__name__}:{error}")
            if phase in {"inventory", "source", "physics", "operations", "admissions", "lifecycle"}:
                source_failures = True
    finite = [
        r["diagnostic_score_m"] for r in audit.actions if r.get("diagnostic_score_m") is not None
    ]
    score = max(finite) if len(finite) == 8 else None
    qualified = (
        score
        if not audit.reasons and not audit.unknown and audit.physical and audit.physical["success"]
        else None
    )
    if audit.unknown:
        audit.issue("required_canonical_effect_UNKNOWN")
    return FullHorizonGroupDiagnostics(
        assignment_id,
        audit.source_ok and not source_failures,
        audit.horizon_ok,
        audit.geometry_ok,
        audit.physical,
        score,
        qualified,
        tuple(audit.actions),
        tuple(audit.reasons),
        len(audit.raw.get("allocated_frames", [])),
        audit.reconstructed,
        audit.raw.get("total_physics_steps", 0),
        tuple(sorted(audit.fingerprints)),
        tuple(sorted(audit.unknown)),
    )


def reconstruct_native_full_horizon_registry(
    protocol: Path, *, roots: Mapping[str, Path], group_sink: Any = None
) -> CompletionCalibrationDiagnosticsV2:
    registration = read_protocol(protocol)
    if registration["schema_version"] == "native.calibration.operational.v7":
        raise ValueError("registered collection has no released full-horizon registry")
    if registration["schema_version"] == "native.calibration.operational.v6":
        raise ValueError(
            "v6 preparation requires its current-frame reader, not full-horizon verification"
        )
    _require(
        set(roots) <= {r["assignment_id"] for r in registration["assignments"]},
        "foreign registry group",
    )
    assignments, observations = [], {}
    for assigned in registration["assignments"]:
        group_id = assigned["assignment_id"]
        report = (
            read_native_full_horizon_group(protocol, assignment_id=group_id, root=roots[group_id])
            if group_id in roots
            else None
        )
        if group_sink is not None:
            group_sink(
                dict(assignment_id=group_id, state="NOT_RUN") if report is None else asdict(report)
            )
        fingerprints = {"seed:" + str(assigned["seed"])}
        if report:
            fingerprints.update(report.fingerprints)
            observations[group_id] = tuple(
                CompletionActionDiagnosticsV2(
                    row["skill"],
                    "COMPLETE" if report.group_score is not None else "UNKNOWN",
                    row["capture_step"],
                    row["dispatch_step"],
                    row["terminal_step"],
                    (("all-required-frames-points-and-holds", row.get("diagnostic_score_m")),),
                )
                for row in report.actions
            )
        assignments.append(
            CompletionGroupAssignmentV2(
                group_id,
                tuple(assigned["ancestors"]),
                tuple(sorted(fingerprints)),
                tuple(
                    CompletionActionAssignmentV2(
                        row["skill"],
                        row["horizon"]["total_steps"],
                        ("all-required-frames-points-and-holds",),
                    )
                    for row in registration["actions"]
                ),
            )
        )
    return joint_completion_calibration_v2(assignments, observations)


def _holding_steps(action: dict[str, Any]) -> range:
    d, a, t = (action[key] for key in ("dispatch_step", "controller_return_step", "terminal_step"))
    _require(
        all(type(n) is int for n in (d, a, t)) and 0 <= d <= a <= t,
        "invalid original action window",
    )
    start = t
    if action["skill"] == "GRASP":
        start = d
    elif action["skill"] == "LIFT":
        start = a - 120
        _require(start >= d, "controller lift tail is incomplete")
    elif action["skill"] == "RELEASE":
        start = a
        _require(t - a >= 240, "open-return release tail is incomplete")
    return range(start, t + 1)


def _release_points(
    protocol: dict[str, Any],
    place: dict[str, Any],
    receipt: dict[str, Any],
    current: dict[str, Any],
    *,
    correct_place_reference: Any,
) -> tuple[Any, Any, Any, Any]:
    registered = protocol["release_reference"]
    _same(
        registered,
        release_reference_registration(protocol["source_hashes"], protocol["geometry"]),
        "RELEASE reference convention changed",
    )
    step = place["executed_step_payload"]
    _require(
        step["skill"] == receipt["skill"] == "PLACE"
        and step["step_id"] == place["step_id"] == "step-6",
        "immediately preceding original PLACE required",
    )
    _require(
        place["disposition"] == "RETURNED"
        and place["returned_result"]["success"] is True
        and receipt["complete"] is True
        and not receipt["reasons"]
        and receipt["failure_type"] is None,
        "matching successful full PLACE required",
    )
    _same(digest(step), receipt["executed_step_sha256"], "PLACE exact payload differs")
    original = _owner_decode(VisualOriginalPlan, place["original_plan"])
    binding = _owner_decode(StepGroundingBinding, place["grounding"])
    _same(original.digest(), receipt["original_plan_sha256"], "PLACE original differs")
    _same(original.digest(), binding.original_plan_hash, "PLACE binding original differs")
    _same(binding.grounded_step.model_dump(mode="json"), step, "PLACE exact grounded step differs")
    _require(
        original.identity.episode_id == current["episode_id"], "PLACE belongs to another episode"
    )
    _require(
        correct_place_reference is not None
        and len(correct_place_reference) == 3
        and all(math.isfinite(v) for v in correct_place_reference),
        "independent correct PLACE reference unavailable",
    )
    grasp = np.asarray(registered["nominal_object_to_tcp"]).reshape(4, 4)
    command = np.eye(4)
    command[:3, :3] = np.asarray(registered["command_tcp_rotation"]).reshape(3, 3)
    command[:3, 3] = [step["parameters"]["target_pose"][key] for key in "xyz"]
    desired = command @ np.linalg.inv(grasp)
    reference = command.copy()
    reference[:3, 3] = correct_place_reference
    reference = reference @ np.linalg.inv(grasp)
    vertices = np.asarray(registered["vertices_object_m"])
    actual_rotation = np.asarray(current["object_geom_rotation_row_major"]).reshape(3, 3)
    _require(
        np.allclose(actual_rotation.T @ actual_rotation, np.eye(3), atol=1e-7)
        and math.isclose(float(np.linalg.det(actual_rotation)), 1, abs_tol=1e-7),
        "actual object rotation invalid",
    )
    p = vertices @ desired[:3, :3].T + desired[:3, 3]
    r = vertices @ reference[:3, :3].T + reference[:3, 3]
    x = vertices @ actual_rotation.T + np.asarray(current["object_geom_position_m"])
    return p.tolist(), r.tolist(), r.tolist(), x.tolist()
