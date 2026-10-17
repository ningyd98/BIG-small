"""内存仓储实现，主要用于测试和本地开发，不作为持久真源。

In-memory EventAutonomyRepository — thread-safe, test/CI only.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from cloud_edge_robot_arm.contracts.models import (
    ActiveContractStatus,
    ActiveTaskContractRecord,
    CommandAck,
    CompletionSummary,
    EdgeEvent,
    ExecutionCheckpoint,
    FailureSummary,
    LocalReplanningRequest,
    LocalReplanningResponse,
    MessageStatus,
    PendingMessage,
    RecoveryBudget,
    ReplanApplyRecord,
    TaskContract,
)
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import (
    IdempotencyConflictError,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _canonical_hash(value: Any) -> str:
    if isinstance(value, BaseModel):
        payload = value.model_dump(mode="json")
    else:
        payload = value
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _contract_hash(contract: TaskContract) -> str:
    return _canonical_hash(contract)


def _checkpoint_hash(checkpoint: ExecutionCheckpoint) -> str:
    payload = checkpoint.model_dump(mode="json")
    payload["checkpoint_hash"] = ""
    return _canonical_hash(payload)


def _apply_hash(record: ReplanApplyRecord) -> str:
    payload = record.model_dump(mode="json")
    payload["apply_hash"] = ""
    return _canonical_hash(payload)


if TYPE_CHECKING:
    from cloud_edge_robot_arm.edge.evidence.models import EvidenceVerdict
    from cloud_edge_robot_arm.edge.recovery.lifecycle import (
        RecoveryAuthorizationEvidence,
        RecoveryAuthorizationResult,
        RecoveryRecord,
        RecoveryReservationEvidence,
        RecoveryTransitionEvidence,
        VerificationBudgetRecord,
    )
    from cloud_edge_robot_arm.edge.recovery.verification_router import VerificationBudgetState
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_bootstrap import (
        VisualBootstrapDefinition,
        VisualBootstrapPromotionInput,
        VisualBootstrapRecord,
        VisualBootstrapTransitionInput,
        VisualBootstrapTransitionResult,
    )
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
        VisualOwnerPublicationRecord,
    )
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_supervision import (
        VisualSupervisionDefinition,
        VisualSupervisionRecord,
        VisualSupervisionTransitionInput,
        VisualSupervisionTransitionResult,
    )
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_verification import (
        VisualVerificationRouteInput,
        VisualVerificationRouteRecord,
        VisualVerificationRouteWriteResult,
    )
    from cloud_edge_robot_arm.vision.owner_registration import (
        StepGroundingBinding,
        VisualOriginalPlan,
    )


class InMemoryEventAutonomyRepository:
    """Thread-safe in-memory implementation for testing and CI."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: dict[str, EdgeEvent] = {}
        self._event_hashes: dict[str, str] = {}
        self._events_by_task: dict[str, list[str]] = {}
        self._budgets: dict[str, RecoveryBudget] = {}
        self._verification_budgets: dict[str, VerificationBudgetRecord] = {}
        self._recoveries: dict[str, RecoveryRecord] = {}
        self._recovery_initial_hashes: dict[str, str] = {}
        self._states: dict[str, str] = {}
        self._transitions: dict[str, list[dict[str, object]]] = {}
        self._failure_summaries: dict[str, FailureSummary] = {}
        self._failure_hashes: dict[str, str] = {}
        self._completion_summaries: dict[str, CompletionSummary] = {}
        self._completion_hashes: dict[str, str] = {}
        self._replan_requests: dict[str, LocalReplanningRequest] = {}
        self._replan_request_hashes: dict[str, str] = {}
        self._replan_idempotency: dict[str, str] = {}
        self._replan_results: dict[str, LocalReplanningResponse] = {}
        self._replan_result_hashes: dict[str, str] = {}
        self._outbox: dict[str, PendingMessage] = {}
        self._outbox_hashes: dict[str, str] = {}
        self._outbox_idempotency: dict[str, str] = {}
        self._plan_versions: dict[str, tuple[int, int]] = {}
        self._active_contracts: dict[str, ActiveTaskContractRecord] = {}
        self._contract_versions: dict[str, list[ActiveTaskContractRecord]] = {}
        self._checkpoints: dict[str, ExecutionCheckpoint] = {}
        self._checkpoint_hashes: dict[str, str] = {}
        self._checkpoints_by_task: dict[str, list[str]] = {}
        self._apply_records: dict[str, ReplanApplyRecord] = {}
        self._apply_by_request: dict[str, str] = {}
        self._apply_hashes: dict[str, str] = {}
        self._acks_by_key: dict[str, CommandAck] = {}
        self._ack_hashes: dict[str, str] = {}
        self._audit: dict[str, list[dict[str, object]]] = {}
        self._visual_bootstraps: dict[str, str] = {}
        self._visual_originals: dict[tuple[str, int], tuple[str, str]] = {}
        self._visual_publications: dict[tuple[str, int], str] = {}
        self._visual_verification_routes: dict[tuple[str, str], str] = {}
        self._visual_verification_sources: dict[tuple[str, str], str] = {}
        self._visual_supervision: dict[str, str] = {}
        self._visual_supervision_verified_bytes: dict[str, str] = {}

    def _visual_supervision_locked(self, task_id: str) -> VisualSupervisionRecord | None:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_supervision import (
            VisualSupervisionRecord,
        )

        raw = self._visual_supervision.get(task_id)
        if raw is None:
            return None
        if self._visual_supervision_verified_bytes.get(task_id) == raw:
            return VisualSupervisionRecord._from_verified_json(raw)
        record = VisualSupervisionRecord.from_json(raw)
        if record.definition.task_id != task_id:
            raise ValueError("stored supervision identity differs")
        self._visual_supervision_verified_bytes[task_id] = raw
        return record

    def get_visual_supervision_source_publication(
        self, task_id: str
    ) -> VisualOwnerPublicationRecord | None:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_supervision import (
            current_supervision_publication,
        )

        with self._lock:
            prior = self._visual_record_locked(task_id)
            if prior is None or self._replan_cancelled_locked(task_id):
                return None
            original = self._visual_original_locked(task_id, prior.checkpoint.plan_version)
            ancestor = (
                self._visual_record_locked(task_id, prior.owner_revision - 1)
                if prior.owner_revision > 1 else None
            )
            if (original is None or not self._visual_versions_match(original)
                or not current_supervision_publication(
                    prior, original, *self._visual_group_locked(task_id), ancestor, now=_utc_now()
                )):
                return None
            return prior.detached()

    def initialize_visual_supervision_if_absent(
        self, definition: VisualSupervisionDefinition
    ) -> VisualSupervisionRecord:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_supervision import (
            VisualSupervisionDefinition,
            VisualSupervisionRecord,
            validate_initial_supervision,
        )

        if type(definition) is not VisualSupervisionDefinition:
            raise ValueError("concrete supervision definition required")
        definition = VisualSupervisionDefinition.from_payload(definition.to_payload())
        task = definition.task_id
        with self._lock:
            stored = self._visual_supervision_locked(task)
            if stored is not None:
                if stored.definition.digest() != definition.digest():
                    raise IdempotencyConflictError("original supervision definition differs")
                return stored
            prior = self._visual_record_locked(task)
            if prior is None:
                raise IdempotencyConflictError("supervision requires current original source")
            original = self._visual_original_locked(task, prior.checkpoint.plan_version)
            ancestor = (
                self._visual_record_locked(task, prior.owner_revision - 1)
                if prior.owner_revision > 1 else None
            )
            if (original is None or not self._visual_versions_match(original)
                or not validate_initial_supervision(
                    definition, original, prior, ancestor, *self._visual_group_locked(task),
                    cancelled=self._replan_cancelled_locked(task), now=_utc_now(),
                    bootstrap=self._visual_bootstrap_for_original_locked(original),
                )):
                raise IdempotencyConflictError("supervision original source is unavailable")
            record = VisualSupervisionRecord.start(definition)
            self._visual_supervision[task] = record.to_json()
            return record

    def get_visual_supervision(self, task_id: str) -> VisualSupervisionRecord | None:
        with self._lock:
            return self._visual_supervision_locked(task_id)

    def transition_visual_supervision_if_current(
        self, *, request: VisualSupervisionTransitionInput
    ) -> VisualSupervisionTransitionResult | None:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_supervision import (
            VisualSupervisionTransitionInput,
            derive_supervision,
        )

        if type(request) is not VisualSupervisionTransitionInput:
            raise ValueError("concrete supervision transition required")
        request = VisualSupervisionTransitionInput.from_json(request.to_json())
        task = request.task_id
        with self._lock:
            stored = self._visual_supervision_locked(task)
            prior = self._visual_record_locked(task)
            if stored is None or prior is None:
                return None
            original = self._visual_original_locked(task, prior.checkpoint.plan_version)
            if original is None or not self._visual_versions_match(original):
                return None
            ancestor = (
                self._visual_record_locked(task, prior.owner_revision - 1)
                if prior.owner_revision > 1 else None
            )
            result = derive_supervision(
                stored, request, original, prior, ancestor, *self._visual_group_locked(task),
                cancelled=self._replan_cancelled_locked(task), now=_utc_now(),
            )
            if result is not None and result.write_disposition == "NEW_COMMIT":
                self._visual_supervision[task] = result.record.to_json()
            return result

    def _visual_bootstrap_locked(self, bootstrap_id: str) -> VisualBootstrapRecord | None:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_bootstrap import (
            VisualBootstrapRecord,
        )

        raw = self._visual_bootstraps.get(bootstrap_id)
        if raw is None:
            return None
        record = VisualBootstrapRecord.from_json(raw)
        if record.definition.bootstrap_id != bootstrap_id:
            raise ValueError("bootstrap indexed identity differs")
        return record

    def initialize_visual_bootstrap_if_absent(
        self, definition: VisualBootstrapDefinition
    ) -> VisualBootstrapRecord:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_bootstrap import (
            VisualBootstrapDefinition,
            VisualBootstrapRecord,
        )

        if type(definition) is not VisualBootstrapDefinition:
            raise ValueError("concrete bootstrap definition required")
        definition = VisualBootstrapDefinition.from_payload(definition.to_payload())
        initial = VisualBootstrapRecord.start(definition)
        with self._lock:
            existing = self._visual_bootstrap_locked(definition.bootstrap_id)
            if existing is not None:
                if existing.definition.digest() != definition.digest():
                    raise IdempotencyConflictError("bootstrap definition differs")
                return existing
            for key in self._visual_bootstraps:
                other = self._visual_bootstrap_locked(key)
                if other is not None and other.definition.episode_id == definition.episode_id:
                    raise IdempotencyConflictError("bootstrap episode belongs to another job/run")
            for task, version in self._visual_originals:
                original = self._visual_original_locked(task, version)
                if original is not None and (
                    original.identity.episode_id == definition.episode_id
                    or (original.identity.job_id, original.identity.run_id)
                    == (definition.lease.job_id, definition.lease.run_id)
                ):
                    raise IdempotencyConflictError("episode/job/run already has an original source")
            task = definition.episode_id
            if (
                any(value is not None for value in self._visual_group_locked(task))
                or self._contract_versions.get(task)
                or self._plan_versions.get(task)
                or self._checkpoints_by_task.get(task)
            ):
                raise IdempotencyConflictError("ordinary task rows already exist")
            self._visual_bootstraps[definition.bootstrap_id] = initial.to_json()
            return VisualBootstrapRecord.from_json(initial.to_json())

    def get_visual_bootstrap(self, bootstrap_id: str) -> VisualBootstrapRecord | None:
        with self._lock:
            return self._visual_bootstrap_locked(bootstrap_id)

    def transition_visual_bootstrap_if_current(
        self, *, request: VisualBootstrapTransitionInput
    ) -> VisualBootstrapTransitionResult | None:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_bootstrap import (
            VisualBootstrapTransitionInput,
            derive_bootstrap,
        )

        if type(request) is not VisualBootstrapTransitionInput:
            raise ValueError("concrete bootstrap transition required")
        request = VisualBootstrapTransitionInput.from_payload(request.to_payload())
        body = request.to_payload()
        with self._lock:
            current = self._visual_bootstrap_locked(body["bootstrap_id"])
            if current is None:
                return None
            for event in current.to_payload()["history"]:
                source = event.get("request", event.get("promotion"))
                if source["event_key"] == body["event_key"]:
                    if source != body:
                        raise IdempotencyConflictError("bootstrap event key changed source")
            try:
                result = derive_bootstrap(current, request, now=_utc_now())
            except (ValueError, TypeError):
                return None
            if result.write_disposition == "NEW_COMMIT":
                self._visual_bootstraps[body["bootstrap_id"]] = result.record.to_json()
            return result

    def _visual_original_locked(self, task_id: str, plan_version: int) -> VisualOriginalPlan | None:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
            original_from_payload,
        )

        stored = self._visual_originals.get((task_id, plan_version))
        if stored is None:
            return None
        original = original_from_payload(json.loads(stored[0]))
        if (
            original.digest() != stored[1]
            or original.identity.task_id != task_id
            or original.contract.plan_version != plan_version
        ):
            raise ValueError("stored original key/hash differs")
        return original

    def _visual_record_locked(
        self, task_id: str, revision: int | None = None
    ) -> VisualOwnerPublicationRecord | None:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
            VisualOwnerPublicationRecord,
        )

        if revision is None:
            revisions = [version for task, version in self._visual_publications if task == task_id]
            if not revisions:
                return None
            revision = max(revisions)
        raw = self._visual_publications.get((task_id, revision))
        if raw is None:
            return None
        record = VisualOwnerPublicationRecord.from_payload(json.loads(raw))
        if record.identity.task_id != task_id or record.owner_revision != revision:
            raise ValueError("stored publication key differs")
        return record

    def _visual_group_locked(self, task_id: str) -> tuple[Any, Any, Any, Any]:
        ids = self._checkpoints_by_task.get(task_id, [])
        return (
            self._active_contracts.get(task_id),
            self._checkpoints.get(ids[-1]) if ids else None,
            self._verification_budgets.get(task_id),
            self._budgets.get(task_id),
        )

    def _visual_versions_match(self, original: VisualOriginalPlan) -> bool:
        task, contract = original.identity.task_id, original.contract
        version = self._version_record(task, contract.plan_version)
        active = self._active_contracts.get(task)
        return (
            self._plan_versions.get(task) == (contract.plan_version, contract.command_seq)
            and version is not None
            and active is not None
            and version.model_dump(mode="json") == active.model_dump(mode="json")
        )

    def get_visual_original_plan(
        self, task_id: str, plan_version: int
    ) -> VisualOriginalPlan | None:
        with self._lock:
            return self._visual_original_locked(task_id, plan_version)

    def get_visual_owner_publication(self, task_id: str) -> VisualOwnerPublicationRecord | None:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
            current_publication,
        )

        with self._lock:
            record = self._visual_record_locked(task_id)
            if record is None:
                return None
            original = self._visual_original_locked(task_id, record.checkpoint.plan_version)
            previous = (
                self._visual_record_locked(task_id, record.owner_revision - 1)
                if record.owner_revision > 1
                else None
            )
            if (
                original is None
                or not self._visual_versions_match(original)
                or not current_publication(
                    record, original, *self._visual_group_locked(task_id), previous=previous
                )
            ):
                return None
            return record.detached()

    def _visual_bootstrap_for_original_locked(
        self, original: VisualOriginalPlan
    ) -> VisualBootstrapRecord | None:
        matching = []
        for key in self._visual_bootstraps:
            record = self._visual_bootstrap_locked(key)
            if record is not None and (
                record.definition.episode_id == original.identity.episode_id
                or (record.definition.lease.job_id, record.definition.lease.run_id)
                == (original.identity.job_id, original.identity.run_id)
            ):
                matching.append(record)
        if len(matching) > 1:
            raise IdempotencyConflictError("original spans different bootstrap source groups")
        return matching[0] if matching else None

    def initialize_visual_owner_if_absent(
        self,
        original: VisualOriginalPlan,
        checkpoint: ExecutionCheckpoint,
        verification_state: VerificationBudgetState,
        retry_budget: RecoveryBudget,
        *,
        bootstrap_promotion: VisualBootstrapPromotionInput | None = None,
    ) -> VisualOwnerPublicationRecord:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
            canonical,
            current_publication,
            initial_inputs,
            publication,
            retry_definition,
            validate_group,
            verification_definition,
        )

        original, checkpoint, pool, retry, key = initial_inputs(
            original, checkpoint, verification_state, retry_budget
        )
        if bootstrap_promotion is not None:
            from cloud_edge_robot_arm.repositories.event_autonomy.visual_bootstrap import (
                VisualBootstrapPromotionInput,
            )

            if type(bootstrap_promotion) is not VisualBootstrapPromotionInput:
                raise ValueError("concrete detached bootstrap promotion required")
            bootstrap_promotion = VisualBootstrapPromotionInput.from_payload(
                bootstrap_promotion.to_payload()
            )
            if canonical(bootstrap_promotion.to_payload()["original"]) != canonical(
                original.to_payload()
            ):
                raise IdempotencyConflictError("promotion differs from incoming full original")
        task = original.identity.task_id
        with self._lock:
            bootstrap = self._visual_bootstrap_for_original_locked(original)
            first = self._visual_record_locked(task, 1)
            promoted: VisualBootstrapRecord | None = None
            promoted_json: str | None = None
            if bootstrap is None:
                if bootstrap_promotion is not None:
                    raise IdempotencyConflictError("promotion has no current stored bootstrap")
            else:
                from cloud_edge_robot_arm.repositories.event_autonomy.visual_bootstrap import (
                    VisualBootstrapRecord,
                    promote_bootstrap,
                )

                if bootstrap_promotion is None:
                    raise IdempotencyConflictError("existing bootstrap requires atomic promotion")
                adopted = bootstrap.terminal_reason == "original_adopted"
                if (first is None and adopted) or (first is not None and not adopted):
                    raise IdempotencyConflictError("bootstrap/ordinary source group is partial")
                source = bootstrap_promotion.to_payload()
                for event in bootstrap.to_payload()["history"]:
                    if "request" in event and event["request"]["event_key"] == source["event_key"]:
                        raise IdempotencyConflictError(
                            "promotion event key belongs to another source"
                        )
                try:
                    promoted = promote_bootstrap(
                        bootstrap, bootstrap_promotion, pool.state, retry, now=_utc_now()
                    )
                    promoted = VisualBootstrapRecord.from_json(promoted.to_json())
                    promoted_json = promoted.to_json()
                except (ValueError, TypeError) as error:
                    raise IdempotencyConflictError("current bootstrap promotion differs") from error
            if first is not None:
                self._ensure_same_hash(
                    "VisualOwnerInitial", task, first.to_payload()["operation_hash"], key
                )
                existing = self._visual_record_locked(task)
                stored_original = self._visual_original_locked(task, original.contract.plan_version)
                previous = (
                    self._visual_record_locked(task, existing.owner_revision - 1)
                    if existing and existing.owner_revision > 1
                    else None
                )
                if (
                    existing is None
                    or stored_original is None
                    or stored_original.digest() != original.digest()
                    or not self._visual_versions_match(original)
                    or not current_publication(
                        existing,
                        stored_original,
                        *self._visual_group_locked(task),
                        previous=previous,
                    )
                ):
                    raise IdempotencyConflictError(
                        "visual source currently unavailable; fresh publication required"
                    )
                return existing.detached()
            if any(name == task for name, _ in self._visual_originals):
                raise IdempotencyConflictError("original sidecar exists without publication")
            active, prior_checkpoint, prior_pool, prior_retry = self._visual_group_locked(task)
            present = [
                value is not None for value in (active, prior_checkpoint, prior_pool, prior_retry)
            ]
            if bootstrap is not None and any(present):
                raise IdempotencyConflictError(
                    "ordinary rows exist before atomic bootstrap adoption"
                )
            if any(present):
                if not all(present):
                    raise IdempotencyConflictError("partial existing visual task group")
                try:
                    validate_group(original, active, prior_checkpoint, prior_pool, prior_retry)
                    if (
                        canonical(prior_checkpoint.model_dump(mode="json"))
                        != canonical(checkpoint.model_dump(mode="json"))
                        or not self._visual_versions_match(original)
                        or verification_definition(prior_pool) != verification_definition(pool)
                        or retry_definition(prior_retry) != retry_definition(retry)
                    ):
                        raise ValueError("existing source definition differs")
                except (ValueError, TypeError) as error:
                    raise IdempotencyConflictError("existing visual source differs") from error
                pool, retry = prior_pool.detached(), prior_retry.model_copy(deep=True)
            else:
                if self._contract_versions.get(task) or self._plan_versions.get(task):
                    raise IdempotencyConflictError("partial existing contract/version history")
                if checkpoint.checkpoint_id in self._checkpoints:
                    raise IdempotencyConflictError(
                        "initial checkpoint identity already belongs to a source"
                    )
                now = _utc_now()
                active = ActiveTaskContractRecord(
                    task_id=task,
                    plan_id=original.identity.plan_id,
                    robot_id=original.identity.robot_id,
                    plan_version=original.contract.plan_version,
                    command_seq=original.contract.command_seq,
                    scene_version=original.contract.scene_version,
                    contract=original.contract,
                    status="ACTIVE",
                    created_at=now,
                    activated_at=now,
                    contract_hash=_contract_hash(original.contract),
                )
            saved = publication(
                original,
                checkpoint,
                pool,
                retry,
                revision=1,
                generation=0,
                source_revision=None,
                operation_hash=key,
            )
            # All validation completed before the first mutation under this lock.
            if not any(present):
                self._active_contracts[task] = active
                self._contract_versions[task] = [active]
                self._plan_versions[task] = (active.plan_version, active.command_seq)
                self._checkpoints[checkpoint.checkpoint_id] = checkpoint
                self._checkpoint_hashes[checkpoint.checkpoint_id] = checkpoint.checkpoint_hash
                self._checkpoints_by_task[task] = [checkpoint.checkpoint_id]
                self._verification_budgets[task] = pool
                self._budgets[task] = retry
            self._visual_originals[(task, original.contract.plan_version)] = (
                canonical(original.to_payload()),
                original.digest(),
            )
            self._visual_publications[(task, 1)] = canonical(saved.to_payload())
            if promoted_json is not None and promoted is not None:
                self._visual_bootstraps[promoted.definition.bootstrap_id] = promoted_json
            return saved.detached()

    def publish_visual_boundary_if_current(
        self,
        *,
        task_id: str,
        owner_epoch: str,
        expected_owner_revision: int,
        expected_contract_hash: str,
        expected_checkpoint_hash: str,
        checkpoint: ExecutionCheckpoint,
        grounding: StepGroundingBinding | None,
        state_generation: int,
    ) -> VisualOwnerPublicationRecord | None:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
            canonical,
            counter,
            monotonic_pools,
            operation_hash,
            publication,
            record_binding_valid,
            validate_checkpoint,
            validate_grounding,
            validate_group,
        )

        counter(expected_owner_revision)
        counter(state_generation)
        key = operation_hash(
            task_id=task_id,
            owner_epoch=owner_epoch,
            expected_owner_revision=expected_owner_revision,
            expected_contract_hash=expected_contract_hash,
            expected_checkpoint_hash=expected_checkpoint_hash,
            checkpoint=checkpoint,
            grounding=grounding,
            state_generation=state_generation,
        )
        with self._lock:
            duplicate = self._visual_record_locked(task_id, expected_owner_revision + 1)
            if duplicate is not None and duplicate.to_payload()["operation_hash"] == key:
                return duplicate.detached()
            previous = self._visual_record_locked(task_id)
            if (
                previous is None
                or previous.owner_revision != expected_owner_revision
                or previous.identity.owner_epoch != owner_epoch
                or state_generation <= previous.state_generation
            ):
                return None
            original = self._visual_original_locked(task_id, previous.checkpoint.plan_version)
            active, current, pool, retry = self._visual_group_locked(task_id)
            if (
                original is None
                or any(value is None for value in (active, current, pool, retry))
                or not self._visual_versions_match(original)
                or active.contract_hash != expected_contract_hash
                or current.checkpoint_hash != expected_checkpoint_hash
                or current.checkpoint_hash != previous.checkpoint.checkpoint_hash
            ):
                return None
            try:
                ancestor = (
                    self._visual_record_locked(task_id, previous.owner_revision - 1)
                    if previous.owner_revision > 1
                    else None
                )
                if not record_binding_valid(previous, original, ancestor):
                    return None
                validate_group(original, active, current, pool, retry)
                if not monotonic_pools(previous, pool, retry):
                    return None
                next_checkpoint = validate_checkpoint(original, checkpoint, current)
                bound = validate_grounding(
                    original, previous, next_checkpoint, grounding, state_generation
                )
                saved = publication(
                    original,
                    next_checkpoint,
                    pool,
                    retry,
                    revision=previous.owner_revision + 1,
                    generation=state_generation,
                    source_revision=previous.owner_revision,
                    operation_hash=key,
                    grounding=bound,
                )
            except (ValueError, TypeError):
                return None
            collision = self._checkpoints.get(next_checkpoint.checkpoint_id)
            if collision is not None and canonical(collision.model_dump(mode="json")) != canonical(
                next_checkpoint.model_dump(mode="json")
            ):
                return None
            self._checkpoints[next_checkpoint.checkpoint_id] = next_checkpoint
            self._checkpoint_hashes[next_checkpoint.checkpoint_id] = next_checkpoint.checkpoint_hash
            ids = self._checkpoints_by_task.setdefault(task_id, [])
            if next_checkpoint.checkpoint_id not in ids:
                ids.append(next_checkpoint.checkpoint_id)
            self._visual_publications[(task_id, saved.owner_revision)] = canonical(
                saved.to_payload()
            )
            return saved.detached()

    def get_visual_verification_route(
        self,
        task_id: str,
        event_key: str,
    ) -> VisualVerificationRouteRecord | None:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_verification import (
            VisualVerificationRouteRecord,
        )

        with self._lock:
            raw = self._visual_verification_routes.get((task_id, event_key))
            if raw is None:
                return None
            record = VisualVerificationRouteRecord.from_json(raw)
            if record.to_payload()["input"]["original"]["identity"]["task_id"] != task_id:
                raise ValueError("stored verification task differs")
            return record

    def route_visual_verification_if_current(
        self,
        *,
        request: VisualVerificationRouteInput,
    ) -> VisualVerificationRouteWriteResult | None:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import canonical
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_verification import (
            VisualVerificationRouteInput,
            VisualVerificationRouteRecord,
            VisualVerificationRouteWriteResult,
            derive_route,
            historical_duplicate,
        )

        if type(request) is not VisualVerificationRouteInput:
            raise ValueError("concrete source routing input required")
        request = VisualVerificationRouteInput.from_json(request.to_json())
        task_id = request.task_id
        with self._lock:
            raw = self._visual_verification_routes.get((task_id, request.event_key))
            same_event = raw is not None
            if raw is None:
                raw = self._visual_verification_sources.get((task_id, request.source_key()))
            if raw is not None:
                return historical_duplicate(
                    request, VisualVerificationRouteRecord.from_json(raw), same_event=same_event
                )
            prior = self._visual_record_locked(task_id)
            if prior is None:
                return None
            original = self._visual_original_locked(task_id, prior.checkpoint.plan_version)
            if original is None or not self._visual_versions_match(original):
                return None
            ancestor = (
                self._visual_record_locked(task_id, prior.owner_revision - 1)
                if prior.owner_revision > 1
                else None
            )
            values = derive_route(
                request,
                original,
                prior,
                ancestor,
                *self._visual_group_locked(task_id),
                cancelled=self._replan_cancelled_locked(task_id),
                now=_utc_now(),
            )
            if values is None:
                return None
            record, pool, produced = values
            # Validate and encode every immutable row before the first mutation.
            history = record.to_json()
            saved = canonical(produced.to_payload())
            self._verification_budgets[task_id] = pool
            self._visual_publications[(task_id, produced.owner_revision)] = saved
            self._visual_verification_routes[(task_id, request.event_key)] = history
            self._visual_verification_sources[(task_id, request.source_key())] = history
            return VisualVerificationRouteWriteResult(record, "NEW_COMMIT")

    # ── generic idempotency helpers ───────────────────────────────────────

    @staticmethod
    def _ensure_same_hash(entity: str, key: str, existing_hash: str, new_hash: str) -> None:
        if existing_hash != new_hash:
            raise IdempotencyConflictError(f"{entity} idempotency conflict for key {key!r}")

    # ── Events ──────────────────────────────────────────────────────────

    def save_event(self, event: EdgeEvent) -> EdgeEvent:
        with self._lock:
            payload_hash = _canonical_hash(event)
            existing = self._events.get(event.event_id)
            if existing is not None:
                self._ensure_same_hash(
                    "EdgeEvent", event.event_id, self._event_hashes[event.event_id], payload_hash
                )
                return existing
            saved = event.model_copy(update={"event_hash": event.event_hash or payload_hash})
            self._events[event.event_id] = saved
            self._event_hashes[event.event_id] = payload_hash
            self._events_by_task.setdefault(event.task_id, []).append(event.event_id)
            return saved

    def get_event(self, event_id: str) -> EdgeEvent | None:
        with self._lock:
            event = self._events.get(event_id)
            return None if event is None else event.model_copy(deep=True)

    def list_events(self, task_id: str) -> list[EdgeEvent]:
        with self._lock:
            ids = self._events_by_task.get(task_id, [])
            return [self._events[eid].model_copy(deep=True) for eid in ids if eid in self._events]

    def mark_event_handled(self, event_id: str, handled_at: datetime | None = None) -> bool:
        return event_id in self._events

    # ── Retry Budget ────────────────────────────────────────────────────

    def save_retry_budget(self, budget: RecoveryBudget) -> RecoveryBudget:
        with self._lock:
            snapshot = budget.model_copy(deep=True)
            self._budgets[budget.task_id] = snapshot
            return snapshot

    def get_retry_budget(self, task_id: str) -> RecoveryBudget | None:
        with self._lock:
            budget = self._budgets.get(task_id)
            return None if budget is None else budget.model_copy(deep=True)

    def initialize_retry_budget_if_absent(self, budget: RecoveryBudget) -> RecoveryBudget:
        """Create a frozen task pool once without resetting spent counts or its deadline."""
        budget = RecoveryBudget.model_validate(budget.model_dump())
        with self._lock:
            existing = self._budgets.get(budget.task_id)
            if existing is None:
                existing = budget.model_copy(deep=True)
                self._budgets[budget.task_id] = existing
            return existing.model_copy(deep=True)

    def consume_retry_if_available(
        self,
        task_id: str,
        step_id: str,
        skill: str,
        expected_count: int,
        event_id: str = "",
    ) -> tuple[bool, RecoveryBudget | None]:
        with self._lock:
            return self._consume_retry_locked(task_id, step_id, skill, expected_count, event_id)

    def _consume_retry_locked(
        self,
        task_id: str,
        step_id: str,
        skill: str,
        expected_count: int,
        event_id: str = "",
        *,
        persist: bool = True,
    ) -> tuple[bool, RecoveryBudget | None]:
        budget = self._budgets.get(task_id)
        if budget is None:
            return False, None
        if budget.retry_count_used != expected_count:
            return False, budget.model_copy(deep=True)
        if budget.remaining_retries <= 0:
            return False, budget.model_copy(deep=True)
        if event_id and budget.event_retry_counts.get(event_id, 0) > 0:
            return False, budget.model_copy(deep=True)

        step_counts = dict(budget.step_retry_counts)
        skill_counts = dict(budget.skill_retry_counts)
        event_counts = dict(budget.event_retry_counts)
        step_count = step_counts.get(step_id, 0)
        skill_count = skill_counts.get(skill, 0)
        task_count = budget.task_retry_count
        effective_remaining = min(
            max(0, budget.task_total_retry_limit - task_count),
            max(0, budget.per_step_retry_limit - step_count),
            max(0, budget.per_skill_retry_limit - skill_count),
            budget.remaining_retries,
        )
        if effective_remaining <= 0:
            return False, budget.model_copy(deep=True)

        now = _utc_now()
        if step_id:
            step_counts[step_id] = step_count + 1
        if skill:
            skill_counts[skill] = skill_count + 1
        if event_id:
            event_counts[event_id] = 1
        updated = budget.model_copy(
            update={
                "retry_count_used": budget.retry_count_used + 1,
                "task_retry_count": budget.task_retry_count + 1,
                "step_retry_counts": step_counts,
                "skill_retry_counts": skill_counts,
                "event_retry_counts": event_counts,
                "remaining_retries": budget.remaining_retries - 1,
                "updated_at": now,
            },
            deep=True,
        )
        if persist:
            self._budgets[task_id] = updated
        return True, updated.model_copy(deep=True)

    def initialize_verification_budget_if_absent(
        self,
        task_id: str,
        state: VerificationBudgetState,
    ) -> VerificationBudgetRecord:
        from cloud_edge_robot_arm.edge.recovery.lifecycle import VerificationBudgetRecord

        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("nonempty task identity required")
        with self._lock:
            existing = self._verification_budgets.get(task_id)
            if existing is None:
                existing = VerificationBudgetRecord.create(task_id, state)
                retry = self._budgets.get(task_id)
                existing.state.remaining_retries = min(
                    max(0, existing.state.limits.max_retries - retry.task_retry_count)
                    if retry
                    else 0,
                    retry.remaining_retries if retry else 0,
                    max(0, retry.task_total_retry_limit - retry.task_retry_count) if retry else 0,
                )
                if (
                    retry
                    and retry.retry_deadline
                    and existing.state.deadline_at > retry.retry_deadline
                ):
                    copied = existing.state
                    copied.deadline_at = retry.retry_deadline
                    existing = VerificationBudgetRecord.create(task_id, copied)
                existing = VerificationBudgetRecord.create(task_id, existing.state)
                self._verification_budgets[task_id] = existing
            return existing.detached()

    def get_verification_budget(self, task_id: str) -> VerificationBudgetRecord | None:
        with self._lock:
            existing = self._verification_budgets.get(task_id)
            return existing.detached() if existing else None

    def initialize_recovery_if_absent(self, record: RecoveryRecord) -> RecoveryRecord:
        from cloud_edge_robot_arm.edge.recovery.lifecycle import validate_detected

        record = record.detached()
        with self._lock:
            existing = self._recoveries.get(record.recovery_id)
            if existing is not None:
                self._ensure_same_hash(
                    "RecoveryRecord",
                    record.recovery_id,
                    self._recovery_initial_hashes[record.recovery_id],
                    record.content_hash(),
                )
                return existing.detached()
            if any(item.event_id == record.event_id for item in self._recoveries.values()):
                raise IdempotencyConflictError("event already has a recovery record")
            if any(
                item.attempt_id == record.attempt_id and item.task_id == record.task_id
                for item in self._recoveries.values()
            ):
                raise ValueError("execution attempt already belongs to a failure event")
            validate_detected(
                record,
                self._events.get(record.event_id),
                self._verification_budgets.get(record.task_id),
            )
            self._recoveries[record.recovery_id] = record
            self._recovery_initial_hashes[record.recovery_id] = record.content_hash()
            return record.detached()

    def get_recovery(self, recovery_id: str) -> RecoveryRecord | None:
        with self._lock:
            record = self._recoveries.get(recovery_id)
            return record.detached() if record else None

    def list_unresolved_recoveries(self, task_id: str) -> list[RecoveryRecord]:
        with self._lock:
            return [
                record.detached()
                for record in self._recoveries.values()
                if record.task_id == task_id
                and not (
                    record.state == "VERIFIED_RESOLVED" and record.evidence_scope == "ACTUAL_SOURCE"
                )
            ]

    def list_recoveries(self, task_id: str) -> list[RecoveryRecord]:
        with self._lock:
            return [
                record.detached()
                for record in self._recoveries.values()
                if record.task_id == task_id
            ]

    def advance_recovery_if_current(
        self,
        record: RecoveryRecord,
        *,
        expected_state: str,
        expected_revision: int,
        expected_budget_revision: int,
        verified_transition: RecoveryTransitionEvidence,
    ) -> RecoveryRecord | None:
        from cloud_edge_robot_arm.edge.recovery.lifecycle import transition_values

        with self._lock:
            current = self._recoveries.get(record.recovery_id)
            pool = self._verification_budgets.get(current.task_id) if current else None
            if not (
                all(
                    type(value) is int and value >= 0
                    for value in (expected_revision, expected_budget_revision)
                )
                and current
                and pool
                and current.state == expected_state
                and current.revision == expected_revision
                and pool.revision == expected_budget_revision
            ):
                return None
            if current.content_hash() != record.content_hash():
                raise ValueError("caller cannot overwrite immutable recovery source")
            ids = self._checkpoints_by_task.get(current.task_id, [])
            checkpoint = self._checkpoints.get(ids[-1]) if ids else None
            values = transition_values(
                current,
                pool,
                verified_transition,
                self._active_contracts.get(current.task_id),
                checkpoint,
                self._replan_cancelled_locked(current.task_id),
                _utc_now(),
            )
            if values is None:
                return current.detached()
            updated, next_pool = values
            self._recoveries[current.recovery_id] = updated
            self._verification_budgets[current.task_id] = next_pool
            return updated.detached()

    def reserve_reobservation_if_current(
        self,
        *,
        recovery_id: str,
        expected_revision: int,
        expected_budget_revision: int,
        reservation: RecoveryReservationEvidence | None = None,
    ) -> RecoveryRecord | None:
        from cloud_edge_robot_arm.edge.recovery.lifecycle import (
            reservation_available,
            reserved_values,
        )

        with self._lock:
            current = self._recoveries.get(recovery_id)
            pool = self._verification_budgets.get(current.task_id) if current else None
            if not (
                all(
                    type(value) is int and value >= 0
                    for value in (expected_revision, expected_budget_revision)
                )
                and current
                and pool
                and current.revision == expected_revision
                and pool.revision == expected_budget_revision
                and not self._replan_cancelled_locked(current.task_id)
            ):
                return None
            ids = self._checkpoints_by_task.get(current.task_id, [])
            checkpoint = self._checkpoints.get(ids[-1]) if ids else None
            if not reservation_available(
                current,
                reservation,
                self._active_contracts.get(current.task_id),
                checkpoint,
                self._replan_cancelled_locked(current.task_id),
                _utc_now(),
            ):
                return None
            values = reserved_values(current, pool, _utc_now())
            if values is None:
                return None
            updated, next_pool = values
            self._recoveries[recovery_id] = updated
            self._verification_budgets[current.task_id] = next_pool
            return updated.detached()

    def consume_retry_and_authorize_recovery_if_current(
        self,
        *,
        recovery_id: str,
        expected_recovery_revision: int,
        expected_verification_budget_revision: int,
        expected_retry_count: int,
        step_id: str,
        skill: str,
        authorization: RecoveryAuthorizationEvidence,
    ) -> RecoveryAuthorizationResult:
        from cloud_edge_robot_arm.edge.recovery.lifecycle import (
            RecoveryAuthorizationResult,
            authorization_reasons,
            authorized_values,
        )

        with self._lock:
            record = self._recoveries.get(recovery_id)
            pool = self._verification_budgets.get(record.task_id) if record else None
            budget = self._budgets.get(record.task_id) if record else None
            reasons: tuple[str, ...] = ("authorization_compare_and_set_conflict",)
            if (
                all(
                    type(value) is int and value >= 0
                    for value in (
                        expected_recovery_revision,
                        expected_verification_budget_revision,
                        expected_retry_count,
                    )
                )
                and record
                and pool
                and budget
                and record.revision == expected_recovery_revision
                and pool.revision == expected_verification_budget_revision
                and budget.retry_count_used == expected_retry_count
            ):
                ids = self._checkpoints_by_task.get(record.task_id, [])
                checkpoint = self._checkpoints.get(ids[-1]) if ids else None
                now = _utc_now()
                reasons = authorization_reasons(
                    record,
                    pool,
                    budget,
                    self._events.get(record.event_id),
                    self._active_contracts.get(record.task_id),
                    checkpoint,
                    self._replan_cancelled_locked(record.task_id),
                    authorization,
                    step_id,
                    skill,
                    now,
                )
                if not reasons:
                    consumed, retry = self._consume_retry_locked(
                        record.task_id,
                        step_id,
                        skill,
                        expected_retry_count,
                        record.event_id,
                        persist=False,
                    )
                    if consumed and retry:
                        updated, next_pool = authorized_values(
                            record, pool, retry, authorization, now
                        )
                        self._budgets[record.task_id] = retry
                        self._recoveries[recovery_id] = updated
                        self._verification_budgets[record.task_id] = next_pool
                        return RecoveryAuthorizationResult(
                            True,
                            updated.detached(),
                            retry.model_copy(deep=True),
                            next_pool.detached(),
                            (),
                        )
                    reasons = ("retry_authority_exhausted",)
            return RecoveryAuthorizationResult(
                False,
                record.detached() if record else None,
                budget.model_copy(deep=True) if budget else None,
                pool.detached() if pool else None,
                reasons,
            )

    # ── State Machine ───────────────────────────────────────────────────

    def save_state(self, task_id: str, state: str, reason: str, event_id: str = "") -> None:
        with self._lock:
            self._states[task_id] = state

    def get_state(self, task_id: str) -> str | None:
        with self._lock:
            return self._states.get(task_id)

    def save_state_transition(
        self, task_id: str, from_state: str, to_state: str, reason: str, event_id: str = ""
    ) -> None:
        with self._lock:
            entry: dict[str, object] = {
                "from_state": from_state,
                "to_state": to_state,
                "reason": reason,
                "event_id": event_id,
                "timestamp": _utc_now().isoformat(),
            }
            self._transitions.setdefault(task_id, []).append(entry)
            self._states[task_id] = to_state

    def list_state_transitions(self, task_id: str) -> list[dict[str, object]]:
        with self._lock:
            return deepcopy(self._transitions.get(task_id, []))

    # ── Failure Summary ─────────────────────────────────────────────────

    def save_failure_summary(self, summary: FailureSummary) -> FailureSummary:
        with self._lock:
            payload_hash = _canonical_hash(summary)
            existing = self._failure_summaries.get(summary.summary_id)
            if existing is not None:
                self._ensure_same_hash(
                    "FailureSummary",
                    summary.summary_id,
                    self._failure_hashes[summary.summary_id],
                    payload_hash,
                )
                return existing
            saved = summary.model_copy(
                update={"summary_hash": summary.summary_hash or payload_hash}
            )
            self._failure_summaries[summary.summary_id] = saved
            self._failure_hashes[summary.summary_id] = payload_hash
            return saved

    def get_failure_summary(self, summary_id: str) -> FailureSummary | None:
        with self._lock:
            summary = self._failure_summaries.get(summary_id)
            return None if summary is None else summary.model_copy(deep=True)

    # ── Completion Summary ──────────────────────────────────────────────

    def save_completion_summary(self, summary: CompletionSummary) -> CompletionSummary:
        with self._lock:
            payload_hash = _canonical_hash(summary)
            existing = self._completion_summaries.get(summary.summary_id)
            if existing is not None:
                if existing.summary_hash and existing.summary_hash == summary.summary_hash:
                    return existing
                self._ensure_same_hash(
                    "CompletionSummary",
                    summary.summary_id,
                    self._completion_hashes[summary.summary_id],
                    payload_hash,
                )
                return existing
            saved = summary.model_copy(
                update={"summary_hash": summary.summary_hash or payload_hash}
            )
            self._completion_summaries[summary.summary_id] = saved
            self._completion_hashes[summary.summary_id] = payload_hash
            return saved

    def get_completion_summary(self, summary_id: str) -> CompletionSummary | None:
        with self._lock:
            summary = self._completion_summaries.get(summary_id)
            return None if summary is None else summary.model_copy(deep=True)

    def get_completion_summary_for_task(self, task_id: str) -> CompletionSummary | None:
        with self._lock:
            matches = [s for s in self._completion_summaries.values() if s.task_id == task_id]
            return None if not matches else matches[-1].model_copy(deep=True)

    # ── Replan ──────────────────────────────────────────────────────────

    def save_replan_request(self, request: LocalReplanningRequest) -> LocalReplanningRequest:
        with self._lock:
            payload_hash = _canonical_hash(request)
            existing = self._replan_requests.get(request.request_id)
            if existing is not None:
                self._ensure_same_hash(
                    "LocalReplanningRequest",
                    request.request_id,
                    self._replan_request_hashes[request.request_id],
                    payload_hash,
                )
                return existing
            if request.idempotency_key:
                existing_id = self._replan_idempotency.get(request.idempotency_key)
                if existing_id is not None:
                    self._ensure_same_hash(
                        "LocalReplanningRequest",
                        request.idempotency_key,
                        self._replan_request_hashes[existing_id],
                        payload_hash,
                    )
                    return self._replan_requests[existing_id]
                self._replan_idempotency[request.idempotency_key] = request.request_id
            self._replan_requests[request.request_id] = request.model_copy(deep=True)
            self._replan_request_hashes[request.request_id] = payload_hash
            return self._replan_requests[request.request_id]

    def get_replan_request(self, request_id: str) -> LocalReplanningRequest | None:
        with self._lock:
            request = self._replan_requests.get(request_id)
            return None if request is None else request.model_copy(deep=True)

    def save_replan_result(self, result: LocalReplanningResponse) -> LocalReplanningResponse:
        with self._lock:
            payload_hash = _canonical_hash(result)
            existing = self._replan_results.get(result.request_id)
            if existing is not None:
                self._ensure_same_hash(
                    "LocalReplanningResponse",
                    result.request_id,
                    self._replan_result_hashes[result.request_id],
                    payload_hash,
                )
                return existing
            saved = result.model_copy(
                update={"response_hash": result.response_hash or payload_hash}
            )
            self._replan_results[result.request_id] = saved
            self._replan_result_hashes[result.request_id] = payload_hash
            return saved

    def get_replan_result(self, request_id: str) -> LocalReplanningResponse | None:
        with self._lock:
            result = self._replan_results.get(request_id)
            return None if result is None else result.model_copy(deep=True)

    # ── Active TaskContract ─────────────────────────────────────────────

    def save_active_contract(
        self,
        contract: TaskContract,
        *,
        plan_id: str,
        robot_id: str,
        status: str = "ACTIVE",
        based_on_plan_version: int | None = None,
        correlation_id: str = "",
    ) -> ActiveTaskContractRecord:
        with self._lock:
            h = _contract_hash(contract)
            existing = self._version_record(contract.task_id, contract.plan_version)
            if existing is not None:
                self._ensure_same_hash(
                    "ActiveTaskContract",
                    f"{contract.task_id}:{contract.plan_version}",
                    existing.contract_hash,
                    h,
                )
                if status == ActiveContractStatus.ACTIVE.value:
                    self._active_contracts[contract.task_id] = existing
                    self._plan_versions[contract.task_id] = (
                        contract.plan_version,
                        contract.command_seq,
                    )
                return existing.model_copy(deep=True)
            now = _utc_now()
            record = ActiveTaskContractRecord(
                task_id=contract.task_id,
                plan_id=plan_id,
                robot_id=robot_id,
                plan_version=contract.plan_version,
                command_seq=contract.command_seq,
                scene_version=contract.scene_version,
                contract=contract.model_copy(deep=True),
                status=status,
                based_on_plan_version=based_on_plan_version,
                created_at=now,
                activated_at=now,
                correlation_id=correlation_id,
                contract_hash=h,
            )
            if status == ActiveContractStatus.ACTIVE.value:
                current = self._active_contracts.get(contract.task_id)
                if current is not None and current.plan_version != record.plan_version:
                    superseded = current.model_copy(
                        update={
                            "status": ActiveContractStatus.SUPERSEDED.value,
                            "superseded_at": now,
                        },
                        deep=True,
                    )
                    self._replace_version_record(superseded)
                self._active_contracts[contract.task_id] = record
                self._plan_versions[contract.task_id] = (
                    contract.plan_version,
                    contract.command_seq,
                )
            self._contract_versions.setdefault(contract.task_id, []).append(record)
            return record.model_copy(deep=True)

    def get_active_contract(self, task_id: str) -> ActiveTaskContractRecord | None:
        with self._lock:
            record = self._active_contracts.get(task_id)
            return None if record is None else record.model_copy(deep=True)

    def advance_active_contract_if_current(
        self,
        *,
        task_id: str,
        expected_plan_version: int,
        expected_command_seq: int,
        new_contract: TaskContract,
        plan_id: str,
        robot_id: str,
        based_on_plan_version: int,
        correlation_id: str = "",
        replan_record: ReplanApplyRecord | None = None,
        activation_guard: Callable[[ReplanApplyRecord, ExecutionCheckpoint, bool], EvidenceVerdict]
        | None = None,
    ) -> ActiveTaskContractRecord | None:
        new_contract = TaskContract.model_validate(new_contract.model_dump())
        with self._lock:
            active = self._active_contracts.get(task_id)
            if active is None:
                return None
            if (
                active.plan_version != expected_plan_version
                or active.command_seq != expected_command_seq
            ):
                return None
            if new_contract.plan_version <= expected_plan_version:
                return None
            if new_contract.command_seq <= expected_command_seq:
                return None
            if new_contract.task_id != task_id:
                return None
            staged = None
            if replan_record is not None:
                staged = ReplanApplyRecord.model_validate(replan_record.model_dump())
                previous = self._apply_records.get(staged.apply_id)
                ids = self._checkpoints_by_task.get(task_id, [])
                checkpoint = self._checkpoints[ids[-1]] if ids else None
                cancelled = self._replan_cancelled_locked(task_id)
                if (
                    previous is None
                    or previous.status != "EDGE_ACCEPTED"
                    or staged.status != "ACTIVATED"
                    or staged.previous_plan_version != expected_plan_version
                    or staged.previous_command_seq != expected_command_seq
                    or based_on_plan_version != staged.previous_plan_version
                    or checkpoint is None
                    or _checkpoint_hash(checkpoint) != staged.checkpoint_hash
                    or checkpoint.checkpoint_id != staged.checkpoint_id
                    or staged.payload_hash != _contract_hash(new_contract)
                    or staged.task_id != task_id
                    or staged.plan_id != plan_id
                    or staged.robot_id != robot_id
                    or cancelled
                    or activation_guard is None
                ):
                    return None
                staged.validate_transition(previous, activation=True)
                from cloud_edge_robot_arm.edge.evidence.models import EvidenceVerdict

                verdict = activation_guard(
                    previous.model_copy(deep=True), checkpoint.model_copy(deep=True), cancelled
                )
                if not isinstance(verdict, EvidenceVerdict) or verdict.status != "VALID":
                    return None
                if self._replan_cancelled_locked(task_id):
                    return None
            h = _contract_hash(new_contract)
            existing = self._version_record(task_id, new_contract.plan_version)
            if existing is not None:
                self._ensure_same_hash(
                    "ActiveTaskContract",
                    f"{task_id}:{new_contract.plan_version}",
                    existing.contract_hash,
                    h,
                )
            # All conflict checks precede the first mutation under the same lock.
            now = _utc_now()
            superseded = active.model_copy(
                update={"status": ActiveContractStatus.SUPERSEDED.value, "superseded_at": now},
                deep=True,
            )
            self._replace_version_record(superseded)
            if existing is not None:
                record = existing.model_copy(
                    update={"status": "ACTIVE", "superseded_at": None}, deep=True
                )
                self._replace_version_record(record)
            else:
                record = ActiveTaskContractRecord(
                    task_id=task_id,
                    plan_id=plan_id,
                    robot_id=robot_id,
                    plan_version=new_contract.plan_version,
                    command_seq=new_contract.command_seq,
                    scene_version=new_contract.scene_version,
                    contract=new_contract.model_copy(deep=True),
                    status=ActiveContractStatus.ACTIVE.value,
                    based_on_plan_version=based_on_plan_version,
                    created_at=now,
                    activated_at=now,
                    correlation_id=correlation_id,
                    contract_hash=h,
                )
                self._contract_versions.setdefault(task_id, []).append(record)
            self._active_contracts[task_id] = record
            self._plan_versions[task_id] = (new_contract.plan_version, new_contract.command_seq)
            if staged is not None:
                self._store_apply_locked(staged)
            return record.model_copy(deep=True)

    def list_contract_versions(self, task_id: str) -> list[ActiveTaskContractRecord]:
        with self._lock:
            return [r.model_copy(deep=True) for r in self._contract_versions.get(task_id, [])]

    def _version_record(self, task_id: str, plan_version: int) -> ActiveTaskContractRecord | None:
        for record in self._contract_versions.get(task_id, []):
            if record.plan_version == plan_version:
                return record
        return None

    def _replace_version_record(self, replacement: ActiveTaskContractRecord) -> None:
        versions = self._contract_versions.get(replacement.task_id, [])
        for idx, record in enumerate(versions):
            if record.plan_version == replacement.plan_version:
                versions[idx] = replacement
                return
        versions.append(replacement)
        self._contract_versions[replacement.task_id] = versions

    # ── Checkpoint ──────────────────────────────────────────────────────

    def save_execution_checkpoint(self, checkpoint: ExecutionCheckpoint) -> ExecutionCheckpoint:
        with self._lock:
            h = checkpoint.checkpoint_hash or _checkpoint_hash(checkpoint)
            saved = checkpoint.model_copy(
                update={"checkpoint_hash": h, "updated_at": checkpoint.updated_at}, deep=True
            )
            existing = self._checkpoints.get(saved.checkpoint_id)
            if existing is not None:
                self._ensure_same_hash(
                    "ExecutionCheckpoint",
                    saved.checkpoint_id,
                    self._checkpoint_hashes[saved.checkpoint_id],
                    h,
                )
                return existing.model_copy(deep=True)
            self._checkpoints[saved.checkpoint_id] = saved
            self._checkpoint_hashes[saved.checkpoint_id] = h
            self._checkpoints_by_task.setdefault(saved.task_id, []).append(saved.checkpoint_id)
            return saved.model_copy(deep=True)

    def get_latest_execution_checkpoint(self, task_id: str) -> ExecutionCheckpoint | None:
        with self._lock:
            ids = self._checkpoints_by_task.get(task_id, [])
            if not ids:
                return None
            checkpoint = self._checkpoints[ids[-1]]
            return checkpoint.model_copy(deep=True)

    def get_checkpoint(self, checkpoint_id: str) -> ExecutionCheckpoint | None:
        with self._lock:
            checkpoint = self._checkpoints.get(checkpoint_id)
            return None if checkpoint is None else checkpoint.model_copy(deep=True)

    def compare_and_set_checkpoint(
        self,
        *,
        checkpoint_id: str,
        expected_checkpoint_hash: str,
        new_checkpoint: ExecutionCheckpoint,
    ) -> bool:
        with self._lock:
            existing = self._checkpoints.get(checkpoint_id)
            if existing is None:
                return False
            if existing.checkpoint_hash != expected_checkpoint_hash:
                return False
            h = new_checkpoint.checkpoint_hash or _checkpoint_hash(new_checkpoint)
            saved = new_checkpoint.model_copy(update={"checkpoint_hash": h}, deep=True)
            self._checkpoints.pop(checkpoint_id, None)
            self._checkpoint_hashes.pop(checkpoint_id, None)
            self._checkpoints[saved.checkpoint_id] = saved
            self._checkpoint_hashes[saved.checkpoint_id] = h
            ids = self._checkpoints_by_task.setdefault(saved.task_id, [])
            if checkpoint_id in ids:
                ids[ids.index(checkpoint_id)] = saved.checkpoint_id
            elif saved.checkpoint_id not in ids:
                ids.append(saved.checkpoint_id)
            return True

    # ── Replan apply and ACK ────────────────────────────────────────────

    def _replan_cancelled_locked(self, task_id: str) -> bool:
        return self._states.get(task_id) in {
            "CANCELLED",
            "ABORTED",
            "STOPPED",
            "SAFETY_STOPPED",
            "COMPLETED",
        } or any(
            self._events[key].severity == "CRITICAL"
            or self._events[key].event_type.value == "MANUAL_INTERRUPT"
            for key in self._events_by_task.get(task_id, [])
        )

    def _store_apply_locked(self, record: ReplanApplyRecord) -> ReplanApplyRecord:
        saved = record.model_copy(update={"apply_hash": record.content_hash()}, deep=True)
        self._apply_records[saved.apply_id] = saved
        self._apply_by_request[saved.request_id] = saved.apply_id
        self._apply_hashes[saved.apply_id] = saved.apply_hash
        return saved.model_copy(deep=True)

    def save_replan_apply_record(self, record: ReplanApplyRecord) -> ReplanApplyRecord:
        record = ReplanApplyRecord.model_validate(record.model_dump())
        with self._lock:
            existing_id = self._apply_by_request.get(record.request_id, record.apply_id)
            existing = self._apply_records.get(existing_id)
            if existing is not None:
                self._ensure_same_hash(
                    "ReplanApplyRecord",
                    record.apply_id,
                    existing.content_hash(),
                    record.content_hash(),
                )
                return existing.model_copy(deep=True)
            if record.status in {"EDGE_ACCEPTED", "ACTIVATED", "EXECUTION_STARTED"}:
                raise ValueError("public insert cannot assert edge activation")
            if record.stage_attempt_id:
                raise ValueError("public insert cannot assert edge activation")
            return self._store_apply_locked(record)

    def update_replan_apply_record_if_current(
        self,
        record: ReplanApplyRecord,
        *,
        expected_status: str,
    ) -> ReplanApplyRecord | None:
        record = ReplanApplyRecord.model_validate(record.model_dump())
        with self._lock:
            previous = self._apply_records.get(record.apply_id)
            if previous is None:
                return None
            if record.status == "EXECUTION_STARTED":
                assert record.start_receipt is not None
                for other in self._apply_records.values():
                    if (
                        other.apply_id != record.apply_id
                        and other.start_receipt is not None
                        and other.start_receipt.event_id == record.start_receipt.event_id
                    ):
                        raise ValueError("execution start event already belongs to another repair")
                active = self._active_contracts.get(record.task_id)
                if (
                    active is None
                    or active.plan_version != record.new_plan_version
                    or active.command_seq != record.new_command_seq
                    or active.contract_hash != record.payload_hash
                ):
                    return None
            if previous.content_hash() == record.content_hash():
                return previous.model_copy(deep=True)
            if previous.status != expected_status:
                return None
            record.validate_transition(previous)
            return self._store_apply_locked(record)

    def get_replan_apply_record(self, apply_id: str) -> ReplanApplyRecord | None:
        with self._lock:
            record = self._apply_records.get(apply_id)
            return None if record is None else record.model_copy(deep=True)

    def get_replan_apply_record_for_request(self, request_id: str) -> ReplanApplyRecord | None:
        with self._lock:
            apply_id = self._apply_by_request.get(request_id)
            if apply_id is None:
                return None
            return self._apply_records[apply_id].model_copy(deep=True)

    def save_command_ack(self, ack: CommandAck) -> CommandAck:
        with self._lock:
            key = ack.request_id or f"{ack.task_id}:{ack.plan_version}:{ack.command_seq}"
            h = _canonical_hash(ack)
            existing = self._acks_by_key.get(key)
            if existing is not None:
                self._ensure_same_hash("CommandAck", key, self._ack_hashes[key], h)
                return existing.model_copy(deep=True)
            saved = ack.model_copy(deep=True)
            self._acks_by_key[key] = saved
            self._ack_hashes[key] = h
            return saved.model_copy(deep=True)

    def get_command_ack(self, request_id: str) -> CommandAck | None:
        with self._lock:
            ack = self._acks_by_key.get(request_id)
            return None if ack is None else ack.model_copy(deep=True)

    # ── Outbox ──────────────────────────────────────────────────────────

    def enqueue_outbox(self, message: PendingMessage) -> PendingMessage:
        with self._lock:
            payload_hash = _canonical_hash(message)
            existing = self._outbox.get(message.message_id)
            if existing is not None:
                self._ensure_same_hash(
                    "PendingMessage",
                    message.message_id,
                    self._outbox_hashes[message.message_id],
                    payload_hash,
                )
                return existing.model_copy(deep=True)
            if message.idempotency_key:
                existing_id = self._outbox_idempotency.get(message.idempotency_key)
                if existing_id is not None:
                    self._ensure_same_hash(
                        "PendingMessage",
                        message.idempotency_key,
                        self._outbox_hashes[existing_id],
                        payload_hash,
                    )
                    return self._outbox[existing_id].model_copy(deep=True)
                self._outbox_idempotency[message.idempotency_key] = message.message_id
            self._outbox[message.message_id] = message.model_copy(deep=True)
            self._outbox_hashes[message.message_id] = payload_hash
            return self._outbox[message.message_id].model_copy(deep=True)

    def claim_outbox_message(self) -> PendingMessage | None:
        with self._lock:
            for msg in self._outbox.values():
                now = _utc_now()
                if msg.status not in {MessageStatus.PENDING, MessageStatus.RETRY_WAIT}:
                    continue
                if msg.next_retry_at is not None and msg.next_retry_at > now:
                    continue
                updated = msg.model_copy(update={"status": MessageStatus.SENDING}, deep=True)
                self._outbox[msg.message_id] = updated
                self._outbox_hashes[msg.message_id] = _canonical_hash(updated)
                return updated.model_copy(deep=True)
            return None

    def mark_outbox_sent(self, message_id: str) -> bool:
        with self._lock:
            msg = self._outbox.get(message_id)
            if msg is None:
                return False
            if msg.status == MessageStatus.SENT:
                return True
            if msg.status != MessageStatus.SENDING:
                return False
            updated = msg.model_copy(update={"status": MessageStatus.SENT}, deep=True)
            self._outbox[message_id] = updated
            self._outbox_hashes[message_id] = _canonical_hash(updated)
            return True

    def mark_outbox_failed(self, message_id: str, error: str) -> bool:
        with self._lock:
            msg = self._outbox.get(message_id)
            if msg is None:
                return False
            new_count = msg.retry_count + 1
            if new_count >= msg.max_retries:
                new_status = MessageStatus.DEAD_LETTER
                next_attempt = None
            else:
                new_status = MessageStatus.RETRY_WAIT
                backoff_ms = msg.backoff_base_ms * (2 ** (new_count - 1))
                next_attempt = _utc_now() + timedelta(milliseconds=backoff_ms)
            updated = msg.model_copy(
                update={
                    "status": new_status,
                    "retry_count": new_count,
                    "last_error": error,
                    "next_retry_at": next_attempt,
                },
                deep=True,
            )
            self._outbox[message_id] = updated
            self._outbox_hashes[message_id] = _canonical_hash(updated)
            return True

    def list_pending_outbox(self, task_id: str | None = None) -> list[PendingMessage]:
        with self._lock:
            result: list[PendingMessage] = []
            for msg in self._outbox.values():
                if msg.status not in {MessageStatus.PENDING, MessageStatus.RETRY_WAIT}:
                    continue
                if task_id is not None and msg.task_id != task_id:
                    continue
                result.append(msg.model_copy(deep=True))
            return result

    # ── Version Management ──────────────────────────────────────────────

    def advance_plan_version_if_current(
        self,
        task_id: str,
        expected_plan_version: int,
        expected_command_seq: int,
        new_plan_version: int,
        new_command_seq: int,
    ) -> bool:
        with self._lock:
            if new_plan_version <= expected_plan_version or new_command_seq <= expected_command_seq:
                return False
            current = self._plan_versions.get(task_id)
            if current is None:
                current = (expected_plan_version, expected_command_seq)
                self._plan_versions[task_id] = current
            if current[0] != expected_plan_version or current[1] != expected_command_seq:
                return False
            self._plan_versions[task_id] = (new_plan_version, new_command_seq)
            return True

    # ── Audit ───────────────────────────────────────────────────────────

    def record_audit_event(self, task_id: str, event_type: str, details: dict[str, object]) -> None:
        with self._lock:
            entry: dict[str, object] = {
                "event_type": event_type,
                "details": deepcopy(details),
                "created_at": _utc_now().isoformat(),
            }
            self._audit.setdefault(task_id, []).append(entry)

    # ── Lifecycle ───────────────────────────────────────────────────────

    def close(self) -> None:
        with self._lock:
            self._events.clear()
            self._event_hashes.clear()
            self._events_by_task.clear()
            self._budgets.clear()
            self._states.clear()
            self._transitions.clear()
            self._failure_summaries.clear()
            self._failure_hashes.clear()
            self._completion_summaries.clear()
            self._completion_hashes.clear()
            self._replan_requests.clear()
            self._replan_request_hashes.clear()
            self._replan_idempotency.clear()
            self._replan_results.clear()
            self._replan_result_hashes.clear()
            self._outbox.clear()
            self._outbox_hashes.clear()
            self._outbox_idempotency.clear()
            self._plan_versions.clear()
            self._active_contracts.clear()
            self._contract_versions.clear()
            self._checkpoints.clear()
            self._checkpoint_hashes.clear()
            self._checkpoints_by_task.clear()
            self._apply_records.clear()
            self._apply_by_request.clear()
            self._apply_hashes.clear()
            self._acks_by_key.clear()
            self._ack_hashes.clear()
            self._audit.clear()
