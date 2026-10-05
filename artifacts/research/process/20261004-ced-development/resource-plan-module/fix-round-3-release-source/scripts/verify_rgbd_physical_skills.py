"""Record real MuJoCo T4 positive and failure-path trajectories."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import mujoco

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.motion_controller import (
    MotionTarget,
    MuJoCoMotionController,
)
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

ASSET = Path("assets/robots/franka_panda/scene.xml")
SOURCE_FILES = (
    Path("src/cloud_edge_robot_arm/simulation/mujoco/backend.py"),
    Path("src/cloud_edge_robot_arm/simulation/mujoco/motion_controller.py"),
    Path("src/cloud_edge_robot_arm/simulation/mujoco/skill_robot.py"),
    Path("scripts/verify_rgbd_physical_skills.py"),
)


def _backend() -> MuJoCoPhysicsBackend:
    backend = MuJoCoPhysicsBackend()
    backend.initialize(SimulatorConfig(model_path=str(ASSET)))
    backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=31))
    return backend


def _snapshot(backend: MuJoCoPhysicsBackend, stage: str) -> dict[str, Any]:
    model = backend._model
    data = backend._data
    assert model is not None and data is not None
    contacts = backend.get_contacts()
    object_xyz = [float(value) for value in data.xpos[model.body("object").id]]
    return {
        "stage": stage,
        "physics_steps_total": backend.total_physics_steps,
        "sim_time_s": backend.get_sim_time(),
        "tcp_xyz_m": backend.get_tcp_pose().model_dump(),
        "object_xyz_m": object_xyz,
        "left_contact_count": sum(
            {contact.geom1, contact.geom2} == {"left_finger_geom", "object_geom"}
            for contact in contacts
        ),
        "right_contact_count": sum(
            {contact.geom1, contact.geom2} == {"right_finger_geom", "object_geom"}
            for contact in contacts
        ),
        "table_object_contact_count": sum(
            {contact.geom1, contact.geom2} == {"table", "object_geom"}
            for contact in contacts
        ),
    }


def _positive() -> dict[str, Any]:
    backend = _backend()
    robot = MuJoCoSkillRobot(backend)
    trace: list[dict[str, Any]] = [_snapshot(backend, "reset")]
    try:
        def execute(stage: str, action: Any) -> None:
            result = action()
            row = _snapshot(backend, stage)
            row["action"] = {
                "success": result.success,
                "error_code": result.error_code,
                "duration_ms": result.duration_ms,
                "physics_steps": result.details.get("physics_steps"),
                "max_load_compensation_rad": result.details.get(
                    "max_load_compensation_rad"
                ),
            }
            trace.append(row)
            if not result.success:
                raise AssertionError(f"{stage}: {result.error_code}")

        # These are explicit, offline fixed-fixture TCP targets. No online
        # skill reads the object's true position or the target-region body.
        execute(
            "move_above",
            lambda: robot.move_above(
                "object", resolved_target=Pose(x=0.45, y=0.0, z=0.16), timeout_ms=8000
            ),
        )
        execute(
            "approach",
            lambda: robot.approach(
                "object", resolved_target=Pose(x=0.45, y=0.0, z=0.045), timeout_ms=8000
            ),
        )
        execute("grasp", lambda: robot.grasp("object", timeout_ms=1000))
        execute("lift_and_hold_0_5_s", lambda: robot.lift(height_m=0.10, timeout_ms=8000))
        # Settle the real grasp before lateral transport. The skill's own
        # 0.5 s bilateral-contact check remains unchanged; this is an
        # explicit additional dwell in the positive acceptance protocol.
        backend.step(steps=120)
        trace.append(_snapshot(backend, "post_lift_dwell_0_5_s"))
        execute(
            "move_to_region",
            lambda: robot.move_to_region(
                "target_region",
                resolved_target=Pose(x=0.20, y=0.25, z=0.16),
                timeout_ms=10000,
            ),
        )
        execute(
            "place",
            lambda: robot.place(
                "target_region",
                resolved_target=Pose(x=0.20, y=0.25, z=0.045),
                timeout_ms=8000,
            ),
        )
        execute("release", lambda: robot.release(timeout_ms=1000))
        backend.step(steps=240)
        trace.append(_snapshot(backend, "stable_1_s_after_release"))

        start_z = trace[0]["object_xyz_m"][2]
        hold = next(row for row in trace if row["stage"] == "lift_and_hold_0_5_s")
        end = trace[-1]
        end_xyz = end["object_xyz_m"]
        passed = (
            hold["object_xyz_m"][2] - start_z >= 0.05
            and hold["left_contact_count"] > 0
            and hold["right_contact_count"] > 0
            and 0.12 <= end_xyz[0] <= 0.28
            and 0.17 <= end_xyz[1] <= 0.33
            and abs(end_xyz[2] - 0.035) <= 0.005
            and end["left_contact_count"] == 0
            and end["right_contact_count"] == 0
        )
        return {
            "passed": passed,
            "trace": trace,
            "measured_lift_m": hold["object_xyz_m"][2] - start_z,
        }
    except AssertionError as exc:
        return {"passed": False, "trace": trace, "failure_reason": str(exc)}
    finally:
        backend.shutdown()


def _no_contact() -> dict[str, Any]:
    backend = _backend()
    try:
        robot = MuJoCoSkillRobot(backend)
        result = robot.grasp("object", timeout_ms=1000)
        return {
            "passed": not result.success and result.error_code == "NO_GRASP_CONTACT",
            "error_code": result.error_code,
            "physics_steps": result.details["physics_steps"],
            "snapshot": _snapshot(backend, "no_contact"),
        }
    finally:
        backend.shutdown()


def _unreachable() -> dict[str, Any]:
    backend = _backend()
    try:
        result = MuJoCoMotionController(backend).move_tcp(
            MotionTarget(
                position=Pose(x=2.0, y=0.0, z=2.0),
                orientation_wxyz=(1.0, 0.0, 0.0, 0.0),
            ),
            timeout_s=0.1,
        )
        return {
            "passed": result.status in {"UNREACHABLE", "TIMED_OUT"}
            and result.position_error_m > 0.5
            and result.physics_steps <= 24,
            "status": result.status,
            "position_error_m": result.position_error_m,
            "physics_steps": result.physics_steps,
            "snapshot": _snapshot(backend, "unreachable"),
        }
    finally:
        backend.shutdown()


def _stopped() -> dict[str, Any]:
    backend = _backend()
    try:
        robot = MuJoCoSkillRobot(backend)
        moved = robot.move_above(
            "object", resolved_target=Pose(x=0.45, y=0.0, z=0.16), timeout_ms=8000
        )
        stopped_pose = backend.get_tcp_pose()
        stop = robot.emergency_stop()
        before = backend.total_physics_steps
        rejected = robot.move_above(
            "object", resolved_target=Pose(x=0.45, y=0.0, z=0.20), timeout_ms=8000
        )
        blocked_motion_steps = backend.total_physics_steps - before
        backend.step(steps=120)
        data = backend._data
        assert data is not None
        after = backend.get_tcp_pose()
        drift_m = (
            (after.x - stopped_pose.x) ** 2
            + (after.y - stopped_pose.y) ** 2
            + (after.z - stopped_pose.z) ** 2
        ) ** 0.5
        return {
            "passed": moved.success
            and stop.success
            and not rejected.success
            and rejected.error_code == "EMERGENCY_STOP"
            and blocked_motion_steps == 0
            and drift_m <= 0.01,
            "error_code": rejected.error_code,
            "blocked_motion_steps": blocked_motion_steps,
            "post_stop_physics_steps": backend.total_physics_steps - before,
            "active_hold_ctrl": [float(value) for value in data.ctrl[:7]],
            "tcp_drift_after_stop_m": drift_m,
            "snapshot": _snapshot(backend, "stopped"),
        }
    finally:
        backend.shutdown()


def _timed_out_motion() -> dict[str, Any]:
    backend = _backend()
    try:
        controller = MuJoCoMotionController(backend)
        result = controller.move_tcp(
            MotionTarget(
                position=Pose(x=0.45, y=0.0, z=0.20),
                orientation_wxyz=(2**-0.5, 0.0, 2**-0.5, 0.0),
            ),
            timeout_s=0.5,
        )
        stopped_pose = backend.get_tcp_pose()
        backend.step(steps=120)
        after = backend.get_tcp_pose()
        drift_m = (
            (after.x - stopped_pose.x) ** 2
            + (after.y - stopped_pose.y) ** 2
            + (after.z - stopped_pose.z) ** 2
        ) ** 0.5
        return {
            "passed": result.status == "TIMED_OUT" and drift_m <= 0.01,
            "status": result.status,
            "motion_physics_steps": result.physics_steps,
            "post_timeout_physics_steps": 120,
            "tcp_drift_after_timeout_m": drift_m,
            "snapshot": _snapshot(backend, "timed_out_then_held"),
        }
    finally:
        backend.shutdown()


def _empty_hand_place() -> dict[str, Any]:
    backend = _backend()
    try:
        robot = MuJoCoSkillRobot(backend)
        before = backend.total_physics_steps
        result = robot.place(
            "target_region",
            resolved_target=Pose(x=0.20, y=0.25, z=0.045),
            timeout_ms=10000,
        )
        return {
            "passed": not result.success
            and result.error_code == "NO_GRASP_CONTACT"
            and backend.total_physics_steps == before,
            "error_code": result.error_code,
            "physics_steps": backend.total_physics_steps - before,
            "snapshot": _snapshot(backend, "empty_hand_place_rejected"),
        }
    finally:
        backend.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    cases = {
        "positive_pick_place": _positive(),
        "grasp_without_contact": _no_contact(),
        "unreachable_target": _unreachable(),
        "timed_out_motion_holds": _timed_out_motion(),
        "emergency_stop": _stopped(),
        "empty_hand_place": _empty_hand_place(),
    }
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "PASS" if all(case["passed"] for case in cases.values()) else "FAIL",
        "evidence_type": "REAL_MUJOCO_PHYSICS",
        "mujoco_version": mujoco.__version__,
        "model_path": str(ASSET),
        "asset_sha256": hashlib.sha256(ASSET.read_bytes()).hexdigest(),
        "source_sha256": {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in SOURCE_FILES
        },
        "scenario_id": "S01_NORMAL_STATIC",
        "seed": 31,
        "target_source": "OFFLINE_FIXED_FIXTURE",
        "cases": cases,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = arguments.output.with_suffix(arguments.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(arguments.output)
    print(json.dumps({"status": payload["status"], "output": str(arguments.output)}))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
