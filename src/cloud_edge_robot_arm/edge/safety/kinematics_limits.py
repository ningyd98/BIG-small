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
