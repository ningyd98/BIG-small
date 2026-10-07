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
from collections.abc import Callable
from contextlib import contextmanager
from copy import deepcopy
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


def _plain_path(path: Path) -> None:
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError(f"symlink source/namespace forbidden: {path}")


def _payloads_match(directory: Path, header: dict) -> None:
    expected = {
        "history.json",
        "pools.json",
        "recipe.json",
        "schedules.json",
        "budgets.json",
        "candidates.json",
    }
    if set(header["payload_hashes"]) != expected:
        raise ValueError("exact six locked input payloads required")
    for name, digest in header["payload_hashes"].items():
        path = directory / name
        _plain_path(path)
        if _hash(path) != digest:
            raise ValueError("protocol payload drift")


def _allocation_records(directory: Path, pools: dict, allowed_hashes: set[str]) -> dict:
    """Read the canonical consumed ledger; missing outputs remain consumed."""
    _plain_path(directory)
    allowed_ids = {row["assignment_id"] for row in pools["recovery"]}
    records: dict[str, dict[int, dict]] = {}
    for path in sorted(directory.glob("*.json")):
        _plain_path(path)
        record = _read(path)
        assignment, ordinal = record["assignment_id"], record["attempt"]
        if (
            assignment not in allowed_ids
            or type(ordinal) is not int
            or not 1 <= ordinal <= 5
            or path.name != f"{assignment}-attempt-{ordinal}.json"
            or record["state"] != "ALLOCATED"
            or record["protocol_hash"] not in allowed_hashes
        ):
            raise ValueError("canonical allocation identity/version mismatch")
        output = Path(record["output"])
        _plain_path(output)
        if str(output.resolve()) != record["output"]:
            raise ValueError("canonical allocation output path mismatch")
        result = _read(output / "result.json") if (output / "result.json").is_file() else None
        if result is not None:
            _plain_path(output / "result.json")
            if result["status"] not in {"PROVEN", "FAILED", "INCOMPLETE", "EXCLUDED"}:
                raise ValueError("unknown canonical allocation result status")
        records.setdefault(assignment, {})[ordinal] = {"record": record, "result": result}
    for attempts in records.values():
        if sorted(attempts) != list(range(1, max(attempts) + 1)):
            raise ValueError("canonical allocation ordinal prefix missing")
        for ordinal in range(1, max(attempts)):
            prior = attempts[ordinal]["result"]
            if prior is None or prior["status"] == "PROVEN":
                raise ValueError("later ordinal follows incomplete or PROVEN allocation")
    return records


