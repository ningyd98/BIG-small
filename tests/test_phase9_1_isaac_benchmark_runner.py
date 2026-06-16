from __future__ import annotations

import sys
from pathlib import Path

from cloud_edge_robot_arm.simulation.evaluation.metrics import run_isaac_physical_trial


def test_run_isaac_physical_trial_uses_process_telemetry(tmp_path: Path) -> None:
    worker = _write_trial_worker(tmp_path)

    result = run_isaac_physical_trial(
        "S19_CAMERA_NOISE_AND_OCCLUSION",
        seed=3,
        randomization_level="MILD",
        process_argv=[sys.executable, str(worker)],
    )

    assert result.scenario_id == "S19_CAMERA_NOISE_AND_OCCLUSION"
    assert result.metrics["physics_steps"] == 5
    assert result.metrics["trajectory_duration_ms"] == 100.0
    assert result.metrics["joint_tracking_rmse"] == 0.02
    assert result.metrics["expected_contact_count"] == 1
    assert result.metrics["sensor_latency_ms"] == 22.0
    assert result.metrics["simulated"] is True
    assert result.metrics["backend"] == "isaac"


def test_phase9_benchmark_runner_uses_isaac_trial_for_isaac_backend() -> None:
    source = Path("scripts/run_phase9_benchmarks.py").read_text(encoding="utf-8")

    assert "run_isaac_physical_trial" in source
    assert 'args.backend == "isaac"' in source
    assert "run_mujoco_physical_trial" in source
    assert "trial_function = (" in source
    assert 'run_isaac_physical_trial if args.backend == "isaac"' in source


def _write_trial_worker(tmp_path: Path) -> Path:
    worker = tmp_path / "isaac_trial_worker.py"
    worker.write_text(
        """
from __future__ import annotations

import json
import sys

sim_time_s = 0.0
physics_steps = 0

def base(message_type: str) -> dict[str, object]:
    return {
        "message_type": message_type,
        "protocol_version": "bigsmall-isaac-jsonl-v1",
        "backend": "isaac_sim",
        "runtime": "isaac_standalone",
        "status": "READY_TO_CONNECT",
        "sim_time_s": sim_time_s,
        "ros_time_s": sim_time_s,
        "sensor_timestamp_s": sim_time_s,
    }

for line in sys.stdin:
    message = json.loads(line)
    if message["message_type"] == "handshake":
        response = base("handshake_ack")
        response.update({
            "message": "trial-worker",
            "capabilities": [
                "joint_state",
                "tcp_pose",
                "rgb_camera",
                "depth_camera",
                "contacts",
                "follow_joint_trajectory",
            ],
        })
        print(json.dumps(response), flush=True)
        continue
    command = message["command"]
    command_type = command["command_type"]
    if command_type == "step":
        physics_steps += int(command["payload"]["steps"])
        sim_time_s = round(physics_steps * 0.02, 6)
    response = base("command_ack")
    response.update({
        "ack": True,
        "command_seq": command["command_seq"],
        "command_type": command_type,
        "physics_steps": physics_steps,
        "joint_state": {
            "names": [f"panda_joint{i}" for i in range(1, 8)],
            "positions": [0.08, -0.17, 0.19, -0.1, 0.06, 0.13, 0.01],
            "velocities": [0.01] * 7,
            "efforts": [0.0] * 7,
        },
        "tcp_pose": {"x": 0.41, "y": 0.0, "z": 0.305},
        "contacts": [
            {
                "geom1": "finger_left",
                "geom2": "cube",
                "impulse": 0.3,
                "position": {"x": 0.41, "y": 0.0, "z": 0.04},
                "expected": True,
                "illegal": False,
            }
        ],
        "sensor_frame": {
            "frame_id": "isaac_camera",
            "width": 640,
            "height": 480,
            "latency_ms": 22.0,
            "object_detections": [{"object_id": "cube", "confidence": 0.88}],
        },
    })
    print(json.dumps(response), flush=True)
""".lstrip(),
        encoding="utf-8",
    )
    return worker
