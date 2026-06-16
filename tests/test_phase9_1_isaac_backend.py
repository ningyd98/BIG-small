from __future__ import annotations

import sys
from pathlib import Path

import pytest

from cloud_edge_robot_arm.simulation.backend import SimulatorBackend
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.isaac.backend import IsaacSimBackend
from cloud_edge_robot_arm.simulation.isaac.client import IsaacProtocolError
from cloud_edge_robot_arm.simulation.models import (
    GripperCommand,
    JointCommand,
    PhysicalFault,
    PhysicalFaultType,
    PhysicalScenarioConfig,
)


def test_isaac_backend_implements_simulator_backend_with_process_telemetry(
    tmp_path: Path,
) -> None:
    worker = _write_backend_worker(tmp_path)
    backend: SimulatorBackend = IsaacSimBackend(process_argv=[sys.executable, str(worker)])

    backend.initialize(SimulatorConfig(backend="isaac"))
    backend.reset(PhysicalScenarioConfig.scenario("S16_PAYLOAD_MASS_VARIATION", seed=4))
    backend.apply_joint_targets(JointCommand(positions=[0.1] * 7))
    backend.apply_gripper_command(GripperCommand(open=False, force_n=18.0))
    backend.inject_fault(PhysicalFault(PhysicalFaultType.CAMERA_NOISE, {"sigma": 0.1}))
    result = backend.step(steps=3)

    assert result.sim_time_s == pytest.approx(0.06)
    assert result.physics_steps == 3
    assert backend.get_sim_time() == pytest.approx(0.06)
    assert backend.get_joint_state().names == [f"panda_joint{i}" for i in range(1, 8)]
    assert backend.get_tcp_pose().x == pytest.approx(0.42)
    assert backend.get_contacts()[0].geom1 == "finger_left"
    assert backend.get_sensor_frame().frame_id == "isaac_camera"

    backend.emergency_stop()
    backend.shutdown()


def test_isaac_backend_getters_fail_without_process_telemetry(tmp_path: Path) -> None:
    worker = _write_backend_worker(tmp_path)
    backend = IsaacSimBackend(process_argv=[sys.executable, str(worker)])

    backend.initialize(SimulatorConfig(backend="isaac"))

    with pytest.raises(IsaacProtocolError, match="telemetry"):
        backend.get_tcp_pose()

    backend.shutdown()


def _write_backend_worker(tmp_path: Path) -> Path:
    worker = tmp_path / "isaac_backend_worker.py"
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
            "message": "backend-worker",
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
            "positions": [0.1] * 7,
            "velocities": [0.0] * 7,
            "efforts": [0.0] * 7,
        },
        "tcp_pose": {"x": 0.42, "y": 0.0, "z": 0.31},
        "contacts": [
            {
                "geom1": "finger_left",
                "geom2": "cube",
                "impulse": 0.2,
                "position": {"x": 0.42, "y": 0.0, "z": 0.04},
                "expected": True,
                "illegal": False,
            }
        ],
        "sensor_frame": {
            "frame_id": "isaac_camera",
            "width": 640,
            "height": 480,
            "latency_ms": 16.0,
            "object_detections": [{"object_id": "cube", "confidence": 0.91}],
        },
    })
    print(json.dumps(response), flush=True)
""".lstrip(),
        encoding="utf-8",
    )
    return worker
