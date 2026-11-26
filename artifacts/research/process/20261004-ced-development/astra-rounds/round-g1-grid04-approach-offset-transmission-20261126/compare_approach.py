"""One render-free grid-04 prefix and paired native APPROACH calls."""

import argparse
import copy
import hashlib
import importlib.util
import inspect
import json
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import (
    GripperCommand,
    JointCommand,
    PhysicalScenarioConfig,
)
from cloud_edge_robot_arm.simulation.mujoco import backend as backend_module
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.motion_controller import MuJoCoMotionController
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.simulation.mujoco.visual_servo import VisualServoSession

HERE = Path(__file__).resolve().parent
ROOT = next(path for path in HERE.parents if (path / ".git").is_file())
PLAN = json.loads((HERE / "plan.json").read_bytes())


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def clean(command):
    return {key: val for key, val in command.items() if key != "episode_id"}


def write(path, data):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, allow_nan=False, sort_keys=True, separators=(",", ":"))
        stream.write("\n")


def validate():
    raw = ROOT / PLAN["original_raw"]
    generation = PLAN["runtime_manifest_sha256"]
    runtime = (
        ROOT
        / "experiments/results/g1-complete-cv-repair-20261125/builds"
        / generation
        / "runtime-source"
    )
    for base, field in ((raw, "original_raw_sha256"), (HERE.parent, "round_input_sha256")):
        for name, expected in PLAN[field].items():
            require(sha(base / name) == expected, f"original changed: {name}")
    manifest = runtime / "runtime-build.json"
    require(sha(manifest) == generation and mujoco.__version__ == "3.3.7", "frozen runtime differs")
    sources = read(manifest)["runtime_files_sha256"]
    for native in (
        MuJoCoPhysicsBackend,
        MuJoCoMotionController,
        MuJoCoSkillRobot,
        VisualServoSession,
    ):
        path = Path(inspect.getfile(native)).resolve()
        require(sha(path) == sources[path.relative_to(runtime).as_posix()], "native source drift")
    receipt = read(raw / "sensor-receipt.json")
    model = (
        runtime
        / "assets/robots/franka_panda"
        / "scene_g1_development_dual_id7_minusx130_id8_plusx130_end_wings_v1.xml"
    )
    require(sha(model) == sources[model.relative_to(runtime).as_posix()], "asset drift")
    reset_start, reset_end = read(raw / "native-resets.json")
    require(
        reset_start["phase"] == "BEGIN"
        and reset_end["phase"] == "END"
        and reset_start["parameters"] == reset_end["parameters"]
        and reset_end["episode_id"] == receipt["episode_id"]
        and reset_end["error"] is None,
        "native reset identity differs",
    )
    params = dict(reset_start["parameters"]["requested"])
    for name in ("object_pose", "target_region_pose"):
        params[name] = Pose.model_validate(params[name])
    config = PhysicalScenarioConfig(**params)
    commands = read(raw / "native-commands.json")
    require(all(c["episode_id"] == receipt["episode_id"] for c in commands), "foreign command")
    index = read(raw / "rgbd-index.json")
    (frame,) = [x["robot"] for x in index["rows"] if (x["skill"], x["phase"]) == ("GRASP", "PRE")]
    (truth,) = [
        x
        for x in read(raw / "offline-physics.json")["frame_labels"]
        if x["frame_id"] == frame["frame_id"]
    ]
    require(
        sha(raw / "rgbd-index.json") == receipt["index_sha256"]
        and (truth["physics_step"], frame["physics_step"]) == (1280, 1280)
        and truth["checksum_sha256"] == frame["checksum_sha256"],
        "GRASP/PRE source mismatch",
    )
    (approach,) = [action for action in receipt["actions"] if action["skill"] == "APPROACH"]
    require(
        (approach["start_step"], approach["end_step"], approach["status"])
        == (PLAN["shared_prefix_steps"], PLAN["A_terminal_tick"], "PASS"),
        "wrong archived return",
    )
    goal = np.add(receipt["slot"]["center_m"], receipt["aim_offset_m"])
    require(
        goal.tolist() == [approach["details"]["target_pose"][axis] for axis in "xyz"],
        "target changed",
    )
    return model, config, commands, frame, truth, goal


def snapshot(backend):
    data = backend._data
    pose = data.site("tcp")
    return {
        "step": backend.total_physics_steps,
        "time_s": backend.get_sim_time(),
        "q": data.qpos.tolist(),
        "dq": data.qvel.tolist(),
        "ctrl": data.ctrl.tolist(),
        "tcp": pose.xpos.tolist(),
        "wrist": pose.xmat.reshape(3, 3).tolist(),
        "fingers": data.qpos[7:9].tolist(),
        "touching": sorted(
            sorted((contact.geom1, contact.geom2)) for contact in backend.get_contacts()
        ),
    }


