from __future__ import annotations

import sys
from pathlib import Path

import pytest

from cloud_edge_robot_arm.simulation.isaac.client import (
    IsaacProtocolError,
    IsaacSimProcessClient,
)
from cloud_edge_robot_arm.simulation.isaac.robot_controller import skill_to_isaac_command


def test_isaac_process_client_performs_jsonl_handshake(tmp_path: Path) -> None:
    worker = _write_worker(tmp_path, replay=False)
    client = IsaacSimProcessClient([sys.executable, str(worker)])

    with client:
        status = client.handshake()
        assert status.status == "READY_TO_CONNECT"
        assert status.sim_time_s == 0.0
        assert status.message == "fake-isaac-process"
        result = client.send_command(
            skill_to_isaac_command(
                "MOVE_ABOVE",
                {"target_object_id": "cube"},
                command_seq=7,
                safety_approval_id="approval-1",
            )
        )

    assert result["ack"] is True
    assert result["command_seq"] == 7
    assert result["command_type"] == "follow_joint_trajectory"


def test_isaac_process_client_rejects_replay_runtime(tmp_path: Path) -> None:
    worker = _write_worker(tmp_path, replay=True)
    client = IsaacSimProcessClient([sys.executable, str(worker)])

    with client:
        with pytest.raises(IsaacProtocolError, match="replay"):
            client.handshake()


def test_isaac_skill_mapping_never_teleports_tcp_pose() -> None:
    movement_skills = [
        "MOVE_ABOVE",
        "APPROACH",
        "LIFT",
        "MOVE_TO_REGION",
        "PLACE",
        "RETREAT",
    ]
    for seq, skill in enumerate(movement_skills):
        command = skill_to_isaac_command(
            skill,
            {"target": "region"},
            command_seq=seq,
            safety_approval_id=f"approval-{seq}",
        )
        assert command.command_type == "follow_joint_trajectory"
        assert command.payload["skill"] == skill
        assert "tcp_pose" not in command.payload
        assert command.payload["safety_approval_id"] == f"approval-{seq}"


def _write_worker(tmp_path: Path, *, replay: bool) -> Path:
    worker = tmp_path / "fake_isaac_worker.py"
    runtime = "recorded_replay" if replay else "isaac_standalone"
    worker.write_text(
        f"""
from __future__ import annotations

import json
import sys

for line in sys.stdin:
    message = json.loads(line)
    if message["message_type"] == "handshake":
        print(json.dumps({{
            "message_type": "handshake_ack",
            "protocol_version": message["protocol_version"],
            "backend": "isaac_sim",
            "runtime": {runtime!r},
            "status": "READY_TO_CONNECT",
            "sim_time_s": 0.0,
            "ros_time_s": 0.0,
            "sensor_timestamp_s": 0.0,
            "message": "fake-isaac-process",
            "capabilities": [
                "joint_state",
                "tcp_pose",
                "rgb_camera",
                "depth_camera",
                "contacts",
                "follow_joint_trajectory"
            ]
        }}), flush=True)
    elif message["message_type"] == "command":
        print(json.dumps({{
            "message_type": "command_ack",
            "protocol_version": message["protocol_version"],
            "backend": "isaac_sim",
            "runtime": "isaac_standalone",
            "ack": True,
            "command_seq": message["command"]["command_seq"],
            "command_type": message["command"]["command_type"],
            "sim_time_s": 0.05,
            "ros_time_s": 0.05,
            "sensor_timestamp_s": 0.05
        }}), flush=True)
""".lstrip(),
        encoding="utf-8",
    )
    return worker
