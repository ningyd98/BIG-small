"""Handwritten SOFTWARE_ONLY full-H originals, never a private recorder export.

In particular the synthetic COMMAND D rows are not issued by today's prefix
producer. The independent oracle is dispatch120/return121/terminal123 at 1/240.
"""

import copy
import hashlib
import json
from dataclasses import asdict, replace
from importlib import import_module

import pytest

from cloud_edge_robot_arm.research.raw_episode_v3 import _camera_hash
from tests.test_native_completion_horizon_v1 import recipe
from tests.test_raw_episode_v3 import control, fixture, hash_payload, state

CONTROLLER = "src/cloud_edge_robot_arm/edge/runtime/skill_executor.py"
SHA = "a" * 64
DOMAIN = "b" * 64


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


@pytest.fixture(scope="module")
def source():
    _, records = fixture()
    old = records.actions[0]
    contract = old.original_plan.contract.model_copy(deep=True)
    step = contract.steps[0].model_copy(update={"timeout_ms": 10, "expected_duration_ms": 10})
    contract.steps[0] = step
    requirements = dict(old.original_plan.requirements)
    requirements["move"] = replace(
        requirements["move"],
        _original_step_json=encoded(step.model_dump(mode="json")).decode(),
        expected_duration_s=0.0125,
    )
    original = replace(
        old.original_plan,
        _contract_json=encoded(contract.model_dump(mode="json")).decode(),
        requirements=requirements,
    )
    action = old.to_payload()
    action.pop("identity")
    action.update(
        original_plan=original.to_payload(),
        executed_step_payload=step.model_dump(mode="json"),
        error=None,
        command_seq_start=1,
        command_seq_end=2,
    )
    action["returned_result"].update(success=True, error_code=None)
    intervals, events, backend, operations, physics, commands, frames = [], [], [], {}, [], [], []

    def interval(name, kind, start, end, clock0, clock1):
        row = dict(
            interval_id=name,
            record_seq=len(intervals) + 1,
            kind=kind,
            start=[clock0, clock0 * 1000, "2026-01-01T00:00:00+00:00", clock0 * 1000 + 1],
            end=[clock1, clock1 * 1000, "2026-01-01T00:00:00+00:00", clock1 * 1000 + 1],
            start_step=start,
            end_step=end,
            start_sim_time_s=start / 240,
            end_sim_time_s=end / 240,
            disposition="COMPLETE",
            error=None,
        )
        intervals.append(row)
        return row

    def operation(kind, start, end, result, parent, *, parameters=None, acquisition=None):
        number = len(events) + 1
        begin_seq = (number - 1) * 3 + 1
        common = dict(
            operation_id=number,
            kind=kind,
            episode_id="episode",
            parameters=parameters or {},
            error=None,
            error_type=None,
        )
        begin = common | dict(
            phase="BEGIN", physics_step=start, sim_time_s=start / 240, result=None
        )
        finish = common | dict(phase="END", physics_step=end, sim_time_s=end / 240, result=result)
        event = dict(
            attempt_seq=number,
            operation_id=number,
            kind=kind,
            source_session_id="session",
            domain_sha256=DOMAIN,
            begin=begin,
            end=finish,
            begin_seq=begin_seq,
            mark_seq=begin_seq + 1,
            end_seq=begin_seq + 2,
            token_identity=f"token-{number}",
            begin_ns=number * 100,
            bracket=dict(
                event_identity=f"token-{number}",
                lower_ns=number * 100,
                upper_ns=number * 100 + 20,
                domain_sha256=DOMAIN,
            ),
            acquisition_id=acquisition,
            error=None,
        )
        events.append(event)
        backend.extend(
            {
                key: boundary[key]
                for key in (
                    "operation_id",
                    "kind",
                    "phase",
                    "episode_id",
                    "physics_step",
                    "error_type",
                    "error",
                )
            }
            for boundary in (begin, finish)
        )
        if kind != "RESET":
            row = interval(
                f"operation-{number}",
                {
                    "CONTROL": "CONTROL_APPLY",
                    "PHYSICS": "PHYSICS_STEP",
                    "COMMAND": "COMMAND",
                    "CAPTURE": "ACQUISITION",
                }[kind],
                start,
                end,
                begin_seq,
                begin_seq + 2,
            )
            operations[str(number)] = dict(
                parameters=parameters or {},
                acquisition_id=acquisition,
                parent=parent,
                action="span-1" if parent == "attempt" else None,
                input_role="ONLINE",
                row=row,
            )
        return number

    reset_result = dict(
        physics_state=state(0),
        physics_dt_s=1 / 240,
        initial_controller_targets=dict(joints_rad=[0] * 7, fingers_m=[0.039] * 2),
        actuator_delay_steps=0,
    )
    operation("RESET", 0, 0, reset_result, None)
    interval("settle", "SETTLE", 0, 120, 4, 725)

    def physical(n, parent):
        c = operation("CONTROL", n - 1, n - 1, {"control_state": control(n)}, parent)
        p = operation("PHYSICS", n - 1, n, {"physics_state": state(n)}, parent)
        physics.append(
            dict(
                record_seq=1000 + n,
                physics_step=n,
                previous_state_hash=hash_payload(state(n - 1)),
                post_state_payload=state(n),
                control_payload=control(n),
                physics_interval_id=f"operation-{p}",
                control_interval_id=f"operation-{c}",
                purpose_interval_id=parent,
            )
        )

    def capture(acquisition, n):
        old_frame = records.frames[0].to_payload()
        old_frame.pop("identity")
        obs = copy.deepcopy(old_frame["observation_payload"])
        obs.update(
            frame_id=acquisition, observation_id=acquisition, sim_time_s=n / 240, checksum_sha256=""
        )
        # The gate checks canonical observation and same-state source joins; RGB-D
        # geometry itself stays in the separate R427 reconstruction reader.
        from cloud_edge_robot_arm.vision.observations import RGBDObservation

        obs = RGBDObservation.model_validate(obs).model_dump(mode="json")
        camera = copy.deepcopy(old_frame["camera_state_payload"])
        camera["sim_time_s"] = n / 240
        passes = [_camera_hash(camera)] * 3
        sensor = dict(frame_id=acquisition, episode_id="episode", sim_time_s=n / 240)
        op = operation(
            "CAPTURE",
            n,
            n,
            dict(sensor_frame=sensor, pass_state_hashes=passes),
            "unbracketed-operations",
            parameters=dict(physics_state=state(n), camera_state=camera),
            acquisition=acquisition,
        )
        old_frame.update(
            acquisition_id=acquisition,
            interval_id=f"operation-{op}",
            observation_payload=obs,
            camera_state_payload=camera,
            joined_physics_observation_hash=hash_payload(state(n)),
            pass_state_hashes=passes,
            file_hashes={},
        )
        frames.append(old_frame)
        return op

    for n in range(1, 121):
        physical(n, "settle")
    open_op = capture("before", 120)
    interval("attempt", "EXECUTOR_ATTEMPT", 120, 121, open_op * 3 + 1, open_op * 3 + 9)

    def command(kind, n, parent, sequence):
        payload = dict(
            type=kind,
            accepted=True,
            reason="",
            after_emergency_stop=False,
            sim_time_s=n / 240,
            episode_id="episode",
            physics_step=n,
            command_seq=sequence,
            target_positions_rad=[0] * 7,
            applied_target_positions_rad=[0] * 7,
        )
        op = operation("COMMAND", n, n, {"command_records": [payload]}, parent)
        commands.append(
            dict(
                record_seq=2000 + sequence,
                command_seq=sequence,
                command_payload=payload,
                interval_id=f"operation-{op}",
                parent_interval_id=parent,
                owner_action_span_id="span-1" if parent == "attempt" else None,
                effective_from_step=n + 1,
            )
        )

    command("joint_target", 120, "attempt", 1)
    physical(121, "attempt")
    interval("hold", "HOLD", 121, 123, (len(events)) * 3 + 1, (len(events) + 5) * 3)
    command("hold_current_joints", 121, "hold", 2)
    physical(122, "hold")
    physical(123, "hold")
    close_op = capture("terminal", 123)
    action["interval_id"] = "attempt"
    ledger = dict(
        schema_version="simulation.operational-prefix.originals.v1",
        source_session_id="session",
        domain_sha256=DOMAIN,
        events=events,
        current=None,
        allocated_acquisition_ids=["before", "terminal"],
        allocated_action_ids=["span-1"],
        failures=[],
        backend_observer_failures=[],
        super_audit_failures=[],
    )
    raw = dict(
        schema_version="native.completion.full-horizon-originals.v1",
        source_session_id="session",
        domain_sha256=DOMAIN,
        operational_ledger=ledger,
        backend_operation_ledger=backend,
        pending_operation_ids=[],
        incomplete_operation_ids=[],
        legacy_operations=operations,
        legacy_intervals=intervals,
        legacy_clock_pairs=[],
        legacy_reset_journal=[],
        legacy_reset_metadata={"config": {"physics_dt_s": 1 / 240}},
        legacy_reset_result=reset_result,
        legacy_reset_count=1,
        legacy_physics=physics,
        legacy_commands=commands,
        legacy_frames=frames,
        legacy_frame_aux={},
        legacy_actions=[action],
        legacy_purpose_allocations=["settle", "hold"],
        last_captured_frame=None,
        explicit_acquisitions=2,
        observed_episode_id="episode",
        observed_total_physics_steps=123,
        source_hashes=dict(original.source_hashes) | {CONTROLLER: SHA},
    )
    registered = recipe(
        original_timeout_ns=10_000_000,
        original_expected_ns=10_000_000,
        compiled_timeout_ns=10_000_000,
        compiled_expected_ns=10_000_000,
        effective_owner_required_ns=12_500_000,
    )
    prereg = dict(
        schema_version="native.completion.horizon-preregistration.v1",
        source_session_id="session",
        episode_id="episode",
        domain_sha256=DOMAIN,
        span_id="span-1",
        recipe=registered,
        step_id="move",
        attempt=1,
        original_plan_sha256=hash_payload(action["original_plan"]),
        executed_step_sha256=hash_payload(action["executed_step_payload"]),
        owner_requirements_sha256=hash_payload(action["original_plan"]["requirements"]["move"]),
        controller_source_sha256=SHA,
        tail_inclusion_basis=None,
    )
    sidecar = dict(
        schema_version="native.completion.full-horizon-sidecar.v1",
        source_session_id="session",
        episode_id="episode",
        domain_sha256=DOMAIN,
        span_id="span-1",
        capture_acquisition_id="before",
        terminal_acquisition_id="terminal",
        recipe=registered,
        originals={},
        open_boundary={"operation_id": open_op},
        close_boundary={"operation_id": close_op},
        hold_interval_ids=["hold"],
        wait_interval_ids=[],
    )
    return raw, prereg, sidecar


