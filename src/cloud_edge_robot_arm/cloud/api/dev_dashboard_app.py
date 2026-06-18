"""本地开发 Dashboard API 入口。

该入口只使用确定性 Mock planner，方便前端和 E2E 在无真实控制器环境中运行。
它不能作为真实机械臂控制入口。
"""

from __future__ import annotations

from cloud_edge_robot_arm.cloud.api.app import create_app
from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline

app = create_app(PlanningPipeline(planner=MockPlannerAdapter()))
