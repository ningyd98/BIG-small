"""固定七案的开发接口验证；原始证据本地保存，不派发硬件。"""

# ruff: noqa: E402
from __future__ import annotations

import argparse
import base64
import copy
import fcntl
import hashlib
import json
import os
import sys
import uuid
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from cloud_edge_robot_arm.cloud.planning.models import (
    InitialPlanningRequest,
    InitialPlanningResponse,
    RobotCapabilities,
    SceneSummary,
)
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec
from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import COLORS
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession
from cloud_edge_robot_arm.vision.grounded_planner import (
    GroundingTaskDescriptor,
    build_molmo_grounded_planner,
)
from cloud_edge_robot_arm.vision.molmo_pointing import MolmoPointProvider
from cloud_edge_robot_arm.vision.role_models import cloud_request_settings, configuration_hash
from scripts.probe_molmo_grounded_planner import _admit_resources, _save_capture

ROUND = ROOT / (
    "artifacts/research/process/20261004-ced-development/astra-rounds/"
    "round558-multiscene-grounded-interface-20261110"
)
GROUPS = {"G1": ("N01", "N02", "P01"), "G2": ("N03", "P02"), "G3": ("N04", "P03")}
CAPS = {"G1": 8, "G2": 6, "G3": 6}
SETTINGS_SHA = "eb31dd5eb394646e1a09a0116c7d8d58c954a8c200f2443d12b5ce3ef972362d"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(_canonical(value))
        stream.flush()
        os.fsync(stream.fileno())
    descriptor = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _stamp() -> dict[str, Any]:
    return {"utc": datetime.now(UTC).isoformat(), "monotonic_s": monotonic()}


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    group_id: str
    expected: Literal["positive", "negative"]
    scene: SceneSpec
    task: GroundingTaskDescriptor
    request_id: str
    point_cap: int
    paid_cap: int

    def payload(self) -> dict[str, Any]:
        return {
            **{
                name: getattr(self, name)
                for name in (
                    "case_id",
                    "group_id",
                    "expected",
                    "request_id",
                    "point_cap",
                    "paid_cap",
                )
            },
            "scene": self.scene.model_dump(mode="json"),
            "task": self.task.model_dump(mode="json"),
        }

    @classmethod
    def read(cls, value: dict[str, Any]) -> CaseSpec:
        value = dict(value)
        value["scene"] = SceneSpec.model_validate(value["scene"])
        value["task"] = GroundingTaskDescriptor.model_validate(value["task"])
        return cls(**value)


def build_cases(asset_sha256: str) -> tuple[CaseSpec, ...]:
    """在渲染和模型访问前固定所有场景及显式任务。"""
    if len(asset_sha256) != 64 or any(c not in "0123456789abcdef" for c in asset_sha256):
        raise ValueError("invalid asset identity")

    def box(color: str, position: list[float], size=None):
        return {
            "position": position,
            "half_size": size or [0.035, 0.035, 0.035],
            "rgba": COLORS[color].copy(),
            "color_name": color,
            "mass_kg": 0.08,
            "friction": 1.0,
        }

    def scene(color, target, destination):
        return {
            "target": box(color, target),
            "distractors": [],
            "destination": {
                "position": destination,
                "half_size": [0.08, 0.08, 0.002],
                "rgba": [0.1, 0.6, 0.2, 1],
            },
            "camera": {"position": [0.35, 0, 1.4], "quaternion": [1, 0, 0, 0], "fovy": 50},
            "light_intensity": 0.9,
            "depth_noise_m": 0.0,
            "invalid_depth_fraction": 0.0,
        }

    nominal = scene("red", [0.45, 0, 0.035], [0.20, 0.25, 0.002])
    shifted = scene("red", [0.36, -0.16, 0.035], [0.18, 0.18, 0.002])
    blue = scene("blue", [0.52, 0.12, 0.035], [0.20, 0.25, 0.002])
    parameters = {
        "P01": nominal,
        "P02": shifted,
        "P03": blue,
        "N01": copy.deepcopy(nominal),
        "N02": copy.deepcopy(nominal),
        "N03": copy.deepcopy(shifted),
        "N04": copy.deepcopy(blue),
    }
    parameters["N02"]["distractors"] = [box("red", [0.62, -0.12, 0.035])]
    parameters["N03"]["destination"]["rgba"] = [0.5, 0.5, 0.5, 1]
    parameters["N04"]["distractors"] = [box("yellow", [0.55, 0.145, 0.12], [0.025, 0.025, 0.045])]
    colors = {
        "P01": "red",
        "P02": "red",
        "P03": "blue",
        "N01": "blue",
        "N02": "red",
        "N03": "red",
        "N04": "blue",
    }
    result = []
    for group, ids in GROUPS.items():
        for name in ids:
            color = colors[name]
            task = GroundingTaskDescriptor(
                instruction=f"Move the {color} block to the green region.",
                target_phrase=f"{color} block",
                destination_phrase="green region",
                target_label=f"{color} block",
            )
            positive = name.startswith("P")
            result.append(
                CaseSpec(
                    name,
                    group,
                    "positive" if positive else "negative",
                    SceneSpec.from_parameters(parameters[name], asset_sha256, 0),
                    task,
                    f"r558-{name.lower()}",
                    4 if positive else 2,
                    int(positive),
                )
            )
    return tuple(result)


def preregister(
    output: Path, cases: tuple[CaseSpec, ...], source_hashes: dict[str, str]
) -> dict[str, Any]:
    """独占登记整个分母，目录及登记均不可覆盖。"""
    output.mkdir(parents=True, exist_ok=False)
    rows = [case.payload() for case in cases]
    expected = [name for ids in GROUPS.values() for name in ids]
    if [row["case_id"] for row in rows] != expected:
        raise ValueError("registry must contain the fixed seven ordered cases")
    registry = {
        "schema": "molmo.interface.r558.v2",
        "raw_root": str(output.resolve()),
        "root_id": uuid.uuid4().hex,
        "cases": rows,
        "groups": {g: {"cases": list(ids), "point_cap": CAPS[g]} for g, ids in GROUPS.items()},
        "source_hashes": source_hashes,
        "prior": {"loads": 4, "generations": 10, "paid": 2},
        "additional_max": {"loads": 3, "generations": 20, "paid": 3},
        "retries": 0,
        "hardware_dispatch": False,
        "physical_formal": "NOT_RUN",
        "sensor_noise": "existing apply_scene clean raw path, 0m; no offline perturbation",
    }
    _write(output / "registry.json", registry)
    _write(output / "registry.sha256", {"sha256": _sha(output / "registry.json")})
    for directory in ["claims", "reservations", "events"]:
        (output / directory).mkdir()
    (output / "ledger.lock").touch(exist_ok=False)
    (output / "group.lock").touch(exist_ok=False)
    return registry


EVENT_SCHEMA = "molmo.interface.event.v2"
CASE_MANIFEST = "case-evidence.manifest.json"
REPAIR = ROUND.parent / "round561-multiscene-evidence-repair-20261111"
NATIVE_FILES = (
    "started.json",
    "prompt.txt",
    "processor.json",
    "input-token-ids.json",
    "generation-started.json",
    "generation-completed.json",
    "output-token-ids.json",
    "raw-response.txt",
    "result.json",
)
STAGE_FILES = {
    "association": "src/cloud_edge_robot_arm/vision/point_association.py",
    "grounding": "src/cloud_edge_robot_arm/vision/planner.py",
    "tracker": "src/cloud_edge_robot_arm/vision/tracking.py",
}


class LedgerPoisoned(RuntimeError):
    """现有组已失去继续委托资格。"""


class EvidenceError(ValueError):
    """原件身份、闭合或完整性不成立。"""


def _require(value, reason):
    if not value:
        raise EvidenceError(reason)


def _read(path):
    return json.loads(path.read_bytes())


def _safe_path(root, relative):
    relative = Path(relative)
    _require(not relative.is_absolute() and ".." not in relative.parts, "unsafe raw path")
    path = root / relative
    _require(path.resolve().is_relative_to(root.resolve()), "raw path escapes root")
    _require(
        not any(p.is_symlink() for p in [path, *path.parents] if p != root.parent), "raw symlink"
    )
    return path


def _ref(root, path):
    path = _safe_path(root, path.relative_to(root))
    return {"path": str(path.relative_to(root)), "bytes": path.stat().st_size, "sha256": _sha(path)}


def _verify_ref(root, row):
    _require(set(row) == {"path", "bytes", "sha256"}, "invalid raw reference")
    path = _safe_path(root, row["path"])
    _require(
        path.is_file() and path.stat().st_size == row["bytes"] and _sha(path) == row["sha256"],
        f"raw missing or changed:{row['path']}",
    )
    return path


def _tree(root, folder):
    return [
        _ref(root, p)
        for p in sorted(folder.rglob("*"))
        if p.is_file() and "runtime-cache" not in p.relative_to(root).parts
    ]


