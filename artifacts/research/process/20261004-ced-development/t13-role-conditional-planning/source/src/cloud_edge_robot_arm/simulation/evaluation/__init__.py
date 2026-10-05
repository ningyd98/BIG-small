"""仿真评估包，负责指标、provenance、跨后端对比和报告收集。"""

from __future__ import annotations

from cloud_edge_robot_arm.simulation.evaluation.metrics import run_mujoco_physical_trial

__all__ = ["run_mujoco_physical_trial"]
