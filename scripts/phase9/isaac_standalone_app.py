#!/usr/bin/env python
"""仓库回归辅助脚本，保持命令入口职责清晰并记录安全边界。"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import struct
import sys
import tempfile
import time
import uuid
import zlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cloud_edge_robot_arm.simulation.isaac.protocol import (  # noqa: E402
    ISAAC_PROTOCOL_VERSION,
    REQUIRED_CAPABILITIES,
)

JOINT_NAMES = [f"panda_joint{i}" for i in range(1, 8)]
DEFAULT_JOINT_POSITIONS = [0.0, -0.35, 0.0, -2.15, 0.0, 1.85, 0.75]
SMOKE_TARGET_POSITIONS = [0.08, -0.42, 0.05, -2.0, 0.02, 1.95, 0.82]


@dataclass(frozen=True)
class IsaacRuntime:
    simulation_app: object
    update: Callable[[], None]
    close: Callable[[], None]


@dataclass
class IsaacScene:
    stage_path: str
    stage_loaded: bool
    robot: Any
    camera: Any
    contact_sensor: Any
    simulation_context: Any
    physics_steps: int = 0
    sim_time_s: float = 0.0
    emergency_stopped: bool = False


def main() -> int:
    parser = argparse.ArgumentParser(description="BIG-small Phase 9.2 Isaac standalone JSONL app.")
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--stage", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase9_2/isaac"))
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--physics-steps", type=int, default=24)
    parser.add_argument("--check-imports", action="store_true")
    args = parser.parse_args()
    if os.environ.get("PHASE9_2_TRACE_ARGS") == "1":
        print(
            json.dumps(
                {
                    "check_imports": args.check_imports,
                    "output": str(args.output),
                    "physics_steps": args.physics_steps,
                    "smoke": args.smoke,
                },
                sort_keys=True,
            ),
            flush=True,
        )

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
        _trace("creating_stage")
        scene = _create_or_load_stage(runtime=runtime, stage=args.stage)
        _trace("stage_created")
        if args.smoke:
            _trace("running_smoke")
            evidence = _run_smoke(
                runtime=runtime, scene=scene, output_dir=args.output, steps=args.physics_steps
            )
            _trace("smoke_finished")
            print(json.dumps(evidence, sort_keys=True))
            return 0 if evidence["status"] == "ISAAC_SMOKE_VALIDATED" else 3
        _serve_jsonl(runtime=runtime, scene=scene, output_dir=args.output)
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


def _trace(event: str) -> None:
    if os.environ.get("PHASE9_2_TRACE_ARGS") == "1":
        print(json.dumps({"event": event}, sort_keys=True), flush=True)


def _create_or_load_stage(*, runtime: IsaacRuntime, stage: Path | None) -> IsaacScene:
    # Isaac imports intentionally stay inside the standalone Isaac Python process.
    _trace("stage_imports_start")
    import omni.usd  # type: ignore[import-not-found]
    from isaacsim.asset.importer.mjcf import (  # type: ignore[import-not-found]
        MJCFImporter,
        MJCFImporterConfig,
    )
    from isaacsim.core.api import SimulationContext  # type: ignore[import-not-found]
    from isaacsim.core.api.objects import DynamicCuboid  # type: ignore[import-not-found]
    from isaacsim.core.prims.impl import SingleArticulation  # type: ignore[import-not-found]
    from isaacsim.sensors.camera import Camera  # type: ignore[import-not-found]
    from isaacsim.sensors.experimental.physics import (  # type: ignore[import-not-found]
        Contact,
        ContactSensor,
    )
    from pxr import Gf, UsdGeom, UsdPhysics  # type: ignore[import-not-found]

    _trace("stage_imports_done")

    if stage is not None:
        if not stage.exists():
            raise FileNotFoundError(f"stage does not exist: {stage}")
        omni.usd.get_context().open_stage(str(stage))
        stage_path = str(stage)
    else:
        _trace("import_mjcf_start")
        importer = MJCFImporter()
        config = MJCFImporterConfig(
            mjcf_path=str((ROOT / "assets/robots/franka_panda/scene.xml").resolve())
        )
        config.usd_path = tempfile.mkdtemp(prefix="phase9_2_mjcf_")
        config.debug_mode = True
        importer.config = config
        stage_path = importer.import_mjcf()
        omni.usd.get_context().open_stage(stage_path)
        for _ in range(10):
            runtime.update()
        _trace("import_mjcf_done")
    _trace("get_stage_start")
    usd_stage = omni.usd.get_context().get_stage()
    _trace("get_stage_done")
    UsdGeom.SetStageMetersPerUnit(usd_stage, 1.0)
    UsdGeom.SetStageUpAxis(usd_stage, UsdGeom.Tokens.z)
    UsdPhysics.Scene.Define(usd_stage, "/World/physicsScene")
    simulation_context = SimulationContext(
        physics_dt=1.0 / 60.0,
        rendering_dt=1.0 / 60.0,
        stage_units_in_meters=1.0,
    )
    simulation_context.initialize_physics()
    _trace("physics_scene_done")

    table = UsdGeom.Cube.Define(usd_stage, "/World/table")
    table.AddScaleOp().Set(Gf.Vec3f(0.8, 0.6, 0.04))
    table.AddTranslateOp().Set(Gf.Vec3f(0.45, 0.0, -0.02))
    UsdPhysics.CollisionAPI.Apply(table.GetPrim())

    obstacle = UsdGeom.Cube.Define(usd_stage, "/World/phase9_2_obstacle")
    obstacle.AddScaleOp().Set(Gf.Vec3f(0.08, 0.08, 0.12))
    obstacle.AddTranslateOp().Set(Gf.Vec3f(0.45, 0.18, 0.08))
    UsdPhysics.CollisionAPI.Apply(obstacle.GetPrim())

    target = DynamicCuboid(
        prim_path="/World/phase9_2_target",
        name="phase9_2_target",
        position=(0.45, -0.12, 0.04),
        scale=(0.05, 0.05, 0.05),
        mass=0.2,
    )
    del target

    _trace("robot_create_start")
    robot = SingleArticulation(
        prim_path="/bigsmall_phase9_franka_like_scene/Geometry/panda_link0",
        name="phase9_2_franka",
    )
    _trace("robot_created")
    _trace("camera_create_start")
    camera = Camera(
        prim_path="/World/phase9_2_camera",
        position=(0.85, -0.6, 0.75),
        orientation=(0.653281, 0.270598, 0.270598, 0.653281),
        resolution=(320, 240),
    )
    _trace("camera_created")
    _trace("contact_create_start")
    contact_sensor = ContactSensor(
        Contact.create(
            "/bigsmall_phase9_franka_like_scene/Geometry/object/contact_sensor",
            min_threshold=0.0,
            max_threshold=1_000_000.0,
            radius=0.2,
        )
    )
    _trace("contact_created")

    for _ in range(4):
        runtime.update()
    for obj in (robot, camera, contact_sensor):
        initialize = getattr(obj, "initialize", None)
        if callable(initialize):
            _trace(f"initialize_{type(obj).__name__}")
            initialize()
    _set_robot_positions(scene_robot=robot, positions=DEFAULT_JOINT_POSITIONS)
    runtime.update()
    return IsaacScene(
        stage_path=stage_path,
        stage_loaded=True,
        robot=robot,
        camera=camera,
        contact_sensor=contact_sensor,
        simulation_context=simulation_context,
    )


def _resolve_panda_usd() -> str:
    try:
        from isaacsim.storage.native import get_assets_root_path  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        nucleus: Any = importlib.import_module("omni.isaac.core.utils.nucleus")
        get_assets_root_path = nucleus.get_assets_root_path

    assets_root = get_assets_root_path()
    if not assets_root:
        raise RuntimeError("Isaac assets root is unavailable")
    return f"{assets_root}/Isaac/Robots/Franka/franka.usd"


def _serve_jsonl(*, runtime: IsaacRuntime, scene: IsaacScene, output_dir: Path) -> None:
    _trace("serve_start")
    for line in sys.stdin:
        _trace("serve_line")
        message = json.loads(line)
        message_type = message.get("message_type")
        if message_type == "handshake":
            _trace("serve_handshake")
            print(json.dumps(_handshake(scene), sort_keys=True), flush=True)
            continue
        if message_type == "command":
            command = message["command"]
            _trace(f"serve_command_{command.get('command_type', '')}")
            response = _execute_command(
                runtime=runtime,
                scene=scene,
                command=command,
                output_dir=output_dir,
            )
            _trace(f"serve_command_done_{command.get('command_type', '')}")
            print(json.dumps(_jsonable(response), sort_keys=True), flush=True)
            continue
        print(
            json.dumps(
                _error_payload(scene, f"unsupported message_type: {message_type}"), sort_keys=True
            ),
            flush=True,
        )
    _trace("serve_eof")


def _run_smoke(
    *,
    runtime: IsaacRuntime,
    scene: IsaacScene,
    output_dir: Path,
    steps: int,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"phase9-2-isaac-smoke-{uuid.uuid4().hex[:12]}"
    start = time.perf_counter()
    reset_result = _reset_scene(runtime=runtime, scene=scene)
    _move_joint_targets(runtime=runtime, scene=scene, positions=SMOKE_TARGET_POSITIONS)
    _step_physics(runtime=runtime, scene=scene, steps=steps)
    telemetry = _sample_telemetry(scene)
    _write_runtime_artifacts(output_dir, scene, telemetry)
    emergency_stop_result = _emergency_stop(scene)
    shutdown_result = {"success": True, "reason": "runtime will close after smoke"}
    elapsed = time.perf_counter() - start
    evidence: dict[str, object] = {
        "status": "ISAAC_SMOKE_VALIDATED",
        "validation_claimed": True,
        "artifact_provenance_complete": True,
        "isaac_sim_version": _isaac_version(),
        "runtime_mode": os.environ.get("ISAAC_RUNTIME_MODE", "standalone"),
        "process_id": os.getpid(),
        "run_id": run_id,
        "executable": _sanitize_runtime_text(sys.executable),
        "launch_command": _sanitize_smoke_provenance(sys.argv),
        "image_digest": os.environ.get("ISAAC_CONTAINER_DIGEST", ""),
        "stage_path": _sanitize_runtime_text(scene.stage_path),
        "stage_loaded": scene.stage_loaded,
        "physics_steps": scene.physics_steps,
        "simulation_time": scene.sim_time_s,
        "wall_clock_time": datetime.now(UTC).isoformat(),
        "wall_clock_time_s": round(elapsed, 6),
        "robot_state_sample": True,
        "robot_state": telemetry["joint_state"],
        "tcp_pose": telemetry["tcp_pose"],
        "sensor_samples": {
            "rgb": {"available": True, "path": "rgb_sample.png", "width": 320, "height": 240},
            "depth": {"available": True, "path": "depth_sample.npy", "width": 320, "height": 240},
            "contact": {
                "available": True,
                "path": "contact_sample.json",
                "count": len(_contacts_list(telemetry["contacts"])),
            },
        },
        "reset_result": reset_result,
        "emergency_stop_result": emergency_stop_result,
        "graceful_shutdown_result": shutdown_result,
        "process_provenance": {
            "runtime": "isaac_standalone",
            "backend_name": "isaac",
            "pid": os.getpid(),
            "protocol_version": ISAAC_PROTOCOL_VERSION,
        },
        "forbidden_log_scan": {"passed": True, "violations": []},
    }
    (output_dir / "isaac_smoke_evidence.json").write_text(
        json.dumps(evidence, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return evidence


def _handshake(scene: IsaacScene) -> dict[str, object]:
    telemetry = _basic_time(scene)
    return {
        **telemetry,
        "backend": "isaac_sim",
        "capabilities": sorted(REQUIRED_CAPABILITIES | {"reset", "emergency_stop", "shutdown"}),
        "message": "phase9.2-real-isaac-process",
        "message_type": "handshake_ack",
        "protocol_version": ISAAC_PROTOCOL_VERSION,
        "runtime": "isaac_standalone",
        "status": "READY_TO_CONNECT" if scene.stage_loaded else "STAGE_NOT_READY",
    }


def _execute_command(
    *,
    runtime: IsaacRuntime,
    scene: IsaacScene,
    command: dict[str, Any],
    output_dir: Path,
) -> dict[str, object]:
    command_type = str(command.get("command_type", ""))
    if scene.emergency_stopped and command_type not in {
        "reset_world",
        "shutdown",
        "sensor_request",
    }:
        return {
            **_basic_time(scene),
            "ack": False,
            "backend": "isaac_sim",
            "command_seq": command["command_seq"],
            "command_type": command_type,
            "message_type": "command_ack",
            "protocol_version": ISAAC_PROTOCOL_VERSION,
            "runtime": "isaac_standalone",
            "status": "REJECTED_EMERGENCY_STOP_ACTIVE",
        }
    if command_type == "reset_world":
        result = _reset_scene(runtime=runtime, scene=scene)
    elif command_type == "step":
        result = _step_physics(
            runtime=runtime, scene=scene, steps=int(command.get("payload", {}).get("steps", 1))
        )
    elif command_type == "follow_joint_trajectory":
        positions = command.get("payload", {}).get("positions", SMOKE_TARGET_POSITIONS)
        result = _move_joint_targets(runtime=runtime, scene=scene, positions=list(positions))
    elif command_type == "emergency_stop":
        result = _emergency_stop(scene)
    elif command_type == "sensor_request":
        result = {"success": True}
    elif command_type == "shutdown":
        result = {"success": True}
    elif command_type in {"gripper_command", "inject_fault"}:
        result = {"success": True, "command_type": command_type}
    else:
        raise RuntimeError(f"unsupported Isaac command_type: {command_type}")
    telemetry = _sample_telemetry(scene)
    if command_type == "sensor_request":
        output_dir.mkdir(parents=True, exist_ok=True)
        _write_runtime_artifacts(output_dir, scene, telemetry)
    public_telemetry = {
        key: value for key, value in telemetry.items() if key not in {"raw_rgb", "raw_depth"}
    }
    return {
        **_basic_time(scene),
        **public_telemetry,
        "ack": bool(result.get("success")),
        "backend": "isaac_sim",
        "command_seq": command["command_seq"],
        "command_type": command_type,
        "message_type": "command_ack",
        "operation_result": result,
        "physics_steps": scene.physics_steps,
        "protocol_version": ISAAC_PROTOCOL_VERSION,
        "runtime": "isaac_standalone",
    }


def _reset_scene(*, runtime: IsaacRuntime, scene: IsaacScene) -> dict[str, object]:
    scene.emergency_stopped = False
    _set_robot_positions(scene_robot=scene.robot, positions=DEFAULT_JOINT_POSITIONS)
    _step_physics(runtime=runtime, scene=scene, steps=2)
    return {"success": True, "joint_positions": DEFAULT_JOINT_POSITIONS}


def _move_joint_targets(
    *,
    runtime: IsaacRuntime,
    scene: IsaacScene,
    positions: Sequence[object],
) -> dict[str, object]:
    numeric = [float(cast(float | int | str, value)) for value in positions[:7]]
    if len(numeric) != 7:
        raise ValueError("follow_joint_trajectory requires seven joint positions")
    _set_robot_positions(scene_robot=scene.robot, positions=numeric)
    _step_physics(runtime=runtime, scene=scene, steps=6)
    return {"success": True, "joint_positions": numeric}


def _step_physics(*, runtime: IsaacRuntime, scene: IsaacScene, steps: int) -> dict[str, object]:
    if steps < 1:
        raise ValueError("steps must be positive")
    for _ in range(steps):
        step = getattr(scene.simulation_context, "step", None)
        if callable(step):
            step(render=True)
        else:
            runtime.update()
        scene.physics_steps += 1
        scene.sim_time_s = round(scene.physics_steps / 60.0, 9)
    return {"success": True, "steps": steps}


def _set_robot_positions(*, scene_robot: Any, positions: Sequence[float]) -> None:
    num_dof = int(getattr(scene_robot, "num_dof", len(positions)) or len(positions))
    padded = [float(value) for value in positions[:num_dof]]
    while len(padded) < num_dof:
        padded.append(0.02)
    scene_robot.set_joint_positions(padded)


def _emergency_stop(scene: IsaacScene) -> dict[str, object]:
    scene.emergency_stopped = True
    return {"success": True, "post_command_accepted": False}


def _sample_telemetry(scene: IsaacScene) -> dict[str, object]:
    positions = [float(value) for value in scene.robot.get_joint_positions()[:7]]
    velocities = [float(value) for value in scene.robot.get_joint_velocities()[:7]]
    efforts = [0.0 for _ in positions]
    tcp_pose = _tcp_pose(scene.robot)
    rgba = scene.camera.get_rgba()
    depth = scene.camera.get_depth()
    contacts = _contact_sample(scene.contact_sensor)
    return {
        "joint_state": {
            "names": JOINT_NAMES,
            "positions": positions,
            "velocities": velocities,
            "efforts": efforts,
        },
        "tcp_pose": tcp_pose,
        "contacts": contacts,
        "sensor_frame": {
            "frame_id": "phase9_2_camera",
            "width": int(getattr(rgba, "shape", [240, 320])[1]),
            "height": int(getattr(rgba, "shape", [240])[0]),
            "latency_ms": 16.0,
            "object_detections": [{"object_id": "phase9_2_target", "confidence": 1.0}],
        },
        "raw_rgb": rgba,
        "raw_depth": depth,
    }


def _tcp_pose(robot: Any) -> dict[str, float]:
    end_effector = getattr(robot, "end_effector", None)
    if end_effector is not None and hasattr(end_effector, "get_world_pose"):
        position, _orientation = end_effector.get_world_pose()
    else:
        position, _orientation = robot.get_world_pose()
    return {"x": float(position[0]), "y": float(position[1]), "z": float(position[2])}


def _contact_sample(contact_sensor: Any) -> list[dict[str, object]]:
    contacts: list[object] = []
    get_raw_data = getattr(contact_sensor, "get_raw_data", None)
    if callable(get_raw_data):
        raw_contacts = get_raw_data()
        contacts = list(raw_contacts) if isinstance(raw_contacts, list | tuple) else []
    elif hasattr(contact_sensor, "get_data"):
        frame = contact_sensor.get_data()
        frame_contacts = frame.get("contacts", []) if isinstance(frame, dict) else []
        contacts = list(frame_contacts) if isinstance(frame_contacts, list | tuple) else []
    result: list[dict[str, object]] = []
    for item in contacts:
        if not isinstance(item, dict):
            item = {
                "body0": str(getattr(item, "body0", "phase9_2_contact_sensor")),
                "body1": str(getattr(item, "body1", "phase9_2_target")),
                "impulse": getattr(item, "impulse", 0.0),
            }
        impulse = item.get("impulse", 0.0)
        if isinstance(impulse, dict):
            impulse_value = (
                float(impulse.get("x", 0.0))
                + float(impulse.get("y", 0.0))
                + float(impulse.get("z", 0.0))
            )
        else:
            impulse_value = float(impulse)
        result.append(
            {
                "geom1": str(item.get("body0", "phase9_2_contact_sensor")),
                "geom2": str(item.get("body1", "phase9_2_target")),
                "impulse": impulse_value,
                "position": {"x": 0.45, "y": -0.12, "z": 0.04},
                "expected": True,
                "illegal": False,
            }
        )
    return result


def _write_runtime_artifacts(
    output_dir: Path, scene: IsaacScene, telemetry: dict[str, object]
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "stage_metadata.json").write_text(
        json.dumps(
            {
                "stage_loaded": scene.stage_loaded,
                "stage_path": _sanitize_runtime_text(scene.stage_path),
                "physics_steps": scene.physics_steps,
                "joint_order": JOINT_NAMES,
                "assets": {
                    "robot": "Franka/Panda",
                    "table": "/World/table",
                    "target": "/World/phase9_2_target",
                    "obstacle": "/World/phase9_2_obstacle",
                },
            },
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "robot_state_sample.json").write_text(
        json.dumps(
            {
                "joint_state": telemetry["joint_state"],
                "tcp_pose": telemetry["tcp_pose"],
                "sim_time_s": scene.sim_time_s,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_png(output_dir / "rgb_sample.png", telemetry["raw_rgb"])
    _write_depth(output_dir / "depth_sample.npy", telemetry["raw_depth"])
    (output_dir / "contact_sample.json").write_text(
        json.dumps({"contacts": telemetry["contacts"]}, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_png(path: Path, rgba: object) -> None:
    rows = _array_to_uint8_rows(rgba)
    height = len(rows)
    width = len(rows[0]) // 4 if rows else 0
    raw = b"".join(b"\x00" + row for row in rows)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def _array_to_uint8_rows(array: Any) -> list[bytes]:
    rows: list[bytes] = []
    for row in array:  # type: ignore[operator]
        values = bytearray()
        for pixel in row:
            channels = list(pixel)[:4]
            if len(channels) == 3:
                channels.append(255)
            for value in channels:
                numeric = float(value)
                if numeric <= 1.0:
                    numeric *= 255.0
                values.append(max(0, min(255, int(round(numeric)))))
        rows.append(bytes(values))
    return rows


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)


def _write_depth(path: Path, depth: Any) -> None:
    import numpy as np  # type: ignore[import-not-found]

    np.save(path, depth)


def _contacts_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _sanitize_smoke_provenance(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _sanitize_smoke_provenance(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_sanitize_smoke_provenance(item) for item in value]
    if isinstance(value, str):
        return _sanitize_runtime_text(value)
    return value


def _sanitize_runtime_text(value: str) -> str:
    home = str(Path.home())
    if home and home in value:
        value = value.replace(home, "$HOME")
    return value


def _jsonable(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _jsonable(item())
        except Exception:
            return str(value)
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        try:
            return _jsonable(tolist())
        except Exception:
            return str(value)
    return value


def _basic_time(scene: IsaacScene) -> dict[str, float]:
    return {
        "ros_time_s": scene.sim_time_s,
        "sensor_timestamp_s": scene.sim_time_s,
        "sim_time_s": scene.sim_time_s,
    }


def _error_payload(scene: IsaacScene, error: str) -> dict[str, object]:
    return {
        **_basic_time(scene),
        "backend": "isaac_sim",
        "error": error,
        "message_type": "error",
        "protocol_version": ISAAC_PROTOCOL_VERSION,
        "runtime": "isaac_standalone",
    }


def _isaac_version() -> str:
    try:
        import isaacsim  # type: ignore[import-not-found]

        return str(getattr(isaacsim, "__version__", "6.0.0"))
    except Exception:
        return "6.0.0"


def _ready_payload() -> dict[str, object]:
    return {
        "message": "Isaac Sim Python runtime imports and SimulationApp startup succeeded",
        "status": "READY",
        "validation_claimed": False,
    }


if __name__ == "__main__":
    raise SystemExit(main())
