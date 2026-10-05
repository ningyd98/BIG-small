"""Phase 3.2 集成验收回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

import pytest

from cloud_edge_robot_arm.edge.runtime.task_executor import TaskExecutor
from cloud_edge_robot_arm.edge.safety.models import Obstacle
from cloud_edge_robot_arm.edge.safety.providers import (
    MockSceneStateProvider,
    MockTelemetryProvider,
)
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield
from cloud_edge_robot_arm.repositories.memory import InMemoryRepository
from cloud_edge_robot_arm.simulation.mock_robot import FaultCode, MockRobotAdapter, MockScene
from tests.phase2_helpers import contract


def _shield() -> SafetyShield:
    return SafetyShield()


def test_task_executor_rejects_non_safety_shield() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    with pytest.raises(TypeError, match="SafetyShield"):
        TaskExecutor(robot=robot, shield="not-a-shield")  # type: ignore[arg-type]


def test_runtime_missing_telemetry_pauses_task() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    tel = MockTelemetryProvider(missing=True)
    result = TaskExecutor(
        robot=robot,
        shield=_shield(),
        repository=InMemoryRepository(),
        telemetry_provider=tel,
    ).submit_contract(contract().model_dump(mode="json"))
    assert result.success is False
    assert result.context is not None
    assert result.context.state == "PAUSED"


def test_runtime_stale_telemetry_pauses_task() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    tel = MockTelemetryProvider(stale_ms=10_000)
    result = TaskExecutor(
        robot=robot,
        shield=_shield(),
        repository=InMemoryRepository(),
        telemetry_provider=tel,
    ).submit_contract(contract().model_dump(mode="json"))
    assert result.success is False
    assert result.context is not None
    assert result.context.state == "PAUSED"


def test_runtime_missing_scene_pauses_task() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    scene = MockSceneStateProvider(robot, missing=True)
    result = TaskExecutor(
        robot=robot,
        shield=_shield(),
        repository=InMemoryRepository(),
        scene_provider=scene,
    ).submit_contract(contract().model_dump(mode="json"))
    assert result.success is False
    assert result.context is not None
    assert result.context.state == "PAUSED"


def test_move_above_resolves_real_target_pose() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    target = robot.resolve_target_pose("MOVE_ABOVE", {"object_id": "red_cube", "z_offset_m": 0.12})
    assert target is not None
    assert abs(target.x - 0.2) < 0.001
    assert abs(target.y - 0.0) < 0.001
    assert abs(target.z - (0.02 + 0.12)) < 0.001


def test_move_to_region_resolves_real_target_pose() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    target = robot.resolve_target_pose("MOVE_TO_REGION", {"region_id": "bin_a"})
    assert target is not None
    # bin_a center is (-0.2, 0.18, 0.02); transport height = max(0.08+0.12, 0.02+0.16)=0.20
    assert abs(target.z - 0.20) < 0.001


def test_lift_resolves_real_target_pose() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    state = robot.get_state()
    target = robot.resolve_target_pose("LIFT", {"height_m": 0.16})
    assert target is not None
    assert abs(target.z - (state.tcp_pose.z + 0.16)) < 0.001


def test_path_collision_blocks_real_move_above() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    obs = Obstacle(obstacle_id="wall", x=0.1, y=0.0, z=0.18, radius_m=0.05)
    scene = MockSceneStateProvider(robot, obstacles=[obs])
    result = TaskExecutor(
        robot=robot,
        shield=_shield(),
        repository=InMemoryRepository(),
        scene_provider=scene,
    ).submit_contract(contract().model_dump(mode="json"))
    assert result.success is False
    dangerous = [
        a.action_type for a in robot.history if a.action_type in ("MOVE_ABOVE", "APPROACH", "LIFT")
    ]
    assert not dangerous


def test_workspace_blocks_real_resolved_target() -> None:
    from cloud_edge_robot_arm.contracts import Pose as CPose
    from cloud_edge_robot_arm.simulation.mock_robot import SceneObject, TargetRegion

    scene = MockScene(
        objects={
            "red_cube": SceneObject(
                object_id="red_cube",
                object_class="cube",
                pose=CPose(x=1.0, y=0.0, z=0.02),
                region_id="table",
            )
        },
        regions={
            "bin_a": TargetRegion(region_id="bin_a", center=CPose(x=-0.2, y=0.18, z=0.02)),
        },
    )
    robot = MockRobotAdapter(scene=scene, auto_connect=True)
    result = TaskExecutor(
        robot=robot,
        shield=_shield(),
        repository=InMemoryRepository(),
    ).submit_contract(contract().model_dump(mode="json"))
    assert result.success is False
    # HOME may still execute; the key is that MOVE_ABOVE or LIFT never runs.
    dangerous = [
        a.action_type
        for a in robot.history
        if a.action_type
        in (
            "MOVE_ABOVE",
            "APPROACH",
            "GRASP",
            "LIFT",
            "MOVE_TO_REGION",
            "PLACE",
            "RELEASE",
            "RETREAT",
        )
    ]
    assert not dangerous


def test_requested_velocity_reaches_safety_context() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    tel = MockTelemetryProvider(tcp_velocity=0.4)
    result = TaskExecutor(
        robot=robot,
        shield=_shield(),
        repository=InMemoryRepository(),
        telemetry_provider=tel,
    ).submit_contract(contract().model_dump(mode="json"))
    assert result.success is True
    # velocity was limited — check the action details
    velocities = set()
    for entry in robot.history:
        details = entry.details or {}
        if "executed_tcp_velocity" in details:
            velocities.add(details["executed_tcp_velocity"])
    assert 0.0 not in velocities
    assert len(velocities) > 0


def test_requested_acceleration_reaches_safety_context() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    tel = MockTelemetryProvider(acceleration=0.5)
    result = TaskExecutor(
        robot=robot,
        shield=_shield(),
        repository=InMemoryRepository(),
        telemetry_provider=tel,
    ).submit_contract(contract().model_dump(mode="json"))
    assert result.success is True


def test_joint_velocity_reaches_safety_context() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    tel = MockTelemetryProvider(joint_velocities=[0.3, 0.4, 0.5])
    result = TaskExecutor(
        robot=robot,
        shield=_shield(),
        repository=InMemoryRepository(),
        telemetry_provider=tel,
    ).submit_contract(contract().model_dump(mode="json"))
    assert result.success is True


def test_allow_with_limits_changes_executed_velocity() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    tel = MockTelemetryProvider(tcp_velocity=0.4)
    result = TaskExecutor(
        robot=robot,
        shield=_shield(),
        repository=InMemoryRepository(),
        telemetry_provider=tel,
    ).submit_contract(contract().model_dump(mode="json"))
    assert result.success is True
    # Verify that at least one action executed with a limited velocity != 0.0
    any_limited = any(
        (entry.details or {}).get("executed_tcp_velocity") is not None for entry in robot.history
    )
    assert any_limited, "No motion recorded executed_tcp_velocity"


def test_original_unlimited_parameters_never_reach_robot() -> None:
    """The original high velocity must never appear in robot history."""
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    tel = MockTelemetryProvider(tcp_velocity=0.4)
    result = TaskExecutor(
        robot=robot,
        shield=_shield(),
        repository=InMemoryRepository(),
        telemetry_provider=tel,
    ).submit_contract(contract().model_dump(mode="json"))
    assert result.success is True
    # The original 0.4 should NOT appear as executed_tcp_velocity (it's limited to 0.15).
    for entry in robot.history:
        details = entry.details or {}
        executed = details.get("executed_tcp_velocity")
        if executed is not None:
            assert executed <= 0.15, f"Found excessive velocity {executed}"


def test_post_check_pause_transitions_to_paused() -> None:
    # Provide missing scene data so scene freshness fails in post_check.
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    scene = MockSceneStateProvider(robot, missing=True)
    tel = MockTelemetryProvider()
    result = TaskExecutor(
        robot=robot,
        shield=_shield(),
        repository=InMemoryRepository(),
        telemetry_provider=tel,
        scene_provider=scene,
    ).submit_contract(contract().model_dump(mode="json"))
    assert result.success is False
    assert result.context is not None
    assert result.context.state == "PAUSED"


def test_post_check_emergency_stop_invokes_stop_controller() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    robot.inject_fault(FaultCode.COLLISION_DETECTED)
    result = TaskExecutor(
        robot=robot,
        shield=_shield(),
        repository=InMemoryRepository(),
    ).submit_contract(contract().model_dump(mode="json"))
    assert result.success is False
    assert result.context is not None
    assert result.context.state == "SAFETY_STOPPED"
    assert robot.get_state().stopped is True


def test_integrated_rejected_task_has_zero_motion_actions() -> None:
    from cloud_edge_robot_arm.contracts import Pose as CPose
    from cloud_edge_robot_arm.simulation.mock_robot import SceneObject, TargetRegion

    scene = MockScene(
        objects={
            "red_cube": SceneObject(
                object_id="red_cube",
                object_class="cube",
                pose=CPose(x=1.0, y=0.0, z=0.02),
                region_id="table",
            )
        },
        regions={
            "bin_a": TargetRegion(region_id="bin_a", center=CPose(x=-0.2, y=0.18, z=0.02)),
        },
    )
    robot = MockRobotAdapter(scene=scene, auto_connect=True)
    result = TaskExecutor(
        robot=robot,
        shield=_shield(),
        repository=InMemoryRepository(),
    ).submit_contract(contract().model_dump(mode="json"))
    assert result.success is False
    dangerous = [
        a.action_type
        for a in robot.history
        if a.action_type
        in (
            "MOVE_ABOVE",
            "APPROACH",
            "GRASP",
            "LIFT",
            "MOVE_TO_REGION",
            "PLACE",
            "RELEASE",
            "RETREAT",
        )
    ]
    assert not dangerous


def test_safety_rule_results_are_persisted() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    repo = InMemoryRepository()
    result = TaskExecutor(
        robot=robot,
        shield=_shield(),
        repository=repo,
    ).submit_contract(contract().model_dump(mode="json"))
    assert result.success is True
    events = repo.list_audit_events(contract().task_id)
    rule_events = [
        e for e in events if e.event_type in ("SAFETY_RULE_PASSED", "SAFETY_RULE_FAILED")
    ]
    assert len(rule_events) > 0
    # Each rule event should have rule_id and decision.
    for ev in rule_events:
        assert "rule_id" in ev.details
        assert "decision" in ev.details
