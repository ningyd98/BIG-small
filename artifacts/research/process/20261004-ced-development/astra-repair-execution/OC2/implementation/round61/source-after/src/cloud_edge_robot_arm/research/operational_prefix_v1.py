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
    validate_policy_v1,
    validate_preregistration_v1,
)

if TYPE_CHECKING:
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
    failures: list[dict[str, Any]] = field(default_factory=list)


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
        # Shared worker branch is deliberately not installed during Task1.
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
        raise RuntimeError("Task2 worker dispatch is not implemented or authorized in Task1")

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

    def check_recorder(self, recorder: Any) -> dict[str, Any]:
        _live(self)
        raise RuntimeError("Task2 recorder issuance is pending; no source verdict")

    def catalog_entry(self) -> dict[str, Any]:
        _live(self)
        raise RuntimeError("no live operational source-only publication in Task1")


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
        record.preregistration_bytes = raw
        context.preregistration_sha256 = hashlib.sha256(raw).hexdigest()
        _check_source_v1(application)
        return context
    except BaseException as error:
        record.failures.append(
            {"phase": "preregistration", "error_type": type(error).__name__, "error": str(error)}
        )
        _write_exclusive_v1(
            record.output / "startup-failures.json", canonical_bytes_v1(record.failures)
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
