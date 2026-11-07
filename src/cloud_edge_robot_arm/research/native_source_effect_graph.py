"""Pure source/effect reconstruction; no backend, execution or qualification authority."""

from __future__ import annotations

import math
from typing import Any

from cloud_edge_robot_arm.research.native_calibration_collection import canonical, detached


def _need(value: Any, reason: str) -> None:
    if not value:
        raise ValueError("source effect graph: " + reason)


def _same(left: Any, right: Any, reason: str) -> None:
    _need(canonical(detached(left)) == canonical(detached(right)), reason)


def _vector(value: Any, size: int, name: str) -> list[float]:
    _need(isinstance(value, (list, tuple)) and len(value) == size, name + " dimension")
    _need(all(type(v) in (float, int) and math.isfinite(v) for v in value), name + " finite")
    return [float(v) for v in value]


def _op(interval: str) -> int:
    prefix, number = interval.split("-", 1)
    _need(prefix == "operation" and number.isdecimal(), "operation interval identity")
    return int(number)


def _interval(row: dict[str, Any], kind: str, start: int, end: int) -> None:
    _need(
        row["kind"] == kind
        and row["start_step"] == start
        and row["end_step"] == end
        and row["disposition"] == "COMPLETE"
        and row["error"] is None,
        "interval kind/step/completion",
    )


