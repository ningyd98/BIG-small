"""Round57 owned CPU fixtures; no renderer, model, or real detector calls."""

from __future__ import annotations

import copy
import gzip
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location("round57_cpu_" + name, HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


P, R, V = (load(name) for name in ("prepare_full", "run_full_once", "verify_full"))


def test_full_header_exact_contract():
    header = P.make_full_header()
    P.validate_full_header(header)
    assert header["expected_callback_steps"] == list(range(4807))
    assert header["expected_frame_count"] == 4807


@pytest.mark.parametrize(
    "field,value",
    [
        ("protocol", "research.custom-sparse-guarded-marker-v4.v1"),
        ("expected_frame_count", 201),
        ("expected_frame_count", True),
        ("expected_physics_steps", 4805),
        ("expected_physics_steps", True),
        ("expected_physics_steps_is_admission_gate", False),
        ("expected_physics_steps_is_admission_gate", 1),
        ("expected_callback_steps", list(range(1, 4808))),
        ("capture_policy", "PREDECLARED_SPARSE_STEPS_ONLY"),
        ("range_policy", "CLIP_TO_EXPECTED"),
        ("attempt_limit", 2),
        ("index_schema", "rgbd.raw.v3"),
        ("readout_schema", "sparse"),
        ("original_max_sample_gap_s", True),
        ("original_max_sample_gap_s", 0.0050001),
        ("asset_sha256", "0" * 64),
        ("guard_snapshot_contract_digest", "0" * 64),
    ],
)
def test_header_rejects_before_configured_runner(field, value, monkeypatch, tmp_path):
    header = P.make_full_header()
    header[field] = value
    P.write_new(tmp_path / "header.json", header)
    monkeypatch.setattr(R, "configured_runner", lambda *_: pytest.fail("runtime reached"))
    with pytest.raises((ValueError, RuntimeError)):
        R.execute_once(tmp_path)


@pytest.mark.parametrize(
    "section,field,value",
    [
        ("config", "physics_dt_s", 0.005),
        ("config", "control_dt_s", 0.03),
        ("config", "sensor_dt_s", 0.04),
        ("config", "camera_width", 320),
        ("scene", "seed", 1),
        ("marker_registration", "marker_size_m", 0.045),
        ("resource_policy", "max_frame_json_bytes", 16 * 1024 * 1024),
        ("environment", "numpy_version", "changed"),
    ],
)
def test_nested_header_rejects(section, field, value):
    header = P.make_full_header()
    header[section][field] = value
    with pytest.raises((ValueError, RuntimeError)):
        P.validate_full_header(header)


def test_existing_freeze_refused(tmp_path):
    with pytest.raises(FileExistsError):
        P.freeze_full(tmp_path)


class TinyObservation:
    def __init__(self, step, stamp):
        self.episode_id, self.sim_time_s = "cpu", stamp
        self.observation_id, self.checksum_sha256 = f"cpu-{step}", "c" * 64

    def model_dump_json(self):
        return json.dumps(vars(self))


class Capture:
    def __init__(self):
        self.step, self.stamp, self.calls = 0, 0.0, 0
        self.last_capture = {"after_guard": {"cpu": 1}, "after_state": {"cpu": 1}}
        self.fail = None

    def __call__(self):
        self.calls += 1
        if self.fail:
            raise self.fail
        return TinyObservation(self.step, self.stamp), ["p", "p"]

    def final(self):
        return {"guard": {"cpu": 1}, "state": {"cpu": 1}}


def record(tmp_path, final=4806):
    capture = Capture()
    recorder = R.FullRGBDRecorder(
        tmp_path / "whole-step",
        capture,
        episode_id="cpu",
        max_sample_gap_s=0.005,
        final_guard=capture.final,
    )
    for step in range(final + 1):
        capture.step, capture.stamp = step, step * 0.0041666667
        recorder.observe_step(episode_id="cpu", physics_step=step, sim_time_s=capture.stamp)
        recorder.record_step(episode_id="cpu", physics_step=step, sim_time_s=capture.stamp)
    summary = recorder.finish(final_step=final, final_sim_time_s=capture.stamp)
    return recorder, capture, summary


@pytest.mark.parametrize(
    "final,status,missing,extra",
    [
        (4806, "COMPLETE", [], []),
        (4805, "INCOMPLETE", [4806], []),
        (4807, "INCOMPLETE", [], [4807]),
    ],
)
def test_real_recorder_preserves_exact_short_extra(tmp_path, final, status, missing, extra):
    recorder, capture, summary = record(tmp_path, final)
    assert summary["status"] == status
    assert summary["expected_frame_count"] == 4807
    assert summary["physical_callbacks"] == final + 1 == capture.calls
    assert summary["missing_steps"] == missing and summary["extra_steps"] == extra
    assert len(list((recorder.directory / "frames").iterdir())) == final + 1
    if status != "COMPLETE":
        assert summary["reasons"]


@pytest.mark.parametrize(
    "step,stamp,episode",
    [
        (True, 0.0, "cpu"),
        (0, True, "cpu"),
        (0, float("nan"), "cpu"),
        (0, float("inf"), "cpu"),
        (0, -1.0, "cpu"),
        (0, 0.1, "cpu"),
        (1, 0.0, "cpu"),
        (0, 0.0, "wrong"),
    ],
)
def test_rejected_callback_retains_declaration(tmp_path, step, stamp, episode):
    capture = Capture()
    recorder = R.FullRGBDRecorder(
        tmp_path / "whole-step",
        capture,
        episode_id="cpu",
        max_sample_gap_s=0.005,
        final_guard=capture.final,
    )
    with pytest.raises(ValueError):
        recorder.observe_step(episode_id=episode, physics_step=step, sim_time_s=stamp)
    summary = recorder.finish(final_step=0, final_sim_time_s=0.0)
    assert summary["status"] == "INCOMPLETE" and summary["physical_callback_attempts"] == 1
    assert "REJECTED" in (recorder.directory / "index.jsonl").read_text()
    assert capture.calls == 0


@pytest.mark.parametrize("kind", ["missing", "mismatch", "exception", "bool", "time"])
def test_final_guard_cannot_be_inferred_from_range(tmp_path, kind):
    capture = Capture()
    provider = capture.final
    if kind == "missing":
        provider = None
    elif kind == "mismatch":
        provider = lambda: {"guard": {"cpu": 2}, "state": {"cpu": 1}}
    elif kind == "exception":

        def provider():
            raise RuntimeError("final original unavailable")

    recorder = R.FullRGBDRecorder(
        tmp_path / "whole-step",
        capture,
        episode_id="cpu",
        max_sample_gap_s=0.005,
        expected_physics_steps=0,
        final_guard=provider,
    )
    recorder.observe_step(episode_id="cpu", physics_step=0, sim_time_s=0.0)
    recorder.record_step(episode_id="cpu", physics_step=0, sim_time_s=0.0)
    summary = recorder.finish(
        final_step=True if kind == "bool" else 0, final_sim_time_s=1.0 if kind == "time" else 0.0
    )
    assert summary["status"] == "INCOMPLETE" and summary["reasons"]


def test_capture_failure_retains_allocation_and_denominator(tmp_path):
    capture = Capture()
    capture.fail = RuntimeError("original camera failure")
    recorder = R.FullRGBDRecorder(
        tmp_path / "whole-step",
        capture,
        episode_id="cpu",
        max_sample_gap_s=0.005,
        final_guard=capture.final,
    )
    recorder.observe_step(episode_id="cpu", physics_step=0, sim_time_s=0.0)
    with pytest.raises(RuntimeError, match="original camera failure"):
        recorder.record_step(episode_id="cpu", physics_step=0, sim_time_s=0.0)
    summary = recorder.finish(final_step=0, final_sim_time_s=0.0)
    assert summary["allocated_steps"] == [0] and summary["failed_steps"] == [0]
    assert summary["expected_frame_count"] == 4807


def test_double_finish_refused(tmp_path):
    recorder, _, _ = record(tmp_path, 0)
    with pytest.raises(RuntimeError):
        recorder.finish(final_step=0, final_sim_time_s=0.0)


def test_streaming_journal_yields_one_then_retains_truncation(tmp_path):
    path = tmp_path / "journal.gz"
    path.write_bytes(gzip.compress(b'{"record_seq":1}\n{"record_seq":2}\n')[:-5])
    stream = V.iter_journal(path)
    assert iter(stream) is stream
    assert next(stream) == {"record_seq": 1}
    with pytest.raises((EOFError, OSError)):
        list(stream)


def test_journal_rejects_overlong_line(tmp_path):
    path = tmp_path / "journal.gz"
    path.write_bytes(gzip.compress(b"x" * (16 * 1024 * 1024 + 1)))
    with pytest.raises(ValueError, match="journal"):
        next(V.iter_journal(path))


def tiny_rgbd(step, *, frame=None, intrinsics=None):
    import base64
    import io
    import struct
    from datetime import UTC, datetime

    from PIL import Image

    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    png = io.BytesIO()
    Image.new("RGB", (2, 2), (255, 255, 255)).save(png, format="PNG")
    return RGBDObservation(
        frame_id=frame or f"cpu-{step}",
        captured_at=datetime(2026, 10, 6, tzinfo=UTC),
        sim_time_s=step * 0.0041666667,
        width=2,
        height=2,
        rgb_png_base64=base64.b64encode(png.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(struct.pack("<4f", 1, 1, 1, 1)).decode(),
        intrinsics=intrinsics or (2, 2, 1, 1),
        camera_to_world=(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
        source="mujoco_camera",
        scene_id="cpu",
        episode_id="cpu",
        calibration_version="cpu",
    )


def raw_fixture(tmp_path, fault=None):
    (tmp_path / "frames").mkdir()
    ends = {}
    for step in range(3):
        obs = tiny_rgbd(
            step,
            frame="cpu-0" if fault == "duplicate" and step == 1 else None,
            intrinsics=(3, 3, 1, 1) if fault == "context" and step == 1 else None,
        )
        raw = obs.model_dump_json().encode()
        zipped = gzip.compress(raw, mtime=0)
        row = dict(
            episode_id="cpu",
            physics_step=step,
            sim_time_s=obs.sim_time_s,
            observation_id=obs.observation_id,
            checksum=obs.checksum_sha256,
            file=f"frames/{step:07d}.json.gz",
            original_bytes=len(raw),
            compressed_bytes=len(zipped),
            original_sha256=P.digest(raw),
            compressed_sha256=P.digest(zipped),
            schema="research.full-marker-v4-index.v1",
            pass_state_hashes=["p", "p"],
            before_physics_sha256="p",
            action_ordinal=None,
            trace_valid=True,
        )
        (tmp_path / row["file"]).write_bytes(zipped)
        ends[step] = row
    if fault in {"first", "middle", "last"}:
        step = {"first": 0, "middle": 1, "last": 2}[fault]
        del ends[step]
    if fault == "compressed":
        (tmp_path / ends[1]["file"]).write_bytes(b"broken gzip")
    if fault == "original":
        ends[1]["original_sha256"] = "0" * 64
    if fault == "checksum":
        ends[1]["checksum"] = "0" * 64
    if fault == "schema":
        ends[1]["schema"] = "unknown"
    if fault == "pass":
        ends[1]["pass_state_hashes"] = ["p", "q"]
    if fault == "camera":
        ends[1]["trace_valid"] = False
    if fault == "shifted":
        ends = {step + 1: row for step, row in ends.items()}
    if fault == "extra":
        ends[3] = copy.deepcopy(ends[2])
    return ends


@pytest.mark.parametrize(
    "fault,calls,observed",
    [
        (None, 3, 3),
        ("first", 2, 2),
        ("middle", 2, 2),
        ("last", 2, 2),
        ("compressed", 2, 2),
        ("original", 2, 2),
        ("checksum", 2, 2),
        ("schema", 2, 2),
        ("pass", 2, 2),
        ("camera", 2, 2),
        ("duplicate", 2, 2),
        ("context", 2, 2),
        ("shifted", 0, 0),
        ("extra", 3, 3),
        ("unknown", 3, 2),
        ("exception", 3, 2),
        ("source", 0, 0),
    ],
)
def test_decode_exact_planned_rows_only_valid_raw(tmp_path, fault, calls, observed):
    from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerEstimate, PoseMarkerRegistration

    ends = raw_fixture(tmp_path, fault)
    counter = []
    registration = PoseMarkerRegistration(7, 0.075, P.ASSET_SHA)

    def detector(observation, frozen_registration):
        counter.append(observation.observation_id)
        if fault == "exception" and observation.frame_id == "cpu-1":
            raise RuntimeError("CPU decoder exception")
        return PoseMarkerEstimate(
            "UNKNOWN" if fault == "unknown" and observation.frame_id == "cpu-1" else "OBSERVED",
            "CPU mock only",
            observation.observation_id,
            observation.checksum_sha256,
            observation.captured_at,
            frozen_registration.digest(),
        )

    rows = list(
        V.decode_planned_rows(
            tmp_path,
            ends,
            list(range(3)),
            registration,
            detector,
            expected_dimensions=(2, 2),
            source_valid=fault != "source",
        )
    )
    assert [r["physics_step"] for r in rows] == [0, 1, 2]
    assert len(counter) == calls
    assert sum(r["decode_status"] == "OBSERVED" for r in rows) == observed
    assert all(r["stability_status"] == "UNKNOWN" for r in rows)


def test_existing_attempt_rejected_before_runtime(tmp_path, monkeypatch):
    P.write_new(tmp_path / "header.json", P.make_full_header())
    (tmp_path / "attempt-1").mkdir()
    monkeypatch.setattr(R, "configured_runner", lambda *_: pytest.fail("runtime reached"))
    with pytest.raises(FileExistsError):
        R.execute_once(tmp_path)


@pytest.mark.parametrize("event", ["END", "FAILED"])
def test_publication_failure_preserves_raw_or_camera_error(tmp_path, monkeypatch, event):
    capture = Capture()
    recorder = R.FullRGBDRecorder(
        tmp_path / "whole-step",
        capture,
        episode_id="cpu",
        max_sample_gap_s=0.005,
        final_guard=capture.final,
    )
    original = recorder.emit

    def emit(name, **payload):
        if name == event:
            raise OSError("CPU " + event + " publication")
        return original(name, **payload)

    monkeypatch.setattr(recorder, "emit", emit)
    if event == "FAILED":
        capture.fail = RuntimeError("original camera failure")
    recorder.observe_step(episode_id="cpu", physics_step=0, sim_time_s=0.0)
    with pytest.raises((OSError, RuntimeError)):
        recorder.record_step(episode_id="cpu", physics_step=0, sim_time_s=0.0)
    summary = recorder.finish(final_step=0, final_sim_time_s=0.0)
    assert summary["status"] == "INCOMPLETE" and summary["allocated_steps"] == [0]
    assert summary["failed_steps"] == [0]
    if event == "END":
        assert (recorder.directory / "frames/0000000.json.gz").is_file()
    else:
        assert summary["publication_errors"]


def test_partial_raw_write_retained(tmp_path, monkeypatch):
    capture = Capture()
    recorder = R.FullRGBDRecorder(
        tmp_path / "whole-step",
        capture,
        episode_id="cpu",
        max_sample_gap_s=0.005,
        final_guard=capture.final,
    )
    original = Path.open

    class PartialWrite:
        def __init__(self, path):
            self.stream = original(path, "xb")

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.stream.close()

        def write(self, data):
            self.stream.write(data[:4])
            self.stream.flush()
            raise OSError("CPU partial original write")

    def open_path(path, mode="r", *args, **kwargs):
        if path.suffix == ".gz" and mode == "xb":
            return PartialWrite(path)
        return original(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_path)
    recorder.observe_step(episode_id="cpu", physics_step=0, sim_time_s=0.0)
    with pytest.raises(OSError, match="partial original"):
        recorder.record_step(episode_id="cpu", physics_step=0, sim_time_s=0.0)
    summary = recorder.finish(final_step=0, final_sim_time_s=0.0)
    assert (recorder.directory / "frames/0000000.json.gz").stat().st_size == 4
    assert summary["status"] == "INCOMPLETE"


@pytest.mark.parametrize("gap,status", [(0.005, "COMPLETE"), (0.005000000000000001, "INCOMPLETE")])
def test_strict_gap_has_no_upward_tolerance(tmp_path, gap, status):
    capture = Capture()
    recorder = R.FullRGBDRecorder(
        tmp_path / "whole-step",
        capture,
        episode_id="cpu",
        max_sample_gap_s=0.005,
        expected_physics_steps=1,
        final_guard=capture.final,
    )
    for step, stamp in [(0, 0.0), (1, gap)]:
        capture.step, capture.stamp = step, stamp
        recorder.observe_step(episode_id="cpu", physics_step=step, sim_time_s=stamp)
        recorder.record_step(episode_id="cpu", physics_step=step, sim_time_s=stamp)
    assert recorder.finish(final_step=1, final_sim_time_s=gap)["status"] == status


@pytest.mark.parametrize(
    "variant", ["healthy", "shift", "missing", "extra", "field", "nested_episode"]
)
def test_comparison_requires_complete_denominators_and_excludes_only_top_episode(tmp_path, variant):
    old = [
        dict(episode_id="old", physics_step=s, value=s, nested={"episode_id": "shared"})
        for s in range(3)
    ]
    new = [{**r, "episode_id": "new"} for r in copy.deepcopy(old)]
    if variant == "shift":
        for r in new:
            r["physics_step"] += 1
    elif variant == "missing":
        new.pop()
    elif variant == "extra":
        new.append(dict(episode_id="new", physics_step=3, value=3))
    elif variant == "field":
        new[1]["value"] = 4
    elif variant == "nested_episode":
        new[1]["nested"]["episode_id"] = "different"
    result = V.compare_complete_streams(
        iter(old),
        iter(new),
        expected_ids=[0, 1, 2],
        key="physics_step",
        output=tmp_path / "comparison.jsonl",
    )
    assert result["complete_exact_denominators"] is (variant not in {"shift", "missing", "extra"})
    assert result["different_rows"] == 0 if variant == "healthy" else result["different_rows"] > 0


def guarded_cpu_camera():
    import struct
    from dataclasses import asdict

    import numpy as np

    from cloud_edge_robot_arm.research import mujoco_state_guard as G

    header = P.make_full_header()
    contract = G.MujocoStateContract(
        Path(header["guard_headers"]["mjxmacro.h"]).read_bytes(),
        Path(header["guard_headers"]["mjdata.h"]).read_bytes(),
        header["guard_binding_sha256"],
        "3.3.7",
    )
    values = dict(sim_time_s=0.0, qpos=[0.0] * 37, qvel=[0.0] * 33, act=[], ctrl=[0.0] * 9)
    fields = {}
    for name in ("qpos", "qvel", "act", "ctrl"):
        raw = struct.pack("<" + "d" * len(values[name]), *values[name])
        fields[name] = G.ArrayField(
            name,
            "DATA_BACKED" if raw else "EMPTY",
            "VIEW" if raw else "OWNING",
            (len(values[name]),),
            "<f8",
            json.dumps(np.dtype("<f8").descr, separators=(",", ":")),
            len(raw),
            P.digest(raw) if raw else None,
        )
    for getter in contract.getters:
        dtype = np.dtype(getter.dtype)
        fields[getter.name] = G.ArrayField(
            getter.name,
            "EMPTY",
            "OWNING",
            (0,) if getter.width == 1 else (0, getter.width),
            dtype.str,
            json.dumps(dtype.descr, separators=(",", ":")),
            0,
            None,
        )
    arrays = G.DataArraySnapshot(contract.digest, tuple(fields[n] for n in sorted(fields)))
    raw = struct.pack("<d", 0.0) + b"".join(
        struct.pack("<I", len(values[n])) + struct.pack("<" + "d" * len(values[n]), *values[n])
        for n in ("qpos", "qvel", "act", "ctrl")
    )
    state = dict(
        sim_time_s=0.0,
        physical_step=0,
        command_count=0,
        sensor_noise_std_m=0.0,
        camera_object_id=1,
        sensor_cache_object_id=2,
        model_arrays_sha256="a" * 64,
        model_options_sha256="b" * 64,
        controller_state_sha256="c" * 64,
        rng_state_sha256="d" * 64,
        physics_state_sha256=P.digest(raw),
    )
    guard = asdict(G.attach_protected_state(arrays, state))
    guard = json.loads(json.dumps(guard))
    state["data_arrays_sha256"] = arrays.digest
    camera = dict(
        guard_protocol="research.mujoco-support-aware-state.v1",
        camera_call_started=True,
        before_guard=copy.deepcopy(guard),
        after_guard=copy.deepcopy(guard),
        before_state=copy.deepcopy(state),
        after_state=copy.deepcopy(state),
        state_unchanged=True,
        pass_state_hashes=[state["physics_state_sha256"]] * 2,
        capture_monotonic_begin_ns=30,
        capture_monotonic_end_ns=40,
        full_capture_state=dict(
            episode_id="cpu", physics_step=0, sim_time_s=0.0, camera_state=values
        ),
    )
    return camera, contract


@pytest.mark.parametrize(
    "variant",
    [
        "healthy",
        "qpos",
        "unsupported_bytes",
        "noise",
        "time_bool",
        "pass",
        "nested",
        "guard",
        "camera_id",
    ],
)
def test_full_guard_numeric_domains_and_nested_brackets(variant):
    camera, contract = guarded_cpu_camera()
    if variant == "qpos":
        camera["full_capture_state"]["camera_state"]["qpos"][0] = 1.0
    elif variant == "unsupported_bytes":
        camera["before_guard"]["arrays"]["fields"][0]["byte_sha256"] = "a" * 64
    elif variant == "noise":
        camera["before_state"]["sensor_noise_std_m"] = 0.001
    elif variant == "time_bool":
        camera["full_capture_state"]["sim_time_s"] = False
    elif variant == "pass":
        camera["pass_state_hashes"][1] = "a" * 64
    elif variant == "nested":
        camera["capture_monotonic_begin_ns"] = 10
    elif variant == "guard":
        camera["after_guard"]["digest"] = "a" * 64
    elif variant == "camera_id":
        camera["after_state"]["camera_object_id"] = 999
    args = (
        camera,
        contract,
        dict(episode_id="cpu", physics_step=0, sim_time_s=0.0),
        [10, 20, 50, 60],
    )
    if variant == "healthy":
        V.validate_frame_camera(*args)
    else:
        with pytest.raises(ValueError):
            V.validate_frame_camera(*args)


def test_cpu_temp_freeze_is_exclusive_and_never_initializes_runtime(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    monkeypatch.setattr(
        MuJoCoPhysicsBackend, "initialize", lambda *_: pytest.fail("model initialization reached")
    )
    monkeypatch.setattr(
        MuJoCoCaptureSession, "__enter__", lambda *_: pytest.fail("capture session reached")
    )
    destination = tmp_path / "frozen"
    result = P.freeze_full(destination)
    header = json.loads((destination / "header.json").read_text())
    assert result["status"] == "PREPARED_SOFTWARE_ONLY" and result["expected_frame_count"] == 4807
    assert result["model_constructions"] == result["decoder_calls"] == 0
    assert P.source_preflight(None, header, destination).digest == P.CONTRACT_DIGEST
    assert set(P.OWNED) <= {p.name for p in (destination / "source-final").iterdir()}
    with pytest.raises(FileExistsError):
        P.freeze_full(destination)
    before = P.hash_file(destination / "header.json")
    (destination / "execution-source-hashes.json").write_text("{}\n")
    with pytest.raises(ValueError, match="metadata"):
        P.source_preflight(None, header, destination)
    assert P.hash_file(destination / "header.json") == before


def test_live_same_named_module_with_wrong_origin_rejected(tmp_path, monkeypatch):
    import sys

    name = "cloud_edge_robot_arm.vision.pose_markers"
    fake = tmp_path / "pose_markers.py"
    fake.write_text("# CPU wrong origin\n")
    module = SimpleNamespace(__file__=str(fake), __spec__=SimpleNamespace(origin=str(fake)))
    monkeypatch.setitem(sys.modules, name, module)
    source = "src/cloud_edge_robot_arm/vision/pose_markers.py"
    with pytest.raises(ValueError, match="origin"):
        P.check_origins({source: P.hash_file(P.ROOT / source)})


def test_decoder_binary_environment_pin_change_rejected():
    header = P.make_full_header()
    header["environment"]["files"]["cv2/binary"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="environment"):
        P.validate_full_header(header)


@pytest.mark.parametrize(
    "payload", [b'{"a":1,"a":2}\n', b'{"sim_time_s":NaN}\n', b'{"sim_time_s":Infinity}\n']
)
def test_streaming_rejects_duplicate_keys_and_nonfinite_json(tmp_path, payload):
    path = tmp_path / "journal.gz"
    path.write_bytes(gzip.compress(payload))
    with pytest.raises(ValueError):
        next(V.iter_journal(path))
