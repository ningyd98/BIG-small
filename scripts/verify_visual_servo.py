"""Local MuJoCo PBVS development checks, without model calls or hardware."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def case_passed(result: dict[str, Any]) -> bool:
    if result.get("case") == "loss":
        injected = result.get("loss_injected_at_step")
        last_safe = result.get("last_safe_sample_step")
        return bool(
            result.get("motion_status") == "STOPPED" and result.get("held_on_exit")
            and result.get("terminal_reason") ==
                "ValueError:servo registered marker geometry unavailable"
            and type(injected) is int and type(last_safe) is int
            and 0 < injected - last_safe <= 8
            and result.get("stop_physics_step") == injected
            and result.get("joint_commands_after_loss") == 0
            and result.get("feedback_count", 0) >= 3
        )
    if result.get("case") == "target_motion" and (
        result.get("independent_object_displacement_m", 0) < 0.005
    ):
        return False
    if result.get("case") == "camera_move" and result.get("camera_translation_m", 0) < 0.01:
        return False
    return bool(
        result.get("motion_status") == "SUCCEEDED"
        and result.get("final_position_error_m", math.inf) <= 0.005
        and result.get("independent_horizontal_error_m", math.inf) <= 0.005
        and result.get("held_on_exit") and result.get("feedback_count", 0) >= 3
    )


def run_case(case: str, output: Path) -> dict[str, Any]:
    """RGB-only colour nomination is an explicit fixture, not a model result."""
    import cv2
    import numpy as np
    from PIL import Image

    from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest
    from cloud_edge_robot_arm.contracts import Pose
    from cloud_edge_robot_arm.research.sol_molmo_components import check_component_hard_state
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import (
        PhysicalFault,
        PhysicalFaultType,
        PhysicalScenarioConfig,
    )
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
    from cloud_edge_robot_arm.simulation.mujoco.motion_controller import MotionTarget
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
    from cloud_edge_robot_arm.simulation.mujoco.visual_servo import (
        MuJoCoVisualServoController,
        VisualServoSession,
    )
    from cloud_edge_robot_arm.vision.marker_families import (
        COMPONENT_DIAGNOSTIC_FAMILY,
        marker_family,
    )
    from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame
    from cloud_edge_robot_arm.vision.planner import ground_observation
    from cloud_edge_robot_arm.vision.servo import OpenCVServoFeedback, save_servo_frame
    from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker

    if case not in {"fixed", "camera_move", "target_motion", "loss"}:
        raise ValueError("unknown development case")
    output.mkdir(parents=True, exist_ok=False)
    os.environ.setdefault("MUJOCO_GL", "egl")
    backend = MuJoCoPhysicsBackend()
    family = marker_family(COMPONENT_DIAGNOSTIC_FAMILY)
    rows: list[dict[str, Any]] = []
    physical: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "case": case, "scope": "MUJOCO_VISUAL_SERVO_DEVELOPMENT",
        "model_calls": 0, "semantic_nomination": "RGB_COLOUR_TEST_FIXTURE",
        "hardware_dispatch": False, "formal_research": "NOT_ACCEPTED",
        "motion_status": "NOT_STARTED", "terminal_reason": None,
        "feedback_count": 0, "simulation_visual_hz": None,
        "final_position_error_m": None,
    }
    session = None
    started = time.monotonic()

    def capture() -> Any:
        observation = observation_from_sensor_frame(
            backend.capture_sensor_frame(), source="mujoco_camera"
        )
        index = len(rows)
        frame_dir = output / "frames" / f"{index:04d}"
        save_servo_frame(observation, frame_dir)
        rows.append(observation.evidence() | {"files": str(frame_dir.relative_to(output))})
        return observation

    try:
        backend.initialize(SimulatorConfig(
            model_path=str(ROOT / family.asset_path), seed=31, physics_dt_s=1 / 240,
            domain_randomization=False, render_rgb=True, render_depth=True,
        ))
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=31))
        backend.step(120)
        robot = MuJoCoSkillRobot(backend)
        observation = capture()
        with Image.open(io.BytesIO(base64.b64decode(observation.rgb_png_base64))) as image:
            rgb = np.asarray(image, dtype=float)
        red, green, blue = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]

        def pixel(mask: Any) -> tuple[int, int]:
            count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype("uint8"))
            components = [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= 8]
            if len(components) != 1:
                raise ValueError("RGB test fixture does not identify one component")
            distance = cv2.distanceTransform((labels == components[0]).astype("uint8"),
                                            cv2.DIST_L2, 5)
            y, x = np.unravel_index(distance.argmax(), distance.shape)
            return int(x), int(y)

        evidence = ground_observation(
            InitialPlanningRequest(
                request_id="servo-development", observation=observation,
                user_instruction="Move the red block to the green region.",
            ),
            observation,
            target_pixel=pixel((red > 1.5 * green) & (red > 1.5 * blue) & (red > 80)),
            destination_pixel=pixel((green > 1.3 * red) & (green > 1.3 * blue) & (green > 50)),
            target_label="red block", grasp_profile="mujoco_upright_box_v2",
            evidence={"nomination": "RGB_COLOUR_TEST_FIXTURE_NO_MODEL"},
        ).evidence
        tracker = OpenCVTargetTracker(observation, evidence)
        grasp = evidence["resolved_top_grasp_tcp"]
        assert tracker.initial is not None
        endpoint = Pose(
            x=float(tracker.initial["center"][0]), y=float(tracker.initial["center"][1]),
            z=max(0.16, grasp["z"] + 0.1),
        )
        servo_reference = capture()
        provider = OpenCVServoFeedback(
            servo_reference, tracker, evidence, skill="MOVE_ABOVE", initial_target=endpoint,
            marker_family_id=family.family_id,
        )
        start_sim = backend.get_sim_time()
        # The experiment driver schedules disturbances; online estimation receives
        # only paired RGBD and robot state, never disturbance/ground-truth labels.
        if case == "target_motion":
            backend.inject_fault(PhysicalFault(PhysicalFaultType.TARGET_MOTION, {
                "speed_m_s": 0.012, "direction_y": 1.0, "duration_s": 1.0,
            }))

        def sample(previous: MotionTarget) -> MotionTarget:
            elapsed = backend.get_sim_time() - start_sim
            if case == "camera_move":
                fraction = min(1.0, elapsed / 0.8)
                backend.set_camera_position((0.35 + 0.02 * fraction, 0, 1.4 - 0.05 * fraction))
            elif case == "loss" and elapsed >= 0.2:
                result["loss_injected_at_step"] = backend.total_physics_steps
                backend.set_camera_position((0.8, -0.5, 0.6))
            fresh = capture()
            position = provider.update(fresh)
            check_component_hard_state(backend, robot)
            result["last_safe_sample_step"] = backend.total_physics_steps
            return MotionTarget(position, previous.orientation_wxyz)

        def observe(snapshot: Any) -> None:
            check_component_hard_state(backend, robot)
            physical.append({
                "physics_step": snapshot.physics_step, "sim_time_s": snapshot.sim_time_s,
                "tcp_position_m": snapshot.tcp_position_m,
                "object_position_m": snapshot.object_position_m,
                "scope": "INDEPENDENT_OFFLINE_EVIDENCE_NOT_ONLINE_INPUT",
            })

        session = VisualServoSession(sample)
        with backend.observe_physics_steps(observe):
            motion = MuJoCoVisualServoController(backend).move_tcp(
                MotionTarget(endpoint, (math.sqrt(0.5), 0, math.sqrt(0.5), 0)),
                timeout_s=10, session=session,
                max_joint_velocity_rad_s=0.5, max_joint_acceleration_rad_s2=0.5 / 0.3,
            )
        result["motion_status"] = motion.status
        result["final_position_error_m"] = motion.position_error_m
        result["visual_measurements"] = provider.records
        # Independent terminal geometry is consumed only after control has ended.
        truth = backend.current_physics_observation()
        tcp = backend.get_tcp_pose()
        result["independent_horizontal_error_m"] = math.hypot(
            tcp.x - truth.object_position_m[0], tcp.y - truth.object_position_m[1]
        )
    except Exception as error:
        result["motion_status"] = "STOPPED"
        result["terminal_reason"] = f"{type(error).__name__}:{error}"
    finally:
        result["wall_elapsed_s"] = time.monotonic() - started
        result["feedback_count"] = len(session.records) if session else 0
        if session and len(session.records) >= 2:
            records = session.records
            span = records[-1]["sim_time_s"] - records[0]["sim_time_s"]
            result["simulation_visual_hz"] = round((len(records) - 1) / span, 6)
            wall_span = records[-1]["wall_elapsed_s"] - records[0]["wall_elapsed_s"]
            result["wall_feedback_hz"] = (len(records) - 1) / wall_span
            result["max_sample_and_ik_ms"] = max(r["sample_and_ik_s"] for r in records) * 1000
        result["held_on_exit"] = bool(backend.command_records) and (
            backend.command_records[-1]["type"] == "hold_current_joints"
        )
        result["stop_physics_step"] = backend.total_physics_steps
        if physical:
            result["independent_object_displacement_m"] = math.dist(
                physical[0]["object_position_m"], physical[-1]["object_position_m"]
            )
        if len(rows) >= 2:
            result["camera_translation_m"] = math.dist(
                [rows[0]["camera_to_world"][index] for index in (3, 7, 11)],
                [rows[-1]["camera_to_world"][index] for index in (3, 7, 11)],
            )
        if result.get("loss_injected_at_step") is not None:
            result["joint_commands_after_loss"] = sum(
                command["type"] == "joint_target"
                and command["physics_step"] >= result["loss_injected_at_step"]
                for command in backend.command_records
            )
        _write(output / "control-samples.json", session.records if session else [])
        _write(output / "physical-evidence.json", physical)
        _write(output / "frames.json", rows)
        _write(output / "commands.json", backend.command_records)
        _write(output / "result.json", result)
        backend.shutdown()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--cases", nargs="+", choices=("fixed", "camera_move", "target_motion", "loss"),
        default=["fixed", "camera_move", "target_motion", "loss"],
    )
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    source_files = (
        Path(__file__).relative_to(ROOT).as_posix(),
        "src/cloud_edge_robot_arm/vision/servo.py",
        "src/cloud_edge_robot_arm/vision/tracking.py",
        "src/cloud_edge_robot_arm/vision/pose_markers.py",
        "src/cloud_edge_robot_arm/vision/observations.py",
        "src/cloud_edge_robot_arm/vision/marker_families.py",
        "src/cloud_edge_robot_arm/vision/top_grasp.py",
        "src/cloud_edge_robot_arm/vision/planner.py",
        "src/cloud_edge_robot_arm/research/sol_molmo_components.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/visual_servo.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/backend.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/motion_controller.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/camera.py",
        "src/cloud_edge_robot_arm/simulation/mujoco/skill_robot.py",
        "src/cloud_edge_robot_arm/simulation/config.py",
        "assets/robots/franka_panda/scene_pose_marker_side_y_plus_75mm_component_v1.xml",
    )
    import cv2
    import mujoco
    import numpy as np

    _write(args.output / "protocol.json", {
        "cases": args.cases, "model_calls": 0, "hardware_dispatch": False,
        "seed": 31, "physics_dt_s": 1 / 240, "vision_period_s": 1 / 30,
        "runtime": {"python": sys.version, "opencv": cv2.__version__,
                    "mujoco": mujoco.__version__, "numpy": np.__version__},
        "scope": "DEVELOPMENT_NOT_GENERALIZATION_OR_PHYSICAL_ACCEPTANCE",
        "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                          for p in source_files},
    })
    results = [run_case(case, args.output / case) for case in args.cases]
    passed = all(case_passed(result) for result in results)
    compact = [{k: v for k, v in r.items() if k != "visual_measurements"} for r in results]
    _write(args.output / "summary.json", {"passed": passed, "results": compact})
    print(json.dumps({"passed": passed, "results": compact}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
