"""SQLite 仓储实现，负责事务、幂等写入和可恢复状态。

SQLite-backed EventAutonomyRepository with conflict-aware idempotency.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
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


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_hash(value: Any) -> str:
    if isinstance(value, BaseModel):
        payload = value.model_dump(mode="json")
    else:
        payload = value
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _checkpoint_hash(checkpoint: ExecutionCheckpoint) -> str:
    payload = checkpoint.model_dump(mode="json")
    payload["checkpoint_hash"] = ""
    return _canonical_hash(payload)


def _apply_hash(record: ReplanApplyRecord) -> str:
    payload = record.model_dump(mode="json")
    payload["apply_hash"] = ""
    return _canonical_hash(payload)


def _same_or_conflict(entity: str, key: str, existing_hash: str, new_hash: str) -> None:
    if existing_hash != new_hash:
        raise IdempotencyConflictError(f"{entity} idempotency conflict for key {key!r}")


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


class SQLiteEventAutonomyRepository:
    """SQLite-backed persistent repository with CAS and conflict semantics."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._write_lock = Lock()
        self._visual_supervision_verified_bytes: dict[str, tuple[Any, ...]] = {}
        self._create_schema()
        self._migrate_schema()

    def _visual_supervision_locked(self, task_id: str) -> VisualSupervisionRecord | None:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_supervision import (
            VisualSupervisionRecord,
        )

        row = self._conn.execute(
            "SELECT * FROM visual_supervision WHERE task_id=?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        identity = tuple(row[name] for name in (
            "task_id", "revision", "definition_hash", "record_hash", "payload_json"
        ))
        if self._visual_supervision_verified_bytes.get(task_id) == identity:
            return VisualSupervisionRecord._from_verified_json(row["payload_json"])
        record = VisualSupervisionRecord.from_json(row["payload_json"])
        if (record.definition.task_id != task_id or record.digest() != row["record_hash"]
            or record.definition.digest() != row["definition_hash"]
            or record.revision != row["revision"]):
            raise ValueError("stored supervision row/hash differs")
        self._visual_supervision_verified_bytes[task_id] = identity
        return record

    def get_visual_supervision_source_publication(
        self, task_id: str
    ) -> VisualOwnerPublicationRecord | None:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_supervision import (
            current_supervision_publication,
        )

        with self._write_lock, self._conn:
            self._conn.execute("BEGIN")
            prior = self._visual_record_locked(task_id)
            if prior is None or self._replan_cancelled_locked(task_id):
                return None
            original = self._visual_original_locked(task_id, prior.checkpoint.plan_version)
            ancestor = (
                self._visual_record_locked(task_id, prior.owner_revision - 1)
                if prior.owner_revision > 1 else None
            )
            try:
                if (original is None or not self._visual_versions_match(original)
                    or not current_supervision_publication(
                        prior, original, *self._visual_verification_group_locked(task_id),
                        ancestor, now=datetime.now(UTC)
                    )):
                    return None
            except (ValueError, TypeError):
                return None
            return prior.detached()

    def _visual_store_supervision_locked(self, record: VisualSupervisionRecord) -> None:
        self._conn.execute(
            "INSERT INTO visual_supervision VALUES (?,?,?,?,?) "
            "ON CONFLICT(task_id) DO UPDATE SET revision=excluded.revision,"
            "record_hash=excluded.record_hash,payload_json=excluded.payload_json",
            (record.definition.task_id, record.revision, record.definition.digest(),
             record.digest(), record.to_json()),
        )

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
        with self._write_lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
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
                    definition, original, prior, ancestor,
                    *self._visual_verification_group_locked(task),
                    cancelled=self._replan_cancelled_locked(task), now=datetime.now(UTC),
                    bootstrap=self._visual_bootstrap_for_original_locked(original),
                )):
                raise IdempotencyConflictError("supervision original source is unavailable")
            record = VisualSupervisionRecord.start(definition)
            self._visual_store_supervision_locked(record)
            return record

    def get_visual_supervision(self, task_id: str) -> VisualSupervisionRecord | None:
        with self._write_lock, self._conn:
            self._conn.execute("BEGIN")
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
        with self._write_lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
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
            try:
                result = derive_supervision(
                    stored, request, original, prior, ancestor,
                    *self._visual_verification_group_locked(task),
                    cancelled=self._replan_cancelled_locked(task), now=datetime.now(UTC),
                )
            except (ValueError, TypeError):
                return None
            if result is not None and result.write_disposition == "NEW_COMMIT":
                self._visual_store_supervision_locked(result.record)
            return result

    def _visual_bootstrap_locked(self, bootstrap_id: str) -> VisualBootstrapRecord | None:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_bootstrap import (
            VisualBootstrapRecord,
        )

        row = self._conn.execute(
            "SELECT * FROM visual_bootstraps WHERE bootstrap_id=?", (bootstrap_id,)
        ).fetchone()
        if row is None:
            return None
        record = VisualBootstrapRecord.from_json(row["payload_json"])
        definition = record.definition
        expected = (
            definition.bootstrap_id,
            definition.lease.job_id,
            definition.lease.run_id,
            definition.episode_id,
            record.revision,
            definition.digest(),
            record.digest(),
        )
        actual = tuple(
            row[key]
            for key in (
                "bootstrap_id",
                "job_id",
                "run_id",
                "episode_id",
                "revision",
                "definition_hash",
                "record_hash",
            )
        )
        if actual != expected:
            raise ValueError("bootstrap indexed source differs")
        return record

    def _visual_store_bootstrap_locked(self, record: VisualBootstrapRecord) -> None:
        definition = record.definition
        self._conn.execute(
            "INSERT INTO visual_bootstraps VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(bootstrap_id) DO UPDATE SET revision=excluded.revision, "
            "record_hash=excluded.record_hash,payload_json=excluded.payload_json",
            (
                definition.bootstrap_id,
                definition.lease.job_id,
                definition.lease.run_id,
                definition.episode_id,
                record.revision,
                definition.digest(),
                record.digest(),
                record.to_json(),
            ),
        )

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
        with self._write_lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            existing = self._visual_bootstrap_locked(definition.bootstrap_id)
            if existing is not None:
                if existing.definition.digest() != definition.digest():
                    raise IdempotencyConflictError("bootstrap definition differs")
                return existing
            row = self._conn.execute(
                "SELECT bootstrap_id FROM visual_bootstraps WHERE episode_id=? "
                "OR (job_id=? AND run_id=?)",
                (definition.episode_id, definition.lease.job_id, definition.lease.run_id),
            ).fetchone()
            if row is not None:
                self._visual_bootstrap_locked(row["bootstrap_id"])
                raise IdempotencyConflictError(
                    "bootstrap episode/job/run already belongs to a source"
                )
            for row in self._conn.execute(
                "SELECT task_id,plan_version FROM visual_original_plans"
            ).fetchall():
                original = self._visual_original_locked(row["task_id"], row["plan_version"])
                if original is not None and (
                    original.identity.episode_id == definition.episode_id
                    or (original.identity.job_id, original.identity.run_id)
                    == (definition.lease.job_id, definition.lease.run_id)
                ):
                    raise IdempotencyConflictError("episode/job/run already has an original source")
            task = definition.episode_id
            if any(value is not None for value in self._visual_group_locked(task)) or any(
                self._conn.execute(f"SELECT 1 FROM {table} WHERE task_id=?", (task,)).fetchone()
                for table in ("task_contract_versions", "plan_versions", "execution_checkpoints")
            ):
                raise IdempotencyConflictError("ordinary task rows already exist")
            self._visual_store_bootstrap_locked(initial)
            return VisualBootstrapRecord.from_json(initial.to_json())

    def get_visual_bootstrap(self, bootstrap_id: str) -> VisualBootstrapRecord | None:
        with self._write_lock, self._conn:
            self._conn.execute("BEGIN")
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
        with self._write_lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            current = self._visual_bootstrap_locked(body["bootstrap_id"])
            if current is None:
                return None
            for event in current.to_payload()["history"]:
                source = event.get("request", event.get("promotion"))
                if source["event_key"] == body["event_key"]:
                    if source != body:
                        raise IdempotencyConflictError("bootstrap event key changed source")
            try:
                result = derive_bootstrap(current, request, now=datetime.now(UTC))
            except (ValueError, TypeError):
                return None
            if result.write_disposition == "NEW_COMMIT":
                self._visual_store_bootstrap_locked(result.record)
            return result

    def _create_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS visual_supervision (
                task_id TEXT PRIMARY KEY,
                revision INTEGER NOT NULL,
                definition_hash TEXT NOT NULL,
                record_hash TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS visual_bootstraps (
                bootstrap_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                episode_id TEXT NOT NULL UNIQUE,
                revision INTEGER NOT NULL,
                definition_hash TEXT NOT NULL,
                record_hash TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                UNIQUE (job_id, run_id)
            );
            CREATE TABLE IF NOT EXISTS visual_verification_routes (
                task_id TEXT NOT NULL,
                event_key TEXT NOT NULL,
                source_key TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                record_hash TEXT NOT NULL,
                PRIMARY KEY (task_id, event_key),
                UNIQUE (task_id, source_key)
            );
            CREATE TABLE IF NOT EXISTS visual_original_plans (
                task_id TEXT NOT NULL,
                plan_version INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                original_hash TEXT NOT NULL,
                PRIMARY KEY (task_id, plan_version)
            );
            CREATE TABLE IF NOT EXISTS visual_owner_publications (
                task_id TEXT NOT NULL,
                owner_revision INTEGER NOT NULL,
                owner_epoch TEXT NOT NULL,
                state_generation INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                publication_hash TEXT NOT NULL,
                PRIMARY KEY (task_id, owner_revision)
            );
            CREATE TABLE IF NOT EXISTS recovery_records (
                recovery_id TEXT PRIMARY KEY,
                event_id TEXT UNIQUE NOT NULL,
                task_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                state TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                initial_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS verification_budgets (
                task_id TEXT PRIMARY KEY,
                revision INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                content_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS edge_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                task_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                step_id TEXT,
                severity TEXT NOT NULL DEFAULT 'ERROR',
                reason_code TEXT DEFAULT '',
                reason_detail TEXT DEFAULT '',
                robot_id TEXT DEFAULT '',
                plan_id TEXT DEFAULT '',
                plan_version INTEGER NOT NULL DEFAULT 0,
                command_seq INTEGER NOT NULL DEFAULT 0,
                details_json TEXT DEFAULT '{}',
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL DEFAULT '',
                handled INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_edge_events_task ON edge_events(task_id);

            CREATE TABLE IF NOT EXISTS recovery_budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                budget_id TEXT NOT NULL UNIQUE,
                task_id TEXT NOT NULL UNIQUE,
                per_step_retry_limit INTEGER NOT NULL DEFAULT 3,
                per_skill_retry_limit INTEGER NOT NULL DEFAULT 5,
                task_total_retry_limit INTEGER NOT NULL DEFAULT 10,
                retry_count_used INTEGER NOT NULL DEFAULT 0,
                task_retry_count INTEGER NOT NULL DEFAULT 0,
                step_retry_counts_json TEXT DEFAULT '{}',
                skill_retry_counts_json TEXT DEFAULT '{}',
                event_retry_counts_json TEXT DEFAULT '{}',
                retry_cooldown_ms INTEGER NOT NULL DEFAULT 500,
                retry_deadline TEXT,
                retry_backoff_policy TEXT NOT NULL DEFAULT 'exponential',
                effective_retry_limit INTEGER NOT NULL DEFAULT 3,
                remaining_retries INTEGER NOT NULL DEFAULT 3,
                scene_version INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_recovery_budgets_task ON recovery_budgets(task_id);

            CREATE TABLE IF NOT EXISTS recovery_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                skill TEXT NOT NULL,
                event_id TEXT DEFAULT '',
                attempt_number INTEGER NOT NULL,
                success INTEGER NOT NULL DEFAULT 0,
                error_code TEXT DEFAULT '',
                duration_ms INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_recovery_attempts_task
                ON recovery_attempts(task_id, step_id);

            CREATE TABLE IF NOT EXISTS event_mode_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL UNIQUE,
                current_state TEXT NOT NULL,
                reason TEXT DEFAULT '',
                event_id TEXT DEFAULT '',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS event_mode_transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                from_state TEXT NOT NULL,
                to_state TEXT NOT NULL,
                reason TEXT DEFAULT '',
                event_id TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_event_mode_transitions_task
                ON event_mode_transitions(task_id);

            CREATE TABLE IF NOT EXISTS failure_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                summary_id TEXT NOT NULL UNIQUE,
                task_id TEXT NOT NULL,
                failure_event_id TEXT NOT NULL,
                failed_step_id TEXT NOT NULL,
                completed_step_ids_json TEXT DEFAULT '[]',
                failure_type TEXT DEFAULT '',
                severity TEXT DEFAULT 'ERROR',
                reason TEXT NOT NULL,
                recovery_hint TEXT DEFAULT '',
                local_retry_count INTEGER NOT NULL DEFAULT 0,
                retry_limit INTEGER NOT NULL DEFAULT 0,
                requested_replan_scope TEXT DEFAULT '',
                plan_version INTEGER NOT NULL DEFAULT 0,
                command_seq INTEGER NOT NULL DEFAULT 0,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_failure_summaries_task ON failure_summaries(task_id);

            CREATE TABLE IF NOT EXISTS completion_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                summary_id TEXT NOT NULL UNIQUE,
                task_id TEXT NOT NULL,
                final_plan_version INTEGER NOT NULL DEFAULT 0,
                completed_step_ids_json TEXT DEFAULT '[]',
                completion_criteria_results_json TEXT DEFAULT '{}',
                local_retry_count INTEGER NOT NULL DEFAULT 0,
                cloud_replan_count INTEGER NOT NULL DEFAULT 0,
                result TEXT NOT NULL DEFAULT 'SUCCESS',
                final_safety_decision TEXT DEFAULT 'ALLOW',
                plan_version INTEGER NOT NULL DEFAULT 0,
                command_seq INTEGER NOT NULL DEFAULT 0,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_completion_summaries_task
                ON completion_summaries(task_id);

            CREATE TABLE IF NOT EXISTS replan_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                idempotency_key TEXT,
                task_id TEXT NOT NULL,
                trigger_event_id TEXT NOT NULL,
                failure_summary_id TEXT DEFAULT '',
                current_plan_version INTEGER NOT NULL DEFAULT 0,
                current_command_seq INTEGER NOT NULL DEFAULT 1,
                requested_replan_scope TEXT DEFAULT '',
                completed_step_ids_json TEXT DEFAULT '[]',
                failed_step_id TEXT DEFAULT '',
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_replan_requests_idempotency
                ON replan_requests(idempotency_key)
                WHERE idempotency_key IS NOT NULL AND idempotency_key != '';
            CREATE INDEX IF NOT EXISTS idx_replan_requests_task ON replan_requests(task_id);

            CREATE TABLE IF NOT EXISTS replan_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                task_id TEXT NOT NULL,
                outcome TEXT NOT NULL DEFAULT 'REPLANNED',
                new_plan_version INTEGER NOT NULL DEFAULT 0,
                new_command_seq INTEGER NOT NULL DEFAULT 1,
                new_steps_json TEXT DEFAULT '[]',
                validation_errors_json TEXT DEFAULT '[]',
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_replan_results_task ON replan_results(task_id);

            CREATE TABLE IF NOT EXISTS event_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL UNIQUE,
                idempotency_key TEXT,
                task_id TEXT NOT NULL,
                message_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'PENDING',
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 5,
                backoff_base_ms INTEGER NOT NULL DEFAULT 1000,
                next_attempt_at TEXT,
                claimed_at TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_event_outbox_task ON event_outbox(task_id);
            CREATE INDEX IF NOT EXISTS idx_event_outbox_status ON event_outbox(status);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_event_outbox_idempotency
                ON event_outbox(idempotency_key)
                WHERE idempotency_key IS NOT NULL AND idempotency_key != '';

            CREATE TABLE IF NOT EXISTS event_audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                details_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_event_audit_events_task ON event_audit_events(task_id);

            CREATE TABLE IF NOT EXISTS plan_versions (
                task_id TEXT PRIMARY KEY,
                plan_version INTEGER NOT NULL,
                command_seq INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS task_contract_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                robot_id TEXT NOT NULL,
                plan_version INTEGER NOT NULL,
                command_seq INTEGER NOT NULL,
                scene_version INTEGER NOT NULL,
                status TEXT NOT NULL,
                based_on_plan_version INTEGER,
                contract_json TEXT NOT NULL,
                record_json TEXT NOT NULL,
                contract_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                activated_at TEXT NOT NULL,
                superseded_at TEXT,
                correlation_id TEXT DEFAULT '',
                UNIQUE(task_id, plan_version)
            );
            CREATE INDEX IF NOT EXISTS idx_contract_versions_task
                ON task_contract_versions(task_id, plan_version);

            CREATE TABLE IF NOT EXISTS active_task_contracts (
                task_id TEXT PRIMARY KEY,
                plan_id TEXT NOT NULL,
                robot_id TEXT NOT NULL,
                plan_version INTEGER NOT NULL,
                command_seq INTEGER NOT NULL,
                scene_version INTEGER NOT NULL,
                record_json TEXT NOT NULL,
                contract_hash TEXT NOT NULL,
                activated_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS execution_checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                checkpoint_id TEXT NOT NULL UNIQUE,
                task_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                robot_id TEXT NOT NULL,
                plan_version INTEGER NOT NULL,
                command_seq INTEGER NOT NULL,
                execution_state TEXT NOT NULL,
                completed_step_ids_json TEXT DEFAULT '[]',
                payload_json TEXT NOT NULL,
                checkpoint_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_checkpoints_task ON execution_checkpoints(task_id, id);

            CREATE TABLE IF NOT EXISTS replan_apply_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                apply_id TEXT NOT NULL UNIQUE,
                request_id TEXT NOT NULL UNIQUE,
                task_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                robot_id TEXT NOT NULL,
                previous_plan_version INTEGER NOT NULL,
                previous_command_seq INTEGER NOT NULL,
                new_plan_version INTEGER NOT NULL,
                new_command_seq INTEGER NOT NULL,
                checkpoint_id TEXT DEFAULT '',
                status TEXT NOT NULL,
                reason TEXT DEFAULT '',
                payload_json TEXT NOT NULL,
                apply_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_replan_apply_task ON replan_apply_records(task_id);

            CREATE TABLE IF NOT EXISTS command_acks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ack_key TEXT NOT NULL UNIQUE,
                request_id TEXT DEFAULT '',
                task_id TEXT NOT NULL,
                plan_version INTEGER NOT NULL,
                command_seq INTEGER NOT NULL,
                checkpoint_id TEXT DEFAULT '',
                status TEXT NOT NULL,
                accepted INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_command_acks_task
                ON command_acks(task_id, plan_version, command_seq);
            """
        )
        self._conn.commit()

    def _migrate_schema(self) -> None:
        additions = {
            "edge_events": [("payload_hash", "TEXT NOT NULL DEFAULT ''")],
            "failure_summaries": [("payload_hash", "TEXT NOT NULL DEFAULT ''")],
            "completion_summaries": [("payload_hash", "TEXT NOT NULL DEFAULT ''")],
            "replan_requests": [("payload_hash", "TEXT NOT NULL DEFAULT ''")],
            "replan_results": [("payload_hash", "TEXT NOT NULL DEFAULT ''")],
            "event_outbox": [("payload_hash", "TEXT NOT NULL DEFAULT ''")],
            "recovery_budgets": [
                ("task_retry_count", "INTEGER NOT NULL DEFAULT 0"),
                ("step_retry_counts_json", "TEXT DEFAULT '{}'"),
                ("skill_retry_counts_json", "TEXT DEFAULT '{}'"),
                ("event_retry_counts_json", "TEXT DEFAULT '{}'"),
            ],
            "recovery_attempts": [("event_id", "TEXT DEFAULT ''")],
        }
        for table, cols in additions.items():
            existing = {r["name"] for r in self._conn.execute(f"PRAGMA table_info({table})")}
            for name, ddl in cols:
                if name not in existing:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        self._conn.commit()

    # ── generic helpers ──────────────────────────────────────────────────

    def _existing_by_key(self, table: str, key_col: str, key: str) -> sqlite3.Row | None:
        row: sqlite3.Row | None = self._conn.execute(
            f"SELECT payload_json, payload_hash FROM {table} WHERE {key_col} = ?",
            (key,),
        ).fetchone()
        return row

    def _json(self, value: Any) -> str:
        return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))

    # ── Events ──────────────────────────────────────────────────────────

    def save_event(self, event: EdgeEvent) -> EdgeEvent:
        payload = event.model_dump_json()
        payload_hash = _canonical_hash(event)
        now = _iso_now()
        with self._write_lock:
            row = self._existing_by_key("edge_events", "event_id", event.event_id)
            if row is not None:
                _same_or_conflict(
                    "EdgeEvent",
                    event.event_id,
                    row["payload_hash"] or _canonical_hash(json.loads(row["payload_json"])),
                    payload_hash,
                )
                return EdgeEvent.model_validate_json(row["payload_json"])
            saved = event.model_copy(update={"event_hash": event.event_hash or payload_hash})
            payload = saved.model_dump_json()
            self._conn.execute(
                """INSERT INTO edge_events (
                    event_id, task_id, event_type, step_id, severity, reason_code,
                    reason_detail, robot_id, plan_id, plan_version, command_seq,
                    details_json, payload_json, payload_hash, handled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                (
                    saved.event_id,
                    saved.task_id,
                    saved.event_type.value,
                    saved.step_id,
                    saved.severity,
                    saved.reason_code,
                    saved.reason_detail,
                    saved.robot_id,
                    saved.plan_id,
                    saved.plan_version,
                    saved.command_seq,
                    self._json(saved.details),
                    payload,
                    payload_hash,
                    now,
                    now,
                ),
            )
            self._conn.commit()
            return saved

    def get_event(self, event_id: str) -> EdgeEvent | None:
        row = self._conn.execute(
            "SELECT payload_json FROM edge_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        return None if row is None else EdgeEvent.model_validate_json(row["payload_json"])

    def list_events(self, task_id: str) -> list[EdgeEvent]:
        rows = self._conn.execute(
            "SELECT payload_json FROM edge_events WHERE task_id = ? ORDER BY id",
            (task_id,),
        ).fetchall()
        return [EdgeEvent.model_validate_json(r["payload_json"]) for r in rows]

    def mark_event_handled(self, event_id: str, handled_at: datetime | None = None) -> bool:
        now = (handled_at or datetime.now(UTC)).isoformat()
        with self._write_lock:
            cursor = self._conn.execute(
                "UPDATE edge_events SET handled = 1, updated_at = ? WHERE event_id = ?",
                (now, event_id),
            )
            self._conn.commit()
            return cursor.rowcount == 1

    # ── Retry Budget ────────────────────────────────────────────────────

    def save_retry_budget(self, budget: RecoveryBudget) -> RecoveryBudget:
        now = _iso_now()
        deadline = budget.retry_deadline.isoformat() if budget.retry_deadline else None
        with self._write_lock:
            self._conn.execute(
                """INSERT INTO recovery_budgets (
                    budget_id, task_id, per_step_retry_limit, per_skill_retry_limit,
                    task_total_retry_limit, retry_count_used, task_retry_count,
                    step_retry_counts_json, skill_retry_counts_json, event_retry_counts_json,
                    retry_cooldown_ms, retry_deadline, retry_backoff_policy,
                    effective_retry_limit, remaining_retries, scene_version,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    per_step_retry_limit = excluded.per_step_retry_limit,
                    per_skill_retry_limit = excluded.per_skill_retry_limit,
                    task_total_retry_limit = excluded.task_total_retry_limit,
                    retry_count_used = excluded.retry_count_used,
                    task_retry_count = excluded.task_retry_count,
                    step_retry_counts_json = excluded.step_retry_counts_json,
                    skill_retry_counts_json = excluded.skill_retry_counts_json,
                    event_retry_counts_json = excluded.event_retry_counts_json,
                    retry_deadline = excluded.retry_deadline,
                    effective_retry_limit = excluded.effective_retry_limit,
                    remaining_retries = excluded.remaining_retries,
                    scene_version = excluded.scene_version,
                    updated_at = excluded.updated_at""",
                (
                    budget.budget_id,
                    budget.task_id,
                    budget.per_step_retry_limit,
                    budget.per_skill_retry_limit,
                    budget.task_total_retry_limit,
                    budget.retry_count_used,
                    budget.task_retry_count,
                    self._json(budget.step_retry_counts),
                    self._json(budget.skill_retry_counts),
                    self._json(budget.event_retry_counts),
                    budget.retry_cooldown_ms,
                    deadline,
                    budget.retry_backoff_policy,
                    budget.effective_retry_limit,
                    budget.remaining_retries,
                    budget.scene_version,
                    now,
                    now,
                ),
            )
            self._conn.commit()
        return self.get_retry_budget(budget.task_id) or budget

    def get_retry_budget(self, task_id: str) -> RecoveryBudget | None:
        row = self._conn.execute(
            "SELECT * FROM recovery_budgets WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        return RecoveryBudget(
            budget_id=row["budget_id"],
            task_id=row["task_id"],
            per_step_retry_limit=row["per_step_retry_limit"],
            per_skill_retry_limit=row["per_skill_retry_limit"],
            task_total_retry_limit=row["task_total_retry_limit"],
            retry_count_used=row["retry_count_used"],
            task_retry_count=row["task_retry_count"],
            step_retry_counts=json.loads(row["step_retry_counts_json"] or "{}"),
            skill_retry_counts=json.loads(row["skill_retry_counts_json"] or "{}"),
            event_retry_counts=json.loads(row["event_retry_counts_json"] or "{}"),
            retry_cooldown_ms=row["retry_cooldown_ms"],
            retry_deadline=datetime.fromisoformat(row["retry_deadline"])
            if row["retry_deadline"]
            else None,
            retry_backoff_policy=row["retry_backoff_policy"],
            effective_retry_limit=row["effective_retry_limit"],
            remaining_retries=row["remaining_retries"],
            scene_version=row["scene_version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def initialize_retry_budget_if_absent(self, budget: RecoveryBudget) -> RecoveryBudget:
        """Create once under BEGIN IMMEDIATE; restarts retain every stored field."""
        budget = RecoveryBudget.model_validate(budget.model_dump())
        with self._write_lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            existing = self.get_retry_budget(budget.task_id)
            if existing is not None:
                return existing.model_copy(deep=True)
            self._conn.execute(
                """INSERT INTO recovery_budgets (
                    budget_id, task_id, per_step_retry_limit, per_skill_retry_limit,
                    task_total_retry_limit, retry_count_used, task_retry_count,
                    step_retry_counts_json, skill_retry_counts_json, event_retry_counts_json,
                    retry_cooldown_ms, retry_deadline, retry_backoff_policy,
                    effective_retry_limit, remaining_retries, scene_version,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    budget.budget_id,
                    budget.task_id,
                    budget.per_step_retry_limit,
                    budget.per_skill_retry_limit,
                    budget.task_total_retry_limit,
                    budget.retry_count_used,
                    budget.task_retry_count,
                    self._json(budget.step_retry_counts),
                    self._json(budget.skill_retry_counts),
                    self._json(budget.event_retry_counts),
                    budget.retry_cooldown_ms,
                    budget.retry_deadline.isoformat() if budget.retry_deadline else None,
                    budget.retry_backoff_policy,
                    budget.effective_retry_limit,
                    budget.remaining_retries,
                    budget.scene_version,
                    budget.created_at.isoformat(),
                    budget.updated_at.isoformat(),
                ),
            )
            saved = self.get_retry_budget(budget.task_id)
            assert saved is not None
            return saved.model_copy(deep=True)

    def consume_retry_if_available(
        self,
        task_id: str,
        step_id: str,
        skill: str,
        expected_count: int,
        event_id: str = "",
    ) -> tuple[bool, RecoveryBudget | None]:
        with self._write_lock:
            return self._consume_retry_locked(task_id, step_id, skill, expected_count, event_id)

    def _consume_retry_locked(
        self,
        task_id: str,
        step_id: str,
        skill: str,
        expected_count: int,
        event_id: str = "",
        *,
        commit: bool = True,
    ) -> tuple[bool, RecoveryBudget | None]:
        now = _iso_now()
        budget = self.get_retry_budget(task_id)
        if budget is None:
            return False, None
        if budget.retry_count_used != expected_count or budget.remaining_retries <= 0:
            return False, budget
        if event_id and budget.event_retry_counts.get(event_id, 0) > 0:
            return False, budget
        step_counts = dict(budget.step_retry_counts)
        skill_counts = dict(budget.skill_retry_counts)
        event_counts = dict(budget.event_retry_counts)
        step_count = step_counts.get(step_id, 0)
        skill_count = skill_counts.get(skill, 0)
        effective_remaining = min(
            max(0, budget.task_total_retry_limit - budget.task_retry_count),
            max(0, budget.per_step_retry_limit - step_count),
            max(0, budget.per_skill_retry_limit - skill_count),
            budget.remaining_retries,
        )
        if effective_remaining <= 0:
            return False, budget
        if step_id:
            step_counts[step_id] = step_count + 1
        if skill:
            skill_counts[skill] = skill_count + 1
        if event_id:
            event_counts[event_id] = 1
        cursor = self._conn.execute(
            """UPDATE recovery_budgets
               SET retry_count_used = retry_count_used + 1,
                   task_retry_count = task_retry_count + 1,
                   step_retry_counts_json = ?,
                   skill_retry_counts_json = ?,
                   event_retry_counts_json = ?,
                   remaining_retries = remaining_retries - 1,
                   updated_at = ?
               WHERE task_id = ? AND retry_count_used = ? AND remaining_retries > 0""",
            (
                self._json(step_counts),
                self._json(skill_counts),
                self._json(event_counts),
                now,
                task_id,
                expected_count,
            ),
        )
        if cursor.rowcount != 1:
            if commit:
                self._conn.commit()
            return False, self.get_retry_budget(task_id)
        self._conn.execute(
            """INSERT INTO recovery_attempts
               (task_id, step_id, skill, event_id, attempt_number, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (task_id, step_id, skill, event_id, expected_count + 1, now),
        )
        if commit:
            self._conn.commit()
        return True, self.get_retry_budget(task_id)

    def initialize_verification_budget_if_absent(
        self,
        task_id: str,
        state: VerificationBudgetState,
    ) -> VerificationBudgetRecord:
        from cloud_edge_robot_arm.edge.recovery.lifecycle import VerificationBudgetRecord

        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("nonempty task identity required")
        with self._write_lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            existing = self.get_verification_budget(task_id)
            if existing is None:
                existing = VerificationBudgetRecord.create(task_id, state)
                retry = self.get_retry_budget(task_id)
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
                self._conn.execute(
                    "INSERT INTO verification_budgets VALUES (?, ?, ?, ?)",
                    (
                        task_id,
                        existing.revision,
                        self._json(existing.to_payload()),
                        existing.content_hash,
                    ),
                )
            return existing.detached()

    def get_verification_budget(self, task_id: str) -> VerificationBudgetRecord | None:
        from cloud_edge_robot_arm.edge.recovery.lifecycle import VerificationBudgetRecord

        row = self._conn.execute(
            "SELECT * FROM verification_budgets WHERE task_id=?",
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        result = VerificationBudgetRecord.from_payload(json.loads(row["payload_json"]))
        if (
            result.content_hash != row["content_hash"]
            or result.task_id != row["task_id"]
            or result.revision != row["revision"]
        ):
            raise ValueError("verification budget stored hash mismatch")
        return result

    def initialize_recovery_if_absent(self, record: RecoveryRecord) -> RecoveryRecord:
        from cloud_edge_robot_arm.edge.recovery.lifecycle import validate_detected

        record = record.detached()
        with self._write_lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            row = self._conn.execute(
                "SELECT initial_hash FROM recovery_records WHERE recovery_id=?",
                (record.recovery_id,),
            ).fetchone()
            if row is not None:
                _same_or_conflict(
                    "RecoveryRecord", record.recovery_id, row["initial_hash"], record.content_hash()
                )
                existing = self.get_recovery(record.recovery_id)
                assert existing is not None
                return existing
            if self._conn.execute(
                "SELECT 1 FROM recovery_records WHERE event_id=?", (record.event_id,)
            ).fetchone():
                raise IdempotencyConflictError("event already has a recovery record")
            if any(
                item.attempt_id == record.attempt_id
                for item in self.list_recoveries(record.task_id)
            ):
                raise ValueError("execution attempt already belongs to a failure event")
            validate_detected(
                record,
                self.get_event(record.event_id),
                self.get_verification_budget(record.task_id),
            )
            self._conn.execute(
                "INSERT INTO recovery_records VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.recovery_id,
                    record.event_id,
                    record.task_id,
                    record.revision,
                    record.state,
                    self._json(record.to_payload()),
                    record.content_hash(),
                    record.content_hash(),
                ),
            )
            return record.detached()

    def get_recovery(self, recovery_id: str) -> RecoveryRecord | None:
        from cloud_edge_robot_arm.edge.recovery.lifecycle import RecoveryRecord

        row = self._conn.execute(
            "SELECT * FROM recovery_records WHERE recovery_id=?", (recovery_id,)
        ).fetchone()
        if row is None:
            return None
        record = RecoveryRecord.from_payload(json.loads(row["payload_json"]))
        if (
            record.content_hash() != row["content_hash"]
            or record.revision != row["revision"]
            or record.state != row["state"]
            or record.task_id != row["task_id"]
            or record.event_id != row["event_id"]
            or record.recovery_id != row["recovery_id"]
        ):
            raise ValueError("stored recovery content mismatch")
        return record

    def list_unresolved_recoveries(self, task_id: str) -> list[RecoveryRecord]:
        return [
            record
            for record in self.list_recoveries(task_id)
            if not (
                record.state == "VERIFIED_RESOLVED" and record.evidence_scope == "ACTUAL_SOURCE"
            )
        ]

    def list_recoveries(self, task_id: str) -> list[RecoveryRecord]:
        rows = self._conn.execute(
            "SELECT recovery_id FROM recovery_records WHERE task_id=? ORDER BY rowid",
            (task_id,),
        ).fetchall()
        return [record for row in rows if (record := self.get_recovery(row["recovery_id"]))]

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

        with self._write_lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            current = self.get_recovery(record.recovery_id)
            pool = self.get_verification_budget(current.task_id) if current else None
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
            values = transition_values(
                current,
                pool,
                verified_transition,
                self.get_active_contract(current.task_id),
                self.get_latest_execution_checkpoint(current.task_id),
                self._replan_cancelled_locked(current.task_id),
                datetime.now(UTC),
            )
            if values is None:
                return current
            updated, next_pool = values
            self._update_recovery_locked(updated, next_pool)
            return updated

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

        with self._write_lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            current = self.get_recovery(recovery_id)
            pool = self.get_verification_budget(current.task_id) if current else None
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
            if not reservation_available(
                current,
                reservation,
                self.get_active_contract(current.task_id),
                self.get_latest_execution_checkpoint(current.task_id),
                self._replan_cancelled_locked(current.task_id),
                datetime.now(UTC),
            ):
                return None
            values = reserved_values(current, pool, datetime.now(UTC))
            if values is None:
                return None
            updated, next_pool = values
            self._update_recovery_locked(updated, next_pool)
            return updated

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

        with self._write_lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            record = self.get_recovery(recovery_id)
            pool = self.get_verification_budget(record.task_id) if record else None
            budget = self.get_retry_budget(record.task_id) if record else None
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
                now = datetime.now(UTC)
                reasons = authorization_reasons(
                    record,
                    pool,
                    budget,
                    self.get_event(record.event_id),
                    self.get_active_contract(record.task_id),
                    self.get_latest_execution_checkpoint(record.task_id),
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
                        commit=False,
                    )
                    if consumed and retry:
                        updated, next_pool = authorized_values(
                            record, pool, retry, authorization, now
                        )
                        self._update_recovery_locked(updated, next_pool)
                        return RecoveryAuthorizationResult(True, updated, retry, next_pool, ())
                    reasons = ("retry_authority_exhausted",)
            return RecoveryAuthorizationResult(False, record, budget, pool, reasons)

    def _update_recovery_locked(
        self,
        record: RecoveryRecord,
        pool: VerificationBudgetRecord,
    ) -> None:
        self._conn.execute(
            "UPDATE recovery_records SET revision=?,state=?,payload_json=?,content_hash=? "
            "WHERE recovery_id=?",
            (
                record.revision,
                record.state,
                self._json(record.to_payload()),
                record.content_hash(),
                record.recovery_id,
            ),
        )
        self._conn.execute(
            "UPDATE verification_budgets SET revision=?,payload_json=?,content_hash=? "
            "WHERE task_id=?",
            (pool.revision, self._json(pool.to_payload()), pool.content_hash, pool.task_id),
        )

    # ── State Machine ───────────────────────────────────────────────────

    def save_state(self, task_id: str, state: str, reason: str, event_id: str = "") -> None:
        now = _iso_now()
        with self._write_lock:
            self._conn.execute(
                """INSERT INTO event_mode_states
                   (task_id, current_state, reason, event_id, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(task_id) DO UPDATE SET
                       current_state = excluded.current_state,
                       reason = excluded.reason,
                       event_id = excluded.event_id,
                       updated_at = excluded.updated_at""",
                (task_id, state, reason, event_id, now),
            )
            self._conn.commit()

    def get_state(self, task_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT current_state FROM event_mode_states WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        return None if row is None else row["current_state"]

    def save_state_transition(
        self, task_id: str, from_state: str, to_state: str, reason: str, event_id: str = ""
    ) -> None:
        now = _iso_now()
        with self._write_lock:
            self._conn.execute(
                """INSERT INTO event_mode_transitions
                   (task_id, from_state, to_state, reason, event_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (task_id, from_state, to_state, reason, event_id, now),
            )
            self._conn.execute(
                """INSERT INTO event_mode_states
                   (task_id, current_state, reason, event_id, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(task_id) DO UPDATE SET
                       current_state = excluded.current_state,
                       reason = excluded.reason,
                       event_id = excluded.event_id,
                       updated_at = excluded.updated_at""",
                (task_id, to_state, reason, event_id, now),
            )
            self._conn.commit()

    def list_state_transitions(self, task_id: str) -> list[dict[str, object]]:
        rows = self._conn.execute(
            """SELECT from_state, to_state, reason, event_id, created_at
               FROM event_mode_transitions WHERE task_id = ? ORDER BY id""",
            (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Failure/Completion/Replan helpers ───────────────────────────────

    def save_failure_summary(self, summary: FailureSummary) -> FailureSummary:
        payload_hash = _canonical_hash(summary)
        payload = summary.model_dump_json()
        now = _iso_now()
        with self._write_lock:
            row = self._existing_by_key("failure_summaries", "summary_id", summary.summary_id)
            if row is not None:
                _same_or_conflict(
                    "FailureSummary",
                    summary.summary_id,
                    row["payload_hash"] or _canonical_hash(json.loads(row["payload_json"])),
                    payload_hash,
                )
                return FailureSummary.model_validate_json(row["payload_json"])
            saved = summary.model_copy(
                update={"summary_hash": summary.summary_hash or payload_hash}
            )
            payload = saved.model_dump_json()
            self._conn.execute(
                """INSERT INTO failure_summaries (
                    summary_id, task_id, failure_event_id, failed_step_id,
                    completed_step_ids_json, failure_type, severity, reason,
                    recovery_hint, local_retry_count, retry_limit,
                    requested_replan_scope, plan_version, command_seq,
                    payload_json, payload_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    saved.summary_id,
                    saved.task_id,
                    saved.failure_event_id,
                    saved.failed_step_id,
                    self._json(saved.completed_step_ids),
                    saved.failure_type,
                    saved.severity,
                    saved.reason,
                    saved.recovery_hint,
                    saved.local_retry_count,
                    saved.retry_limit,
                    saved.requested_replan_scope,
                    saved.plan_version,
                    saved.command_seq,
                    payload,
                    payload_hash,
                    now,
                    now,
                ),
            )
            self._conn.commit()
            return saved

    def get_failure_summary(self, summary_id: str) -> FailureSummary | None:
        row = self._conn.execute(
            "SELECT payload_json FROM failure_summaries WHERE summary_id = ?",
            (summary_id,),
        ).fetchone()
        return None if row is None else FailureSummary.model_validate_json(row["payload_json"])

    def save_completion_summary(self, summary: CompletionSummary) -> CompletionSummary:
        payload_hash = _canonical_hash(summary)
        payload = summary.model_dump_json()
        now = _iso_now()
        with self._write_lock:
            row = self._existing_by_key("completion_summaries", "summary_id", summary.summary_id)
            if row is not None:
                existing = CompletionSummary.model_validate_json(row["payload_json"])
                if existing.summary_hash and existing.summary_hash == summary.summary_hash:
                    return existing
                _same_or_conflict(
                    "CompletionSummary",
                    summary.summary_id,
                    row["payload_hash"] or _canonical_hash(json.loads(row["payload_json"])),
                    payload_hash,
                )
                return existing
            saved = summary.model_copy(
                update={"summary_hash": summary.summary_hash or payload_hash}
            )
            payload = saved.model_dump_json()
            self._conn.execute(
                """INSERT INTO completion_summaries (
                    summary_id, task_id, final_plan_version, completed_step_ids_json,
                    completion_criteria_results_json, local_retry_count, cloud_replan_count,
                    result, final_safety_decision, plan_version, command_seq,
                    payload_json, payload_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    saved.summary_id,
                    saved.task_id,
                    saved.final_plan_version,
                    self._json(saved.completed_step_ids),
                    self._json(saved.completion_criteria_results),
                    saved.local_retry_count,
                    saved.cloud_replan_count,
                    saved.result,
                    saved.final_safety_decision,
                    saved.plan_version,
                    saved.command_seq,
                    payload,
                    payload_hash,
                    now,
                    now,
                ),
            )
            self._conn.commit()
            return saved

    def get_completion_summary(self, summary_id: str) -> CompletionSummary | None:
        row = self._conn.execute(
            "SELECT payload_json FROM completion_summaries WHERE summary_id = ?",
            (summary_id,),
        ).fetchone()
        return None if row is None else CompletionSummary.model_validate_json(row["payload_json"])

    def get_completion_summary_for_task(self, task_id: str) -> CompletionSummary | None:
        row = self._conn.execute(
            """SELECT payload_json FROM completion_summaries
               WHERE task_id = ? ORDER BY id DESC LIMIT 1""",
            (task_id,),
        ).fetchone()
        return None if row is None else CompletionSummary.model_validate_json(row["payload_json"])

    def save_replan_request(self, request: LocalReplanningRequest) -> LocalReplanningRequest:
        payload_hash = _canonical_hash(request)
        payload = request.model_dump_json()
        now = _iso_now()
        with self._write_lock:
            row = self._existing_by_key("replan_requests", "request_id", request.request_id)
            if row is not None:
                _same_or_conflict(
                    "LocalReplanningRequest",
                    request.request_id,
                    row["payload_hash"] or _canonical_hash(json.loads(row["payload_json"])),
                    payload_hash,
                )
                return LocalReplanningRequest.model_validate_json(row["payload_json"])
            if request.idempotency_key:
                row = self._conn.execute(
                    """SELECT payload_json, payload_hash FROM replan_requests
                       WHERE idempotency_key = ?""",
                    (request.idempotency_key,),
                ).fetchone()
                if row is not None:
                    _same_or_conflict(
                        "LocalReplanningRequest",
                        request.idempotency_key,
                        row["payload_hash"] or _canonical_hash(json.loads(row["payload_json"])),
                        payload_hash,
                    )
                    return LocalReplanningRequest.model_validate_json(row["payload_json"])
            self._conn.execute(
                """INSERT INTO replan_requests (
                    request_id, idempotency_key, task_id, trigger_event_id,
                    failure_summary_id, current_plan_version, current_command_seq,
                    requested_replan_scope, completed_step_ids_json, failed_step_id,
                    payload_json, payload_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    request.request_id,
                    request.idempotency_key or None,
                    request.task_id,
                    request.trigger_event_id,
                    request.failure_summary_id,
                    request.current_plan_version,
                    request.current_command_seq,
                    request.requested_replan_scope,
                    self._json(request.completed_step_ids),
                    request.failed_step_id,
                    payload,
                    payload_hash,
                    now,
                    now,
                ),
            )
            self._conn.commit()
            return request

    def get_replan_request(self, request_id: str) -> LocalReplanningRequest | None:
        row = self._conn.execute(
            "SELECT payload_json FROM replan_requests WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        return (
            None if row is None else LocalReplanningRequest.model_validate_json(row["payload_json"])
        )

    def save_replan_result(self, result: LocalReplanningResponse) -> LocalReplanningResponse:
        payload_hash = _canonical_hash(result)
        payload = result.model_dump_json()
        now = _iso_now()
        with self._write_lock:
            row = self._existing_by_key("replan_results", "request_id", result.request_id)
            if row is not None:
                _same_or_conflict(
                    "LocalReplanningResponse",
                    result.request_id,
                    row["payload_hash"] or _canonical_hash(json.loads(row["payload_json"])),
                    payload_hash,
                )
                return LocalReplanningResponse.model_validate_json(row["payload_json"])
            task_id = self._task_id_for_request(result.request_id)
            saved = result.model_copy(
                update={"response_hash": result.response_hash or payload_hash}
            )
            payload = saved.model_dump_json()
            self._conn.execute(
                """INSERT INTO replan_results (
                    request_id, task_id, outcome, new_plan_version, new_command_seq,
                    new_steps_json, validation_errors_json, payload_json, payload_hash,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    saved.request_id,
                    task_id,
                    saved.outcome,
                    saved.new_plan_version,
                    saved.new_command_seq,
                    self._json([s.model_dump(mode="json") for s in saved.new_steps]),
                    self._json(saved.validation_errors),
                    payload,
                    payload_hash,
                    now,
                    now,
                ),
            )
            self._conn.commit()
            return saved

    def get_replan_result(self, request_id: str) -> LocalReplanningResponse | None:
        row = self._conn.execute(
            "SELECT payload_json FROM replan_results WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        return (
            None
            if row is None
            else LocalReplanningResponse.model_validate_json(row["payload_json"])
        )

    def _task_id_for_request(self, request_id: str) -> str:
        row = self._conn.execute(
            "SELECT task_id FROM replan_requests WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        return "" if row is None else row["task_id"]

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
        with self._write_lock:
            return self._save_active_contract_locked(
                contract,
                plan_id=plan_id,
                robot_id=robot_id,
                status=status,
                based_on_plan_version=based_on_plan_version,
                correlation_id=correlation_id,
            )

    def _save_active_contract_locked(
        self,
        contract: TaskContract,
        *,
        plan_id: str,
        robot_id: str,
        status: str,
        based_on_plan_version: int | None,
        correlation_id: str,
        commit: bool = True,
    ) -> ActiveTaskContractRecord:
        now = datetime.now(UTC)
        contract_hash = _canonical_hash(contract)
        existing = self._conn.execute(
            """SELECT record_json, contract_hash FROM task_contract_versions
               WHERE task_id = ? AND plan_version = ?""",
            (contract.task_id, contract.plan_version),
        ).fetchone()
        if existing is not None:
            _same_or_conflict(
                "ActiveTaskContract",
                f"{contract.task_id}:{contract.plan_version}",
                existing["contract_hash"],
                contract_hash,
            )
            record = ActiveTaskContractRecord.model_validate_json(existing["record_json"])
            if status == ActiveContractStatus.ACTIVE.value:
                self._set_active_locked(record)
            if commit:
                self._conn.commit()
            return record
        record = ActiveTaskContractRecord(
            task_id=contract.task_id,
            plan_id=plan_id,
            robot_id=robot_id,
            plan_version=contract.plan_version,
            command_seq=contract.command_seq,
            scene_version=contract.scene_version,
            contract=contract,
            status=status,
            based_on_plan_version=based_on_plan_version,
            created_at=now,
            activated_at=now,
            correlation_id=correlation_id,
            contract_hash=contract_hash,
        )
        if status == ActiveContractStatus.ACTIVE.value:
            current = self.get_active_contract(contract.task_id)
            if current is not None and current.plan_version != record.plan_version:
                self._supersede_version_locked(current.task_id, current.plan_version, now)
        self._conn.execute(
            """INSERT INTO task_contract_versions (
                task_id, plan_id, robot_id, plan_version, command_seq, scene_version,
                status, based_on_plan_version, contract_json, record_json, contract_hash,
                created_at, activated_at, superseded_at, correlation_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.task_id,
                record.plan_id,
                record.robot_id,
                record.plan_version,
                record.command_seq,
                record.scene_version,
                record.status,
                record.based_on_plan_version,
                contract.model_dump_json(),
                record.model_dump_json(),
                record.contract_hash,
                record.created_at.isoformat(),
                record.activated_at.isoformat(),
                record.superseded_at.isoformat() if record.superseded_at else None,
                record.correlation_id,
            ),
        )
        if status == ActiveContractStatus.ACTIVE.value:
            self._set_active_locked(record)
            self._conn.execute(
                """INSERT INTO plan_versions (task_id, plan_version, command_seq, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(task_id) DO UPDATE SET
                       plan_version = excluded.plan_version,
                       command_seq = excluded.command_seq,
                       updated_at = excluded.updated_at""",
                (record.task_id, record.plan_version, record.command_seq, _iso_now()),
            )
        if commit:
            self._conn.commit()
        return record

    def _set_active_locked(self, record: ActiveTaskContractRecord) -> None:
        now = _iso_now()
        self._conn.execute(
            """INSERT INTO active_task_contracts (
                task_id, plan_id, robot_id, plan_version, command_seq, scene_version,
                record_json, contract_hash, activated_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                plan_id = excluded.plan_id,
                robot_id = excluded.robot_id,
                plan_version = excluded.plan_version,
                command_seq = excluded.command_seq,
                scene_version = excluded.scene_version,
                record_json = excluded.record_json,
                contract_hash = excluded.contract_hash,
                activated_at = excluded.activated_at,
                updated_at = excluded.updated_at""",
            (
                record.task_id,
                record.plan_id,
                record.robot_id,
                record.plan_version,
                record.command_seq,
                record.scene_version,
                record.model_dump_json(),
                record.contract_hash,
                record.activated_at.isoformat(),
                now,
            ),
        )

    def _supersede_version_locked(self, task_id: str, plan_version: int, at: datetime) -> None:
        row = self._conn.execute(
            "SELECT record_json FROM task_contract_versions WHERE task_id = ? AND plan_version = ?",
            (task_id, plan_version),
        ).fetchone()
        if row is None:
            return
        record = ActiveTaskContractRecord.model_validate_json(row["record_json"])
        updated = record.model_copy(
            update={"status": ActiveContractStatus.SUPERSEDED.value, "superseded_at": at},
            deep=True,
        )
        self._conn.execute(
            """UPDATE task_contract_versions
               SET status = ?, record_json = ?, superseded_at = ?
               WHERE task_id = ? AND plan_version = ?""",
            (
                updated.status,
                updated.model_dump_json(),
                updated.superseded_at.isoformat() if updated.superseded_at else None,
                task_id,
                plan_version,
            ),
        )

    def get_active_contract(self, task_id: str) -> ActiveTaskContractRecord | None:
        row = self._conn.execute(
            "SELECT record_json FROM active_task_contracts WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        return (
            None
            if row is None
            else ActiveTaskContractRecord.model_validate_json(row["record_json"])
        )

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
        with self._write_lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            active = self.get_active_contract(task_id)
            if (
                active is None
                or active.plan_version != expected_plan_version
                or active.command_seq != expected_command_seq
                or new_contract.task_id != task_id
                or new_contract.plan_version <= expected_plan_version
                or new_contract.command_seq <= expected_command_seq
            ):
                return None
            staged = None
            if replan_record is not None:
                staged = ReplanApplyRecord.model_validate(replan_record.model_dump())
                previous = self.get_replan_apply_record(staged.apply_id)
                checkpoint = self.get_latest_execution_checkpoint(task_id)
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
                    or staged.payload_hash != _canonical_hash(new_contract)
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
            record = self._save_active_contract_locked(
                new_contract,
                plan_id=plan_id,
                robot_id=robot_id,
                status="ACTIVE",
                based_on_plan_version=based_on_plan_version,
                correlation_id=correlation_id,
                commit=False,
            )
            if staged is not None:
                self._update_apply_locked(staged)
            return record.model_copy(deep=True)

    def list_contract_versions(self, task_id: str) -> list[ActiveTaskContractRecord]:
        rows = self._conn.execute(
            """SELECT record_json FROM task_contract_versions
               WHERE task_id = ? ORDER BY plan_version""",
            (task_id,),
        ).fetchall()
        return [ActiveTaskContractRecord.model_validate_json(r["record_json"]) for r in rows]

    # ── Checkpoints ─────────────────────────────────────────────────────

    def save_execution_checkpoint(self, checkpoint: ExecutionCheckpoint) -> ExecutionCheckpoint:
        h = checkpoint.checkpoint_hash or _checkpoint_hash(checkpoint)
        saved = checkpoint.model_copy(update={"checkpoint_hash": h}, deep=True)
        payload = saved.model_dump_json()
        now = _iso_now()
        with self._write_lock:
            row = self._conn.execute(
                """SELECT payload_json, checkpoint_hash FROM execution_checkpoints
                   WHERE checkpoint_id = ?""",
                (saved.checkpoint_id,),
            ).fetchone()
            if row is not None:
                _same_or_conflict(
                    "ExecutionCheckpoint", saved.checkpoint_id, row["checkpoint_hash"], h
                )
                return ExecutionCheckpoint.model_validate_json(row["payload_json"])
            self._conn.execute(
                """INSERT INTO execution_checkpoints (
                    checkpoint_id, task_id, plan_id, robot_id, plan_version, command_seq,
                    execution_state, completed_step_ids_json, payload_json, checkpoint_hash,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    saved.checkpoint_id,
                    saved.task_id,
                    saved.plan_id,
                    saved.robot_id,
                    saved.plan_version,
                    saved.command_seq,
                    saved.execution_state,
                    self._json(saved.completed_step_ids),
                    payload,
                    h,
                    saved.created_at.isoformat(),
                    now,
                ),
            )
            self._conn.commit()
            return saved

    def get_latest_execution_checkpoint(self, task_id: str) -> ExecutionCheckpoint | None:
        row = self._conn.execute(
            """SELECT payload_json FROM execution_checkpoints
               WHERE task_id = ? ORDER BY id DESC LIMIT 1""",
            (task_id,),
        ).fetchone()
        return None if row is None else ExecutionCheckpoint.model_validate_json(row["payload_json"])

    def get_checkpoint(self, checkpoint_id: str) -> ExecutionCheckpoint | None:
        row = self._conn.execute(
            "SELECT payload_json FROM execution_checkpoints WHERE checkpoint_id = ?",
            (checkpoint_id,),
        ).fetchone()
        return None if row is None else ExecutionCheckpoint.model_validate_json(row["payload_json"])

    def compare_and_set_checkpoint(
        self,
        *,
        checkpoint_id: str,
        expected_checkpoint_hash: str,
        new_checkpoint: ExecutionCheckpoint,
    ) -> bool:
        existing = self.get_checkpoint(checkpoint_id)
        if existing is None or existing.checkpoint_hash != expected_checkpoint_hash:
            return False
        h = new_checkpoint.checkpoint_hash or _checkpoint_hash(new_checkpoint)
        saved = new_checkpoint.model_copy(update={"checkpoint_hash": h}, deep=True)
        payload = saved.model_dump_json()
        with self._write_lock:
            if saved.checkpoint_id == checkpoint_id:
                cursor = self._conn.execute(
                    """UPDATE execution_checkpoints
                       SET task_id = ?, plan_id = ?, robot_id = ?, plan_version = ?,
                           command_seq = ?, execution_state = ?, completed_step_ids_json = ?,
                           payload_json = ?, checkpoint_hash = ?, updated_at = ?
                       WHERE checkpoint_id = ? AND checkpoint_hash = ?""",
                    (
                        saved.task_id,
                        saved.plan_id,
                        saved.robot_id,
                        saved.plan_version,
                        saved.command_seq,
                        saved.execution_state,
                        self._json(saved.completed_step_ids),
                        payload,
                        h,
                        _iso_now(),
                        checkpoint_id,
                        expected_checkpoint_hash,
                    ),
                )
                self._conn.commit()
                return cursor.rowcount == 1
            row = self._conn.execute(
                "SELECT checkpoint_hash FROM execution_checkpoints WHERE checkpoint_id = ?",
                (saved.checkpoint_id,),
            ).fetchone()
            if row is not None:
                _same_or_conflict(
                    "ExecutionCheckpoint", saved.checkpoint_id, row["checkpoint_hash"], h
                )
                return True
            self._conn.execute(
                """INSERT INTO execution_checkpoints (
                    checkpoint_id, task_id, plan_id, robot_id, plan_version, command_seq,
                    execution_state, completed_step_ids_json, payload_json, checkpoint_hash,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    saved.checkpoint_id,
                    saved.task_id,
                    saved.plan_id,
                    saved.robot_id,
                    saved.plan_version,
                    saved.command_seq,
                    saved.execution_state,
                    self._json(saved.completed_step_ids),
                    payload,
                    h,
                    saved.created_at.isoformat(),
                    _iso_now(),
                ),
            )
            self._conn.commit()
            return True

    # ── Replan apply and ACK ────────────────────────────────────────────

    def _replan_cancelled_locked(self, task_id: str) -> bool:
        return self.get_state(task_id) in {
            "CANCELLED",
            "ABORTED",
            "STOPPED",
            "SAFETY_STOPPED",
            "COMPLETED",
        } or any(
            event.severity == "CRITICAL" or event.event_type.value == "MANUAL_INTERRUPT"
            for event in self.list_events(task_id)
        )

    def _update_apply_locked(self, record: ReplanApplyRecord) -> ReplanApplyRecord:
        saved = record.model_copy(update={"apply_hash": record.content_hash()}, deep=True)
        self._conn.execute(
            "UPDATE replan_apply_records SET status=?, reason=?, payload_json=?, apply_hash=? "
            "WHERE apply_id=?",
            (saved.status, saved.reason, saved.model_dump_json(), saved.apply_hash, saved.apply_id),
        )
        return saved.model_copy(deep=True)

    def save_replan_apply_record(self, record: ReplanApplyRecord) -> ReplanApplyRecord:
        record = ReplanApplyRecord.model_validate(record.model_dump())
        h = record.content_hash()
        saved = record.model_copy(update={"apply_hash": h}, deep=True)
        payload = saved.model_dump_json()
        with self._write_lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            row = self._conn.execute(
                """SELECT payload_json, apply_hash FROM replan_apply_records
                   WHERE apply_id = ? OR request_id = ?""",
                (saved.apply_id, saved.request_id),
            ).fetchone()
            if row is not None:
                _same_or_conflict("ReplanApplyRecord", saved.apply_id, row["apply_hash"], h)
                return ReplanApplyRecord.model_validate_json(row["payload_json"])
            if saved.status in {"EDGE_ACCEPTED", "ACTIVATED", "EXECUTION_STARTED"}:
                raise ValueError("public insert cannot assert edge activation")
            if record.stage_attempt_id:
                raise ValueError("public insert cannot assert edge activation")
            self._conn.execute(
                """INSERT INTO replan_apply_records (
                    apply_id, request_id, task_id, plan_id, robot_id,
                    previous_plan_version, previous_command_seq, new_plan_version,
                    new_command_seq, checkpoint_id, status, reason, payload_json,
                    apply_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    saved.apply_id,
                    saved.request_id,
                    saved.task_id,
                    saved.plan_id,
                    saved.robot_id,
                    saved.previous_plan_version,
                    saved.previous_command_seq,
                    saved.new_plan_version,
                    saved.new_command_seq,
                    saved.checkpoint_id,
                    saved.status,
                    saved.reason,
                    payload,
                    h,
                    saved.created_at.isoformat(),
                ),
            )
            return saved

    def update_replan_apply_record_if_current(
        self,
        record: ReplanApplyRecord,
        *,
        expected_status: str,
    ) -> ReplanApplyRecord | None:
        record = ReplanApplyRecord.model_validate(record.model_dump())
        with self._write_lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            previous = self.get_replan_apply_record(record.apply_id)
            if previous is None:
                return None
            if record.status == "EXECUTION_STARTED":
                assert record.start_receipt is not None
                rows = self._conn.execute(
                    "SELECT payload_json FROM replan_apply_records "
                    "WHERE status='EXECUTION_STARTED' AND apply_id != ?",
                    (record.apply_id,),
                ).fetchall()
                for row in rows:
                    other = ReplanApplyRecord.model_validate_json(row["payload_json"])
                    if (
                        other.start_receipt is not None
                        and other.start_receipt.event_id == record.start_receipt.event_id
                    ):
                        raise ValueError("execution start event already belongs to another repair")
                active = self.get_active_contract(record.task_id)
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
            return self._update_apply_locked(record)

    def get_replan_apply_record(self, apply_id: str) -> ReplanApplyRecord | None:
        row = self._conn.execute(
            "SELECT payload_json FROM replan_apply_records WHERE apply_id = ?",
            (apply_id,),
        ).fetchone()
        return None if row is None else ReplanApplyRecord.model_validate_json(row["payload_json"])

    def get_replan_apply_record_for_request(self, request_id: str) -> ReplanApplyRecord | None:
        row = self._conn.execute(
            "SELECT payload_json FROM replan_apply_records WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        return None if row is None else ReplanApplyRecord.model_validate_json(row["payload_json"])

    def save_command_ack(self, ack: CommandAck) -> CommandAck:
        key = ack.request_id or f"{ack.task_id}:{ack.plan_version}:{ack.command_seq}"
        h = _canonical_hash(ack)
        payload = ack.model_dump_json()
        with self._write_lock:
            row = self._conn.execute(
                "SELECT payload_json, payload_hash FROM command_acks WHERE ack_key = ?",
                (key,),
            ).fetchone()
            if row is not None:
                _same_or_conflict("CommandAck", key, row["payload_hash"], h)
                return CommandAck.model_validate_json(row["payload_json"])
            self._conn.execute(
                """INSERT INTO command_acks (
                    ack_key, request_id, task_id, plan_version, command_seq,
                    checkpoint_id, status, accepted, payload_json, payload_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    key,
                    ack.request_id,
                    ack.task_id,
                    ack.plan_version,
                    ack.command_seq,
                    ack.checkpoint_id,
                    ack.status,
                    int(ack.accepted),
                    payload,
                    h,
                    _iso_now(),
                ),
            )
            self._conn.commit()
            return ack

    def get_command_ack(self, request_id: str) -> CommandAck | None:
        row = self._conn.execute(
            """SELECT payload_json FROM command_acks
               WHERE ack_key = ? OR request_id = ? ORDER BY id DESC LIMIT 1""",
            (request_id, request_id),
        ).fetchone()
        return None if row is None else CommandAck.model_validate_json(row["payload_json"])

    # ── Outbox ──────────────────────────────────────────────────────────

    def enqueue_outbox(self, message: PendingMessage) -> PendingMessage:
        payload_hash = _canonical_hash(message)
        payload = message.model_dump_json()
        now = _iso_now()
        with self._write_lock:
            row = self._existing_by_key("event_outbox", "message_id", message.message_id)
            if row is not None:
                _same_or_conflict(
                    "PendingMessage",
                    message.message_id,
                    row["payload_hash"] or _canonical_hash(json.loads(row["payload_json"])),
                    payload_hash,
                )
                return PendingMessage.model_validate_json(row["payload_json"])
            idempotency_key = message.idempotency_key or message.message_id
            row = self._conn.execute(
                "SELECT payload_json, payload_hash FROM event_outbox WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if row is not None:
                _same_or_conflict(
                    "PendingMessage",
                    idempotency_key,
                    row["payload_hash"] or _canonical_hash(json.loads(row["payload_json"])),
                    payload_hash,
                )
                return PendingMessage.model_validate_json(row["payload_json"])
            self._conn.execute(
                """INSERT INTO event_outbox (
                    message_id, idempotency_key, task_id, message_type, payload_json,
                    payload_hash, status, retry_count, max_retries, backoff_base_ms,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    message.message_id,
                    idempotency_key,
                    message.task_id,
                    message.message_type,
                    payload,
                    payload_hash,
                    message.status.value,
                    message.retry_count,
                    message.max_retries,
                    message.backoff_base_ms,
                    now,
                    now,
                ),
            )
            self._conn.commit()
            return message

    def claim_outbox_message(self) -> PendingMessage | None:
        now = _iso_now()
        with self._write_lock:
            row = self._conn.execute(
                """SELECT message_id, payload_json FROM event_outbox
                   WHERE status IN ('PENDING', 'RETRY_WAIT')
                     AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                   ORDER BY id LIMIT 1""",
                (now,),
            ).fetchone()
            if row is None:
                return None
            msg = PendingMessage.model_validate_json(row["payload_json"])
            updated = msg.model_copy(update={"status": MessageStatus.SENDING}, deep=True)
            updated_payload = updated.model_dump_json()
            cursor = self._conn.execute(
                """UPDATE event_outbox
                   SET status = 'SENDING', claimed_at = ?, payload_json = ?,
                       payload_hash = ?, updated_at = ?
                   WHERE message_id = ? AND status IN ('PENDING', 'RETRY_WAIT')""",
                (now, updated_payload, _canonical_hash(updated), now, msg.message_id),
            )
            self._conn.commit()
            return updated if cursor.rowcount == 1 else None

    def mark_outbox_sent(self, message_id: str) -> bool:
        now = _iso_now()
        with self._write_lock:
            row = self._conn.execute(
                "SELECT status, payload_json FROM event_outbox WHERE message_id = ?",
                (message_id,),
            ).fetchone()
            if row is None:
                return False
            if row["status"] == "SENT":
                return True
            if row["status"] != "SENDING":
                return False
            msg = PendingMessage.model_validate_json(row["payload_json"])
            updated = msg.model_copy(update={"status": MessageStatus.SENT}, deep=True)
            cursor = self._conn.execute(
                """UPDATE event_outbox
                   SET status = 'SENT', payload_json = ?, payload_hash = ?, updated_at = ?
                   WHERE message_id = ? AND status = 'SENDING'""",
                (updated.model_dump_json(), _canonical_hash(updated), now, message_id),
            )
            self._conn.commit()
            return cursor.rowcount == 1

    def mark_outbox_failed(self, message_id: str, error: str) -> bool:
        now = _iso_now()
        with self._write_lock:
            row = self._conn.execute(
                """SELECT retry_count, max_retries, backoff_base_ms, payload_json
                   FROM event_outbox WHERE message_id = ?""",
                (message_id,),
            ).fetchone()
            if row is None:
                return False
            msg = PendingMessage.model_validate_json(row["payload_json"])
            new_count = int(row["retry_count"]) + 1
            if new_count >= int(row["max_retries"]):
                new_status = MessageStatus.DEAD_LETTER
                next_attempt = None
            else:
                new_status = MessageStatus.RETRY_WAIT
                backoff_ms = int(row["backoff_base_ms"]) * (2 ** (new_count - 1))
                next_attempt = datetime.now(UTC) + timedelta(milliseconds=backoff_ms)
            updated = msg.model_copy(
                update={
                    "status": new_status,
                    "retry_count": new_count,
                    "last_error": error,
                    "next_retry_at": next_attempt,
                },
                deep=True,
            )
            self._conn.execute(
                """UPDATE event_outbox
                   SET status = ?, retry_count = ?, last_error = ?, next_attempt_at = ?,
                       payload_json = ?, payload_hash = ?, updated_at = ?
                   WHERE message_id = ?""",
                (
                    new_status.value,
                    new_count,
                    error,
                    next_attempt.isoformat() if next_attempt else None,
                    updated.model_dump_json(),
                    _canonical_hash(updated),
                    now,
                    message_id,
                ),
            )
            self._conn.commit()
            return True

    def list_pending_outbox(self, task_id: str | None = None) -> list[PendingMessage]:
        if task_id is None:
            rows = self._conn.execute(
                """SELECT payload_json FROM event_outbox
                   WHERE status IN ('PENDING', 'RETRY_WAIT') ORDER BY id"""
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT payload_json FROM event_outbox
                   WHERE status IN ('PENDING', 'RETRY_WAIT') AND task_id = ? ORDER BY id""",
                (task_id,),
            ).fetchall()
        return [PendingMessage.model_validate_json(r["payload_json"]) for r in rows]

    # ── Version Management ──────────────────────────────────────────────

    def advance_plan_version_if_current(
        self,
        task_id: str,
        expected_plan_version: int,
        expected_command_seq: int,
        new_plan_version: int,
        new_command_seq: int,
    ) -> bool:
        if new_plan_version <= expected_plan_version or new_command_seq <= expected_command_seq:
            return False
        now = _iso_now()
        with self._write_lock:
            row = self._conn.execute(
                "SELECT plan_version, command_seq FROM plan_versions WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if row is None:
                self._conn.execute(
                    """INSERT INTO plan_versions
                       (task_id, plan_version, command_seq, updated_at)
                       VALUES (?, ?, ?, ?)""",
                    (task_id, expected_plan_version, expected_command_seq, now),
                )
            elif (
                int(row["plan_version"]) != expected_plan_version
                or int(row["command_seq"]) != expected_command_seq
            ):
                self._conn.commit()
                return False
            cursor = self._conn.execute(
                """UPDATE plan_versions
                   SET plan_version = ?, command_seq = ?, updated_at = ?
                   WHERE task_id = ? AND plan_version = ? AND command_seq = ?""",
                (
                    new_plan_version,
                    new_command_seq,
                    now,
                    task_id,
                    expected_plan_version,
                    expected_command_seq,
                ),
            )
            self._conn.commit()
            return cursor.rowcount == 1

    # ── Audit/Lifecycle ─────────────────────────────────────────────────

    def record_audit_event(self, task_id: str, event_type: str, details: dict[str, object]) -> None:
        now = _iso_now()
        with self._write_lock:
            self._conn.execute(
                """INSERT INTO event_audit_events
                   (task_id, event_type, details_json, created_at)
                   VALUES (?, ?, ?, ?)""",
                (task_id, event_type, self._json(details), now),
            )
            self._conn.commit()

    def _visual_original_locked(self, task_id: str, plan_version: int) -> VisualOriginalPlan | None:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
            original_from_payload,
        )

        row = self._conn.execute(
            "SELECT * FROM visual_original_plans WHERE task_id=? AND plan_version=?",
            (task_id, plan_version),
        ).fetchone()
        if row is None:
            return None
        original = original_from_payload(json.loads(row["payload_json"]))
        if (
            original.digest() != row["original_hash"]
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
            row = self._conn.execute(
                "SELECT * FROM visual_owner_publications WHERE task_id=? "
                "ORDER BY owner_revision DESC LIMIT 1",
                (task_id,),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT * FROM visual_owner_publications WHERE task_id=? AND owner_revision=?",
                (task_id, revision),
            ).fetchone()
        if row is None:
            return None
        result = VisualOwnerPublicationRecord.from_payload(json.loads(row["payload_json"]))
        if (
            result.identity.task_id != task_id
            or result.owner_revision != row["owner_revision"]
            or result.identity.owner_epoch != row["owner_epoch"]
            or result.state_generation != row["state_generation"]
            or result.digest() != row["publication_hash"]
        ):
            raise ValueError("stored publication columns/hash differ")
        return result

    def _visual_group_locked(self, task_id: str) -> tuple[Any, Any, Any, Any]:
        active = None
        row = self._conn.execute(
            "SELECT * FROM active_task_contracts WHERE task_id=?", (task_id,)
        ).fetchone()
        if row is not None:
            active = ActiveTaskContractRecord.model_validate_json(row["record_json"])
            if any(
                getattr(active, name) != row[name]
                for name in (
                    "task_id",
                    "plan_id",
                    "robot_id",
                    "plan_version",
                    "command_seq",
                    "scene_version",
                    "contract_hash",
                )
            ):
                raise ValueError("active source columns differ")
        checkpoint = None
        row = self._conn.execute(
            "SELECT * FROM execution_checkpoints WHERE task_id=? ORDER BY id DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        if row is not None:
            checkpoint = ExecutionCheckpoint.model_validate_json(row["payload_json"])
            if any(
                getattr(checkpoint, name) != row[name]
                for name in (
                    "checkpoint_id",
                    "task_id",
                    "plan_id",
                    "robot_id",
                    "plan_version",
                    "command_seq",
                    "execution_state",
                    "checkpoint_hash",
                )
            ):
                raise ValueError("checkpoint source columns differ")
        return (
            active,
            checkpoint,
            self.get_verification_budget(task_id),
            self.get_retry_budget(task_id),
        )

    def _visual_versions_match(self, original: VisualOriginalPlan) -> bool:
        row = self._conn.execute(
            "SELECT plan_version,command_seq FROM plan_versions WHERE task_id=?",
            (original.identity.task_id,),
        ).fetchone()
        active = self._conn.execute(
            "SELECT record_json FROM active_task_contracts WHERE task_id=?",
            (original.identity.task_id,),
        ).fetchone()
        version = self._conn.execute(
            "SELECT record_json,contract_hash,plan_id,robot_id,command_seq,scene_version "
            "FROM task_contract_versions WHERE task_id=? AND plan_version=?",
            (original.identity.task_id, original.contract.plan_version),
        ).fetchone()
        if row is None or active is None or version is None:
            return False
        active_payload, version_payload = (
            json.loads(active["record_json"]),
            json.loads(version["record_json"]),
        )
        return (
            (row["plan_version"], row["command_seq"])
            == (original.contract.plan_version, original.contract.command_seq)
            and active_payload == version_payload
            and all(
                version_payload[name] == version[name]
                for name in ("contract_hash", "plan_id", "robot_id", "command_seq", "scene_version")
            )
        )

    def _visual_store_record_locked(self, record: VisualOwnerPublicationRecord) -> None:
        self._conn.execute(
            "INSERT INTO visual_owner_publications VALUES (?,?,?,?,?,?)",
            (
                record.identity.task_id,
                record.owner_revision,
                record.identity.owner_epoch,
                record.state_generation,
                self._json(record.to_payload()),
                record.digest(),
            ),
        )

    def _visual_store_checkpoint_locked(self, checkpoint: ExecutionCheckpoint) -> None:
        row = self._conn.execute(
            "SELECT checkpoint_hash FROM execution_checkpoints WHERE checkpoint_id=?",
            (checkpoint.checkpoint_id,),
        ).fetchone()
        if row is not None:
            _same_or_conflict(
                "ExecutionCheckpoint",
                checkpoint.checkpoint_id,
                row["checkpoint_hash"],
                checkpoint.checkpoint_hash,
            )
            return
        self._conn.execute(
            """INSERT INTO execution_checkpoints (
            checkpoint_id,task_id,plan_id,robot_id,plan_version,command_seq,execution_state,
            completed_step_ids_json,payload_json,checkpoint_hash,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                checkpoint.checkpoint_id,
                checkpoint.task_id,
                checkpoint.plan_id,
                checkpoint.robot_id,
                checkpoint.plan_version,
                checkpoint.command_seq,
                checkpoint.execution_state,
                self._json(checkpoint.completed_step_ids),
                checkpoint.model_dump_json(),
                checkpoint.checkpoint_hash,
                checkpoint.created_at.isoformat(),
                checkpoint.updated_at.isoformat(),
            ),
        )

    def _visual_store_retry_locked(self, retry: RecoveryBudget) -> None:
        self._conn.execute(
            """INSERT INTO recovery_budgets (
            budget_id,task_id,per_step_retry_limit,per_skill_retry_limit,task_total_retry_limit,
            retry_count_used,task_retry_count,step_retry_counts_json,skill_retry_counts_json,event_retry_counts_json,
            retry_cooldown_ms,retry_deadline,retry_backoff_policy,effective_retry_limit,remaining_retries,
            scene_version,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                retry.budget_id,
                retry.task_id,
                retry.per_step_retry_limit,
                retry.per_skill_retry_limit,
                retry.task_total_retry_limit,
                retry.retry_count_used,
                retry.task_retry_count,
                self._json(retry.step_retry_counts),
                self._json(retry.skill_retry_counts),
                self._json(retry.event_retry_counts),
                retry.retry_cooldown_ms,
                retry.retry_deadline.isoformat() if retry.retry_deadline else None,
                retry.retry_backoff_policy,
                retry.effective_retry_limit,
                retry.remaining_retries,
                retry.scene_version,
                retry.created_at.isoformat(),
                retry.updated_at.isoformat(),
            ),
        )

    def _visual_verification_group_locked(self, task_id: str) -> tuple[Any, Any, Any, Any]:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import counter
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_verification import (
            _load,
            _pool,
            strict_source_json_model,
        )

        for table, column, model in (
            ("active_task_contracts", "record_json", ActiveTaskContractRecord),
            ("execution_checkpoints", "payload_json", ExecutionCheckpoint),
        ):
            order = " ORDER BY id DESC" if table == "execution_checkpoints" else ""
            row = self._conn.execute(
                f"SELECT {column} FROM {table} WHERE task_id=?{order} LIMIT 1",
                (task_id,),
            ).fetchone()
            if row is not None:
                strict_source_json_model(row[0], model)
        row = self._conn.execute(
            "SELECT payload_json FROM verification_budgets WHERE task_id=?",
            (task_id,),
        ).fetchone()
        if row is not None:
            _pool(_load(row[0]))
        row = self._conn.execute(
            "SELECT * FROM recovery_budgets WHERE task_id=?",
            (task_id,),
        ).fetchone()
        if row is not None:
            for name in (
                "step_retry_counts_json",
                "skill_retry_counts_json",
                "event_retry_counts_json",
            ):
                for value in _load(row[name]).values():
                    counter(value)
        return self._visual_group_locked(task_id)

    def _visual_verification_record_locked(
        self,
        task_id: str,
        *,
        event_key: str | None = None,
        source_key: str | None = None,
    ) -> VisualVerificationRouteRecord | None:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_verification import (
            VisualVerificationRouteRecord,
        )

        column, key = (
            ("event_key", event_key) if event_key is not None else ("source_key", source_key)
        )
        row = self._conn.execute(
            f"SELECT * FROM visual_verification_routes WHERE task_id=? AND {column}=?",
            (task_id, key),
        ).fetchone()
        if row is None:
            return None
        record = VisualVerificationRouteRecord.from_json(row["payload_json"])
        payload = record.to_payload()
        if (
            record.digest() != row["record_hash"]
            or payload["source_key"] != row["source_key"]
            or payload["input"]["event_key"] != row["event_key"]
            or payload["input"]["original"]["identity"]["task_id"] != task_id
        ):
            raise ValueError("stored verification row/hash differs")
        return record

    def get_visual_verification_route(
        self,
        task_id: str,
        event_key: str,
    ) -> VisualVerificationRouteRecord | None:
        with self._write_lock, self._conn:
            self._conn.execute("BEGIN")
            return self._visual_verification_record_locked(task_id, event_key=event_key)

    def route_visual_verification_if_current(
        self,
        *,
        request: VisualVerificationRouteInput,
    ) -> VisualVerificationRouteWriteResult | None:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_verification import (
            VisualVerificationRouteInput,
            VisualVerificationRouteWriteResult,
            derive_route,
            historical_duplicate,
        )

        if type(request) is not VisualVerificationRouteInput:
            raise ValueError("concrete source routing input required")
        request = VisualVerificationRouteInput.from_json(request.to_json())
        task_id = request.task_id
        with self._write_lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            stored = self._visual_verification_record_locked(task_id, event_key=request.event_key)
            same_event = stored is not None
            if stored is None:
                stored = self._visual_verification_record_locked(
                    task_id, source_key=request.source_key()
                )
            if stored is not None:
                return historical_duplicate(request, stored, same_event=same_event)
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
            try:
                group = self._visual_verification_group_locked(task_id)
                values = derive_route(
                    request,
                    original,
                    prior,
                    ancestor,
                    *group,
                    cancelled=self._replan_cancelled_locked(task_id),
                    now=datetime.now(UTC),
                )
            except (ValueError, TypeError):
                return None
            if values is None:
                return None
            record, pool, produced = values
            self._conn.execute(
                "UPDATE verification_budgets SET revision=?,payload_json=?,content_hash=? "
                "WHERE task_id=?",
                (pool.revision, self._json(pool.to_payload()), pool.content_hash, task_id),
            )
            self._visual_store_record_locked(produced)
            self._conn.execute(
                "INSERT INTO visual_verification_routes VALUES (?,?,?,?,?)",
                (
                    task_id,
                    request.event_key,
                    request.source_key(),
                    record.to_json(),
                    record.digest(),
                ),
            )
            return VisualVerificationRouteWriteResult(record, "NEW_COMMIT")

    def get_visual_original_plan(
        self, task_id: str, plan_version: int
    ) -> VisualOriginalPlan | None:
        with self._write_lock, self._conn:
            self._conn.execute("BEGIN")
            return self._visual_original_locked(task_id, plan_version)

    def get_visual_owner_publication(self, task_id: str) -> VisualOwnerPublicationRecord | None:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
            current_publication,
        )

        with self._write_lock, self._conn:
            self._conn.execute("BEGIN")
            record = self._visual_record_locked(task_id)
            if record is None:
                return None
            original = self._visual_original_locked(task_id, record.checkpoint.plan_version)
            if original is None or not self._visual_versions_match(original):
                return None
            previous = (
                self._visual_record_locked(task_id, record.owner_revision - 1)
                if record.owner_revision > 1
                else None
            )
            try:
                group = self._visual_group_locked(task_id)
            except (ValueError, TypeError):
                return None
            return (
                record.detached()
                if current_publication(record, original, *group, previous=previous)
                else None
            )

    def _visual_bootstrap_for_original_locked(
        self, original: VisualOriginalPlan
    ) -> VisualBootstrapRecord | None:
        matching = []
        for row in self._conn.execute("SELECT bootstrap_id FROM visual_bootstraps").fetchall():
            record = self._visual_bootstrap_locked(row["bootstrap_id"])
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
        with self._write_lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            bootstrap = self._visual_bootstrap_for_original_locked(original)
            first = self._visual_record_locked(task, 1)
            promoted: VisualBootstrapRecord | None = None
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
                        bootstrap, bootstrap_promotion, pool.state, retry, now=datetime.now(UTC)
                    )
                    promoted = VisualBootstrapRecord.from_json(promoted.to_json())
                except (ValueError, TypeError) as error:
                    raise IdempotencyConflictError("current bootstrap promotion differs") from error
            if first is not None:
                _same_or_conflict(
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
            if self._conn.execute(
                "SELECT 1 FROM visual_original_plans WHERE task_id=?", (task,)
            ).fetchone():
                raise IdempotencyConflictError("original sidecar exists without publication")
            try:
                active, prior_checkpoint, prior_pool, prior_retry = self._visual_group_locked(task)
            except (ValueError, TypeError) as error:
                raise IdempotencyConflictError("existing visual source differs") from error
            present = [
                item is not None for item in (active, prior_checkpoint, prior_pool, prior_retry)
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
                if (
                    self._conn.execute(
                        "SELECT 1 FROM task_contract_versions WHERE task_id=?", (task,)
                    ).fetchone()
                    or self._conn.execute(
                        "SELECT 1 FROM plan_versions WHERE task_id=?", (task,)
                    ).fetchone()
                ):
                    raise IdempotencyConflictError("partial existing contract/version history")
                if self._conn.execute(
                    "SELECT 1 FROM execution_checkpoints WHERE checkpoint_id=?",
                    (checkpoint.checkpoint_id,),
                ).fetchone():
                    raise IdempotencyConflictError(
                        "initial checkpoint identity already belongs to a source"
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
            if not any(present):
                self._save_active_contract_locked(
                    original.contract,
                    plan_id=original.identity.plan_id,
                    robot_id=original.identity.robot_id,
                    status="ACTIVE",
                    based_on_plan_version=None,
                    correlation_id="",
                    commit=False,
                )
                self._visual_store_checkpoint_locked(checkpoint)
                self._visual_store_retry_locked(retry)
                self._conn.execute(
                    "INSERT INTO verification_budgets VALUES (?,?,?,?)",
                    (
                        task,
                        pool.revision,
                        self._json(pool.to_payload()),
                        pool.content_hash,
                    ),
                )
            self._conn.execute(
                "INSERT INTO visual_original_plans VALUES (?,?,?,?)",
                (
                    task,
                    original.contract.plan_version,
                    canonical(original.to_payload()),
                    original.digest(),
                ),
            )
            self._visual_store_record_locked(saved)
            if promoted is not None:
                self._visual_store_bootstrap_locked(promoted)
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
        with self._write_lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
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
            try:
                active, current, pool, retry = self._visual_group_locked(task_id)
            except (ValueError, TypeError):
                return None
            if (
                original is None
                or any(item is None for item in (active, current, pool, retry))
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
            row = self._conn.execute(
                "SELECT payload_json,checkpoint_hash FROM execution_checkpoints "
                "WHERE checkpoint_id=?",
                (next_checkpoint.checkpoint_id,),
            ).fetchone()
            if row is not None and (
                row["checkpoint_hash"] != next_checkpoint.checkpoint_hash
                or canonical(json.loads(row["payload_json"]))
                != canonical(next_checkpoint.model_dump(mode="json"))
            ):
                return None
            self._visual_store_checkpoint_locked(next_checkpoint)
            self._visual_store_record_locked(saved)
            return saved.detached()

    def close(self) -> None:
        self._conn.close()
