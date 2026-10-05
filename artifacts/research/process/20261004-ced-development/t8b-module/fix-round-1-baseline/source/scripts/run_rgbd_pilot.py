"""Preregister a real 120-scene foundation pilot and retain every failure/block."""

from __future__ import annotations

import argparse
import base64
import copy
import io
import json
import os
import shutil
import sys
import threading
import time
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from PIL import Image

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec, content_digest
from cloud_edge_robot_arm.edge.recovery.verification_router import VerificationBudget
from cloud_edge_robot_arm.research.budget import estimate_budget
from cloud_edge_robot_arm.research.cost_ledger import CostLedger
from cloud_edge_robot_arm.research.network import NetworkInjector, NetworkSchedule
from cloud_edge_robot_arm.research.pilot import PilotReport, derive_tcap, run_pilot_stage
from cloud_edge_robot_arm.research.protocol import (
    NETWORKS,
    ProtocolSpec,
    build_scene_pools,
    file_hash,
    read_excluded_groups,
)
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalFault, PhysicalFaultType
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession, save_observation
from cloud_edge_robot_arm.vision.evaluation import ExecutionPolicy, write_json
from cloud_edge_robot_arm.vision.execution import run_visual_episode
from cloud_edge_robot_arm.vision.frozen_model import load_frozen_planner
from cloud_edge_robot_arm.vision.observations import RGBDObservation


class PerturbedCapture(MuJoCoCaptureSession):
    """Offline-fixed sensor faults; never inspect target labels to choose corruption."""

    noise_m = 0.0
    invalid_fraction = 0.0
    occlusion_fraction = 0.0
    raw_directory: Path | None = None
    frame_count = 0
    perturbation_seed = 0

    def capture(self) -> RGBDObservation:
        observation = super().capture()
        self.frame_count += 1
        if self.raw_directory is not None:
            save_observation(observation, self.raw_directory / f"{self.frame_count:05d}")
        if not (self.noise_m or self.invalid_fraction or self.occlusion_fraction):
            return observation
        rng = np.random.default_rng(self.perturbation_seed + self.frame_count)
        depth = np.asarray(observation.depth_values(), dtype="<f4").reshape(
            observation.height, observation.width
        )
        valid = depth > 0
        depth[valid] += rng.normal(0, self.noise_m, int(valid.sum()))
        depth[rng.random(depth.shape) < self.invalid_fraction] = 0
        depth[depth < 0] = 0
        with Image.open(io.BytesIO(base64.b64decode(observation.rgb_png_base64))) as image:
            rgb = np.asarray(image.convert("RGB")).copy()
        width = round(observation.width * self.occlusion_fraction)
        if width:
            start = (observation.width - width) // 2
            rgb[:, start : start + width] = 0
            depth[:, start : start + width] = 0
        encoded = io.BytesIO()
        Image.fromarray(rgb).save(encoded, format="PNG")
        data = observation.model_dump()
        data.update(
            rgb_png_base64=base64.b64encode(encoded.getvalue()).decode(),
            depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
            valid_mask_base64=None,
            checksum_sha256="",
        )
        return RGBDObservation.model_validate(data)


def publish_final_costs(
    report: PilotReport, ledgers: list[tuple[CostLedger, Path]], *, settle_timeout_s: float = 5.0
) -> int:
    """Take one settled snapshot per case and publish it consistently everywhere."""
    deadline = time.monotonic() + settle_timeout_s
    while any(r.status == "IN_FLIGHT" for ledger, _ in ledgers for r in ledger.requests()):
        if time.monotonic() >= deadline:
            break
        time.sleep(0.025)
    rows = {row["assignment_id"]: row for row in report.records}
    inflight = 0
    for ledger, directory in ledgers:
        publication = ledger.export()
        pending = sum(r["status"] == "IN_FLIGHT" for r in publication["requests"])
        inflight += pending
        snapshot = publication["summary"]
        row = rows[directory.name]
        row.update(
            costs=snapshot,
            model_calls=snapshot["model_requests"],
            cost_settlement="UNSETTLED" if pending else "SETTLED",
            inflight_requests=pending,
        )
        write_json(
            directory / "costs.json",
            {
                **publication,
                "settlement": row["cost_settlement"],
            },
        )
        write_json(directory / "case-result.json", row)
    return inflight