def validate_native_command_controls(
    raw: dict[str, Any],
    intervals: dict[str, Any],
    states: dict[int, Any],
    *,
    expected_delay_steps: int | None = None,
) -> None:
    """Replay every command and original CONTROL, including final nonphysics STOP control."""
    reset = raw["reset"]
    delay = reset["actuator_delay_steps"]
    _need(type(delay) is int and delay >= 0, "actuator delay")
    if expected_delay_steps is not None:
        _need(delay == expected_delay_steps, "unregistered actuator delay")
    _need(
        reset["physics_dt_s"] == raw["reset_metadata"]["config"]["physics_dt_s"] == 1 / 240,
        "reset time grid",
    )
    episode = states[0]["episode_id"]
    arm = _vector(reset["initial_controller_targets"]["joints_rad"], 7, "initial arm")
    fingers = _vector(reset["initial_controller_targets"]["fingers_m"], 2, "initial fingers")
    _same(arm, _vector(states[0]["joint_positions_rad"], 7, "reset joints"), "initial arm target")
    _same(fingers, [0.039, 0.039], "initial finger target")
    controls = raw["control_sources"]
    commands = raw["commands"]
    n = raw["total_physics_steps"]
    _need(type(n) is int and n >= 1 and set(states) == set(range(n + 1)), "physical denominator")
    _need(len(controls) == n + 1 <= 12961, "one original CONTROL per physics plus STOP")
    indexed = {r["interval_id"]: r for r in controls}
    _need(len(indexed) == len(controls), "duplicate original CONTROL")
    used = []
    for row in raw["physics"]:
        number = row["physics_step"]
        control = indexed[row["control_interval_id"]]
        _same(row["control_payload"], control["control_state"], "physics CONTROL payload")
        _interval(intervals[control["interval_id"]], "CONTROL_APPLY", number - 1, number - 1)
        _need(control["physics_step"] == number - 1, "physics CONTROL current step")
        _need(
            _op(row["control_interval_id"]) < _op(row["physics_interval_id"]),
            "CONTROL must precede PHYSICS",
        )
        used.append(row["control_interval_id"])
    _need(len(set(used)) == n, "reused CONTROL")
    extra = set(indexed) - set(used)
    _need(len(extra) == 1, "unique terminal CONTROL required")
    terminal = indexed[next(iter(extra))]
    _need(terminal["physics_step"] == n, "terminal CONTROL current step")
    _interval(intervals[terminal["interval_id"]], "CONTROL_APPLY", n, n)
    _need(terminal["control_state"]["physics_step"] == n + 1, "terminal CONTROL target step")
    _need(
        [c["command_seq"] for c in commands] == list(range(1, len(commands) + 1)),
        "command sequence",
    )
    timeline = [(_op(c["interval_id"]), "COMMAND", c) for c in commands]
    timeline += [(c["operation_id"], "CONTROL", c) for c in controls]
    _need(len({row[0] for row in timeline}) == len(timeline), "effect operation reused")
    pending: list[tuple[int, list[float]]] = []
    actions = {row["span_id"]: row for row in raw["actions"]}
    stopped = False
    for operation, kind, row in sorted(timeline):
        if kind == "COMMAND":
            value = row["command_payload"]
            step = value["physics_step"]
            _need(step in states and value["episode_id"] == episode, "command identity")
            _need(value["command_seq"] == row["command_seq"], "command payload sequence")
            _need(
                math.isclose(value["sim_time_s"], states[step]["sim_time_s"], abs_tol=1e-9),
                "command current time",
            )
            _interval(intervals[row["interval_id"]], "COMMAND", step, step)
            parent = intervals[row["parent_interval_id"]]
            _need(parent["start_step"] <= step <= parent["end_step"], "command parent range")
            child = intervals[row["interval_id"]]
            _need(
                parent["start"][3] <= child["start"][1] and child["end"][3] <= parent["end"][1],
                "command parent containment",
            )
            action = row["owner_action_span_id"]
            if action is not None:
                _need(
                    action in actions
                    and actions[action]["interval_id"] == row["parent_interval_id"]
                    and parent["kind"] == "EXECUTOR_ATTEMPT"
                    and actions[action]["command_seq_start"]
                    <= row["command_seq"]
                    < actions[action]["command_seq_end"],
                    "command action parent",
                )
            else:
                _need(
                    parent["kind"] in {"SETTLE", "WAIT", "VERIFY_ADVANCE", "HOLD", "TERMINATION"},
                    "command purpose parent",
                )
            command = value["type"]
            _need(
                command in {"joint_target", "gripper", "hold_current_joints", "emergency_stop"},
                "unknown command",
            )
            _need(
                type(value["accepted"]) is bool and type(value["after_emergency_stop"]) is bool,
                "command boolean flags",
            )
            _need(
                value["after_emergency_stop"] == (stopped and command != "emergency_stop"),
                "command stop flag",
            )
            accepted = value["accepted"]
            _need(
                accepted == (not stopped or command in {"hold_current_joints", "emergency_stop"}),
                "command acceptance/stop latch",
            )
            effect = step + 1 + (delay if command == "joint_target" else 0)
            _need(
                row["effective_from_step"] == (effect if accepted else None),
                "command effective step",
            )
            if not accepted:
                _need(value["reason"] == "emergency_stop", "rejected command reason")
                continue
            if command == "joint_target":
                _need(parent["kind"] != "HOLD", "new joint target inside HOLD")
                requested = _vector(value["target_positions_rad"], 7, "joint request")
                clipped = [max(-2.8, min(2.8, v)) for v in requested]
                _same(
                    _vector(value["applied_target_positions_rad"], 7, "joint applied"),
                    clipped,
                    "joint clipping",
                )
                _need(
                    value["reason"]
                    == (f"queued_until_physics_step={step + delay}" if delay else ""),
                    "joint queue availability",
                )
                if delay:
                    pending.append((step + delay, clipped))
                else:
                    arm = clipped
            elif command == "hold_current_joints":
                arm = _vector(states[step]["joint_positions_rad"], 7, "hold measured joints")
                _same(value["target_positions_rad"], arm, "hold target must be measured")
                _same(value["applied_target_positions_rad"], arm, "hold applied target")
                _need(value["reason"] == "motion_terminated", "hold reason")
                pending.clear()
            elif command == "gripper":
                _need(
                    parent["kind"] != "HOLD" and type(value["target_open"]) is bool,
                    "gripper target/parent",
                )
                _need(value["reason"] == "", "gripper reason")
                fingers = [0.039, 0.039] if value["target_open"] else [0.0, 0.0]
            else:
                _need(value["reason"] == "", "STOP reason")
                stopped = True
        else:
            step = row["physics_step"]
            _need(step in states and row["episode_id"] == episode, "CONTROL identity")
            _need(operation == _op(row["interval_id"]), "CONTROL operation identity")
            _interval(intervals[row["interval_id"]], "CONTROL_APPLY", step, step)
            while pending and pending[0][0] <= step:
                _, arm = pending.pop(0)
            value = row["control_state"]
            _need(
                value["episode_id"] == episode and value["physics_step"] == step + 1,
                "CONTROL target step identity",
            )
            _need(
                math.isclose(value["sim_time_s"], states[step]["sim_time_s"], abs_tol=1e-9),
                "CONTROL current time",
            )
            _same(
                _vector(value["applied_joint_targets_rad"], 7, "CONTROL arm"),
                arm,
                "applied arm target replay",
            )
            _same(
                _vector(value["finger_control_targets_m"], 2, "CONTROL fingers"),
                fingers,
                "applied gripper target replay",
            )
            current = _vector(value["pre_joint_positions_rad"], 7, "CONTROL pre joints")
            _same(
                current,
                _vector(states[step]["joint_positions_rad"], 7, "state joints"),
                "CONTROL previous physical joints",
            )
            biases = _vector(value["pre_gravity_bias_nm"], 7, "bias")
            gains = _vector(value["actuator_gains"], 7, "gain")
            outputs = _vector(value["control_rad"], 7, "control output")
            ranges = value["actuator_ctrl_ranges"]
            _need(len(ranges) == 7, "control range dimension")
            for i in range(7):
                lo, hi = _vector(ranges[i], 2, "actuator range")
                _need(lo < hi and gains[i] > 0, "actuator gain/range")
                expected = min(
                    hi,
                    max(
                        lo,
                        current[i]
                        + min(0.1, max(-0.1, arm[i] - current[i]))
                        + biases[i] / gains[i],
                    ),
                )
                _need(
                    math.isclose(outputs[i], expected, rel_tol=0, abs_tol=1e-9), "control equation"
                )
    _need(stopped, "missing STOP command")


