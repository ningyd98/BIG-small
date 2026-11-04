"""Handwritten SOFTWARE_ONLY full-H originals, never a private recorder export.

In particular the synthetic COMMAND D rows are not issued by today's prefix
producer. The independent oracle is dispatch120/return121/terminal123 at 1/240.
"""

import base64
import copy
import hashlib
import io
import json
import struct
from dataclasses import asdict, replace
from datetime import datetime
from importlib import import_module

import pytest
from PIL import Image

from cloud_edge_robot_arm.research.raw_episode_v3 import _camera_hash
from cloud_edge_robot_arm.simulation.models import SensorFrame
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame
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
    clock_pairs = []

    def clock():
        sequence = len(clock_pairs) + 1
        pair = [sequence, sequence * 1000, "2026-01-01T00:00:00+00:00", sequence * 1000 + 1]
        clock_pairs.append(
            dict(
                clock_domain_id="r431-software-monotonic",
                sequence=pair[0],
                mono_before_ns=pair[1],
                utc_at=pair[2],
                mono_after_ns=pair[3],
            )
        )
        return pair

    def interval(name, kind, start, end):
        row = dict(
            interval_id=name,
            record_seq=len(intervals) + 1,
            kind=kind,
            start=clock(),
            end=None if kind in {"SETTLE", "EXECUTOR_ATTEMPT", "HOLD"} else clock(),
            start_step=start,
            end_step=end,
            start_sim_time_s=start / 240,
            end_sim_time_s=end / 240,
            disposition="COMPLETE",
            error=None,
        )
        intervals.append(row)
        return row

    def close_purpose(name):
        next(row for row in intervals if row["interval_id"] == name)["end"] = clock()

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
            )
            operations[str(number)] = dict(
                parameters=parameters or {},
                acquisition_id=acquisition,
                parent=parent,
                action="span-1" if parent == "attempt" else None,
                input_role="ONLINE",
                row=row,
            )
        else:
            clock()
            clock()
        return number

    reset_result = dict(
        physics_state=state(0),
        physics_dt_s=1 / 240,
        initial_controller_targets=dict(joints_rad=[0] * 7, fingers_m=[0.039] * 2),
        actuator_delay_steps=0,
    )
    operation("RESET", 0, 0, reset_result, None)
    interval("settle", "SETTLE", 0, 120)

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
        with Image.open(io.BytesIO(base64.b64decode(obs["rgb_png_base64"]))) as image:
            rgb = image.tobytes()
        sensor_source = SensorFrame(
            frame_id=acquisition,
            sim_time_s=n / 240,
            width=obs["width"],
            height=obs["height"],
            rgb=rgb,
            depth=tuple(
                value[0]
                for value in struct.iter_unpack("<f", base64.b64decode(obs["depth_float32_base64"]))
            ),
            intrinsics=tuple(obs["intrinsics"]),
            camera_to_world=tuple(obs["camera_to_world"]),
            captured_at=datetime.fromisoformat(obs["captured_at"]),
            scene_id=obs["scene_id"],
            episode_id="episode",
            calibration_version=obs["calibration_version"],
            valid_mask=base64.b64decode(obs["valid_mask_base64"]),
        )
        obs = observation_from_sensor_frame(sensor_source, source="mujoco_camera").model_dump(
            mode="json"
        )
        camera = copy.deepcopy(old_frame["camera_state_payload"])
        camera["sim_time_s"] = n / 240
        passes = [_camera_hash(camera)] * 3
        sensor = asdict(sensor_source)
        sensor["captured_at"] = sensor_source.captured_at.isoformat()
        for key in ("rgb", "valid_mask"):
            sensor[key] = {"original_bytes_base64": base64.b64encode(sensor[key]).decode()}
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
    close_purpose("settle")
    open_op = capture("before", 120)
    interval("attempt", "EXECUTOR_ATTEMPT", 120, 121)

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
        op = operation(
            "COMMAND", n, n, {"physics_state": state(n), "command_records": [payload]}, parent
        )
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
    close_purpose("attempt")
    interval("hold", "HOLD", 121, 123)
    command("hold_current_joints", 121, "hold", 2)
    physical(122, "hold")
    physical(123, "hold")
    close_purpose("hold")
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
        legacy_clock_pairs=clock_pairs,
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
    raw = source[0]
    assert [row["sequence"] for row in raw["legacy_clock_pairs"]] == list(
        range(1, len(raw["legacy_clock_pairs"]) + 1)
    )
    for event in raw["operational_ledger"]["events"]:
        if event["kind"] == "COMMAND":
            assert event["end"]["result"]["physics_state"] == state(event["end"]["physics_step"])
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