def replay_prefix(backend, commands):
    boundary = PLAN["shared_prefix_steps"]
    grouped = defaultdict(list)
    for command in commands:
        if command["command_seq"] <= PLAN["prefix_hold_sequence"]:
            grouped[command["physics_step"]].append(command)
    for step in range(boundary + 1):
        for command in grouped[step]:
            kind = command["type"]
            if kind == "joint_target":
                backend.apply_joint_targets(JointCommand(positions=command["target_positions_rad"]))
            elif kind == "hold_current_joints":
                backend.hold_current_joints()
            elif kind == "gripper":
                backend.apply_gripper_command(GripperCommand(open=command["target_open"]))
            else:
                raise ValueError(f"unexpected prefix command: {kind}")
            require(clean(backend.command_records[-1]) == clean(command), "prefix command differs")
        if step < boundary:
            require(backend.step(1).physics_steps == 1, "prefix step differs")
    require(
        backend.total_physics_steps == boundary
        and len(backend.command_records) == PLAN["prefix_hold_sequence"]
        and backend.command_records[-1]["type"] == "hold_current_joints"
        and not backend._pending_joint_targets,
        "872-step hold boundary differs",
    )


def branch(backend, goal, max_steps):
    start = backend.total_physics_steps
    ordinal = len(backend.command_records)
    states, applied = [snapshot(backend)], []

    def after_step(row):
        require(row.physics_step <= start + max_steps, "approach branch exceeded its budget")
        require(not any(contact.illegal for contact in backend.get_contacts()), "illegal contact")
        states.append(snapshot(backend))

    def before_step(row):
        require(row.physics_step <= start + max_steps, "approach actuator exceeded its budget")
        applied.append(
            {
                "step": row.physics_step,
                "applied_joint_targets": row.applied_joint_targets_rad,
                "ctrl": (*row.control_rad, *row.finger_control_targets_m),
            }
        )

    arm = MuJoCoSkillRobot(backend)
    session = VisualServoSession(lambda target: target)
    with backend.observe_physics_steps(after_step), backend.observe_actuator_steps(before_step):
        with arm.visual_servo(session):
            result = arm.approach(
                "object",
                resolved_target=Pose(**dict(zip("xyz", goal, strict=True))),
                tcp_velocity=0.15,
                acceleration=0.5,
                timeout_ms=8000,
            )
    return {
        "success": result.success,
        "error_code": result.error_code,
        "start_step": start,
        "end_step": backend.total_physics_steps,
        "target": goal.tolist(),
        "states": states,
        "applied": applied,
        "commands": [clean(c) for c in backend.command_records[ordinal:]],
    }


