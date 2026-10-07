"""Streaming saved-original verification; truth never enters the strict detector."""

from __future__ import annotations

import argparse
import base64
import gzip
import importlib.util
import json
import resource
import time
from collections import Counter
from dataclasses import asdict
from itertools import zip_longest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("round57_reader_prepare", HERE / "prepare_full.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
ROOT, DEV, OLD = P.ROOT, P.DEV, P.OLD


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            P.require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def constant(value):
        raise ValueError("nonfinite JSON number: " + value)

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def iter_journal(path):
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else Path.open
    with opener(path, "rb") as stream:
        while True:
            line = stream.readline(P.RESOURCE["max_journal_record_bytes"] + 1)
            if not line:
                break
            P.require(
                len(line) <= P.RESOURCE["max_journal_record_bytes"], "journal record resource limit"
            )
            P.require(line.endswith(b"\n"), "journal truncated line")
            yield strict_json(line)


def identity(row):
    result = {k: row[k] for k in ("episode_id", "physics_step", "sim_time_s")}
    P.require(
        type(result["physics_step"]) is int and P.finite(result["sim_time_s"]),
        "identity type/SimulationS invalid",
    )
    return result


def helpers():
    plan = P.plan_data()["input_pins"]
    v3 = DEV / "t7b-continuous-visibility-v3/verify_offline.py"
    sparse = P.SPARSE / "fix-round-1/offline/verify_sparse.py"
    return (
        P.load_pinned(v3, plan[str(v3.relative_to(ROOT))]["sha256"], "round57_v3_pure_verify"),
        P.load_pinned(
            sparse, plan[str(sparse.relative_to(ROOT))]["sha256"], "round57_sparse_pure_verify"
        ),
    )


def validate_frame_camera(
    camera, contract, expected_identity, outer_brackets, *, helpers_pair=None
):
    helper, sparse = helpers_pair or helpers()
    identity(camera["full_capture_state"])
    P.require(
        P.finite(camera["before_state"]["sim_time_s"])
        and P.finite(camera["after_state"]["sim_time_s"]),
        "guard SimulationS type",
    )
    helper.verify_camera_guard(camera, contract)
    P.require(
        camera["state_unchanged"] is True and camera["before_state"]["sensor_noise_std_m"] == 0.0,
        "capture unchanged/noise contract",
    )
    sparse.validate_full_state(
        camera["full_capture_state"],
        camera["before_state"],
        camera["before_guard"]["arrays"]["fields"],
        expected_identity,
    )
    lo, begin, end, hi = outer_brackets
    clocks = [
        lo,
        begin,
        camera["capture_monotonic_begin_ns"],
        camera["capture_monotonic_end_ns"],
        end,
        hi,
    ]
    P.require(
        all(type(v) is int for v in clocks) and clocks == sorted(clocks),
        "capture complete nested clocks",
    )
    P.require(
        camera["before_state"]["physical_step"] == expected_identity["physics_step"]
        and camera["before_state"]["sim_time_s"] == expected_identity["sim_time_s"],
        "frame guard identity bridge",
    )


def index_contract(attempt, expected_steps):
    ends, begins, callbacks, errors = {}, {}, {}, []
    final_guard = finish = None
    previous_step, previous_time = -1, None
    max_gap, gap_violations = None, []
    try:
        for row in iter_journal(Path(attempt) / "whole-step/index.jsonl"):
            event = row.get("event")
            if event in {"PHYSICAL_CALLBACK", "BEGIN", "END"}:
                step = row.get("physics_step")
                try:
                    ident = identity(row)
                    if event == "PHYSICAL_CALLBACK":
                        P.require(
                            step == previous_step + 1
                            and (
                                row["sim_time_s"] == 0
                                if step == 0
                                else row["sim_time_s"] > previous_time
                            ),
                            "callback exact sequence/SimulationS",
                        )
                        if previous_time is not None:
                            gap = row["sim_time_s"] - previous_time
                            max_gap = max(max_gap or 0, gap)
                            if not 0 < gap <= 0.005:
                                gap_violations.append(step)
                        callbacks[step] = ident
                        previous_step, previous_time = step, row["sim_time_s"]
                    elif event == "BEGIN":
                        P.require(
                            step not in begins
                            and step in callbacks
                            and P.same(ident, callbacks[step]),
                            "index BEGIN allocation join",
                        )
                        P.require(
                            type(row["capture_monotonic_begin_ns"]) is int, "index begin clock"
                        )
                        begins[step] = row["capture_monotonic_begin_ns"]
                    else:
                        P.require(
                            step not in ends and step in begins and P.same(ident, callbacks[step]),
                            "index END publication join",
                        )
                        P.require(
                            type(row["capture_monotonic_end_ns"]) is int
                            and begins[step] <= row["capture_monotonic_end_ns"],
                            "index capture clock",
                        )
                        ends[step] = row
                except Exception as error:
                    errors.append(dict(kind="index", step=repr(step), reason=str(error)))
            elif event == "FINAL_GUARD":
                if final_guard is not None:
                    errors.append(dict(kind="duplicate_final_guard"))
                final_guard = row
            elif event == "FINISH":
                if finish is not None:
                    errors.append(dict(kind="duplicate_finish"))
                finish = row.get("summary")
            else:
                errors.append(dict(kind="retained_index_failure_or_unknown", event=event))
    except Exception as error:
        errors.append(dict(kind="index_read_failure", reason=repr(error)))
    for kind, mapping in (("callbacks", callbacks), ("allocated", begins), ("saved", ends)):
        if sorted(mapping) != expected_steps:
            errors.append(
                dict(
                    kind="range_" + kind,
                    missing=sorted(set(expected_steps) - set(mapping)),
                    extra=sorted(set(mapping) - set(expected_steps)),
                )
            )
    summary_path = Path(attempt) / "whole-step/summary.json"
    series = strict_json(summary_path.read_bytes()) if summary_path.exists() else {}
    if finish is None or not P.same(finish, series) or series.get("status") != "COMPLETE":
        errors.append(dict(kind="index_finish_summary_incomplete"))
    for field in ("publication_errors", "failed_steps", "missing_steps", "extra_steps", "reasons"):
        if series.get(field):
            errors.append(dict(kind="index_summary_failure", field=field))
    if final_guard is None:
        errors.append(dict(kind="missing_final_guard"))
    return dict(
        ends=ends,
        begins=begins,
        callbacks=callbacks,
        final_guard=final_guard,
        series=series,
        max_gap_s=max_gap,
        gap_violations=gap_violations,
        errors=errors,
    )


def validate_full_trace(attempt, header, contract):
    """Stream guard-heavy journal; retain compact joins, never a full journal list."""
    from cloud_edge_robot_arm.simulation.mujoco.backend import PhysicsStepObservation
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
        CompletionCriteria,
        sample_physical_observation,
    )

    helper, sparse = helpers()
    attempt = Path(attempt)
    index = index_contract(attempt, header["expected_callback_steps"])
    errors = index["errors"]
    summary = strict_json((attempt / "summary.json").read_bytes())
    terminal = strict_json((attempt / "terminal.json").read_bytes())
    teacher = strict_json((attempt / "teacher-evidence.json").read_bytes())
    episode = terminal["episode_id"]
    pending, actions, teacher_actions = {}, {}, {}
    active_action = None
    control = actuator = physics = acq_begin = last_camera = None
    sequence = ledger_cursor = command_cursor = op_begin_count = frame_count = acquisition_next = 0
    previous_clock = -1
    fixed_camera_context = None
    trace_started = time.monotonic()
    physical_steps, actuator_steps, scorer_steps = [], [], []
    final_guard_seen, last_final_guard = 0, None
    criteria = CompletionCriteria("object", "target_region")
    ledger_keys = (
        "operation_id",
        "kind",
        "phase",
        "episode_id",
        "physics_step",
        "error_type",
        "error",
    )
    allowed = {
        "SETUP_BEGIN",
        "SETUP_END",
        "BOOTSTRAP_SAVED",
        "OPERATION",
        "ACTUATOR",
        "ACQUISITION_BEGIN",
        "ACQUISITION_END",
        "ACTION_BEGIN",
        "ACTION_END",
        "TEACHER_ACTION",
        "FINAL_GUARD",
    }

    def check_physical(source):
        ident = identity(source)
        step = ident["physics_step"]
        P.require(
            step == len(physical_steps)
            and ident["episode_id"] == episode
            and P.same(ident, index["callbacks"].get(step)),
            "physical complete callback join",
        )
        physical_steps.append(step)
        sample = asdict(sample_physical_observation(PhysicsStepObservation(**source), criteria))
        P.require(
            step < len(teacher["physical_samples"])
            and P.same(sample, teacher["physical_samples"][step]),
            "scorer all-field evidence mismatch",
        )
        scorer_steps.append(step)

    try:
        for row in iter_journal(attempt / "nominal-journal.jsonl.gz"):
            P.require(
                time.monotonic() - trace_started <= P.RESOURCE["reader_wall_limit_s"],
                "RESOURCE_ABORT trace wall",
            )
            P.require(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
                <= P.RESOURCE["peak_rss_limit_bytes"],
                "RESOURCE_ABORT trace RSS",
            )
            sequence += 1
            event, step = row.get("event"), row.get("physics_step")
            try:
                P.require(
                    type(row.get("record_seq")) is int and row["record_seq"] == sequence,
                    "journal exact record_seq",
                )
                clock = row["clock"]
                lo, hi = clock["monotonic_before_ns"], clock["monotonic_after_ns"]
                P.require(
                    type(lo) is int and type(hi) is int and previous_clock <= lo <= hi,
                    "journal monotonic bracket",
                )
                previous_clock = hi
                P.require(event in allowed, "retained failure or unknown journal event")
                if event == "SETUP_BEGIN":
                    P.require(sequence == 1, "setup must be first")
                    sparse.validate_runtime(attempt, [row], header, contract)
                elif event == "SETUP_END":
                    P.require(
                        identity(row) == dict(episode_id=episode, physics_step=0, sim_time_s=0.0),
                        "setup identity",
                    )
                    helper.guard_record(row["setup_state"]["guard"], contract)
                elif event == "OPERATION":
                    source = row["source"]
                    ident = identity(source)
                    operation_id = source["operation_id"]
                    P.require(
                        type(operation_id) is int
                        and source["kind"] in {"PHYSICS", "CONTROL", "COMMAND", "CAPTURE"},
                        "operation id/kind",
                    )
                    P.require(source["phase"] in {"BEGIN", "END"}, "operation retained failure")
                    projection = {k: source[k] for k in ledger_keys}
                    P.require(
                        ledger_cursor < len(terminal["operation_ledger"])
                        and P.same(projection, terminal["operation_ledger"][ledger_cursor]),
                        "operation ledger exact join",
                    )
                    ledger_cursor += 1
                    if source["phase"] == "BEGIN":
                        op_begin_count += 1
                        P.require(
                            operation_id == op_begin_count and operation_id not in pending,
                            "operation allocation exact IDs",
                        )
                        P.require(len(pending) < 4, "operation nesting exceeds four declared kinds")
                        pending[operation_id] = row
                    else:
                        P.require(operation_id in pending, "operation missing begin")
                        begin = pending.pop(operation_id)
                        sparse.validate_operation_pair(begin, row, episode)
                        if source["kind"] == "CONTROL":
                            P.require(
                                ident == index["callbacks"].get(source["physics_step"]),
                                "CONTROL prior callback join",
                            )
                            control = (begin, row)
                        elif source["kind"] == "PHYSICS":
                            P.require(
                                control is not None and actuator is not None,
                                "CONTROL/ACTUATOR before PHYSICS",
                            )
                            prior = index["callbacks"].get(source["physics_step"] - 1)
                            P.require(
                                identity(begin["source"]) == prior
                                and ident == index["callbacks"].get(source["physics_step"]),
                                "PHYSICS callback begin/end join",
                            )
                            P.require(
                                control[0]["record_seq"]
                                < control[1]["record_seq"]
                                < actuator["record_seq"]
                                < begin["record_seq"]
                                < row["record_seq"],
                                "CONTROL ACTUATOR PHYSICS order",
                            )
                            P.require(
                                actuator["source"]["physics_step"] == source["physics_step"],
                                "upcoming actuator step",
                            )
                            physics = row
                            check_physical(source["result"]["physics_state"])
                        elif source["kind"] == "COMMAND":
                            for command in source["result"]["command_records"]:
                                command_cursor += 1
                                P.require(
                                    type(command["command_seq"]) is int
                                    and command["command_seq"] == command_cursor
                                    and command_cursor <= len(terminal["commands"])
                                    and P.same(command, terminal["commands"][command_cursor - 1]),
                                    "command exact sequence/terminal fields",
                                )
                elif event == "ACTUATOR":
                    source = row["source"]
                    ident = identity(source)
                    P.require(
                        control is not None
                        and ident["physics_step"] == len(actuator_steps) + 1
                        and ident["sim_time_s"]
                        == index["callbacks"][ident["physics_step"] - 1]["sim_time_s"]
                        and ident["episode_id"] == episode
                        and row["control_operation_id"] == control[1]["source"]["operation_id"]
                        and P.same(source, control[1]["source"]["result"]["control_state"]),
                        "ACTUATOR exact CONTROL bridge",
                    )
                    P.require(row["action_ordinal"] == active_action, "actuator action owner")
                    actuator_steps.append(ident["physics_step"])
                    actuator = row
                elif event == "ACQUISITION_BEGIN":
                    ident = identity(row)
                    step = ident["physics_step"]
                    P.require(
                        acq_begin is None
                        and step == acquisition_next
                        and ident == index["callbacks"].get(step)
                        and row["action_ordinal"] == active_action,
                        "acquisition allocation callback/action join",
                    )
                    if step == 0:
                        P.require(
                            row["control_operation_id"] is None
                            and row["physics_operation_id"] is None,
                            "initial acquisition operations",
                        )
                        check_physical(row["physical_source"])
                    else:
                        P.require(
                            physics is not None
                            and identity(physics["source"]) == ident
                            and P.same(
                                row["physical_source"], physics["source"]["result"]["physics_state"]
                            )
                            and row["control_operation_id"] == control[1]["source"]["operation_id"]
                            and row["physics_operation_id"] == physics["source"]["operation_id"],
                            "acquisition full physical join",
                        )
                    acquisition_next += 1
                    acq_begin = row
                elif event == "ACQUISITION_END":
                    ident = identity(row)
                    step = ident["physics_step"]
                    saved = index["ends"].get(step)
                    P.require(
                        acq_begin is not None
                        and ident == identity(acq_begin)
                        and saved is not None
                        and P.same(row["saved"], saved)
                        and row["action_ordinal"] == active_action
                        and row["control_operation_id"] == acq_begin["control_operation_id"]
                        and row["physics_operation_id"] == acq_begin["physics_operation_id"],
                        "acquisition/index exact END join",
                    )
                    camera = row["camera"]
                    validate_frame_camera(
                        camera,
                        contract,
                        ident,
                        [
                            acq_begin["clock"]["monotonic_after_ns"],
                            index["begins"][step],
                            saved["capture_monotonic_end_ns"],
                            row["clock"]["monotonic_before_ns"],
                        ],
                        helpers_pair=(helper, sparse),
                    )
                    context = tuple(
                        camera["before_state"][k]
                        for k in ("camera_object_id", "model_arrays_sha256", "model_options_sha256")
                    )
                    P.require(
                        fixed_camera_context is None or context == fixed_camera_context,
                        "sole camera/model context changed",
                    )
                    fixed_camera_context = context
                    P.require(
                        camera["before_state"]["physical_step"] == step
                        and camera["before_state"]["sim_time_s"] == ident["sim_time_s"]
                        and saved["pass_state_hashes"] == camera["pass_state_hashes"],
                        "capture exact time/pass bridge",
                    )
                    saved.update(
                        trace_valid=True,
                        before_physics_sha256=camera["before_state"]["physics_state_sha256"],
                        action_ordinal=active_action,
                        full_state_digest=P.digest(
                            json.dumps(camera["full_capture_state"], sort_keys=True).encode()
                        ),
                    )
                    last_camera = {
                        "after_guard": camera["after_guard"],
                        "after_state": camera["after_state"],
                        "operation_ledger_prefix_count": camera["operation_ledger_prefix_count"],
                    }
                    frame_count += 1
                    acq_begin = control = actuator = physics = None
                elif event in {"ACTION_BEGIN", "ACTION_END"}:
                    ordinal = row["action_ordinal"]
                    P.require(
                        type(ordinal) is int
                        and 1 <= ordinal <= 9
                        and (ordinal, event) not in actions,
                        "action exact identity",
                    )
                    actions[(ordinal, event)] = row
                    if event == "ACTION_BEGIN":
                        P.require(active_action is None, "unexpected action nesting")
                        active_action = ordinal
                    else:
                        P.require(
                            active_action == ordinal
                            and row["error_type"] is None
                            and row["error"] is None,
                            "action original completion",
                        )
                        active_action = None
                elif event == "TEACHER_ACTION":
                    ordinal = row["action_ordinal"]
                    P.require(
                        type(ordinal) is int and ordinal not in teacher_actions,
                        "teacher action unique",
                    )
                    teacher_actions[ordinal] = row
                elif event == "FINAL_GUARD":
                    final_guard_seen += 1
                    P.require(
                        final_guard_seen == 1 and frame_count == 4807 and last_camera is not None,
                        "FINAL_GUARD single complete endpoint",
                    )
                    guard = helper.guard_record(row["guard"], contract)
                    P.require(
                        P.same(row["guard"], last_camera["after_guard"])
                        and P.same(row["state"], last_camera["after_state"]),
                        "FINAL_GUARD full protected snapshot equality",
                    )
                    P.require(
                        P.same(
                            {
                                **json.loads(guard.protected_json),
                                "data_arrays_sha256": guard.arrays.digest,
                            },
                            row["state"],
                        ),
                        "FINAL_GUARD scalar bridge",
                    )
                    P.require(
                        identity(row) == index["callbacks"][4806]
                        and row["command_count"] == 743
                        and row["operation_ledger_count"] == len(terminal["operation_ledger"])
                        and row["operation_ledger_sha256"]
                        == P.digest(
                            json.dumps(
                                terminal["operation_ledger"], sort_keys=True, allow_nan=False
                            ).encode()
                        ),
                        "FINAL_GUARD terminal/ledger binding",
                    )
                    prefix = last_camera["operation_ledger_prefix_count"]
                    P.require(
                        not any(
                            r["kind"] in {"PHYSICS", "CONTROL", "COMMAND"}
                            for r in terminal["operation_ledger"][prefix:]
                        ),
                        "new physical/control/command after last frame",
                    )
                    P.require(
                        index["final_guard"] is not None
                        and P.same(
                            index["final_guard"]["snapshot"],
                            {
                                k: v
                                for k, v in row.items()
                                if k not in {"event", "clock", "record_seq"}
                            },
                        ),
                        "FINAL_GUARD index/journal join",
                    )
                    last_final_guard = row
            except Exception as error:
                errors.append(
                    dict(
                        kind="journal",
                        sequence=sequence,
                        event=str(event)[:200],
                        step=repr(step),
                        reason=repr(error)[:1000],
                    )
                )
                if event == "ACQUISITION_END" and type(step) is int and step in index["ends"]:
                    index["ends"][step]["trace_valid"] = False
                    acq_begin = control = actuator = physics = None
    except Exception as error:
        errors.append(dict(kind="journal_read_failure", reason=repr(error)))
    try:
        P.require(
            not pending and acq_begin is None and active_action is None,
            "unclosed operation/action/acquisition",
        )
        P.require(
            ledger_cursor == len(terminal["operation_ledger"])
            and not terminal["operation_observer_failures"],
            "complete ledger consumer",
        )
        P.require(
            physical_steps == scorer_steps == list(range(4807))
            and actuator_steps == list(range(1, 4807))
            and len(teacher["physical_samples"]) == 4807,
            "complete physical/actuator/scorer denominator",
        )
        P.require(
            command_cursor == len(terminal["commands"]) == 743, "complete commands denominator"
        )
        P.require(
            type(terminal["final_step"]) is int
            and terminal["final_step"] == 4806
            and P.finite(terminal["final_sim_time_s"])
            and terminal["final_sim_time_s"] == index["callbacks"][4806]["sim_time_s"],
            "exact terminal endpoint SimulationS",
        )
        P.require(
            summary["run_status"] == "COMPLETED_SINGLE_ATTEMPT"
            and summary["acquisition_allocated"] == summary["acquisition_completed"] == 4807
            and summary["acquisition_failed"] == 0
            and summary["whole_step_capture_calls"] == 4807
            and not summary["nominal_journal_failure"]
            and not summary["acquisition_failure_journal_errors"],
            "single attempt summary incomplete",
        )
        P.require(
            summary["protocol"] == header["protocol"]
            and summary["execution_header_sha256"] == P.hash_file(attempt.parent / "header.json")
            and P.hash_file(attempt / "execution-header.json")
            == P.hash_file(attempt.parent / "header.json"),
            "execution frozen header bridge",
        )
        P.require(
            final_guard_seen == 1 and last_final_guard is not None, "missing verified FINAL_GUARD"
        )
        recipe, failures = helper.verify_original_recipe(
            header, actions, teacher_actions, summary, terminal
        )
        P.require(
            not failures and recipe == "COMPLETE_ORIGINAL_120_9_2",
            "original recipe: " + repr(failures),
        )
        for ordinal in range(1, 10):
            begin, end, teacher_action = (
                actions[(ordinal, "ACTION_BEGIN")],
                actions[(ordinal, "ACTION_END")],
                teacher_actions[ordinal]["source"],
            )
            P.require(
                begin["episode_id"] == end["episode_id"] == teacher_action["episode_id"] == episode
                and begin["start_step"] == end["start_step"] == teacher_action["start_step"]
                and end["end_step"] == teacher_action["end_step"]
                and begin["action_type"] == end["action_type"]
                and begin["record_seq"] < end["record_seq"]
                and P.same(teacher_action["result"], teacher["actions"][ordinal - 1]),
                "action complete source/evidence identity",
            )
            P.require(
                begin["command_seq_start"]
                == end["command_seq_start"]
                == teacher_action["command_seq_start"]
                and end["command_seq_end"] == teacher_action["command_seq_end"],
                "action command span joins",
            )
        for step, row in index["ends"].items():
            if step in header["expected_callback_steps"]:
                P.require(
                    row.get("action_ordinal") == sparse.owner(step, actions),
                    "full action physical ownership",
                )
    except Exception as error:
        errors.append(dict(kind="terminal_recipe", reason=repr(error)))
    return dict(
        ends=index["ends"],
        errors=errors,
        trace_valid=not errors,
        journal_records=sequence,
        operation_count=op_begin_count,
        physical_count=len(physical_steps),
        actuator_count=len(actuator_steps),
        scorer_count=len(scorer_steps),
        commands=command_cursor,
        full_capture_state_count=frame_count,
        final_guard_count=final_guard_seen,
        max_sample_gap_s=index["max_gap_s"],
        sampling_gap_violation_steps=index["gap_violations"],
        series=index["series"],
        unexpected_steps=sorted(set(index["ends"]) - set(header["expected_callback_steps"])),
    )


