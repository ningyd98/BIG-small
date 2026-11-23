"""One preallocated r593 development attempt using existing guarded components."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import platform
import shutil
import time
import traceback
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path

import cv2
import mujoco
import numpy as np
import PIL
from scripts.graduation.perception_io import ROOT, check_sources, pinned, read, sha, write

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.edge.evidence.conditions import (
    OnlineEvidenceSnapshot,
    evaluate_registered_conditions_v2,
)
from cloud_edge_robot_arm.edge.runtime.skill_executor import SkillExecutor
from cloud_edge_robot_arm.edge.runtime.skill_registry import SkillRegistry
from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
from cloud_edge_robot_arm.research.native_calibration_collection import (
    action_horizons,
    source_inventory,
)
from cloud_edge_robot_arm.research.native_calibration_collection import (
    digest as product_digest,
)
from cloud_edge_robot_arm.research.native_collection_grounding import (
    bootstrap_collection_tracker,
    bootstrap_registered_collection_tracker_v2,
    build_collection_contract_v2,
    collection_bootstrap_evidence,
    geometry_registration,
    registered_collection_grounding_preview_v2,
    registered_collection_step_v2,
    registered_expected_conditions_v2,
    registered_nominal_region_policy_v1,
    validate_camera,
    validate_registration_handoff,
)
from cloud_edge_robot_arm.research.sol_molmo_components import (
    ComponentStopped,
    check_component_hard_state,
    check_component_lease,
)
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.motion_controller import MotionTarget
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.simulation.mujoco.visual_servo import (
    VisualServoConfig,
    VisualServoSession,
)
from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository
from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker
from cloud_edge_robot_arm.vision.execution import research_safety_shield, resolved_step
from cloud_edge_robot_arm.vision.marker_families import SIDE_PREPARE_ONLY_FAMILY
from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame
from cloud_edge_robot_arm.vision.owner_registration import RegisteredGroundingFrameInputsV2
from cloud_edge_robot_arm.vision.servo import OpenCVServoFeedback


def plain(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if dataclasses.is_dataclass(value):
        return {f.name: plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(x) for x in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


R593_SOURCE_SCHEMA = "native.calibration.operational.v4"
R593_CONFIG = "configs/research/native_operational_calibration_side_y_plus_75mm_r593.yaml"


def inventory():
    return source_inventory(
        marker_family_id=SIDE_PREPARE_ONLY_FAMILY, protocol_schema=R593_SOURCE_SCHEMA
    )


def bind_catalog(raw, full, marked_asset):
    paths = {str(p.relative_to(ROOT)) for p in (ROOT / "src/cloud_edge_robot_arm").rglob("*.py")}
    paths.update(
        {
            R593_CONFIG,
            marked_asset,
            "assets/robots/franka_panda/scene.xml",
            "assets/robots/franka_panda/scene_pose_marker_outboard_v3.xml",
            "scripts/collect_native_calibration.py",
            "pyproject.toml",
        }
    )
    independent = {}
    for name in sorted(paths):
        path = ROOT / name
        if not path.is_file() or path.resolve() != path or not path.is_relative_to(ROOT):
            raise ValueError("catalog path is not a regular project file")
        independent[name] = sha(path)
    default = source_inventory(marker_family_id=SIDE_PREPARE_ONLY_FAMILY)
    if independent != full or default != full or len(full) != 456:
        raise ValueError("r593 independently enumerated source generation differs")
    catalog_file = raw / "r593-v4-source-inventory.json"
    write(catalog_file, full)
    catalog_file.chmod(0o444)
    if pinned(catalog_file, sha(catalog_file)) != independent:
        raise ValueError("private catalog bytes differ from independent enumeration")
    return {
        "family": SIDE_PREPARE_ONLY_FAMILY,
        "selection": R593_SOURCE_SCHEMA,
        "default_matches_entry_by_entry": True,
        "count": len(full),
        "config": R593_CONFIG,
        "config_sha256": full[R593_CONFIG],
        "product_compact_sorted_utf8_sha256": product_digest(full),
        "development_default_separators_sorted_utf8_sha256": digest(full),
        "archived_json_sha256": sha(catalog_file),
        "private_filename": catalog_file.name,
    }


def clock_preflight(marked_asset):
    evidence = {}
    for label, asset, dt in (
        ("canonical", "assets/robots/franka_panda/scene.xml", SimulatorConfig().physics_dt_s),
        ("visual", marked_asset, 1 / 240),
    ):
        xml = ET.parse(ROOT / asset).getroot().find("option")
        config = SimulatorConfig(model_path=str(ROOT / asset), physics_dt_s=dt)
        backend = MuJoCoPhysicsBackend()
        try:
            backend.initialize(config)
            effective = float(backend._model.opt.timestep)
            if effective != dt or backend.total_physics_steps != 0:
                raise ValueError("non-running model initialization clock mismatch")
            evidence[label] = {
                "asset": asset,
                "xml_dt_s": float(xml.attrib["timestep"]),
                "config_dt_s": dt,
                "initialized_effective_dt_s": effective,
                "simulator_resets": 0,
                "mj_steps": 0,
                "software_grid_end_step": 6000,
                "software_grid_end_s": 6000 * dt,
            }
        finally:
            backend.shutdown()
    return evidence


def allocate(plan, raw, out):
    from OpenGL import GL

    if os.environ.get("MUJOCO_GL") != "egl" or shutil.disk_usage(raw).free < 2**30:
        raise ValueError("preallocated EGL and 1 GiB free disk required")
    if (raw / "instance").exists():
        raise ValueError("development execution directory already exists")
    ctx = mujoco.GLContext(320, 240)
    try:
        ctx.make_current()
        gpu = GL.glGetString(GL.GL_RENDERER).decode()
    finally:
        ctx.free()
    case = read(plan)["allocation"]
    geometry = geometry_registration(marker_family_id=SIDE_PREPARE_ONLY_FAMILY)
    full = inventory()
    companion = plan.parent.parent / "round-graduation-dynamic-source-catalog-20261123"
    clocks = clock_preflight(geometry["asset_path"])
    catalog = bind_catalog(raw, full, geometry["asset_path"])
    paths = [
        "scripts/graduation/dynamic_vision.py",
        "scripts/graduation/dynamic_vision_score.py",
        "scripts/graduation/perception_io.py",
        "scripts/graduation/perception_pixels.py",
        "scripts/phase7/frozen_vision.py",
        "tests/test_graduation_dynamic_vision.py",
        "assets/robots/franka_panda/scene.xml",
        geometry["asset_path"],
    ]
    sha_set = {path: sha(ROOT / path) for path in paths}
    write(
        out,
        {
            "schema": "graduation.r593.dynamic-allocation.v1",
            "issued_at": datetime.now(UTC).isoformat(),
            "case": case,
            "geometry": geometry,
            "asset_sha256": sha_set[geometry["asset_path"]],
            "plan_sha256": sha(plan),
            "plan_md_sha256": sha(plan.with_name("plan.md")),
            "source_catalog_plan_sha256": sha(companion / "plan.json"),
            "source_catalog_plan_md_sha256": sha(companion / "plan.md"),
            "canonical_allocation_sha256": sha(plan.with_name("allocation-physics.public.json")),
            "catalog": catalog,
            "clock_preflight": clocks,
            "baseline": "6416a6cc4b1b087c17cf1c738b202e8f28421e2a",
            "sources_sha256": sha_set,
            "component_catalog_sha256": digest(full),
            "component_catalog_count": len(full),
            "runtime": {
                "egl_renderer": gpu,
                "python": platform.python_version(),
                "mujoco": mujoco.__version__,
                "opencv": cv2.__version__,
                "pillow": PIL.__version__,
                "numpy": np.__version__,
                "free_bytes": shutil.disk_usage(raw).free,
                "cpu_count": os.cpu_count(),
            },
            "capture_grid": {
                "reset_step": 0,
                "passive_settle_steps": 120,
                "rgbd": [320, 240],
                "dt": [1, 240],
                "explicit_frames": (
                    "reset, bootstrap, same-step registration handoff, PRE, fresh servo reference, "
                    "due feedback, POST, LIFT/RELEASE return and 8-step dwell grid, terminal"
                ),
                "physics": "Detached step 0 and one sample per mj_step",
                "servo": dataclasses.asdict(VisualServoConfig()),
                "intermediate_unrendered": "30 Hz servo grid, no observer rendering",
                "archives": "Frames held through active TTL and sealed before offline scoring",
            },
            "selected_entry": {
                "contract": "build_collection_contract_v2, original eight intentions",
                "grounding": (
                    "bootstrap_collection_tracker/collection_bootstrap_evidence, "
                    "bootstrap_registered_collection_tracker_v2, registered_collection_step_v2"
                ),
                "source_guard": (
                    "Real isolated SQLite worker, check_component_lease and "
                    "check_component_hard_state. Hard check each step, 50 ms lease poll and "
                    "16,000-step limit"
                ),
                "admission": (
                    "registered_expected_conditions_v2/evaluate_registered_conditions_v2, "
                    "all original conditions must PASS. research_safety_shield.pre_check/post_check"
                ),
                "controller": (
                    "edge.runtime.SkillExecutor.execute_attempt, MuJoCoSkillRobot.visual_servo, "
                    "VisualServoSession/OpenCVServoFeedback and default development limits"
                ),
                "qualification": (
                    "Independent component evidence. NativeCollectionApplication, teacher "
                    "exceptions, native writer, registered owner and models are outside this run."
                ),
                "stop": "MuJoCoSkillRobot.safe_stop on first rejection, one instance",
                "job_ttl_s": 3600,
                "watchdog_s": 120,
                "maximum_wall_minutes": 60,
                "original_horizons": action_horizons(use_v2=True),
            },
            "private_output_suffix": raw.name + "/instance",
            "intent_descriptor": {
                "type": "preallocated deterministic development skill intentions",
                "model_calls": 0,
                "stages": case["visual_stages_in_order"],
            },
        },
    )


class Owner:
    def __init__(self, raw, allocation, alloc_sha):
        self.repo = SQLiteSimulationJobRepository(raw / "development-worker.db")
        self.begin = time.monotonic()
        self.worker = SimulationWorker(
            worker_id="graduation-r593-component",
            backend="MUJOCO",
            repository=self.repo,
            artifact_root=raw,
            lease_ttl_seconds=3600,
        )
        case = allocation["case"]
        self.job = self.repo.create_job(
            run_id=case["visual_id"].replace("/", ":"),
            batch_id="",
            backend="MUJOCO",
            scenario_id="S01_NORMAL_STATIC",
            control_mode="DEVELOPMENT_COMPONENTS",
            seed=case["visual_seed"],
            manifest_id="graduation-r593-dev",
            reproducibility_hash=alloc_sha,
            draft=allocation["intent_descriptor"],
            timeout_seconds=3600,
            max_attempts=1,
            artifact_root=str(raw),
            source_commit=allocation["baseline"],
            source_tree_hash=allocation["component_catalog_sha256"],
        )
        self.repo.update_status_cas(
            self.job.job_id,
            expected=RuntimeJobStatus.CREATED,
            next_status=RuntimeJobStatus.QUEUED,
            reason_code="development",
            worker_id="",
            lease_id="",
        )
        lease = self.repo.acquire_lease(
            worker_id=self.worker.worker_id, backend="MUJOCO", lease_ttl_seconds=3600
        )
        if lease is None:
            raise ValueError("development lease acquisition denied")
        self.lease = lease
        self.attempt = self.repo.start_attempt(self.job.job_id, worker_id=self.worker.worker_id)
        for old, new in [
            (RuntimeJobStatus.LEASED, RuntimeJobStatus.STARTING),
            (RuntimeJobStatus.STARTING, RuntimeJobStatus.RUNNING),
        ]:
            self.transition(old, new)
        self.job = self.repo.get_job(self.job.job_id)
        self.current()

    def transition(self, old, new):
        if not self.repo.update_status_cas(
            self.job.job_id,
            expected=old,
            next_status=new,
            reason_code="development",
            worker_id=self.worker.worker_id,
            lease_id=self.lease.lease_id,
            expected_lease_id=self.lease.lease_id,
        ):
            raise ValueError("development job transition denied")

    def current(self):
        return check_component_lease(self.worker, self.job, self.begin, expected_attempt=1)

    def close(self, complete):
        self.repo.finish_attempt(
            self.job.job_id,
            attempt=self.attempt.attempt,
            result="SUCCEEDED" if complete else "FAILED",
            error="" if complete else "guarded stop",
            artifact_paths={},
        )
        self.transition(RuntimeJobStatus.RUNNING, RuntimeJobStatus.FINALIZING)
        self.transition(
            RuntimeJobStatus.FINALIZING,
            RuntimeJobStatus.SUCCEEDED if complete else RuntimeJobStatus.FAILED,
        )
        self.repo.release_lease(self.lease.lease_id)
        return {
            "worker": self.worker.worker_id,
            "run_id": self.job.run_id,
            "job_id": self.job.job_id,
            "attempt": self.attempt.attempt,
            "final_job_status": self.repo.get_job(self.job.job_id).status,
            "lease_released": True,
        }


class Episode:
    def __init__(self, raw, alloc, alloc_sha, catalog):
        self.raw, self.alloc, self.alloc_sha, self.catalog = raw, alloc, alloc_sha, catalog
        self.case = alloc["case"]
        self.geometry = alloc["geometry"]
        self.owner = Owner(raw, alloc, alloc_sha)
        self.backend = MuJoCoPhysicsBackend()
        self.robot = MuJoCoSkillRobot(self.backend)
        self.executor = SkillExecutor(robot=self.robot, registry=SkillRegistry.default())
        self.shield = research_safety_shield()
        self.frames = []
        self.audit = []
        self.report = {
            "control": "development worker, registered conditions and research Shield; "
            "no native or formal execution authority",
            "actions": [
                {"skill": s, "status": "NOT_RUN"} for s in self.case["visual_stages_in_order"]
            ],
        }
        self.phase = "RESET"
        self.action = None
        self.registration = NativeGeometryRegistration(self.geometry)

    def active(self):
        lease = self.owner.current()
        check_component_hard_state(self.backend, self.robot)
        return lease

    def capture(self, label):
        sensor = self.backend.capture_sensor_frame()
        obs = observation_from_sensor_frame(sensor, source="mujoco_camera", png_compress_level=1)
        validate_camera(obs, self.geometry)
        self.frames.append((self.backend.total_physics_steps, label, obs))
        return obs

    def bootstrap(self):
        boot = self.capture("bootstrap")
        lease = self.active()
        self.color, self.evidence = bootstrap_collection_tracker(boot, self.geometry)
        self.report["bootstrap"] = {
            "frame_id": boot.frame_id,
            "checksum_sha256": boot.checksum_sha256,
            "original_pixel_target": self.evidence["original_pixel_target"],
            "original_pixel_destination": self.evidence["original_pixel_destination"],
            "resolved_top_grasp_tcp_m": self.evidence["resolved_top_grasp_tcp"],
            "depth_error_bound_m": self.evidence["depth_error_bound_m"],
        }
        issued = lease.acquired_at
        self.original = build_collection_contract_v2(
            assignment=self.case,
            current_owner={
                "task_id": "graduation-r593-task",
                "plan_id": "graduation-r593-plan",
                "issued_at": issued,
                "deadline_at": issued + timedelta(seconds=3600),
                "role_sha256": digest(self.alloc["intent_descriptor"]),
                "lease": lease,
            },
            geometry=self.geometry,
            source_hashes=self.catalog,
            observation=boot,
            protocol_settings={"timeout_basis": "physics_steps"},
        )
        preview_evidence = {
            **self.evidence,
            "grounded_destination": boot.world_point(
                self.evidence["original_pixel_destination"]
            ).model_dump(),
        }
        preview_step = resolved_step(self.original.contract.steps[0], self.robot, preview_evidence)
        self.report["bootstrap"]["resolver_candidate_m"] = preview_step.parameters["target_pose"]
        self.report["bootstrap"]["resolver_use"] = "read-only development comparison"
        self.report["bootstrap"]["physics_step"] = self.backend.total_physics_steps
        before_reset = self.frames[0][2]
        try:
            zero = collection_bootstrap_evidence(before_reset, self.geometry)
            zero["grounded_destination"] = before_reset.world_point(
                zero["original_pixel_destination"]
            ).model_dump()
            zero_step = resolved_step(self.original.contract.steps[0], self.robot, zero)
            self.report["bootstrap"]["reset_readonly"] = {
                "physics_step": self.frames[0][0],
                "checksum_sha256": before_reset.checksum_sha256,
                "frame_id": before_reset.frame_id,
                "target_pixel": zero["original_pixel_target"],
                "destination_pixel": zero["original_pixel_destination"],
                "top_grasp_tcp_m": zero["resolved_top_grasp_tcp"],
                "read_only_move_above_m": zero_step.parameters["target_pose"],
                "use": "step-0 read-only comparison; actual stage uses separate fresh pixels",
            }
        except ValueError as exc:
            self.report["bootstrap"]["reset_readonly"] = {"physics_step": 0, "refusal": str(exc)}

        before = self.backend.total_physics_steps
        fresh = self.capture("registration-handoff")
        validate_registration_handoff(
            self.original,
            lease.to_payload(),
            boot,
            fresh,
            step_before=before,
            step_after=self.backend.total_physics_steps,
            now=datetime.now(UTC),
        )
        self.registered = bootstrap_registered_collection_tracker_v2(
            fresh,
            self.registration,
            source_root=ROOT,
            source_hashes=self.catalog,
            nominal_policy=registered_nominal_region_policy_v1(self.catalog),
        )

    def check_shield(self, obs, phase, contract, step, started, clearance):
        now = datetime.now(UTC)
        velocity = float(step.parameters.get("tcp_velocity", 0))
        context = self.shield.context_builder.build(
            contract=contract,
            step=step,
            robot_state=self.robot.get_state(),
            scene_version=contract.scene_version,
            resolved_parameters=dict(step.parameters),
            scene_updated_at=obs.captured_at,
            telemetry_timestamp=now,
            wall_clock_now=now,
            step_started_at_mono=started,
            task_started_at_mono=self.owner.begin,
            monotonic_now=time.monotonic(),
            requested_joint_velocities=[
                *map(abs, self.backend.get_joint_state().velocities),
                velocity / 0.3,
            ],
            requested_velocity=velocity,
            requested_acceleration=float(step.parameters.get("acceleration", 0)),
            vertical_clearance=clearance,
            expected_holding_object_id="object"
            if step.skill.value in {"LIFT", "MOVE_TO_REGION", "PLACE"}
            else None,
        )
        fn = self.shield.post_check if phase == "POST" else self.shield.pre_check
        verdict = fn(context)
        details = plain(verdict)
        self.audit.append(
            {
                "phase": phase,
                "step_id": step.step_id,
                "frame_id": obs.frame_id,
                "target_pose": step.parameters.get("target_pose"),
                "shield": details,
            }
        )
        return {
            "allowed": verdict.allowed,
            "unmodified": verdict.limited_parameters in (None, step.parameters),
            "result": details,
        }

    def admission(self, obs, phase, contract, step, binding, started, clearance):
        self.active()
        state = self.robot.get_state()
        preview = registered_collection_grounding_preview_v2(self.registered, obs, state)
        inputs = (
            RegisteredGroundingFrameInputsV2.from_preview(preview, obs, self.registration)
            if preview.status == "DERIVED"
            else None
        )
        snap = OnlineEvidenceSnapshot(
            obs, state, self.color.facts(obs, state), 1, 1, self.original.digest()
        )
        conditions = registered_expected_conditions_v2(self.original, binding, phase)
        verdicts = evaluate_registered_conditions_v2(
            conditions, snap, grounding_inputs=inputs, now=datetime.now(UTC)
        )
        shield = self.check_shield(obs, phase, contract, step, started, clearance)
        self.action[phase.lower()] = {
            "frame_id": obs.frame_id,
            "checksum_sha256": obs.checksum_sha256,
            "conditions": [
                {"name": v.condition_name, "status": v.status.value, "reasons": list(v.reasons)}
                for v in verdicts
            ],
            "shield": shield,
        }
        self.audit.append(
            {
                "phase": phase,
                "preview": preview.to_payload(),
                "verdicts": plain(verdicts),
                "requirements": plain(conditions),
                "state": plain(state),
            }
        )
        reasons = [
            v.condition_name + "=" + v.status.value for v in verdicts if v.status.value != "PASS"
        ]
        if not shield["allowed"] or not shield["unmodified"]:
            reasons.append("SAFETY_SHIELD_REJECTED_OR_LIMITED")
        if reasons:
            raise ComponentStopped(phase + " " + ",".join(reasons))

    def execute(self, index):
        action = self.report["actions"][index]
        self.action = action
        name = action["skill"]
        started = time.monotonic()
        action.update(
            status="ENTERED", entered_step=self.backend.total_physics_steps, dispatched=False
        )
        self.phase = "GROUNDING"
        current = self.capture(name + "/PRE")
        contract, step, binding, _, _ = registered_collection_step_v2(
            self.original,
            index=index,
            observation=current,
            state=self.robot.get_state(),
            tracker=self.registered,
            lease_source=self.active(),
            evidence_sink=self.audit.append,
        )
        target = step.parameters.get("target_pose")
        if index == 0:
            self.report["candidate"] = {
                "skill": name,
                "frame_id": current.frame_id,
                "checksum_sha256": current.checksum_sha256,
                "target_pose_m": target,
                "binding_sha256": binding.digest(),
            }
        clearance = None
        if name in {"LIFT", "RETREAT"} and target:
            pose = self.robot.get_state().tcp_pose
            if (target["x"], target["y"]) == (pose.x, pose.y):
                clearance = VerticalClearancePath(
                    task_id=contract.task_id,
                    step_id=step.step_id,
                    skill=name,
                    start_m=(pose.x, pose.y, pose.z),
                    target_m=tuple(target[k] for k in "xyz"),
                    minimum_height_m=max(0.08, contract.safety_constraints.minimum_safe_height),
                )
        self.phase = "PRE"
        self.admission(current, "PRE", contract, step, binding, started, clearance)
        session = None
        provider = None
        if target and name not in {"GRASP", "RELEASE"}:
            self.phase = "SERVO_REFERENCE"
            ref = self.capture(name + "/servo_reference")
            provider = OpenCVServoFeedback(
                ref,
                self.color,
                self.evidence,
                skill=name,
                initial_target=Pose.model_validate(target),
                marker_family_id=SIDE_PREPARE_ONLY_FAMILY,
                verify_mujoco_calibration=True,
            )

            def sample(previous):
                self.active()
                fresh = self.capture(name + "/feedback")
                measured = provider.update(fresh)
                dynamic = step.model_copy(
                    update={
                        "parameters": {**step.parameters, "target_pose": measured.model_dump()}
                    },
                    deep=True,
                )
                updated = contract.model_copy(
                    update={
                        "steps": [
                            dynamic if s.step_id == step.step_id else s for s in contract.steps
                        ]
                    },
                    deep=True,
                )
                verdict = self.check_shield(fresh, "FEEDBACK", updated, dynamic, started, clearance)
                if not verdict["allowed"] or not verdict["unmodified"]:
                    raise ComponentStopped("dynamic research Shield rejected or limited")
                self.active()
                return MotionTarget(measured, previous.orientation_wxyz)

            session = VisualServoSession(sample, vertical_clearance=clearance)
        self.active()
        self.phase = "CONTROLLER"
        action["dispatched"] = True
        action["dispatch_step"] = self.backend.total_physics_steps
        try:
            with self.robot.visual_servo(session) if session else nullcontext():
                outcome = self.executor.execute_attempt(contract=contract, step=step, attempt=1)
        finally:
            if session is not None:
                action["feedback_accepted"] = len(provider.records)
                action["servo_terminal_reason"] = session.terminal_reason
                self.audit.append(
                    {
                        "phase": "servo",
                        "skill": name,
                        "control_samples": plain(session.records),
                        "visual_samples": plain(provider.records),
                    }
                )
        action["controller_return_step"] = self.backend.total_physics_steps
        action["controller_result"] = {
            "success": outcome.success,
            "code": outcome.error_code,
            "details": plain(outcome.error),
        }
        self.audit.append({"phase": "controller", "receipt": plain(outcome)})
        if not outcome.success:
            raise ComponentStopped("controller: " + str(outcome.error_code))
        if name in {"LIFT", "RELEASE"}:
            action["dwell_start_step"] = self.backend.total_physics_steps
            self.capture(name + "/dwell-0")
            for tick in range(8, (120 if name == "LIFT" else 240) + 1, 8):
                self.active()
                self.backend.step(8)
                self.capture(name + "/dwell-" + str(tick))
        self.phase = "POST"
        post = self.capture(name + "/POST")
        self.admission(post, "POST", contract, step, binding, started, clearance)
        action.update(status="PASS", end_step=self.backend.total_physics_steps)

    def run(self):
        config = SimulatorConfig(
            model_path=str(ROOT / self.geometry["asset_path"]),
            seed=self.case["visual_seed"],
            physics_dt_s=1 / 240,
            domain_randomization=False,
            render_rgb=True,
            render_depth=True,
        )
        self.backend.initialize(config)
        x, y, z = self.case["reset_fixture_center_m"]
        self.backend.reset(
            PhysicalScenarioConfig(
                scenario_id="S01_NORMAL_STATIC",
                seed=self.case["visual_seed"],
                object_pose=Pose(x=x, y=y, z=z),
                object_yaw_rad=self.case["yaw_rad"],
            )
        )
        snapshots = [self.backend.current_physics_observation()]
        last_poll = time.monotonic()

        def observe(snapshot):
            nonlocal last_poll
            snapshots.append(snapshot)
            now = time.monotonic()
            if self.backend.total_physics_steps >= 16000:
                raise ComponentStopped("COMPONENT_PHYSICS_BUDGET_EXHAUSTED")
            if now - self.owner.begin >= self.owner.job.timeout_seconds:
                raise ComponentStopped("COMPONENT_TASK_DEADLINE_OR_LEASE_FAILURE")
            if now - last_poll >= 0.05:
                self.owner.current()
                last_poll = now
            check_component_hard_state(self.backend, self.robot)

        with self.backend.observe_physics_steps(observe):
            try:
                self.capture("reset")
                self.phase = "SETTLE"
                with self.backend.sensor_capture_on_demand():
                    self.backend.step(120)
                self.phase = "BOOTSTRAP"
                self.bootstrap()
                for index in range(len(self.report["actions"])):
                    self.execute(index)
            except Exception as exc:
                stack = traceback.extract_tb(exc.__traceback__)
                self.audit.append(
                    {
                        "phase": self.phase,
                        "stop_stack": [
                            {
                                "source": Path(entry.filename).name,
                                "line": entry.lineno,
                                "function": entry.name,
                            }
                            for entry in stack
                        ],
                    }
                )
                product_origin = Path(stack[-1].filename).is_relative_to(
                    ROOT / "src/cloud_edge_robot_arm"
                )
                classification = "SOFTWARE_ADAPTATION_OR_OPERATION_ERROR"
                if isinstance(exc, ComponentStopped):
                    classification = "COMPONENT_GUARD_OR_CONTROLLER_STOP"
                elif (
                    isinstance(exc, ValueError)
                    and product_origin
                    and self.phase
                    in {
                        "GROUNDING",
                        "SERVO_REFERENCE",
                        "PRE",
                        "POST",
                    }
                ):
                    classification = "COMPONENT_INPUT_OR_ADMISSION_REFUSAL"
                self.report["stop"] = {
                    "classification": classification,
                    "origin": Path(stack[-1].filename).name,
                    "function": stack[-1].name,
                    "phase": self.phase,
                    "type": type(exc).__name__,
                    "reason": str(exc),
                    "skill": self.action["skill"] if self.action else None,
                    "physics_step": self.backend.total_physics_steps,
                }
                if self.action is not None:
                    self.action.update(status="STOPPED", end_step=self.backend.total_physics_steps)
                self.report["safe_stop"] = plain(self.robot.safe_stop())
            self.capture("terminal")
        self.report["lease_summary"] = self.owner.close("stop" not in self.report)
        self.backend.shutdown()
        frame_rows = []
        (self.raw / "frames").mkdir()
        for i, (step, label, obs) in enumerate(self.frames):
            path = f"frames/{i:04d}.json"
            write(self.raw / path, obs.model_dump(mode="json"))
            frame_rows.append(
                {
                    "physics_step": step,
                    "label": label,
                    "frame_id": obs.frame_id,
                    "checksum_sha256": obs.checksum_sha256,
                    "file": path,
                    "file_sha256": sha(self.raw / path),
                }
            )
        first = self.frames[0][2]
        write(
            self.raw / "pixel-index.json",
            {
                "allocation_sha256": self.alloc_sha,
                "frames": frame_rows,
                "episode": first.episode_id,
                "scene": first.scene_id,
            },
        )
        write(self.raw / "online-audit.json", plain(self.audit))
        write(self.raw / "run.json", plain(self.report))
        write(
            self.raw / "offline-truth.json",
            {
                "allocation_sha256": self.alloc_sha,
                "asset_sha256": self.alloc["asset_sha256"],
                "episode": first.episode_id,
                "samples": [dataclasses.asdict(s) for s in snapshots],
            },
        )
        write(
            self.raw / "acquisition-seal.json",
            {
                "index_sha256": sha(self.raw / "pixel-index.json"),
                "audit_sha256": sha(self.raw / "online-audit.json"),
                "run_sha256": sha(self.raw / "run.json"),
                "truth_sha256": sha(self.raw / "offline-truth.json"),
            },
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    allocate_cli = sub.add_parser("allocate")
    allocate_cli.add_argument("plan", type=Path)
    allocate_cli.add_argument("raw_parent", type=Path)
    allocate_cli.add_argument("output", type=Path)
    run_cli = sub.add_parser("run")
    run_cli.add_argument("allocation", type=Path)
    run_cli.add_argument("sha256")
    run_cli.add_argument("raw_parent", type=Path)
    args = parser.parse_args()
    if args.command == "allocate":
        allocate(args.plan, args.raw_parent, args.output)
        return
    alloc = pinned(args.allocation, args.sha256)
    check_sources(alloc)
    catalog = inventory()
    if digest(catalog) != alloc["component_catalog_sha256"] or os.environ.get("MUJOCO_GL") != "egl":
        raise ValueError("component catalog or EGL mismatch")
    archived = pinned(
        args.raw_parent / alloc["catalog"]["private_filename"],
        alloc["catalog"]["archived_json_sha256"],
    )
    if (
        archived != catalog
        or product_digest(archived) != (alloc["catalog"]["product_compact_sorted_utf8_sha256"])
    ):
        raise ValueError("sealed source catalog no longer matches")
    dest = args.raw_parent / "instance"
    dest.mkdir()
    Episode(dest, alloc, args.sha256, catalog).run()


if __name__ == "__main__":
    main()
