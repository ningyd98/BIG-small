"""Dashboard evidence 索引。

索引器读取 artifact 元数据并输出脱敏后的证据目录，帮助前端区分 authoritative、
derived、configured default 和 unavailable 等来源。
"""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from cloud_edge_robot_arm.dashboard.models import (
    EvidenceDetailResponse,
    EvidenceIndexRecord,
    EvidenceStatus,
    HardwareClaim,
)
from cloud_edge_robot_arm.dashboard.redaction import redact

ALLOWED_EXTENSIONS = {".json", ".jsonl", ".md", ".txt", ".log"}


@dataclass
class EvidenceIndexError:
    path: str
    error: str


EvidenceSnapshot = tuple[list[EvidenceIndexRecord], list[EvidenceIndexError]]


class EvidenceIndex:
    def __init__(self, root: Path, *, max_bytes: int = 2_000_000) -> None:
        self.root = root
        self.max_bytes = max_bytes
        self._snapshot: EvidenceSnapshot = ([], [])
        self._refresh_lock = Lock()
        self._inflight: Future[EvidenceSnapshot] | None = None

    @property
    def errors(self) -> list[EvidenceIndexError]:
        return list(self._snapshot[1])

    def refresh(self) -> list[EvidenceIndexRecord]:
        return self.refresh_snapshot()[0]

    def refresh_snapshot(self) -> EvidenceSnapshot:
        """Share an in-flight scan and publish records/errors only when complete.

        Sequential calls still scan for new evidence; this is not a stale cache.
        """
        with self._refresh_lock:
            future = self._inflight
            owner = future is None
            if future is None:
                future = Future()
                self._inflight = future
        if owner:
            try:
                snapshot = self._scan()
            except BaseException as exc:
                with self._refresh_lock:
                    future.set_exception(exc)
                    self._inflight = None
                raise
            with self._refresh_lock:
                self._snapshot = snapshot
                future.set_result(snapshot)
                self._inflight = None
        records, errors = future.result()
        return list(records), list(errors)

    def _scan(self) -> EvidenceSnapshot:
        records: dict[str, EvidenceIndexRecord] = {}
        errors: list[EvidenceIndexError] = []
        if not self.root.exists():
            return [], []
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or path.suffix not in ALLOWED_EXTENSIONS:
                continue
            relative_path = path.relative_to(self.root).as_posix()
            try:
                resolved = path.resolve(strict=True)
                if self.root.resolve() not in resolved.parents and resolved != self.root.resolve():
                    continue
                if path.is_symlink() or path.stat().st_size > self.max_bytes:
                    continue
            except OSError:
                continue
            try:
                record = self._record_for(path, errors)
            except Exception as exc:  # pragma: no cover - defensive evidence path
                errors.append(EvidenceIndexError(path=relative_path, error=str(exc)))
                continue
            records[record.evidence_id] = record
        return list(records.values()), errors

    def resolve_user_path(self, relative_path: str) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("path traversal is not allowed")
        resolved = (self.root / candidate).resolve(strict=True)
        if self.root.resolve() not in resolved.parents:
            raise ValueError("path escapes artifact root")
        return resolved

    def get_detail(self, evidence_id: str) -> EvidenceDetailResponse:
        records = self.refresh()
        record = next((item for item in records if item.evidence_id == evidence_id), None)
        if record is None:
            raise FileNotFoundError(evidence_id)
        path = self.resolve_user_path(record.relative_path)
        if path.suffix in {".json", ".jsonl"}:
            content = _load_jsonish(path)
        else:
            content = path.read_text(encoding="utf-8", errors="replace")
        return EvidenceDetailResponse(record=record, content=redact(content))

    def _record_for(self, path: Path, errors: list[EvidenceIndexError]) -> EvidenceIndexRecord:
        relative_path = path.relative_to(self.root).as_posix()
        evidence_id = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:16]
        payload = _load_jsonish(path) if path.suffix in {".json", ".jsonl"} else {}
        if isinstance(payload, dict) and "parse_error" in payload:
            errors.append(EvidenceIndexError(relative_path, str(payload.get("parse_error", ""))))
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and "parse_error" in item:
                    errors.append(
                        EvidenceIndexError(relative_path, str(item.get("parse_error", "")))
                    )
                    break
        if isinstance(payload, list):
            payload = payload[0] if payload and isinstance(payload[0], dict) else {}
        payload = payload if isinstance(payload, dict) else {}
        raw_provenance = payload.get("provenance")
        provenance: dict[str, Any] = raw_provenance if isinstance(raw_provenance, dict) else {}
        status = _evidence_status(str(payload.get("status", "")))
        return EvidenceIndexRecord(
            evidence_id=evidence_id,
            phase=_phase_from_path(relative_path),
            evidence_type=path.suffix.lstrip(".") or "artifact",
            status=status,
            backend=str(payload.get("planner_backend") or payload.get("backend") or ""),
            hardware_claim=_hardware_claim(payload),
            generated_at=str(payload.get("generated_at") or provenance.get("generated_at") or ""),
            generated_from_commit=str(provenance.get("generated_from_commit", "")),
            source_tree_hash=str(provenance.get("source_tree_hash", "")),
            worktree_clean=provenance.get("worktree_clean")
            if isinstance(provenance.get("worktree_clean"), bool)
            else None,
            config_hash=str(provenance.get("config_hash", "")),
            environment_hash=str(provenance.get("environment_hash", "")),
            relative_path=relative_path,
            summary=str(payload.get("status", path.name)),
            blockers=[str(item) for item in payload.get("blockers", []) if isinstance(item, str)],
        )


def _load_jsonish(path: Path) -> dict[str, Any] | list[Any] | str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".jsonl":
        rows: list[Any] = []
        for line in text.splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    rows.append({"parse_error": str(exc), "raw_line": line})
        return rows
    try:
        loaded: dict[str, Any] | list[Any] | str = json.loads(text)
    except json.JSONDecodeError as exc:
        return {"parse_error": str(exc), "raw_text": text[:2048]}
    return loaded


def _evidence_status(status: str) -> EvidenceStatus:
    if status.endswith("ACCEPTED") or status in {"PASSED", "MOVEIT_DRY_RUN_VALIDATED"}:
        return EvidenceStatus.ACCEPTED
    if status in {"BLOCKED_BY_ENV", "MOVEIT_DRY_RUN_BLOCKED_BY_ENV"}:
        return EvidenceStatus.BLOCKED_BY_ENV
    if status in {"REJECTED", "FAILED", "INCOMPLETE"}:
        return EvidenceStatus.REJECTED
    if status == "DEVELOPMENT_EVIDENCE":
        return EvidenceStatus.DEVELOPMENT_EVIDENCE
    return EvidenceStatus.UNKNOWN


def _hardware_claim(payload: dict[str, Any]) -> HardwareClaim:
    raw_claim = str(payload.get("hardware_claim", ""))
    if raw_claim:
        try:
            return HardwareClaim(raw_claim)
        except ValueError:
            pass
    if payload.get("hardware_motion_observed") is True:
        return HardwareClaim.HARDWARE_MOTION
    if str(payload.get("status", "")).startswith("PHASE10_MOVEIT_DRY_RUN_ACCEPTED"):
        return HardwareClaim.PLANNING_ONLY
    if payload.get("moveit_runtime_used") is True:
        return HardwareClaim.PLANNING_ONLY
    if payload.get("real_robot_validation") == "NOT_STARTED":
        return HardwareClaim.PLANNING_ONLY
    return HardwareClaim.NONE


def _phase_from_path(path: str) -> str:
    parts = Path(path).parts
    return parts[0] if parts else "unknown"
