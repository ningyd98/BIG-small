"""SOFTWARE_ONLY live SQLite and publication graph controls, never native proof."""

import copy
import json
import time
from datetime import UTC, datetime
from importlib import import_module, util
from pathlib import Path

import pytest

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository
from tests.test_native_reset_capture_v2 import reset_events
from tests.test_visual_raw_recorder_v3 import recorder_fixture


def api():
    name = "cloud_edge_robot_arm.research.native_clock_publication_v2"
    assert util.find_spec(name), "startup-owned prefix publisher is missing"
    return import_module(name)


def application(tmp_path):
    module = api()
    tmp_path.mkdir(parents=True, exist_ok=True)
    config = tmp_path / "policy.json"
    source = Path(__file__).resolve().parents[1] / "configs/research/native_clock_authority_v2.json"
    config.write_bytes(source.read_bytes())
    return module.NativeClockPrefixApplicationV2.from_startup(config, output=tmp_path / "app")


def activate(app):
    repo = app.repository
    job = app.prepare_once()
    lease = repo.acquire_lease(
        worker_id=app.worker.worker_id, backend="MUJOCO", lease_ttl_seconds=60
    )
    assert lease is not None
    repo.start_attempt(job.job_id, worker_id=app.worker.worker_id)
    for old, new in (
        (RuntimeJobStatus.LEASED, RuntimeJobStatus.STARTING),
        (RuntimeJobStatus.STARTING, RuntimeJobStatus.RUNNING),
    ):
        assert repo.update_status_cas(
            job.job_id,
            expected=old,
            next_status=new,
            reason_code="SOFTWARE_ONLY",
            worker_id=lease.worker_id,
            lease_id=lease.lease_id,
            expected_lease_id=lease.lease_id,
        )
    start = time.monotonic()
    app.worker.active_job_id = job.job_id
    app.worker._active_task_origin = (job.job_id, start, datetime.now(UTC))
    current = repo.get_job(job.job_id)
    app.check_worker(app.worker, current, start_monotonic=start)
    return current, lease, start


def owned_recorder(app, tmp_path):
    _, backend, capture, executor, *_ = recorder_fixture(tmp_path / "fixtures")
    backend._config = SimulatorConfig(render_rgb=True, render_depth=True, seed=app.config["seed"])
    rec = import_module(
        "cloud_edge_robot_arm.research.native_reset_capture_v2"
    ).VisualResetClockRecorderV2.from_worker_owner(
        app,
        None,
        backend,
        capture,
        executor,
        clock_source=app.clock_source,
        directory=app.output / "prefix-originals",
    )
    return rec, backend


def test_startup_factory_has_no_job_effect_and_current_real_lease_seals_capture(tmp_path):
    app = application(tmp_path)
    assert app.repository.list_jobs() == []
    assert app.worker.planner_factory is None and app.worker.visual_role_binding is None
    with pytest.raises(RuntimeError):
        owned_recorder(app, tmp_path)
    job, lease, _ = activate(app)
    assert app.check_active()["attempt"] == 1
    rec, _ = owned_recorder(app, tmp_path)
    assert app.check_recorder(rec)["lease_id"] == lease.lease_id
    assert job.max_attempts == 1
    with pytest.raises(RuntimeError):
        app.prepare_once()


@pytest.mark.parametrize("replacement", ["copied_app", "foreign_worker", "foreign_repository"])
def test_public_copies_cannot_substitute_live_application_objects(tmp_path, replacement):
    app = application(tmp_path)
    job, _, start = activate(app)
    if replacement == "copied_app":
        copied = copy.copy(app)
        with pytest.raises((RuntimeError, ValueError, TypeError)):
            api().ApplicationClockSourceV2.from_application(copied)
    elif replacement == "foreign_worker":
        with pytest.raises((RuntimeError, ValueError, TypeError)):
            app.check_worker(copy.copy(app.worker), job, start_monotonic=start)
    else:
        app.repository = SQLiteSimulationJobRepository(app.repository.database_path)
        with pytest.raises((RuntimeError, ValueError, TypeError)):
            app.check_active()


