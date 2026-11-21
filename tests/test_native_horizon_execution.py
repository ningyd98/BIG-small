"""Full-horizon orchestration against explicit software execution seams."""

import json
from contextlib import ExitStack, contextmanager
from dataclasses import FrozenInstanceError, asdict
from datetime import UTC, datetime
from importlib import import_module, util
from types import SimpleNamespace

import pytest

from cloud_edge_robot_arm.contracts import ActionResult, SkillName
from cloud_edge_robot_arm.edge.runtime.skill_executor import StepExecutionResult
from cloud_edge_robot_arm.research.native_calibration_collection import action_horizons, detached
from cloud_edge_robot_arm.research.native_full_horizon_recorder import _v2_receipt
from cloud_edge_robot_arm.vision.native_completion_horizon import (
    completion_horizon_rational_v1,
    completion_horizon_rational_v2,
)
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
def run_fixture(
    skill="MOVE_ABOVE",
    controller_steps=2,
    success=True,
    callback=lambda: None,
    *,
    dispatch_step=0,
    controller_details=None,
):
    backend = software_backend()
    software_sensor_camera(backend)
    backend._total_physics_steps = dispatch_step
    backend._data.time = dispatch_step / 240
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
            details=(
                {"contact_hold_s": 0.5, "physics_steps": controller_steps}
                if controller_details is None
                else controller_details
            ),
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
        stack.enter_context(backend.enforce_execution_guard(lambda _: None, event_limit=40000))
        stack.enter_context(backend.capture_each_physics_step(max_captures=3000))
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


def v10_action(skill):
    row = next(row for row in action_horizons(use_v2=True) if row["skill"] == skill)
    return row, completion_horizon_rational_v2(skill, **row["recipe"])


@contextmanager
def run_v10_fixture(skill, **options):
    action, horizon_v2 = v10_action(skill)
    with run_fixture(skill, **options) as (kwargs, receipts, _):
        kwargs["step"] = kwargs["step"].model_copy(
            update={
                "timeout_ms": action["original_timeout_ms"],
                "metadata": {"horizon": action["horizon"]},
            }
        )
        yield action, horizon_v2, kwargs, receipts


@pytest.mark.parametrize(
    "skill,dispatch,controller_steps,terminal_steps",
    [
        ("MOVE_ABOVE", 120, 1920, 1920),
        ("LIFT", 4200, 2040, 2040),
        ("RELEASE", 10560, 240, 480),
    ],
)
@pytest.mark.parametrize("extra_steps", [0, 1])
def test_v10_deadline_is_inclusive_and_relative_to_dispatch(
    skill,
    dispatch,
    controller_steps,
    terminal_steps,
    extra_steps,
):
    returned = controller_steps + extra_steps
    with run_v10_fixture(skill, controller_steps=returned, dispatch_step=dispatch) as (
        action,
        horizon_v2,
        kwargs,
        receipts,
    ):
        receipt = runner()(**kwargs, horizon=horizon_v2)
        assert receipt.dispatch_step == dispatch
        assert receipt.controller_return_step == dispatch + returned
        assert receipts == [receipt]
        if extra_steps:
            assert receipt.reasons == ("controller_exceeded_registered_deadline",)
            assert receipt.terminal_step == dispatch + returned
            assert receipt.padding_interval_id is receipt.terminal_acquisition_id is None
            assert not receipt.complete and kwargs["backend"].estop_engaged
        else:
            assert receipt.complete and receipt.terminal_step == dispatch + terminal_steps
            assert receipt.terminal_acquisition_id == "terminal-1"
            _v2_receipt(
                detached(asdict(receipt)),
                action,
                task_id=kwargs["contract"].task_id,
                step=kwargs["step"],
            )


@pytest.mark.parametrize(
    "elapsed,details",
    [
        (121, {"contact_hold_s": 0.5}),
        (121, {"contact_hold_s": 0.5, "physics_steps": 121.0}),
        (121, {"contact_hold_s": 0.5, "physics_steps": True}),
        (121, {"contact_hold_s": 0.5, "physics_steps": 120}),
        (119, {"contact_hold_s": 0.5, "physics_steps": 119}),
        (121, {"contact_hold_s": 0.51, "physics_steps": 121}),
    ],
)
def test_v10_lift_deadline_requires_evidence_of_the_builtin_hold(elapsed, details):
    with run_v10_fixture(
        "LIFT", controller_steps=elapsed, dispatch_step=4200, controller_details=details
    ) as (_, horizon_v2, kwargs, receipts):
        receipt = runner()(**kwargs, horizon=horizon_v2)
        assert (receipt.reasons, receipt.complete) == (("controller_lift_hold_incomplete",), False)
        assert receipt.terminal_acquisition_id is None and receipt.terminal_step == 4200 + elapsed
        assert kwargs["backend"].estop_engaged and receipts == [receipt]


