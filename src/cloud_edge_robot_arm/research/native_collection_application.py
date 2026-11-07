"""Private, one-assignment teacher collector entered only by the actual SQLite worker.

No descriptor, public result or finite diagnostic confers online/native authority.
The operational origin is created before enqueue; legacy UTC lease vetoes remain.
"""

from __future__ import annotations

import hashlib
import json
import os
import resource
import shutil
import sys
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn, SupportsIndex
from uuid import uuid4

from cloud_edge_robot_arm.edge.evidence.conditions import (
    ConditionSpec,
    OnlineEvidenceSnapshot,
    evaluate_conditions,
)
from cloud_edge_robot_arm.research.native_calibration_collection import (
    ROOT,
    canonical,
    check_sources,
    digest,
    fresh_directory,
    read_protocol,
    save_exclusive,
)
from cloud_edge_robot_arm.research.native_calibration_collection import detached as _plain
from cloud_edge_robot_arm.research.native_collection_grounding import (
    bootstrap_collection_tracker,
    build_collection_contract,
    collection_grounding_inputs,
    collection_unknown_row,
    grounded_collection_step,
    validate_registration_handoff,
)
from cloud_edge_robot_arm.research.operational_time_v1 import open_operational_clock
from cloud_edge_robot_arm.vision.raw_recorder_v3 import _error
from cloud_edge_robot_arm.vision.worker_owner import (
    grounded_worker_effect_conditions,
    read_visual_worker_lease,
)

_ISSUER = object()

if TYPE_CHECKING:
    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
        SQLiteSimulationJobRepository,
    )
    from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker


@dataclass
class _Live:
    repository: Any
    worker: Any
    output: Path
    protocol_path: Path
    protocol_json: bytes
    assignment_id: str
    pid: int
    thread: int
    application_id: str = field(default_factory=lambda: uuid4().hex)
    prepared: bool = False
    executed: bool = False
    entered: bool = False
    closed: bool = False
    job_id: str | None = None
    job_basis: bytes | None = None
    worker_origin: tuple[Any, ...] | None = None
    fencing: tuple[Any, ...] | None = None
    owner: Any = None
    origin_token: Any = None
    origin: Any = None
    deadline: Any = None
    issued_at: datetime | None = None
    backend: Any = None
    capture: Any = None
    robot: Any = None
    executor: Any = None
    recorder: Any = None
    original: Any = None
    tracker: Any = None
    grounding_evidence: Any = None
    session: Any = None
    next_index: int = 0
    completed: list[Any] = field(default_factory=list)
    executed_steps: list[Any] = field(default_factory=list)
    checks: list[Any] = field(default_factory=list)
    failures: list[Any] = field(default_factory=list)
    result: dict[str, Any] | None = None
    config_json: bytes | None = None
    pending: tuple[int, str, str] | None = None
    progress: dict[str, bool] = field(default_factory=dict)
    consumptions: list[Any] = field(default_factory=list)


_REGISTRY: dict[Any, _Live] = {}


def _live(app: Any) -> _Live:
    if type(app) is not NativeCollectionApplication or app not in _REGISTRY:
        raise RuntimeError("exact live collection application required")
    live = _REGISTRY[app]
    if (
        live.closed
        or os.getpid() != live.pid
        or threading.get_ident() != live.thread
        or app.worker is not live.worker
        or app.repository is not live.repository
        or live.worker.repository is not live.repository
        or app.output != live.output
        or live.worker._native_collection_application is not app
        or live.worker.planner_factory is not None
        or live.worker.visual_role_binding is not None
        or getattr(live.worker, "_operational_prefix_application", None) is not None
        or live.worker._native_clock_prefix_application is not None
    ):
        raise RuntimeError("collection lifecycle, thread or exclusive worker identity changed")
    return live


def _job_basis(job: Any) -> bytes:
    return canonical(
        {
            name: getattr(job, name)
            for name in (
                "job_id",
                "run_id",
                "backend",
                "scenario_id",
                "control_mode",
                "seed",
                "draft",
                "timeout_seconds",
                "max_attempts",
                "manifest_id",
                "reproducibility_hash",
                "artifact_root",
                "source_commit",
                "source_tree_hash",
            )
        }
    )


def _remember(live: _Live, phase: str, error: BaseException, *, secondary: bool = False) -> None:
    live.failures.append(
        dict(
            phase=phase,
            error_type=type(error).__name__,
            error=_error(error),
            role="SECONDARY" if secondary or live.failures else "PRIMARY",
        )
    )


def _tracker_clock_record(
    live: _Live,
    observation: Any,
    protocol: dict[str, Any],
    *,
    purpose: str,
    started_at: datetime,
    evaluated_at: datetime,
    finished_at: datetime,
    consumption_before: dict[str, Any],
    consumption_after: dict[str, Any],
    index: int | None = None,
    step_id: str | None = None,
) -> dict[str, Any]:
    """Retain source readings; none of these timestamps is an inferred replacement."""
    return dict(
        schema_version="native.tracker.clock.v1",
        purpose=purpose,
        index=index,
        step_id=step_id,
        acquisition=live.recorder.acquisition_source(),
        observation_id=observation.observation_id,
        checksum_sha256=observation.checksum_sha256,
        source_generation=protocol["source_generation"],
        started_at=started_at.isoformat(),
        evaluated_at=evaluated_at.isoformat(),
        finished_at=finished_at.isoformat(),
        consumption_before=consumption_before,
        consumption_after=consumption_after,
    )


def _record_bootstrap_tracker(
    live: _Live,
    observation: Any,
    protocol: dict[str, Any],
    *,
    purpose: str,
    name: str,
    consume_capture: Callable[[], dict[str, Any]],
) -> tuple[Any, dict[str, Any]]:
    before = consume_capture()
    started = datetime.now(UTC)
    tracker, evidence = bootstrap_collection_tracker(observation, protocol["geometry"])
    finished = datetime.now(UTC)
    after = consume_capture()
    record = _tracker_clock_record(
        live,
        observation,
        protocol,
        purpose=purpose,
        started_at=started,
        evaluated_at=tracker.last_binding_evaluated_at,
        finished_at=finished,
        consumption_before=before,
        consumption_after=after,
    )
    live.recorder._write_original(name, record)
    return tracker, evidence


