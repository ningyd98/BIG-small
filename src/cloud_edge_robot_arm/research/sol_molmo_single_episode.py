"""单场景来源、标记与 Sol/Molmo 规划诊断；执行资格继续由原运行时持有。"""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import struct
import time
from contextlib import AbstractContextManager, closing, nullcontext
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from cloud_edge_robot_arm.vision.marker_families import LEGACY_FAMILY, marker_family
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker
from cloud_edge_robot_arm.vision.top_grasp import calibration_asset_sha256

if TYPE_CHECKING:
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

ROOT = Path(__file__).resolve().parents[3]
MODES = frozenset({"dry-run", "check-marker", "plan-only", "execute"})
SOURCE_PATHS = (
    "scripts/run_sol_molmo_single_episode.py",
    "src/cloud_edge_robot_arm/research/sol_molmo_single_episode.py",
    "src/cloud_edge_robot_arm/vision/marker_families.py",
    "src/cloud_edge_robot_arm/vision/pose_markers.py",
    "src/cloud_edge_robot_arm/vision/capture.py",
    "src/cloud_edge_robot_arm/vision/grounded_planner.py",
    "src/cloud_edge_robot_arm/vision/molmo_pointing.py",
    "src/cloud_edge_robot_arm/vision/point_association.py",
    "src/cloud_edge_robot_arm/vision/role_models.py",
    "src/cloud_edge_robot_arm/vision/execution.py",
    "src/cloud_edge_robot_arm/research/native_collection_application.py",
    "src/cloud_edge_robot_arm/cloud/planning/pipeline.py",
)


def _sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
        default=lambda item: item.isoformat(),
    )
    with path.open("x", encoding="utf-8") as stream:
        stream.write(encoded + "\n")


def scene_assignment(seed: int, marker_family_id: str) -> dict[str, Any]:
    """登记固定 S01；不同 seed 不声称生成了不同的随机场景。"""
    if type(seed) is not int or not 0 <= seed < 2**31:
        raise ValueError("seed must be an integer in 0..2147483647")
    family = marker_family(marker_family_id)
    if _sha(ROOT / family.asset_path) != family.asset_sha256:
        raise ValueError("registered marker asset bytes changed")
    return {
        "schema_version": "sol-molmo.single-scene.v1",
        "scenario_id": "S01_NORMAL_STATIC",
        "seed": seed,
        "scene_sampling": "FIXED_REGISTERED_SCENE",
        "independent_random_scene": False,
        "instruction": "Pick up the red block and place it in the green region.",
        "model_path": family.asset_path,
        "asset_sha256": family.asset_sha256,
        "marker_family_id": family.family_id,
        "marker": {
            "marker_id": family.marker_id,
            "marker_size_m": family.marker_size_m,
            "dictionary": family.dictionary,
            "marked_asset_sha256": family.asset_sha256,
        },
        "camera_size": [320, 240],
        "physics_dt_rational": [1, 240],
        "settle_steps": 120,
        "grasp_profile": "mujoco_upright_box_v2",
        "budget": {
            "model_loads": 1,
            "local_generations": 4,
            "cloud_requests": 1,
            "repairs": 0,
            "retries": 0,
        },
    }


def execution_blockers(assignment: dict[str, Any]) -> list[str]:
    """报告真实接口缺口，不将配置或几何预览升级为执行能力。"""
    blockers = []
    if assignment["asset_sha256"] != calibration_asset_sha256(assignment["grasp_profile"]):
        blockers.append("marked_asset_not_qualified_for_visual_episode")
    # The current OpenCV path requires a concrete VisualWorkerRuntime. The
    # Molmo planning adapter has no accepted live worker/source handoff yet.
    blockers.append("molmo_live_opencv_worker_handoff_not_integrated")
    if assignment["marker_family_id"] != LEGACY_FAMILY:
        blockers.append("prepare_only_marker_family_no_execution_release")
    return blockers


