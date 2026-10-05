"""Phase 12 固定实验注册表。

注册表是最终实验套件的权威来源。它只包含软件、仿真、dry-run 和 planner dry-run
runner，不接受任意 shell、脚本路径、环境变量、URL 或真实硬件 runner。
"""

from __future__ import annotations

from cloud_edge_robot_arm.final_evaluation.models import (
    HardwareClaims,
    Phase12Backend,
    Phase12ExperimentDefinition,
    Phase12ExperimentPlan,
    Phase12Profile,
    Phase12SamplePolicy,
)

PHASE12_EXPERIMENT_IDS = [
    f"F{index:02d}_{name}"
    for index, name in enumerate(
        [
            "PC_SC_BASELINE",
            "ETEAC_BASELINE",
            "AUTO_BASELINE",
            "NETWORK_LATENCY",
            "NETWORK_JITTER",
            "PACKET_LOSS",
            "CLOUD_INTERRUPTION",
            "TARGET_MOVEMENT",
            "OBSTACLE_CHANGE",
            "LOCAL_RECOVERY",
            "LOCAL_REPLANNING",
            "SAFETY_REJECTION",
            "SKILL_CACHE",
            "AUTO_POLICY",
            "MUJOCO_ISAAC_PAIRED",
            "PLANNER_PROVIDER_COMPARISON",
            "ABLATION_RECOVERY",
            "ABLATION_REPLANNING",
            "ABLATION_SAFETY",
            "STRESS_AND_RECOVERY",
        ],
        start=1,
    )
]

ALLOWLISTED_RUNNERS = {
    "PHASE8_EXPERIMENT_RUNNER",
    "PHASE9_MUJOCO",
    "PHASE9_2_ISAAC",
    "PHASE10_SYNTHETIC_DRY_RUN",
    "PHASE10_MOVEIT_RUNTIME_DRY_RUN",
    "PHASE11_SIMULATION_RUNTIME",
    "PHASE11_2_PLANNER_DRY_RUN",
}


