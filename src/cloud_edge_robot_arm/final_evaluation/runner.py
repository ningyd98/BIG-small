"""Phase 12 固定评估 runner。

runner 只执行最终评估的受控软件/仿真路径。smoke profile 生成明确标记的
SYNTHETIC_PIPELINE_SAMPLE；validation/full profile 调用固定 allowlist adapter，
环境依赖项不可用时记录 BLOCKED_BY_ENV，不回退到 Mock 冒充 Isaac、Ollama 或真实后端。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from cloud_edge_robot_arm.final_evaluation.adapters import runner_adapter_registry
from cloud_edge_robot_arm.final_evaluation.adapters.base import (
    Phase12AdapterResult,
    Phase12RunContext,
    sha256_path,
)
from cloud_edge_robot_arm.final_evaluation.models import (
    BlockerStage,
    EnvironmentStatus,
    ExecutionSource,
    HardwareClaims,
    MetricProvenance,
    MetricSource,
    Phase12Backend,
    Phase12Profile,
    Phase12Result,
    Phase12RunManifest,
    Phase12RunStatus,
)
from cloud_edge_robot_arm.final_evaluation.provenance import (
    environment_hash,
    git_commit,
    source_tree_hash,
    stable_hash,
    worktree_clean,
)
from cloud_edge_robot_arm.final_evaluation.registry import build_experiment_plan


def run_phase12_experiments(profile: Phase12Profile, output_root: Path) -> dict[str, object]:
    """运行 Phase 12 profile 并写出 manifests、raw runs、events 和 provenance。"""

    output_root.mkdir(parents=True, exist_ok=True)
    for subdir in ("manifests", "runs", "reports"):
        (output_root / subdir).mkdir(parents=True, exist_ok=True)
    plan = build_experiment_plan(profile)
    rows: list[Phase12Result] = []
    manifests: list[Phase12RunManifest] = []
    commit = git_commit()
    tree_hash = source_tree_hash()
    clean = worktree_clean()
    env_hash = environment_hash()
    started_at = datetime.now(UTC)
    run_index = 0
    adapters = runner_adapter_registry()
    for experiment in plan.experiments:
        seeds = _seeds_for_profile(experiment, profile)
        repetitions = _repetitions_for_profile(experiment, profile)
        for scenario_id in experiment.scenario_ids:
            for backend in experiment.backends:
                for mode in experiment.control_modes:
                    for seed in seeds:
                        for repetition in range(repetitions):
                            run_index += 1
                            manifest = _manifest(
                                run_index=run_index,
                                profile=profile,
                                experiment_id=experiment.experiment_id,
                                research_question=experiment.research_question,
                                backend=backend,
                                scenario_id=scenario_id,
                                mode=mode,
                                seed=seed,
                                repetition=repetition,
                                commit=commit,
                                tree_hash=tree_hash,
                                clean=clean,
                                env_hash=env_hash,
                            )
                            if profile == Phase12Profile.SMOKE:
                                result = _result_from_manifest(manifest, experiment.title)
                            else:
                                context = Phase12RunContext(
                                    run_id=manifest.run_id,
                                    experiment_id=experiment.experiment_id,
                                    scenario_id=scenario_id,
                                    backend=backend,
                                    control_mode=mode,
                                    seed=seed,
                                    repetition=repetition,
                                    output_root=output_root,
                                    planner_provider=_planner_provider_for(
                                        experiment.experiment_id, seed, repetition, mode
                                    ),
                                    model_name=_model_name_for(
                                        experiment.experiment_id, seed, repetition, mode
                                    ),
                                )
                                adapter = adapters[
                                    _runner_kind_for(experiment.runner_kind, backend)
                                ]
                                adapter_result = adapter.run(context)
                                authoritative = _authoritative_for_thesis(
                                    manifest, adapter_result, output_root=output_root
                                )
                                manifest = manifest.model_copy(
                                    update={
                                        **_source_fields(adapter_result),
                                        "authoritative_for_thesis": authoritative,
                                    },
                                    deep=True,
                                )
                                result = _result_from_adapter(
                                    manifest, adapter_result, authoritative_for_thesis=authoritative
                                )
                            manifests.append(manifest)
                            rows.append(result)
    manifests, rows = _normalize_source_artifact_hashes(output_root, manifests, rows)
    _write_jsonl(
        output_root / "manifests/run_manifests.jsonl",
        [m.model_dump(mode="json") for m in manifests],
    )
    _write_jsonl(output_root / "runs/raw_runs.jsonl", [r.model_dump(mode="json") for r in rows])
    _write_jsonl(output_root / "runs/events.jsonl", [_event(row) for row in rows])
    provenance = {
        "profile": profile.value,
        "source_commit": commit,
        "source_tree_hash": tree_hash,
        "worktree_clean": clean,
        "environment_hash": env_hash,
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(UTC).isoformat(),
        "hardware_claims": HardwareClaims().model_dump(mode="json"),
        "execution_source_counts": _execution_source_counts(rows),
    }
    _write_json(output_root / "manifests/provenance.json", provenance)
    summary: dict[str, object] = {
        "profile": profile.value,
        "run_count": len(rows),
        "blocked_by_env_count": sum(
            1 for row in rows if row.status == Phase12RunStatus.BLOCKED_BY_ENV
        ),
        "synthetic_sample_count": sum(
            1 for row in rows if row.execution_source == ExecutionSource.SYNTHETIC_PIPELINE_SAMPLE
        ),
        "actual_run_count": sum(1 for row in rows if row.runtime_invoked),
        "adapter_attempt_count": sum(1 for row in rows if row.adapter_attempted),
        "runtime_invocation_count": sum(1 for row in rows if row.runtime_invoked),
        "runtime_completion_count": sum(1 for row in rows if row.runtime_completed),
        "blocked_before_runtime_count": sum(
            1
            for row in rows
            if row.status == Phase12RunStatus.BLOCKED_BY_ENV
            and row.environment_check_completed
            and not row.runtime_invoked
        ),
        "authoritative_thesis_run_count": sum(1 for row in rows if row.authoritative_for_thesis),
        "actual_backend_counts": _actual_backend_counts(rows),
        "runtime_backend_counts": _runtime_backend_counts(rows),
        "unsafe_command_execution_count": sum(row.unsafe_command_execution_count for row in rows),
        "hardware_claims": HardwareClaims().model_dump(mode="json"),
        "artifact_hash": stable_hash([row.result_hash for row in rows]),
    }
    _write_json(output_root / "runs/run_summary.json", summary)
    return summary


def _manifest(
    *,
    run_index: int,
    profile: Phase12Profile,
    experiment_id: str,
    research_question: str,
    backend: Phase12Backend,
    scenario_id: str,
    mode: str,
    seed: int,
    repetition: int,
    commit: str,
    tree_hash: str,
    clean: bool,
    env_hash: str,
) -> Phase12RunManifest:
    config = {
        "experiment_id": experiment_id,
        "backend": backend.value,
        "scenario_id": scenario_id,
        "control_mode": mode,
        "seed": seed,
        "repetition": repetition,
        "profile": profile.value,
    }
    return Phase12RunManifest(
        run_id=f"phase12-{run_index:05d}",
        experiment_id=experiment_id,
        research_question=research_question,
        profile=profile,
        backend=backend,
        scenario_id=scenario_id,
        control_mode=mode,
        seed=seed,
        repetition=repetition,
        source_commit=commit,
        source_tree_hash=tree_hash,
        worktree_clean=clean,
        config_hash=stable_hash(config),
        environment_hash=env_hash,
        planner_provider=_planner_provider_for(experiment_id, seed, repetition, mode),
        model_name=_model_name_for(experiment_id, seed, repetition, mode),
        completed_at=datetime.now(UTC),
    )


def _planner_provider_for(experiment_id: str, seed: int, repetition: int, mode: str) -> str:
    if experiment_id != "F16_PLANNER_PROVIDER_COMPARISON":
        return "NONE"
    providers = ["MOCK", "RULE_BASED", "OPENAI_COMPATIBLE", "OLLAMA"]
    mode_offset = {"PCSC": 0, "ETEAC": 1, "AUTO": 2}[mode]
    return providers[(seed + repetition + mode_offset) % len(providers)]


def _model_name_for(experiment_id: str, seed: int, repetition: int, mode: str) -> str:
    provider = _planner_provider_for(experiment_id, seed, repetition, mode)
    return {
        "MOCK": "mock-planner",
        "RULE_BASED": "rule-based",
        "OPENAI_COMPATIBLE": "not-configured",
        "OLLAMA": "not-installed",
        "NONE": "",
    }[provider]


def _runner_kind_for(experiment_runner_kind: str, backend: Phase12Backend) -> str:
    """Select the fixed allowlisted runner matching the row backend."""

    if backend == Phase12Backend.MUJOCO:
        return "PHASE9_MUJOCO"
    if backend == Phase12Backend.ISAAC_SIM:
        return "PHASE9_2_ISAAC"
    if backend == Phase12Backend.SYNTHETIC_DRY_RUN:
        return "PHASE10_SYNTHETIC_DRY_RUN"
    if backend == Phase12Backend.MOVEIT_DRY_RUN:
        return "PHASE10_MOVEIT_RUNTIME_DRY_RUN"
    if backend == Phase12Backend.PLANNER_DRY_RUN:
        return "PHASE11_2_PLANNER_DRY_RUN"
    return experiment_runner_kind


def _result_from_adapter(
    manifest: Phase12RunManifest,
    adapter_result: Phase12AdapterResult,
    *,
    authoritative_for_thesis: bool | None = None,
) -> Phase12Result:
    metrics = adapter_result.metrics
    result_hash = str(metrics.get("result_hash") or stable_hash(metrics))
    artifact_hash = str(metrics.get("artifact_hash") or adapter_result.source_artifact_hash)
    row_authoritative = (
        _authoritative_for_thesis(manifest, adapter_result)
        if authoritative_for_thesis is None
        else authoritative_for_thesis
    )
    return Phase12Result(
        run_id=manifest.run_id,
        experiment_id=manifest.experiment_id,
        research_question=manifest.research_question,
        profile=manifest.profile,
        backend=manifest.backend,
        scenario_id=manifest.scenario_id,
        control_mode=manifest.control_mode,
        seed=manifest.seed,
        repetition=manifest.repetition,
        status=adapter_result.status,
        task_success=adapter_result.task_success,
        failure_type=adapter_result.failure_type,
        task_completion_rate=float(metrics.get("task_completion_rate", 0.0)),
        total_completion_time_ms=float(metrics.get("total_completion_time_ms", 0.0)),
        cloud_planning_time_ms=float(metrics.get("cloud_planning_time_ms", 0.0)),
        edge_execution_time_ms=float(metrics.get("edge_execution_time_ms", 0.0)),
        local_recovery_time_ms=float(metrics.get("local_recovery_time_ms", 0.0)),
        replanning_time_ms=float(metrics.get("replanning_time_ms", 0.0)),
        communication_wait_time_ms=float(metrics.get("communication_wait_time_ms", 0.0)),
        cloud_invocation_count=int(metrics.get("cloud_invocation_count", 0)),
        communication_count=int(metrics.get("communication_count", 0)),
        uploaded_bytes=int(metrics.get("uploaded_bytes", 0)),
        downloaded_bytes=int(metrics.get("downloaded_bytes", 0)),
        supervision_count=int(metrics.get("supervision_count", 0)),
        mode_switch_count=int(metrics.get("mode_switch_count", 0)),
        local_retry_count=int(metrics.get("local_retry_count", 0)),
        local_recovery_success_count=int(metrics.get("local_recovery_success_count", 0)),
        replan_count=int(metrics.get("replan_count", 0)),
        cloud_fallback_count=int(metrics.get("cloud_fallback_count", 0)),
        completed_without_cloud_after_start=bool(
            metrics.get("completed_without_cloud_after_start", False)
        ),
        safety_intervention_count=int(metrics.get("safety_intervention_count", 0)),
        rejected_action_count=int(metrics.get("rejected_action_count", 0)),
        stale_telemetry_rejection=int(metrics.get("stale_telemetry_rejection", 0)),
        workspace_rejection=int(metrics.get("workspace_rejection", 0)),
        collision_rejection=int(metrics.get("collision_rejection", 0)),
        emergency_stop_event=int(metrics.get("emergency_stop_event", 0)),
        unsafe_command_execution_count=int(metrics.get("unsafe_command_execution_count", 0)),
        restart_recovery_success=bool(metrics.get("restart_recovery_success", True)),
        duplicate_execution_count=int(metrics.get("duplicate_execution_count", 0)),
        lease_recovery_count=int(metrics.get("lease_recovery_count", 0)),
        artifact_consistency=bool(metrics.get("artifact_consistency", True)),
        event_loss_count=int(metrics.get("event_loss_count", 0)),
        paired_success_agreement=_optional_bool(metrics.get("paired_success_agreement")),
        completion_time_delta=_optional_float(metrics.get("completion_time_delta")),
        planner_success=bool(metrics.get("planner_success", adapter_result.task_success)),
        valid_contract_rate=float(metrics.get("valid_contract_rate", 1.0)),
        repair_count=int(metrics.get("repair_count", 0)),
        refusal_rate=float(metrics.get("refusal_rate", 0.0)),
        response_latency_ms=float(metrics.get("response_latency_ms", 0.0)),
        result_hash=result_hash,
        artifact_hash=artifact_hash,
        execution_source=adapter_result.execution_source,
        actual_runner_invoked=adapter_result.actual_runner_invoked,
        adapter_attempted=adapter_result.adapter_attempted,
        environment_check_completed=adapter_result.environment_check_completed,
        runtime_invoked=adapter_result.runtime_invoked,
        runtime_completed=adapter_result.runtime_completed,
        authoritative_for_thesis=row_authoritative,
        blocker_stage=adapter_result.blocker_stage,
        source_artifact_path=adapter_result.source_artifact_path,
        source_artifact_hash=adapter_result.source_artifact_hash,
        source_verifier=adapter_result.source_verifier,
        environment_status=adapter_result.environment_status,
        metric_provenance=adapter_result.metric_provenance,
        planner_provider=adapter_result.planner_provider,
        model_name=adapter_result.model_name,
        hardware_claims=adapter_result.hardware_claims,
    )


def _result_from_manifest(manifest: Phase12RunManifest, title: str) -> Phase12Result:
    status = _status_for(manifest)
    success = status == Phase12RunStatus.SUCCESS
    base = 900 + manifest.seed * 17 + manifest.repetition * 11 + len(manifest.scenario_id) * 3
    mode_factor = {"PCSC": 180, "ETEAC": 80, "AUTO": 120}.get(manifest.control_mode, 100)
    backend_factor = {
        Phase12Backend.MOCK: 0,
        Phase12Backend.MUJOCO: 90,
        Phase12Backend.ISAAC_SIM: 140,
        Phase12Backend.MOVEIT_DRY_RUN: 220,
        Phase12Backend.SYNTHETIC_DRY_RUN: 40,
        Phase12Backend.PLANNER_DRY_RUN: 30,
    }[manifest.backend]
    scenario_penalty = (
        260 if "S14" in manifest.scenario_id else 160 if "S07" in manifest.scenario_id else 90
    )
    total_time = float(base + mode_factor + backend_factor + scenario_penalty)
    cloud_calls = {"PCSC": 4, "AUTO": 2, "ETEAC": 1}.get(manifest.control_mode, 1)
    if manifest.experiment_id in {"F10_LOCAL_RECOVERY", "F17_ABLATION_RECOVERY"}:
        recovery_success = success and manifest.experiment_id == "F10_LOCAL_RECOVERY"
        retry_count = 2
    else:
        recovery_success = success
        retry_count = 1 if "S04" in manifest.scenario_id else 0
    safety_interventions = (
        1
        if manifest.experiment_id in {"F12_SAFETY_REJECTION", "F19_ABLATION_SAFETY"}
        or "S14" in manifest.scenario_id
        else 0
    )
    unsafe_count = 0
    payload = {
        "run_id": manifest.run_id,
        "status": status.value,
        "title": title,
        "time": total_time,
        "success": success,
    }
    result_hash = stable_hash(payload)
    return Phase12Result(
        run_id=manifest.run_id,
        experiment_id=manifest.experiment_id,
        research_question=manifest.research_question,
        profile=manifest.profile,
        backend=manifest.backend,
        scenario_id=manifest.scenario_id,
        control_mode=manifest.control_mode,
        seed=manifest.seed,
        repetition=manifest.repetition,
        status=status,
        task_success=success,
        failure_type="" if success else status.value,
        task_completion_rate=1.0
        if success
        else 0.0
        if status == Phase12RunStatus.BLOCKED_BY_ENV
        else 0.5,
        total_completion_time_ms=total_time,
        cloud_planning_time_ms=float(cloud_calls * 55),
        edge_execution_time_ms=total_time * 0.55,
        local_recovery_time_ms=120.0 if recovery_success else 0.0,
        replanning_time_ms=180.0
        if manifest.experiment_id in {"F11_LOCAL_REPLANNING", "F18_ABLATION_REPLANNING"}
        else 0.0,
        communication_wait_time_ms=90.0 if "NETWORK" in manifest.experiment_id else 20.0,
        cloud_invocation_count=cloud_calls,
        communication_count=cloud_calls * 2 + retry_count,
        uploaded_bytes=512 + cloud_calls * 160,
        downloaded_bytes=256 + cloud_calls * 120,
        supervision_count=cloud_calls,
        mode_switch_count=1 if manifest.control_mode == "AUTO" else 0,
        local_retry_count=retry_count,
        local_recovery_success_count=1 if recovery_success and retry_count else 0,
        replan_count=1
        if manifest.experiment_id in {"F11_LOCAL_REPLANNING", "F18_ABLATION_REPLANNING"}
        else 0,
        cloud_fallback_count=1
        if manifest.experiment_id == "F07_CLOUD_INTERRUPTION" and manifest.control_mode != "ETEAC"
        else 0,
        completed_without_cloud_after_start=manifest.control_mode == "ETEAC" and success,
        safety_intervention_count=safety_interventions,
        rejected_action_count=safety_interventions,
        stale_telemetry_rejection=1 if manifest.experiment_id == "F12_SAFETY_REJECTION" else 0,
        workspace_rejection=1
        if manifest.experiment_id in {"F09_OBSTACLE_CHANGE", "F12_SAFETY_REJECTION"}
        else 0,
        collision_rejection=1 if manifest.experiment_id == "F12_SAFETY_REJECTION" else 0,
        emergency_stop_event=1 if "S14" in manifest.scenario_id else 0,
        unsafe_command_execution_count=unsafe_count,
        restart_recovery_success=manifest.experiment_id == "F20_STRESS_AND_RECOVERY" or success,
        duplicate_execution_count=0,
        lease_recovery_count=1 if manifest.experiment_id == "F20_STRESS_AND_RECOVERY" else 0,
        artifact_consistency=True,
        event_loss_count=0,
        paired_success_agreement=True
        if manifest.experiment_id == "F15_MUJOCO_ISAAC_PAIRED"
        and status != Phase12RunStatus.BLOCKED_BY_ENV
        else None,
        completion_time_delta=50.0
        if manifest.experiment_id == "F15_MUJOCO_ISAAC_PAIRED"
        and manifest.backend == Phase12Backend.MUJOCO
        else None,
        planner_success=status == Phase12RunStatus.SUCCESS,
        valid_contract_rate=1.0 if status == Phase12RunStatus.SUCCESS else 0.0,
        repair_count=1 if manifest.experiment_id == "F16_PLANNER_PROVIDER_COMPARISON" else 0,
        refusal_rate=0.0,
        response_latency_ms=180.0
        if manifest.experiment_id == "F16_PLANNER_PROVIDER_COMPARISON"
        else 0.0,
        result_hash=result_hash,
        artifact_hash=stable_hash(
            {"manifest": manifest.model_dump(mode="json"), "result": result_hash}
        ),
        execution_source=ExecutionSource.SYNTHETIC_PIPELINE_SAMPLE,
        actual_runner_invoked=False,
        adapter_attempted=False,
        environment_check_completed=False,
        runtime_invoked=False,
        runtime_completed=False,
        authoritative_for_thesis=False,
        blocker_stage=BlockerStage.NONE
        if status != Phase12RunStatus.BLOCKED_BY_ENV
        else BlockerStage.ENVIRONMENT_CHECK,
        source_artifact_path="",
        source_artifact_hash="",
        source_verifier="phase12.synthetic_pipeline",
        environment_status=EnvironmentStatus.READY
        if status != Phase12RunStatus.BLOCKED_BY_ENV
        else EnvironmentStatus.BLOCKED_BY_ENV,
        metric_provenance=_synthetic_metric_provenance(),
        planner_provider=manifest.planner_provider,
        model_name=manifest.model_name,
        hardware_claims=HardwareClaims(),
    )


def _status_for(manifest: Phase12RunManifest) -> Phase12RunStatus:
    if manifest.backend == Phase12Backend.ISAAC_SIM:
        return Phase12RunStatus.BLOCKED_BY_ENV
    if (
        manifest.experiment_id == "F16_PLANNER_PROVIDER_COMPARISON"
        and manifest.profile != Phase12Profile.SMOKE
    ):
        return Phase12RunStatus.SUCCESS
    if "S14" in manifest.scenario_id or manifest.experiment_id == "F12_SAFETY_REJECTION":
        return Phase12RunStatus.SAFETY_STOPPED
    if manifest.experiment_id == "F19_ABLATION_SAFETY":
        return Phase12RunStatus.SAFETY_STOPPED
    return Phase12RunStatus.SUCCESS


def _seeds_for_profile(experiment: object, profile: Phase12Profile) -> list[int]:
    if profile == Phase12Profile.SMOKE:
        return list(experiment.seeds_smoke)  # type: ignore[attr-defined]
    if profile == Phase12Profile.VALIDATION:
        return list(range(experiment.validation_seed_count))  # type: ignore[attr-defined]
    return list(range(experiment.sample_policy.seed_count))  # type: ignore[attr-defined]


def _repetitions_for_profile(experiment: object, profile: Phase12Profile) -> int:
    if profile == Phase12Profile.SMOKE:
        return 1
    if profile == Phase12Profile.VALIDATION:
        return 2
    return int(experiment.sample_policy.repetitions)  # type: ignore[attr-defined]


def _event(row: Phase12Result) -> dict[str, object]:
    return {
        "run_id": row.run_id,
        "event_type": "phase12_run_recorded",
        "status": row.status.value,
        "experiment_id": row.experiment_id,
        "execution_source": row.execution_source.value,
        "actual_runner_invoked": row.actual_runner_invoked,
        "adapter_attempted": row.adapter_attempted,
        "environment_check_completed": row.environment_check_completed,
        "runtime_invoked": row.runtime_invoked,
        "runtime_completed": row.runtime_completed,
        "blocker_stage": row.blocker_stage.value,
        "authoritative_for_thesis": row.authoritative_for_thesis,
        "timestamp": datetime.now(UTC).isoformat(),
        "hardware_motion_observed": False,
    }


def _source_fields(adapter_result: Phase12AdapterResult) -> dict[str, object]:
    return {
        "execution_source": adapter_result.execution_source,
        "actual_runner_invoked": adapter_result.actual_runner_invoked,
        "adapter_attempted": adapter_result.adapter_attempted,
        "environment_check_completed": adapter_result.environment_check_completed,
        "runtime_invoked": adapter_result.runtime_invoked,
        "runtime_completed": adapter_result.runtime_completed,
        "authoritative_for_thesis": adapter_result.authoritative_for_thesis,
        "blocker_stage": adapter_result.blocker_stage,
        "source_artifact_path": adapter_result.source_artifact_path,
        "source_artifact_hash": adapter_result.source_artifact_hash,
        "source_verifier": adapter_result.source_verifier,
        "environment_status": adapter_result.environment_status,
    }


def _authoritative_for_thesis(
    manifest: Phase12RunManifest,
    adapter_result: Phase12AdapterResult,
    *,
    output_root: Path | None = None,
) -> bool:
    """生成端论文权威 gate，避免 dirty provenance 或半完成 runtime 写成权威样本。"""

    base_gate = (
        manifest.worktree_clean
        and adapter_result.authoritative_for_thesis
        and adapter_result.runtime_invoked
        and adapter_result.runtime_completed
        and adapter_result.environment_status == EnvironmentStatus.READY
        and bool(adapter_result.source_artifact_path)
        and bool(adapter_result.source_artifact_hash)
    )
    if not base_gate:
        return False
    if output_root is None:
        return True
    return _source_artifact_hash_verified(output_root, adapter_result)


def _source_artifact_hash_verified(output_root: Path, adapter_result: Phase12AdapterResult) -> bool:
    """校验 adapter 声称的 source evidence 在输出根内且 hash 匹配。"""

    rel_path = Path(adapter_result.source_artifact_path)
    if rel_path.is_absolute():
        return False
    root = output_root.resolve()
    candidate = (root / rel_path).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return False
    return sha256_path(candidate) == adapter_result.source_artifact_hash


def _normalize_source_artifact_hashes(
    output_root: Path,
    manifests: list[Phase12RunManifest],
    rows: list[Phase12Result],
) -> tuple[list[Phase12RunManifest], list[Phase12Result]]:
    """写出最终行前按磁盘 source evidence 重新绑定 hash。

    Adapter 返回 hash 后，部分 runner 仍可能完成 artifact 清理或重写终态 evidence。
    这里以最终落盘文件为准更新 manifest/result，确保 verifier 的 source hash
    检查代表真实文件内容，而不是中间态 digest。
    """

    normalized_manifests = [
        _normalize_manifest_source_hash(output_root, manifest) for manifest in manifests
    ]
    normalized_rows = [_normalize_result_source_hash(output_root, row) for row in rows]
    return normalized_manifests, normalized_rows


def _normalize_manifest_source_hash(
    output_root: Path, manifest: Phase12RunManifest
) -> Phase12RunManifest:
    digest = _final_source_artifact_hash(output_root, manifest.source_artifact_path)
    if not digest:
        return manifest
    return manifest.model_copy(update={"source_artifact_hash": digest}, deep=True)


def _normalize_result_source_hash(output_root: Path, row: Phase12Result) -> Phase12Result:
    digest = _final_source_artifact_hash(output_root, row.source_artifact_path)
    if not digest:
        return row
    return row.model_copy(update={"source_artifact_hash": digest}, deep=True)


def _final_source_artifact_hash(output_root: Path, source_artifact_path: str) -> str:
    if not source_artifact_path:
        return ""
    rel_path = Path(source_artifact_path)
    if rel_path.is_absolute():
        return ""
    root = output_root.resolve()
    candidate = (root / rel_path).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return ""
    return sha256_path(candidate)


def _execution_source_counts(rows: list[Phase12Result]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.execution_source.value] = counts.get(row.execution_source.value, 0) + 1
    return counts


def _actual_backend_counts(rows: list[Phase12Result]) -> dict[str, int]:
    """兼容旧字段名；实际含义按 runtime_invoked 统计真实 runtime 调用。"""

    counts: dict[str, int] = {}
    for row in rows:
        if row.runtime_invoked:
            counts[row.backend.value] = counts.get(row.backend.value, 0) + 1
    return counts


def _runtime_backend_counts(rows: list[Phase12Result]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        if row.runtime_invoked:
            counts[row.backend.value] = counts.get(row.backend.value, 0) + 1
    return counts


def _synthetic_metric_provenance() -> dict[str, MetricProvenance]:
    return {
        "total_completion_time_ms": MetricProvenance(
            source=MetricSource.CONSTANT_PLACEHOLDER,
            source_field="phase12.synthetic_formula",
            source_artifact="",
            unit="ms",
        )
    }


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None


def _optional_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8"
    )


def _write_jsonl(path: Path, rows: list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in rows),
        encoding="utf-8",
    )