def run_foundation(config_path: Path, output: Path) -> dict[str, Any]:
    settings = yaml.safe_load(config_path.read_text())
    if isinstance(settings, dict) and settings.get("protocol_version") == "ced.research.v2":
        return run_ced_pilot(config_path, output, "foundation")
    if settings["episodes"] != 120 or settings["b0_period_s"] not in (0.5, 1, 2, 5):
        raise ValueError("foundation needs 120 scenes and a preregistered B0 period")
    excluded = read_excluded_groups([Path(p) for p in settings["exclude_datasets"]])
    for previous in settings.get("exclude_pilots", []):
        old = json.loads((Path(previous) / "assignments.json").read_text())
        excluded.update(row["scene"]["group_id"] for row in old)
    pools = build_scene_pools(int(settings["seed"]), excluded)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "pools.json", pools)
    write_json(output / "assignments.json", pools["foundation"])
    write_json(output / "excluded-groups.json", sorted(excluded))
    (output / "config.yaml").write_bytes(config_path.read_bytes())
    sources = [
        *sorted(Path("src/cloud_edge_robot_arm").rglob("*.py")),
        *sorted(Path("scripts").rglob("*.py")),
        *sorted(Path("configs/research").glob("*.yaml")),
        Path("assets/robots/franka_panda/scene.xml"),
        Path("pyproject.toml"),
    ]
    write_json(output / "source-hashes.json", {str(p): file_hash(p) for p in sources})
    for source in sources:
        archived = output / "source" / source
        archived.parent.mkdir(parents=True, exist_ok=True)
        archived.write_bytes(source.read_bytes())
    write_json(
        output / "pool-audit.json",
        {
            "pool_hashes": {k: content_digest(v) for k, v in pools.items()},
            "excluded_group_count": len(excluded),
            "excluded_group_ids_hash": content_digest(sorted(excluded)),
            "model_snapshot_hash": None,
            "seed": settings["seed"],
            "all_groups_disjoint": True,
            "opportunity_snapshots": "NOT_EXECUTED",
            "recovery_fault_manifest": "NOT_EXECUTED",
        },
    )
    planner = None
    blocked_reason = None
    try:
        planner = load_frozen_planner(Path(settings["frozen_dir"]))
        shutil.copytree(settings["frozen_dir"], output / "model-probe")
    except Exception as exc:
        blocked_reason = f"BLOCKED_BY_ENV: {type(exc).__name__}: {exc}"
    report = PilotReport(assigned=120)
    ledgers = []
    for assignment in pools["foundation"]:
        directory = output / "cases" / assignment["assignment_id"]
        directory.mkdir(parents=True)
        write_json(directory / "assignment.json", assignment)
        ledger = CostLedger()
        ledgers.append((ledger, directory))
        started = time.monotonic()
        row: dict[str, Any] = {
            "assignment_id": assignment["assignment_id"],
            "stratum_id": assignment["stratum_id"],
            "scene_hash": assignment["scene_hash"],
            "success": False,
            "blocked": False,
        }
        try:
            if planner is None:
                raise RuntimeError(blocked_reason)
            active = copy.copy(planner)
            active.cost_ledger = ledger
            rtt = int(assignment["stratum_id"].split("RTT")[1])
            loss = dict(NETWORKS)[rtt]
            scene = SceneSpec.model_validate(assignment["scene"])
            schedule = NetworkSchedule(
                schedule_id=assignment["assignment_id"], rtt_ms=rtt, loss_rate=loss, seed=scene.seed
            )
            active.network_injector = NetworkInjector(schedule)
            config = SimulatorConfig(
                render_rgb=True, render_depth=True, domain_randomization=False, seed=scene.seed
            )
            capture = PerturbedCapture(config)
            with capture:
                capture.apply_scene(scene)
                capture._backend.step(steps=120)
                capture.raw_directory = directory / "raw-frames"
                capture.perturbation_seed = scene.seed
                task = assignment["stratum_id"].split("_RTT")[0]
                perturbation = assignment["perturbation"]
                if task == "SENSOR":
                    capture.noise_m = perturbation["noise_m"]
                    capture.invalid_fraction = perturbation["invalid_fraction"]
                    capture.occlusion_fraction = perturbation["occlusion_fraction"]
                if task == "DYNAMIC":
                    capture._backend.inject_fault(
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
                        "assignment": perturbation,
                        "task": task,
                        "sensor_applied_from_frame": 1,
                        "movement_duration_sim_s": 5.0 if task == "DYNAMIC" else 0.0,
                        "network": schedule.model_dump(mode="json"),
                    },
                )
                color = scene.scene_parameters["target"]["color_name"]
                assert active.model_snapshot is not None
                policy = ExecutionPolicy(
                    instruction=f"Move the {color} block to the green region.",
                    model_snapshot_hash=active.model_snapshot.digest(),
                    output_dir=directory,
                    timeout_s=float(settings["timeout_s"]),
                    supervision_period_s=float(settings["b0_period_s"]),
                    advance_physics_during_wait=True,
                    verification_budget=VerificationBudget(**settings["verification_budget"]),
                )
                outcome = run_visual_episode(
                    active, MuJoCoSkillRobot(capture._backend), capture, policy
                )
                row.update(
                    {k: v for k, v in asdict(outcome).items() if k != "verification_records"}
                )
                row["blocked"] = bool(
                    outcome.terminal_reason and outcome.terminal_reason.startswith("BLOCKED_BY_ENV")
                )
                row["network_cost"] = active.network_injector.snapshot().model_dump(mode="json")
                write_json(directory / "fault-events.json", capture._backend.fault_records)
        except Exception as exc:
            # Never erase already recorded stages if a runner exception follows motion.
            row.update(
                blocked=planner is None,
                status="BLOCKED" if planner is None else "FAILED",
                terminal_reason=f"{type(exc).__name__}: {exc}",
                model_calls=ledger.snapshot().model_requests,
                stage_accounting="SEE_RAW_CASE_ARTIFACTS",
            )
        row["wall_duration_s"] = time.monotonic() - started
        write_json(
            directory / "costs.json",
            {
                "summary": ledger.snapshot().model_dump(),
                "requests": [r.model_dump(mode="json") for r in ledger.requests()],
            },
        )
        row["artifact_bytes"] = sum(p.stat().st_size for p in directory.rglob("*") if p.is_file())
        row["costs"] = ledger.snapshot().model_dump()
        write_json(directory / "case-result.json", row)
        report.records.append(row)
        write_json(output / "progress.json", report.summary())
        print(
            f"{row['assignment_id']} {row['stratum_id']}: "
            f"{row.get('status', 'BLOCKED')} {row.get('terminal_reason', '')}",
            flush=True,
        )
    # A late actual response updates its own ledger, never online state or success.
    inflight = publish_final_costs(report, ledgers)
    summary = {
        **report.summary(),
        "method_id": "B0",
        "b0_period_s": settings["b0_period_s"],
        "formal_g1": False,
        "inflight_requests": inflight,
        "protocol_snapshot_complete": False,
        "status": "COMPLETE" if len(report.records) == 120 else "INCOMPLETE",
        "research_acceptance": "NOT_ACCEPTED_PENDING_PROTOCOL_EVIDENCE",
    }
    durations = [r["wall_duration_s"] for r in report.records if r.get("success")]
    summary["tcap_s"] = derive_tcap(durations) if durations else None
    nominal = [r for r in report.records if r["stratum_id"].startswith("STATIC")]
    summary["nominal_success_rate"] = sum(r.get("success", False) for r in nominal) / len(nominal)
    summary["safety_violation_rate"] = (
        sum(r.get("safety_violation", False) for r in report.records) / 120
    )
    summary["baseline_feasibility"] = (
        "FEASIBLE"
        if summary["nominal_success_rate"] >= 0.9
        and summary["success_rate_all_assigned"] >= 0.8
        and summary["safety_violation_rate"] <= 0.01
        else "NO_FEASIBLE_BASELINE"
    )
    summary["model_snapshot_hash"] = (
        planner.model_snapshot.digest() if (planner and planner.model_snapshot) else None
    )
    write_json(output / "budget.json", estimate_budget(report, ProtocolSpec().formal_ns))
    write_json(output / "results.json", report.records)
    write_json(output / "summary.json", summary)
    write_json(output / "progress.json", summary)
    return summary


