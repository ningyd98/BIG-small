#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cloud_edge_robot_arm.simulation.isaac.protocol import (  # noqa: E402
    ISAAC_PROTOCOL_VERSION,
    REQUIRED_CAPABILITIES,
)


@dataclass(frozen=True)
class IsaacRuntime:
    simulation_app: object
    update: Callable[[], None]
    close: Callable[[], None]


def main() -> int:
    parser = argparse.ArgumentParser(description="BIG-small Phase 9.1 Isaac standalone JSONL app.")
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--stage", type=Path, default=None)
    parser.add_argument("--check-imports", action="store_true")
    args = parser.parse_args()

    runtime_result = _start_isaac_runtime(headless=args.headless)
    if runtime_result["status"] != "READY":
        print(json.dumps(runtime_result, sort_keys=True))
        return 0 if args.check_imports else 2
    runtime = runtime_result["runtime"]
    if not isinstance(runtime, IsaacRuntime):
        print(json.dumps({"message": "runtime bootstrap failed", "status": "BLOCKED_BY_ENV"}))
        return 2
    if args.check_imports:
        print(json.dumps(_ready_payload(), sort_keys=True))
        runtime.close()
        return 0
    try:
        _serve_jsonl(runtime=runtime, stage=args.stage)
    finally:
        runtime.close()
    return 0


def _start_isaac_runtime(*, headless: bool) -> dict[str, object]:
    try:
        try:
            from isaacsim import SimulationApp  # type: ignore[import-not-found]
        except ModuleNotFoundError:
            from omni.isaac.kit import SimulationApp  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        return {
            "message": f"Isaac Sim Python modules are unavailable: {exc.name}",
            "status": "BLOCKED_BY_ENV",
            "validation_claimed": False,
        }
    app = SimulationApp({"headless": headless})
    return {
        "runtime": IsaacRuntime(simulation_app=app, update=app.update, close=app.close),
        "status": "READY",
        "validation_claimed": False,
    }


def _serve_jsonl(*, runtime: IsaacRuntime, stage: Path | None) -> None:
    stage_status = _load_stage(stage)
    sim_time_s = 0.0
    for line in sys.stdin:
        message = json.loads(line)
        message_type = message.get("message_type")
        if message_type == "handshake":
            print(
                json.dumps(
                    {
                        "backend": "isaac_sim",
                        "capabilities": sorted(REQUIRED_CAPABILITIES),
                        "message": stage_status["message"],
                        "message_type": "handshake_ack",
                        "protocol_version": ISAAC_PROTOCOL_VERSION,
                        "ros_time_s": sim_time_s,
                        "runtime": "isaac_standalone",
                        "sensor_timestamp_s": sim_time_s,
                        "sim_time_s": sim_time_s,
                        "status": "READY_TO_CONNECT"
                        if stage_status["loaded"]
                        else "STAGE_NOT_READY",
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
        elif message_type == "command":
            command = message["command"]
            sim_time_s = _execute_command(runtime=runtime, command=command, sim_time_s=sim_time_s)
            print(
                json.dumps(
                    {
                        "ack": True,
                        "backend": "isaac_sim",
                        "command_seq": command["command_seq"],
                        "command_type": command["command_type"],
                        "message_type": "command_ack",
                        "protocol_version": ISAAC_PROTOCOL_VERSION,
                        "ros_time_s": sim_time_s,
                        "runtime": "isaac_standalone",
                        "sensor_timestamp_s": sim_time_s,
                        "sim_time_s": sim_time_s,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
        else:
            print(
                json.dumps(
                    {
                        "backend": "isaac_sim",
                        "error": f"unsupported message_type: {message_type}",
                        "message_type": "error",
                        "protocol_version": ISAAC_PROTOCOL_VERSION,
                        "ros_time_s": sim_time_s,
                        "runtime": "isaac_standalone",
                        "sensor_timestamp_s": sim_time_s,
                        "sim_time_s": sim_time_s,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )


def _load_stage(stage: Path | None) -> dict[str, object]:
    if stage is None:
        return {"loaded": False, "message": "no Isaac stage path supplied"}
    if not stage.exists():
        return {"loaded": False, "message": f"stage does not exist: {stage}"}
    try:
        import omni.usd  # type: ignore[import-not-found]

        omni.usd.get_context().open_stage(str(stage))
    except Exception as exc:  # pragma: no cover - requires Isaac runtime
        return {"loaded": False, "message": f"stage load failed: {exc}"}
    return {"loaded": True, "message": str(stage)}


def _execute_command(*, runtime: IsaacRuntime, command: dict[str, Any], sim_time_s: float) -> float:
    command_type = command.get("command_type")
    if command_type in {
        "emergency_stop",
        "follow_joint_trajectory",
        "gripper_command",
        "sensor_request",
    }:
        runtime.update()
        return sim_time_s + 0.0166666667
    raise RuntimeError(f"unsupported Isaac command_type: {command_type}")


def _ready_payload() -> dict[str, object]:
    return {
        "message": "Isaac Sim Python runtime imports and SimulationApp startup succeeded",
        "status": "READY",
        "validation_claimed": False,
    }


if __name__ == "__main__":
    raise SystemExit(main())
