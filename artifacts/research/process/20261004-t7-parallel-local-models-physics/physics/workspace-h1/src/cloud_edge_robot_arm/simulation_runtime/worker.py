"""仿真 worker 执行器。

Worker 只消费 repository 中已租约保护的 job，并通过固定 runner 分支执行
Mock 或 MuJoCo。这里刻意不暴露 shell、脚本路径或真实机械臂写操作；所有输出
都落到相对 artifact 路径，供验收和重启恢复读取。
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal, cast

from cloud_edge_robot_arm.cloud.planning.adapter import PlannerAdapter
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
    """操作员取消请求被 worker 观察到时使用的内部异常。"""

    pass


class TimedOut(RuntimeError):
    """任务超过 job timeout 后使用的内部异常。"""

    pass


class SimulationWorker:
    """单 backend 的租约 worker。

    每次只领取一个 job，执行期间写 heartbeat/attempt/event/metric/artifact。
    取消和超时采用协作式检查，保证已有部分证据不会因为终止而被删除。
    """

    def __init__(
        self,
        *,
        worker_id: str,
        backend: str,
        repository: SimulationJobRepository,
        artifact_root: Path,
        lease_ttl_seconds: int = 30,
        planner_factory: Callable[[], PlannerAdapter] | None = None,
    ) -> None:
        self.worker_id = worker_id
        self.backend = backend
        self.repository = repository
        self.artifact_root = artifact_root
        self.lease_ttl_seconds = lease_ttl_seconds
        self.planner_factory = planner_factory
        self.active_job_id = ""
        self.heartbeat_at: str | None = None
        self._heartbeat_failed = threading.Event()

    def poll_once(self) -> bool:
        # acquire_lease 是跨进程/跨线程的唯一消费门；没有租约就不能执行 job。
        lease = self.repository.acquire_lease(
            worker_id=self.worker_id,
            backend=self.backend,
            lease_ttl_seconds=self.lease_ttl_seconds,
        )
        if lease is None:
            return False
        self.active_job_id = lease.job_id
        self._heartbeat_failed.clear()
        stop_heartbeat = threading.Event()

        def maintain_lease() -> None:
            from datetime import UTC, datetime

            while not stop_heartbeat.is_set():
                try:
                    self.repository.heartbeat_lease(
                        lease.lease_id, lease_ttl_seconds=self.lease_ttl_seconds
                    )
                    self.heartbeat_at = datetime.now(UTC).isoformat()
                except Exception:
                    self._heartbeat_failed.set()
                    return
                stop_heartbeat.wait(max(0.05, self.lease_ttl_seconds / 3))

        heartbeat = threading.Thread(target=maintain_lease, name="simulation-lease", daemon=True)
        heartbeat.start()
        try:
            self._execute(lease.job_id, lease.lease_id)
        finally:
            stop_heartbeat.set()
            heartbeat.join(timeout=1)
            self.repository.release_lease(lease.lease_id)
            self.active_job_id = ""
        return True

    def _execute(self, job_id: str, lease_id: str) -> None:
        with self.repository.publication_guard():
            job = self.repository.get_job(job_id)
            if job.lease_id != lease_id or job.worker_id != self.worker_id:
                self.repository.append_event(
                    job_id,
                    event_type="stale_worker_start_discarded",
                    source="simulation_runtime",
                    payload={"lease_id": lease_id, "worker_id": self.worker_id},
                )
                self.repository.release_lease(lease_id)
                return
            if job.status not in {RuntimeJobStatus.LEASED, RuntimeJobStatus.CANCEL_REQUESTED}:
                return
            if not self._owns_artifact_publication(job, lease_id):
                return
            attempt = self.repository.start_attempt(job_id, worker_id=self.worker_id)
        artifacts: dict[str, str] = {}
        error = ""
        publishing_success = False
        result: dict[str, Any] | ExperimentResult | None = None
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
            terminal = RuntimeJobStatus.SUCCEEDED
            if isinstance(result, dict) and result.get("job_type") == "DATASET_GENERATION":
                if result.get("dataset_status") == "BLOCKED":
                    terminal = RuntimeJobStatus.BLOCKED_BY_ENV
                elif result.get("job_completed") is not True:
                    terminal = RuntimeJobStatus.FAILED
            if isinstance(result, dict) and result.get("evaluation_scope") == "VISION_CLOSED_LOOP":
                if result.get("blocked_by_env"):
                    terminal = RuntimeJobStatus.BLOCKED_BY_ENV
                elif result.get("task_success") is not True:
                    terminal = RuntimeJobStatus.FAILED
            with self.repository.publication_guard():
                self._raise_if_cancelled_or_timed_out(job_id, job, start_monotonic)
                if self._active_job_cancelled(job):
                    raise RuntimeError("lease lost before evidence publication")
                if terminal == RuntimeJobStatus.BLOCKED_BY_ENV:
                    self._transition(job_id, RuntimeJobStatus.RUNNING, terminal, lease_id)
                else:
                    self._transition(
                        job_id,
                        RuntimeJobStatus.RUNNING,
                        RuntimeJobStatus.FINALIZING,
                        lease_id,
                    )
                artifacts = self._artifact_paths(job)
                self.repository.save_metrics(
                    job_id, [metric.model_dump(mode="json") for metric in metrics]
                )
                self.repository.finish_attempt(
                    job_id,
                    attempt=attempt.attempt,
                    result=terminal.value,
                    error="",
                    artifact_paths=artifacts,
                )
                self.repository.save_artifacts(job_id, artifacts)
                if terminal != RuntimeJobStatus.BLOCKED_BY_ENV:
                    self._transition(job_id, RuntimeJobStatus.FINALIZING, terminal, lease_id)
                publishing_success = terminal == RuntimeJobStatus.SUCCEEDED
                self.repository.append_event(
                    job_id,
                    event_type="artifact_created",
                    source="simulation_runtime",
                    payload=dict(artifacts),
                )
                self.repository.release_lease(lease_id)
                artifacts = self._write_artifacts(
                    self.repository.get_job(job_id),
                    events=events,
                    metrics=metrics,
                    result=result,
                    expected_terminal_status=terminal,
                )
                self.repository.save_artifacts(job_id, artifacts)
                publishing_success = False
        except Exception as exc:
            error = (
                str(exc)
                if isinstance(exc, (CancelledByOperator, TimedOut))
                else (f"{type(exc).__name__}: {exc}")
            )
            if (
                publishing_success
                and result is not None
                and self._recover_failed_publication(
                    job_id,
                    lease_id=lease_id,
                    attempt=attempt.attempt,
                    error=error,
                    result=result,
                )
            ):
                return
            preferred = (
                RuntimeJobStatus.CANCELLED
                if isinstance(exc, CancelledByOperator)
                else RuntimeJobStatus.TIMED_OUT
                if isinstance(exc, TimedOut)
                else RuntimeJobStatus.FAILED
            )
            failure_terminal = self._settle_failure_status(
                job_id,
                lease_id=lease_id,
                preferred=preferred,
                error=error,
            )
            if failure_terminal is None:
                self._discard_stale_attempt(
                    job_id,
                    attempt=attempt.attempt,
                    lease_id=lease_id,
                    error=error,
                )
                return
            artifacts = self._write_terminal_artifacts(
                job_id,
                attempt=attempt.attempt,
                lease_id=lease_id,
                status=failure_terminal,
                error=error,
            )

    def _recover_failed_publication(
        self,
        job_id: str,
        *,
        lease_id: str,
        attempt: int,
        error: str,
        result: dict[str, Any] | ExperimentResult,
    ) -> bool:
        """Correct only this owner's just-published success, then try one archive."""
        from pydantic_core import to_jsonable_python

        with self.repository.publication_guard():
            current = self.repository.get_job(job_id)
            if current.lease_id != lease_id or current.worker_id != self.worker_id:
                self._discard_stale_attempt(job_id, attempt=attempt, lease_id=lease_id, error=error)
                return True
            if current.status != RuntimeJobStatus.SUCCEEDED:
                return False
            corrected = self.repository.update_status_cas(
                job_id,
                expected=RuntimeJobStatus.SUCCEEDED,
                next_status=RuntimeJobStatus.RECOVERY_PENDING,
                reason_code="artifact_publication_failed",
                worker_id=self.worker_id,
                lease_id=lease_id,
                expected_lease_id=lease_id,
                expected_worker_id=self.worker_id,
                error_code="artifact_publication_failed",
                error_message=error,
            )
            if corrected is None:
                return False
            evidence = to_jsonable_python(
                result.model_dump(mode="json") if isinstance(result, ExperimentResult) else result
            )
            evidence.update(
                status=RuntimeJobStatus.RECOVERY_PENDING.value,
                success=False,
                task_success=False,
                error=error,
            )
            # Persist the corrected outcome before another filesystem attempt.
            # If the disk stays unwritable, stale success files are not indexed.
            self.repository.finish_attempt(
                job_id,
                attempt=attempt,
                result=RuntimeJobStatus.RECOVERY_PENDING.value,
                error=error,
                artifact_paths={},
            )
            self.repository.save_artifacts(job_id, {})
            self.repository.save_metrics(job_id, [])
            self.repository.append_event(
                job_id,
                event_type="artifact_publication_failed",
                source="simulation_runtime",
                payload={"lease_id": lease_id, "attempt": attempt, "result_evidence": evidence},
            )
            self.repository.release_lease(lease_id)
            try:
                artifacts = self._write_artifacts(
                    self.repository.get_job(job_id),
                    events=[],
                    metrics=[],
                    result=evidence,
                    expected_terminal_status=RuntimeJobStatus.RECOVERY_PENDING,
                )
                self.repository.save_artifacts(job_id, artifacts)
                self.repository.finish_attempt(
                    job_id,
                    attempt=attempt,
                    result=RuntimeJobStatus.RECOVERY_PENDING.value,
                    error=error,
                    artifact_paths=artifacts,
                )
            except Exception as recovery_error:
                self.repository.append_event(
                    job_id,
                    event_type="artifact_recovery_write_failed",
                    source="simulation_runtime",
                    payload={
                        "lease_id": lease_id,
                        "attempt": attempt,
                        "error": f"{type(recovery_error).__name__}: {recovery_error}",
                    },
                )
            return True

    def _settle_failure_status(
        self,
        job_id: str,
        *,
        lease_id: str,
        preferred: RuntimeJobStatus,
        error: str,
    ) -> RuntimeJobStatus | None:
        """Converge owned failures; None means another lease owns the job now."""
        active = {
            RuntimeJobStatus.LEASED,
            RuntimeJobStatus.STARTING,
            RuntimeJobStatus.RUNNING,
            RuntimeJobStatus.FINALIZING,
            RuntimeJobStatus.CANCEL_REQUESTED,
            RuntimeJobStatus.CANCELLING,
        }
        for _ in range(8):
            current = self.repository.get_job(job_id)
            if current.lease_id != lease_id or current.worker_id != self.worker_id:
                return None
            if current.status not in active:
                return current.status
            if current.status == RuntimeJobStatus.CANCEL_REQUESTED:
                next_status = RuntimeJobStatus.CANCELLING
            elif current.status == RuntimeJobStatus.CANCELLING:
                next_status = RuntimeJobStatus.CANCELLED
            elif current.status == RuntimeJobStatus.FINALIZING:
                # The existing state machine closes finalization failures as FAILED.
                next_status = RuntimeJobStatus.FAILED
            elif current.cancel_requested or preferred == RuntimeJobStatus.CANCELLED:
                next_status = RuntimeJobStatus.CANCEL_REQUESTED
            elif current.status == RuntimeJobStatus.LEASED:
                next_status = RuntimeJobStatus.INTERRUPTED
            else:
                next_status = preferred
            updated = self.repository.update_status_cas(
                job_id,
                expected=current.status,
                next_status=next_status,
                reason_code=next_status.value.lower(),
                worker_id=self.worker_id,
                lease_id=lease_id,
                error_message=error,
                expected_lease_id=lease_id,
                expected_worker_id=self.worker_id,
            )
            if updated is not None and next_status not in active:
                return updated.status
            # A racing operator cancel or lease interruption wins the next read.
        current = self.repository.get_job(job_id)
        return (
            current.status
            if (current.lease_id == lease_id and current.worker_id == self.worker_id)
            else None
        )

    def _discard_stale_attempt(
        self,
        job_id: str,
        *,
        attempt: int,
        lease_id: str,
        error: str,
    ) -> None:
        """Close only the old attempt; shared metrics/files belong to the new owner."""
        self.repository.finish_attempt(
            job_id,
            attempt=attempt,
            result=RuntimeJobStatus.INTERRUPTED.value,
            error=f"lease ownership lost; late result discarded: {error}",
            artifact_paths={},
        )
        self.repository.append_event(
            job_id,
            event_type="stale_worker_result_discarded",
            source="simulation_runtime",
            payload={
                "lease_id": lease_id,
                "worker_id": self.worker_id,
                "attempt": attempt,
                "attempt_result": RuntimeJobStatus.INTERRUPTED.value,
            },
        )
        self.repository.release_lease(lease_id)

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
        if draft.job_type == "DATASET_GENERATION":
            from cloud_edge_robot_arm.simulation_runtime.dataset_job import run_dataset_job

            result = run_dataset_job(
                draft,
                self.artifact_root / job.artifact_root,
                cancelled=lambda: (
                    self._active_job_cancelled(job)
                    or time.monotonic() - start_monotonic >= job.timeout_seconds
                ),
            )
            self._raise_if_cancelled_or_timed_out(job.job_id, job, start_monotonic)
            if result.get("dataset_status") == "CANCELLED":
                raise CancelledByOperator("dataset generation cancelled")
            self.repository.append_event(
                job.job_id,
                event_type="dataset_generated",
                source="dataset_generation",
                payload={"dataset_status": result["dataset_status"], "task_success": False},
            )
            return result, [], []
        if draft.input_mode == "RGBD":
            return self._run_rgbd(job, draft, start_monotonic=start_monotonic)
        if job.backend == SimulationBackend.MOCK.value:
            return self._run_mock(job, draft)
        if job.backend == SimulationBackend.MUJOCO.value:
            return self._run_mujoco(job, draft)
        # 非可用后端必须明确 BLOCKED_BY_ENV，不能回退到 Mock 冒充成功。
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

    def _run_rgbd(
        self, job: SimulationJobRecord, draft: ExperimentDraft, *, start_monotonic: float
    ) -> tuple[dict[str, Any], list[TimelineEvent], list[SimulationMetric]]:
        from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest
        from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
        from cloud_edge_robot_arm.vision.capture import (
            capture_simulated_observation,
            save_observation,
        )
        from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter
        from cloud_edge_robot_arm.vision.request_control import (
            ModelCallCancelled,
            ModelCallTimedOut,
            bounded_model_call,
        )

        run_dir = self._rgbd_work_dir(job)
        try:
            if job.backend not in {"MUJOCO", "ISAAC_SIM"}:
                raise RuntimeError(
                    "RGBD_CAMERA_REQUIRED: select MuJoCo or Isaac; Mock is legacy only"
                )
            if draft.execution_scope == "VISION_CLOSED_LOOP":
                return self._run_visual_closed_loop(job, draft, start_monotonic=start_monotonic)
            observation = capture_simulated_observation(
                backend=cast(Literal["MUJOCO", "ISAAC_SIM"], job.backend),
                scenario_id=job.scenario_id,
                seed=job.seed,
            )
            save_observation(observation, run_dir)
            self.repository.append_event(
                job.job_id,
                event_type="rgbd_captured",
                source="rgbd_camera",
                payload=observation.evidence(),
            )
            if draft.execution_scope == "CAPTURE_ONLY":
                return (
                    {
                        "evaluation_scope": "CAPTURE_ONLY",
                        "task_success": False,
                        "task_execution": "NOT_RUN",
                        "observation": observation.evidence(),
                    },
                    [],
                    [],
                )
            planner = (
                self.planner_factory()
                if self.planner_factory
                else RGBDPlannerAdapter.from_environment()
            )
            request = InitialPlanningRequest(
                request_id=job.run_id,
                user_instruction=draft.user_instruction,
                observation=observation,
                control_mode="EVENT_TRIGGERED_EDGE_AUTONOMY"
                if job.control_mode != "PCSC"
                else "PERIODIC_CLOUD_SUPERVISION",
            )
            response = bounded_model_call(
                lambda: PlanningPipeline(planner=planner).process(request),
                timeout_s=job.timeout_seconds - (time.monotonic() - start_monotonic),
                cancelled=lambda: self._active_job_cancelled(job),
                resource_key=str(getattr(planner, "base_url", "visual-provider")),
            )
            self._raise_if_cancelled_or_timed_out(job.job_id, job, start_monotonic)
            _atomic_write_json(run_dir / "visual_plan.json", response.model_dump(mode="json"))
            if response.outcome != "PLANNED":
                if response.reason and "RGBD_MODEL_UNAVAILABLE" in response.reason:
                    raise RuntimeError(response.reason)
                raise ValueError(response.reason or "visual planning rejected")
        except ModelCallCancelled as exc:
            if self._heartbeat_failed.is_set():
                raise RuntimeError("lease heartbeat failed; result discarded") from exc
            raise CancelledByOperator(str(exc)) from exc
        except ModelCallTimedOut as exc:
            raise TimedOut(str(exc)) from exc
        except (CancelledByOperator, TimedOut):
            raise
        except (RuntimeError, ImportError, OSError) as exc:
            self._transition(
                job.job_id,
                RuntimeJobStatus.RUNNING,
                RuntimeJobStatus.BLOCKED_BY_ENV,
                job.lease_id,
                error_message=str(exc),
            )
            raise
        latency = sum(attempt.latency_ms for attempt in response.attempts)
        if response.contract is None:
            raise ValueError("planned result has no contract")
        self.repository.append_event(
            job.job_id,
            event_type="rgbd_plan_validated",
            source="rgbd_visual",
            payload={
                "evaluation_scope": "RGBD_PLANNING_ONLY",
                "task_success": False,
                "task_execution": "NOT_RUN",
                "latency_ms": latency,
            },
        )
        metric = SimulationMetric(
            name="valid_decision_latency_ms",
            value=latency,
            unit="ms",
            source="rgbd_visual",
            backend=SimulationBackend(job.backend),
            scenario=job.scenario_id,
            seed=job.seed,
            control_mode=job.control_mode,
        )
        return (
            {
                "evaluation_scope": "RGBD_PLANNING_ONLY",
                "task_success": False,
                "task_execution": "NOT_RUN",
                "planning_outcome": response.outcome.value,
                "observation": observation.evidence(),
                "contract": response.contract.model_dump(mode="json"),
            },
            [],
            [metric],
        )

    def _run_visual_closed_loop(
        self, job: SimulationJobRecord, draft: ExperimentDraft, *, start_monotonic: float
    ) -> tuple[dict[str, Any], list[TimelineEvent], list[SimulationMetric]]:
        from pydantic_core import to_jsonable_python

        from cloud_edge_robot_arm.simulation.config import SimulatorConfig
        from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
        from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
        from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
        from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession
        from cloud_edge_robot_arm.vision.evaluation import ExecutionPolicy
        from cloud_edge_robot_arm.vision.execution import run_visual_episode
        from cloud_edge_robot_arm.vision.planner import RGBDModelUnavailable, RGBDPlannerAdapter
        from cloud_edge_robot_arm.vision.task_semantics import apply_s01_task_semantics

        if job.backend != "MUJOCO" or job.scenario_id != "S01_NORMAL_STATIC":
            raise RGBDModelUnavailable("RGBD_MODEL_UNAVAILABLE: unsupported online asset/scenario")
        if self.planner_factory is None:
            raise RGBDModelUnavailable("RGBD_MODEL_UNAVAILABLE: explicit frozen planner required")
        planner = self.planner_factory()
        if not isinstance(planner, RGBDPlannerAdapter):
            raise RGBDModelUnavailable("RGBD_MODEL_UNAVAILABLE: visual adapter required")
        snapshot = getattr(planner, "model_snapshot", None)
        if (
            snapshot is None
            or not snapshot.weight_digest
            or snapshot.grasp_profile != "mujoco_upright_box_v1"
        ):
            raise RGBDModelUnavailable(
                "RGBD_MODEL_UNAVAILABLE: configure a verified research snapshot"
            )
        self._raise_if_cancelled_or_timed_out(job.job_id, job, start_monotonic)
        config = SimulatorConfig(render_rgb=True, render_depth=True, seed=job.seed)
        backend = MuJoCoPhysicsBackend()
        run_dir = self._rgbd_work_dir(job)
        try:
            backend.initialize(config)
            backend.reset(PhysicalScenarioConfig.scenario(job.scenario_id, seed=job.seed))
            backend.step(steps=120)  # Initialization settling precedes the evaluated episode.
            robot = MuJoCoSkillRobot(backend)
            with MuJoCoCaptureSession(config, backend=backend) as capture:
                outcome = run_visual_episode(
                    planner,
                    robot,
                    capture,
                    ExecutionPolicy(
                        instruction=draft.user_instruction,
                        model_snapshot_hash=snapshot.digest(),
                        timeout_s=max(
                            0.001, job.timeout_seconds - (time.monotonic() - start_monotonic)
                        ),
                        cancelled=lambda: self._active_job_cancelled(job),
                        output_dir=run_dir / "visual_episode",
                    ),
                )
        finally:
            backend.shutdown()
        self._raise_if_cancelled_or_timed_out(job.job_id, job, start_monotonic)
        episode_payload = to_jsonable_python(asdict(outcome))
        for record in episode_payload["verification_records"]:
            self.repository.append_event(
                job.job_id, event_type="rgbd_episode_evidence", source="rgbd_visual", payload=record
            )
        result = apply_s01_task_semantics(episode_payload, draft.user_instruction)
        result.update(
            task_execution="EXECUTED" if outcome.executed_actions else "NOT_EXECUTED",
            blocked_by_env=(outcome.terminal_reason or "").startswith("BLOCKED_BY_ENV"),
        )
        return result, [], []

    def _run_mock(
        self, job: SimulationJobRecord, draft: ExperimentDraft
    ) -> tuple[ExperimentResult, list[TimelineEvent], list[SimulationMetric]]:
        run_dir = self.artifact_root / job.artifact_root
        config = _experiment_config(draft, job, run_dir)
        runner = ExperimentRunner(config)
        try:
            execution = runner.run()
        finally:
            # ExperimentRunner 持有 RuntimeExperimentHarness，harness 内部使用多个
            # SQLite 仓库；worker 必须显式关闭，避免 terminal artifact 清理后留下
            # 指向 deleted sqlite 文件的 fd。
            runner.harness.close()
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
            randomization_parameters={
                name: {
                    **parameter.model_dump(mode="json", exclude_none=True),
                    "enabled": parameter.enabled and draft.domain_randomization.enabled,
                }
                for name, parameter in draft.domain_randomization.parameters.items()
            },
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
        expected_terminal_status: RuntimeJobStatus | None = None,
    ) -> dict[str, str]:
        run_dir = self.artifact_root / job.artifact_root
        run_dir.mkdir(parents=True, exist_ok=True)
        # artifact 文件是重启恢复和验收的第二真源；数据库缺记录时可以从这里恢复，
        # 但写入时仍只保存相对路径，避免泄露本机目录。
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
            "evidence_consistency": run_dir / "evidence_consistency.json",
            "trajectory": run_dir / "trajectory.json",
            "sensor_stream": run_dir / "sensor_stream.json",
            "randomization_sample": run_dir / "randomization_sample.json",
            "backend_parameter_mapping": run_dir / "backend_parameter_mapping.json",
            "sim_trace": run_dir / "sim_trace.json",
            "rerun_viewer_manifest": run_dir / "rerun_viewer_manifest.json",
            "sim_real_gap_report": run_dir / "sim_real_gap_report.json",
        }
        _atomic_write_json(paths["run_manifest"], redact(job.manifest))
        job_events = self.repository.list_events(job.run_id)
        _atomic_write_jsonl(
            paths["events"],
            [
                {
                    "sequence": event.sequence,
                    "event_type": event.event_type,
                    "source": event.source,
                    "severity": "info",
                    "virtual_time_ms": 0,
                    "wall_time": event.timestamp.isoformat(),
                    "payload": redact(event.payload),
                }
                for event in job_events
            ],
        )
        _atomic_write_json(paths["metrics"], [metric.model_dump(mode="json") for metric in metrics])
        _atomic_write_json(paths["logs"], {"messages": [], "redacted": True})
        if isinstance(result, ExperimentResult):
            result_payload: dict[str, Any] = result.model_dump(mode="json")
        else:
            result_payload = dict(result)
        result_payload.update(
            {
                "status": job.status.value,
                "backend": job.backend,
                "runner": "RGBD_" + job.draft.get("execution_scope", "VISUAL_PLANNING")
                if job.draft.get("input_mode", "RGBD") == "RGBD"
                else ("MUJOCO_SCENARIO" if job.backend == "MUJOCO" else "MOCK_SCENARIO"),
                "runtime_executed": True,
                "mock_fallback_used": False,
                "real_controller_contacted": False,
                "hardware_motion_observed": False,
                "hardware_write_operations": [],
            }
        )
        if job.draft.get("job_type") == "DATASET_GENERATION":
            result_payload["runner"] = "DATASET_GENERATION"
        if job.draft.get("input_mode", "RGBD") == "RGBD":
            scope = job.draft.get("execution_scope", "VISUAL_PLANNING")
            result_payload.setdefault("evaluation_scope", scope)
            if scope != "VISION_CLOSED_LOOP":
                result_payload.update(task_success=False, task_execution="NOT_RUN")
            else:
                result_payload.setdefault("task_success", False)
                result_payload.setdefault("task_execution", "NOT_EXECUTED")
        paths.update(self._rgbd_artifact_paths(job))
        if (run_dir / "dataset/manifest.json").exists():
            paths["dataset_manifest"] = run_dir / "dataset/manifest.json"
        trial_payload = result_payload.get("trial", {})
        if not isinstance(trial_payload, dict):
            trial_payload = {}
        trajectory = trial_payload.get("trajectory", [])
        sensor_stream = trial_payload.get("sensor_stream", [])
        randomization_sample = trial_payload.get("randomization_sample", {})
        backend_mapping = trial_payload.get("backend_parameter_evidence", {})
        _atomic_write_json(paths["trajectory"], trajectory)
        _atomic_write_json(paths["sensor_stream"], sensor_stream)
        _atomic_write_json(paths["randomization_sample"], randomization_sample)
        _atomic_write_json(paths["backend_parameter_mapping"], backend_mapping)
        sim_trace = _sim_trace_payload(job, trial_payload)
        _atomic_write_json(paths["sim_trace"], sim_trace)
        _atomic_write_json(
            paths["rerun_viewer_manifest"],
            {
                "schema_version": "sim2real.rerun-viewer.v1",
                "timeline": "elapsed_s",
                "frame": "world",
                "simulation_trace": "sim_trace.json",
                "real_trace_required": True,
                "viewer": "Rerun",
                "generator": "scripts/generate_sim2real_gap_report.py --rerun",
            },
        )
        _atomic_write_json(
            paths["sim_real_gap_report"],
            {
                "schema_version": "sim2real.gap-report.v1",
                "status": "WAITING_FOR_REAL_TRACE",
                "simulation_trace_id": sim_trace.get("trace_id", ""),
                "report_endpoint": "/api/v1/simulation/sim2real/gap-report",
                "real_trace_is_read_only_evidence": True,
                "real_controller_contacted_by_reporter": False,
                "hardware_write_operations": [],
            },
        )
        _atomic_write_json(paths["result"], redact(result_payload))
        _atomic_write_json(paths["provenance"], redact(job.provenance))
        runtime_job_payload = redact(_job_artifact(job))
        _atomic_write_json(paths["runtime_job"], runtime_job_payload)
        _atomic_write_json(paths["job"], runtime_job_payload)
        transitions = [
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
            }
            for event in job_events
            if event.previous_status or event.next_status
        ]
        _atomic_write_jsonl(paths["state_transitions"], transitions)
        attempts = self.repository.list_attempts(job.run_id)
        _atomic_write_jsonl(
            paths["attempts"],
            [
                {
                    "attempt": attempt.attempt,
                    "worker_id": attempt.worker_id,
                    "started_at": attempt.started_at.isoformat(),
                    "ended_at": attempt.ended_at.isoformat() if attempt.ended_at else "",
                    "result": attempt.result,
                    "error": attempt.error,
                }
                for attempt in attempts
            ],
        )
        leases = self.repository.list_leases(job.run_id)
        lease_rows = [
            {
                "job_id": lease.job_id,
                "lease_id": lease.lease_id,
                "worker_id": lease.worker_id,
                "acquired_at": lease.acquired_at.isoformat(),
                "expires_at": lease.expires_at.isoformat(),
                "heartbeat_at": lease.heartbeat_at.isoformat(),
                "released_at": lease.released_at.isoformat() if lease.released_at else "",
            }
            for lease in leases
        ]
        _atomic_write_jsonl(paths["leases"], lease_rows)
        _atomic_write_jsonl(paths["lease_history"], lease_rows)
        _atomic_write_json(
            paths["resource_usage"],
            {
                "cpu_quota": "not_enforced",
                "memory_soft_limit": "not_enforced",
                "max_log_bytes": 0,
                "max_event_count": len(job_events),
                "max_runtime_seconds": job.timeout_seconds,
                "redacted": True,
            },
        )
        _atomic_write_json(
            paths["cancellation"],
            {
                "requested_at": job.updated_at.isoformat() if job.cancel_requested else "",
                "acknowledged_at": job.updated_at.isoformat() if job.cancel_requested else "",
                "terminated_at": job.completed_at.isoformat()
                if job.completed_at and job.cancel_requested
                else "",
                "force_killed": False,
            },
        )
        _atomic_write_json(
            paths["recovery"],
            {
                "recovered": False,
                "recovery_required": job.status == RuntimeJobStatus.RECOVERY_PENDING,
                "duplicate_execution_prevented": True,
            },
        )
        _atomic_write_json(
            paths["evidence_consistency"],
            _evidence_consistency(
                run_id=job.run_id,
                expected_terminal_status=expected_terminal_status,
                job=job,
                attempts=attempts,
                leases=leases,
                transitions=transitions,
                events=job_events,
                result_payload=result_payload,
                paths=paths,
            ),
        )
        _remove_internal_sqlite_sidecars(run_dir)
        return {
            name: path.relative_to(self.artifact_root).as_posix() for name, path in paths.items()
        }

    def _rgbd_work_dir(self, job: SimulationJobRecord) -> Path:
        """Late flushes remain private to the lease that started the RGB-D run."""
        run_dir = self.artifact_root / job.artifact_root
        return run_dir / "rgbd-attempts" / job.lease_id if job.lease_id else run_dir

    def _rgbd_artifact_paths(self, job: SimulationJobRecord) -> dict[str, Path]:
        directory = self._rgbd_work_dir(job)
        return {
            key: directory / name
            for key, name in {
                "rgb": "rgb.png",
                "depth": "depth.f32",
                "depth_visualization": "depth.png",
                "observation": "observation.json",
                "visual_plan": "visual_plan.json",
                "visual_episode": "visual_episode/episode.json",
                "verification_state": "visual_episode/verification-state.json",
                "physical_outcome": "visual_episode/physical-outcome.json",
                "physical_evidence": "visual_episode/physical-evidence.json",
            }.items()
            if (directory / name).is_file()
        }

    def _artifact_paths(self, job: SimulationJobRecord) -> dict[str, str]:
        run_dir = self.artifact_root / job.artifact_root
        names = {
            "run_manifest": "run_manifest.json",
            "events": "events.jsonl",
            "metrics": "metrics.json",
            "logs": "logs.json",
            "result": "result.json",
            "provenance": "provenance.json",
            "job": "job.json",
            "state_transitions": "state_transitions.jsonl",
            "runtime_job": "runtime_job.json",
            "attempts": "attempts.jsonl",
            "leases": "leases.jsonl",
            "lease_history": "lease_history.jsonl",
            "resource_usage": "resource_usage.json",
            "cancellation": "cancellation.json",
            "recovery": "recovery.json",
            "evidence_consistency": "evidence_consistency.json",
            "trajectory": "trajectory.json",
            "sensor_stream": "sensor_stream.json",
            "randomization_sample": "randomization_sample.json",
            "backend_parameter_mapping": "backend_parameter_mapping.json",
            "sim_trace": "sim_trace.json",
            "rerun_viewer_manifest": "rerun_viewer_manifest.json",
            "sim_real_gap_report": "sim_real_gap_report.json",
        }
        if (run_dir / "dataset/manifest.json").exists():
            names["dataset_manifest"] = "dataset/manifest.json"
        paths = {
            key: (run_dir / name).relative_to(self.artifact_root).as_posix()
            for key, name in names.items()
        }
        paths.update(
            {
                key: path.relative_to(self.artifact_root).as_posix()
                for key, path in self._rgbd_artifact_paths(job).items()
            }
        )
        return paths

    def _owns_artifact_publication(self, job: SimulationJobRecord, lease_id: str) -> bool:
        from datetime import UTC, datetime

        from cloud_edge_robot_arm.simulation_runtime.models import TERMINAL_STATUSES

        if job.lease_id != lease_id or job.worker_id != self.worker_id:
            return False
        lease = next(
            (
                item
                for item in self.repository.list_leases(job.run_id)
                if item.lease_id == lease_id and item.worker_id == self.worker_id
            ),
            None,
        )
        if lease is None:
            return False
        # A completed owner may archive after releasing its own lease while the
        # publication guard prevents a retry from acquiring a replacement lease.
        if job.status in TERMINAL_STATUSES:
            return True
        now = datetime.now(UTC)
        return (
            lease.released_at is None
            and lease.expires_at > now
            and job.lease_expires_at is not None
            and job.lease_expires_at > now
        )

    def _write_terminal_artifacts(
        self,
        job_id: str,
        *,
        attempt: int,
        lease_id: str,
        status: RuntimeJobStatus,
        error: str,
    ) -> dict[str, str]:
        with self.repository.publication_guard():
            return self._write_owned_terminal_artifacts(
                job_id,
                attempt=attempt,
                lease_id=lease_id,
                status=status,
                error=error,
            )

    def _write_owned_terminal_artifacts(
        self,
        job_id: str,
        *,
        attempt: int,
        lease_id: str,
        status: RuntimeJobStatus,
        error: str,
    ) -> dict[str, str]:
        job = self.repository.get_job(job_id)
        if not self._owns_artifact_publication(job, lease_id):
            self._discard_stale_attempt(job_id, attempt=attempt, lease_id=lease_id, error=error)
            return {}
        episode_path = self._rgbd_work_dir(job) / "visual_episode/episode.json"
        episode_evidence: dict[str, Any] = {}
        if job.draft.get("execution_scope") == "VISION_CLOSED_LOOP" and episode_path.is_file():
            episode_evidence = json.loads(episode_path.read_text())
            episode_evidence.update(
                task_success=False,
                task_execution="EXECUTED"
                if episode_evidence.get("executed_actions", 0)
                else "NOT_EXECUTED",
            )
        artifacts = self._artifact_paths(job)
        self.repository.save_metrics(job_id, [])
        self.repository.finish_attempt(
            job_id,
            attempt=attempt,
            result=status.value,
            error=error,
            artifact_paths=artifacts,
        )
        self.repository.append_event(
            job_id,
            event_type="artifact_created",
            source="simulation_runtime",
            payload=dict(artifacts),
        )
        self.repository.release_lease(lease_id)
        artifacts = self._write_artifacts(
            self.repository.get_job(job_id),
            events=[],
            metrics=[],
            result={
                **episode_evidence,
                "status": status.value,
                "error": error,
                "runtime_executed": True,
                "mock_fallback_used": False if job.backend == "MUJOCO" else None,
            },
            expected_terminal_status=status,
        )
        self.repository.save_artifacts(job_id, artifacts)
        return artifacts

    def _transition(
        self,
        job_id: str,
        expected: RuntimeJobStatus,
        next_status: RuntimeJobStatus,
        lease_id: str,
        *,
        error_message: str = "",
        absorb_cancel_race: bool = False,
    ) -> None:
        updated = self.repository.update_status_cas(
            job_id,
            expected=expected,
            next_status=next_status,
            reason_code=next_status.value.lower(),
            worker_id=self.worker_id,
            lease_id=lease_id,
            error_message=error_message,
            expected_lease_id=lease_id,
            expected_worker_id=self.worker_id,
        )
        if updated is None:
            current = self.repository.get_job(job_id)
            if current.status in {
                RuntimeJobStatus.CANCEL_REQUESTED,
                RuntimeJobStatus.CANCELLING,
                RuntimeJobStatus.CANCELLED,
            }:
                if absorb_cancel_race:
                    return
                raise CancelledByOperator("cancelled by operator")
            if current.status != next_status:
                raise RuntimeError(f"state transition lost: {expected.value}->{next_status.value}")

    def _active_job_cancelled(self, original: SimulationJobRecord) -> bool:
        """Recheck persisted ownership at each model return and physical boundary."""
        from datetime import UTC, datetime

        try:
            current = self.repository.get_job(original.job_id)
            if current.cancel_requested or current.status in {
                RuntimeJobStatus.CANCEL_REQUESTED,
                RuntimeJobStatus.CANCELLING,
                RuntimeJobStatus.CANCELLED,
            }:
                return True
            if self._heartbeat_failed.is_set():
                return True
            now = datetime.now(UTC)
            if (
                not original.lease_id
                or current.lease_id != original.lease_id
                or current.worker_id != self.worker_id
                or current.status != RuntimeJobStatus.RUNNING
                or current.lease_expires_at is None
                or current.lease_expires_at <= now
            ):
                self._heartbeat_failed.set()
                return True
            lease = next(
                (
                    item
                    for item in self.repository.list_leases(original.run_id)
                    if item.lease_id == original.lease_id
                ),
                None,
            )
            if (
                lease is None
                or lease.released_at is not None
                or lease.expires_at <= now
                or lease.worker_id != self.worker_id
            ):
                self._heartbeat_failed.set()
                return True
            return False
        except Exception:
            # A missing/unreadable lease cannot authorize a late response.
            self._heartbeat_failed.set()
            return True

    def _cancel_requested(self, job_id: str) -> bool:
        return self.repository.get_job(job_id).cancel_requested

    def _raise_if_cancelled_or_timed_out(
        self, job_id: str, original: SimulationJobRecord, start_monotonic: float
    ) -> None:
        current = self.repository.get_job(job_id)
        if current.cancel_requested or current.status == RuntimeJobStatus.CANCEL_REQUESTED:
            raise CancelledByOperator("cancelled by operator")
        if self._heartbeat_failed.is_set():
            raise RuntimeError("lease heartbeat failed; dispatch stopped")
        if current.lease_id != original.lease_id or current.status != RuntimeJobStatus.RUNNING:
            raise RuntimeError("job no longer owns an active running lease")
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
    """把 Mock runner 结果投影为统一指标模型。"""

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
    """把真实 MuJoCo trial 结果投影为统一指标模型。

    这里的 backend 固定为 MUJOCO，并显式记录 mock_fallback_used=false，
    供 Phase 11.1 验收区分 readiness 与 runtime acceptance。
    """

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


