"""OC2 CPU raw backend/counter seams; real worker, observer, recorder and reader."""

import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from cloud_edge_robot_arm.research import operational_prefix_v1 as module
from cloud_edge_robot_arm.research.operational_time_v1 import _open_clock_for_test
from cloud_edge_robot_arm.simulation.models import SensorFrame
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
from tests.test_operational_prefix_v1 import application
from tests.test_operational_time_v1 import _RawSource
from tests.test_visual_raw_recorder_v3 import software_backend


def cpu_components(monkeypatch, app, failure=None):
    """Replace raw CPU source and backend construction only, never verdicts."""
    backend = software_backend()
    backend._episode_id = None
    calls = []
    raw = _RawSource(list(range(10_000, 30_000)))
    monkeypatch.setattr(module, "_open_clock_v1", lambda: _open_clock_for_test(raw))
    monkeypatch.setattr(module, "_new_prefix_backend_v1", lambda: backend)
    original_observer = backend.observe_operation_boundaries

    @contextmanager
    def observe(callback):
        calls.append("observer")
        with original_observer(callback):
            yield

    backend.observe_operation_boundaries = observe

    def initialize(config):
        assert (app.output / "prefix-originals/preregistration.json").is_file()
        backend._config = config
        calls.append("initialize")

    backend.initialize = initialize
    backend.shutdown = lambda: calls.append("shutdown")
    captures = 0

    def camera(data, **kwargs):
        nonlocal captures
        captures += 1
        if failure == "capture" and captures == 3:
            raise RuntimeError("CPU explicit camera failure")
        if captures == 3 and failure == "cancel":
            app.repository.request_cancel(module._live(app).job_id)
        if captures == 3 and failure == "policy":
            app.config_path.write_bytes(app.config_path.read_bytes() + b" ")
        if captures == 3 and failure == "capture_swap":
            module._live(app).source.capture._backend = software_backend()
        count = 320 * 240
        frame = SensorFrame(
            frame_id=f"CPU-frame-{captures}",
            sim_time_s=backend.get_sim_time(),
            width=320,
            height=240,
            rgb=bytes([100, 120, 150]) * count,
            depth=(0.5,) * count,
            intrinsics=(300.0, 300.0, 160.0, 120.0),
            camera_to_world=(
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1.0,
            ),
            captured_at=datetime.now(UTC),
            episode_id=backend._episode_id,
            scene_id="S01_NORMAL_STATIC",
            calibration_version="CPU-only",
            valid_mask=bytes([1]) * count,
        )
        digest = MuJoCoRGBDCamera._physics_state_hash(data)
        return frame, (-1,) * count, {-1: "background"}, (digest,) * 3

    backend._camera = SimpleNamespace(capture_with_instances=camera)

    def cached():
        backend._sensor_frame = backend.capture_sensor_frame_with_instances()[0]

    backend._update_sensor_frame = cached

    def reset(scenario):
        calls.append("RESET")
        with backend._operation_source("RESET", {"requested": scenario}):
            if failure == "reset":
                raise RuntimeError("CPU reset failure")
            backend._episode_id = "CPU-new-episode"
            backend._scenario = scenario
            backend._total_physics_steps = 0
            backend._data.time = 0.0
            cached()

    backend.reset = reset
    app.worker.planner_factory = lambda: pytest.fail("planner/model/provider forbidden")
    if failure == "export":
        from cloud_edge_robot_arm.research.operational_capture_v1 import OperationalPrefixRecorderV1

        monkeypatch.setattr(
            OperationalPrefixRecorderV1,
            "_save_frames",
            lambda self: (_ for _ in ()).throw(OSError("CPU export failure")),
        )
    if failure == "catalog":
        original_write = module._write_exclusive_v1

        def write(path, raw_bytes):
            if path.name == "capture-catalog.json":
                raise OSError("CPU catalog failure")
            original_write(path, raw_bytes)

        monkeypatch.setattr(module, "_write_exclusive_v1", write)
    return backend, calls


def require_task2():
    assert hasattr(module, "run_operational_prefix_v1"), "Task2 runner interface missing"
    assert hasattr(module, "verify_operational_prefix_originals_v1"), (
        "Task3 reader interface missing"
    )


def test_real_interfaces_reset120_capture_current_chain_cpu(tmp_path, monkeypatch):
    require_task2()
    app = application(tmp_path)
    backend, calls = cpu_components(monkeypatch, app)
    receipt = app.execute_once()
    assert receipt["source_prefix_complete"] is True
    assert receipt["actual_capture_allocations"] == 3
    assert receipt["explicit_acquisitions"] == 1 and receipt["allocated_actions"] == 0
    assert calls == ["initialize", "observer", "RESET", "shutdown"]
    job = app.repository.list_jobs()[0]
    assert job.status == RuntimeJobStatus.SUCCEEDED
    assert len(app.repository.list_attempts(job.run_id)) == 1
    assert backend.total_physics_steps == 120
    view = module.verify_operational_prefix_originals_v1(app.output / "prefix-originals", receipt)
    assert view["original_integrity"] == "VERIFIED" and view["source_prefix_complete"] is True
    assert view["recorded_source_current_age"]["within_5s"] is True
    assert view["formal_accepted"] is False and view["calibration_groups"] == 0
    assert app.catalog_entry() == receipt
    with pytest.raises(RuntimeError, match="twice"):
        app.execute_once()


