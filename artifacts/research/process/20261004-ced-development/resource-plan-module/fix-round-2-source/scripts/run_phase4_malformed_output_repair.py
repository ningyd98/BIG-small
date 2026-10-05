#!/usr/bin/env python3
"""Phase 4 云端规划和契约修复演示或实验入口，用固定参数运行受控流程并输出可追溯结果。

Phase 4 acceptance: malformed output detection and repair.

Tests:
- Malformed JSON (non-list steps → PLANNER_FAILED)
- Repair fixes timeout < duration
- Repair exhaustion (max attempts)"""

from __future__ import annotations

import sys
from datetime import UTC

from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
from cloud_edge_robot_arm.cloud.planning.models import (
    PlannerDraft,
    PlanningOutcome,
    ValidationResult,
)
from cloud_edge_robot_arm.cloud.planning.pipeline import (
    PlanningPipeline,
    attempt_repair,
)


def main() -> None:
    errors: list[str] = []
    from datetime import datetime

    from cloud_edge_robot_arm.cloud.planning.models import (
        InitialPlanningRequest,
        Pose,
        RobotCapabilities,
        SceneObjectSummary,
        SceneSummary,
        TargetRegionSummary,
    )
    from cloud_edge_robot_arm.contracts import SkillName

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

    # --- Malformed JSON (steps is a string) ---
    pipeline = PlanningPipeline(
        planner=MockPlannerAdapter(canned_output={"steps": "not_a_list"}),
    )
    req = InitialPlanningRequest(
        request_id="malform-001",
        user_instruction="pick red cube",
        scene=scene,
        capabilities=caps,
    )
    result = pipeline.process(req)
    if result.outcome != PlanningOutcome.PLANNER_FAILED:
        errors.append(f"malformed JSON: expected PLANNER_FAILED, got {result.outcome.value}")
    print(f"  malformed JSON -> {result.outcome.value}")

    # --- Repair fixes timeout < duration ---
    draft = PlannerDraft(
        raw_text="x",
        parsed_json={
            "task_target": {"object_id": "x", "object_class": "c", "target_region_id": "r"},
            "steps": [
                {
                    "step_id": "s1",
                    "skill": "HOME",
                    "parameters": {},
                    "expected_duration_ms": 5000,
                    "timeout_ms": 1000,
                    "retry_limit": 1,
                    "preconditions": [],
                    "success_conditions": [],
                }
            ],
        },
    )
    validation = ValidationResult(
        passed=False,
        errors=[
            {"field": "steps[0]", "message": "timeout_ms (1000) < expected_duration_ms (5000)"}
        ],
    )
    repaired = attempt_repair(draft, validation, req)
    if repaired is None:
        errors.append("repair returned None")
    else:
        new_timeout = repaired["steps"][0]["timeout_ms"]
        if new_timeout < repaired["steps"][0]["expected_duration_ms"]:
            errors.append(f"repair did not fix timeout: {new_timeout}")
        print(f"  repair timeout -> timeout_ms={new_timeout}")

    # --- Repair exhaustion ---
    pipeline = PlanningPipeline(
        planner=MockPlannerAdapter(
            canned_output={
                "task_target": {"object_id": "x", "object_class": "c", "target_region_id": "r"},
                "steps": [
                    {
                        "step_id": "s1",
                        "skill": "FAKE_SKILL",
                        "parameters": {"joint_angles": [1, 2]},
                        "expected_duration_ms": 1000,
                        "timeout_ms": 100,
                        "retry_limit": 1,
                        "preconditions": [],
                        "success_conditions": [],
                    }
                ],
                "safety_constraints": {
                    "max_joint_velocity": 0.5,
                    "max_tcp_velocity": 0.15,
                    "minimum_safe_height": 0.08,
                    "workspace_id": "workspace_a",
                    "collision_check_required": True,
                },
            }
        ),
        max_repair_attempts=1,
    )
    result = pipeline.process(req)
    if result.outcome.value == "PLANNED":
        errors.append(f"repair exhaustion: expected non-PLANNED, got {result.outcome.value}")
    print(f"  repair exhaustion -> {result.outcome.value}")

    if errors:
        print(f"\nFAIL: {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    print("\nPASS: Malformed output detection and repair")
    print("success=true")


if __name__ == "__main__":
    main()
