"""Task1 CPU registry/SQLite facts; no source verdict or worker dispatch."""

import copy
import hashlib
import json
import pickle
import time
from dataclasses import asdict
from datetime import UTC, datetime
from importlib import import_module, util
from pathlib import Path

import pytest

from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository

ROOT = Path(__file__).resolve().parents[1]


def api():
    name = "cloud_edge_robot_arm.research.operational_prefix_v1"
    assert util.find_spec(name), "Task1 operational prefix interface is missing"
    return import_module(name)


def application(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    config = tmp_path / "policy.json"
    config.write_bytes((ROOT / "configs/research/operational_prefix_v1.json").read_bytes())
    return api().OperationalPrefixApplicationV1.from_startup(config, output=tmp_path / "app")


def activate(app):
    """Real repository transitions, with a CPU-only worker origin fixture."""
    job = app.prepare_once()
    repo = app.repository
    lease = repo.acquire_lease(
        worker_id=app.worker.worker_id, backend="MUJOCO", lease_ttl_seconds=60
    )
    assert lease is not None
    repo.start_attempt(job.job_id, worker_id=lease.worker_id)
    for old, new in (
        (RuntimeJobStatus.LEASED, RuntimeJobStatus.STARTING),
        (RuntimeJobStatus.STARTING, RuntimeJobStatus.RUNNING),
    ):
        assert repo.update_status_cas(
            job.job_id,
            expected=old,
            next_status=new,
            reason_code="OC2_TASK1_CPU",
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


def test_startup_exact_registry_and_once_only(tmp_path):
    app = application(tmp_path)
    assert type(app.repository) is SQLiteSimulationJobRepository
    assert app.repository.list_jobs() == []
    with pytest.raises(RuntimeError):
        app.check_active()
    job, lease, _ = activate(app)
    state = app.check_active()
    assert state["job_id"] == job.job_id and state["lease_id"] == lease.lease_id
    assert state["attempt"] == job.max_attempts == 1
    assert state["lease_clock_migration"] == "NOT_DONE_OC3"
    with pytest.raises(RuntimeError):
        app.prepare_once()
    # An already allocated active assignment cannot be dispatched as a second run.
    with pytest.raises(RuntimeError, match="cannot be retried or reallocated"):
        app.execute_once()
    with pytest.raises(RuntimeError, match="twice"):
        app.execute_once()
    assert len(app.repository.list_jobs()) == len(app.repository.list_attempts(job.run_id)) == 1
    assert not (app.output / "prefix-originals").exists()
    with pytest.raises(RuntimeError):
        app.catalog_entry()


@pytest.mark.parametrize("operation", [copy.copy, copy.deepcopy, pickle.dumps])
def test_live_application_cannot_copy_or_serialize(tmp_path, operation):
    app = application(tmp_path)
    job, lease, start = activate(app)
    app.check_worker(app.worker, job, start_monotonic=start)
    healthy = app.check_active()
    assert healthy["job_id"] == job.job_id and healthy["lease_id"] == lease.lease_id
    assert healthy["attempt"] == 1
    reason = {
        copy.copy: "live operational application cannot be copied",
        copy.deepcopy: "live operational application cannot be deep-copied",
        pickle.dumps: "live operational application cannot be serialized",
    }[operation]
    with pytest.raises(RuntimeError, match=reason):
        operation(app)
    forged = object.__new__(type(app))
    for name in ("repository", "worker", "output", "config_path"):
        setattr(forged, name, getattr(app, name))
    with pytest.raises(RuntimeError, match="exact startup-owned private application required"):
        forged.check_active()


@pytest.mark.parametrize(
    "replacement",
    ["worker", "repository", "origin", "assignment", "cancel", "released", "duplicate_attempt"],
)
def test_worker_authority_is_not_counter_descriptor(tmp_path, replacement):
    app = application(tmp_path)
    job, lease, start = activate(app)
    app.check_worker(app.worker, job, start_monotonic=start)
    healthy = app.check_active()
    assert healthy["job_id"] == job.job_id and healthy["lease_id"] == lease.lease_id
    assert healthy["worker_id"] == app.worker.worker_id and healthy["attempt"] == 1
    from cloud_edge_robot_arm.research.operational_time_v1 import open_operational_clock

    owner = open_operational_clock()
    assert owner.domain.worker_authority == owner.domain.lease_authority == "UNAVAILABLE"
    with pytest.raises(ValueError, match="current exact configured worker/assignment required"):
        app.check_worker(asdict(owner.domain), job, start_monotonic=start)
    if replacement == "worker":
        app.worker = copy.copy(app.worker)
    elif replacement == "repository":
        app.repository = SQLiteSimulationJobRepository(app.repository.database_path)
    elif replacement == "origin":
        app.worker._active_task_origin = (job.job_id, start + 1, datetime.now(UTC))
    elif replacement == "assignment":
        with app.repository._connect() as conn:
            conn.execute(
                "UPDATE simulation_jobs SET max_attempts = 2 WHERE job_id = ?", (job.job_id,)
            )
    elif replacement == "cancel":
        app.repository.request_cancel(job.job_id)
    elif replacement == "released":
        app.repository.release_lease(lease.lease_id)
    else:
        app.repository.start_attempt(job.job_id, worker_id=app.worker.worker_id)
    reasons = {
        "worker": "actual private application/repository/worker identity changed",
        "repository": "actual private application/repository/worker identity changed",
        "origin": "original live worker task/assignment changed",
        "assignment": "original operational assignment changed",
        "cancel": "worker job identity/status/lease source invalid",
        "released": "unique live job lease required",
        "duplicate_attempt": "unique open job attempt required",
    }
    with pytest.raises(ValueError, match=reasons[replacement]):
        app.check_active()
    if replacement in {"worker", "repository"}:
        with pytest.raises(ValueError, match=reasons[replacement]):
            app.catalog_entry()
    else:
        # This stub refusal records zero publication, not source rejection.
        with pytest.raises(RuntimeError, match="no live operational source-only publication"):
            app.catalog_entry()


def test_not_running_or_missing_attempt_cannot_establish_source(tmp_path):
    app = application(tmp_path)
    job = app.prepare_once()
    lease = app.repository.acquire_lease(
        worker_id=app.worker.worker_id, backend="MUJOCO", lease_ttl_seconds=60
    )
    start = time.monotonic()
    app.worker.active_job_id = job.job_id
    app.worker._active_task_origin = (job.job_id, start, datetime.now(UTC))
    with pytest.raises(ValueError):
        app.check_worker(app.worker, app.repository.get_job(job.job_id), start_monotonic=start)
    assert lease is not None and app.repository.list_attempts(job.run_id) == []


@pytest.mark.parametrize(
    "extra",
    [
        "backend",
        "clock_owner",
        "repository",
        "pid",
        "preregistered",
        "group_inventory",
        "worker_authority",
    ],
)
def test_startup_factory_rejects_caller_authority_kwargs(tmp_path, extra):
    with pytest.raises(TypeError):
        api().OperationalPrefixApplicationV1.from_startup(
            ROOT / "configs/research/operational_prefix_v1.json",
            output=tmp_path / "app",
            **{extra: True},
        )
    assert not (tmp_path / "app").exists()


def test_startup_rejects_existing_or_symlink_output(tmp_path):
    existing = tmp_path / "existing"
    existing.mkdir()
    original = existing / "keep.bin"
    original.write_bytes(b"original")
    linked = tmp_path / "linked"
    linked.symlink_to(existing, target_is_directory=True)
    for output in (existing, linked, linked / "fresh"):
        with pytest.raises(ValueError):
            api().OperationalPrefixApplicationV1.from_startup(
                ROOT / "configs/research/operational_prefix_v1.json", output=output
            )
    assert original.read_bytes() == b"original" and not (existing / "fresh").exists()


class CpuBackend:
    """Raw backend construction double; no initialize/reset/step/capture methods."""


def test_preregistration_real_join_exact_handles_and_zero_source_events(tmp_path, monkeypatch):
    module = api()
    app = application(tmp_path)
    job, lease, start = activate(app)
    backend = CpuBackend()
    monkeypatch.setattr(module, "_new_prefix_backend_v1", lambda: backend)
    context = module._prepare_source_v1(app, app.worker, job, start_monotonic=start)
    prereg_path = app.output / "prefix-originals/preregistration.json"
    original = prereg_path.read_bytes()
    prereg = json.loads(original)
    assert context.backend is backend
    assert context.capture._backend is context.executor._robot._backend is backend
    assert context.capture._owns_backend is False
    assert prereg["worker_source"]["lease_id"] == lease.lease_id
    assert prereg["worker_source"]["attempt"] == 1
    assert prereg["group_inventory"]["support_group_count"] == 0
    assert prereg["group_inventory"]["independence"] == "UNESTABLISHED"
    assert prereg["clock_domain"]["worker_authority"] == "UNAVAILABLE"
    assert prereg["limits"]["formal_accepted"] is False
    assert (
        module._check_source_v1(app).preregistration_sha256 == hashlib.sha256(original).hexdigest()
    )
    assert not context.capture._open
    assert not hasattr(backend, "operation_ledger")
    with pytest.raises(RuntimeError):
        module._prepare_source_v1(app, app.worker, job, start_monotonic=start)
    context.capture._backend = CpuBackend()
    with pytest.raises(ValueError):
        module._check_source_v1(app)
    assert prereg_path.read_bytes() == original
    with pytest.raises(RuntimeError):
        app.catalog_entry()


def test_changed_policy_rejects_before_preregistration(tmp_path, monkeypatch):
    app = application(tmp_path)
    job, _, start = activate(app)
    original = app.config_path.read_bytes()
    app.config_path.write_bytes(original + b" ")
    monkeypatch.setattr(api(), "_new_prefix_backend_v1", lambda: pytest.fail("source allocated"))
    with pytest.raises(ValueError):
        api()._prepare_source_v1(app, app.worker, job, start_monotonic=start)
    assert not (app.output / "prefix-originals").exists()


def test_preregistration_write_failure_preserves_original_and_no_retry(tmp_path, monkeypatch):
    app = application(tmp_path)
    job, _, start = activate(app)
    monkeypatch.setattr(api(), "_new_prefix_backend_v1", CpuBackend)
    root = app.output / "prefix-originals"
    root.mkdir()
    existing = root / "preregistration.json"
    existing.write_bytes(b"frozen prior failed allocation")
    with pytest.raises((OSError, ValueError, RuntimeError)):
        api()._prepare_source_v1(app, app.worker, job, start_monotonic=start)
    assert existing.read_bytes() == b"frozen prior failed allocation"
    with pytest.raises(RuntimeError):
        api()._prepare_source_v1(app, app.worker, job, start_monotonic=start)
    failure = json.loads((app.output / "startup-failures.json").read_text())
    assert len(failure) == 1 and failure[0]["phase"] == "preregistration"
    with pytest.raises(RuntimeError):
        app.catalog_entry()