def _collect_grounded_step(
    live: _Live,
    index: int,
    observation: Any,
    protocol: dict[str, Any],
    *,
    consume_capture: Callable[[], dict[str, Any]],
) -> Any:
    before = consume_capture()
    started = datetime.now(UTC)

    def record(data: dict[str, Any]) -> None:
        finished = datetime.now(UTC)
        after = consume_capture()
        data["tracker_clock"] = _tracker_clock_record(
            live,
            observation,
            protocol,
            purpose="GROUNDING",
            index=index,
            step_id=data["step_id"],
            started_at=started,
            evaluated_at=datetime.fromisoformat(data["tracker_evaluated_at"]),
            finished_at=finished,
            consumption_before=before,
            consumption_after=after,
        )
        live.recorder.record_grounding(data)

    return grounded_collection_step(
        live.original,
        index=index,
        observation=observation,
        state=live.robot.get_state(),
        tracker=live.tracker,
        evidence=live.grounding_evidence,
        geometry=protocol["geometry"],
        evidence_sink=record,
    )


def _handoff_registered_capture(
    live: _Live,
    bootstrap: Any,
    lease: Any,
    protocol: dict[str, Any],
    *,
    consume_capture: Callable[[], dict[str, Any]],
) -> Any:
    """One actual post-registration capture, with both original trackers retained."""
    recorder = live.recorder
    before = live.backend.total_physics_steps
    bootstrap_source = recorder.acquisition_source()
    _, _, bootstrap_bracket = recorder.current_capture()
    dispatch = recorder.capture()
    after = live.backend.total_physics_steps
    checked_at = datetime.now(UTC)
    validate_registration_handoff(
        live.original,
        lease.to_payload(),
        bootstrap,
        dispatch,
        step_before=before,
        step_after=after,
        now=checked_at,
    )
    dispatch_source = recorder.acquisition_source()
    _, _, dispatch_bracket = recorder.current_capture()
    if bootstrap_source["acquisition_id"] == dispatch_source["acquisition_id"]:
        raise ValueError("new actual acquisition required after registration")
    tracker, evidence = _record_bootstrap_tracker(
        live,
        dispatch,
        protocol,
        purpose="BOOTSTRAP_E",
        name="tracker-clock/dispatch.json",
        consume_capture=consume_capture,
    )
    dispatch_sha = recorder._write_original("dispatch-bootstrap.json", evidence)

    def source_row(
        observation: Any, source: Any, bracket: Any, name: str, sha: str, clock_name: str
    ) -> dict[str, Any]:
        return dict(
            acquisition=source,
            observation_id=observation.observation_id,
            checksum_sha256=observation.checksum_sha256,
            captured_at=observation.captured_at.isoformat(),
            sim_time_s=observation.sim_time_s,
            bracket=_plain(bracket),
            bootstrap=dict(path=name, sha256=sha),
            tracker_clock=dict(path=clock_name, sha256=recorder.inventory[clock_name]["sha256"]),
        )

    timeline = dict(
        schema_version="native.registration.handoff.v1",
        original_plan_sha256=live.original.digest(),
        registered_at=live.original.registered_at.isoformat(),
        identity=live.original.identity.to_payload(),
        contract_issued_at=live.original.contract.issued_at.isoformat(),
        task_deadline_at=live.original.task_deadline_at.isoformat(),
        verification_deadline_at=live.original.verification_deadline_at.isoformat(),
        origin=_plain(live.origin),
        deadline=_plain(live.deadline),
        lease=lease.to_payload(),
        checked_at=checked_at.isoformat(),
        step_before=before,
        step_after=after,
        source_generation=protocol["source_generation"],
        bootstrap=source_row(
            bootstrap,
            bootstrap_source,
            bootstrap_bracket,
            "bootstrap.json",
            recorder.inventory["bootstrap.json"]["sha256"],
            "tracker-clock/bootstrap.json",
        ),
        dispatch=source_row(
            dispatch,
            dispatch_source,
            dispatch_bracket,
            "dispatch-bootstrap.json",
            dispatch_sha,
            "tracker-clock/dispatch.json",
        ),
        active_tracker_reference_acquisition_id=dispatch_source["acquisition_id"],
        tracker_transition="BOOTSTRAP_TO_DISPATCH_BEFORE_FIRST_ACTION",
    )
    recorder._write_original("registration-timeline.json", timeline)
    live.tracker, live.grounding_evidence = tracker, evidence
    return dispatch


@contextmanager
def _collection_guard(live: _Live, callback: Any, event_limit: int) -> Any:
    """Put the real guard's exit, including its STOP, inside a real purpose."""
    guard = live.backend.enforce_execution_guard(callback, event_limit=event_limit)
    guard.__enter__()
    live.progress["guard_entered"] = True
    primary = None
    original_exc: tuple[Any, Any, Any] = (None, None, None)
    try:
        yield
    except BaseException as error:
        primary = error
        original_exc = sys.exc_info()
    purpose = None
    entered = False
    try:
        purpose = live.recorder.purpose("TERMINATION")
        purpose.__enter__()
        entered = True
    except BaseException as error:
        _remember(live, "termination_entry", error, secondary=primary is not None)
        primary = primary or error
    try:
        guard.__exit__(*original_exc)
        live.progress["guard_exited"] = True
    except BaseException as error:
        _remember(live, "guard_exit", error, secondary=primary is not None)
        primary = primary or error
    finally:
        if entered:
            try:
                assert purpose is not None
                purpose.__exit__(*original_exc)
            except BaseException as error:
                _remember(live, "termination_exit", error, secondary=primary is not None)
                primary = primary or error
    if primary is not None:
        raise primary.with_traceback(
            original_exc[2] if primary is original_exc[1] else primary.__traceback__
        )