def validate_marker_visibility(
    capture: Any,
    output_dir: Path,
    registration: PoseMarkerRegistration,
) -> dict[str, Any]:
    """保存该次真实采集后解码；不从实例ID推断检测结果或遮挡原因。"""
    from cloud_edge_robot_arm.vision.capture import save_captured_frame

    output_dir.mkdir(parents=True, exist_ok=False)
    frame = capture.capture_with_instances()
    if any(depth > 0 for depth in frame.observation.depth_values()):
        save_captured_frame(frame, output_dir)
    else:
        # The common preview writer cannot draw an all-invalid depth image.
        # Preserve its raw bytes and report UNKNOWN; never fabricate a preview.
        observation = frame.observation
        (output_dir / "rgb.png").write_bytes(base64.b64decode(observation.rgb_png_base64))
        (output_dir / "depth.f32").write_bytes(base64.b64decode(observation.depth_float32_base64))
        (output_dir / "valid_mask.u8").write_bytes(observation.valid_mask_bytes())
        (output_dir / "instance_geom_ids.i32").write_bytes(
            struct.pack(f"<{len(frame.instance_ids)}i", *frame.instance_ids)
        )
        _write(
            output_dir / "observation.json",
            observation.evidence()
            | {
                "model_image_count": 0,
                "depth_preview_status": "UNAVAILABLE_ALL_DEPTH_INVALID",
                "physics_state_hash": frame.physics_state_hash,
                "pass_state_hashes": list(frame.pass_state_hashes),
                "instance_labels": frame.instance_labels,
            },
        )
    estimate = detect_pose_marker(frame.observation, registration, corner_refinement="SUBPIX")
    result = asdict(estimate) | {
        "physics_state_hash": frame.physics_state_hash,
        "pass_state_hashes": list(frame.pass_state_hashes),
        "continuous_visibility_proven": False,
        "evidence_scope": "SINGLE_CAPTURE_DETECTION_NOT_MOTION_QUALIFICATION",
    }
    # Return exactly the same JSON values that readers see on disk.
    result = cast(
        dict[str, Any], json.loads(json.dumps(result, default=lambda value: value.isoformat()))
    )
    _write(output_dir / "marker-validation.json", result)
    return result


class _ReadOnlyProfileRepository:
    """只读现有配置，不初始化数据库、激活模型或复制凭据。"""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve(strict=True)
        if not self.path.is_file():
            raise ValueError("existing model database required")

    def _query(self, query: str, parameters: tuple = ()) -> Any:
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as connection:
            return connection.execute(query, parameters).fetchone()

    def get_profile(self, profile_id: str) -> Any:
        from cloud_edge_robot_arm.model_control.models import ModelProviderProfile

        row = self._query(
            "SELECT payload_json FROM model_provider_profiles WHERE profile_id = ?", (profile_id,)
        )
        if row is None:
            raise ValueError("selected profile unavailable")
        return ModelProviderProfile.model_validate_json(row[0])

    def get_active_profile_id(self) -> str:
        row = self._query("SELECT value FROM model_runtime_state WHERE key = 'active_profile_id'")
        return str(row[0]) if row else ""


def selected_sol_service(database: Path, profile_id: str) -> Any:
    """复用已有加密 secret store；不接受通过 CLI 传入明文 key。"""
    from cloud_edge_robot_arm.model_control.models import PlannerProviderKind
    from cloud_edge_robot_arm.model_control.repository import PlannerProfileRepository
    from cloud_edge_robot_arm.model_control.secret_store import create_secret_store
    from cloud_edge_robot_arm.model_control.service import ModelControlService

    repository = _ReadOnlyProfileRepository(database)
    profile = repository.get_profile(profile_id)
    if (
        not profile.enabled
        or profile.provider_kind != PlannerProviderKind.OPENAI_COMPATIBLE
        or profile.model_name != "gpt-6.1-sol"
    ):
        raise ValueError("explicit enabled Sol profile required")
    service = ModelControlService(
        # This read-only service path consumes exactly get_profile/get_active_profile_id.
        repository=cast(PlannerProfileRepository, repository),
        secret_store=create_secret_store(database),
    )
    if not service.secret_store.has_secret(profile_id):
        raise ValueError("selected Sol secret unavailable")
    return service


