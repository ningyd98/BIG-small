"""Private OC1 lease issuer; stage A retains the independent legacy UTC veto.

Only the dedicated broker creates, reads and closes its D_lease clock. Detached
observations and SQL COMMITTED rows are history, never reconstructable authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import queue
import sqlite3
import sys
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from cloud_edge_robot_arm.research.operational_time_v1 import (
    OperationalBracket,
    OperationalClockOwner,
    OperationalDeadline,
    OperationalDomain,
    OperationalEventToken,
    open_operational_clock,
)

if TYPE_CHECKING:
    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository
    from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker

_TOKEN = object()
_REGISTRY_LOCK = threading.RLock()
_SCOPE = threading.local()
_SESSIONS: dict[str, OperationalLeaseSession] = {}
_VIEWS: dict[int, LockedLeaseView] = {}
_PROPOSALS: dict[int, LeaseProposal] = {}
_ACKS: dict[int, LeaseCommitAck] = {}


class OperationalLeaseError(RuntimeError):
    """No current, genuine lease permission is available."""


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def _canonical(row: Mapping[str, Any]) -> str:
    return _digest({key: value for key, value in row.items() if key != "proposed_row_digest"})


class _Opaque:
    def __copy__(self) -> object:
        raise OperationalLeaseError("live lease capabilities cannot be copied")

    def __deepcopy__(self, memo: dict[int, object]) -> object:
        raise OperationalLeaseError("live lease capabilities cannot be copied")

    def __reduce_ex__(self, protocol: int) -> object:
        raise OperationalLeaseError("live lease capabilities cannot be serialized")


@dataclass(frozen=True)
class OperationalLeaseObservation:
    status: str
    reasons: tuple[str, ...]
    domain: OperationalDomain
    original_acquisition: Mapping[str, Any]
    segment: Mapping[str, Any]
    current: Mapping[str, Any]
    job_id: str
    lease_id: str
    worker_id: str
    attempt: int | None
    generation: int
    source_identity: str
    schema: str = "simulation.operational-lease-observation.v1"
    stage_label: str = "LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO"


class LockedLeaseView(_Opaque):
    def __init__(self, *, _token: object, session: OperationalLeaseSession,
                 repository: SQLiteSimulationJobRepository, connection: sqlite3.Connection,
                 nonce: str, snapshot: Mapping[str, Any], purpose: str,
                 operation_sha256: str) -> None:
        if _token is not _TOKEN:
            raise OperationalLeaseError("view must be issued after actual BEGIN")
        self._session = session
        self._repository = repository
        self._connection = connection
        self._nonce = nonce
        self._thread_id = threading.get_ident()
        self._native_thread_id = threading.get_native_id()
        self._snapshot_json = json.dumps(dict(snapshot), sort_keys=True, allow_nan=False)
        self.purpose = purpose
        self.operation_sha256 = operation_sha256
        self.state = "OPEN"
        self._repository_target: dict[str, Any] = {}
        self._proposal: LeaseProposal | None = None
        self._ack: LeaseCommitAck | None = None
        with _REGISTRY_LOCK:
            _VIEWS[id(self)] = self

    @property
    def snapshot(self) -> Mapping[str, Any]:
        return MappingProxyType(json.loads(self._snapshot_json))


class LeaseProposal(_Opaque):
    def __init__(self, *, _token: object, view: LockedLeaseView, target: Mapping[str, Any],
                 segment: _Segment, previous: _Segment | None) -> None:
        if _token is not _TOKEN:
            raise OperationalLeaseError("proposal is broker issued")
        self._view = view
        self._target_json = json.dumps(dict(target), sort_keys=True, allow_nan=False)
        self._segment = segment
        self._previous = previous
        self.state = "PENDING"
        with _REGISTRY_LOCK:
            _PROPOSALS[id(self)] = self

    @property
    def target(self) -> Mapping[str, Any]:
        return MappingProxyType(json.loads(self._target_json))


class LeaseCommitAck(_Opaque):
    def __init__(self, *, _token: object, proposal: LeaseProposal,
                 commit_identity: str, row_digest: str) -> None:
        if _token is not _TOKEN:
            raise OperationalLeaseError("ack is created only by real commit owner")
        self._proposal = proposal
        self._commit_identity = commit_identity
        self._row_digest = row_digest
        self._used = False
        with _REGISTRY_LOCK:
            _ACKS[id(self)] = self


@dataclass
class _Segment:
    token: OperationalEventToken
    event: OperationalBracket
    deadline: OperationalDeadline

    def receipt(self) -> dict[str, Any]:
        return {"domain": asdict(self.event.domain), "event_id": self.token.event_identity,
                "lower_ns": self.event.lower_ns, "upper_ns": self.event.upper_ns,
                "deadline_ns": self.deadline.deadline_ns, "budget_ns": self.deadline.budget_ns,
                "end_exclusive": True}


@dataclass
class _Request:
    kind: str
    view: LockedLeaseView | None = None
    ack: LeaseCommitAck | None = None
    role: str = "main"
    completed: threading.Event = field(default_factory=threading.Event)
    cancelled: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: BaseException | None = None


class OperationalLeaseSession(_Opaque):
    def __init__(self, *, _token: object, worker: SimulationWorker) -> None:
        if _token is not _TOKEN:
            raise OperationalLeaseError("session requires genuine worker poll lifecycle")
        ttl = worker.lease_ttl_seconds
        if type(ttl) is not int or not math.isfinite(ttl) or ttl <= 0:
            raise OperationalLeaseError("frozen TTL must be positive finite integer seconds")
        self.worker = worker
        self.repository = cast("SQLiteSimulationJobRepository", worker.repository)
        self.worker_id = worker.worker_id
        self._binding = worker.visual_role_binding
        self._binding_hash = _digest(self._binding.evidence()) if self._binding is not None else ""
        self.main_thread = threading.get_ident()
        self.main_native_thread = threading.get_native_id()
        self.ttl_ns = ttl * 1_000_000_000
        self.wait_cap = min(1.0, max(0.05, ttl / 3))
        self.epoch = uuid4().hex
        self.job_id = ""
        self.lease_id = ""
        self._domain: OperationalDomain | None = None
        self._closed = False
        self._unusable = threading.Event()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._startup_error: BaseException | None = None
        self._queue: queue.Queue[_Request] = queue.Queue()
        self._heartbeat_thread: threading.Thread | None = None
        self._active: LeaseProposal | None = None
        self._pending: LeaseProposal | None = None
        self._original: _Segment | None = None
        self.ingress_history: list[dict[str, Any]] = []
        self.cleanup_reason = ""
        self.join_failed = False
        self._broker = threading.Thread(target=self._serve, name="operational-lease-broker", daemon=True)
        with _REGISTRY_LOCK:
            _SESSIONS[self.epoch] = self
        self._broker.start()
        if not self._ready.wait(self.wait_cap) or self._startup_error is not None:
            self.invalidate("broker startup failed")
            self._stop.set()
            self._broker.join(timeout=1)
            raise OperationalLeaseError("broker OC1 startup unavailable") from self._startup_error

    @property
    def domain(self) -> OperationalDomain:
        if self._domain is None:
            raise OperationalLeaseError("broker original domain unavailable")
        return self._domain

    def _check_ingress(self, purpose: str) -> str:
        with _REGISTRY_LOCK:
            if _SESSIONS.get(self.epoch) is not self or self._closed or self._unusable.is_set():
                raise OperationalLeaseError("session is closed, revoked or unregistered")
        if getattr(_SCOPE, "session", None) is not self:
            raise OperationalLeaseError("actual private worker lifecycle scope required")
        role = getattr(_SCOPE, "role", "")
        if role == "main":
            if (threading.get_ident(), threading.get_native_id()) != (
                self.main_thread, self.main_native_thread
            ):
                raise OperationalLeaseError("main thread identity changed")
        elif role == "heartbeat":
            if threading.current_thread() is not self._heartbeat_thread or purpose != "heartbeat":
                raise OperationalLeaseError("heartbeat scope cannot perform this operation")
        else:
            raise OperationalLeaseError("unknown private lifecycle role")
        if self.worker.repository is not self.repository or self.worker.worker_id != self.worker_id:
            self.invalidate("worker repository identity changed")
            raise OperationalLeaseError("worker original source changed")
        if (self.worker.visual_role_binding is not self._binding or self._binding is None
            or _digest(self._binding.evidence()) != self._binding_hash
            or self.worker.lease_ttl_seconds * 1_000_000_000 != self.ttl_ns):
            self.invalidate("worker original policy changed")
            raise OperationalLeaseError("worker frozen source/TTL policy changed")
        if self.worker.operational_time_mode != self.worker._frozen_operational_time_mode:
            self.invalidate("worker mode changed while active")
            raise OperationalLeaseError("worker frozen mode changed")
        return str(role)

    def _view(self, view: LockedLeaseView, *, committed: bool = False) -> None:
        if type(view) is not LockedLeaseView:
            raise OperationalLeaseError("caller descriptors cannot register locked views")
        with _REGISTRY_LOCK:
            if _VIEWS.get(id(view)) is not view or view._session is not self:
                raise OperationalLeaseError("unregistered/foreign view")
        if (view._thread_id, view._native_thread_id) != (
            threading.get_ident(), threading.get_native_id()
        ):
            _invalidate_view(view, "transaction owner thread mismatch")
            raise OperationalLeaseError("transaction owner thread mismatch")
        if view._repository is not self.repository or not view._repository._view_is_current(view):
            raise OperationalLeaseError("actual transaction registry mismatch")
        states = {"COMMITTED"} if committed else {"OPEN", "DECIDED"}
        if view.state not in states:
            raise OperationalLeaseError("view terminal or already consumed")
        try:
            in_transaction = view._connection.in_transaction
        except sqlite3.Error as error:
            _invalidate_view(view, "connection closed")
            raise OperationalLeaseError("connection closed") from error
        if not committed and not in_transaction:
            _invalidate_view(view, "transaction ended before decision")
            raise OperationalLeaseError("view no longer inside real transaction")

    def _rpc(self, request: _Request) -> Any:
        purpose = request.view.purpose if request.view is not None else "confirm"
        # Ack carries its true originating purpose for the narrowly scoped heartbeat.
        if request.ack is not None:
            purpose = request.ack._proposal._view.purpose
        request.role = self._check_ingress(purpose)
        self._queue.put(request)  # no registry or database acquisition in broker
        if not request.completed.wait(self.wait_cap):
            request.cancelled.set()
            self.invalidate("RPC wait cap exceeded")
            raise OperationalLeaseError("broker request timed out; late reply is blocked")
        if request.error is not None:
            if isinstance(request.error, OperationalLeaseError):
                raise request.error
            self.invalidate("broker clock/RPC failure")
            raise OperationalLeaseError("broker clock/RPC failed") from request.error
        if self._unusable.is_set() or request.cancelled.is_set():
            raise OperationalLeaseError("late or revoked broker response")
        # Consumption rechecks the original domain via a second broker read, never D_app.
        if request.kind != "consume":
            check = _Request("consume")
            check.role = request.role
            self._queue.put(check)
            if not check.completed.wait(self.wait_cap):
                check.cancelled.set()
                self.invalidate("response consumption timeout")
                raise OperationalLeaseError("response consumption timed out")
            if check.error is not None or self._unusable.is_set():
                self.invalidate("response crossed original segment bound")
                raise OperationalLeaseError("response crossed original lease bound")
        return request.result

    def evaluate_locked(self, view: LockedLeaseView) -> OperationalLeaseObservation:
        self._check_ingress(view.purpose if type(view) is LockedLeaseView else "inspect")
        self._view(view)
        observation = self._rpc(_Request("evaluate", view=view))
        view.state = "DECIDED"
        return cast(OperationalLeaseObservation, observation)

    def propose_locked(self, view: LockedLeaseView, *, ttl_ns: int) -> LeaseProposal:
        self._check_ingress(view.purpose if type(view) is LockedLeaseView else "inspect")
        self._view(view)
        if type(ttl_ns) is not int or ttl_ns != self.ttl_ns:
            raise OperationalLeaseError("renewal cannot change frozen TTL policy")
        if view._proposal is not None:
            raise OperationalLeaseError("view proposal already issued")
        proposal = self._rpc(_Request("propose", view=view))
        view._proposal = proposal
        view.state = "CONSUMED"
        return cast(LeaseProposal, proposal)

    def confirm_committed(self, ack: LeaseCommitAck) -> OperationalLeaseObservation:
        if type(ack) is not LeaseCommitAck:
            raise OperationalLeaseError("unregistered commit descriptor")
        with _REGISTRY_LOCK:
            if _ACKS.get(id(ack)) is not ack or ack._used:
                raise OperationalLeaseError("commit acknowledgement replay")
        view = ack._proposal._view
        self._check_ingress(view.purpose)
        self._view(view, committed=True)
        ack._used = True
        return cast(OperationalLeaseObservation, self._rpc(_Request("confirm", view=view, ack=ack)))

    def invalidate(self, reason: str) -> None:
        self._unusable.set()
        self.cleanup_reason = reason
        with _REGISTRY_LOCK:
            for proposal in (_PROPOSALS.values()):
                if proposal._view._session is self:
                    proposal.state = "REVOKED"
            for view in _VIEWS.values():
                if view._session is self and view.state not in {"CLOSED", "INVALIDATED"}:
                    view.state = "INVALIDATED"

    def _serve(self) -> None:
        clock: OperationalClockOwner | None = None
        try:
            clock = open_operational_clock()
            self._domain = clock.domain
            self._ready.set()
            while not self._stop.is_set():
                try:
                    request = self._queue.get(timeout=0.05)
                except queue.Empty:
                    continue
                try:
                    if request.cancelled.is_set() or self._unusable.is_set():
                        raise OperationalLeaseError("cancelled/unusable broker epoch")
                    request.result = self._decide(clock, request)
                    if request.cancelled.is_set() or self._unusable.is_set():
                        self.invalidate("late broker reply")
                        raise OperationalLeaseError("late reply cannot activate")
                except BaseException as error:
                    request.error = error
                finally:
                    request.completed.set()
        except BaseException as error:
            self._startup_error = error
            self.invalidate("broker thread failure")
        finally:
            self._ready.set()
            if clock is not None:
                clock.close()  # always its original owner thread

    def _live(self, clock: OperationalClockOwner, segment: _Segment) -> OperationalBracket:
        current = clock.read_current(after=segment.token)
        if not clock.before_deadline(segment.deadline, current):
            self.invalidate("original lease segment expired")
            raise OperationalLeaseError("original lease hard-open segment expired")
        return current

    def _decide(self, clock: OperationalClockOwner, request: _Request) -> Any:
        if request.kind == "consume":
            if self._pending is not None:
                self._live(clock, self._pending._segment)
                if self._pending._previous is not None:
                    self._live(clock, self._pending._previous)
            elif self._active is not None:
                self._live(clock, self._active._segment)
            return None
        view = request.view
        if view is None:
            raise OperationalLeaseError("missing registered request view")
        with _REGISTRY_LOCK:
            if _VIEWS.get(id(view)) is not view:
                raise OperationalLeaseError("unregistered broker request relation")
        row = dict(view.snapshot)
        self.ingress_history.append({"role": request.role, "purpose": view.purpose,
                                     "thread_id": view._thread_id,
                                     "native_thread_id": view._native_thread_id,
                                     "lifecycle": row["lifecycle"]})
        if request.kind == "confirm":
            ack = request.ack
            if ack is None or self._pending is not ack._proposal:
                raise OperationalLeaseError("no exact pending proposal for this commit")
            proposal = ack._proposal
            if proposal.state != "PENDING" or ack._row_digest != _canonical(proposal.target):
                raise OperationalLeaseError("committed row digest/proposal mismatch")
            if proposal._previous is not None:
                self._live(clock, proposal._previous)
            current = self._live(clock, proposal._segment)
            self._active = proposal
            self._pending = None
            proposal.state = "ACTIVE"
            return self._observation(proposal.target, current)
        if view.purpose != "acquire":
            active = self._active
            if self._pending is not None or active is None or active.state != "ACTIVE":
                raise OperationalLeaseError("SQL history lacks ACTIVE exact broker generation")
            if row["proposed_row_digest"] != _canonical(row) or row != dict(active.target):
                raise OperationalLeaseError("locked row differs from ACTIVE generation")
            if row["durable_phase"] != "COMMITTED" or row["lifecycle"] == "TERMINAL":
                raise OperationalLeaseError("terminal durable row")
            current = self._live(clock, active._segment)
            if request.kind == "evaluate":
                return self._observation(row, current)
        elif self._active is not None or self._original is not None:
            raise OperationalLeaseError("acquisition origin cannot be reissued")
        if request.kind != "propose":
            raise OperationalLeaseError("acquisition requires real proposal")
        previous = self._active._segment if self._active is not None else None
        if view.purpose in {"acquire", "heartbeat"}:
            token = clock.begin_event("LEASE_" + view.purpose.upper())
            clock.mark_event(token)
            event = clock.end_event(token)
            deadline = clock.start_deadline(task_key=self.epoch + ":" + token.event_identity,
                                            origin=event, budget_ns=self.ttl_ns)
            segment = _Segment(token, event, deadline)
        else:
            if previous is None:
                raise OperationalLeaseError("bind requires original active segment")
            segment = previous
        if self._original is None:
            self._original = segment
        target = dict(row)
        target.update(generation=int(row["generation"]) + 1,
                      row_revision=int(row["row_revision"]) + 1,
                      original_acquisition_json=json.dumps(self._original.receipt(), sort_keys=True),
                      segment_json=json.dumps(segment.receipt(), sort_keys=True),
                      proposal_id=uuid4().hex, operation_sha256=view.operation_sha256,
                      durable_phase="COMMITTED")
        # Mutation target (actual job/attempt snapshot) is sealed by the transaction owner.
        target.update(view._repository_target)
        target["proposed_row_digest"] = _canonical(target)
        proposal = LeaseProposal(_token=_TOKEN, view=view, target=target, segment=segment,
                                 previous=previous)
        self._pending = proposal
        return proposal

    def _observation(self, row: Mapping[str, Any], current: OperationalBracket) -> OperationalLeaseObservation:
        return OperationalLeaseObservation(
            "VALID", (), self.domain,
            MappingProxyType(json.loads(row["original_acquisition_json"])),
            MappingProxyType(json.loads(row["segment_json"])),
            MappingProxyType({"domain": asdict(current.domain), "lower_ns": current.lower_ns,
                              "upper_ns": current.upper_ns}),
            str(row["job_id"]), str(row["lease_id"]), str(row["worker_id"]),
            row["attempt"], int(row["generation"]), str(row["original_policy_digest"]),
        )


def _issue_view(session: OperationalLeaseSession, repository: SQLiteSimulationJobRepository,
                connection: sqlite3.Connection, nonce: str, snapshot: Mapping[str, Any],
                purpose: str, operation_sha256: str) -> LockedLeaseView:
    session._check_ingress(purpose)
    if repository is not session.repository or not connection.in_transaction:
        raise OperationalLeaseError("issuer must own registered repository transaction")
    if len(operation_sha256) != 64 or any(c not in "0123456789abcdef" for c in operation_sha256):
        raise OperationalLeaseError("operation digest must be exact SHA256")
    if not repository._txn_is_current(connection, nonce):
        raise OperationalLeaseError("plain publication guard does not issue a view")
    view = LockedLeaseView(_token=_TOKEN, session=session, repository=repository,
                          connection=connection, nonce=nonce, snapshot=snapshot,
                          purpose=purpose, operation_sha256=operation_sha256)
    view._repository_target = {}  # only concrete current transaction seals target fields
    return view


def _make_ack(view: LockedLeaseView, proposal: LeaseProposal, commit_identity: str,
              row: Mapping[str, Any]) -> LeaseCommitAck:
    if view.state != "CONSUMED" or proposal._view is not view or proposal.state != "PENDING":
        raise OperationalLeaseError("commit does not match one-use proposal")
    if not view._repository._commit_is_recorded(view, commit_identity):
        raise OperationalLeaseError("actual successful commit registry required")
    if dict(row) != dict(proposal.target):
        raise OperationalLeaseError("committed reread differs from intended canonical row")
    view.state = "COMMITTED"
    ack = LeaseCommitAck(_token=_TOKEN, proposal=proposal, commit_identity=commit_identity,
                         row_digest=_canonical(row))
    view._ack = ack
    return ack


def _invalidate_view(view: LockedLeaseView, reason: str) -> None:
    with _REGISTRY_LOCK:
        if view._proposal is not None and view._proposal.state != "ACTIVE":
            view._proposal.state = "REVOKED"
            view._session.invalidate(reason)
        view.state = "INVALIDATED"


def _close_view(view: LockedLeaseView) -> None:
    with _REGISTRY_LOCK:
        if view._proposal is not None and view._proposal.state != "ACTIVE":
            _invalidate_view(view, "unconfirmed proposal scope exit")
        elif view._proposal is None or view.state == "INVALIDATED":
            view.state = "INVALIDATED"
        else:
            view.state = "CLOSED"
        _VIEWS.pop(id(view), None)
        if view._ack is not None:
            _ACKS.pop(id(view._ack), None)


def _current_session(repository: SQLiteSimulationJobRepository) -> OperationalLeaseSession | None:
    session = getattr(_SCOPE, "session", None)
    if type(session) is OperationalLeaseSession and session.repository is repository:
        return session
    return None


def _open_worker_lease_session(worker: SimulationWorker) -> OperationalLeaseSession:
    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository
    from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker

    if type(worker) is not SimulationWorker or sys._getframe(1).f_code is not SimulationWorker.poll_once.__code__:
        raise OperationalLeaseError("only genuine exact worker poll opens session")
    if not isinstance(worker.repository, SQLiteSimulationJobRepository) or worker.backend != "MUJOCO":
        raise OperationalLeaseError("operational route requires concrete SQLite/MUJOCO worker")
    if any(value is None for value in (worker.visual_role_binding, worker.visual_event_repository,
                                       worker.visual_robot_id)):
        raise OperationalLeaseError("complete actual visual configuration required")
    if worker._operational_lease_session is not None:
        raise OperationalLeaseError("worker already has a live poll session")
    return OperationalLeaseSession(_token=_TOKEN, worker=worker)


@contextmanager
def _worker_lease_scope(session: OperationalLeaseSession) -> Iterator[None]:
    if threading.get_ident() != session.main_thread or session._closed:
        raise OperationalLeaseError("original main lifecycle thread required")
    previous = getattr(_SCOPE, "session", None), getattr(_SCOPE, "role", None)
    _SCOPE.session, _SCOPE.role = session, "main"
    try:
        yield
    finally:
        _SCOPE.session, _SCOPE.role = previous


def _install_heartbeat_thread(session: OperationalLeaseSession, thread: threading.Thread) -> None:
    session._check_ingress("acquire")
    if session._heartbeat_thread is not None:
        raise OperationalLeaseError("heartbeat thread already installed")
    session._heartbeat_thread = thread


@contextmanager
def _heartbeat_lease_scope(session: OperationalLeaseSession) -> Iterator[None]:
    if threading.current_thread() is not session._heartbeat_thread:
        raise OperationalLeaseError("only installed actual heartbeat thread may enter")
    previous = getattr(_SCOPE, "session", None), getattr(_SCOPE, "role", None)
    _SCOPE.session, _SCOPE.role = session, "heartbeat"
    try:
        session._check_ingress("heartbeat")
        yield
    finally:
        _SCOPE.session, _SCOPE.role = previous


def _close_worker_lease_session(session: OperationalLeaseSession, *, reason: str) -> None:
    if type(session) is not OperationalLeaseSession:
        raise OperationalLeaseError("unregistered session close")
    session.invalidate(reason)  # fail closed before any join/wait
    session._closed = True
    session._stop.set()
    session._broker.join(timeout=1)
    session.join_failed = session.join_failed or session._broker.is_alive()


def _epoch_has_ended(epoch: str) -> bool:
    with _REGISTRY_LOCK:
        session = _SESSIONS.get(epoch)
        return session is not None and (session._closed or session._unusable.is_set())


def _revoke_epoch(epoch: str, reason: str) -> None:
    with _REGISTRY_LOCK:
        session = _SESSIONS.get(epoch)
    if session is not None:
        session.invalidate(reason)
