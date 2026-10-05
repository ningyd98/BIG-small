"""Offline integrity/visibility replay and CPU-only script integration checks."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import importlib.util
import json
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker

HERE = Path(__file__).resolve().parent
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


def verify_attempt(directory: Path, *, decode=False):
    module = runner_api()
    summary = json.loads((directory / "summary.json").read_text())
    terminal = json.loads((directory / "terminal.json").read_text())
    report = verify_series(
        directory / "whole-step", decode=decode, output=directory / "offline-observations.jsonl"
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
    for row in module.read_jsonl_gzip(directory / "nominal-journal.jsonl.gz"):
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
            actuator = actuators.get(step - 1)
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
        integrity_status="VERIFIED" if not failures else "INCOMPLETE_OR_INVALID",
        association_scope="EXCLUDED_TEACHER_TRACE_NOT_NATIVE_RAW_V3",
        nominal_event_count=sequence,
        source_authenticity="UNKNOWN",
        original_action_begins=summary["action_begins"],
        original_action_ends=summary["action_ends"],
    )
    with (directory / "offline-verification.json").open("x") as stream:
        stream.write(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return report


def runner_api():
    path = HERE / "run_once.py"
    assert path.exists(), "artifact-local one-attempt runner is missing"
    spec = importlib.util.spec_from_file_location("ced_continuous_runner", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_same_scene_camera_controller_config_and_new_excluded_group():
    module = runner_api()
    scene, config = module.specification()
    prior_scene, prior_config = module.prior_specification()
    assert scene.scene_hash == prior_scene.scene_hash
    assert scene.scene_parameters == prior_scene.scene_parameters
    assert scene.group_id != prior_scene.group_id
    assert config == prior_config
    assert (config.camera_width, config.camera_height) == (640, 480)
    assert config.physics_dt_s < 0.005


def test_original_action_delegates_once_and_restores_on_interruption(tmp_path):
    from types import SimpleNamespace

    import pytest

    module = runner_api()
    calls = []

    class Robot:
        def move_above(self, *args, **kwargs):
            calls.append((args, kwargs))
            raise KeyboardInterrupt("bounded interruption")

    for name in module.ROBOT_ACTIONS:
        if name != "move_above":
            setattr(Robot, name, Robot.move_above)
    robot = Robot()
    backend = SimpleNamespace(
        total_physics_steps=0,
        command_records=[],
        _episode_id="episode",
        get_sim_time=lambda: 0.0,
        _operation_observer_failures=[],
    )
    teacher = SimpleNamespace(_dwell=lambda *args: None)
    original_dwell = teacher._dwell
    journal = module.NominalJournal(tmp_path / "journal.jsonl.gz")
    tracker = module.ActionTracker(backend, journal)
    with pytest.raises(KeyboardInterrupt, match="bounded interruption"):
        with module.wrap_original_actions(robot, teacher, tracker):
            robot.move_above("object", timeout_ms=8000)
    assert calls == [(("object",), {"timeout_ms": 8000})]
    assert "move_above" not in robot.__dict__
    assert teacher._dwell is original_dwell
    assert tracker.begins == tracker.ends == 1
    assert tracker.current is None
    journal.close()
    events = list(module.read_jsonl_gzip(tmp_path / "journal.jsonl.gz"))
    assert [r["event"] for r in events] == ["ACTION_BEGIN", "ACTION_END"]
    assert events[-1]["error_type"] == "KeyboardInterrupt"
    assert events[-1]["result"] is None


def fake_backend(mutation=None):
    from datetime import UTC, datetime
    from types import SimpleNamespace

    import numpy as np

    from cloud_edge_robot_arm.simulation.models import SensorFrame

    backend = SimpleNamespace(
        _data=SimpleNamespace(time=0.0, qpos=np.zeros(2), ctrl=np.zeros(2)),
        _model=SimpleNamespace(body_mass=np.ones(2), opt=SimpleNamespace(timestep=1 / 240)),
        _rng=np.random.default_rng(0),
        _sensor_frame=object(),
        _sensor_noise_std_m=0.0,
        _scenario=SimpleNamespace(scenario_id="scene"),
        _episode_id="episode",
        _target_positions=np.zeros(2),
        _pending_joint_targets=[],
        _gripper_open=True,
        _estop_engaged=False,
        _actuator_delay_steps=0,
        total_physics_steps=0,
        command_records=[],
        _operation_observer_failures=[],
    )

    class Camera:
        def _capture(self, data, **kwargs):
            assert kwargs["include_instances"] is False
            assert kwargs["noise_std_m"] == 0.0
            if mutation == "rng":
                backend._rng.random()
            elif mutation == "data":
                data.qpos[0] += 1
            elif mutation == "control":
                backend._target_positions[0] += 1
            elif mutation == "model":
                backend._model.body_mass[0] += 1
            elif mutation == "cache":
                backend._sensor_frame = object()
            frame = SensorFrame(
                frame_id=f"frame-{backend.total_physics_steps}",
                sim_time_s=data.time,
                width=2,
                height=2,
                rgb=bytes([90, 110, 130]) * 4,
                depth=(0.5, 0.6, 0.7, 0.8),
                intrinsics=(2.0, 2.0, 0.5, 0.5),
                camera_to_world=(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
                captured_at=datetime.now(UTC),
                episode_id="episode",
                scene_id="scene",
                calibration_version="camera-calibration",
                valid_mask=b"\x01" * 4,
            )
            return frame, (), {}, ("a" * 64,) * 2

    backend._camera = Camera()
    return backend


def test_extra_rgbd_preserves_data_model_control_rng_and_cache(tmp_path):
    module = runner_api()
    backend = fake_backend()
    journal = module.NominalJournal(tmp_path / "journal.jsonl.gz")
    adapter = module.CaptureAdapter(backend, journal)
    before = module.capture_state(backend)
    observation, hashes = adapter()
    assert before == module.capture_state(backend)
    assert hashes == ("a" * 64,) * 2
    assert observation.episode_id == "episode"
    assert adapter.last_capture["state_unchanged"] is True
    journal.close()


def test_extra_rgbd_rejects_each_measured_state_mutation(tmp_path):
    import pytest

    module = runner_api()
    for mutation in ("rng", "data", "control", "model", "cache"):
        journal = module.NominalJournal(tmp_path / f"{mutation}.jsonl.gz")
        adapter = module.CaptureAdapter(fake_backend(mutation), journal)
        with pytest.raises(RuntimeError, match="capture changed"):
            adapter()
        journal.close()


def test_extra_rgbd_rejects_nonzero_noise_before_camera(tmp_path):
    import pytest

    module = runner_api()
    backend = fake_backend()
    backend._sensor_noise_std_m = 0.001
    journal = module.NominalJournal(tmp_path / "journal.jsonl.gz")
    with pytest.raises(RuntimeError, match="zero noise"):
        module.CaptureAdapter(backend, journal)()
    journal.close()


def test_nominal_journal_failure_and_backend_swallowed_failure_abort(tmp_path):
    import pytest

    module = runner_api()
    journal = module.NominalJournal(tmp_path / "journal.jsonl.gz")
    backend = fake_backend()
    backend._operation_observer_failures.append({"error": "retained operation failure"})
    with pytest.raises(RuntimeError, match="operation observer"):
        journal.ensure(backend)
    journal.close()


def test_offline_archive_verifies_complete_horizon_and_detects_tamper(tmp_path):
    import gzip
    import json

    from cloud_edge_robot_arm.research.step_rgbd import StepRGBDRecorder

    module = runner_api()
    backend = fake_backend()
    journal = module.NominalJournal(tmp_path / "journal.jsonl.gz")
    adapter = module.CaptureAdapter(backend, journal)
    recorder = StepRGBDRecorder(tmp_path / "series", adapter, episode_id="episode")
    recorder.record_step(episode_id="episode", physics_step=0, sim_time_s=0.0)
    recorder.finish(final_step=0, final_sim_time_s=0.0)
    journal.close()
    result = verify_series(tmp_path / "series", decode=False)
    assert result["integrity_status"] == "VERIFIED"
    assert result["verified_frames"] == result["allocated_steps"] == 1
    assert result["formal_accepted"] is False
    payload = tmp_path / "series/frames/0000000.json.gz"
    changed = json.loads(gzip.decompress(payload.read_bytes()))
    changed["episode_id"] = "wrong"
    payload.write_bytes(gzip.compress(json.dumps(changed).encode(), mtime=0))
    result = verify_series(tmp_path / "series", decode=False)
    assert result["integrity_status"] == "INCOMPLETE_OR_INVALID"
    assert result["verified_frames"] == 0
    assert result["allocated_steps"] == 1
    assert result["failures"]


def synthetic_attempt(directory, corruption=None):
    """Small software-only trace; no actual-source or execution authenticity."""
    from datetime import UTC, datetime

    from cloud_edge_robot_arm.research.step_rgbd import StepRGBDRecorder

    module = runner_api()
    backend = fake_backend()
    journal = module.NominalJournal(directory / "nominal-journal.jsonl.gz")
    adapter = module.CaptureAdapter(backend, journal)
    recorder = StepRGBDRecorder(directory / "whole-step", adapter, episode_id="episode")
    for step in range(3):
        if step == 1:
            journal.emit("ACTION_BEGIN", action_ordinal=1, start_step=0, command_seq_start=1)
            action_started = datetime.now(UTC).isoformat()
        if step:
            control_id, physics_id = step * 2 - 1, step * 2
            source = {
                "operation_id": control_id,
                "phase": "BEGIN",
                "kind": "CONTROL",
                "physics_step": step - 1,
                "episode_id": "episode",
                "sim_time_s": backend._data.time,
            }
            journal.emit("OPERATION", source=source)
            journal.emit("OPERATION", source={**source, "phase": "END"})
            journal.emit(
                "ACTUATOR", control_operation_id=control_id, source={"physics_step": step - 1}
            )
            source = {
                "operation_id": physics_id,
                "phase": "BEGIN",
                "kind": "PHYSICS",
                "physics_step": step - 1,
                "episode_id": "episode",
                "sim_time_s": backend._data.time,
            }
            journal.emit("OPERATION", source=source)
            backend.total_physics_steps = step
            backend._data.time = step / 240
            journal.emit(
                "OPERATION",
                source={
                    **source,
                    "phase": "END",
                    "physics_step": step,
                    "sim_time_s": backend._data.time,
                    "result": {
                        "physics_state": {
                            "episode_id": "episode",
                            "physics_step": step,
                            "sim_time_s": backend._data.time,
                        }
                    },
                },
            )
        else:
            control_id = physics_id = None
        if corruption != "missing_acquisition_begin" or step != 1:
            journal.emit(
                "ACQUISITION_BEGIN",
                physics_step=step,
                episode_id="episode",
                sim_time_s=backend._data.time,
                physical_source={
                    "episode_id": "episode",
                    "physics_step": step,
                    "sim_time_s": backend._data.time,
                },
                action_ordinal=1 if step else None,
                control_operation_id=control_id,
                physics_operation_id=physics_id,
            )
        row = recorder.record_step(
            episode_id="episode", physics_step=step, sim_time_s=backend._data.time
        )
        journal.emit(
            "ACQUISITION_END",
            physics_step=step,
            episode_id="episode",
            sim_time_s=backend._data.time,
            action_ordinal=1 if step else None,
            control_operation_id=control_id,
            physics_operation_id=physics_id,
            saved=row,
            camera=adapter.last_capture,
        )
    journal.emit(
        "ACTION_END",
        action_ordinal=1,
        start_step=0,
        end_step=2,
        command_seq_start=1,
        command_seq_end=2 if corruption == "command_span" else 1,
        error_type=None,
        result={"started_at": action_started, "finished_at": datetime.now(UTC).isoformat()},
    )
    journal.emit(
        "TEACHER_ACTION",
        action_ordinal=1,
        source={"start_step": 0, "end_step": 2, "command_seq_start": 1, "command_seq_end": 1},
    )
    recorder.finish(final_step=2, final_sim_time_s=2 / 240)
    journal.close()
    (directory / "summary.json").write_text(
        json.dumps({"run_status": "COMPLETED_SINGLE_ATTEMPT", "action_begins": 1, "action_ends": 1})
    )
    (directory / "terminal.json").write_text(
        json.dumps(
            {
                "operation_observer_failures": [],
                "commands": [],
                "final_step": 2,
                "final_sim_time_s": 2 / 240,
                "episode_id": "episode",
            }
        )
    )
    if corruption == "physics_begin":
        path = directory / "nominal-journal.jsonl.gz"
        rows = list(module.read_jsonl_gzip(path))
        rows = [
            row
            for row in rows
            if not (
                row["event"] == "OPERATION"
                and row["source"]["kind"] == "PHYSICS"
                and row["source"]["phase"] == "BEGIN"
            )
        ]
        for ordinal, row in enumerate(rows, 1):
            row["record_seq"] = ordinal
        path.write_bytes(
            gzip.compress(b"".join(json.dumps(row).encode() + b"\n" for row in rows), mtime=0)
        )


def test_complete_software_trace_has_exact_nominal_associations(tmp_path):
    synthetic_attempt(tmp_path)
    result = verify_attempt(tmp_path)
    assert result["integrity_status"] == "VERIFIED"
    assert result["source_authenticity"] == "UNKNOWN"
    assert result["formal_accepted"] is False


def test_missing_begin_and_bad_half_open_command_span_cannot_verify(tmp_path):
    accepted = []
    for corruption in ("missing_acquisition_begin", "physics_begin", "command_span"):
        directory = tmp_path / corruption
        directory.mkdir()
        synthetic_attempt(directory, corruption)
        result = verify_attempt(directory)
        if result["integrity_status"] != "INCOMPLETE_OR_INVALID":
            accepted.append(corruption)
        assert result["allocated_steps"] == 3
    assert not accepted, accepted


def test_independent_p2_saved_terminal_and_unique_action_bindings(tmp_path):
    import copy

    accepted = []
    cases = (
        "saved_payload_identity",
        "terminal_episode",
        "terminal_time",
        "action_ownership",
        "acquisition_episode",
        "camera_step",
        "final_physics_time",
        "overlapping_actions",
    )
    for kind in cases:
        directory = tmp_path / kind
        directory.mkdir()
        synthetic_attempt(directory)
        if kind.startswith("terminal_"):
            path = directory / "terminal.json"
            terminal = json.loads(path.read_text())
            key, value = (
                ("episode_id", "unrelated-episode")
                if kind == "terminal_episode"
                else ("final_sim_time_s", 9.0)
            )
            terminal[key] = value
            path.write_text(json.dumps(terminal))
        else:
            path = directory / "nominal-journal.jsonl.gz"
            rows = list(runner_api().read_jsonl_gzip(path))
            rewritten = []
            for row in rows:
                if row["event"] == "ACQUISITION_END" and row["physics_step"] == 1:
                    if kind == "saved_payload_identity":
                        row["saved"].update(
                            observation_id="unrelated-frame",
                            observation_checksum_sha256="b" * 64,
                            file="frames/unrelated.json.gz",
                        )
                    elif kind == "camera_step":
                        for state in ("before_state", "after_state"):
                            row["camera"][state]["physical_step"] = 99
                if (
                    row["event"] in {"ACQUISITION_BEGIN", "ACQUISITION_END"}
                    and row["physics_step"] == 1
                ):
                    if kind == "action_ownership":
                        row["action_ordinal"] = None
                    elif kind == "acquisition_episode":
                        row["episode_id"] = "unrelated-episode"
                if (
                    kind == "final_physics_time"
                    and row["event"] == "OPERATION"
                    and row["source"]["kind"] == "PHYSICS"
                    and row["source"]["phase"] == "END"
                    and row["source"]["physics_step"] == 2
                ):
                    row["source"]["result"]["physics_state"]["sim_time_s"] = 9.0
                rewritten.append(row)
                if kind == "overlapping_actions" and row["event"] in {
                    "ACTION_BEGIN",
                    "ACTION_END",
                    "TEACHER_ACTION",
                }:
                    duplicate = copy.deepcopy(row)
                    duplicate["action_ordinal"] = 2
                    duplicate["clock"]["monotonic_before_ns"] = duplicate["clock"][
                        "monotonic_after_ns"
                    ]
                    rewritten.append(duplicate)
            for sequence, row in enumerate(rewritten, 1):
                row["record_seq"] = sequence
            path.write_bytes(
                gzip.compress(
                    b"".join(json.dumps(row).encode() + b"\n" for row in rewritten), mtime=0
                )
            )
            if kind == "overlapping_actions":
                summary_path = directory / "summary.json"
                summary = json.loads(summary_path.read_text())
                summary.update(action_begins=2, action_ends=2)
                summary_path.write_text(json.dumps(summary))
        result = verify_attempt(directory, decode=False)
        if result["integrity_status"] != "INCOMPLETE_OR_INVALID":
            accepted.append(kind)
        assert result["allocated_steps"] == result["verified_frames"] == 3
        assert result["source_authenticity"] == "UNKNOWN"
        assert result["formal_accepted"] is False
    assert not accepted, accepted


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt", type=Path, required=True)
    parser.add_argument("--decode", action="store_true")
    arguments = parser.parse_args()
    result = verify_attempt(arguments.attempt, decode=arguments.decode)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["integrity_status"] == "VERIFIED" else 1)
