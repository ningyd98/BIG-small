"""Phase 3 安全屏障和故障场景回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from cloud_edge_robot_arm.edge.runtime.task_executor import TaskExecutor
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield
from cloud_edge_robot_arm.repositories.memory import InMemoryRepository
from cloud_edge_robot_arm.repositories.sqlite import SQLiteRepository
from cloud_edge_robot_arm.simulation.mock_robot import FaultCode, MockRobotAdapter, MockScene
from tests.phase2_helpers import contract


def test_inmemory_safety_stop_records_audit_events() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    robot.inject_fault(FaultCode.COLLISION_DETECTED)
    repository = InMemoryRepository()

    result = TaskExecutor(
        robot=robot, shield=SafetyShield(), repository=repository
    ).submit_contract(contract().model_dump(mode="json"))

    assert result.success is False
    assert result.context is not None
    assert result.context.state == "SAFETY_STOPPED"
    events = [e.event_type for e in repository.list_audit_events(result.context.task_id)]
    assert "STOP_REQUESTED" in events
    assert "TASK_FAILED" in events


def test_sqlite_safety_stop_records_audit_events(tmp_path: object) -> None:
    db_path = tmp_path / "safety_stop.sqlite3"  # type: ignore[operator]
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    robot.inject_fault(FaultCode.COLLISION_DETECTED)
    repository = SQLiteRepository(db_path)

    result = TaskExecutor(
        robot=robot, shield=SafetyShield(), repository=repository
    ).submit_contract(contract(task_id="task-sqlite-safety").model_dump(mode="json"))

    assert result.success is False
    assert result.context is not None
    assert result.context.state == "SAFETY_STOPPED"
    events = [e.event_type for e in repository.list_audit_events("task-sqlite-safety")]
    assert "STOP_REQUESTED" in events
    assert "TASK_FAILED" in events
    repository.close()


def test_sqlite_stop_action_execution_persisted(tmp_path: object) -> None:
    db_path = tmp_path / "stop_action.sqlite3"  # type: ignore[operator]
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    robot.inject_fault(FaultCode.COLLISION_DETECTED)
    repository = SQLiteRepository(db_path)

    result = TaskExecutor(
        robot=robot, shield=SafetyShield(), repository=repository
    ).submit_contract(contract(task_id="task-stop-action").model_dump(mode="json"))

    assert result.context is not None
    actions = repository.list_action_executions("task-stop-action")
    action_types = [a.action_type for a in actions]
    assert "STOP" in action_types
    repository.close()


def test_emergency_stop_only_when_stop_fails(tmp_path: object) -> None:
    db_path = tmp_path / "estop_only.sqlite3"  # type: ignore[operator]
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    repository = SQLiteRepository(db_path)

    result = TaskExecutor(
        robot=robot, shield=SafetyShield(), repository=repository
    ).submit_contract(contract(task_id="task-normal-complete").model_dump(mode="json"))

    assert result.success is True
    actions = repository.list_action_executions("task-normal-complete")
    action_types = [a.action_type for a in actions]
    assert "STOP" not in action_types
    assert "EMERGENCY_STOP" not in action_types
    repository.close()
