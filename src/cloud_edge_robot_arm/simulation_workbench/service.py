"""仿真工作台服务层。

该服务从 scenario_registry、ExperimentConfig 和 runtime service 派生工作台数据。
它负责校验高层实验配置、生成 manifest、读写 artifact，并明确区分 Mock、MuJoCo、
Isaac BLOCKED_BY_ENV 和 MoveIt dry-run。
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from collections.abc import Iterable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from cloud_edge_robot_arm.dashboard.event_stream import DashboardEventStream
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
from cloud_edge_robot_arm.experiments.reproducibility import stable_hash
from cloud_edge_robot_arm.experiments.runner import ExperimentRunner, git_sha
from cloud_edge_robot_arm.experiments.scenario import get_scenario, scenario_registry
from cloud_edge_robot_arm.real_robot.provenance import current_source_tree_hash
from cloud_edge_robot_arm.simulation.environment import detect_environment
from cloud_edge_robot_arm.simulation.evaluation.cross_backend import compare_backend_results
from cloud_edge_robot_arm.simulation.evaluation.metrics import run_mujoco_physical_trial
from cloud_edge_robot_arm.simulation_runtime.service import SimulationRuntimeService
from cloud_edge_robot_arm.simulation_workbench.models import (
    BackendCapability,
    BackendReadiness,
    BatchProgress,
    BatchRecord,
    ComparisonRequest,
    ComparisonResponse,
    ExperimentDraft,
    ExperimentManifest,
    ExportRequest,
    ExportResponse,
    NetworkDraft,
    ParameterSchemaResponse,
    ReproductionResponse,
    ScenarioCategory,
    ScenarioDefinitionView,
    ScenarioListResponse,
    SimulationArtifactsResponse,
    SimulationBackend,
    SimulationCapabilitiesResponse,
    SimulationEventsResponse,
    SimulationMetric,
    SimulationMetricsResponse,
    SimulationRunListResponse,
    SimulationRunnerKind,
    SimulationRunRecord,
    SimulationRunStatus,
    SimulationRunType,
    TimelineEvent,
    ValidationResponse,
)

MAX_BATCH_RUNS = 120
SCHEMA_VERSION = "phase11.simulation.v1"
FORBIDDEN_FIELDS = [
    "shell",
    "command",
    "cmd",
    "script",
    "path",
    "module",
    "environment",
    "env",
    "executable",
    "runner",
    "runner_name",
    "pythonpath",
]


class SimulationWorkbenchService:
    """仿真工作台服务 facade，桥接 scenario registry、runtime 和 artifact 导出。"""

    def __init__(self, *, artifact_root: Path, event_stream: DashboardEventStream | None = None):
        self.artifact_root = artifact_root
        self.phase_root = artifact_root / "phase11"
        self.runs_root = self.phase_root / "runs"
        self.batches_root = self.phase_root / "batches"
        self.comparisons_root = self.phase_root / "comparisons"
        self.exports_root = self.phase_root / "exports"
        self.events = event_stream or DashboardEventStream()
        self._runs: dict[str, SimulationRunRecord] = {}
        self._drafts: dict[str, ExperimentDraft] = {}
        self._events: dict[str, list[TimelineEvent]] = {}
        self._metrics: dict[str, list[SimulationMetric]] = {}
        self._results: dict[str, ExperimentResult | dict[str, Any]] = {}
        self._batches: dict[str, BatchRecord] = {}
        self._comparisons: dict[str, ComparisonResponse] = {}
        runtime_db = os.environ.get("SIMULATION_RUNTIME_DB")
        if runtime_db:
            database_path = Path(runtime_db)
        elif artifact_root == Path("artifacts"):
            database_path = Path("data/simulation_runtime.db")
        else:
            database_path = artifact_root / "simulation_runtime.db"
        self.runtime = SimulationRuntimeService(
            artifact_root=artifact_root,
            database_path=database_path,
            event_stream=self.events,
            runtime_root=artifact_root / "phase11_1/runtime",
        )

    def capabilities(self) -> SimulationCapabilitiesResponse:
        """返回后端能力和 readiness，不把枚举存在误判为 READY。"""
        env = detect_environment()
        isaac_blockers = [str(item) for item in env.details.get("isaac_blockers", [])]
        mujoco_ready = bool(env.details.get("mujoco_version"))
        backends = [
            BackendCapability(
                backend=SimulationBackend.MOCK,
                readiness=BackendReadiness.READY,
                supported_modes=["PCSC", "ETEAC", "AUTO"],
                supported_run_types=[
                    SimulationRunType.SINGLE,
                    SimulationRunType.BATCH,
                    SimulationRunType.SWEEP,
                    SimulationRunType.MODE_COMPARISON,
                ],
                supported_experiment_types=["MOCK_SCENARIO", "PHASE8_BATCH", "PHASE8_SWEEP"],
                runner_allowlist=[
                    SimulationRunnerKind.MOCK_SCENARIO,
                    SimulationRunnerKind.PHASE8_BATCH,
                    SimulationRunnerKind.PHASE8_SWEEP,
                ],
                export_formats=_export_formats(),
                batch_limits={"max_runs": MAX_BATCH_RUNS, "max_concurrency": 1},
            ),
            BackendCapability(
                backend=SimulationBackend.MUJOCO,
                readiness=BackendReadiness.READY
                if mujoco_ready
                else BackendReadiness.BLOCKED_BY_ENV,
                supported_modes=["PCSC", "ETEAC", "AUTO"],
                supported_run_types=[
                    SimulationRunType.SINGLE,
                    SimulationRunType.PAIRED_BACKEND,
                ],
                supported_experiment_types=[
                    "MUJOCO_SCENARIO",
                    "PHASE9_MUJOCO_BENCHMARK",
                    "CROSS_BACKEND_PAIRED",
                ],
                runner_allowlist=[
                    SimulationRunnerKind.MUJOCO_SCENARIO,
                    SimulationRunnerKind.PHASE9_MUJOCO_BENCHMARK,
                    SimulationRunnerKind.CROSS_BACKEND_PAIRED,
                ],
                export_formats=_export_formats(),
                batch_limits={"max_runs": 30, "max_concurrency": 1},
                blockers=[] if mujoco_ready else ["MuJoCo Python package is not available"],
            ),
            BackendCapability(
                backend=SimulationBackend.ISAAC_SIM,
                readiness=BackendReadiness.READY
                if env.level == "ISAAC_READY"
                else BackendReadiness.BLOCKED_BY_ENV,
                supported_modes=["PCSC", "ETEAC", "AUTO"],
                supported_run_types=[
                    SimulationRunType.SINGLE,
                    SimulationRunType.PAIRED_BACKEND,
                ],
                supported_experiment_types=["ISAAC_BENCHMARK", "CROSS_BACKEND_PAIRED"],
                runner_allowlist=[
                    SimulationRunnerKind.ISAAC_BENCHMARK,
                    SimulationRunnerKind.CROSS_BACKEND_PAIRED,
                ],
                export_formats=_export_formats(),
                batch_limits={"max_runs": 10, "max_concurrency": 1},
                blockers=[] if env.level == "ISAAC_READY" else isaac_blockers,
            ),
            BackendCapability(
                backend=SimulationBackend.MOVEIT_DRY_RUN,
                readiness=BackendReadiness.NOT_CONFIGURED,
                supported_modes=["PCSC", "ETEAC", "AUTO"],
                supported_run_types=[SimulationRunType.SINGLE],
                supported_experiment_types=["MOVEIT_DRY_RUN"],
                runner_allowlist=[],
                export_formats=_export_formats(),
                batch_limits={"max_runs": 1, "max_concurrency": 1},
                blockers=["Phase 11 workbench does not execute MoveIt trajectories"],
            ),
        ]
        return SimulationCapabilitiesResponse(
            backends=backends,
            supported_modes=["PCSC", "ETEAC", "AUTO"],
            supported_run_types=list(SimulationRunType),
            runner_allowlist=list(SimulationRunnerKind),
            export_formats=_export_formats(),
            max_batch_runs=MAX_BATCH_RUNS,
        )

    def scenarios(self) -> ScenarioListResponse:
        """从 scenario_registry 动态返回全部场景视图。"""
        return ScenarioListResponse(
            scenarios=[_scenario_view(item) for item in scenario_registry()]
        )

    def scenario(self, scenario_id: str) -> ScenarioDefinitionView:
        """按场景 ID 返回单个场景视图。"""
        return _scenario_view(get_scenario(scenario_id))

    def parameter_schema(self) -> ParameterSchemaResponse:
        """返回前端参数编辑器使用的权威枚举、边界和禁用字段。"""
        return ParameterSchemaResponse(
            authoritative_models=["ExperimentConfig", "ScenarioDefinition", "ExperimentDraft"],
            enums={
                "backends": [item.value for item in SimulationBackend],
                "run_types": [item.value for item in SimulationRunType],
                "run_statuses": [item.value for item in SimulationRunStatus],
                "control_modes": ["PCSC", "ETEAC", "AUTO"],
                "network_profiles": [item.value for item in NetworkProfileName],
                "cache_policies": [item.value for item in CachePolicy],
                "scenario_categories": [item.value for item in ScenarioCategory],
                "runner_allowlist": [item.value for item in SimulationRunnerKind],
            },
            numeric_limits={
                "seed": {"min": 0, "max": 2**63 - 1},
                "repetitions": {"min": 1, "max": 100},
                "base_latency_ms": {"min": 0, "max": 60000},
                "jitter_ms": {"min": 0, "max": 60000},
                "packet_loss": {"min": 0.0, "max": 1.0},
                "supervision_period_ms": {"min": 1, "max": 60000},
                "timeout_ms": {"min": 1, "max": 600000},
                "max_batch_runs": {"min": 1, "max": MAX_BATCH_RUNS},
            },
            forbidden_fields=FORBIDDEN_FIELDS,
        )

    def validate(self, draft: ExperimentDraft) -> ValidationResponse:
        """校验实验草稿并生成 manifest，但不启动任何运行。"""
        run_count = _run_count(draft)
        if run_count > MAX_BATCH_RUNS:
            raise ValueError(f"batch run count {run_count} exceeds limit {MAX_BATCH_RUNS}")
        _validate_scenarios(draft.scenarios)
        manifest = self._manifest(draft, run_count=run_count)
        blockers = _backend_blockers(draft.backend, self.capabilities())
        return ValidationResponse(
            valid=not blockers,
            manifest=manifest,
            run_count=run_count,
            blockers=blockers,
            warnings=[] if not blockers else ["selected backend is not ready"],
        )

    def list_runs(self) -> SimulationRunListResponse:
        """列出持久化 runtime 中的仿真运行。"""
        return self.runtime.list_runs()

    def get_run(self, run_id: str) -> SimulationRunRecord:
        """按 run_id 查询仿真运行记录。"""
        return self.runtime.get_run(run_id)

    def create_run(self, draft: ExperimentDraft) -> SimulationRunRecord:
        """创建仿真运行并立即交给异步 runtime 队列。"""
        validation = self.validate(draft)
        return self.runtime.create_run(
            draft,
            manifest=validation.manifest,
            blockers=validation.blockers,
        )

    def cancel_run(self, run_id: str) -> SimulationRunRecord:
        """请求取消单个仿真运行，保留已有 evidence。"""
        return self.runtime.cancel_run(run_id)

    def retry_run(self, run_id: str) -> SimulationRunRecord:
        """重试失败或可恢复的仿真运行。"""
        return self.runtime.retry_run(run_id)

    def clone_run(self, run_id: str) -> ReproductionResponse:
        """从历史 run 克隆复现实验草稿。"""
        return self.runtime.clone_run(run_id)

    def reproduce_run(self, run_id: str) -> ReproductionResponse:
        """从持久化 manifest 构造复现实验响应。"""
        return self.runtime.reproduce_run(run_id)

    def events_for(self, run_id: str) -> SimulationEventsResponse:
        """读取 run 的持久化时间线事件。"""
        return self.runtime.events_for(run_id)

    def metrics_for(self, run_id: str) -> SimulationMetricsResponse:
        """读取 run 的持久化指标。"""
        return self.runtime.metrics_for(run_id)

    def artifacts_for(self, run_id: str) -> SimulationArtifactsResponse:
        """读取 run 的 artifact 相对路径。"""
        return self.runtime.artifacts_for(run_id)

    def create_batch(self, draft: ExperimentDraft) -> BatchRecord:
        """创建批量实验并按 manifest 派生多个异步 run。"""
        validation = self.validate(draft)
        return self.runtime.create_batch(
            draft,
            manifest=validation.manifest,
            blockers=validation.blockers,
        )

    def get_batch(self, batch_id: str) -> BatchRecord:
        """按 batch_id 查询批量实验记录。"""
        return self.runtime.get_batch(batch_id)

    def batch_runs(self, batch_id: str) -> SimulationRunListResponse:
        """列出指定 batch 下的全部 run。"""
        return self.runtime.batch_runs(batch_id)

    def cancel_batch(self, batch_id: str) -> BatchRecord:
        """请求取消批量实验中未完成的 run。"""
        return self.runtime.cancel_batch(batch_id)

    def retry_failed_batch(self, batch_id: str) -> BatchRecord:
        """重试 batch 中失败且可重试的 run。"""
        return self.runtime.retry_failed_batch(batch_id)

    def compare(self, request: ComparisonRequest) -> ComparisonResponse:
        """根据已有 run 指标计算模式或后端对比统计。"""
        runs: list[SimulationRunRecord] = []
        metrics: list[SimulationMetric] = []
        for run_id in request.run_ids:
            try:
                run = self.runtime.get_run(run_id)
            except KeyError:
                continue
            runs.append(run)
            metrics.extend(self.runtime.metrics_for(run_id).metrics)
        completion = [float(metric.value) for metric in metrics if metric.name == "completion_time"]
        success = [float(bool(metric.value)) for metric in metrics if metric.name == "task_success"]
        comparison_id = "cmp-" + stable_hash(request.model_dump(mode="json"))[:12]
        statistics = {
            "mean": _mean(completion),
            "median": _median(completion),
            "min": min(completion) if completion else 0.0,
            "max": max(completion) if completion else 0.0,
            "standard_deviation": _stddev(completion),
            "success_rate": _mean(success),
            "failure_rate": 1.0 - _mean(success) if success else 0.0,
            "percentile": {"p95": _percentile(completion, 0.95)},
            "paired_delta": _paired_delta(metrics),
            "relative_delta": _relative_delta(metrics),
        }
        response = ComparisonResponse(
            comparison_id=comparison_id,
            comparison_type=request.comparison_type,
            statistics=statistics,
            metrics=metrics,
            warnings=[] if runs else ["no matching runs"],
        )
        self._comparisons[comparison_id] = response
        self._write_comparison_artifact(response)
        self._publish(
            "comparison_ready", comparison_id, {"comparison_type": request.comparison_type}
        )
        return response

    def export(self, request: ExportRequest) -> ExportResponse:
        """导出 metrics CSV 或 manifest JSON，并对预览内容脱敏。"""
        export_id = "export-" + stable_hash(request.model_dump(mode="json"))[:12]
        self.exports_root.mkdir(parents=True, exist_ok=True)
        if request.export_type == "Metrics CSV":
            relative = Path("phase11") / "exports" / export_id / "metrics.csv"
            path = self.artifact_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            rows = [
                metric
                for run_id in request.run_ids
                for metric in self.runtime.metrics_for(run_id).metrics
            ]
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "name",
                        "value",
                        "unit",
                        "source",
                        "aggregation",
                        "sample_count",
                        "backend",
                        "scenario",
                        "seed",
                        "control_mode",
                    ],
                    lineterminator="\n",
                )
                writer.writeheader()
                for metric in rows:
                    writer.writerow(metric.model_dump(mode="json"))
            preview = path.read_text(encoding="utf-8")[:500]
        else:
            relative = Path("phase11") / "exports" / export_id / "manifest.json"
            path = self.artifact_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "export_type": request.export_type,
                "run_ids": request.run_ids,
                "batch_id": request.batch_id,
                "comparison_id": request.comparison_id,
            }
            path.write_text(
                json.dumps(redact(payload), sort_keys=True, indent=2) + "\n", encoding="utf-8"
            )
            preview = path.read_text(encoding="utf-8")[:500]
        return ExportResponse(
            export_id=export_id,
            format=request.export_type,
            relative_path=relative.as_posix(),
            redacted=True,
            content_preview=str(redact(preview)),
        )

    def _execute_run(self, run_id: str) -> None:
        record = self._runs[run_id]
        draft = self._drafts[run_id]
        self._update_run(run_id, status=SimulationRunStatus.VALIDATING)
        self._append_event(run_id, "experiment_started", {"backend": draft.backend.value})
        if record.blockers:
            self._append_event(run_id, "backend_blocked", {"blockers": record.blockers})
            self._finalize_blocked(run_id)
            return
        self._update_run(
            run_id,
            status=SimulationRunStatus.STARTING,
            started_at=datetime.now(UTC),
        )
        self._update_run(run_id, status=SimulationRunStatus.RUNNING)
        try:
            if draft.backend == SimulationBackend.MOCK:
                self._run_mock(run_id)
            elif draft.backend == SimulationBackend.MUJOCO:
                self._run_mujoco(run_id)
            elif draft.backend == SimulationBackend.ISAAC_SIM:
                self._finalize_blocked(
                    run_id, blockers=["Isaac Sim is not started by Phase 11 API"]
                )
            elif draft.backend == SimulationBackend.MOVEIT_DRY_RUN:
                self._finalize_blocked(
                    run_id,
                    blockers=["MoveIt dry-run is visible but not executed by Phase 11 workbench"],
                )
        except Exception as exc:  # pragma: no cover - defensive artifact surface
            self._append_event(run_id, "run_failed", {"error": f"{type(exc).__name__}: {exc}"})
            self._update_run(
                run_id,
                status=SimulationRunStatus.FAILED,
                completed_at=datetime.now(UTC),
                blockers=[f"{type(exc).__name__}: {exc}"],
            )
        else:
            if self._runs[run_id].status not in _terminal_statuses():
                self._update_run(run_id, status=SimulationRunStatus.FINALIZING)
                self._write_run_artifacts(run_id)
                self._append_event(run_id, "artifact_created", self._runs[run_id].artifact_paths)
                self._update_run(
                    run_id,
                    status=SimulationRunStatus.SUCCEEDED,
                    completed_at=datetime.now(UTC),
                )
        self._publish(
            "run_state",
            run_id,
            {"status": self._runs[run_id].status.value},
        )

    def _run_mock(self, run_id: str) -> None:
        record = self._runs[run_id]
        draft = self._drafts[run_id]
        run_dir = self.runs_root / run_id
        config = _experiment_config(draft, record, run_dir)
        execution = ExperimentRunner(config).run()
        self._results[run_id] = execution.result
        self._append_runner_events(run_id, execution.events)
        self._append_event(
            run_id,
            "task_completed",
            {
                "status": execution.result.result_status.value,
                "success": execution.result.task_success,
            },
        )
        self._metrics[run_id] = _metrics_from_result(
            execution.result,
            backend=draft.backend,
            scenario_id=record.scenario_id,
            control_mode=record.control_mode,
            seed=record.seed,
            reproducibility_hash=record.manifest.reproducibility_hash,
        )

    def _run_mujoco(self, run_id: str) -> None:
        record = self._runs[run_id]
        draft = self._drafts[run_id]
        randomization_level = draft.domain_randomization.level or "NONE"
        trial = run_mujoco_physical_trial(
            record.scenario_id,
            seed=record.seed,
            randomization_level=randomization_level,
        )
        self._results[run_id] = {"trial": asdict(trial), "status": "SUCCEEDED"}
        self._append_event(
            run_id,
            "task_completed",
            {"status": "SUCCESS", "result_hash": trial.result_hash},
        )
        self._metrics[run_id] = _metrics_from_trial(
            trial.metrics,
            backend=draft.backend,
            scenario_id=record.scenario_id,
            control_mode=record.control_mode,
            seed=record.seed,
            reproducibility_hash=record.manifest.reproducibility_hash,
        )

    def _finalize_blocked(self, run_id: str, blockers: list[str] | None = None) -> None:
        record = self._runs[run_id]
        merged = [*record.blockers, *(blockers or [])]
        self._update_run(
            run_id,
            status=SimulationRunStatus.BLOCKED_BY_ENV,
            blockers=merged,
            completed_at=datetime.now(UTC),
        )
        self._metrics[run_id] = []
        self._write_run_artifacts(run_id)
        self._append_event(run_id, "artifact_created", self._runs[run_id].artifact_paths)

    def _write_run_artifacts(self, run_id: str) -> dict[str, str]:
        record = self._runs[run_id]
        run_dir = self.runs_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        paths = {
            "run_manifest": run_dir / "run_manifest.json",
            "events": run_dir / "events.jsonl",
            "metrics": run_dir / "metrics.json",
            "logs": run_dir / "logs.json",
            "result": run_dir / "result.json",
            "provenance": run_dir / "provenance.json",
        }
        paths["run_manifest"].write_text(
            json.dumps(record.manifest.model_dump(mode="json"), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        with paths["events"].open("w", encoding="utf-8") as handle:
            for event in self._events[run_id]:
                handle.write(event.model_dump_json() + "\n")
        paths["metrics"].write_text(
            json.dumps(
                [metric.model_dump(mode="json") for metric in self._metrics[run_id]],
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
        result = self._results.get(run_id, {})
        if isinstance(result, ExperimentResult):
            result_payload: dict[str, Any] = result.model_dump(mode="json")
        else:
            result_payload = dict(result)
        result_payload.update(
            {
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
            json.dumps(record.provenance, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        relative = {
            name: path.relative_to(self.artifact_root).as_posix() for name, path in paths.items()
        }
        self._update_run(run_id, artifact_paths=relative)
        return relative

    def _write_batch_artifacts(
        self,
        batch_id: str,
        manifest: ExperimentManifest,
        run_ids: list[str],
    ) -> dict[str, str]:
        batch_dir = self.batches_root / batch_id
        batch_dir.mkdir(parents=True, exist_ok=True)
        paths = {
            "batch_manifest": batch_dir / "batch_manifest.json",
            "run_index": batch_dir / "run_index.json",
            "summary": batch_dir / "summary.json",
            "summary_csv": batch_dir / "summary.csv",
            "comparison": batch_dir / "comparison.json",
            "report": batch_dir / "report.md",
        }
        paths["batch_manifest"].write_text(
            json.dumps(manifest.model_dump(mode="json"), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        paths["run_index"].write_text(
            json.dumps({"run_ids": run_ids}, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        progress = _batch_progress([self._runs[run_id] for run_id in run_ids])
        paths["summary"].write_text(
            json.dumps(progress.model_dump(mode="json"), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        with paths["summary_csv"].open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["run_id", "status"], lineterminator="\n")
            writer.writeheader()
            for run_id in run_ids:
                writer.writerow({"run_id": run_id, "status": self._runs[run_id].status.value})
        paths["comparison"].write_text("{}\n", encoding="utf-8")
        paths["report"].write_text(
            "# Phase 11 Batch Report\n\n"
            "Simulation-only batch evidence. No real controller contact and no hardware motion.\n",
            encoding="utf-8",
        )
        return {
            name: path.relative_to(self.artifact_root).as_posix() for name, path in paths.items()
        }

    def _write_comparison_artifact(self, response: ComparisonResponse) -> None:
        path = self.comparisons_root / response.comparison_id / "comparison.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(response.model_dump_json(indent=2) + "\n", encoding="utf-8")

    def _manifest(self, draft: ExperimentDraft, *, run_count: int) -> ExperimentManifest:
        normalized = _normalized_config(draft)
        source_commit = git_sha()
        source_tree_hash = _source_tree_hash()
        reproducibility_hash = stable_hash(
            {
                "normalized_config": normalized,
                "source_commit": source_commit,
                "source_tree_hash": source_tree_hash,
            }
        )
        return ExperimentManifest(
            manifest_id="manifest-" + reproducibility_hash[:12],
            normalized_config=normalized,
            source_commit=source_commit,
            source_tree_hash=source_tree_hash,
            run_count=run_count,
            reproducibility_hash=reproducibility_hash,
        )

    def _append_runner_events(self, run_id: str, events: Iterable[ExperimentEvent]) -> None:
        for event in events:
            event_type = _event_type(event.event_type)
            self._append_event(
                run_id,
                event_type,
                {
                    "entity_id": event.entity_id,
                    "payload": event.payload,
                    "payload_hash": event.payload_hash,
                },
                virtual_time_ms=event.virtual_time_ms,
            )

    def _append_event(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        virtual_time_ms: int = 0,
        severity: str = "info",
    ) -> None:
        sequence = len(self._events[run_id]) + 1
        event = TimelineEvent(
            sequence=sequence,
            event_type=event_type,
            source="simulation_workbench",
            severity=severity,
            virtual_time_ms=virtual_time_ms,
            payload=redact(payload),
        )
        self._events[run_id].append(event)
        self._publish("timeline_event", run_id, event.model_dump(mode="json"))

    def _update_run(self, run_id: str, **updates: Any) -> SimulationRunRecord:
        current = self._runs[run_id]
        updated = current.model_copy(update={"updated_at": datetime.now(UTC), **updates}, deep=True)
        self._runs[run_id] = updated
        self._publish("run_state", run_id, {"status": updated.status.value})
        return updated

    def _publish(self, event_type: str, key: str, payload: dict[str, Any]) -> None:
        self.events.publish(
            event_type,
            "simulation_workbench",
            payload,
            experiment_id=key,
        )


def _scenario_view(scenario: Any) -> ScenarioDefinitionView:
    fault_types = [fault.fault_type.value for fault in scenario.scheduled_faults]
    return ScenarioDefinitionView(
        scenario_id=scenario.scenario_id,
        description=scenario.description,
        category=_scenario_category(scenario.scenario_id, fault_types),
        fault_types=fault_types,
        initial_world_state=dict(scenario.initial_world_state),
        scheduled_faults=[fault.model_dump(mode="json") for fault in scenario.scheduled_faults],
        expected_invariants=list(scenario.expected_invariants),
        allowed_result_statuses=[status.value for status in scenario.allowed_result_statuses],
        forbidden_result_statuses=[status.value for status in scenario.forbidden_result_statuses],
        maximum_virtual_duration_ms=scenario.maximum_virtual_duration_ms,
        backend_support={
            SimulationBackend.MOCK.value: BackendReadiness.READY,
            SimulationBackend.MUJOCO.value: BackendReadiness.READY,
            SimulationBackend.ISAAC_SIM.value: BackendReadiness.BLOCKED_BY_ENV,
            SimulationBackend.MOVEIT_DRY_RUN.value: BackendReadiness.NOT_CONFIGURED,
        },
    )


def _scenario_category(scenario_id: str, fault_types: list[str]) -> ScenarioCategory:
    if scenario_id == "S01_NORMAL_STATIC":
        return ScenarioCategory.NORMAL
    if any(item in fault_types for item in {"TARGET_MOVED", "OBSTACLE_INSERTED"}):
        return ScenarioCategory.SCENE_CHANGE
    if any(item in fault_types for item in {"TARGET_LOST", "PERCEPTION_DEGRADED"}):
        return ScenarioCategory.PERCEPTION
    if any(item in fault_types for item in {"NETWORK_DEGRADED", "NETWORK_OUTAGE"}):
        return ScenarioCategory.NETWORK
    if "CLOUD_UNAVAILABLE" in fault_types:
        return ScenarioCategory.CLOUD
    if "STALE_DUPLICATE_REORDERED_COMMAND" in fault_types:
        return ScenarioCategory.COMMAND
    if any(item.startswith("SKILL_CACHE") for item in fault_types):
        return ScenarioCategory.CACHE
    if "MODE_OSCILLATION_PRESSURE" in fault_types:
        return ScenarioCategory.MODE
    if "EMERGENCY_STOP" in fault_types:
        return ScenarioCategory.SAFETY
    return ScenarioCategory.RECOVERY


def _experiment_config(
    draft: ExperimentDraft, record: SimulationRunRecord, run_dir: Path
) -> ExperimentConfig:
    network_name = _network_profile_name(draft.network_profiles[0])
    fault_name = (
        draft.fault_profiles[0].name if draft.fault_profiles else record.scenario_id.lower()
    )
    supervision_period_ms = int(draft.parameter_overrides.get("supervision_period_ms", 300))
    timeout_ms = int(draft.parameter_overrides.get("timeout_ms", 30_000))
    cache_policy = CachePolicy(str(draft.parameter_overrides.get("cache_policy", "CACHE_ENABLED")))
    return ExperimentConfig(
        experiment_id=record.run_id,
        scenario_id=record.scenario_id,
        mode=ExperimentMode(record.control_mode),
        seed=record.seed,
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


def _metrics_from_result(
    result: ExperimentResult,
    *,
    backend: SimulationBackend,
    scenario_id: str,
    control_mode: str,
    seed: int,
    reproducibility_hash: str,
) -> list[SimulationMetric]:
    source = "ExperimentRunner"

    def metric(name: str, value: int | float | str | bool | Any, unit: str) -> SimulationMetric:
        """把 ExperimentRunner 字段转换为统一 SimulationMetric。"""
        return _metric(name, value, unit, source, backend, scenario_id, seed, control_mode)

    return [
        metric("task_success", result.task_success, ""),
        metric("completion_time", result.task_completion_time_ms, "ms"),
        metric("planning_time", 0, "ms"),
        metric("execution_time", result.task_completion_time_ms, "ms"),
        metric("cloud_calls", result.cloud_invocation_count, "count"),
        metric(
            "communication_count",
            result.command_count + result.telemetry_count,
            "count",
        ),
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
    source = "MuJoCoPhysicalTrial"

    def metric(name: str, value: int | float | str | bool | Any, unit: str) -> SimulationMetric:
        """把 MuJoCo trial 字段转换为统一 SimulationMetric。"""
        return _metric(name, value, unit, source, backend, scenario_id, seed, control_mode)

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


def _normalized_config(draft: ExperimentDraft) -> dict[str, Any]:
    payload = draft.model_dump(mode="json")
    payload["scenarios"] = sorted(payload["scenarios"])
    payload["control_modes"] = sorted(payload["control_modes"])
    payload["seeds"] = sorted(payload["seeds"])
    return payload


def _run_count(draft: ExperimentDraft) -> int:
    return len(draft.scenarios) * len(draft.control_modes) * len(draft.seeds) * draft.repetitions


def _validate_scenarios(scenarios: list[str]) -> None:
    known = {scenario.scenario_id for scenario in scenario_registry()}
    unknown = sorted(set(scenarios).difference(known))
    if unknown:
        raise ValueError(f"unknown scenario: {unknown[0]}")


def _backend_blockers(
    backend: SimulationBackend,
    capabilities: SimulationCapabilitiesResponse,
) -> list[str]:
    for item in capabilities.backends:
        if item.backend == backend:
            return list(item.blockers) if item.readiness != BackendReadiness.READY else []
    return ["backend is not known"]


def _provenance(manifest: ExperimentManifest) -> dict[str, Any]:
    return {
        "source_commit": manifest.source_commit,
        "source_tree_hash": manifest.source_tree_hash,
        "generated_at": datetime.now(UTC).isoformat(),
        "config_hash": stable_hash(manifest.normalized_config),
        "real_controller_contacted": False,
        "hardware_motion_observed": False,
        "hardware_write_operations": [],
    }


def _source_tree_hash() -> str:
    try:
        return current_source_tree_hash()
    except Exception:
        return hashlib.sha256(b"unknown-source-tree").hexdigest()


def _event_type(raw: str) -> str:
    mapping = {
        "run_started": "experiment_started",
        "run_completed": "task_completed",
        "fault_injected": "fault_injected",
        "fault_detected": "fault_detected",
        "network_degraded": "network_degraded",
        "pcsc_tick": "supervision_tick",
        "safety_decision": "SafetyShield allow/reject",
    }
    if raw in mapping:
        return mapping[raw]
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


def _batch_progress(runs: list[SimulationRunRecord]) -> BatchProgress:
    total = len(runs)
    queued = sum(1 for run in runs if run.status == SimulationRunStatus.QUEUED)
    running = sum(
        1
        for run in runs
        if run.status
        in {
            SimulationRunStatus.VALIDATING,
            SimulationRunStatus.STARTING,
            SimulationRunStatus.RUNNING,
            SimulationRunStatus.FINALIZING,
        }
    )
    succeeded = sum(1 for run in runs if run.status == SimulationRunStatus.SUCCEEDED)
    failed = sum(1 for run in runs if run.status == SimulationRunStatus.FAILED)
    blocked = sum(1 for run in runs if run.status == SimulationRunStatus.BLOCKED_BY_ENV)
    cancelled = sum(1 for run in runs if run.status == SimulationRunStatus.CANCELLED)
    done = succeeded + failed + blocked + cancelled
    return BatchProgress(
        total=total,
        queued=queued,
        running=running,
        succeeded=succeeded,
        failed=failed,
        blocked=blocked,
        cancelled=cancelled,
        progress_ratio=done / total if total else 0.0,
    )


def _batch_status(progress: BatchProgress) -> SimulationRunStatus:
    if progress.cancelled:
        return SimulationRunStatus.CANCELLED
    if progress.failed:
        return SimulationRunStatus.FAILED
    if progress.blocked and progress.blocked == progress.total:
        return SimulationRunStatus.BLOCKED_BY_ENV
    if progress.succeeded + progress.blocked == progress.total:
        return SimulationRunStatus.SUCCEEDED
    if progress.running:
        return SimulationRunStatus.RUNNING
    return SimulationRunStatus.QUEUED


def _terminal_statuses() -> set[SimulationRunStatus]:
    return {
        SimulationRunStatus.SUCCEEDED,
        SimulationRunStatus.FAILED,
        SimulationRunStatus.CANCELLED,
        SimulationRunStatus.BLOCKED_BY_ENV,
    }


def _export_formats() -> list[str]:
    return [
        "Manifest JSON",
        "Metrics CSV",
        "Events JSONL",
        "Comparison CSV",
        "Chart PNG",
        "Chart SVG",
        "Markdown report",
        "Paper table CSV",
        "Reproducibility bundle manifest",
    ]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def _paired_delta(metrics: list[SimulationMetric]) -> float:
    by_mode = {
        metric.control_mode: float(metric.value)
        for metric in metrics
        if metric.name == "completion_time" and isinstance(metric.value, int | float)
    }
    if len(by_mode) < 2:
        return 0.0
    values = list(by_mode.values())
    return values[1] - values[0]


def _relative_delta(metrics: list[SimulationMetric]) -> float:
    by_mode = {
        metric.control_mode: float(metric.value)
        for metric in metrics
        if metric.name == "completion_time" and isinstance(metric.value, int | float)
    }
    if len(by_mode) < 2:
        return 0.0
    values = list(by_mode.values())
    return (values[1] - values[0]) / values[0] if values[0] else 0.0


def build_cross_backend_preview(scenario_id: str, seed: int) -> dict[str, object]:
    """构造跨后端预览结果，Isaac 不可用时保持 BLOCKED 语义。"""
    env = detect_environment()
    return compare_backend_results(
        scenario_id=scenario_id,
        seed=seed,
        isaac_ready=env.level == "ISAAC_READY",
    )


def parse_draft(payload: dict[str, Any]) -> ExperimentDraft:
    """将 API payload 解析为 ExperimentDraft，保留 Pydantic 校验错误。"""
    try:
        return ExperimentDraft.model_validate(payload)
    except ValidationError:
        raise
