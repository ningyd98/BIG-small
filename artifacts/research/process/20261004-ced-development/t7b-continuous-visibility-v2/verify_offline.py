"""V2 offline replay of existing full-step RGB-D; no acquisition or native authority."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker

READER_VERSION = "research.whole-step-offline-reader.v2"
BASE_VERIFIER_SOURCE_SHA256 = "19225d13e058cb428b8cf3a99095bde6b46bfd985bcb3290e4824fdd4b0b4e6f"
ASSET_HASH = "ddc34b13d8df403f3fdeeab94be75ca988541f2eac0a3e534704f68200c39a23"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def same_json(left, right):
    """Preserve JSON types as well as values when joining saved raw records."""
    return json.dumps(left, sort_keys=True, separators=(",", ":")) == json.dumps(
        right, sort_keys=True, separators=(",", ":")
    )


def frame_identity(row):
    return {key: row.get(key) for key in ("episode_id", "physics_step", "sim_time_s")}


def verify_series(directory: Path, *, decode=False, output=None):
    """Read saved observations only; no backend, truth, command target or instance input."""
    summary = json.loads((directory / "summary.json").read_text())
    failures, ends, begins = [], {}, []
    for line in (directory / "index.jsonl").read_text().splitlines():
        row = json.loads(line)
        if row["event"] == "BEGIN":
            begins.append(row["physics_step"])
        elif row["event"] == "END":
            step = row["physics_step"]
            if step in ends:
                failures.append(f"duplicate END at {step}")
            ends[step] = row
        else:
            failures.append("retained recorder failure: " + row["event"])
    allocated = summary["allocated_steps"]
    if type(allocated) is not int or allocated < 1:
        failures.append("invalid allocated terminal horizon")
        allocated = 0
    expected = list(range(allocated))
    if begins != expected or sorted(ends) != expected or summary["status"] != "COMPLETE":
        failures.append("full declared horizon not collected")
    if summary["original_max_sample_gap_s"] > 0.005:
        failures.append("original sampling criterion enlarged")
    marker_registration = PoseMarkerRegistration(7, 0.045, ASSET_HASH) if decode else None
    stream = output.open("x") if output else None
    verified = 0
    ids = set()
    camera = None
    previous_time = previous_end_utc = previous_end_ns = None
    max_gap = 0.0
    statuses = Counter()
    compressed_total = original_total = 0
    try:
        for step, row in sorted(ends.items()):
            try:
                expected_path = f"frames/{step:07d}.json.gz"
                if row["file"] != expected_path:
                    raise ValueError("noncanonical payload path")
                compressed = (directory / expected_path).read_bytes()
                raw = gzip.decompress(compressed)
                if (
                    sha(compressed) != row["compressed_sha256"]
                    or sha(raw) != row["observation_json_sha256"]
                ):
                    raise ValueError("original/compressed payload hash mismatch")
                if len(compressed) != row["compressed_bytes"] or len(raw) != row["original_bytes"]:
                    raise ValueError("payload byte length mismatch")
                observation = RGBDObservation.model_validate_json(raw)
                if (
                    observation.episode_id != summary["episode_id"]
                    or observation.sim_time_s != row["sim_time_s"]
                    or observation.observation_id != row["observation_id"]
                    or observation.checksum_sha256 != row["observation_checksum_sha256"]
                    or observation.observation_id in ids
                ):
                    raise ValueError("frame step/identity/checksum mismatch")
                current_camera = (
                    observation.width,
                    observation.height,
                    observation.intrinsics,
                    observation.camera_to_world,
                    observation.calibration_version,
                    observation.scene_id,
                    observation.source,
                )
                if camera is not None and current_camera != camera:
                    raise ValueError("camera context changed")
                start, end = row["monotonic_begin_ns"], row["monotonic_end_ns"]
                begin_utc, end_utc = (
                    datetime.fromisoformat(row["utc_begin"]),
                    datetime.fromisoformat(row["utc_end"]),
                )
                if (
                    type(start) is not int
                    or type(end) is not int
                    or start > end
                    or not begin_utc <= observation.captured_at <= end_utc
                    or previous_end_utc is not None
                    and begin_utc < previous_end_utc
                    or previous_end_ns is not None
                    and start < previous_end_ns
                ):
                    raise ValueError("nominal capture interval invalid")
                hashes = row["pass_state_hashes"]
                if len(hashes) != 2 or hashes[0] != hashes[1]:
                    raise ValueError("registered two-pass source mismatch")
                if previous_time is not None:
                    gap = observation.sim_time_s - previous_time
                    if not 0 < gap <= summary["original_max_sample_gap_s"] + 1e-9:
                        raise ValueError("original maximum simulation sample gap exceeded")
                    max_gap = max(max_gap, gap)
                members = {
                    name: base64.b64decode(getattr(observation, field), validate=True)
                    for name, field in (
                        ("rgb.png", "rgb_png_base64"),
                        ("depth.f32", "depth_float32_base64"),
                        ("valid_mask.u8", "valid_mask_base64"),
                    )
                }
                measured = {
                    "physics_step": step,
                    "episode_id": observation.episode_id,
                    "sim_time_s": observation.sim_time_s,
                    "observation_id": observation.observation_id,
                    "checksum": observation.checksum_sha256,
                    "raw_member_sha256": {name: sha(data) for name, data in members.items()},
                    "raw_member_bytes": {name: len(data) for name, data in members.items()},
                    "decode_status": "NOT_REQUESTED",
                }
                if marker_registration is not None:
                    estimate = detect_pose_marker(observation, marker_registration)
                    measured["marker"] = asdict(estimate)
                    measured["marker"]["captured_at"] = estimate.captured_at.isoformat()
                    measured["decode_status"] = estimate.status
                    statuses[estimate.status] += 1
                if stream:
                    stream.write(json.dumps(measured, allow_nan=False) + "\n")
                    stream.flush()
                verified += 1
                ids.add(observation.observation_id)
                camera = current_camera
                previous_time, previous_end_utc, previous_end_ns = (
                    observation.sim_time_s,
                    end_utc,
                    end,
                )
                compressed_total += len(compressed)
                original_total += len(raw)
            except (OSError, ValueError, TypeError, KeyError) as error:
                failures.append(f"step {step}: {type(error).__name__}: {error}")
                if stream:
                    stream.write(
                        json.dumps(
                            {
                                "physics_step": step,
                                "decode_status": "UNAVAILABLE_INVALID_RAW",
                                "reason": str(error),
                            }
                        )
                        + "\n"
                    )
                    stream.flush()
    finally:
        if stream:
            stream.close()
    if verified != allocated or previous_time != summary["final_sim_time_s"]:
        failures.append("verified terminal horizon mismatch")
    return {
        "scope": "EXCLUDED_DEVELOPMENT_OFFLINE_RAW_RGBD_REPLAY",
        "integrity_status": "VERIFIED" if not failures else "INCOMPLETE_OR_INVALID",
        "allocated_steps": allocated,
        "allocated_step_denominator_retained": True,
        "verified_frames": verified,
        "failed_or_missing_frames": allocated - verified,
        "max_sim_sample_gap_s": max_gap,
        "original_max_sample_gap_s": summary["original_max_sample_gap_s"],
        "compressed_bytes": compressed_total,
        "original_json_bytes": original_total,
        "decoder_status_counts": dict(statuses),
        "decoder_requested": decode,
        "failures": failures,
        "clock_scope": "SAME_PROCESS_NOMINAL_BRACKETS_ONLY",
        "external_utc_uncertainty": "UNAVAILABLE",
        "formal_accepted": False,
        "native_admission": "NOT_PROMOTED",
        "continuous_motion": "NOT_CERTIFIED",
        "future_stability": "UNAVAILABLE",
        "calibrated_error_bound": "UNAVAILABLE",
    }


def read_jsonl_gzip(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def verify_attempt(input_directory: Path, *, output_directory: Path, decode=False):
    """Replay existing bytes; write derived evidence only outside the input tree."""
    directory = input_directory.resolve(strict=True)
    output_directory = output_directory.resolve()
    if output_directory == directory or directory in output_directory.parents:
        raise ValueError("output directory must be outside input directory")
    output_directory.mkdir(parents=True, exist_ok=False)
    summary = json.loads((directory / "summary.json").read_text())
    terminal = json.loads((directory / "terminal.json").read_text())
    report = verify_series(
        directory / "whole-step",
        decode=decode,
        output=output_directory / "offline-observations.jsonl",
    )
    failures = report["failures"]
    series_summary = json.loads((directory / "whole-step/summary.json").read_text())
    index_ends = {}
    for line in (directory / "whole-step/index.jsonl").read_text().splitlines():
        source_row = json.loads(line)
        if source_row["event"] == "END":
            index_ends[source_row["physics_step"]] = source_row
    final_identity = {
        "episode_id": series_summary["episode_id"],
        "physics_step": series_summary["final_step"],
        "sim_time_s": series_summary["final_sim_time_s"],
    }
    if not same_json(
        final_identity,
        {
            "episode_id": terminal.get("episode_id"),
            "physics_step": terminal.get("final_step"),
            "sim_time_s": terminal.get("final_sim_time_s"),
        },
    ):
        failures.append("terminal episode/step/time differs from continuous sequence")
    if not same_json(
        frame_identity(index_ends.get(series_summary["final_step"], {})), final_identity
    ):
        failures.append("terminal continuous sequence/index identity mismatch")
    actions, operations, acquisitions, acquisition_begins, teacher_actions, actuators = (
        {},
        {},
        {},
        {},
        {},
        {},
    )
    original_commands = []
    sequence = 0
    last_ns = None
    for row in read_jsonl_gzip(directory / "nominal-journal.jsonl.gz"):
        clock = row["clock"]
        before, after = clock["monotonic_before_ns"], clock["monotonic_after_ns"]
        if (
            row["record_seq"] != sequence + 1
            or before > after
            or last_ns is not None
            and before < last_ns
        ):
            failures.append("nominal event sequence/clock bracket invalid")
        sequence, last_ns = row["record_seq"], after
        if row["event"] == "OPERATION":
            source = row["source"]
            key = (source["operation_id"], source["phase"])
            if key in operations:
                failures.append("duplicate operation boundary")
            operations[key] = row
            if source["kind"] == "COMMAND" and source["phase"] == "END":
                original_commands.extend((source.get("result") or {}).get("command_records", []))
        elif row["event"] in {"ACTION_BEGIN", "ACTION_END"}:
            key = (row["action_ordinal"], row["event"])
            if key in actions:
                failures.append("duplicate original action boundary")
            actions[key] = row
        elif row["event"] == "TEACHER_ACTION":
            teacher_actions[row["action_ordinal"]] = row
        elif row["event"] == "ACTUATOR":
            step = row["source"]["physics_step"]
            if step in actuators:
                failures.append("duplicate pre-physics actuator source")
            actuators[step] = row
        elif row["event"] == "ACQUISITION_BEGIN":
            step = row["physics_step"]
            if step in acquisition_begins:
                failures.append("duplicate acquisition BEGIN")
            acquisition_begins[step] = row
        elif row["event"] == "ACQUISITION_END":
            if row["physics_step"] in acquisitions:
                failures.append("duplicate acquisition END")
            acquisitions[row["physics_step"]] = row
    if (
        summary["run_status"] != "COMPLETED_SINGLE_ATTEMPT"
        or terminal["operation_observer_failures"]
    ):
        failures.append("attempt or operation association remained partial")
    if summary["action_begins"] != summary["action_ends"]:
        failures.append("original action BEGIN/END count mismatch")
    if original_commands != terminal["commands"]:
        failures.append("original command source differs from terminal command journal")
    if report["allocated_steps"] != terminal["final_step"] + 1:
        failures.append("terminal and declared frame horizons differ")
    action_spans = {}
    for ordinal in range(1, summary["action_begins"] + 1):
        begin, end = actions.get((ordinal, "ACTION_BEGIN")), actions.get((ordinal, "ACTION_END"))
        teacher_action = teacher_actions.get(ordinal)
        if begin is None or end is None or teacher_action is None:
            failures.append(f"action {ordinal}: original/teacher span missing")
            continue
        start_step, end_step = begin["start_step"], end["end_step"]
        if (
            type(start_step) is not int
            or type(end_step) is not int
            or not 0 <= start_step <= end_step <= terminal["final_step"]
            or end["start_step"] != start_step
        ):
            failures.append(f"action {ordinal}: invalid original physical span")
        else:
            action_spans[ordinal] = (start_step, end_step)
        start, stop = begin["command_seq_start"], end["command_seq_end"]
        if (
            not 1 <= start <= stop <= len(terminal["commands"]) + 1
            or end["command_seq_start"] != start
        ):
            failures.append(f"action {ordinal}: half-open command span invalid")
        expected = {
            "start_step": begin["start_step"],
            "end_step": end["end_step"],
            "command_seq_start": start,
            "command_seq_end": stop,
        }
        if any(teacher_action["source"][key] != value for key, value in expected.items()):
            failures.append(f"action {ordinal}: teacher/original span mismatch")
        result = end.get("result")
        if result is None or end.get("error_type"):
            failures.append(f"action {ordinal}: original action did not return")
        else:
            start_utc, finish_utc = (
                datetime.fromisoformat(result["started_at"]),
                datetime.fromisoformat(result["finished_at"]),
            )
            if not (
                datetime.fromisoformat(begin["clock"]["utc"])
                <= start_utc
                <= finish_utc
                <= datetime.fromisoformat(end["clock"]["utc"])
            ):
                failures.append(f"action {ordinal}: original wall interval outside nominal wrapper")
    for step in range(report["allocated_steps"]):
        row = acquisitions.get(step)
        if row is None:
            failures.append(f"step {step}: missing saved acquisition association")
            continue
        begin = acquisition_begins.get(step)
        authoritative = index_ends.get(step, {})
        if not same_json(row["saved"], authoritative):
            failures.append(f"step {step}: saved acquisition differs from complete index END")
        identity = frame_identity(authoritative)
        if (
            not same_json(frame_identity(row), identity)
            or begin is None
            or not same_json(frame_identity(begin), identity)
            or not same_json(frame_identity(begin.get("physical_source", {})), identity)
        ):
            failures.append(f"step {step}: acquisition/raw physical identity mismatch")
        owners = [
            ordinal
            for ordinal, (start_step, end_step) in action_spans.items()
            if start_step < step <= end_step
        ]
        if len(owners) > 1 or row["action_ordinal"] != (owners[0] if owners else None):
            failures.append(f"step {step}: action ownership not unique or incorrectly bound")
        if (
            begin is None
            or begin["action_ordinal"] != row["action_ordinal"]
            or begin["clock"]["monotonic_after_ns"] > row["saved"]["monotonic_begin_ns"]
            or row["saved"]["monotonic_end_ns"] > row["clock"]["monotonic_before_ns"]
        ):
            failures.append(f"step {step}: acquisition BEGIN/END bracket invalid")
        if (
            not row["camera"]["state_unchanged"]
            or row["camera"]["before_state"] != row["camera"]["after_state"]
        ):
            failures.append(f"step {step}: measured state preservation invalid")
        for state in ("before_state", "after_state"):
            camera_identity = {
                "physics_step": row["camera"][state].get("physical_step"),
                "sim_time_s": row["camera"][state].get("sim_time_s"),
            }
            if not same_json(
                camera_identity, {key: identity[key] for key in ("physics_step", "sim_time_s")}
            ):
                failures.append(f"step {step}: camera measured step/time mismatch")
        if not (
            row["saved"]["monotonic_begin_ns"]
            <= row["camera"]["capture_monotonic_begin_ns"]
            <= row["camera"]["capture_monotonic_end_ns"]
            <= row["saved"]["monotonic_end_ns"]
        ):
            failures.append(f"step {step}: camera/raw capture clock interval mismatch")
        if step:
            physics = operations.get((row["physics_operation_id"], "END"))
            control = operations.get((row["control_operation_id"], "END"))
            physics_begin = operations.get((row["physics_operation_id"], "BEGIN"))
            control_begin = operations.get((row["control_operation_id"], "BEGIN"))
            # Source _build_actuator_observation identifies the upcoming step n.
            # CONTROL and PHYSICS BEGIN remain at n-1; PHYSICS END is n.
            actuator = actuators.get(step)
            if physics is not None:
                physical_source = (physics["source"].get("result") or {}).get("physics_state", {})
                if not same_json(frame_identity(physics["source"]), identity) or not same_json(
                    frame_identity(physical_source), identity
                ):
                    failures.append(f"step {step}: declared PHYSICS source identity mismatch")
            if (
                physics is None
                or physics["source"]["kind"] != "PHYSICS"
                or physics["source"]["physics_step"] != step
                or control is None
                or control["source"]["kind"] != "CONTROL"
                or control["source"]["physics_step"] != step - 1
                or physics_begin is None
                or control_begin is None
                or begin is None
                or actuator is None
            ):
                failures.append(f"step {step}: CONTROL/PHYSICS association mismatch")
            elif not (
                control_begin["clock"]["monotonic_after_ns"]
                <= control["clock"]["monotonic_before_ns"]
                <= actuator["clock"]["monotonic_before_ns"]
                <= physics_begin["clock"]["monotonic_before_ns"]
                <= physics["clock"]["monotonic_before_ns"]
                <= begin["clock"]["monotonic_before_ns"]
                and actuator["control_operation_id"] == row["control_operation_id"]
            ):
                failures.append(
                    f"step {step}: CONTROL/actuator/PHYSICS/acquisition clocks mismatch"
                )
        ordinal = row["action_ordinal"]
        if ordinal is not None:
            begin, end = (
                actions.get((ordinal, "ACTION_BEGIN")),
                actions.get((ordinal, "ACTION_END")),
            )
            if (
                begin is None
                or end is None
                or not begin["start_step"] < step <= end["end_step"]
                or not begin["clock"]["monotonic_after_ns"]
                <= row["saved"]["monotonic_begin_ns"]
                <= row["clock"]["monotonic_after_ns"]
                <= end["clock"]["monotonic_before_ns"]
            ):
                failures.append(f"step {step}: original action span mismatch")
    report.update(
        reader_version=READER_VERSION,
        base_verifier_source_sha256=BASE_VERIFIER_SOURCE_SHA256,
        input_directory=str(directory),
        actuator_step_domain="UPCOMING_PHYSICS_STEP_N",
        integrity_status="VERIFIED" if not failures else "INCOMPLETE_OR_INVALID",
        association_scope="EXCLUDED_TEACHER_TRACE_NOT_NATIVE_RAW_V3",
        nominal_event_count=sequence,
        source_authenticity="UNKNOWN",
        original_action_begins=summary["action_begins"],
        original_action_ends=summary["action_ends"],
    )
    with (output_directory / "offline-verification.json").open("x") as stream:
        stream.write(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--decode", action="store_true")
    arguments = parser.parse_args()
    result = verify_attempt(
        arguments.input, output_directory=arguments.output, decode=arguments.decode
    )
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["integrity_status"] == "VERIFIED" else 1)