def _plan(
    capture: Any,
    assignment: dict[str, Any],
    output: Path,
    result: dict[str, Any],
    *,
    service: Any,
    profile_id: str,
    points: Any,
) -> None:
    from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest
    from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
    from cloud_edge_robot_arm.research.cost_ledger import CostLedger
    from cloud_edge_robot_arm.vision.capture import save_observation
    from cloud_edge_robot_arm.vision.grounded_planner import (
        GroundingTaskDescriptor,
        build_molmo_grounded_planner,
    )

    observation = capture.capture()
    save_observation(observation, output / "planning-input")
    request = InitialPlanningRequest(
        request_id="sol-molmo-single-episode",
        user_instruction=assignment["instruction"],
        observation=observation,
    )
    task = GroundingTaskDescriptor(
        instruction=assignment["instruction"],
        target_phrase="red block",
        destination_phrase="green region",
        target_label="red block",
    )
    _write(output / "planning-request.json", request.model_dump(mode="json"))
    _write(output / "task-descriptor.json", task.model_dump(mode="json"))

    def refresh() -> RGBDObservation:
        # This existing revalidation protocol binds a paused physical state.
        # Capture new sensor bytes/time/identity without changing sim_time_s.
        current = cast("RGBDObservation", capture.capture())
        save_observation(current, output / "post-cloud-observation")
        return current

    planner = build_molmo_grounded_planner(
        service=service,
        profile_id=profile_id,
        point_provider=points,
        task=task,
        grasp_profile=assignment["grasp_profile"],
        allow_paid=True,
        post_cloud_observation_supplier=refresh,
    )
    if planner.cloud.model_name != "gpt-6.1-sol":
        raise ValueError("selected profile is not Sol")
    ledger = CostLedger()
    planner.cloud.cost_ledger = ledger

    def wire(phase: str, path: str, data: bytes) -> None:
        if phase == "REQUEST":
            if result["cloud_request_reservations"] >= 1:
                raise RuntimeError("single cloud request budget exhausted")
            result["cloud_request_reservations"] += 1
        _write_wire = output / "raw/cloud" / (phase.lower() + ".json")
        _write_wire.parent.mkdir(parents=True, exist_ok=True)
        with _write_wire.open("xb") as stream:
            stream.write(data)

    planner.cloud.raw_transport_observer = wire
    _write(output / "cloud-role.json", cast(Any, planner.cloud).role_snapshot.evidence())
    assert planner.cloud.model_snapshot is not None
    _write(output / "cloud-model-snapshot.json", planner.cloud.model_snapshot.evidence())
    try:
        response = PlanningPipeline(planner=planner, max_repair_attempts=0).process(request)
        _write(output / "planning-response.json", response.model_dump(mode="json"))
        result["planning_outcome"] = response.outcome.value
        result["planning_passed"] = response.outcome.value == "PLANNED"
        result["status"] = "PLANNED" if result["planning_passed"] else "PLANNING_REJECTED"
    finally:
        _write(output / "costs.json", ledger.export())
        result["cloud_requests"] = ledger.snapshot().cloud_model_requests


def _run_observed_scene(
    assignment: dict[str, Any],
    output: Path,
    result: dict[str, Any],
    *,
    mode: str,
    profile_id: str | None,
    model_control_db: Path | None,
    model_directory: Path | None,
    asset_manifest: Path | None,
    gpu_lock: Path | None,
) -> None:
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    service = points = None
    resources: AbstractContextManager[Any]
    if mode == "plan-only":
        from scripts.probe_molmo_grounded_planner import _admit_resources

        service = selected_sol_service(cast(Path, model_control_db), cast(str, profile_id))
        resources = _admit_resources(cast(Path, model_directory), gpu_lock)
    else:
        resources = nullcontext()
    with resources:
        try:
            if mode == "plan-only":
                from cloud_edge_robot_arm.vision.molmo_pointing import MolmoPointProvider

                points = MolmoPointProvider(
                    model_directory=cast(Path, model_directory),
                    asset_manifest=cast(Path, asset_manifest),
                    raw_directory=output / "raw/molmo",
                    generation_limit=4,
                )
            config = SimulatorConfig(
                model_path=str(ROOT / assignment["model_path"]),
                seed=assignment["seed"],
                domain_randomization=False,
                render_rgb=True,
                render_depth=True,
                camera_width=320,
                camera_height=240,
                physics_dt_s=1 / 240,
            )
            with MuJoCoCaptureSession(config) as capture:
                backend = capture._backend
                try:
                    backend.step(steps=120)
                    registration = PoseMarkerRegistration(**assignment["marker"])
                    result["marker_before"] = validate_marker_visibility(
                        capture,
                        output / "before",
                        registration,
                    )
                    try:
                        if mode == "plan-only":
                            _plan(
                                capture,
                                assignment,
                                output,
                                result,
                                service=service,
                                profile_id=cast(str, profile_id),
                                points=points,
                            )
                        else:
                            result["status"] = "MARKER_CHECKED"
                    finally:
                        backend.step(steps=1)
                        result["marker_after"] = validate_marker_visibility(
                            capture,
                            output / "after",
                            registration,
                        )
                finally:
                    result["physics_steps"] = backend.total_physics_steps
                    result["episode_id"] = backend._episode_id
        finally:
            if points is not None:
                result["model_loads"] = points.model_loads_started
                result["local_generations"] = points.generation_calls_started
                result["local_generations_completed"] = points.generation_calls_completed
            else:
                # A constructor failure may already have started a real load.
                result["model_loads"] = int((output / "raw/molmo/load-started.json").is_file())
            result["model_calls"] = result["local_generations"] + result["cloud_requests"]