def _registry_check(root, registry):
    _require(
        root.is_dir() and str(root.resolve()) == registry["raw_root"], "registry root mismatch"
    )
    _require(
        _canonical(registry) == (root / "registry.json").read_bytes(), "registry bytes mismatch"
    )
    _require(
        _read(root / "registry.sha256") == {"sha256": _sha(root / "registry.json")},
        "registry seal mismatch",
    )
    assigned = registry["cases"]
    asset = assigned[0]["scene"]["asset_family_hash"]
    _require(
        _canonical(assigned) == _canonical([c.payload() for c in build_cases(asset)]),
        "fixed case matrix changed",
    )
    _require(
        registry["additional_max"] == {"loads": 3, "generations": 20, "paid": 3},
        "allocation changed",
    )
    _require(registry["schema"] == "molmo.interface.r558.v2", "registry schema")
    _require(
        _canonical(registry["groups"])
        == _canonical({g: {"cases": list(ids), "point_cap": CAPS[g]} for g, ids in GROUPS.items()}),
        "group matrix changed",
    )
    _require(
        _canonical(registry["prior"]) == _canonical({"loads": 4, "generations": 10, "paid": 2})
        and type(registry["retries"]) is int
        and registry["retries"] == 0
        and registry["hardware_dispatch"] is False
        and registry["physical_formal"] == "NOT_RUN",
        "run boundary changed",
    )
    known_cases = {c["case_id"] for c in assigned}
    known_claims = {f"group-{g}.json" for g in GROUPS} | {
        f"case-{c}-{phase}.json" for c in known_cases for phase in ("start", "end")
    }
    _require(
        all(
            p.name in known_claims and p.is_file() and not p.is_symlink()
            for p in (root / "claims").iterdir()
        ),
        "unknown claim namespace",
    )
    for folder in (root / "events").iterdir():
        _require(
            folder.name in known_cases | {f"_{g}" for g in GROUPS}
            and folder.is_dir()
            and not folder.is_symlink(),
            "unknown event namespace",
        )
        _require(
            all(
                p.name == f"{i:04}.json" and p.is_file() and not p.is_symlink()
                for i, p in enumerate(sorted(folder.iterdir()), 1)
            ),
            "event filename sequence/type",
        )
    _require(
        all(
            p.name in GROUPS and p.is_dir() and not p.is_symlink()
            for p in root.iterdir()
            if p.name.startswith("G")
        ),
        "unknown group namespace",
    )
    _reservations(root, registry)
    for name, digest in registry["source_hashes"].items():
        path = (ROOT / name).resolve()
        _require(path.is_relative_to(ROOT) and _sha(path) == digest, "registered source changed")


def _identity(root, registry, group, case=None):
    return {
        "root_id": registry["root_id"],
        "registry_sha256": _sha(root / "registry.json"),
        "group_id": group,
        "case_id": case.case_id if case else None,
        "request_id": case.request_id if case else None,
    }


def _reservations(root, registry):
    result = []
    for kind in ("load", "point", "paid"):
        paths = sorted((root / "reservations").glob(f"{kind}-*.json"))
        for index, path in enumerate(paths, 1):
            _require(path.is_file() and not path.is_symlink(), "reservation file type")
            row = _read(path)
            _require(
                path.name == f"{kind}-{index:03}.json" and row["kind"] == kind,
                "reservation sequence",
            )
            group = row["group_id"]
            _require(
                group in GROUPS
                and row["root_id"] == registry["root_id"]
                and row["registry_sha256"] == _sha(root / "registry.json"),
                "reservation identity",
            )
            _require(
                (kind == "load" and row["case_id"] is None)
                or (kind != "load" and row["case_id"] in GROUPS[group]),
                "reservation membership",
            )
            result.append((path, row))
        _require(len(paths) <= {"load": 3, "point": 20, "paid": 3}[kind], "global reservation cap")
    _require(
        {p for p, _ in result} == set((root / "reservations").iterdir()),
        "unknown reservation namespace",
    )
    for group, ids in GROUPS.items():
        grouped = [r for _, r in result if r["group_id"] == group]
        _require(
            all(
                sum(r["kind"] == kind for r in grouped) <= cap
                for kind, cap in (("load", 1), ("point", CAPS[group]), ("paid", 1))
            ),
            "group reservation cap",
        )
        for case in registry["cases"]:
            if case["case_id"] in ids:
                _require(
                    all(
                        sum(r["kind"] == kind and r["case_id"] == case["case_id"] for r in grouped)
                        <= case[field]
                        for kind, field in (("point", "point_cap"), ("paid", "paid_cap"))
                    ),
                    "case reservation cap",
                )
    for _, row in result:
        expected_request = next(
            (c["request_id"] for c in registry["cases"] if c["case_id"] == row["case_id"]), None
        )
        _require(row["request_id"] == expected_request, "reservation request identity")
    return result


class RunLedger:
    """持久化故障先poison，调用预留不可回收，终态只关闭已开始操作。"""

    def __init__(self, output: Path, registry: dict[str, Any]):
        self.output, self.registry = output, registry
        self.fatal, self.stop_reason = False, None
        self.group_id, self._group_lock = None, None
        self.terminal_errors, self._open_ops = [], {}
        self.cases = {row["case_id"]: row for row in registry["cases"]}
        self._io("registry", lambda: _registry_check(output, registry))

    def poison(self, reason: str) -> None:
        if not self.fatal:
            self.fatal, self.stop_reason = True, reason
            try:
                _write(
                    self.output / f"fatal-{self.group_id or 'unclaimed'}.json",
                    {"reason": reason, "group_id": self.group_id, **_stamp()},
                )
            except BaseException as exc:
                self.terminal_errors.append(type(exc).__name__)

    def _io(self, operation, action):
        try:
            return action()
        except BaseException as exc:
            self.poison(f"{operation}:{type(exc).__name__}")
            raise

    def _alive(self):
        if self.fatal:
            raise LedgerPoisoned(self.stop_reason)

    @contextmanager
    def locked(self):
        stream = self._io("lock.open", lambda: (self.output / "ledger.lock").open("r+"))
        try:
            self._io("lock.flock", lambda: fcntl.flock(stream, fcntl.LOCK_EX))
            yield
        finally:
            try:
                self._io("lock.unlock", lambda: fcntl.flock(stream, fcntl.LOCK_UN))
            finally:
                self._io("ledger.lock.close", stream.close)

    def claim(self, group_id):
        self._alive()
        if group_id not in GROUPS or self._group_lock is not None:
            raise ValueError("invalid group claim")
        stream = self._io("group.lock.open", lambda: (self.output / "group.lock").open("r+"))
        try:
            self._io("group.lock.flock", lambda: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB))
            with self.locked():
                path = self.output / "claims" / f"group-{group_id}.json"
                if self._io("claim.exists", path.exists):
                    raise ValueError("group already claimed; no restart")
                earlier = list(GROUPS)[: list(GROUPS).index(group_id)]
                if self._io(
                    "claim.order",
                    lambda: any(
                        not (self.output / "claims" / f"group-{g}.json").exists() for g in earlier
                    ),
                ):
                    raise ValueError("group order violation")
                self._io(
                    "claim.write",
                    lambda: _write(
                        path,
                        _identity(self.output, self.registry, group_id)
                        | {"pid": os.getpid(), **_stamp()},
                    ),
                )
            self._group_lock, self.group_id = stream, group_id
        except BaseException:
            stream.close()
            raise

    def close(self):
        if self._group_lock is not None:
            stream = self._group_lock
            self._group_lock = None
            self._io("group.lock.close", stream.close)

    def _case_path(self, case_id, phase):
        return self.output / "claims" / f"case-{case_id}-{phase}.json"

    def begin_case(self, group_id, case_id):
        self._alive()
        with self.locked():
            if group_id != self.group_id or case_id not in GROUPS[group_id]:
                raise ValueError("case/group mismatch")
            earlier = GROUPS[group_id][: GROUPS[group_id].index(case_id)]
            if self._io(
                "case.order", lambda: any(not self._case_path(n, "end").exists() for n in earlier)
            ):
                raise ValueError("case order violation")
            case = CaseSpec.read(self.cases[case_id])
            self._io(
                "case.begin",
                lambda: _write(
                    self._case_path(case_id, "start"),
                    _identity(self.output, self.registry, group_id, case)
                    | {"phase": "start", **_stamp()},
                ),
            )

    def end_case(self, group_id, case_id):
        if group_id != self.group_id or not self._io(
            "case.exists", lambda: self._case_path(case_id, "start").exists()
        ):
            raise ValueError("case not started")
        case = CaseSpec.read(self.cases[case_id])
        self._io(
            "case.end",
            lambda: _write(
                self._case_path(case_id, "end"),
                _identity(self.output, self.registry, group_id, case)
                | {"phase": "end", **_stamp()},
            ),
        )

    def reserve(self, kind, *, group_id, case_id):
        self._alive()
        with self.locked():
            if group_id != self.group_id or kind not in {"load", "point", "paid"}:
                raise ValueError("invalid reservation")
            if kind == "load":
                if case_id is not None:
                    raise ValueError("load is group scoped")
                cap, case_cap, total = 1, 1, 3
            else:
                if case_id not in GROUPS[group_id] or not self._io(
                    "case.active",
                    lambda: self._case_path(case_id, "start").exists()
                    and not self._case_path(case_id, "end").exists(),
                ):
                    raise ValueError("inactive case reservation")
                cap, case_cap, total = (
                    (CAPS[group_id], self.cases[case_id]["point_cap"], 20)
                    if kind == "point"
                    else (1, self.cases[case_id]["paid_cap"], 3)
                )
            all_rows = self._io(
                "reservations.read", lambda: _reservations(self.output, self.registry)
            )
            rows = [r for _, r in all_rows if r["kind"] == kind]
            if (
                len(rows) >= total
                or sum(r["group_id"] == group_id for r in rows) >= cap
                or sum(r["group_id"] == group_id and r["case_id"] == case_id for r in rows)
                >= case_cap
            ):
                raise ValueError("reservation allocation exhausted")
            path = self.output / "reservations" / f"{kind}-{len(rows) + 1:03}.json"
            case = CaseSpec.read(self.cases[case_id]) if case_id else None
            self._io(
                "reservation.write",
                lambda: _write(
                    path,
                    _identity(self.output, self.registry, group_id, case)
                    | {"kind": kind, **_stamp()},
                ),
            )
            return path

    def record(self, case_id, **event):
        phase = event.get("phase", "notice")
        if phase == "start" or event.get("kind") == "cloud_entry":
            self._alive()
        folder = self.output / "events" / (case_id or f"_{self.group_id}")

        def persist():
            folder.mkdir(exist_ok=True)
            paths = sorted(folder.glob("*.json"))
            case = CaseSpec.read(self.cases[case_id]) if case_id else None
            row = {
                "schema": EVENT_SCHEMA,
                **_identity(self.output, self.registry, self.group_id, case),
                "seq": len(paths) + 1,
                "op_id": uuid.uuid4().hex,
                "parent_op_id": None,
                "reservation_id": None,
                "raw_refs": [],
                **_stamp(),
                **event,
                "phase": phase,
            }
            _write(folder / f"{len(paths) + 1:04}.json", row)
            return row

        return self._io("event.persist", persist)

    def start(self, kind, case_id, *, parent=None, reservation=None, **fields):
        self._alive()
        op = uuid.uuid4().hex
        common = {
            "kind": kind,
            "op_id": op,
            "parent_op_id": parent,
            "reservation_id": str(reservation.relative_to(self.output)) if reservation else None,
        }
        self.record(case_id, phase="start", **common, **fields)
        self._open_ops[op] = common | {"case_id": case_id}
        return op

    def end(self, op, *, error=None, **fields):
        common = dict(self._open_ops[op])
        case_id = common.pop("case_id")
        terminal = {
            "outcome": "error" if error else "success",
            "error_type": f"{type(error).__module__}.{type(error).__qualname__}" if error else None,
            "error_message": str(error) if error else None,
            "counters_before": None,
            "counters_after": None,
            "started_delta": None,
            "completed_delta": None,
        } | fields
        self.record(case_id, phase="end", **common, **terminal)
        del self._open_ops[op]

    def events_for(self, case_id):
        def collect():
            folder = self.output / "events" / (case_id or f"_{self.group_id}")
            return [_read(p) for p in sorted(folder.glob("*.json"))]

        return self._io("events.read", collect)


