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


def cpu_components(monkeypatch, app, failure=None, *, production_cached=False):
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

    def camera(data, include_instances=True, **kwargs):
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
        if not include_instances:
            return frame, (), {}, (digest,) * 2
        return frame, (-1,) * count, {-1: "background"}, (digest,) * 3

    backend._camera = SimpleNamespace(_capture=camera, capture_with_instances=camera)

    def cached():
        backend._sensor_frame = backend.capture_sensor_frame_with_instances()[0]

    backend._update_sensor_frame = cached
    if production_cached:
        from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

        backend._update_sensor_frame = MuJoCoPhysicsBackend._update_sensor_frame.__get__(backend)

    def reset(scenario):
        calls.append("RESET")
        with backend._operation_source("RESET", {"requested": scenario}):
            if failure == "reset":
                raise RuntimeError("CPU reset failure")
            backend._episode_id = "CPU-new-episode"
            backend._scenario = scenario
            backend._total_physics_steps = 0
            backend._data.time = 0.0
            backend._update_sensor_frame()

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


FAILURE_EXPECTATIONS = {
    "reset": (RuntimeJobStatus.BLOCKED_BY_ENV, "RuntimeError", "CPU reset failure"),
    "capture": (RuntimeJobStatus.BLOCKED_BY_ENV, "RuntimeError", "CPU explicit camera failure"),
    "cancel": (
        RuntimeJobStatus.CANCELLED,
        "ValueError",
        "worker job identity/status/lease source invalid",
    ),
    "policy": (
        RuntimeJobStatus.FAILED,
        "ValueError",
        "frozen policy/source/asset inventory changed",
    ),
    "capture_swap": (
        RuntimeJobStatus.FAILED,
        "ValueError",
        "original source/backend/capture/executor/OC1 handles changed",
    ),
    "export": (
        RuntimeJobStatus.BLOCKED_BY_ENV,
        "RuntimeError",
        "legacy frame/export failure retained",
    ),
    "catalog": (RuntimeJobStatus.BLOCKED_BY_ENV, "OSError", "CPU catalog failure"),
}


