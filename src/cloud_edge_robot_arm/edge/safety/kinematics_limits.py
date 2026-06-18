"""运动学限速工具。

有效速度取任务约束和设备上限的更严格值，防止配置放宽真实能力限制。
"""

from __future__ import annotations

from cloud_edge_robot_arm.contracts import TaskContract


def effective_max_tcp_velocity(contract: TaskContract, device_limit: float | None = None) -> float:
    candidates = [contract.safety_constraints.max_tcp_velocity]
    if device_limit is not None:
        candidates.append(device_limit)
    return min(candidates)


def effective_max_joint_velocity(
    contract: TaskContract, device_limit: float | None = None
) -> float:
    candidates = [contract.safety_constraints.max_joint_velocity]
    if device_limit is not None:
        candidates.append(device_limit)
    return min(candidates)
