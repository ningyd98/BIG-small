"""Locked offline recovery production; physical imports occur only on execute-once.

This producer never changes protocol_evidence's acceptance rules, calls a provider,
or supplies formal truth to development consumers. Its inventory proves closure
inside explicitly declared local sources, not the existence of external history.
"""

from __future__ import annotations

import fcntl
import gzip
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import queue
import shutil
import signal
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

import yaml

from cloud_edge_robot_arm.datasets.rgbd.models import canonical_json, content_digest
from cloud_edge_robot_arm.research.protocol import build_scene_pools
from cloud_edge_robot_arm.research.protocol_evidence import (
    RULES_PATH,
    _candidate,
    _eligible,
    _fault,
    _pool_check,
    _recovery,
    _topology_complete,
    write_recovery_source,
)

REPOSITORY = Path(__file__).resolve().parents[3]
BUDGETS = {
    "wall_s": 1800.0,
    "retained_bytes": 2 * 1024**3,
    "min_free_bytes": 10 * 1024**3,
    "rcap_s": 60.0,
}
SOURCE_PATHS = (
    "src/cloud_edge_robot_arm/research/protocol_generation.py",
    "scripts/generate_rgbd_protocol_evidence.py",
    "src/cloud_edge_robot_arm/research/protocol_evidence.py",
    "src/cloud_edge_robot_arm/research/protocol.py",
    "src/cloud_edge_robot_arm/datasets/rgbd/teacher.py",
    "src/cloud_edge_robot_arm/datasets/rgbd/models.py",
    "src/cloud_edge_robot_arm/datasets/rgbd/scene_sampler.py",
    "src/cloud_edge_robot_arm/datasets/rgbd/capture.py",
    "src/cloud_edge_robot_arm/simulation/config.py",
    "src/cloud_edge_robot_arm/simulation/models.py",
    "src/cloud_edge_robot_arm/simulation/mujoco/backend.py",
    "src/cloud_edge_robot_arm/simulation/mujoco/camera.py",
    "src/cloud_edge_robot_arm/simulation/mujoco/skill_robot.py",
    "src/cloud_edge_robot_arm/simulation/mujoco/motion_controller.py",
    "src/cloud_edge_robot_arm/simulation/mujoco/episode_evaluator.py",
    "src/cloud_edge_robot_arm/vision/capture.py",
    "src/cloud_edge_robot_arm/vision/observations.py",
    "src/cloud_edge_robot_arm/contracts/models.py",
    "src/cloud_edge_robot_arm/edge/robot_adapter.py",
    "assets/robots/franka_panda/scene.xml",
)