def test_v10_rejects_backend_config_with_the_wrong_physics_grid():
    with run_v10_fixture("RELEASE", dispatch_step=10560) as (_, horizon_v2, kwargs, receipts):
        backend = kwargs["backend"]
        backend._config = backend._config.model_copy(update={"physics_dt_s": 0.004})
        with pytest.raises(ValueError, match="physics grid"):
            runner()(**kwargs, horizon=horizon_v2)
        assert backend.total_physics_steps == 10560 and receipts == []


@pytest.mark.parametrize("delta", [-1, 1])
def test_v10_terminal_capture_must_leave_the_backend_at_the_exact_endpoint(delta):
    with run_v10_fixture("RELEASE", controller_steps=240, dispatch_step=10560) as (
        _,
        horizon_v2,
        kwargs,
        receipts,
    ):
        backend = kwargs["backend"]
        recorder = kwargs["recorder"]
        capture = recorder.capture

        def capture_and_change_step():
            capture()
            backend._total_physics_steps += delta

        recorder.capture = capture_and_change_step
        with pytest.raises(RuntimeError, match="terminal capture"):
            runner()(**kwargs, horizon=horizon_v2)
        assert len(receipts) == 1 and not receipts[0].complete
        assert receipts[0].terminal_step == 10560 + 480 + delta


def test_v10_cannot_reuse_the_previous_acquisition_as_its_terminal_frame():
    with run_v10_fixture("RELEASE", controller_steps=240, dispatch_step=10560) as (
        _,
        horizon_v2,
        kwargs,
        receipts,
    ):
        recorder = kwargs["recorder"]
        recorder.allocated_acquisition_ids.append("previous")
        recorder.capture = lambda: None
        with pytest.raises(RuntimeError, match="terminal capture"):
            runner()(**kwargs, horizon=horizon_v2)
        assert len(receipts) == 1 and not receipts[0].complete
        assert receipts[0].terminal_acquisition_id is None


@pytest.mark.parametrize(
    "field,reason",
    [
        ("return", "controller_exceeded_registered_deadline"),
        ("start", "receipt window invalid"),
        ("early", "exact terminal step"),
        ("late", "receipt window invalid"),
        ("capture", "receipt identity required"),
        ("step", "source association differs"),
        ("recipe", "source association differs"),
    ],
)
def test_v10_receipt_reader_rechecks_the_declared_step_window(field, reason):
    with run_v10_fixture("RELEASE", controller_steps=240, dispatch_step=10560) as (
        action,
        horizon_v2,
        kwargs,
        _,
    ):
        receipt = detached(asdict(runner()(**kwargs, horizon=horizon_v2)))
        if field == "return":
            receipt["controller_return_step"] += 1
        elif field == "start":
            receipt["dispatch_step"] -= 1
        elif field == "early":
            receipt["terminal_step"] -= 1
        elif field == "late":
            receipt["terminal_step"] += 1
        elif field == "capture":
            receipt["terminal_acquisition_id"] = None
        elif field == "step":
            receipt["step_id"] = "another-step"
        else:
            modified = json.loads(receipt["horizon_json"])
            modified["controller_deadline_steps"] += 1
            receipt["horizon_json"] = json.dumps(modified)
        with pytest.raises(ValueError, match=reason):
            _v2_receipt(receipt, action, task_id=kwargs["contract"].task_id, step=kwargs["step"])


def test_v10_receipt_reader_checks_lift_hold_evidence_even_at_the_correct_terminal():
    with run_v10_fixture("LIFT", controller_steps=2040, dispatch_step=4200) as (
        action,
        horizon_v2,
        kwargs,
        _,
    ):
        receipt = detached(asdict(runner()(**kwargs, horizon=horizon_v2)))
        result = json.loads(receipt["controller_result_json"])
        result["action_result"]["details"]["physics_steps"] -= 1
        receipt["controller_result_json"] = json.dumps(result)
        with pytest.raises(ValueError, match="controller_lift_hold_incomplete"):
            _v2_receipt(receipt, action, task_id=kwargs["contract"].task_id, step=kwargs["step"])