def test_source_only_registry_rejects_expired_lease_and_changed_original_policy(tmp_path):
    app = application(tmp_path)
    _, lease, _ = activate(app)
    app.repository.release_lease(lease.lease_id)
    with pytest.raises(ValueError):
        app.check_active()
    other = application(tmp_path / "second")
    activate(other)
    other.config_path.write_bytes(other.config_path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        other.check_active()


def test_unbound_failed_prefix_publishes_complete_original_inventory_without_utc(tmp_path):
    app = application(tmp_path)
    activate(app)
    rec, backend = owned_recorder(app, tmp_path)
    with rec:
        reset_events(rec, backend)
        rec.freeze_unbound_prefix()
        receipt = api().publish_reset_clock_capture_v2(rec, application=app)
        assert receipt["publication_scope"] == "LIVE_APPLICATION_SOURCE_ONLY"
        assert receipt["raw_source_binding"] == "UNBOUND"
        assert receipt["prefix_complete"] is False  # 0 of required120 SETTLE rows
        assert receipt["native_utc"] == receipt["current_time_utc"] == "UNAVAILABLE"
        assert receipt["issuer_accuracy"] == "UNVERIFIED"
        assert receipt["role_validation"] == "UNAVAILABLE"
        assert receipt["independent_calibration_group"] is False
        view = api().verify_reset_clock_originals_v2(rec.directory, receipt)
        assert view["original_integrity"] == "VERIFIED"
        assert view["prefix_complete"] is False and view["native_utc"] == "UNAVAILABLE"
        public = app.catalog_entry()
        public["file_hashes"].clear()
        assert app.catalog_entry()["file_hashes"]
        with pytest.raises(RuntimeError):
            api().publish_reset_clock_capture_v2(rec, application=app)
    assert (rec.directory / "reset-journal.json").is_file()
    (rec.directory / "clock-pairs.json").write_text("[]\n")
    view = api().verify_reset_clock_originals_v2(rec.directory, receipt)
    assert view["original_integrity"] == "INVALID" and view["reasons"]


def test_current_original_assignment_and_formal_config_changes_reject(tmp_path):
    app = application(tmp_path)
    activate(app)
    with app.repository._connect() as connection:
        connection.execute("UPDATE simulation_jobs SET draft_json = ?", ("{}",))
    with pytest.raises(ValueError):
        app.check_active()
    other = application(tmp_path / "second")
    activate(other)
    rec, backend = owned_recorder(other, tmp_path / "second")
    backend._config = backend._config.model_copy(update={"camera_width": 640})
    with pytest.raises(ValueError):
        other.check_recorder(rec)


def test_off_callback_bounded_exchange_saves_real_wire_failure_originals(tmp_path, monkeypatch):
    app = application(tmp_path)
    activate(app)
    rec, backend = owned_recorder(app, tmp_path)
    source = app.clock_source
    calls = []
    fixture = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "tools/research/native-clock-v2/testdata/software-only-exchange.json"
        ).read_text()
    )
    import base64

    def wrong_issuer_response(request, config, *, attempt):
        calls.append(request)
        start = time.monotonic_ns()
        return base64.b64decode(fixture["response_b64"]), {
            name: start + i
            for i, name in enumerate(
                ("send_before_ns", "send_after_ns", "receive_before_ns", "receive_after_ns")
            )
        }

    monkeypatch.setattr(api(), "_udp_exchange_v2", wrong_issuer_response)
    with rec:
        backend._in_observer_callback = True
        with pytest.raises(RuntimeError):
            source.exchange(
                domain=rec._clock_domain_id,
                exchange_id="A",
                commitment=bytes(32),
                previous_reply=b"",
            )
        backend._in_observer_callback = False
        result = source.exchange(
            domain=rec._clock_domain_id, exchange_id="A", commitment=bytes(32), previous_reply=b""
        )
        assert result is None and len(calls) == 1
        attempt = app.exchange_attempts[0]
        assert attempt["request_b64"] and attempt["response_b64"]
        assert attempt["verified_before_ns"] <= attempt["verified_after_ns"]
        assert attempt["status"] == "UNAVAILABLE" and attempt["error"]
        with pytest.raises(RuntimeError):
            source.exchange(
                domain=rec._clock_domain_id,
                exchange_id="A",
                commitment=bytes(32),
                previous_reply=b"",
            )
        with pytest.raises(RuntimeError):
            source.exchange(
                domain=rec._clock_domain_id,
                exchange_id="B",
                commitment=bytes(32),
                previous_reply=b"",
            )
        public = app.exchange_attempts
        public.clear()
        assert len(app.exchange_attempts) == 1
        rec.freeze_unbound_prefix()


def test_actual_asset_substitution_and_non_native_recorder_copies_cannot_publish(tmp_path):
    app = application(tmp_path)
    activate(app)
    rec, backend = owned_recorder(app, tmp_path)
    with pytest.raises(ValueError):
        app.check_recorder(copy.copy(rec))
    backend._mjspec_xml_sha256 = "0" * 64
    with pytest.raises(ValueError):
        app.check_recorder(rec)


def test_failed_capture_stays_in_prefix_denominator_even_with_120_physics_rows(
    tmp_path, monkeypatch
):
    from tests.test_native_clock_prefix_worker_v2 import software_components

    app = application(tmp_path)
    _, backend = software_components(monkeypatch, app)
    original_step = backend.step

    def inject_failed_cached_capture(*, steps):
        original_step(steps=steps)
        rec = backend._operation_observer.__self__
        from tests.test_native_reset_capture_v2 import event

        rec._on_boundary(event("CAPTURE", "BEGIN", op=900, step=120))
        rec._on_boundary(
            event("CAPTURE", "END", op=900, step=120, error="SOFTWARE_ONLY cached failure")
        )

    backend.step = inject_failed_cached_capture
    receipt = app.execute_once()
    assert receipt["cached_capture_allocations"] == 2
    assert receipt["prefix_complete"] is False
    assert app.repository.list_jobs()[0].status == RuntimeJobStatus.FAILED


def test_public_verifier_copy_cannot_replace_the_startup_issued_verifier(tmp_path):
    app = application(tmp_path)
    activate(app)
    app.clock_source.verifier = copy.copy(app.clock_source.verifier)
    with pytest.raises(ValueError):
        app.check_active()


def test_catalog_write_failure_never_exposes_a_live_publication_and_keeps_raw(
    tmp_path, monkeypatch
):
    from tests.test_native_clock_prefix_worker_v2 import software_components

    app = application(tmp_path)
    software_components(monkeypatch, app)
    original = api()._write_original

    def fail_catalog(directory, name, value):
        if name == "capture-catalog.json":
            raise OSError("SOFTWARE_ONLY catalog write failed")
        return original(directory, name, value)

    monkeypatch.setattr(api(), "_write_original", fail_catalog)
    with pytest.raises(RuntimeError, match="no live source-only publication"):
        app.execute_once()
    assert (app.output / "prefix-originals/reset-journal.json").is_file()
    assert (app.output / "prefix-originals/publication-failure.json").is_file()
    assert app.repository.list_jobs()[0].status == RuntimeJobStatus.BLOCKED_BY_ENV