def _read_events(root, folder):
    return [_read(p) for p in sorted((root / "events" / folder).glob("*.json"))]


def _counts(events, reservations=()):
    points = [e for e in events if e["kind"] == "point" and e["phase"] == "end"]
    starts = [e for e in events if e["kind"] == "point" and e["phase"] == "start"]
    paid = [e for e in events if e["kind"] == "paid" and e["phase"] == "end"]
    unknown = len(points) != len(starts) or any(
        e.get("started_delta") is None or e.get("completed_delta") is None for e in points
    )
    return {
        "actual_generations": None if unknown else sum(e["started_delta"] for e in points),
        "actual_generations_completed": None
        if unknown
        else sum(e["completed_delta"] for e in points),
        "native_unknown": int(unknown),
        "point_statuses": [e.get("status") for e in points],
        "capture_count": sum(
            e["kind"] == "capture" and e["phase"] == "end" and e["outcome"] == "success"
            for e in events
        ),
        "paid_responses": sum(e.get("response_observed", 0) for e in paid),
        "paid": {
            "reserved": sum(r["kind"] == "paid" for _, r in reservations),
            **{
                key: sum(e.get(key, 0) for e in paid)
                for key in (
                    "delegated_post",
                    "request_observed",
                    "response_observed",
                    "parsed_success",
                )
            },
            "transmission_state": [e.get("transmission_state", "UNKNOWN") for e in paid],
        },
    }


@dataclass
class EvidenceCheck:
    ok: bool
    errors: list[str]
    counts: dict[str, Any]
    refusal_source: str | None = None


def _event_check(root, registry, group_id, case, events):
    expected = _identity(root, registry, group_id, case)
    opened, ended, notices = {}, {}, set()
    for index, e in enumerate(events, 1):
        _require(
            e["schema"] == EVENT_SCHEMA
            and e["seq"] == index
            and all(e[k] == v for k, v in expected.items()),
            "event identity/sequence",
        )
        _require(e["phase"] in {"start", "end", "notice"}, "event phase")
        for row in e["raw_refs"]:
            _verify_ref(root, row)
        op = e["op_id"]
        if e["phase"] == "notice":
            _require(
                e["kind"] in {"cloud_entry", "runtime_error", "budget_block", "fatal"}
                and op not in notices
                and op not in opened,
                "unknown/duplicate notice",
            )
            notices.add(op)
            continue
        _require(
            e["kind"] in {"load", "capture", "point", "stage", "paid", "pipeline"},
            "unknown operation",
        )
        if e["phase"] == "start":
            _require(op not in opened and op not in notices, "duplicate start")
            opened[op] = e
        else:
            _require(op in opened and op not in ended, "unmatched/duplicate end")
            start = opened[op]
            _require(
                all(e[k] == start[k] for k in ("kind", "parent_op_id", "reservation_id"))
                and e["monotonic_s"] >= start["monotonic_s"]
                and e["utc"] >= start["utc"],
                "terminal identity/order",
            )
            _require(e["outcome"] in {"success", "error", "not_delegated"}, "terminal outcome")
            ended[op] = e
        if e["kind"] in {"load", "point", "paid"}:
            path = _safe_path(root, e["reservation_id"])
            row = _read(path)
            _require(
                row["kind"] == e["kind"]
                and row["group_id"] == group_id
                and row["case_id"] == expected["case_id"],
                "reservation binding",
            )
        else:
            _require(e["reservation_id"] is None, "unexpected reservation")
    _require(set(opened) == set(ended), "operation not closed")
    for op, start in opened.items():
        parent = start["parent_op_id"]
        if parent:
            _require(
                parent in opened
                and opened[parent]["kind"] == "pipeline"
                and opened[parent]["monotonic_s"]
                <= start["monotonic_s"]
                <= ended[op]["monotonic_s"]
                <= ended[parent]["monotonic_s"],
                "operation parent/order",
            )
    return opened, ended


def _case_paths(root, case, events, response_received):
    folder = root / case.group_id / case.case_id
    paths = {
        folder / "task.json",
        folder / "scene-setup.json",
        folder / ("pipeline-return.json" if response_received else "case-error.json"),
        root / "claims" / f"group-{case.group_id}.json",
        root / "claims" / f"case-{case.case_id}-start.json",
        root / "claims" / f"case-{case.case_id}-end.json",
        root / "registry.json",
        root / "registry.sha256",
    }
    paths.update((root / "events" / case.case_id).glob("*.json"))
    for event in events:
        if event.get("reservation_id"):
            paths.add(_safe_path(root, event["reservation_id"]))
        paths.update(_safe_path(root, r["path"]) for r in event["raw_refs"])
        if event["kind"] == "capture" and event["phase"] == "end" and event["outcome"] == "success":
            paths.update(
                folder / f"capture-{event['capture_index']:02}" / n
                for n in ("request.json", "rgb.png", "depth.f32", "valid_mask.u8")
            )
        if event["kind"] == "point" and event["phase"] == "end" and event.get("native_directory"):
            native = _safe_path(root, event["native_directory"])
            names = (
                NATIVE_FILES if event["outcome"] == "success" else ("started.json", "failure.json")
            )
            paths.update(native / n for n in names)
    return paths


def _seal_case(ledger, case, response_received):
    events = ledger.events_for(case.case_id)

    def seal():
        refs = [
            _ref(ledger.output, p)
            for p in sorted(_case_paths(ledger.output, case, events, response_received))
        ]
        folder = ledger.output / case.group_id / case.case_id
        _write(
            folder / CASE_MANIFEST,
            {
                "schema": "molmo.interface.case.v2",
                **_identity(ledger.output, ledger.registry, case.group_id, case),
                "response_received": response_received,
                "files": refs,
            },
        )

    ledger._io("case.manifest", seal)


def _fresh_at(observation, stamp):
    age = (datetime.fromisoformat(stamp) - observation.captured_at).total_seconds()
    _require(-0.05 <= age <= 5.0, "recorded frame not fresh")


def _manifest_check(root, registry, path, identity, expected):
    manifest = _read(path)
    _require(
        manifest["schema"]
        == (
            "molmo.interface.case.v2" if path.name == CASE_MANIFEST else "molmo.interface.group.v2"
        ),
        "manifest schema",
    )
    _require(all(manifest[k] == v for k, v in identity.items()), "manifest identity")
    refs = manifest["files"]
    paths = [str(_verify_ref(root, row).relative_to(root)) for row in refs]
    _require(
        len(paths) == len(set(paths))
        and set(paths) == {str(p.relative_to(root)) for p in expected},
        "manifest required set mismatch",
    )
    return manifest