def test_malformed_result_does_not_hide_later_original_failure(source, tmp_path):
    raw, prereg, sidecar = copy.deepcopy(source)
    first = raw["legacy_actions"][0]
    later = copy.deepcopy(first)
    first.update(returned_result=[], error=None)
    marker = "R431_LATER_ACTION_FAILURE"
    later.update(
        span_id="span-2",
        record_seq=max(row["record_seq"] for row in raw["legacy_actions"]) + 1,
        disposition="RETURNED",
        error=marker,
    )
    later["returned_result"].update(success=False, error_code=marker)
    raw["legacy_actions"].append(later)
    raw["operational_ledger"]["allocated_action_ids"].append("span-2")
    inputs = raw, prereg, sidecar
    before = encoded(inputs)
    sidecar_bytes, originals = pack(inputs)
    for name, payload in originals.items():
        (tmp_path / name).write_bytes(payload)
    (tmp_path / "sidecar.json").write_bytes(sidecar_bytes)
    (tmp_path / "input-sha256.txt").write_text(hashlib.sha256(before).hexdigest() + "\n")
    result = audit(inputs)
    assert encoded(inputs) == before
    assert result.coverage_status == "INCOMPLETE"
    assert result.allocated_action_count == 2
    assert (
        result.evidence_scope,
        result.qualification,
        result.native_authority,
        result.producer_status,
        result.guard_status,
    ) == ("SOFTWARE_ONLY", "UNKNOWN", "UNAVAILABLE", "UNAVAILABLE", "NOT_PROVEN")
    failures = [json.loads(value) for value in result.original_failures]
    originals_retained = [value.get("original", value) for value in failures]
    assert first in originals_retained
    assert later in originals_retained, "later original action failure was omitted"


def rebuild_clock_tee(raw):
    """Reindex a deliberately retimed software source without breaking its tee."""
    pairs = {
        row["sequence"]: [
            row["sequence"],
            row["mono_before_ns"],
            row["utc_at"],
            row["mono_after_ns"],
        ]
        for row in raw["legacy_clock_pairs"]
    }
    for row in raw["legacy_intervals"]:
        for key in ("start", "end"):
            pairs[row[key][0]] = list(row[key])
    ordered = sorted(pairs.values(), key=lambda pair: pair[1])
    new_sequences = {pair[0]: index for index, pair in enumerate(ordered, 1)}
    for row in raw["legacy_intervals"]:
        for key in ("start", "end"):
            row[key][0] = new_sequences[row[key][0]]
    raw["legacy_clock_pairs"] = [
        dict(
            clock_domain_id="r431-software-monotonic",
            sequence=index,
            mono_before_ns=pair[1],
            utc_at=pair[2],
            mono_after_ns=pair[3],
        )
        for index, pair in enumerate(ordered, 1)
    ]


def insert_unrepresented_capture(raw, sidecar):
    events = raw["operational_ledger"]["events"]
    index = next(
        i + 1
        for i, event in enumerate(events)
        if event["kind"] == "PHYSICS" and event["end"]["physics_step"] == 122
    )
    before = next(event for event in events if event["acquisition_id"] == "before")
    extra = copy.deepcopy(before)
    extra.update(operation_id=10000, acquisition_id="unrepresented")
    for phase in ("begin", "end"):
        extra[phase].update(operation_id=10000, physics_step=122, sim_time_s=122 / 240)
        extra[phase]["parameters"]["physics_state"] = state(122)
        extra[phase]["parameters"]["camera_state"]["sim_time_s"] = 122 / 240
    extra["end"]["result"]["sensor_frame"].update(frame_id="unrepresented", sim_time_s=122 / 240)
    extra["end"]["result"]["pass_state_hashes"] = [
        _camera_hash(extra["begin"]["parameters"]["camera_state"])
    ] * 3
    operation = copy.deepcopy(raw["legacy_operations"][str(before["operation_id"])])
    row = operation["row"]
    previous = raw["legacy_operations"][str(events[index - 1]["operation_id"])]["row"]
    lower = previous["end"][3] + 100
    pair_seq = len(raw["legacy_clock_pairs"])
    row.update(
        interval_id="operation-10000",
        record_seq=max(r["record_seq"] for r in raw["legacy_intervals"]) + 1,
        start_step=122,
        end_step=122,
        start_sim_time_s=122 / 240,
        end_sim_time_s=122 / 240,
        start=[pair_seq + 1, lower, row["start"][2], lower + 1],
        end=[pair_seq + 2, lower + 100, row["end"][2], lower + 101],
    )
    operation.update(
        parameters=extra["begin"]["parameters"],
        acquisition_id="unrepresented",
        parent="hold",
        action=None,
    )
    raw["legacy_operations"]["10000"] = operation
    raw["legacy_intervals"].append(row)
    events.insert(index, extra)
    mapping = {event["operation_id"]: i for i, event in enumerate(events, 1)}

    def renamed(value):
        return (
            f"operation-{mapping[int(value.split('-')[1])]}"
            if value.startswith("operation-")
            else value
        )

    for event in events:
        n = mapping[event["operation_id"]]
        event.update(
            operation_id=n,
            attempt_seq=n,
            begin_seq=3 * n - 2,
            mark_seq=3 * n - 1,
            end_seq=3 * n,
            token_identity=f"token-{n}",
            begin_ns=n * 100,
            bracket=dict(
                event_identity=f"token-{n}",
                lower_ns=n * 100,
                upper_ns=n * 100 + 20,
                domain_sha256=DOMAIN,
            ),
        )
        event["begin"]["operation_id"] = event["end"]["operation_id"] = n
    raw["legacy_operations"] = {
        str(mapping[int(key)]): value for key, value in raw["legacy_operations"].items()
    }
    for interval in raw["legacy_intervals"]:
        interval["interval_id"] = renamed(interval["interval_id"])
    for record in raw["legacy_physics"]:
        for key in ("physics_interval_id", "control_interval_id"):
            record[key] = renamed(record[key])
    for record in raw["legacy_commands"] + raw["legacy_frames"]:
        record["interval_id"] = renamed(record["interval_id"])
    for key in ("open_boundary", "close_boundary"):
        sidecar[key]["operation_id"] = mapping[sidecar[key]["operation_id"]]
    keys = ("operation_id", "kind", "phase", "episode_id", "physics_step", "error_type", "error")
    raw["backend_operation_ledger"] = [
        {key: event[phase][key] for key in keys} for event in events for phase in ("begin", "end")
    ]
    rebuild_clock_tee(raw)