def _ced_pools(settings: Mapping[str, Any]) -> dict[str, Any]:
    """Exclude every supplied historical source before freezing all six pools."""
    from cloud_edge_robot_arm.research.pilot import validate_pilot_pools

    excluded = read_excluded_groups([Path(p) for p in settings["exclude_datasets"]])
    for previous in settings["exclude_pilots"]:
        source = Path(previous)
        rows = json.loads((source / "assignments.json").read_text())
        if isinstance(rows, dict):
            rows = rows["assignments"]
        if not isinstance(rows, list):
            raise ValueError("historical source assignments must be complete raw rows")
        for row in rows:
            base = row.get("base_assignment", row)
            scene = base.get("scene")
            group = scene["group_id"] if isinstance(scene, dict) else base.get("group_id")
            if not isinstance(group, str) or not group:
                raise ValueError("historical source group identity is unavailable")
            excluded.add(group)
    if settings["pools_path"]:
        pools = json.loads(Path(settings["pools_path"]).read_text())
    else:
        pools = build_scene_pools(
            int(settings["seed"]), excluded, protocol_version="ced.research.v2"
        )
    validate_pilot_pools(pools)
    if excluded & {row["scene"]["group_id"] for rows in pools.values() for row in rows}:
        raise ValueError("pilot pool reuses a previously used source group")
    return dict(pools)


