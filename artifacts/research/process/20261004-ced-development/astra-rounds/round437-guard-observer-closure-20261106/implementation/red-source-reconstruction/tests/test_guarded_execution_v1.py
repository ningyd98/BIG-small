"""OC1 raw counter controls, with the actual diagnostic isolated in one node."""

import json
import os
from dataclasses import replace
from importlib import import_module, util
from pathlib import Path

import pytest

from cloud_edge_robot_arm.research.operational_time_v1 import _open_clock_for_test
from tests.test_operational_time_v1 import _identity
from tests.test_visual_raw_recorder_v3 import software_backend


def test_operational_guard_api_required():
    assert util.find_spec("cloud_edge_robot_arm.research.guarded_execution_v1") is not None, (
        "live deadline execution composition is missing"
    )


def api():
    return import_module("cloud_edge_robot_arm.research.guarded_execution_v1")


class RawCounter:
    resolution_seconds = 1e-9

    def __init__(self):
        self.now = 100
        self.current_identity = _identity()

    def identity(self):
        return self.current_identity

    def read_ns(self):
        return self.now


def configured():
    raw = RawCounter()
    owner = _open_clock_for_test(raw)
    token = owner.begin_event("allocation")
    owner.mark_event(token)
    receipt = owner.end_event(token)
    deadline = owner.start_deadline(task_key="one-task", origin=receipt, budget_ns=10)
    backend = software_backend()
    guard = api().OperationalExecutionGuardV1(
        owner, origin_token=token, deadline=deadline, backend=backend
    )
    return raw, owner, token, deadline, backend, guard


@pytest.mark.parametrize(
    "failure", ["equality", "later", "closed", "rollback", "identity", "episode", "cancel"]
)
def test_deadline_equality_identity_and_cancel_fail_closed(failure):
    raw, owner, _, _, backend, guard = configured()
    with backend.enforce_execution_guard(guard):
        raw.now = 109
        backend.step()
        if failure == "equality":
            raw.now = 110
        elif failure == "later":
            raw.now = 111
        elif failure == "closed":
            owner.close()
        elif failure == "rollback":
            raw.now = 108
        elif failure == "identity":
            raw.current_identity = replace(raw.current_identity, process_start_ticks=2)
        elif failure == "episode":
            backend._episode_id = "changed-episode"
        else:
            guard.cancel("requested stop")
        expected_error = TimeoutError if failure in {"equality", "later"} else RuntimeError
        with pytest.raises(expected_error) as caught:
            backend.step(3)
        if failure in {"equality", "later"}:
            assert str(caught.value) == "original execution deadline expired"
        assert backend.total_physics_steps == 1
        assert backend.estop_engaged
    with pytest.raises(RuntimeError):
        backend.step()


def test_foreign_origin_deadline_and_refresh_rejected():
    _, owner, token, deadline, backend, _ = configured()
    _, other, other_token, foreign, _, _ = configured()
    for selected_token, selected_deadline in ((other_token, deadline), (token, foreign)):
        with pytest.raises(RuntimeError):
            api().OperationalExecutionGuardV1(
                owner, origin_token=selected_token, deadline=selected_deadline, backend=backend
            )
    with pytest.raises(RuntimeError):
        owner.start_deadline(task_key="one-task", origin=deadline.origin, budget_ns=11)
    owner.close()
    other.close()


def test_guard_cannot_be_installed_on_another_backend():
    _, _, _, _, _, guard = configured()
    other = software_backend()
    with pytest.raises(RuntimeError, match="another backend"):
        with other.enforce_execution_guard(guard):
            other.step()
    assert other.total_physics_steps == 0


def test_diagnostic_scope_cannot_mint_native_authority():
    _, _, _, _, backend, guard = configured()
    with backend.enforce_execution_guard(guard):
        backend.step()
    assert guard.evidence_scope == "EXCLUDED_GUARDED_EXECUTION_DIAGNOSTIC"
    assert guard.native_authority == "UNAVAILABLE"
    assert guard.qualification == "UNKNOWN"
    assert not hasattr(guard, "certified_artifacts")


def test_actual_mujoco_guarded_diagnostic_no_render():
    stage = Path(os.environ["R413_STAGE_DIR"])
    output = stage / "actual-diagnostic"
    result = api().run_guarded_execution_diagnostic_v1(output)
    assert result["status"] == "PASS"
    assert result["physics_steps"] == 2
    assert result["qualification"] == "UNKNOWN"
    assert result["full_horizon_producer"] == "UNAVAILABLE"
    assert result["expected_refusals"] == ["expired_command", "expired_step", "closed_step"]
    operations = json.loads((output / "operations.json").read_text())
    assert not any(x["kind"] == "CAPTURE" for x in operations)
    assert sum(x["kind"] == "PHYSICS" and x["phase"] == "END" for x in operations) == 2
    assert not result["primary_error"]
    assert not result["secondary_errors"]


def test_diagnostic_retained_failures_change_status():
    evidence = {}
    for mode in ("stop", "snapshot", "expected_deadline"):
        backend = software_backend()
        primary = TimeoutError("original execution deadline expired")
        original_control = backend._apply_control
        original_snapshot = backend.current_physics_observation
        control_calls = []

        def bad_control_once():
            control_calls.append(1)
            if len(control_calls) == 1:
                raise ValueError("first stop control failed")
            original_control()

        def bad_snapshot():
            raise LookupError("failure snapshot unavailable")

        def reject(_):
            raise primary

        if mode == "stop":
            backend._apply_control = bad_control_once
        elif mode == "snapshot":
            backend.current_physics_observation = bad_snapshot
        with pytest.raises(TimeoutError) as caught:
            with backend.enforce_execution_guard(reject):
                backend.step()
        assert caught.value is primary
        assert backend.estop_engaged
        assert backend.total_physics_steps == 0
        backend.current_physics_observation = original_snapshot
        backend.emergency_stop()  # A later successful stop cannot erase the first failure.
        if mode == "stop":
            assert len(control_calls) == 2
        evidence[mode] = backend.execution_guard_events

    merge = getattr(api(), "_guard_secondary_errors", None)
    assert callable(merge), "diagnostic drops retained guard stop/snapshot failures"
    for mode, events in evidence.items():
        secondary = merge(events)
        primary_error = None  # Only the predeclared deadline refusal was caught.
        status = "PASS" if primary_error is None and not secondary else "FAIL"
        assert status == ("PASS" if mode == "expected_deadline" else "FAIL")
        if mode != "expected_deadline":
            assert len(secondary) == 1
            assert secondary[0]["stage"] == f"guard_{mode}"
            assert secondary[0]["type"] == ("ValueError" if mode == "stop" else "LookupError")
            assert secondary[0]["message"]
            closure = next(row for row in events if row["kind"] == "FAILURE")
            assert merge(({"closure": closure},)) == secondary