def decode_planned_rows(
    directory,
    ends,
    steps,
    registration,
    decoder,
    *,
    expected_dimensions=(640, 480),
    source_valid=True,
):
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    directory = Path(directory)
    ids, context = set(), None
    for step in steps:
        measured = dict(
            physics_step=step, decode_status="UNAVAILABLE_MISSING_RAW", stability_status="UNKNOWN"
        )
        if not source_valid:
            measured.update(
                decode_status="UNAVAILABLE_SOURCE_PIN_FAILURE",
                reason="global source admission failed; decoder forbidden",
            )
            yield measured
            continue
        try:
            P.require(step in ends, "planned raw unavailable")
            row = ends[step]
            measured["decode_status"] = "UNAVAILABLE_INVALID_RAW"
            P.require(
                row.get("schema") == "research.full-marker-v4-index.v1"
                and row.get("trace_valid") is True,
                "raw schema or guarded journal join invalid",
            )
            P.require(
                identity(row)["physics_step"] == step
                and row["file"] == f"frames/{step:07d}.json.gz",
                "canonical raw/frame identity",
            )
            path = directory / row["file"]
            P.require(
                path.resolve(strict=True).parent == (directory / "frames").resolve()
                and not path.is_symlink(),
                "raw path escape",
            )
            P.require(
                type(row["compressed_bytes"]) is int
                and path.stat().st_size == row["compressed_bytes"]
                and P.hash_file(path) == row["compressed_sha256"],
                "compressed original bytes/hash",
            )
            with gzip.open(path, "rb") as stream:
                raw = stream.read(P.RESOURCE["max_frame_json_bytes"] + 1)
            P.require(len(raw) <= P.RESOURCE["max_frame_json_bytes"], "frame JSON resource limit")
            P.require(
                type(row["original_bytes"]) is int
                and len(raw) == row["original_bytes"]
                and P.digest(raw) == row["original_sha256"],
                "uncompressed original bytes/hash",
            )
            data = strict_json(raw)
            P.require(P.finite(data.get("sim_time_s")), "raw SimulationS type")
            observation = RGBDObservation.model_validate(data)
            P.require(
                observation.episode_id == row["episode_id"]
                and observation.sim_time_s == row["sim_time_s"]
                and observation.observation_id == row["observation_id"]
                and observation.checksum_sha256 == row["checksum"]
                and observation.observation_id not in ids,
                "raw identity/checksum/unique observation",
            )
            P.require(
                (observation.width, observation.height) == expected_dimensions
                and observation.source == "mujoco_camera"
                and observation.calibration_version,
                "registered sole camera dimensions/source",
            )
            camera_context = (
                observation.width,
                observation.height,
                observation.intrinsics,
                observation.camera_to_world,
                observation.calibration_version,
                observation.scene_id,
                observation.source,
            )
            P.require(context is None or camera_context == context, "camera context changed")
            P.require(
                row["pass_state_hashes"] == [row["before_physics_sha256"]] * 2,
                "raw two pass guard bridge",
            )
            ids.add(observation.observation_id)
            context = camera_context
            measured.update(
                episode_id=observation.episode_id,
                sim_time_s=observation.sim_time_s,
                observation_id=observation.observation_id,
                checksum=observation.checksum_sha256,
                original_sha256=row["original_sha256"],
                compressed_sha256=row["compressed_sha256"],
                original_bytes=len(raw),
                compressed_bytes=row["compressed_bytes"],
                action_ordinal=row.get("action_ordinal"),
                raw_member_sha256={},
                raw_member_bytes={},
                raw_valid=True,
            )
            for member, field in (
                ("rgb.png", "rgb_png_base64"),
                ("depth.f32", "depth_float32_base64"),
                ("valid_mask.u8", "valid_mask_base64"),
            ):
                data = base64.b64decode(getattr(observation, field), validate=True)
                measured["raw_member_sha256"][member] = P.digest(data)
                measured["raw_member_bytes"][member] = len(data)
            measured.update(decode_status="DECODE_ERROR", decoder_called=True)
            estimate = decoder(observation, registration)
            marker = asdict(estimate)
            marker["captured_at"] = estimate.captured_at.isoformat()
            P.require(
                estimate.status in {"OBSERVED", "UNKNOWN"}
                and estimate.stability_status == "UNKNOWN"
                and estimate.geometric_error_bound_m is None
                and estimate.angular_velocity_bound_rad_s is None,
                "decoder nonpromotion result differs",
            )
            measured.update(marker=marker, decode_status=estimate.status, reason=estimate.reason)
            del observation, raw
        except Exception as error:
            measured["failure"] = dict(type=type(error).__name__, message=str(error))
        yield measured


