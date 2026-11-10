"""显式诊断 Molmo/OpenCV/云规划组合；默认空运行，始终禁止硬件派发。"""
# ruff: noqa: E402
# 直接调用脚本时须先建立当前工作区路径，再导入项目模块。

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))

from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession
from cloud_edge_robot_arm.vision.grounded_planner import (
    GroundingTaskDescriptor,
    MolmoGroundedPlannerAdapter,
    build_molmo_grounded_planner,
)
from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot
from cloud_edge_robot_arm.vision.molmo_pointing import (
    BoundPointResult,
    MolmoPointProvider,
    parse_native_point,
)
from cloud_edge_robot_arm.vision.planner import RGBDModelUnavailable, RGBDPlannerAdapter
from cloud_edge_robot_arm.vision.role_models import configuration_hash


def _read_bytes(path: Path, limit: int = 5_000_000) -> tuple[Any, bytes]:
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("input exceeds diagnostic limit")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate input JSON key")
            result[key] = value
        return result

    def reject(value: str) -> None:
        raise ValueError("nonfinite input JSON value")

    return json.loads(raw, object_pairs_hook=unique, parse_constant=reject), raw


def _write(path: Path, value: object) -> None:
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def _finalize(output: Path, report: dict[str, Any]) -> None:
    rows = []
    for path in sorted((output / "raw").rglob("*")):
        if path.is_file():
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            rows.append(
                {
                    "path": str(path.relative_to(output)),
                    "bytes": path.stat().st_size,
                    "sha256": digest,
                }
            )
    _write(output / "raw-manifest.local.json", {"files": rows})
    report["raw_manifest_sha256"] = hashlib.sha256(
        (output / "raw-manifest.local.json").read_bytes()
    ).hexdigest()
    _write(output / "report.json", report)


@contextmanager
def _admit_resources(model_directory: Path, lock_path: Path | None) -> Iterator[dict[str, Any]]:
    lock_path = lock_path or (
        model_directory.resolve().parents[2]
        / "zdtaichu5-9b-fp8-round473/research/.r468-r469-gpu.lock"
    )
    if not lock_path.is_file():
        raise ValueError("existing shared GPU lock is required")
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        apps = subprocess.check_output(
            ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True
        ).strip()
        free = int(
            subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                text=True,
            ).strip()
        )
        ram = (
            int(
                next(
                    row.split()[1]
                    for row in Path("/proc/meminfo").read_text().splitlines()
                    if row.startswith("MemAvailable:")
                )
            )
            * 1024
        )
        disk = shutil.disk_usage(model_directory).free
        if apps or free < 12000 or ram < 8 * 1024**3 or disk < 60 * 1024**3:
            raise RuntimeError("local resource admission failed")
        yield {
            "gpu_free_MiB": free,
            "ram_available_bytes": ram,
            "disk_free_bytes": disk,
            "foreign_compute_apps": False,
            "lock_path": str(lock_path),
        }


class _ReplayPoints:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = {}
        for row in rows:
            key = (row["observation_checksum"], row["query_sha256"])
            if key in self.rows:
                raise ValueError("duplicate replay point binding")
            self.rows[key] = row
        self.calls = 0

    def point(self, observation: Any, phrase: str) -> BoundPointResult:
        query = hashlib.sha256(phrase.encode()).hexdigest()
        row = self.rows.get((observation.checksum_sha256, query))
        if row is None or row["rgb_sha256"] != observation.evidence()["rgb_sha256"]:
            raise RuntimeError("replay point binding mismatch")
        self.calls += 1
        return BoundPointResult(
            parse_native_point(row["raw_text"]),
            observation.checksum_sha256,
            row["rgb_sha256"],
            query,
            {"evidence_scope": "REPLAY"},
        )


class _UnstartedPoints:
    def point(self, observation: Any, phrase: str) -> BoundPointResult:
        raise RuntimeError("native provider not started")


class _DiagnosticCloud(RGBDPlannerAdapter):
    def __init__(self, content: str | None = None) -> None:
        snapshot = ModelConfigSnapshot(
            provider="openai_compatible",
            model="not-invoked",
            endpoint="http://127.0.0.1:11434",
            weight_digest=None,
            quantization=None,
            image_size=(320, 240),
            generation_parameters={"temperature": 0, "num_predict": 512},
            timeout_s=30,
            grasp_profile="mujoco_upright_box_v2",
        )
        super().__init__(
            base_url=snapshot.endpoint,
            provider=snapshot.provider,
            model=snapshot.model,
            model_snapshot=snapshot,
            allow_paid=False,
        )
        self.content = content
        self.fixture_calls = 0

    def _request_visual(self, messages: Any, decision_schema: Any) -> dict[str, Any]:
        if self.content is None:
            raise RGBDModelUnavailable("real cloud deliberately not invoked")
        self.fixture_calls += 1
        return {"choices": [{"message": {"content": self.content}}]}