def _sim_trace_payload(job: SimulationJobRecord, trial: dict[str, Any]) -> dict[str, object]:
    raw_trajectory = trial.get("trajectory", [])
    raw_sensors = trial.get("sensor_stream", [])
    trajectory = raw_trajectory if isinstance(raw_trajectory, list) else []
    sensors = raw_sensors if isinstance(raw_sensors, list) else []
    samples: list[dict[str, object]] = []
    for index, raw in enumerate(trajectory):
        if not isinstance(raw, dict):
            continue
        sensor = sensors[min(index, len(sensors) - 1)] if sensors else {}
        if not isinstance(sensor, dict):
            sensor = {}
        samples.append(
            {
                "elapsed_s": raw.get("elapsed_s", 0.0),
                "joint_positions_rad": raw.get("joint_positions_rad", []),
                "tcp_position_m": raw.get("tcp_position_m"),
                "sensor_latency_ms": sensor.get("latency_ms"),
                "depth_mean_m": sensor.get("depth_mean_m"),
                "frame_id": sensor.get("frame_id", "world"),
            }
        )
    randomization = trial.get("randomization_sample", {})
    parameters: dict[str, float] = {}
    if isinstance(randomization, dict):
        raw_parameters = randomization.get("parameters", {})
        if isinstance(raw_parameters, dict):
            for name, item in raw_parameters.items():
                if isinstance(item, dict) and isinstance(item.get("value"), int | float):
                    parameters[str(name)] = float(item["value"])
    source = "ISAAC_SIM" if job.backend == "ISAAC_SIM" else "SIM"
    return {
        "trace_id": f"{job.run_id}-{job.backend.lower()}",
        "source": source,
        "clock": "simulation_time",
        "frame": "world",
        "samples": samples,
        "parameters": parameters,
        "provenance": {
            "run_id": job.run_id,
            "job_id": job.job_id,
            "backend": job.backend,
            "reproducibility_hash": job.reproducibility_hash,
        },
    }


