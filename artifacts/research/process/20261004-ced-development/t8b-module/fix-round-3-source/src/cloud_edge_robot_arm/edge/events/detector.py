"""事件检测器协议定义。

所有 detector 都必须只读取 DetectionContext 并返回结构化 EdgeEvent 或 None，
不得在检测阶段调用大模型、外部服务或隐藏的全局状态。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from cloud_edge_robot_arm.contracts.models import EdgeEvent
from cloud_edge_robot_arm.edge.events.models import DetectionContext


@runtime_checkable
class EventDetector(Protocol):
    """Protocol for event detectors.

        Each detector examines a DetectionContext and returns an EdgeEvent
        if its triggering condition is met, or None otherwise.

        Detectors must be:
        - Stateless (or only hold configuration)
        - Deterministic for the same input
        - Free of LLM / external service calls
        - Free of direct global variable access
    事件检测器协议。

    所有 detector 必须实现同一接口，输入 DetectionContext，输出结构化 EdgeEvent 列表。

    """

    def detect(self, context: DetectionContext) -> EdgeEvent | None:
        """Examine context; return event if condition met, else None."""
        ...

    @property
    def detector_name(self) -> str:
        """Human-readable name for audit and debugging."""
        ...
