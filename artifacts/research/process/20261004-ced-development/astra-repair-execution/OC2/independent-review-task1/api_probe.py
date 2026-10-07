"""One bounded independent Task1 probe; raw backend seam only, never a verdict mock."""
from __future__ import annotations
import copy
import hashlib
import json
import tempfile
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from cloud_edge_robot_arm.research import operational_prefix_v1 as api
from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository

ROOT = Path.cwd()
WORK = Path(tempfile.mkdtemp(prefix="bigsmall-oc2-independent-task1-"))
OBSERVATIONS = []
APPS = []

class RawCpuBackend:
    """Construction replacement has no event/initialize/reset/step/capture interface."""


def record(name, **facts):
    OBSERVATIONS.append({"scenario": name, "status": "PASS", **facts})


def reject(name, exception_type, message, call):
    try:
        call()
    except exception_type as error:
        if message is not None and str(error) != message:
            raise AssertionError(f"{name}: exact rejection message differs: {str(error)!r}") from error
        record(name, exception_type=type(error).__name__, message=str(error))
    else:
        raise AssertionError(f"{name}: rejection did not occur")


def app_in(label):
    base = WORK / label
    base.mkdir()
    config = base / "policy.json"
    config.write_bytes((ROOT / "configs/research/operational_prefix_v1.json").read_bytes())
    app = api.OperationalPrefixApplicationV1.from_startup(config, output=base / "application")
    if type(app.repository) is not SQLiteSimulationJobRepository:
        raise AssertionError("real exact SQLite repository required")
    APPS.append(app)
    return app


def activate(app):
    job = app.prepare_once()
    lease = app.repository.acquire_lease(worker_id=app.worker.worker_id, backend="MUJOCO", lease_ttl_seconds=60)
    if lease is None:
        raise AssertionError("real lease allocation missing")
    attempt = app.repository.start_attempt(job.job_id, worker_id=lease.worker_id)
    for old, new in [(RuntimeJobStatus.LEASED, RuntimeJobStatus.STARTING), (RuntimeJobStatus.STARTING, RuntimeJobStatus.RUNNING)]:
        changed = app.repository.update_status_cas(job.job_id, expected=old, next_status=new,
            reason_code="INDEPENDENT_OC2_TASK1_CPU", worker_id=lease.worker_id, lease_id=lease.lease_id,
            expected_lease_id=lease.lease_id)
        if changed is None:
            raise AssertionError("real RUNNING transition missing")
    origin = time.monotonic()
    app.worker.active_job_id = job.job_id
    app.worker._active_task_origin = (job.job_id, origin, datetime.now(UTC))
    job = app.repository.get_job(job.job_id)
    app.check_worker(app.worker, job, start_monotonic=origin)
    state = app.check_active()
    if state["job_id"] != job.job_id or state["lease_id"] != lease.lease_id or state["attempt"] != 1:
        raise AssertionError("healthy current job/lease/attempt join differs")
    return job, lease, origin, state


