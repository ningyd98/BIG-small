"""Private OC1 lease issuer; stage A retains the independent legacy UTC veto.

Only the dedicated broker creates, reads and closes its D_lease clock. Detached
observations and SQL COMMITTED rows are history, never reconstructable authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import queue
import sqlite3
import sys
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, NoReturn, SupportsIndex, cast
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
    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
        SQLiteSimulationJobRepository,
    )
    from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker

_TOKEN = object()
_REGISTRY_LOCK = threading.RLock()
_SCOPE = threading.local()
_SESSIONS: dict[str, OperationalLeaseSession] = {}
_VIEWS: dict[int, _IssuedView] = {}
_VIEW_LIVES: dict[int, _ViewLife] = {}
_PROPOSALS: dict[int, _IssuedProposal] = {}
_PROPOSAL_STATES: dict[int, str] = {}
_ACKS: dict[int, _IssuedAck] = {}
_ACK_USES: dict[int, bool] = {}
_REQUESTS: dict[int, _RequestBinding] = {}
_REPLIES: dict[int, _ReplyBinding] = {}


class OperationalLeaseError(RuntimeError):
    """No current, genuine lease permission is available."""


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _canonical(row: Mapping[str, Any]) -> str:
    return _digest({key: value for key, value in row.items() if key != "proposed_row_digest"})


class _Opaque:
    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_sealed", False):
            raise OperationalLeaseError("issued binding/lifecycle is owner controlled")
        object.__setattr__(self, name, value)

    def __copy__(self) -> object:
        raise OperationalLeaseError("live lease capabilities cannot be copied")

    def __deepcopy__(self, memo: dict[int, object]) -> object:
        raise OperationalLeaseError("live lease capabilities cannot be copied")

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
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


@dataclass(frozen=True)
class _IssuedView:
    view: LockedLeaseView
    session: OperationalLeaseSession
    repository: SQLiteSimulationJobRepository
    database: Path
    connection: sqlite3.Connection
    nonce: str
    pid: int
    thread_id: int
    native_thread_id: int
    snapshot_json: str
    purpose: str
    operation_sha256: str


@dataclass
class _ViewLife:
    state: str = "OPEN"
    target_json: str = "{}"
    proposal: LeaseProposal | None = None
    ack: LeaseCommitAck | None = None


@dataclass(frozen=True)
class _IssuedProposal:
    proposal: LeaseProposal
    view: LockedLeaseView
    target_json: str
    segment: _Segment
    previous: _Segment | None
    binding: _IssuedView


@dataclass(frozen=True)
class _IssuedAck:
    ack: LeaseCommitAck
    proposal: LeaseProposal
    commit_identity: str
    row_digest: str


@dataclass(frozen=True)
class _RequestBinding:
    request: _Request
    kind: str
    view: LockedLeaseView | None
    ack: LeaseCommitAck | None
    role: str
    source_reply: _ReplyBinding | None


@dataclass(frozen=True)
class _ReplyBinding:
    source: _Request
    kind: str
    view: _IssuedView
    proposal: _IssuedProposal
    generation: int
    segments: tuple[_Segment, ...]


class LockedLeaseView(_Opaque):
    def __init__(
        self,
        *,
        _token: object,
        session: OperationalLeaseSession,
        repository: SQLiteSimulationJobRepository,
        connection: sqlite3.Connection,
        nonce: str,
        snapshot: Mapping[str, Any],
        purpose: str,
        operation_sha256: str,
    ) -> None:
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
        self._repository_target: Mapping[str, Any] = MappingProxyType({})
        self._proposal: LeaseProposal | None = None
        self._ack: LeaseCommitAck | None = None
        with _REGISTRY_LOCK:
            _VIEWS[id(self)] = _IssuedView(
                self,
                session,
                repository,
                repository.database_path.resolve(),
                connection,
                nonce,
                os.getpid(),
                self._thread_id,
                self._native_thread_id,
                self._snapshot_json,
                purpose,
                operation_sha256,
            )
            _VIEW_LIVES[id(self)] = _ViewLife()
        self._sealed = True

    @property
    def snapshot(self) -> Mapping[str, Any]:
        return MappingProxyType(json.loads(self._snapshot_json))


class LeaseProposal(_Opaque):
    def __init__(
        self,
        *,
        _token: object,
        view: LockedLeaseView,
        target: Mapping[str, Any],
        segment: _Segment,
        previous: _Segment | None,
    ) -> None:
        if _token is not _TOKEN:
            raise OperationalLeaseError("proposal is broker issued")
        self._view = view
        self._target_json = json.dumps(dict(target), sort_keys=True, allow_nan=False)
        self._segment = segment
        self._previous = previous
        self.state = "PENDING"
        with _REGISTRY_LOCK:
            _PROPOSALS[id(self)] = _IssuedProposal(
                self, view, self._target_json, segment, previous, _view_record(view)
            )
            _PROPOSAL_STATES[id(self)] = "PENDING"
        self._sealed = True

    @property
    def target(self) -> Mapping[str, Any]:
        return MappingProxyType(json.loads(self._target_json))


class LeaseCommitAck(_Opaque):
    def __init__(
        self, *, _token: object, proposal: LeaseProposal, commit_identity: str, row_digest: str
    ) -> None:
        if _token is not _TOKEN:
            raise OperationalLeaseError("ack is created only by real commit owner")
        self._proposal = proposal
        self._commit_identity = commit_identity
        self._row_digest = row_digest
        self._used = False
        with _REGISTRY_LOCK:
            _ACKS[id(self)] = _IssuedAck(self, proposal, commit_identity, row_digest)
            _ACK_USES[id(self)] = False
        self._sealed = True


def _view_record(view: LockedLeaseView) -> _IssuedView:
    with _REGISTRY_LOCK:
        issued = _VIEWS.get(id(view))
        life = _VIEW_LIVES.get(id(view))
        if (
            type(view) is not LockedLeaseView
            or issued is None
            or issued.view is not view
            or life is None
        ):
            raise OperationalLeaseError("unregistered issued view")
        if (
            issued.pid != os.getpid()
            or view._session is not issued.session
            or view._repository is not issued.repository
            or issued.repository.database_path.resolve() != issued.database
            or view._connection is not issued.connection
            or view._nonce != issued.nonce
            or (view._thread_id, view._native_thread_id)
            != (issued.thread_id, issued.native_thread_id)
            or view._snapshot_json != issued.snapshot_json
            or view.purpose != issued.purpose
            or view.operation_sha256 != issued.operation_sha256
            or view.state != life.state
            or view._proposal is not life.proposal
            or view._ack is not life.ack
            or dict(view._repository_target) != json.loads(life.target_json)
        ):
            raise OperationalLeaseError("issued view binding/lifecycle retargeted")
        return issued


def _proposal_record(proposal: LeaseProposal) -> _IssuedProposal:
    with _REGISTRY_LOCK:
        issued = _PROPOSALS.get(id(proposal))
        if (
            type(proposal) is not LeaseProposal
            or issued is None
            or issued.proposal is not proposal
            or proposal._view is not issued.view
            or proposal._target_json != issued.target_json
            or proposal._segment is not issued.segment
            or proposal._previous is not issued.previous
            or proposal.state != _PROPOSAL_STATES.get(id(proposal))
        ):
            raise OperationalLeaseError("proposal binding/lifecycle mismatch")
        bound = issued.binding
        view = issued.view
        if (
            bound.pid != os.getpid()
            or view._session is not bound.session
            or view._repository is not bound.repository
            or bound.repository.database_path.resolve() != bound.database
            or view._connection is not bound.connection
            or view._nonce != bound.nonce
            or view._snapshot_json != bound.snapshot_json
            or view.purpose != bound.purpose
            or view.operation_sha256 != bound.operation_sha256
            or (view._thread_id, view._native_thread_id)
            != (bound.thread_id, bound.native_thread_id)
        ):
            raise OperationalLeaseError("proposal original issued view binding changed")
        return issued


def _ack_record(ack: LeaseCommitAck) -> _IssuedAck:
    with _REGISTRY_LOCK:
        issued = _ACKS.get(id(ack))
        if (
            type(ack) is not LeaseCommitAck
            or issued is None
            or issued.ack is not ack
            or ack._proposal is not issued.proposal
            or ack._commit_identity != issued.commit_identity
            or ack._row_digest != issued.row_digest
            or ack._used != _ACK_USES.get(id(ack))
        ):
            raise OperationalLeaseError("ack binding/lifecycle mismatch")
        _proposal_record(issued.proposal)
        return issued


def _set_view_state(view: LockedLeaseView, state: str) -> None:
    with _REGISTRY_LOCK:
        _VIEW_LIVES[id(view)].state = state
        object.__setattr__(view, "state", state)


def _set_proposal_state(proposal: LeaseProposal, state: str) -> None:
    with _REGISTRY_LOCK:
        _PROPOSAL_STATES[id(proposal)] = state
        object.__setattr__(proposal, "state", state)


def _seal_repository_target(view: LockedLeaseView, target: Mapping[str, Any]) -> None:
    issued = _view_record(view)
    if sys._getframe(1).f_code not in {
        issued.repository._dispatch_writer.__code__,
        issued.repository._acquire_operational.__code__,
    }:
        raise OperationalLeaseError("only the actual repository dispatcher seals a target")
    if not issued.repository._view_is_current(view):
        raise OperationalLeaseError("only actual transaction owner seals mutation target")
    encoded = json.dumps(dict(target), sort_keys=True, allow_nan=False)
    with _REGISTRY_LOCK:
        _VIEW_LIVES[id(view)].target_json = encoded
        object.__setattr__(view, "_repository_target", MappingProxyType(json.loads(encoded)))


@dataclass(frozen=True)
class _Segment:
    token: OperationalEventToken
    event: OperationalBracket
    deadline: OperationalDeadline

    def receipt(self) -> dict[str, Any]:
        return {
            "domain": asdict(self.event.domain),
            "event_id": self.token.event_identity,
            "lower_ns": self.event.lower_ns,
            "upper_ns": self.event.upper_ns,
            "deadline_ns": self.deadline.deadline_ns,
            "budget_ns": self.deadline.budget_ns,
            "end_exclusive": True,
        }


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
    source_reply: _ReplyBinding | None = None


def _request_record(request: _Request) -> _RequestBinding:
    with _REGISTRY_LOCK:
        binding = _REQUESTS.get(id(request))
        if (
            binding is None
            or binding.request is not request
            or request.kind != binding.kind
            or request.view is not binding.view
            or request.ack is not binding.ack
            or request.role != binding.role
            or request.source_reply is not binding.source_reply
        ):
            raise OperationalLeaseError("request relation is not the issued exact operation")
        return binding


class OperationalLeaseSession(_Opaque):
    def __init__(self, *, _token: object, worker: SimulationWorker) -> None:
        if _token is not _TOKEN:
            raise OperationalLeaseError("session requires genuine worker poll lifecycle")
        ttl = worker.lease_ttl_seconds
        if type(ttl) is not int or not math.isfinite(ttl) or ttl <= 0:
            raise OperationalLeaseError("frozen TTL must be positive finite integer seconds")
        self.worker = worker
        self._mode = worker._frozen_operational_time_mode
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
        self._broker = threading.Thread(
            target=self._serve, name="operational-lease-broker", daemon=True
        )
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
                self.main_thread,
                self.main_native_thread,
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
        if (
            self.worker.visual_role_binding is not self._binding
            or self._binding is None
            or _digest(self._binding.evidence()) != self._binding_hash
            or self.worker.lease_ttl_seconds * 1_000_000_000 != self.ttl_ns
        ):
            self.invalidate("worker original policy changed")
            raise OperationalLeaseError("worker frozen source/TTL policy changed")
        if (self.worker._frozen_operational_time_mode != self._mode
                or (self._mode != "LOCAL_TEMPORAL_PUBLICATION_V1"
                    and self.worker.operational_time_mode != self._mode)):
            self.invalidate("worker mode changed while active")
            raise OperationalLeaseError("worker frozen mode changed")
        return str(role)

    def _view(self, view: LockedLeaseView, *, committed: bool = False) -> None:
        if type(view) is not LockedLeaseView:
            raise OperationalLeaseError("caller descriptors cannot register locked views")
        issued = _view_record(view)
        if issued.session is not self:
            raise OperationalLeaseError("foreign issued view")
        if (view._thread_id, view._native_thread_id) != (
            threading.get_ident(),
            threading.get_native_id(),
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
        if request.ack is not None:
            purpose = _ack_record(request.ack).proposal._view.purpose
        request.role = self._check_ingress(purpose)
        check: _Request | None = None
        with _REGISTRY_LOCK:
            _REQUESTS[id(request)] = _RequestBinding(
                request, request.kind, request.view, request.ack, request.role, None
            )
        try:
            self._queue.put(request)
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
            with _REGISTRY_LOCK:
                reply = _REPLIES.get(id(request))
            if reply is None or reply.source is not request:
                raise OperationalLeaseError("missing exact operation response binding")
            check = _Request("consume", source_reply=reply, role=request.role)
            with _REGISTRY_LOCK:
                _REQUESTS[id(check)] = _RequestBinding(
                    check, "consume", None, None, request.role, reply
                )
            self._queue.put(check)
            if not check.completed.wait(self.wait_cap):
                check.cancelled.set()
                request.cancelled.set()
                self.invalidate("response consumption timeout")
                raise OperationalLeaseError("response consumption timed out")
            if (
                check.error is not None
                or self._unusable.is_set()
                or check.cancelled.is_set()
                or request.cancelled.is_set()
            ):
                self.invalidate("response crossed original operation segment bound")
                raise OperationalLeaseError("response crossed original lease bound")
            return request.result
        finally:
            with _REGISTRY_LOCK:
                _REQUESTS.pop(id(request), None)
                _REPLIES.pop(id(request), None)
                if check is not None:
                    _REQUESTS.pop(id(check), None)

    def _bind_reply(self, request: _Request, proposal: LeaseProposal) -> None:
        binding = _request_record(request)
        if binding.view is None:
            raise OperationalLeaseError("response needs original issued view")
        issued_view = _view_record(binding.view)
        issued_proposal = _proposal_record(proposal)
        segments = (
            (issued_proposal.previous, issued_proposal.segment)
            if binding.kind in {"propose", "confirm"} and issued_proposal.previous is not None
            else (issued_proposal.segment,)
        )
        with _REGISTRY_LOCK:
            _REPLIES[id(request)] = _ReplyBinding(
                request,
                binding.kind,
                issued_view,
                issued_proposal,
                int(json.loads(issued_proposal.target_json)["generation"]),
                segments,
            )

    def evaluate_locked(self, view: LockedLeaseView) -> OperationalLeaseObservation:
        self._check_ingress(view.purpose if type(view) is LockedLeaseView else "inspect")
        self._view(view)
        observation = self._rpc(_Request("evaluate", view=view))
        _set_view_state(view, "DECIDED")
        return cast(OperationalLeaseObservation, observation)

    def propose_locked(self, view: LockedLeaseView, *, ttl_ns: int) -> LeaseProposal:
        self._check_ingress(view.purpose if type(view) is LockedLeaseView else "inspect")
        self._view(view)
        if type(ttl_ns) is not int or ttl_ns != self.ttl_ns:
            raise OperationalLeaseError("renewal cannot change frozen TTL policy")
        if view._proposal is not None:
            raise OperationalLeaseError("view proposal already issued")
        proposal = self._rpc(_Request("propose", view=view))
        with _REGISTRY_LOCK:
            _VIEW_LIVES[id(view)].proposal = proposal
            object.__setattr__(view, "_proposal", proposal)
        _set_view_state(view, "CONSUMED")
        return cast(LeaseProposal, proposal)

    def confirm_committed(self, ack: LeaseCommitAck) -> OperationalLeaseObservation:
        if type(ack) is not LeaseCommitAck:
            raise OperationalLeaseError("unregistered commit descriptor")
        _ack_record(ack)
        if _ACK_USES[id(ack)]:
            raise OperationalLeaseError("commit acknowledgement replay")
        view = ack._proposal._view
        self._check_ingress(view.purpose)
        self._view(view, committed=True)
        with _REGISTRY_LOCK:
            _ACK_USES[id(ack)] = True
            object.__setattr__(ack, "_used", True)
        return cast(OperationalLeaseObservation, self._rpc(_Request("confirm", view=view, ack=ack)))

    def invalidate(self, reason: str) -> None:
        self._unusable.set()
        self.cleanup_reason = reason
        with _REGISTRY_LOCK:
            for issued in _PROPOSALS.values():
                if issued.binding.session is self:
                    _set_proposal_state(issued.proposal, "REVOKED")
            for issued_view in _VIEWS.values():
                if issued_view.session is self and issued_view.view.state not in {
                    "CLOSED",
                    "INVALIDATED",
                }:
                    _set_view_state(issued_view.view, "INVALIDATED")

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
                    _request_record(request)
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
        binding = _request_record(request)
        if binding.kind == "consume":
            reply = binding.source_reply
            if reply is None or reply.source.cancelled.is_set() or self._unusable.is_set():
                raise OperationalLeaseError("consumption cancelled or missing original response")
            with _REGISTRY_LOCK:
                if _REPLIES.get(id(reply.source)) is not reply:
                    raise OperationalLeaseError("consumption response relation expired")
            source = _request_record(reply.source)
            if source.kind != reply.kind or source.view is not reply.view.view:
                raise OperationalLeaseError("consumption does not match original operation")
            _view_record(reply.view.view)
            issued_proposal = _proposal_record(reply.proposal.proposal)
            if (
                issued_proposal is not reply.proposal
                or int(json.loads(issued_proposal.target_json)["generation"]) != reply.generation
            ):
                raise OperationalLeaseError("consumption generation binding changed")
            for segment in reply.segments:
                self._live(clock, segment)
            if (
                reply.source.cancelled.is_set()
                or request.cancelled.is_set()
                or self._unusable.is_set()
            ):
                raise OperationalLeaseError("late consume cannot expose response")
            return None
        view = binding.view
        if view is None or _view_record(view).session is not self:
            raise OperationalLeaseError("missing original registered request view")
        row = dict(view.snapshot)
        self.ingress_history.append(
            {
                "role": request.role,
                "purpose": view.purpose,
                "thread_id": view._thread_id,
                "native_thread_id": view._native_thread_id,
                "lifecycle": row["lifecycle"],
            }
        )
        if request.kind == "confirm":
            ack = request.ack
            if ack is None or self._pending is not ack._proposal:
                raise OperationalLeaseError("no exact pending proposal for this commit")
            _ack_record(ack)
            proposal = ack._proposal
            _proposal_record(proposal)
            if proposal.state != "PENDING" or ack._row_digest != _canonical(proposal.target):
                raise OperationalLeaseError("committed row digest/proposal mismatch")
            if proposal._previous is not None:
                self._live(clock, proposal._previous)
            current = self._live(clock, proposal._segment)
            self._active = proposal
            self._pending = None
            _set_proposal_state(proposal, "ACTIVE")
            self._bind_reply(request, proposal)
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
                self._bind_reply(request, active)
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
            deadline = clock.start_deadline(
                task_key=self.epoch + ":" + token.event_identity,
                origin=event,
                budget_ns=self.ttl_ns,
            )
            segment = _Segment(token, event, deadline)
        else:
            if previous is None:
                raise OperationalLeaseError("bind requires original active segment")
            segment = previous
        if self._original is None:
            self._original = segment
        target = dict(row)
        target.update(
            generation=int(row["generation"]) + 1,
            row_revision=int(row["row_revision"]) + 1,
            original_acquisition_json=json.dumps(self._original.receipt(), sort_keys=True),
            segment_json=json.dumps(segment.receipt(), sort_keys=True),
            proposal_id=uuid4().hex,
            operation_sha256=view.operation_sha256,
            durable_phase="COMMITTED",
        )
        # Mutation target (actual job/attempt snapshot) is sealed by the transaction owner.
        target.update(view._repository_target)
        target["proposed_row_digest"] = _canonical(target)
        proposal = LeaseProposal(
            _token=_TOKEN, view=view, target=target, segment=segment, previous=previous
        )
        self._pending = proposal
        self._bind_reply(request, proposal)
        return proposal

    def _observation(
        self, row: Mapping[str, Any], current: OperationalBracket
    ) -> OperationalLeaseObservation:
        return OperationalLeaseObservation(
            "VALID",
            (),
            self.domain,
            MappingProxyType(json.loads(row["original_acquisition_json"])),
            MappingProxyType(json.loads(row["segment_json"])),
            MappingProxyType(
                {
                    "domain": asdict(current.domain),
                    "lower_ns": current.lower_ns,
                    "upper_ns": current.upper_ns,
                }
            ),
            str(row["job_id"]),
            str(row["lease_id"]),
            str(row["worker_id"]),
            row["attempt"],
            int(row["generation"]),
            str(row["original_policy_digest"]),
        )


def _issue_view(
    session: OperationalLeaseSession,
    repository: SQLiteSimulationJobRepository,
    connection: sqlite3.Connection,
    nonce: str,
    snapshot: Mapping[str, Any],
    purpose: str,
    operation_sha256: str,
) -> LockedLeaseView:
    session._check_ingress(purpose)
    if repository is not session.repository or not connection.in_transaction:
        raise OperationalLeaseError("issuer must own registered repository transaction")
    if len(operation_sha256) != 64 or any(c not in "0123456789abcdef" for c in operation_sha256):
        raise OperationalLeaseError("operation digest must be exact SHA256")
    if not repository._txn_is_current(connection, nonce):
        raise OperationalLeaseError("plain publication guard does not issue a view")
    view = LockedLeaseView(
        _token=_TOKEN,
        session=session,
        repository=repository,
        connection=connection,
        nonce=nonce,
        snapshot=snapshot,
        purpose=purpose,
        operation_sha256=operation_sha256,
    )
    return view


def _make_ack(
    view: LockedLeaseView, proposal: LeaseProposal, commit_identity: str, row: Mapping[str, Any]
) -> LeaseCommitAck:
    issued = _view_record(view)
    if sys._getframe(1).f_code is not issued.repository._commit_operational_proposal.__code__:
        raise OperationalLeaseError("only the actual commit owner creates an acknowledgement")
    _proposal_record(proposal)
    if view.state != "CONSUMED" or proposal._view is not view or proposal.state != "PENDING":
        raise OperationalLeaseError("commit does not match one-use proposal")
    if not view._repository._commit_is_recorded(view, commit_identity):
        raise OperationalLeaseError("actual successful commit registry required")
    if dict(row) != dict(proposal.target):
        raise OperationalLeaseError("committed reread differs from intended canonical row")
    _set_view_state(view, "COMMITTED")
    ack = LeaseCommitAck(
        _token=_TOKEN,
        proposal=proposal,
        commit_identity=commit_identity,
        row_digest=_canonical(row),
    )
    with _REGISTRY_LOCK:
        _VIEW_LIVES[id(view)].ack = ack
        object.__setattr__(view, "_ack", ack)
    return ack


def _invalidate_view(view: LockedLeaseView, reason: str) -> None:
    with _REGISTRY_LOCK:
        if view._proposal is not None and view._proposal.state != "ACTIVE":
            _set_proposal_state(view._proposal, "REVOKED")
            view._session.invalidate(reason)
        _set_view_state(view, "INVALIDATED")


def _close_view(view: LockedLeaseView) -> None:
    with _REGISTRY_LOCK:
        if view._proposal is not None and view._proposal.state != "ACTIVE":
            _invalidate_view(view, "unconfirmed proposal scope exit")
        elif view._proposal is None or view.state == "INVALIDATED":
            _set_view_state(view, "INVALIDATED")
        else:
            _set_view_state(view, "CLOSED")
        _VIEWS.pop(id(view), None)
        _VIEW_LIVES.pop(id(view), None)
        if view._ack is not None:
            _ACKS.pop(id(view._ack), None)
            _ACK_USES.pop(id(view._ack), None)


def _current_session(repository: SQLiteSimulationJobRepository) -> OperationalLeaseSession | None:
    session = getattr(_SCOPE, "session", None)
    if type(session) is OperationalLeaseSession and session.repository is repository:
        return session
    return None


def _open_worker_lease_session(worker: SimulationWorker) -> OperationalLeaseSession:
    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
        SQLiteSimulationJobRepository,
    )
    from cloud_edge_robot_arm.simulation_runtime.worker import (
        SimulationWorker,
        _GENUINE_WORKER_MODULE_GLOBALS,
        _GENUINE_WORKER_POLL_CODE,
    )

    caller = sys._getframe(1)
    if (
        type(worker) is not SimulationWorker
        or caller.f_code is not _GENUINE_WORKER_POLL_CODE
        or caller.f_globals is not _GENUINE_WORKER_MODULE_GLOBALS
        or caller.f_locals.get("self") is not worker
    ):
        raise OperationalLeaseError("only genuine exact worker poll opens session")
    if (
        not isinstance(worker.repository, SQLiteSimulationJobRepository)
        or worker.backend != "MUJOCO"
    ):
        raise OperationalLeaseError("operational route requires concrete SQLite/MUJOCO worker")
    if any(
        value is None
        for value in (
            worker.visual_role_binding,
            worker.visual_event_repository,
            worker.visual_robot_id,
        )
    ):
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
