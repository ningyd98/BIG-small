"""Worker-owned local windows; typed D obligations intersect the real UTC lease.

Exported JSON is descriptive. Only the exact current startup registry entry on
its original owner thread can use a live window. P6 dispatch/transactions and
D lease production remain separate from these local software constraints.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from decimal import ROUND_FLOOR, Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from cloud_edge_robot_arm.research.operational_time_v1 import (
    OperationalBracket,
    OperationalClockOwner,
    OperationalDeadline,
    OperationalEventToken,
    OperationalTimeError,
    open_operational_clock,
)
from cloud_edge_robot_arm.vision.worker_owner import (
    pin_worker_source_inventory,
    read_visual_worker_lease,
)

if TYPE_CHECKING:
    from cloud_edge_robot_arm.edge.evidence.models import EvidenceVerdict
    from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker

_FIVE_NS = 5_000_000_000
_SCHEMA = "simulation.operational-window.v1"
_KINDS = frozenset(
    {"bootstrap", "capture", "plan", "grounding", "supervision", "marker", "condition"}
)
_PENDING: dict[object, _Startup] = {}
_OWNERS: dict[object, OperationalWindowOwner] = {}
_HANDOFFS: dict[object, OperationalWindowOwner] = {}
_SCOPES: dict[int, list[OperationalWindowOwner]] = {}
_TRANSITIONS: dict[int, tuple[OperationalWindowOwner, str, tuple[str, ...]]] = {}
_CONSTRUCTION = object()


def _descriptor_plain(value: object) -> Any:
    """Detach JSON data without coercion; acyclic aliases are allowed."""
    active: set[int] = set()

    def plain(item: object) -> Any:
        if item is None or type(item) in {str, bool, int}:
            return item
        if type(item) is float:
            if not math.isfinite(item):
                raise ValueError("nonfinite operational JSON number")
            return item
        if isinstance(item, Mapping) or type(item) in {list, tuple}:
            identity = id(item)
            if identity in active:
                raise ValueError("cyclic operational JSON data")
            active.add(identity)
            try:
                if isinstance(item, Mapping):
                    if any(type(key) is not str for key in item):
                        raise ValueError("operational JSON keys must be strings")
                    return {key: plain(value) for key, value in item.items()}
                return [plain(value) for value in item]
            finally:
                active.remove(identity)
        raise ValueError("unsupported operational JSON value")

    return plain(value)


def _json(value: object) -> str:
    return json.dumps(
        _descriptor_plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _hash(value: object) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _seconds_ns(value: object) -> int:
    if type(value) not in {int, float}:
        raise OperationalTimeError("original positive duration source required")
    duration = Decimal(str(value))
    if not duration.is_finite() or duration <= 0:
        raise OperationalTimeError("original positive finite duration required")
    result = int((duration * 1_000_000_000).to_integral_value(rounding=ROUND_FLOOR))
    if result <= 0:
        raise OperationalTimeError("duration has no supported positive integer budget")
    return result


def _job_source(job: object) -> str:
    names = (
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
        "manifest",
        "reproducibility_hash",
        "source_commit",
        "source_tree_hash",
    )
    return _hash({name: getattr(job, name) for name in names})


@dataclass(frozen=True)
class _Startup:
    worker: object
    repository: object
    job_id: str
    run_id: str
    lease_id: str
    attempt: int
    acquired_at: object
    job_source: str
    task_ns: int
    verification_ns: int
    binding: object
    binding_hash: str
    thread_id: int


@dataclass(frozen=True)
class _Age:
    event: OperationalBracket
    budget_ns: int
    source_id: str


@dataclass(frozen=True)
class _Hard:
    deadline: OperationalDeadline
    source_id: str


@dataclass(frozen=True)
class _Window:
    kind: str
    event: OperationalBracket
    budget_ns: int
    parents: tuple[str, ...]
    ages: tuple[_Age, ...]
    hard: tuple[_Hard, ...]


def _prepare_startup(worker: SimulationWorker, job: object) -> bool:
    """Called only by real _execute after RUNNING and its unique open attempt."""
    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
        SQLiteSimulationJobRepository,
    )
    from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker
    from cloud_edge_robot_arm.simulation_workbench.models import ExperimentDraft
    from cloud_edge_robot_arm.vision.runtime_binding import RoleRuntimeBinding

    if getattr(worker, "_operational_prefix_application", None) is not None or (
        getattr(worker, "_native_clock_prefix_application", None) is not None
    ):
        return False
    if worker.visual_role_binding is None:
        return False
    draft = ExperimentDraft.model_validate(job.draft)
    if not (
        job.backend == "MUJOCO"
        and job.scenario_id == "S01_NORMAL_STATIC"
        and draft.input_mode == "RGBD"
        and draft.execution_scope == "VISION_CLOSED_LOOP"
        and worker.visual_role_binding is not None
    ):
        return False
    if (
        type(worker) is not SimulationWorker
        or type(worker.repository) is not SQLiteSimulationJobRepository
    ):
        raise OperationalTimeError("exact current SQLite visual worker required")
    if (
        type(worker.visual_role_binding) is not RoleRuntimeBinding
        or worker.active_job_id != job.job_id
    ):
        raise OperationalTimeError("actual visual startup binding required")
    if worker in _PENDING or worker in _OWNERS:
        raise OperationalTimeError("startup cannot be issued twice")
    current = worker.repository.get_job(job.job_id)
    lease = read_visual_worker_lease(
        worker.repository,
        job_id=current.job_id,
        run_id=current.run_id,
        worker_id=worker.worker_id,
        lease_id=current.lease_id,
    )
    binding = worker.visual_role_binding
    binding_hash = _hash(binding.evidence())
    policy = binding.evidence()["edge_policy"]["verification_budget"]
    _PENDING[worker] = _Startup(
        worker,
        worker.repository,
        current.job_id,
        current.run_id,
        current.lease_id,
        lease.attempt,
        lease.acquired_at,
        _job_source(current),
        _seconds_ns(current.timeout_seconds),
        _seconds_ns(policy["deadline_s"]),
        binding,
        binding_hash,
        threading.get_ident(),
    )
    return True


class OperationalWindowOwner:
    """Opaque lifecycle owner. Public descriptors cannot construct or install it."""

    def __init__(self, startup: _Startup, *, _capability: object) -> None:
        if _capability is not _CONSTRUCTION:
            raise OperationalTimeError("use genuine normal worker startup")
        self._startup = startup
        self._clock = open_operational_clock()
        self._closed = False
        self._windows: dict[str, _Window] = {}
        self._observations: dict[str, tuple[OperationalBracket, str]] = {}
        self._observation_values: dict[str, object] = {}
        self._references: dict[tuple[str, str, int], str] = {}
        self._policies: dict[tuple[str, str], tuple[int, str]] = {}
        self._maximum_ages: dict[str, tuple[int, str]] = {}
        self._source_root: object | None = None
        self._source_hashes: dict[str, str] | None = None
        self._source_identity = startup.job_source
        self._origin_tuple: object | None = None
        self._episode_id: str | None = None
        self.task_origin_token: OperationalEventToken | None = None
        self.task_origin: OperationalBracket | None = None
        self.task_window: str | None = None
        self._hard: tuple[_Hard, ...] = ()

    def __copy__(self) -> object:
        raise OperationalTimeError("live window owners cannot be copied")

    def __deepcopy__(self, memo: dict[int, object]) -> object:
        raise OperationalTimeError("live window owners cannot be copied")

    def __reduce_ex__(self, protocol: int) -> object:
        raise OperationalTimeError("live window owners cannot be serialized")

    @classmethod
    def from_worker(cls, worker: SimulationWorker, *, job_id: str) -> OperationalWindowOwner:
        from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker

        if cls is not OperationalWindowOwner or type(worker) is not SimulationWorker:
            raise OperationalTimeError("unissued or already consumed startup capability")
        if worker not in _PENDING:
            raise OperationalTimeError("unissued or already consumed startup capability")
        startup = _PENDING.pop(worker)
        if startup.worker is not worker or startup.job_id != job_id:
            raise OperationalTimeError("startup identity mismatch")
        owner = cls(startup, _capability=_CONSTRUCTION)
        _OWNERS[worker] = owner
        try:
            owner._check_live()
        except Exception:
            _revoke_worker(worker)
            raise
        return owner

    @property
    def clock(self) -> OperationalClockOwner:
        self._check_live()
        return self._clock

    def _check_live(self) -> None:
        s = self._startup
        worker = s.worker
        if self._closed or _OWNERS.get(worker) is not self or threading.get_ident() != s.thread_id:
            raise OperationalTimeError("current exact owner-thread startup unavailable")
        if (
            worker.repository is not s.repository
            or worker.active_job_id != s.job_id
            or worker.visual_role_binding is not s.binding
        ):
            raise OperationalTimeError("worker startup source changed")
        if _hash(s.binding.evidence()) != s.binding_hash:
            raise OperationalTimeError("original role policy source changed")
        current = worker.repository.get_job(s.job_id)
        try:
            lease = read_visual_worker_lease(
                worker.repository,
                job_id=s.job_id,
                run_id=s.run_id,
                worker_id=worker.worker_id,
                lease_id=s.lease_id,
            )
        except (ValueError, TypeError, KeyError) as error:
            _revoke_worker(worker)
            raise OperationalTimeError("actual UTC lease/attempt veto") from error
        if (
            lease.attempt != s.attempt
            or lease.acquired_at != s.acquired_at
            or _job_source(current) != s.job_source
        ):
            _revoke_worker(worker)
            raise OperationalTimeError("original job/attempt/fencing source changed")
        if self._origin_tuple is not None and worker._active_task_origin != self._origin_tuple:
            raise OperationalTimeError("original task origin changed")
        _ = self._clock.domain  # OC1 retains its exact process/thread/boot checks.
        if self._source_hashes is not None:
            pin_worker_source_inventory(
                self._source_root,
                self._source_hashes,
                required_paths=frozenset(self._source_hashes),
            )

    def _begin_origin(self) -> None:
        self._check_live()
        self.task_origin_token = self._clock.begin_event("ORIGINAL_TASK_D")

    def _mark_origin(self) -> None:
        self._clock.mark_event(self.task_origin_token)

    def _seal_origin(self, original_tuple: object) -> None:
        if self.task_origin is not None:
            raise OperationalTimeError("original origin cannot be refreshed")
        self.task_origin = self._clock.end_event(self.task_origin_token)
        self._origin_tuple = original_tuple
        s = self._startup
        self._hard = tuple(
            _Hard(
                self._clock.start_deadline(task_key=key, origin=self.task_origin, budget_ns=budget),
                key,
            )
            for key, budget in (
                (s.job_source + ":task", s.task_ns),
                (s.binding_hash + ":verification", s.verification_ns),
            )
        )
        self.task_window = self.issue(
            "bootstrap", self.task_origin, budget_ns=s.task_ns, parent_ids=()
        )

    def _bind_inputs(self, source: object, limits: object) -> None:
        self._check_live()
        s = self._startup
        if source.job_repository is not s.worker.repository or (
            source.job_id,
            source.run_id,
            source.worker_id,
            source.lease_id,
        ) != (s.job_id, s.run_id, s.worker.worker_id, s.lease_id):
            raise OperationalTimeError("runtime source differs from actual startup")
        if (
            source.task_started_at != self._origin_tuple[2]
            or _seconds_ns(source.task_timeout_s) != s.task_ns
        ):
            raise OperationalTimeError("late runtime changed original task budget")
        if asdict(limits) != s.binding.evidence()["edge_policy"]["verification_budget"]:
            raise OperationalTimeError("verification budget source changed")
        hashes = dict(source.source_hashes)
        if self._source_hashes is not None and hashes != self._source_hashes:
            raise OperationalTimeError("original inventory cannot be rebound")
        self._source_root = source.source_root
        self._source_hashes = hashes
        self._source_identity = _hash(
            {
                "job": s.job_source,
                "role": s.binding_hash,
                "sources": hashes,
                "robot": source.robot_id,
                "plan": source.plan_id,
            }
        )
        self._check_live()

    def issue(
        self, kind: str, event: OperationalBracket, *, budget_ns: int, parent_ids: tuple[str, ...]
    ) -> str:
        self._check_live()
        cap = self._startup.task_ns if kind == "bootstrap" else _FIVE_NS
        if kind not in _KINDS or type(budget_ns) is not int or not 0 < budget_ns <= cap:
            raise OperationalTimeError("unregistered kind or enlarged original budget")
        if type(parent_ids) is not tuple or len(set(parent_ids)) != len(parent_ids):
            raise OperationalTimeError("exact issued parent identities required")
        # An actual OC1 event and its own current establish authenticity/causality.
        self._clock.age_bounds(event, self._clock.read_current(after=_event_token(self, event)))
        if kind == "bootstrap" and event is not self.task_origin:
            raise OperationalTimeError("bootstrap hard origin must be original task receipt")
        parents = []
        for name in parent_ids:
            if type(name) is not str or name not in self._windows:
                raise OperationalTimeError("foreign/unissued parent")
            parents.append(self._windows[name])
        identifier = uuid4().hex
        ages = (
            []
            if kind == "bootstrap"
            else [_Age(event, budget_ns, self._source_identity + ":" + kind)]
        )
        hard = list(self._hard)
        if kind == "bootstrap":
            hard.append(
                _Hard(
                    self._clock.start_deadline(
                        task_key=identifier, origin=self.task_origin, budget_ns=budget_ns
                    ),
                    self._source_identity + ":bootstrap",
                )
            )
        for parent in parents:
            ages.extend(parent.ages)
            hard.extend(parent.hard)
        ages = list({(id(a.event), a.budget_ns, a.source_id): a for a in ages}.values())
        hard = list({id(h.deadline): h for h in hard}.values())
        self._windows[identifier] = _Window(
            kind, event, budget_ns, parent_ids, tuple(ages), tuple(hard)
        )
        return identifier

    def check(self, window_id: str, *, after: OperationalEventToken) -> EvidenceVerdict:
        from cloud_edge_robot_arm.edge.evidence.models import EvidenceVerdict

        try:
            self._check_live()
            window = self._windows[window_id]
            # Reject an unrelated/before event; each actual constraint gets its own paired read.
            relevant = [
                window.event,
                *(a.event for a in window.ages),
                *(h.deadline.origin for h in window.hard),
            ]
            if not any(_event_token(self, receipt) is after for receipt in relevant):
                raise OperationalTimeError("after token unrelated to original obligations")
            self._clock.read_current(after=after)
            for age in window.ages:
                current = self._clock.read_current(after=_event_token(self, age.event))
                if not self._clock.within_age(age.event, current, max_age_ns=age.budget_ns):
                    return EvidenceVerdict("INVALID", ("original_age_exhausted",))
            for hard in window.hard:
                current = self._clock.read_current(after=_event_token(self, hard.deadline.origin))
                if not self._clock.before_deadline(hard.deadline, current):
                    return EvidenceVerdict("INVALID", ("original_hard_deadline_exhausted",))
            self._check_live()
            return EvidenceVerdict("VALID", ())
        except (OperationalTimeError, ValueError, TypeError, KeyError, OSError):
            return EvidenceVerdict("UNKNOWN", ("operational_window_authority_unavailable",))

    def export_record(self, window_id: str) -> dict[str, Any]:
        self._check_live()
        window = self._windows[window_id]
        ages = [
            {
                "event_id": _event_token(self, age.event).event_identity,
                "source_id": age.source_id,
                "lower_ns": age.event.lower_ns,
                "upper_ns": age.event.upper_ns,
                "max_age_ns": age.budget_ns,
                "upper_age_inclusive": True,
                "expiry_upper_ns": age.event.lower_ns + age.budget_ns,
            }
            for age in window.ages
        ]
        hard = [
            {
                "origin_event_id": _event_token(self, item.deadline.origin).event_identity,
                "source_id": item.source_id,
                "budget_ns": item.deadline.budget_ns,
                "deadline_ns": item.deadline.deadline_ns,
                "end_exclusive": True,
            }
            for item in window.hard
        ]
        deadline = min(item["deadline_ns"] for item in hard)
        upper = min([deadline, *(age["expiry_upper_ns"] for age in ages)])
        s = self._startup
        return {
            "schema_version": _SCHEMA,
            "window_id": window_id,
            "kind": window.kind,
            "kind_policy": (
                "HARD_ORIGINAL_TASK_LIFECYCLE" if window.kind == "bootstrap" else "AGE_CLOSED"
            ),
            "budget_semantics": "HARD_OPEN" if window.kind == "bootstrap" else "AGE_CLOSED",
            "budget_ns": window.budget_ns,
            "domain": asdict(self._clock.domain),
            "origin_domain": "ORIGINAL_TASK_D",
            "task_origin_event_id": self.task_origin_token.event_identity,
            "event_id": _event_token(self, window.event).event_identity,
            "source_hashes": dict(self._source_hashes or {}),
            "source_identity": self._source_identity,
            "job_id": s.job_id,
            "run_id": s.run_id,
            "worker_id": s.worker.worker_id,
            "lease_id": s.lease_id,
            "attempt": s.attempt,
            "fencing": str(s.acquired_at),
            "episode_id": self._episode_id,
            "parents": list(window.parents),
            "age_constraints": ages,
            "hard_deadlines": hard,
            "deadline_ns": deadline,
            "deadline_semantics": "HARD_OPEN",
            "effective_upper": {"value_ns": upper, "inclusive": upper < deadline},
            "lease_deadline_domain": "UTC_LEGACY_VETO",
            "live_authority": "NOT_EXPORTED",
        }


def _event_token(
    owner: OperationalWindowOwner, receipt: OperationalBracket
) -> OperationalEventToken:
    # OC1 does not expose receipt-token access publicly; its exact issuance record is read only.
    record = owner._clock._receipt_record(receipt)
    if record.role != "event":
        raise OperationalTimeError("original complete event required")
    return record.token


def _owner_for_worker(worker: object) -> OperationalWindowOwner:
    owner = _OWNERS.get(worker)
    if owner is None:
        raise OperationalTimeError("worker has no genuine startup owner")
    owner._check_live()
    return owner


def _revoke_worker(worker: object) -> None:
    _PENDING.pop(worker, None)
    owner = _OWNERS.pop(worker, None)
    if owner is None:
        return
    owner._closed = True
    for token, candidate in list(_HANDOFFS.items()):
        if candidate is owner:
            del _HANDOFFS[token]
    owner._windows.clear()
    owner._observations.clear()
    try:
        owner._clock.close()
    except OperationalTimeError:
        # Already unusable OC1 identity cannot mask the original worker exception.
        pass


def _new_handoff(worker: object, source: object, limits: object) -> object:
    owner = _owner_for_worker(worker)
    owner._bind_inputs(source, limits)
    token = object()
    _HANDOFFS[token] = owner
    return token


def _consume_handoff(
    token: object, source: object, binding: object, limits: object, episode_id: str
) -> OperationalWindowOwner:
    owner = _HANDOFFS.pop(token, None)
    if owner is None or owner._startup.binding is not binding:
        raise OperationalTimeError("unissued or consumed runtime handoff")
    owner._bind_inputs(source, limits)
    if type(episode_id) is not str or not episode_id or owner._episode_id is not None:
        raise OperationalTimeError("actual backend episode required once")
    owner._episode_id = episode_id
    return owner


@contextmanager
def _worker_scope(worker: object) -> Iterator[None]:
    owner = _OWNERS.get(worker)
    if owner is None:
        yield
        return
    owner._check_live()
    stack = _SCOPES.setdefault(threading.get_ident(), [])
    stack.append(owner)
    try:
        yield
    finally:
        stack.pop()
        if not stack:
            _SCOPES.pop(threading.get_ident(), None)


def _current_owner() -> OperationalWindowOwner | None:
    stack = _SCOPES.get(threading.get_ident())
    if not stack:
        return None
    owner = stack[-1]
    owner._check_live()
    return owner


def _observation_key(observation: object) -> str:
    return _hash(observation.model_dump(mode="json"))


def _register_observation(
    owner: OperationalWindowOwner, event: OperationalBracket, observation: object
) -> None:
    owner._check_live()
    if observation.episode_id != owner._episode_id:
        raise OperationalTimeError("actual acquisition episode mismatch")
    key = _observation_key(observation)
    if key in owner._observations:
        raise OperationalTimeError("original acquisition cannot be refreshed")
    window = owner.issue("capture", event, budget_ns=_FIVE_NS, parent_ids=())
    owner._observations[key] = (event, window)
    owner._observation_values[key] = observation.model_copy(deep=True)


def _reference_for_observation(
    observation: object, kind: str, *, max_age_s: object = 5.0
) -> dict[str, Any] | None:
    owner = _current_owner()
    if owner is None:
        return None
    key = _observation_key(observation)
    if key not in owner._observations:
        raise OperationalTimeError("observation lacks original acquisition source")
    event, capture = owner._observations[key]
    policy = owner._policies.get((key, kind))
    cap = policy[0] if policy is not None else _FIVE_NS
    requested_ns = _seconds_ns(max_age_s)
    budget = min(cap, requested_ns)
    lookup = (key, kind, budget)
    window = owner._references.get(lookup)
    if window is None:
        origin = owner.task_origin if kind == "bootstrap" else event
        requested = owner._startup.task_ns if kind == "bootstrap" else budget
        window = owner.issue(kind, origin, budget_ns=requested, parent_ids=(capture,))
        owner._references[lookup] = window
    return owner.export_record(window)


def _check_reference(reference: object) -> EvidenceVerdict:
    from cloud_edge_robot_arm.edge.evidence.models import EvidenceVerdict

    try:
        reference = _descriptor_plain(reference)
        _validate_references([reference])
        owner = _current_owner()
        if owner is None:
            raise OperationalTimeError("descriptive reference has no live owner")
        identifier = reference["window_id"]
        if _json(reference) != _json(owner.export_record(identifier)):
            raise OperationalTimeError("descriptor differs from immutable registered window")
        window = owner._windows[identifier]
        verdict = owner.check(identifier, after=_event_token(owner, window.event))
        if verdict.status != "VALID":
            return verdict
        for key, (event, _) in owner._observations.items():
            policy = owner._policies.get((key, window.kind))
            maximum = owner._maximum_ages.get(key) if window.kind == "supervision" else None
            caps = [bound[0] for bound in (policy, maximum) if bound is not None]
            if caps and any(age.event is event for age in window.ages):
                current = owner._clock.read_current(after=_event_token(owner, event))
                if not owner._clock.within_age(event, current, max_age_ns=min(caps)):
                    return EvidenceVerdict("INVALID", ("original_policy_age_exhausted",))
        owner._check_live()
        return verdict
    except (OperationalTimeError, ValueError, TypeError, KeyError, OSError):
        return EvidenceVerdict("UNKNOWN", ("unregistered_operational_reference",))


def _check_observation(
    observation: object, kind: str, *, max_age_s: object = 5.0, reference: object = None
) -> bool | None:
    try:
        if reference is None:
            reference = _reference_for_observation(observation, kind, max_age_s=max_age_s)
        if reference is None:
            return None
        reference = _descriptor_plain(reference)
        _validate_references([reference])
        owner = _current_owner()
        if owner is None:
            return False
        key = _observation_key(observation)
        if key not in owner._observations or reference.get("kind") != kind:
            return False
        receipt, _ = owner._observations[key]
        window = owner._windows.get(reference.get("window_id"))
        if window is None or not any(a.event is receipt for a in window.ages):
            return False
        if _check_reference(reference).status != "VALID":
            return False
        current = owner._clock.read_current(after=_event_token(owner, receipt))
        cap = owner._policies.get((key, kind), (_FIVE_NS, ""))[0]
        return owner._clock.within_age(
            receipt, current, max_age_ns=min(cap, _seconds_ns(max_age_s))
        )
    except (OperationalTimeError, ValueError, TypeError, KeyError, OSError):
        return False


@contextmanager
def _transition_scope(
    owner: OperationalWindowOwner | None, payload: dict[str, Any]
) -> Iterator[None]:
    references = payload.get("operational_windows")
    if owner is None and not references:
        yield
        return
    if owner is None or _current_owner() is not owner or threading.get_ident() in _TRANSITIONS:
        raise OperationalTimeError("actual one-shot transition owner required")
    owner._check_live()
    _TRANSITIONS[threading.get_ident()] = (
        owner,
        _hash(payload),
        tuple(r["window_id"] for r in references),
    )
    try:
        yield
    finally:
        _TRANSITIONS.pop(threading.get_ident(), None)


def _consume_transition(payload: dict[str, Any], *, required: bool = False) -> None:
    references = payload.get("operational_windows")
    if not references:
        if required or _current_owner() is not None:
            raise OperationalTimeError("operational transition cannot downgrade to legacy")
        return
    scope = _TRANSITIONS.pop(threading.get_ident(), None)
    if scope is None or _current_owner() is not scope[0] or scope[1] != _hash(payload):
        raise OperationalTimeError("replayed public transition has no live effect authority")
    if tuple(r["window_id"] for r in references) != scope[2] or any(
        _check_reference(r).status != "VALID" for r in references
    ):
        raise OperationalTimeError("original transition obligations unavailable or exhausted")


def _descriptor_fields(record: object, expected: set[str]) -> dict[str, Any]:
    if type(record) is not dict or set(record) != expected:
        raise ValueError("exact operational descriptor fields required")
    return record


def _descriptor_integer(value: object, *, positive: bool = False) -> int:
    if type(value) is not int or value < (1 if positive else 0):
        raise ValueError("original integer operational constraint required")
    return value


def _descriptor_text(value: object) -> str:
    if type(value) is not str or not value:
        raise ValueError("original operational identity required")
    return value


def _descriptor_digest(value: object) -> str:
    text = _descriptor_text(value)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError("original operational source hash required")
    return text


def _validate_domain(value: object) -> None:
    domain = _descriptor_fields(
        value,
        {
            "boot_id",
            "pid",
            "process_start_ticks",
            "owner_thread_id",
            "owner_native_thread_id",
            "namespace_device",
            "namespace_inode",
            "namespace_offsets",
            "startup_nonce",
            "startup_counter_ns",
            "os_name",
            "os_release",
            "os_version",
            "machine",
            "python_version",
            "resolution_seconds",
            "schema",
            "api",
            "scope",
            "utc_accuracy",
            "si_accuracy",
            "accuracy_status",
            "worker_authority",
            "lease_authority",
            "native_authority",
            "future_horizon",
            "restart_suspend_hostpause",
        },
    )
    for name in (
        "boot_id",
        "startup_nonce",
        "os_release",
        "os_version",
        "machine",
        "python_version",
    ):
        _descriptor_text(domain[name])
    for name in (
        "pid",
        "process_start_ticks",
        "owner_thread_id",
        "owner_native_thread_id",
        "namespace_inode",
    ):
        _descriptor_integer(domain[name], positive=True)
    for name in ("namespace_device", "startup_counter_ns"):
        _descriptor_integer(domain[name])
    offsets = domain["namespace_offsets"]
    if type(offsets) is not list or len(offsets) != 2:
        raise ValueError("complete original time namespace offsets required")
    for expected, entry in zip(("monotonic", "boottime"), offsets, strict=True):
        if (
            type(entry) is not list
            or len(entry) != 3
            or entry[0] != expected
            or type(entry[1]) is not int
        ):
            raise ValueError("typed original time namespace offsets required")
        if _descriptor_integer(entry[2]) >= 1_000_000_000:
            raise ValueError("namespace nanoseconds out of range")
    constants = {
        "os_name": "Linux",
        "schema": "simulation.operational-time.v1",
        "api": "Linux time.clock_gettime_ns(time.CLOCK_BOOTTIME)",
        "scope": "SOFTWARE_ONLY",
        "utc_accuracy": None,
        "si_accuracy": None,
        "accuracy_status": "UNVERIFIED",
        "worker_authority": "UNAVAILABLE",
        "lease_authority": "UNAVAILABLE",
        "native_authority": "UNAVAILABLE",
        "future_horizon": "UNKNOWN",
        "restart_suspend_hostpause": "NOT_TESTED_OC3_GATE",
    }
    if any(domain[name] != expected for name, expected in constants.items()):
        raise ValueError("unsupported descriptive operational domain")
    resolution = domain["resolution_seconds"]
    if resolution is not None and (type(resolution) is not float or resolution <= 0):
        raise ValueError("original positive descriptive resolution required")


def _validate_references(references: object) -> None:
    """Pure typed history validation; never authenticates source or owner."""
    references = _descriptor_plain(references)
    if type(references) is not list or not references:
        raise ValueError("nonempty versioned operational references required")
    for record in references:
        record = _descriptor_fields(
            record,
            {
                "schema_version",
                "window_id",
                "kind",
                "kind_policy",
                "budget_semantics",
                "budget_ns",
                "domain",
                "origin_domain",
                "task_origin_event_id",
                "event_id",
                "source_hashes",
                "source_identity",
                "job_id",
                "run_id",
                "worker_id",
                "lease_id",
                "attempt",
                "fencing",
                "episode_id",
                "parents",
                "age_constraints",
                "hard_deadlines",
                "deadline_ns",
                "deadline_semantics",
                "effective_upper",
                "lease_deadline_domain",
                "live_authority",
            },
        )
        if (
            record["schema_version"] != _SCHEMA
            or type(record["kind"]) is not str
            or record["kind"] not in _KINDS
        ):
            raise ValueError("unsupported operational reference schema/kind")
        bootstrap = record["kind"] == "bootstrap"
        constants = {
            "kind_policy": "HARD_ORIGINAL_TASK_LIFECYCLE" if bootstrap else "AGE_CLOSED",
            "budget_semantics": "HARD_OPEN" if bootstrap else "AGE_CLOSED",
            "origin_domain": "ORIGINAL_TASK_D",
            "deadline_semantics": "HARD_OPEN",
            "lease_deadline_domain": "UTC_LEGACY_VETO",
            "live_authority": "NOT_EXPORTED",
        }
        if any(record[name] != expected for name, expected in constants.items()):
            raise ValueError("typed original operational policy required")
        for name in (
            "window_id",
            "event_id",
            "task_origin_event_id",
            "job_id",
            "run_id",
            "worker_id",
            "lease_id",
            "fencing",
        ):
            _descriptor_text(record[name])
        _descriptor_digest(record["source_identity"])
        _descriptor_integer(record["attempt"], positive=True)
        if record["episode_id"] is not None:
            _descriptor_text(record["episode_id"])
        budget = _descriptor_integer(record["budget_ns"], positive=True)
        if not bootstrap and budget > _FIVE_NS:
            raise ValueError("evidence budget exceeds original maximum")
        _validate_domain(record["domain"])
        hashes = record["source_hashes"]
        if type(hashes) is not dict:
            raise ValueError("descriptive source inventory required")
        for path, digest in hashes.items():
            _descriptor_text(path)
            _descriptor_digest(digest)
        parents = record["parents"]
        if type(parents) is not list:
            raise ValueError("parent identity sequence required")
        for parent in parents:
            _descriptor_text(parent)
        if len(set(parents)) != len(parents) or record["window_id"] in parents:
            raise ValueError("duplicate or self parent identity")
        ages = record["age_constraints"]
        hard = record["hard_deadlines"]
        if type(ages) is not list or type(hard) is not list or not hard:
            raise ValueError("complete typed operational constraints required")
        endpoints = []
        own_age = False
        for age in ages:
            age = _descriptor_fields(
                age,
                {
                    "event_id",
                    "source_id",
                    "lower_ns",
                    "upper_ns",
                    "max_age_ns",
                    "upper_age_inclusive",
                    "expiry_upper_ns",
                },
            )
            _descriptor_text(age["event_id"])
            source_id = _descriptor_text(age["source_id"])
            _descriptor_digest(source_id.split(":", 1)[0])
            lower = _descriptor_integer(age["lower_ns"])
            upper = _descriptor_integer(age["upper_ns"])
            maximum = _descriptor_integer(age["max_age_ns"], positive=True)
            expiry = _descriptor_integer(age["expiry_upper_ns"], positive=True)
            if (
                lower > upper
                or maximum > _FIVE_NS
                or expiry != lower + maximum
                or age["upper_age_inclusive"] is not True
            ):
                raise ValueError("inconsistent original AGE_CLOSED constraint")
            own_age |= age["event_id"] == record["event_id"] and maximum == budget
            endpoints.append(expiry)
        if not bootstrap and not own_age:
            raise ValueError("original evidence event age constraint required")
        hard_endpoints = []
        hard_origins = set()
        own_bootstrap = False
        for deadline in hard:
            deadline = _descriptor_fields(
                deadline,
                {"origin_event_id", "source_id", "budget_ns", "deadline_ns", "end_exclusive"},
            )
            if deadline["origin_event_id"] != record["task_origin_event_id"]:
                raise ValueError("original task hard origin identity required")
            source_id = _descriptor_text(deadline["source_id"])
            _descriptor_digest(source_id.split(":", 1)[0])
            hard_budget = _descriptor_integer(deadline["budget_ns"], positive=True)
            end = _descriptor_integer(deadline["deadline_ns"], positive=True)
            if end < hard_budget or deadline["end_exclusive"] is not True:
                raise ValueError("original HARD_OPEN constraint required")
            hard_endpoints.append(end)
            hard_origins.add(end - hard_budget)
            own_bootstrap |= hard_budget == budget
        if len(hard_origins) != 1 or (
            bootstrap
            and (record["event_id"] != record["task_origin_event_id"] or not own_bootstrap)
        ):
            raise ValueError("inconsistent original task hard constraints")
        minimum = min(hard_endpoints)
        if _descriptor_integer(record["deadline_ns"], positive=True) != minimum:
            raise ValueError("inconsistent minimum hard deadline")
        effective = _descriptor_fields(record["effective_upper"], {"value_ns", "inclusive"})
        value = min([minimum, *endpoints])
        if (
            _descriptor_integer(effective["value_ns"], positive=True) != value
            or type(effective["inclusive"]) is not bool
            or effective["inclusive"] != (value < minimum)
        ):
            raise ValueError("inconsistent effective operational endpoint")


def _bind_observation_policy(
    owner: OperationalWindowOwner, observation: object, kind: str, budget_s: object, source: object
) -> None:
    """Bind an actual immutable requirement before its consumer; never rebind/refill."""
    owner._check_live()
    key = _observation_key(observation)
    if key not in owner._observations or kind not in _KINDS - {"bootstrap", "capture"}:
        raise OperationalTimeError("original acquisition and supported policy required")
    value = (min(_FIVE_NS, _seconds_ns(budget_s)), _hash(source))
    existing = owner._policies.get((key, kind))
    if existing is not None and existing != value:
        raise OperationalTimeError("original observation policy source changed")
    owner._policies[(key, kind)] = value


def _check_context(context: object, max_age_s: object, reference: object = None) -> bool | None:
    try:
        owner = _current_owner()
        if owner is None:
            return False if reference is not None else None
        matches = [
            key
            for key in owner._observations
            if key in owner._observation_values
            and owner._observation_values[key].observation_id == context.observation_id
            and owner._observation_values[key].episode_id == context.episode_id
            and owner._observation_values[key].captured_at == context.captured_at
        ]
        if len(matches) != 1:
            return False
        key = matches[0]
        maximum = (
            min(_FIVE_NS, _seconds_ns(max_age_s)),
            _hash({"context": context.model_dump(mode="json"), "maximum_age_s": max_age_s}),
        )
        existing = owner._maximum_ages.get(key)
        if existing is not None and existing != maximum:
            return False
        owner._maximum_ages[key] = maximum
        return _check_observation(
            owner._observation_values[key], "supervision", max_age_s=max_age_s, reference=reference
        )
    except (OperationalTimeError, ValueError, TypeError, KeyError, OSError):
        return False