def inventory(paths):
    return {
        str(p.resolve()): dict(bytes=p.stat().st_size, sha256=P.hash_file(p))
        for p in sorted(set(map(Path, paths)))
        if p.is_file()
    }


def inventory_changes(before, after):
    return dict(
        missing=sorted(before.keys() - after.keys()),
        added=sorted(after.keys() - before.keys()),
        changed=sorted(k for k in before.keys() & after.keys() if not P.same(before[k], after[k])),
    )


def baseline_markers():
    manifest_path = HERE.parent / "raw-inventory.json"
    manifest = strict_json(manifest_path.read_bytes())
    P.require(manifest["root"] == str(OLD.relative_to(ROOT)), "old manifest root differs")
    members = {row["path"]: row for row in manifest["all_files"]}
    P.require(
        len(members) == len(manifest["all_files"]) == manifest["file_count"],
        "old raw manifest duplicate/count",
    )
    actual = {str(p.relative_to(OLD)) for p in OLD.rglob("*") if p.is_file()}
    P.require(actual == set(members), "old original file set differs")
    index = {}
    for row in iter_journal(OLD / "whole-step/index.jsonl"):
        if row["event"] == "END":
            step = row["physics_step"]
            P.require(type(step) is int and step not in index, "old index duplicate identity")
            index[step] = row
    P.require(sorted(index) == list(range(4807)), "old source index incomplete")
    markers = {}
    path = HERE.parent / "offline/offline-markers.jsonl"
    for row in iter_journal(path):
        step = row["physics_step"]
        P.require(
            type(step) is int
            and step == len(markers)
            and row["decode_status"] in {"OBSERVED", "UNKNOWN"},
            "old complete marker baseline identity/status",
        )
        saved = index[step]
        relative = "whole-step/" + saved["file"]
        P.require(
            relative == f"whole-step/frames/{step:07d}.json.gz"
            and relative in members
            and saved["compressed_sha256"] == members[relative]["sha256"]
            and saved["compressed_bytes"] == members[relative]["bytes"]
            and row["observation_id"] == saved["observation_id"]
            and row["checksum"] == saved["checksum"]
            and identity(row) == identity(saved),
            "old marker source/manifest/index binding",
        )
        markers[step] = row
    P.require(
        sorted(markers) == list(range(4807))
        and Counter(r["decode_status"] for r in markers.values())
        == {"OBSERVED": 4618, "UNKNOWN": 189},
        "old fixed denominator/count changed",
    )
    for relative, row in members.items():
        path = OLD / relative
        P.require(
            not path.is_symlink()
            and path.resolve().is_relative_to(OLD.resolve())
            and path.stat().st_size == row["bytes"]
            and P.hash_file(path) == row["sha256"],
            "old raw original changed: " + relative,
        )
    return markers, [OLD / relative for relative in members]


