#!/usr/bin/env python3
"""Phase 4 acceptance: REQUEST_MORE_OBSERVATION scenarios.

Tests:
- Empty scene (no objects)
- Low confidence scene
- Stale scene
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

from cloud_edge_robot_arm.cloud.planning.adapter import RuleBasedPlannerAdapter
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
    caps = RobotCapabilities(supported_skills=[s.value for s in SkillName])

    # --- Empty scene ---
    pipeline = PlanningPipeline(planner=RuleBasedPlannerAdapter())
    scene = SceneSummary(
        scene_version=1,
        updated_at=datetime.now(UTC),
        objects=[],
        regions=[],
    )
    req = InitialPlanningRequest(
        request_id="obs-empty-001",
        user_instruction="pick red cube",
        scene=scene,
        capabilities=caps,
    )
    result = pipeline.process(req)
    if result.outcome != PlanningOutcome.REQUEST_MORE_OBSERVATION:
        errors.append(f"empty scene: expected REQUEST_MORE_OBSERVATION, got {result.outcome.value}")
    print(f"  empty scene -> {result.outcome.value}: {result.reason}")

    # --- Low confidence ---
    scene = SceneSummary(
        scene_version=1,
        updated_at=datetime.now(UTC),
        objects=[
            SceneObjectSummary(
                object_id="red_cube",
                object_class="cube",
                pose=Pose(x=0.2, y=0.0, z=0.02),
                pose_confidence=0.3,
            )
        ],
        regions=[
            TargetRegionSummary(
                region_id="bin_a",
                center=Pose(x=-0.2, y=0.18, z=0.02),
            )
        ],
        scene_confidence=0.3,
    )
    req = InitialPlanningRequest(
        request_id="obs-lowconf-001",
        user_instruction="pick red cube",
        scene=scene,
        capabilities=caps,
    )
    result = pipeline.process(req)
    if result.outcome != PlanningOutcome.REQUEST_MORE_OBSERVATION:
        errors.append(
            f"low confidence: expected REQUEST_MORE_OBSERVATION, got {result.outcome.value}"
        )
    print(f"  low confidence -> {result.outcome.value}: {result.reason}")

    # --- Stale scene ---
    pipeline = PlanningPipeline(planner=RuleBasedPlannerAdapter(), scene_staleness_ms=100)
    scene = SceneSummary(
        scene_version=1,
        updated_at=datetime.now(UTC) - timedelta(minutes=10),
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
    req = InitialPlanningRequest(
        request_id="obs-stale-001",
        user_instruction="pick red cube",
        scene=scene,
        capabilities=caps,
    )
    result = pipeline.process(req)
    if result.outcome != PlanningOutcome.REQUEST_MORE_OBSERVATION:
        errors.append(f"stale scene: expected REQUEST_MORE_OBSERVATION, got {result.outcome.value}")
    print(f"  stale scene -> {result.outcome.value}: {result.reason}")

    if errors:
        print(f"\nFAIL: {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    print("\nPASS: REQUEST_MORE_OBSERVATION scenarios")
    print("success=true")


if __name__ == "__main__":
    main()
