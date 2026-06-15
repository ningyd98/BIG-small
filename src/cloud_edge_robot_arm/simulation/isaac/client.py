from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from types import TracebackType
from typing import cast

from cloud_edge_robot_arm.simulation.isaac.protocol import (
    ISAAC_PROTOCOL_VERSION,
    REQUIRED_CAPABILITIES,
    IsaacCommand,
    IsaacHandshake,
    IsaacStatus,
)


class IsaacProtocolError(RuntimeError):
    pass


class IsaacSimClient:
    """Independent-process Isaac Sim client guard.

    The core package never imports Isaac private modules. A compatible host runs
    the standalone Isaac app and communicates over ROS 2 or the bridge protocol.
    """

    def check_status(self) -> IsaacStatus:
        root = os.environ.get("ISAAC_SIM_ROOT", "")
        if not root or not Path(root).exists():
            return IsaacStatus(
                status="BLOCKED_BY_ENV",
                sim_time_s=0.0,
                message="ISAAC_SIM_ROOT is unset or missing",
            )
        return IsaacStatus(status="READY_TO_CONNECT", sim_time_s=0.0, message=root)


class IsaacSimProcessClient:
    """JSONL client for a real Isaac Sim standalone process.

    The process is external to the core Python environment. This client only
    speaks a versioned protocol over stdin/stdout and rejects recorded replay
    runtimes so a fixture cannot be mistaken for Isaac validation.
    """

    def __init__(self, argv: list[str], *, timeout_s: float = 10.0) -> None:
        self._argv = argv
        self._timeout_s = timeout_s
        self._process: subprocess.Popen[str] | None = None
        self._last_sim_time_s = -1.0

    def __enter__(self) -> IsaacSimProcessClient:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def start(self) -> None:
        if self._process is not None:
            return
        self._process = subprocess.Popen(
            self._argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def close(self) -> None:
        if self._process is None:
            return
        process = self._process
        self._process = None
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)

    def handshake(self) -> IsaacStatus:
        payload: dict[str, object] = {
            "message_type": "handshake",
            "protocol_version": ISAAC_PROTOCOL_VERSION,
            "required_capabilities": sorted(REQUIRED_CAPABILITIES),
            "time_domains": [
                "simulation_time",
                "ros_time",
                "wall_clock_time",
                "sensor_timestamp",
            ],
        }
        response = self._round_trip(payload)
        handshake = self._parse_handshake(response)
        self._last_sim_time_s = handshake.sim_time_s
        return handshake.to_status()

    def send_command(self, command: IsaacCommand) -> dict[str, object]:
        response = self._round_trip(
            {
                "message_type": "command",
                "protocol_version": ISAAC_PROTOCOL_VERSION,
                "command": command.to_jsonable(),
                "wall_time_ns": time.time_ns(),
            }
        )
        if response.get("message_type") != "command_ack":
            raise IsaacProtocolError(f"expected command_ack, got {response.get('message_type')}")
        self._validate_common_response(response)
        sim_time_s = _required_float(response, "sim_time_s")
        if sim_time_s < self._last_sim_time_s:
            raise IsaacProtocolError("simulation time moved backwards")
        self._last_sim_time_s = sim_time_s
        return response

    def _round_trip(self, payload: dict[str, object]) -> dict[str, object]:
        if self._process is None:
            self.start()
        process = self._require_process()
        if process.stdin is None or process.stdout is None:
            raise IsaacProtocolError("Isaac process pipes are unavailable")
        process.stdin.write(json.dumps(payload, sort_keys=True) + "\n")
        process.stdin.flush()
        line = process.stdout.readline()
        if not line:
            stderr = process.stderr.read() if process.stderr else ""
            raise IsaacProtocolError(f"Isaac process produced no response: {stderr[-1000:]}")
        decoded = json.loads(line)
        if not isinstance(decoded, dict):
            raise IsaacProtocolError("Isaac process response must be a JSON object")
        return decoded

    def _parse_handshake(self, response: dict[str, object]) -> IsaacHandshake:
        if response.get("message_type") != "handshake_ack":
            raise IsaacProtocolError(f"expected handshake_ack, got {response.get('message_type')}")
        self._validate_common_response(response)
        raw_capabilities = response.get("capabilities", [])
        if not isinstance(raw_capabilities, list):
            raise IsaacProtocolError("Isaac capabilities must be a list")
        capabilities = frozenset(str(item) for item in raw_capabilities)
        missing = REQUIRED_CAPABILITIES - capabilities
        if missing:
            raise IsaacProtocolError(f"Isaac process is missing capabilities: {sorted(missing)}")
        if response.get("runtime") != "isaac_standalone":
            raise IsaacProtocolError("Isaac process runtime is replay or unsupported")
        return IsaacHandshake(
            backend="isaac_sim",
            runtime="isaac_standalone",
            status=str(response["status"]),
            sim_time_s=_required_float(response, "sim_time_s"),
            ros_time_s=_required_float(response, "ros_time_s"),
            sensor_timestamp_s=_required_float(response, "sensor_timestamp_s"),
            message=str(response.get("message", "")),
            capabilities=capabilities,
        )

    def _validate_common_response(self, response: dict[str, object]) -> None:
        if response.get("protocol_version") != ISAAC_PROTOCOL_VERSION:
            raise IsaacProtocolError("Isaac protocol version mismatch")
        if response.get("backend") != "isaac_sim":
            raise IsaacProtocolError("response did not come from Isaac backend")
        if response.get("runtime") in {"recorded_replay", "mock", "static_fixture"}:
            raise IsaacProtocolError("Isaac replay/static runtime is not valid for validation")
        for key in ("sim_time_s", "ros_time_s", "sensor_timestamp_s"):
            if key not in response:
                raise IsaacProtocolError(f"missing time domain: {key}")

    def _require_process(self) -> subprocess.Popen[str]:
        if self._process is None:
            raise IsaacProtocolError("Isaac process has not been started")
        if self._process.poll() is not None:
            raise IsaacProtocolError(f"Isaac process exited with {self._process.returncode}")
        return self._process


def _required_float(payload: dict[str, object], key: str) -> float:
    value = payload[key]
    return float(cast(float | int | str, value))