def recorded_rows(attempt, kind):
    attempt = Path(attempt)
    if kind in {"commands", "scorer"}:
        document, field = (
            ("terminal.json", "commands")
            if kind == "commands"
            else ("teacher-evidence.json", "physical_samples")
        )
        yield from strict_json((attempt / document).read_bytes())[field]
        return
    for row in iter_journal(attempt / "nominal-journal.jsonl.gz"):
        if kind == "physical":
            if row["event"] == "ACQUISITION_BEGIN" and row["physics_step"] == 0:
                yield row["physical_source"]
            elif (
                row["event"] == "OPERATION"
                and row["source"]["kind"] == "PHYSICS"
                and row["source"]["phase"] == "END"
            ):
                yield row["source"]["result"]["physics_state"]
        elif kind == "actuator" and row["event"] == "ACTUATOR":
            yield row["source"]


def compare_complete_streams(old_rows, new_rows, *, expected_ids, key, output):
    count_old = count_new = differing = 0
    exact_old = exact_new = True
    with Path(output).open("x", encoding="utf-8") as stream:
        for offset, (old, new) in enumerate(zip_longest(old_rows, new_rows)):
            if old is not None:
                count_old += 1
                exact_old &= (
                    offset < len(expected_ids)
                    and type(old.get(key)) is int
                    and old[key] == expected_ids[offset]
                )
            if new is not None:
                count_new += 1
                exact_new &= (
                    offset < len(expected_ids)
                    and type(new.get(key)) is int
                    and new[key] == expected_ids[offset]
                )
            left = {k: v for k, v in old.items() if k != "episode_id"} if old is not None else None
            right = {k: v for k, v in new.items() if k != "episode_id"} if new is not None else None
            if not P.same(left, right):
                differing += 1
                stream.write(
                    json.dumps(dict(row_index=offset, old=left, new=right), allow_nan=False) + "\n"
                )
    complete = count_old == count_new == len(expected_ids) and exact_old and exact_new
    return dict(
        old_rows=count_old,
        new_rows=count_new,
        expected_rows=len(expected_ids),
        complete_exact_denominators=complete,
        status="ALL_RECORDED_FIELDS_EQUAL"
        if complete and differing == 0
        else "RECORDED_DIFFERENCES"
        if complete
        else "INCOMPLETE_NO_COMPARISON_CONCLUSION",
        different_rows=differing,
        mismatch_file=Path(output).name,
        excluded_fields=["episode_id"],
        scope="RECORDED_FIELDS_ONLY_OLD_FULL_QPOS_UNAVAILABLE_NOT_ALL_INTERNAL_STATE",
    )