def pack(source):
    raw, prereg, sidecar = copy.deepcopy(source)
    originals = {"raw.json": encoded(raw), "prereg.json": encoded(prereg)}
    sidecar["originals"] = {
        role: dict(
            path=name,
            bytes=len(originals[name]),
            sha256=hashlib.sha256(originals[name]).hexdigest(),
        )
        for role, name in (("partial_attempts", "raw.json"), ("preregistration", "prereg.json"))
    }
    return encoded(sidecar), originals


def audit(source):
    sidecar, originals = pack(source)
    module = import_module("cloud_edge_robot_arm.research.native_completion_horizon_originals")
    return module.audit_completion_horizon_originals_v1(sidecar_bytes=sidecar, originals=originals)


def test_complete_handwritten_originals_keep_unknown(source):
    result = audit(source)
    assert result.coverage_status == "STRUCTURALLY_COMPLETE", result.structural_reasons
    assert (result.dispatch_step, result.return_step, result.terminal_step) == (120, 121, 123)
    assert (
        result.execution_steps == (121,)
        and result.hold_steps == (122, 123)
        and result.wait_steps == ()
    )
    assert result.horizon.total_steps == 3
    assert result.allocated_action_count == 1 and result.allocated_acquisition_count == 2
    assert result.qualification == "UNKNOWN" and result.producer_status == "UNAVAILABLE"
    assert result.guard_status == "NOT_PROVEN"
    assert "execution_deadline_guards_unproven" in result.qualification_reasons
    assert not {"e", "v", "certified", "q"} & asdict(result).keys()


