"""Measure original hold and stop at checkpoints of encoder-closed native motion."""

from __future__ import annotations

import argparse
import itertools
import math
from pathlib import Path

import mujoco
import numpy as np
from scripts.graduation import g1_clearance_mount as mount
from scripts.graduation.g1_clearance_mount_physics import (
    ALLOWED,
    CENTER,
    PHYSICS_DT,
    ROOT,
    digest,
    initialize,
    set_diagnostic_arm,
    write,
)

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

NAMES = (
    "base",
    *(f"link{i}" for i in range(1, 7)),
    "hand",
    "left_finger_geom",
    "right_finger_geom",
    "object_geom",
    *(f"g1_dual_id{code}_{part}" for code in (7, 8) for part in mount.PARTS),
)
GROUPS = {
    "arm_links": slice(0, 7),
    "palm": slice(7, 8),
    "fingers": slice(8, 10),
    "payload": slice(10, None),
}
SIGNS = np.array(list(itertools.product((-1, 1), repeat=3)))
STATE = mujoco.mjtState.mjSTATE_INTEGRATION


class Bodies:
    def __init__(self, model):
        self.ids = np.array([model.geom(n).id for n in NAMES])
        half = []
        for i in self.ids:
            g = model.geom(i)
            if g.type[0] == mujoco.mjtGeom.mjGEOM_BOX:
                h = g.size
            elif g.type[0] == mujoco.mjtGeom.mjGEOM_CYLINDER:
                h = [g.size[0], g.size[0], g.size[1]]
            elif g.type[0] == mujoco.mjtGeom.mjGEOM_CAPSULE:
                h = [g.size[0], g.size[0], g.size[1] + g.size[0]]
            else:
                raise ValueError("unexpected calibration shape " + g.name)
            half.append(h)
        self.local = np.array(half)[:, None, :] * SIGNS[None, :, :]

    def points(self, data):
        return data.geom_xpos[self.ids, None, :] + self.local @ data.geom_xmat[self.ids].reshape(
            -1, 3, 3
        ).transpose(0, 2, 1)


def rotation_angle(a, b):
    r = a.reshape(3, 3).T @ b.reshape(3, 3)
    return math.degrees(math.acos(float(np.clip((np.trace(r) - 1) / 2, -1, 1))))


def render_state(model, data, bodies):
    return bodies.points(data), data.site("tcp").xpos.copy(), data.site("tcp").xmat.copy()


def blank(near):
    backend = MuJoCoPhysicsBackend()
    robot = initialize(backend, CENTER, 0, 1083, False)
    if near:
        set_diagnostic_arm(backend, robot, (CENTER[0], CENTER[1], CENTER[2] + 0.01))
    else:
        backend._data.qpos[
            0
        ] = -0.8  # same native open-camera observation reset, physics-only fixture
        mujoco.mj_forward(backend._model, backend._data)
        backend.hold_current_joints()
    return backend, robot