def validate_A(backend, result, commands, frame, truth):
    data = backend._data
    terminal = result["states"][-1]
    require(
        result["success"]
        and result["end_step"] == PLAN["A_terminal_tick"]
        and result["commands"]
        == [
            clean(c)
            for c in commands
            if PLAN["original_approach_first_sequence"]
            <= c["command_seq"]
            <= PLAN["original_approach_terminating_hold_sequence"]
        ],
        "central native APPROACH did not reproduce the original command stream",
    )
    require(
        terminal["time_s"] == frame["sim_time_s"] == frame["camera_encoder_sim_time_s"]
        and terminal["q"][:7] == frame["joint_positions_rad"]
        and terminal["dq"][:7] == frame["joint_velocities_rad_s"]
        and terminal["q"][7:9] == frame["finger_positions_m"]
        and terminal["dq"][7:9] == frame["finger_velocities_m_s"]
        and terminal["touching"] == sorted(sorted(x) for x in truth["touching"])
        and np.array_equal(data.geom("object_geom").xpos, truth["center_m"])
        and np.array_equal(data.geom("object_geom").xmat.reshape(3, 3), truth["rotation"]),
        "central APPROACH did not reproduce the original closure state",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    model, scenario, commands, frame, truth, goal = validate()
    source = HERE.parent / "round-g1-release-terminal-rebound-20261125/terminal_rebound.py"
    spec = importlib.util.spec_from_file_location("zero_camera_lifecycle", source)
    lifecycle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lifecycle)
    args.output.mkdir(parents=True, exist_ok=False)
    backend = MuJoCoPhysicsBackend()
    count = 0
    step_limit = PLAN["shared_prefix_steps"]
    camera_attempts = 0
    suppressed_updates = 0
    native_step = mujoco.mj_step

    def step(model, data):
        nonlocal count
        require(count < step_limit, "registered current phase step cap exceeded")
        count += 1
        return native_step(model, data)

    def deny(*args, **kwargs):
        nonlocal camera_attempts
        camera_attempts += 1
        raise RuntimeError("CPU-only replay attempted to render")

    def suppress_update():
        nonlocal suppressed_updates
        suppressed_updates += 1

    class ScopePreflight(Exception):
        pass

    def preflight_lifecycle():
        empty_frame = backend._sensor_frame
        for signal in (None, ScopePreflight()):
            try:
                with backend.sensor_capture_on_demand():
                    require(backend._sensor_capture_on_demand, "native capture flag never entered")
                    if signal is not None:
                        raise signal
            except ScopePreflight as exc:
                require(exc is signal, "unexpected capture lifecycle exception")
            require(
                not backend._sensor_capture_on_demand
                and backend._camera is None
                and backend._sensor_frame is empty_frame
                and not backend.command_records
                and backend.total_physics_steps == count == camera_attempts == 0,
                "zero-step capture lifecycle preflight altered state",
            )

    with (
        patch.multiple(mujoco, mj_step=step, Renderer=deny, mjr_render=deny),
        patch.object(backend_module, "MuJoCoRGBDCamera", deny),
        patch.multiple(
            backend,
            _update_sensor_frame=suppress_update,
            capture_sensor_frame=deny,
            capture_sensor_frame_with_instances=deny,
            _capture_cached_observed=deny,
        ),
    ):
        try:
            backend.initialize(
                SimulatorConfig(
                    model_path=str(model),
                    seed=scenario.seed,
                    physics_dt_s=1 / 240,
                    domain_randomization=False,
                    render_rgb=True,
                    render_depth=True,
                )
            )
            backend.reset(scenario)
            preflight_lifecycle()
            replay_prefix(backend, commands)
            require(
                not backend._sensor_capture_on_demand, "original APPROACH requires a free scope"
            )
            beginning = lifecycle.integration_digest(backend, mujoco)
            start_data = copy.copy(backend._data)
            fields = (
                "_target_positions",
                "_pending_joint_targets",
                "_command_records",
                "_last_contacts",
                "_gripper_open",
                "_total_physics_steps",
                "_sensor_frame",
            )
            start_fields = {name: copy.deepcopy(getattr(backend, name)) for name in fields}
            step_limit = PLAN["A_terminal_tick"]
            A = branch(backend, goal, PLAN["A_terminal_tick"] - PLAN["shared_prefix_steps"])
            write(args.output / "A.json", A)
            validate_A(backend, A, commands, frame, truth)
            require(camera_attempts == 0, "unexpected real acquisition during A")
            backend._data = start_data
            for name, value in start_fields.items():
                setattr(backend, name, value)
            require(
                lifecycle.integration_digest(backend, mujoco) == beginning
                and not backend._sensor_capture_on_demand,
                "branch start integration and control state differs",
            )
            step_limit = min(count + PLAN["B_max_steps"], PLAN["total_CPU_integration_limit"])
            B = branch(backend, goal + PLAN["B_offset_xyz_m"], PLAN["B_max_steps"])
            write(args.output / "B.json", B)
            require(
                camera_attempts == 0
                and backend._camera is None
                and not backend._sensor_capture_on_demand,
                "reference-only run failed to close without capture",
            )
        except BaseException as exc:
            write(
                args.output / "terminated.json",
                {
                    "error_type": type(exc).__name__,
                    "raw_steps": count,
                    "capture_attempts": camera_attempts,
                    "suppressed_updates": suppressed_updates,
                },
            )
            try:
                backend.shutdown()
            except BaseException as cleanup:
                exc.add_note(f"shutdown also failed: {cleanup}")
            raise
        else:
            backend.shutdown()
    write(
        args.output / "receipt.json",
        {
            "reviewed_prefix_state": beginning,
            "A_archive_checks_passed": True,
            "raw_steps": count,
            "resets": 1,
            "render_calls": camera_attempts,
            "suppressed_sensor_updates": suppressed_updates,
            "physics_scope": "APPROACH_ONLY_NO_LIVE_OPTICAL_AUTHORITY",
            "sha256": {name: sha(args.output / name) for name in ("A.json", "B.json")},
        },
    )


if __name__ == "__main__":
    main()