def run_single_episode(
    *,
    output: Path,
    seed: int = 42001,
    marker_family_id: str = LEGACY_FAMILY,
    mode: str = "dry-run",
    profile_id: str | None = None,
    model_control_db: Path | None = None,
    model_directory: Path | None = None,
    asset_manifest: Path | None = None,
    gpu_lock: Path | None = None,
    allow_paid: bool = False,
) -> dict[str, Any]:
    """统一显式入口；当前 execute 如实阻塞，不冒充已接通物理 worker。"""
    if mode not in MODES:
        raise ValueError("unsupported single episode mode")
    if mode == "plan-only" and (
        not allow_paid
        or not profile_id
        or model_control_db is None
        or model_directory is None
        or asset_manifest is None
    ):
        raise ValueError(
            "plan-only needs explicit Sol profile, database, Molmo assets and allow-paid"
        )
    assignment = scene_assignment(seed, marker_family_id)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    sources: dict[str, str] = {}
    result = {
        "schema_version": "sol-molmo.single-episode-result.v1",
        "mode": mode,
        "status": "PREPARED",
        "seed": seed,
        "instruction": assignment["instruction"],
        "scene_file": assignment["model_path"],
        "success": False,
        "physical_success": None,
        "online_reported_complete": None,
        "executed_actions": 0,
        "physics_steps": 0,
        "model_calls": 0,
        "model_loads": 0,
        "local_generations": 0,
        "local_generations_completed": 0,
        "cloud_requests": 0,
        "cloud_request_reservations": 0,
        "marker_before": {"status": "NOT_RUN"},
        "marker_after": {"status": "NOT_RUN"},
        "marker_endpoints_observed": False,
        "continuous_visibility_proven": False,
        "planning_passed": False,
        "planning_outcome": "NOT_RUN",
        "blocking_reasons": [],
        "source_snapshot_status": "INCOMPLETE",
        "hardware_dispatch": False,
        "formal_research": "NOT_ACCEPTED",
        "qualified_groups_added": 0,
        "raw_delivery": "LOCAL_ONLY",
        "started_at": datetime.now(UTC).isoformat(),
    }
    started = time.monotonic()
    try:
        _write(output / "scene-assignment.json", assignment)
        for name in (*SOURCE_PATHS, assignment["model_path"]):
            sources[name] = _sha(ROOT / name)
        _write(output / "source-hashes.json", {"scope": "SELECTED_ENTRY_SOURCES", "files": sources})
        result["source_snapshot_status"] = "COMPLETE"
        if mode == "execute":
            result.update(status="BLOCKED", blocking_reasons=execution_blockers(assignment))
        elif mode != "dry-run":
            _run_observed_scene(
                assignment,
                output,
                result,
                mode=mode,
                profile_id=profile_id,
                model_control_db=model_control_db,
                model_directory=model_directory,
                asset_manifest=asset_manifest,
                gpu_lock=gpu_lock,
            )
    except (KeyboardInterrupt, SystemExit) as error:
        result.update(status="INTERRUPTED", error_type=type(error).__name__)
        raise
    except Exception as error:
        result.update(status="FAILED", error_type=type(error).__name__)
    finally:
        result["marker_endpoints_observed"] = all(
            result[key]["status"] == "OBSERVED" for key in ("marker_before", "marker_after")
        )
        drift = []
        for name, expected in sources.items():
            try:
                unchanged = _sha(ROOT / name) == expected
            except OSError:
                unchanged = False
            if not unchanged:
                drift.append(name)
        result["changed_source_paths"] = drift
        if drift and result["status"] != "INTERRUPTED":
            result.update(status="FAILED", error_type="SourceDrift")
        result["elapsed_s"] = time.monotonic() - started
        _write(output / "result.json", result)
        files = [
            {
                "path": str(path.relative_to(output)),
                "bytes": path.stat().st_size,
                "sha256": _sha(path),
            }
            for path in sorted(output.rglob("*"))
            if path.is_file()
        ]
        _write(
            output / "evidence-manifest.json", {"schema_version": "local.files.v1", "files": files}
        )
    return result