def _selected_cloud(args: argparse.Namespace, task: GroundingTaskDescriptor) -> Any:
    from cloud_edge_robot_arm.model_control.secret_store import create_secret_store
    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository

    if not args.profile_id or not args.model_store or not args.model_store.is_file():
        raise ValueError("paid mode requires an existing explicit model store and profile")
    service = ModelControlService(
        repository=SQLiteModelProfileRepository(args.model_store),
        secret_store=create_secret_store(args.model_store),
    )
    if not service.secret_store.has_secret(args.profile_id):
        raise ValueError("selected profile has no existing saved secret")
    return build_molmo_grounded_planner(
        service=service,
        profile_id=args.profile_id,
        point_provider=_UnstartedPoints(),
        task=task,
        grasp_profile="mujoco_upright_box_v2",
        allow_paid=True,
    )


def _fresh_capture() -> Any:
    from cloud_edge_robot_arm.vision.capture import capture_simulated_observation

    return capture_simulated_observation()


def _save_capture(folder: Path, request: InitialPlanningRequest, observation: Any) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    snapshot = request.model_copy(update={"observation": observation})
    _write(folder / "request.json", snapshot.model_dump(mode="json"))
    _write_bytes(folder / "rgb.png", base64.b64decode(observation.rgb_png_base64))
    _write_bytes(folder / "depth.f32", base64.b64decode(observation.depth_float32_base64))
    _write_bytes(folder / "valid_mask.u8", observation.valid_mask_bytes())


