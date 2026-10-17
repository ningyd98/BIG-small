"""Owned periodic capture, supervisor and baseline-wait source claims.

These pure records own local reservations only. Typed lease observations are
sources, never a cross-database transaction, action permit or UTC certificate.
The worker must read the real job/lease and immutable policy before and after
each effect. Pending costs survive restart and are never replayed or refunded.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, ClassVar, Literal, cast

from cloud_edge_robot_arm.contracts.models import (
    ActiveTaskContractRecord,
    ExecutionCheckpoint,
    RecoveryBudget,
    RobotState,
)
from cloud_edge_robot_arm.edge.recovery.lifecycle import VerificationBudgetRecord
from cloud_edge_robot_arm.repositories.event_autonomy.visual_bootstrap import (
    VisualBootstrapRecord,
    _lease,
    _lease_key,
    _load,
    _model,
    _plain,
)
from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
    VisualOwnerPublicationRecord,
    aware,
    canonical,
    counter,
    digest,
    original_from_payload,
    record_binding_valid,
    serialized_model,
    sha,
    validate_group,
)
from cloud_edge_robot_arm.repositories.event_autonomy.visual_verification import (
    camera_source_descriptor_sha256,
    current_models_exact,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.owner_registration import VisualOriginalPlan
from cloud_edge_robot_arm.vision.role_models import RoleModelBundle, RoleProviderSnapshot
from cloud_edge_robot_arm.vision.supervision import SupervisionContext, SupervisionDecision
from cloud_edge_robot_arm.vision.worker_owner import WorkerLeaseObservation, _identity_string

SUPERVISION_SOURCE_PATH = (
    "src/cloud_edge_robot_arm/repositories/event_autonomy/visual_supervision.py"
)
KINDS = frozenset(
    {
        "RESERVE_CAPTURE",
        "COMPLETE_CAPTURE",
        "RESERVE_PLAN",
        "COMPLETE_PLAN",
        "RESERVE_WAIT",
        "COMPLETE_WAIT",
    }
)


def _positive(value: Any) -> float:
    if type(value) not in {int, float} or not math.isfinite(value) or value <= 0:
        raise ValueError("finite positive source duration required")
    return float(value)


def _bundle(raw: dict[str, Any]) -> RoleModelBundle:
    if set(raw) != {
        "cloud_snapshot",
        "edge_provider_id",
        "edge_provider_hash",
        "device_pipeline_hash",
    }:
        raise ValueError("complete original role bundle required")
    cloud = raw["cloud_snapshot"]
    if set(cloud) != set(RoleProviderSnapshot.__dataclass_fields__):
        raise ValueError("complete concrete cloud snapshot required")
    result = RoleModelBundle(
        RoleProviderSnapshot(**cloud),
        raw["edge_provider_id"],
        raw["edge_provider_hash"],
        raw["device_pipeline_hash"],
    )
    if canonical(result.evidence()) != canonical(raw):
        raise ValueError("role snapshot source types changed")
    return result


@dataclass(frozen=True, init=False)
class VisualSupervisionDefinition:
    _json: str
    scope: ClassVar[str] = "SUPERVISION_SOURCE_ONLY"

    def __init__(
        self,
        *,
        original: VisualOriginalPlan,
        publication: VisualOwnerPublicationRecord,
        lease: WorkerLeaseObservation,
        task_started_at: datetime,
        task_timeout_s: float,
        supervision_period_s: float | None,
        model_snapshot_hash: str,
        role_bundle: RoleModelBundle,
        job_configuration_hash: str | None = None,
        operational_windows: list[dict[str, Any]] | None = None,
    ) -> None:
        if (
            type(original) is not VisualOriginalPlan
            or type(publication) is not VisualOwnerPublicationRecord
            or type(lease) is not WorkerLeaseObservation
            or type(role_bundle) is not RoleModelBundle
        ):
            raise ValueError("concrete original/publication/lease/role sources required")
        body = _plain(
            dict(
                schema_version="visual.supervision.definition.v1",
                scope=self.scope,
                original=original.to_payload(),
                publication=publication.to_payload(),
                lease=lease.to_payload(),
                task_started_at=task_started_at,
                task_timeout_s=task_timeout_s,
                supervision_period_s=supervision_period_s,
                model_snapshot_hash=model_snapshot_hash,
                role_bundle=role_bundle.evidence(),
                job_configuration_hash=job_configuration_hash,
            )
        )
        if operational_windows is not None:
            body["operational_windows"] = operational_windows
        self._validate(body)
        object.__setattr__(self, "_json", canonical(body))

    @staticmethod
    def _validate(body: dict[str, Any]) -> None:
        if "operational_windows" in body:
            from cloud_edge_robot_arm.vision.operational_windows import _validate_references

            _validate_references(body["operational_windows"])
        if set(body) - {"operational_windows"} != {
            "schema_version",
            "scope",
            "original",
            "publication",
            "lease",
            "task_started_at",
            "task_timeout_s",
            "supervision_period_s",
            "model_snapshot_hash",
            "role_bundle",
            "job_configuration_hash",
        }:
            raise ValueError("complete supervision definition required")
        if (
            body["schema_version"] != "visual.supervision.definition.v1"
            or body["scope"] != "SUPERVISION_SOURCE_ONLY"
        ):
            raise ValueError("fixed supervision definition scope required")
        original = original_from_payload(body["original"])
        publication = VisualOwnerPublicationRecord.from_payload(body["publication"])
        lease = _lease(body["lease"])
        bundle = _bundle(body["role_bundle"])
        start = aware(datetime.fromisoformat(body["task_started_at"]))
        timeout = _positive(body["task_timeout_s"])
        if body["supervision_period_s"] is not None:
            _positive(body["supervision_period_s"])
        sha(body["model_snapshot_hash"])
        if body["job_configuration_hash"] is not None:
            sha(body["job_configuration_hash"])
        identity = lease.identity(
            episode_id=original.identity.episode_id,
            task_id=original.identity.task_id,
            plan_id=original.identity.plan_id,
            robot_id=original.identity.robot_id,
        )
        limits = publication.verification_budget.state.limits
        try:
            task_end = start + timedelta(seconds=timeout)
            verification_end = min(task_end, start + timedelta(seconds=limits.deadline_s))
        except OverflowError as error:
            raise ValueError("original supervision clock exceeds range") from error
        if (
            identity != original.identity
            or publication.identity != identity
            or publication.original_plan_hash != original.digest()
            or bundle.digest() != original.role_bundle_hash
            or any(
                original.source_hashes.get(k) != v
                for k, v in bundle.cloud_snapshot.source_hashes.items()
            )
            or not lease.acquired_at
            <= start
            <= original.registered_at
            <= lease.observed_at
            < lease.expires_at
            or task_end != original.task_deadline_at
            or verification_end != original.verification_deadline_at
            or publication.verification_budget.state.deadline_at != verification_end
        ):
            raise ValueError("supervision original identity/policy/deadline source changed")

    @classmethod
    def from_payload(cls, body: dict[str, Any]) -> VisualSupervisionDefinition:
        copied = _load(canonical(_plain(body)))
        cls._validate(copied)
        result = object.__new__(cls)
        object.__setattr__(result, "_json", canonical(copied))
        return result

    def to_payload(self) -> dict[str, Any]:
        return _load(self._json)

    def digest(self) -> str:
        return digest(self.to_payload())

    @property
    def original(self) -> VisualOriginalPlan:
        return original_from_payload(self.to_payload()["original"])

    @property
    def task_id(self) -> str:
        return self.original.identity.task_id

    @property
    def deadline_at(self) -> datetime:
        return self.original.effective_deadline_at

    @property
    def max_periodic_captures(self) -> int:
        body = self.to_payload()
        period = body["supervision_period_s"]
        if period is None:
            return 0
        duration = (
            self.deadline_at - datetime.fromisoformat(body["task_started_at"])
        ).total_seconds()
        # Periodic candidates strictly precede the inherited absolute deadline.
        return max(0, math.ceil(duration / float(period)) - 1)


@dataclass(frozen=True, init=False)
class VisualSupervisionTransitionInput:
    _json: str
    scope: ClassVar[str] = "SUPERVISION_SOURCE_ONLY"

    def __init__(
        self,
        *,
        record: VisualSupervisionRecord,
        original: VisualOriginalPlan,
        publication: VisualOwnerPublicationRecord,
        lease: WorkerLeaseObservation,
        robot_state: RobotState,
        step_id: str,
        cursor: int,
        kind: str,
        event_key: str,
        model_snapshot_hash: str,
        role_bundle: RoleModelBundle,
        claim_id: str | None = None,
        observation: RGBDObservation | None = None,
        context: SupervisionContext | None = None,
        decision: SupervisionDecision | None = None,
        wait_duration_s: float | None = None,
        wait_elapsed_s: float | None = None,
        operational_windows: list[dict[str, Any]] | None = None,
    ) -> None:
        if (
            type(record) is not VisualSupervisionRecord
            or type(original) is not VisualOriginalPlan
            or type(publication) is not VisualOwnerPublicationRecord
            or type(lease) is not WorkerLeaseObservation
            or type(role_bundle) is not RoleModelBundle
        ):
            raise ValueError("concrete complete supervision transition sources required")
        body = _plain(
            dict(
                schema_version="visual.supervision.transition.v1",
                scope=self.scope,
                task_id=original.identity.task_id,
                definition_hash=record.definition.digest(),
                expected_revision=record.revision,
                expected_record_hash=record.digest(),
                original=original.to_payload(),
                publication=publication.to_payload(),
                lease=lease.to_payload(),
                robot_state=_model(robot_state, RobotState),
                step_id=step_id,
                cursor=cursor,
                kind=kind,
                event_key=event_key,
                model_snapshot_hash=model_snapshot_hash,
                role_bundle=role_bundle.evidence(),
                claim_id=claim_id,
                observation=_model(observation, RGBDObservation)
                if observation is not None
                else None,
                context=_model(context, SupervisionContext) if context is not None else None,
                decision=_model(decision, SupervisionDecision) if decision is not None else None,
                wait_duration_s=wait_duration_s,
                wait_elapsed_s=wait_elapsed_s,
            )
        )
        if operational_windows is not None:
            body["operational_windows"] = operational_windows
        self._validate(body)
        object.__setattr__(self, "_json", canonical(body))

    @staticmethod
    def _validate(body: dict[str, Any]) -> None:
        if "operational_windows" in body:
            from cloud_edge_robot_arm.vision.operational_windows import _validate_references

            _validate_references(body["operational_windows"])
        if set(body) - {"operational_windows"} != {
            "schema_version",
            "scope",
            "task_id",
            "definition_hash",
            "expected_revision",
            "expected_record_hash",
            "original",
            "publication",
            "lease",
            "robot_state",
            "step_id",
            "cursor",
            "kind",
            "event_key",
            "model_snapshot_hash",
            "role_bundle",
            "claim_id",
            "observation",
            "context",
            "decision",
            "wait_duration_s",
            "wait_elapsed_s",
        }:
            raise ValueError("complete supervision transition required")
        if (
            body["schema_version"] != "visual.supervision.transition.v1"
            or body["scope"] != "SUPERVISION_SOURCE_ONLY"
            or body["kind"] not in KINDS
        ):
            raise ValueError("fixed source transition kind/scope required")
        for name in ("task_id", "step_id", "event_key"):
            _identity_string(body[name])
        counter(body["expected_revision"])
        if counter(body["cursor"]) < 1:
            raise ValueError("positive original source cursor required")
        for name in ("definition_hash", "expected_record_hash", "model_snapshot_hash"):
            sha(body[name])
        original_from_payload(body["original"])
        VisualOwnerPublicationRecord.from_payload(body["publication"])
        _lease(body["lease"])
        serialized_model(body["robot_state"], RobotState)
        _bundle(body["role_bundle"])
        kind = body["kind"]
        required = {
            "RESERVE_CAPTURE": set(),
            "COMPLETE_CAPTURE": {"claim_id", "observation", "context"},
            "RESERVE_PLAN": {"claim_id"},
            "COMPLETE_PLAN": {"claim_id", "decision"},
            "RESERVE_WAIT": {"wait_duration_s"},
            "COMPLETE_WAIT": {"claim_id", "wait_elapsed_s"},
        }[kind]
        optional = {
            "claim_id",
            "observation",
            "context",
            "decision",
            "wait_duration_s",
            "wait_elapsed_s",
        }
        if {name for name in optional if body[name] is not None} != required:
            raise ValueError("exact phase-specific source receipt required")
        if body["claim_id"] is not None:
            sha(body["claim_id"])
        for name, model in (
            ("observation", RGBDObservation),
            ("context", SupervisionContext),
            ("decision", SupervisionDecision),
        ):
            if body[name] is not None:
                serialized_model(body[name], model)
        if body["wait_duration_s"] is not None:
            _positive(body["wait_duration_s"])
        elapsed = body["wait_elapsed_s"]
        if elapsed is not None and (
            type(elapsed) not in {int, float} or not math.isfinite(elapsed) or elapsed < 0
        ):
            raise ValueError("finite nonnegative measured wait source required")

    @classmethod
    def from_payload(cls, body: dict[str, Any]) -> VisualSupervisionTransitionInput:
        copied = _load(canonical(_plain(body)))
        cls._validate(copied)
        result = object.__new__(cls)
        object.__setattr__(result, "_json", canonical(copied))
        return result

    @classmethod
    def from_json(cls, raw: str) -> VisualSupervisionTransitionInput:
        return cls.from_payload(_load(raw))

    def to_payload(self) -> dict[str, Any]:
        return _load(self._json)

    def to_json(self) -> str:
        return self._json

    @property
    def task_id(self) -> str:
        return cast(str, self.to_payload()["task_id"])

    def digest(self) -> str:
        return digest(self.to_payload())

    def semantic_hash(self) -> str:
        body = self.to_payload()
        for name in ("event_key", "expected_revision", "expected_record_hash"):
            body.pop(name)
        body["lease"] = {
            k: body["lease"][k]
            for k in ("job_id", "run_id", "worker_id", "lease_id", "attempt", "acquired_at")
        }
        return digest(body)


def _start(definition: VisualSupervisionDefinition) -> dict[str, Any]:
    return dict(
        schema_version="visual.supervision.record.v1",
        scope="SUPERVISION_SOURCE_ONLY",
        definition=definition.to_payload(),
        revision=0,
        deadline_at=definition.deadline_at.isoformat(),
        max_periodic_captures=definition.max_periodic_captures,
        max_supervisor_calls=definition.max_periodic_captures,
        captures_reserved=0,
        supervisor_calls_reserved=0,
        last_capture_cursor=0,
        last_wait_cursor=0,
        wait_seconds_reserved=0.0,
        claims={},
        history=[],
    )


@dataclass(frozen=True, init=False)
class VisualSupervisionRecord:
    _json: str
    scope: ClassVar[str] = "SUPERVISION_SOURCE_ONLY"

    @classmethod
    def start(cls, definition: VisualSupervisionDefinition) -> VisualSupervisionRecord:
        return cls._trusted(_start(definition))

    @classmethod
    def _trusted(cls, body: dict[str, Any]) -> VisualSupervisionRecord:
        result = object.__new__(cls)
        object.__setattr__(result, "_json", canonical(_plain(body)))
        return result

    @classmethod
    def _from_verified_json(cls, raw: str) -> VisualSupervisionRecord:
        """Repository-local exact immutable-byte cache; changed bytes require full replay."""
        result = object.__new__(cls)
        object.__setattr__(result, "_json", raw)
        return result

    @classmethod
    def from_payload(cls, body: dict[str, Any]) -> VisualSupervisionRecord:
        copied = _load(canonical(_plain(body)))
        definition = VisualSupervisionDefinition.from_payload(copied["definition"])
        expected = _start(definition)
        if set(copied) != set(expected) or type(copied["history"]) is not list:
            raise ValueError("complete supervision history required")
        counter(copied["revision"])
        for event in copied["history"]:
            if set(event) != {"request", "committed_at"}:
                raise ValueError("complete source history event required")
            request = VisualSupervisionTransitionInput.from_payload(event["request"])
            expected, _ = _apply(
                expected, request, aware(datetime.fromisoformat(event["committed_at"]))
            )
        if canonical(expected) != canonical(copied):
            raise ValueError("source history cannot reproduce supervision costs and receipts")
        return cls._trusted(expected)

    @classmethod
    def from_json(cls, raw: str) -> VisualSupervisionRecord:
        return cls.from_payload(_load(raw))

    def to_payload(self) -> dict[str, Any]:
        return _load(self._json)

    def to_json(self) -> str:
        return self._json

    def digest(self) -> str:
        return digest(self.to_payload())

    @property
    def revision(self) -> int:
        return cast(int, self.to_payload()["revision"])

    @property
    def definition(self) -> VisualSupervisionDefinition:
        return VisualSupervisionDefinition.from_payload(self.to_payload()["definition"])


@dataclass(frozen=True)
class VisualSupervisionTransitionResult:
    record: VisualSupervisionRecord
    claim_id: str
    write_disposition: Literal["NEW_COMMIT", "HISTORICAL_DUPLICATE"]
    scope: ClassVar[str] = "SUPERVISION_SOURCE_ONLY"


def _claim_key(body: dict[str, Any]) -> str:
    domain = "WAIT" if "WAIT" in body["kind"] else "SUPERVISION"
    return digest(["visual.supervision.claim.v1", body["definition_hash"], domain, body["cursor"]])


def _apply(
    state: dict[str, Any], request: VisualSupervisionTransitionInput, now: datetime
) -> tuple[dict[str, Any], str]:
    body = request.to_payload()
    definition = VisualSupervisionDefinition.from_payload(state["definition"])
    original = original_from_payload(body["original"])
    publication = VisualOwnerPublicationRecord.from_payload(body["publication"])
    lease = _lease(body["lease"])
    robot = serialized_model(body["robot_state"], RobotState)
    frozen = definition.to_payload()
    start = aware(datetime.fromisoformat(frozen["task_started_at"]))
    if (
        body["expected_revision"] != state["revision"]
        or body["expected_record_hash"] != digest(state)
        or body["definition_hash"] != definition.digest()
        or body["task_id"] != definition.task_id
        or original.digest() != definition.original.digest()
        or canonical(body["role_bundle"]) != canonical(frozen["role_bundle"])
        or body["model_snapshot_hash"] != frozen["model_snapshot_hash"]
        or publication.original_plan_hash != original.digest()
        or publication.identity != original.identity
        or _lease_key(lease) != _lease_key(_lease(frozen["lease"]))
        or lease.acquired_at != _lease(frozen["lease"]).acquired_at
        or not start <= lease.observed_at <= now < min(lease.expires_at, definition.deadline_at)
        or publication.checkpoint.updated_at > now
        or body["step_id"] != publication.checkpoint.current_step_id
        or body["step_id"] in publication.checkpoint.completed_step_ids
        or body["step_id"] not in original.requirements
        or publication.verification_budget.state.exhausted_reason is not None
        or robot.estop_engaged
        or robot.collision_detected
        or not robot.connected
    ):
        raise ValueError("supervision current source/deadline/step/lease invalid")
    claim_id = _claim_key(body)
    kind, cursor = body["kind"], body["cursor"]
    claims = state["claims"]
    if kind in {"RESERVE_CAPTURE", "RESERVE_WAIT"}:
        if claim_id in claims:
            raise ValueError("existing source claim cannot reserve again")
        claim = dict(
            kind="WAIT" if kind == "RESERVE_WAIT" else "SUPERVISION",
            cursor=cursor,
            step_id=body["step_id"],
            publication_hash=publication.digest(),
            checkpoint_hash=publication.checkpoint.checkpoint_hash,
            state_generation=publication.state_generation,
            reserved_at=now.isoformat(),
            observation=None,
            context=None,
            decision=None,
            capture_completed_at=None,
            plan_reserved_at=None,
            plan_completed_at=None,
            model_snapshot_hash=body["model_snapshot_hash"],
            cloud_snapshot=frozen["role_bundle"]["cloud_snapshot"],
            cloud_snapshot_hash=_bundle(frozen["role_bundle"]).cloud_snapshot.digest(),
            source_hashes=dict(original.source_hashes),
            wait_duration_s=None,
            wait_elapsed_s=None,
            wait_completed_at=None,
        )
        if kind == "RESERVE_CAPTURE":
            period = frozen["supervision_period_s"]
            if (
                period is None
                or cursor <= state["last_capture_cursor"]
                or cursor > state["max_periodic_captures"]
                or start + timedelta(seconds=cursor * period) > now
                or state["captures_reserved"] >= state["max_periodic_captures"]
            ):
                raise ValueError("periodic capture original candidate allowance unavailable")
            state["captures_reserved"] += 1
            state["last_capture_cursor"] = cursor
            claim["status"] = "CAPTURE_PENDING"
        else:
            duration = _positive(body["wait_duration_s"])
            window = (definition.deadline_at - start).total_seconds()
            if (
                cursor <= state["last_wait_cursor"]
                or state["wait_seconds_reserved"] + duration > window
            ):
                raise ValueError("original baseline wait allocation exhausted")
            state["wait_seconds_reserved"] += duration
            state["last_wait_cursor"] = cursor
            claim.update(status="WAIT_PENDING", wait_duration_s=duration)
        claims[claim_id] = claim
    else:
        if body["claim_id"] != claim_id or claim_id not in claims:
            raise ValueError("exact owned claim receipt required")
        claim = claims[claim_id]
        if (
            claim["step_id"] != body["step_id"]
            or claim["publication_hash"] != publication.digest()
            or claim["checkpoint_hash"] != publication.checkpoint.checkpoint_hash
        ):
            raise ValueError("claim source context invalidated")
        if kind == "COMPLETE_CAPTURE":
            if claim["status"] != "CAPTURE_PENDING":
                raise ValueError("capture claim not pending")
            observation = serialized_model(body["observation"], RGBDObservation)
            context = serialized_model(body["context"], SupervisionContext)
            requirement = original.requirements[body["step_id"]]
            if (
                not aware(datetime.fromisoformat(claim["reserved_at"]))
                <= observation.captured_at
                <= now
                or observation.episode_id != original.identity.episode_id
                or not observation.calibration_version
                or context.episode_id != observation.episode_id
                or context.plan_version != original.contract.plan_version
                or context.state_version != publication.state_generation
                or context.next_step_id != body["step_id"]
                or context.next_skill != requirement.original_step.skill.value
                or context.observation_id != observation.observation_id
                or context.captured_at != observation.captured_at
            ):
                raise ValueError("capture receipt is not exact current episode/step/context")
            descriptor = camera_source_descriptor_sha256(observation)
            for spec in (*requirement.preconditions, *requirement.postconditions):
                wanted = spec.tolerances.get("camera_source_descriptor_sha256")
                calibration = spec.tolerances.get("calibration_version")
                if (wanted is not None and sha(wanted) != descriptor) or (
                    calibration is not None and calibration != observation.calibration_version
                ):
                    raise ValueError("original camera/calibration requirement changed")
            grounding = publication.to_payload()["grounding"]
            if (
                grounding is not None
                and grounding["calibration_version"] != observation.calibration_version
            ):
                raise ValueError("current grounded source calibration changed")
            if any(
                c["observation"] is not None
                and c["observation"]["observation_id"] == observation.observation_id
                for c in claims.values()
            ):
                raise ValueError("one capture source cannot be rebound to another claim")
            claim.update(
                status="CAPTURED",
                observation=body["observation"],
                context=body["context"],
                capture_completed_at=now.isoformat(),
            )
        elif kind == "RESERVE_PLAN":
            if (
                claim["status"] != "CAPTURED"
                or state["supervisor_calls_reserved"] >= state["max_supervisor_calls"]
                or (
                    now - datetime.fromisoformat(claim["observation"]["captured_at"])
                ).total_seconds()
                > original.requirements[body["step_id"]].ordinary_ttl_s
            ):
                raise ValueError("supervisor source allowance/frame unavailable")
            state["supervisor_calls_reserved"] += 1
            claim.update(status="PLAN_PENDING", plan_reserved_at=now.isoformat())
        elif kind == "COMPLETE_PLAN":
            if claim["status"] != "PLAN_PENDING":
                raise ValueError("supervisor claim not pending")
            context = claim["context"]
            for name in (
                "episode_id",
                "plan_version",
                "state_version",
                "observation_id",
                "next_step_id",
            ):
                if body["decision"][name] != context[name]:
                    raise ValueError("typed supervisor receipt changed exact captured context")
            if (
                now - datetime.fromisoformat(claim["observation"]["captured_at"])
            ).total_seconds() > (original.requirements[body["step_id"]].ordinary_ttl_s):
                raise ValueError("late supervisor receipt source expired")
            claim.update(
                status="PLAN_COMPLETE", decision=body["decision"], plan_completed_at=now.isoformat()
            )
        elif kind == "COMPLETE_WAIT":
            if (
                claim["status"] != "WAIT_PENDING"
                or body["wait_elapsed_s"] > claim["wait_duration_s"]
            ):
                raise ValueError("wait completion allocation source changed")
            claim.update(
                status="WAIT_COMPLETE",
                wait_elapsed_s=body["wait_elapsed_s"],
                wait_completed_at=now.isoformat(),
            )
    state["revision"] += 1
    state["history"].append(dict(request=body, committed_at=now.isoformat()))
    return state, claim_id


def current_supervision_publication(
    prior: VisualOwnerPublicationRecord,
    original: VisualOriginalPlan,
    active: ActiveTaskContractRecord | None,
    checkpoint: ExecutionCheckpoint | None,
    pool: VerificationBudgetRecord | None,
    retry: RecoveryBudget | None,
    ancestor: VisualOwnerPublicationRecord | None,
    *,
    now: datetime,
) -> bool:
    """Current literal source rows, without lending expired grounding action freshness.

    Binding validity is still checked at its immutable publication boundary.
    Only this observer path omits current grounding TTL; all original deadlines,
    checkpoint/pool hashes, full requirements and native action getters remain.
    """
    if (
        active is None
        or checkpoint is None
        or pool is None
        or retry is None
        or not current_models_exact(active, checkpoint, retry)
    ):
        return False
    try:
        validate_group(original, active, checkpoint, pool, retry)
        if not record_binding_valid(prior, original, ancestor):
            return False
        return (
            prior.to_payload()["contract_hash"] == active.contract_hash
            and canonical(prior.checkpoint.model_dump(mode="json"))
            == canonical(checkpoint.model_dump(mode="json"))
            and prior.verification_budget.content_hash == pool.detached().content_hash
            and canonical(prior.retry_budget.model_dump(mode="json"))
            == canonical(retry.model_dump(mode="json"))
            and aware(now) < min(prior.effective_deadline_at, original.effective_deadline_at)
        )
    except (ValueError, TypeError):
        return False


def validate_initial_supervision(
    definition: VisualSupervisionDefinition,
    original: VisualOriginalPlan,
    prior: VisualOwnerPublicationRecord,
    ancestor: VisualOwnerPublicationRecord | None,
    active: ActiveTaskContractRecord | None,
    checkpoint: ExecutionCheckpoint | None,
    pool: VerificationBudgetRecord | None,
    retry: RecoveryBudget | None,
    *,
    cancelled: bool,
    now: datetime,
    bootstrap: VisualBootstrapRecord | None,
) -> bool:
    """Pure validation of an original registration against transaction-current rows."""
    body = definition.to_payload()
    if (
        cancelled
        or not current_models_exact(active, checkpoint, retry)
        or original.digest() != definition.original.digest()
        or prior.digest() != VisualOwnerPublicationRecord.from_payload(body["publication"]).digest()
        or not current_supervision_publication(
            prior, original, active, checkpoint, pool, retry, ancestor, now=now
        )
        or aware(now) >= definition.deadline_at
    ):
        return False
    if bootstrap is not None:
        frozen = bootstrap.definition
        if (
            bootstrap.terminal_reason != "original_adopted"
            or frozen.task_started_at != datetime.fromisoformat(body["task_started_at"])
            or frozen.task_timeout_s != body["task_timeout_s"]
            or frozen.model_snapshot_hash != body["model_snapshot_hash"]
            or frozen.role_bundle_hash != original.role_bundle_hash
            or dict(frozen.source_hashes) != dict(original.source_hashes)
            or frozen.verification_limits != prior.verification_budget.state.limits
            or _lease_key(frozen.lease) != _lease_key(_lease(body["lease"]))
        ):
            return False
    return True


def derive_supervision(
    record: VisualSupervisionRecord,
    request: VisualSupervisionTransitionInput,
    original: VisualOriginalPlan,
    prior: VisualOwnerPublicationRecord,
    ancestor: VisualOwnerPublicationRecord | None,
    active: ActiveTaskContractRecord | None,
    checkpoint: ExecutionCheckpoint | None,
    pool: VerificationBudgetRecord | None,
    retry: RecoveryBudget | None,
    *,
    cancelled: bool,
    now: datetime,
) -> VisualSupervisionTransitionResult | None:
    """Local CAS ownership, with no sensor/model/controller call or pool mutation."""
    from cloud_edge_robot_arm.repositories.event_autonomy.protocol import IdempotencyConflictError

    body = request.to_payload()
    history = record.to_payload()["history"]
    for event in history:
        old = VisualSupervisionTransitionInput.from_payload(event["request"])
        same_event = event["request"]["event_key"] == body["event_key"]
        same_source = event["request"]["kind"] == body["kind"] and _claim_key(
            event["request"]
        ) == _claim_key(body)
        if same_event or same_source:
            if old.semantic_hash() != request.semantic_hash():
                raise IdempotencyConflictError("supervision event/claim changed source bytes")
            return VisualSupervisionTransitionResult(
                record, _claim_key(body), "HISTORICAL_DUPLICATE"
            )
    from cloud_edge_robot_arm.vision.operational_windows import _consume_transition

    _consume_transition(
        body, required="operational_windows" in record.definition.to_payload()
    )
    if (
        cancelled
        or not current_models_exact(active, checkpoint, retry)
        or original.digest() != record.definition.original.digest()
        or prior.digest() != VisualOwnerPublicationRecord.from_payload(body["publication"]).digest()
        or not current_supervision_publication(
            prior, original, active, checkpoint, pool, retry, ancestor, now=now
        )
    ):
        return None
    try:
        state, claim_id = _apply(record.to_payload(), request, aware(now))
    except (ValueError, TypeError, OverflowError):
        return None
    produced = VisualSupervisionRecord._trusted(state)
    return VisualSupervisionTransitionResult(produced, claim_id, "NEW_COMMIT")
