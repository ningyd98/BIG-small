"""V3 SOFTWARE_ONLY lifecycle/source/guard/association tests; no actual calls."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def runner():
    baseline = os.environ.get("BIGSMALL_V3_RED_BASELINE")
    return load(HERE / (baseline or "run_once.py"), "custom_v3_cpu_runner")


class FakeJournal:
    def __init__(self, fault=None):
        self.fault = fault
        self.events = []
        self.last_control = self.last_physics = None

    def ensure(self, backend):
        pass

    def emit(self, event, **payload):
        if event == self.fault or isinstance(self.fault, set) and event in self.fault:
            raise OSError("journal " + event)
        row = {"event": event, **payload}
        self.events.append(row)
        return row


class FakeSeries:
    def __init__(self, error=None):
        self.error = error
        self.calls = self.saved = 0

    def record_step(self, **identity):
        self.calls += 1
        if self.error is not None:
            raise self.error
        self.saved += 1
        return {"event": "END", **identity}


def coordinator(runner, fault=None, error=None):
    backend = SimpleNamespace(command_records=[])
    journal, series = FakeJournal(fault), FakeSeries(error)
    adapter = SimpleNamespace(last_capture=None)
    tracker = SimpleNamespace(current=None)
    owner = runner.AcquisitionCoordinator(backend, journal, series, tracker, adapter)
    return owner, journal, series


def step(n=0):
    return SimpleNamespace(episode_id="cpu-episode", physics_step=n, sim_time_s=n / 240)


def test_BEGIN_failure_keeps_allocation_and_marks_failed_before_camera(runner):
    owner, journal, series = coordinator(runner, "ACQUISITION_BEGIN")
    with pytest.raises(OSError, match="ACQUISITION_BEGIN"):
        owner.record(step())
    assert (owner.allocated, owner.completed, owner.failed, series.calls) == (1, 0, 1, 0)
    assert [r["event"] for r in journal.events] == ["ACQUISITION_FAILED"]


def test_END_failure_preserves_saved_frame_without_completed_double_count(runner):
    owner, journal, series = coordinator(runner, "ACQUISITION_END")
    with pytest.raises(OSError, match="ACQUISITION_END"):
        owner.record(step())
    assert (owner.allocated, owner.completed, owner.failed, series.calls, series.saved) == (
        1,
        0,
        1,
        1,
        1,
    )


def test_FAILED_publication_does_not_mask_original_error(runner):
    original = ValueError("original capture interruption")
    owner, journal, series = coordinator(runner, "ACQUISITION_FAILED", original)
    with pytest.raises(ValueError, match="original capture interruption") as caught:
        owner.record(step())
    assert caught.value is original
    assert owner.failure_journal_errors
    assert (owner.allocated, owner.completed, owner.failed, series.calls) == (1, 0, 1, 1)


@pytest.mark.parametrize("failure_step", [0, 1, 3])
def test_interruption_preserves_every_prior_step_and_failed_denominator(runner, failure_step):
    owner, journal, series = coordinator(runner)
    for n in range(failure_step):
        owner.record(step(n))
    series.error = ValueError("no retry")
    with pytest.raises(ValueError, match="no retry"):
        owner.record(step(failure_step))
    assert (owner.allocated, owner.completed, owner.failed) == (failure_step + 1, failure_step, 1)
    assert series.saved == failure_step
    with pytest.raises(RuntimeError, match="stopped"):
        owner.record(step(failure_step))
    assert series.calls == failure_step + 1


def action_tracker(runner, fault=None):
    backend = SimpleNamespace(
        total_physics_steps=0,
        command_records=[],
        _episode_id="cpu-episode",
        get_sim_time=lambda: 0.0,
    )
    journal = FakeJournal(fault)
    return runner.ActionTracker(backend, journal), journal


def test_action_BEGIN_failure_retains_allocated_attempt_without_delegate(runner):
    tracker, journal = action_tracker(runner, "ACTION_BEGIN")
    calls = []
    with pytest.raises(OSError, match="ACTION_BEGIN"):
        tracker.invoke("LIFT", lambda: calls.append(1))
    assert calls == []
    assert (tracker.begins, tracker.ends) == (1, 0)
    assert (tracker.failed, tracker.delegated) == (1, 0)
    assert tracker.current is None


def test_action_END_failure_does_not_count_completed_end_or_repeat_delegate(runner):
    tracker, journal = action_tracker(runner, "ACTION_END")
    calls = []
    with pytest.raises(OSError, match="ACTION_END"):
        tracker.invoke("LIFT", lambda: calls.append(1))
    assert calls == [1]
    assert (tracker.begins, tracker.ends) == (1, 0)
    assert (tracker.failed, tracker.delegated) == (1, 1)
    assert tracker.current is None
    with pytest.raises(RuntimeError, match="stopped"):
        tracker.invoke("LIFT", lambda: calls.append(1))
    assert calls == [1]


def test_action_FAILED_publication_preserves_original_exception(runner):
    tracker, journal = action_tracker(runner, {"ACTION_END", "ACTION_FAILED"})
    original = ValueError("original action interruption")

    def fail():
        raise original

    with pytest.raises(ValueError) as caught:
        tracker.invoke("LIFT", fail)
    assert caught.value is original
    assert getattr(original, "__notes__", []), (
        "publication failure must remain attached to original"
    )
    assert tracker.failure_journal_errors
    assert (tracker.begins, tracker.ends) == (1, 0)
    assert (tracker.failed, tracker.delegated) == (1, 1)
    assert tracker.current is None


@pytest.fixture
def reader():
    path = (
        HERE.parent / "t7b-continuous-visibility-v2/verify_offline.py"
        if os.environ.get("BIGSMALL_V3_READER_RED_BASELINE")
        else HERE / "verify_offline.py"
    )
    return load(path, "custom_v3_cpu_reader")


def guard_fixture(runner):
    helpers = load(runner.ROOT / "tests/test_mujoco_state_guard.py", "frozen_guard_fake_helpers")
    api = runner.state_guard
    header_root = runner.ROOT / ".venv/lib/python3.12/site-packages/mujoco/include/mujoco"
    contract = api.MujocoStateContract(
        (header_root / "mjxmacro.h").read_bytes(),
        (header_root / "mjdata.h").read_bytes(),
        api.BINDING_SHA256,
        "3.3.7",
    )
    model = SimpleNamespace(nv=3, nC=5, ntendon=0)
    data = helpers.FakeData(model)
    return api, contract, model, data


def guarded_camera(runner, contract, model, data, step_number, sim_time):
    api = runner.state_guard
    protected = {key: "a" * 64 for key in api._PROTECTED_KEYS if key.endswith("sha256")}
    protected.update(
        sensor_cache_object_id=11,
        camera_object_id=12,
        physical_step=step_number,
        command_count=0,
        sensor_noise_std_m=0.0,
        sim_time_s=sim_time,
    )
    arrays = api.snapshot_data_arrays(data, model, contract=contract, runtime_version="3.3.7")
    guarded = api.attach_protected_state(arrays, protected)
    state = {**protected, "data_arrays_sha256": arrays.digest}
    return dict(
        guard_protocol=runner.GUARD_PROTOCOL,
        camera_call_started=True,
        before_guard=runner.plain(guarded),
        after_guard=runner.plain(guarded),
        before_state=state,
        after_state=copy.deepcopy(state),
        state_unchanged=True,
        pass_state_hashes=[protected["physics_state_sha256"]] * 2,
    )


def v3_attempt(source, runner):
    """Three bounded synthetic steps; no MuJoCo model, reset, physics or renderer."""
    old = load(HERE.parent / "t7b-continuous-visibility-v2/test_cpu.py", "v2_fake_trace_helpers")
    old.upcoming_attempt(source)
    api, contract, model, data = guard_fixture(runner)
    records = old.rows(source)
    for row in records:
        if row["event"] == "ACQUISITION_END":
            camera = guarded_camera(
                runner, contract, model, data, row["physics_step"], row["sim_time_s"]
            )
            for key in ("capture_monotonic_begin_ns", "capture_monotonic_end_ns"):
                camera[key] = row["camera"][key]
            row["camera"] = camera
            # Full guarded physics digest must agree with saved two-pass digest.
            camera["before_state"]["physics_state_sha256"] = row["saved"]["pass_state_hashes"][0]
            camera["after_state"]["physics_state_sha256"] = row["saved"]["pass_state_hashes"][0]
            for key in ("before_guard", "after_guard"):
                protected = json.loads(camera[key]["protected_json"])
                protected["physics_state_sha256"] = row["saved"]["pass_state_hashes"][0]
                arrays = api.snapshot_data_arrays(
                    data, model, contract=contract, runtime_version="3.3.7"
                )
                camera[key] = runner.plain(api.attach_protected_state(arrays, protected))
            camera["pass_state_hashes"] = row["saved"]["pass_state_hashes"]
    old.write_rows(source, records)
    # Pin small software-only fixture source/archive bytes, not an actual source claim.
    fixture_root = source.parent / "fake-source"
    fixture_root.mkdir()
    archive = source.parent / "fake-archive"
    archive.mkdir()
    guard_name = "src/cloud_edge_robot_arm/research/mujoco_state_guard.py"
    members = {guard_name: (runner.ROOT / guard_name).read_bytes()}
    members.update(
        {f"fixture_{i}.py": b"fixture software only " + str(i).encode() for i in range(31)}
    )
    manifest, index = {}, {}
    for i, (name, raw) in enumerate(members.items()):
        path = fixture_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        (archive / str(i)).write_bytes(raw)
        manifest[name] = hashlib.sha256(raw).hexdigest()
        index[name] = {"sha256": manifest[name], "bytes": len(raw), "archive": str(i)}
    manifest_path, index_path = (
        source.parent / "execution-source-hashes.json",
        source.parent / "execution-archive-index.json",
    )
    manifest_path.write_text(json.dumps(manifest))
    index_path.write_text(json.dumps(index))
    header_root = runner.ROOT / ".venv/lib/python3.12/site-packages/mujoco/include/mujoco"
    header = dict(
        protocol=runner.PROTOCOL,
        guard_protocol=runner.GUARD_PROTOCOL,
        raw_v3_status="CUSTOM_PROTOCOL_NOT_RAW_V3",
        source_authenticity="UNKNOWN",
        independent_calibration_group=False,
        source_root=str(fixture_root),
        archive_root=str(archive),
        source_manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        source_archive_index_sha256=hashlib.sha256(index_path.read_bytes()).hexdigest(),
        source_count=len(manifest),
        guard_core_sha256=manifest[guard_name],
        guard_headers={name: str(header_root / name) for name in ("mjxmacro.h", "mjdata.h")},
        guard_binding_sha256=api.BINDING_SHA256,
        environment={"mujoco_version": "3.3.7", "files": {}},
        config={"camera_width": 2, "camera_height": 2},
    )
    header_path = source / "execution-header.json"
    header_path.write_text(json.dumps(header))
    summary_path = source / "summary.json"
    summary = json.loads(summary_path.read_text())
    summary.update(
        protocol=runner.PROTOCOL,
        raw_v3_status="CUSTOM_PROTOCOL_NOT_RAW_V3",
        execution_header_sha256=hashlib.sha256(header_path.read_bytes()).hexdigest(),
        acquisition_allocated=3,
        acquisition_completed=3,
        acquisition_failed=0,
        whole_step_capture_calls=3,
        acquisition_failure_journal_errors=[],
        action_failed=0,
        action_delegated=1,
        action_failure_journal_errors=[],
        nominal_journal_failure=None,
    )
    summary_path.write_text(json.dumps(summary))
    return old


def test_complete_custom_trace_verifies_without_source_or_native_promotion(
    tmp_path, runner, reader
):
    source = tmp_path / "input"
    source.mkdir()
    old = v3_attempt(source, runner)
    before = old.hashes(source)
    result = reader.verify_attempt(source, output_directory=tmp_path / "output", decode=False)
    assert result["integrity_status"] == "VERIFIED", result["failures"]
    assert old.hashes(source) == before
    old.assert_authority_closed(result)


@pytest.mark.parametrize(
    "kind",
    ["missing", "active", "status", "inventory", "descriptor", "protected", "bridge", "pass_hash"],
)
def test_full_guard_tamper_cannot_verify_custom_trace(tmp_path, runner, reader, kind):
    source = tmp_path / "input"
    source.mkdir()
    old = v3_attempt(source, runner)
    records = old.rows(source)
    camera = next(
        row["camera"]
        for row in records
        if row["event"] == "ACQUISITION_END" and row["physics_step"] == 1
    )
    if kind == "missing":
        camera.pop("before_guard")
    elif kind == "active":
        camera["after_guard"]["arrays"]["fields"][-1]["byte_sha256"] = "b" * 64
    elif kind == "status":
        field = camera["after_guard"]["arrays"]["fields"][-1]
        field.update(status="UNSUPPORTED_NULL_ALLOCATION", storage="OWNING", byte_sha256=None)
    elif kind == "inventory":
        camera["after_guard"]["arrays"]["fields"].pop()
    elif kind == "descriptor":
        camera["after_guard"]["arrays"]["fields"][-1]["dtype_descr_json"] = "0"
    elif kind == "protected":
        camera["after_guard"]["protected_json"] = camera["after_guard"]["protected_json"].replace(
            '"command_count":0', '"command_count":1'
        )
    elif kind == "bridge":
        for key in ("before_state", "after_state"):
            camera[key]["rng_state_sha256"] = "b" * 64
    else:
        camera["pass_state_hashes"] = ["b" * 64] * 2
    old.write_rows(source, records)
    result = reader.verify_attempt(source, output_directory=tmp_path / "output", decode=False)
    assert result["integrity_status"] == "INCOMPLETE_OR_INVALID"
    assert any("guarded acquisition invalid" in error for error in result["failures"]), result[
        "failures"
    ]
    old.assert_authority_closed(result)


@pytest.mark.parametrize(
    "kind",
    [
        "saved_identity",
        "episode",
        "time",
        "ownership",
        "camera_step",
        "capture_clock",
        "physics_time",
        "overlap",
        "missing_begin",
        "old_actuator",
    ],
)
def test_original_complete_associations_stay_strict(tmp_path, runner, reader, kind):
    source = tmp_path / "input"
    source.mkdir()
    old = v3_attempt(source, runner)
    records = old.rows(source)
    if kind in {"episode", "time"}:
        path = source / "terminal.json"
        terminal = json.loads(path.read_text())
        terminal["episode_id" if kind == "episode" else "final_sim_time_s"] = (
            "unrelated" if kind == "episode" else 9.0
        )
        path.write_text(json.dumps(terminal))
    else:
        updated = []
        for row in records:
            if (
                kind == "missing_begin"
                and row["event"] == "ACQUISITION_BEGIN"
                and row["physics_step"] == 1
            ):
                continue
            if kind == "old_actuator" and row["event"] == "ACTUATOR":
                row["source"]["physics_step"] -= 1
            if row["event"] == "ACQUISITION_END" and row["physics_step"] == 1:
                if kind == "saved_identity":
                    row["saved"].update(
                        observation_id="wrong",
                        observation_checksum_sha256="b" * 64,
                        file="frames/wrong.json.gz",
                    )
                elif kind == "camera_step":
                    for key in ("before_state", "after_state"):
                        row["camera"][key]["physical_step"] = 99
                elif kind == "capture_clock":
                    row["camera"]["capture_monotonic_end_ns"] = row["saved"]["monotonic_end_ns"] + 1
            if (
                kind == "ownership"
                and row["event"] in {"ACQUISITION_BEGIN", "ACQUISITION_END"}
                and row["physics_step"] == 1
            ):
                row["action_ordinal"] = None
            if (
                kind == "physics_time"
                and row["event"] == "OPERATION"
                and row["source"]["kind"] == "PHYSICS"
                and row["source"]["phase"] == "END"
                and row["source"]["physics_step"] == 2
            ):
                row["source"]["result"]["physics_state"]["sim_time_s"] = 9.0
            updated.append(row)
            if kind == "overlap" and row["event"] in {
                "ACTION_BEGIN",
                "ACTION_END",
                "TEACHER_ACTION",
            }:
                duplicate = copy.deepcopy(row)
                duplicate["action_ordinal"] = 2
                duplicate["clock"]["monotonic_before_ns"] = duplicate["clock"]["monotonic_after_ns"]
                updated.append(duplicate)
        old.write_rows(source, updated)
        if kind == "overlap":
            path = source / "summary.json"
            summary = json.loads(path.read_text())
            summary.update(action_begins=2, action_ends=2)
            path.write_text(json.dumps(summary))
    result = reader.verify_attempt(source, output_directory=tmp_path / "output", decode=False)
    assert result["integrity_status"] == "INCOMPLETE_OR_INVALID"
    assert result["allocated_steps"] == result["verified_frames"] == 3
    old.assert_authority_closed(result)


@pytest.mark.parametrize(
    "kind", ["source", "archive", "manifest", "index", "inventory", "header", "version", "core"]
)
def test_source_preflight_and_offline_pins_fail_closed(tmp_path, runner, reader, monkeypatch, kind):
    source = tmp_path / "input"
    source.mkdir()
    v3_attempt(source, runner)
    header_path = source / "execution-header.json"
    header = json.loads(header_path.read_text())
    monkeypatch.setattr(runner, "ROOT", Path(header["source_root"]))
    monkeypatch.setattr(runner, "HERE", Path(header["archive_root"]) / "unused")
    if kind in {"source", "archive"}:
        root = Path(header["source_root"] if kind == "source" else header["archive_root"])
        target = root / ("fixture_0.py" if kind == "source" else "1")
        target.write_bytes(b"changed source")
    elif kind in {"manifest", "index"}:
        name = (
            "execution-source-hashes.json" if kind == "manifest" else "execution-archive-index.json"
        )
        with (source.parent / name).open("a") as stream:
            stream.write(" ")
    elif kind == "header":
        header_path.write_text(header_path.read_text() + " ")
    else:
        if kind == "inventory":
            header["source_count"] = 31
        elif kind == "version":
            header["environment"]["mujoco_version"] = "3.4.0"
        else:
            header["guard_core_sha256"] = "b" * 64
        header_path.write_text(json.dumps(header))
        path = source / "summary.json"
        summary = json.loads(path.read_text())
        summary["execution_header_sha256"] = hashlib.sha256(header_path.read_bytes()).hexdigest()
        path.write_text(json.dumps(summary))
    if kind != "header":
        with pytest.raises((RuntimeError, runner.state_guard.StateGuardError)):
            runner.source_preflight(header, source.parent)
    result = reader.verify_attempt(source, output_directory=tmp_path / "output", decode=False)
    assert result["integrity_status"] == "INCOMPLETE_OR_INVALID"
    assert any("header/source preflight" in error for error in result["failures"])


def fake_adapter(runner, monkeypatch, mutation=None):
    api, contract, model, data = guard_fixture(runner)
    data.time = 0.0
    data.arrays.update(qvel=np.ones(2).view(), act=np.zeros(0).view(), ctrl=np.ones(2).view())
    data.changing = {"iM", "dof_island"}
    backend = SimpleNamespace(
        _model=model,
        _data=data,
        _mujoco=SimpleNamespace(__version__="3.3.7", MjData=type(data), MjModel=type(model)),
        _target_positions={},
        _pending_joint_targets={},
        _gripper_open=True,
        _estop_engaged=False,
        _actuator_delay_steps=0,
        _rng=np.random.default_rng(0),
        _sensor_frame=None,
        total_physics_steps=0,
        command_records=[],
        _sensor_noise_std_m=0.0,
        _scenario=SimpleNamespace(scenario_id="cpu-scene"),
        _episode_id="cpu-episode",
    )
    original_camera = runner.MuJoCoRGBDCamera

    class FakeCamera:
        _physics_state_hash = staticmethod(original_camera._physics_state_hash)

    monkeypatch.setattr(runner, "MuJoCoRGBDCamera", FakeCamera)
    model.camera = lambda name: SimpleNamespace(id=7)
    camera = FakeCamera()
    camera.calls = 0
    camera._model, camera._mujoco = model, backend._mujoco
    camera._width, camera._height, camera._camera_id = 640, 480, 7
    camera._renderer = object()

    def capture(supplied, **kwargs):
        camera.calls += 1
        assert supplied is data and kwargs["include_instances"] is False
        assert kwargs["rng"] is backend._rng and kwargs["noise_std_m"] == 0.0
        physical = runner.MuJoCoRGBDCamera._physics_state_hash(data)
        if mutation:
            mutation(data, backend)
        return SimpleNamespace(latency_ms=0.1), (), {}, (physical, physical)

    camera._capture = capture
    backend._camera = camera
    monkeypatch.setattr(
        runner, "observation_from_sensor_frame", lambda frame, source: "cpu-observation"
    )
    return runner.CaptureAdapter(backend, FakeJournal(), contract), data, backend, camera


def test_same_camera_capture_ignores_only_legal_allocation_bytes_and_delegates_once(
    runner, monkeypatch
):
    adapter, data, backend, camera = fake_adapter(runner, monkeypatch)
    value, hashes = adapter()
    assert value == "cpu-observation" and len(hashes) == 2
    assert (adapter.allocated, adapter.calls, camera.calls) == (1, 1, 1)
    assert adapter.last_capture["state_unchanged"]
    assert data.reads["iM"] == data.reads["dof_island"] == 2
    records = adapter.last_capture["before_guard"]["arrays"]["fields"]
    assert any(r["name"] == "iM" and r["status"] == "UNSUPPORTED_NULL_ALLOCATION" for r in records)


@pytest.mark.parametrize(
    "kind", ["active", "support", "inventory", "owning", "rng", "control", "cache", "model", "step"]
)
def test_capture_side_effects_fail_closed_after_one_original_delegate(runner, monkeypatch, kind):
    def mutate(data, backend):
        if kind == "active":
            data.arrays["qpos"][0] += 1
        elif kind == "support":
            data.changing.clear()
            data.arrays["iM"] = data.arrays["iM"].view()
        elif kind == "inventory":
            data.arrays["extra_live"] = np.ones(2).view()
        elif kind == "owning":
            data.arrays["unknown_owned"] = np.ones(2)
        elif kind == "rng":
            backend._rng.random()
        elif kind == "control":
            backend._gripper_open = False
        elif kind == "cache":
            backend._sensor_frame = object()
        elif kind == "model":
            backend._model.extra_view = np.ones(2).view()
        else:
            backend.total_physics_steps += 1

    adapter, data, backend, camera = fake_adapter(runner, monkeypatch, mutate)
    with pytest.raises((RuntimeError, runner.state_guard.StateGuardError)):
        adapter()
    assert (adapter.allocated, adapter.calls, camera.calls) == (1, 1, 1)


@pytest.mark.parametrize("kind", ["noise", "camera", "version", "unknown_owned", "camera_width"])
def test_camera_preflight_refuses_before_original_delegate(runner, monkeypatch, kind):
    adapter, data, backend, camera = fake_adapter(runner, monkeypatch)
    if kind == "noise":
        backend._sensor_noise_std_m = 0.001
    elif kind == "camera":
        backend._camera = object()
    elif kind == "version":
        backend._mujoco.__version__ = "3.4.0"
    elif kind == "camera_width":
        camera._width = 320
    else:
        data.arrays["unproven_owned"] = np.ones(2)
    with pytest.raises((RuntimeError, runner.state_guard.StateGuardError)):
        adapter()
    assert (adapter.allocated, adapter.calls, camera.calls) == (1, 0, 0)
    assert adapter.last_capture is None


@pytest.mark.parametrize("interrupt", [False, True])
def test_bound_method_and_dwell_wrappers_restore_and_delegate_once(runner, interrupt):
    calls = []

    class Robot:
        pass

    for name in runner.ROBOT_ACTIONS:
        setattr(Robot, name, lambda self, _name=name: calls.append(_name))
    robot = Robot()

    def original_override():
        calls.append("existing override")

    robot.lift = original_override

    def original_dwell(*args, **kwargs):
        calls.append("dwell")

    teacher = SimpleNamespace(_dwell=original_dwell)
    tracker = SimpleNamespace(
        invoke=lambda kind, original, *args, **kwargs: original(*args, **kwargs)
    )
    try:
        with runner.wrap_original_actions(robot, teacher, tracker):
            robot.move_above()
            robot.lift()
            teacher._dwell()
            if interrupt:
                raise ValueError("stop")
    except ValueError:
        assert interrupt
    assert calls == ["move_above", "existing override", "dwell"]
    assert teacher._dwell is original_dwell and robot.lift is original_override
    assert set(robot.__dict__) == {"lift"}


def test_invalid_guard_blocks_decoder_and_preserves_input(tmp_path, runner, reader, monkeypatch):
    source = tmp_path / "input"
    source.mkdir()
    old = v3_attempt(source, runner)
    records = old.rows(source)
    next(r["camera"] for r in records if r["event"] == "ACQUISITION_END").pop("before_guard")
    old.write_rows(source, records)
    before = old.hashes(source)
    monkeypatch.setattr(
        reader, "detect_pose_marker", lambda *args: pytest.fail("invalid source decoded")
    )
    result = reader.verify_attempt(source, output_directory=tmp_path / "output", decode=True)
    assert result["decoder_blocked_by_integrity_failure"]
    assert old.hashes(source) == before


@pytest.mark.parametrize(
    "kind", ["enlarged_gap", "missing_frame", "extra_horizon", "terminal_time", "failed_index"]
)
def test_every_step_original_cadence_and_terminal_denominator_remain_required(
    tmp_path, runner, reader, kind
):
    source = tmp_path / "input"
    source.mkdir()
    old = v3_attempt(source, runner)
    series = source / "whole-step"
    path = series / "summary.json"
    summary = json.loads(path.read_text())
    if kind == "enlarged_gap":
        summary["original_max_sample_gap_s"] = 0.1
    elif kind == "extra_horizon":
        summary["allocated_steps"] = 4
    elif kind == "terminal_time":
        summary["final_sim_time_s"] = 9.0
    elif kind == "missing_frame":
        (series / "frames/0000002.json.gz").unlink()
    else:
        with (series / "index.jsonl").open("a") as stream:
            stream.write(json.dumps({"event": "FAILED", "physics_step": 2}) + "\n")
    path.write_text(json.dumps(summary))
    result = reader.verify_attempt(source, output_directory=tmp_path / "output", decode=False)
    assert result["integrity_status"] == "INCOMPLETE_OR_INVALID"
    assert result["allocated_steps"] == (4 if kind == "extra_horizon" else 3)
    assert result["verified_frames"] == (2 if kind == "missing_frame" else 3)
    old.assert_authority_closed(result)


@pytest.mark.parametrize("nested", [False, True])
def test_custom_reader_output_never_writes_into_raw_input(tmp_path, runner, reader, nested):
    source = tmp_path / "input"
    source.mkdir()
    old = v3_attempt(source, runner)
    before = old.hashes(source)
    with pytest.raises(ValueError, match="outside input"):
        reader.verify_attempt(source, output_directory=source / "derived" if nested else source)
    assert old.hashes(source) == before
