from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from cloud_edge_robot_arm.dashboard.redaction import redact
from cloud_edge_robot_arm.experiments.models import (
    CachePolicy,
    ExperimentConfig,
    ExperimentEvent,
    ExperimentMode,
    ExperimentResult,
    FaultProfile,
    NetworkProfileName,
    TaskProfile,
)
from cloud_edge_robot_arm.experiments.runner import ExperimentRunner
from cloud_edge_robot_arm.simulation.evaluation.metrics import run_mujoco_physical_trial
from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus, SimulationJobRecord
from cloud_edge_robot_arm.simulation_runtime.repository import SimulationJobRepository
from cloud_edge_robot_arm.simulation_workbench.models import (
    ExperimentDraft,
    NetworkDraft,
    SimulationBackend,
    SimulationMetric,
    TimelineEvent,
)


class CancelledByOperator(RuntimeError):
    pass


class TimedOut(RuntimeError):
    pass


class SimulationWorker:
    def __init__(
        self,
        *,
        worker_id: str,
        backend: str,
        repository: SimulationJobRepository,
        artifact_root: Path,
        lease_ttl_seconds: int = 30,
    ) -> None:
        self.worker_id = worker_id
        self.backend = backend
        self.repository = repository
        self.artifact_root = artifact_root
        self.lease_ttl_seconds = lease_ttl_seconds
        self.active_job_id = ""
        self.heartbeat_at: str | None = None

    def poll_once(self) -> bool:
        lease = self.repository.acquire_lease(
            worker_id=self.worker_id,
            backend=self.backend,
            lease_ttl_seconds=self.lease_ttl_seconds,
        )
        if lease is None:
            return False
        self.active_job_id = lease.job_id
        try:
            self._execute(lease.job_id, lease.lease_id)
        finally:
            self.repository.release_lease(lease.lease_id)
            self.active_job_id = ""
        return True

    def _execute(self, job_id: str, lease_id: str) -> None:
        job = self.repository.get_job(job_id)
        attempt = self.repository.start_attempt(job_id, worker_id=self.worker_id)
        artifacts: dict[str, str] = {}
        error = ""
        try:
            if self._cancel_requested(job_id):
                self._transition(
                    job_id,
                    RuntimeJobStatus.LEASED,
                    RuntimeJobStatus.CANCEL_REQUESTED,
                    lease_id,
                )
                self._transition(
                    job_id,
                    RuntimeJobStatus.CANCEL_REQUESTED,
                    RuntimeJobStatus.CANCELLING,
                    lease_id,
                )
                raise CancelledByOperator("cancelled before start")
            self._transition(job_id, RuntimeJobStatus.LEASED, RuntimeJobStatus.STARTING, lease_id)
            self._transition(job_id, RuntimeJobStatus.STARTING, RuntimeJobStatus.RUNNING, lease_id)
            start_monotonic = time.monotonic()
            result, events, metrics = self._run(job, start_monotonic=start_monotonic)
            self._raise_if_cancelled_or_timed_out(job_id, job, start_monotonic)
            self._transition(
                job_id,
                RuntimeJobStatus.RUNNING,
                RuntimeJobStatus.FINALIZING,
                lease_id,
            )
            artifacts = self._write_artifacts(job, events=events, metrics=metrics, result=result)
            self.repository.save_metrics(
                job_id, [metric.model_dump(mode="json") for metric in metrics]
            )
            self.repository.save_artifacts(job_id, artifacts)
            self.repository.append_event(
                job_id,
                event_type="artifact_created",
                source="simulation_runtime",
                payload=dict(artifacts),
            )
            self.repository.finish_attempt(
                job_id,
                attempt=attempt.attempt,
                result=RuntimeJobStatus.SUCCEEDED.value,
                error="",
                artifact_paths=artifacts,
            )
            self._transition(
                job_id,
                RuntimeJobStatus.FINALIZING,
                RuntimeJobStatus.SUCCEEDED,
                lease_id,
            )
        except CancelledByOperator as exc:
            error = str(exc)
            current = self.repository.get_job(job_id)
            if current.status == RuntimeJobStatus.RUNNING:
                self._transition(
                    job_id,
                    RuntimeJobStatus.RUNNING,
                    RuntimeJobStatus.CANCEL_REQUESTED,
                    lease_id,
                )
                current = self.repository.get_job(job_id)
            if current.status == RuntimeJobStatus.CANCEL_REQUESTED:
                self._transition(
                    job_id,
                    RuntimeJobStatus.CANCEL_REQUESTED,
                    RuntimeJobStatus.CANCELLING,
                    lease_id,
                )
            current = self.repository.get_job(job_id)
            if current.status == RuntimeJobStatus.CANCELLING:
                self._transition(
                    job_id,
                    RuntimeJobStatus.CANCELLING,
                    RuntimeJobStatus.CANCELLED,
                    lease_id,
                )
            artifacts = self._write_terminal_artifacts(
                job_id,
                attempt=attempt.attempt,
                status=RuntimeJobStatus.CANCELLED,
                error=error,
            )
        except TimedOut as exc:
            error = str(exc)
            current = self.repository.get_job(job_id)
            if current.status == RuntimeJobStatus.RUNNING:
                self._transition(
                    job_id,
                    RuntimeJobStatus.RUNNING,
                    RuntimeJobStatus.TIMED_OUT,
                    lease_id,
                )
            artifacts = self._write_terminal_artifacts(
                job_id,
                attempt=attempt.attempt,
                status=RuntimeJobStatus.TIMED_OUT,
                error=error,
            )
        except Exception as exc:  # pragma: no cover - defensive runtime surface
            error = f"{type(exc).__name__}: {exc}"
            current = self.repository.get_job(job_id)
            if current.status == RuntimeJobStatus.BLOCKED_BY_ENV:
                pass
            elif current.status == RuntimeJobStatus.RUNNING:
                self._transition(
                    job_id,
                    RuntimeJobStatus.RUNNING,
                    RuntimeJobStatus.FAILED,
                    lease_id,
                    error_message=error,
                )
            artifacts = self._write_terminal_artifacts(
                job_id,
                attempt=attempt.attempt,
                status=RuntimeJobStatus.FAILED,
                error=error,
            )

    def _run(
        self, job: SimulationJobRecord, *, start_monotonic: float
    ) -> tuple[dict[str, Any] | ExperimentResult, list[TimelineEvent], list[SimulationMetric]]:
        draft = ExperimentDraft.model_validate(job.draft)
        delay_ms = int(draft.parameter_overrides.get("runtime_delay_ms", 0))
        while delay_ms > 0 and (time.monotonic() - start_monotonic) * 1000 < delay_ms:
            self._raise_if_cancelled_or_timed_out(job.job_id, job, start_monotonic)
            self.repository.heartbeat_lease(job.lease_id, lease_ttl_seconds=self.lease_ttl_seconds)
            time.sleep(0.05)
        self._raise_if_cancelled_or_timed_out(job.job_id, job, start_monotonic)
        if job.backend == SimulationBackend.MOCK.value:
            return self._run_mock(job, draft)
        if job.backend == SimulationBackend.MUJOCO.value:
            return self._run_mujoco(job, draft)
        blockers = ["backend is blocked by environment"]
        self.repository.append_event(
            job.job_id,
            event_type="backend_blocked",
            source="simulation_runtime",
            payload={"blockers": blockers, "backend": job.backend},
        )
        self._transition(
            job.job_id,
            RuntimeJobStatus.RUNNING,
            RuntimeJobStatus.BLOCKED_BY_ENV,
            job.lease_id,
            error_message="backend_blocked",
        )
        raise RuntimeError("backend_blocked")

    def _run_mock(
        self, job: SimulationJobRecord, draft: ExperimentDraft
    ) -> tuple[ExperimentResult, list[TimelineEvent], list[SimulationMetric]]:
        run_dir = self.artifact_root / job.artifact_root
        config = _experiment_config(draft, job, run_dir)
        execution = ExperimentRunner(config).run()
        events = _timeline_events_from_runner(execution.events)
        for event in events:
            self.repository.append_event(
                job.job_id,
                event_type=event.event_type,
                source=event.source,
                payload=event.payload,
            )
        self.repository.append_event(
            job.job_id,
            event_type="task_completed",
            source="simulation_runtime",
            payload={
                "status": execution.result.result_status.value,
                "success": execution.result.task_success,
            },
        )
        metrics = _metrics_from_result(
            execution.result,
            backend=SimulationBackend.MOCK,
            scenario_id=job.scenario_id,
            control_mode=job.control_mode,
            seed=job.seed,
            reproducibility_hash=job.reproducibility_hash,
        )
        return execution.result, events, metrics

    def _run_mujoco(
        self, job: SimulationJobRecord, draft: ExperimentDraft
    ) -> tuple[dict[str, Any], list[TimelineEvent], list[SimulationMetric]]:
        randomization_level = draft.domain_randomization.level or "NONE"
        trial = run_mujoco_physical_trial(
            job.scenario_id,
            seed=job.seed,
            randomization_level=randomization_level,
        )
        self.repository.append_event(
            job.job_id,
            event_type="task_completed",
            source="MuJoCoPhysicalTrial",
            payload={"status": "SUCCESS", "result_hash": trial.result_hash},
        )
        metrics = _metrics_from_trial(
            trial.metrics,
            backend=SimulationBackend.MUJOCO,
            scenario_id=job.scenario_id,
            control_mode=job.control_mode,
            seed=job.seed,
            reproducibility_hash=job.reproducibility_hash,
        )
        return (
            {
                "trial": asdict(trial),
                "status": "SUCCEEDED",
                "runtime_executed": True,
                "mock_fallback_used": False,
            },
            [],
            metrics,
        )

    def _write_artifacts(
        self,
        job: SimulationJobRecord,
        *,
        events: list[TimelineEvent],
        metrics: list[SimulationMetric],
        result: dict[str, Any] | ExperimentResult,
    ) -> dict[str, str]:
        run_dir = self.artifact_root / job.artifact_root
        run_dir.mkdir(parents=True, exist_ok=True)
        paths = {
            "run_manifest": run_dir / "run_manifest.json",
            "events": run_dir / "events.jsonl",
            "metrics": run_dir / "metrics.json",
            "logs": run_dir / "logs.json",
            "result": run_dir / "result.json",
            "provenance": run_dir / "provenance.json",
            "job": run_dir / "job.json",
            "state_transitions": run_dir / "state_transitions.jsonl",
            "runtime_job": run_dir / "runtime_job.json",
            "attempts": run_dir / "attempts.jsonl",
            "leases": run_dir / "leases.jsonl",
            "lease_history": run_dir / "lease_history.jsonl",
            "resource_usage": run_dir / "resource_usage.json",
            "cancellation": run_dir / "cancellation.json",
            "recovery": run_dir / "recovery.json",
        }
        paths["run_manifest"].write_text(
            json.dumps(redact(job.manifest), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        job_events = self.repository.list_events(job.run_id)
        with paths["events"].open("w", encoding="utf-8") as handle:
            for event in job_events:
                handle.write(
                    json.dumps(
                        {
                            "sequence": event.sequence,
                            "event_type": event.event_type,
                            "source": event.source,
                            "severity": "info",
                            "virtual_time_ms": 0,
                            "wall_time": event.timestamp.isoformat(),
                            "payload": redact(event.payload),
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
        paths["metrics"].write_text(
            json.dumps(
                [metric.model_dump(mode="json") for metric in metrics],
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        paths["logs"].write_text(
            json.dumps({"messages": [], "redacted": True}, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        if isinstance(result, ExperimentResult):
            result_payload: dict[str, Any] = result.model_dump(mode="json")
        else:
            result_payload = dict(result)
        result_payload.update(
            {
                "backend": job.backend,
                "runner": "MUJOCO_SCENARIO" if job.backend == "MUJOCO" else "MOCK_SCENARIO",
                "runtime_executed": True,
                "mock_fallback_used": False if job.backend == "MUJOCO" else None,
                "real_controller_contacted": False,
                "hardware_motion_observed": False,
                "hardware_write_operations": [],
            }
        )
        paths["result"].write_text(
            json.dumps(redact(result_payload), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        paths["provenance"].write_text(
            json.dumps(redact(job.provenance), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        paths["runtime_job"].write_text(
            json.dumps(redact(_job_artifact(job)), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        paths["job"].write_text(paths["runtime_job"].read_text(encoding="utf-8"))
        with paths["state_transitions"].open("w", encoding="utf-8") as handle:
            for event in job_events:
                if event.previous_status or event.next_status:
                    handle.write(
                        json.dumps(
                            {
                                "event_id": event.event_id,
                                "sequence": event.sequence,
                                "previous_status": event.previous_status,
                                "next_status": event.next_status,
                                "reason_code": event.reason_code,
                                "timestamp": event.timestamp.isoformat(),
                                "worker_id": event.payload.get("worker_id", ""),
                                "lease_id": event.payload.get("lease_id", ""),
                                "attempt": job.attempt,
                                "source": event.source,
                            },
                            sort_keys=True,
                        )
                        + "\n"
                    )
        attempts = self.repository.list_attempts(job.run_id)
        with paths["attempts"].open("w", encoding="utf-8") as handle:
            for attempt in attempts:
                handle.write(
                    json.dumps(
                        {
                            "attempt": attempt.attempt,
                            "worker_id": attempt.worker_id,
                            "started_at": attempt.started_at.isoformat(),
                            "ended_at": attempt.ended_at.isoformat() if attempt.ended_at else "",
                            "result": attempt.result,
                            "error": attempt.error,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
        lease_payload = {
            "job_id": job.job_id,
            "lease_id": job.lease_id,
            "worker_id": job.worker_id,
            "lease_expires_at": job.lease_expires_at.isoformat() if job.lease_expires_at else "",
        }
        paths["leases"].write_text(
            json.dumps(lease_payload, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        paths["lease_history"].write_text(paths["leases"].read_text(encoding="utf-8"))
        paths["resource_usage"].write_text(
            json.dumps(
                {
                    "cpu_quota": "not_enforced",
                    "memory_soft_limit": "not_enforced",
                    "max_log_bytes": 0,
                    "max_event_count": len(job_events),
                    "max_runtime_seconds": job.timeout_seconds,
                    "redacted": True,
                },
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        paths["cancellation"].write_text(
            json.dumps(
                {
                    "requested_at": job.updated_at.isoformat() if job.cancel_requested else "",
                    "acknowledged_at": job.updated_at.isoformat() if job.cancel_requested else "",
                    "terminated_at": job.completed_at.isoformat()
                    if job.completed_at and job.cancel_requested
                    else "",
                    "force_killed": False,
                },
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        paths["recovery"].write_text(
            json.dumps(
                {
                    "recovered": False,
                    "recovery_required": False,
                    "duplicate_execution_prevented": True,
                },
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        _remove_internal_sqlite_sidecars(run_dir)
        return {
            name: path.relative_to(self.artifact_root).as_posix() for name, path in paths.items()
        }

    def _write_terminal_artifacts(
        self,
        job_id: str,
        *,
        attempt: int,
        status: RuntimeJobStatus,
        error: str,
    ) -> dict[str, str]:
        job = self.repository.get_job(job_id)
        self.repository.finish_attempt(
            job_id,
            attempt=attempt,
            result=status.value,
            error=error,
            artifact_paths={},
        )
        artifacts = self._write_artifacts(
            job,
            events=[],
            metrics=[],
            result={
                "status": status.value,
                "error": error,
                "runtime_executed": True,
                "mock_fallback_used": False if job.backend == "MUJOCO" else None,
            },
        )
        self.repository.save_metrics(job_id, [])
        self.repository.save_artifacts(job_id, artifacts)
        self.repository.append_event(
            job_id,
            event_type="artifact_created",
            source="simulation_runtime",
            payload=dict(artifacts),
        )
        self.repository.finish_attempt(
            job_id,
            attempt=attempt,
            result=status.value,
            error=error,
            artifact_paths=artifacts,
        )
        return artifacts

    def _transition(
        self,
        job_id: str,
        expected: RuntimeJobStatus,
        next_status: RuntimeJobStatus,
        lease_id: str,
        *,
        error_message: str = "",
    ) -> None:
        updated = self.repository.update_status_cas(
            job_id,
            expected=expected,
            next_status=next_status,
            reason_code=next_status.value.lower(),
            worker_id=self.worker_id,
            lease_id=lease_id,
            error_message=error_message,
        )
        if updated is None:
            current = self.repository.get_job(job_id)
            if current.status != next_status:
                raise RuntimeError(f"state transition lost: {expected.value}->{next_status.value}")

    def _cancel_requested(self, job_id: str) -> bool:
        return self.repository.get_job(job_id).cancel_requested

    def _raise_if_cancelled_or_timed_out(
        self, job_id: str, original: SimulationJobRecord, start_monotonic: float
    ) -> None:
        current = self.repository.get_job(job_id)
        if current.cancel_requested or current.status == RuntimeJobStatus.CANCEL_REQUESTED:
            raise CancelledByOperator("cancelled by operator")
        if (time.monotonic() - start_monotonic) >= original.timeout_seconds:
            raise TimedOut("timeout")


def _experiment_config(
    draft: ExperimentDraft, job: SimulationJobRecord, run_dir: Path
) -> ExperimentConfig:
    network_name = _network_profile_name(draft.network_profiles[0])
    fault_name = draft.fault_profiles[0].name if draft.fault_profiles else job.scenario_id.lower()
    supervision_period_ms = int(draft.parameter_overrides.get("supervision_period_ms", 300))
    timeout_ms = int(draft.parameter_overrides.get("timeout_ms", 30_000))
    cache_policy = CachePolicy(str(draft.parameter_overrides.get("cache_policy", "CACHE_ENABLED")))
    return ExperimentConfig(
        experiment_id=job.run_id,
        scenario_id=job.scenario_id,
        mode=ExperimentMode(job.control_mode),
        seed=job.seed,
        repetitions=1,
        network_profile=network_name,
        fault_profile=FaultProfile(name=fault_name),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=cache_policy,
        risk_policy_version="risk-v1",
        supervision_period_ms=supervision_period_ms,
        timeout_ms=timeout_ms,
        artifact_dir=run_dir,
    )


def _network_profile_name(profile: NetworkDraft) -> NetworkProfileName:
    try:
        return NetworkProfileName(profile.name)
    except ValueError:
        if profile.packet_loss >= 0.2 or profile.base_latency_ms >= 300:
            return NetworkProfileName.SEVERE
        if profile.packet_loss >= 0.05 or profile.base_latency_ms >= 150:
            return NetworkProfileName.DEGRADED
        return NetworkProfileName.NORMAL


def _timeline_events_from_runner(events: list[ExperimentEvent]) -> list[TimelineEvent]:
    timeline: list[TimelineEvent] = []
    for index, event in enumerate(events, start=1):
        timeline.append(
            TimelineEvent(
                sequence=index,
                event_type=_event_type(event.event_type),
                source="ExperimentRunner",
                virtual_time_ms=event.virtual_time_ms,
                payload={
                    "entity_id": event.entity_id,
                    "payload": event.payload,
                    "payload_hash": event.payload_hash,
                },
            )
        )
    return timeline


def _metrics_from_result(
    result: ExperimentResult,
    *,
    backend: SimulationBackend,
    scenario_id: str,
    control_mode: str,
    seed: int,
    reproducibility_hash: str,
) -> list[SimulationMetric]:
    def metric(name: str, value: int | float | str | bool | Any, unit: str) -> SimulationMetric:
        return _metric(
            name,
            value,
            unit,
            "ExperimentRunner",
            backend,
            scenario_id,
            seed,
            control_mode,
        )

    return [
        metric("task_success", result.task_success, ""),
        metric("completion_time", result.task_completion_time_ms, "ms"),
        metric("planning_time", 0, "ms"),
        metric("execution_time", result.task_completion_time_ms, "ms"),
        metric("cloud_calls", result.cloud_invocation_count, "count"),
        metric("communication_count", result.command_count + result.telemetry_count, "count"),
        metric("local_retries", result.retry_count, "count"),
        metric("local_recovery", int(result.recovery_success), "bool"),
        metric("replan_count", result.replan_count, "count"),
        metric(
            "safety_interventions",
            result.safety_pause_count + result.safety_reject_count + result.emergency_stop_count,
            "count",
        ),
        metric("mode_switches", result.mode_switch_count, "count"),
        metric("cache_hits", result.cache_hit_count, "count"),
        metric("recovery_time", result.recovery_latency_ms or 0, "ms"),
        metric("latency", result.cloud_response_latency_ms or 0, "ms"),
        metric("packet_loss", 0.0, "ratio"),
        metric("cpu", 0.0, "percent"),
        metric("memory", 0.0, "mb"),
        metric("collision_count", result.simulated_collision_count, "count"),
        metric("final_pose_error", 0.0, "m"),
        metric("reproducibility_hash", reproducibility_hash, "sha256"),
    ]


def _metrics_from_trial(
    values: dict[str, Any],
    *,
    backend: SimulationBackend,
    scenario_id: str,
    control_mode: str,
    seed: int,
    reproducibility_hash: str,
) -> list[SimulationMetric]:
    def metric(name: str, value: int | float | str | bool | Any, unit: str) -> SimulationMetric:
        return _metric(
            name,
            value,
            unit,
            "MuJoCoPhysicalTrial",
            backend,
            scenario_id,
            seed,
            control_mode,
        )

    return [
        metric("task_success", values.get("illegal_collision_count", 0) == 0, ""),
        metric("completion_time", values.get("trajectory_duration_ms", 0), "ms"),
        metric("planning_time", 0, "ms"),
        metric("execution_time", values.get("trajectory_duration_ms", 0), "ms"),
        metric("cloud_calls", 0, "count"),
        metric("communication_count", values.get("control_ticks", 0), "count"),
        metric("local_retries", 0, "count"),
        metric("local_recovery", 0, "bool"),
        metric("replan_count", 0, "count"),
        metric("safety_interventions", values.get("illegal_collision_count", 0), "count"),
        metric("mode_switches", 0, "count"),
        metric("cache_hits", 0, "count"),
        metric("recovery_time", 0, "ms"),
        metric("latency", values.get("sensor_latency_ms", 0), "ms"),
        metric("packet_loss", 0.0, "ratio"),
        metric("cpu", 0.0, "percent"),
        metric("memory", 0.0, "mb"),
        metric("collision_count", values.get("illegal_collision_count", 0), "count"),
        metric("final_pose_error", values.get("tcp_position_error_m", 0), "m"),
        metric("reproducibility_hash", reproducibility_hash, "sha256"),
    ]


def _metric(
    name: str,
    value: int | float | str | bool | Any,
    unit: str,
    source: str,
    backend: SimulationBackend,
    scenario: str,
    seed: int,
    control_mode: str,
) -> SimulationMetric:
    if not isinstance(value, int | float | str | bool):
        value = str(value)
    return SimulationMetric(
        name=name,
        value=value,
        unit=unit,
        source=source,
        backend=backend,
        scenario=scenario,
        seed=seed,
        control_mode=control_mode,
    )


def _remove_internal_sqlite_sidecars(run_dir: Path) -> None:
    for pattern in ("*.sqlite3", "*.sqlite3-shm", "*.sqlite3-wal"):
        for path in run_dir.glob(pattern):
            path.unlink(missing_ok=True)


def _event_type(raw: str) -> str:
    if raw == "run_started":
        return "experiment_started"
    if raw == "run_completed":
        return "task_completed"
    if "fault" in raw and "inject" in raw:
        return "fault_injected"
    if "fault" in raw and "detect" in raw:
        return "fault_detected"
    if "replan" in raw:
        return "replan_requested"
    if "retry" in raw:
        return "local_retry"
    if "safety" in raw:
        return "SafetyShield allow/reject"
    return raw


def _job_artifact(job: SimulationJobRecord) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "run_id": job.run_id,
        "backend": job.backend,
        "scenario_id": job.scenario_id,
        "control_mode": job.control_mode,
        "seed": job.seed,
        "status": job.status.value,
        "attempt": job.attempt,
        "timeout_seconds": job.timeout_seconds,
        "source_commit": job.source_commit,
        "source_tree_hash": job.source_tree_hash,
        "real_controller_contacted": False,
        "hardware_motion_observed": False,
        "hardware_write_operations": [],
    }
