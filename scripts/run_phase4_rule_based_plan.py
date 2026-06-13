#!/usr/bin/env python3
"""Phase 4 acceptance: RuleBased planner produces a valid TaskContract."""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from cloud_edge_robot_arm.cloud.planning.adapter import RuleBasedPlannerAdapter
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
    pipeline = PlanningPipeline(planner=RuleBasedPlannerAdapter())
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
        request_id="rule-plan-001",
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
        steps = result.contract.steps
        if len(steps) != 10:
            errors.append(f"expected 10 steps, got {len(steps)}")
        skills = [s.skill.value for s in steps]
        if "GRASP" not in skills or "PLACE" not in skills:
            errors.append(f"missing GRASP/PLACE in skills: {skills}")
        print(
            f"  outcome=PLANNED task_id={result.contract.task_id} steps={len(steps)} skills={skills[:5]}..."
        )
        print(
            f"  target={result.contract.task_target.object_id} -> {result.contract.task_target.target_region_id}"
        )

    if errors:
        print(f"\nFAIL: {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    print("\nPASS: RuleBased planner works")
    print("success=true")


if __name__ == "__main__":
    main()
