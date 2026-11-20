"""CPU-only fixture using the frozen whole-action inputs and actual worker poll."""

import argparse
import json
import resource
import sqlite3
import threading
from collections import Counter
from contextlib import ExitStack, contextmanager, nullcontext
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import cloud_edge_robot_arm.research.native_collection_application as application
from cloud_edge_robot_arm.research.native_action_timing import use_action_timing
from cloud_edge_robot_arm.research.operational_time_v1 import open_operational_clock
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus

RELEASE = Path(
    "experiments/results/phase9/p0-first-teacher-20261119/whole-action-egl-development-20261120/release"
)
registration_bytes = (RELEASE / "protocol.json").read_bytes()
registration = json.loads(registration_bytes)
startup_bytes = (RELEASE / "run/startup.json").read_bytes()
startup = json.loads(startup_bytes)


def summary(samples):
    return dict(
        count=len(samples),
        mean_ns=sum(samples) / len(samples),
        p50_ns=median(samples),
        p95_ns=sorted(samples)[int(0.95 * (len(samples) - 1))],
    )


def run(count, trace, variant):
    totals = Counter()
    calls = Counter()

    def wrap(name, func):
        def tracked(*args, **kwargs):
            before = perf_counter_ns()
            try:
                return func(*args, **kwargs)
            finally:
                totals[name] += perf_counter_ns() - before
                calls[name] += 1

        return tracked

    @contextmanager
    def measure(name, cm):
        enter = perf_counter_ns()
        with cm:
            elapsed = perf_counter_ns() - enter
            try:
                yield
            finally:
                leave = perf_counter_ns()
        totals[name] += elapsed + perf_counter_ns() - leave
        calls[name] += 1

    with TemporaryDirectory(prefix="bigsmall-state-") as root:
        app = application.NativeCollectionApplication._create(
            RELEASE,
            registration["assignment_id"],
            Path(root) / "run",
            registration["recipe"],
            diagnostic=application._CheckpointDiagnostic(
                registration_sha256=application.digest(registration),
                whole_action=True,
            ),
        )
        live = application._live(app)
        repo = live.repository
        live.owner = open_operational_clock()
        live.origin_token = live.owner.begin_event("COLLECTION_TASK_ORIGIN")
        live.owner.mark_event(live.origin_token)
        live.origin = live.owner.end_event(live.origin_token)
        job_basis = {k: v for k, v in startup["job_basis"].items() if k != "job_id"}
        live.deadline = live.owner.start_deadline(
            task_key=live.assignment_id,
            origin=live.origin,
            budget_ns=job_basis["timeout_seconds"] * 10**9,
        )
        live.issued_at = datetime.now(UTC)
        job = repo.create_job(
            batch_id="",
            provenance=dict(
                scope=registration["scope"],
                protocol_sha256=startup["protocol_sha256"],
            ),
            **job_basis,
        )
        live.job_id, live.job_basis = job.job_id, application._job_basis(job)
        assert repo.update_status_cas(
            job.job_id,
            expected=RuntimeJobStatus.CREATED,
            next_status=RuntimeJobStatus.QUEUED,
            reason_code="software fixture",
            worker_id="",
            lease_id="",
        )

        def body(self, worker, current, *, start_monotonic):
            assert worker._frozen_operational_time_mode == "UTC_LEGACY_VETO"
            assert repo.get_job(current.job_id).status == RuntimeJobStatus.RUNNING
            live.worker_origin = worker._active_task_origin
            live.backend = MuJoCoPhysicsBackend()
            config = SimulatorConfig(
                render_rgb=True,
                render_depth=True,
                physics_dt_s=1 / 240,
                seed=job.seed,
                model_path=self.policy["model_path"],
                domain_randomization=False,
            )
            live.backend._config = config
            live.config_json = application.canonical(config.model_dump(mode="json"))
            assert live.backend.total_physics_steps == 0
            if variant == "dynamic-limits":
                live.guard_limits = None
            live.diagnostic.start_action(perf_counter_ns(), 0)
            props = type(self).protocol
            settings = type(self).policy
            runtime_repo = type(repo)
            original_read = repo._teacher_checkpoint_read
            original_json_loads = json.loads
            original_connect = sqlite3.connect
            body_thread = threading.get_ident()

            def loads(data, *args, **kwargs):
                if data is live.protocol_json:
                    return wrap("frozen_protocol_decode", original_json_loads)(
                        data, *args, **kwargs
                    )
                return original_json_loads(data, *args, **kwargs)

            def connect(*args, **kwargs):
                if threading.get_ident() != body_thread:
                    return original_connect(*args, **kwargs)
                connection = wrap("sqlite_connect", original_connect)(*args, **kwargs)

                def sql_trace(statement):
                    words = statement.split()
                    kind = words[0].upper()
                    if kind == "SELECT":
                        kind += ":" + words[words.index("FROM") + 1] if "FROM" in words else ""
                    calls["sql:" + kind] += 1

                connection.set_trace_callback(sql_trace)
                return connection

            with ExitStack() as stack:
                stack.enter_context(use_action_timing(live.action_timing))
                if trace:
                    stack.enter_context(
                        patch.multiple(
                            runtime_repo,
                            get_job=wrap("get_job", runtime_repo.get_job),
                            list_attempts=wrap("list_attempts", runtime_repo.list_attempts),
                            list_leases=wrap("list_leases", runtime_repo.list_leases),
                            _teacher_checkpoint_database=wrap(
                                "database_identity",
                                runtime_repo._teacher_checkpoint_database,
                            ),
                        )
                    )
                    stack.enter_context(
                        patch.object(
                            type(self),
                            "protocol",
                            property(wrap("protocol_accessor", props.fget)),
                        )
                    )
                    stack.enter_context(
                        patch.object(
                            type(self),
                            "policy",
                            property(wrap("policy_accessor", settings.fget)),
                        )
                    )
                    stack.enter_context(
                        patch.object(
                            repo,
                            "_teacher_checkpoint_read",
                            lambda db: measure("snapshot_enter_exit", original_read(db)),
                        )
                    )
                    stack.enter_context(patch.object(sqlite3, "connect", connect))
                    stack.enter_context(patch.object(json, "loads", loads))
                    stack.enter_context(
                        patch.object(
                            application,
                            "_job_basis",
                            wrap("job_basis", application._job_basis),
                        )
                    )
                    stack.enter_context(
                        patch.object(
                            SimulatorConfig,
                            "model_dump",
                            wrap("backend_dump", SimulatorConfig.model_dump),
                        )
                    )
                    clock = type(live.owner)
                    stack.enter_context(
                        patch.multiple(
                            clock,
                            read_current=wrap("owner_read_current", clock.read_current),
                            before_deadline=wrap("owner_before_deadline", clock.before_deadline),
                        )
                    )
                samples = []
                cpu_start = process_time_ns()
                for _ in range(count):
                    began = perf_counter_ns()
                    self.check_active()
                    samples.append(perf_counter_ns() - began)
                cpu_ns = process_time_ns() - cpu_start
            print(
                json.dumps(
                    dict(
                        count=count,
                        wall=summary(samples),
                        cpu_ns=cpu_ns,
                        instrumentation=trace,
                        variant=variant,
                        component_inclusive_ns=dict(totals),
                        calls=dict(calls),
                        sqlite_action_ns=live.diagnostic.action_read_wall_ns,
                        sqlite_action_reads=live.diagnostic.action_reads_completed,
                        operational_mode=worker._frozen_operational_time_mode,
                        registration_sha256=sha256(registration_bytes).hexdigest(),
                        startup_sha256=sha256(startup_bytes).hexdigest(),
                        protocol_bytes=len(live.protocol_json),
                        rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
                    ),
                    sort_keys=True,
                )
            )
            live.result = dict(status="SOFTWARE_ONLY")
            return dict(evaluation_scope="TEACHER_COLLECTION", task_success=False), [], []

        # Start the genuine worker and lease heartbeat without issuing a new
        # registration, original claim, physics, renderer or camera operation.
        live.prepared = True
        with ExitStack() as stack:
            stack.enter_context(
                patch.object(
                    application.NativeCollectionApplication,
                    "run_from_worker",
                    body,
                )
            )
            if variant == "one-shot":
                stack.enter_context(
                    patch.object(
                        repo,
                        "_teacher_checkpoint_lifecycle",
                        lambda _database: nullcontext(),
                    )
                )
            if variant == "repeat-select":
                from cloud_edge_robot_arm.simulation_runtime import sqlite_repository

                original_snapshot = sqlite_repository._TeacherCheckpointSnapshot

                class NoRowMemo(dict):
                    def __setitem__(self, key, value):
                        pass

                stack.enter_context(
                    patch.object(
                        sqlite_repository,
                        "_TeacherCheckpointSnapshot",
                        lambda pid, connection, _rows: original_snapshot(
                            pid,
                            connection,
                            NoRowMemo(),
                        ),
                    )
                )
            assert app.execute_once()["status"] == "SOFTWARE_ONLY"
        assert live.diagnostic.action_reads_completed == count


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--count", type=int, default=5000)
    p.add_argument("--trace", action="store_true")
    p.add_argument(
        "--variant", choices=("full", "one-shot", "repeat-select", "dynamic-limits"), default="full"
    )
    options = p.parse_args()
    run(options.count, options.trace, options.variant)
