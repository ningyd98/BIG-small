"""仓储接口或实现，隔离业务服务与底层存储细节。"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from cloud_edge_robot_arm.contracts import SafetyDecision
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import (
    IdempotencyConflictError,
    VersionConflictError,
)
from cloud_edge_robot_arm.skill_cache.models import (
    SkillCacheKey,
    SkillCacheLookupResult,
    SkillCachePromotionPolicy,
    SkillExecutionRecord,
    SkillStatistics,
    SkillTemplate,
    SkillTemplateStatus,
    stable_payload_hash,
)


@runtime_checkable
class SkillCacheRepository(Protocol):
    def save_template(self, template: SkillTemplate) -> SkillTemplate: ...

    def get_template(self, template_id: str) -> SkillTemplate | None: ...

    def lookup_templates(self, key: SkillCacheKey) -> SkillCacheLookupResult: ...

    def save_execution_record(self, record: SkillExecutionRecord) -> SkillExecutionRecord: ...

    def get_statistics(self, template_id: str) -> SkillStatistics: ...

    def promote_template(
        self,
        template_id: str,
        *,
        policy: SkillCachePromotionPolicy,
        expected_template_version: int,
    ) -> SkillTemplate: ...

    def quarantine_template(self, template_id: str, reason: str) -> SkillTemplate: ...

    def invalidate_template(self, template_id: str, reason: str) -> SkillTemplate: ...

    def expire_templates(self, *, now: datetime | None = None) -> list[str]: ...

    def compare_and_set_template_version(
        self,
        template_id: str,
        *,
        expected_template_version: int,
        new_status: SkillTemplateStatus,
    ) -> bool: ...

    def list_templates(self) -> list[SkillTemplate]: ...

    def record_audit_event(
        self, template_id: str, event_type: str, details: dict[str, object] | None = None
    ) -> None: ...

    def close(self) -> None: ...


def _utc_now() -> datetime:
    return datetime.now(UTC)


class InMemorySkillCacheRepository:
    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or _utc_now
        self._lock = threading.RLock()
        self._templates: dict[str, SkillTemplate] = {}
        self._template_hashes: dict[str, str] = {}
        self._records: dict[str, SkillExecutionRecord] = {}
        self._record_hashes: dict[str, str] = {}
        self._records_by_template: dict[str, list[str]] = {}
        self._audit: list[dict[str, object]] = []

    def save_template(self, template: SkillTemplate) -> SkillTemplate:
        with self._lock:
            h = stable_payload_hash(template)
            existing = self._templates.get(template.template_id)
            if existing is not None:
                _same_or_conflict(
                    "SkillTemplate",
                    template.template_id,
                    self._template_hashes[template.template_id],
                    h,
                )
                return existing.model_copy(deep=True)
            saved = template.model_copy(deep=True)
            self._templates[saved.template_id] = saved
            self._template_hashes[saved.template_id] = h
            self.record_audit_event(
                saved.template_id, "TEMPLATE_SAVED", {"status": saved.status.value}
            )
            return saved.model_copy(deep=True)

    def get_template(self, template_id: str) -> SkillTemplate | None:
        with self._lock:
            template = self._templates.get(template_id)
            return None if template is None else template.model_copy(deep=True)

    def lookup_templates(self, key: SkillCacheKey) -> SkillCacheLookupResult:
        with self._lock:
            now = self._clock()
            active = [
                template
                for template in self._templates.values()
                if template.status == SkillTemplateStatus.TRUSTED and template.expires_at > now
            ]
            exact = [template for template in active if template.cache_key == key]
            if exact:
                return SkillCacheLookupResult(
                    match_type="exact_match",
                    templates=[template.model_copy(deep=True) for template in exact],
                )
            reason_codes = _mismatch_reasons(list(self._templates.values()), key)
            compatible = [
                template for template in active if _compatible_key(template.cache_key, key)
            ]
            if compatible:
                return SkillCacheLookupResult(
                    match_type="compatible_match",
                    templates=[template.model_copy(deep=True) for template in compatible],
                    reason_codes=["calibration_compatible"],
                )
            return SkillCacheLookupResult(
                match_type="no_match",
                templates=[],
                reason_codes=reason_codes or ["no_trusted_template"],
            )

    def save_execution_record(self, record: SkillExecutionRecord) -> SkillExecutionRecord:
        with self._lock:
            h = stable_payload_hash(record)
            existing = self._records.get(record.execution_id)
            if existing is not None:
                _same_or_conflict(
                    "SkillExecutionRecord",
                    record.execution_id,
                    self._record_hashes[record.execution_id],
                    h,
                )
                return existing.model_copy(deep=True)
            saved = record.model_copy(deep=True)
            self._records[saved.execution_id] = saved
            self._record_hashes[saved.execution_id] = h
            self._records_by_template.setdefault(saved.template_id, []).append(saved.execution_id)
            if not saved.success and saved.safety_decision in {
                SafetyDecision.REJECT,
                SafetyDecision.EMERGENCY_STOP,
                SafetyDecision.PAUSE,
            }:
                self._set_status(saved.template_id, SkillTemplateStatus.QUARANTINED, "safety")
            return saved.model_copy(deep=True)

    def get_statistics(self, template_id: str) -> SkillStatistics:
        with self._lock:
            return _statistics(
                [
                    self._records[execution_id]
                    for execution_id in self._records_by_template.get(template_id, [])
                    if execution_id in self._records
                ]
            )

    def promote_template(
        self,
        template_id: str,
        *,
        policy: SkillCachePromotionPolicy,
        expected_template_version: int,
    ) -> SkillTemplate:
        with self._lock:
            template = self._require_template(template_id)
            if template.template_version != expected_template_version:
                raise VersionConflictError("template version conflict")
            stats = self.get_statistics(template_id)
            if (
                template.status != SkillTemplateStatus.CANDIDATE
                or stats.successful_executions < policy.min_successes
                or stats.recent_success_rate < policy.min_recent_success_rate
                or stats.safety_rejection_count > 0
                or stats.consecutive_failures > 0
            ):
                return template.model_copy(deep=True)
            return self._set_status(
                template_id, SkillTemplateStatus.TRUSTED, "promotion_policy_satisfied"
            )

    def quarantine_template(self, template_id: str, reason: str) -> SkillTemplate:
        with self._lock:
            return self._set_status(template_id, SkillTemplateStatus.QUARANTINED, reason)

    def invalidate_template(self, template_id: str, reason: str) -> SkillTemplate:
        with self._lock:
            return self._set_status(template_id, SkillTemplateStatus.INVALIDATED, reason)

    def expire_templates(self, *, now: datetime | None = None) -> list[str]:
        checked_at = now or self._clock()
        expired: list[str] = []
        with self._lock:
            for template in list(self._templates.values()):
                if template.expires_at <= checked_at and template.status not in {
                    SkillTemplateStatus.INVALIDATED,
                    SkillTemplateStatus.EXPIRED,
                }:
                    self._set_status(
                        template.template_id, SkillTemplateStatus.EXPIRED, "ttl_expired"
                    )
                    expired.append(template.template_id)
        return expired

    def compare_and_set_template_version(
        self,
        template_id: str,
        *,
        expected_template_version: int,
        new_status: SkillTemplateStatus,
    ) -> bool:
        with self._lock:
            template = self._templates.get(template_id)
            if template is None or template.template_version != expected_template_version:
                return False
            self._set_status(template_id, new_status, "cas_update")
            return True

    def list_templates(self) -> list[SkillTemplate]:
        with self._lock:
            return [template.model_copy(deep=True) for template in self._templates.values()]

    def record_audit_event(
        self, template_id: str, event_type: str, details: dict[str, object] | None = None
    ) -> None:
        self._audit.append(
            {
                "template_id": template_id,
                "event_type": event_type,
                "details": dict(details or {}),
                "created_at": self._clock().isoformat(),
            }
        )

    def close(self) -> None:
        return None

    def _require_template(self, template_id: str) -> SkillTemplate:
        template = self._templates.get(template_id)
        if template is None:
            raise KeyError(template_id)
        return template

    def _set_status(
        self, template_id: str, status: SkillTemplateStatus, reason: str
    ) -> SkillTemplate:
        template = self._require_template(template_id)
        updated = template.model_copy(
            update={
                "status": status,
                "template_version": template.template_version + 1,
                "updated_at": self._clock(),
            },
            deep=True,
        )
        self._templates[template_id] = updated
        self._template_hashes[template_id] = stable_payload_hash(updated)
        self.record_audit_event(template_id, f"TEMPLATE_{status.value}", {"reason": reason})
        return updated.model_copy(deep=True)


class SQLiteSkillCacheRepository:
    def __init__(self, path: str | Path, *, clock: Callable[[], datetime] | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock or _utc_now
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_schema()
        self._memory = InMemorySkillCacheRepository(clock=self._clock)
        self._load()

    def save_template(self, template: SkillTemplate) -> SkillTemplate:
        saved = self._memory.save_template(template)
        self._upsert_template(saved)
        return saved

    def get_template(self, template_id: str) -> SkillTemplate | None:
        return self._memory.get_template(template_id)

    def lookup_templates(self, key: SkillCacheKey) -> SkillCacheLookupResult:
        return self._memory.lookup_templates(key)

    def save_execution_record(self, record: SkillExecutionRecord) -> SkillExecutionRecord:
        saved = self._memory.save_execution_record(record)
        h = stable_payload_hash(saved)
        row = self._conn.execute(
            "SELECT payload_hash FROM skill_execution_records WHERE execution_id = ?",
            (saved.execution_id,),
        ).fetchone()
        if row is not None:
            _same_or_conflict("SkillExecutionRecord", saved.execution_id, row["payload_hash"], h)
            return saved
        self._conn.execute(
            """
            INSERT INTO skill_execution_records (
                execution_id, template_id, payload_json, payload_hash, executed_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                saved.execution_id,
                saved.template_id,
                saved.model_dump_json(),
                h,
                saved.executed_at.isoformat(),
            ),
        )
        self._conn.commit()
        self._upsert_template(self._memory.get_template(saved.template_id))
        return saved

    def get_statistics(self, template_id: str) -> SkillStatistics:
        return self._memory.get_statistics(template_id)

    def promote_template(
        self,
        template_id: str,
        *,
        policy: SkillCachePromotionPolicy,
        expected_template_version: int,
    ) -> SkillTemplate:
        saved = self._memory.promote_template(
            template_id, policy=policy, expected_template_version=expected_template_version
        )
        self._upsert_template(saved)
        return saved

    def quarantine_template(self, template_id: str, reason: str) -> SkillTemplate:
        saved = self._memory.quarantine_template(template_id, reason)
        self._upsert_template(saved)
        return saved

    def invalidate_template(self, template_id: str, reason: str) -> SkillTemplate:
        saved = self._memory.invalidate_template(template_id, reason)
        self._upsert_template(saved)
        return saved

    def expire_templates(self, *, now: datetime | None = None) -> list[str]:
        expired = self._memory.expire_templates(now=now)
        for template_id in expired:
            self._upsert_template(self._memory.get_template(template_id))
        return expired

    def compare_and_set_template_version(
        self,
        template_id: str,
        *,
        expected_template_version: int,
        new_status: SkillTemplateStatus,
    ) -> bool:
        ok = self._memory.compare_and_set_template_version(
            template_id,
            expected_template_version=expected_template_version,
            new_status=new_status,
        )
        if ok:
            self._upsert_template(self._memory.get_template(template_id))
        return ok

    def list_templates(self) -> list[SkillTemplate]:
        return self._memory.list_templates()

    def record_audit_event(
        self, template_id: str, event_type: str, details: dict[str, object] | None = None
    ) -> None:
        self._memory.record_audit_event(template_id, event_type, details)
        self._conn.execute(
            """
            INSERT INTO skill_cache_audit_events (template_id, event_type, details_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (template_id, event_type, _json_dump(details or {}), self._clock().isoformat()),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _create_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS skill_templates (
                template_id TEXT PRIMARY KEY,
                key_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                template_version INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_skill_templates_key ON skill_templates(key_hash);

            CREATE TABLE IF NOT EXISTS skill_execution_records (
                execution_id TEXT PRIMARY KEY,
                template_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                executed_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_skill_records_template
                ON skill_execution_records(template_id);

            CREATE TABLE IF NOT EXISTS skill_cache_audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                details_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def _load(self) -> None:
        for row in self._conn.execute(
            "SELECT payload_json FROM skill_templates ORDER BY updated_at"
        ):
            self._memory.save_template(SkillTemplate.model_validate_json(row["payload_json"]))
        for row in self._conn.execute(
            "SELECT payload_json FROM skill_execution_records ORDER BY executed_at"
        ):
            self._memory.save_execution_record(
                SkillExecutionRecord.model_validate_json(row["payload_json"])
            )

    def _upsert_template(self, template: SkillTemplate | None) -> None:
        if template is None:
            return
        h = stable_payload_hash(template)
        self._conn.execute(
            """
            INSERT INTO skill_templates (
                template_id, key_hash, status, template_version,
                payload_json, payload_hash, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(template_id) DO UPDATE SET
                key_hash = excluded.key_hash,
                status = excluded.status,
                template_version = excluded.template_version,
                payload_json = excluded.payload_json,
                payload_hash = excluded.payload_hash,
                updated_at = excluded.updated_at
            WHERE skill_templates.template_version <= excluded.template_version
            """,
            (
                template.template_id,
                template.cache_key.stable_hash(),
                template.status.value,
                template.template_version,
                template.model_dump_json(),
                h,
                template.updated_at.isoformat(),
            ),
        )
        self._conn.commit()


def _same_or_conflict(entity: str, key: str, existing_hash: str, new_hash: str) -> None:
    if existing_hash != new_hash:
        raise IdempotencyConflictError(f"{entity} idempotency conflict for key {key!r}")


def _statistics(records: list[SkillExecutionRecord]) -> SkillStatistics:
    if not records:
        return SkillStatistics()
    ordered = sorted(records, key=lambda record: record.executed_at)
    successes = [record for record in ordered if record.success]
    failures = [record for record in ordered if not record.success]
    safety_rejections = [
        record
        for record in ordered
        if record.safety_decision in {SafetyDecision.REJECT, SafetyDecision.EMERGENCY_STOP}
    ]
    durations = [record.duration_ms for record in ordered]
    recent = ordered[-10:]
    recent_success_rate = sum(1 for record in recent if record.success) / len(recent)
    consecutive_failures = 0
    for record in reversed(ordered):
        if record.success:
            break
        consecutive_failures += 1
    return SkillStatistics(
        total_executions=len(ordered),
        successful_executions=len(successes),
        failed_executions=len(failures),
        safety_rejection_count=len(safety_rejections),
        timeout_count=sum(1 for record in ordered if record.failure_reason == "timeout"),
        average_duration_ms=sum(durations) / len(durations),
        recent_success_rate=recent_success_rate,
        confidence_score=recent_success_rate
        * (1.0 if not safety_rejections else 0.0)
        * min(1.0, len(successes) / 3),
        consecutive_failures=consecutive_failures,
        last_success_at=successes[-1].executed_at if successes else None,
        last_failure_at=failures[-1].executed_at if failures else None,
    )


def _compatible_key(existing: SkillCacheKey, requested: SkillCacheKey) -> bool:
    return (
        existing.skill_name == requested.skill_name
        and existing.robot_model == requested.robot_model
        and existing.end_effector_type == requested.end_effector_type
        and existing.object_class == requested.object_class
        and existing.task_intent == requested.task_intent
        and existing.workspace_id == requested.workspace_id
        and existing.parameter_schema_version == requested.parameter_schema_version
        and existing.robot_capability_hash == requested.robot_capability_hash
        and existing.safety_policy_hash == requested.safety_policy_hash
    )


def _mismatch_reasons(templates: list[SkillTemplate], key: SkillCacheKey) -> list[str]:
    reasons: set[str] = set()
    for template in templates:
        other = template.cache_key
        for field in (
            "skill_name",
            "robot_model",
            "end_effector_type",
            "object_class",
            "task_intent",
            "workspace_id",
            "parameter_schema_version",
            "robot_capability_hash",
            "safety_policy_hash",
            "calibration_version",
        ):
            if getattr(other, field) != getattr(key, field):
                reasons.add(f"{field}_mismatch")
    return sorted(reasons)


def _json_dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, default=str)
