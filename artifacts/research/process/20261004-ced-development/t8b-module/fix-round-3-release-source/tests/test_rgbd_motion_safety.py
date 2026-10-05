"""RGB-D motion uses explicit clearance targets and the effective workspace."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cloud_edge_robot_arm.contracts import Pose, RobotState, SafetyDecision, SkillName
from cloud_edge_robot_arm.edge.safety.context_builder import SafetyContextBuilder
from cloud_edge_robot_arm.edge.safety.models import (
    HardSafetyLimits,
    SafetyContext,
    WorkspaceDefinition,
)
from cloud_edge_robot_arm.edge.safety.policy import OperationalSafetyPolicy, merge_constraints
from cloud_edge_robot_arm.edge.safety.rules import MinimumHeightRule, WorkspaceRule
from tests.phase2_helpers import contract, step


def _context(
    *,
    skill: SkillName = SkillName.LIFT,
    current: Pose | None = None,
    target: dict[str, object] | None = None,
    hard: HardSafetyLimits | None = None,
    policy: OperationalSafetyPolicy | None = None,
) -> SafetyContext:
    motion = step("rgbd-motion", skill)
    task = contract(steps=[motion])
    hard = hard or HardSafetyLimits()
    builder = SafetyContextBuilder(
        merged=merge_constraints(hard, policy or OperationalSafetyPolicy()),
        hard_limits=hard,
    )
    return builder.build(
        contract=task,
        step=motion,
        robot_state=RobotState(
            tcp_pose=current or Pose(x=0.2, y=-0.1, z=0.02), connected=True
        ),
        scene_version=1,
        scene_updated_at=datetime.now(UTC),
        resolved_parameters={} if target is None else {"target_pose": target},
    )


@pytest.mark.parametrize("skill", [SkillName.LIFT, SkillName.RETREAT])
@pytest.mark.parametrize("target_z", [0.08, 0.16])
def test_low_pose_can_only_escape_upward_to_safe_height(skill: SkillName, target_z: float) -> None:
    context = _context(skill=skill, target={"x": 0.2, "y": -0.1, "z": target_z})
    assert MinimumHeightRule().evaluate(context).decision == SafetyDecision.ALLOW


@pytest.mark.parametrize("skill", [SkillName.LIFT, SkillName.RETREAT])
@pytest.mark.parametrize(
    "target",
    [
        None,
        {},
        {"z": 0.16},
        {"x": 0.2, "y": -0.1},
        {"x": 0.21, "y": -0.1, "z": 0.16},
        {"x": 0.2, "y": -0.09, "z": 0.16},
        {"x": 0.2, "y": -0.1, "z": 0.079},
        {"x": 0.2, "y": -0.1, "z": 0.01},
        {"x": 0.2, "y": -0.1, "z": float("inf")},
        {"x": 0.2, "y": -0.1, "z": float("nan")},
        {"x": 0.2, "y": -0.1, "z": "0.16"},
    ],
)
def test_low_pose_rejects_missing_lateral_descending_or_invalid_target(
    skill: SkillName, target: dict[str, object] | None
) -> None:
    context = _context(skill=skill, target=target)
    assert MinimumHeightRule().evaluate(context).decision == SafetyDecision.REJECT


@pytest.mark.parametrize("skill", [SkillName.HOME, SkillName.MOVE_ABOVE, SkillName.MOVE_TO_REGION])
def test_clearance_exception_does_not_exempt_other_motion_skills(skill: SkillName) -> None:
    context = _context(skill=skill, target={"x": 0.2, "y": -0.1, "z": 0.16})
    assert MinimumHeightRule().evaluate(context).decision == SafetyDecision.REJECT


def test_workspace_uses_explicit_hard_limits_for_current_and_target_pose() -> None:
    hard = HardSafetyLimits(
        workspace_x_min=-0.85, workspace_x_max=0.85,
        workspace_y_min=-0.85, workspace_y_max=0.85,
        workspace_z_min=0.0, workspace_z_max=1.2,
    )
    context = _context(
        current=Pose(x=0.625, y=0.0, z=0.6),
        target={"x": 0.7, "y": 0.0, "z": 1.0},
        hard=hard,
    )
    assert WorkspaceRule().evaluate(context).decision == SafetyDecision.ALLOW


@pytest.mark.parametrize("outside_current", [False, True])
def test_workspace_preserves_narrower_operational_boundary(outside_current: bool) -> None:
    policy = OperationalSafetyPolicy(
        workspace=WorkspaceDefinition(workspace_id="narrow", x_min=-0.3, x_max=0.3)
    )
    context = _context(
        current=Pose(x=0.35 if outside_current else 0.2, y=0.0, z=0.2),
        target={"x": 0.2 if outside_current else 0.35, "y": 0.0, "z": 0.2},
        policy=policy,
    )
    verdict = WorkspaceRule().evaluate(context)
    assert verdict.decision == SafetyDecision.REJECT
    assert verdict.details["check"] == ("current_pose" if outside_current else "target_pose")


@pytest.mark.parametrize("axis,value", [("x", 0.51), ("y", -0.51), ("z", 0.61)])
def test_operational_workspace_cannot_expand_hard_bounds(axis: str, value: float) -> None:
    target: dict[str, object] = {"x": 0.2, "y": 0.0, "z": 0.2}
    target[axis] = value
    context = _context(
        current=Pose(x=0.2, y=0.0, z=0.2),
        target=target,
        policy=OperationalSafetyPolicy(
            workspace=WorkspaceDefinition(
                workspace_id="overwide", x_min=-1, x_max=1,
                y_min=-1, y_max=1, z_min=-1, z_max=2,
            )
        ),
    )
    assert WorkspaceRule().evaluate(context).decision == SafetyDecision.REJECT