def main(argv: list[str] | None = None) -> int:
    """执行可审计诊断；--allow-paid 只能在另行授权的实际云端验证中使用。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, action="append", required=True)
    parser.add_argument("--task-descriptor", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("dry-run", "replay", "native"), default="dry-run")
    parser.add_argument("--profile-id")
    parser.add_argument("--model-store", type=Path)
    parser.add_argument("--model-directory", type=Path)
    parser.add_argument("--asset-manifest", type=Path)
    parser.add_argument("--replay-points", type=Path)
    parser.add_argument("--replay-cloud", type=Path)
    parser.add_argument("--generation-limit", type=int, default=8)
    parser.add_argument("--gpu-lock", type=Path)
    parser.add_argument("--capture-fresh", action="store_true")
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--post-cloud-revalidate", action="store_true")
    args = parser.parse_args(argv)
    report: dict[str, Any] = {
        "status": "NOT_STARTED",
        "execution_mode": args.mode.upper(),
        "model_loads_started": 0,
        "generation_calls_started": 0,
        "generation_calls_completed": 0,
        "paid_cloud_calls_started": 0,
        "post_cloud_revalidation_enabled": args.post_cloud_revalidate,
        "refresh_capture_calls_started": 0,
        "refresh_capture_calls_completed": 0,
        "api_fixture_calls": 0,
        "hardware_dispatch": False,
        "real_cloud_status": "NOT_PERFORMED",
        "physical_status": "NOT_PERFORMED",
        "formal_research_status": "NOT_PERFORMED",
        "attempts": [],
    }
    provider = None
    output_created = False
    paid_starts = []
    try:
        if len(args.request) != len(args.task_descriptor) or not 1 <= len(args.request) <= 4:
            raise ValueError("provide 1..4 matching request/descriptor pairs")
        pairs = []
        snapshots: list[tuple[str, bytes]] = []
        for index, (request_path, task_path) in enumerate(
            zip(args.request, args.task_descriptor, strict=True), 1
        ):
            request_data, request_raw = _read_bytes(request_path)
            task_data, task_raw = _read_bytes(task_path, 10000)
            request = InitialPlanningRequest.model_validate(request_data)
            task = GroundingTaskDescriptor.model_validate(task_data)
            snapshots += [
                (f"request-{index:02}.json", request_raw),
                (f"task-{index:02}.json", task_raw),
            ]
            if (
                request.observation is None and not (args.mode == "native" and args.capture_fresh)
            ) or request.user_instruction != task.instruction:
                raise ValueError("request/descriptor binding mismatch")
            pairs.append((request, task))
        if not 1 <= args.generation_limit <= 8 or 2 * len(pairs) > args.generation_limit:
            raise ValueError("native generation budget must cover at most8 bounded starts")
        if args.allow_paid and args.mode != "native":
            raise ValueError("paid flag is only valid for explicitly authorized native mode")
        if args.capture_fresh and args.mode != "native":
            raise ValueError("fresh sensor acquisition requires native mode")
        if args.post_cloud_revalidate and (
            args.mode != "native"
            or not args.capture_fresh
            or not args.allow_paid
            or len(pairs) != 1
            or args.generation_limit < 4
        ):
            raise ValueError(
                "post-cloud revalidation requires native fresh paid single-pair budget>=4"
            )
        if args.mode == "native" and (
            not args.model_directory
            or not args.model_directory.is_dir()
            or not args.asset_manifest
            or not args.asset_manifest.is_file()
        ):
            raise ValueError("native mode requires existing local assets")
        replay_cloud = None
        if args.mode == "replay":
            if not args.replay_points or not args.replay_cloud or len(pairs) != 1:
                raise ValueError("replay requires one explicitly bound fixture pair")
            point_data, point_raw = _read_bytes(args.replay_points)
            replay_cloud, cloud_raw = _read_bytes(args.replay_cloud)
            snapshots += [("replay-points.json", point_raw), ("replay-cloud.json", cloud_raw)]
            provider = _ReplayPoints(point_data)
            request, task = pairs[0]
            if replay_cloud[
                "observation_checksum"
            ] != request.observation.checksum_sha256 or replay_cloud[
                "task_descriptor_sha256"
            ] != configuration_hash(task.model_dump()):
                raise ValueError("replay cloud binding mismatch")
        adapters = [_selected_cloud(args, task) for _, task in pairs] if args.allow_paid else []
        args.output.mkdir(parents=True, exist_ok=False)
        output_created = True
        for name, raw_input in snapshots:
            _write_bytes(args.output / "raw/inputs" / name, raw_input)
        if args.mode != "dry-run":
            with ExitStack() as stack:
                capture_session = None
                if args.mode == "native":
                    report["resource_admission"] = stack.enter_context(
                        _admit_resources(args.model_directory, args.gpu_lock)
                    )
                    cache = args.output / "runtime-cache"
                    cache.mkdir()
                    settings = {
                        "HF_HUB_OFFLINE": "1",
                        "TRANSFORMERS_OFFLINE": "1",
                        "HF_HOME": str(cache / "hf"),
                        "HF_MODULES_CACHE": str(cache / "modules"),
                    }
                    old = {key: os.environ.get(key) for key in settings}

                    def restore_environment() -> None:
                        for key, value in old.items():
                            if value is None:
                                os.environ.pop(key, None)
                            else:
                                os.environ[key] = value

                    stack.callback(restore_environment)
                    os.environ.update(settings)
                    provider = MolmoPointProvider(
                        model_directory=args.model_directory,
                        asset_manifest=args.asset_manifest,
                        raw_directory=args.output / "raw/native",
                        generation_limit=args.generation_limit,
                    )
                    if args.post_cloud_revalidate:
                        capture_session = stack.enter_context(
                            MuJoCoCaptureSession(
                                SimulatorConfig(render_rgb=True, render_depth=True)
                            )
                        )
                for index, (request, task) in enumerate(pairs, 1):
                    if args.capture_fresh:
                        observation = (
                            capture_session.capture()
                            if capture_session is not None
                            else _fresh_capture()
                        )
                        request = request.model_copy(update={"observation": observation})
                        _save_capture(
                            args.output / "raw" / f"capture-{index:02}", request, observation
                        )
                    if adapters:
                        adapter = adapters[index - 1]
                        adapter.point_provider = provider
                        if args.post_cloud_revalidate:
                            if capture_session is None:
                                raise ValueError("post-cloud capture session unavailable")

                            def refresh_capture(
                                *,
                                session: Any = capture_session,
                                original: InitialPlanningRequest = request,
                                attempt: int = index,
                            ) -> Any:
                                if report["refresh_capture_calls_started"] >= 1:
                                    raise RuntimeError("post-cloud capture allocation exhausted")
                                report["refresh_capture_calls_started"] += 1
                                folder = args.output / "raw" / f"refresh-{attempt:02}"
                                folder.mkdir(parents=True, exist_ok=False)
                                _write(
                                    folder / "capture-started.json",
                                    {
                                        "utc": datetime.now(UTC).isoformat(),
                                        "monotonic_s": monotonic(),
                                        "request_id": original.request_id,
                                        "capture_role": "POST_CLOUD_REVALIDATION",
                                    },
                                )
                                try:
                                    fresh = session.capture()
                                except Exception as exc:
                                    try:
                                        _write(
                                            folder / "capture-failure.json",
                                            {
                                                "error_type": type(exc).__name__,
                                            },
                                        )
                                    except OSError as log_error:
                                        report["capture_failure_log_error_type"] = type(
                                            log_error
                                        ).__name__
                                    raise
                                report["refresh_capture_calls_completed"] += 1
                                _save_capture(folder, original, fresh)
                                return fresh

                            adapter.post_cloud_observation_supplier = refresh_capture

                        observer_counts = {"REQUEST": 0, "RESPONSE": 0}

                        def observe(
                            phase: str,
                            path: str,
                            data: bytes,
                            *,
                            attempt_index: int = index,
                            counts: dict[str, int] = observer_counts,
                        ) -> None:
                            counts[phase] += 1
                            name = f"{phase.lower()}-{counts[phase]:04}.json"
                            _write_bytes(
                                args.output / "raw/cloud" / f"attempt-{attempt_index:02}" / name,
                                data,
                            )
                            if phase == "REQUEST":
                                paid_starts.append(hashlib.sha256(data).hexdigest())

                        adapter.cloud.raw_transport_observer = observe
                        cloud = adapter.cloud
                    else:
                        content = replay_cloud["content"] if replay_cloud else None
                        cloud = _DiagnosticCloud(content)
                        adapter = MolmoGroundedPlannerAdapter(
                            point_provider=provider, cloud=cloud, task=task
                        )
                    result = PlanningPipeline(planner=adapter).process(request)
                    draft = result.attempts[0].draft if result.attempts else None
                    evidence = draft.observation_evidence if draft else {}
                    if draft is not None and draft.raw_text:
                        _write_bytes(
                            args.output / "raw" / f"attempt-{index:02}" / "cloud-content.txt",
                            draft.raw_text.encode(),
                        )
                    ready = "opencv_initial_geometry" in evidence
                    report["attempts"].append(
                        {
                            "request_id": request.request_id,
                            "observation_checksum": request.observation.checksum_sha256,
                            "initial_observation_checksum": request.observation.checksum_sha256,
                            "final_observation_checksum": (
                                evidence.get("checksum_sha256")
                                if result.outcome.value == "PLANNED"
                                else None
                            ),
                            "post_cloud_revalidation_status": evidence.get(
                                "post_cloud_revalidation", {}
                            ).get("status", "NOT_PERFORMED"),
                            "pipeline_outcome": result.outcome.value,
                            "local_geometry_status": "READY" if ready else "NOT_READY",
                            "parse_error": draft.parse_error if draft else None,
                            "reason": result.reason,
                            "evidence": evidence,
                        }
                    )
                    report["api_fixture_calls"] += getattr(cloud, "fixture_calls", 0)
                report["status"] = "COMPLETED"
        if args.mode == "native":
            report["model_loads_started"] = getattr(provider, "model_loads_started", 0)
            report["generation_calls_started"] = getattr(provider, "generation_calls_started", 0)
            report["generation_calls_completed"] = getattr(
                provider, "generation_calls_completed", 0
            )
        report["paid_cloud_calls_started"] = len(paid_starts)
        complete = bool(report["attempts"]) and len(report["attempts"]) == len(pairs)
        planned = complete and all(
            row["pipeline_outcome"] == "PLANNED" for row in report["attempts"]
        )
        geometry_ready = complete and all(
            row["local_geometry_status"] == "READY" for row in report["attempts"]
        )
        if args.mode == "dry-run":
            ok = True
        elif args.mode == "replay":
            ok = planned
        elif args.allow_paid:
            ok = planned and geometry_ready and len(paid_starts) >= len(pairs)
        else:
            ok = geometry_ready
        report["diagnostic_passed"] = ok
        if paid_starts:
            report["real_cloud_status"] = "PLANNED" if ok else "FAILED"
        try:
            _finalize(args.output, report)
        except Exception as final_error:
            print(
                json.dumps(
                    {"status": "FAILED", "finalization_error_type": type(final_error).__name__}
                )
            )
            return 2
        print(
            json.dumps(
                {
                    key: report[key]
                    for key in (
                        "status",
                        "execution_mode",
                        "diagnostic_passed",
                        "model_loads_started",
                        "generation_calls_started",
                        "paid_cloud_calls_started",
                    )
                }
            )
        )
        return 0 if ok else 2
    except Exception as exc:
        report.update(
            status="FAILED",
            error_type=type(exc).__name__,
            diagnostic_passed=False,
            model_loads_started=getattr(provider, "model_loads_started", 0),
            generation_calls_started=getattr(provider, "generation_calls_started", 0),
            generation_calls_completed=getattr(provider, "generation_calls_completed", 0),
            paid_cloud_calls_started=len(paid_starts),
        )
        raw = args.output / "raw/native"
        if provider is None and raw.exists():
            report["model_loads_started"] = int((raw / "load-started.json").exists())
        if paid_starts:
            report["real_cloud_status"] = "FAILED"
        if output_created:
            try:
                _finalize(args.output, report)
            except Exception as final_error:
                # 原错误仍是主因；不让清单写入错误掩盖它。
                report["finalization_error_type"] = type(final_error).__name__
        print(json.dumps({"status": "FAILED", "error_type": type(exc).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