@pytest.mark.parametrize(
    "change",
    [
        "recipe",
        "open",
        "control",
        "missing",
        "duplicate",
        "reordered",
        "hold_target",
        "hold_command",
        "wait",
        "terminal",
        "failure",
        "next_action",
        "domain",
        "pending",
    ],
)
def test_original_counterexamples_do_not_gain_coverage(source, change):
    raw, prereg, sidecar = copy.deepcopy(source)
    if change == "recipe":
        sidecar["recipe"]["effective_owner_required_ns"] += 1
    elif change == "open":
        sidecar["open_boundary"]["operation_id"] = sidecar["close_boundary"]["operation_id"]
    elif change == "control":
        raw["legacy_physics"][-1]["control_payload"]["control_rad"][0] = 0.1
    elif change == "missing":
        raw["legacy_physics"].pop(-2)
    elif change == "duplicate":
        raw["legacy_physics"].append(copy.deepcopy(raw["legacy_physics"][-1]))
    elif change == "reordered":
        raw["backend_operation_ledger"][-5:-3] = reversed(raw["backend_operation_ledger"][-5:-3])
    elif change == "hold_target":
        raw["legacy_commands"][-1]["command_payload"]["target_positions_rad"][0] = 0.2
    elif change == "hold_command":
        raw["legacy_commands"].pop()
    elif change == "wait":
        sidecar["wait_interval_ids"] = ["hold"]
    elif change == "terminal":
        raw["legacy_frames"].pop()
    elif change == "failure":
        raw["operational_ledger"]["failures"].append(
            {"phase": "capture", "error": "ORIGINAL_FAILURE"}
        )
    elif change == "next_action":
        raw["legacy_actions"].append(copy.deepcopy(raw["legacy_actions"][0]))
        raw["operational_ledger"]["allocated_action_ids"].append("span-2")
    elif change == "domain":
        raw["operational_ledger"]["events"][-1]["domain_sha256"] = SHA
    elif change == "pending":
        raw["pending_operation_ids"].append(999)
    result = audit((raw, prereg, sidecar))
    assert result.coverage_status == "INCOMPLETE" and result.structural_reasons
    assert result.allocated_action_count == len(raw["operational_ledger"]["allocated_action_ids"])
    if change == "failure":
        assert any("ORIGINAL_FAILURE" in value for value in result.original_failures)