def assert_primary_failed_prefix(app, receipt, expected, calls):
    status, kind, message = expected
    assert receipt["source_prefix_complete"] is False
    assert app.repository.list_jobs()[0].status == status
    assert receipt["primary_error"] == {"error_type": kind, "error": message}
    primary = [row for row in receipt["failures"] if row.get("role") == "PRIMARY"]
    assert len(primary) == 1 and primary[0]["error_type"] == kind and primary[0]["error"] == message
    assert all(
        row["primary_failure_id"] == primary[0]["failure_id"] for row in receipt["secondary_errors"]
    )
    with pytest.raises(RuntimeError, match="no live operational source-only publication"):
        app.catalog_entry()
    assert calls.count("RESET") == calls.count("initialize") == calls.count("observer") == 1
    assert len(app.repository.list_attempts(app.repository.list_jobs()[0].run_id)) == 1
    root = app.output / "prefix-originals"
    partial = json.loads((root / "partial-attempts.json").read_bytes())
    stage_files = sorted(root.glob("stage-failures-*.json"))
    assert stage_files
    stage = json.loads(stage_files[-1].read_bytes())
    assert stage["primary_failure_id"] == primary[0]["failure_id"]
    assert stage["failures"][0]["error"] == message
    saved = json.loads((app.output / "runner-failure.json").read_bytes())
    assert saved["primary_error"] == receipt["primary_error"]
    before = {str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    with pytest.raises(RuntimeError, match="twice"):
        app.execute_once()
    assert {str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()} == before
    return partial


@pytest.mark.parametrize(
    "failure", ["reset", "capture", "cancel", "policy", "capture_swap", "export", "catalog"]
)
def test_partial_prefix_keeps_all_failures(tmp_path, monkeypatch, failure):
    require_task2()
    app = application(tmp_path)
    _, calls = cpu_components(monkeypatch, app, failure)
    receipt = app.execute_once()
    partial = assert_primary_failed_prefix(app, receipt, FAILURE_EXPECTATIONS[failure], calls)
    root = app.output / "prefix-originals"
    slab = json.loads((root / "operational-originals.json").read_bytes())
    ledger = partial["operational_ledger"]
    assert len(ledger["events"]) == (1 if failure == "reset" else 244)
    assert len(partial["backend_operation_ledger"]) == (2 if failure == "reset" else 488)
    assert [row["operation_id"] for row in ledger["events"]] == list(
        range(1, len(ledger["events"]) + 1)
    )
    expected_ids = [] if failure == "reset" else ["acquisition-1", "acquisition-2", "acquisition-3"]
    assert ledger["allocated_acquisition_ids"] == expected_ids
    assert len(partial["legacy_frames"]) == len(expected_ids)
    assert ledger["allocated_action_ids"] == []
    assert ledger["current"] is None or failure in {"export", "catalog"}
    assert any(row["error"] == FAILURE_EXPECTATIONS[failure][2] for row in ledger["failures"])
    if failure in {"reset", "capture"}:
        failed = slab["events"][-1]
        assert failed["kind"] == ("RESET" if failure == "reset" else "CAPTURE")
        assert (
            failed["bracket"] is None and failed["mark_seq"] is None and failed["end_seq"] is None
        )
        assert failed["end"]["error"] == FAILURE_EXPECTATIONS[failure][2]
        assert partial["incomplete_operation_ids"] == [failed["operation_id"]]
        assert (
            slab["backend_observer_failures"]
            == partial["operational_ledger"]["backend_observer_failures"]
        )
        original = json.loads((root / "prefix-failures.json").read_bytes())
        assert any(row["error"] == FAILURE_EXPECTATIONS[failure][2] for row in original)
    if failure == "capture":
        assert slab["allocated_acquisition_ids"][-1] == "acquisition-3"
        assert partial["legacy_frames"][-1]["observation_payload"] is None
    if failure in {"export", "catalog"}:
        assert (root / "prefix-failures.json").read_bytes() == b"[]"
        assert slab["failures"] == []
        stage = json.loads((root / "stage-failures-1.json").read_bytes())
        for name, pin in stage["existing_original_pins"].items():
            original = (root / name).read_bytes()
            assert (
                len(original) == pin["bytes"]
                and hashlib.sha256(original).hexdigest() == pin["sha256"]
            )
    if failure == "export":
        exported = json.loads((root / "unbound-export.json").read_bytes())
        assert exported["export_failures"] == ["OSError: CPU export failure"]
        recorder = module._live(app).recorder
        assert recorder._operational_export is None
        assert isinstance(recorder._operational_export_error, RuntimeError)
    if failure == "catalog":
        assert (root / "prefix-receipt.json").is_file()
        assert not (app.output / "capture-catalog.json").exists()


def test_reset_primary_survives_legacy_freeze_failure(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.research.operational_capture_v1 import OperationalPrefixRecorderV1

    app = application(tmp_path)
    _, calls = cpu_components(monkeypatch, app, "reset")
    freeze_calls = []

    def freeze(self):
        freeze_calls.append("legacy_freeze")
        raise OSError("CPU legacy freeze secondary")

    monkeypatch.setattr(OperationalPrefixRecorderV1, "freeze_unbound_prefix", freeze)
    receipt = app.execute_once()
    partial = assert_primary_failed_prefix(app, receipt, FAILURE_EXPECTATIONS["reset"], calls)
    assert freeze_calls == ["legacy_freeze"]
    assert partial["operational_ledger"]["events"][0]["end"]["error"] == "CPU reset failure"
    assert partial["operational_ledger"]["events"][0]["bracket"] is None
    assert any(
        row["phase"] == "failure_freeze"
        and row["error_type"] == "OSError"
        and row["error"] == "CPU legacy freeze secondary"
        for row in receipt["secondary_errors"]
    )
    assert module._live(app).recorder._operational_freeze_attempted is True


def test_reset_primary_survives_failure_export_failure(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.research.operational_capture_v1 import OperationalPrefixRecorderV1

    app = application(tmp_path)
    _, calls = cpu_components(monkeypatch, app, "reset")
    export_calls = []
    original = OperationalPrefixRecorderV1.export_operational_prefix

    def legacy_export(self):
        export_calls.append("legacy_export")
        raise OSError("CPU failure export secondary")

    def reject_cached_failure(self):
        try:
            return original(self)
        except OSError as primary_export:
            with pytest.raises(OSError, match="CPU failure export secondary") as repeated:
                original(self)
            assert repeated.value is primary_export
            raise

    monkeypatch.setattr(OperationalPrefixRecorderV1, "export_unbound_prefix", legacy_export)
    monkeypatch.setattr(
        OperationalPrefixRecorderV1, "export_operational_prefix", reject_cached_failure
    )
    receipt = app.execute_once()
    partial = assert_primary_failed_prefix(app, receipt, FAILURE_EXPECTATIONS["reset"], calls)
    assert export_calls == ["legacy_export"]
    assert partial["operational_ledger"]["events"][0]["end"]["error"] == "CPU reset failure"
    assert partial["operational_ledger"]["allocated_acquisition_ids"] == []
    assert any(
        row["phase"] == "failure_export"
        and row["error_type"] == "OSError"
        and row["error"] == "CPU failure export secondary"
        for row in receipt["secondary_errors"]
    )
    assert module._live(app).recorder._operational_export is None


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


@pytest.mark.parametrize("config_state", ["missing", "changed"])
def test_recorder_rejects_missing_or_changed_backend_config_cpu(
    tmp_path, monkeypatch, config_state
):
    require_task2()
    app = application(tmp_path)
    backend, calls = cpu_components(monkeypatch, app)
    original_initialize = backend.initialize

    def initialize(config):
        original_initialize(config)
        backend._config = (
            None if config_state == "missing" else config.model_copy(update={"seed": 1})
        )

    monkeypatch.setattr(backend, "initialize", initialize)
    receipt = app.execute_once()
    assert receipt["source_prefix_complete"] is False
    assert receipt["primary_error"] == {
        "error_type": "ValueError",
        "error": "original backend simulator configuration changed",
    }
    primary = [row for row in receipt["failures"] if row.get("role") == "PRIMARY"]
    assert len(primary) == 1
    assert primary[0]["error_type"] == "ValueError"
    assert primary[0]["error"] == receipt["primary_error"]["error"]
    job = app.repository.list_jobs()[0]
    assert job.status == RuntimeJobStatus.FAILED
    assert len(app.repository.list_attempts(job.run_id)) == 1
    assert calls == ["initialize", "shutdown"]
    assert not (app.output / "capture-catalog.json").exists()
    assert not (app.output / "prefix-originals/prefix-receipt.json").exists()
    with pytest.raises(RuntimeError, match="no live operational source-only publication"):
        app.catalog_entry()
    saved = json.loads((app.output / "runner-failure.json").read_bytes())
    assert saved["primary_error"] == receipt["primary_error"]
    assert saved["source_prefix_complete"] is False


@pytest.mark.parametrize("entry", ["direct", "worker"])
def test_preregistration_primary_survives_startup_report_failure_cpu(tmp_path, monkeypatch, entry):
    from tests.test_operational_prefix_v1 import activate

    require_task2()
    app = application(tmp_path)
    _, calls = cpu_components(monkeypatch, app)
    original = ValueError("CPU preregistration primary")
    startup_writes = []
    original_write = module._write_exclusive_v1

    def construct():
        raise original

    def write(path, raw):
        if path.name == "startup-failures.json":
            startup_writes.append(path)
            raise OSError("CPU startup report secondary")
        original_write(path, raw)

    monkeypatch.setattr(module, "_new_prefix_backend_v1", construct)
    monkeypatch.setattr(module, "_write_exclusive_v1", write)
    if entry == "direct":
        job, _, start = activate(app)
        with pytest.raises(BaseException) as caught:
            module._prepare_source_v1(app, app.worker, job, start_monotonic=start)
        assert caught.value is original
        failures = module._live(app).failures
        with pytest.raises(RuntimeError, match="cannot be allocated twice"):
            module._prepare_source_v1(app, app.worker, job, start_monotonic=start)
    else:
        receipt = app.execute_once()
        assert receipt["primary_error"] == {
            "error_type": "ValueError",
            "error": "CPU preregistration primary",
        }
        failures = receipt["failures"]
        job = app.repository.list_jobs()[0]
        assert job.status == RuntimeJobStatus.FAILED
        assert len(app.repository.list_attempts(job.run_id)) == 1
        saved = json.loads((app.output / "runner-failure.json").read_bytes())
        assert saved["primary_error"] == receipt["primary_error"]
        assert saved["durable_failure_evidence_complete"] is False
    primary = [row for row in failures if row["role"] == "PRIMARY"]
    assert len(primary) == 1
    assert primary[0]["error_type"] == "ValueError"
    assert primary[0]["error"] == "CPU preregistration primary"
    assert primary[0]["phase"] == "preregistration"
    secondary = [row for row in failures if row["role"] == "SECONDARY"]
    assert secondary
    assert all(row["primary_failure_id"] == primary[0]["failure_id"] for row in secondary)
    assert any(
        row["error_type"] == "OSError"
        and row["error"] == "CPU startup report secondary"
        and row["phase"] == "startup_failure_persistence"
        for row in secondary
    )
    assert len({row["failure_id"] for row in failures}) == len(failures)
    assert module._live(app).durable_failure_evidence_complete is False
    stages = sorted(app.output.glob("stage-failures-*.json"))
    assert stages
    stage = json.loads(stages[0].read_bytes())
    assert stage["primary_failure_id"] == primary[0]["failure_id"]
    assert stage["durable_failure_evidence_complete"] is False
    assert stage["failures"][:2] == failures[:2]
    assert len(startup_writes) == 1
    assert calls == []
    assert not (app.output / "capture-catalog.json").exists()
    with pytest.raises(RuntimeError, match="no live operational source-only publication"):
        app.catalog_entry()


@pytest.mark.parametrize("tamper", ["missing_returned", "wrong_source_relation"])
def test_reader_rejects_broken_returned_acquisition_join_cpu(tmp_path, monkeypatch, tamper):
    require_task2()
    app = application(tmp_path)
    cpu_components(monkeypatch, app)
    receipt = app.execute_once()
    assert receipt["source_prefix_complete"] is True
    root = app.output / "prefix-originals"
    path = root / "operational-originals.json"
    slab = json.loads(path.read_bytes())
    if tamper == "missing_returned":
        returned_id = "CPU-absent-returned-acquisition"
    else:
        frames = json.loads((root / "frozen-originals.json").read_bytes())["frames"]
        frame = next(
            row
            for row in frames
            if row["acquisition_id"] != slab["current"]["source_acquisition_id"]
            and (row["source_acquisition_id"] or row["acquisition_id"])
            != slab["current"]["source_acquisition_id"]
        )
        returned_id = frame["acquisition_id"]
    slab["current"]["returned_acquisition_id"] = returned_id
    raw = module.canonical_bytes_v1(slab)
    path.write_bytes(raw)
    receipt["original_files"][path.name] = {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }
    monkeypatch.setattr(module, "_open_clock_v1", lambda: pytest.fail("reader minted live D"))
    monkeypatch.setattr(
        module, "_new_prefix_backend_v1", lambda: pytest.fail("reader initialized backend")
    )
    view = module.verify_operational_prefix_originals_v1(root, receipt)
    assert view["original_integrity"] == "INVALID"
    assert view["source_prefix_complete"] is False
    assert view["live_authority"] == "UNAVAILABLE"


@pytest.mark.parametrize("returned_kind", ["direct", "derived"])
def test_current_source_event_join_accepts_direct_and_derived_ids(returned_kind):
    source = {
        "acquisition_id": "source-1",
        "source_acquisition_id": None,
        "interval_id": "operation-7",
    }
    event = {"kind": "CAPTURE", "acquisition_id": "source-1", "operation_id": 7}
    frames = [source]
    returned_id = "source-1"
    if returned_kind == "derived":
        returned_id = "returned-1"
        frames.append(
            {
                "acquisition_id": returned_id,
                "source_acquisition_id": "source-1",
                "interval_id": "operation-7",
            }
        )
    current = {"returned_acquisition_id": returned_id, "source_acquisition_id": "source-1"}
    assert module._current_source_event_v1(current, frames, [event]) is event


def _r93_repin_json(root, receipt, name, value):
    raw = module.canonical_bytes_v1(value)
    (root / name).write_bytes(raw)
    receipt["original_files"][name] = {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def test_cached_capture_preserves_empty_instance_sidecars_cpu(tmp_path, monkeypatch):
    app = application(tmp_path)
    backend, calls = cpu_components(monkeypatch, app, production_cached=True)
    receipt = app.execute_once()
    assert receipt["source_prefix_complete"] is True
    root = app.output / "prefix-originals"
    slab = json.loads((root / "operational-originals.json").read_bytes())
    frozen = json.loads((root / "frozen-originals.json").read_bytes())
    captures = [row for row in slab["events"] if row["kind"] == "CAPTURE"]
    assert len(slab["events"]) == 244 and len(captures) == 3
    assert backend.total_physics_steps == 120
    assert receipt["actual_capture_allocations"] == 3
    assert receipt["explicit_acquisitions"] == 1 and receipt["allocated_actions"] == 0
    assert calls == ["initialize", "observer", "RESET", "shutdown"]
    assert app.repository.list_jobs()[0].status == RuntimeJobStatus.SUCCEEDED
    assert [len(row["end"]["result"]["instance_ids"]) for row in captures] == [0, 0, 76800]
    for capture, size, count, available, passes in zip(
        captures, [0, 0, 307200], [0, 0, 76800], [False, False, True], [2, 2, 3], strict=True
    ):
        acquisition = capture["acquisition_id"]
        prefix = f"frames/{acquisition}/"
        raw = (root / (prefix + "instances.i32")).read_bytes()
        assert len(raw) == size
        assert receipt["original_files"][prefix + "instances.i32"] == {
            "bytes": size,
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        metadata = json.loads((root / (prefix + "source-frame.json")).read_bytes())
        source = capture["end"]["result"]
        aux = frozen["frame_aux"][acquisition]
        assert metadata["instances_available"] is available
        assert type(metadata["instance_id_count"]) is int
        assert metadata["instance_id_count"] == count
        assert aux["instance_ids"] == source["instance_ids"]
        assert metadata["instance_labels"] == aux["instance_labels"] == source["instance_labels"]
        assert metadata["pass_state_hashes"] == source["pass_state_hashes"]
        assert len(metadata["pass_state_hashes"]) == passes
        assert len(set(metadata["pass_state_hashes"])) == 1
        assert capture["begin_seq"] < capture["mark_seq"] < capture["end_seq"]
    assert (root / "prefix-receipt.json").is_file()
    assert (app.output / "capture-catalog.json").is_file()
    assert app.catalog_entry() == receipt
    view = module.verify_operational_prefix_originals_v1(root, receipt)
    assert view["original_integrity"] == "VERIFIED"
    assert view["source_prefix_complete"] is True
    assert view["formal_accepted"] is False and view["live_authority"] == "UNAVAILABLE"


@pytest.mark.parametrize(
    "byte_count",
    [0, False, True, -1, "0", 0.0],
    ids=["zero", "false", "true", "negative", "string", "float"],
)
def test_source_inventory_rejects_empty_and_noninteger_bytes_cpu(byte_count):
    from cloud_edge_robot_arm.research.operational_prefix_schema_v1 import validate_inventory_v1

    with pytest.raises(ValueError):
        validate_inventory_v1({"x.py": {"sha256": "a" * 64, "bytes": byte_count}})
    if type(byte_count) is int and byte_count == 0:
        with pytest.raises(ValueError):
            validate_inventory_v1(
                {"frames/acquisition-1/instances.i32": {"sha256": "a" * 64, "bytes": 0}}
            )


@pytest.mark.parametrize(
    "tamper",
    ["bytes_bool", "bytes_string", "bytes_negative", "empty_rgb", "empty_depth", "empty_mask"],
)
def test_artifact_inventory_preserves_negative_and_geometry_guards_cpu(
    tmp_path, monkeypatch, tamper
):
    app = application(tmp_path)
    cpu_components(monkeypatch, app)
    receipt = app.execute_once()
    assert receipt["source_prefix_complete"] is True
    root = app.output / "prefix-originals"
    prefix = "frames/acquisition-1/"
    if tamper.startswith("bytes_"):
        receipt["original_files"][prefix + "instances.i32"]["bytes"] = {
            "bytes_bool": True,
            "bytes_string": "0",
            "bytes_negative": -1,
        }[tamper]
    else:
        name = (
            prefix
            + {"empty_rgb": "rgb.png", "empty_depth": "depth.f32", "empty_mask": "mask.u8"}[tamper]
        )
        (root / name).write_bytes(b"")
        receipt["original_files"][name] = {"sha256": hashlib.sha256(b"").hexdigest(), "bytes": 0}
    view = module.verify_operational_prefix_originals_v1(root, receipt)
    assert view["original_integrity"] == "INVALID"
    assert view["source_prefix_complete"] is False
    assert view["live_authority"] == "UNAVAILABLE"


@pytest.mark.parametrize("tamper", ["availability_false", "count_bool", "source_ids_changed"])
def test_reader_rejects_instance_source_metadata_mismatch_cpu(tmp_path, monkeypatch, tamper):
    app = application(tmp_path)
    cpu_components(monkeypatch, app)
    receipt = app.execute_once()
    assert receipt["source_prefix_complete"] is True
    root = app.output / "prefix-originals"
    if tamper == "source_ids_changed":
        slab = json.loads((root / "operational-originals.json").read_bytes())
        capture = next(row for row in slab["events"] if row["kind"] == "CAPTURE")
        capture["end"]["result"]["instance_ids"] = []
        _r93_repin_json(root, receipt, "operational-originals.json", slab)
    else:
        name = "frames/acquisition-1/source-frame.json"
        metadata = json.loads((root / name).read_bytes())
        metadata[
            "instances_available" if tamper == "availability_false" else "instance_id_count"
        ] = False if tamper == "availability_false" else True
        _r93_repin_json(root, receipt, name, metadata)
        digest = receipt["original_files"][name]["sha256"]
        frozen = json.loads((root / "frozen-originals.json").read_bytes())
        persisted = json.loads((root / "persisted-frames.json").read_bytes())
        frozen["frames"][0]["file_hashes"][name] = digest
        persisted[0]["file_hashes"][name] = digest
        _r93_repin_json(root, receipt, "frozen-originals.json", frozen)
        _r93_repin_json(root, receipt, "unbound-frames.json", frozen["frames"])
        _r93_repin_json(root, receipt, "persisted-frames.json", persisted)
    view = module.verify_operational_prefix_originals_v1(root, receipt)
    assert view["original_integrity"] == "INVALID"
    assert view["source_prefix_complete"] is False
    assert any("instance" in reason for reason in view["reasons"])
    assert view["live_authority"] == "UNAVAILABLE"
