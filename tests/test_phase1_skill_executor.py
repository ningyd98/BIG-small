from __future__ import annotations

from cloud_edge_robot_arm.contracts import SkillName, TaskStep
from cloud_edge_robot_arm.edge.skill_executor import SkillExecutor
from cloud_edge_robot_arm.edge.skill_registry import SkillRegistry
from cloud_edge_robot_arm.simulation.mock_robot import MockRobotAdapter, MockScene


def _step(step_id: str, skill: SkillName, **parameters: object) -> TaskStep:
    return TaskStep(
        step_id=step_id,
        skill=skill,
        parameters=parameters,
        expected_duration_ms=500,
        timeout_ms=2_000,
        retry_limit=0,
        preconditions=[],
        success_conditions=[],
    )


def test_all_phase_one_atomic_skills_are_registered_as_enum_handlers() -> None:
    registry = SkillRegistry.default()

    assert set(registry.skills()) == set(SkillName)
    for skill in SkillName:
        assert registry.handler_for(skill) is not None
    assert registry.handler_for("RUN_ARBITRARY_CODE") is None


def test_skill_executor_runs_fixed_pick_and_place_sequence() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene())
    executor = SkillExecutor(robot=robot, registry=SkillRegistry.default())
    steps = [
        _step("step-001", SkillName.HOME),
        _step("step-002", SkillName.OBSERVE),
        _step("step-003", SkillName.LOCATE_OBJECT, object_id="red_cube"),
        _step("step-004", SkillName.MOVE_ABOVE, object_id="red_cube", z_offset_m=0.12),
        _step("step-005", SkillName.APPROACH, object_id="red_cube"),
        _step("step-006", SkillName.GRASP, object_id="red_cube"),
        _step("step-007", SkillName.LIFT, height_m=0.16),
        _step("step-008", SkillName.MOVE_TO_REGION, region_id="bin_a"),
        _step("step-009", SkillName.PLACE, region_id="bin_a"),
        _step("step-010", SkillName.RELEASE),
        _step("step-011", SkillName.RETREAT, distance_m=0.1),
        _step("step-012", SkillName.VERIFY_RESULT, object_id="red_cube", region_id="bin_a"),
    ]

    results = [
        executor.execute_step(
            step,
            task_id="task-red-cube",
            plan_version=1,
            command_seq=index,
            scene_version=robot.scene_version,
        )
        for index, step in enumerate(steps, start=1)
    ]

    assert all(result.success for result in results)
    assert robot.object_region("red_cube") == "bin_a"
    assert results[-1].details["verified"] is True


def test_skill_executor_safe_stop_closes_execution_path() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene())
    executor = SkillExecutor(robot=robot, registry=SkillRegistry.default())

    result = executor.execute_step(
        _step("step-safe-stop", SkillName.SAFE_STOP),
        task_id="task-red-cube",
        plan_version=1,
        command_seq=99,
        scene_version=robot.scene_version,
    )

    assert result.success is True
    assert robot.state.estop_engaged is True
    assert result.details["robot_state"]["estop_engaged"] is True