def _atomic_write_json(path: Path, payload: Any) -> None:
    _atomic_write_text(path, json.dumps(redact(payload), sort_keys=True, indent=2) + "\n")


def _atomic_write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    text = "".join(json.dumps(redact(row), sort_keys=True) + "\n" for row in rows)
    _atomic_write_text(path, text)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    with temp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def _evidence_consistency(
    *,
    run_id: str,
    expected_terminal_status: RuntimeJobStatus | None,
    job: SimulationJobRecord,
    attempts: list[Any],
    leases: list[Any],
    transitions: list[dict[str, Any]],
    events: list[Any],
    result_payload: dict[str, Any],
    paths: dict[str, Path],
) -> dict[str, Any]:
    expected = expected_terminal_status.value if expected_terminal_status else job.status.value
    final_attempt_status = attempts[-1].result if attempts else ""
    final_transition_status = transitions[-1]["next_status"] if transitions else ""
    event_types = {event.event_type for event in events}
    terminal_event = {
        RuntimeJobStatus.SUCCEEDED.value: "job_completed",
        RuntimeJobStatus.CANCELLED.value: "job_cancelled",
        RuntimeJobStatus.TIMED_OUT.value: "job_timed_out",
        RuntimeJobStatus.FAILED.value: "job_failed",
    }.get(expected, "")
    result_status = str(result_payload.get("status", ""))
    artifact_created_present = "artifact_created" in event_types
    terminal_event_present = terminal_event in event_types if terminal_event else True
    lease_released = not leases or all(lease.released_at is not None for lease in leases)
    consistent = all(
        [
            job.status.value == expected,
            final_attempt_status == expected,
            final_transition_status == expected,
            result_status == expected,
            artifact_created_present,
            terminal_event_present,
            lease_released,
        ]
    )
    return {
        "run_id": run_id,
        "expected_terminal_status": expected,
        "api_status": job.status.value,
        "job_status": job.status.value,
        "runtime_job_status": job.status.value,
        "final_attempt_status": final_attempt_status,
        "final_transition_status": final_transition_status,
        "result_status": result_status,
        "lease_released": lease_released,
        "artifact_created_present": artifact_created_present,
        "terminal_event_present": terminal_event_present,
        "consistent": consistent,
        "checked_at": job.updated_at.isoformat(),
        "file_hashes": _file_hashes(paths),
    }


def _file_hashes(paths: dict[str, Path]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for key, path in sorted(paths.items()):
        if key == "evidence_consistency" or not path.exists():
            continue
        hashes[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes
