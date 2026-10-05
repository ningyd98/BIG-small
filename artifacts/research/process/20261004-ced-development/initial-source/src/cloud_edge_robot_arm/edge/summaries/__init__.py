"""边缘摘要构建器导出。
摘要用于完成和失败证据，必须保持确定性和可复现。

Edge summaries — FailureSummary and CompletionSummary builders.
"""

from cloud_edge_robot_arm.edge.summaries.completion import CompletionSummaryBuilder
from cloud_edge_robot_arm.edge.summaries.failure import FailureSummaryBuilder

__all__ = [
    "CompletionSummaryBuilder",
    "FailureSummaryBuilder",
]
