"""Phase 11.1 仿真运行时 validation adapter。

F20 通过真实 SQLite repository、lease、worker、attempt、event、metric 和
terminal artifact 路径生成证据；不再用 Phase8 runner 投影 restart/lease 语义。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import time
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cloud_edge_robot_arm.experiments.models import ExperimentResult
from cloud_edge_robot_arm.experiments.reproducibility import stable_hash
from cloud_edge_robot_arm.experiments.runner import stable_run_id
from cloud_edge_robot_arm.final_evaluation.adapters.base import (
    Phase12AdapterResult,
    Phase12RunContext,
    sha256_payload,
    write_source_artifact,
)
from cloud_edge_robot_arm.final_evaluation.models import (
    BlockerStage,
    EnvironmentStatus,
    ExecutionSource,
    MetricProvenance,
    MetricSource,
    Phase12RunStatus,
)
from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus, SimulationJobLease
from cloud_edge_robot_arm.simulation_runtime.recovery import ArtifactRecoveryService
from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository
from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker


class Phase11RuntimeAdapter:
    runner_kind = "PHASE11_SIMULATION_RUNTIME"

    def capability(self) -> dict[str, Any]:
        return {
            "runner_kind": self.runner_kind,
            "actual_runner": "SimulationWorker + SQLiteSimulationJobRepository",
        }

    def validate_environment(self, context: Phase12RunContext) -> EnvironmentStatus:
        return EnvironmentStatus.READY

    def run(self, context: Phase12RunContext) -> Phase12AdapterResult:
        evidence_root = context.output_root / "source_evidence" / context.run_id / "phase11_runtime"
        if evidence_root.exists():
            shutil.rmtree(evidence_root)
        evidence_root.mkdir(parents=True, exist_ok=True)
        database_path = evidence_root / "runtime.sqlite3"
        artifact_root = evidence_root / "artifacts"
        repo = SQLiteSimulationJobRepository(database_path, artifact_root=artifact_root)

        main = _run_completed_job(repo, context, artifact_root)
        recovery = _run_recovery_job(repo, context, artifact_root)
        duplicate = _run_duplicate_competition_job(repo, context, artifact_root)
        outcome = _runtime_outcome(main, recovery, duplicate)
        sqlite_summary = _sqlite_summary(database_path, output_root=context.output_root)
        runtime_receipt = {
            "runner": self.runner_kind,
            "run_id": context.run_id,
            "main_job": main,
            "recovery_evidence": recovery,
            "duplicate_competition_evidence": duplicate,
            "worker_lease_evidence": {
                "lease_count": main["lease_count"],
                "heartbeat_observed": main["heartbeat_observed"],
                "released_lease_count": main["released_lease_count"],
            },
            "sqlite_evidence": sqlite_summary,
            "artifact_atomicity": {
                "terminal_artifacts_present": main["terminal_artifacts_present"],
                "evidence_consistency_present": main["evidence_consistency_present"],
                "evidence_consistency_hash": main["evidence_consistency_hash"],
            },
            "real_controller_contacted": False,
            "hardware_motion_observed": False,
            "hardware_write_operations": [],
            "runtime_outcome": outcome,
            "research_qualification": {
                "authoritative_for_thesis": False,
                "reason": "UNQUALIFIED_TIMING_AND_QUALITY_METRICS",
                "detail": "Historical event-count durations and quality constants "
                "lack qualified measurements. "
                "NOT_AVAILABLE zero/false values are schema placeholders, not measured results. "
                "Native software completion does not confer research or hardware acceptance.",
            },
        }
        runtime_receipt["runtime_receipt_hash"] = sha256_payload(runtime_receipt)
        rel, digest = write_source_artifact(
            context, "phase11_runtime_actual_run.json", runtime_receipt
        )
        metrics = _metrics_from_runtime(main, recovery, duplicate, digest)
        return Phase12AdapterResult(
            status=outcome["status"],
            task_success=outcome["task_success"],
            metrics=metrics,
            events=[
                {"event_type": "phase11_runtime_completed", "job_id": main["job_id"]},
                {"event_type": "phase11_runtime_recovery_completed"},
                {"event_type": "phase11_duplicate_competition_completed"},
            ]
            if outcome["runtime_completed"]
            else [
                {
                    "event_type": "phase11_runtime_incomplete",
                    "status": outcome["status"],
                    "failure_type": outcome["failure_type"],
                },
            ],
            execution_source=ExecutionSource.PHASE11_RUNTIME_ACTUAL,
            actual_runner_invoked=outcome["runtime_invoked"],
            adapter_attempted=True,
            environment_check_completed=True,
            runtime_invoked=outcome["runtime_invoked"],
            runtime_completed=outcome["runtime_completed"],
            authoritative_for_thesis=False,
            blocker_stage=outcome["blocker_stage"],
            source_artifact_path=rel,
            source_artifact_hash=digest,
            source_verifier=self.runner_kind,
            environment_status=outcome["environment_status"],
            metric_provenance=_metric_provenance(rel),
            failure_type=outcome["failure_type"],
        )

    def collect_evidence(self, context: Phase12RunContext) -> dict[str, Any]:
        return {"runner_kind": self.runner_kind}

    def cancel(self, run_id: str) -> None:
        return None

    def result_source(self) -> ExecutionSource:
        return ExecutionSource.PHASE11_RUNTIME_ACTUAL


def _run_completed_job(
    repo: SQLiteSimulationJobRepository, context: Phase12RunContext, artifact_root: Path
) -> dict[str, Any]:
    job = repo.create_job(
        run_id=f"{context.run_id}-runtime",
        batch_id="phase12-f20",
        backend="MOCK",
        scenario_id=context.scenario_id,
        control_mode=context.control_mode,
        seed=context.seed,
        manifest_id=f"manifest-{context.run_id}",
        reproducibility_hash=stable_hash({"run_id": context.run_id, "kind": "runtime"}),
        draft=_draft(context),
        manifest={"manifest_id": f"manifest-{context.run_id}", "schema_version": "phase12.2"},
        timeout_seconds=30,
        max_attempts=2,
        artifact_root=f"phase11_1/runtime/{context.run_id}-runtime",
        source_commit="phase12-validation",
        source_tree_hash="phase12-validation",
        provenance={"phase": "12.2", "runner": "SimulationWorker"},
    )
    repo.update_status_cas(
        job.job_id,
        expected=RuntimeJobStatus.CREATED,
        next_status=RuntimeJobStatus.QUEUED,
        reason_code="phase12_runtime_queued",
        worker_id="",
        lease_id="",
    )
    worker = SimulationWorker(
        worker_id=f"phase12-worker-{context.run_id}",
        backend="MOCK",
        repository=repo,
        artifact_root=artifact_root,
        lease_ttl_seconds=30,
    )
    consumed = worker.poll_once()
    terminal = repo.get_job(job.job_id)
    attempts = repo.list_attempts(job.run_id)
    leases = repo.list_leases(job.run_id)
    events = repo.list_events(job.run_id)
    artifacts = repo.get_artifacts(job.run_id)
    consistency_path = artifact_root / artifacts.get("evidence_consistency", "")
    return {
        "job_id": job.job_id,
        "run_id": job.run_id,
        "worker_consumed": consumed,
        "status": terminal.status.value,
        "attempt_count": len(attempts),
        "event_count": len(events),
        "metric_count": len(repo.get_metrics(job.run_id)),
        "lease_count": len(leases),
        "released_lease_count": sum(1 for lease in leases if lease.released_at is not None),
        "heartbeat_observed": any(lease.heartbeat_at is not None for lease in leases),
        "terminal_artifacts_present": all(
            (artifact_root / rel).exists() for rel in artifacts.values()
        ),
        "evidence_consistency_present": consistency_path.exists(),
        "evidence_consistency_hash": _path_hash(consistency_path)
        if consistency_path.exists()
        else "",
        "artifact_paths": artifacts,
        "execution_evidence": _collect_job_evidence(repo, job.run_id, artifact_root),
    }


def _run_recovery_job(
    repo: SQLiteSimulationJobRepository, context: Phase12RunContext, artifact_root: Path
) -> dict[str, Any]:
    job = repo.create_job(
        run_id=f"{context.run_id}-recovery",
        batch_id="phase12-f20",
        backend="MOCK",
        scenario_id=context.scenario_id,
        control_mode=context.control_mode,
        seed=context.seed,
        manifest_id=f"manifest-{context.run_id}-recovery",
        reproducibility_hash=stable_hash({"run_id": context.run_id, "kind": "recovery"}),
        draft=_draft(context, runtime_delay_ms=10),
        manifest={"manifest_id": f"manifest-{context.run_id}-recovery"},
        timeout_seconds=30,
        max_attempts=2,
        artifact_root=f"phase11_1/runtime/{context.run_id}-recovery",
        source_commit="phase12-validation",
        source_tree_hash="phase12-validation",
    )
    repo.update_status_cas(
        job.job_id,
        expected=RuntimeJobStatus.CREATED,
        next_status=RuntimeJobStatus.QUEUED,
        reason_code="phase12_recovery_queued",
        worker_id="",
        lease_id="",
    )
    lease = repo.acquire_lease(
        worker_id="phase12-worker-crashed", backend="MOCK", lease_ttl_seconds=1
    )
    if lease is None:
        raise RuntimeError("expected recovery lease")
    repo.start_attempt(job.job_id, worker_id="phase12-worker-crashed")
    repo.update_status_cas(
        job.job_id,
        expected=RuntimeJobStatus.LEASED,
        next_status=RuntimeJobStatus.STARTING,
        reason_code="phase12_recovery_starting",
        worker_id="phase12-worker-crashed",
        lease_id=lease.lease_id,
    )
    repo.update_status_cas(
        job.job_id,
        expected=RuntimeJobStatus.STARTING,
        next_status=RuntimeJobStatus.RUNNING,
        reason_code="phase12_recovery_running",
        worker_id="phase12-worker-crashed",
        lease_id=lease.lease_id,
    )
    time.sleep(1.05)
    interrupted = repo.expire_leases()
    crash_cleanup = _release_expired_simulated_crash_lease(
        repo, run_id=job.run_id, lease=lease, interrupted_jobs=interrupted
    )
    recovery = ArtifactRecoveryService(
        repository=repo, artifact_root=artifact_root, requeue_recoverable=True
    ).recover_interrupted_jobs()
    worker = SimulationWorker(
        worker_id="phase12-worker-recovered",
        backend="MOCK",
        repository=repo,
        artifact_root=artifact_root,
    )
    consumed = worker.poll_once()
    terminal = repo.get_job(job.job_id)
    transitions = [
        (event.previous_status, event.next_status)
        for event in repo.list_events(job.run_id)
        if event.previous_status or event.next_status
    ]
    return {
        "job_id": job.job_id,
        "run_id": job.run_id,
        "stale_lease_id": lease.lease_id,
        "simulated_crash_cleanup": crash_cleanup,
        "lease_expired": job.job_id in interrupted,
        "recovered_jobs": recovery.recovered_jobs,
        "worker_consumed_after_recovery": consumed,
        "final_status": terminal.status.value,
        "attempt_count": len(repo.list_attempts(job.run_id)),
        "transitions": transitions,
        "execution_evidence": _collect_job_evidence(repo, job.run_id, artifact_root),
    }


def _release_expired_simulated_crash_lease(
    repo: SQLiteSimulationJobRepository,
    *,
    run_id: str,
    lease: SimulationJobLease,
    interrupted_jobs: list[str],
) -> dict[str, Any]:
    """只收口本probe自建且已过期的模拟crashed owner，不替代生产恢复。"""
    with repo.publication_guard():
        job = repo.get_job_by_run_id(run_id)
        rows = [item for item in repo.list_leases(run_id) if item.lease_id == lease.lease_id]
        now = datetime.now(UTC)
        identity = (
            job.job_id,
            job.run_id,
            job.status,
            job.worker_id,
            job.lease_id,
            job.lease_expires_at,
        )
        expected = (
            lease.job_id,
            run_id,
            RuntimeJobStatus.INTERRUPTED,
            "phase12-worker-crashed",
            lease.lease_id,
            lease.expires_at,
        )
        if (
            lease.worker_id != "phase12-worker-crashed"
            or lease.released_at is not None
            or job.job_id not in interrupted_jobs
            or identity != expected
            or len(rows) != 1
        ):
            raise RuntimeError("simulated_crash_cleanup_owner_or_interruption_mismatch")
        current = rows[0]
        if (
            current.job_id != lease.job_id
            or current.worker_id != lease.worker_id
            or current.acquired_at != lease.acquired_at
            or current.expires_at != lease.expires_at
            or current.released_at is not None
            or current.expires_at > now
            or job.lease_expires_at is None
            or job.lease_expires_at > now
        ):
            raise RuntimeError("simulated_crash_cleanup_lease_not_exact_expired_unreleased")
        repo.release_lease(lease.lease_id)
        after = repo.get_job_by_run_id(run_id)
        released = [item for item in repo.list_leases(run_id) if item.lease_id == lease.lease_id]
        if (
            (
                after.job_id,
                after.run_id,
                after.status,
                after.worker_id,
                after.lease_id,
                after.lease_expires_at,
            )
            != identity
            or len(released) != 1
            or released[0].job_id != lease.job_id
            or released[0].worker_id != lease.worker_id
            or released[0].acquired_at != lease.acquired_at
            or released[0].expires_at != lease.expires_at
            or released[0].released_at is None
        ):
            raise RuntimeError("simulated_crash_cleanup_release_not_confirmed")
        return {
            "scope": "ADAPTER_SIMULATED_CRASH_ONLY",
            "job_id": job.job_id,
            "run_id": run_id,
            "lease_id": lease.lease_id,
            "worker_id": lease.worker_id,
            "acquired_at": lease.acquired_at.isoformat(),
            "expires_at": lease.expires_at.isoformat(),
            "expiry_confirmed_at": now.isoformat(),
            "released_at_before": None,
            "released_at_after": released[0].released_at.isoformat(),
            "identity_unchanged": True,
        }


def _run_duplicate_competition_job(
    repo: SQLiteSimulationJobRepository, context: Phase12RunContext, artifact_root: Path
) -> dict[str, Any]:
    job = repo.create_job(
        run_id=f"{context.run_id}-duplicate",
        batch_id="phase12-f20",
        backend="MOCK",
        scenario_id=context.scenario_id,
        control_mode=context.control_mode,
        seed=context.seed,
        manifest_id=f"manifest-{context.run_id}-duplicate",
        reproducibility_hash=stable_hash({"run_id": context.run_id, "kind": "duplicate"}),
        draft=_draft(context),
        manifest={"manifest_id": f"manifest-{context.run_id}-duplicate"},
        timeout_seconds=30,
        max_attempts=2,
        artifact_root=f"phase11_1/runtime/{context.run_id}-duplicate",
        source_commit="phase12-validation",
        source_tree_hash="phase12-validation",
    )
    repo.update_status_cas(
        job.job_id,
        expected=RuntimeJobStatus.CREATED,
        next_status=RuntimeJobStatus.QUEUED,
        reason_code="phase12_duplicate_queued",
        worker_id="",
        lease_id="",
    )
    invocation_count = 0

    class CountingWorker(SimulationWorker):
        def _run_mock(self, job: Any, draft: Any) -> Any:
            nonlocal invocation_count
            invocation_count += 1
            return super()._run_mock(job, draft)

    worker_a = CountingWorker(
        worker_id="phase12-worker-a",
        backend="MOCK",
        repository=repo,
        artifact_root=artifact_root,
    )
    worker_b = CountingWorker(
        worker_id="phase12-worker-b",
        backend="MOCK",
        repository=repo,
        artifact_root=artifact_root,
    )
    consumed_a = worker_a.poll_once()
    consumed_b = worker_b.poll_once()
    terminal = repo.get_job(job.job_id)
    attempts = repo.list_attempts(job.run_id)
    leases = repo.list_leases(job.run_id)
    lease_winner = leases[0].worker_id if leases else ""
    return {
        "job_id": job.job_id,
        "run_id": job.run_id,
        "competing_worker_ids": ["phase12-worker-a", "phase12-worker-b"],
        "lease_winner": lease_winner,
        "lease_loser": "phase12-worker-b"
        if lease_winner == "phase12-worker-a"
        else "phase12-worker-a",
        "worker_a_consumed": consumed_a,
        "worker_b_consumed": consumed_b,
        "runner_invocation_count": invocation_count,
        "attempt_count": len(attempts),
        "lease_count": len(leases),
        "final_status": terminal.status.value,
        "execution_evidence": _collect_job_evidence(repo, job.run_id, artifact_root),
    }


def _collect_job_evidence(
    repo: SQLiteSimulationJobRepository, run_id: str, artifact_root: Path
) -> dict[str, Any]:
    """只读联接当前job、attempt、原件与公开发布确认；包装器进入不算任务执行。"""
    job = repo.get_job_by_run_id(run_id)
    attempts = repo.list_attempts(run_id)
    leases = repo.list_leases(run_id)
    events = repo.list_events(run_id)
    paths = repo.get_artifacts(run_id)
    publication = repo.get_publication_summary(run_id, attempt=job.attempt)
    selected = [item for item in attempts if item.attempt == job.attempt]
    attempt_complete = (
        len(selected) == 1
        and selected[0].ended_at is not None
        and selected[0].job_id == job.job_id
        and selected[0].run_id == run_id
        and selected[0].result == job.status.value
    )
    lease_released = bool(leases) and all(item.released_at is not None for item in leases)
    mode = job.draft.get("input_mode", "RGBD")
    scope = job.draft.get("execution_scope", "VISUAL_PLANNING")
    publication_required = publication.confirmation_state != "NOT_APPLICABLE" or (
        mode == "RGBD" and scope == "VISION_CLOSED_LOOP"
    )
    evidence: dict[str, Any] = {
        "job_id": job.job_id,
        "run_id": run_id,
        "attempt": job.attempt,
        "status": job.status.value,
        "input_mode": mode,
        "execution_scope": scope,
        "evidence_valid": False,
        "evidence_errors": [],
        "artifacts_verified": False,
        "attempt_completed": attempt_complete,
        "lease_released": lease_released,
        "executor_invoked": False,
        "executor_returned": False,
        "task_success": False,
        "publication_required": publication_required,
        "publication_status": publication.confirmation_state,
        "publication_confirmed": publication.accepted,
        "publication": publication.to_payload(),
        "artifact_hashes": {},
        "failure_type": job.error_message or job.error_code,
    }
    errors = evidence["evidence_errors"]
    if not attempt_complete:
        errors.append("current_attempt_not_complete_or_mismatched")
    if not lease_released:
        errors.append("missing_or_unreleased_lease")
    if publication_required and not publication.accepted:
        errors.append("terminal_publication_not_confirmed")
    required = {"result", "runtime_job", "attempts", "metrics", "events", "evidence_consistency"}
    if not paths or not required.issubset(paths):
        errors.append("missing_required_artifact_paths")
        return evidence
    try:
        root = artifact_root.resolve(strict=True)
        job_root = root / job.artifact_root
        loaded = {}
        for name, relative in paths.items():
            relative_path = Path(relative)
            path = root / relative_path
            if (
                relative_path.is_absolute()
                or ".." in relative_path.parts
                or path.resolve(strict=True) != path
                or not path.is_relative_to(job_root)
                or not path.is_file()
                or path.is_symlink()
                or any(parent.is_symlink() for parent in path.parents)
            ):
                raise ValueError("artifact_path_not_exact_regular_current_job_file")
            data = path.read_bytes()
            evidence["artifact_hashes"][name] = hashlib.sha256(data).hexdigest()
            if name in required:
                loaded[name] = (
                    [json.loads(line) for line in data.splitlines()]
                    if name in {"attempts", "events"}
                    else json.loads(data)
                )
        consistency = loaded["evidence_consistency"]
        hashes = consistency["file_hashes"]
        if set(hashes) != set(paths) - {"evidence_consistency"} or any(
            hashes[name] != evidence["artifact_hashes"][name] for name in hashes
        ):
            errors.append("artifact_hash_manifest_mismatch")
        if (
            consistency["run_id"] != run_id
            or consistency["consistent"] is not True
            or any(
                consistency[name] != job.status.value
                for name in (
                    "expected_terminal_status",
                    "job_status",
                    "runtime_job_status",
                    "result_status",
                    "final_attempt_status",
                    "final_transition_status",
                )
            )
        ):
            errors.append("terminal_consistency_identity_or_status_mismatch")
        runtime_job = loaded["runtime_job"]
        if any(
            runtime_job[name] != expected
            for name, expected in (
                ("job_id", job.job_id),
                ("run_id", run_id),
                ("attempt", job.attempt),
                ("status", job.status.value),
                ("backend", job.backend),
                ("scenario_id", job.scenario_id),
                ("control_mode", job.control_mode),
                ("seed", job.seed),
            )
        ):
            errors.append("runtime_job_identity_mismatch")
        current_rows = [row for row in loaded["attempts"] if row["attempt"] == job.attempt]
        if (
            len(current_rows) != 1
            or not current_rows[0]["ended_at"]
            or current_rows[0]["result"] != job.status.value
            or current_rows[0]["worker_id"] != selected[0].worker_id
        ):
            errors.append("artifact_attempt_mismatch_or_incomplete")
        result = loaded["result"]
        if result["status"] != job.status.value or result["backend"] != job.backend:
            errors.append("result_status_or_backend_mismatch")
        evidence["failure_type"] = str(result.get("error") or evidence["failure_type"])
        evidence["artifacts_verified"] = not errors
        # 旧软件runner有独立experiment身份及真实task_completed事件；不采信runtime_executed包装标记。
        if mode == "LEGACY_PIPELINE" and job.status == RuntimeJobStatus.SUCCEEDED:
            experiment = ExperimentResult.model_validate(result)
            expected_run = stable_run_id(job.run_id, job.scenario_id, experiment.mode, job.seed)
            if (
                experiment.experiment_id != run_id
                or experiment.run_id != expected_run
                or experiment.scenario_id != job.scenario_id
                or experiment.mode.value != job.control_mode
                or experiment.seed != job.seed
                or result["runner"] != "MOCK_SCENARIO"
            ):
                errors.append("task_executor_identity_mismatch")
            completed = [
                event
                for event in events
                if event.event_type == "task_completed" and event.source == "simulation_runtime"
            ]
            if (
                len(completed) != 1
                or completed[0].payload.get("success") is not experiment.task_success
                or completed[0].payload.get("status") != experiment.result_status.value
            ):
                errors.append("task_executor_return_event_missing_or_mismatched")
            if not errors:
                evidence.update(
                    executor_invoked=True,
                    executor_returned=True,
                    task_success=experiment.task_success,
                )
        elif mode == "RGBD" and scope == "VISION_CLOSED_LOOP":
            entered = result.get("task_execution") == "EXECUTED"
            evidence.update(
                executor_invoked=entered,
                executor_returned=entered,
                task_success=entered and result.get("task_success") is True,
            )
    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
        errors.append(type(error).__name__ + ": " + str(error))
    evidence["artifacts_verified"] = not errors
    evidence["evidence_valid"] = not errors
    return evidence


def _runtime_outcome(
    main: dict[str, Any], recovery: dict[str, Any], duplicate: dict[str, Any]
) -> dict[str, Any]:
    """分别判定证据、执行完成和任务达成，三条probe均可否决成功。"""
    probes = {"main": main, "recovery": recovery, "duplicate": duplicate}
    facts = {name: item.get("execution_evidence", {}) for name, item in probes.items()}
    statuses = {
        "main": main["status"],
        "recovery": recovery["final_status"],
        "duplicate": duplicate["final_status"],
    }
    invalid = []
    reasons = []
    for name, evidence in facts.items():
        valid = (
            evidence.get("evidence_valid") is True
            and evidence.get("artifacts_verified") is True
            and evidence.get("attempt_completed") is True
            and evidence.get("lease_released") is True
            and evidence.get("status") == statuses[name]
            and (
                not evidence.get("publication_required")
                or evidence.get("publication_confirmed") is True
            )
        )
        if not valid:
            invalid.append(name)
            reasons.append(name + ": evidence_invalid " + str(evidence.get("evidence_errors", [])))
        if evidence.get("failure_type"):
            reasons.append(name + ": " + str(evidence["failure_type"]))
    blocked = "BLOCKED_BY_ENV" in statuses.values()
    timed_out = any(value in {"TIMED_OUT", "TIMEOUT"} for value in statuses.values())
    complete = (
        not invalid
        and not blocked
        and not timed_out
        and all(
            item.get("executor_returned") is True and item.get("executor_invoked") is True
            for item in facts.values()
        )
    )
    recovery_transitions = {tuple(pair) for pair in recovery.get("transitions", [])}
    recovery_proven = (
        recovery.get("lease_expired") is True
        and recovery["job_id"] in recovery.get("recovered_jobs", [])
        and {
            ("RUNNING", "INTERRUPTED"),
            ("INTERRUPTED", "RECOVERY_PENDING"),
            ("RECOVERY_PENDING", "QUEUED"),
        }.issubset(recovery_transitions)
    )
    duplicate_proven = (
        duplicate.get("runner_invocation_count") == 1
        and duplicate.get("attempt_count") == 1
        and bool(duplicate.get("lease_winner"))
        and bool(duplicate.get("lease_loser"))
        and duplicate["lease_winner"] != duplicate["lease_loser"]
    )
    task_success = (
        complete
        and recovery_proven
        and duplicate_proven
        and all(
            item.get("task_success") is True and statuses[name] == "SUCCEEDED"
            for name, item in facts.items()
        )
    )
    if invalid:
        status, blocker = Phase12RunStatus.FAILED, BlockerStage.FINALIZATION
    elif blocked:
        status, blocker = Phase12RunStatus.BLOCKED_BY_ENV, BlockerStage.RUNTIME
    elif timed_out:
        status, blocker = Phase12RunStatus.TIMEOUT, BlockerStage.RUNTIME
    elif not task_success:
        status, blocker = Phase12RunStatus.FAILED, BlockerStage.RUNTIME
        reasons.append("task_or_recovery_or_duplicate_obligations_not_proved")
    else:
        status, blocker = Phase12RunStatus.SUCCESS, BlockerStage.NONE
    return {
        "status": status,
        "task_success": task_success,
        "runtime_invoked": facts["main"].get("executor_invoked") is True,
        "runtime_completed": complete,
        "blocker_stage": blocker,
        "environment_status": EnvironmentStatus.BLOCKED_BY_ENV
        if blocked
        else EnvironmentStatus.READY,
        "failure_type": "; ".join(reasons) if status != Phase12RunStatus.SUCCESS else "",
        "probe_statuses": statuses,
        "invalid_probes": invalid,
        "recovery_obligations_proved": recovery_proven,
    }


def _draft(context: Phase12RunContext, *, runtime_delay_ms: int = 0) -> dict[str, Any]:
    return {
        "backend": "MOCK",
        "run_type": "SINGLE",
        "scenarios": [context.scenario_id],
        "control_modes": [context.control_mode],
        "seeds": [context.seed],
        "repetitions": 1,
        "network_profiles": [
            {
                "name": "NORMAL",
                "base_latency_ms": 40,
                "jitter_ms": 5,
                "packet_loss": 0.0,
                "bandwidth_kbps": 10000,
            }
        ],
        "fault_profiles": [{"name": context.scenario_id.lower(), "parameters": {}}],
        "parameter_overrides": {
            "cache_policy": "CACHE_ENABLED",
            "retry_budget": 2,
            "supervision_period_ms": 300,
            "timeout_ms": 30000,
            "runtime_delay_ms": runtime_delay_ms,
        },
        "domain_randomization": {"enabled": False, "level": "NONE"},
        "tags": ["phase12-2-validation"],
        "description": "phase12 runtime authenticity validation",
    }


def _sqlite_summary(database_path: Path, *, output_root: Path) -> dict[str, Any]:
    counts: dict[str, int] = {}
    with closing(sqlite3.connect(database_path)) as conn:
        with conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            for table in (
                "simulation_jobs",
                "simulation_job_events",
                "simulation_job_leases",
                "simulation_job_attempts",
                "simulation_metrics",
                "simulation_artifacts",
            ):
                row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                counts[table] = int(row[0]) if row else 0
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            # 中文说明：保留事务语义，显式关闭自有连接后再计算稳定文件hash。
            conn.execute("VACUUM")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return {
        "exists": database_path.exists(),
        "sha256": _path_hash(database_path),
        "tables": counts,
        "relative_path": str(database_path.relative_to(output_root)),
        "relative_name": database_path.name,
    }


def _metrics_from_runtime(
    main: dict[str, Any],
    recovery: dict[str, Any],
    duplicate: dict[str, Any],
    digest: str,
) -> dict[str, float | int | bool | str]:
    outcome = _runtime_outcome(main, recovery, duplicate)
    recovery_fact = recovery["execution_evidence"]
    recovery_success = (
        recovery_fact.get("evidence_valid") is True
        and recovery_fact.get("executor_returned") is True
        and recovery_fact.get("task_success") is True
        and recovery["final_status"] == "SUCCEEDED"
        and outcome["recovery_obligations_proved"]
    )
    return {
        "task_completion_rate": float(outcome["task_success"]),
        "total_completion_time_ms": 0.0,
        "cloud_planning_time_ms": 0.0,
        "edge_execution_time_ms": 0.0,
        "local_recovery_time_ms": 0.0,
        "replanning_time_ms": 0.0,
        "communication_wait_time_ms": 0.0,
        "cloud_invocation_count": 0,
        "communication_count": 0,
        "uploaded_bytes": 0,
        "downloaded_bytes": 0,
        "supervision_count": 0,
        "mode_switch_count": 0,
        "local_retry_count": max(0, int(recovery["attempt_count"]) - 1),
        "local_recovery_success_count": int(recovery_success),
        "replan_count": 0,
        "cloud_fallback_count": 0,
        "completed_without_cloud_after_start": False,
        "safety_intervention_count": 0,
        "rejected_action_count": 0,
        "stale_telemetry_rejection": 0,
        "workspace_rejection": 0,
        "collision_rejection": 0,
        "emergency_stop_event": 0,
        "unsafe_command_execution_count": 0,
        "restart_recovery_success": recovery_success,
        "duplicate_execution_count": max(0, int(duplicate["runner_invocation_count"]) - 1),
        "lease_recovery_count": int(outcome["recovery_obligations_proved"]),
        "artifact_consistency": all(
            probe["execution_evidence"].get("artifacts_verified") is True
            for probe in (main, recovery, duplicate)
        ),
        "event_loss_count": 0,
        "planner_success": False,
        "valid_contract_rate": 0.0,
        "repair_count": 0,
        "refusal_rate": 0.0,
        "response_latency_ms": 0.0,
        "result_hash": digest,
        "artifact_hash": digest,
    }


def _metric_provenance(source_artifact: str) -> dict[str, MetricProvenance]:
    event_metrics = {
        "task_completion_rate": ("runtime_outcome.task_success", "ratio"),
        "local_retry_count": ("recovery_evidence.attempt_count minus initial attempt", "count"),
        "local_recovery_success_count": (
            "recovery execution evidence and recovery obligations",
            "count",
        ),
        "restart_recovery_success": (
            "recovery execution evidence and recovery obligations",
            "bool",
        ),
        "duplicate_execution_count": (
            "duplicate_competition_evidence.runner_invocation_count minus one",
            "count",
        ),
        "lease_recovery_count": ("runtime_outcome.recovery_obligations_proved", "count"),
        "artifact_consistency": ("all three execution_evidence.artifacts_verified", "bool"),
    }
    provenance: dict[str, MetricProvenance] = {}
    for metric, (field, unit) in event_metrics.items():
        provenance[metric] = MetricProvenance(
            source=MetricSource.EVENT_DERIVED,
            source_field=field,
            source_artifact=source_artifact,
            unit=unit,
        )
    # 中文说明：未取得测量的字段保留schema占位，来源明确不可用于论文统计。
    for metric in (
        "total_completion_time_ms",
        "cloud_planning_time_ms",
        "edge_execution_time_ms",
        "local_recovery_time_ms",
        "replanning_time_ms",
        "communication_wait_time_ms",
        "cloud_invocation_count",
        "communication_count",
        "uploaded_bytes",
        "downloaded_bytes",
        "supervision_count",
        "mode_switch_count",
        "replan_count",
        "cloud_fallback_count",
        "completed_without_cloud_after_start",
        "safety_intervention_count",
        "rejected_action_count",
        "stale_telemetry_rejection",
        "workspace_rejection",
        "collision_rejection",
        "emergency_stop_event",
        "unsafe_command_execution_count",
        "event_loss_count",
        "planner_success",
        "valid_contract_rate",
        "repair_count",
        "refusal_rate",
        "response_latency_ms",
    ):
        provenance[metric] = MetricProvenance(
            source=MetricSource.NOT_AVAILABLE,
            source_field="unmeasured; zero/false schema placeholder",
            source_artifact=source_artifact,
            unit="ms" if metric.endswith("_ms") else "",
        )
    for metric in ("result_hash", "artifact_hash"):
        provenance[metric] = MetricProvenance(
            source=MetricSource.ADAPTER_DERIVED,
            source_field="sha256 of source receipt",
            source_artifact=source_artifact,
            unit="sha256",
        )
    return provenance


def _path_hash(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()
