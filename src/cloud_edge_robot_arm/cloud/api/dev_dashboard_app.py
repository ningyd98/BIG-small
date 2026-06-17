"""Local dashboard API entrypoint backed by the deterministic mock planner."""

from __future__ import annotations

from cloud_edge_robot_arm.cloud.api.app import create_app
from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline

app = create_app(PlanningPipeline(planner=MockPlannerAdapter()))
