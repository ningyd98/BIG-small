"""A bound clearance path is not a generic low-height or no-payload exemption."""

from dataclasses import replace

import pytest

from cloud_edge_robot_arm.contracts import Pose, SafetyDecision, SkillName
from cloud_edge_robot_arm.edge.safety.models import SafetyContext
from cloud_edge_robot_arm.edge.safety.rules import CarrySafetyRule, MinimumHeightRule
from tests.test_rgbd_motion_safety import _context


def clearance(context):
    from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath

    return VerticalClearancePath(
        task_id=context.task_id, step_id=context.step_id, skill=context.skill,
        start_m=(0.2, -0.1, 0.048), target_m=(0.2, -0.1, 0.16), minimum_height_m=0.08,
    )


def lifted_context():
    return _context(
        current=Pose(x=0.19998276, y=-0.10000451, z=0.048021),
        target={"x": 0.2, "y": -0.1, "z": 0.16},
    )


def test_bound_vertical_clearance_accepts_measured_small_tracking_error():
    context = lifted_context()
    assert MinimumHeightRule().evaluate(context).decision == SafetyDecision.REJECT
    context.vertical_clearance = clearance(context)
    assert MinimumHeightRule().evaluate(context).decision == SafetyDecision.ALLOW


@pytest.mark.parametrize("damage", ["task", "step", "skill", "target", "lateral", "downward"])
def test_clearance_rejects_rebinding_changed_goal_or_corridor_escape(damage):
    context = lifted_context()
    path = clearance(context)
    if damage == "task":
        path = replace(path, task_id="other-task")
    elif damage == "step":
        path = replace(path, step_id="other-step")
    elif damage == "skill":
        context.skill = "MOVE_TO_REGION"
    elif damage == "target":
        context.parameters["target_pose"]["z"] = 0.18
    elif damage == "lateral":
        context.tcp_x = 0.2011
    else:
        context.tcp_z = 0.0469
    context.vertical_clearance = path
    assert MinimumHeightRule().evaluate(context).decision == SafetyDecision.REJECT


@pytest.mark.parametrize("target", [(0.21, -0.1, 0.16), (0.2, -0.1, 0.079)])
def test_clearance_cannot_claim_a_lateral_or_below_safe_height_target(target):
    with pytest.raises(ValueError):
        replace(clearance(lifted_context()), target_m=target)


def test_clearance_monitor_rejects_reversal_from_the_highest_reached_pose():
    path = clearance(lifted_context())
    path.check_position((0.2, -0.1, 0.06), peak_z=0.06)
    with pytest.raises(ValueError):
        path.check_position((0.2, -0.1, 0.0589), peak_z=0.06)


def test_clearance_cannot_end_below_a_stricter_merged_height_limit():
    context = lifted_context()
    context.parameters["target_pose"]["z"] = 0.10
    context.merged_minimum_safe_height = 0.12
    context.vertical_clearance = replace(clearance(context), target_m=(0.2, -0.1, 0.10))
    assert MinimumHeightRule().evaluate(context).decision == SafetyDecision.REJECT


@pytest.mark.parametrize("actual", [None, "another-object"])
def test_required_grasp_cannot_be_treated_as_an_empty_transport(actual):
    context = _context(
        skill=SkillName.MOVE_TO_REGION, current=Pose(x=0.2, y=-0.1, z=0.16),
        target={"x": 0.3, "y": 0.2, "z": 0.16},
    )
    context = SafetyContext(**(context.model_dump() | {
        "expected_holding_object_id": "object", "holding_object_id": actual,
        "holding_object": actual is not None,
    }))
    assert CarrySafetyRule().evaluate(context).decision == SafetyDecision.REJECT


def test_empty_motion_without_a_required_grasp_keeps_legacy_semantics():
    context = _context(
        skill=SkillName.MOVE_ABOVE, current=Pose(x=0.2, y=-0.1, z=0.16),
        target={"x": 0.3, "y": 0.2, "z": 0.16},
    )
    assert CarrySafetyRule().evaluate(context).decision == SafetyDecision.ALLOW


@pytest.mark.parametrize("fields", [("start_m",), ("target_m",), ("start_m", "target_m")])
def test_clearance_cannot_retain_mutable_coordinate_containers(fields):
    path = clearance(lifted_context())
    with pytest.raises(ValueError):
        replace(path, **{field: list(getattr(path, field)) for field in fields})


def test_context_builder_takes_authority_only_from_trusted_arguments():
    from cloud_edge_robot_arm.contracts import RobotState
    from cloud_edge_robot_arm.edge.safety.context_builder import SafetyContextBuilder
    from cloud_edge_robot_arm.edge.safety.models import HardSafetyLimits
    from cloud_edge_robot_arm.edge.safety.policy import OperationalSafetyPolicy, merge_constraints

    context = lifted_context()
    path = clearance(context)
    hard = HardSafetyLimits()
    builder = SafetyContextBuilder(
        merged=merge_constraints(hard, OperationalSafetyPolicy()), hard_limits=hard,
    )
    step = context.contract.steps[0]
    options = dict(
        contract=context.contract, step=step,
        robot_state=RobotState(tcp_pose=Pose(x=0.2, y=-0.1, z=0.048), connected=True),
        scene_version=1,
        resolved_parameters={
            **context.parameters, "vertical_clearance": path,
            "expected_holding_object_id": "object", "holding_object_id": "object",
        },
    )
    untrusted = builder.build(**options)
    assert untrusted.vertical_clearance is None
    assert untrusted.expected_holding_object_id is None
    assert untrusted.holding_object_id is None
    trusted = builder.build(**options, vertical_clearance=path,
                            expected_holding_object_id="object")
    assert MinimumHeightRule().evaluate(trusted).decision == SafetyDecision.ALLOW
    assert CarrySafetyRule().evaluate(trusted).decision == SafetyDecision.REJECT