def status_segments(rows, predicate):
    segments, start, end = [], None, None
    for row in rows:
        step = row["physics_step"]
        if predicate(row):
            if start is None:
                start = step
            end = step
        elif start is not None:
            segments.append(dict(first_step=start, last_step=end, frame_count=end - start + 1))
            start = end = None
    if start is not None:
        segments.append(dict(first_step=start, last_step=end, frame_count=end - start + 1))
    return segments


def verify_and_decode(attempt, output):
    """Exactly one readout directory; errors retain a 4807 planned denominator."""
    from cloud_edge_robot_arm.vision import pose_markers

    attempt, output = Path(attempt), Path(output)
    if output.exists():
        raise FileExistsError("one decode readout only; previous evidence retained")
    header = strict_json((attempt.parent / "header.json").read_bytes())
    output.mkdir()
    started = time.monotonic()
    source_valid, source_failure, contract = True, None, None
    before = {}
    old_markers = {}
    protected = []
    trace = dict(
        ends={},
        errors=[],
        trace_valid=False,
        max_sample_gap_s=None,
        sampling_gap_violation_steps=[],
        unexpected_steps=[],
    )
    try:
        P.validate_full_header(header)
        P.require_resources(output)
        contract = P.source_preflight(None, header, attempt.parent)
        old_markers, old_paths = baseline_markers()
        sources = strict_json((attempt.parent / "execution-source-hashes.json").read_bytes())
        archives = strict_json((attempt.parent / "execution-archive-index.json").read_bytes())
        protected = (
            [p for p in attempt.rglob("*") if p.is_file()] + old_paths + [ROOT / n for n in sources]
        )
        protected += [ROOT / r["archive"] for r in archives.values()]
        protected += [Path(r["path"]) for r in header["environment"]["files"].values()]
        protected += [ROOT / n for n in P.plan_data()["input_pins"]]
        protected += [p for p in attempt.parent.iterdir() if p.is_file()]
        before = inventory(protected)
        P.write_new(output / "input-inventory-before.json", before)
    except Exception as error:
        source_valid, source_failure = False, repr(error)
    if source_valid:
        try:
            trace = validate_full_trace(attempt, header, contract)
        except Exception as error:
            trace["errors"].append(dict(kind="trace_fatal", reason=repr(error)))
    ends = trace["ends"]
    planned = list(range(4807))
    actual_raw = {
        str(p.relative_to(attempt / "whole-step"))
        for p in (attempt / "whole-step/frames").rglob("*")
        if p.is_file()
    }
    declared_raw = {r["file"] for r in ends.values()}
    raw_file_set_matches = actual_raw == declared_raw
    P.write_new(
        output / "unexpected-actual.json",
        dict(
            steps=trace["unexpected_steps"],
            undeclared_files=sorted(actual_raw - declared_raw),
            declared_missing_files=sorted(declared_raw - actual_raw),
            rows=[r for step, r in ends.items() if step not in planned],
        ),
    )
    registration = pose_markers.PoseMarkerRegistration(**header["marker_registration"])
    counts, reasons, decoded, raw_valid = Counter(), Counter(), 0, 0
    rows = []  # Readout rows only; no raw images or guard dictionaries are retained.
    resource_abort = None
    generator = decode_planned_rows(
        attempt / "whole-step",
        ends,
        planned,
        registration,
        pose_markers.detect_pose_marker,
        source_valid=source_valid,
    )
    with (output / "offline-markers.jsonl").open("x", encoding="utf-8") as stream:
        for step in planned:
            if resource_abort is None:
                try:
                    P.require(
                        time.monotonic() - started <= P.RESOURCE["reader_wall_limit_s"],
                        "RESOURCE_ABORT reader wall",
                    )
                    P.require(
                        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
                        <= P.RESOURCE["peak_rss_limit_bytes"],
                        "RESOURCE_ABORT reader RSS",
                    )
                    if step % 240 == 0:
                        P.require(
                            sum(p.stat().st_size for p in output.rglob("*") if p.is_file())
                            <= P.RESOURCE["output_budget_bytes"],
                            "RESOURCE_ABORT readout budget",
                        )
                    measured = next(generator)
                except Exception as error:
                    resource_abort = repr(error)
            if resource_abort is not None:
                measured = dict(
                    physics_step=step,
                    decode_status="UNAVAILABLE_RESOURCE_ABORT",
                    stability_status="UNKNOWN",
                    reason=resource_abort,
                )
            raw_valid += int(measured.get("raw_valid") is True)
            decoded += int(measured.get("decoder_called") is True)
            counts[measured["decode_status"]] += 1
            reasons[measured.get("reason", measured["decode_status"])] += 1
            rows.append(
                {
                    k: measured[k]
                    for k in ("physics_step", "decode_status", "sim_time_s")
                    if k in measured
                }
            )
            stream.write(json.dumps(measured, allow_nan=False) + "\n")
            stream.flush()
            if step % 240 == 0:
                print(
                    json.dumps(
                        dict(verified_step=step, raw_verified=raw_valid, decoder_calls=decoded)
                    ),
                    flush=True,
                )
    comparison = {}
    if source_valid:
        try:
            for kind, expected_ids, key in (
                ("physical", planned, "physics_step"),
                ("actuator", list(range(1, 4807)), "physics_step"),
                ("commands", list(range(1, 744)), "command_seq"),
                ("scorer", planned, "physics_step"),
            ):
                comparison[kind] = compare_complete_streams(
                    recorded_rows(OLD, kind),
                    recorded_rows(attempt, kind),
                    expected_ids=expected_ids,
                    key=key,
                    output=output / (kind + "-mismatches.jsonl"),
                )
        except Exception as error:
            comparison["failure"] = repr(error)
    transitions = Counter()
    with (output / "old-new-marker-pairs.jsonl").open("x", encoding="utf-8") as stream:
        for row in rows:
            step = row["physics_step"]
            old = old_markers.get(step, {})
            transitions[old.get("decode_status", "UNAVAILABLE") + "->" + row["decode_status"]] += 1
            stream.write(
                json.dumps(
                    dict(
                        physics_step=step,
                        old=old.get("decode_status", "UNAVAILABLE"),
                        new=row["decode_status"],
                        old_observation_id=old.get("observation_id"),
                    ),
                    allow_nan=False,
                )
                + "\n"
            )
    after = inventory(protected)
    # Re-enumerate attempt originals, so added files cannot evade the protected set.
    after.update(inventory(p for p in attempt.rglob("*") if p.is_file()))
    after.update(inventory(p for p in OLD.rglob("*") if p.is_file()))
    changes = inventory_changes(before, after)
    immutable = bool(before) and not any(changes.values())
    P.write_new(output / "input-inventory-after.json", after)
    P.write_new(output / "immutable-differences.json", changes)
    full_integrity = (
        source_valid
        and trace["trace_valid"]
        and raw_valid == 4807
        and raw_file_set_matches
        and immutable
        and not resource_abort
    )
    gaps_pass = (
        trace["max_sample_gap_s"] is not None
        and trace["max_sample_gap_s"] <= 0.005
        and not trace["sampling_gap_violation_steps"]
        and trace["series"].get("saved_steps") == planned
    )
    observed_times = [
        r["sim_time_s"] for r in rows if r["decode_status"] == "OBSERVED" and "sim_time_s" in r
    ]
    observed_max_gap = max(
        (b - a for a, b in zip(observed_times, observed_times[1:])), default=None
    )
    selection = strict_json((P.SPARSE / "selection-manifest.json").read_bytes())["selected_steps"]
    subgroup = dict(
        denominator=201,
        old_status_counts=dict(
            Counter(old_markers.get(s, {}).get("decode_status", "UNAVAILABLE") for s in selection)
        ),
        new_status_counts=dict(Counter(rows[s]["decode_status"] for s in selection)),
        scope="ORIGINAL_201_SUBGROUP_OF_NEW_FULL_DENOMINATOR_NOT_A_SUBSTITUTE",
    )
    result = dict(
        schema="research.full-marker-v4-readout.v1",
        scope=P.SCOPE,
        **P.NONPROMOTION,
        integrity_status="VERIFIED_FULL_RAW_AND_RECORDED_TRACE"
        if full_integrity
        else "INCOMPLETE_OR_INVALID",
        sampling_gap_status="PASS_RECORDED_SIMULATIONS" if gaps_pass else "FAIL_OR_UNAVAILABLE",
        full_frame_observability_status="PASS_THIS_FULL_HORIZON"
        if full_integrity and gaps_pass and counts == {"OBSERVED": 4807}
        else "FAIL_OR_UNAVAILABLE",
        expected_frame_count=4807,
        raw_verified_frames=raw_valid,
        decoder_calls=decoded,
        decode_status_counts=dict(counts),
        decode_reason_counts=dict(reasons),
        coverage=counts["OBSERVED"] / 4807,
        full_max_sample_gap_s=trace["max_sample_gap_s"],
        sampling_gap_violation_steps=trace["sampling_gap_violation_steps"],
        observed_adjacent_max_gap_s=observed_max_gap,
        unknown_or_unavailable_segments=status_segments(
            rows, lambda r: r["decode_status"] != "OBSERVED"
        ),
        newly_unknown_segments=status_segments(
            rows,
            lambda r: r["decode_status"] != "OBSERVED"
            and old_markers.get(r["physics_step"], {}).get("decode_status") == "OBSERVED",
        ),
        old_full_status_counts=dict(Counter(r["decode_status"] for r in old_markers.values())),
        transitions=dict(transitions),
        sparse_subgroup=subgroup,
        recorded_comparison=comparison,
        raw_file_set_matches=raw_file_set_matches,
        source_valid=source_valid,
        source_failure=source_failure,
        originals_unchanged=immutable,
        immutable_differences=changes,
        resource_abort=resource_abort,
        reader_wall_s=time.monotonic() - started,
        reader_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        resource_policy=header["resource_policy"],
        time_domain=header["time_domain"],
        execution_header_sha256=P.hash_file(attempt.parent / "header.json"),
        reader_source_sha256=P.hash_file(Path(__file__)),
        detector_source_sha256=P.hash_file(Path(pose_markers.__file__)),
        registration=header["marker_registration"],
        trace={k: v for k, v in trace.items() if k != "ends"},
    )
    P.write_new(output / "offline-verification.json", result)
    P.write_new(
        output / "raw-source-inventory.json",
        dict(
            actual_raw_files=sorted(actual_raw),
            source_count=header.get("source_count"),
            protected_file_count=len(before),
            decoder_scope="NEW_SAVED_RGBD_AND_FROZEN_REGISTRATION_ONLY",
        ),
    )
    with (output / "report.md").open("x", encoding="utf-8") as stream:
        stream.write(
            "# Marker V4 full readout\n\n"
            + json.dumps(
                {
                    k: result[k]
                    for k in (
                        "integrity_status",
                        "sampling_gap_status",
                        "full_frame_observability_status",
                        "decode_status_counts",
                        "coverage",
                    )
                },
                indent=2,
            )
            + "\n\nOnly this saved full horizon is assessed. Formal/native, continuous physical motion, calibration, UTC and future stability remain unpromoted.\n"
        )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol-directory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--decode-once", required=True, action="store_true")
    args = parser.parse_args()
    P.require(
        args.protocol_directory.resolve() == (HERE / "full-protocol").resolve()
        and args.output.resolve() == (HERE / "offline").resolve(),
        "only frozen full protocol/readout CLI paths permitted",
    )
    print(
        json.dumps(verify_and_decode(args.protocol_directory / "attempt-1", args.output), indent=2),
        flush=True,
    )
