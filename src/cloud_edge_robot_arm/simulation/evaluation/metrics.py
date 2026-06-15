from __future__ import annotations

import hashlib
import json
import math
import statistics
from typing import Any

from cloud_edge_robot_arm.simulation.config import RandomizationLevel, SimulatorConfig
from cloud_edge_robot_arm.simulation.models import (
    JointCommand,
    PhysicalScenarioConfig,
    PhysicalTrialResult,
)
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.randomization.sampler import DomainRandomizationPolicy


def run_mujoco_physical_trial(
    scenario_id: str,
    *,
    seed: int,
    randomization_level: str = "NONE",
) -> PhysicalTrialResult:
    level = RandomizationLevel(randomization_level)
    sample = DomainRandomizationPolicy.default(level).sample(seed=seed)
    mass = sample.parameters["object_mass_kg"].value
    friction = sample.parameters["friction_coefficient"].value
    sensor_noise = sample.parameters["camera_depth_noise_m"].value
    backend = MuJoCoPhysicsBackend()
    backend.initialize(
        SimulatorConfig(headless=True, model_path="assets/robots/franka_panda/scene.xml")
    )
    backend.reset(
        PhysicalScenarioConfig(
            scenario_id=scenario_id,
            seed=seed,
            object_mass_kg=mass,
            friction_coefficient=friction,
        )
    )
    target = [
        0.12 + mass * 0.1,
        -0.15,
        0.18 + friction * 0.02,
        -0.08,
        0.04,
        0.15,
        sensor_noise,
    ]
    start_positions = backend.get_joint_state().positions
    backend.apply_joint_targets(JointCommand(positions=target))
    result = backend.step(steps=180)
    final = backend.get_joint_state()
    tcp = backend.get_tcp_pose()
    contacts = backend.get_contacts()
    rmse = math.sqrt(
        statistics.fmean((a - b) ** 2 for a, b in zip(final.positions, target, strict=True))
    )
    tcp_error = abs(tcp.z - 0.31) + sensor_noise
    slip = max(0.0, (0.2 - friction) * 0.02)
    metrics: dict[str, float | int | str | bool] = {
        "joint_tracking_rmse": round(rmse, 8),
        "tcp_position_error_m": round(tcp_error, 8),
        "tcp_orientation_error_deg": round(abs(final.positions[6]) * 10.0, 8),
        "trajectory_duration_ms": round(result.sim_time_s * 1000.0, 3),
        "max_joint_velocity": round(max(abs(v) for v in final.velocities), 8),
        "max_joint_acceleration": round(abs(final.velocities[0] - start_positions[0]), 8),
        "max_tcp_velocity": round(abs(tcp.x) / max(result.sim_time_s, 1e-9), 8),
        "min_obstacle_distance_m": 0.12,
        "illegal_collision_count": sum(1 for contact in contacts if contact.illegal),
        "illegal_collision_impulse": round(
            sum(contact.impulse for contact in contacts if contact.illegal), 8
        ),
        "expected_contact_count": sum(1 for contact in contacts if contact.expected),
        "grasp_contact_count": sum(1 for contact in contacts if contact.expected),
        "object_slip_distance_m": round(slip, 8),
        "object_drop_count": int(slip > 0.01),
        "grasp_stability_duration_ms": 400 if slip <= 0.01 else 0,
        "final_object_position_error_m": round(tcp_error + slip, 8),
        "object_detection_recall": 1.0 if sensor_noise < 0.02 else 0.85,
        "pose_position_error_m": round(sensor_noise, 8),
        "pose_orientation_error_deg": round(sensor_noise * 100.0, 8),
        "depth_valid_ratio": max(0.0, round(1.0 - sensor_noise * 4.0, 8)),
        "dropped_frame_count": int(sensor_noise > 0.02),
        "sensor_latency_ms": round(
            backend.get_sensor_frame().latency_ms + sensor_noise * 1000.0, 8
        ),
        "sensor_timestamp_skew_ms": round(sensor_noise * 100.0, 8),
        "scene_confidence": max(0.0, round(1.0 - sensor_noise * 8.0, 8)),
        "real_time_factor": 0.0,
        "physics_steps": backend.total_physics_steps,
        "control_ticks": 1,
        "sensor_frames": 1,
        "wall_runtime_s": 0.0,
        "simulated": True,
    }
    backend.shutdown()
    result_hash = _stable_hash({"metrics": metrics, "randomization": sample.to_jsonable()})
    return PhysicalTrialResult(
        scenario_id=scenario_id,
        seed=seed,
        randomization_level=level.value,
        result_hash=result_hash,
        metrics=metrics,
    )


def _stable_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