def actual_trajectory(near, stride, release_retreat=False):
    b, robot = blank(near)
    model, data = b._model, b._data
    bodies = Bodies(model)
    scratch = mujoco.MjData(model)
    stage = ""
    frames = []
    checkpoints = []
    actions = []

    def observe(state):
        if any(frozenset(p) not in ALLOWED for p in state.contact_pairs):
            raise ValueError(
                "actual fixture touched an unauthorized geometry at " + str(state.physics_step)
            )
        scratch.qpos[:] = data.qpos
        scratch.qpos[:7] = b._target_positions
        mujoco.mj_forward(model, scratch)
        actual, tcp, orientation = render_state(model, data, bodies)
        desired, ref, ref_r = render_state(model, scratch, bodies)
        xyz_max = np.max(np.linalg.norm(actual - desired, axis=2), axis=1)
        samples = {k: float(xyz_max[i].max()) for k, i in GROUPS.items() if k != "payload"}
        frames.append(
            {
                "step": state.physics_step,
                "phase": stage,
                "tcp_m": tcp.tolist(),
                "tcp_rotation": orientation.tolist(),
                "q_rad": list(state.joint_positions_rad),
                "qvel_rad_s": list(state.joint_velocities_rad_s),
                "finger_q_m": list(state.finger_positions_m),
                "finger_qvel_m_s": list(state.finger_velocities_m_s),
                "cube_rotation": list(state.object_geom_rotation_row_major),
                "cube_linear_velocity_m_s": list(state.object_linear_velocity_m_s),
                "cube_angular_velocity_rad_s": list(state.object_angular_velocity_rad_s),
                "command_q_rad": b._target_positions.tolist(),
                "command_tcp_m": ref.tolist(),
                "tcp_tracking_m": float(np.linalg.norm(tcp - ref)),
                "wrist_tracking_deg": rotation_angle(orientation, ref_r),
                "max_vertex_tracking_m": samples,
                "cube_xyz_m": list(state.object_geom_position_m),
                "cube_bottom_z_m": state.object_bottom_z_m,
                "contact_pairs": list(state.contact_pairs),
            }
        )
        if state.physics_step % stride == 0:
            packed = np.empty(mujoco.mj_stateSize(model, STATE))
            mujoco.mj_getState(model, data, packed, STATE)
            checkpoints.append(
                (stage, state.physics_step, packed, b._target_positions.copy(), b._gripper_open)
            )

    v = dict(tcp_velocity=0.15, acceleration=0.5)
    low = Pose(x=CENTER[0], y=CENTER[1], z=0.045)
    high = Pose(x=CENTER[0], y=CENTER[1], z=0.16)
    if near:
        calls = (
            ("GRASP", lambda: robot.grasp("object", timeout_ms=1000)),
            ("LIFT", lambda: robot.lift(0.115, timeout_ms=8000, resolved_target=high, **v)),
            (
                "MOVE_TO_REGION",
                lambda: robot.move_to_region(
                    "target_region",
                    timeout_ms=10000,
                    resolved_target=Pose(x=0.2, y=0.25, z=0.16),
                    **v,
                ),
            ),
            (
                "PLACE",
                lambda: robot.place(
                    "target_region",
                    timeout_ms=8000,
                    resolved_target=Pose(x=0.2, y=0.25, z=0.045),
                    **v,
                ),
            ),
        )
        if release_retreat:
            calls += (
                ("RELEASE", lambda: robot.release(timeout_ms=1000)),
                (
                    "RETREAT",
                    lambda: robot.retreat(
                        0.10, timeout_ms=8000, resolved_target=Pose(x=0.2, y=0.25, z=0.16), **v
                    ),
                ),
            )
    else:
        calls = (
            (
                "MOVE_ABOVE",
                lambda: robot.move_above("object", timeout_ms=10000, resolved_target=high, **v),
            ),
            (
                "APPROACH",
                lambda: robot.approach("object", timeout_ms=8000, resolved_target=low, **v),
            ),
        )
    try:
        b.step(60 if near else 120)
        with b.observe_physics_steps(observe):
            for stage, call in calls:
                initial = b.total_physics_steps
                action = call()
                actions.append(
                    dict(
                        stage=stage,
                        status=action.success,
                        error_code=action.error_code,
                        initial=initial,
                        last=b.total_physics_steps,
                    )
                )
                if not action.success:
                    break
    finally:
        b.shutdown()
    return frames, checkpoints, actions


