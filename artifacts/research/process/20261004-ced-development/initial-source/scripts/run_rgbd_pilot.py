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
import time
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
from cloud_edge_robot_arm.research.pilot import PilotReport, derive_tcap
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
            rgb[:, start:start+width] = 0
            depth[:, start:start+width] = 0
        encoded = io.BytesIO()
        Image.fromarray(rgb).save(encoded, format="PNG")
        data = observation.model_dump()
        data.update(rgb_png_base64=base64.b64encode(encoded.getvalue()).decode(),
                    depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
                    valid_mask_base64=None, checksum_sha256="")
        return RGBDObservation.model_validate(data)


def publish_final_costs(report: PilotReport, ledgers: list[tuple[CostLedger, Path]],
                        *, settle_timeout_s: float = 5.) -> int:
    """Take one settled snapshot per case and publish it consistently everywhere."""
    deadline = time.monotonic() + settle_timeout_s
    while any(r.status == "IN_FLIGHT" for ledger, _ in ledgers for r in ledger.requests()):
        if time.monotonic() >= deadline:
            break
        time.sleep(.025)
    rows = {row["assignment_id"]: row for row in report.records}
    inflight = 0
    for ledger, directory in ledgers:
        publication = ledger.export()
        pending = sum(r["status"] == "IN_FLIGHT" for r in publication["requests"])
        inflight += pending
        snapshot = publication["summary"]
        row = rows[directory.name]
        row.update(costs=snapshot, model_calls=snapshot["model_requests"],
                   cost_settlement="UNSETTLED" if pending else "SETTLED",
                   inflight_requests=pending)
        write_json(directory / "costs.json", {
            **publication, "settlement": row["cost_settlement"],
        })
        write_json(directory / "case-result.json", row)
    return inflight