def final_experiment_registry() -> list[Phase12ExperimentDefinition]:
    """返回 F01-F20 固定实验定义，顺序即论文和 verifier 使用的权威顺序。"""

    common_metrics = [
        "task_success",
        "total_completion_time_ms",
        "cloud_invocation_count",
        "communication_count",
        "safety_intervention_count",
        "unsafe_command_execution_count",
    ]
    return [
        _definition(
            "F01_PC_SC_BASELINE",
            "PCSC 正常静态基线",
            "RQ1",
            ["S01_NORMAL_STATIC"],
            [Phase12Backend.MOCK, Phase12Backend.MUJOCO],
            ["PCSC"],
            ["control_mode"],
            common_metrics,
            "PHASE8_EXPERIMENT_RUNNER",
        ),
        _definition(
            "F02_ETEAC_BASELINE",
            "ETEAC 正常静态基线",
            "RQ1",
            ["S01_NORMAL_STATIC"],
            [Phase12Backend.MOCK, Phase12Backend.MUJOCO],
            ["ETEAC"],
            ["control_mode"],
            common_metrics,
            "PHASE8_EXPERIMENT_RUNNER",
        ),
        _definition(
            "F03_AUTO_BASELINE",
            "AUTO 正常静态基线",
            "RQ2",
            ["S01_NORMAL_STATIC"],
            [Phase12Backend.MOCK, Phase12Backend.MUJOCO],
            ["AUTO"],
            ["control_mode"],
            common_metrics,
            "PHASE8_EXPERIMENT_RUNNER",
        ),
        _definition(
            "F04_NETWORK_LATENCY",
            "网络延迟敏感性",
            "RQ2",
            ["S07_NETWORK_DEGRADED"],
            [Phase12Backend.MOCK, Phase12Backend.MUJOCO],
            ["PCSC", "ETEAC", "AUTO"],
            ["latency_ms"],
            common_metrics + ["communication_wait_time_ms"],
            "PHASE11_SIMULATION_RUNTIME",
        ),
        _definition(
            "F05_NETWORK_JITTER",
            "网络抖动敏感性",
            "RQ2",
            ["S07_NETWORK_DEGRADED"],
            [Phase12Backend.MOCK],
            ["PCSC", "ETEAC", "AUTO"],
            ["jitter_ms"],
            common_metrics,
            "PHASE11_SIMULATION_RUNTIME",
        ),
        _definition(
            "F06_PACKET_LOSS",
            "丢包敏感性",
            "RQ2",
            ["S07_NETWORK_DEGRADED", "S08_NETWORK_OUTAGE"],
            [Phase12Backend.MOCK],
            ["PCSC", "ETEAC", "AUTO"],
            ["packet_loss"],
            common_metrics,
            "PHASE11_SIMULATION_RUNTIME",
        ),
        _definition(
            "F07_CLOUD_INTERRUPTION",
            "云端中断与恢复",
            "RQ3",
            ["S09_CLOUD_UNAVAILABLE"],
            [Phase12Backend.MOCK],
            ["PCSC", "ETEAC", "AUTO"],
            ["cloud_available", "outage_duration_ms"],
            common_metrics + ["cloud_fallback_count"],
            "PHASE8_EXPERIMENT_RUNNER",
        ),
        _definition(
            "F08_TARGET_MOVEMENT",
            "目标移动故障",
            "RQ3",
            ["S02_TARGET_MOVED"],
            [Phase12Backend.MOCK, Phase12Backend.MUJOCO],
            ["PCSC", "ETEAC", "AUTO"],
            ["target_motion_time", "target_motion_distance"],
            common_metrics,
            "PHASE9_MUJOCO",
        ),
        _definition(
            "F09_OBSTACLE_CHANGE",
            "障碍物和工作空间变化",
            "RQ3",
            ["S03_OBSTACLE_INSERTED"],
            [Phase12Backend.MOCK, Phase12Backend.MUJOCO],
            ["PCSC", "ETEAC", "AUTO"],
            ["obstacle_time", "workspace_change"],
            common_metrics + ["workspace_rejection"],
            "PHASE9_MUJOCO",
        ),
        _definition(
            "F10_LOCAL_RECOVERY",
            "本地恢复预算",
            "RQ3",
            ["S04_GRASP_FAILURE"],
            [Phase12Backend.MOCK],
            ["ETEAC", "AUTO"],
            ["retry_budget"],
            common_metrics + ["local_recovery_success_count"],
            "PHASE8_EXPERIMENT_RUNNER",
        ),
        _definition(
            "F11_LOCAL_REPLANNING",
            "局部重规划对比",
            "RQ3",
            ["S02_TARGET_MOVED", "S03_OBSTACLE_INSERTED"],
            [Phase12Backend.MOCK],
            ["PCSC", "ETEAC", "AUTO"],
            ["replanning_scope"],
            common_metrics + ["replan_count"],
            "PHASE8_EXPERIMENT_RUNNER",
        ),
        _definition(
            "F12_SAFETY_REJECTION",
            "SafetyShield 和 HardwareExecutionGate fail-closed",
            "RQ4",
            ["S06_PERCEPTION_DEGRADED", "S14_EMERGENCY_STOP"],
            [Phase12Backend.SYNTHETIC_DRY_RUN, Phase12Backend.MOVEIT_DRY_RUN],
            ["PCSC", "ETEAC", "AUTO"],
            ["unsafe_request_type"],
            common_metrics
            + [
                "stale_telemetry_rejection",
                "collision_rejection",
                "emergency_stop_event",
            ],
            "PHASE10_SYNTHETIC_DRY_RUN",
        ),
        _definition(
            "F13_SKILL_CACHE",
            "技能缓存消融",
            "RQ7",
            ["S11_SKILL_CACHE_HIT", "S12_SKILL_CACHE_QUARANTINE"],
            [Phase12Backend.MOCK],
            ["ETEAC", "AUTO"],
            ["cache_policy"],
            common_metrics + ["completed_without_cloud_after_start"],
            "PHASE8_EXPERIMENT_RUNNER",
        ),
        _definition(
            "F14_AUTO_POLICY",
            "AUTO 策略贡献",
            "RQ2",
            ["S13_MODE_OSCILLATION_PRESSURE"],
            [Phase12Backend.MOCK],
            ["PCSC", "ETEAC", "AUTO"],
            ["auto_policy"],
            common_metrics + ["mode_switch_count"],
            "PHASE8_EXPERIMENT_RUNNER",
        ),
        _definition(
            "F15_MUJOCO_ISAAC_PAIRED",
            "MuJoCo / Isaac 成对比较",
            "RQ5",
            ["S01_NORMAL_STATIC", "S07_NETWORK_DEGRADED", "S14_EMERGENCY_STOP"],
            [Phase12Backend.MUJOCO, Phase12Backend.ISAAC_SIM],
            ["PCSC"],
            ["backend"],
            common_metrics + ["completion_time_delta", "paired_success_agreement"],
            "PHASE9_2_ISAAC",
            pairing_key="scenario|seed|mode|network",
            status_if_unavailable="BLOCKED_BY_ENV",
        ),
        _definition(
            "F16_PLANNER_PROVIDER_COMPARISON",
            "规划器 provider 对比",
            "RQ6",
            ["S01_NORMAL_STATIC", "S07_NETWORK_DEGRADED"],
            [Phase12Backend.PLANNER_DRY_RUN],
            ["PCSC", "ETEAC", "AUTO"],
            ["planner_provider"],
            common_metrics + ["planner_success", "valid_contract_rate", "response_latency_ms"],
            "PHASE11_2_PLANNER_DRY_RUN",
        ),
        _definition(
            "F17_ABLATION_RECOVERY",
            "移除本地恢复消融",
            "RQ7",
            ["S04_GRASP_FAILURE"],
            [Phase12Backend.MOCK],
            ["ETEAC", "AUTO"],
            ["local_recovery_enabled"],
            common_metrics + ["local_recovery_success_count"],
            "PHASE8_EXPERIMENT_RUNNER",
        ),
        _definition(
            "F18_ABLATION_REPLANNING",
            "移除局部重规划消融",
            "RQ7",
            ["S02_TARGET_MOVED", "S03_OBSTACLE_INSERTED"],
            [Phase12Backend.MOCK],
            ["ETEAC", "AUTO"],
            ["local_replanning_enabled"],
            common_metrics + ["replan_count"],
            "PHASE8_EXPERIMENT_RUNNER",
        ),
        _definition(
            "F19_ABLATION_SAFETY",
            "安全盾仿真旁路消融",
            "RQ7",
            ["S06_PERCEPTION_DEGRADED", "S14_EMERGENCY_STOP"],
            [Phase12Backend.MOCK],
            ["PCSC", "ETEAC", "AUTO"],
            ["safety_policy_stub"],
            common_metrics + ["safety_intervention_count"],
            "PHASE8_EXPERIMENT_RUNNER",
        ),
        _definition(
            "F20_STRESS_AND_RECOVERY",
            "运行时压力、租约和恢复",
            "RQ3",
            ["S15_SQLITE_RESTART_DURING_RUN"],
            [Phase12Backend.MOCK],
            ["PCSC", "ETEAC", "AUTO"],
            ["worker_restart", "lease_expiration", "duplicate_worker_competition"],
            common_metrics + ["restart_recovery_success", "duplicate_execution_count"],
            "PHASE11_SIMULATION_RUNTIME",
        ),
    ]


