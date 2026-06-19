"""Phase 12 最终实验评估包。

本包只组织软件、仿真、dry-run 和 planner dry-run 证据，不注册真实机械臂 runner，
也不允许输出真实硬件验收结论。
"""

from cloud_edge_robot_arm.final_evaluation.models import Phase12Profile
from cloud_edge_robot_arm.final_evaluation.registry import final_experiment_registry

__all__ = ["Phase12Profile", "final_experiment_registry"]
