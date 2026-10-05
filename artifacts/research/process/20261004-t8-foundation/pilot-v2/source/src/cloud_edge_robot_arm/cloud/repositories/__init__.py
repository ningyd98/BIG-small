"""云端仓储包，提供内存和协议抽象，避免服务直接依赖具体存储。

Cloud-side repositories for planning artifacts.
"""

from __future__ import annotations

from cloud_edge_robot_arm.cloud.repositories.base import CloudPlanningRepository
from cloud_edge_robot_arm.cloud.repositories.memory import InMemoryCloudPlanningRepository

__all__ = [
    "CloudPlanningRepository",
    "InMemoryCloudPlanningRepository",
]
