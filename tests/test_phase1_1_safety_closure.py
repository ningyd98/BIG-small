from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scripts.run_fixed_pick_place import run_mock_repeat

from cloud_edge_robot_arm.contracts import (
    ActionResult,
    ControlMode,
    FailurePolicy,
    RobotState,
    SafetyConstraints,
    SkillName,
    TaskContract,
    TaskStep,
    TaskTarget,
)
from cloud_edge_robot_arm.edge.contract_validator import EdgeContractValidator
from cloud_edge_robot_arm.edge.fixed_pick_place import run_fixed_pick_place
from cloud_edge_robot_arm.edge.robot_adapter import build_action_result
from cloud_edge_robot_arm.simulation.mock_robot import MockRobotAdapter, MockScene


def _contract_payload(now: datetime) -> dict[str, object]:
    contract = TaskContract(
        task_id="task-invalid-datetime",
        plan_version=1,
        command_seq=1,
        timestamp=now,
        control_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        issued_at=now,
        valid_until=now + timedelta(seconds=30),
        user_instruction="place the red cube into bin a",
        scene_version=1,
        expected_scene_version=1,
        task_target=TaskTarget(
            object_id="red_cube",
            object_class="cube",
            target_region_id="bin_a",
        ),
        steps=[
            TaskStep(
                step_id="step-home",
                skill=SkillName.HOME,
                parameters={},
                expected_duration_ms=10,
                timeout_ms=100,
                retry_limit=0,
                preconditions=[],
                success_conditions=[],
            )
        ],
        safety_constraints=SafetyConstraints(
            max_joint_velocity=0.5,
            max_tcp_velocity=0.15,
            minimum_safe_height=0.08,
            workspace_id="workspace_a",
            collision_check_required=True,
        ),
        failure_policy=FailurePolicy(
            local_retry_limit=0,
            on_timeout="SAFE_STOP",
            on_safety_rejection="PAUSE_AND_REPORT",
            on_network_loss="SAFE_STOP",
        ),
        completion_criteria=["robot_in_safe_pose"],
    )
    return contract.model_dump(mode="json")


def test_flow_stops_after_grasp_failure() -> None:
    robot = MockRobotAdapter(
        scene=MockScene.with_default_pick_place_scene(),
        grasp_failures_remaining=1,
    )

    summary = run_fixed_pick_place(robot)

    assert summary.success is False
    assert summary.failed_step_id == "GRASP"
    assert summary.history[-1] in {"STOP", "EMERGENCY_STOP"}
    assert summary.skipped_steps == [
        "LIFT",
        "MOVE_TO_REGION",
        "PLACE",
        "RELEASE",
        "RETREAT",
        "HOME",
    ]


def test_flow_does_not_lift_after_grasp_failure() -> None:
    robot = MockRobotAdapter(
        scene=MockScene.with_default_pick_place_scene(),
        grasp_failures_remaining=1,
    )

    summary = run_fixed_pick_place(robot)

    assert "GRASP" in summary.history
    assert "LIFT" not in summary.history


def test_flow_invokes_safe_stop_after_failure() -> None:
    robot = MockRobotAdapter(
        scene=MockScene.with_default_pick_place_scene(),
        grasp_failures_remaining=1,
    )

    run_fixed_pick_place(robot)

    assert robot.get_state().stopped is True
    assert robot.history[-1].action_type in {"STOP", "EMERGENCY_STOP"}


def test_runner_connects_and_disconnects() -> None:
    payload = run_mock_repeat(1)

    assert payload["successes"] == 1
    assert payload["lifecycle_history"] == ["CONNECT", "DISCONNECT"]


def test_robot_state_defaults_to_disconnected() -> None:
    assert RobotState().connected is False


def test_invalid_datetime_returns_structured_error() -> None:
    now = datetime(2026, 6, 13, 10, 30, tzinfo=UTC)
    payload = _contract_payload(now)
    payload["valid_until"] = "definitely-not-a-date"

    result = EdgeContractValidator(min_plan_version=1).accept_payload(payload, now=now)

    assert result.accepted is False
    assert result.error is not None
    assert result.error.code == "CONTRACT_SCHEMA_INVALID"


def test_fixed_flow_does_not_depend_on_mock_concrete_type() -> None:
    class RecordingPickPlaceAdapter:
        def __init__(self) -> None:
            self.calls: list[str] = []
            self.connected = True
            self.stopped = False

        def _ok(self, action_type: str) -> ActionResult:
            self.calls.append(action_type)
            return build_action_result(
                action_type=action_type,
                success=True,
                state_before={},
                state_after={},
                duration_ms=1,
            )

        def home(self, *, timeout_ms: int | None = None) -> ActionResult:
            return self._ok("HOME")

        def move_above(
            self, object_id: str, z_offset_m: float = 0.12, *, timeout_ms: int | None = None
        ) -> ActionResult:
            return self._ok("MOVE_ABOVE")

        def approach(self, object_id: str, *, timeout_ms: int | None = None) -> ActionResult:
            return self._ok("APPROACH")

        def grasp(self, object_id: str, *, timeout_ms: int | None = None) -> ActionResult:
            return self._ok("GRASP")

        def lift(self, height_m: float = 0.15, *, timeout_ms: int | None = None) -> ActionResult:
            return self._ok("LIFT")

        def move_to_region(self, region_id: str, *, timeout_ms: int | None = None) -> ActionResult:
            return self._ok("MOVE_TO_REGION")

        def place(self, region_id: str, *, timeout_ms: int | None = None) -> ActionResult:
            return self._ok("PLACE")

        def release(self, *, timeout_ms: int | None = None) -> ActionResult:
            return self._ok("RELEASE")

        def retreat(
            self, distance_m: float = 0.1, *, timeout_ms: int | None = None
        ) -> ActionResult:
            return self._ok("RETREAT")

        def stop(self, *, timeout_ms: int | None = None) -> ActionResult:
            self.stopped = True
            return self._ok("STOP")

        def emergency_stop(self, *, timeout_ms: int | None = None) -> ActionResult:
            self.stopped = True
            return self._ok("EMERGENCY_STOP")

        def object_region(self, object_id: str) -> str:
            return "bin_a"

    adapter = RecordingPickPlaceAdapter()

    summary = run_fixed_pick_place(adapter)

    assert summary.success is True
    assert adapter.calls == [
        "HOME",
        "MOVE_ABOVE",
        "APPROACH",
        "GRASP",
        "LIFT",
        "MOVE_TO_REGION",
        "PLACE",
        "RELEASE",
        "RETREAT",
        "HOME",
    ]