def brake_case(state, backend, bodies, duration):
    stage, step, packed, command, opened = state
    data, model = backend._data, backend._model
    mujoco.mj_setState(model, data, packed, STATE)
    # Refresh kinematics/contacts for this exact checkpoint without advancing physical time.
    mujoco.mj_forward(model, data)
    backend._target_positions = command.copy()
    backend._gripper_open = opened
    backend._total_physics_steps = step
    backend._estop_engaged = False
    initial, tcp, rot = render_state(model, data, bodies)
    start = data.qpos[:7].copy()
    speed = float(np.abs(data.qvel[:7]).max())
    backend.emergency_stop()  # invokes the original hold_current_joints and immediate stop control
    history = []

    def sample():
        site = data.site("tcp")
        cube = data.geom("object_geom")
        wrist = site.xmat.reshape(3, 3)
        history.append(
            (
                data.qpos.copy(),
                data.qvel.copy(),
                site.xpos.copy(),
                wrist.copy(),
                cube.xpos.copy(),
                cube.xmat.reshape(3, 3).copy(),
                wrist.T @ (cube.xpos - site.xpos),
                wrist.T @ cube.xmat.reshape(3, 3),
                data.ctrl.copy(),
            )
        )

    sample()
    thresholds = (1, 8, 32, duration)
    cumulative = np.zeros(len(NAMES))
    maxtcp = 0.0
    maxwrist = 0.0
    maxq = 0.0
    milestones = {}
    forbidden = []
    lost = []
    settle = None
    for idx in range(1, duration + 1):
        backend.step()
        sample()
        current, p, r = render_state(model, data, bodies)
        distances = np.linalg.norm(current - initial, axis=2).max(axis=1)
        cumulative = np.maximum(distances, cumulative)
        maxtcp = max(maxtcp, float(np.linalg.norm(p - tcp)))
        maxwrist = max(maxwrist, rotation_angle(rot, r))
        maxq = max(maxq, float(np.abs(data.qpos[:7] - start).max()))
        pairs = {
            frozenset((model.geom(c.geom1).name, model.geom(c.geom2).name)) for c in data.contact
        }
        bad = pairs - ALLOWED
        if bad:
            forbidden.append([idx, [sorted(x) for x in bad]])
        if stage in ("LIFT", "MOVE_TO_REGION", "PLACE") and not all(
            frozenset((f, "object_geom")) in pairs
            for f in ("left_finger_geom", "right_finger_geom")
        ):
            lost.append(idx)
        if float(np.max(np.abs(data.qvel[:7]))) >= 0.02:
            settle = None
        elif settle is None:
            settle = idx
        if idx in thresholds:
            milestones[str(idx)] = dict(
                tcp_m=maxtcp,
                wrist_deg=maxwrist,
                joint_rad=maxq,
                max_vertex_m={k: float(cumulative[i].max()) for k, i in GROUPS.items()},
            )
    return dict(
        stage=stage,
        step=step,
        initial_max_joint_speed_rad_s=speed,
        milestones=milestones,
        forbidden_contacts=forbidden,
        loaded_bilateral_loss_steps=lost,
        terminal_quiet_since_step=settle,
    ), {
        k: np.stack(values)
        for k, values in zip(
            (
                "qpos",
                "qvel",
                "tcp_m",
                "wrist_matrix",
                "cube_m",
                "cube_matrix",
                "cube_in_tcp_xyz_m",
                "cube_in_tcp_rotation",
                "ctrl",
            ),
            zip(*history, strict=True),
            strict=True,
        )
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--stride", type=int, default=40)
    p.add_argument("--duration", type=int, default=240)
    p.add_argument("--loaded-through-retreat", action="store_true")
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    if a.stride < 1 or a.duration < 32:
        raise ValueError("invalid branch grid")
    modes = {}
    groups = (
        ((True, "loaded"),) if a.loaded_through_retreat else ((False, "empty"), (True, "loaded"))
    )
    for near, kind in groups:
        frames, states, actions = actual_trajectory(near, a.stride, a.loaded_through_retreat)

        write(a.out / (kind + "-native.json.gz"), dict(actions=actions, frames=frames))
        print(kind, actions, len(states), flush=True)
        b, _ = blank(near)
        bodies = Bodies(b._model)
        try:
            results = [brake_case(s, b, bodies, a.duration) for s in states]
            cases, trajectories = zip(*results, strict=True)
            np.savez_compressed(
                a.out / (kind + "-continuous.npz"),
                stage=[item["stage"] for item in cases],
                step=[item["step"] for item in cases],
                **{k: np.stack([row[k] for row in trajectories]) for k in trajectories[0]},
            )

        finally:
            b.shutdown()
        write(a.out / (kind + "-branches.json.gz"), cases)
        modes[kind] = dict(
            actions=actions,
            steps=len(frames),
            branches=len(cases),
            native_sha256=digest(a.out / (kind + "-native.json.gz")),
            branches_sha256=digest(a.out / (kind + "-branches.json.gz")),
            continuous_sha256=digest(a.out / (kind + "-continuous.npz")),
        )
    write(
        a.out / "summary.json",
        dict(
            scope="native actuator calibration at registered targets; visual feedback absent",
            asset_sha256=digest(ROOT / mount.ASSET_PATH),
            timestep_s=PHYSICS_DT,
            stages=modes,
            stride=a.stride,
            followed_steps=a.duration,
            complete_episodes=0,
            diagnostic_generation_sha256=digest(ROOT / "mount-diagnostic-generation.json"),
        ),
    )


if __name__ == "__main__":
    main()