def _native_check(root, case, start, end, observation):
    from dataclasses import asdict

    from cloud_edge_robot_arm.vision.molmo_pointing import (
        MODEL_ID,
        NativePointResult,
        native_prompt,
        parse_native_point,
    )

    _require(end["counters_before"] == start["counters_before"], "native before counters changed")
    before, after = end["counters_before"], end["counters_after"]
    _require(isinstance(before, dict) and isinstance(after, dict), "native counters unknown")
    _require(
        all(type(v) is int and v >= 0 for row in (before, after) for v in row.values()),
        "native counters invalid",
    )
    ds, dc = after["started"] - before["started"], after["completed"] - before["completed"]
    _require(
        ds == end["started_delta"]
        and dc == end["completed_delta"]
        and ds in {0, 1}
        and dc in {0, 1}
        and after["completed"] <= after["started"],
        "native counter delta",
    )
    directory = _safe_path(root, end["native_directory"])
    _require(
        directory.parent == root / case.group_id / "native"
        and directory.name.startswith("request-"),
        "native directory binding",
    )
    binding = {
        "observation_checksum": observation.checksum_sha256,
        "rgb_sha256": observation.evidence()["rgb_sha256"],
        "query_sha256": hashlib.sha256(start["query"].encode()).hexdigest(),
    }
    original = _read(directory / "started.json")
    _require(
        all(original[k] == v for k, v in binding.items()) and original["phrase"] == start["query"],
        "native original query binding",
    )
    if end["outcome"] != "success":
        failed = _read(directory / "failure.json")
        _require(
            all(failed[k] == v for k, v in binding.items())
            and failed["generation_calls_started"] == after["started"]
            and failed["generation_calls_completed"] == after["completed"],
            "native failure counters/binding",
        )
        return None
    _require(ds == dc == 1, "successful point needs one real generation")
    raw = (directory / "raw-response.txt").read_text()
    result = _read(directory / "result.json")
    parsed = parse_native_point(raw)
    if result["reached_cap"]:
        parsed = NativePointResult("INVALID", None, None, raw, "output token cap")
    _require(
        _canonical(result["native"]) == _canonical(asdict(parsed)), "native parse/raw mismatch"
    )
    _require(
        all(result[k] == v for k, v in binding.items())
        and result["model"] == MODEL_ID
        and result["precision"] == "BF16"
        and result["model_image_count"] == 1,
        "native identity/binding",
    )
    _require(
        result["raw_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
        and end["raw_sha256"] == result["raw_sha256"],
        "native raw hash",
    )
    _require(
        Path(result["raw_directory"]).resolve() == directory.resolve(), "provider directory changed"
    )
    _require(
        end["status"] == parsed.status
        and end["bound"]
        and end["query_sha256"] == binding["query_sha256"]
        and end["observation_checksum"] == binding["observation_checksum"]
        and end["rgb_sha256"] == binding["rgb_sha256"],
        "returned native binding",
    )
    _require(
        _read(directory / "generation-started.json")["generation_calls_started"]
        == after["started"]
        == result["generation_calls_started"],
        "raw started counter",
    )
    _require(
        _read(directory / "generation-completed.json")["generation_calls_completed"]
        == after["completed"]
        == result["generation_calls_completed"],
        "raw completed counter",
    )
    for name, count in (
        ("input-token-ids.json", result["input_tokens"]),
        ("output-token-ids.json", result["output_tokens"]),
    ):
        ids = _read(directory / name)
        _require(
            isinstance(ids, list)
            and len(ids) == count
            and count > 0
            and all(type(i) is int and i >= 0 for i in ids),
            "native token evidence",
        )
    _require(
        isinstance(_read(directory / "processor.json"), dict)
        and native_prompt(start["query"]) in (directory / "prompt.txt").read_text(),
        "native prompt/processor binding",
    )
    return parsed


def _visual_source(case, response, observations, opened, ended, parsed):
    from cloud_edge_robot_arm.vision.grounded_planner import model_to_observation_pixel
    from cloud_edge_robot_arm.vision.point_association import (
        PointAssociationError,
        associate_target_point,
    )
    from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker

    points = [e for e in ended.values() if e["kind"] == "point"]
    stages = [e for e in ended.values() if e["kind"] == "stage"]
    if any(p is not None and p.status == "ABSENT" for p in parsed):
        _require(
            len(observations) == 1
            and not stages
            and parsed[-1].status == "ABSENT"
            and all(p.status == "POINT" for p in parsed[:-1]),
            "absence causal path",
        )
        return "model_absence"
    if len(points) != 2 or not all(p is not None and p.status == "POINT" for p in parsed):
        return None
    allow = _read(REPAIR / "plan.json")["visual_refusal_allowlist"]
    for stage in stages:
        if stage["outcome"] != "error":
            continue
        name = stage["stage"]
        policy = allow.get(name, {})
        message = stage["error_message"]
        if stage["error_type"] != policy.get("exception") or message not in policy.get(
            "exact_messages", []
        ):
            continue
        context = stage["context"]
        observation = observations[context["observation_checksum"]]
        _fresh_at(observation, stage["utc"])
        _require(response.reason == message, "causal pipeline refusal differs")
        native = model_to_observation_pixel(
            parsed[0].normalized_1000, observation, coordinate_system="normalized_1000"
        )
        _require(context["native_pixel"] == list(native), "stage/native pixel context")
        if name == "association":
            _require(
                context["target_phrase"] == case.task.target_phrase,
                "association descriptor context",
            )
            try:
                associate_target_point(observation, native, target_phrase=case.task.target_phrase)
            except PointAssociationError as exc:
                _require(
                    str(exc) == message
                    and _canonical(exc.evidence) == _canonical(stage["exception_evidence"]),
                    "original association evidence differs",
                )
                ev = exc.evidence
                _require(
                    ev["schema"] == "bounded_local_component.v1"
                    and ev["status"] == "REJECTED"
                    and ev["reason"] == message
                    and ev["helper_sha256"] == _sha(ROOT / STAGE_FILES[name]),
                    "association structured identity",
                )
                return "program_geometry"
            raise EvidenceError("association rejection not reproduced")
        if name == "tracker":
            grounding = context["grounding"]
            _require(
                grounding["checksum_sha256"] == observation.checksum_sha256
                and grounding["native_original_pixel_target"] == list(native),
                "tracker observation context",
            )
            _require(
                grounding["original_pixel_target"] == grounding["associated_pixel_target"]
                and grounding["grasp_calibration_asset_sha256"],
                "tracker calibrated geometry context",
            )
            try:
                OpenCVTargetTracker(observation, grounding)
            except ValueError as exc:
                _require(str(exc) == message, "original tracker refusal differs")
                return "program_geometry"
            raise EvidenceError("tracker rejection not reproduced")
    return None


def validate_case_evidence(case, *, root, registry, response, events):
    counts = _counts(events)
    try:
        _registry_check(root, registry)
        reservations = [
            (p, r) for p, r in _reservations(root, registry) if r["case_id"] == case.case_id
        ]
        counts = _counts(events, reservations)
        disk = _read_events(root, case.case_id)
        _require(_canonical(events) == _canonical(disk), "passed events differ from originals")
        opened, ended = _event_check(root, registry, case.group_id, case, events)
        folder = root / case.group_id / case.case_id
        present = response is not None
        required = _case_paths(root, case, events, present)
        required.update(p for p in folder.rglob("*") if p.is_file() and p.name != CASE_MANIFEST)
        manifest = _manifest_check(
            root,
            registry,
            folder / CASE_MANIFEST,
            _identity(root, registry, case.group_id, case),
            required,
        )
        _require(manifest["response_received"] == present, "response presence changed")
        _require(
            _read(folder / "task.json") == case.task.model_dump(mode="json")
            and _read(folder / "scene-setup.json") == case.scene.model_dump(mode="json"),
            "task/setup identity",
        )
        for phase in ("start", "end"):
            claim = _read(root / "claims" / f"case-{case.case_id}-{phase}.json")
            _require(
                claim["phase"] == phase
                and all(
                    claim[k] == v for k, v in _identity(root, registry, case.group_id, case).items()
                ),
                "case claim identity",
            )
        if not present:
            return EvidenceCheck(False, ["no actual pipeline response"], counts)
        _require(
            _canonical(response.model_dump(mode="json"))
            == _canonical(_read(folder / "pipeline-return.json")),
            "original pipeline response changed",
        )
        _require(response.request_id == case.request_id, "response request binding")
        pipeline = [e for e in ended.values() if e["kind"] == "pipeline"]
        _require(len(pipeline) == 1 and pipeline[0]["outcome"] == "success", "pipeline closure")
        captures = [e for e in ended.values() if e["kind"] == "capture"]
        _require(
            1 <= len(captures) <= (2 if case.expected == "positive" else 1)
            and all(e["outcome"] == "success" for e in captures),
            "capture closure",
        )
        _require(len({e["session_id"] for e in captures}) == 1, "capture session changed")
        observations = {}
        initial = None
        for index, event in enumerate(captures, 1):
            _require(event["capture_index"] == index, "capture sequence")
            capture = folder / f"capture-{index:02}"
            request = InitialPlanningRequest.model_validate(_read(capture / "request.json"))
            obs = request.observation
            _require(
                obs is not None
                and request.request_id == case.request_id
                and request.user_instruction == case.task.instruction,
                "capture task request",
            )
            _require(
                not request.scene.objects
                and not request.scene.regions
                and not request.scene.obstacles
                and not request.scene.robot_state,
                "truth in online scene",
            )
            _require(
                obs.source == "mujoco_camera"
                and obs.episode_id
                and obs.calibration_version
                and obs.scene_id == case.scene.group_id
                and obs.depth_convention == "optical_z_m",
                "capture domain/binding",
            )
            _require(
                base64.b64decode(obs.rgb_png_base64) == (capture / "rgb.png").read_bytes()
                and base64.b64decode(obs.depth_float32_base64)
                == (capture / "depth.f32").read_bytes()
                and obs.valid_mask_bytes() == (capture / "valid_mask.u8").read_bytes(),
                "capture bytes differ from request",
            )
            _require(
                event["observation_checksum"] == obs.checksum_sha256
                and event["frame_id"] == obs.frame_id
                and event["evidence"] == json.loads(_canonical(obs.evidence())),
                "capture event binding",
            )
            observations[obs.checksum_sha256] = obs
            if initial is None:
                initial = obs
        _require(len(observations) == len(captures), "duplicate capture checksum")
        points = [e for e in ended.values() if e["kind"] == "point"]
        _require(1 <= len(points) <= case.point_cap, "missing/excess point attempts")
        queries = (
            f"visible top center of {case.task.target_phrase}",
            f"interior of {case.task.destination_phrase}",
        )
        frames = list(observations)
        parsed = []
        prior_after = None
        for index, end in enumerate(points):
            start = opened[end["op_id"]]
            checksum = frames[index // 2]
            _require(
                start["query"] == queries[index % 2]
                and start["observation_checksum"] == checksum
                and end["observation_checksum"] == checksum,
                "query/frame sequence",
            )
            _require(start["parent_op_id"] == pipeline[0]["op_id"], "point outside pipeline")
            obs = observations[checksum]
            _require(
                opened[captures[index // 2]["op_id"]]["monotonic_s"]
                <= captures[index // 2]["monotonic_s"]
                <= start["monotonic_s"],
                "point before capture",
            )
            if prior_after is not None:
                _require(end["counters_before"] == prior_after, "native counter continuity")
            parsed.append(_native_check(root, case, start, end, obs))
            prior_after = end["counters_after"]
            if end["outcome"] == "success":
                _fresh_at(obs, end["utc"])
        _require(
            len({e["reservation_id"] for e in points})
            == len(points)
            == sum(r["kind"] == "point" for _, r in reservations),
            "point reservation reconciliation",
        )
        stages = [e for e in ended.values() if e["kind"] == "stage"]
        by_frame = {checksum: [] for checksum in frames}
        for end in stages:
            context = end["context"]
            name = end["stage"]
            _require(
                name in STAGE_FILES and context == opened[end["op_id"]]["context"],
                "stage context changed",
            )
            _require(
                end["source_sha256"]
                == _sha(ROOT / STAGE_FILES[name])
                == registry["source_hashes"].get(STAGE_FILES[name]),
                "stage source identity",
            )
            _require(context["observation_checksum"] in observations, "stage frame binding")
            by_frame[context["observation_checksum"]].append(name)
        for sequence in by_frame.values():
            _require(
                sequence == ["association", "grounding", "tracker"][: len(sequence)], "stage order"
            )
        paid = [e for e in ended.values() if e["kind"] == "paid"]
        _require(
            len(paid) <= case.paid_cap
            and len(paid) == sum(r["kind"] == "paid" for _, r in reservations),
            "paid reservation reconciliation",
        )
        for end in paid:
            refs = {Path(r["path"]).name: r for r in end["raw_refs"]}
            _require(
                end["delegated_post"] in {0, 1}
                and end["request_observed"] == int("request-0001.json" in refs)
                and end["response_observed"] == int("response-0001.json" in refs),
                "paid wire reconciliation",
            )
            if end["request_observed"]:
                body = _read(root / refs["request-0001.json"]["path"])
                _require(
                    body["model"] == "gpt-6.1-sol" and end["route"] == "/v1/chat/completions",
                    "cloud selected route",
                )
            if end["parsed_success"]:
                body = _read(root / refs["response-0001.json"]["path"])
                _require(
                    end["outcome"] == "success"
                    and body.get("model") == end["model"]
                    and body.get("usage") == end["usage"],
                    "cloud parsed response binding",
                )
        if len(captures) == 2:
            from cloud_edge_robot_arm.vision.revalidation import validate_post_cloud_observation

            _require(
                len(paid) == 1
                and paid[0]["parsed_success"] == 1
                and paid[0]["monotonic_s"] <= opened[captures[1]["op_id"]]["monotonic_s"],
                "refresh before real cloud completion",
            )
            validate_post_cloud_observation(
                initial, observations[frames[1]], not_before=datetime.fromisoformat(paid[0]["utc"])
            )
        _fresh_at(observations[frames[-1]], pipeline[0]["utc"])
        refusal = None
        if (
            case.expected == "negative"
            and response.outcome.value == "REQUEST_MORE_OBSERVATION"
            and response.contract is None
            and not paid
            and not any(e["kind"] == "cloud_entry" for e in events)
        ):
            refusal = _visual_source(case, response, observations, opened, ended, parsed)
        return EvidenceCheck(True, [], counts, refusal)
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
        return EvidenceCheck(False, [f"{type(exc).__name__}:{exc}"], counts)


def classify_case(case, response, events, *, root, registry):
    check = validate_case_evidence(
        case, root=root, registry=registry, response=response, events=events
    )
    result = {
        "case_id": case.case_id,
        "group_id": case.group_id,
        "expected": case.expected,
        "request_id": case.request_id,
        "verdict": "ERROR_OR_INCOMPLETE",
        "passed": False,
        "refusal_source": None,
        **check.counts,
        "evidence_ok": check.ok,
        "evidence_errors": check.errors,
        "outcome": response.outcome.value if response else None,
        "reason": response.reason if response else None,
    }
    if case.expected == "negative" and any(e["kind"] == "cloud_entry" for e in events):
        result["verdict"] = "FAIL_CLOUD_GATE_REACHED"
        return result
    if any(e["kind"] == "budget_block" for e in events):
        result["verdict"] = "FAIL_BUDGET_BLOCK"
        return result
    if not check.ok or response is None:
        return result
    if any(
        e["kind"] in {"runtime_error", "fatal"}
        or (e["kind"] == "point" and e["phase"] == "end" and e["outcome"] != "success")
        for e in events
    ):
        return result
    if any(status not in {"POINT", "ABSENT"} for status in result["point_statuses"]):
        result["verdict"] = "ERROR_POINT_OR_BINDING"
        return result
    if case.expected == "negative":
        result["verdict"] = "ERROR_UNCLASSIFIED_REJECTION"
        if check.refusal_source:
            result.update(
                verdict="PASS_EXPECTED_REJECTION", passed=True, refusal_source=check.refusal_source
            )
        return result
    evidence = response.attempts[-1].draft.observation_evidence if response.attempts else {}
    if (
        response.outcome.value == "PLANNED"
        and response.contract is not None
        and response.validation.passed
        and evidence.get("post_cloud_revalidation", {}).get("status") == "PASSED"
        and evidence.get("final_plan_admission", {}).get("status") == "PASSED"
        and result["actual_generations"] == result["actual_generations_completed"] == 4
        and result["capture_count"] == 2
        and result["point_statuses"] == ["POINT"] * 4
        and result["paid"]["parsed_success"] == 1
    ):
        result.update(verdict="PASS_PLANNED", passed=True)
    else:
        result["verdict"] = "FAIL_INTERFACE"
    return result


def _group_paths(root, registry, group):
    folder = root / group
    paths = {
        p
        for p in folder.rglob("*")
        if p.is_file()
        and p.name != "raw-manifest.local.json"
        and "runtime-cache" not in p.relative_to(root).parts
    }
    paths.update(
        {root / "registry.json", root / "registry.sha256", root / "claims" / f"group-{group}.json"}
    )
    for case_id in GROUPS[group]:
        paths.update((root / "events" / case_id).glob("*.json"))
        paths.update(
            p
            for phase in ("start", "end")
            if (p := root / "claims" / f"case-{case_id}-{phase}.json").exists()
        )
    paths.update((root / "events" / f"_{group}").glob("*.json"))
    paths.update(p for p, r in _reservations(root, registry) if r["group_id"] == group)
    if (root / f"fatal-{group}.json").exists():
        paths.add(root / f"fatal-{group}.json")
    return paths


def _group_accounting(root, registry, group, actual):
    reservations = [(p, r) for p, r in _reservations(root, registry) if r["group_id"] == group]
    events = [e for name in GROUPS[group] for e in _read_events(root, name)]
    counts = _counts(events, reservations)
    reserved = {
        kind: sum(r["kind"] == kind for _, r in reservations) for kind in ("load", "point", "paid")
    }
    return {
        "reserved": reserved,
        "observed": counts,
        "actual": actual,
        "unspent": {
            "loads": 1 - reserved["load"],
            "generations": CAPS[group] - reserved["point"],
            "paid": 1 - reserved["paid"],
        },
    }


def validate_group_evidence(group_id, *, root, registry):
    counts = {}
    try:
        _registry_check(root, registry)
        report = _read(root / group_id / "group-end.json")
        _require(
            report["group_id"] == group_id
            and report["status"] == "COMPLETED"
            and report["stop_reason"] is None,
            "group incomplete/stopped",
        )
        _manifest_check(
            root,
            registry,
            root / group_id / "raw-manifest.local.json",
            _identity(root, registry, group_id),
            _group_paths(root, registry, group_id),
        )
        claim = _read(root / "claims" / f"group-{group_id}.json")
        _require(
            all(claim[k] == v for k, v in _identity(root, registry, group_id).items()),
            "group claim identity",
        )
        events = _read_events(root, f"_{group_id}")
        opened, ended = _event_check(root, registry, group_id, None, events)
        loads = [e for e in ended.values() if e["kind"] == "load"]
        _require(
            len(loads) == 1 and len(opened) == 1 and loads[0]["outcome"] == "success",
            "load closure",
        )
        native = root / group_id / "native"
        _require(
            _read(native / "load-started.json")["model_loads_started"]
            == _read(native / "loaded.json")["model_loads_started"]
            == 1,
            "load original identity",
        )
        actual = report["actual_counts"]
        counts = _group_accounting(root, registry, group_id, actual)
        _require(
            counts == report["accounting"] and actual["loads"] == 1, "group accounting changed"
        )
        _require(
            counts["observed"]["actual_generations"] == actual["generations_started"]
            and counts["observed"]["actual_generations_completed"]
            == actual["generations_completed"]
            and not counts["observed"]["native_unknown"],
            "native group counter reconciliation",
        )
        point_ends = [
            e
            for name in GROUPS[group_id]
            for e in _read_events(root, name)
            if e["kind"] == "point" and e["phase"] == "end"
        ]
        _require(
            {e["native_directory"] for e in point_ends}
            == {str(p.relative_to(root)) for p in native.glob("request-*")},
            "unassigned native attempt",
        )
        _require(
            [r["case_id"] for r in report["results"]] == list(GROUPS[group_id]), "group fixed rows"
        )
        for case_id in GROUPS[group_id]:
            case = CaseSpec.read(next(c for c in registry["cases"] if c["case_id"] == case_id))
            response = InitialPlanningResponse.model_validate(
                _read(root / group_id / case_id / "pipeline-return.json")
            )
            events = _read_events(root, case_id)
            result = classify_case(case, response, events, root=root, registry=registry)
            stored = _read(root / group_id / f"result-{case_id}.json")
            _require(
                stored == result
                and stored == next(r for r in report["results"] if r["case_id"] == case_id),
                "case result contradicts originals",
            )
            _require(result["evidence_ok"], "case evidence incomplete")
        return EvidenceCheck(True, [], counts)
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
        return EvidenceCheck(False, [f"{type(exc).__name__}:{exc}"], counts)


def summarize(registry, results, *, root):
    assigned = registry["cases"]
    expected = {c["case_id"] for c in assigned}
    counts = Counter(r.get("case_id") for r in results)
    unknown = sum(r.get("case_id") not in expected for r in results)
    duplicates = sum(counts[n] > 1 for n in expected)
    checks = {g: validate_group_evidence(g, root=root, registry=registry) for g in GROUPS}
    rows = []
    errors = []
    for item in assigned:
        matches = [r for r in results if r.get("case_id") == item["case_id"]]
        row = (
            matches[0]
            if len(matches) == 1
            else {
                "case_id": item["case_id"],
                "group_id": item["group_id"],
                "expected": item["expected"],
                "verdict": "NOT_RUN" if not matches else "INVALID_DUPLICATE",
                "passed": False,
            }
        )
        if len(matches) == 1:
            try:
                original = _read(root / item["group_id"] / f"result-{item['case_id']}.json")
                _require(
                    row == original
                    and row["group_id"] == item["group_id"]
                    and row["expected"] == item["expected"]
                    and row["request_id"] == item["request_id"],
                    "summary row identity/content contradiction",
                )
                _require(
                    row["passed"]
                    == (row["verdict"] in {"PASS_PLANNED", "PASS_EXPECTED_REJECTION"}),
                    "passed/verdict contradiction",
                )
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors.append(f"{item['case_id']}:{type(exc).__name__}:{exc}")
        rows.append(row)
    valid = not unknown and not duplicates and not errors and all(c.ok for c in checks.values())
    positive = (
        sum(
            r.get("passed") is True
            and r.get("expected") == "positive"
            and r.get("verdict") == "PASS_PLANNED"
            for r in rows
        )
        if valid
        else 0
    )
    negative = (
        sum(
            r.get("passed") is True
            and r.get("expected") == "negative"
            and r.get("verdict") == "PASS_EXPECTED_REJECTION"
            for r in rows
        )
        if valid
        else 0
    )
    return {
        "total_cases": 7,
        "positive_cases": 3,
        "negative_cases": 4,
        "cases": rows,
        "unknown_records": unknown,
        "duplicate_cases": duplicates,
        "missing_cases": sum(counts[n] == 0 for n in expected),
        "valid_suite": valid,
        "passed_cases": positive + negative,
        "positive_passed": positive,
        "negative_passed": negative,
        "all_cases_pass": valid and positive == 3 and negative == 4 and len(results) == 7,
        "evidence_errors": errors
        + [{"group_id": g, "errors": c.errors} for g, c in checks.items() if not c.ok],
        "group_accounting": {g: c.counts for g, c in checks.items()},
    }


def _provider_counters(provider):
    result = {
        "started": provider.generation_calls_started,
        "completed": provider.generation_calls_completed,
    }
    _require(
        all(type(v) is int and v >= 0 for v in result.values())
        and result["completed"] <= result["started"],
        "provider counters invalid",
    )
    return result


def _raw_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _stage_context(stage, args, kwargs):
    observation = args[1] if stage == "grounding" else args[0]
    context = {"observation_checksum": observation.checksum_sha256}
    if stage == "association":
        context.update(native_pixel=list(args[1]), target_phrase=kwargs["target_phrase"])
    else:
        grounding = args[1] if stage == "tracker" else kwargs["evidence"]
        context.update(
            native_pixel=copy.deepcopy(grounding.get("native_original_pixel_target")),
            grounding=copy.deepcopy(grounding),
        )
    return context


@contextmanager
def _observe_stages(ledger, case, parent):
    import cloud_edge_robot_arm.vision.grounded_planner as module

    originals = {}
    for attribute, stage in (
        ("associate_target_point", "association"),
        ("ground_observation", "grounding"),
        ("OpenCVTargetTracker", "tracker"),
    ):
        original = getattr(module, attribute)
        originals[attribute] = original

        def observed(*args, _original=original, _stage=stage, **kwargs):
            context = _stage_context(_stage, args, kwargs)
            fields = {
                "stage": _stage,
                "context": context,
                "source_sha256": _sha(ROOT / STAGE_FILES[_stage]),
                "callee": f"{_original.__module__}.{_original.__qualname__}",
            }
            op = ledger.start("stage", case.case_id, parent=parent, **fields)
            error = None
            try:
                return _original(*args, **kwargs)
            except BaseException as exc:
                error = exc
                raise
            finally:
                ledger.end(
                    op,
                    error=error,
                    **fields,
                    exception_evidence=copy.deepcopy(getattr(error, "evidence", None)),
                )

        setattr(module, attribute, observed)
    try:
        yield
    finally:
        for name, original in originals.items():
            setattr(module, name, original)


def run_case(case, *, provider, service, profile_id, ledger, output):
    """原pipeline一次调用及原响应；任何原件错误都停止当前resident组。"""
    ledger.begin_case(case.group_id, case.case_id)
    folder = output / case.group_id / case.case_id
    captures = []
    request = None
    response = None
    error = None
    pipeline_op = None
    session_id = uuid.uuid4().hex

    class Points:
        def point(self, observation, phrase):
            try:
                reservation = ledger.reserve("point", group_id=case.group_id, case_id=case.case_id)
            except ValueError:
                ledger.record(case.case_id, kind="budget_block", operation="point")
                raise
            before = ledger._io("provider.counters.before", lambda: _provider_counters(provider))
            native = output / case.group_id / "native"
            previous = ledger._io("native.enumerate.before", lambda: set(native.glob("request-*")))
            op = ledger.start(
                "point",
                case.case_id,
                parent=pipeline_op,
                reservation=reservation,
                query=phrase,
                observation_checksum=observation.checksum_sha256,
                counters_before=before,
            )
            point = None
            failure = None
            try:
                point = provider.point(observation, phrase)
                return point
            except BaseException as exc:
                failure = exc
                raise
            finally:
                try:
                    after = ledger._io(
                        "provider.counters.after", lambda: _provider_counters(provider)
                    )
                    ds, dc = (
                        after["started"] - before["started"],
                        after["completed"] - before["completed"],
                    )
                    added = ledger._io(
                        "native.enumerate.after", lambda: set(native.glob("request-*")) - previous
                    )
                    directory = next(iter(added)) if len(added) == 1 else None
                    refs = (
                        ledger._io("native.references", lambda: _tree(output, directory))
                        if directory
                        else []
                    )
                    if point is not None:
                        _require(
                            directory is not None
                            and Path(point.evidence["raw_directory"]).resolve()
                            == directory.resolve(),
                            "provider result/raw directory binding",
                        )
                    fields = {
                        "query": phrase,
                        "observation_checksum": observation.checksum_sha256,
                        "rgb_sha256": observation.evidence()["rgb_sha256"],
                        "query_sha256": hashlib.sha256(phrase.encode()).hexdigest(),
                        "counters_before": before,
                        "counters_after": after,
                        "started_delta": ds,
                        "completed_delta": dc,
                        "native_directory": str(directory.relative_to(output))
                        if directory
                        else None,
                        "raw_refs": refs,
                        "status": point.result.status if point else None,
                        "raw_sha256": hashlib.sha256(point.result.raw_text.encode()).hexdigest()
                        if point
                        else None,
                        "bound": bool(
                            point
                            and point.observation_checksum == observation.checksum_sha256
                            and point.rgb_sha256 == observation.evidence()["rgb_sha256"]
                            and point.query_sha256 == hashlib.sha256(phrase.encode()).hexdigest()
                        ),
                    }
                    ledger.end(op, error=failure, **fields)
                    if (
                        failure
                        or ds not in {0, 1}
                        or dc not in {0, 1}
                        or (point is not None and (ds, dc) != (1, 1))
                        or directory is None
                    ):
                        ledger.poison(
                            f"provider:"
                            f"{type(failure).__name__ if failure else 'counter_or_raw_integrity'}"
                        )
                except BaseException as final_error:
                    ledger.poison(f"point.finalize:{type(final_error).__name__}")
                    if failure is None:
                        raise
                finally:
                    if failure is not None:
                        ledger.poison(f"provider:{type(failure).__name__}")

    try:
        ledger._io("case.mkdir", lambda: folder.mkdir(parents=True, exist_ok=False))
        ledger._io(
            "task.write", lambda: _write(folder / "task.json", case.task.model_dump(mode="json"))
        )
        ledger._io(
            "setup.write",
            lambda: _write(folder / "scene-setup.json", case.scene.model_dump(mode="json")),
        )
        with MuJoCoCaptureSession(SimulatorConfig(render_rgb=True, render_depth=True)) as session:
            ledger._io("scene.apply", lambda: session.apply_scene(case.scene))

            def capture():
                nonlocal request
                if len(captures) >= (2 if case.expected == "positive" else 1):
                    ledger.record(case.case_id, kind="budget_block", operation="capture")
                    raise ValueError("capture allocation exhausted")
                index = len(captures) + 1
                op = ledger.start(
                    "capture",
                    case.case_id,
                    parent=pipeline_op,
                    capture_index=index,
                    session_id=session_id,
                )
                failure = None
                observation = None
                try:
                    observation = ledger._io("capture.exposure", session.capture)
                    if request is None:
                        request = InitialPlanningRequest(
                            request_id=case.request_id,
                            user_instruction=case.task.instruction,
                            observation=observation,
                            scene=SceneSummary(scene_version=1, updated_at=observation.captured_at),
                            capabilities=RobotCapabilities(
                                supported_skills=[
                                    "HOME",
                                    "MOVE_ABOVE",
                                    "APPROACH",
                                    "GRASP",
                                    "LIFT",
                                    "MOVE_TO_REGION",
                                    "PLACE",
                                    "RELEASE",
                                    "RETREAT",
                                ]
                            ),
                        )
                    ledger._io(
                        "capture.raw",
                        lambda: _save_capture(folder / f"capture-{index:02}", request, observation),
                    )
                    captures.append(observation)
                    return observation
                except BaseException as exc:
                    failure = exc
                    raise
                finally:
                    ledger.end(
                        op,
                        error=failure,
                        capture_index=index,
                        session_id=session_id,
                        observation_checksum=observation.checksum_sha256 if observation else None,
                        frame_id=observation.frame_id if observation else None,
                        evidence=observation.evidence() if observation else None,
                        raw_refs=ledger._io(
                            "capture.references",
                            lambda: _tree(output, folder / f"capture-{index:02}"),
                        ),
                    )

            capture()
            adapter = build_molmo_grounded_planner(
                service=service,
                profile_id=profile_id,
                point_provider=Points(),
                task=case.task,
                grasp_profile="mujoco_upright_box_v2",
                allow_paid=True,
                post_cloud_observation_supplier=capture if case.expected == "positive" else None,
            )
            cloud = adapter.cloud
            original_visual, original_post, original_observer = (
                cloud._request_visual,
                cloud._post,
                cloud.raw_transport_observer,
            )
            wire_counts = Counter()

            def wire(phase, path, data):
                if phase not in {"REQUEST", "RESPONSE"} or path != "/v1/chat/completions":
                    ledger.poison("cloud observer identity")
                    raise EvidenceError("cloud observer identity")
                wire_counts[phase] += 1
                if wire_counts[phase] > 1:
                    ledger.poison("duplicate wire observation")
                    raise EvidenceError("duplicate wire observation")
                ledger._io(
                    "cloud.raw",
                    lambda: _raw_bytes(
                        folder / "cloud" / f"{phase.lower()}-{wire_counts[phase]:04}.json", data
                    ),
                )

            def visual(*args, **kwargs):
                ledger.record(case.case_id, kind="cloud_entry", parent_op_id=pipeline_op)
                if case.expected == "negative":
                    raise RuntimeError("negative cloud entry forbidden")
                return original_visual(*args, **kwargs)

            def post(path, body):
                try:
                    reservation = ledger.reserve(
                        "paid", group_id=case.group_id, case_id=case.case_id
                    )
                except ValueError:
                    ledger.record(case.case_id, kind="budget_block", operation="paid")
                    raise
                op = ledger.start(
                    "paid", case.case_id, parent=pipeline_op, reservation=reservation, route=path
                )
                result = None
                failure = None
                delegated = 0
                try:
                    _require(
                        path == "/v1/chat/completions" and body.get("model") == "gpt-6.1-sol",
                        "selected cloud route drift",
                    )
                    delegated = 1
                    result = original_post(path, body)
                    return result
                except BaseException as exc:
                    failure = exc
                    raise
                finally:
                    ledger.end(
                        op,
                        error=failure,
                        route=path,
                        delegated_post=delegated,
                        request_observed=wire_counts["REQUEST"],
                        response_observed=wire_counts["RESPONSE"],
                        parsed_success=int(result is not None),
                        transmission_state="RESPONSE_OBSERVED"
                        if wire_counts["RESPONSE"]
                        else ("UNKNOWN" if delegated else "NOT_DELEGATED"),
                        model=result.get("model") if result else None,
                        usage=result.get("usage") if result else None,
                        http_numeric_status="NOT_CAPTURED",
                        raw_refs=ledger._io(
                            "cloud.references", lambda: _tree(output, folder / "cloud")
                        ),
                    )

            cloud._request_visual, cloud._post, cloud.raw_transport_observer = visual, post, wire
            try:
                pipeline_op = ledger.start("pipeline", case.case_id)
                failure = None
                try:
                    with _observe_stages(ledger, case, pipeline_op):
                        response = PlanningPipeline(planner=adapter).process(request)
                    ledger._io(
                        "pipeline.raw",
                        lambda: _write(
                            folder / "pipeline-return.json", response.model_dump(mode="json")
                        ),
                    )
                except BaseException as exc:
                    failure = exc
                    raise
                finally:
                    refs = (
                        [_ref(output, folder / "pipeline-return.json")]
                        if (folder / "pipeline-return.json").exists()
                        else []
                    )
                    ledger.end(pipeline_op, error=failure, raw_refs=refs)
                return response
            finally:
                cloud._request_visual, cloud._post, cloud.raw_transport_observer = (
                    original_visual,
                    original_post,
                    original_observer,
                )
    except BaseException as exc:
        error = exc
        ledger.poison(f"case:{type(exc).__name__}")
        try:
            ledger.record(
                case.case_id, kind="runtime_error", operation="case", error_type=type(exc).__name__
            )
            if folder.exists():
                ledger._io(
                    "case.error",
                    lambda: _write(
                        folder / "case-error.json", {"error_type": type(error).__name__, **_stamp()}
                    ),
                )
        except BaseException:
            pass
        raise
    finally:
        try:
            ledger.end_case(case.group_id, case.case_id)
            _seal_case(ledger, case, response is not None)
        except BaseException:
            if error is None:
                raise


def _profile(model_store, profile_id, task):
    from cloud_edge_robot_arm.model_control.secret_store import create_secret_store
    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository

    if not model_store.is_file():
        raise ValueError("existing model store required")
    service = ModelControlService(
        repository=SQLiteModelProfileRepository(model_store),
        secret_store=create_secret_store(model_store),
    )
    if not service.secret_store.has_secret(profile_id):
        raise ValueError("existing saved secret required")
    adapter = build_molmo_grounded_planner(
        service=service,
        profile_id=profile_id,
        point_provider=object(),
        task=task,
        grasp_profile="mujoco_upright_box_v2",
        allow_paid=True,
    )
    settings = cloud_request_settings(adapter.cloud)
    if configuration_hash(settings) != SETTINGS_SHA:
        raise ValueError("selected Sol settings drift")
    return service, {
        "settings_hash": SETTINGS_SHA,
        "secret_present": True,
        "role": adapter.cloud.role_snapshot.evidence(),
    }


def _check_sources(registry):
    required = json.loads((ROUND / "plan.json").read_bytes())["inputs"]
    for row in required:
        relative = str(Path(row["path"]).relative_to(ROOT))
        if registry["source_hashes"].get(relative) != row["sha256"]:
            raise ValueError("frozen source missing or changed")
    for name, digest in registry["source_hashes"].items():
        path = (ROOT / name).resolve(strict=True)
        if not path.is_relative_to(ROOT) or _sha(path) != digest:
            raise ValueError("source identity drift")


def _actual_counts(provider, group):
    if provider is not None:
        values = _provider_counters(provider)
        return {
            "loads": provider.model_loads_started,
            "generations_started": values["started"],
            "generations_completed": values["completed"],
        }
    marker = group / "native/load-started.json"
    loads = _read(marker)["model_loads_started"] if marker.exists() else None
    return {"loads": loads, "generations_started": 0, "generations_completed": 0}


def _not_run(case, reason):
    return {
        "case_id": case.case_id,
        "group_id": case.group_id,
        "expected": case.expected,
        "request_id": case.request_id,
        "verdict": "NOT_RUN",
        "passed": False,
        "refusal_source": None,
        "reason": reason,
        "outcome": None,
        "actual_generations": 0,
        "actual_generations_completed": 0,
        "capture_count": 0,
        "point_statuses": [],
        "paid_responses": 0,
    }


def run_group(
    group_id,
    *,
    registry,
    output,
    model_directory,
    asset_manifest,
    model_store,
    profile_id,
    gpu_lock,
    allow_paid,
):
    """独占claim到最终封存均在无条件解锁边界内；未执行案保留固定行。"""
    if not allow_paid or group_id not in GROUPS:
        raise ValueError("explicit bounded paid mode and registered group required")
    registered = _read(registry)
    if registry.read_bytes() != (output / "registry.json").read_bytes():
        raise ValueError("external registry drift")
    _check_sources(registered)
    ledger = None
    provider = None
    group = output / group_id
    results = []
    error = None
    cases = [CaseSpec.read(c) for c in registered["cases"] if c["group_id"] == group_id]
    report = {
        "group_id": group_id,
        "status": "INCOMPLETE",
        "results": [],
        "stop_reason": "not_started",
    }
    try:
        ledger = RunLedger(output, registered)
        ledger.claim(group_id)
        ledger._io("group.mkdir", lambda: group.mkdir(exist_ok=False))
        _require(tuple(c.case_id for c in cases) == GROUPS[group_id], "registered group changed")
        service, profile = _profile(model_store, profile_id, cases[0].task)
        ledger._io("profile.write", lambda: _write(group / "profile-preflight.json", profile))
        with _admit_resources(model_directory, gpu_lock) as resources:
            ledger._io("resources.write", lambda: _write(group / "resources.json", resources))
            cache = group / "runtime-cache"
            os.environ.update(
                HF_HUB_OFFLINE="1",
                TRANSFORMERS_OFFLINE="1",
                HF_HOME=str(cache / "hf"),
                HF_MODULES_CACHE=str(cache / "modules"),
                PYTHONDONTWRITEBYTECODE="1",
            )
            reservation = ledger.reserve("load", group_id=group_id, case_id=None)
            op = ledger.start("load", None, reservation=reservation)
            load_error = None
            try:
                provider = MolmoPointProvider(
                    model_directory=model_directory,
                    asset_manifest=asset_manifest,
                    raw_directory=group / "native",
                    generation_limit=CAPS[group_id],
                )
            except BaseException as exc:
                load_error = exc
                raise
            finally:
                try:
                    actual = ledger._io("load.counters", lambda: _actual_counts(provider, group))
                    ledger.end(
                        op,
                        error=load_error,
                        actual_counts=actual,
                        raw_refs=ledger._io(
                            "load.references", lambda: _tree(output, group / "native")
                        ),
                    )
                finally:
                    if load_error:
                        ledger.poison(f"provider.load:{type(load_error).__name__}")
            for case in cases:
                response = None
                try:
                    response = run_case(
                        case,
                        provider=provider,
                        service=service,
                        profile_id=profile_id,
                        ledger=ledger,
                        output=output,
                    )
                except Exception as exc:
                    error = type(exc).__name__
                events = ledger.events_for(case.case_id)
                row = classify_case(case, response, events, root=output, registry=registered)
                ledger._io(
                    "case.result",
                    lambda case=case, row=row: _write(group / f"result-{case.case_id}.json", row),
                )
                results.append(row)
                if not row["evidence_ok"]:
                    ledger.poison("case evidence validation failed")
                if any(e["kind"] == "budget_block" for e in events):
                    ledger.poison("budget allocation stopped")
                if ledger.fatal:
                    break
    except Exception as exc:
        error = type(exc).__name__
        if ledger:
            ledger.poison(f"group:{error}")
        else:
            raise
    finally:
        if ledger is not None:
            try:
                if ledger._io("group.exists", group.exists):
                    attempted = {r["case_id"] for r in results}
                    for case in cases:
                        if case.case_id not in attempted:
                            row = _not_run(
                                case, ledger.stop_reason or error or "earlier operation incomplete"
                            )
                            results.append(row)
                            ledger._io(
                                "not_run.result",
                                lambda case=case, row=row: _write(
                                    group / f"result-{case.case_id}.json", row
                                ),
                            )
                    actual = ledger._io("group.counters", lambda: _actual_counts(provider, group))
                    accounting = ledger._io(
                        "group.accounting",
                        lambda: _group_accounting(output, registered, group_id, actual),
                    )
                    if (
                        accounting["observed"]["actual_generations"]
                        != actual["generations_started"]
                        or accounting["observed"]["actual_generations_completed"]
                        != actual["generations_completed"]
                    ):
                        ledger.poison("group native counters do not reconcile")
                    report = {
                        "group_id": group_id,
                        "status": "COMPLETED"
                        if not ledger.fatal and len(attempted) == len(cases)
                        else "INCOMPLETE",
                        "error_type": error,
                        "stop_reason": ledger.stop_reason,
                        "actual_counts": actual,
                        "accounting": accounting,
                        "results": results,
                        "terminal_errors": ledger.terminal_errors,
                        "end": _stamp(),
                        "hardware_dispatch": False,
                    }
                    ledger._io("group.report", lambda: _write(group / "group-end.json", report))
                    ledger._io(
                        "group.manifest",
                        lambda: _write(
                            group / "raw-manifest.local.json",
                            {
                                "schema": "molmo.interface.group.v2",
                                **_identity(output, registered, group_id),
                                "files": [
                                    _ref(output, p)
                                    for p in sorted(_group_paths(output, registered, group_id))
                                ],
                                "excluded": ["runtime-cache", "lock files"],
                            },
                        ),
                    )
            except BaseException as exc:
                ledger.poison(f"group.finalize:{type(exc).__name__}")
                report.update(
                    status="INCOMPLETE",
                    stop_reason=ledger.stop_reason,
                    terminal_errors=ledger.terminal_errors,
                )
            finally:
                ledger.close()
    return report


def main(argv: list[str] | None = None) -> int:
    """登记、运行一个固定组或汇总；没有重试/筛选/调大预算参数。"""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    register = sub.add_parser("preregister")
    register.add_argument("--output", type=Path, required=True)
    register.add_argument("--registry", type=Path, required=True)
    worker = sub.add_parser("run-group")
    worker.add_argument("--group", choices=tuple(GROUPS), required=True)
    for key in [
        "registry",
        "output",
        "model-directory",
        "asset-manifest",
        "model-store",
        "gpu-lock",
    ]:
        worker.add_argument("--" + key, type=Path, required=True)
    worker.add_argument("--profile-id", required=True)
    worker.add_argument("--allow-paid", action="store_true")
    summary = sub.add_parser("summarize")
    summary.add_argument("--registry", type=Path, required=True)
    summary.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "preregister":
        plan = json.loads((ROUND / "plan.json").read_bytes())
        paths = [Path(row["path"]) for row in plan["inputs"]]
        paths += [
            Path(__file__),
            ROOT / "tests/test_molmo_multiscene.py",
            ROUND / "plan.md",
            ROUND / "plan.json",
            REPAIR / "plan.md",
            REPAIR / "plan.json",
            *(ROOT / name for name in STAGE_FILES.values()),
            ROUND / "implementation/launch_multiscene.py",
            ROOT / "docs/research/molmo-opencv-grounded-planner.md",
        ]
        sources = {str(path.relative_to(ROOT)): _sha(path) for path in paths}
        registry = preregister(
            args.output, build_cases(_sha(ROOT / "assets/robots/franka_panda/scene.xml")), sources
        )
        _write(args.registry, registry)
        print(
            json.dumps(
                {"status": "PREREGISTERED", "cases": 7, "registry_sha256": _sha(args.registry)}
            )
        )
        return 0
    if args.command == "summarize":
        registry = json.loads(args.registry.read_bytes())
        results = [
            json.loads(path.read_bytes()) for path in sorted(args.output.glob("G*/result-*.json"))
        ]
        result = summarize(registry, results, root=args.output)
        _write(args.output / "summary.local.json", result)
        print(
            json.dumps(
                {
                    k: result[k]
                    for k in [
                        "total_cases",
                        "passed_cases",
                        "positive_passed",
                        "negative_passed",
                        "all_cases_pass",
                    ]
                }
            )
        )
        return 0 if result["all_cases_pass"] else 2
    report = run_group(
        args.group,
        registry=args.registry,
        output=args.output,
        model_directory=args.model_directory,
        asset_manifest=args.asset_manifest,
        model_store=args.model_store,
        profile_id=args.profile_id,
        gpu_lock=args.gpu_lock,
        allow_paid=args.allow_paid,
    )
    print(
        json.dumps(
            {
                "group_id": args.group,
                "status": report["status"],
                "actual_counts": report["actual_counts"],
            }
        )
    )
    return 0 if report["status"] == "COMPLETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