def test_bad_file_hash_paths_schemas_keys_and_nonfinite_are_value_errors(source):
    module = import_module("cloud_edge_robot_arm.research.native_completion_horizon_originals")
    sidecar_bytes, originals = pack(source)
    for kind in ("hash", "path", "schema", "duplicate", "nan", "missing", "extra"):
        sidecar = json.loads(sidecar_bytes)
        files = dict(originals)
        if kind == "hash":
            files["raw.json"] += b" "
        elif kind == "path":
            sidecar["originals"]["partial_attempts"]["path"] = "../raw.json"
        elif kind == "schema":
            sidecar["schema_version"] = "simulation.operational-prefix.originals.v1"
        elif kind == "missing":
            files.pop("raw.json")
        elif kind == "extra":
            sidecar["status"] = "PASS"
        payload = encoded(sidecar)
        if kind == "duplicate":
            payload = payload[:-1] + b',"span_id":"span-1"}'
        elif kind == "nan":
            payload = payload.replace(
                b'"registered_dt_s":0.004166666666666667', b'"registered_dt_s":NaN'
            )
        with pytest.raises(ValueError):
            module.audit_completion_horizon_originals_v1(sidecar_bytes=payload, originals=files)


def test_huge_claimed_horizon_preserves_inventory_without_allocation(source):
    raw, prereg, sidecar = copy.deepcopy(source)
    for registration in (prereg, sidecar):
        registration["recipe"]["effective_owner_required_ns"] = 10**30
    result = audit((raw, prereg, sidecar))
    assert result.coverage_status == "INCOMPLETE" and len(result.hold_steps) <= 2


def test_failed_action_is_preserved_and_not_promoted(source):
    raw, prereg, sidecar = copy.deepcopy(source)
    raw["legacy_actions"][0]["returned_result"].update(
        success=False, error_code="ORIGINAL_ACTION_FAILURE"
    )
    raw["legacy_actions"][0]["error"] = "ORIGINAL_ACTION_FAILURE"
    result = audit((raw, prereg, sidecar))
    assert result.coverage_status == "INCOMPLETE"
    assert any("ORIGINAL_ACTION_FAILURE" in row for row in result.original_failures)