def _hash(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _read(path: Path) -> Any:
    def reject(value: str) -> Any:
        raise ValueError(f"nonfinite JSON: {value}")

    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as stream:
        return json.load(stream, parse_constant=reject)


def _write(path: Path, value: Any) -> None:
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("symlink output forbidden")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        stream.write(canonical_json(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _fresh(path: Path) -> None:
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("symlink output forbidden")
    path.mkdir(parents=True, exist_ok=False)


def _physical_key(parameters: dict) -> str | None:
    if not {"target", "destination"} <= parameters.keys():
        return None

    # Camera/noise/asset/name changes never create independent physical scenes.
    def body(value: dict) -> dict:
        return {
            key: value[key]
            for key in ("position", "half_size", "mass_kg", "friction")
            if key in value
        }

    geometry = {
        "target": body(parameters["target"]),
        "destination": body(parameters["destination"]),
        "distractors": [body(v) for v in parameters.get("distractors", [])],
    }
    return content_digest(geometry)


def inventory_history(sources: list[Path]) -> dict:
    """Join explicit original metadata identities, including renamed components."""
    if not sources or len({p.resolve() for p in sources}) != len(sources):
        raise ValueError("nonempty unique history sources required")
    parents: dict[str, str] = {}
    group_files: dict[str, set[str]] = {}
    physical: set[str] = set()
    scene_hashes: set[str] = set()

    def find(node: str) -> str:
        parents.setdefault(node, node)
        if parents[node] != node:
            parents[node] = find(parents[node])
        return parents[node]

    def join(nodes: list[str]) -> None:
        if nodes:
            base = find(nodes[0])
            for node in nodes[1:]:
                parents[find(node)] = base

    def walk(value: Any, path: str, component: str | None = None) -> None:
        if isinstance(value, dict):
            component = value.get("component", component)
            group = value.get("group_id")
            scene = value.get("scene_hash")
            parameters = value.get("scene_parameters", {})
            nodes = []
            nested_scene = value.get("scene")
            if isinstance(nested_scene, dict):
                nested_group = nested_scene.get("group_id")
                if isinstance(nested_group, str):
                    nodes.append("g:" + nested_group)
                    group_files.setdefault(nested_group, set()).add(path)
            if isinstance(group, str):
                nodes.append("g:" + group)
                group_files.setdefault(group, set()).add(path)
            if isinstance(scene, str) and len(scene) == 64:
                nodes.append("s:" + scene)
                scene_hashes.add(scene)
            key = _physical_key(parameters) if isinstance(parameters, dict) else None
            if key:
                nodes.append("p:" + key)
                physical.add(key)
            if isinstance(component, str) and nodes:
                nodes.append("c:" + component)
            join(nodes)
            for child in value.values():
                walk(child, path, component)
        elif isinstance(value, list):
            for child in value:
                walk(child, path, component)

    entries = []
    for source in sources:
        if not source.is_file() or any(p.is_symlink() for p in (source, *source.parents)):
            raise ValueError(f"missing/symlink history source: {source}")
        source = source.resolve()
        entries.append({"path": str(source), "sha256": _hash(source)})
        if source.suffix == ".jsonl":
            with source.open() as stream:
                for line in stream:
                    walk(json.loads(line), str(source))
        else:
            walk(_read(source), str(source))
    components: dict[str, list[str]] = {}
    for node in parents:
        components.setdefault(find(node), []).append(node)
    unresolved = sorted(
        group
        for group in group_files
        if not any(n.startswith("p:") for n in components[find("g:" + group)])
    )
    return {
        "schema_version": "ced.history-inventory.v1",
        "entries": entries,
        "group_ids": sorted(group_files),
        "scene_hashes": sorted(scene_hashes),
        "physical_keys": sorted(physical),
        "components": sorted(sorted(v) for v in components.values()),
        "unresolved_groups": unresolved,
        "unresolved_sources": {g: sorted(group_files[g]) for g in unresolved},
        "complete": bool(group_files) and not unresolved,
        "scope": "EXPLICIT_LOCAL_ORIGINALS_ONLY",
    }


def _source_pins() -> dict:
    paths = set(SOURCE_PATHS)
    paths.update(
        str(p.relative_to(REPOSITORY))
        for p in (REPOSITORY / "assets/robots/franka_panda").glob("*.xml")
    )
    return {p: _hash(REPOSITORY / p) for p in sorted(paths)}


def _environment() -> dict:
    return {
        "python": platform.python_version(),
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("mujoco", "numpy", "pillow", "pydantic")
        },
    }


def prepare_generation(history_sources: list[Path], output: Path, seed: int = 2026100507) -> dict:
    """Pure CPU: archive inventory and register fresh complete pools and all schedules."""
    inventory = inventory_history(history_sources)
    rules = yaml.safe_load(RULES_PATH.read_text())
    if (
        rules["fault_type"],
        rules["required_recovery_groups"],
        rules["speed_m_s"],
        rules["duration_s"],
        rules["directions_y"],
        rules["maximum_recovery_s"],
    ) != ("TARGET_MOTION", 200, 0.02, 1.0, [1.0, -1.0], 60.0):
        raise ValueError("unsupported original fault recipe")
    excluded = set(inventory["group_ids"])
    pools: dict[str, Any]
    for _ in range(5):
        pools = cast(
            dict[str, Any], build_scene_pools(seed, excluded, protocol_version="ced.research.v2")
        )
        aliases = {
            row["scene"]["group_id"]
            for rows in pools.values()
            for row in rows
            if row["scene_hash"] in inventory["scene_hashes"]
            or _physical_key(row["scene"]["scene_parameters"]) in inventory["physical_keys"]
        }
        if not aliases:
            break
        excluded.update(aliases)
    else:
        raise ValueError("bounded history isolation sampling exhausted")
    _pool_check(pools, excluded)
    if not _topology_complete(pools, "ced.research.v2"):
        raise ValueError("complete3260v2 topology required")
    pools["_evidence"] = {
        "protocol_version": "ced.research.v2",
        "history_roots": [e["path"] for e in inventory["entries"]],
        "excluded_groups": sorted(excluded),
        "opportunity_sources": {},
        "recovery_sources": {},
    }
    schedules = {
        row["assignment_id"]: {"fault": _fault(index, rules), "eligible": _eligible(row, rules)}
        for index, row in enumerate(pools["recovery"])
    }
    _fresh(output)
    payloads = {
        "history.json": inventory,
        "pools.json": pools,
        "recipe.json": rules,
        "schedules.json": schedules,
        "budgets.json": BUDGETS,
        "candidates.json": {r["assignment_id"]: _candidate(r) for r in pools["formal"]},
    }
    for name, value in payloads.items():
        _write(output / name, value)
    header = {
        "schema_version": "ced.recovery-generation.v1",
        "protocol_directory": str(output.resolve()),
        "seed": seed,
        "history_complete": inventory["complete"],
        "payload_hashes": {name: _hash(output / name) for name in payloads},
        "source_hashes": _source_pins(),
        "environment": _environment(),
        "config": {
            "model_path": "assets/robots/franka_panda/scene.xml",
            "physics_dt_s": 0.0041666667,
            "domain_randomization": False,
            "render_rgb": True,
            "render_depth": True,
            "camera_width": 320,
            "camera_height": 240,
        },
        "settle_steps": 120,
        "provider_calls": 0,
        "implicit_retries": 0,
    }
    _write(output / "generation.json", header)
    return {
        "status": "READY_FOR_REVIEW" if inventory["complete"] else "BLOCKED_HISTORY",
        "protocol_hash": content_digest(header),
        "history": inventory,
        "formal_opportunity_producer": "NOT_IMPLEMENTED",
        "actual_calls": 0,
    }


def preflight_generation(protocol: Path, assignment_id: str, attempt: int = 1) -> dict:
    header = _read(protocol / "generation.json")
    if any(p.is_symlink() for p in (protocol, *protocol.parents)):
        raise ValueError("symlink protocol directory forbidden")
    if header.get("protocol_directory") != str(protocol.resolve()):
        raise ValueError("copied or renamed protocol directory cannot reset attempt identity")
    if header["schema_version"] != "ced.recovery-generation.v1":
        raise ValueError("unsupported generation protocol")
    for name, digest in header["payload_hashes"].items():
        if Path(name).name != name or _hash(protocol / name) != digest:
            raise ValueError("protocol payload drift")
    if header["source_hashes"] != _source_pins() or header["environment"] != _environment():
        raise ValueError("execution source/environment drift")
    inventory = _read(protocol / "history.json")
    for entry in inventory["entries"]:
        if _hash(Path(entry["path"])) != entry["sha256"]:
            raise ValueError("history source drift")
    if not inventory["complete"] or not header["history_complete"]:
        raise ValueError("history identity closure is incomplete")
    if type(attempt) is not int or not 1 <= attempt <= 5:
        raise ValueError("bounded attempt ordinal1..5 required")
    pools = _read(protocol / "pools.json")
    _pool_check(pools, set(pools["_evidence"]["excluded_groups"]))
    if not _topology_complete(
        {k: v for k, v in pools.items() if not k.startswith("_")}, "ced.research.v2"
    ):
        raise ValueError("complete3260v2 topology required")
    rows = [r for r in pools["recovery"] if r["assignment_id"] == assignment_id]
    if len(rows) != 1:
        raise ValueError("canonical recovery assignment required")
    schedule = _read(protocol / "schedules.json")[assignment_id]
    rules = _read(protocol / "recipe.json")
    index = pools["recovery"].index(rows[0])
    if schedule != {"fault": _fault(index, rules), "eligible": _eligible(rows[0], rules)}:
        raise ValueError("registered fault/eligibility schedule drift")
    return {
        **header,
        **schedule,
        "row": rows[0],
        "attempt": attempt,
        "budgets": _read(protocol / "budgets.json"),
        "protocol_hash": content_digest(header),
        "status": "PREFLIGHT_ONLY",
        "actual_calls": 0,
    }


class StepSpool:
    """Bounded detached-event writer. Callbacks enqueue; only this thread flushes.

    A crash preserves its fsynced prefix and the allocation BEGIN. Missing tail
    remains INCOMPLETE, never repaired into a successful physical history.
    """

    def __init__(self, path: Path) -> None:
        self.events: queue.Queue[Any] = queue.Queue(maxsize=32768)
        self.sequence = 0
        self.error: Exception | None = None
        self.stream = path.open("x")
        self.worker = threading.Thread(target=self._drain, daemon=True)
        self.worker.start()

    def _drain(self) -> None:
        try:
            while True:
                event = self.events.get()
                if event is None:
                    break
                self.stream.write(canonical_json(event) + "\n")
                if event["record_seq"] % 64 == 0:
                    self.stream.flush()
                    os.fsync(self.stream.fileno())
            self.stream.flush()
            os.fsync(self.stream.fileno())
        except Exception as exc:
            self.error = exc
        finally:
            self.stream.close()

    def append(self, kind: str, payload: dict) -> None:
        if self.error is not None:
            raise RuntimeError("raw step spool failed") from self.error
        self.sequence += 1
        try:
            self.events.put_nowait({"record_seq": self.sequence, "kind": kind, "payload": payload})
        except queue.Full as exc:
            raise BudgetExceeded("bounded raw step spool saturated") from exc

    def close(self) -> None:
        if self.worker.is_alive():
            self.events.put(None, timeout=5.0)
        self.worker.join(timeout=5.0)
        if self.worker.is_alive() or self.error is not None:
            raise RuntimeError("raw step spool did not finish durably") from self.error


class BudgetExceeded(RuntimeError):
    """Stop the current allocation without deleting its physical prefix."""


class GenerationBudget:
    def __init__(
        self, limits: dict, output: Path, *, clock: Any = time.monotonic, disk_free: Any = None
    ) -> None:
        self.limits = limits
        self.output = output
        self.clock = clock
        self.started = clock()
        self.fault_start_s: float | None = None
        self.disk_free = disk_free or (lambda: shutil.disk_usage(output).free)

    def check(self, sim_time_s: float, retained_bytes: int) -> None:
        if not math.isfinite(sim_time_s):
            raise BudgetExceeded("nonfinite physical clock")
        if self.clock() - self.started > self.limits["wall_s"]:
            raise BudgetExceeded("wall budget exceeded")
        if (
            self.fault_start_s is not None
            and sim_time_s - self.fault_start_s > self.limits["rcap_s"]
        ):
            raise BudgetExceeded("fault-start Rcap budget exceeded")
        if retained_bytes > self.limits["retained_bytes"]:
            raise BudgetExceeded("retained byte budget exceeded")
        if self.disk_free() < self.limits["min_free_bytes"] + retained_bytes:
            raise BudgetExceeded("disk free-space reserve would be violated")


@contextmanager
def renderer_exclusive(path: Path) -> Any:
    """Cross-process advisory lease for this producer's sole renderer queue.

    Root must also serialize other renderer users; they do not share this lease.
    """
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("symlink renderer lease forbidden")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BudgetExceeded("renderer is already leased by another producer") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def wall_deadline(seconds: float) -> Any:
    """Linux CLI wall alarm, restored after the allocation; no hidden retry."""
    previous = signal.getsignal(signal.SIGALRM)
    prior_timer = signal.getitimer(signal.ITIMER_REAL)
    if prior_timer[0] or threading.current_thread() is not threading.main_thread():
        raise ValueError("execute-once needs the sole CLI main-thread wall timer")

    def expire(_number: int, _frame: Any) -> None:
        raise BudgetExceeded("wall budget alarm exceeded")

    signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous)


def _run_physical(plan: dict, output: Path) -> dict:
    """The sole actual path: existing scene reset, fault, T5 and passive hooks."""
    # Lazy imports: default CLI and prepare never initialize a backend or renderer.
    from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec
    from cloud_edge_robot_arm.datasets.rgbd.teacher import EpisodeRecorder, run_teacher_episode
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import PhysicalFault, PhysicalFaultType
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    scene = SceneSpec.model_validate(plan["row"]["scene"])
    guard = GenerationBudget(plan["budgets"], output)
    spool = StepSpool(output / "raw-step-journal.jsonl")
    raw: list[Any] = []
    controls: list[Any] = []
    actions: list[dict] = []
    commands: list[dict] = []
    events: list[dict] = []
    recovery_start: int | None = None
    backend: Any = None
    recorder: Any = None
    outcome = None
    failure = None

    def record(snapshot: Any) -> None:
        if raw and raw[-1].physics_step == snapshot.physics_step:
            if raw[-1] != snapshot:
                raise ValueError("same-step physical snapshot changed")
            return
        raw.append(snapshot)
        spool.append("PHYSICS", asdict(snapshot))
        # Conservative reservation for both originals and final six-file source.
        guard.check(snapshot.sim_time_s, (len(raw) + len(controls)) * 16384)

    def actuator(snapshot: Any) -> None:
        controls.append(snapshot)
        spool.append("ACTUATOR_PRE", asdict(snapshot))
        guard.check(snapshot.sim_time_s, (len(raw) + len(controls)) * 16384)

    try:
        guard.check(0.0, 0)
        with MuJoCoCaptureSession(SimulatorConfig(**plan["config"])) as capture:
            capture.apply_scene(scene)
            backend = capture._backend
            record(backend.current_physics_observation())
            with backend.observe_actuator_steps(actuator):
                with backend.observe_physics_steps(record):
                    backend.step(steps=plan["settle_steps"])
                    guard.fault_start_s = backend.get_sim_time()
                    parameters = plan["fault"]["parameters"]
                    backend.inject_fault(PhysicalFault(PhysicalFaultType.TARGET_MOTION, parameters))
                    maximum_steps = (
                        math.ceil(parameters["duration_s"] / plan["config"]["physics_dt_s"]) + 1
                    )
                    for _ in range(maximum_steps):
                        if any(
                            e["event"] == "TARGET_MOTION_FINISHED" for e in backend.fault_records
                        ):
                            break
                        backend.step(steps=1)
                    if not any(
                        e["event"] == "TARGET_MOTION_FINISHED" for e in backend.fault_records
                    ):
                        raise RuntimeError(
                            "actual injected fault did not finish within locked duration"
                        )
                # T5 installs the original sole observer; do not nest observers.
                recovery_start = backend.total_physics_steps
                recorder = EpisodeRecorder()
                outcome = run_teacher_episode(
                    scene,
                    MuJoCoSkillRobot(backend),
                    recorder,
                    settle_steps=0,
                    physical_observer=record,
                    action_observer=lambda event: actions.append(dict(event)),
                )
            commands = backend.command_records
            events = backend.fault_records
    except Exception as exc:
        failure = f"{type(exc).__name__}: {exc}"
        if backend is not None:
            commands = backend.command_records
            events = backend.fault_records
    finally:
        try:
            spool.close()
        except Exception as exc:
            failure = f"raw step spool: {exc}"
        # Outside callbacks, persist every available detached original, even after
        # budget/action/renderer failures. No fabricated step or success completion.
        for name, values in (("raw-observations.jsonl", raw), ("raw-actuators.jsonl", controls)):
            path = output / name
            with path.open("x") as stream:
                for value in values:
                    stream.write(canonical_json(asdict(value)) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        for name, value in (
            ("action-events.json", actions),
            ("backend-commands.json", commands),
            ("raw-fault-events.json", events),
        ):
            _write(output / name, value)
        _write(
            output / "teacher-frames.json",
            [frame.model_dump(mode="json") for frame in recorder.frames] if recorder else [],
        )
        _write(
            output / "teacher-unframed-actions.json",
            [value.model_dump(mode="json") for value in recorder.unframed_actions]
            if recorder
            else [],
        )
        _write(
            output / "physical-terminal.json",
            {
                "failure": failure,
                "independent_t5_outcome": asdict(outcome) if outcome else None,
                "recovery_start_step": recovery_start,
                "raw_states": len(raw),
                "actuator_rows": len(controls),
                "actions": len(actions),
                "scope": "ACTUAL_OFFLINE_T5",
            },
        )
    if raw and controls:
        # Failed and partial traces are intentionally serialized too; independent
        # acceptance can only PROVE the complete injected successful safe trace.
        write_recovery_source(
            row=plan["row"],
            observations=raw,
            action_events=actions,
            backend_commands=commands,
            actuator_steps=controls,
            fault_events=events,
            recovery_start_step=recovery_start
            if recovery_start is not None
            else raw[-1].physics_step,
            output=output / "source",
        )
    if failure:
        raise RuntimeError(failure)
    return {
        "physical_calls": len(raw) - 1,
        "raw_states": len(raw),
        "actuator_rows": len(controls),
        "teacher_actions": len(actions),
    }


def execute_recovery_once(
    protocol: Path,
    assignment_id: str,
    output: Path,
    *,
    attempt: int = 1,
    expected_protocol_hash: str,
) -> dict:
    """Allocate once before actual work and retain failure/partial physical input."""
    plan = preflight_generation(protocol, assignment_id, attempt)
    if expected_protocol_hash != plan["protocol_hash"]:
        raise ValueError("review protocol hash differs from frozen input")
    if any(p.is_symlink() for p in (output, *output.parents)) or output.exists():
        raise ValueError("fresh nonsymlink attempt output required")
    allocations = protocol / "allocations"
    if attempt > 1:
        previous = allocations / f"{assignment_id}-attempt-{attempt - 1}.json"
        if not previous.is_file():
            raise ValueError("previous attempt allocation must exist; no ordinal skipping")
        previous_output = Path(_read(previous)["output"])
        if (
            not (previous_output / "result.json").is_file()
            or _read(previous_output / "result.json")["status"] == "PROVEN"
        ):
            raise ValueError("previous attempt incomplete or already PROVEN; no implicit retry")
    # Exclusive file is also the per-allocation concurrency/re-entry guard. A
    # crashed BEGIN remains consumed; new output names cannot reset its identity.
    _write(
        allocations / f"{assignment_id}-attempt-{attempt}.json",
        {
            "assignment_id": assignment_id,
            "attempt": attempt,
            "state": "ALLOCATED",
            "protocol_hash": plan["protocol_hash"],
            "output": str(output.resolve()),
        },
    )
    _fresh(output)
    _write(output / "execution-plan.json", plan)
    status, reason, diagnostics, proof = "INCOMPLETE", None, {}, None
    try:
        if not plan["eligible"]:
            status, reason = "EXCLUDED", "preregistered workspace eligibility failed"
        else:
            lease = (
                REPOSITORY
                / "artifacts/research/process/20261004-ced-development"
                / "astra-repair-execution/R07/producer/renderer.lock"
            )
            with renderer_exclusive(lease), wall_deadline(plan["budgets"]["wall_s"]):
                diagnostics = _run_physical(plan, output)
            _, proof = _recovery(
                output / "source", plan["row"], plan["fault"], _read(protocol / "recipe.json")
            )
            # Enforce G4's fault-start deadline, stronger than teacher-only bound.
            if (
                proof["independent_outcome"]["elapsed_s"]
                + proof["recovery_start_s"]
                - proof["injection_start_s"]
                > 60.0
            ):
                raise BudgetExceeded("fault-start Rcap result exceeded")
            status = "PROVEN"
    except Exception as exc:
        status, reason = "FAILED", f"{type(exc).__name__}: {exc}"
    files = [p for p in output.rglob("*") if p.is_file()]
    retained = sum(p.stat().st_size for p in files)
    if retained > plan["budgets"]["retained_bytes"]:
        status, reason = "FAILED", "retained byte budget exceeded; originals preserved"
    attempted_groups = {p.name.rsplit("-attempt-", 1)[0] for p in allocations.glob("*.json")}
    report = {
        "schema_version": "ced.recovery-generation-result.v1",
        "assignment_id": assignment_id,
        "attempt": attempt,
        "status": status,
        "reason": reason,
        "diagnostics": diagnostics,
        "proof": proof,
        "denominator": 200,
        "attempted": len(attempted_groups),
        "unattempted": 200 - len(attempted_groups),
        "g4_measured": False,
        "provider_calls": 0,
        "implicit_retries": 0,
        "retained_bytes": retained,
        "payload_hashes": {str(p.relative_to(output)): _hash(p) for p in files},
    }
    _write(output / "result.json", report)
    return report
