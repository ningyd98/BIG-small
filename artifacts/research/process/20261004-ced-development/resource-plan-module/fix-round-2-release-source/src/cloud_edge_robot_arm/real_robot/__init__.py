"""真实机械臂安全边界模块。

当前项目主线已冻结真机开发；该包保留回归和 Level 0 只读框架，不允许自动进入
Level 1，也不应从仿真工作台触发真实控制器写操作。
"""

from __future__ import annotations

from cloud_edge_robot_arm.real_robot.acceptance import (
    RealRobotAcceptanceLevel,
    RealRobotAcceptanceStore,
)
from cloud_edge_robot_arm.real_robot.config import (
    ExecutionMode,
    RealRobotConfig,
    RealRobotRuntimeSettings,
)
from cloud_edge_robot_arm.real_robot.dry_run import DryRunValidationService
from cloud_edge_robot_arm.real_robot.gate import HardwareExecutionGate
from cloud_edge_robot_arm.real_robot.level0 import (
    FakeReadOnlyAdapter,
    ReadOnlyRobotAdapterProtocol,
    SiteReadOnlySession,
    VendorRealRobotReadOnlyAdapter,
)
from cloud_edge_robot_arm.real_robot.operator_confirmation import OperatorConfirmation
from cloud_edge_robot_arm.real_robot.planners import SyntheticDryRunPlanner

__all__ = [
    "DryRunValidationService",
    "ExecutionMode",
    "FakeReadOnlyAdapter",
    "HardwareExecutionGate",
    "OperatorConfirmation",
    "ReadOnlyRobotAdapterProtocol",
    "RealRobotAcceptanceLevel",
    "RealRobotAcceptanceStore",
    "RealRobotConfig",
    "RealRobotRuntimeSettings",
    "SiteReadOnlySession",
    "SyntheticDryRunPlanner",
    "VendorRealRobotReadOnlyAdapter",
]
