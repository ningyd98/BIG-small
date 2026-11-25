"""Full physical force and contact-point measurements for the registered closure/lift fixture."""

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import mujoco
import numpy as np
from scripts.graduation import g1_clearance_mount_physics as physics


def contacts(backend):
    model, data = backend._model, backend._data
    names = list(physics.GRIP_NAMES)
    positions, forces = [[], []], [[], []]
    for index, point in enumerate(data.contact):
        pair = [model.geom(int(n)).name for n in (point.geom1, point.geom2)]
        if "object_geom" not in pair:
            continue
        finger = next((k for k in pair if k in names), None)
        if finger is None:
            continue
        side = names.index(finger)
        force = np.zeros(6)
        mujoco.mj_contactForce(model, data, index, force)
        if force[0] <= 0:
            continue
        pos = (point.pos - data.geom("object_geom").xpos) @ data.geom("object_geom").xmat.reshape(
            3, 3
        )
        positions[side].append(pos.tolist())
        forces[side].append(
            [float(force[0]), float(np.linalg.norm(force[1:3])), float(point.friction[0])]
        )
    return positions, forces


def trajectory(job):
    out, name, d = job
    backend = physics.MuJoCoPhysicsBackend()
    history = []
    phase = "setup"
    errors = []
    closed = lifted = None
    original = None
    try:
        xyz = np.array([*d["center_mm"], 35.0]) * 0.001
        robot = physics.initialize(backend, xyz, d["yaw_deg"], 11252538, False)
        physics.set_diagnostic_arm(
            backend,
            robot,
            xyz + 0.001 * np.array([d[k] for k in ("x_mm", "y_mm", "z_offset_mm")]),
            tuple(np.asarray(d["fingers_mm"]) * 0.001),
        )

        def save(state):
            r = physics.snapshot(backend, state)
            points, forces = contacts(backend)
            body = backend._model.body("object").id
            r.update(
                phase=phase,
                points_object_m=points,
                forces_N_and_mu=forces,
                com_world_m=backend._data.xipos[body].tolist(),
            )
            history.append(r)
            if r["forbidden_pairs"]:
                raise ValueError("forbidden physical contact")
            if phase == "settle" and max(r["normal_force_N"]) > 0:
                raise ValueError("one or both open fingers already contact the object")

        phase = "settle"
        with backend.observe_physics_steps(save):
            save(backend.current_physics_observation())
            backend.step(60)
            original = history[-1]
            phase = "close"
            closed = robot.grasp("object", timeout_ms=1000)
            if closed.success:
                phase = "lift"
                lifted = robot.lift(
                    height_m=0.10, tcp_velocity=0.15, acceleration=0.5, timeout_ms=8000
                )
    except (ValueError, RuntimeError) as exc:
        errors.append(str(exc))
    finally:
        commands = list(backend.command_records)
        backend.shutdown()
    if original is None and history:
        original = history[-1]
    hold = [r for r in history if r["phase"] == "lift"][-120:]
    minimum = min((r["cube_bottom_m"] - original["cube_bottom_m"] for r in hold), default=0.0)
    forbidden = sum(bool(r["forbidden_pairs"]) for r in history)
    bilateral = len(hold) == 120 and all(min(r["normal_force_N"]) > 0 for r in hold)
    raw = out / (name + ".json.gz")
    physics.write(raw, history)
    physics.write(out / (name + "-commands.json.gz"), commands)
    return dict(
        id=name,
        design=d,
        eligible=bool(
            closed
            and closed.success
            and lifted
            and lifted.success
            and not errors
            and not forbidden
            and bilateral
            and minimum >= 0.05
        ),
        clip_sha256=physics.digest(raw),
        command_sha256=physics.digest(out / (name + "-commands.json.gz")),
        forbidden=forbidden,
        lower_hold_lift_m=minimum,
        last120_bilateral=bilateral,
        closed=closed.success if closed else False,
        lifted=lifted.success if lifted else False,
        error=errors,
        open_object_relative_tcp_m=original["xyz_error_object_m"] if original else None,
        opening_m=original["finger_joints_m"] if original else None,
        pose_before_grasp=original
        and {
            k: original[k]
            for k in [
                "cube_xyz_m",
                "cube_rotation",
                "wrist_rotation",
                "tcp_xyz_m",
                "finger_joints_m",
            ]
        },
        physical_steps=len(history),
    )


def run(design, out, jobs, groups):
    out.mkdir(parents=True, exist_ok=False)
    spec = json.loads(design.read_bytes())
    work = [
        (out, group + "-" + str(i).zfill(3), d)
        for group in groups
        for i, d in enumerate(spec[group + "_rows"])
    ]
    physics.write(
        out / "prospective.json",
        dict(
            design_sha256=physics.digest(design),
            driver_sha256=physics.digest(Path(__file__)),
            asset_sha256=physics.digest(physics.ROOT / physics.mount.ASSET_PATH),
            groups=groups,
            ids=[v[1] for v in work],
        ),
    )
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        results = []
        for row in pool.map(trajectory, work):
            physics.write(out / (row["id"] + "-result.json"), row)
            results.append(row)
            print(row["id"], row["eligible"], row["error"], flush=True)
    physics.write(
        out / "index.json", dict(prospective=physics.digest(out / "prospective.json"), rows=results)
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("design", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("groups", nargs="+", choices=("fit", "test", "negative"))
    options = parser.parse_args()
    run(options.design, options.out, options.jobs, options.groups)