class _RoleBoundPilotExecutor:
    """The existing B0/skill path with actual role binding and detached raw observers."""

    def __init__(self, settings: Mapping[str, Any], planner: Any, binding: Any, output: Path):
        self.settings, self.planner, self.binding, self.output = settings, planner, binding, output
        self.ledgers: list[tuple[CostLedger, Path]] = []
        self.archived = False

    def _archive(self) -> None:
        if self.archived:
            return
        from cloud_edge_robot_arm.research.pilot import stage_source_paths

        sources = stage_source_paths()
        write_json(self.output / "source-hashes.json", {str(p): file_hash(p) for p in sources})
        for source in sources:
            destination = self.output / "source" / source
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
        shutil.copytree(self.settings["role_probe"], self.output / "role-probe")
        for key, name in (
            ("selection_evidence", "selection-evidence"),
            ("protocol_evidence", "protocol-evidence"),
        ):
            if self.settings.get(key):
                shutil.copytree(self.settings[key], self.output / name)
        self.archived = True

    def __call__(self, assignment: Mapping[str, Any], directory: Path) -> Mapping[str, Any]:
        self._archive()
        active = copy.copy(self.planner)
        ledger = CostLedger()
        active.cost_ledger = ledger
        self.ledgers.append((ledger, directory))
        schedule = NetworkSchedule.model_validate(assignment["network_schedule"])
        active.network_injector = NetworkInjector(schedule)
        wire: list[dict[str, Any]] = []
        pending: dict[int, dict[str, Any]] = {}
        lock = threading.Lock()

        def observe(phase: str, path: str, raw: bytes) -> None:
            import hashlib

            from scripts.probe_rgbd_roles import _text_contains_credential

            # Hashing records actual bytes; a credential-bearing body is withheld.
            if active._api_key and _text_contains_credential(
                raw.decode(errors="replace"), active._api_key
            ):
                raise ValueError("credential-bearing body withheld")
            with lock:
                thread = threading.get_ident()
                if phase == "REQUEST":
                    if thread in pending:
                        raise ValueError("provider has multiple in-flight requests in one thread")
                    entry: dict[str, Any] = {
                        "request_path": f"wire/{len(wire):05d}.request.raw",
                        "request_sha256": hashlib.sha256(raw).hexdigest(),
                        "chat_path": path,
                        "serialized_sent_bytes": len(raw),
                        "serialized_received_bytes": 0,
                    }
                    wire.append(entry)
                    pending[thread] = entry
                    target = directory / entry["request_path"]
                else:
                    entry = pending.pop(thread)
                    entry.update(
                        response_path=entry["request_path"].replace("request", "response"),
                        response_sha256=hashlib.sha256(raw).hexdigest(),
                        serialized_received_bytes=len(raw),
                    )
                    target = directory / entry["response_path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as stream:
                    stream.write(raw)
                write_json(directory / "wire-index.json", wire)

        active.raw_transport_observer = observe
        scene = SceneSpec.model_validate(assignment["base_assignment"]["scene"])
        config = SimulatorConfig(
            render_rgb=True,
            render_depth=True,
            camera_width=320,
            camera_height=240,
            domain_randomization=False,
            seed=scene.seed,
        )
        started = time.monotonic()
        row: dict[str, Any] = {
            "assignment_id": assignment["assignment_id"],
            "success": False,
            "stratum_id": assignment["stratum_id"],
            "status": "FAILED",
            "safety_violation": False,
            "scope": "REAL_RUNTIME",
            "accepted_success": False,
            "wall_duration_s": 0.0,
            "cloud_requests": 0,
        }
        capture = PerturbedCapture(config)
        with capture:
            capture.apply_scene(scene)
            backend = capture._backend
            assert backend._data is not None
            raw: list[dict[str, Any]] = []
            controls: list[dict[str, Any]] = []
            initial = {
                "joints_rad": backend._target_positions.tolist(),
                "fingers_m": backend._data.ctrl[7:9].tolist(),
            }

            def collect(control: Any) -> None:
                # Read the preceding physical step through the detached actuator hook.
                # run_visual_episode retains ownership of its own physics observer.
                raw.append(asdict(backend.current_physics_observation()))
                controls.append(asdict(control))

            try:
                with backend.observe_actuator_steps(collect):
                    backend.step(steps=120)
                    capture.raw_directory = directory / "raw-frames"
                    capture.perturbation_seed = scene.seed
                    task = assignment["stratum_id"].split("_RTT")[0]
                    perturbation = assignment["base_assignment"]["perturbation"]
                    if task == "SENSOR":
                        capture.noise_m = perturbation["noise_m"]
                        capture.invalid_fraction = perturbation["invalid_fraction"]
                        capture.occlusion_fraction = perturbation["occlusion_fraction"]
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
                            "network": schedule.model_dump(mode="json"),
                        },
                    )
                    assert active.model_snapshot is not None
                    color = scene.scene_parameters["target"]["color_name"]
                    policy = ExecutionPolicy(
                        instruction=f"Move the {color} block to the green region.",
                        model_snapshot_hash=active.model_snapshot.digest(),
                        output_dir=directory,
                        timeout_s=float(self.settings["timeout_s"]),
                        supervision_period_s=assignment["period_s"],
                        advance_physics_during_wait=True,
                        verification_budget=VerificationBudget(
                            **dict(self.binding.edge_policy["verification_budget"])
                        ),
                        device_pipeline="OPENCV",
                        role_binding=self.binding,
                    )
                    self.binding.validate(active)
                    outcome = run_visual_episode(active, MuJoCoSkillRobot(backend), capture, policy)
                    row.update(
                        {
                            key: value
                            for key, value in asdict(outcome).items()
                            if key != "verification_records"
                        }
                    )
            except Exception as error:
                row.update(
                    success=False,
                    status="FAILED",
                    terminal_reason=f"PILOT_RUNTIME_{type(error).__name__}",
                )
            finally:
                raw.append(asdict(backend.current_physics_observation()))
                write_json(directory / "physical-observations.json", raw)
                write_json(directory / "actuator-steps.json", controls)
                write_json(directory / "commands.json", backend.command_records)
                write_json(directory / "fault-events.json", backend.fault_records)
                write_json(
                    directory / "context.json",
                    {
                        "schema_version": "rgbd.raw-episode.v2",
                        "assignment_hash": content_digest(assignment["base_assignment"]),
                        "pilot_assignment_hash": content_digest(assignment),
                        "group_id": scene.group_id,
                        "scene_hash": scene.scene_hash,
                        "episode_id": raw[0]["episode_id"],
                        "reset_step": 0,
                        "reset_sim_time_s": 0.0,
                        "terminal_step": raw[-1]["physics_step"],
                        "terminal_sim_time_s": raw[-1]["sim_time_s"],
                        "physics_dt_s": config.physics_dt_s,
                        "reset_observation_hash": content_digest(raw[0]),
                        "terminal_observation_hash": content_digest(raw[-1]),
                        "evaluation_start_step": 120,
                        "initial_controller_targets": initial,
                        "actuator_delay_steps": backend._actuator_delay_steps,
                        "role_bundle_hash": self.binding.bundle.digest(),
                    },
                )
        row.update(
            wall_duration_s=time.monotonic() - started,
            costs=ledger.snapshot().model_dump(),
            cloud_requests=ledger.snapshot().cloud_model_requests,
        )
        write_json(directory / "costs.json", ledger.export())
        write_json(directory / "wire-index.json", wire)
        return row


