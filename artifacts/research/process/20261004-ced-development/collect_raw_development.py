"""One actual development-only recovery source; never a formal G4 success."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec
from cloud_edge_robot_arm.datasets.rgbd.teacher import EpisodeRecorder, run_teacher_episode
from cloud_edge_robot_arm.research.protocol import build_scene_pools
from cloud_edge_robot_arm.research.protocol_evidence import write_recovery_source
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalFault, PhysicalFaultType
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession


def main() -> None:
    base = Path(__file__).resolve().parent / "t8-real-raw-development"
    base.mkdir(exist_ok=False)
    row = build_scene_pools(2026100431, set(), protocol_version="ced.research.v2")["recovery"][0]
    (base / "assignment.json").write_text(json.dumps(row, indent=2) + "\n")
    scene = SceneSpec.model_validate(row["scene"])
    raw, controls, actions = [], [], []

    def record(snapshot):
        if raw and raw[-1].physics_step == snapshot.physics_step:
            if raw[-1] != snapshot:
                raise ValueError("duplicate physical step changed")
            return
        raw.append(snapshot)

    config = SimulatorConfig(domain_randomization=False, render_rgb=False, render_depth=False)
    with MuJoCoCaptureSession(config) as capture:
        capture.apply_scene(scene)
        backend = capture._backend
        record(backend.current_physics_observation())
        with backend.observe_actuator_steps(controls.append):
            backend.inject_fault(PhysicalFault(PhysicalFaultType.TARGET_MOTION, {
                "speed_m_s": .02, "direction": 1., "duration_s": 1.,
            }))
            with backend.observe_physics_steps(record):
                backend.step(steps=241)
            recovery_start = backend.total_physics_steps
            recorder = EpisodeRecorder()
            outcome = run_teacher_episode(
                scene, MuJoCoSkillRobot(backend), recorder, settle_steps=0,
                physical_observer=record, action_observer=actions.append,
            )
        header = write_recovery_source(
            row=row, observations=raw, action_events=actions,
            backend_commands=backend.command_records, actuator_steps=controls,
            fault_events=backend.fault_records, recovery_start_step=recovery_start,
            output=base / "attempt-1",
        )
        summary = {"kind": "PHYSICS", "scope": "DEVELOPMENT_ONLY", "model_requests": 0,
                   "online_recovery_g4": False, "raw_physics_steps": len(raw),
                   "actuator_steps": len(controls), "teacher_action_count": len(actions),
                   "header": header, "independent_outcome": asdict(outcome)}
        (base / "assessment.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps({key: value for key, value in summary.items()
                          if key not in {"header", "independent_outcome"}}, ensure_ascii=False))
        print(json.dumps({"physical_success": outcome.success, "status": outcome.status,
                          "safety": outcome.safety_assessment, "reason": outcome.failure_reason}))


if __name__ == "__main__":
    main()
