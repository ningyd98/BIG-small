"""Live worker coordination around durable visual source claims.

This coordinator does not perform camera, model or controller calls and does not
grant action permission. The owner wraps those real effects between reservations
and completions, and still uses the native gate, SafetyShield and SkillExecutor.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Literal, Protocol, cast

from cloud_edge_robot_arm.cloud.planning.models import PlannerDraft
from cloud_edge_robot_arm.contracts.models import (
    ExecutionCheckpoint,
    RobotState,
    SkillExecutionResult,
    SkillName,
    TaskContract,
)
from cloud_edge_robot_arm.edge.evidence.conditions import OnlineEvidenceSnapshot
from cloud_edge_robot_arm.edge.recovery.lifecycle import checkpoint_digest
from cloud_edge_robot_arm.edge.recovery.verification_router import (
    VerificationBudget,
    VerificationBudgetState,
)
from cloud_edge_robot_arm.repositories.event_autonomy.memory import InMemoryEventAutonomyRepository
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import EventAutonomyRepository
from cloud_edge_robot_arm.repositories.event_autonomy.sqlite import SQLiteEventAutonomyRepository
from cloud_edge_robot_arm.repositories.event_autonomy.visual_bootstrap import (
    BOOTSTRAP_SOURCE_PATH,
    VisualBootstrapDefinition,
    VisualBootstrapPromotionInput,
    VisualBootstrapRecord,
    VisualBootstrapTransitionInput,
    bootstrap_retry_budget,
    compile_bootstrap_original_plan,
)
from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
    VisualOwnerPublicationRecord,
    aware,
    digest,
    original_from_payload,
    serialized_model,
)
from cloud_edge_robot_arm.repositories.event_autonomy.visual_supervision import (
    SUPERVISION_SOURCE_PATH,
    VisualSupervisionDefinition,
    VisualSupervisionRecord,
    VisualSupervisionTransitionInput,
    VisualSupervisionTransitionResult,
)
from cloud_edge_robot_arm.repositories.event_autonomy.visual_verification import (
    VisualEffectCompletion,
    VisualVerificationRouteInput,
    VisualVerificationRouteRecord,
    camera_source_descriptor_sha256,
)
from cloud_edge_robot_arm.simulation_runtime.in_memory_repository import (
    InMemorySimulationJobRepository,
)
from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.operational_windows import (
    _bind_observation_policy,
    _check_observation,
    _consume_handoff,
    _reference_for_observation,
    _register_observation,
    _transition_scope,
)
from cloud_edge_robot_arm.vision.owner_registration import StepGroundingBinding, VisualOriginalPlan
from cloud_edge_robot_arm.vision.role_models import configuration_hash
from cloud_edge_robot_arm.vision.runtime_binding import RoleRuntimeBinding
from cloud_edge_robot_arm.vision.supervision import SupervisionContext, SupervisionDecision
from cloud_edge_robot_arm.vision.worker_owner import (
    REQUIRED_COMPILER_SOURCES,
    WorkerLeaseObservation,
    _identity_string,
    pin_worker_source_inventory,
    read_visual_worker_lease,
)

REQUIRED_WORKER_RUNTIME_SOURCES = REQUIRED_COMPILER_SOURCES | frozenset(
    {
        BOOTSTRAP_SOURCE_PATH,
        "src/cloud_edge_robot_arm/vision/operational_windows.py",
        "src/cloud_edge_robot_arm/research/operational_time_v1.py",
        "src/cloud_edge_robot_arm/vision/worker_runtime.py",
        "src/cloud_edge_robot_arm/repositories/event_autonomy/protocol.py",
        "src/cloud_edge_robot_arm/repositories/event_autonomy/memory.py",
        "src/cloud_edge_robot_arm/repositories/event_autonomy/sqlite.py",
        "src/cloud_edge_robot_arm/repositories/event_autonomy/visual_owner.py",
        "src/cloud_edge_robot_arm/repositories/event_autonomy/visual_verification.py",
        SUPERVISION_SOURCE_PATH,
    }
)


class VisualWorkerRouteResult(Protocol):
    """Typed read view of the repository's immutable route write result."""

    record: VisualVerificationRouteRecord
    write_disposition: Literal["NEW_COMMIT", "HISTORICAL_DUPLICATE"]


class VisualSupervisionReplyExpired(RuntimeError):
    """Only original frame TTL expired after strict current source validation."""


class _VisualSupervisionCommitRejected(RuntimeError):
    """No new commit; actual database exceptions remain distinct."""


@dataclass(frozen=True)
class WorkerRuntimeSource:
    job_repository: SQLiteSimulationJobRepository | InMemorySimulationJobRepository
    event_repository: EventAutonomyRepository
    job_id: str
    run_id: str
    worker_id: str
    lease_id: str
    source_root: Path
    source_hashes: Mapping[str, str]
    robot_id: str
    plan_id: str
    task_started_at: datetime
    task_timeout_s: float

    def __post_init__(self) -> None:
        if type(self.job_repository) not in {
            SQLiteSimulationJobRepository,
            InMemorySimulationJobRepository,
        } or type(self.event_repository) not in {
            InMemoryEventAutonomyRepository,
            SQLiteEventAutonomyRepository,
        }:
            raise TypeError("concrete worker and event repositories required")
        for value in (
            self.job_id,
            self.run_id,
            self.worker_id,
            self.lease_id,
            self.robot_id,
            self.plan_id,
        ):
            _identity_string(value)
        if (
            type(self.task_timeout_s) not in (int, float)
            or not math.isfinite(self.task_timeout_s)
            or self.task_timeout_s <= 0
        ):
            raise ValueError("positive finite original task timeout required")
        object.__setattr__(self, "task_started_at", aware(self.task_started_at))
        object.__setattr__(self, "source_root", Path(self.source_root))
        object.__setattr__(
            self,
            "source_hashes",
            pin_worker_source_inventory(
                self.source_root,
                self.source_hashes,
                required_paths=REQUIRED_WORKER_RUNTIME_SOURCES,
            ),
        )


@dataclass(frozen=True)
class VisualWorkerSupervisionClaim:
    """Immutable local source handle, never a native or physical action permit."""

    _json: str

    def to_payload(self) -> dict[str, object]:
        return cast(dict[str, object], json.loads(self._json))

    def digest(self) -> str:
        return digest(self.to_payload())

    @property
    def claim_id(self) -> str:
        return cast(str, self.to_payload()["claim_id"])

    @property
    def cursor(self) -> int:
        return cast(int, self.to_payload()["cursor"])

    @property
    def step_id(self) -> str:
        return cast(str, self.to_payload()["step_id"])

    @property
    def publication_hash(self) -> str:
        return self.publication.digest()

    @property
    def publication(self) -> VisualOwnerPublicationRecord:
        return VisualOwnerPublicationRecord.from_payload(
            cast(dict, self.to_payload()["publication"])
        )

    @property
    def original(self) -> VisualOriginalPlan:
        return original_from_payload(cast(dict, self.to_payload()["original"]))