def run_ced_pilot(
    config_path: Path,
    output: Path,
    stage: str,
    *,
    service: Any = None,
    profile_id: str | None = None,
    execute: bool = False,
    allow_paid: bool = False,
    initial: Path | None = None,
    methods: Path | None = None,
) -> dict[str, Any]:
    """Explicit v2 stages; dry/unavailable prerequisites retain every unexecuted group."""
    from cloud_edge_robot_arm.research.freeze_evidence import (
        audit_ced_pilot_stage,
        verify_role_probe_evidence,
    )
    from cloud_edge_robot_arm.research.protocol import load_protocol
    from cloud_edge_robot_arm.vision.role_models import (
        RoleModelBundle,
        RoleProviderSnapshot,
        resolve_cloud_role,
    )
    from cloud_edge_robot_arm.vision.runtime_binding import RoleRuntimeBinding
    from scripts.probe_rgbd_roles import read_role_config

    settings = yaml.safe_load(config_path.read_text())
    fields = {
        "schema_version",
        "protocol_version",
        "episodes",
        "seed",
        "pools_path",
        "timeout_s",
        "role_config",
        "role_probe",
        "selection_evidence",
        "protocol_evidence",
        "exclude_datasets",
        "exclude_pilots",
    }
    if (
        not isinstance(settings, dict)
        or set(settings) != fields
        or (
            settings["schema_version"] != "ced.pilot-config.v1"
            or settings["protocol_version"] != "ced.research.v2"
            or settings["episodes"] != 120
            or type(settings["seed"]) is not int
            or type(settings["timeout_s"]) not in {int, float}
            or not 0 < settings["timeout_s"] <= 600
            or not isinstance(settings["exclude_datasets"], list)
            or not isinstance(settings["exclude_pilots"], list)
        )
    ):
        raise ValueError("v2 pilot config cannot override stages/periods/roles/fixed design")
    pools = _ced_pools(settings)
    reasons = []
    period = None
    executor = None
    bundle_hash = None
    if stage == "power":
        try:
            if initial is None or methods is None:
                raise ValueError("power requires actual INITIAL and accepted frozen methods")
            frozen = load_protocol(initial)
            if frozen.stage != "INITIAL" or frozen.spec.schema_version != "ced.research.v2":
                raise ValueError("power requires the current v2 INITIAL")
            json.loads(methods.read_text())
            reasons.append("method runtime and actual power source acceptance are not integrated")
        except (OSError, ValueError, TypeError, KeyError):
            reasons.append("power prerequisites unavailable; no full-method pilot was run")
    elif execute:
        try:
            if service is None or not profile_id or not allow_paid or not settings["role_probe"]:
                raise ValueError(
                    "actual v2 execution requires selected service, probe and payment authorization"
                )
            if not service.secret_store.has_secret(profile_id):
                raise ValueError("selected cloud secret unavailable")
            verified = verify_role_probe_evidence(Path(settings["role_probe"]))
            if not verified["available"]:
                raise ValueError("original nominal cloud role probe unavailable")
            probe = verified["report"]
            role_config = read_role_config(Path(settings["role_config"]))
            planner, cloud = resolve_cloud_role(
                service,
                profile_id,
                source_hashes=probe["bundle"]["cloud_snapshot"]["source_hashes"],
                allow_paid=allow_paid,
                image_size=tuple(role_config["cloud"]["image_size"]),
                coordinate_system=role_config["cloud"]["coordinate_system"],
                grasp_profile=role_config["cloud"]["grasp_profile"],
                available_model_ids=role_config["cloud"]["available_model_ids"],
            )
            if cloud.evidence() != probe["bundle"]["cloud_snapshot"]:
                raise ValueError("resolved cloud settings differ from frozen probe")
            bundle = RoleModelBundle(
                cloud,
                probe["bundle"]["edge_provider_id"],
                probe["bundle"]["edge_provider_hash"],
                probe["bundle"]["device_pipeline_hash"],
            )
            edge = RoleProviderSnapshot(**probe["edge_snapshot"])
            binding = RoleRuntimeBinding(
                bundle, edge, probe["device_source_hashes"], probe["edge_policy"]
            )
            binding.validate(planner)
            bundle_hash = bundle.digest()
            if stage == "foundation":
                if not settings["selection_evidence"]:
                    raise ValueError("foundation selection source unavailable")
                selection = audit_ced_pilot_stage(Path(settings["selection_evidence"]), "selection")
                if (
                    not selection["available"]
                    or selection["pools"] != pools
                    or selection["role_bundle_hash"] != bundle_hash
                ):
                    raise ValueError(
                        "foundation source selection does not bind the same frozen pool/roles"
                    )
                period = selection["selected_period_s"]
            executor = _RoleBoundPilotExecutor(settings, planner, binding, output)
        except Exception as error:
            # Never persist an endpoint, key or arbitrary remote error body.
            reasons.append(f"actual stage prerequisites unavailable: {type(error).__name__}")
    else:
        reasons.append("execution not requested; no model/renderer contacted")
    summary = run_pilot_stage(
        stage, pools, output, period_s=period, role_bundle_hash=bundle_hash, _real_executor=executor
    )
    if executor is not None:
        results = json.loads((output / "results.json").read_text())
        report = PilotReport(assigned=len(results), records=results)
        unsettled = publish_final_costs(report, executor.ledgers)
        for row in report.records:
            row["cloud_requests"] = row["costs"]["cloud_model_requests"]
            write_json(output / "cases" / row["assignment_id"] / "case-result.json", row)
        write_json(output / "results.json", report.records)
        summary["unsettled_requests"] = unsettled
        summary["declared_success"] = sum(r["success"] for r in report.records)
        reasons.append(
            "raw records require independent stage audit; no automatic INITIAL/FINAL freeze"
        )
    summary["reasons"] = reasons
    write_json(output / "summary.json", summary)
    (output / "config.yaml").write_bytes(config_path.read_bytes())
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["selection", "foundation", "power"], required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--profile-id")
    parser.add_argument("--model-control-db", type=Path, default=Path("data/model_control.db"))
    parser.add_argument("--secret-env", default="BIGSMALL_VLM_API_KEY")
    parser.add_argument("--initial", type=Path)
    parser.add_argument("--methods", type=Path)
    args = parser.parse_args(argv)
    settings = yaml.safe_load(args.config.read_text())
    if isinstance(settings, dict) and settings.get("protocol_version") == "ced.research.v2":
        service = None
        if args.execute and args.model_control_db.is_file() and args.profile_id:
            from cloud_edge_robot_arm.model_control.service import ModelControlService
            from cloud_edge_robot_arm.model_control.sqlite_repository import (
                SQLiteModelProfileRepository,
            )
            from scripts.probe_rgbd_roles import _EnvironmentProfileSecrets

            service = ModelControlService(
                repository=SQLiteModelProfileRepository(args.model_control_db),
                secret_store=_EnvironmentProfileSecrets(args.profile_id, args.secret_env),
            )
        try:
            summary = run_ced_pilot(
                args.config,
                args.output,
                args.stage,
                service=service,
                profile_id=args.profile_id,
                execute=args.execute,
                allow_paid=args.allow_paid,
                initial=args.initial,
                methods=args.methods,
            )
        except (ValueError, OSError, TypeError, KeyError) as error:
            parser.exit(3, f"v2 pilot not started: {type(error).__name__}\n")
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 3
    if args.stage != "foundation":
        parser.exit(3, "power pilot BLOCKED: T13/T15a/T16a are not accepted\n")
    os.environ.setdefault("MUJOCO_GL", "egl")
    try:
        summary = run_foundation(args.config, args.output)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"pilot not started: {exc}\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return (
        0
        if summary["freeze_ready"] and summary["protocol_snapshot_complete"]
        else (3 if summary["blocked"] == summary["assigned"] else 4)
    )


if __name__ == "__main__":
    raise SystemExit(main())