def prepare_successor_generation(
    predecessor: Path, output: Path, *, expected_predecessor_hash: str
) -> dict:
    """Pure CPU, one v2 overlay; preserve original inputs/evidence/consumed ledger."""
    _plain_path(predecessor)
    prior = _read(predecessor / "generation.json")
    if (
        prior["schema_version"] != "ced.recovery-generation.v1"
        or prior["protocol_directory"] != str(predecessor.resolve())
        or content_digest(prior) != expected_predecessor_hash
    ):
        raise ValueError("reviewed initial predecessor hash/namespace mismatch")
    _payloads_match(predecessor, prior)
    if prior["environment"] != _environment():
        raise ValueError("predecessor environment drift")
    inventory = _read(predecessor / "history.json")
    if not inventory["complete"] or not prior["history_complete"]:
        raise ValueError("predecessor history closure incomplete")
    for entry in inventory["entries"]:
        _plain_path(Path(entry["path"]))
        if _hash(Path(entry["path"])) != entry["sha256"]:
            raise ValueError("predecessor history source drift")
    pools = _read(predecessor / "pools.json")
    _pool_check(pools, set(pools["_evidence"]["excluded_groups"]))
    if not _topology_complete(
        {k: v for k, v in pools.items() if not k.startswith("_")}, "ced.research.v2"
    ):
        raise ValueError("predecessor complete3260v2 topology required")
    allocations = predecessor / "allocations"
    records = _allocation_records(allocations, pools, {expected_predecessor_hash})
    evidence: dict[str, str] = {}
    roots = []
    for assignment, attempts in records.items():
        for ordinal, item in attempts.items():
            allocation = allocations / f"{assignment}-attempt-{ordinal}.json"
            evidence[str(allocation.resolve())] = _hash(allocation)
            attempt_output = Path(item["record"]["output"])
            if attempt_output.is_dir():
                roots.append(str(attempt_output.resolve()))
                for path in sorted(attempt_output.rglob("*")):
                    _plain_path(path)
                    if path.is_file():
                        evidence[str(path.resolve())] = _hash(path)
    _fresh(output)
    source_hashes = _source_pins()
    archive = {
        **source_hashes,
        "tests/test_protocol_generation_sources.py": _hash(
            REPOSITORY / "tests/test_protocol_generation_sources.py"
        ),
    }
    for name, digest in archive.items():
        path = output / "source-archive" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write((REPOSITORY / name).read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        if _hash(path) != digest:
            raise ValueError("source changed during successor archive")
    _write(output / "predecessor-generation.json", prior)
    header = {
        **prior,
        "schema_version": "ced.recovery-generation.v2",
        "protocol_directory": str(output.resolve()),
        "predecessor_directory": str(predecessor.resolve()),
        "predecessor_protocol_hash": expected_predecessor_hash,
        "predecessor_manifest_sha256": _hash(predecessor / "generation.json"),
        "predecessor_archive_sha256": _hash(output / "predecessor-generation.json"),
        "allocation_directory": str(allocations.resolve()),
        "source_hashes": source_hashes,
        "source_archive_hashes": archive,
        "environment": _environment(),
        "predecessor_evidence_hashes": evidence,
        "predecessor_evidence_roots": roots,
    }
    _write(output / "generation.json", header)
    return {
        "status": "READY_FOR_REVIEW",
        "protocol_hash": content_digest(header),
        "predecessor_protocol_hash": expected_predecessor_hash,
        "denominator": 200,
        "attempted": len(records),
        "unattempted": 200 - len(records),
        "actual_calls": 0,
        "g4_measured": False,
    }


def _generation_inputs(protocol: Path) -> tuple[dict, Path, Path]:
    _plain_path(protocol)
    header = _read(protocol / "generation.json")
    if header.get("protocol_directory") != str(protocol.resolve()):
        raise ValueError("copied or renamed protocol directory cannot reset attempt identity")
    if header["schema_version"] == "ced.recovery-generation.v1":
        inputs, allocations = protocol, protocol / "allocations"
    elif header["schema_version"] == "ced.recovery-generation.v2":
        inputs = Path(header["predecessor_directory"])
        _plain_path(inputs)
        _plain_path(inputs / "generation.json")
        prior = _read(inputs / "generation.json")
        if (
            prior["schema_version"] != "ced.recovery-generation.v1"
            or prior["protocol_directory"] != str(inputs.resolve())
            or content_digest(prior) != header["predecessor_protocol_hash"]
            or _hash(inputs / "generation.json") != header["predecessor_manifest_sha256"]
            or _hash(protocol / "predecessor-generation.json")
            != header["predecessor_archive_sha256"]
            or _read(protocol / "predecessor-generation.json") != prior
            or header["payload_hashes"] != prior["payload_hashes"]
            or any(
                header[k] != prior[k]
                for k in (
                    "seed",
                    "history_complete",
                    "config",
                    "settle_steps",
                    "provider_calls",
                    "implicit_retries",
                )
            )
        ):
            raise ValueError("immutable predecessor manifest/payload/config drift")
        allocations = inputs / "allocations"
        if header["allocation_directory"] != str(allocations.resolve()):
            raise ValueError("canonical predecessor allocation directory mismatch")
        for name, digest in header["source_archive_hashes"].items():
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise ValueError("source archive path invalid")
            path = protocol / "source-archive" / name
            _plain_path(path)
            if _hash(path) != digest:
                raise ValueError("execution source archive drift")
        for name, digest in header["predecessor_evidence_hashes"].items():
            path = Path(name)
            _plain_path(path)
            if _hash(path) != digest:
                raise ValueError("immutable predecessor evidence drift")
        for name in header["predecessor_evidence_roots"]:
            actual = {str(p.resolve()) for p in Path(name).rglob("*") if p.is_file()}
            expected = {
                p for p in header["predecessor_evidence_hashes"] if Path(name) in Path(p).parents
            }
            if actual != expected:
                raise ValueError("immutable predecessor evidence file coverage drift")
    else:
        raise ValueError("unsupported generation protocol")
    _payloads_match(inputs, header)
    if header["source_hashes"] != _source_pins() or header["environment"] != _environment():
        raise ValueError("execution source/environment drift")
    return header, inputs, allocations


def preflight_generation(protocol: Path, assignment_id: str, attempt: int = 1) -> dict:
    header, inputs, allocations = _generation_inputs(protocol)
    inventory = _read(inputs / "history.json")
    for entry in inventory["entries"]:
        if _hash(Path(entry["path"])) != entry["sha256"]:
            raise ValueError("history source drift")
    if not inventory["complete"] or not header["history_complete"]:
        raise ValueError("history identity closure is incomplete")
    if type(attempt) is not int or not 1 <= attempt <= 5:
        raise ValueError("bounded attempt ordinal1..5 required")
    pools = _read(inputs / "pools.json")
    _pool_check(pools, set(pools["_evidence"]["excluded_groups"]))
    if not _topology_complete(
        {k: v for k, v in pools.items() if not k.startswith("_")}, "ced.research.v2"
    ):
        raise ValueError("complete3260v2 topology required")
    rows = [r for r in pools["recovery"] if r["assignment_id"] == assignment_id]
    if len(rows) != 1:
        raise ValueError("canonical recovery assignment required")
    allowed_hashes = {content_digest(header)}
    if header["schema_version"] == "ced.recovery-generation.v2":
        allowed_hashes.add(header["predecessor_protocol_hash"])
    records = _allocation_records(allocations, pools, allowed_hashes)
    attempts = records.get(assignment_id, {})
    if attempt in attempts:
        raise ValueError("canonical allocation ordinal already consumed")
    if attempt > 1:
        previous = attempts.get(attempt - 1)
        if previous is None or previous["result"] is None:
            raise ValueError("previous attempt incomplete or missing; no ordinal skipping")
        if previous["result"]["status"] == "PROVEN":
            raise ValueError("previous attempt already PROVEN; no retry")
    schedule = _read(inputs / "schedules.json")[assignment_id]
    rules = _read(inputs / "recipe.json")
    index = pools["recovery"].index(rows[0])
    if schedule != {"fault": _fault(index, rules), "eligible": _eligible(rows[0], rules)}:
        raise ValueError("registered fault/eligibility schedule drift")
    return {
        **header,
        **schedule,
        "row": rows[0],
        "attempt": attempt,
        "budgets": _read(inputs / "budgets.json"),
        "input_directory": str(inputs.resolve()),
        "allocation_directory": str(allocations.resolve()),
        "denominator": 200,
        "attempted": len(records),
        "unattempted": 200 - len(records),
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


_RECOVERY_WALL_SCOPE = "r07.recovery-wall.development.v1"
_RECOVERY_WALL_SEMANTICS = "LINUX_BOOTTIME_INCLUDES_SUSPEND"
_RECOVERY_WALL_NS = 60_000_000_000
_RECOVERY_WALL_FACTORY_KEY = object()
_RECOVERY_WALL_APP_NONCE = os.urandom(32).hex()
_RECOVERY_WALL_STARTUP_IDENTITY: dict | None = None
_RECOVERY_WALL_LEASES: dict[int, _RecoveryWallRendererLease] = {}
_RECOVERY_WALL_OWNERS: dict[int, _RecoveryWallOwner] = {}
_RECOVERY_WALL_BACKENDS: dict[int, tuple[_RecoveryWallOwner, object, str]] = {}
_RECOVERY_WALL_PLATFORM_EVIDENCE = (
    REPOSITORY
    / "artifacts/research/process/20261004-ced-development/astra-repair-execution"
    / "R07/producer/recovery-wall/implementation/task1/platform-evidence/report.json"
)
_RECOVERY_WALL_PLATFORM_SHA = "1f7dd09001b4b288a81ccdf44adb2682ffeecd8276c82ea59dc525c5888cf7f6"


def _recovery_wall_process_identity() -> dict:
    """Actual process/boot/time namespace; no caller identity or clock fallback."""
    if platform.system() != "Linux":
        raise ValueError("recovery wall requires Linux process identity")
    fields = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
    start = fields[19]
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    namespace = os.readlink("/proc/self/ns/time")
    offsets = Path("/proc/self/timens_offsets").read_text()
    if not start.isdecimal() or not boot or not namespace or not offsets:
        raise ValueError("missing recovery wall process/boot/time namespace identity")
    return {
        "pid": os.getpid(),
        "process_start_ticks": start,
        "boot_id": boot,
        "time_namespace": namespace,
        "time_namespace_offsets": offsets,
        "app_nonce": _RECOVERY_WALL_APP_NONCE,
    }


def _recovery_wall_boottime_reader() -> Callable[[], int]:
    if platform.system() != "Linux" or not hasattr(time, "CLOCK_BOOTTIME"):
        raise ValueError("Linux CLOCK_BOOTTIME unsupported; no fallback")
    clock_id = time.CLOCK_BOOTTIME

    def read() -> int:
        try:
            value = time.clock_gettime_ns(clock_id)
        except Exception as exc:
            raise BudgetExceeded("CLOCK_BOOTTIME counter read failed; no fallback") from exc
        if type(value) is not int or value < 0:
            raise BudgetExceeded("CLOCK_BOOTTIME counter is not nonnegative integer ns")
        return value

    return read


class _RecoveryWallRendererLease:
    """Only a currently held producer renderer context issues a production lease."""

    def __init__(
        self, key: object, *, handle: Any, identity_read: Callable[[], dict], cpu: bool
    ) -> None:
        if key is not _RECOVERY_WALL_FACTORY_KEY:
            raise ValueError("private live renderer lease factory required")
        self._handle = handle
        self._identity_read = identity_read
        self._identity = deepcopy(identity_read())
        self._cpu = cpu
        self._nonce = os.urandom(32).hex()
        self._file_identity = (
            None if cpu else (os.fstat(handle.fileno()).st_dev, os.fstat(handle.fileno()).st_ino)
        )
        _RECOVERY_WALL_LEASES[id(self)] = self

    def __copy__(self) -> Any:
        raise TypeError("live renderer lease cannot be copied")

    def __deepcopy__(self, _memo: dict) -> Any:
        raise TypeError("live renderer lease cannot be copied")

    def __reduce__(self) -> Any:
        raise TypeError("live renderer lease cannot be pickled")

    def _require_live(self, *, production: bool = False) -> None:
        if _RECOVERY_WALL_LEASES.get(id(self)) is not self or (production and self._cpu):
            raise ValueError("unregistered or CPU-only renderer lease")
        if self._identity_read() != self._identity:
            raise ValueError("renderer lease process identity/lifecycle changed")
        if not self._cpu:
            if self._handle.closed:
                raise ValueError("renderer lease context is closed")
            stat = os.fstat(self._handle.fileno())
            if (stat.st_dev, stat.st_ino) != self._file_identity:
                raise ValueError("renderer lease file identity changed")


def _recovery_wall_lease(value: object, *, production: bool) -> _RecoveryWallRendererLease:
    if type(value) is not _RecoveryWallRendererLease:
        raise ValueError("actual registered renderer context lease required")
    lease = cast(_RecoveryWallRendererLease, value)
    lease._require_live(production=production)
    return lease


def _recovery_wall_evidence(value: Any) -> Any:
    """Retain invalid observations as tagged representations, never valid counters."""
    if isinstance(value, dict):
        return {str(k): _recovery_wall_evidence(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_recovery_wall_evidence(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return {"invalid_type": "float", "original_repr": repr(value)}
    if value is None or type(value) in (str, int, float, bool):
        return value
    return {"invalid_type": type(value).__name__, "original_repr": repr(value)}


class _RecoveryWallOwner:
    """One live development owner; offline receipts cannot recreate its authority.

    The private backend bind is a prerequisite to BEGIN. Task RW2 must obtain that
    exact object inside the held capture/renderer context; RW1 does not wire it.
    """

    def __init__(
        self,
        key: object,
        plan: dict,
        output: Path,
        *,
        lease: _RecoveryWallRendererLease,
        raw_read: Callable[[], Any],
        platform_evidence: dict,
    ) -> None:
        if key is not _RECOVERY_WALL_FACTORY_KEY:
            raise ValueError("private recovery wall owner factory required")
        lease._require_live()
        self._lease = lease
        self._identity = deepcopy(lease._identity)
        self._plan = plan
        self._output = output.resolve()
        _plain_path(output)
        if not output.is_dir():
            raise ValueError("existing allocation output required")
        self._binding = self._plan_binding()
        allocation = Path(self._binding["allocation_path"])
        _plain_path(allocation)
        self._allocation_sha = _hash(allocation)
        row = _read(allocation)
        if row != {
            "assignment_id": self._binding["assignment_id"],
            "attempt": self._binding["attempt"],
            "state": "ALLOCATED",
            "protocol_hash": self._binding["protocol_hash"],
            "output": str(self._output),
        }:
            raise ValueError("canonical allocation does not bind this owner/attempt/output")
        if plan.get("budgets", {}).get("rcap_s") != 60.0:
            raise ValueError("immutable recovery wall Rcap60 required")
        self._raw_read = raw_read
        self._last_ns: int | None = None
        self._backend: Any = None
        self._episode: str | None = None
        self._last_state: dict | None = None
        self._fault_begin: dict | None = None
        self._fault_end: dict | None = None
        self._fault_prefix: list[dict] | None = None
        self._failure: str | None = None
        self._finished = False
        _RECOVERY_WALL_OWNERS[id(self)] = self
        try:
            startup_ns = self._counter()
            self._startup = {
                "scope": _RECOVERY_WALL_SCOPE,
                "clock_semantics": _RECOVERY_WALL_SEMANTICS,
                "clock_api": "time.clock_gettime_ns(time.CLOCK_BOOTTIME)",
                "clock_id": 7,
                "startup_counter_ns": startup_ns,
                "identity": deepcopy(self._identity),
                "renderer_lease_nonce": lease._nonce,
                "allocation": {**self._binding, "sha256": self._allocation_sha},
                "implementation": {
                    "os": platform.system(),
                    "kernel_release": platform.release(),
                    "python": platform.python_version(),
                    "python_implementation": platform.python_implementation(),
                },
                "platform_evidence": platform_evidence,
                "cpu_scripted": lease._cpu,
                "actual_authority": not lease._cpu,
                "formal_accepted": False,
            }
            self._journal = StepSpool(output / "raw-wall-checks.jsonl")
            self._journal.append("OWNER_START", self._startup)
        except Exception:
            _RECOVERY_WALL_OWNERS.pop(id(self), None)
            raise

    def __copy__(self) -> Any:
        raise TypeError("live recovery wall owner cannot be copied")

    def __deepcopy__(self, _memo: dict) -> Any:
        raise TypeError("live recovery wall owner cannot be copied")

    def __reduce__(self) -> Any:
        raise TypeError("live recovery wall owner cannot be pickled")

    def _plan_binding(self) -> dict:
        assignment = self._plan["row"]["assignment_id"]
        attempt = self._plan["attempt"]
        protocol_hash = self._plan["protocol_hash"]
        if (
            not isinstance(assignment, str)
            or not assignment
            or Path(assignment).name != assignment
            or type(attempt) is not int
            or not 1 <= attempt <= 5
            or not isinstance(protocol_hash, str)
            or len(protocol_hash) != 64
            or any(c not in "0123456789abcdef" for c in protocol_hash)
        ):
            raise ValueError("invalid recovery wall plan allocation identity")
        directory = Path(self._plan["allocation_directory"])
        _plain_path(directory)
        return {
            "assignment_id": assignment,
            "attempt": attempt,
            "protocol_hash": protocol_hash,
            "allocation_path": str((directory / f"{assignment}-attempt-{attempt}.json").resolve()),
            "output": str(self._output),
        }

    def _require_live(self) -> None:
        if _RECOVERY_WALL_OWNERS.get(id(self)) is not self or self._finished:
            raise ValueError("unregistered or finished live recovery wall owner")
        self._lease._require_live()
        if self._lease._identity != self._identity:
            raise ValueError("owner startup identity/lifecycle changed")
        if self._plan_binding() != self._binding:
            raise ValueError("recovery wall plan allocation identity changed")
        allocation = Path(self._binding["allocation_path"])
        _plain_path(allocation)
        if _hash(allocation) != self._allocation_sha:
            raise ValueError("canonical allocation bytes changed")

    def _counter(self) -> int:
        self._require_live()
        try:
            value = self._raw_read()
        except Exception as exc:
            raise BudgetExceeded("recovery wall counter read failed") from exc
        self._require_live()
        if type(value) is not int or value < 0:
            raise BudgetExceeded("recovery wall counter requires nonnegative integer ns")
        if self._last_ns is not None and value < self._last_ns:
            raise BudgetExceeded("recovery wall counter rollback/order violation")
        self._last_ns = value
        return cast(int, value)

    def _bind_backend(self, backend: object) -> None:
        """Private producer bind, once; BEGIN never binds from caller assertions."""
        self._require_live()
        if self._backend is not None or self._failure is not None:
            raise ValueError("recovery wall backend already bound or owner failed")
        self._backend = backend
        try:
            self._last_state = self._sample_state()
            self._episode = self._last_state["episode_id"]
            _RECOVERY_WALL_BACKENDS[id(self)] = (self, backend, cast(str, self._episode))
        except Exception as exc:
            self._remember_failure("BACKEND_BIND_FAILED", exc, {})
            raise

    @staticmethod
    def _valid_state(step: Any, sim_time_s: Any) -> None:
        if type(step) is not int or step < 0:
            raise ValueError("invalid source physics step")
        if type(sim_time_s) not in (int, float) or not math.isfinite(sim_time_s) or sim_time_s < 0:
            raise ValueError("invalid source sim state")

    def _sample_state(self) -> dict:
        self._require_live()
        if self._backend is None:
            raise ValueError("owned live backend must be privately bound before BEGIN")
        binding = _RECOVERY_WALL_BACKENDS.get(id(self))
        if binding is not None and (binding[0] is not self or binding[1] is not self._backend):
            raise ValueError("owner backend exact identity changed")
        episode = self._backend._episode_id
        if (
            not isinstance(episode, str)
            or not episode
            or (self._episode is not None and episode != self._episode)
        ):
            raise ValueError("owned backend episode missing or changed")
        step = self._backend.total_physics_steps
        sim_time_s = self._backend.get_sim_time()
        self._valid_state(step, sim_time_s)
        if self._backend._episode_id != episode:
            raise ValueError("owned backend episode changed during source sampling")
        if self._last_state is not None and (
            step < self._last_state["step"]
            or sim_time_s < self._last_state["sim_time_s"]
            or (step == self._last_state["step"] and sim_time_s != self._last_state["sim_time_s"])
        ):
            raise ValueError("owned source step/sim order changed")
        self._require_live()
        return {
            "episode_id": episode,
            "step": step,
            "sim_time_s": sim_time_s,
            "episode_source": "owned_live_backend._episode_id",
            "step_source": "owned_live_backend.total_physics_steps",
            "sim_time_source": "owned_live_backend.get_sim_time()",
        }

    def _source_records(self) -> list[dict]:
        try:
            rows = self._backend.fault_records
            if type(rows) is not list or any(type(row) is not dict for row in rows):
                raise ValueError("owned fault source must be a list of original dictionaries")
            result = deepcopy(rows)
            canonical_json(result)
            return cast(list[dict], result)
        except Exception as exc:
            raise ValueError("owned fault source read/type/payload invalid") from exc

    @staticmethod
    def _assert_state(state: dict, *, step: int, sim_time_s: float) -> None:
        _RecoveryWallOwner._valid_state(step, sim_time_s)
        if state["step"] != step:
            raise ValueError("caller step does not equal owned live source step")
        if state["sim_time_s"] != sim_time_s:
            raise ValueError("caller sim state does not equal owned live source sim state")

    def _remember_failure(self, kind: str, exc: Exception, payload: dict) -> None:
        if self._failure is None:
            self._failure = f"{type(exc).__name__}: {exc}"
        try:
            self._journal.append(kind, {"failure": str(exc), **_recovery_wall_evidence(payload)})
        except Exception as writer_exc:
            self._failure += f"; wall journal/spool failure: {writer_exc}"

    def begin_fault(
        self, *, backend: object, episode_id: str, step: int, sim_time_s: float
    ) -> None:
        self._require_live()
        payload: dict = {}
        try:
            if self._fault_begin is not None or self._failure is not None:
                raise ValueError("fault BEGIN already recorded or owner already failed")
            if backend is not self._backend:
                raise ValueError("caller backend is not the exact privately owned backend")
            lower = self._counter()
            state = self._sample_state()
            self._assert_state(state, step=step, sim_time_s=sim_time_s)
            if episode_id != state["episode_id"]:
                raise ValueError("caller episode assertion does not equal live backend episode")
            rows = self._source_records()
            if self._sample_state() != state:
                raise ValueError("source step/sim/episode changed before BEGIN")
            payload = {
                **state,
                "lower_ns": lower,
                "deadline_ns": lower + _RECOVERY_WALL_NS,
                "source_length": len(rows),
                "source_prefix": rows,
                "event_source": "owned_backend.fault_records",
            }
            # The exclusive fsynced BEGIN is durable before this method returns,
            # therefore before its caller may perform the single real injection.
            _write(self._output / "wall-start.json", {**self._startup, "fault_begin": payload})
            self._fault_begin = deepcopy(payload)
            self._fault_prefix = rows
            self._last_state = state
            self._journal.append("FAULT_BEGIN", payload)
        except Exception as exc:
            self._remember_failure("FAULT_BEGIN_FAILED", exc, payload)
            raise

    def end_fault_injection(self, *, step: int, sim_time_s: float) -> None:
        self._require_live()
        payload: dict = {}
        try:
            if self._failure is not None or self._fault_end is not None:
                raise ValueError("fault END already recorded or owner already failed")
            if self._fault_begin is None or self._fault_prefix is None:
                raise ValueError("fault END requires durable BEGIN")
            state = self._sample_state()
            self._assert_state(state, step=step, sim_time_s=sim_time_s)
            begin = self._fault_begin
            if any(state[key] != begin[key] for key in ("episode_id", "step", "sim_time_s")):
                raise ValueError("synchronous fault END live source step/sim/episode changed")
            rows = self._source_records()
            payload = {"source_records": rows, "end_source_state": state}
            size = begin["source_length"]
            if canonical_json(rows[:size]) != canonical_json(self._fault_prefix):
                raise ValueError("owned fault source prefix mutated/truncated/reset")
            if len(rows) != size + 1:
                raise ValueError(
                    "owned fault source requires exactly one fresh event at BEGIN ordinal"
                )
            event = rows[size]
            if event.get("event") != "TARGET_MOTION_STARTED":
                raise ValueError("fresh source event is not TARGET_MOTION_STARTED")
            if any(canonical_json(event) == canonical_json(old) for old in self._fault_prefix):
                raise ValueError("replayed original source event payload")
            self._valid_state(event.get("physics_step"), event.get("sim_time_s"))
            if event["physics_step"] != state["step"] or event["sim_time_s"] != state["sim_time_s"]:
                raise ValueError("original source event step/sim mismatch")
            if self._sample_state() != state:
                raise ValueError("owned source step/sim/episode changed during END")
            upper = self._counter()
            if upper >= begin["deadline_ns"]:
                raise BudgetExceeded("recovery wall fixed deadline reached at fault END")
            payload = {
                **state,
                "upper_ns": upper,
                "event_ordinal": size,
                "event": event,
                "event_source": "owned_backend.fault_records",
            }
            self._journal.append("FAULT_END", payload)
            self._fault_end = deepcopy(payload)
            self._last_state = state
        except Exception as exc:
            self._remember_failure("FAULT_END_FAILED", exc, payload)
            raise

    def _current(self, kind: str, *, step: int, sim_time_s: float) -> dict:
        payload: dict = {"kind": kind}
        try:
            self._require_live()
            payload["lower_ns"] = self._counter()
            state = self._sample_state()
            payload.update(state)
            self._assert_state(state, step=step, sim_time_s=sim_time_s)
            payload["upper_ns"] = self._counter()
            self._require_live()
            if self._fault_begin is not None:
                payload["age_upper_ns"] = payload["upper_ns"] - self._fault_begin["lower_ns"]
                if payload["upper_ns"] >= self._fault_begin["deadline_ns"]:
                    raise BudgetExceeded("recovery wall fixed deadline reached")
            self._journal.append("CHECK", payload)
            self._last_state = state
            return payload
        except Exception as exc:
            self._remember_failure("CHECK_FAILED", exc, payload)
            raise

    def check(self, kind: str, *, step: int, sim_time_s: float) -> None:
        self._require_live()
        if self._failure is not None:
            raise BudgetExceeded("recovery wall owner already failed")
        self._current(kind, step=step, sim_time_s=sim_time_s)

    def finish(self, *, step: int, sim_time_s: float, failure: str | None) -> dict:
        # Identity drift must still permit a failed offline terminal to preserve
        # the original BEGIN and journal. It never authorizes another live call.
        if _RECOVERY_WALL_OWNERS.get(id(self)) is not self or self._finished:
            raise ValueError("live recovery wall owner already finished or foreign")
        terminal = None
        if failure is not None:
            self._remember_failure("EXECUTION_FAILED", RuntimeError(failure), {})
        try:
            terminal = self._current("TERMINAL", step=step, sim_time_s=sim_time_s)
        except Exception:
            pass  # _current retained the exact failure and partial observation.
        if self._fault_begin is None or self._fault_end is None:
            self._remember_failure("INCOMPLETE", ValueError("missing fault BEGIN/END pair"), {})
        try:
            self._journal.append("FINISH", {"failure": self._failure, "terminal": terminal})
            self._journal.close()
        except Exception as exc:
            self._remember_failure("JOURNAL_FAILED", exc, {})
            try:
                self._journal.close()
            except Exception:
                pass
        result = {
            "schema_version": "r07.recovery-wall.terminal.v1",
            **self._startup,
            "status": "PASS"
            if self._failure is None
            else (
                "INCOMPLETE" if self._fault_begin is None or self._fault_end is None else "FAILED"
            ),
            "wall_pass": self._failure is None and terminal is not None,
            "failure": self._failure,
            "deadline_ns": self._fault_begin["deadline_ns"] if self._fault_begin else None,
            "fault_begin": self._fault_begin,
            "fault_end": self._fault_end,
            "terminal": terminal,
            "journal_sha256": _hash(self._output / "raw-wall-checks.jsonl"),
            "start_sha256": _hash(self._output / "wall-start.json") if self._fault_begin else None,
            "formal_wall_accepted": False,
            "g4_measured": False,
        }
        try:
            _write(self._output / "wall-terminal.json", result)
        finally:
            self._finished = True
            _RECOVERY_WALL_OWNERS.pop(id(self), None)
            _RECOVERY_WALL_BACKENDS.pop(id(self), None)
            if self._lease._cpu:
                _RECOVERY_WALL_LEASES.pop(id(self._lease), None)
        return result


def _open_recovery_wall_owner(
    plan: dict, output: Path, *, renderer_lease: object
) -> _RecoveryWallOwner:
    """Production has no caller clock/domain/seconds parameter or CPU authority."""
    lease = _recovery_wall_lease(renderer_lease, production=True)
    raw_read = _recovery_wall_boottime_reader()
    evidence = _RECOVERY_WALL_PLATFORM_EVIDENCE
    _plain_path(evidence)
    if _hash(evidence) != _RECOVERY_WALL_PLATFORM_SHA:
        raise ValueError("frozen local BOOTTIME platform semantics evidence missing or changed")
    record = _read(evidence)
    if (
        not record["boottime_semantics_documented_locally"]
        or not record["capability"]["supported_now"]
    ):
        raise ValueError("local BOOTTIME semantics/capability actual prerequisite unmet")
    return _RecoveryWallOwner(
        _RECOVERY_WALL_FACTORY_KEY,
        plan,
        output,
        lease=lease,
        raw_read=raw_read,
        platform_evidence={
            "path": str(evidence),
            "sha256": _RECOVERY_WALL_PLATFORM_SHA,
            "suspend_restart_hostpause_actual": "NOT_TESTED",
        },
    )


def _open_recovery_wall_owner_for_test(
    plan: dict,
    output: Path,
    *,
    backend: object,
    raw_read: Callable[[], Any],
    identity_read: Callable[[], dict],
) -> _RecoveryWallOwner:
    """Private CPU seam: scripted raw reads, real validation, no production lease."""
    lease = _RecoveryWallRendererLease(
        _RECOVERY_WALL_FACTORY_KEY, handle=None, identity_read=identity_read, cpu=True
    )
    try:
        owner = _RecoveryWallOwner(
            _RECOVERY_WALL_FACTORY_KEY,
            plan,
            output,
            lease=lease,
            raw_read=raw_read,
            platform_evidence={"CPU_ONLY": True, "actual_platform_probe": False},
        )
        owner._bind_backend(backend)
        return owner
    except Exception:
        _RECOVERY_WALL_LEASES.pop(id(lease), None)
        raise


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
        lease = None
        try:
            global _RECOVERY_WALL_STARTUP_IDENTITY
            identity = _recovery_wall_process_identity()
            if _RECOVERY_WALL_STARTUP_IDENTITY is None:
                _RECOVERY_WALL_STARTUP_IDENTITY = deepcopy(identity)
            if identity != _RECOVERY_WALL_STARTUP_IDENTITY:
                raise ValueError("renderer context startup process identity changed")
            lease = _RecoveryWallRendererLease(
                _RECOVERY_WALL_FACTORY_KEY,
                handle=handle,
                identity_read=_recovery_wall_process_identity,
                cpu=False,
            )
            yield lease
        finally:
            if lease is not None:
                _RECOVERY_WALL_LEASES.pop(id(lease), None)
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
    allocations = Path(plan["allocation_directory"])
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
                output / "source",
                plan["row"],
                plan["fault"],
                _read(Path(plan["input_directory"]) / "recipe.json"),
            )
            # The verified full trace begins at reset/time0, so elapsed is the
            # terminal timestamp, not duration since the recovery lift baseline.
            if proof["independent_outcome"]["elapsed_s"] - proof["injection_start_s"] > 60.0:
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
