"""仿真后端抽象或具体实现，区分 Mock、MuJoCo、Isaac 和 dry-run。"""

from __future__ import annotations

import os
import shlex
from typing import cast

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.isaac.client import (
    IsaacProtocolError,
    IsaacSimProcessClient,
)
from cloud_edge_robot_arm.simulation.isaac.protocol import IsaacCommand
from cloud_edge_robot_arm.simulation.models import (
    ContactSnapshot,
    GripperCommand,
    JointCommand,
    JointStateSnapshot,
    PhysicalFault,
    PhysicalScenarioConfig,
    SensorFrame,
    SimulationStepResult,
)


class IsaacSimBackend:
    """SimulatorBackend implementation backed by a real Isaac standalone process.

    The backend does not import Isaac Sim modules into the core Python process.
    It communicates with an already configured Isaac Python/runtime process over
    the Phase 9.1 JSONL protocol and refuses to synthesize telemetry.
    """

    def __init__(self, process_argv: list[str] | None = None) -> None:
        self._process_argv = process_argv
        self._client: IsaacSimProcessClient | None = None
        self._config: SimulatorConfig | None = None
        self._command_seq = 0
        self._last_response: dict[str, object] | None = None

    def initialize(self, config: SimulatorConfig) -> None:
        self._config = config
        argv = self._process_argv or _argv_from_env()
        if not argv:
            raise IsaacProtocolError("Isaac process argv is required; set ISAAC_SIM_BACKEND_CMD")
        self._client = IsaacSimProcessClient(argv)
        self._client.start()
        self._client.handshake()

    def reset(self, scenario: PhysicalScenarioConfig) -> None:
        self._send(
            "reset_world",
            {
                "scenario_id": scenario.scenario_id,
                "seed": scenario.seed,
                "object_mass_kg": scenario.object_mass_kg,
                "friction_coefficient": scenario.friction_coefficient,
                "max_episode_s": scenario.max_episode_s,
            },
        )

    def step(self, steps: int = 1) -> SimulationStepResult:
        if steps < 1:
            raise ValueError("steps must be positive")
        response = self._send("step", {"steps": steps})
        return SimulationStepResult(
            sim_time_s=_required_float(response, "sim_time_s"),
            physics_steps=_required_int(response, "physics_steps"),
            contacts=self._parse_contacts(response),
            sensor_frame=self._parse_sensor_frame(response),
        )

    def shutdown(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def get_sim_time(self) -> float:
        response = self._require_telemetry()
        return _required_float(response, "sim_time_s")

    def get_joint_state(self) -> JointStateSnapshot:
        response = self._require_telemetry()
        payload = _required_dict(response, "joint_state")
        return JointStateSnapshot(
            names=[str(item) for item in _required_list(payload, "names")],
            positions=_required_float_list(payload, "positions"),
            velocities=_required_float_list(payload, "velocities"),
            efforts=_required_float_list(payload, "efforts"),
            sim_time_s=_required_float(response, "sim_time_s"),
        )

    def get_tcp_pose(self) -> Pose:
        response = self._require_telemetry()
        payload = _required_dict(response, "tcp_pose")
        return _parse_pose(payload)

    def get_contacts(self) -> list[ContactSnapshot]:
        return self._parse_contacts(self._require_telemetry())

    def get_sensor_frame(self) -> SensorFrame:
        return self._parse_sensor_frame(self._require_telemetry())

    def apply_joint_targets(self, targets: JointCommand) -> None:
        self._send(
            "follow_joint_trajectory",
            {
                "positions": targets.positions,
                "max_velocity": targets.max_velocity,
                "timeout_s": targets.timeout_s,
            },
        )

    def apply_gripper_command(self, command: GripperCommand) -> None:
        self._send(
            "gripper_command",
            {
                "open": command.open,
                "force_n": command.force_n,
                "timeout_s": command.timeout_s,
            },
        )

    def emergency_stop(self) -> None:
        self._send("emergency_stop", {"reason": "phase9_1_backend_request"})

    def inject_fault(self, fault: PhysicalFault) -> None:
        self._send(
            "inject_fault",
            {
                "fault_type": fault.fault_type.value,
                "parameters": dict(fault.parameters),
            },
        )

    def _send(self, command_type: str, payload: dict[str, object]) -> dict[str, object]:
        if self._client is None:
            raise IsaacProtocolError("Isaac backend is not initialized")
        self._command_seq += 1
        response = self._client.send_command(
            IsaacCommand(
                command_type=command_type,
                payload=payload,
                command_seq=self._command_seq,
            )
        )
        self._last_response = response
        return response

    def _require_telemetry(self) -> dict[str, object]:
        if self._last_response is None:
            raise IsaacProtocolError("Isaac backend telemetry is unavailable")
        for key in ("joint_state", "tcp_pose", "sensor_frame"):
            if key not in self._last_response:
                raise IsaacProtocolError(f"Isaac backend telemetry missing {key}")
        return self._last_response

    def _parse_contacts(self, response: dict[str, object]) -> list[ContactSnapshot]:
        contacts = response.get("contacts", [])
        if not isinstance(contacts, list):
            raise IsaacProtocolError("Isaac contacts must be a list")
        parsed: list[ContactSnapshot] = []
        sim_time_s = _required_float(response, "sim_time_s")
        for item in contacts:
            if not isinstance(item, dict):
                raise IsaacProtocolError("Isaac contact entry must be an object")
            parsed.append(
                ContactSnapshot(
                    geom1=str(item["geom1"]),
                    geom2=str(item["geom2"]),
                    impulse=float(cast(float | int | str, item["impulse"])),
                    position=_parse_pose(_required_dict(item, "position")),
                    sim_time_s=sim_time_s,
                    expected=bool(item.get("expected", False)),
                    illegal=bool(item.get("illegal", False)),
                )
            )
        return parsed

    def _parse_sensor_frame(self, response: dict[str, object]) -> SensorFrame:
        payload = _required_dict(response, "sensor_frame")
        return SensorFrame(
            frame_id=str(payload["frame_id"]),
            sim_time_s=_required_float(response, "sim_time_s"),
            width=_required_int(payload, "width"),
            height=_required_int(payload, "height"),
            object_detections=[
                dict(cast(dict[str, object], item))
                for item in _required_list(payload, "object_detections")
            ],
            latency_ms=_required_float(payload, "latency_ms"),
            ground_truth_used_for_control=False,
        )


def _argv_from_env() -> list[str]:
    raw = os.environ.get("ISAAC_SIM_BACKEND_CMD", "")
    return shlex.split(raw) if raw else []


def _required_dict(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise IsaacProtocolError(f"missing object field: {key}")
    return cast(dict[str, object], value)


def _required_list(payload: dict[str, object], key: str) -> list[object]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise IsaacProtocolError(f"missing list field: {key}")
    return value


def _required_float_list(payload: dict[str, object], key: str) -> list[float]:
    values = _required_list(payload, key)
    result: list[float] = []
    for value in values:
        if not isinstance(value, (float, int, str)):
            raise IsaacProtocolError(f"non-numeric value in list field: {key}")
        result.append(float(value))
    return result


def _required_float(payload: dict[str, object], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, (float, int, str)):
        raise IsaacProtocolError(f"missing numeric field: {key}")
    return float(value)


def _required_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, (float, int, str)):
        raise IsaacProtocolError(f"missing integer field: {key}")
    return int(value)


def _parse_pose(payload: dict[str, object]) -> Pose:
    return Pose(
        x=_required_float(payload, "x"),
        y=_required_float(payload, "y"),
        z=_required_float(payload, "z"),
    )
