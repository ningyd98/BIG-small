"""严格绑定历史模型输出的离线诊断；原worker、安全、物理及评价路径保持原样。"""

from __future__ import annotations

import base64
import copy
import hashlib
import importlib
import json
import os
import socket
import ssl
import subprocess
import sys
import tarfile
import tempfile
import threading
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

from cloud_edge_robot_arm.research.cost_ledger import CostLedger
from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot
from cloud_edge_robot_arm.vision.molmo_pointing import BoundPointResult, parse_native_point
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter

ROOT = Path(__file__).resolve().parents[3]
PROCESS = ROOT / "artifacts/research/process/20261115-v4-marker-ambiguity"
PLAN = (
    ROOT
    / "artifacts/research/process/20261004-ced-development/astra-rounds"
    / "round-v3-offline-27-regression-20261115"
)
SCOPE = "OFFLINE_FROZEN_OUTPUT_REPLAY"
SUCCESS_CASES = tuple(
    [f"fixed-{s:06d}" for s in range(42001, 42011)]
    + [
        f"development-{s:06d}"
        for s in (43001, 43002, 43005, 43006, 43007, 43010, 43013, 43014, 43015)
    ]
    + [f"held-out-{s:06d}" for s in (44001, 44002, 44003, 44005, 44006, 44010, 44013, 44015)]
)
PLAN_DIGESTS = {
    "case-inputs.json": "56f960411955676cce54016124a73e8c901521d973769f0cc4ddc68225d9946d",
    "episode-manifest-bindings.json": (
        "37ea0c5b01827a39225d38f7b4e18f8aebf2245e0f0c63f025602c12a537537f"
    ),
    "frame-inputs.json": "1f475b456333667e52698159ce51efee60e9f900b62e6f651e01b584697d3fac",
}
SOURCE_MODULES = (
    "vision.pose_markers",
    "research.sol_molmo_components",
    "research.sol_molmo_single_episode",
    "vision.grounded_planner",
    "vision.molmo_worker",
    "vision.execution",
    "simulation.mujoco.backend",
    "simulation.mujoco.episode_evaluator",
)
BASELINE_SHA = "4ee75e26c90dc6e6e503fea59cf04524f13ddd96238c90189480487d4bccaa8d"
ARCHIVE_SHA = "6fde448feedd3748a0943f28d01197dc66050bd65f4625767af8f3a97294061d"
ENTRY_PATHS = (
    "src/cloud_edge_robot_arm/research/sol_molmo_offline_regression.py",
    "scripts/run_v3_marker_offline_regression.py",
    "tests/test_sol_molmo_offline_regression.py",
)
_PROTECTED_INPUTS = {
    Path("/home/ningyd/文档/ChatGPT/BIGsmall"),
    Path("/home/ningyd/.codex/worktrees/molmo-absence-protocol-1472/BIGsmall"),
    PROCESS / "v3-baseline",
    PLAN.parent,
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(path: Path) -> Any:
    return json.loads(path.read_bytes())


def _write(path: Path, value: Any) -> None:
    path = output_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(
            value,
            stream,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
            default=lambda x: x.isoformat(),
        )
        stream.write("\n")


def _contained(root: Path, path: Path) -> Path:
    root, path = root.resolve(), path.resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError("FROZEN_PATH_ESCAPE")
    return path


def output_path(path: Path, protected: list[Path] = ()) -> Path:
    """在创建文件或目录前统一验证批准根、输入重叠及已有路径。"""
    path = path.resolve()
    if any(
        path.is_relative_to(p.resolve()) or p.resolve().is_relative_to(path)
        for p in (*_PROTECTED_INPUTS, *protected)
    ):
        raise ValueError("PROTECTED_OUTPUT_PATH")
    roots = (Path("/tmp"), PROCESS / "offline-regression")
    if not any(path != root.resolve() and path.is_relative_to(root.resolve()) for root in roots):
        raise ValueError("OUTPUT_ROOT_NOT_AUTHORIZED")
    if path.exists():
        raise FileExistsError(str(path))
    return path


def new_output(path: Path, protected: list[Path]) -> Path:
    """独占创建输出，禁止覆盖历史实验或已有运行。"""
    path = output_path(path, protected)
    path.mkdir(parents=True, exist_ok=False)
    return path


def _read_baseline(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if _sha(data) != BASELINE_SHA:
        raise ValueError("BASELINE_SNAPSHOT_HASH_MISMATCH")
    snapshot = json.loads(data)
    members = snapshot["source_mapping"]
    if (
        len(members) != 594
        or len({r["archive_member"] for r in members}) != 594
        or sum(r["archive_member"].startswith("source/") for r in members) != 591
        or snapshot["source_archive_sha256"] != ARCHIVE_SHA
    ):
        raise ValueError("BASELINE_MEMBER_SET_MISMATCH")
    return snapshot


def _archive_path(snapshot: dict[str, Any], baseline: Path) -> Path:
    local = baseline.parent / "source-bytes.local.tar.gz"
    return local if local.is_file() else Path(snapshot["source_archive"])


def _verify_archive(snapshot: dict[str, Any], archive: Path) -> None:
    if _sha(archive.read_bytes()) != ARCHIVE_SHA:
        raise ValueError("BASELINE_ARCHIVE_HASH_MISMATCH")
    expected = {r["archive_member"]: r for r in snapshot["source_mapping"]}
    seen = set()
    with tarfile.open(archive) as source:
        for member in source:
            if not member.isfile() or member.name not in expected or member.name in seen:
                raise ValueError("BASELINE_ARCHIVE_MEMBER_SET_MISMATCH")
            data = source.extractfile(member).read()
            row = expected[member.name]
            if _sha(data) != row["sha256"] or len(data) != row["bytes"]:
                raise ValueError("BASELINE_ARCHIVE_MEMBER_HASH_MISMATCH")
            seen.add(member.name)
    if seen != set(expected):
        raise ValueError("BASELINE_ARCHIVE_MEMBER_SET_MISMATCH")


def _capture_inventory(paths: list[Path]) -> dict[str, Any]:
    result = {}
    for path in paths:
        if path.is_symlink():
            raise ValueError("SOURCE_INVENTORY_CHANGED:" + str(path))
        data = path.read_bytes()
        result[str(path.absolute())] = {
            "sha256": _sha(data),
            "bytes": len(data),
            "resolved_path": str(path.resolve()),
        }
    return result


def _verify_inventory(inventory: dict[str, Any]) -> None:
    for name, expected in inventory.items():
        try:
            current = _capture_inventory([Path(name)])[name]
        except (OSError, ValueError) as error:
            raise ValueError("SOURCE_INVENTORY_CHANGED:" + name) from error
        if current != expected:
            raise ValueError("SOURCE_INVENTORY_CHANGED:" + name)


@dataclass(frozen=True)
class FrozenCase:
    """每次读取都检查冻结清单中的路径、长度与SHA。"""

    root: Path
    files: dict[str, dict[str, Any]]
    row: dict[str, Any]

    def read(self, name: str) -> bytes:
        """拒绝越界、清单外或字节改变的文件。"""
        path = _contained(self.root, self.root / name)
        entry = self.files.get(name)
        if entry is None or path.relative_to(self.root.resolve()).as_posix() != name:
            raise ValueError("FROZEN_FILE_NOT_BOUND")
        data = path.read_bytes()
        if _sha(data) != entry["sha256"] or len(data) != entry["bytes"]:
            raise ValueError("FROZEN_FILE_HASH_MISMATCH:" + name)
        return data

    def json(self, name: str) -> Any:
        """解析已验SHA的JSON。"""
        return json.loads(self.read(name))


@dataclass(frozen=True)
class V3Manifest:
    """保留全部40例、589帧及固定27例分母。"""

    root: Path
    baseline: Path
    cases: dict[str, FrozenCase]
    frames: list[dict[str, Any]]
    verified_files: int


def load_v3_manifest(v3_root: Path, baseline_snapshot: Path) -> V3Manifest:
    """严格核对Astra固定的清单与所有原始输入，不接受新的成功子集。"""
    tables = {}
    for name, digest in PLAN_DIGESTS.items():
        data = (PLAN / name).read_bytes()
        if _sha(data) != digest:
            raise ValueError("PLAN_INPUT_HASH_MISMATCH:" + name)
        tables[name] = json.loads(data)
    baseline = _read_baseline(baseline_snapshot)
    archive = _archive_path(baseline, baseline_snapshot)
    _verify_archive(baseline, archive)
    _PROTECTED_INPUTS.update(
        (v3_root.resolve(), baseline_snapshot.parent.resolve(), archive.resolve())
    )
    rows = tables["case-inputs.json"]
    bindings = {r["case"]: r for r in tables["episode-manifest-bindings.json"]}
    if len(rows) != 40 or len(bindings) != 40 or len({r["case"] for r in rows}) != 40:
        raise ValueError("V3_CASE_COVERAGE_MISMATCH")
    if {r["case"] for r in rows if r["v3_component_success"]} != set(SUCCESS_CASES):
        raise ValueError("V3_SUCCESS_DENOMINATOR_MISMATCH")
    cases, count = {}, 0
    for row in rows:
        name = row["case"]
        folder = _contained(v3_root, v3_root / name)
        data = (folder / "evidence-manifest.json").read_bytes()
        if _sha(data) != bindings[name]["sha256"]:
            raise ValueError("EPISODE_MANIFEST_HASH_MISMATCH:" + name)
        entries = json.loads(data)["files"]
        files = {e["path"]: e for e in entries}
        if len(files) != len(entries) or len(files) != bindings[name]["files"]:
            raise ValueError("DUPLICATE_OR_MISSING_MANIFEST_PATH")
        for entry in row["inputs"]:
            relative = (
                Path(entry["absolute_path"])
                .relative_to(Path(bindings[name]["absolute_path"]).parent)
                .as_posix()
            )
            if relative == "evidence-manifest.json":
                continue
            if relative in files and files[relative]["sha256"] != entry["sha256"]:
                raise ValueError("CASE_INPUT_HASH_CONFLICT")
            files[relative] = entry | {"path": relative}
        case = FrozenCase(folder, files, row)
        for relative in files:
            case.read(relative)
            count += 1
        cases[name] = case
    frames = tables["frame-inputs.json"]
    frame_keys = set()
    for row in frames:
        case = cases[row["case"]]
        parent = Path(bindings[row["case"]]["absolute_path"]).parent
        for entry in row["files"]:
            name = Path(entry["absolute_path"]).relative_to(parent).as_posix()
            if case.files[name]["sha256"] != entry["sha256"]:
                raise ValueError("FRAME_INPUT_HASH_CONFLICT")
        frame_keys.add((row["case"], row["label"]))
    actual = {
        (name, (Path(p).parent.name if p.startswith("component/") else Path(p).parent.as_posix()))
        for name, case in cases.items()
        for p in case.files
        if p.endswith("/observation.json")
    }
    if len(frames) != 589 or len(frame_keys) != 589 or frame_keys != actual:
        raise ValueError("V3_FRAME_COVERAGE_MISMATCH")
    return V3Manifest(v3_root.resolve(), baseline_snapshot.resolve(), cases, frames, count)


class FrozenPointProvider:
    """仅回放四份同RGB、同校准、同阶段、同query的原生模型原文。"""

    def __init__(self, case: FrozenCase) -> None:
        self.case = case
        self.replay_calls = 0
        self.model_loads_started = 0
        self.generation_calls_started = 0
        self.generation_calls_completed = 0
        self.records: list[dict[str, Any]] = []
        self._phase_identities: dict[str, tuple[Any, ...]] = {}

    def point(self, observation: RGBDObservation, phrase: str) -> BoundPointResult:
        """所有检查通过后才消费一次本地输出；新观测checksum明确重新绑定。"""
        if self.replay_calls >= 4:
            raise ValueError("FROZEN_POINT_BUDGET_EXHAUSTED")
        i = self.replay_calls + 1
        prefix = f"raw/molmo/request-{i:04d}/"
        started = self.case.json(prefix + "started.json")
        result = self.case.json(prefix + "result.json")
        phase = "before" if i <= 2 else "component/frames/post-cloud"
        identity = (
            observation.observation_id,
            observation.frame_id,
            observation.checksum_sha256,
            observation.captured_at,
        )
        if i in (2, 4) and self._phase_identities[phase] != identity:
            raise ValueError("FROZEN_POINT_PHASE_IDENTITY_MISMATCH")
        if i == 3:
            before = self._phase_identities["before"]
            if (
                any(a == b for a, b in zip(identity[:3], before[:3], strict=True))
                or identity[3] <= before[3]
            ):
                raise ValueError("FROZEN_POINT_PHASE_REFRESH_REQUIRED")
        meta = self.case.json(phase + "/observation.json")
        rgb_sha = observation.evidence()["rgb_sha256"]
        query_sha = _sha(phrase.encode())
        if any(
            (
                started["phrase"] != phrase,
                started["query_sha256"] != query_sha,
                started["rgb_sha256"] != rgb_sha,
                meta["rgb_sha256"] != rgb_sha,
                started["observation_checksum"] != meta["checksum_sha256"],
            )
        ):
            raise ValueError("FROZEN_POINT_INPUT_MISMATCH")
        values = observation.model_dump(mode="json")
        for key in (
            "width",
            "height",
            "intrinsics",
            "camera_to_world",
            "calibration_version",
            "sim_time_s",
            "depth_convention",
            "source",
            "scene_id",
        ):
            if values[key] != meta[key]:
                raise ValueError("FROZEN_POINT_CALIBRATION_OR_PHASE_MISMATCH:" + key)
        for key in ("observation_checksum", "rgb_sha256", "query_sha256"):
            if result[key] != started[key]:
                raise ValueError("FROZEN_POINT_RESULT_BINDING_MISMATCH")
        raw = self.case.read(prefix + "raw-response.txt").decode("utf-8")
        if _sha(raw.encode()) != result["raw_sha256"]:
            raise ValueError("FROZEN_POINT_RAW_HASH_MISMATCH")
        native = parse_native_point(raw)
        if json.loads(json.dumps(asdict(native))) != result["native"]:
            raise ValueError("FROZEN_POINT_NATIVE_RESULT_MISMATCH")
        record = {
            "scope": SCOPE,
            "replay_call": i,
            "phase": phase,
            "phase_identity": [*identity[:3], identity[3].isoformat()],
            "historical_source": str(self.case.root / prefix),
            "historical_observation_checksum": started["observation_checksum"],
            "current_observation_checksum": observation.checksum_sha256,
            "rgb_sha256": rgb_sha,
            "query_sha256": query_sha,
            "raw_sha256": result["raw_sha256"],
            "output_tokens": result["output_tokens"],
            "reached_cap": result["reached_cap"],
            "reused_historical_provenance": result,
        }
        self.records.append(record)
        if i in (1, 3):
            self._phase_identities[phase] = identity
        self.replay_calls += 1
        return BoundPointResult(native, observation.checksum_sha256, rgb_sha, query_sha, record)


class FrozenCloudReplayAdapter(RGBDPlannerAdapter):
    """保持原云请求生成及解析，唯一HTTP边界只读返回完全匹配的冻结JSON。"""

    def __init__(self, case: FrozenCase, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.case = case
        self.replay_calls = 0
        self.records: list[dict[str, Any]] = []

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        self._validate_sol_identity()
        if self.replay_calls:
            raise ValueError("FROZEN_CLOUD_BUDGET_EXHAUSTED")
        frozen = self.case.json("raw/cloud/request.json")
        if path != self.chat_path or body != frozen:
            self.records.append(
                {
                    "error": "FROZEN_CLOUD_REQUEST_MISMATCH",
                    "actual_path": path,
                    "expected_path": self.chat_path,
                    "actual_body": body,
                    "expected_body": frozen,
                }
            )
            raise ValueError("FROZEN_CLOUD_REQUEST_MISMATCH")
        response_bytes = self.case.read("raw/cloud/response.json")
        self.records.append(
            {
                "scope": SCOPE,
                "path": path,
                "actual_body_sha256": _sha(json.dumps(body, sort_keys=True).encode()),
                "historical_request_sha256": _sha(self.case.read("raw/cloud/request.json")),
                "historical_response_sha256": _sha(response_bytes),
            }
        )
        self.replay_calls += 1
        return copy.deepcopy(json.loads(response_bytes))


_GUARD_LOCK = threading.RLock()
_ACTIVE_GUARDS: list[Any] = []
_NETWORK_METHODS: list[Any] = []


def _reject_network(event: str) -> None:
    with _GUARD_LOCK:
        active = tuple(_ACTIVE_GUARDS)
        for guard in active:
            guard.attempts.append({"event": event})
    if active:
        raise RuntimeError("OFFLINE_NETWORK_DENIED:" + event)


def _deny_network(event: str, args: tuple[Any, ...]) -> None:
    if event.startswith("socket.") and event != "socket.__new__" or event == "urllib.Request":
        _reject_network(event)


sys.addaudithook(_deny_network)


class NetworkDenyGuard:
    """独立于两个回放器，在Python网络调用到达系统前拒绝并留证。"""

    def __init__(self) -> None:
        self.attempts: list[dict[str, Any]] = []

    def __enter__(self) -> NetworkDenyGuard:
        with _GUARD_LOCK:
            if self in _ACTIVE_GUARDS:
                raise RuntimeError("OFFLINE_GUARD_REENTRY")
            if not _ACTIVE_GUARDS:
                owners = (
                    (
                        socket.socket,
                        (
                            "connect",
                            "connect_ex",
                            "send",
                            "sendall",
                            "sendto",
                            "sendmsg",
                            "sendfile",
                        ),
                    ),
                    (
                        ssl.SSLSocket,
                        (
                            "connect",
                            "connect_ex",
                            "send",
                            "sendall",
                            "write",
                            "do_handshake",
                            "sendfile",
                        ),
                    ),
                    (
                        socket,
                        (
                            "getaddrinfo",
                            "gethostbyname",
                            "gethostbyname_ex",
                            "gethostbyaddr",
                            "getnameinfo",
                        ),
                    ),
                )
                for owner, names in owners:
                    for name in names:
                        original = getattr(owner, name, None)
                        if original is None:
                            continue

                        def denied(
                            *args: Any,
                            _original: Any = original,
                            _event: str = "python.network." + name,
                            **kwargs: Any,
                        ) -> Any:
                            _reject_network(_event)
                            return _original(*args, **kwargs)

                        _NETWORK_METHODS.append((owner, name, original))
                        setattr(owner, name, denied)
            _ACTIVE_GUARDS.append(self)
        return self

    def __exit__(self, *args: Any) -> None:
        with _GUARD_LOCK:
            _ACTIVE_GUARDS.remove(self)
            if not _ACTIVE_GUARDS:
                for owner, name, original in reversed(_NETWORK_METHODS):
                    setattr(owner, name, original)
                _NETWORK_METHODS.clear()


def validate_source_imports(root: Path, expected: dict[str, str]) -> dict[str, Any]:
    """核对已加载模块的真实位置及字节，防止共享venv导入其它checkout。"""
    modules = {}
    for suffix in SOURCE_MODULES:
        module = importlib.import_module("cloud_edge_robot_arm." + suffix)
        path = Path(module.__file__).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("SOURCE_IMPORT_MISMATCH:" + str(path))
        relative = path.relative_to(root.resolve()).as_posix()
        digest = _sha(path.read_bytes())
        if relative not in expected or expected[relative] != digest:
            raise ValueError("SOURCE_IMPORT_MISMATCH:" + relative)
        modules[suffix] = {"path": str(path), "sha256": digest}
    return {
        "executable": sys.executable,
        "cwd": os.getcwd(),
        "sys_path": sys.path[:4],
        "modules": modules,
        "argv": sys.argv,
        "environment": {
            k: os.environ.get(k)
            for k in (
                "MUJOCO_GL",
                "PYOPENGL_PLATFORM",
                "MUJOCO_EGL_DEVICE_ID",
                "EGL_DEVICE_ID",
                "LIBGL_ALWAYS_SOFTWARE",
            )
        },
        "gl_vendor_device": "UNKNOWN_NOT_QUERIED",
    }


def _expected_sources(manifest: V3Manifest) -> dict[str, str]:
    snapshot = _read_baseline(manifest.baseline)
    sources = {
        r["archive_member"][7:]: r["sha256"]
        for r in snapshot["source_mapping"]
        if r["archive_member"].startswith("source/")
    }
    # 本轮唯一批准的既有生产源码变动；其余591个基线成员保持原字节。
    sources["src/cloud_edge_robot_arm/vision/pose_markers.py"] = (
        "e6eb27d2b2c19481054c2b834d2ece29a53d747fff26c82d1dd6246ddf71ff40"
    )
    for relative, digest in sources.items():
        if _sha((ROOT / relative).read_bytes()) != digest:
            raise ValueError("SOURCE_INPUT_HASH_MISMATCH:" + relative)
    return sources


def _source_inventory(manifest: V3Manifest) -> dict[str, Any]:
    sources = _expected_sources(manifest)
    snapshot = _read_baseline(manifest.baseline)
    paths = [ROOT / name for name in sources]
    for row in snapshot["source_mapping"]:
        if not row["archive_member"].startswith("source/"):
            path = Path(row["original_path"])
            data = path.read_bytes()
            if _sha(data) != row["sha256"] or len(data) != row["bytes"]:
                raise ValueError("EXTERNAL_SOURCE_INPUT_HASH_MISMATCH:" + str(path))
            paths.append(path)
    paths.extend((manifest.baseline, _archive_path(snapshot, manifest.baseline)))
    paths.extend(ROOT / name for name in ENTRY_PATHS)
    return _capture_inventory(paths)


def _validated_component_scene(case: FrozenCase) -> dict[str, Any] | None:
    from cloud_edge_robot_arm.research.sol_molmo_scenarios import physical_component_scenario

    assignment = case.json("scene-assignment.json")
    policy = case.json("role-binding.json")["edge_policy"]
    job = case.json("worker/job.json")
    seed, split = assignment["seed"], case.row["split"]
    if (
        type(seed) is not int
        or seed != case.row["seed"]
        or seed != job["seed"]
        or assignment["scenario_id"] != "S01_NORMAL_STATIC"
        or job["scenario_id"] != "S01_NORMAL_STATIC"
    ):
        raise ValueError("COMPONENT_SCENE_JOB_BINDING_MISMATCH")
    if split == "fixed":
        if (
            assignment["scene_sampling"] != "FIXED_REGISTERED_SCENE"
            or assignment["independent_random_scene"] is not False
            or "component_scene" in assignment
            or "component_scene" in policy
        ):
            raise ValueError("COMPONENT_SCENE_FIXED_MUST_BE_ABSENT")
        scene = None
    elif split in {"development", "held-out"}:
        scene = assignment.get("component_scene")
        if (
            assignment["scene_sampling"] != "SEEDED_COMPONENT_POSE_V1"
            or assignment["independent_random_scene"] is not True
            or not isinstance(scene, dict)
            or scene != policy.get("component_scene")
            or scene.get("seed") != seed
            or scene.get("split") != split
        ):
            raise ValueError("COMPONENT_SCENE_SEEDED_BINDING_MISMATCH")
    else:
        raise ValueError("COMPONENT_SCENE_UNKNOWN_SPLIT")
    try:
        physical_component_scenario(seed, scene)
    except ValueError as error:
        raise ValueError("COMPONENT_SCENE_PHYSICAL_CONFIG_MISMATCH") from error
    return scene


def build_frozen_worker(
    case: FrozenCase, manifest: V3Manifest, output: Path
) -> tuple[Any, Any, FrozenPointProvider, FrozenCloudReplayAdapter]:
    """使用真实两阶段planner和当前设备绑定，不创建模型或读取任何凭据。"""
    from cloud_edge_robot_arm.vision.grounded_planner import (
        GroundingTaskDescriptor,
        MolmoGroundedPlannerAdapter,
    )
    from cloud_edge_robot_arm.vision.molmo_worker import MolmoWorkerPlanner, make_worker_binding
    from cloud_edge_robot_arm.vision.role_models import (
        RoleProviderSnapshot,
        cloud_request_settings,
        configuration_hash,
    )

    evidence = case.json("planning/planning-stage-01.json")["attempts"][0]["draft"][
        "observation_evidence"
    ]
    config = dict(evidence["cloud_model_snapshot"])
    endpoint_hash = config.pop("endpoint_hash")
    endpoints = [
        e
        for e in ("https://api.openai.com", "https://api.openai.com/v1")
        if _sha(e.encode()) == endpoint_hash
    ]
    if len(endpoints) != 1:
        raise ValueError("HISTORICAL_ENDPOINT_BINDING_MISMATCH")
    snapshot = ModelConfigSnapshot(**config, endpoint=endpoints[0])
    if snapshot.digest() != evidence["cloud_model_snapshot_hash"]:
        raise ValueError("HISTORICAL_MODEL_SNAPSHOT_MISMATCH")
    historical_binding = case.json("role-binding.json")
    role = RoleProviderSnapshot(**historical_binding["bundle"]["cloud_snapshot"])
    for name, digest in role.source_hashes.items():
        if _sha(_contained(ROOT, ROOT / name).read_bytes()) != digest:
            raise ValueError("HISTORICAL_CLOUD_SOURCE_MISMATCH:" + name)
    cloud = FrozenCloudReplayAdapter(
        case,
        base_url=snapshot.endpoint,
        model=snapshot.model,
        provider=snapshot.provider,
        api_key="",
        timeout_s=snapshot.timeout_s,
        allow_paid=True,
        chat_path="/chat/completions"
        if snapshot.endpoint.endswith("/v1")
        else "/v1/chat/completions",
        model_snapshot=snapshot,
        cost_ledger=CostLedger(),
    )
    cloud.role_config_version = 2
    cloud.role_snapshot = role
    if configuration_hash(cloud_request_settings(cloud)) != role.request_config_hash:
        raise ValueError("HISTORICAL_CLOUD_CONFIG_MISMATCH")
    assignment = case.json("scene-assignment.json")
    points = FrozenPointProvider(case)
    grounded = MolmoGroundedPlannerAdapter(
        point_provider=points,
        cloud=cloud,
        task=GroundingTaskDescriptor(
            instruction=assignment["instruction"],
            target_phrase="red block",
            destination_phrase="green region",
            target_label="red block",
        ),
        worker_owned_refresh=True,
        component_diagnostic=True,
        cloud_vision_fallback=assignment["cloud_vision_fallback"],
    )
    worker = MolmoWorkerPlanner(grounded, output=output / "planning")
    if (
        worker.role_config_version != 2
        or configuration_hash(cloud_request_settings(worker)) != role.request_config_hash
    ):
        raise ValueError("HISTORICAL_WORKER_CONFIG_MISMATCH")
    binding = make_worker_binding(
        worker,
        asset_manifest_sha256=historical_binding["edge_policy"]["perception_binding"][
            "asset_manifest_sha256"
        ],
        marker_family_id=assignment["marker_family_id"],
        component_diagnostic=True,
        component_scene=_validated_component_scene(case),
    )
    binding.validate(worker)
    _write(output / "role-binding.json", binding.evidence())
    return worker, binding, points, cloud


def run_frozen_component_case(case_id: str, manifest: V3Manifest, output: Path) -> dict[str, Any]:
    """从原SQLite worker入口重建合同并执行；失败同样保存完整原始证据。"""
    from cloud_edge_robot_arm.research.sol_molmo_single_episode import run_worker_episode

    if case_id not in SUCCESS_CASES:
        raise ValueError("CASE_NOT_IN_ORIGINAL_27")
    new_output(output, [manifest.root, Path(_read_baseline(manifest.baseline)["source_root"])])
    sources = _expected_sources(manifest)
    receipt = validate_source_imports(ROOT, sources)
    receipt["complete_source_inventory"] = _source_inventory(manifest)
    for name in ENTRY_PATHS:
        receipt.setdefault("offline_entry_sources", {})[name] = _sha((ROOT / name).read_bytes())
    _write(output / "source-receipt.json", receipt)
    result: dict[str, Any] = {
        "scope": SCOPE,
        "case": case_id,
        "component_success": False,
        "new_paid_requests": 0,
        "formal_research": "NOT_EVALUATED",
    }
    case = manifest.cases[case_id]
    points = cloud = None
    with NetworkDenyGuard() as guard:
        try:
            planner, binding, points, cloud = build_frozen_worker(case, manifest, output)
            assignment = case.json("scene-assignment.json")
            _write(output / "scene-assignment.json", assignment)
            run_worker_episode(assignment, output, result, planner=planner, binding=binding)
            episode = result.get("outcome", {})
            result["component_success"] = all(
                (
                    result.get("worker_status") == "SUCCEEDED",
                    episode.get("diagnostic_complete") is True,
                    episode.get("physical_success") is True,
                    episode.get("executed_actions") == 8,
                    episode.get("terminal_reason") is None,
                    len(episode.get("safety_checks", [])) == 16,
                    points.replay_calls == 4,
                    cloud.replay_calls == 1,
                    planner.cost_ledger.snapshot().cloud_model_requests == 0,
                    not guard.attempts,
                )
            )
        except Exception as error:
            import traceback

            result.update(
                error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc()
            )
        finally:
            result["network_attempts"] = guard.attempts
            if points is not None:
                _write(output / "replay/points.json", points.records)
                result["point_replays"] = points.replay_calls
                result["model_loads_started"] = points.model_loads_started
                result["generation_calls_started"] = points.generation_calls_started
                result["generation_calls_completed"] = points.generation_calls_completed
            if cloud is not None:
                _write(output / "replay/cloud.json", cloud.records)
                result["cloud_replays"] = cloud.replay_calls
            try:
                _verify_inventory(receipt["complete_source_inventory"])
                _expected_sources(manifest)
                after = validate_source_imports(ROOT, sources)
                if after["modules"] != receipt["modules"]:
                    raise ValueError("SOURCE_IMPORT_CHANGED_AFTER")
                result["source_bytes_unchanged_after"] = True
            except (OSError, ValueError) as error:
                result.update(
                    component_success=False,
                    source_bytes_unchanged_after=False,
                    integrity_failure=str(error),
                    status="FAILED",
                )
            _write(output / "result.json", result)
            entries = [
                {
                    "path": p.relative_to(output).as_posix(),
                    "bytes": p.stat().st_size,
                    "sha256": _sha(p.read_bytes()),
                }
                for p in sorted(output.rglob("*"))
                if p.is_file()
            ]
            _write(output / "evidence-manifest.json", {"scope": SCOPE, "files": entries})
    return result


def load_observation(case: FrozenCase, folder: str) -> RGBDObservation:
    """从原始RGB/深度/valid bytes重建并保留原时间和checksum。"""
    meta = case.json(folder + "/observation.json")
    values = {k: meta[k] for k in RGBDObservation.model_fields if k in meta}
    for field, name in (
        ("rgb_png_base64", "rgb.png"),
        ("depth_float32_base64", "depth.f32"),
        ("valid_mask_base64", "valid_mask.u8"),
    ):
        values[field] = base64.b64encode(case.read(folder + "/" + name)).decode()
    return RGBDObservation.model_validate(values)


def _historical_clock(obs: RGBDObservation) -> Any:
    from cloud_edge_robot_arm.vision import tracking

    class Clock(type(obs.captured_at)):
        @classmethod
        def now(cls, tz: Any = None) -> Any:
            return obs.captured_at + timedelta(milliseconds=100)

    return patch.object(tracking, "datetime", Clock)


def audit_child(manifest: V3Manifest, output: Path, source_root: Path) -> dict[str, Any]:
    """仅供独立历史审计进程使用显式历史时钟，绝不进入新闭环执行。"""
    from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest
    from cloud_edge_robot_arm.contracts import RobotState
    from cloud_edge_robot_arm.research.sol_molmo_components import (
        _ground_component,
        _visible_support,
    )
    from cloud_edge_robot_arm.vision.marker_families import marker_family
    from cloud_edge_robot_arm.vision.planner import ground_observation
    from cloud_edge_robot_arm.vision.point_association import associate_target_point
    from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker
    from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker

    output_path(output, [manifest.root, source_root])
    _PROTECTED_INPUTS.add(source_root.resolve())
    baseline = _read_baseline(manifest.baseline)
    expected = {
        r["archive_member"][7:]: r["sha256"]
        for r in baseline["source_mapping"]
        if r["archive_member"].startswith("source/")
    }
    if source_root == ROOT:
        expected = _expected_sources(manifest)
    imports = validate_source_imports(source_root, expected)
    rows = []
    for name, case in manifest.cases.items():
        assignment = case.json("scene-assignment.json")
        family = marker_family(assignment["marker_family_id"])
        registration = PoseMarkerRegistration(
            marker_id=family.marker_id,
            dictionary=family.dictionary,
            marker_size_m=family.marker_size_m,
            marked_asset_sha256=family.asset_sha256,
        )
        episode = case.json("component/episode.json")
        stage1 = case.json("planning/planning-stage-01.json")["attempts"][0]["draft"][
            "observation_evidence"
        ]
        stage2_path = "planning/planning-stage-02.json"
        evidence, tracker, initial_reason = None, None, None
        fresh = (
            load_observation(case, "component/frames/post-cloud")
            if "component/frames/post-cloud/observation.json" in case.files
            else load_observation(case, "before")
        )
        try:
            if stage2_path not in case.files:
                raise ValueError("HISTORICAL_POST_CLOUD_GROUNDING_NOT_RECORDED")
            evidence = case.json(stage2_path)["attempts"][0]["draft"]["observation_evidence"]
            if "original_pixel_target" not in evidence:
                # 失败例仍用原像素、原规则重算，失败理由保留，不编造tracker。
                target = associate_target_point(
                    fresh, tuple(stage1["native_original_pixel_target"]), target_phrase="red block"
                )
                request = InitialPlanningRequest(
                    request_id="frozen-audit",
                    user_instruction=assignment["instruction"],
                    observation=fresh,
                )
                measured = ground_observation(
                    request,
                    fresh,
                    target_pixel=target.pixel,
                    destination_pixel=tuple(stage1["native_original_pixel_destination"]),
                    target_label="red block",
                    grasp_profile=assignment["grasp_profile"],
                    evidence=dict(stage1),
                )
                evidence = dict(stage1) | measured.evidence
            with _historical_clock(fresh):
                tracker = OpenCVTargetTracker(fresh, evidence)
        except (ValueError, KeyError) as error:
            initial_reason = str(error)
        for frame in (f for f in manifest.frames if f["case"] == name):
            label = frame["label"]
            folder = label if label in {"before", "after"} else "component/frames/" + label
            obs = load_observation(case, folder)
            marker = detect_pose_marker(obs, registration, corner_refinement="SUBPIX")
            row = {
                "case": name,
                "label": label,
                "marker": asdict(marker),
                "historical_marker_status": frame["v3_marker_status"],
                "historical_terminal_reason": case.row["v3_terminal_reason"],
            }
            if tracker is None:
                row["geometry"] = {
                    "status": "INITIAL_GROUNDING_UNAVAILABLE",
                    "current_reason": initial_reason,
                    "historical_reason": case.row["v3_terminal_reason"],
                }
            else:
                with _historical_clock(obs):
                    target, target_reason = tracker._geometry(
                        obs, tracker.target_color, target=True
                    )
                    region, region_reason = tracker._geometry(
                        obs, tracker.destination_color, target=False, occlusion_geometry=target
                    )
                    geometry = {
                        "status": "GEOMETRY_EVALUATED",
                        "target_complete": target is not None,
                        "region_complete": region is not None,
                        "target_reason": target_reason,
                        "region_reason": region_reason,
                    }
                    for key, color, reference in (
                        ("target_support", tracker.target_color, None),
                        ("region_support", tracker.destination_color, tracker.destination["mask"]),
                    ):
                        try:
                            _, support = _visible_support(obs, color, reference_mask=reference)
                            geometry[key] = support
                        except ValueError as error:
                            geometry[key] = {"error": str(error)}
                        except RuntimeError as error:
                            geometry[key] = {"error": str(error)}
                    action = next(
                        (
                            a
                            for i, a in enumerate(episode["actions"])
                            if label == f"pre-{i:02d}-{a['skill'].lower()}"
                        ),
                        None,
                    )
                    if action is None or "state_before" not in action.get(
                        "controller_result", {}
                    ).get("action_result", {}):
                        geometry["action_semantics"] = (
                            "ACTION_STATE_NOT_RECORDED"
                            if label.startswith("pre-")
                            else "NO_PENDING_ACTION"
                        )
                    else:
                        state = RobotState.model_validate(
                            action["controller_result"]["action_result"]["state_before"]
                        )
                        try:
                            _, grounding = _ground_component(
                                obs, tracker, evidence, family.family_id, action["skill"], state
                            )
                            geometry.update(action_semantics="ACCEPTED", grounding=grounding)
                        except (ValueError, RuntimeError) as error:
                            geometry.update(
                                action_semantics="REJECTED", grounding_reason=str(error)
                            )
                    row["geometry"] = geometry
            rows.append(row)
    result = {
        "scope": "HISTORICAL_FRAME_COUNTERFACTUAL_AUDIT",
        "source": imports,
        "rows": rows,
        "frames": len(rows),
        "geometry_status_counts": dict(Counter(r["geometry"]["status"] for r in rows)),
    }
    _write(output, result)
    return result


def audit_frozen_frames(manifest: V3Manifest, output: Path) -> dict[str, Any]:
    """在两个独立进程运行归档V3与当前解码器，配对全部589帧。"""
    new_output(output, [manifest.root])
    snapshot = _read_baseline(manifest.baseline)
    archive = _archive_path(snapshot, manifest.baseline)
    _verify_archive(snapshot, archive)
    extracted = Path(tempfile.mkdtemp(prefix="bigsmall-v3-source-"))
    expected = {r["archive_member"]: r for r in snapshot["source_mapping"]}
    with tarfile.open(archive) as source:
        for member in source:
            if member.name not in expected or not member.isfile():
                raise ValueError("BASELINE_ARCHIVE_MEMBER_MISMATCH")
            content = source.extractfile(member).read()
            if (
                _sha(content) != expected[member.name]["sha256"]
                or len(content) != expected[member.name]["bytes"]
            ):
                raise ValueError("BASELINE_ARCHIVE_MEMBER_HASH_MISMATCH")
            destination = _contained(extracted, extracted / member.name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
    driver = ROOT / "scripts/run_v3_marker_offline_regression.py"
    for label, source_root in (("v3", extracted / "source"), ("current", ROOT)):
        environment = os.environ | {
            "PYTHONPATH": str(source_root / "src") + os.pathsep + str(source_root),
            "PYTHONDONTWRITEBYTECODE": "1",
            "MUJOCO_GL": "egl",
        }
        command = [
            sys.executable,
            str(driver),
            "audit-child",
            "--v3-root",
            str(manifest.root),
            "--baseline",
            str(manifest.baseline),
            "--output",
            str(output / (label + ".json")),
            "--audit-source",
            str(source_root),
        ]
        with output_path(output / (label + ".log")).open("xb") as log:
            process = subprocess.run(
                command, env=environment, stdout=log, stderr=subprocess.STDOUT, check=False
            )
        _write(
            output / (label + "-exit.json"), {"command": command, "exit_code": process.returncode}
        )
        if process.returncode:
            raise RuntimeError("FRAME_AUDIT_CHILD_FAILED:" + label)
    old, current = _json(output / "v3.json"), _json(output / "current.json")
    pairs = []
    for a, b in zip(old["rows"], current["rows"], strict=True):
        if (a["case"], a["label"]) != (b["case"], b["label"]):
            raise ValueError("AUDIT_PAIR_MISMATCH")
        geometry = b["geometry"]
        new_rejection = (
            geometry.get("action_semantics") == "REJECTED"
            and a["geometry"].get("action_semantics") == "ACCEPTED"
        )
        classification = (
            "NEW_GROUNDING_REJECTION"
            if new_rejection
            else (
                "INITIAL_GROUNDING_UNAVAILABLE"
                if geometry["status"] == "INITIAL_GROUNDING_UNAVAILABLE"
                else "COMPLETE_GEOMETRY_TAKES_OVER"
                if geometry.get("target_complete")
                else "ACCEPTED_STAGE_FEEDBACK"
                if geometry.get("action_semantics") == "ACCEPTED"
                else "DIAGNOSTIC_OR_NON_ACTION_FRAME"
            )
        )
        pairs.append(
            {
                "case": b["case"],
                "label": b["label"],
                "classification": classification,
                "marker_changed": a["marker"] != b["marker"],
                "old_marker_status": a["marker"]["status"],
                "new_marker_status": b["marker"]["status"],
                "new_rejection": new_rejection,
            }
        )
    result = {
        "scope": "HISTORICAL_FRAME_COUNTERFACTUAL_AUDIT",
        "frames": len(pairs),
        "pairs": pairs,
        "new_grounding_rejections": sum(p["new_rejection"] for p in pairs),
        "classifications": dict(Counter(p["classification"] for p in pairs)),
        "not_dynamic_closed_loop_evidence": True,
        "archived_source": str(extracted / "source"),
    }
    _write(output / "summary.json", result)
    return result
