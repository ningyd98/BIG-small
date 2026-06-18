#!/usr/bin/env python3
"""Phase 4 云端规划和契约修复演示或实验入口，用固定参数运行受控流程并输出可追溯结果。

Phase 4 acceptance: idempotency and request-ID conflict detection."""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
from cloud_edge_robot_arm.cloud.planning.models import (
    InitialPlanningRequest,
    PlanningOutcome,
    Pose,
    RobotCapabilities,
    SceneObjectSummary,
    SceneSummary,
    TargetRegionSummary,
)
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
from cloud_edge_robot_arm.contracts import SkillName


def main() -> None:
    errors: list[str] = []
    pipeline = PlanningPipeline(planner=MockPlannerAdapter())
    caps = RobotCapabilities(supported_skills=[s.value for s in SkillName])
    scene = SceneSummary(
        scene_version=1,
        updated_at=datetime.now(UTC),
        objects=[
            SceneObjectSummary(
                object_id="red_cube",
                object_class="cube",
                pose=Pose(x=0.2, y=0.0, z=0.02),
                pose_confidence=0.95,
            )
        ],
        regions=[
            TargetRegionSummary(
                region_id="bin_a",
                center=Pose(x=-0.2, y=0.18, z=0.02),
            )
        ],
    )

    # --- Idempotency: same request -> same result ---
    req = InitialPlanningRequest(
        request_id="idem-001",
        user_instruction="pick red cube",
        scene=scene,
        capabilities=caps,
    )
    r1 = pipeline.process(req)
    r2 = pipeline.process(req)
    if r1.outcome != r2.outcome:
        errors.append(f"idempotency: outcomes differ ({r1.outcome.value} vs {r2.outcome.value})")
    if r1.contract and r2.contract and r1.contract.task_id != r2.contract.task_id:
        errors.append("idempotency: task_ids differ")
    print(f"  idempotency: same request -> same outcome={r1.outcome.value}")

    # --- Request ID conflict ---
    req2 = InitialPlanningRequest(
        request_id="idem-001",
        user_instruction="different instruction altogether",
        scene=scene,
        capabilities=caps,
    )
    r3 = pipeline.process(req2)
    if r3.outcome != PlanningOutcome.REJECTED:
        errors.append(f"request ID conflict: expected REJECTED, got {r3.outcome.value}")
    print(f"  request ID conflict -> {r3.outcome.value}: {r3.reason}")

    if errors:
        print(f"\nFAIL: {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    print("\nPASS: Idempotency and conflict detection")
    print("success=true")


if __name__ == "__main__":
    main()