def test_counter_source_is_not_old_monotonic_pair(tmp_path, monkeypatch):
    require_task2()
    app = application(tmp_path)
    cpu_components(monkeypatch, app)
    receipt = app.execute_once()
    root = app.output / "prefix-originals"
    d = json.loads((root / "operational-originals.json").read_bytes())
    legacy = json.loads((root / "frozen-originals.json").read_bytes())
    assert d["events"][0]["bracket"]["lower_ns"] == 10_000
    assert legacy["clock_pairs"][0]["mono_before_ns"] > 30_000
    assert legacy["clock_pairs"][0]["utc_at"]
    assert receipt["clock_schema"] == "simulation.operational-time.v1"
    assert d["current"]["source_acquisition_id"] == "acquisition-3"


def test_operation_brackets_capture_identity_and_denominator(tmp_path, monkeypatch):
    require_task2()
    app = application(tmp_path)
    cpu_components(monkeypatch, app)
    app.execute_once()
    slab = json.loads((app.output / "prefix-originals/operational-originals.json").read_bytes())
    events = slab["events"]
    assert len(events) == 244
    assert events[0]["begin"]["episode_id"] is None
    assert events[0]["end"]["episode_id"] == "CPU-new-episode"
    assert events[1]["kind"] == "CAPTURE"
    assert (
        events[0]["begin_seq"]
        < events[1]["begin_seq"]
        < events[1]["mark_seq"]
        < events[0]["mark_seq"]
    )
    assert [r["acquisition_id"] for r in events if r["kind"] == "CAPTURE"] == [
        "acquisition-1",
        "acquisition-2",
        "acquisition-3",
    ]
    assert all(r["begin_seq"] < r["mark_seq"] < r["end_seq"] for r in events)
    assert slab["allocated_acquisition_ids"] == ["acquisition-1", "acquisition-2", "acquisition-3"]


@pytest.mark.parametrize(
    "failure", ["reset", "capture", "cancel", "policy", "capture_swap", "export", "catalog"]
)
def test_partial_prefix_keeps_all_failures(tmp_path, monkeypatch, failure):
    require_task2()
    app = application(tmp_path)
    cpu_components(monkeypatch, app, failure)
    receipt = app.execute_once()
    assert receipt["source_prefix_complete"] is False
    assert app.repository.list_jobs()[0].status in {
        RuntimeJobStatus.FAILED,
        RuntimeJobStatus.CANCELLED,
    }
    with pytest.raises(RuntimeError, match="no live operational source-only publication"):
        app.catalog_entry()
    root = app.output / "prefix-originals"
    assert (root / "prefix-failures.json").is_file()
    slab = json.loads((root / "operational-originals.json").read_bytes())
    assert slab["events"]
    assert slab["failures"] or (root / "publication-failure.json").is_file()
    if failure == "capture":
        failed = slab["events"][-1]
        assert failed["kind"] == "CAPTURE" and failed["bracket"] is None
        assert failed["mark_seq"] is None and failed["end_seq"] is None
        assert slab["allocated_acquisition_ids"][-1] == "acquisition-3"


@pytest.mark.parametrize(
    "tamper",
    [
        "flag",
        "allocation",
        "pair",
        "episode",
        "reset",
        "hash",
        "bytes",
        "escape",
        "symlink",
        "schema",
    ],
)
def test_reader_recomputes_and_never_mints_authority(tmp_path, monkeypatch, tamper):
    require_task2()
    app = application(tmp_path)
    cpu_components(monkeypatch, app)
    receipt = app.execute_once()
    root = app.output / "prefix-originals"
    receipt["source_prefix_complete"] = False
    if tamper == "flag":
        pass
    elif tamper in {"allocation", "pair", "episode", "reset", "schema"}:
        p = root / "operational-originals.json"
        slab = json.loads(p.read_bytes())
        if tamper == "allocation":
            slab["allocated_acquisition_ids"].append("acquisition-extra")
        elif tamper == "pair":
            slab["events"][-1]["bracket"] = None
        elif tamper == "episode":
            slab["events"][-1]["end"]["episode_id"] = "foreign"
        elif tamper == "reset":
            slab["events"][0]["begin"]["episode_id"] = "forged-old"
        else:
            slab["schema_version"] = "foreign"
        raw = module.canonical_bytes_v1(slab)
        p.write_bytes(raw)
        receipt["original_files"][p.name] = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        }
    elif tamper == "hash":
        (root / "frames/acquisition-3/rgb.png").write_bytes(b"changed")
    elif tamper == "bytes":
        receipt["original_files"]["operational-originals.json"]["bytes"] += 1
    elif tamper == "escape":
        receipt["original_files"]["../runtime.db"] = {"sha256": "0" * 64, "bytes": 1}
    else:
        p = root / "operational-originals.json"
        q = root / "outside.json"
        q.write_bytes(p.read_bytes())
        p.unlink()
        p.symlink_to(q)
    monkeypatch.setattr(module, "_open_clock_v1", lambda: pytest.fail("reader minted live D"))
    monkeypatch.setattr(
        module, "_new_prefix_backend_v1", lambda: pytest.fail("reader initialized backend")
    )
    view = module.verify_operational_prefix_originals_v1(root, receipt)
    assert view["source_prefix_complete"] is (tamper == "flag")
    assert view["live_authority"] == "UNAVAILABLE"
