"""可复现实验框架。

该包定义场景、实验配置、runner、batch 和 metrics，用于 Mock/MuJoCo/论文实验复现。
这里的实验 runner 只面向仿真和离线证据，不应被扩展成任意 shell 执行入口。
"""

from cloud_edge_robot_arm.experiments.models import (
    AblationType,
    CachePolicy,
    ExperimentConfig,
    ExperimentMode,
    ExperimentResult,
    ExperimentRun,
    FaultEvent,
    FaultProfile,
    MetricSummary,
    NetworkProfileName,
    ScenarioDefinition,
    TaskProfile,
)

__all__ = [
    "AblationType",
    "CachePolicy",
    "ExperimentConfig",
    "ExperimentMode",
    "ExperimentResult",
    "ExperimentRun",
    "FaultEvent",
    "FaultProfile",
    "MetricSummary",
    "NetworkProfileName",
    "ScenarioDefinition",
    "TaskProfile",
]
