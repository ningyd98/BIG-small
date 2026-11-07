"""Full-horizon orchestration against explicit software execution seams."""

from contextlib import ExitStack, contextmanager
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from importlib import import_module, util
from types import SimpleNamespace

import pytest

from cloud_edge_robot_arm.contracts import ActionResult, SkillName
from cloud_edge_robot_arm.edge.runtime.skill_executor import StepExecutionResult
from cloud_edge_robot_arm.vision.native_completion_horizon import completion_horizon_rational_v1
from tests.test_visual_owner_registration import values
from tests.test_visual_raw_recorder_v3 import software_backend, software_sensor_camera


def test_full_horizon_session_api_required():
    name = "cloud_edge_robot_arm.simulation.mujoco.native_horizon"
    module = import_module(name) if util.find_spec(name) else None
    assert callable(getattr(module, "_run_registered_horizon", None)), "full-H runner missing"


def horizon(skill, steps=24, included=False):
    return completion_horizon_rational_v1(
        skill,
        dt_numerator=1,
        dt_denominator=240,
        registered_dt_s=1 / 240,
        original_timeout_ns=steps * 10**9 // 240,
        original_expected_ns=1,
        compiled_timeout_ns=1,
        compiled_expected_ns=1,
        effective_owner_required_ns=1,
        builtin_tail_included=included,
    )


@contextmanager
def run_fixture(skill="MOVE_ABOVE", controller_steps=2, success=True, callback=lambda: None):
    backend = software_backend()
    software_sensor_camera(backend)
    original = values()["original"]
    contract = original.contract
    step = contract.steps[0].model_copy(update={"skill": SkillName(skill)})
    state = SimpleNamespace(holding_object_id=contract.task_target.object_id, gripper_open=True)
    robot = SimpleNamespace(_backend=backend, get_state=lambda: state)
    executor = SimpleNamespace(_robot=robot)
    receipts, capture_ids, purposes = [], [], []

    @contextmanager
    def purpose(kind):
        purposes.append((kind, backend.total_physics_steps))
        yield "hold-1"

    def execute_attempt(**kwargs):
        backend.step(controller_steps)
        now = datetime.now(UTC)
        action = ActionResult(
            success=success,
            action_id="action-1",
            action_type=skill,
            started_at=now,
            finished_at=now,
            duration_ms=1,
            details={"contact_hold_s": 0.5},
        )
        return StepExecutionResult(
            contract.task_id, step.step_id, skill, 1, success, None, action, 1, now
        )

    def capture():
        backend.capture_sensor_frame_with_instances()
        capture_ids.append("terminal-1")

    recorder = SimpleNamespace(
        backend=backend,
        executor=executor,
        _original=original,
        execute_attempt=execute_attempt,
        purpose=purpose,
        capture=capture,
        allocated_acquisition_ids=capture_ids,
        record_horizon=receipts.append,
    )
    kwargs = dict(
        backend=backend,
        robot=robot,
        executor=executor,
        recorder=recorder,
        contract=contract,
        step=step,
        grounding=None,
        check_active=callback,
    )
    with ExitStack() as stack:
        stack.enter_context(backend.observe_operation_boundaries(lambda _: None))
        stack.enter_context(backend.enforce_execution_guard(lambda _: None, event_limit=20000))
        stack.enter_context(backend.capture_each_physics_step(max_captures=2000))
        yield kwargs, receipts, state


def runner():
    return import_module(
        "cloud_edge_robot_arm.simulation.mujoco.native_horizon"
    )._run_registered_horizon


def test_early_success_keeps_actual_controller_target_until_registered_terminal():
    with run_fixture() as (kwargs, receipts, _):
        backend = kwargs["backend"]
        target = backend._target_positions.copy()
        result = runner()(**kwargs, horizon=horizon("MOVE_ABOVE"))
        assert (result.dispatch_step, result.controller_return_step, result.terminal_step) == (
            0,
            2,
            24,
        )
        assert result.complete and not result.reasons
        assert result.terminal_acquisition_id == "terminal-1"
        assert backend._target_positions.tolist() == target.tolist()
        assert not backend.command_records  # Padding issued no HOLD/replacement command.
        assert receipts == [result]
        with pytest.raises(FrozenInstanceError):
            result.complete = False


def test_unsuccessful_controller_stops_without_padding_or_terminal_capture():
    with run_fixture(success=False) as (kwargs, receipts, _):
        result = runner()(**kwargs, horizon=horizon("MOVE_ABOVE"))
        assert not result.complete
        assert result.terminal_step == result.controller_return_step == 2
        assert result.padding_interval_id is result.terminal_acquisition_id is None
        assert result.reasons == ("controller_unsuccessful",)
        assert kwargs["backend"].estop_engaged
        assert receipts == [result]


def test_controller_overrun_retains_actual_steps_and_never_reports_complete():
    with run_fixture(controller_steps=25) as (kwargs, receipts, _):
        result = runner()(**kwargs, horizon=horizon("MOVE_ABOVE"))
        assert not result.complete and result.terminal_step == 25
        assert result.reasons == ("controller_exceeded_registered_horizon",)
        assert receipts == [result]


@pytest.mark.parametrize("included,base,expected", [(False, 24, 144), (True, 144, 144)])
def test_lift_tail_is_not_added_twice(included, base, expected):
    with run_fixture("LIFT", controller_steps=120) as (kwargs, _, _):
        result = runner()(**kwargs, horizon=horizon("LIFT", steps=base, included=included))
        assert result.complete and result.terminal_step == expected


@pytest.mark.parametrize("returned,complete", [(24, True), (25, False)])
def test_release_requires_full_one_second_after_open_controller_return(returned, complete):
    with run_fixture("RELEASE", controller_steps=returned) as (kwargs, _, _):
        result = runner()(**kwargs, horizon=horizon("RELEASE"))
        assert result.complete is complete
        assert result.terminal_step == (264 if complete else returned)


def test_expiry_at_equality_after_return_retains_controller_result_and_effect():
    checks = [0]
    expired = TimeoutError("original deadline equality")

    def check():
        checks[0] += 1
        if checks[0] == 2:
            raise expired

    with run_fixture(callback=check) as (kwargs, receipts, _):
        with pytest.raises(TimeoutError) as caught:
            runner()(**kwargs, horizon=horizon("MOVE_ABOVE"))
        assert caught.value is expired
        assert receipts[0].controller_result_json is not None
        assert receipts[0].controller_return_step == receipts[0].terminal_step == 2
        assert not receipts[0].complete


def test_grasp_loss_during_padding_preserves_partial_instead_of_finishing():
    with run_fixture("GRASP") as (kwargs, receipts, state):

        def check():
            if kwargs["backend"].total_physics_steps >= 3:
                state.holding_object_id = None

        kwargs["check_active"] = check
        with pytest.raises(RuntimeError, match="grasp lost"):
            runner()(**kwargs, horizon=horizon("GRASP"))
        assert receipts[0].terminal_step == 3
        assert not receipts[0].complete


def test_public_session_construction_cannot_issue_authority():
    module = import_module("cloud_edge_robot_arm.simulation.mujoco.native_horizon")
    with pytest.raises(TypeError, match="live collection"):
        module.NativeHorizonSession()