@pytest.mark.parametrize(
    "change,reason",
    [
        ("extra_accepted_command", "command_result_inventory_mismatch"),
        ("extra_rejected_command", "command_result_inventory_mismatch"),
        ("unrepresented_capture", "capture_event_inventory_mismatch"),
        ("hold_clock_after_terminal", "purpose_clock_containment_mismatch"),
        ("attempt_clock_before_preopen", "preopen_attempt_clock_order_mismatch"),
        ("truncated_action_result", "invalid_action_result"),
        ("boolean_action_attempt", "invalid_action_attempt"),
    ],
    ids=[
        "extra_accepted_command",
        "extra_rejected_command",
        "unrepresented_capture",
        "hold_clock_after_terminal",
        "attempt_clock_before_preopen",
        "truncated_action_result",
        "boolean_action_attempt",
    ],
)
def test_review_counterexamples_require_incomplete(source, change, reason):
    raw, prereg, sidecar = copy.deepcopy(source)
    if change in {"extra_accepted_command", "extra_rejected_command"}:
        event = [
            event for event in raw["operational_ledger"]["events"] if event["kind"] == "COMMAND"
        ][-1]
        payload = copy.deepcopy(event["end"]["result"]["command_records"][0])
        payload.update(type="joint_target", command_seq=3)
        if change == "extra_rejected_command":
            payload.update(accepted=False, reason="R431_REJECTED_ORIGINAL")
            payload.pop("applied_target_positions_rad")
        event["end"]["result"]["command_records"].append(payload)
    elif change == "unrepresented_capture":
        insert_unrepresented_capture(raw, sidecar)
    elif change == "hold_clock_after_terminal":
        row = next(row for row in raw["legacy_intervals"] if row["interval_id"] == "hold")
        lower = raw["legacy_clock_pairs"][-1]["mono_after_ns"] + 1000
        row["start"][1], row["start"][3] = lower, lower + 1
        row["end"][1], row["end"][3] = lower + 1000, lower + 1001
        rebuild_clock_tee(raw)
    elif change == "attempt_clock_before_preopen":
        row = next(row for row in raw["legacy_intervals"] if row["interval_id"] == "attempt")
        before = raw["legacy_operations"][str(sidecar["open_boundary"]["operation_id"])]["row"]
        lower = before["start"][1] - 100
        row["start"][1], row["start"][3] = lower, lower + 1
        rebuild_clock_tee(raw)
    elif change == "truncated_action_result":
        result = raw["legacy_actions"][0]["returned_result"]
        raw["legacy_actions"][0]["returned_result"] = {
            key: result[key] for key in ("success", "error_code", "action_type", "details")
        }
    else:
        raw["legacy_actions"][0]["attempt"] = True
    result = audit((raw, prereg, sidecar))
    assert result.coverage_status == "INCOMPLETE", result.structural_reasons
    assert reason in result.structural_reasons
    assert (result.allocated_action_count, result.allocated_acquisition_count) == (1, 2)
    assert (result.qualification, result.producer_status, result.guard_status) == (
        "UNKNOWN",
        "UNAVAILABLE",
        "NOT_PROVEN",
    )
    if change == "extra_rejected_command":
        assert any(
            "R431_REJECTED_ORIGINAL" in row and "operation_id" in row
            for row in result.original_failures
        )
    elif change == "unrepresented_capture":
        assert any(
            "unrepresented" in row and "operation_id" in row for row in result.original_failures
        )
