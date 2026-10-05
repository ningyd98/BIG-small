"""云边网关包，处理边缘事件上报、命令确认和合同同步。

Edge gateway: cloud-side dispatch of validated contracts to the edge runtime.
"""

from __future__ import annotations

from cloud_edge_robot_arm.cloud.gateway.edge_gateway import (
    EdgeDispatchResult,
    EdgeGateway,
    InProcessEdgeGateway,
)

__all__ = [
    "EdgeDispatchResult",
    "EdgeGateway",
    "InProcessEdgeGateway",
]