@dataclass(frozen=True)
class VisualWorkerSupervisionFrame:
    """Frozen provider source; detached getters never access backend or camera."""

    _json: str

    def to_payload(self) -> dict[str, object]:
        return cast(dict[str, object], json.loads(self._json))

    def digest(self) -> str:
        return digest(self.to_payload())

    @property
    def claim(self) -> VisualWorkerSupervisionClaim:
        return VisualWorkerSupervisionClaim(json.dumps(self.to_payload()["claim"], sort_keys=True))

    @property
    def claim_id(self) -> str:
        return self.claim.claim_id

    @property
    def cursor(self) -> int:
        return self.claim.cursor

    @property
    def step_id(self) -> str:
        return self.claim.step_id

    @property
    def publication_hash(self) -> str:
        return self.claim.publication_hash

    @property
    def observation(self) -> RGBDObservation:
        return serialized_model(cast(dict, self.to_payload()["observation"]), RGBDObservation)

    @property
    def context(self) -> SupervisionContext:
        return serialized_model(cast(dict, self.to_payload()["context"]), SupervisionContext)


class VisualWorkerRuntime:
    """Tie the current concrete worker attempt to one immutable source history."""

    def __init__(
        self,
        source: WorkerRuntimeSource,
        *,
        episode_id: str,
        instruction: str,
        role_binding: RoleRuntimeBinding,
        model_snapshot_hash: str,
        verification_limits: VerificationBudget,
        _operational_handoff: object | None = None,
    ) -> None:
        if type(source) is not WorkerRuntimeSource or type(role_binding) is not RoleRuntimeBinding:
            raise TypeError("concrete worker source and role binding required")
        self.source = source
        self.role_binding = role_binding
        self._operational_owner = (
            _consume_handoff(
                _operational_handoff, source, role_binding, verification_limits, episode_id
            )
            if _operational_handoff is not None
            else None
        )
        self._operational_pending = {}
        self._operational_completed = {}
        self._lock = RLock()
        self._claims: dict[str, str] = {}
        self._capture_sources: dict[str, tuple[datetime, RGBDObservation]] = {}
        self._ordinary_capture_claim: tuple[str, RGBDObservation] | None = None
        self._effect_capture_claims: set[tuple[str, str]] = set()
        self._returned_effects: dict[str, str] = {}
        self._phase_receipts: dict[tuple[str, str], str] = {}
        self._supervision_handles: dict[str, tuple[str, str]] = {}
        self._supervision_known_frames: dict[str, str] = {}
        self._supervision_capture_data: dict[str, tuple[RGBDObservation, SupervisionContext]] = {}
        self._can_capture_effects = False
        self._role_hash = role_binding.bundle.digest()
        self._validate_role_sources(verification_limits)
        lease = self._read_lease()
        self._frozen_job_configuration_hash = digest(self._job_configuration())
        bootstrap_id = digest(["visual.bootstrap.job-run.v1", source.job_id, source.run_id])
        existing = source.event_repository.get_visual_bootstrap(bootstrap_id)
        if existing is None:
            definition = VisualBootstrapDefinition(
                lease=lease,
                episode_id=episode_id,
                user_instruction=instruction,
                task_started_at=source.task_started_at,
                task_timeout_s=source.task_timeout_s,
                verification_limits=verification_limits,
                role_bundle_hash=self._role_hash,
                model_snapshot_hash=model_snapshot_hash,
                source_hashes=source.source_hashes,
                registered_at=datetime.now(UTC),
                operational_windows=(
                    tuple(self._operational_references())
                    if self._operational_owner is not None else None
                ),
            )
        else:
            definition = existing.definition
            if (
                definition.episode_id != episode_id
                or definition.user_instruction != instruction
                or definition.task_started_at != source.task_started_at
                or definition.task_timeout_s != source.task_timeout_s
                or definition.verification_limits != verification_limits
                or definition.role_bundle_hash != self._role_hash
                or definition.model_snapshot_hash != model_snapshot_hash
                or dict(definition.source_hashes) != dict(source.source_hashes)
                or self._lease_key(definition.lease) != self._lease_key(lease)
                or definition.lease.acquired_at != lease.acquired_at
            ):
                raise RuntimeError("restart differs from immutable original worker source")
        # Exact initialization preserves a persisted pending claim and all spent pools.
        source.event_repository.initialize_visual_bootstrap_if_absent(definition)
        self._bootstrap_id = definition.bootstrap_id
        self._lease_identity = self._lease_key(definition.lease)
        self._last_observation = self.bootstrap.observation
        self._read_lease()

    def _operational_begin(self, claim: str, kind: str, observation=None) -> None:
        owner = self._operational_owner
        if owner is None:
            return
        token = owner.clock.begin_event(kind + ":ENCLOSING_EFFECT")
        owner.clock.mark_event(token)
        self._operational_pending[claim] = (token, kind, observation)

    def _operational_finish(self, claim: str):
        owner = self._operational_owner
        if owner is None:
            return None
        token, kind, observation = self._operational_pending.pop(claim)
        receipt = owner.clock.end_event(token)
        parents = ()
        if observation is not None:
            original = _reference_for_observation(observation, "capture")
            parents = (original["window_id"],)
        identifier = owner.issue(kind, receipt, budget_ns=5_000_000_000, parent_ids=parents)
        if owner.check(identifier, after=token).status != "VALID":
            raise RuntimeError("original enclosing effect window expired")
        self._operational_completed[claim] = identifier
        return receipt

    def _operational_references(self, claim=None, observation=None):
        owner = self._operational_owner
        if owner is None:
            return None
        refs = [owner.export_record(owner.task_window)]
        if claim in self._operational_completed:
            refs.append(owner.export_record(self._operational_completed[claim]))
        if observation is not None:
            refs.append(_reference_for_observation(observation, "bootstrap"))
        return refs

    @staticmethod
    def _lease_key(lease: WorkerLeaseObservation) -> tuple[str | int, ...]:
        return lease.job_id, lease.run_id, lease.worker_id, lease.lease_id, lease.attempt

    def _read_lease(self) -> WorkerLeaseObservation:
        try:
            lease = read_visual_worker_lease(
                self.source.job_repository,
                job_id=self.source.job_id,
                run_id=self.source.run_id,
                worker_id=self.source.worker_id,
                lease_id=self.source.lease_id,
            )
            if hasattr(self, "_lease_identity") and self._lease_key(lease) != self._lease_identity:
                raise ValueError("worker attempt changed")
            return lease
        except (ValueError, TypeError, KeyError) as error:
            raise RuntimeError("live worker lease source unavailable") from error

    def _validate_role_sources(self, limits: VerificationBudget) -> None:
        binding = self.role_binding
        if binding.root.resolve() != self.source.source_root.resolve():
            raise ValueError("role and worker source roots differ")
        if binding.bundle.digest() != self._role_hash:
            raise RuntimeError("role bundle source changed")
        policy = cast(dict[str, object], binding.evidence()["edge_policy"])
        capabilities = policy.get("capabilities")
        if policy["verification_budget"] != asdict(limits):
            raise ValueError("original verification limits differ from role policy")
        if (
            configuration_hash(policy) != binding.edge_snapshot.request_config_hash
            or binding.edge_snapshot.digest() != binding.bundle.edge_provider_hash
            or configuration_hash(cast(Mapping[str, object], binding.device_source_hashes))
            != binding.bundle.device_pipeline_hash
            or policy.get("runtime_router") != "verification_router.v1"
            or type(capabilities) is not list
            or len(capabilities) != 3
            or set(capabilities) != {"CONTINUE", "REOBSERVE", "STOP"}
            or policy.get("local_recover_enabled") is not False
        ):
            raise RuntimeError("frozen role policy source changed")
        for hashes in (
            binding.bundle.cloud_snapshot.source_hashes,
            binding.edge_snapshot.source_hashes,
            binding.device_source_hashes,
        ):
            if any(self.source.source_hashes.get(name) != value for name, value in hashes.items()):
                raise ValueError("complete exact role source inventory required")
        try:
            pin_worker_source_inventory(
                self.source.source_root,
                self.source.source_hashes,
                required_paths=REQUIRED_WORKER_RUNTIME_SOURCES,
            )
        except (ValueError, TypeError, OSError) as error:
            raise RuntimeError("worker implementation source changed or unavailable") from error

    @property
    def bootstrap(self) -> VisualBootstrapRecord:
        record = self.source.event_repository.get_visual_bootstrap(self._bootstrap_id)
        if record is None:
            raise RuntimeError("durable bootstrap source missing")
        return record

    @property
    def is_adopted(self) -> bool:
        return self.bootstrap.terminal_reason == "original_adopted"

    @property
    def episode_id(self) -> str:
        return self.bootstrap.definition.episode_id

    @property
    def publication(self) -> VisualOwnerPublicationRecord:
        publication = self.source.event_repository.get_visual_owner_publication(
            self.bootstrap.definition.episode_id
        )
        if publication is None:
            raise RuntimeError("coherent current worker publication unavailable")
        return publication

    @property
    def original(self) -> VisualOriginalPlan:
        publication = self.supervision_source_publication
        original = self.source.event_repository.get_visual_original_plan(
            publication.identity.task_id, publication.checkpoint.plan_version
        )
        if original is None or original.digest() != publication.original_plan_hash:
            raise RuntimeError("current original worker policy unavailable")
        return original

    @property
    def verification_state(self) -> VerificationBudgetState:
        return (
            self.supervision_source_publication.verification_budget.state
            if self.is_adopted
            else self.bootstrap.verification_state
        )

    def check_active(self, robot_state: RobotState) -> WorkerLeaseObservation:
        lease = self._read_lease()
        owner = self._operational_owner
        if owner is not None and owner.check(
            owner.task_window, after=owner.task_origin_token
        ).status != "VALID":
            raise RuntimeError("original operational task/verification window unavailable")
        record = self.bootstrap
        self._validate_role_sources(record.definition.verification_limits)
        if type(robot_state) is not RobotState or (
            not robot_state.connected or robot_state.estop_engaged or robot_state.collision_detected
        ):
            raise RuntimeError("current robot hard safety source prevents work")
        state = self.verification_state
        if record.terminal_reason not in (None, "original_adopted") or state.exhausted_reason:
            raise RuntimeError("durable visual worker already stopped")
        if datetime.now(UTC) >= min(record.task_deadline_at, state.deadline_at):
            raise RuntimeError("original worker deadline exhausted")
        return lease

    @property
    def supervision_source_publication(self) -> VisualOwnerPublicationRecord:
        """Coherent observer/budget source, never current grounding action validity."""
        source = self.source.event_repository.get_visual_supervision_source_publication(
            self.episode_id
        )
        if source is None:
            raise RuntimeError("coherent current observer source publication unavailable")
        return source

    def _job_configuration(self) -> dict[str, object]:
        """Read actual immutable job fields; no dynamic lease/status bytes enter this hash."""
        job = SQLiteSimulationJobRepository.get_job(self.source.job_repository, self.source.job_id)
        return {
            name: getattr(job, name)
            for name in (
                "job_id",
                "run_id",
                "backend",
                "scenario_id",
                "control_mode",
                "seed",
                "manifest_id",
                "reproducibility_hash",
                "draft",
                "manifest",
                "max_attempts",
                "timeout_seconds",
                "source_commit",
                "source_tree_hash",
            )
        }

    def _runtime_option_sources(self) -> tuple[float | None, bool]:
        config = self._job_configuration()
        if digest(config) != self._frozen_job_configuration_hash:
            raise RuntimeError("immutable worker job configuration source changed")
        if config["timeout_seconds"] != self.source.task_timeout_s:
            raise RuntimeError("original task timeout differs from job configuration")
        draft = config["draft"]
        if type(draft) is not dict:
            raise RuntimeError("concrete immutable job draft required")
        parameters = draft.get("parameter_overrides", {})
        if type(parameters) is not dict:
            raise RuntimeError("concrete immutable job parameter sources required")
        milliseconds = parameters.get("supervision_period_ms")
        if milliseconds is not None and (
            type(milliseconds) not in {int, float}
            or not math.isfinite(milliseconds)
            or milliseconds <= 0
        ):
            raise RuntimeError("finite positive explicitly persisted supervision period required")
        waits = parameters.get("advance_physics_during_wait", False)
        if type(waits) is not bool:
            raise RuntimeError("strict persisted passive wait flag required")
        period = float(milliseconds) / 1000.0 if milliseconds is not None else None
        return period, waits

    def _check_optional_sources(self) -> WorkerLeaseObservation:
        lease = self._read_lease()
        bootstrap = self.bootstrap
        self._validate_role_sources(bootstrap.definition.verification_limits)
        self._runtime_option_sources()
        if self.source.event_repository.get_state(self.episode_id) in {
            "CANCELLED",
            "ABORTED",
            "STOPPED",
            "SAFETY_STOPPED",
            "COMPLETED",
        } or any(
            event.severity == "CRITICAL" or event.event_type.value == "MANUAL_INTERRUPT"
            for event in self.source.event_repository.list_events(self.episode_id)
        ):
            raise RuntimeError("current event repository cancelled the optional worker source")
        if bootstrap.terminal_reason not in {None, "original_adopted"}:
            raise RuntimeError("original worker source is already stopped")
        if datetime.now(UTC) >= min(
            bootstrap.task_deadline_at, bootstrap.verification_state.deadline_at
        ):
            raise RuntimeError("original worker deadline exhausted")
        stored = self.source.event_repository.get_visual_supervision(self.episode_id)
        if stored is not None and stored.definition.to_payload()["job_configuration_hash"] != (
            self._frozen_job_configuration_hash
        ):
            raise RuntimeError("persisted supervision job configuration source changed")
        return lease

    def validate_runtime_options(
        self, period_s: float | None, advance_physics_during_wait: bool
    ) -> None:
        """Verify policy options against real job config without reading a backend."""
        with self._lock:
            self._check_optional_sources()
            expected_period, expected_waits = self._runtime_option_sources()
            if (
                type(advance_physics_during_wait) is not bool
                or advance_physics_during_wait != expected_waits
                or (period_s is not None and type(period_s) not in {int, float})
                or period_s != expected_period
            ):
                raise ValueError("runtime options differ from immutable job configuration")
            self._check_optional_sources()

    def validates_wait_policy(self, robot_state: RobotState) -> None:
        with self._lock:
            self.check_active(robot_state)
            self._check_optional_sources()
            if not self._runtime_option_sources()[1]:
                raise RuntimeError("passive wait was not requested in immutable job configuration")
            self.check_active(robot_state)

    def assert_owned_plan_wait(self, claim_id: str, robot_state: RobotState) -> None:
        """Read-only passive wait along this instance's existing initial PLAN claim."""
        with self._lock:
            self.validates_wait_policy(robot_state)
            bootstrap = self.bootstrap
            pending = bootstrap.to_payload()["pending"]
            if (
                self._claims.get(claim_id) != "PLAN"
                or self.is_adopted
                or pending is None
                or pending["effect"] != "PLAN"
                or pending["claim_id"] != claim_id
            ):
                raise RuntimeError("passive planning wait lacks this live owner's exact claim")
            self.check_active(robot_state)

    def initialize_supervision(
        self, period_s: float | None, robot_state: RobotState
    ) -> VisualSupervisionRecord:
        with self._lock:
            lease = self.check_active(robot_state)
            self._check_optional_sources()
            expected_period, _ = self._runtime_option_sources()
            if (period_s is not None and type(period_s) not in {int, float}) or (
                period_s != expected_period
            ):
                raise ValueError("supervision period differs from immutable job configuration")
            if not self.is_adopted:
                raise RuntimeError("supervision registration requires the original adopted plan")
            existing = self.source.event_repository.get_visual_supervision(self.episode_id)
            if existing is None:
                original, publication = self.original, self.supervision_source_publication
                frozen = self.bootstrap.definition
                definition = VisualSupervisionDefinition(
                    original=original,
                    publication=publication,
                    lease=lease,
                    task_started_at=frozen.task_started_at,
                    task_timeout_s=frozen.task_timeout_s,
                    supervision_period_s=period_s,
                    model_snapshot_hash=frozen.model_snapshot_hash,
                    role_bundle=self.role_binding.bundle,
                    job_configuration_hash=self._frozen_job_configuration_hash,
                    operational_windows=self._operational_references(),
                )
            else:
                definition = existing.definition
                body = definition.to_payload()
                if (
                    definition.original.digest() != self.original.digest()
                    or body["supervision_period_s"] != period_s
                    or body["model_snapshot_hash"] != self.bootstrap.definition.model_snapshot_hash
                    or body["job_configuration_hash"] != self._frozen_job_configuration_hash
                    or body["role_bundle"] != self.role_binding.bundle.evidence()
                ):
                    raise RuntimeError("restart differs from original supervision job source")
            record = self.source.event_repository.initialize_visual_supervision_if_absent(
                definition
            )
            self.check_active(robot_state)
            self._check_optional_sources()
            return record

    def _supervision_transition(
        self,
        kind: str,
        robot_state: RobotState,
        *,
        cursor: int,
        claim: VisualWorkerSupervisionClaim | None = None,
        observation: RGBDObservation | None = None,
        context: SupervisionContext | None = None,
        decision: SupervisionDecision | None = None,
        wait_duration_s: float | None = None,
        wait_elapsed_s: float | None = None,
    ) -> VisualSupervisionTransitionResult:
        lease = self.check_active(robot_state)
        self._check_optional_sources()
        record = self.source.event_repository.get_visual_supervision(self.episode_id)
        if record is None:
            raise RuntimeError("original supervision source ledger unavailable")
        publication = self.supervision_source_publication
        if claim is not None and publication.digest() != claim.publication_hash:
            raise RuntimeError("supervision/wait claim publication source invalidated")
        request = VisualSupervisionTransitionInput(
            record=record,
            original=self.original,
            publication=publication,
            lease=lease,
            robot_state=robot_state,
            step_id=publication.checkpoint.current_step_id,
            cursor=cursor,
            kind=kind,
            event_key=digest(["worker-supervision", record.definition.digest(), kind, cursor]),
            model_snapshot_hash=self.bootstrap.definition.model_snapshot_hash,
            role_bundle=self.role_binding.bundle,
            claim_id=claim.claim_id if claim is not None else None,
            observation=observation,
            context=context,
            decision=decision,
            wait_duration_s=wait_duration_s,
            wait_elapsed_s=wait_elapsed_s,
            operational_windows=self._operational_references(
                claim.claim_id if claim is not None else None
            ),
        )
        with _transition_scope(self._operational_owner, request.to_payload()):
            result = self.source.event_repository.transition_visual_supervision_if_current(
                request=request
            )
        if result is None or result.write_disposition != "NEW_COMMIT":
            raise _VisualSupervisionCommitRejected(
                "supervision source is stale or historical; no effect replay"
            )
        self.check_active(robot_state)
        self._check_optional_sources()
        return result

    def _new_supervision_handle(
        self, result: VisualSupervisionTransitionResult, *, kind: str
    ) -> VisualWorkerSupervisionClaim:
        state = result.record.to_payload()["claims"][result.claim_id]
        publication, original = self.supervision_source_publication, self.original
        if (
            publication.digest() != state["publication_hash"]
            or original.digest() != result.record.definition.original.digest()
        ):
            raise RuntimeError("supervision/wait claim source changed after local commit")
        claim = VisualWorkerSupervisionClaim(
            json.dumps(
                {
                    "scope": "SUPERVISION_SOURCE_ONLY",
                    "claim_id": result.claim_id,
                    "cursor": state["cursor"],
                    "step_id": state["step_id"],
                    "kind": kind,
                    "publication": publication.to_payload(),
                    "original": original.to_payload(),
                },
                sort_keys=True,
            )
        )
        self._supervision_handles[claim.claim_id] = (kind, claim.digest())
        return claim

    def reserve_supervision_capture(
        self, cursor: int, robot_state: RobotState
    ) -> VisualWorkerSupervisionClaim:
        with self._lock:
            result = self._supervision_transition("RESERVE_CAPTURE", robot_state, cursor=cursor)
            claim = self._new_supervision_handle(result, kind="CAPTURE")
            self._operational_begin(claim.claim_id, "capture")
            return claim

    def _owned_supervision_handle(self, claim: VisualWorkerSupervisionClaim, kind: str) -> None:
        if type(claim) is not VisualWorkerSupervisionClaim or (
            self._supervision_handles.get(claim.claim_id) != (kind, claim.digest())
        ):
            raise RuntimeError("supervision/wait claim is not owned by this live coordinator")

    def complete_supervision_capture(
        self,
        claim: VisualWorkerSupervisionClaim,
        observation: RGBDObservation,
        context: SupervisionContext,
        robot_state: RobotState,
    ) -> None:
        with self._lock:
            self._owned_supervision_handle(claim, "CAPTURE")
            del self._supervision_handles[claim.claim_id]
            if (
                type(context) is not SupervisionContext
                or context.task_instruction != self.bootstrap.definition.user_instruction
            ):
                raise RuntimeError("supervision context changed original instruction source")
            receipt = self._operational_finish(claim.claim_id)
            self._supervision_transition(
                "COMPLETE_CAPTURE",
                robot_state,
                cursor=claim.cursor,
                claim=claim,
                observation=observation,
                context=context,
            )
            if receipt is not None:
                _register_observation(self._operational_owner, receipt, observation)
                requirement = claim.original.requirements[claim.step_id]
                _bind_observation_policy(
                    self._operational_owner, observation, "supervision",
                    requirement.ordinary_ttl_s, {"requirement": requirement.to_payload()},
                )
            self._supervision_handles[claim.claim_id] = ("CAPTURED", claim.digest())
            self._supervision_capture_data[claim.claim_id] = (
                observation.model_copy(deep=True),
                context.model_copy(deep=True),
            )

    def reserve_supervision_plan(
        self, claim: VisualWorkerSupervisionClaim, robot_state: RobotState
    ) -> VisualWorkerSupervisionFrame:
        with self._lock:
            self._owned_supervision_handle(claim, "CAPTURED")
            del self._supervision_handles[claim.claim_id]
            observation, context = self._supervision_capture_data.pop(claim.claim_id)
            self._supervision_transition(
                "RESERVE_PLAN", robot_state, cursor=claim.cursor, claim=claim
            )
            frame = VisualWorkerSupervisionFrame(
                json.dumps(
                    {
                        "scope": "SUPERVISION_SOURCE_ONLY",
                        "claim": claim.to_payload(),
                        "observation": observation.model_dump(mode="json"),
                        "context": context.model_dump(mode="json"),
                        "model_snapshot_hash": self.bootstrap.definition.model_snapshot_hash,
                        "cloud_snapshot": self.role_binding.bundle.cloud_snapshot.evidence(),
                        "source_hashes": dict(self.original.source_hashes),
                    },
                    sort_keys=True,
                )
            )
            self._supervision_handles[claim.claim_id] = ("PLAN", frame.digest())
            self._supervision_known_frames[claim.claim_id] = frame.digest()
            self._operational_begin(claim.claim_id, "supervision", observation)
            return frame

    def assert_supervision_plan_pending(self, frame: VisualWorkerSupervisionFrame) -> None:
        """Read-only provider boundary; no backend state is accessed on this thread."""
        with self._lock:
            if type(frame) is not VisualWorkerSupervisionFrame or (
                self._supervision_handles.get(frame.claim_id) != ("PLAN", frame.digest())
            ):
                raise RuntimeError("supervisor source frame is not owned by this live coordinator")
            self._check_optional_sources()
            record = self.source.event_repository.get_visual_supervision(self.episode_id)
            claim = (
                record.to_payload()["claims"].get(frame.claim_id) if record is not None else None
            )
            if (
                record is None
                or claim is None
                or claim["status"] != "PLAN_PENDING"
                or claim["publication_hash"] != frame.publication_hash
                or claim["observation"] != frame.observation.model_dump(mode="json")
                or claim["context"] != frame.context.model_dump(mode="json")
            ):
                raise RuntimeError("supervisor source claim is not exact durable PLAN_PENDING")
            self._assert_supervision_frame_current_source(frame, record)
            self._check_optional_sources()
            self._assert_supervision_frame_current_source(frame, record)

    def _assert_supervision_frame_current_source(
        self, frame: VisualWorkerSupervisionFrame, record: VisualSupervisionRecord
    ) -> None:
        """Join the immutable receipt to the live source, never to action validity."""
        publication = self.supervision_source_publication
        original = self.source.event_repository.get_visual_original_plan(
            publication.identity.task_id, publication.checkpoint.plan_version
        )
        receipt_original = frame.claim.original
        source = frame.to_payload()
        definition = record.definition.to_payload()
        if (
            publication.digest() != frame.publication_hash
            or original is None
            or original.digest() != receipt_original.digest()
            or publication.original_plan_hash != receipt_original.digest()
            or record.definition.original.digest() != receipt_original.digest()
            or publication.verification_budget.state.exhausted_reason is not None
            or source["model_snapshot_hash"] != self.bootstrap.definition.model_snapshot_hash
            or definition["model_snapshot_hash"] != source["model_snapshot_hash"]
            or definition["role_bundle"] != self.role_binding.bundle.evidence()
            or source["cloud_snapshot"] != self.role_binding.bundle.cloud_snapshot.evidence()
            or source["source_hashes"] != dict(original.source_hashes)
        ):
            raise RuntimeError("supervisor current publication/original/model source invalidated")

    def complete_supervision_plan(
        self,
        frame: VisualWorkerSupervisionFrame,
        decision: SupervisionDecision,
        robot_state: RobotState,
    ) -> VisualSupervisionRecord:
        with self._lock:
            self.assert_supervision_plan_pending(frame)
            del self._supervision_handles[frame.claim_id]
            self._operational_finish(frame.claim_id)
            try:
                result = self._supervision_transition(
                    "COMPLETE_PLAN",
                    robot_state,
                    cursor=frame.cursor,
                    claim=frame.claim,
                    decision=decision,
                )
            except _VisualSupervisionCommitRejected:
                if self.classify_supervision_reply(frame) == "EXPIRED":
                    raise VisualSupervisionReplyExpired(
                        "original supervisor frame TTL expired"
                    ) from None
                raise
            return result.record

    def classify_supervision_reply(
        self, frame: VisualWorkerSupervisionFrame
    ) -> Literal["CURRENT", "EXPIRED"]:
        """Read-only expiry classification; source/cancel/lease/config failures raise.

        A consumed local completion handle can be classified while its exact
        durable receipt remains PLAN_PENDING. This grants no replay handle.
        """
        with self._lock:
            if type(frame) is not VisualWorkerSupervisionFrame or (
                self._supervision_known_frames.get(frame.claim_id) != frame.digest()
            ):
                raise RuntimeError("reply lacks this live owner's exact immutable frame source")
            self._check_optional_sources()
            publication = self.supervision_source_publication
            original = frame.claim.original
            record = self.source.event_repository.get_visual_supervision(self.episode_id)
            claim = (
                record.to_payload()["claims"].get(frame.claim_id) if record is not None else None
            )
            if (
                record is None
                or publication.digest() != frame.publication_hash
                or publication.original_plan_hash != original.digest()
                or publication.verification_budget.state.exhausted_reason is not None
                or claim is None
                or claim["status"] != "PLAN_PENDING"
                or claim["observation"] != frame.observation.model_dump(mode="json")
                or claim["context"] != frame.context.model_dump(mode="json")
            ):
                raise RuntimeError("reply current source/checkpoint/typed receipt invalidated")
            self._assert_supervision_frame_current_source(frame, record)
            self._check_optional_sources()
            self._assert_supervision_frame_current_source(frame, record)
            age = (datetime.now(UTC) - frame.observation.captured_at).total_seconds()
            if age < 0:
                raise RuntimeError("supervisor frame clock is ahead of current source clock")
            ttl = original.requirements[frame.step_id].ordinary_ttl_s
            local = _check_observation(frame.observation, "supervision", max_age_s=ttl)
            return "EXPIRED" if local is False or age > ttl else "CURRENT"

    def reserve_wait(
        self, duration_s: float, robot_state: RobotState
    ) -> VisualWorkerSupervisionClaim:
        with self._lock:
            self.validates_wait_policy(robot_state)
            record = self.source.event_repository.get_visual_supervision(self.episode_id)
            if record is None:
                period, _ = self._runtime_option_sources()
                record = self.initialize_supervision(period, robot_state)
            cursor = int(record.to_payload()["last_wait_cursor"]) + 1
            result = self._supervision_transition(
                "RESERVE_WAIT", robot_state, cursor=cursor, wait_duration_s=duration_s
            )
            return self._new_supervision_handle(result, kind="WAIT")

    def complete_wait(
        self, claim: VisualWorkerSupervisionClaim, elapsed_s: float, robot_state: RobotState
    ) -> VisualSupervisionRecord:
        with self._lock:
            self._owned_supervision_handle(claim, "WAIT")
            del self._supervision_handles[claim.claim_id]
            self.validates_wait_policy(robot_state)
            return self._supervision_transition(
                "COMPLETE_WAIT",
                robot_state,
                cursor=claim.cursor,
                claim=claim,
                wait_elapsed_s=elapsed_s,
            ).record

    def _transition(
        self,
        kind: str,
        robot_state: RobotState,
        *,
        claim_id: str | None = None,
        observation: RGBDObservation | None = None,
        draft: PlannerDraft | None = None,
    ) -> VisualBootstrapRecord:
        lease = self.check_active(robot_state)
        record = self.bootstrap
        if record.terminal_reason == "original_adopted":
            raise RuntimeError("bootstrap effects ended at original adoption")
        request = VisualBootstrapTransitionInput(
            record=record,
            kind=kind,
            event_key=f"worker-{kind.lower()}-{record.revision}",
            current_lease=lease,
            robot_state=robot_state,
            claim_id=claim_id,
            observation=observation,
            draft=draft,
            operational_windows=self._operational_references(
                claim_id, record.observation if kind != "COMPLETE_CAPTURE" else None
            ),
        )
        with _transition_scope(self._operational_owner, request.to_payload()):
            result = self.source.event_repository.transition_visual_bootstrap_if_current(
                request=request
            )
        if result is None or result.write_disposition != "NEW_COMMIT":
            raise RuntimeError("source claim is stale or historical; no effect replay allowed")
        self.check_active(robot_state)
        return result.record

    def reserve_capture(self, robot_state: RobotState, *, initial: bool = False) -> str:
        with self._lock:
            if self.is_adopted:
                self.check_active(robot_state)
                if initial or self._ordinary_capture_claim is None:
                    raise RuntimeError("no new owned ordinary reobservation claim")
                claim, before = self._ordinary_capture_claim
                self._ordinary_capture_claim = None
                self._claims[claim] = "ORDINARY_CAPTURE"
                self._capture_sources[claim] = (datetime.now(UTC), before)
                self._operational_begin(claim, "capture")
                return claim
            record = self._transition(
                "RESERVE_INITIAL_CAPTURE" if initial else "RESERVE_REOBSERVATION", robot_state
            )
            if record.pending_claim_id is None:
                raise RuntimeError("capture budget stopped without effect permission")
            self._claims[record.pending_claim_id] = "CAPTURE"
            self._operational_begin(record.pending_claim_id, "capture")
            return record.pending_claim_id

    def complete_capture(
        self, claim_id: str, observation: RGBDObservation, robot_state: RobotState
    ) -> None:
        with self._lock:
            if self._claims.get(claim_id) == "ORDINARY_CAPTURE":
                # Consume the local handle before checking the returned source. A
                # rejected/lost completion cannot allocate another camera effect.
                del self._claims[claim_id]
                claimed_at, before = self._capture_sources.pop(claim_id)
                self.check_active(robot_state)
                now = datetime.now(UTC)
                if type(observation) is not RGBDObservation or (
                    observation.episode_id != self.episode_id
                    or not claimed_at <= observation.captured_at <= now
                    or observation.captured_at <= before.captured_at
                    or observation.frame_id == before.frame_id
                    or camera_source_descriptor_sha256(observation)
                    != camera_source_descriptor_sha256(before)
                    or (
                        self._last_observation is not None
                        and (
                            observation.frame_id == self._last_observation.frame_id
                            or observation.captured_at <= self._last_observation.captured_at
                        )
                    )
                ):
                    raise RuntimeError("ordinary capture source/frame/clock changed")
                receipt = self._operational_finish(claim_id)
                if receipt is not None:
                    _register_observation(self._operational_owner, receipt, observation)
                self._last_observation = observation.model_copy(deep=True)
                self.check_active(robot_state)
                return
            if self._claims.get(claim_id) != "CAPTURE":
                raise RuntimeError("capture claim is not owned by this live coordinator")
            receipt = self._operational_finish(claim_id)
            self._transition(
                "COMPLETE_CAPTURE", robot_state, claim_id=claim_id, observation=observation
            )
            if receipt is not None:
                _register_observation(self._operational_owner, receipt, observation)
            self._last_observation = observation.model_copy(deep=True)
            del self._claims[claim_id]

    def reserve_plan(self, robot_state: RobotState) -> str:
        with self._lock:
            record = self._transition("RESERVE_PLAN", robot_state)
            if record.pending_claim_id is None:
                raise RuntimeError("planning source stopped without effect claim")
            self._claims[record.pending_claim_id] = "PLAN"
            self._operational_begin(record.pending_claim_id, "plan", record.observation)
            return record.pending_claim_id

    def complete_plan(self, claim_id: str, draft: PlannerDraft, robot_state: RobotState) -> None:
        with self._lock:
            if self._claims.get(claim_id) != "PLAN":
                raise RuntimeError("planning claim is not owned by this live coordinator")
            self._operational_finish(claim_id)
            self._transition("COMPLETE_PLAN", robot_state, claim_id=claim_id, draft=draft)
            del self._claims[claim_id]

    def adopt_plan(
        self, robot_state: RobotState
    ) -> tuple[TaskContract, VisualOwnerPublicationRecord]:
        with self._lock:
            lease = self.check_active(robot_state)
            if self.is_adopted:
                return self.original.contract, self.publication
            record = self.bootstrap
            now = datetime.now(UTC)
            original = compile_bootstrap_original_plan(
                record,
                current_lease=lease,
                plan_id=self.source.plan_id,
                robot_id=self.source.robot_id,
                registered_at=now,
            )
            retry = bootstrap_retry_budget(record, original, created_at=now)
            contract = original.contract
            checkpoint = ExecutionCheckpoint(
                checkpoint_id=f"visual-initial-{record.definition.bootstrap_id[:32]}",
                task_id=contract.task_id,
                plan_id=original.identity.plan_id,
                robot_id=original.identity.robot_id,
                plan_version=contract.plan_version,
                command_seq=contract.command_seq,
                scene_version=contract.scene_version,
                current_step_id=contract.steps[0].step_id,
                pending_step_ids=[step.step_id for step in contract.steps],
                robot_state=robot_state.model_dump(mode="json"),
                created_at=now,
                updated_at=now,
            )
            checkpoint = checkpoint.model_copy(
                update={"checkpoint_hash": checkpoint_digest(checkpoint)}
            )
            promotion = VisualBootstrapPromotionInput(
                record=record,
                original=original,
                event_key=f"worker-adopt-{record.revision}",
                current_lease=lease,
                robot_state=robot_state,
            )
            publication = self.source.event_repository.initialize_visual_owner_if_absent(
                original,
                checkpoint,
                record.verification_state,
                retry,
                bootstrap_promotion=promotion,
            )
            self.check_active(robot_state)
            self._can_capture_effects = True
            return contract, publication

    def route(
        self,
        online: OnlineEvidenceSnapshot,
        *,
        step_id: str,
        phase: str,
        execution_contract: TaskContract,
        completion: VisualEffectCompletion | None = None,
        grounding_receipt: StepGroundingBinding | None = None,
        attempt: int = 1,
    ) -> VisualWorkerRouteResult:
        """Publish one canonical route; historical reobservation never repeats work."""
        with self._lock:
            self.check_active(online.robot_state)
            if (
                self._ordinary_capture_claim is not None
                or "ORDINARY_CAPTURE" in self._claims.values()
            ):
                raise RuntimeError("previous ordinary capture claim remains unconsumed")
            publication = (
                self.supervision_source_publication
                if phase in {"AFTER_EFFECT", "POST_HOLD", "TERMINAL"} and completion is not None
                else self.publication
            )
            if online.context_hash != publication.checkpoint.checkpoint_hash:
                raise RuntimeError("online source binds a stale worker checkpoint")
            if self._operational_owner is not None:
                from dataclasses import replace

                from cloud_edge_robot_arm.edge.evidence.conditions import _operational_freshness

                requirement = self.original.requirements[step_id]
                specs = (*requirement.preconditions, *requirement.postconditions)
                ttl = min(
                    requirement.ordinary_ttl_s,
                    *(spec.tolerances.get("max_age_s", 5.0) for spec in specs),
                )
                _bind_observation_policy(
                    self._operational_owner, online.observation, "condition", ttl,
                    {"requirement": requirement.to_payload()},
                )
                reference = _reference_for_observation(
                    online.observation, "condition", max_age_s=ttl
                )
                if _operational_freshness(
                    replace(online, operational_reference=reference), ttl
                ) is not True:
                    raise RuntimeError("original condition acquisition window unavailable")
            request = VisualVerificationRouteInput(
                original=self.original,
                publication=publication,
                online=online,
                step_id=step_id,
                attempt=attempt,
                phase=phase,
                event_key=digest(
                    [
                        "worker-route",
                        phase,
                        step_id,
                        attempt,
                        online.observation.frame_id,
                        publication.digest(),
                    ]
                ),
                execution_contract=execution_contract,
                completion=completion,
                grounding_receipt=grounding_receipt,
            )
            result = self.source.event_repository.route_visual_verification_if_current(
                request=request
            )
            if result is None:
                raise RuntimeError("ordinary worker source route is stale")
            typed_result = cast(VisualWorkerRouteResult, result)
            # STOP is a durable outcome, returned for owner logging; live cancellation
            # and source drift are still checked after publication without refilling.
            self._read_lease()
            self._validate_role_sources(self.bootstrap.definition.verification_limits)
            if (
                typed_result.write_disposition == "HISTORICAL_DUPLICATE"
                and typed_result.record.route == "REOBSERVE"
            ):
                raise RuntimeError("historical reobservation claim cannot repeat capture")
            if (
                typed_result.write_disposition == "NEW_COMMIT"
                and typed_result.record.route == "REOBSERVE"
            ):
                if self._ordinary_capture_claim is not None:
                    raise RuntimeError("previous ordinary capture claim remains unconsumed")
                self._ordinary_capture_claim = (
                    typed_result.record.digest(),
                    online.observation.model_copy(deep=True),
                )
            if (
                typed_result.write_disposition == "NEW_COMMIT"
                and typed_result.record.route == "CONTINUE"
            ):
                self._phase_receipts[(step_id, phase)] = request.to_payload()["event_key"]
            return typed_result

    def publish_grounding(
        self, binding: StepGroundingBinding, robot_state: RobotState
    ) -> VisualOwnerPublicationRecord:
        """Persist a current source binding; native and safety checks remain required."""
        with self._lock:
            self.check_active(robot_state)
            if type(binding) is not StepGroundingBinding:
                raise TypeError("complete concrete grounding binding required")
            current = self.publication
            if self._operational_owner is not None:
                _bind_observation_policy(
                    self._operational_owner, self._last_observation, "grounding",
                    binding.original_requirements.ordinary_ttl_s,
                    {"requirement": binding.original_requirements.to_payload()},
                )
                if self._last_observation is None or (
                    binding.observation_id != self._last_observation.observation_id
                    or binding.observation_checksum_sha256 != self._last_observation.checksum_sha256
                    or _check_observation(
                        self._last_observation, "grounding",
                        max_age_s=binding.original_requirements.ordinary_ttl_s,
                    ) is not True
                ):
                    raise RuntimeError("original grounding acquisition window unavailable")
            checkpoint = current.checkpoint
            checkpoint = checkpoint.model_copy(
                update={
                    "checkpoint_id": (
                        f"visual-ground-{current.owner_revision + 1}-{binding.binding_hash[:24]}"
                    ),
                    "updated_at": datetime.now(UTC),
                    "robot_state": robot_state.model_dump(mode="json"),
                    "safety_state": {
                        **checkpoint.safety_state,
                        "grounding_binding_hash": binding.binding_hash,
                        "original_requirements_hash": binding.original_requirements.digest(),
                    },
                    "checkpoint_hash": "",
                },
                deep=True,
            )
            checkpoint = checkpoint.model_copy(
                update={"checkpoint_hash": checkpoint_digest(checkpoint)}
            )
            published = self.source.event_repository.publish_visual_boundary_if_current(
                task_id=current.identity.task_id,
                owner_epoch=current.identity.owner_epoch,
                expected_owner_revision=current.owner_revision,
                expected_contract_hash=current.to_payload()["contract_hash"],
                expected_checkpoint_hash=current.checkpoint.checkpoint_hash,
                checkpoint=checkpoint,
                grounding=binding,
                state_generation=binding.state_generation,
            )
            if published is None:
                raise RuntimeError("grounding source is stale or differs from original policy")
            self.check_active(robot_state)
            return published

    def reserve_effect_capture(
        self,
        completion: VisualEffectCompletion,
        robot_state: RobotState,
        *,
        purpose: str = "AFTER_EFFECT",
    ) -> str:
        """Allocate a result-bound camera read, preserving the existing retry pool.

        Result consistency is checked here. Authentic action admission still
        belongs to the live owner's sole native/SafetyShield/SkillExecutor path.
        A resumed coordinator cannot reconstruct these local effect handles.
        """
        with self._lock:
            self.check_active(robot_state)
            if type(completion) is not VisualEffectCompletion or not self._can_capture_effects:
                raise RuntimeError("result capture requires this live owner and typed completion")
            if purpose not in {"AFTER_EFFECT", "POST_HOLD", "TERMINAL"}:
                raise RuntimeError("registered effect capture purpose required")
            source = completion.to_payload()
            receipt = completion.digest()
            known_effect = self._returned_effects.get(receipt)
            if purpose != "AFTER_EFFECT" and known_effect != completion.to_json():
                raise RuntimeError("later phase requires the owned returned effect source")
            current, original = self.supervision_source_publication, self.original
            result = SkillExecutionResult.model_validate_json(json.dumps(source["result"]))
            step_id = current.checkpoint.current_step_id
            requirement = original.requirements[step_id]
            execution = original.contract.model_dump(mode="json")
            grounding = current.to_payload()["grounding"]
            if grounding is not None:
                execution["steps"] = [
                    grounding["grounded_step"] if step["step_id"] == step_id else step
                    for step in execution["steps"]
                ]
                if purpose == "AFTER_EFFECT" and not (
                    aware(datetime.fromisoformat(grounding["created_at"]))
                    <= aware(datetime.fromisoformat(source["started_at"]))
                    < aware(datetime.fromisoformat(grounding["valid_until"]))
                ):
                    raise RuntimeError(
                        "effect source did not start inside original grounding validity"
                    )
            now = datetime.now(UTC)
            if (
                source["task_id"] != current.identity.task_id
                or source["plan_id"] != current.identity.plan_id
                or source["robot_id"] != current.identity.robot_id
                or source["step_id"] != step_id
                or source["attempt"] < 1
                or source["attempt"] > requirement.original_step.retry_limit + 1
                or (source["plan_version"], source["command_seq"])
                != (current.checkpoint.plan_version, current.checkpoint.command_seq)
                or source["source_checkpoint_hash"] != current.checkpoint.checkpoint_hash
                or (
                    purpose == "AFTER_EFFECT"
                    and source["execution_payload_hash"] != digest(execution)
                )
                or dict(source["source_hashes"]) != dict(original.source_hashes)
                or (
                    result.task_id,
                    result.step_id,
                    result.skill,
                    result.scene_version,
                    result.plan_version,
                    result.command_seq,
                )
                != (
                    current.identity.task_id,
                    step_id,
                    requirement.original_step.skill,
                    original.contract.scene_version,
                    current.checkpoint.plan_version,
                    current.checkpoint.command_seq,
                )
                or not result.success
                or not original.registered_at
                <= aware(datetime.fromisoformat(source["started_at"]))
                <= result.timestamp
                <= aware(datetime.fromisoformat(source["returned_at"]))
                <= now
                or self._last_observation is None
                or (
                    purpose == "AFTER_EFFECT"
                    and source["before_observation_id"] != self._last_observation.observation_id
                )
            ):
                raise RuntimeError("typed effect completion source differs from current owner")
            key = (receipt, purpose)
            if key in self._effect_capture_claims:
                raise RuntimeError("effect camera source already claimed; no replay")
            names = {spec.name for spec in requirement.postconditions}
            if purpose == "POST_HOLD" and (
                requirement.original_step.skill != SkillName.LIFT
                or not {"object_held", "object_lifted", "object_stable"} <= names
            ):
                raise RuntimeError("full post-hold phase requirements are unregistered")
            if purpose == "TERMINAL" and (
                step_id != original.contract.steps[-1].step_id
                or not set(original.contract.completion_criteria) <= names
            ):
                raise RuntimeError("full terminal phase requirements are unregistered")
            if (
                purpose != "AFTER_EFFECT"
                and (receipt, "AFTER_EFFECT") not in self._effect_capture_claims
            ):
                raise RuntimeError("later phase requires the owned returned effect source")
            claim = digest(["worker-effect-capture", receipt, purpose])
            self._returned_effects[receipt] = completion.to_json()
            self._effect_capture_claims.add(key)
            self._claims[claim] = "ORDINARY_CAPTURE"
            self._capture_sources[claim] = (now, self._last_observation.model_copy(deep=True))
            self._operational_begin(claim, "capture")
            return claim

    def complete_step(self, step_id: str, robot_state: RobotState) -> VisualOwnerPublicationRecord:
        """Advance the original prefix only from stored full canonical phase routes."""
        with self._lock:
            self.check_active(robot_state)
            current, original = self.publication, self.original
            if step_id != current.checkpoint.current_step_id:
                raise RuntimeError("completion cursor differs from original pending step")
            required = {"AFTER_EFFECT"}
            if original.requirements[step_id].original_step.skill == SkillName.LIFT:
                required.add("POST_HOLD")
            if step_id == original.contract.steps[-1].step_id:
                required.add("TERMINAL")
            completion_hashes = set()
            effect_attempt = None
            for phase in required:
                event_key = self._phase_receipts.get((step_id, phase))
                record = (
                    self.source.event_repository.get_visual_verification_route(
                        current.identity.task_id, event_key
                    )
                    if event_key is not None
                    else None
                )
                if record is None:
                    raise RuntimeError("full canonical effect phase not stored")
                body = record.to_payload()
                incoming = body["input"]
                completion = incoming["completion"]
                if (
                    record.route != "CONTINUE"
                    or incoming["phase"] != phase
                    or incoming["step_id"] != step_id
                    or completion is None
                    or incoming["online"]["context_hash"] != current.checkpoint.checkpoint_hash
                    or incoming["original"] != original.to_payload()
                ):
                    raise RuntimeError("stored canonical phase differs from current original")
                completion_hashes.add(digest(completion))
                effect_attempt = completion["attempt"]
            if len(completion_hashes) != 1:
                raise RuntimeError("canonical phases bind different actual effect receipts")
            checkpoint = current.checkpoint
            done = [*checkpoint.completed_step_ids, step_id]
            pending = [step.step_id for step in original.contract.steps[len(done) :]]
            checkpoint = checkpoint.model_copy(
                update={
                    "checkpoint_id": (
                        f"visual-step-{current.owner_revision + 1}-"
                        f"{checkpoint.checkpoint_hash[:24]}"
                    ),
                    "completed_step_ids": done,
                    "pending_step_ids": pending,
                    "current_step_index": len(done),
                    "current_step_id": pending[0] if pending else "",
                    "last_successful_step_id": step_id,
                    "step_attempts": {**checkpoint.step_attempts, step_id: effect_attempt},
                    "robot_state": robot_state.model_dump(mode="json"),
                    "updated_at": datetime.now(UTC),
                    "checkpoint_hash": "",
                    "execution_state": "STEP_SUCCEEDED" if pending else "COMPLETED",
                },
                deep=True,
            )
            checkpoint = checkpoint.model_copy(
                update={"checkpoint_hash": checkpoint_digest(checkpoint)}
            )
            result = self.source.event_repository.publish_visual_boundary_if_current(
                task_id=current.identity.task_id,
                owner_epoch=current.identity.owner_epoch,
                expected_owner_revision=current.owner_revision,
                expected_contract_hash=current.to_payload()["contract_hash"],
                expected_checkpoint_hash=current.checkpoint.checkpoint_hash,
                checkpoint=checkpoint,
                grounding=None,
                state_generation=current.state_generation + 1,
            )
            if result is None:
                raise RuntimeError("canonical completion cursor publication is stale")
            self.check_active(robot_state)
            return result
