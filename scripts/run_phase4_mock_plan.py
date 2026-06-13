#!/usr/bin/env python3
"""Phase 4 acceptance: Mock planner produces a valid, edge-ready TaskContract."""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
from cloud_edge_robot_arm.cloud.planning.models import (
    InitialPlanningRequest,
    Pose,
    RobotCapabilities,
    SceneObjectSummary,
    SceneSummary,
    TargetRegionSummary,
)
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
from cloud_edge_robot_arm.contracts import SkillName


def main() -> None:
    pipeline = PlanningPipeline(planner=MockPlannerAdapter())
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
    caps = RobotCapabilities(supported_skills=[s.value for s in SkillName])
    req = InitialPlanningRequest(
        request_id="mock-plan-001",
        user_instruction="pick red cube and place into bin_a",
        scene=scene,
        capabilities=caps,
    )
    result = pipeline.process(req)

    errors: list[str] = []
    if result.outcome.value != "PLANNED":
        errors.append(f"outcome={result.outcome.value}, expected PLANNED")
    if result.contract is None:
        errors.append("contract is None")
    else:
        c = result.contract
        if not c.task_id.startswith("task-"):
            errors.append(f"unexpected task_id: {c.task_id}")
        if c.plan_version != 1:
            errors.append(f"plan_version={c.plan_version}, expected 1")
        if c.command_seq != 1:
            errors.append(f"command_seq={c.command_seq}, expected 1")
        if c.issued_at.tzinfo is None:
            errors.append("issued_at missing timezone")
    print(
        f"  outcome={result.outcome.value} task_id={result.contract.task_id if result.contract else 'N/A'}"
    )

    if errors:
        print(f"\nFAIL: {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    print("\nPASS: Mock planner works")
    print("success=true")


if __name__ == "__main__":
    main()
