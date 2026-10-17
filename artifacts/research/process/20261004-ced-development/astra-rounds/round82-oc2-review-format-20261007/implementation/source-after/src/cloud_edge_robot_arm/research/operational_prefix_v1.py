"""Task1 startup-owned OC2 registry and preregistration, without source publication.

Backend/model dependencies are lazy. The default CLI is pure read-only input
validation. Execution/recorder/reader are pending later round60 gates and cannot
publish a source verdict. CPU SQLite fixture state is never a real capture.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn, SupportsIndex, cast
from uuid import uuid4

from cloud_edge_robot_arm.research.operational_prefix_schema_v1 import (
    LIMITS_V1,
    canonical_bytes_v1,
    decode_original_json_v1,
    validate_inventory_v1,
    validate_operational_originals_v1,
    validate_policy_v1,
    validate_preregistration_v1,
)

if TYPE_CHECKING:
    from cloud_edge_robot_arm.research.operational_capture_v1 import OperationalPrefixRecorderV1
    from cloud_edge_robot_arm.research.operational_time_v1 import OperationalClockOwner
    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
        SQLiteSimulationJobRepository,
    )
    from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker

_ROOT = Path(__file__).resolve().parents[3]
_TOKEN = object()
_SOURCE_ROOTS = frozenset(
    {
        "src/cloud_edge_robot_arm/research/operational_prefix_schema_v1.py",
        "src/cloud_edge_robot_arm/research/operational_capture_v1.py",
        "src/cloud_edge_robot_arm/research/operational_prefix_v1.py",
        "src/cloud_edge_robot_arm/research/operational_time_v1.py",
        "src/cloud_edge_robot_arm/research/native_reset_capture_v2.py",
        "src/cloud_edge_robot_arm/vision/raw_recorder_v3.py",
        "src/cloud_edge_robot_arm/vision/worker_owner.py",
        "src/cloud_edge_robot_arm/vision/capture.py",
        "src/cloud_edge_robot_arm/simulation_runtime/worker.py",
        "src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py",
        "src/cloud_edge_robot_arm/simulation_runtime/models.py",
        "src/cloud_edge_robot_arm/simulation_runtime/state_machine.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/backend.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/camera.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/skill_robot.py",
        "src/cloud_edge_robot_arm/edge/runtime/skill_executor.py",
        "src/cloud_edge_robot_arm/simulation/config.py",
        "src/cloud_edge_robot_arm/simulation/models.py",
        "scripts/run_operational_prefix_v1.py",
        "assets/robots/franka_panda/scene.xml",
    }
)


def _regular(path: Path) -> Path:
    lexical = path.absolute()
    if any(p.is_symlink() for p in (lexical, *lexical.parents)) or not lexical.is_file():
        raise ValueError("regular original input without lexical symlinks required")
    return lexical


def _pin(path: Path) -> dict[str, Any]:
    raw = _regular(path).read_bytes()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def _module_paths(name: str) -> set[str]:
    if not name.startswith("cloud_edge_robot_arm"):
        return set()
    stem = "src/" + name.replace(".", "/")
    found = {p for p in (stem + ".py", stem + "/__init__.py") if (_ROOT / p).is_file()}
    pieces = name.split(".")
    for end in range(1, len(pieces)):
        candidate = "src/" + "/".join(pieces[:end]) + "/__init__.py"
        if (_ROOT / candidate).is_file():
            found.add(candidate)
    return found


def _source_inventory_v1() -> dict[str, Any]:
    """Static local import closure: read Python syntax, never import runtime code."""
    inventory: dict[str, Any] = {}
    pending = set(_SOURCE_ROOTS)
    while pending:
        name = pending.pop()
        if name in inventory:
            continue
        path = _regular(_ROOT / name)
        inventory[name] = _pin(path)
        if path.suffix != ".py":
            continue
        module = name.removeprefix("src/").removesuffix(".py").replace("/", ".")
        package = (
            module.removesuffix(".__init__")
            if module.endswith(".__init__")
            else module.rsplit(".", 1)[0]
        )
        for node in ast.walk(ast.parse(path.read_bytes(), filename=name)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    pending.update(_module_paths(alias.name))
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    pieces = package.split(".")
                    prefix = ".".join(pieces[: len(pieces) - node.level + 1])
                    base = ".".join(p for p in (prefix, base) if p)
                pending.update(_module_paths(base))
                for alias in node.names:
                    pending.update(_module_paths(base + "." + alias.name))
    validate_inventory_v1(inventory)
    return dict(sorted(inventory.items()))


def validate_operational_prefix_inputs_v1(config_path: Path) -> dict[str, Any]:
    path = _regular(Path(config_path))
    raw = path.read_bytes()
    config = validate_policy_v1(decode_original_json_v1(raw))
    return {
        "config_path": str(path),
        "config_sha256": hashlib.sha256(raw).hexdigest(),
        "config_bytes": len(raw),
        "config": config,
        "source_inventory": _source_inventory_v1(),
    }


@dataclass
class _ApplicationSourceV1:
    backend: Any
    capture: Any
    executor: Any
    owner: OperationalClockOwner
    directory: Path
    source_session_id: str
    preregistration_sha256: str = ""


@dataclass
class _LiveApplicationV1:
    repository: SQLiteSimulationJobRepository
    worker: SimulationWorker
    output: Path
    config_path: Path
    inputs_json: bytes
    application_id: str
    pid: int
    prepared: bool = False
    execute_called: bool = False
    source_called: bool = False
    job_id: str | None = None
    assignment_json: bytes | None = None
    origin: tuple[Any, ...] | None = None
    fencing: tuple[Any, ...] | None = None
    source: _ApplicationSourceV1 | None = None
    exact_handles: tuple[Any, ...] | None = None
    preregistration_bytes: bytes | None = None
    preregistration_primary: tuple[BaseException, int] | None = None
    failures: list[dict[str, Any]] = field(default_factory=list)
    recorder: OperationalPrefixRecorderV1 | None = None
    issuing: bool = False
    catalog_json: bytes | None = None
    partial_receipt: dict[str, Any] | None = None
    partial_attempt_snapshot: dict[str, Any] | None = None
    failure_sidecar_sequence: int = 0
    durable_failure_evidence_complete: bool = True


_REGISTRY: dict[OperationalPrefixApplicationV1, _LiveApplicationV1] = {}


def _live(application: Any) -> _LiveApplicationV1:
    if type(application) is not OperationalPrefixApplicationV1 or application not in _REGISTRY:
        raise RuntimeError("exact startup-owned private application required")
    record = _REGISTRY[application]
    if (
        os.getpid() != record.pid
        or application.repository is not record.repository
        or application.worker is not record.worker
        or record.worker.repository is not record.repository
        or application.output != record.output
        or application.config_path != record.config_path
    ):
        raise ValueError("actual private application/repository/worker identity changed")
    return record


def _assignment_basis(job: Any) -> dict[str, Any]:
    return {
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


def _check_inputs(application: OperationalPrefixApplicationV1) -> dict[str, Any]:
    record = _live(application)
    current = validate_operational_prefix_inputs_v1(record.config_path)
    if canonical_bytes_v1(current) != record.inputs_json:
        raise ValueError("frozen policy/source/asset inventory changed")
    return current


class OperationalPrefixApplicationV1:
    """Exact private registry handle; values and descriptors grant no authority."""

    __slots__ = ("repository", "worker", "output", "config_path")
    repository: SQLiteSimulationJobRepository
    worker: SimulationWorker
    output: Path
    config_path: Path

    def __init__(self, *, _token: object | None = None) -> None:
        if _token is not _TOKEN:
            raise TypeError("use the concrete operational startup factory")

    def __copy__(self) -> NoReturn:
        raise RuntimeError("live operational application cannot be copied")

    def __deepcopy__(self, memo: dict[int, object]) -> NoReturn:
        raise RuntimeError("live operational application cannot be deep-copied")

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        raise RuntimeError("live operational application cannot be serialized")

    @classmethod
    def from_startup(cls, config_path: Path, *, output: Path) -> OperationalPrefixApplicationV1:
        if cls is not OperationalPrefixApplicationV1:
            raise TypeError("exact startup application type required")
        inputs = validate_operational_prefix_inputs_v1(config_path)
        destination = Path(output).absolute()
        if destination.exists() or any(p.is_symlink() for p in (destination, *destination.parents)):
            raise ValueError("fresh exclusive output without lexical symlinks required")
        destination.mkdir(parents=True, exist_ok=False)
        if any(p.is_symlink() for p in (destination, *destination.parents)):
            raise ValueError("fresh output acquired a lexical symlink")
        from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
            SQLiteSimulationJobRepository,
        )
        from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker

        app = cls(_token=_TOKEN)
        app.output = destination
        app.config_path = Path(inputs["config_path"])
        app.repository = SQLiteSimulationJobRepository(destination / "runtime.db")
        app.worker = SimulationWorker(
            worker_id="operational-prefix-" + uuid4().hex,
            backend="MUJOCO",
            repository=app.repository,
            artifact_root=destination,
            planner_factory=None,
        )
        _REGISTRY[app] = _LiveApplicationV1(
            app.repository,
            app.worker,
            app.output,
            app.config_path,
            canonical_bytes_v1(inputs),
            uuid4().hex,
            os.getpid(),
        )
        app.worker._operational_prefix_application = app
        return app

    @property
    def config(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(_live(self).inputs_json)["config"])

    def prepare_once(self) -> Any:
        from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus

        record = _live(self)
        if record.prepared:
            raise RuntimeError("operational assignment cannot be retried or reallocated")
        record.prepared = True
        inputs = _check_inputs(self)
        assignment: dict[str, object] = {
            "input_mode": "RGBD",
            "execution_scope": "VISION_CLOSED_LOOP",
            "backend": "MUJOCO",
            "scenarios": ["S01_NORMAL_STATIC"],
            "control_modes": ["PCSC"],
            "seeds": [0],
            "user_instruction": "excluded operational RESET120 capture prefix; no actions",
        }
        job = record.repository.create_job(
            run_id="operational-prefix-" + uuid4().hex,
            batch_id="",
            backend="MUJOCO",
            scenario_id="S01_NORMAL_STATIC",
            control_mode="PCSC",
            seed=0,
            manifest_id="simulation.operational-prefix.v1",
            reproducibility_hash=hashlib.sha256(canonical_bytes_v1(assignment)).hexdigest(),
            draft=assignment,
            timeout_seconds=60,
            max_attempts=1,
            artifact_root="worker-attempt",
            source_commit="SOURCE_ONLY_CURRENT_BYTES",
            source_tree_hash=hashlib.sha256(
                canonical_bytes_v1(inputs["source_inventory"])
            ).hexdigest(),
            provenance={
                "scope": "EXCLUDED_SOURCE_ONLY_PREFIX",
                "config_sha256": inputs["config_sha256"],
            },
        )
        record.job_id = job.job_id
        record.assignment_json = canonical_bytes_v1(_assignment_basis(job))
        queued = record.repository.update_status_cas(
            job.job_id,
            expected=RuntimeJobStatus.CREATED,
            next_status=RuntimeJobStatus.QUEUED,
            reason_code="operational_prefix_startup",
            worker_id="",
            lease_id="",
        )
        if queued is None:
            raise RuntimeError("sole operational assignment queue transition failed")
        return record.repository.get_job(job.job_id)

    def execute_once(self) -> dict[str, Any]:
        record = _live(self)
        if record.execute_called:
            raise RuntimeError("operational process cannot execute twice")
        record.execute_called = True
        self.prepare_once()
        if not record.worker.poll_once():
            raise RuntimeError("sole operational worker lease was not obtained")
        if record.catalog_json is not None:
            return self.catalog_entry()
        return record.partial_receipt or {
            "source_prefix_complete": False,
            "failures": record.failures,
            **LIMITS_V1,
        }

    def check_worker(self, worker: SimulationWorker, job: Any, *, start_monotonic: float) -> None:
        record = _live(self)
        if (
            worker is not record.worker
            or job.job_id != record.job_id
            or worker.active_job_id != record.job_id
        ):
            raise ValueError("current exact configured worker/assignment required")
        origin = worker._active_task_origin
        if origin is None or origin[:2] != (job.job_id, start_monotonic):
            raise ValueError("original worker MONOTONIC task origin required")
        if record.origin is not None and record.origin != origin:
            raise ValueError("original worker task origin changed")
        # The origin is tentative until the real lease/attempt join passes.
        previous = record.origin
        record.origin = origin
        try:
            self.check_active()
        except BaseException:
            record.origin = previous
            raise

    def check_active(self) -> dict[str, Any]:
        from cloud_edge_robot_arm.vision.worker_owner import read_visual_worker_lease

        record = _live(self)
        _check_inputs(self)
        if record.job_id is None or record.origin is None:
            raise RuntimeError("actual RUNNING assignment/lease/origin not established")
        job = record.repository.get_job(record.job_id)
        if canonical_bytes_v1(_assignment_basis(job)) != record.assignment_json:
            raise ValueError("original operational assignment changed")
        if (
            record.worker._active_task_origin != record.origin
            or record.worker.active_job_id != job.job_id
            or job.max_attempts != 1
            or job.seed != 0
            or job.backend != "MUJOCO"
            or job.scenario_id != "S01_NORMAL_STATIC"
        ):
            raise ValueError("original live worker task/assignment changed")
        # Never accept a caller's now; retain the existing real UTC lease guard.
        lease = read_visual_worker_lease(
            record.repository,
            job_id=job.job_id,
            run_id=job.run_id,
            worker_id=record.worker.worker_id,
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
        if lease.attempt != 1 or record.fencing is not None and record.fencing != fencing:
            raise ValueError("original sole lease/attempt/fencing changed")
        record.fencing = fencing
        origin = record.origin
        if origin is None:
            raise RuntimeError("actual RUNNING assignment/lease/origin not established")
        return {
            "job_id": job.job_id,
            "run_id": job.run_id,
            "attempt": lease.attempt,
            "lease_id": lease.lease_id,
            "worker_id": lease.worker_id,
            "lease": lease.to_payload(),
            "task_origin": [origin[0], origin[1], origin[2].isoformat()],
            "lease_clock_migration": "NOT_DONE_OC3",
        }

    def check_recorder(self, recorder: object) -> dict[str, Any]:
        from cloud_edge_robot_arm.research.operational_capture_v1 import OperationalPrefixRecorderV1

        record = _live(self)
        source = _check_source_v1(self)
        if (
            type(recorder) is not OperationalPrefixRecorderV1
            or recorder is not record.recorder
            or recorder.backend is not source.backend
            or recorder.capture_session is not source.capture
            or recorder.executor is not source.executor
            or recorder._owner is not source.owner
            or recorder._application is not self
            or recorder._session_id != source.source_session_id
            or recorder.directory != source.directory
            or recorder.source_root != _ROOT
        ):
            raise ValueError("exact issued operational recorder/source handles required")
        prereg = decode_original_json_v1(record.preregistration_bytes or b"")
        config = source.backend._config
        if config is None or config.model_dump(mode="json") != prereg["recipe"]["simulator_config"]:
            raise ValueError("original backend simulator configuration changed")
        if recorder._current_asset_hash() != prereg["recipe"]["scene"]["sha256"]:
            raise ValueError("original source scene asset changed")
        return self.check_active()

    def catalog_entry(self) -> dict[str, Any]:
        record = _live(self)
        if record.catalog_json is None:
            raise RuntimeError("no live operational source-only publication")
        return cast(dict[str, Any], decode_original_json_v1(record.catalog_json))


def _new_prefix_backend_v1() -> Any:
    """The single raw CPU replacement seam; production initializes nothing here."""
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

    return MuJoCoPhysicsBackend()


def _open_clock_v1() -> OperationalClockOwner:
    from cloud_edge_robot_arm.research.operational_time_v1 import open_operational_clock

    return open_operational_clock()


def _write_exclusive_v1(path: Path, raw: bytes) -> None:
    if any(p.is_symlink() for p in (path.absolute(), *path.absolute().parents)):
        raise ValueError("lexical original symlink rejected")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    if _regular(path).read_bytes() != raw:
        raise ValueError("persisted original read-back differs")


def _prepare_source_v1(
    application: OperationalPrefixApplicationV1,
    worker: SimulationWorker,
    job: Any,
    *,
    start_monotonic: float,
) -> _ApplicationSourceV1:
    """Private future-runner preregistration, exercised only by Task1 CPU fixture.

    It constructs borrowed real interface handles and an OC1 owner, but never
    opens capture, initializes backend, registers observer, RESETs or steps.
    """
    record = _live(application)
    if record.source_called:
        raise RuntimeError("operational source/preregistration cannot be allocated twice")
    record.source_called = True
    try:
        application.check_worker(worker, job, start_monotonic=start_monotonic)
        inputs = _check_inputs(application)
        from cloud_edge_robot_arm.edge.runtime.skill_executor import SkillExecutor
        from cloud_edge_robot_arm.edge.runtime.skill_registry import SkillRegistry
        from cloud_edge_robot_arm.simulation.config import SimulatorConfig
        from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
        from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

        config = SimulatorConfig(render_rgb=True, render_depth=True, seed=0)
        owner = _open_clock_v1()
        backend = _new_prefix_backend_v1()
        capture = MuJoCoCaptureSession(config, backend=backend)
        executor = SkillExecutor(robot=MuJoCoSkillRobot(backend), registry=SkillRegistry.default())
        context = _ApplicationSourceV1(
            backend, capture, executor, owner, record.output / "prefix-originals", uuid4().hex
        )
        record.source = context
        record.exact_handles = (backend, capture, executor, owner, threading.get_ident())
        state = application.check_active()
        scene = "assets/robots/franka_panda/scene.xml"
        prereg = {
            "schema_version": "simulation.operational-prefix.preregistration.v1",
            "application_id": record.application_id,
            "source_session_id": context.source_session_id,
            "policy": inputs["config"],
            "config_sha256": inputs["config_sha256"],
            "source_inventory": inputs["source_inventory"],
            "recipe": {
                "recipe_id": "oc2-reset120-capture-v1",
                "reset_count": 1,
                "settle_steps": 120,
                "explicit_capture_count": 1,
                "scenario": "S01_NORMAL_STATIC",
                "seed": 0,
                "scene": {"path": scene, **inputs["source_inventory"][scene]},
                "camera": {"width": 320, "height": 240, "render_rgb": True, "render_depth": True},
                "simulator_config": config.model_dump(mode="json"),
            },
            "worker_source": state,
            "clock_domain": asdict(owner.domain),
            "group_inventory": {
                "source_session_ids": [context.source_session_id],
                "source_session_count": 1,
                "independence": "UNESTABLISHED",
                "support_group_count": 0,
            },
            "limits": LIMITS_V1,
        }
        raw = canonical_bytes_v1(prereg)
        validate_preregistration_v1(decode_original_json_v1(raw))
        context.directory.mkdir(exist_ok=False)
        _write_exclusive_v1(context.directory / "preregistration.json", raw)
        _write_exclusive_v1(context.directory / "startup-inputs.json", record.inputs_json)
        _write_exclusive_v1(
            context.directory / "startup-policy.json", _regular(record.config_path).read_bytes()
        )
        record.preregistration_bytes = raw
        context.preregistration_sha256 = hashlib.sha256(raw).hexdigest()
        _check_source_v1(application)
        return context
    except BaseException as error:
        row = _failure_row_v1(record, "preregistration", error, primary_id=None)
        primary_id = row["failure_id"]
        record.preregistration_primary = (error, primary_id)
        if not _failure_write_v1(
            record,
            record.output / "startup-failures.json",
            record.failures,
            phase="startup_failure_persistence",
            primary_id=primary_id,
        ):
            try:
                _persist_failure_stage_v1(record, record.output, primary_id=primary_id)
            except BaseException as secondary:
                record.durable_failure_evidence_complete = False
                _failure_row_v1(
                    record, "startup_failure_fallback", secondary, primary_id=primary_id
                )
        raise


def _check_source_v1(application: OperationalPrefixApplicationV1) -> _ApplicationSourceV1:
    record = _live(application)
    application.check_active()
    source = record.source
    if source is None or record.exact_handles is None or record.preregistration_bytes is None:
        raise RuntimeError("persisted private original source preregistration required")
    backend, capture, executor, owner, thread = record.exact_handles
    if (
        source.backend is not backend
        or source.capture is not capture
        or source.executor is not executor
        or source.owner is not owner
        or thread != threading.get_ident()
        or capture._backend is not backend
        or capture._owns_backend
        or executor._robot._backend is not backend
        or owner.domain.owner_thread_id != thread
        or source.directory != record.output / "prefix-originals"
    ):
        raise ValueError("original source/backend/capture/executor/OC1 handles changed")
    raw = _regular(source.directory / "preregistration.json").read_bytes()
    if (
        raw != record.preregistration_bytes
        or hashlib.sha256(raw).hexdigest() != source.preregistration_sha256
    ):
        raise ValueError("persisted original preregistration changed")
    return source


def _issue_recorder_v1(
    application: OperationalPrefixApplicationV1,
    backend: Any,
    capture: Any,
    executor: Any,
    *,
    directory: Path,
) -> OperationalPrefixRecorderV1:
    from cloud_edge_robot_arm.research.operational_capture_v1 import (
        _ISSUER,
        OperationalPrefixRecorderV1,
    )

    record = _live(application)
    source = _check_source_v1(application)
    if (
        not record.issuing
        or record.recorder is not None
        or backend is not source.backend
        or capture is not source.capture
        or executor is not source.executor
        or Path(directory).absolute() != source.directory
        or not capture._open
    ):
        raise ValueError("sole private runner must issue original configured recorder")
    inputs = decode_original_json_v1(record.inputs_json)
    recorder = OperationalPrefixRecorderV1(
        backend,
        capture,
        executor,
        directory=directory,
        source_root=_ROOT,
        source_hashes={p: pin["sha256"] for p, pin in inputs["source_inventory"].items()},
        application=application,
        owner=source.owner,
        session_id=source.source_session_id,
        _token=_ISSUER,
    )
    record.recorder = recorder
    application.check_recorder(recorder)
    return recorder


def _historical_path_v1(root: Path, name: str) -> Path:
    if (
        type(name) is not str
        or not name
        or name.startswith("/")
        or "\\" in name
        or any(piece in {"", ".", ".."} for piece in name.split("/"))
    ):
        raise ValueError("repository-relative original file without path escape required")
    return _regular(root / name)


def _read_original_v1(root: Path, name: str) -> Any:
    return decode_original_json_v1(_historical_path_v1(root, name).read_bytes())


def _same_v1(actual: Any, wanted: Any, message: str) -> None:
    if canonical_bytes_v1(actual) != canonical_bytes_v1(wanted):
        raise ValueError(message)


def _integer_ns_v1(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("original nonnegative integer ns required")
    return cast(int, value)


def _current_source_event_v1(
    current: dict[str, Any], frames: list[dict[str, Any]], captures: list[dict[str, Any]]
) -> dict[str, Any]:
    returned_id = current.get("returned_acquisition_id")
    source_id = current.get("source_acquisition_id")
    if (
        not isinstance(returned_id, str)
        or not returned_id
        or not isinstance(source_id, str)
        or not source_id
    ):
        raise ValueError("original returned/source acquisition identity missing")
    returned = [frame for frame in frames if frame.get("acquisition_id") == returned_id]
    if len(returned) != 1:
        raise ValueError("exact original returned frame required")
    returned_frame = returned[0]
    original_source = (
        returned_frame.get("source_acquisition_id") or returned_frame["acquisition_id"]
    )
    if original_source != source_id:
        raise ValueError("original returned frame/source acquisition relation differs")
    sources = [frame for frame in frames if frame.get("acquisition_id") == original_source]
    events = [
        event
        for event in captures
        if event.get("kind") == "CAPTURE" and event.get("acquisition_id") == original_source
    ]
    if len(sources) != 1 or len(events) != 1:
        raise ValueError("exact original source frame/CAPTURE event required")
    source_event = events[0]
    interval_id = f"operation-{source_event['operation_id']}"
    if (
        sources[0].get("interval_id") != interval_id
        or returned_frame.get("interval_id") != interval_id
    ):
        raise ValueError("original returned/source frame operation interval differs")
    return source_event


def verify_operational_prefix_originals_v1(root: Path, catalog: dict[str, Any]) -> dict[str, Any]:
    """Historical original joins only: never read now, DBlive or execute an app."""
    result: dict[str, Any] = {
        "original_integrity": "INVALID",
        "source_prefix_complete": False,
        "recorded_source_current_age": None,
        "reasons": [],
        "live_authority": "UNAVAILABLE",
        "native_utc": "UNAVAILABLE",
        "current_external_UTC": "UNAVAILABLE",
        **LIMITS_V1,
    }
    try:
        import base64
        import struct

        root = Path(root).absolute()
        if any(p.is_symlink() for p in (root, *root.parents)) or not root.is_dir():
            raise ValueError("regular original root required")
        entry = decode_original_json_v1(canonical_bytes_v1(catalog))
        if entry.get("schema_version") != "simulation.operational-prefix.receipt.v1":
            raise ValueError("operational source receipt schema required")
        manifest = entry["original_files"]
        validate_inventory_v1(manifest)
        for name, expected in manifest.items():
            _same_v1(
                _pin(_historical_path_v1(root, name)),
                expected,
                "original SHA256/byte count changed",
            )
        actual_names = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
        if actual_names - {"prefix-receipt.json"} != set(manifest):
            raise ValueError("complete original file denominator differs")
        prereg = validate_preregistration_v1(_read_original_v1(root, "preregistration.json"))
        inputs = _read_original_v1(root, "startup-inputs.json")
        config_raw = _historical_path_v1(root, "startup-policy.json").read_bytes()
        _same_v1(
            validate_policy_v1(decode_original_json_v1(config_raw)),
            prereg["policy"],
            "policy/preregistration join changed",
        )
        if hashlib.sha256(config_raw).hexdigest() != prereg["config_sha256"]:
            raise ValueError("original config bytes differ")
        _same_v1(
            inputs["source_inventory"],
            prereg["source_inventory"],
            "startup/source inventory join changed",
        )
        _same_v1(inputs["config"], prereg["policy"], "startup policy join changed")
        if inputs["config_sha256"] != prereg["config_sha256"] or inputs["config_bytes"] != len(
            config_raw
        ):
            raise ValueError("startup config SHA/bytes join changed")
        frozen = _read_original_v1(root, "frozen-originals.json")
        d = validate_operational_originals_v1(_read_original_v1(root, "operational-originals.json"))
        if (
            d["schema_version"] != "simulation.operational-prefix.originals.v1"
            or frozen["schema_version"] != "native.reset.prefix.originals.v2"
        ):
            raise ValueError("foreign source slab schema")
        domain_sha = hashlib.sha256(canonical_bytes_v1(prereg["clock_domain"])).hexdigest()
        if (
            d["source_session_id"] != prereg["source_session_id"]
            or d["domain_sha256"] != domain_sha
            or entry["application_id"] != prereg["application_id"]
            or entry["source_session_id"] != d["source_session_id"]
        ):
            raise ValueError("original application/session/domain joins differ")
        _same_v1(
            frozen["source_hashes"],
            {p: row["sha256"] for p, row in prereg["source_inventory"].items()},
            "legacy/new source inventory join changed",
        )
        legacy_names = {
            "reset-journal.json": "reset_journal",
            "clock-pairs.json": "clock_pairs",
            "operation-ledger.json": "operation_ledger",
            "unbound-intervals.json": "intervals",
            "unbound-physics.json": "physics",
            "unbound-commands.json": "commands",
            "unbound-frames.json": "frames",
            "purpose-allocations.json": "purpose_allocations",
            "observer-failures.json": "observer_failures",
            "source-hashes.json": "source_hashes",
        }
        for name, key in legacy_names.items():
            _same_v1(
                _read_original_v1(root, name), frozen[key], "legacy original slab joins differ"
            )
        _same_v1(
            _read_original_v1(root, "observed-reset-source.json"),
            {k: frozen[k] for k in ("reset_metadata", "reset_result", "reset_count")},
            "legacy RESET source joins differ",
        )
        published = _read_original_v1(root, "source-publication-state.json")
        original_worker = prereg["worker_source"]
        for key in (
            "job_id",
            "run_id",
            "attempt",
            "lease_id",
            "worker_id",
            "task_origin",
            "lease_clock_migration",
        ):
            _same_v1(
                published[key], original_worker[key], "historical worker/fencing source changed"
            )
        if published["lease"]["acquired_at"] != original_worker["lease"]["acquired_at"]:
            raise ValueError("historical original lease fencing changed")
        events = d["events"]
        if type(events) is not list or not events:
            raise ValueError("complete operation attempts required")
        ledger = frozen["operation_ledger"]
        ids = [row["operation_id"] for row in events]
        if ids != list(range(1, len(events) + 1)) or [row["attempt_seq"] for row in events] != ids:
            raise ValueError("operation allocation denominator changed")
        by_id = {row["operation_id"]: row for row in events}
        expected_ledger = []
        seqs = []
        token_ids = []
        for row in events:
            if (
                row["source_session_id"] != d["source_session_id"]
                or row["domain_sha256"] != domain_sha
            ):
                raise ValueError("foreign event source/domain")
            begin, end, bracket = row["begin"], row["end"], row["bracket"]
            if (
                begin is None
                or end is None
                or bracket is None
                or row["error"] is not None
                or begin["operation_id"] != row["operation_id"]
                or end["operation_id"] != row["operation_id"]
                or begin["kind"] != row["kind"]
                or end["kind"] != row["kind"]
                or begin["phase"] != "BEGIN"
                or end["phase"] != "END"
                or end["error_type"] is not None
                or end["error"] is not None
                or end["result"] is None
            ):
                raise ValueError("missing/failed/foreign operation bracket")
            _same_v1(
                begin["parameters"], end["parameters"], "original operation parameters changed"
            )
            for boundary in (begin, end):
                expected_ledger.append(
                    {
                        k: boundary[k]
                        for k in (
                            "operation_id",
                            "kind",
                            "phase",
                            "episode_id",
                            "physics_step",
                            "error_type",
                            "error",
                        )
                    }
                )
            points = [_integer_ns_v1(row[k]) for k in ("begin_seq", "mark_seq", "end_seq")]
            if not points[0] < points[1] < points[2]:
                raise ValueError("operation BEGIN/MARK/END causality missing")
            seqs.extend(points)
            token_ids.append(row["token_identity"])
            lower, upper = (_integer_ns_v1(bracket[k]) for k in ("lower_ns", "upper_ns"))
            if (
                lower > upper
                or row["begin_ns"] != lower
                or bracket["event_identity"] != row["token_identity"]
                or bracket["domain_sha256"] != domain_sha
            ):
                raise ValueError("original D receipt/event token join changed")
        if len(set(seqs)) != len(seqs) or len(set(token_ids)) != len(token_ids):
            raise ValueError("duplicate causal point/event token")
        expected_ledger.sort(
            key=lambda r: by_id[r["operation_id"]][
                "begin_seq" if r["phase"] == "BEGIN" else "end_seq"
            ]
        )
        _same_v1(expected_ledger, ledger, "backend/observer whole-operation denominator differs")
        reset = [r for r in events if r["kind"] == "RESET"]
        if len(reset) != 1 or frozen["reset_count"] != 1:
            raise ValueError("exactly one original RESET required")
        reset_row = reset[0]
        episode = reset_row["end"]["episode_id"]
        if (
            not episode
            or episode != frozen["observed_episode_id"]
            or reset_row["end"]["physics_step"] != 0
        ):
            raise ValueError("post-reset original episode/S differs")
        journal = frozen["reset_journal"]
        _same_v1(
            [r["event"] for r in journal],
            [reset_row["begin"], reset_row["end"]],
            "original old/new RESET boundaries changed",
        )
        if any(r["observer_error"] is not None for r in journal):
            raise ValueError("legacy RESET observer failure")
        for row in events:
            if row["kind"] != "RESET" and (
                row["begin"]["episode_id"] != episode or row["end"]["episode_id"] != episode
            ):
                raise ValueError("operation/RESET episode join differs")
        if (
            frozen["reset_result"]["physics_state"]["episode_id"] != episode
            or frozen["reset_result"]["physics_state"]["physics_step"] != 0
        ):
            raise ValueError("reset physics state/S join differs")
        _same_v1(
            frozen["reset_metadata"]["config"],
            prereg["recipe"]["simulator_config"],
            "actual simulator/preregistered config differs",
        )
        if frozen["reset_metadata"]["asset_hash"] != prereg["recipe"]["scene"]["sha256"]:
            raise ValueError("actual scene/preregistered asset differs")
        physics = frozen["physics"]
        if [r["physics_step"] for r in physics] != list(range(1, 121)) or frozen[
            "observed_total_physics_steps"
        ] != 120:
            raise ValueError("original 120-step physics denominator incomplete")
        settle = [r for r in frozen["intervals"] if r["kind"] == "SETTLE"]
        if len(settle) != 1 or settle[0]["start_step"] != 0 or settle[0]["end_step"] != 120:
            raise ValueError("sole original SETTLE0..120 required")
        for row in physics:
            step = row["physics_step"]
            if (
                row["control_payload"]["physics_step"] != step
                or row["post_state_payload"]["physics_step"] != step
                or row["post_state_payload"]["episode_id"] != episode
                or row["purpose_interval_id"] != settle[0]["interval_id"]
            ):
                raise ValueError("physics/control/SETTLE S joins differ")
            for name, kind, key in [
                ("control_interval_id", "CONTROL", "control_state"),
                ("physics_interval_id", "PHYSICS", "physics_state"),
            ]:
                op = int(row[name].removeprefix("operation-"))
                source = by_id[op]
                if source["kind"] != kind or source["end"]["result"][key]["physics_step"] != step:
                    raise ValueError("physics/control operation join differs")
                _same_v1(
                    source["end"]["result"][key],
                    row["control_payload"] if kind == "CONTROL" else row["post_state_payload"],
                    "operation/state original join changed",
                )
        if any(r["disposition"] != "COMPLETE" for r in frozen["intervals"]):
            raise ValueError("incomplete legacy pair interval")
        pairs = frozen["clock_pairs"]
        pairs_by_seq = {r["sequence"]: r for r in pairs}
        if len(pairs_by_seq) != len(pairs) or list(pairs_by_seq) != list(range(1, len(pairs) + 1)):
            raise ValueError("legacy MONOTONIC/UTC pair denominator differs")
        for interval in frozen["intervals"]:
            for endpoint in ("start", "end"):
                pair = interval[endpoint]
                if pair is None:
                    raise ValueError("missing legacy pair")
                source = pairs_by_seq[pair[0]]
                _same_v1(
                    list(pair),
                    [
                        source["sequence"],
                        source["mono_before_ns"],
                        source["utc_at"],
                        source["mono_after_ns"],
                    ],
                    "legacy pair tee changed",
                )
        captures = [r for r in events if r["kind"] == "CAPTURE"]
        allocated = [r["acquisition_id"] for r in captures]
        _same_v1(
            d["allocated_acquisition_ids"], allocated, "all capture allocation denominator differs"
        )
        frames = frozen["frames"]
        persisted = _read_original_v1(root, "persisted-frames.json")
        _same_v1(
            [r["acquisition_id"] for r in frames],
            allocated,
            "failed/missing frame allocation differs",
        )
        if len(persisted) != len(frames) or frozen["explicit_acquisitions"] != 1:
            raise ValueError("one explicit acquisition and complete frames required")
        required_files = set(legacy_names) | {
            "frozen-originals.json",
            "late-events.json",
            "observed-reset-source.json",
            "persisted-frames.json",
            "unbound-export.json",
            "preregistration.json",
            "startup-inputs.json",
            "startup-policy.json",
            "operational-originals.json",
            "prefix-failures.json",
            "source-publication-state.json",
        }
        for frame, saved, source in zip(frames, persisted, captures, strict=True):
            _same_v1(
                {k: v for k, v in frame.items() if k != "file_hashes"},
                {k: v for k, v in saved.items() if k != "file_hashes"},
                "persisted frame original changed",
            )
            obs = frame["observation_payload"]
            if (
                obs is None
                or obs["episode_id"] != episode
                or obs["width"] != 320
                or obs["height"] != 240
            ):
                raise ValueError("original RGB-D frame/episode/camera join differs")
            if frame["interval_id"] != f"operation-{source['operation_id']}":
                raise ValueError("frame/source operation identity differs")
            sensor = source["end"]["result"]["sensor_frame"]
            if (
                sensor["frame_id"] != obs["frame_id"]
                or sensor["episode_id"] != episode
                or sensor["sim_time_s"] != obs["sim_time_s"]
            ):
                raise ValueError("frame/source sensor identity differs")
            _same_v1(
                frame["camera_state_payload"],
                source["begin"]["parameters"]["camera_state"],
                "frame camera checkpoint differs",
            )
            physical = source["begin"]["parameters"]["physics_state"]
            if (
                hashlib.sha256(canonical_bytes_v1(physical)).hexdigest()
                != frame["joined_physics_observation_hash"]
            ):
                raise ValueError("frame physics state hash differs")
            _same_v1(
                frame["pass_state_hashes"],
                source["end"]["result"]["pass_state_hashes"],
                "frame pass hashes differ",
            )
            if len(set(frame["pass_state_hashes"])) != 1:
                raise ValueError("RGB-D passes differ")
            prefix = f"frames/{frame['acquisition_id']}/"
            mask = (
                bytes([1]) * (obs["width"] * obs["height"])
                if obs.get("valid_mask_base64") is None
                else base64.b64decode(obs["valid_mask_base64"])
            )
            blobs = {
                "rgb.png": base64.b64decode(obs["rgb_png_base64"]),
                "depth.f32": base64.b64decode(obs["depth_float32_base64"]),
                "mask.u8": mask,
                "instances.i32": struct.pack(
                    f"<{len(frozen['frame_aux'][frame['acquisition_id']]['instance_ids'])}i",
                    *frozen["frame_aux"][frame["acquisition_id"]]["instance_ids"],
                ),
            }
            for name, raw in blobs.items():
                if _historical_path_v1(root, prefix + name).read_bytes() != raw:
                    raise ValueError("persisted frame bytes differ from original source")
            metadata = _read_original_v1(root, prefix + "source-frame.json")
            _same_v1(metadata["observation"], obs, "frame metadata original differs")
            for name in [*blobs, "source-frame.json"]:
                required_files.add(prefix + name)
                if saved["file_hashes"].get(prefix + name) != manifest[prefix + name]["sha256"]:
                    raise ValueError("frame hash/manifest join differs")
        if set(manifest) != required_files:
            raise ValueError("required complete originals inventory differs")
        if (
            d["failures"]
            or d["backend_observer_failures"]
            or d["super_audit_failures"]
            or frozen["observer_failures"]
            or frozen["actions"]
            or d["allocated_action_ids"]
            or _read_original_v1(root, "prefix-failures.json")
            or _read_original_v1(root, "late-events.json")
            or _read_original_v1(root, "unbound-export.json")["export_failures"]
        ):
            raise ValueError("complete prefix contains retained failure/action/late denominator")
        current = d["current"]
        if current is None:
            raise ValueError("original capture/current causal pair missing")
        source = _current_source_event_v1(current, frames, captures)
        if (
            current["after_token_identity"] != source["token_identity"]
            or current["domain_sha256"] != domain_sha
            or _integer_ns_v1(current["current_seq"]) <= source["mark_seq"]
            or current["episode_id"] != episode
            or current["physics_step"] != 120
            or current["sim_time_s"] != source["end"]["sim_time_s"]
        ):
            raise ValueError("original same-D/S capture-current causality differs")
        cminus, cplus = (source["bracket"][k] for k in ("lower_ns", "upper_ns"))
        nminus, nplus = (_integer_ns_v1(current[k]) for k in ("lower_ns", "upper_ns"))
        if nminus > nplus or nplus < cminus:
            raise ValueError("invalid original current bracket")
        age = {
            "lower_ns": max(0, nminus - cplus),
            "upper_ns": nplus - cminus,
            "within_5s": nplus - cminus <= 5_000_000_000,
        }
        if (
            current["age_lower_ns"] != age["lower_ns"]
            or current["age_upper_ns"] != age["upper_ns"]
            or current["within_5s"] is not age["within_5s"]
        ):
            raise ValueError("recorded age differs from integer recomputation")
        result.update(
            original_integrity="VERIFIED",
            source_prefix_complete=True,
            recorded_source_current_age=age,
            actual_capture_allocations=len(allocated),
            explicit_acquisitions=1,
            allocated_actions=0,
        )
    except (OSError, ValueError, TypeError, KeyError, IndexError, StopIteration) as error:
        result["reasons"].append(str(error))
    return result


def _publish_operational_prefix_v1(
    application: OperationalPrefixApplicationV1, recorder: Any
) -> dict[str, Any]:
    record = _live(application)
    with record.repository.publication_guard():
        state = application.check_recorder(recorder)
        if record.catalog_json is not None:
            raise RuntimeError("operational prefix already published")
        exported = recorder.export_operational_prefix()
        _write_exclusive_v1(
            recorder.directory / "source-publication-state.json", canonical_bytes_v1(state)
        )
        manifest = dict(exported["original_files"])
        manifest["source-publication-state.json"] = _pin(
            recorder.directory / "source-publication-state.json"
        )
        source = record.source
        if source is None:
            raise RuntimeError("private operational source missing")
        receipt = {
            "schema_version": "simulation.operational-prefix.receipt.v1",
            "scope": "EXCLUDED_SOURCE_ONLY_PREFIX",
            "clock_schema": "simulation.operational-time.v1",
            "application_id": record.application_id,
            "source_session_id": source.source_session_id,
            "original_files": manifest,
            "source_prefix_complete": False,
            **LIMITS_V1,
        }
        view = verify_operational_prefix_originals_v1(recorder.directory, receipt)
        if view["original_integrity"] != "VERIFIED" or view["source_prefix_complete"] is not True:
            raise ValueError(
                "historical original reader rejected source prefix: " + "; ".join(view["reasons"])
            )
        receipt.update({k: v for k, v in view.items() if k not in {"reasons", "live_authority"}})
        application.check_recorder(recorder)
        second = verify_operational_prefix_originals_v1(recorder.directory, receipt)
        _same_v1(second, view, "originals changed across guarded publication")
        raw = canonical_bytes_v1(receipt)
        _write_exclusive_v1(recorder.directory / "prefix-receipt.json", raw)
        _write_exclusive_v1(
            record.output / "capture-catalog.json",
            canonical_bytes_v1(
                {
                    "scope": "SOURCE_ONLY_NO_NATIVE_ADMISSION",
                    "receipt_path": "prefix-originals/prefix-receipt.json",
                    "receipt_sha256": hashlib.sha256(raw).hexdigest(),
                    "entry": receipt,
                }
            ),
        )
        record.catalog_json = raw
        return cast(dict[str, Any], decode_original_json_v1(raw))


def _failure_row_v1(
    record: _LiveApplicationV1, phase: str, error: BaseException, *, primary_id: int | None
) -> dict[str, Any]:
    row = {
        "failure_id": len(record.failures) + 1,
        "phase": phase,
        "error_type": type(error).__name__,
        "error": str(error),
        "role": "PRIMARY" if primary_id is None else "SECONDARY",
        "primary_failure_id": primary_id,
    }
    record.failures.append(row)
    return row


def _failure_write_v1(
    record: _LiveApplicationV1, path: Path, payload: Any, *, phase: str, primary_id: int
) -> bool:
    try:
        _write_exclusive_v1(path, canonical_bytes_v1(payload))
        return True
    except BaseException as error:
        record.durable_failure_evidence_complete = False
        _failure_row_v1(record, phase, error, primary_id=primary_id)
        return False


def _persist_failure_stage_v1(
    record: _LiveApplicationV1, directory: Path, *, primary_id: int
) -> None:
    record.failure_sidecar_sequence += 1
    number = record.failure_sidecar_sequence
    originals: dict[str, Any] = {}
    for name in (
        "preregistration.json",
        "prefix-failures.json",
        "frozen-originals.json",
        "operational-originals.json",
        "prefix-receipt.json",
    ):
        path = directory / name
        if path.exists():
            try:
                originals[name] = _pin(path)
            except BaseException as error:
                record.durable_failure_evidence_complete = False
                _failure_row_v1(record, "failure_reference_pin", error, primary_id=primary_id)
    payload = {
        "schema_version": "simulation.operational-prefix.stage-failures.v1",
        "primary_failure_id": primary_id,
        "failures": record.failures,
        "existing_original_pins": originals,
        "durable_failure_evidence_complete": record.durable_failure_evidence_complete,
    }
    success = _failure_write_v1(
        record,
        directory / f"stage-failures-{number}.json",
        payload,
        phase="stage_failure_persistence",
        primary_id=primary_id,
    )
    if not success:
        # Independent append-only fallback, never a retry of the failed target.
        _failure_write_v1(
            record,
            record.output / f"stage-failure-fallback-{number}.json",
            {**payload, "failures": record.failures},
            phase="stage_failure_fallback_persistence",
            primary_id=primary_id,
        )


def _archive_primary_failure_v1(
    record: _LiveApplicationV1,
    recorder: Any,
    directory: Path,
    error: BaseException,
    *,
    primary_id: int,
) -> None:
    """Primary plus actual partial data precede any fallible inherited archival."""
    if recorder is not None:
        recorder.record_failure("execution_publication", error)
    prefix_failures = directory / "prefix-failures.json"
    if not prefix_failures.exists():
        _failure_write_v1(
            record,
            prefix_failures,
            recorder._d_failures if recorder is not None else record.failures,
            phase="prefix_failure_persistence",
            primary_id=primary_id,
        )
    _persist_failure_stage_v1(record, directory, primary_id=primary_id)
    try:
        if recorder is not None:
            snapshot = recorder.detached_partial_attempts()
        else:
            snapshot = {
                "schema_version": "simulation.operational-prefix.startup-partial.v1",
                "recorder_allocated": False,
                "source_allocated": record.source is not None,
                "job_id": record.job_id,
                "failures": record.failures,
            }
        record.partial_attempt_snapshot = snapshot
        _failure_write_v1(
            record,
            directory / "partial-attempts.json",
            snapshot,
            phase="partial_attempt_persistence",
            primary_id=primary_id,
        )
    except BaseException as secondary:
        record.durable_failure_evidence_complete = False
        _failure_row_v1(record, "partial_attempt_snapshot", secondary, primary_id=primary_id)
    if recorder is not None:
        if not recorder._operational_freeze_attempted:
            try:
                recorder.freeze_operational_prefix()
            except BaseException as secondary:
                _failure_row_v1(record, "failure_freeze", secondary, primary_id=primary_id)
        if not recorder._operational_export_attempted and recorder._operational_frozen is not None:
            try:
                recorder.export_operational_prefix()
            except BaseException as secondary:
                _failure_row_v1(record, "failure_export", secondary, primary_id=primary_id)
    _failure_write_v1(
        record,
        directory / "publication-failure.json",
        {
            "error_type": type(error).__name__,
            "error": str(error),
            "primary_failure_id": primary_id,
            "additional_failures": record.failures,
        },
        phase="publication_failure_persistence",
        primary_id=primary_id,
    )
    _persist_failure_stage_v1(record, directory, primary_id=primary_id)


def run_operational_prefix_v1(
    application: OperationalPrefixApplicationV1,
    worker: SimulationWorker,
    job: Any,
    *,
    start_monotonic: float,
) -> tuple[dict[str, Any], list[Any], list[Any]]:
    from contextlib import ExitStack

    from cloud_edge_robot_arm.research.operational_capture_v1 import OperationalPrefixRecorderV1
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig

    record = _live(application)
    source = None
    recorder = None
    receipt = None
    primary: BaseException | None = None
    primary_traceback: Any = None
    primary_id = 0
    resources = ExitStack()

    def preserve(error: BaseException, phase: str) -> None:
        nonlocal primary, primary_traceback, primary_id
        if primary is not None:
            _failure_row_v1(record, phase, error, primary_id=primary_id)
            return
        pending = record.preregistration_primary
        record.preregistration_primary = None
        if pending is None:
            primary = error
            primary_traceback = error.__traceback__
            primary_id = _failure_row_v1(record, phase, error, primary_id=None)["failure_id"]
        else:
            primary, primary_id = pending
            primary_traceback = primary.__traceback__
            if error is not primary:
                _failure_row_v1(record, phase, error, primary_id=primary_id)
        record.catalog_json = None
        directory = source.directory if source is not None else record.output
        try:
            _archive_primary_failure_v1(record, recorder, directory, primary, primary_id=primary_id)
        except BaseException as archive_error:
            record.durable_failure_evidence_complete = False
            _failure_row_v1(record, "failure_archival", archive_error, primary_id=primary_id)
            _persist_failure_stage_v1(record, record.output, primary_id=primary_id)

    try:
        source = _prepare_source_v1(application, worker, job, start_monotonic=start_monotonic)
        source.backend.initialize(source.capture._config)
        _check_source_v1(application)
        resources.enter_context(source.capture)
        record.issuing = True
        try:
            recorder = OperationalPrefixRecorderV1.from_application(
                application,
                source.backend,
                source.capture,
                source.executor,
                directory=source.directory,
            )
        finally:
            record.issuing = False
        resources.enter_context(recorder)
        application.check_recorder(recorder)
        source.backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=0))
        application.check_recorder(recorder)
        with recorder.purpose("SETTLE"):
            source.backend.step(steps=120)
        application.check_recorder(recorder)
        recorder.capture()
        application.check_recorder(recorder)
        recorder.read_capture_current()
        application.check_recorder(recorder)
        if (
            source.backend.operation_observer_failures
            or recorder._d_failures
            or recorder._audit_failures
        ):
            raise RuntimeError("retained backend/D/super observer failure")
        _write_exclusive_v1(source.directory / "prefix-failures.json", canonical_bytes_v1([]))
        recorder.freeze_operational_prefix()
        receipt = _publish_operational_prefix_v1(application, recorder)
    except BaseException as error:
        preserve(error, "runner")
    finally:
        try:
            resources.__exit__(
                type(primary) if primary is not None else None, primary, primary_traceback
            )
        except BaseException as cleanup_error:
            preserve(cleanup_error, "resource_cleanup")
        if source is not None:
            try:
                source.backend.shutdown()
            except BaseException as cleanup_error:
                preserve(cleanup_error, "backend_shutdown")
    if primary is not None:
        directory = source.directory if source is not None else record.output
        _persist_failure_stage_v1(record, directory, primary_id=primary_id)
        record.partial_receipt = {
            "source_prefix_complete": False,
            "primary_error": {"error_type": type(primary).__name__, "error": str(primary)},
            "failures": record.failures,
            "secondary_errors": [row for row in record.failures if row.get("role") == "SECONDARY"],
            "durable_failure_evidence_complete": record.durable_failure_evidence_complete,
            **LIMITS_V1,
        }
        if not record.durable_failure_evidence_complete:
            record.partial_receipt["available_partial_attempts"] = record.partial_attempt_snapshot
        _failure_write_v1(
            record,
            record.output / "runner-failure.json",
            record.partial_receipt,
            phase="runner_failure_persistence",
            primary_id=primary_id,
        )
        # A reporting failure stays secondary; private memory retains the original.
        record.partial_receipt["secondary_errors"] = [
            row for row in record.failures if row.get("role") == "SECONDARY"
        ]
        record.partial_receipt["durable_failure_evidence_complete"] = (
            record.durable_failure_evidence_complete
        )
        _persist_failure_stage_v1(record, record.output, primary_id=primary_id)
        raise primary.with_traceback(primary_traceback)
    if receipt is None:
        raise RuntimeError("operational prefix ended without source receipt")
    return (
        {
            "evaluation_scope": "OPERATIONAL_SOURCE_PREFIX_EXCLUDED",
            "source_prefix_complete": True,
            "task_execution": "NOT_RUN",
            "receipt": receipt,
        },
        [],
        [],
    )