def build_experiment_plan(profile: Phase12Profile) -> Phase12ExperimentPlan:
    """按 profile 展开样本量，只计算计划，不触发实验执行。"""

    registry = final_experiment_registry()
    seed_count = _profile_seed_count(profile)
    repetitions = _profile_repetitions(profile)
    run_count = 0
    for experiment in registry:
        seeds = _seeds_for(experiment, profile)
        experiment_repetitions = _repetitions_for(experiment, profile)
        run_count += (
            len(experiment.scenario_ids)
            * len(experiment.backends)
            * len(experiment.control_modes)
            * len(seeds)
            * experiment_repetitions
        )
    return Phase12ExperimentPlan(
        profile=profile,
        experiments=registry,
        run_count=run_count,
        seed_count=seed_count,
        baseline_seed_count=30 if profile == Phase12Profile.FULL else seed_count,
        repetitions=repetitions,
        runner_mapping={runner: runner for runner in sorted(ALLOWLISTED_RUNNERS)},
        hardware_claims=HardwareClaims(),
    )


def _definition(
    experiment_id: str,
    title: str,
    rq: str,
    scenarios: list[str],
    backends: list[Phase12Backend],
    modes: list[str],
    independent_variables: list[str],
    metrics: list[str],
    runner_kind: str,
    *,
    pairing_key: str | None = None,
    status_if_unavailable: str = "BLOCKED_BY_ENV",
) -> Phase12ExperimentDefinition:
    if runner_kind not in ALLOWLISTED_RUNNERS:
        raise ValueError(f"runner not allowlisted: {runner_kind}")
    full_seed_count = _full_seed_count(experiment_id)
    task_count = 100 if experiment_id == "F20_STRESS_AND_RECOVERY" else 1
    return Phase12ExperimentDefinition(
        experiment_id=experiment_id,
        title=title,
        research_question=rq,
        scenario_ids=scenarios,
        backends=backends,
        control_modes=modes,
        independent_variables=independent_variables,
        dependent_metrics=metrics,
        seeds_smoke=[0],
        validation_seed_count=3,
        full_seed_count=full_seed_count,
        repetitions=1,
        runner_kind=runner_kind,
        sample_policy=Phase12SamplePolicy(
            seed_count=full_seed_count,
            repetitions=3,
            task_count=task_count,
            pairing_required=experiment_id == "F15_MUJOCO_ISAAC_PAIRED",
            required_actual_backend=True,
            minimum_successful_samples=max(1, full_seed_count // 2),
        ),
        pairing_key=pairing_key,
        status_if_unavailable=status_if_unavailable,
    )


def _profile_seed_count(profile: Phase12Profile) -> int:
    if profile == Phase12Profile.SMOKE:
        return 1
    if profile == Phase12Profile.VALIDATION:
        return 3
    return 30


def _profile_repetitions(profile: Phase12Profile) -> int:
    if profile == Phase12Profile.SMOKE:
        return 1
    if profile == Phase12Profile.VALIDATION:
        return 2
    return 3


def _seeds_for(experiment: Phase12ExperimentDefinition, profile: Phase12Profile) -> list[int]:
    if profile == Phase12Profile.SMOKE:
        return list(experiment.seeds_smoke)
    if profile == Phase12Profile.VALIDATION:
        return list(range(experiment.validation_seed_count))
    return list(range(experiment.sample_policy.seed_count))


def _repetitions_for(experiment: Phase12ExperimentDefinition, profile: Phase12Profile) -> int:
    if profile == Phase12Profile.SMOKE:
        return 1
    if profile == Phase12Profile.VALIDATION:
        return 2
    return experiment.sample_policy.repetitions


def _full_seed_count(experiment_id: str) -> int:
    if experiment_id in {"F01_PC_SC_BASELINE", "F02_ETEAC_BASELINE", "F03_AUTO_BASELINE"}:
        return 30
    if experiment_id == "F20_STRESS_AND_RECOVERY":
        return 20
    return 20