def main():
    app = app_in("healthy-and-identity")
    reject("not-yet-running", RuntimeError, "actual RUNNING assignment/lease/origin not established", app.check_active)
    job, lease, start, healthy = activate(app)
    record("healthy-real-worker-and-lease", worker_source=healthy,
        actual_dispatch=0, temporary_worker_origin_fixture=True)
    reject("once-only-prepare", RuntimeError, "operational assignment cannot be retried or reallocated", app.prepare_once)
    reject("foreign-worker-argument", ValueError, "current exact configured worker/assignment required",
        lambda: app.check_worker(copy.copy(app.worker), job, start_monotonic=start))
    old_worker = app.worker
    app.worker = copy.copy(old_worker)
    reject("foreign-exact-looking-worker-field", ValueError,
        "actual private application/repository/worker identity changed", app.check_active)
    app.worker = old_worker
    old_repo = app.repository
    app.repository = SQLiteSimulationJobRepository(old_repo.database_path)
    reject("foreign-same-db-repository-object", ValueError,
        "actual private application/repository/worker identity changed", app.check_active)
    app.repository = old_repo
    forged = object.__new__(type(app))
    for name in ("repository", "worker", "output", "config_path"):
        setattr(forged, name, getattr(app, name))
    reject("foreign-reconstructed-private-app", RuntimeError,
        "exact startup-owned private application required", forged.check_active)
    reject("copy-live-application", RuntimeError, "live operational application cannot be copied", lambda: copy.copy(app))
    old_origin = app.worker._active_task_origin
    app.worker._active_task_origin = None
    reject("missing-live-worker-origin", ValueError,
        "original live worker task/assignment changed", app.check_active)
    app.worker._active_task_origin = old_origin
    reject("caller-now-injection", TypeError, None, lambda: app.check_active(now=datetime.now(UTC)))
    raw_backend = RawCpuBackend()
    original_constructor = api._new_prefix_backend_v1
    api._new_prefix_backend_v1 = lambda: raw_backend
    try:
        context = api._prepare_source_v1(app, app.worker, job, start_monotonic=start)
    finally:
        api._new_prefix_backend_v1 = original_constructor
    original = (context.directory / "preregistration.json").read_bytes()
    prereg = json.loads(original)
    if context.backend is not raw_backend or context.capture._backend is not raw_backend or context.executor._robot._backend is not raw_backend:
        raise AssertionError("real borrowed capture/executor exact backend join differs")
    if context.capture._open or context.capture._owns_backend or context.owner._events or context.owner._receipts:
        raise AssertionError("source event/capture effect before prereg")
    if any(hasattr(raw_backend, name) for name in ["initialize", "reset", "step", "capture", "observe_operation_boundaries", "operation_ledger"]):
        raise AssertionError("raw CPU seam acquired source operations")
    if prereg["worker_source"]["lease_id"] != lease.lease_id or prereg["group_inventory"]["support_group_count"] != 0:
        raise AssertionError("prereg actual lease or support-group boundary differs")
    if api._check_source_v1(app) is not context:
        raise AssertionError("healthy source exact identity missing")
    record("healthy-prereg-real-borrowed-handles-no-source-event",
        preregistration_sha256=hashlib.sha256(original).hexdigest(), preregistration_bytes=len(original),
        directory=str(context.directory), owner_events=0, capture_open=False, support_groups=0,
        worker_authority=context.owner.domain.worker_authority,
        lease_authority=context.owner.domain.lease_authority, native_authority=context.owner.domain.native_authority)
    if any(getattr(context.owner.domain, key) != "UNAVAILABLE" for key in ["worker_authority", "lease_authority", "native_authority"]):
        raise AssertionError("OC1 descriptor unexpectedly carries authority")
    reject("counter-descriptor-cannot-act-as-worker", ValueError,
        "current exact configured worker/assignment required",
        lambda: app.check_worker(asdict(context.owner.domain), job, start_monotonic=start))
    reject("source-allocation-cannot-repeat", RuntimeError,
        "operational source/preregistration cannot be allocated twice",
        lambda: api._prepare_source_v1(app, app.worker, job, start_monotonic=start))
    context.capture._backend = RawCpuBackend()
    reject("foreign-borrowed-capture-backend", ValueError,
        "original source/backend/capture/executor/OC1 handles changed", lambda: api._check_source_v1(app))
    if (context.directory / "preregistration.json").read_bytes() != original:
        raise AssertionError("original preregistration changed during rejection")
    app.repository.request_cancel(job.job_id)
    reject("real-cancelled-lease-source", ValueError,
        "worker job identity/status/lease source invalid", app.check_active)
    # These are only the Task2 boundary. They are deliberately not authority counterexamples.
    reject("catalog-stub-boundary-not-authority-case", RuntimeError,
        "no live operational source-only publication in Task1", app.catalog_entry)
    reject("execute-stub-boundary-not-authority-case", RuntimeError,
        "Task2 worker dispatch is not implemented or authorized in Task1", app.execute_once)
    reject("execute-once-consumed", RuntimeError,
        "operational process cannot execute twice", app.execute_once)
    failed_app = app_in("failed-preregistration")
    failed_job, failed_lease, failed_start, _ = activate(failed_app)
    prior_dir = failed_app.output / "prefix-originals"
    prior_dir.mkdir()
    prior_file = prior_dir / "preregistration.json"
    sentinel = b"independent failed-allocation original; must stay byte-for-byte"
    prior_file.write_bytes(sentinel)
    original_constructor = api._new_prefix_backend_v1
    api._new_prefix_backend_v1 = RawCpuBackend
    try:
        reject("exclusive-preregistration-failure", FileExistsError, None,
            lambda: api._prepare_source_v1(failed_app, failed_app.worker, failed_job, start_monotonic=failed_start))
    finally:
        api._new_prefix_backend_v1 = original_constructor
    failures = json.loads((failed_app.output / "startup-failures.json").read_bytes())
    failed_context = api._REGISTRY[failed_app].source
    if prior_file.read_bytes() != sentinel or len(failures) != 1 or failures[0]["phase"] != "preregistration":
        raise AssertionError("failed allocation denominator/original not preserved")
    if failed_context.capture._open or failed_context.owner._events or failed_context.owner._receipts:
        raise AssertionError("failed preregistration triggered a source event")
    record("failed-preregistration-original-and-denominator-preserved", failed_allocations=1,
        failure_original=failures, prior_sha256=hashlib.sha256(sentinel).hexdigest(), prior_bytes=len(sentinel),
        source_events=0, capture_open=False)
    reject("failed-source-no-retry", RuntimeError,
        "operational source/preregistration cannot be allocated twice",
        lambda: api._prepare_source_v1(failed_app, failed_app.worker, failed_job, start_monotonic=failed_start))
    databases = []
    for actual_app in APPS:
        with actual_app.repository._connect() as conn:
            counts = {table:int(conn.execute("SELECT COUNT(*) FROM " + table).fetchone()[0])
                for table in ["simulation_jobs", "simulation_job_leases", "simulation_job_attempts"]}
        databases.append({"path":str(actual_app.repository.database_path),"rows":counts})
    return {"status":"PASS_SCOPED_CPU_PROBE_OC2_TASK1", "probe_runs":1,
        "scenario_count":len(OBSERVATIONS), "observations":OBSERVATIONS, "work_root":str(WORK),
        "temporary_databases":databases, "source_allocation_denominator":2,
        "successful_preregistrations":1, "failed_preregistrations":1,
        "execution":{"worker_dispatch":0,"source_events":0,"source_positive":0,"catalog_publication":0,
            "actual":0,"backend_initialize":0,"physics":0,"renderer":0,"camera":0,"network":0,"model":0},
        "fixture_scope":"real temporary SQLite/lease/attempt plus CPU-only worker origin; sole raw backend construction replacement; no final-verdict mocks",
        "do_not_add_to_author_40":True}

try:
    RESULT = main()
except BaseException as error:
    print(json.dumps({"status":"REQUEST_NEXT_ASTRA_PLAN", "probe_runs":1,
        "completed_observation_count":len(OBSERVATIONS), "observations":OBSERVATIONS,
        "unexpected_error_type":type(error).__name__, "unexpected_error":str(error),
        "work_root":str(WORK)},ensure_ascii=False))
    raise
else:
    print(json.dumps(RESULT,ensure_ascii=False))