def validate_native_source_effect_graph(
    raw: dict[str, Any],
    intervals: dict[str, Any],
    states: dict[int, Any],
    frame_metadata: dict[str, Any],
    active_checks: list[Any],
    *,
    domain: Any,
    deadline: int,
    lease_id: str,
) -> dict[str, Any]:
    """Match required effects, exact backend guard grammar and the real safe termination."""
    validate_native_command_controls(raw, intervals, states)
    rows = raw["operational_events"]
    events = {r["operation_id"]: r for r in rows}
    _need([r["operation_id"] for r in rows] == list(range(1, len(rows) + 1)), "operation IDs")
    _need([r["sequence"] for r in rows] == list(range(1, len(rows) + 1)), "operation sequence")
    n, episode = raw["total_physics_steps"], states[0]["episode_id"]
    _need(raw["reset_count"] == 1, "one RESET required")
    expected: dict[int, tuple[str, int, int]] = {1: ("RESET", 0, 0)}

    def add(number: int, kind: str, start: int, end: int) -> None:
        _need(number not in expected, "primary effect operation reused")
        expected[number] = (kind, start, end)

    for row in raw["control_sources"]:
        add(row["operation_id"], "CONTROL", row["physics_step"], row["physics_step"])
    for row in raw["physics"]:
        add(
            _op(row["physics_interval_id"]), "PHYSICS", row["physics_step"] - 1, row["physics_step"]
        )
    commands = {_op(c["interval_id"]): c for c in raw["commands"]}
    _need(len(commands) == len(raw["commands"]), "command operation duplicate")
    for number, row in commands.items():
        step = row["command_payload"]["physics_step"]
        add(number, "COMMAND", step, step)
    allocated = raw["allocated_frames"]
    _need(
        len(set(allocated)) == len(allocated)
        and set(allocated) == set(raw["frame_sources"]) == set(frame_metadata),
        "allocated frame coverage",
    )
    roles = raw["capture_source_roles"]
    _need(len(roles) == len(allocated), "capture role coverage")
    for aid, metadata in frame_metadata.items():
        frame, source = metadata["frame"], metadata["capture_source"]
        number, step = source["operation_id"], source["physics_step"]
        _need(
            frame["acquisition_id"] == aid and _op(frame["interval_id"]) == number,
            "capture primary identity",
        )
        _need(frame["source_acquisition_id"] is None, "transformed capture")
        _same(source, roles[str(number)], "capture role original")
        _need(
            source["role"]
            in {
                "IMPLICIT_SENSOR_CACHE_UPDATE",
                "REGISTERED_PER_PHYSICS_STEP",
                "REGISTERED_ACTION_BOUNDARY",
            },
            "capture role",
        )
        add(number, "CAPTURE", step, step)
        _need(events[number]["acquisition_id"] == aid, "capture allocation operation")
    _need(set(expected) == set(events), "required primary operation coverage")
    kinds = {
        "CONTROL": "CONTROL_APPLY",
        "PHYSICS": "PHYSICS_STEP",
        "COMMAND": "COMMAND",
        "CAPTURE": "ACQUISITION",
    }
    operation_intervals = {key for key, row in intervals.items() if row["kind"] in kinds.values()}
    _need(
        operation_intervals == {f"operation-{i}" for i in expected if i != 1},
        "operation interval coverage",
    )
    for number, (kind, start, end) in expected.items():
        event = events[number]
        _need(
            (event["kind"], event["begin_step"], event["end_step"]) == (kind, start, end),
            "operation effect kind/step",
        )
        _need(event["error_type"] is None and event["error"] is None, "failed operation")
        _need(
            event["episode_id"] == episode or number == 1 and event["episode_id"] is None,
            "operation episode",
        )
        if number != 1:
            _interval(intervals[f"operation-{number}"], kinds[kind], start, end)
        bracket = event["bracket"]
        _same(bracket["domain"], domain, "operation clock domain")
        _same(bracket["event_identity"], event["token"], "operation event token")
        _need(
            type(bracket["lower_ns"]) is int
            and type(bracket["upper_ns"]) is int
            and 0 <= bracket["lower_ns"] <= bracket["upper_ns"] < deadline,
            "operation deadline",
        )

    tail = raw["commands"][-2:]
    _need(
        len(tail) == 2
        and [c["command_payload"]["type"] for c in tail]
        == ["hold_current_joints", "emergency_stop"],
        "real hold then STOP required",
    )
    hold, stop = (_op(c["interval_id"]) for c in tail)
    terminal_control = max(events)
    _need(
        (hold, stop, terminal_control) == (len(events) - 2, len(events) - 1, len(events))
        and events[terminal_control]["kind"] == "CONTROL",
        "final STOP internal CONTROL",
    )
    _need(tail[0]["parent_interval_id"] == tail[1]["parent_interval_id"], "termination parent")
    for row in tail:
        _interval(intervals[row["parent_interval_id"]], "TERMINATION", n, n)
        _need(
            row["owner_action_span_id"] is None
            and row["command_payload"]["accepted"] is True
            and row["command_payload"]["physics_step"] == n,
            "termination command source",
        )
    extra = set(c["interval_id"] for c in raw["control_sources"]) - {
        r["control_interval_id"] for r in raw["physics"]
    }
    _need(extra == {f"operation-{terminal_control}"}, "unmatched STOP CONTROL")
    ledger = raw["backend_operation_ledger"]
    stack: list[int] = []
    seen: set[tuple[int, str]] = set()
    children: dict[int, list[int]] = {}
    begun: list[int] = []
    last_boundary = 0
    for row in ledger:
        number, phase = row["operation_id"], row["phase"]
        _need(
            number in events and phase in {"BEGIN", "END"} and (number, phase) not in seen,
            "ledger operation duplicate/orphan",
        )
        seen.add((number, phase))
        event = events[number]
        boundary = event["bracket"]["lower_ns" if phase == "BEGIN" else "upper_ns"]
        _need(boundary >= last_boundary, "ledger original clock order")
        last_boundary = boundary
        _need(
            row["kind"] == event["kind"] and row["error_type"] is None and row["error"] is None,
            "ledger effect/error",
        )
        _need(
            row["physics_step"] == event["begin_step" if phase == "BEGIN" else "end_step"],
            "ledger physical step",
        )
        _need(
            row["episode_id"] == (event["episode_id"] if phase == "BEGIN" else episode),
            "ledger episode",
        )
        if phase == "BEGIN":
            begun.append(number)
            if stack:
                parent = stack[-1]
                children.setdefault(parent, []).append(number)
                _need(
                    events[parent]["bracket"]["lower_ns"] <= event["bracket"]["lower_ns"]
                    and event["bracket"]["upper_ns"] <= events[parent]["bracket"]["upper_ns"],
                    "nested operation clock order",
                )
            stack.append(number)
        else:
            _need(bool(stack) and stack.pop() == number, "operation nesting/closure")
    _need(
        not stack and seen == {(number, phase) for number in events for phase in ("BEGIN", "END")},
        "ledger required coverage",
    )
    _need(begun == list(events), "ledger BEGIN order")
    _same(
        children, {1: [2], stop: [terminal_control]}, "only RESET capture and STOP control may nest"
    )
    _need(
        roles["2"]["role"] == "IMPLICIT_SENSOR_CACHE_UPDATE" and roles["2"]["physics_step"] == 0,
        "RESET implicit acquisition",
    )

    # Emit the exact source grammar, preserving duplicate PHYSICS checkpoints.
    checkpoints: list[tuple[dict[str, Any], int, int]] = []
    prefix_end: dict[int, int] = {0: 0}
    for number, event in events.items():
        prefix_end[number] = max(prefix_end[number - 1], event["bracket"]["upper_ns"])

    def emit(kind: str, phase: str, step: int, number: int, lo: int, hi: int) -> None:
        checkpoints.append(
            (
                dict(
                    kind=kind,
                    phase=phase,
                    episode_id=episode,
                    physics_step=step,
                    operation_id=number,
                ),
                lo,
                hi,
            )
        )

    def inside(kind: str, phase: str, step: int, number: int) -> None:
        bracket = events[number]["bracket"]
        emit(kind, phase, step, number, bracket["lower_ns"], bracket["upper_ns"])

    def after(kind: str, phase: str, step: int, number: int) -> None:
        hi = events[number + 1]["bracket"]["lower_ns"] if number + 1 in events else deadline
        emit(kind, phase, step, number, events[number]["bracket"]["upper_ns"], hi)

    in_step = False
    sampled: list[int] = []
    for number, event in events.items():
        kind, start, end = event["kind"], event["begin_step"], event["end_step"]
        if number in {1, 2, hold, stop, terminal_control}:
            continue
        if kind == "COMMAND":
            _need(not in_step, "command inside backend step call")
            # Safe explicit hold has no ordinary guard, as in the original backend.
            if commands[number]["command_payload"]["type"] == "hold_current_joints":
                continue
            _need(commands[number]["command_payload"]["type"] != "emergency_stop", "early STOP")
            inside(kind, "BEFORE", start, number)
            inside(kind, "AFTER", end, number)
            after("RETURN", "AFTER", end, number)
        elif kind == "CONTROL":
            if not in_step:
                emit(
                    "RETURN",
                    "BEFORE",
                    start,
                    number - 1,
                    prefix_end[number - 1],
                    event["bracket"]["lower_ns"],
                )
                in_step = True
            _need(events[number + 1]["kind"] == "PHYSICS", "CONTROL lacks following PHYSICS")
            inside(kind, "BEFORE", start, number)
            inside(kind, "AFTER", end, number)
            after("RETURN", "AFTER", end, number)
        elif kind == "PHYSICS":
            _need(in_step and events[number - 1]["kind"] == "CONTROL", "PHYSICS grouping")
            for _ in range(2):
                inside(kind, "BEFORE", start, number)
            for _ in range(2):
                inside(kind, "AFTER", end, number)
            after("RETURN", "AFTER", end, number)
            _need(
                roles[str(number + 1)]["role"] == "REGISTERED_PER_PHYSICS_STEP",
                "PHYSICS sampler missing",
            )
        else:
            role = roles[str(number)]
            if role["role"] == "REGISTERED_PER_PHYSICS_STEP":
                _need(
                    in_step
                    and events[number - 1]["kind"] == "PHYSICS"
                    and role["sample_slot"] == end,
                    "per-step capture slot",
                )
                after("CAPTURE", "BEFORE", end, number - 1)
                after("CAPTURE", "AFTER", end, number)
                sampled.append(end)
            elif role["role"] == "IMPLICIT_SENSOR_CACHE_UPDATE":
                _need(in_step, "implicit step tail without step")
                after("RETURN", "AFTER", end, number)
                in_step = False
            else:
                _need(not in_step, "boundary capture inside step")
    _need(not in_step and sampled == list(range(1, n + 1)), "complete sampler/step schedule")
    guards = raw["guard_events"]
    _need(guards and guards[-1] == {"kind": "CLOSED", "physics_step": n}, "normal guard close")
    _need(
        len(guards) - 1 == len(active_checks) == len(checkpoints) > 0, "guard/active-check coverage"
    )
    previous = 0
    for index, (guard, check, expected_check) in enumerate(
        zip(guards[:-1], active_checks, checkpoints, strict=True), 1
    ):
        checkpoint, lo, hi = expected_check
        _same(guard, dict(checkpoint, sequence=index, outcome="ALLOWED"), "guard exact schedule")
        _same(check["checkpoint"], checkpoint, "active checkpoint")
        _need(
            check["step"] == checkpoint["physics_step"] and check["lease_id"] == lease_id,
            "active owner/step",
        )
        current = check["current"]
        _same(current["domain"], domain, "active clock domain")
        lower, upper = current["lower_ns"], current["upper_ns"]
        _need(
            type(lower) is int
            and type(upper) is int
            and max(previous, lo) <= lower <= upper <= hi
            and upper < deadline,
            "guard operational timing/order",
        )
        previous = upper
    return dict(
        evidence_scope="READ_ONLY_SOURCE_EFFECT_GRAPH",
        physics_steps=n,
        control_count=len(raw["control_sources"]),
        legacy_utc_mapping="UNAVAILABLE",
        native_qualification="UNKNOWN",
        execution_admitted=False,
    )
