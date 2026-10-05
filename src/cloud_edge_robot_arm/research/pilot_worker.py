"""Run assigned pilot scenes through a durable worker attempt and one controller.

The research assignment is an immutable job input. Its identifiers and current
lease are read from SQLite; this module supplies no action-admission flag.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any
from uuid import uuid4

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.datasets.rgbd.capture import _validate_parameters
from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec, content_digest
from cloud_edge_robot_arm.edge.recovery.verification_router import VerificationBudget
from cloud_edge_robot_arm.edge.runtime.skill_executor import SkillExecutor
from cloud_edge_robot_arm.edge.runtime.skill_registry import SkillRegistry
from cloud_edge_robot_arm.repositories.event_autonomy.sqlite import SQLiteEventAutonomyRepository
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import (
    PhysicalFault,
    PhysicalFaultType,
    PhysicalScenarioConfig,
)
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.simulation_runtime.models import (
    RuntimeJobStatus,
    SimulationJobAttempt,
    SimulationJobRecord,
)
from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession
from cloud_edge_robot_arm.vision.evaluation import ExecutionPolicy, VisualEpisodeOutcome, write_json
from cloud_edge_robot_arm.vision.execution import run_visual_episode
from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter
from cloud_edge_robot_arm.vision.raw_recorder_v3 import RECORDER_SOURCE_PATHS, VisualRawRecorderV3
from cloud_edge_robot_arm.vision.runtime_binding import RoleRuntimeBinding
from cloud_edge_robot_arm.vision.worker_owner import (
    pin_worker_source_inventory,
    read_visual_worker_lease,
)
from cloud_edge_robot_arm.vision.worker_runtime import (
    REQUIRED_WORKER_RUNTIME_SOURCES,
    VisualWorkerRuntime,
    WorkerRuntimeSource,
)

PILOT_WORKER_SOURCE_PATHS = (
    REQUIRED_WORKER_RUNTIME_SOURCES
    | RECORDER_SOURCE_PATHS
    | frozenset(
        {
            "src/cloud_edge_robot_arm/research/pilot_worker.py",
            "src/cloud_edge_robot_arm/research/pilot.py",
            "src/cloud_edge_robot_arm/research/protocol.py",
            "src/cloud_edge_robot_arm/research/network.py",
            "src/cloud_edge_robot_arm/datasets/rgbd/capture.py",
            "src/cloud_edge_robot_arm/datasets/rgbd/models.py",
            "scripts/run_rgbd_pilot.py",
            "assets/robots/franka_panda/scene.xml",
        }
    )
)


def compile_pilot_scene(
    scene: SceneSpec, config: SimulatorConfig
) -> tuple[str, PhysicalScenarioConfig]:
    """Compile fixed SceneSpec geometry before the backend's single real RESET.

    This changes only offline scene inputs, including free-body default poses.
    The calibrated arm and gripper elements retain their original geometry.
    """
    params = scene.scene_parameters
    _validate_parameters(params)
    asset = Path(config.model_path).read_bytes()
    if hashlib.sha256(asset).hexdigest() != scene.asset_family_hash:
        raise ValueError("pilot scene asset family differs from calibrated asset")
    tree = ET.fromstring(asset)
    world = tree.find("worldbody")
    if world is None:
        raise ValueError("pilot scene requires the calibrated worldbody")

    def numbers(values: list[float]) -> str:
        return " ".join(str(value) for value in values)

    def apply_geometry(body: ET.Element, obj: Mapping[str, Any]) -> None:
        geom = body.find("geom")
        if geom is None:
            raise ValueError("pilot object requires a box geometry")
        body.set("pos", numbers(obj["position"]))
        geom.set("size", numbers(obj["half_size"]))
        geom.set("rgba", numbers(obj["rgba"]))
        if "mass_kg" in obj:
            geom.set("mass", str(obj["mass_kg"]))
            geom.set("friction", f"{obj['friction']} 0.01 0.001")

    for name, obj in (("object", params["target"]), ("target_region", params["destination"])):
        body = world.find(f"body[@name='{name}']")
        if body is None:
            raise ValueError("pilot scene requires the calibrated object and destination")
        apply_geometry(body, obj)
    for index, obj in enumerate(params["distractors"]):
        body = ET.SubElement(world, "body", name=f"dataset_distractor_{index}")
        ET.SubElement(body, "freejoint", name=f"dataset_distractor_{index}_free")
        ET.SubElement(
            body,
            "geom",
            name=f"dataset_distractor_{index}_geom",
            type="box",
            contype="1",
            conaffinity="1",
        )
        apply_geometry(body, obj)
    camera = world.find("camera[@name='rgbd']")
    light = world.find("light[@name='rgbd_light']")
    if camera is None or light is None:
        raise ValueError("pilot scene requires the registered RGB-D camera and light")
    camera.set("pos", numbers(params["camera"]["position"]))
    camera.set("quat", numbers(params["camera"]["quaternion"]))
    camera.set("fovy", str(params["camera"]["fovy"]))
    light.set("diffuse", numbers([params["light_intensity"]] * 3))
    target, destination = params["target"], params["destination"]
    scenario = PhysicalScenarioConfig(
        scenario_id=scene.group_id,
        seed=scene.seed,
        object_mass_kg=target["mass_kg"],
        friction_coefficient=target["friction"],
        object_pose=Pose(**dict(zip("xyz", target["position"], strict=True))),
        target_region_pose=Pose(**dict(zip("xyz", destination["position"], strict=True))),
    )
    return ET.tostring(tree, encoding="unicode"), scenario


class PilotWorkerAttempt:
    """One genuine queued job, acquired lease and current open persisted attempt."""

    def __init__(
        self,
        *,
        planner: RGBDPlannerAdapter,
        binding: RoleRuntimeBinding,
        assignment: Mapping[str, Any],
        directory: Path,
        runtime_directory: Path,
        timeout_s: float,
    ) -> None:
        if type(binding) is not RoleRuntimeBinding:
            raise TypeError("concrete frozen role binding required")
        if (
            type(timeout_s) not in {int, float}
            or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 600
        ):
            raise ValueError("pilot original timeout must be finite and within protocol bounds")
        self.planner, self.binding = planner, binding
        self.assignment = json.loads(json.dumps(dict(assignment), allow_nan=False))
        self.scene = SceneSpec.model_validate(self.assignment["base_assignment"]["scene"])
        if (
            self.assignment["group_id"] != self.scene.group_id
            or self.assignment["physics_seed"] != self.scene.seed
            or self.assignment["scene_hash"] != self.scene.scene_hash
            or self.assignment["role_bundle_hash"] != binding.bundle.digest()
        ):
            raise ValueError("pilot assignment scene/seed/role source differs")
        self.directory, self.runtime_directory = Path(directory), Path(runtime_directory)
        self.timeout_s = float(timeout_s)
        self.config = SimulatorConfig(
            render_rgb=True,
            render_depth=True,
            camera_width=320,
            camera_height=240,
            domain_randomization=False,
            seed=self.scene.seed,
        )
        self.model_xml, self.scenario = compile_pilot_scene(self.scene, self.config)
        self.worker_id = "pilot-worker-" + uuid4().hex
        self.run_id = "pilot-run-" + uuid4().hex
        database_directory = self.runtime_directory / self.run_id
        self.jobs = SQLiteSimulationJobRepository(database_directory / "jobs.sqlite")
        self.events = SQLiteEventAutonomyRepository(database_directory / "events.sqlite")
        self.lease_ttl_s = 30
        self.source: WorkerRuntimeSource
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._heartbeat_error: BaseException | None = None
        self._entered = False
        self._successful = False
        self._terminal_reason = "PILOT_EPISODE_NOT_COMPLETED"

    def __enter__(self) -> PilotWorkerAttempt:
        if self._entered:
            raise RuntimeError("pilot attempt lifetime cannot be reused")
        self._entered = True
        try:
            return self._enter_attempt()
        except BaseException as error:
            self._abort_start(error)
            raise

    def _enter_attempt(self) -> PilotWorkerAttempt:
        self.binding.validate(self.planner)
        inventory: dict[str, str] = {}
        for role_sources in (
            self.binding.bundle.cloud_snapshot.source_hashes,
            self.binding.edge_snapshot.source_hashes,
            self.binding.device_source_hashes,
        ):
            for name, expected in role_sources.items():
                if name in inventory and inventory[name] != expected:
                    raise ValueError("pilot role source inventories disagree")
                inventory[name] = expected
        for name in PILOT_WORKER_SOURCE_PATHS:
            actual = hashlib.sha256((self.binding.root / name).read_bytes()).hexdigest()
            if name in inventory and inventory[name] != actual:
                raise ValueError("pilot worker source differs from frozen role source")
            inventory[name] = actual
        inventory = dict(
            pin_worker_source_inventory(
                self.binding.root, inventory, required_paths=PILOT_WORKER_SOURCE_PATHS
            )
        )
        job = self.jobs.create_job(
            run_id=self.run_id,
            batch_id="",
            backend="MUJOCO",
            scenario_id=self.scene.group_id,
            control_mode="CLOUD",
            seed=self.scene.seed,
            manifest_id="pilot-assignment-" + content_digest(self.assignment),
            reproducibility_hash=content_digest(self.assignment),
            draft={
                "user_instruction": self.instruction,
                "parameter_overrides": {
                    "supervision_period_ms": None
                    if self.assignment["period_s"] is None
                    else int(self.assignment["period_s"] * 1000),
                    "advance_physics_during_wait": True,
                },
            },
            manifest={
                "schema_version": "ced.pilot-worker-job.v1",
                "pilot_assignment": self.assignment,
                "scene_spec": self.scene.model_dump(mode="json"),
                "compiled_scene_sha256": hashlib.sha256(self.model_xml.encode()).hexdigest(),
                "timeout_s": self.timeout_s,
                "raw_camera_depth_noise_m": 0.0,
                "source_hashes": inventory,
            },
            timeout_seconds=math.ceil(self.timeout_s),
            max_attempts=1,
            artifact_root="cases/" + self.assignment["assignment_id"],
            source_commit="source-inventory-only",
            source_tree_hash=content_digest(inventory),
        )
        self._job = job
        if (
            self.jobs.update_status_cas(
                job.job_id,
                expected=RuntimeJobStatus.CREATED,
                next_status=RuntimeJobStatus.QUEUED,
                reason_code="pilot_assignment_queued",
                worker_id="",
                lease_id="",
            )
            is None
        ):
            raise RuntimeError("pilot job queue transition was not committed")
        with self.jobs.publication_guard():
            lease = self.jobs.acquire_lease(
                worker_id=self.worker_id, backend="MUJOCO", lease_ttl_seconds=self.lease_ttl_s
            )
            if lease is None or lease.job_id != job.job_id:
                raise RuntimeError("pilot assignment did not acquire its own queued job")
            self._lease = lease
            self._task_started_monotonic = time.monotonic()
            attempt = self.jobs.start_attempt(job.job_id, worker_id=self.worker_id)
            self._attempt = attempt
            for old, new in (
                (RuntimeJobStatus.LEASED, RuntimeJobStatus.STARTING),
                (RuntimeJobStatus.STARTING, RuntimeJobStatus.RUNNING),
            ):
                self._transition(job.job_id, lease.lease_id, old, new)
            self.source = WorkerRuntimeSource(
                job_repository=self.jobs,
                event_repository=self.events,
                job_id=job.job_id,
                run_id=job.run_id,
                worker_id=self.worker_id,
                lease_id=lease.lease_id,
                source_root=self.binding.root,
                source_hashes=inventory,
                robot_id="pilot-mujoco-arm",
                plan_id="plan-" + job.job_id,
                task_started_at=attempt.started_at,
                task_timeout_s=self.timeout_s,
            )
            self.check_active()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, name="pilot-worker-heartbeat", daemon=True
        )
        self._heartbeat_thread.start()
        self.publish_source()
        return self

    def _abort_start(self, error: BaseException) -> None:
        """An exception from __enter__ still closes its genuine persisted attempt."""
        self._heartbeat_stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=2)
        try:
            if not hasattr(self, "_job"):
                return
            with self.jobs.publication_guard():
                job = self.jobs.get_job(self._job.job_id)
                if not hasattr(self, "_lease"):
                    if job.status in {RuntimeJobStatus.CREATED, RuntimeJobStatus.QUEUED}:
                        self.jobs.update_status_cas(
                            job.job_id,
                            expected=job.status,
                            next_status=RuntimeJobStatus.BLOCKED_BY_ENV,
                            reason_code="pilot_start_source_unavailable",
                            worker_id="",
                            lease_id="",
                            expected_worker_id=job.worker_id,
                            expected_lease_id=job.lease_id,
                        )
                    return
                if not self._owns_original_lease(job):
                    return
                actual_attempt = self._unique_open_attempt(job)
                all_attempts = [
                    row for row in self.jobs.list_attempts(job.run_id) if row.job_id == job.job_id
                ]
                if actual_attempt is None and (job.attempt != 0 or all_attempts):
                    # A missing/ambiguous/ended attempt is forensic source, not
                    # permission to reconstruct or overwrite an attempt record.
                    self._release_original_lease(job)
                    return
                if job.status in {RuntimeJobStatus.CANCEL_REQUESTED, RuntimeJobStatus.CANCELLING}:
                    self._transition(
                        job.job_id, job.lease_id, job.status, RuntimeJobStatus.CANCELLED
                    )
                elif job.status == RuntimeJobStatus.LEASED:
                    # start_attempt may fail before commit or after committing
                    # its real row. End startup through existing legal states;
                    # an absent attempt remains absent and never receives an ID.
                    for before, after in (
                        (RuntimeJobStatus.LEASED, RuntimeJobStatus.INTERRUPTED),
                        (RuntimeJobStatus.INTERRUPTED, RuntimeJobStatus.RECOVERY_PENDING),
                        (RuntimeJobStatus.RECOVERY_PENDING, RuntimeJobStatus.FAILED),
                    ):
                        self._transition(job.job_id, job.lease_id, before, after)
                elif job.status in {RuntimeJobStatus.STARTING, RuntimeJobStatus.RUNNING}:
                    self._transition(job.job_id, job.lease_id, job.status, RuntimeJobStatus.FAILED)
                else:
                    self._release_original_lease(job)
                    return
                terminal = self.jobs.get_job(job.job_id)
                if actual_attempt is not None:
                    self.jobs.finish_attempt(
                        job.job_id,
                        attempt=actual_attempt.attempt,
                        result=terminal.status.value,
                        error=type(error).__name__,
                        artifact_paths={},
                    )
                self._release_original_lease(terminal)
        finally:
            self.events.close()

    def _owns_original_lease(self, job: SimulationJobRecord) -> bool:
        """Read current ownership; this predicate never changes a job or lease."""
        if not hasattr(self, "_lease") or (
            job.job_id != self._lease.job_id
            or job.run_id != self.run_id
            or job.worker_id != self.worker_id
            or job.lease_id != self._lease.lease_id
        ):
            return False
        matches = [
            row
            for row in self.jobs.list_leases(job.run_id)
            if row.job_id == job.job_id
            and row.lease_id == self._lease.lease_id
            and row.worker_id == self.worker_id
            and row.acquired_at == self._lease.acquired_at
        ]
        return len(matches) == 1

    def _unique_open_attempt(self, job: SimulationJobRecord) -> SimulationJobAttempt | None:
        """Join an actual unique current open row, including a lost start response."""
        rows = [
            row
            for row in self.jobs.list_attempts(job.run_id)
            if row.job_id == job.job_id and row.ended_at is None
        ]
        if len(rows) != 1:
            return None
        row = rows[0]
        cached = getattr(self, "_attempt", None)
        if (
            row.run_id != job.run_id
            or row.worker_id != self.worker_id
            or row.attempt != job.attempt
            or row.result != "RUNNING"
            or row.started_at < self._lease.acquired_at
            or cached is not None
            and row != cached
        ):
            return None
        return row

    def _release_original_lease(self, job: SimulationJobRecord) -> None:
        """Release only this unchanged original identity under the publication guard."""
        current = self.jobs.get_job(job.job_id)
        if not self._owns_original_lease(current):
            return
        matches = [
            row
            for row in self.jobs.list_leases(current.run_id)
            if row.lease_id == self._lease.lease_id and row.released_at is None
        ]
        if len(matches) == 1:
            self.jobs.release_lease(self._lease.lease_id)

    @property
    def instruction(self) -> str:
        color = self.scene.scene_parameters["target"]["color_name"]
        return f"Move the {color} block to the green region."

    def _transition(
        self, job_id: str, lease_id: str, old: RuntimeJobStatus, new: RuntimeJobStatus
    ) -> None:
        if (
            self.jobs.update_status_cas(
                job_id,
                expected=old,
                next_status=new,
                reason_code="pilot_worker_" + new.value.lower(),
                worker_id=self.worker_id,
                lease_id=lease_id,
                expected_lease_id=lease_id,
                expected_worker_id=self.worker_id,
            )
            is None
        ):
            raise RuntimeError("pilot current ownership/status transition was not committed")

    def _read_lease(self) -> None:
        read_visual_worker_lease(
            self.jobs,
            job_id=self.source.job_id,
            run_id=self.source.run_id,
            worker_id=self.source.worker_id,
            lease_id=self.source.lease_id,
        )

    def remaining_s(self) -> float:
        elapsed = max(
            (datetime.now(UTC) - self.source.task_started_at).total_seconds(),
            time.monotonic() - self._task_started_monotonic,
        )
        return self.source.task_timeout_s - elapsed

    def check_active(self) -> None:
        if self.remaining_s() <= 0:
            raise TimeoutError("pilot original task deadline elapsed")
        if self._heartbeat_error is not None:
            raise RuntimeError(
                "pilot current lease heartbeat unavailable"
            ) from self._heartbeat_error
        try:
            self._read_lease()
        except (ValueError, KeyError) as error:
            raise RuntimeError("pilot current worker lease source unavailable") from error
        pin_worker_source_inventory(
            self.binding.root, self.source.source_hashes, required_paths=PILOT_WORKER_SOURCE_PATHS
        )
        self.binding.validate(self.planner)

    def cancelled(self) -> bool:
        try:
            self._read_lease()
        except (ValueError, KeyError, RuntimeError):
            return True
        return self._heartbeat_error is not None

    def heartbeat(self) -> None:
        with self.jobs.publication_guard():
            try:
                self._read_lease()
            except (ValueError, KeyError) as error:
                raise RuntimeError("pilot heartbeat current source unavailable") from error
            self.jobs.heartbeat_lease(self.source.lease_id, lease_ttl_seconds=self.lease_ttl_s)
            self._read_lease()

    def _heartbeat_loop(self) -> None:
        while not self._heartbeat_stop.wait(self.lease_ttl_s / 3):
            try:
                self.heartbeat()
            except BaseException as error:
                self._heartbeat_error = error
                return

    def record_outcome(self, outcome: VisualEpisodeOutcome) -> None:
        self._successful = outcome.success
        self._terminal_reason = outcome.terminal_reason or outcome.status

    def source_evidence(self) -> dict[str, Any]:
        job = self.jobs.get_job(self.source.job_id)
        attempts = [row for row in self.jobs.list_attempts(job.run_id) if row.job_id == job.job_id]
        return {
            "schema_version": "ced.pilot-worker-source.v1",
            "scope": "SOURCE_CONSISTENCY_ONLY",
            "job_id": job.job_id,
            "run_id": job.run_id,
            "worker_id": job.worker_id,
            "lease_id": job.lease_id,
            "attempt": job.attempt,
            "status": job.status.value,
            "attempt_result": attempts[-1].result,
            "task_started_at": self.source.task_started_at.isoformat(),
            "task_timeout_s": self.source.task_timeout_s,
            "pilot_assignment_hash": content_digest(self.assignment),
            "compiled_scene_sha256": hashlib.sha256(self.model_xml.encode()).hexdigest(),
            "raw_episode_schema": "rgbd.raw-episode.v3",
            "database_directory": "worker-runtime/" + self.run_id,
            "research_acceptance": "NOT_ACCEPTED",
        }

    def publish_source(self) -> None:
        write_json(self.directory / "pilot-worker-source.json", self.source_evidence())

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._heartbeat_stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=2)
        final_source_error: BaseException | None = None
        try:
            with self.jobs.publication_guard():
                job = self.jobs.get_job(self.source.job_id)
                if not self._owns_original_lease(job):
                    raise RuntimeError("pilot finalization cannot overwrite changed ownership")
                actual_attempt = self._unique_open_attempt(job)
                if actual_attempt is None:
                    self._release_original_lease(job)
                    raise RuntimeError("pilot finalization current open attempt source unavailable")
                if self._successful and exc is None:
                    try:
                        self.check_active()
                    except (ValueError, OSError, RuntimeError, TimeoutError) as error:
                        final_source_error = error
                        self._successful = False
                status = job.status
                if status in {RuntimeJobStatus.CANCEL_REQUESTED, RuntimeJobStatus.CANCELLING}:
                    self._transition(job.job_id, job.lease_id, status, RuntimeJobStatus.CANCELLED)
                elif status == RuntimeJobStatus.RUNNING:
                    if self.remaining_s() <= 0 or isinstance(exc, TimeoutError):
                        self._transition(
                            job.job_id, job.lease_id, status, RuntimeJobStatus.TIMED_OUT
                        )
                    else:
                        self._transition(
                            job.job_id, job.lease_id, status, RuntimeJobStatus.FINALIZING
                        )
                        self._transition(
                            job.job_id,
                            job.lease_id,
                            RuntimeJobStatus.FINALIZING,
                            RuntimeJobStatus.SUCCEEDED
                            if exc is None and self._successful
                            else RuntimeJobStatus.FAILED,
                        )
                terminal = self.jobs.get_job(job.job_id)
                self.jobs.finish_attempt(
                    job.job_id,
                    attempt=actual_attempt.attempt,
                    result=terminal.status.value,
                    error=type(exc).__name__ if exc is not None else self._terminal_reason,
                    artifact_paths={"raw_episode_v3": "raw_episode_v3"},
                )
                self._release_original_lease(terminal)
                self.publish_source()
        finally:
            self.events.close()
        if final_source_error is not None:
            raise final_source_error


@dataclass(frozen=True)
class PilotVisualWorkerResult:
    outcome: VisualEpisodeOutcome
    worker_source: Mapping[str, Any]


def run_pilot_visual_worker(
    *,
    planner: RGBDPlannerAdapter,
    binding: RoleRuntimeBinding,
    assignment: Mapping[str, Any],
    directory: Path,
    runtime_directory: Path,
    timeout_s: float,
    capture_factory: Callable[..., MuJoCoCaptureSession],
) -> PilotVisualWorkerResult:
    """Preserve full assigned scenes and fixed periods through the real worker path."""
    owner = PilotWorkerAttempt(
        planner=planner,
        binding=binding,
        assignment=assignment,
        directory=directory,
        runtime_directory=runtime_directory,
        timeout_s=timeout_s,
    )
    with owner:
        backend = MuJoCoPhysicsBackend()
        try:
            owner.check_active()
            backend.initialize(owner.config, model_xml=owner.model_xml)
            # Preserve the preregistered clean acquisition before fixed sensor corruption.
            # This is offline setup, matching the dataset scene application's raw camera.
            backend._sensor_noise_std_m = 0.0
            owner.check_active()
            with ExitStack() as resources:
                robot = MuJoCoSkillRobot(backend)
                capture = resources.enter_context(capture_factory(owner.config, backend=backend))
                executor = SkillExecutor(robot=robot, registry=SkillRegistry.default())
                recorder = resources.enter_context(
                    VisualRawRecorderV3(
                        backend,
                        capture,
                        executor,
                        directory=directory / "raw_episode_v3",
                        source_root=binding.root,
                        source_hashes=owner.source.source_hashes,
                    )
                )
                owner.check_active()
                backend.reset(owner.scenario)
                owner.check_active()
                with recorder.purpose("SETTLE"):
                    backend.step(steps=120)
                owner.check_active()
                capture.raw_directory = directory / "raw-frames"  # type: ignore[attr-defined]
                capture.perturbation_seed = owner.scene.seed  # type: ignore[attr-defined]
                task = assignment["stratum_id"].split("_RTT")[0]
                perturbation = assignment["base_assignment"]["perturbation"]
                if task == "SENSOR":
                    capture.noise_m = perturbation["noise_m"]  # type: ignore[attr-defined]
                    capture.invalid_fraction = perturbation["invalid_fraction"]  # type: ignore[attr-defined]
                    capture.occlusion_fraction = perturbation["occlusion_fraction"]  # type: ignore[attr-defined]
                if task == "DYNAMIC":
                    backend.inject_fault(
                        PhysicalFault(
                            fault_type=PhysicalFaultType.TARGET_MOTION,
                            parameters={
                                "speed_m_s": perturbation["movement_speed_m_s"],
                                "duration_s": 5.0,
                                "direction_y": 1.0,
                            },
                        )
                    )
                write_json(
                    directory / "perturbation.json",
                    {
                        "task": task,
                        "assignment": perturbation,
                        "network": assignment["network_schedule"],
                        "sensor_applied_from_frame": 1,
                        "movement_duration_sim_s": 5.0 if task == "DYNAMIC" else 0.0,
                    },
                )
                assert planner.model_snapshot is not None
                budget_data = binding.edge_policy.get("verification_budget")
                if not isinstance(budget_data, Mapping):
                    raise ValueError("frozen pilot verification limits are unavailable")
                limits = VerificationBudget(**dict(budget_data))
                episode_id = backend._episode_id
                if type(episode_id) is not str or not episode_id:
                    raise RuntimeError("pilot backend did not supply its actual reset episode")
                runtime = VisualWorkerRuntime(
                    owner.source,
                    episode_id=episode_id,
                    instruction=owner.instruction,
                    role_binding=binding,
                    model_snapshot_hash=planner.model_snapshot.digest(),
                    verification_limits=limits,
                )
                runtime.check_active(robot.get_state())
                owner.check_active()
                policy = ExecutionPolicy(
                    instruction=owner.instruction,
                    model_snapshot_hash=planner.model_snapshot.digest(),
                    output_dir=directory,
                    timeout_s=max(0.001, owner.remaining_s()),
                    supervision_period_s=assignment["period_s"],
                    advance_physics_during_wait=True,
                    verification_budget=limits,
                    device_pipeline="OPENCV",
                    role_binding=binding,
                    worker_runtime=runtime,
                    raw_recorder=recorder,
                    cancelled=owner.cancelled,
                )
                outcome = run_visual_episode(planner, robot, capture, policy)
                owner.check_active()
                owner.record_outcome(outcome)
            # Detached labels and fault logs are published only after termination.
            write_json(directory / "commands.json", backend.command_records)
            write_json(directory / "fault-events.json", backend.fault_records)
        finally:
            backend.shutdown()
    return PilotVisualWorkerResult(outcome, owner.source_evidence())
