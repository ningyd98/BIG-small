"""Branch from archived visual-controller trajectories into the original native stop."""

from __future__ import annotations

import argparse
import collections
import json
import math
from pathlib import Path

import mujoco
import numpy as np
from scripts.graduation import g1_clearance_mount as mount
from scripts.graduation.g1_clearance_mount_brake import STATE, Bodies, brake_case
from scripts.graduation.g1_clearance_mount_contact import INPUTS
from scripts.graduation.g1_clearance_mount_physics import PHYSICS_DT, ROOT, digest, write

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import JointCommand, PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

COMMANDS = {
    "train-radial15-timing-01": "3d0b504dd2dd81d77ff7b28f3c2a486b4542667fadd0a65d454af2c372621754",
    "train-radial30-contact-d02-02": (
        "6dea1a3740d0c1275a21c658895fca984774d36d3fec21f4a99ca927b9f8d2c0"
    ),
}
APPROACH = {"train-radial15-timing-01": 912, "train-radial30-contact-d02-02": 896}


def initialize(xml, initial):
    backend = MuJoCoPhysicsBackend()
    backend.initialize(
        SimulatorConfig(
            model_path=str(xml),
            physics_dt_s=PHYSICS_DT,
            domain_randomization=False,
        )
    )
    x, y, z = initial["object_position_m"]
    rotation = initial["object_geom_rotation_row_major"]
    backend.reset(
        PhysicalScenarioConfig(
            scenario_id="S01_NORMAL_STATIC",
            seed=22,
            object_pose=Pose(x=x, y=y, z=z),
            object_mass_kg=float(backend._model.body("object").mass[0]),
            object_yaw_rad=math.atan2(rotation[3], rotation[0]),
        )
    )
    data = backend._data
    data.qpos[:7] = initial["joint_positions_rad"]
    data.qpos[7:9] = initial["finger_positions_m"]
    backend._target_positions = np.array(initial["joint_positions_rad"])
    mujoco.mj_forward(backend._model, data)
    return backend


def replay(xml, rows, commands, name, stride, prefix, output):
    b = initialize(xml, rows[0])
    model, data = b._model, b._data
    command_by_step = collections.defaultdict(list)
    for c in commands:
        command_by_step[c["physics_step"]].append(c)
    residual_joint = 0.0
    residual_finger = 0.0
    residual_tcp = 0.0
    residual_cube = 0.0
    checkpoints = []
    try:
        for step, row in enumerate(rows):
            residual_joint = max(
                residual_joint, float(max(abs(data.qpos[:7] - row["joint_positions_rad"])))
            )
            residual_finger = max(
                residual_finger, float(max(abs(data.qpos[7:9] - row["finger_positions_m"])))
            )
            residual_tcp = max(
                residual_tcp, float(np.linalg.norm(data.site("tcp").xpos - row["tcp_position_m"]))
            )
            residual_cube = max(
                residual_cube,
                float(
                    np.linalg.norm(data.geom("object_geom").xpos - row["object_geom_position_m"])
                ),
            )
            if row["physics_step"] != step:
                raise ValueError("nonuniform native visual trajectory")
            if (step >= 120 and step % stride == 0) or step in {
                len(rows) - 10,
                len(rows) - 9,
                len(rows) - 2,
            }:
                packed = np.empty(mujoco.mj_stateSize(model, STATE))
                mujoco.mj_getState(model, data, packed, STATE)
                phase = "APPROACH" if step >= APPROACH[name] else "MOVE_ABOVE"
                checkpoints.append(
                    (phase, step, packed, b._target_positions.copy(), b._gripper_open)
                )
            if step == len(rows) - 1:
                break
            for cmd in command_by_step[step]:
                if not cmd["accepted"]:
                    continue
                if cmd["type"] == "joint_target":
                    b.apply_joint_targets(JointCommand(positions=cmd["target_positions_rad"]))
                elif cmd["type"] == "hold_current_joints":
                    b.hold_current_joints()
                else:
                    raise ValueError("unexpected preterminal command: " + cmd["type"])
            b.step()
    finally:
        b.shutdown()
    if (
        prefix == "original"
        and max(residual_joint, residual_tcp, residual_finger, residual_cube) > 1e-6
    ):
        raise ValueError(
            f"archived original not reproduced: {residual_joint}, {residual_tcp}, {residual_cube}"
        )
    b = initialize(xml, rows[0])
    bodies = Bodies(b._model)
    try:
        results = [brake_case(s, b, bodies, 240) for s in checkpoints]
    finally:
        b.shutdown()
    cases, paths = zip(*results, strict=True)
    key = name + "-" + prefix
    write(output / (key + "-stop.json.gz"), cases)
    np.savez_compressed(
        output / (key + "-continuous.npz"),
        step=[r["step"] for r in cases],
        stage=[r["stage"] for r in cases],
        **{k: np.stack([p[k] for p in paths]) for k in paths[0]},
    )
    return dict(
        trajectory=name,
        mount=prefix,
        source_states=len(rows),
        count=len(cases),
        original_commands_replayed=len(commands) - len(command_by_step[len(rows) - 1]),
        max_joint_residual_rad=residual_joint,
        max_finger_residual_m=residual_finger,
        max_tcp_residual_m=residual_tcp,
        max_cube_center_residual_m=residual_cube,
        stop_sha256=digest(output / (key + "-stop.json.gz")),
        continuous_sha256=digest(output / (key + "-continuous.npz")),
        asset_sha256=digest(xml),
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--stride", type=int, default=32)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    base = a.repo / "experiments/results/g1-visibility-pose-repair-20261124/batches"
    results = []
    for name, count, truth_sha, asset in INPUTS:
        case = base / name / "d02/instance"
        raw = case / "offline-truth.json"
        commands = case / "backend-commands.json"
        if digest(raw) != truth_sha or digest(commands) != COMMANDS[name]:
            raise ValueError("foreign archived observations or visual-controller commands")
        trace = json.loads(raw.read_bytes())
        rows = trace["samples"]
        if len(rows) != count or trace["asset_sha256"] != digest(ROOT / asset):
            raise ValueError("wrong archival state count or physical model")
        for label, path in (("original", ROOT / asset), ("end-wings", ROOT / mount.ASSET_PATH)):
            result = replay(
                path, rows, json.loads(commands.read_bytes()), name, a.stride, label, a.out
            )
            print(
                name,
                label,
                result["max_joint_residual_rad"],
                result["max_tcp_residual_m"],
                flush=True,
            )
            results.append(
                dict(offline_truth_sha256=truth_sha, commands_sha256=COMMANDS[name], **result)
            )
    write(
        a.out / "summary.json",
        dict(
            scope="native archived visual commands, counterfactual stop branches",
            complete_episodes=0,
            trajectory_runs=results,
            stride=a.stride,
            diagnostic_generation_sha256=digest(ROOT / "mount-diagnostic-generation.json"),
        ),
    )


if __name__ == "__main__":
    main()
