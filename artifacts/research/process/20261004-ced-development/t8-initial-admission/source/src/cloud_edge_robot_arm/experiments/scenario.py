"""实验场景注册表。

scenario_registry 是 S01-S15 场景的权威来源，前端和 API 都应从这里派生场景目录，
不能在 React 页面中硬编码场景列表。
"""

from __future__ import annotations

from cloud_edge_robot_arm.experiments.models import (
    FaultEvent,
    FaultType,
    ResultStatus,
    ScenarioDefinition,
)


def scenario_registry() -> list[ScenarioDefinition]:
    return [
        _scenario(
            "S01_NORMAL_STATIC",
            "Static target without obstacle changes.",
            [],
            [ResultStatus.SUCCESS],
        ),
        _scenario(
            "S02_TARGET_MOVED",
            "Target moves during execution.",
            [
                FaultEvent(
                    fault_id="f-target-moved",
                    fault_type=FaultType.TARGET_MOVED,
                    trigger_time_ms=700,
                )
            ],
            [ResultStatus.SUCCESS, ResultStatus.NEEDS_OBSERVATION],
        ),
        _scenario(
            "S03_OBSTACLE_INSERTED",
            "A new obstacle blocks the remaining path.",
            [
                FaultEvent(
                    fault_id="f-obstacle",
                    fault_type=FaultType.OBSTACLE_INSERTED,
                    trigger_time_ms=900,
                )
            ],
            [ResultStatus.SUCCESS, ResultStatus.NEEDS_OBSERVATION, ResultStatus.SAFETY_STOPPED],
        ),
        _scenario(
            "S04_GRASP_FAILURE",
            "Initial grasp attempt fails and recovery is required.",
            [
                FaultEvent(
                    fault_id="f-grasp",
                    fault_type=FaultType.GRASP_FAILURE,
                    trigger_time_ms=250,
                    parameters={"failures": 1},
                )
            ],
            [ResultStatus.SUCCESS, ResultStatus.FAILED],
        ),
        _scenario(
            "S05_TARGET_LOST",
            "Target is temporarily not visible.",
            [FaultEvent(fault_id="f-lost", fault_type=FaultType.TARGET_LOST, trigger_time_ms=600)],
            [ResultStatus.NEEDS_OBSERVATION, ResultStatus.SUCCESS],
        ),
        _scenario(
            "S06_PERCEPTION_DEGRADED",
            "Scene confidence degrades below the fail-closed threshold.",
            [
                FaultEvent(
                    fault_id="f-perception",
                    fault_type=FaultType.PERCEPTION_DEGRADED,
                    trigger_time_ms=600,
                )
            ],
            [ResultStatus.NEEDS_OBSERVATION, ResultStatus.SAFETY_STOPPED],
        ),
        _scenario(
            "S07_NETWORK_DEGRADED",
            "Network latency, jitter, and packet loss increase.",
            [
                FaultEvent(
                    fault_id="f-network-degraded",
                    fault_type=FaultType.NETWORK_DEGRADED,
                    trigger_time_ms=500,
                )
            ],
            [ResultStatus.SUCCESS, ResultStatus.NEEDS_OBSERVATION],
        ),
        _scenario(
            "S08_NETWORK_OUTAGE",
            "Network disconnects during execution and later recovers.",
            [
                FaultEvent(
                    fault_id="f-outage",
                    fault_type=FaultType.NETWORK_OUTAGE,
                    trigger_time_ms=800,
                    duration_ms=1_000,
                )
            ],
            [ResultStatus.SUCCESS, ResultStatus.NEEDS_OBSERVATION, ResultStatus.SAFETY_STOPPED],
        ),
        _scenario(
            "S09_CLOUD_UNAVAILABLE",
            "Cloud supervision times out or rejects requests.",
            [
                FaultEvent(
                    fault_id="f-cloud",
                    fault_type=FaultType.CLOUD_UNAVAILABLE,
                    trigger_time_ms=800,
                )
            ],
            [ResultStatus.SUCCESS, ResultStatus.NEEDS_OBSERVATION, ResultStatus.SAFETY_STOPPED],
        ),
        _scenario(
            "S10_STALE_DUPLICATE_REORDERED_COMMAND",
            "Stale, duplicate, and reordered commands are injected.",
            [
                FaultEvent(
                    fault_id="f-command",
                    fault_type=FaultType.STALE_DUPLICATE_REORDERED_COMMAND,
                    trigger_time_ms=400,
                )
            ],
            [ResultStatus.SUCCESS],
        ),
        _scenario(
            "S11_SKILL_CACHE_HIT",
            "A trusted high-level skill template is available.",
            [
                FaultEvent(
                    fault_id="f-cache-hit",
                    fault_type=FaultType.SKILL_CACHE_HIT,
                    trigger_time_ms=0,
                )
            ],
            [ResultStatus.SUCCESS],
        ),
        _scenario(
            "S12_SKILL_CACHE_QUARANTINE",
            "Unsafe or repeated failures quarantine a cached template.",
            [
                FaultEvent(
                    fault_id="f-cache-quarantine",
                    fault_type=FaultType.SKILL_CACHE_QUARANTINE,
                    trigger_time_ms=700,
                )
            ],
            [ResultStatus.SUCCESS, ResultStatus.FAILED, ResultStatus.SAFETY_STOPPED],
        ),
        _scenario(
            "S13_MODE_OSCILLATION_PRESSURE",
            "Network and risk oscillate near mode thresholds.",
            [
                FaultEvent(
                    fault_id="f-oscillation",
                    fault_type=FaultType.MODE_OSCILLATION_PRESSURE,
                    trigger_time_ms=300,
                )
            ],
            [ResultStatus.SUCCESS, ResultStatus.NEEDS_OBSERVATION],
        ),
        _scenario(
            "S14_EMERGENCY_STOP",
            "Emergency stop is injected.",
            [
                FaultEvent(
                    fault_id="f-estop",
                    fault_type=FaultType.EMERGENCY_STOP,
                    trigger_time_ms=600,
                )
            ],
            [ResultStatus.SAFETY_STOPPED],
        ),
        _scenario(
            "S15_SQLITE_RESTART_DURING_RUN",
            "SQLite repositories are reopened during a prepared transition or stats write.",
            [
                FaultEvent(
                    fault_id="f-restart",
                    fault_type=FaultType.SQLITE_RESTART,
                    trigger_time_ms=500,
                )
            ],
            [ResultStatus.SUCCESS, ResultStatus.NEEDS_OBSERVATION],
        ),
    ]


def get_scenario(scenario_id: str) -> ScenarioDefinition:
    for scenario in scenario_registry():
        if scenario.scenario_id == scenario_id:
            return scenario
    raise KeyError(f"unknown scenario_id: {scenario_id}")


def _scenario(
    scenario_id: str,
    description: str,
    faults: list[FaultEvent],
    allowed: list[ResultStatus],
) -> ScenarioDefinition:
    return ScenarioDefinition(
        scenario_id=scenario_id,
        description=description,
        initial_world_state={
            "target_visible": True,
            "scene_confidence": 0.95,
            "target_confidence": 0.95,
            "obstacle_count": 0,
        },
        scheduled_faults=faults,
        expected_invariants=[
            "SafetyShield is not bypassed",
            "simulated_collision_count remains zero for formal modes",
            "completed steps are not repeated",
        ],
        allowed_result_statuses=allowed,
        forbidden_result_statuses=[ResultStatus.TIMEOUT],
        maximum_virtual_duration_ms=30_000,
    )