def _close_body_resources(live: _Live, primary: BaseException | None) -> BaseException | None:
    recorder = live.recorder
    operations: list[tuple[str, Any]] = []
    if live.progress.get("recorder_entered"):

        def freeze() -> None:
            recorder._write_original("active-checks.json", live.checks)
            recorder._write_original("capture-consumptions.json", live.consumptions)
            recorder.freeze()

        operations.extend(
            [
                ("freeze", freeze),
                (
                    "recorder_close",
                    lambda: recorder.__exit__(
                        type(primary) if primary else None,
                        primary,
                        primary.__traceback__ if primary else None,
                    ),
                ),
            ]
        )
    if live.progress.get("capture_entered"):
        operations.append(("capture_close", lambda: live.capture.__exit__(None, None, None)))
    if live.progress.get("backend_initialization_attempted"):
        operations.append(("backend_shutdown", live.backend.shutdown))
    for phase, operation in operations:
        live.progress[phase + "_attempted"] = True
        try:
            operation()
            live.progress[phase + "_completed"] = True
        except BaseException as error:
            _remember(live, phase, error, secondary=primary is not None)
            primary = primary or error
    return primary


@dataclass(frozen=True, slots=True)
class CollectionAdmissionDecision:
    phase: str
    step_id: str
    allowed: bool
    retained_unknown_conditions: tuple[str, ...]
    whitelist_rows: tuple[str, ...]
    reasons: tuple[str, ...]
    original_inputs_sha256: str
    schema_version: str = "teacher.collection.admission.v1"
    execution_admitted: bool = False
    native_qualification: str = "UNKNOWN"