def run_foundation(config_path: Path, output: Path) -> dict[str, Any]:
    settings = yaml.safe_load(config_path.read_text())
    if settings["episodes"] != 120 or settings["b0_period_s"] not in (.5, 1, 2, 5):
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
    sources = [*sorted(Path("src/cloud_edge_robot_arm").rglob("*.py")),
        *sorted(Path("scripts").rglob("*.py")),
        *sorted(Path("configs/research").glob("*.yaml")),
        Path("assets/robots/franka_panda/scene.xml"), Path("pyproject.toml")]
    write_json(output / "source-hashes.json", {str(p): file_hash(p) for p in sources})
    for source in sources:
        archived = output / "source" / source
        archived.parent.mkdir(parents=True, exist_ok=True)
        archived.write_bytes(source.read_bytes())
    write_json(output / "pool-audit.json", {
        "pool_hashes": {k: content_digest(v) for k, v in pools.items()},
        "excluded_group_count": len(excluded),
        "excluded_group_ids_hash": content_digest(sorted(excluded)),
        "model_snapshot_hash": None,
        "seed": settings["seed"], "all_groups_disjoint": True,
        "opportunity_snapshots": "NOT_EXECUTED",
        "recovery_fault_manifest": "NOT_EXECUTED",
    })
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
        row: dict[str, Any] = {"assignment_id": assignment["assignment_id"],
                              "stratum_id": assignment["stratum_id"],
                              "scene_hash": assignment["scene_hash"],
                              "success": False, "blocked": False}
        try:
            if planner is None:
                raise RuntimeError(blocked_reason)
            active = copy.copy(planner)
            active.cost_ledger = ledger
            rtt = int(assignment["stratum_id"].split("RTT")[1])
            loss = dict(NETWORKS)[rtt]
            scene = SceneSpec.model_validate(assignment["scene"])
            schedule = NetworkSchedule(schedule_id=assignment["assignment_id"], rtt_ms=rtt,
                                       loss_rate=loss, seed=scene.seed)
            active.network_injector = NetworkInjector(schedule)
            config = SimulatorConfig(render_rgb=True, render_depth=True,
                                     domain_randomization=False, seed=scene.seed)
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
                    capture._backend.inject_fault(PhysicalFault(
                        fault_type=PhysicalFaultType.TARGET_MOTION,
                        parameters={"speed_m_s": perturbation["movement_speed_m_s"],
                                    "duration_s": 5., "direction_y": 1.},
                    ))
                write_json(directory / "perturbation.json", {
                    "assignment": perturbation, "task": task,
                    "sensor_applied_from_frame": 1,
                    "movement_duration_sim_s": 5. if task == "DYNAMIC" else 0.,
                    "network": schedule.model_dump(mode="json"),
                })
                color = scene.scene_parameters["target"]["color_name"]
                assert active.model_snapshot is not None
                policy = ExecutionPolicy(
                    instruction=f"Move the {color} block to the green region.",
                    model_snapshot_hash=active.model_snapshot.digest(), output_dir=directory,
                    timeout_s=float(settings["timeout_s"]),
                    supervision_period_s=float(settings["b0_period_s"]),
                    advance_physics_during_wait=True,
                    verification_budget=VerificationBudget(**settings["verification_budget"]),
                )
                outcome = run_visual_episode(active, MuJoCoSkillRobot(capture._backend),
                                             capture, policy)
                row.update({k: v for k, v in asdict(outcome).items()
                            if k != "verification_records"})
                row["blocked"] = bool(outcome.terminal_reason and
                                      outcome.terminal_reason.startswith("BLOCKED_BY_ENV"))
                row["network_cost"] = active.network_injector.snapshot().model_dump(mode="json")
                write_json(directory / "fault-events.json", capture._backend.fault_records)
        except Exception as exc:
            # Never erase already recorded stages if a runner exception follows motion.
            row.update(blocked=planner is None, status="BLOCKED" if planner is None else "FAILED",
                       terminal_reason=f"{type(exc).__name__}: {exc}",
                       model_calls=ledger.snapshot().model_requests,
                       stage_accounting="SEE_RAW_CASE_ARTIFACTS")
        row["wall_duration_s"] = time.monotonic() - started
        write_json(directory / "costs.json", {
            "summary": ledger.snapshot().model_dump(),
            "requests": [r.model_dump(mode="json") for r in ledger.requests()],
        })
        row["artifact_bytes"] = sum(p.stat().st_size for p in directory.rglob("*") if p.is_file())
        row["costs"] = ledger.snapshot().model_dump()
        write_json(directory / "case-result.json", row)
        report.records.append(row)
        write_json(output / "progress.json", report.summary())
        print(f'{row["assignment_id"]} {row["stratum_id"]}: '
              f'{row.get("status", "BLOCKED")} {row.get("terminal_reason", "")}', flush=True)
    # A late actual response updates its own ledger, never online state or success.
    inflight = publish_final_costs(report, ledgers)
    summary = {**report.summary(), "method_id": "B0", "b0_period_s": settings["b0_period_s"],
               "formal_g1": False, "inflight_requests": inflight,
               "protocol_snapshot_complete": False,
               "status": "COMPLETE" if len(report.records) == 120 else "INCOMPLETE",
               "research_acceptance": "NOT_ACCEPTED_PENDING_PROTOCOL_EVIDENCE"}
    durations = [r["wall_duration_s"] for r in report.records if r.get("success")]
    summary["tcap_s"] = derive_tcap(durations) if durations else None
    nominal = [r for r in report.records if r["stratum_id"].startswith("STATIC")]
    summary["nominal_success_rate"] = sum(r.get("success", False) for r in nominal) / len(nominal)
    summary["safety_violation_rate"] = sum(r.get("safety_violation", False)
                                           for r in report.records) / 120
    summary["baseline_feasibility"] = (
        "FEASIBLE" if summary["nominal_success_rate"] >= .9
        and summary["success_rate_all_assigned"] >= .8
        and summary["safety_violation_rate"] <= .01 else "NO_FEASIBLE_BASELINE"
    )
    summary["model_snapshot_hash"] = planner.model_snapshot.digest() if (
        planner and planner.model_snapshot) else None
    write_json(output / "budget.json", estimate_budget(report, ProtocolSpec().formal_ns))
    write_json(output / "results.json", report.records)
    write_json(output / "summary.json", summary)
    write_json(output / "progress.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["foundation", "power"], required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.stage != "foundation":
        parser.exit(3, "power pilot BLOCKED: T13/T15a/T16a are not accepted\n")
    os.environ.setdefault("MUJOCO_GL", "egl")
    try:
        summary = run_foundation(args.config, args.output)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"pilot not started: {exc}\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["freeze_ready"] and summary["protocol_snapshot_complete"] else (
        3 if summary["blocked"] == summary["assigned"] else 4
    )


if __name__ == "__main__":
    raise SystemExit(main())
