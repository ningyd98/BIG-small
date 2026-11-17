"""Local route stages retain the registered endpoint and low-height boundary."""

from types import SimpleNamespace

import pytest

from cloud_edge_robot_arm.contracts import Pose, SkillName
from tests.phase2_helpers import step


@pytest.mark.parametrize("skill,current,target,intermediate", [
    (SkillName.RETREAT, (0.2, 0.25, 0.045), (0.2, 0.15, 0.16), (0.2, 0.25, 0.16)),
])
def test_staged_route_keeps_final_pose_and_binds_vertical_escape(
    skill, current, target, intermediate,
):
    from cloud_edge_robot_arm.research.sol_molmo_components import component_motion_phases

    original = step("motion", skill).model_copy(update={
        "parameters": {"target_pose": dict(zip("xyz", target, strict=True))},
    })
    phases = component_motion_phases(original, Pose(**dict(zip("xyz", current, strict=True))))
    assert len(phases) == 2
    assert phases[0].step_id != original.step_id
    assert phases[0].parameters["target_pose"] == dict(zip("xyz", intermediate, strict=True))
    assert phases[1] == original
    assert phases[0].timeout_ms == phases[1].timeout_ms


def test_already_aligned_transport_and_elevated_retreat_need_no_extra_phase():
    from cloud_edge_robot_arm.research.sol_molmo_components import component_motion_phases

    for skill, current in [(SkillName.MOVE_TO_REGION, (0.45, 0.0, 0.16)),
                           (SkillName.RETREAT, (0.2, 0.25, 0.16))]:
        original = step("motion", skill).model_copy(update={
            "parameters": {"target_pose": {"x": 0.2, "y": 0.15, "z": 0.16}},
        })
        assert component_motion_phases(
            original, Pose(**dict(zip("xyz", current, strict=True))),
        ) == [original]


@pytest.mark.parametrize("skill", ["RETREAT", "MOVE_TO_REGION", "PLACE"])
def test_retreat_does_not_require_destination_geometry_unused_by_its_target(monkeypatch, skill):
    import cloud_edge_robot_arm.research.sol_molmo_components as component
    from tests.test_servo_region_support import partial_region
    from tests.test_visual_servo import acquisition

    reference, tracked, evidence, _ = acquisition()
    obscured = partial_region(reference, "missing")
    monkeypatch.setattr(component, "detect_pose_marker", lambda *a, **k:
                        SimpleNamespace(status="OBSERVED"))
    monkeypatch.setattr("cloud_edge_robot_arm.vision.servo_region.measure_servo_region",
                        lambda *a, **k: (None, "region_missing_color_not_explained_by_foreground"))
    state = SimpleNamespace(gripper_open=skill == "RETREAT", holding_object_id="object")
    if skill == "RETREAT":
        _, audit = component._ground_component(
            obscured, tracked, evidence, "side_y_plus_id7_75mm_component_v1", skill, state,
            moving_camera=True,
        )
        assert audit["destination_source"] == "REFERENCE_REGION_NOT_USED_BY_THIS_MOTION"
    else:
        with pytest.raises(component.ComponentStopped):
            component._ground_component(
                obscured, tracked, evidence, "side_y_plus_id7_75mm_component_v1", skill, state,
                moving_camera=True,
            )