class NativeCollectionApplication:
    __slots__ = ("repository", "worker", "output")
    repository: SQLiteSimulationJobRepository
    worker: SimulationWorker
    output: Path

    def __init__(self, *, _token: object | None = None) -> None:
        if _token is not _ISSUER:
            raise TypeError("use the exclusive collection startup factory")

    def __copy__(self) -> NoReturn:
        raise RuntimeError("live collection capability cannot be copied")

    def __deepcopy__(self, memo: dict[int, object]) -> NoReturn:
        raise RuntimeError("live collection capability cannot be copied")

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        raise RuntimeError("live collection capability cannot be serialized")

    @classmethod
    def from_startup(
        cls, protocol: Path, *, assignment_id: str, output: Path
    ) -> NativeCollectionApplication:
        if cls is not NativeCollectionApplication:
            raise TypeError("exact collection factory required")
        registration = read_protocol(protocol)
        if assignment_id != registration["settings"]["released_assignment"]:
            raise ValueError("only the first preregistered assignment is released")
        claim = protocol / "claims" / (assignment_id + ".json")
        if claim.exists():
            raise RuntimeError("assignment already claimed; no retry or restart")
        destination = fresh_directory(output)
        from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
            SQLiteSimulationJobRepository,
        )
        from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker

        app = cls(_token=_ISSUER)
        app.output = destination
        app.repository = SQLiteSimulationJobRepository(destination / "runtime.db")
        app.worker = SimulationWorker(
            worker_id="native-collection-" + uuid4().hex,
            backend="MUJOCO",
            repository=app.repository,
            artifact_root=destination,
        )
        app.worker._native_collection_application = app
        _REGISTRY[app] = _Live(
            app.repository,
            app.worker,
            destination,
            protocol.absolute(),
            canonical(registration),
            assignment_id,
            os.getpid(),
            threading.get_ident(),
        )
        return app

    @property
    def protocol(self) -> dict[str, Any]:
        value: object = json.loads(_live(self).protocol_json)
        if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
            raise ValueError("registered protocol must be a string-keyed JSON object")
        return value

    @property
    def policy(self) -> dict[str, Any]:
        value: object = self.protocol["settings"]
        if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
            raise ValueError("registered settings must be a string-keyed JSON object")
        return value

    def prepare_once(self) -> Any:
        from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus

        live = _live(self)
        if live.prepared:
            raise RuntimeError("collection assignment may be prepared once")
        live.prepared = True
        protocol = read_protocol(live.protocol_path)
        if canonical(protocol) != live.protocol_json:
            raise ValueError("original preregistration changed")
        save_exclusive(
            live.protocol_path / "claims" / (live.assignment_id + ".json"),
            dict(
                assignment_id=live.assignment_id,
                output=str(live.output),
                protocol_sha256=digest(protocol),
                application_id=live.application_id,
            ),
        )
        live.owner = open_operational_clock()
        live.origin_token = live.owner.begin_event("COLLECTION_TASK_ORIGIN")
        live.owner.mark_event(live.origin_token)
        live.origin = live.owner.end_event(live.origin_token)
        live.deadline = live.owner.start_deadline(
            task_key=live.assignment_id,
            origin=live.origin,
            budget_ns=self.policy["task_timeout_s"] * 10**9,
        )
        live.issued_at = datetime.now(UTC)
        assignment = next(
            row for row in protocol["assignments"] if row["assignment_id"] == live.assignment_id
        )
        draft = dict(
            input_mode="RGBD",
            execution_scope="VISION_CLOSED_LOOP",
            backend="MUJOCO",
            scenarios=["S01_NORMAL_STATIC"],
            control_modes=["PCSC"],
            seeds=[assignment["seed"]],
            user_instruction=protocol["role"]["instruction"],
        )
        job = live.repository.create_job(
            run_id="native-collection-" + uuid4().hex,
            batch_id="",
            backend="MUJOCO",
            scenario_id="S01_NORMAL_STATIC",
            control_mode="PCSC",
            seed=assignment["seed"],
            manifest_id="native.calibration.operational.v2",
            reproducibility_hash=digest(assignment),
            draft=draft,
            timeout_seconds=self.policy["task_timeout_s"],
            max_attempts=1,
            artifact_root="worker-attempt",
            source_commit="CURRENT_REGISTERED_SOURCE_BYTES",
            source_tree_hash=protocol["source_generation"],
            provenance=dict(scope="TEACHER_COLLECTION", protocol_sha256=digest(protocol)),
        )
        live.job_id, live.job_basis = job.job_id, _job_basis(job)
        save_exclusive(
            live.output / "startup.json",
            dict(
                assignment=assignment,
                protocol_sha256=digest(protocol),
                application_id=live.application_id,
                job_basis=json.loads(live.job_basis),
                origin=_plain(live.origin),
                deadline=_plain(live.deadline),
                issued_at=live.issued_at.isoformat(),
                role=protocol["role"],
                legacy_lease_clock="UTC_LEGACY_VETO",
                native_qualification="UNKNOWN",
            ),
        )
        queued = live.repository.update_status_cas(
            job.job_id,
            expected=RuntimeJobStatus.CREATED,
            next_status=RuntimeJobStatus.QUEUED,
            reason_code="native_collection_startup",
            worker_id="",
            lease_id="",
        )
        if queued is None:
            raise RuntimeError("sole assignment enqueue failed")
        return live.repository.get_job(job.job_id)

    def execute_once(self) -> dict[str, Any]:
        live = _live(self)
        if live.executed:
            raise RuntimeError("collection application cannot execute twice")
        live.executed = True
        primary: BaseException | None = None
        worker_snapshot: dict[str, Any] = {}
        closure = dict(attempted=False, completed=False)
        try:
            if not live.prepared:
                self.prepare_once()
            if not live.worker.poll_once():
                raise RuntimeError("sole worker did not acquire the assignment")
        except BaseException as error:
            _remember(live, "prepare_or_worker_poll", error)
            primary = error
        finally:
            if live.job_id is not None and live.job_basis is not None:
                run_id = json.loads(live.job_basis)["run_id"]
                queries = {
                    "job": lambda: live.repository.get_job(live.job_id),
                    "attempts": lambda: [
                        r
                        for r in live.repository.list_attempts(run_id)
                        if r.job_id == live.job_id and r.attempt == 1
                    ],
                    "events": lambda: [
                        r for r in live.repository.list_events(run_id) if r.job_id == live.job_id
                    ],
                }
                for name, query in queries.items():
                    try:
                        worker_snapshot[name] = _plain(query())
                    except BaseException as error:
                        _remember(live, "repository_" + name, error, secondary=primary is not None)
                        primary = primary or error
                job = worker_snapshot.get("job", {})
                if job.get("status") != "SUCCEEDED":
                    terminal_error = RuntimeError(
                        "worker terminal outcome: "
                        + json.dumps(worker_snapshot, ensure_ascii=False)
                    )
                    _remember(
                        live, "worker_terminal", terminal_error, secondary=primary is not None
                    )
                    primary = primary or terminal_error
            if live.result is None:
                missing_body_error = RuntimeError(
                    "worker returned without a collection body receipt"
                )
                _remember(live, "missing_body", missing_body_error, secondary=primary is not None)
                primary = primary or missing_body_error
            try:
                if live.owner is not None:
                    closure["attempted"] = True
                    live.owner.close()
                    closure["completed"] = True
            except BaseException as error:
                _remember(live, "owner_close", error, secondary=primary is not None)
                primary = primary or error
            finally:
                live.closed = True
        body = dict(live.result or {})
        links: dict[str, Any] = {}
        for name in ("collection-body-result.json", "originals/inventory.json"):
            try:
                path = live.output / name
                if path.is_file():
                    links[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            except BaseException as error:
                _remember(live, "final_links", error, secondary=primary is not None)
                primary = primary or error
        live.result = dict(
            body,
            assignment_id=live.assignment_id,
            worker_snapshot=worker_snapshot,
            owner_closure=closure,
            progress=dict(live.progress),
            lifecycle_links=links,
            failures=list(live.failures),
            source_generation=json.loads(live.protocol_json)["source_generation"],
            status="COLLECTION_PARTIAL"
            if primary or live.failures
            else body.get("status", "COLLECTION_PARTIAL"),
            teacher_collection_admitted=not (primary or live.failures)
            and body.get("teacher_collection_admitted", False),
            online_effect_status="UNKNOWN",
            native_qualification="UNKNOWN",
            execution_admitted=False,
            joint_bound_m=None,
            qualified_group_score=None,
            final_lifecycle_receipt=True,
        )
        try:
            save_exclusive(live.output / "collection-result.json", live.result)
        except BaseException as error:
            _remember(live, "final_save", error, secondary=primary is not None)
            live.result.update(
                status="COLLECTION_PARTIAL",
                teacher_collection_admitted=False,
                failures=list(live.failures),
                final_receipt_persisted=False,
            )
            primary = primary or error
        if primary is not None:
            raise primary
        return dict(live.result)

    def check_active(self) -> dict[str, Any]:
        live = _live(self)
        if live.worker_origin is None or live.job_id is None:
            raise RuntimeError("actual running worker origin required")
        job = live.repository.get_job(live.job_id)
        if (
            _job_basis(job) != live.job_basis
            or live.worker._active_task_origin != live.worker_origin
            or live.worker.active_job_id != live.job_id
            or job.max_attempts != 1
        ):
            raise RuntimeError("original assignment/worker origin changed")
        live.worker._raise_if_cancelled_or_timed_out(job.job_id, job, live.worker_origin[1])
        lease = read_visual_worker_lease(
            live.repository,
            job_id=job.job_id,
            run_id=job.run_id,
            worker_id=live.worker.worker_id,
            lease_id=job.lease_id,
        )
        fencing = (
            job.job_id,
            job.run_id,
            lease.worker_id,
            lease.lease_id,
            lease.attempt,
            lease.acquired_at,
        )
        if lease.attempt != 1 or live.fencing is not None and live.fencing != fencing:
            raise RuntimeError("original lease/attempt changed")
        live.fencing = fencing
        current = live.owner.read_current(after=live.origin_token)
        if not live.owner.before_deadline(live.deadline, current):
            raise RuntimeError("original operational deadline expired")
        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 > self.policy["rss_bytes"]:
            raise RuntimeError("registered process RSS budget exhausted")
        if live.backend is not None and live.config_json is not None:
            if canonical(live.backend._config.model_dump(mode="json")) != live.config_json:
                raise RuntimeError("backend configuration changed")
            if live.backend.total_physics_steps > self.protocol["physical_budget"]:
                raise RuntimeError("registered physical budget exhausted")
        snapshot = dict(
            lease=lease.to_payload(),
            task_origin=_plain(live.worker_origin),
            current=_plain(current),
            original_deadline_ns=live.deadline.deadline_ns,
        )
        return snapshot

    def _guard(self, checkpoint: Any) -> None:
        live = _live(self)
        snapshot = self.check_active()
        state = live.robot.get_state()
        if not state.connected or state.estop_engaged or state.collision_detected:
            raise RuntimeError("current robot hard safety stop")
        # Boundary receipts are originals, not cached permission booleans.
        live.checks.append(
            dict(
                checkpoint=_plain(checkpoint),
                step=live.backend.total_physics_steps,
                current=snapshot["current"],
                lease_id=snapshot["lease"]["lease_id"],
            )
        )

    def _consume_capture(self) -> dict[str, Any]:
        live = _live(self)
        state = self.check_active()
        aid, token, bracket = live.recorder.current_capture()
        current = live.owner.read_current(after=token)
        if not live.owner.within_age(
            bracket, current, max_age_ns=self.policy["ordinary_max_age_ns"]
        ):
            raise RuntimeError("original acquisition TTL exceeded")
        frame = live.recorder.last_captured_frame.observation
        if round(frame.sim_time_s * 240) != live.backend.total_physics_steps:
            raise RuntimeError("capture and dispatch physics step differ")
        original = dict(
            acquisition_id=aid,
            capture=_plain(bracket),
            consumed=_plain(current),
            step=live.backend.total_physics_steps,
            live_owner=state,
        )
        live.consumptions.append(original)
        return original

    def recorder_source(self, recorder: Any) -> dict[str, Any]:
        live = _live(self)
        source = self.check_active()
        if (
            recorder is not live.recorder
            or recorder.backend is not live.backend
            or recorder.executor is not live.executor
            or recorder.capture_session is not live.capture
            or recorder.owner is not live.owner
            or recorder._reset_count != 1
            or live.original is None
        ):
            raise RuntimeError("same actual source and original plan required")
        job = live.repository.get_job(live.job_id)
        attempts = [
            row
            for row in live.repository.list_attempts(job.run_id)
            if row.job_id == job.job_id and row.ended_at is None
        ]
        if len(attempts) != 1:
            raise RuntimeError("unique current original attempt required")
        assignment_basis = dict(
            registered_assignment=self.protocol["assignments"][0],
            simulation_job_assignment={
                name: getattr(job, name)
                for name in (
                    "job_id",
                    "run_id",
                    "batch_id",
                    "backend",
                    "scenario_id",
                    "control_mode",
                    "seed",
                    "manifest_id",
                    "reproducibility_hash",
                    "draft",
                    "manifest",
                )
            },
        )
        attempt_basis = dict(
            attempt=_plain(attempts[0]),
            lease_id=source["lease"]["lease_id"],
            lease_acquired_at=source["lease"]["acquired_at"],
        )
        return dict(
            assignment_basis=assignment_basis,
            attempt_basis=attempt_basis,
            control_source="PIXELS_PROPRIO_REGISTERED_CONSTANTS",
            truth="OFFLINE_LABELS_ONLY",
            session_id=live.application_id,
            assignment_id=live.assignment_id,
            protocol_sha256=digest(self.protocol),
            source_generation=self.protocol["source_generation"],
            asset_sha256=self.policy["marked_asset_sha256"],
            original=live.original,
            scope="TEACHER_COLLECTION",
            source=source,
            origin=_plain(live.origin),
            deadline=_plain(live.deadline),
            geometry=self.protocol["geometry"],
            native_qualification="UNKNOWN",
        )

    def _nominal_release(self, observation: Any, state: Any) -> bool:
        live = _live(self)
        if (
            not live.completed
            or live.completed[-1].skill != "PLACE"
            or not live.completed[-1].complete
        ):
            return False
        target, _ = live.tracker._geometry(observation, live.tracker.target_color, target=True)
        region, _ = live.tracker._geometry(
            observation, live.tracker.destination_color, target=False, occlusion_geometry=target
        )
        if target is None or region is None:
            return False
        inside = all(
            target["min"][i] >= region["inner_min"][i]
            and target["max"][i] <= region["inner_max"][i]
            for i in (0, 1)
        )
        initial = live.tracker.initial
        height = abs(
            target["center"][2]
            - initial["center"][2]
            - region["center"][2]
            + live.tracker.support_z
        )
        from math import dist

        destination = live.executed_steps[-1].parameters["target_pose"]
        tcp = dist(
            (state.tcp_pose.x, state.tcp_pose.y, state.tcp_pose.z), [destination[k] for k in "xyz"]
        )
        return bool(inside and height <= 0.012 and tcp <= 0.02)

    def _evaluate_collection_admission(
        self,
        *,
        phase: str,
        step: Any,
        conditions: Any,
        observation: Any,
        shield: Any,
        receipt: Any = None,
        binding: Any = None,
        shield_source: Any = None,
    ) -> CollectionAdmissionDecision:
        from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration
        from cloud_edge_robot_arm.vision.pose_markers import detect_pose_marker
        from cloud_edge_robot_arm.vision.tracking import _CONDITIONS, OpenCVTargetTracker

        live = _live(self)
        consumed = self._consume_capture()
        tracker_started = datetime.now(UTC)
        state = live.robot.get_state()
        if type(live.tracker) is not OpenCVTargetTracker:
            raise RuntimeError("exact original pixel tracker required")
        facts = live.tracker.facts(observation, state)
        tracker_evaluated = live.tracker.last_binding_evaluated_at
        snapshot = OnlineEvidenceSnapshot(observation, state, facts, 1, 1, live.original.digest())
        evaluated_at = datetime.now(UTC)
        verdicts = evaluate_conditions(conditions, snapshot, now=evaluated_at)
        supplemental = evaluate_conditions(
            [
                ConditionSpec("target_visible", "object"),
                ConditionSpec("gripper_holding", "object"),
                ConditionSpec("gripper_released", "object"),
                ConditionSpec("robot_in_safe_pose", "object", {"minimum_safe_height": 0.0}),
            ],
            snapshot,
            now=evaluated_at,
        )
        status = {v.condition_name: v.status.value for v in [*verdicts, *supplemental]}
        reasons: list[str] = []
        # Current, complete marker/colour geometry comes from the same RGB-D frame.
        marker = detect_pose_marker(
            observation, NativeGeometryRegistration(self.protocol["geometry"]).pose_marker
        )
        if marker.status != "OBSERVED":
            reasons.append("registered_marker_unavailable")
        try:
            collection_grounding_inputs(
                observation,
                state,
                self.protocol["geometry"],
                tracker=live.tracker,
                evidence=live.grounding_evidence,
                source_hashes=live.original.source_hashes,
            )
        except ValueError as error:
            reasons.append(_error(error))
        if (
            status["target_visible"] != "PASS"
            or not state.connected
            or state.estop_engaged
            or state.collision_detected
            or not shield.allowed
            or shield.limited_parameters
            and shield.limited_parameters != step.parameters
        ):
            reasons.append("common_geometry_proprioception_or_shield_gate")
        if phase == "TERMINAL" and (
            status["gripper_released"] != "PASS" or status["robot_in_safe_pose"] != "PASS"
        ):
            reasons.append("terminal_proprioception_unconfirmed")
        full = bool(receipt is not None and receipt.complete and not receipt.reasons)
        nominal = (
            self._nominal_release(observation, state)
            if phase == "PRE" and step.skill.value == "RELEASE"
            else False
        )
        rows: list[str] = []
        unknowns: list[str] = []
        for verdict in verdicts:
            if verdict.status.value == "PASS":
                continue
            unknowns.append(verdict.condition_name)
            row = collection_unknown_row(
                phase=phase,
                skill=step.skill.value,
                condition=verdict.condition_name,
                verdict=_plain(verdict),
                facts=facts,
                holding=status["gripper_holding"] == "PASS",
                tcp_reached=status.get("tcp_at_resolved_target") == "PASS",
                full_horizon=full,
                nominal_release=nominal,
                released=status["gripper_released"] == "PASS",
                tracker_has_no_held="object_held" not in _CONDITIONS,
                depth_bound_missing=live.tracker.depth_error_bound_m is None,
            )
            if row is None:
                reasons.append("condition_not_admitted:" + verdict.condition_name)
            else:
                rows.append(row)
        tracker_finished = datetime.now(UTC)
        consumed_after = self._consume_capture()
        tracker_clock = _tracker_clock_record(
            live,
            observation,
            self.protocol,
            purpose="ADMISSION_" + phase,
            index=next(
                i for i, s in enumerate(live.original.contract.steps) if s.step_id == step.step_id
            ),
            step_id=step.step_id,
            started_at=tracker_started,
            evaluated_at=tracker_evaluated,
            finished_at=tracker_finished,
            consumption_before=consumed,
            consumption_after=consumed_after,
        )
        original_inputs = dict(
            phase=phase,
            skill=step.skill.value,
            step=step.model_dump(mode="json"),
            conditions=_plain(conditions),
            verdicts=_plain(verdicts),
            supplemental=_plain(supplemental),
            facts=facts,
            robot_state=state.model_dump(mode="json"),
            shield=_plain(shield),
            shield_source=shield_source,
            capture=consumed,
            tracker_clock=tracker_clock,
            source_generation=self.protocol["source_generation"],
            original_plan_sha256=live.original.digest(),
            nominal_collection_position_check=nominal,
            complete_horizon=full,
            receipt=_plain(receipt) if receipt is not None else None,
            grounding=binding.to_payload() if binding is not None else None,
            marker=_plain(marker),
            evaluation_at=evaluated_at.isoformat(),
        )
        decision = CollectionAdmissionDecision(
            phase,
            step.step_id,
            not reasons,
            tuple(unknowns),
            tuple(rows),
            tuple(reasons),
            digest(_plain(original_inputs)),
        )
        live.recorder.decisions.append(
            dict(
                inputs=_plain(original_inputs),
                decision=asdict(decision),
                decision_kind="CONTINUE_EXPERIMENT" if decision.allowed else "STOP",
                semantic_effect_status="UNKNOWN" if unknowns else "PASS",
            )
        )
        if not decision.allowed:
            raise RuntimeError("collection admission stopped: " + ";".join(reasons))
        if phase == "PRE":
            live.pending = (live.next_index, digest(step.model_dump(mode="json")), binding.digest())
        return decision

    def _execute_horizon(
        self, session: Any, *, index: int, contract: Any, step: Any, binding: Any
    ) -> Any:
        from cloud_edge_robot_arm.simulation.mujoco.native_horizon import _run_registered_horizon
        from cloud_edge_robot_arm.vision.native_completion_horizon import (
            completion_horizon_rational_v1,
        )

        live = _live(self)
        if session is not live.session or index != live.next_index or index != len(live.completed):
            raise RuntimeError("private ordered horizon capability required")
        self._consume_capture()
        expected = (index, digest(step.model_dump(mode="json")), binding.digest())
        if live.pending != expected:
            raise RuntimeError("one unconsumed actual pre-admission required")
        live.pending = None
        row = self.protocol["actions"][index]
        if step.skill.value != row["skill"] or binding.grounded_step != step:
            raise RuntimeError("fixed original step/payload mismatch")
        receipt = _run_registered_horizon(
            backend=live.backend,
            robot=live.robot,
            executor=live.executor,
            recorder=live.recorder,
            contract=contract,
            step=step,
            grounding=binding,
            horizon=completion_horizon_rational_v1(row["skill"], **row["recipe"]),
            check_active=self.check_active,
        )
        if not receipt.complete:
            raise RuntimeError("controller or registered horizon incomplete")
        return receipt

    def run_from_worker(
        self, worker: Any, job: Any, *, start_monotonic: float
    ) -> tuple[Any, list[Any], list[Any]]:
        from cloud_edge_robot_arm.edge.runtime.skill_executor import SkillExecutor
        from cloud_edge_robot_arm.edge.runtime.skill_registry import SkillRegistry
        from cloud_edge_robot_arm.research.native_full_horizon_recorder import (
            _ISSUER as recorder_issuer,
        )
        from cloud_edge_robot_arm.research.native_full_horizon_recorder import (
            NativeFullHorizonRecorder,
        )
        from cloud_edge_robot_arm.simulation.config import SimulatorConfig
        from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
        from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
        from cloud_edge_robot_arm.simulation.mujoco.native_horizon import _issue_collection_session
        from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
        from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession
        from cloud_edge_robot_arm.vision.execution import research_safety_shield
        from cloud_edge_robot_arm.vision.top_grasp import matches_calibrated_gripper

        live = _live(self)
        if (
            live.entered
            or worker is not live.worker
            or job.job_id != live.job_id
            or worker._active_task_origin is None
            or worker._active_task_origin[:2] != (job.job_id, start_monotonic)
        ):
            raise RuntimeError("sole actual worker entry required")
        live.entered = True
        live.worker_origin = worker._active_task_origin
        primary: BaseException | None = None
        recorder = None
        phase = "preflight"
        physics_steps = None
        render_passes = None
        render_accounting: dict[str, Any] | None = None
        try:
            self.check_active()
            check_sources(self.protocol["source_hashes"])
            if shutil.disk_usage(live.output).free < self.policy["free_disk_min_bytes"]:
                raise RuntimeError("registered 32GiB free disk prerequisite unavailable")
            live.progress["preflight_completed"] = True
            phase = "resource_construction"
            config = SimulatorConfig(
                render_rgb=True,
                render_depth=True,
                physics_dt_s=1 / 240,
                seed=job.seed,
                model_path=self.policy["model_path"],
                domain_randomization=False,
            )
            live.config_json = canonical(config.model_dump(mode="json"))
            live.backend = MuJoCoPhysicsBackend()
            live.robot = MuJoCoSkillRobot(live.backend)
            live.executor = SkillExecutor(robot=live.robot, registry=SkillRegistry.default())
            live.capture = MuJoCoCaptureSession(config, backend=live.backend)
            phase = "backend_initialization"
            live.progress["backend_initialization_attempted"] = True
            live.backend.initialize(config)
            live.progress["backend_initialized"] = True
            if not matches_calibrated_gripper(live.backend._model, self.policy["grasp_profile"]):
                raise RuntimeError("registered original gripper profile mismatch")
            phase = "capture_entry"
            live.capture.__enter__()
            live.progress["capture_entered"] = True
            recorder = NativeFullHorizonRecorder(
                live.backend,
                live.capture,
                live.executor,
                directory=live.output / "originals",
                source_root=ROOT,
                source_hashes=self.protocol["source_hashes"],
                application=self,
                owner=live.owner,
                _token=recorder_issuer,
            )
            live.recorder = recorder
            phase = "recorder_entry"
            recorder.__enter__()
            live.progress["recorder_entered"] = True
            phase = "collection_body"
            live.backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=job.seed))
            recorder.require_clean_reset()
            with _collection_guard(live, self._guard, self.policy["guard_event_limit"]):
                with live.backend.capture_each_physics_step(
                    max_captures=self.protocol["physical_budget"]
                ):
                    with recorder.purpose("SETTLE"):
                        live.backend.step(120)
                    observation = recorder.capture()
                    live.tracker, live.grounding_evidence = _record_bootstrap_tracker(
                        live,
                        observation,
                        self.protocol,
                        purpose="BOOTSTRAP_B",
                        name="tracker-clock/bootstrap.json",
                        consume_capture=self._consume_capture,
                    )
                    current_job = live.repository.get_job(job.job_id)
                    lease = read_visual_worker_lease(
                        live.repository,
                        job_id=job.job_id,
                        run_id=job.run_id,
                        worker_id=worker.worker_id,
                        lease_id=current_job.lease_id,
                    )
                    assert live.issued_at is not None
                    live.original = build_collection_contract(
                        assignment=self.protocol["assignments"][0],
                        current_owner=dict(
                            issued_at=live.issued_at,
                            deadline_at=live.issued_at
                            + timedelta(seconds=self.policy["task_timeout_s"]),
                            task_id=job.job_id,
                            plan_id="collection-" + live.application_id,
                            lease=lease,
                            role_sha256=digest(self.protocol["role"]),
                        ),
                        geometry=self.protocol["geometry"],
                        source_hashes=self.protocol["source_hashes"],
                        observation=observation,
                    )
                    recorder.bind_collection_source(self)
                    recorder._write_original("bootstrap.json", live.grounding_evidence)
                    observation = _handoff_registered_capture(
                        live,
                        observation,
                        lease,
                        self.protocol,
                        consume_capture=self._consume_capture,
                    )
                    live.session = _issue_collection_session(self)
                    shield = research_safety_shield(self.policy["task_timeout_s"])
                    recorder.record_shield_config(shield)
                    for index in range(8):
                        check_sources(self.protocol["source_hashes"])
                        contract, step, binding, _, _ = _collect_grounded_step(
                            live,
                            index,
                            observation,
                            self.protocol,
                            consume_capture=self._consume_capture,
                        )
                        params = dict(step.parameters)
                        context = shield.context_builder.build(
                            contract=contract,
                            step=step,
                            robot_state=live.robot.get_state(),
                            scene_version=contract.scene_version,
                            resolved_parameters=params,
                            scene_updated_at=observation.captured_at,
                            telemetry_timestamp=datetime.now(UTC),
                            wall_clock_now=datetime.now(UTC),
                            step_started_at_mono=time.monotonic(),
                            task_started_at_mono=start_monotonic,
                            monotonic_now=time.monotonic(),
                            requested_joint_velocities=[
                                *[abs(v) for v in live.backend.get_joint_state().velocities],
                                float(params.get("tcp_velocity", 0.0)) / 0.3,
                            ],
                            requested_velocity=float(params.get("tcp_velocity", 0)),
                            requested_acceleration=float(params.get("acceleration", 0)),
                        )
                        pre, pre_source = recorder.check_shield(
                            shield, context, index=index, phase="PRE"
                        )
                        self._evaluate_collection_admission(
                            phase="PRE",
                            step=step,
                            conditions=live.original.requirements[step.step_id].preconditions,
                            observation=observation,
                            shield=pre,
                            binding=binding,
                            shield_source=pre_source,
                        )
                        receipt = live.session.execute(
                            index=index, contract=contract, step=step, binding=binding
                        )
                        terminal_frame = recorder.last_captured_frame
                        if terminal_frame is None:
                            raise RuntimeError(
                                "full horizon returned without its original terminal frame"
                            )
                        observation = terminal_frame.observation
                        state = live.robot.get_state()
                        post_context = context.model_copy(
                            update=dict(
                                robot_collision_detected=state.collision_detected,
                                robot_estop_engaged=state.estop_engaged,
                                tcp_x=state.tcp_pose.x,
                                tcp_y=state.tcp_pose.y,
                                tcp_z=state.tcp_pose.z,
                                scene_updated_at=observation.captured_at,
                                wall_clock_now=datetime.now(UTC),
                                telemetry_timestamp=datetime.now(UTC),
                                monotonic_now=time.monotonic(),
                                joint_velocities=[
                                    abs(v) for v in live.backend.get_joint_state().velocities
                                ],
                            )
                        )
                        post, post_source = recorder.check_shield(
                            shield, post_context, index=index, phase="POST"
                        )
                        conditions = grounded_worker_effect_conditions(live.original, binding)
                        self._evaluate_collection_admission(
                            phase="POST",
                            step=step,
                            conditions=conditions,
                            observation=observation,
                            shield=post,
                            receipt=receipt,
                            binding=binding,
                            shield_source=post_source,
                        )
                        live.completed.append(receipt)
                        live.executed_steps.append(step)
                        live.next_index += 1
                    self._evaluate_collection_admission(
                        phase="TERMINAL",
                        step=step,
                        conditions=conditions,
                        observation=observation,
                        shield=post,
                        receipt=receipt,
                        binding=binding,
                        shield_source=dict(post_source, reused_from="POST"),
                    )
                    self.check_active()
        except BaseException as error:
            primary = error
            _remember(live, phase, error)
            if recorder is not None:
                recorder.record_failure(phase, error)
        finally:
            if live.progress.get("backend_initialized"):
                try:
                    physics_steps = live.backend.total_physics_steps
                    render_accounting = recorder.render_accounting if recorder is not None else None
                    render_passes = (
                        render_accounting["exact_passes"] if render_accounting is not None else None
                    )
                    for event in live.backend.execution_guard_events:
                        for key in ("stop_error", "snapshot_error"):
                            if key in event:
                                guard_secondary_error = RuntimeError(str(event[key]))
                                _remember(
                                    live,
                                    "guard_" + key,
                                    guard_secondary_error,
                                    secondary=primary is not None,
                                )
                                primary = primary or guard_secondary_error
                except BaseException as error:
                    _remember(live, "counter_snapshot", error, secondary=primary is not None)
                    primary = primary or error
            elif not live.progress.get("backend_initialization_attempted"):
                physics_steps = render_passes = 0
            primary = _close_body_resources(live, primary)
            live.result = dict(
                status="COLLECTION_PARTIAL"
                if primary or live.failures
                else "COLLECTION_COMPLETE_WITH_UNRESOLVED_EFFECTS",
                assignment_id=live.assignment_id,
                source_generation=self.protocol["source_generation"],
                completed_action_count=len(live.completed),
                physics_steps=physics_steps,
                render_passes=render_passes,
                render_passes_lower_bound=(
                    render_accounting["known_completed_passes"] if render_accounting else 0
                ),
                render_count_status=(
                    render_accounting["status"]
                    if render_accounting
                    else "EXACT"
                    if render_passes == 0
                    else "UNAVAILABLE"
                ),
                render_accounting=render_accounting,
                render_count_provenance=(
                    "CAPTURE_END_RETURNED_PASSES_BEFORE_SHUTDOWN"
                    if render_accounting
                    else "NOT_STARTED"
                    if render_passes == 0
                    else "UNAVAILABLE"
                ),
                count_provenance="BEFORE_SHUTDOWN"
                if live.progress.get("backend_initialized")
                else "UNAVAILABLE"
                if live.progress.get("backend_initialization_attempted")
                else "NOT_STARTED",
                progress=dict(live.progress),
                failures=list(live.failures),
                online_effect_status="UNKNOWN",
                native_qualification="UNKNOWN",
                execution_admitted=False,
                teacher_collection_admitted=primary is None and not live.failures,
                peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
                original_bytes=recorder.bytes_written if recorder is not None else 0,
                joint_bound_m=None,
                qualified_group_score=None,
                intermediate_body_receipt=True,
            )
            try:
                save_exclusive(live.output / "collection-body-result.json", live.result)
            except BaseException as error:
                _remember(live, "body_save", error, secondary=primary is not None)
                primary = primary or error
                live.result.update(
                    status="COLLECTION_PARTIAL",
                    teacher_collection_admitted=False,
                    failures=list(live.failures),
                )
        if primary is not None:
            raise primary
        return (
            dict(evaluation_scope="TEACHER_COLLECTION", task_success=False, **live.result),
            [],
            [],
        )
