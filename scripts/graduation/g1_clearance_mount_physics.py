"""Independent actuator-driven grasp/lift qualification, starting once at a known open-hand pose."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path

import mujoco
import numpy as np
from scripts.graduation import g1_clearance_mount as mount

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD, MuJoCoSkillRobot

PHYSICS_DT = 1 / 240
CENTER = (0.45, 0.0, 0.035)
ANGLES = (0.0, -1.0, 1.0, -2.5, 2.5, -1.5, 1.5, -2.0, 2.0)
OFFSETS_MM = ((0, 0), *[p for p in itertools.product((-3, 0, 3), repeat=2) if p != (0, 0)])
ALLOWED = {
    frozenset((name, "object_geom")) for name in ("left_finger_geom", "right_finger_geom", "table")
}
GRIP_NAMES = ("left_finger_geom", "right_finger_geom")
ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    payload = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if path.suffix == ".gz":
        payload = gzip.compress(payload, compresslevel=3, mtime=0)
    with path.open("xb") as stream:
        stream.write(payload)


def initialize(backend, xyz, angle_deg, seed, rendering):
    backend.initialize(
        SimulatorConfig(
            model_path=str(ROOT / mount.ASSET_PATH),
            seed=seed,
            physics_dt_s=PHYSICS_DT,
            domain_randomization=False,
            render_rgb=rendering,
            render_depth=rendering,
        )
    )
    backend.reset(
        PhysicalScenarioConfig(
            scenario_id="S01_NORMAL_STATIC",
            seed=seed,
            object_mass_kg=mount.BODY_MASS_KG,
            object_pose=Pose(x=xyz[0], y=xyz[1], z=xyz[2]),
            object_yaw_rad=math.radians(angle_deg),
        )
    )
    return MuJoCoSkillRobot(backend)


def set_diagnostic_arm(backend, robot, xyz, finger_positions=(0.04, 0.04)):
    model, data = backend._model, backend._data
    if backend.total_physics_steps or np.any(data.qvel):
        raise ValueError("diagnostic initial-pose assignment requires an untouched static fixture")
    q = robot._motion._inverse_kinematics(np.array(xyz), np.array(_DOWNWARD), model.site("tcp").id)
    if q is None:
        raise ValueError("registered fixed-wrist pose has no native IK solution")
    # Initial fixture only. No object coordinate or actuator command is written after this setup.
    data.qpos[:7] = q
    for name, value in zip(
        ("finger_left_joint", "finger_right_joint"), finger_positions, strict=True
    ):
        data.qpos[model.joint(name).qposadr[0]] = value
    mujoco.mj_forward(model, data)
    backend.hold_current_joints()


def snapshot(backend, state):
    model, data = backend._model, backend._data
    forces = [0.0, 0.0]
    illegal = []
    for i, c in enumerate(data.contact):
        pair = (model.geom(int(c.geom1)).name, model.geom(int(c.geom2)).name)
        names = frozenset(pair)
        if names not in ALLOWED:
            illegal.append(pair)
        for j, finger in enumerate(GRIP_NAMES):
            if names == {finger, "object_geom"}:
                force = np.zeros(6)
                mujoco.mj_contactForce(model, data, i, force)
                forces[j] += float(force[0])
    rotation = np.asarray(state.object_geom_rotation_row_major).reshape(3, 3)
    hand = data.site("tcp").xmat.reshape(3, 3)
    side = abs(rotation.T @ hand[:, 1]) @ np.array([0.035] * 3)
    width = sum(state.finger_positions_m) + 0.002
    relative = rotation.T @ (np.asarray(state.tcp_position_m) - state.object_geom_position_m)
    return dict(
        step=state.physics_step,
        dt_s=state.sim_time_s,
        cube_xyz_m=state.object_geom_position_m,
        tcp_xyz_m=state.tcp_position_m,
        cube_bottom_m=state.object_bottom_z_m,
        cube_rotation=state.object_geom_rotation_row_major,
        wrist_rotation=hand.ravel().tolist(),
        xyz_error_object_m=relative.tolist(),
        projected_cube_width_m=float(2 * side),
        inside_jaw_width_m=width,
        finger_joints_m=state.finger_positions_m,
        normal_force_N=forces,
        joints_rad=state.joint_positions_rad,
        speeds_rad_s=state.joint_velocities_rad_s,
        cube_linear_velocity_m_s=state.object_linear_velocity_m_s,
        cube_angular_velocity_rad_s=state.object_angular_velocity_rad_s,
        contact_pairs=state.contact_pairs,
        forbidden_pairs=illegal,
    )


def run_case(out, case_id, angle, xy_mm):
    backend = MuJoCoPhysicsBackend()
    rows = []
    phase = "RESET"
    close_result = lift_result = None
    try:
        robot = initialize(backend, CENTER, angle, 1083, False)
        target = (CENTER[0] + xy_mm[0] / 1000, CENTER[1] + xy_mm[1] / 1000, CENTER[2] + 0.01)
        set_diagnostic_arm(backend, robot, target)

        def record(state):
            row = snapshot(backend, state)
            rows.append(dict(phase=phase, **row))
            if row["forbidden_pairs"]:
                raise RuntimeError(
                    "forbidden diagnostic physical contact: " + str(row["forbidden_pairs"])
                )

        record(backend.current_physics_observation())
        with backend.observe_physics_steps(record):
            phase = "OPEN_SETTLE"
            backend.step(60)
            if any(f > 0 for f in rows[-1]["normal_force_N"]):
                raise ValueError("open hand already touching before commanded closure")
            phase = "GRASP"
            close_result = robot.grasp("object", timeout_ms=1000)
            if close_result.success:
                phase = "LIFT"
                lift_result = robot.lift(
                    height_m=0.10, tcp_velocity=0.15, acceleration=0.5, timeout_ms=8000
                )
        commands = backend.command_records
        write(out / (case_id + "-commands.json.gz"), commands)
    finally:
        backend.shutdown()
        write(out / (case_id + ".json.gz"), rows)
    closes = [r for r in rows if r["phase"] == "GRASP"]
    lifts = [r for r in rows if r["phase"] == "LIFT"]
    before = next(r for r in reversed(rows) if r["phase"] == "OPEN_SETTLE")
    hold = lifts[-120:]
    first = []
    for side in range(2):
        hits = [r["step"] for r in closes if r["normal_force_N"][side] > 0]
        first.append(hits[0] if hits else None)
    initial = np.asarray(before["xyz_error_object_m"])
    rr = np.array(before["cube_rotation"]).reshape(3, 3)
    rw = np.array(before["wrist_rotation"]).reshape(3, 3)
    yaw = math.degrees(math.atan2((rr.T @ rw[:, 1])[0], (rr.T @ rw[:, 1])[1]))
    bilateral_hold = len(hold) == 120 and all(min(r["normal_force_N"]) > 0 for r in hold)
    measured_lift = min((r["cube_bottom_m"] - before["cube_bottom_m"] for r in hold), default=0)
    yaw_cube = [
        math.degrees(math.atan2(r["cube_rotation"][3], r["cube_rotation"][0])) for r in closes
    ]
    grip_slip = max(
        (
            np.linalg.norm(np.array(r["xyz_error_object_m"]) - closes[-1]["xyz_error_object_m"])
            for r in lifts
        ),
        default=0,
    )
    return dict(
        case=case_id,
        nominal_cube_yaw_deg=angle,
        target_offset_xy_mm=xy_mm,
        measured_open_xyz_error_object_m=initial.tolist(),
        measured_face_yaw_deg=yaw,
        projected_cube_width_m=before["projected_cube_width_m"],
        inside_open_width_m=before["inside_jaw_width_m"],
        first_contact_step=first,
        bilateral_close=bool(close_result.success),
        closed_jaw_width_m=closes[-1]["inside_jaw_width_m"],
        close_normal_force_N=closes[-1]["normal_force_N"],
        close_cube_yaw_range_deg=[min(yaw_cube), max(yaw_cube)],
        max_lift_slip_m=float(grip_slip),
        native_lift_success=bool(lift_result and lift_result.success),
        lift_error_code=lift_result.error_code if lift_result else None,
        lift_threshold_continuous_hold=bilateral_hold and measured_lift >= 0.05,
        last_half_second_min_lift_m=measured_lift,
        min_hold_normal_force_N=(
            np.min([r["normal_force_N"] for r in hold], axis=0).tolist() if hold else None
        ),
        forbidden_contact_steps=sum(bool(r["forbidden_pairs"]) for r in rows),
        physical_steps=rows[-1]["step"],
        raw_sha256=digest(out / (case_id + ".json.gz")),
        commands_sha256=hashlib.sha256(json.dumps(commands, sort_keys=True).encode()).hexdigest(),
        eligible=bool(
            close_result.success
            and lift_result
            and lift_result.success
            and bilateral_hold
            and measured_lift >= 0.05
        ),
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--center-only", action="store_true")
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    cases = itertools.product(
        ANGLES if not a.center_only else (0,), OFFSETS_MM if not a.center_only else ((0, 0),)
    )
    rows = []
    for i, (angle, xy) in enumerate(cases, start=1):
        case = run_case(a.out, f"close-{i:03d}", angle, xy)
        write(a.out / f"close-{i:03d}-summary.json", case)
        rows.append(case)
        print(
            f"{case['case']} angle={angle} xy_mm={xy} achieved={case['eligible']} "
            f"hold_m={case['last_half_second_min_lift_m']:.6f}",
            flush=True,
        )
    write(
        a.out / "summary.json",
        dict(
            mount_asset_sha256=digest(ROOT / mount.ASSET_PATH),
            effective_diagnostic_generation_sha256=digest(
                ROOT / "mount-diagnostic-generation.json"
            ),
            fixed_wrist_wxyz=_DOWNWARD,
            native_dt_s=PHYSICS_DT,
            grasp_duration_s=1.0,
            lift_height_requested_m=0.10,
            lift_timeout_s=8.0,
            tcp_velocity_m_s=0.15,
            acceleration_m_s2=0.5,
            sensor_feedback=False,
            development_diagnostic_fixture=True,
            complete_skill_dispatches=0,
            cases=rows,
            total=len(rows),
            passed=sum(r["eligible"] for r in rows),
        ),
    )


if __name__ == "__main__":
    main()
