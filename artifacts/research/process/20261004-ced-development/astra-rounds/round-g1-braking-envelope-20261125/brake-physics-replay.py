"""Offline empirical full-state branching with the registered native MuJoCo backend."""

from __future__ import annotations

import argparse
import collections
import hashlib
import itertools
import json
import math
from pathlib import Path

import mujoco
import numpy as np

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import JointCommand, PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco import backend as native
from cloud_edge_robot_arm.simulation.mujoco.motion_controller import MuJoCoMotionController
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD

HERE = Path(__file__).resolve().parent
DT = 1 / 240
STATE = mujoco.mjtState.mjSTATE_INTEGRATION
NAMES = (
    "base",
    *(f"link{i}" for i in range(1, 7)),
    "hand",
    "left_finger_geom",
    "right_finger_geom",
    "object_geom",
    *(f"g1_dual_id{i}_{part}" for i in (7, 8) for part in ("plate", "crossbar", "upright")),
    "table",
)
PAIR_NAMES = tuple(itertools.product(NAMES[7:10], NAMES[10:]))
TARGET_PAIR = ("left_finger_geom", "g1_dual_id8_plate")
SIGNS = np.array(list(itertools.product((-1, 1), repeat=3)))


def read(path):
    return json.loads(path.read_bytes())


def write(path, obj):
    with path.open("x") as f:
        json.dump(obj, f, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def init(xml, row, allocation):
    b = native.MuJoCoPhysicsBackend()
    c = allocation.get("case", {})
    b.initialize(SimulatorConfig(model_path=str(xml), physics_dt_s=DT, domain_randomization=False))
    x, y, z = row["object_position_m"]
    rot = row["object_geom_rotation_row_major"]
    b.reset(
        PhysicalScenarioConfig(
            scenario_id="S01_NORMAL_STATIC",
            seed=c.get("seed", 22),
            object_pose=Pose(x=x, y=y, z=z),
            object_mass_kg=float(b._model.body("object").mass[0]),
            object_yaw_rad=math.atan2(rot[3], rot[0]),
        )
    )
    b._data.qpos[:7] = row["joint_positions_rad"]
    b._data.qpos[7:9] = row["finger_positions_m"]
    b._target_positions = np.asarray(row["joint_positions_rad"]).copy()
    mujoco.mj_forward(b._model, b._data)
    return b


def pack(b):
    state = np.empty(mujoco.mj_stateSize(b._model, STATE))
    mujoco.mj_getState(b._model, b._data, state, STATE)
    if b._pending_joint_targets:
        raise ValueError(
            "selected course has delayed controls; serialize and restore the queue first"
        )
    return state, b._target_positions.copy(), b._gripper_open, b.total_physics_steps


def restore(b, checkpoint):
    packed, targets, opened, step = checkpoint
    mujoco.mj_setState(b._model, b._data, packed, STATE)
    mujoco.mj_forward(b._model, b._data)
    mujoco.mj_setState(b._model, b._data, packed, STATE)
    b._target_positions = targets.copy()
    b._gripper_open = opened
    b._total_physics_steps = step
    b._estop_engaged = False
    b._command_records.clear()


def actuate(b, cmd):
    if not cmd["accepted"]:
        return
    kind = cmd["type"]
    if kind == "joint_target":
        b.apply_joint_targets(JointCommand(positions=cmd["target_positions_rad"]))
    elif kind == "hold_current_joints":
        b.hold_current_joints()
    else:
        raise ValueError(f"unexpected preterminal command {kind}")


class Scene:
    def __init__(self, model):
        self.model = model
        self.scratch = mujoco.MjData(model)
        self.ids = np.array([model.geom(x).id for x in NAMES])
        halves = []
        for i in self.ids:
            g = model.geom(i)
            if g.type[0] == mujoco.mjtGeom.mjGEOM_BOX:
                halves.append(g.size.copy())
            elif g.type[0] == mujoco.mjtGeom.mjGEOM_CAPSULE:
                halves.append([g.size[0], g.size[0], g.size[0] + g.size[1]])
            elif g.type[0] == mujoco.mjtGeom.mjGEOM_CYLINDER:
                halves.append([g.size[0], g.size[0], g.size[1]])
            else:
                raise ValueError("unregistered shape " + g.name)
        self.half = np.array(halves)
        self.local = self.half[:, None, :] * SIGNS
        self.ij = np.array([(NAMES.index(a), NAMES.index(b)) for a, b in PAIR_NAMES]).T
        self.pair_geom_ids = self.ids[self.ij].T
        self.all_names = [model.geom(i).name for i in range(model.ngeom)]

    def sample(self, b):
        # Consistent post-integration FK on a dedicated scratch model state. The live solver
        # records its integration contacts before advancing q, so store both contact lists.
        data = b._data
        d = self.scratch
        d.qpos[:] = data.qpos
        d.qvel[:] = data.qvel
        mujoco.mj_fwdPosition(self.model, d)
        r = d.geom_xmat[self.ids].reshape(-1, 3, 3)
        g = d.geom_xpos[self.ids]
        vertices = g[:, None, :] + self.local @ r.transpose(0, 2, 1)
        a, c = self.ij
        ra, rc = r[a].transpose(0, 2, 1), r[c].transpose(0, 2, 1)
        cross = np.cross(ra[:, :, None, :], rc[:, None, :, :]).reshape(-1, 9, 3)
        axes = np.concatenate((ra, rc, cross), axis=1)
        lengths = np.linalg.norm(axes, axis=2)
        axes = axes / np.where(lengths > 1e-10, lengths, 1)[:, :, None]
        delta = g[c] - g[a]
        centers = np.einsum("pki,pi->pk", axes, delta)
        radius = np.einsum("pki,pi->pk", abs(axes @ r[a]), self.half[a])
        radius += np.einsum("pki,pi->pk", abs(axes @ r[c]), self.half[c])
        projected = abs(centers) - radius
        projected[lengths < 1e-10] = -np.inf
        active = np.argmax(projected, axis=1)
        sat_gap = projected[np.arange(len(a)), active]
        separating_axis = (
            axes[np.arange(len(a)), active] * np.sign(centers[np.arange(len(a)), active])[:, None]
        )
        raw_gap = np.array(
            [
                mujoco.mj_geomDistance(self.model, d, int(i), int(j), 2.0, None)
                for i, j in self.pair_geom_ids
            ]
        )
        # mj_geomDistance can return exact zero for separated boxes. A strictly positive
        # certified SAT witness then gives a conservative geometric separation.
        gap = np.where((raw_gap == 0) & (sat_gap > 0), sat_gap, raw_gap)
        xyz_radius = abs(r[a]) @ self.half[a, :, None] + abs(r[c]) @ self.half[c, :, None]
        xyz_support = np.stack((delta - xyz_radius[:, :, 0], -delta - xyz_radius[:, :, 0]), axis=1)
        tcp = d.site("tcp")
        wrist = tcp.xmat.reshape(3, 3)
        rel = np.column_stack((wrist.T @ r[10], wrist.T @ (g[10] - tcp.xpos)))
        contacts = []
        for epoch, source in enumerate((data, d)):
            for co in source.contact:
                contacts.append([epoch, int(co.geom1), int(co.geom2), float(co.dist)])
        return dict(
            q=data.qpos.copy(),
            qvel=data.qvel.copy(),
            ctrl=data.ctrl.copy(),
            command_q=b._target_positions.copy(),
            points=vertices,
            centers=g.copy(),
            rotation=r.copy(),
            tcp=tcp.xpos.copy(),
            tcp_rotation=wrist.copy(),
            cube_in_tcp=rel,
            engine_gap=raw_gap,
            pair_gap=gap,
            sat_gap=sat_gap,
            sat_axis=separating_axis,
            xyz_directed_gap=xyz_support,
        ), contacts


def compare(b, row, residual):
    d = b._data
    checks = dict(
        q=(d.qpos[:7], row["joint_positions_rad"]),
        qvel=(d.qvel[:7], row["joint_velocities_rad_s"]),
        fingers=(d.qpos[7:9], row["finger_positions_m"]),
        finger_vel=(d.qvel[7:9], row["finger_velocities_m_s"]),
        tcp=(d.site("tcp").xpos, row["tcp_position_m"]),
        cube=(d.geom("object_geom").xpos, row["object_geom_position_m"]),
        cube_rotation=(d.geom("object_geom").xmat, row["object_geom_rotation_row_major"]),
        cube_vel=(d.qvel[9:12], row["object_linear_velocity_m_s"]),
        cube_omega=(d.qvel[12:15], row["object_angular_velocity_rad_s"]),
        clock=(float(d.time), row["sim_time_s"]),
    )
    for key, (v, u) in checks.items():
        residual[key] = max(residual.get(key, 0.0), float(np.max(abs(np.asarray(v) - u))))


def native_next(b, goal, previous, velocity, limits):
    dt = 5 * DT
    vmax, amax = limits["max_velocity_rad_s"], limits["max_acceleration_rad_s2"]
    desired = np.clip((goal - previous) / dt, -vmax, vmax)
    velocity = velocity + np.clip(desired - velocity, -amax * dt, amax * dt)
    command = previous + velocity * dt
    b.apply_joint_targets(JointCommand(positions=command.tolist(), max_velocity=vmax))
    return command, velocity


def trajectory(b, scene, rows, commands, case, mode, local, limits):
    originals = collections.defaultdict(list)
    for cmd in commands:
        originals[cmd["physics_step"]].append(cmd)
    last = max(case["anchors"]) + 8
    terminal = len(rows) - 1
    needed = {a + j for a in case["anchors"] for j in range(9)}
    checkpoints, normal, normal_contacts, checks = {}, {}, {}, {}
    cmd_state = np.asarray(rows[0]["joint_positions_rad"])
    cmd_velocity = np.zeros(7)
    previous_cmd, previous_time = None, None
    records = []
    undefined_velocity_steps = []
    for step in range(last + 1):
        if step <= terminal:
            if step != rows[step]["physics_step"] or b.total_physics_steps != step:
                raise ValueError("nonuniform native tick")
            compare(b, rows[step], checks)
            comparisons = [("command_q", b._target_positions, cmd_state)]
            try:
                handoff = b.get_joint_command_state()
            except ValueError as e:
                if str(e) != "joint command handoff has conflicting targets at one time":
                    raise
                # Two native accepted targets at the same timestamp have no finite sent
                # derivative. Confirm the archived equal-time records have the same conflict.
                if previous_time is None or not any(
                    len([c for c in seq if c["accepted"]]) > 1
                    and seq[-1]["sim_time_s"] == previous_time
                    for seq in originals.values()
                ):
                    raise
                undefined_velocity_steps.append(step)
            else:
                comparisons.append(("command_velocity", handoff.velocity_rad_s, cmd_velocity))
            for key, measured, expected in comparisons:
                diff = float(np.max(abs(np.asarray(measured) - expected)))
                checks[key] = max(checks.get(key, 0.0), diff)
        if step in needed:
            checkpoints[step] = pack(b)
            normal[step], normal_contacts[step] = scene.sample(b)
        if step == last:
            break
        if mode == "last_valid_fixed_wrist" and step == 1128:
            last_valid = next(
                r for r in local["rows"] if r["physics_step"] == 1128 and r["status"] == "CLEAR"
            )
            goal = MuJoCoMotionController(b)._inverse_kinematics(
                np.array([last_valid["target_xyz"][k] for k in "xyz"]),
                np.asarray(_DOWNWARD),
                b._model.site("tcp").id,
            )
            if goal is None:
                raise ValueError("last passed native IK unavailable")
        if step < terminal:
            for c in originals[step]:
                if not c["accepted"]:
                    continue
                if mode == "last_valid_fixed_wrist" and step == 1132:
                    # Reproduce the already archived in-grid target first, as an independent
                    # check of the continuation equation before using the counterfactual.
                    candidate_b = b.get_joint_command_state()
                    prev = np.asarray(candidate_b.positions_rad)
                    vel = np.asarray(candidate_b.velocity_rad_s)
                    command, velocity = native_next(b, goal, prev, vel, limits)
                    checks["control_grid_validation"] = float(
                        max(abs(command - c["applied_target_positions_rad"]))
                    )
                else:
                    actuate(b, c)
                cmd_state = np.asarray(c["applied_target_positions_rad"])
                timestamp = c["sim_time_s"]
                cmd_velocity = np.zeros(7)
                if (
                    c["type"] == "joint_target"
                    and previous_cmd is not None
                    and timestamp > previous_time
                ):
                    cmd_velocity = (cmd_state - previous_cmd) / (timestamp - previous_time)
                previous_cmd, previous_time = cmd_state, timestamp
        elif mode == "last_valid_fixed_wrist" and (step - 1132) % 5 == 0:
            command, velocity = native_next(b, goal, command, velocity, limits)
            records.append(
                dict(step=step, command_q=command.tolist(), command_velocity=velocity.tolist())
            )
        b.step(1)
    return checkpoints, normal, normal_contacts, checks, records, undefined_velocity_steps


def stack(samples):
    return {k: np.stack([s[k] for s in samples]) for k in samples[0]}


def summarize(window, contacts, scene, normal0, first_stop):
    group_names = ("arm_links", "hand", "fingers", "assembly")
    spans = (slice(0, 7), slice(7, 8), slice(8, 10), slice(10, 17))
    result = {}
    for end in (1, 8, 240):
        w = slice(0, end + 1)
        motion = np.linalg.norm(window["points"][w] - window["points"][0], axis=-1)
        peak = {
            name: float(motion[:, idx].max()) for name, idx in zip(group_names, spans, strict=True)
        }
        i = PAIR_NAMES.index(TARGET_PAIR)
        gaps = window["pair_gap"][w]
        mins = np.unravel_index(np.argmin(gaps), gaps.shape)
        result[str(end)] = dict(
            minimum_pair=list(PAIR_NAMES[mins[1]]),
            minimum_gap=float(gaps[mins]),
            minimum_step=int(mins[0]),
            left_id8_min=float(gaps[:, i].min()),
            peak_corner_displacement_m=peak,
            max_tcp_displacement_m=float(
                np.linalg.norm(window["tcp"][w] - window["tcp"][0], axis=1).max()
            ),
            max_cube_displacement_m=float(
                np.linalg.norm(window["centers"][w, 10] - window["centers"][0, 10], axis=1).max()
            ),
            max_cube_in_tcp_displacement_m=float(
                np.linalg.norm(
                    window["cube_in_tcp"][w, :, -1] - window["cube_in_tcp"][0, :, -1], axis=1
                ).max()
            ),
            max_relative_finger1_id8_center_change_m=float(
                np.linalg.norm(
                    (window["centers"][w, 14] - window["centers"][w, 8])
                    - (normal0["centers"][14] - normal0["centers"][8]),
                    axis=1,
                ).max()
            ),
        )
    forbidden = set()
    for tick, (_, entries) in enumerate(contacts):
        for epoch, a, b, _dist in entries:
            pair = tuple(sorted((scene.all_names[a], scene.all_names[b])))
            if pair != ("object_geom", "table"):
                forbidden.add((tick, epoch, pair))
    return dict(
        brake_start=first_stop,
        windows=result,
        stop_gap_m=window["pair_gap"][0].tolist(),
        min_gap_m=window["pair_gap"].min(axis=0).tolist(),
        forbidden_pairs=sorted(set("/".join(pair) for _, _, pair in forbidden)),
        forbidden_contact_rows=len(forbidden),
        first_forbidden_tick=min((tick for tick, _, _ in forbidden), default=None),
    )


def run_case(root, runtime, current_xml, reg, case, mode, out):
    d = root / case["directory"]
    for file, wanted in case["input_sha256"].items():
        if sha(root / file) != wanted:
            raise ValueError("original file drift " + file)
    tr = read(d / "instance/offline-truth.json")
    rows, commands = tr["samples"], read(d / "instance/backend-commands.json")
    alloc = read(d / "allocation.json")
    local = (
        read(d / "instance/local-clearance.json")
        if (d / "instance/local-clearance.json").exists()
        else None
    )
    xml = current_xml
    if case["xml_mode"] == "original" and tr["asset_sha256"] != sha(xml):
        xml = next(p for p in current_xml.parent.glob("*.xml") if sha(p) == tr["asset_sha256"])
    b = init(xml, rows[0], alloc)
    try:
        scene = Scene(b._model)
        checkpoints, normal, normal_contacts, residual, generated, undefined_velocity = trajectory(
            b, scene, rows, commands, case, mode, local, reg["fixed_control_limits"]
        )
    finally:
        b.shutdown()
    reference = case["xml_mode"] == "original"
    if reference and max(residual.values()) > 1e-6:
        raise ValueError(f"original state mismatch {case['name']} {residual}")
    name = case["name"] + "-" + mode
    dest = out / name
    dest.mkdir(exist_ok=False)
    steps = sorted(checkpoints)
    np.savez_compressed(dest / "normal-prefix.npz", step=steps, **stack([normal[j] for j in steps]))
    b = init(xml, rows[0], alloc)
    unique = []
    try:
        scene = Scene(b._model)
        for step in steps:
            restore(b, checkpoints[step])
            b.emergency_stop()
            if [r["type"] for r in b.command_records] != ["hold_current_joints", "emergency_stop"]:
                raise ValueError("original emergency_stop failed to log the native hold")
            obs, contactlog = [], []
            for j in range(241):
                snap, contacts = scene.sample(b)
                obs.append(snap)
                contactlog.append([j, contacts])
                if j < 240:
                    b.step(1)
            data = stack(obs)
            window = dest / f"stop-{step}.npz"
            np.savez_compressed(window, **data)
            write(dest / f"contacts-{step}.json", contactlog)
            unique.append(summarize(data, contactlog, scene, normal[step], step))
    finally:
        b.shutdown()
    write(dest / "normal-contacts.json", {str(j): normal_contacts[j] for j in steps})
    anchors = {str(n): [n + j for j in range(9)] for n in case["anchors"]}
    meta = dict(
        name=name,
        role=case["whole_trajectory_role"],
        reference_match_required=reference,
        xml=str(xml.relative_to(runtime)),
        xml_sha256=sha(xml),
        rows=len(rows),
        original_terminal=len(rows) - 1,
        maximum_absolute_original_replay_residual=residual,
        t01_controlled_extension=generated,
        named_geometries=list(NAMES),
        named_pairs=PAIR_NAMES,
        model_contact_names=scene.all_names,
        anchor_to_native_stop_steps=anchors,
        unique_stops=unique,
        held_payload=False,
        geometry_notes=(
            "Eight vertices of each local box (capsules/cylinder use enclosing box for "
            "vertices only). 24 exact physical hand/finger/assembly/table signed pair "
            "queries, independent OBB SAT and signed +/- world-axis gaps for those "
            "boxes. Original solver contact and same-instant FK contact are both "
            "retained. Payload is on table in these approach runs."
        ),
    )
    if undefined_velocity:
        meta["sent_velocity_native_equal_timestamp_undefined"] = undefined_velocity
    write(dest / "results.json", meta)
    print(
        name,
        "reference",
        max(residual.values()),
        "gap_id8",
        min(w["windows"]["240"]["left_id8_min"] for w in unique),
        "forbidden",
        sum(w["forbidden_contact_rows"] > 0 for w in unique),
        flush=True,
    )
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--case", required=True)
    args = ap.parse_args()
    root = args.root.resolve()
    reg = read(HERE / "brake-physics-preregistration.json")
    if sha(HERE / "plan.json") != reg["plan_sha256"]:
        raise ValueError("unregistered plan")
    runtime = root / reg["frozen_runtime"]
    if not Path(native.__file__).resolve().is_relative_to(runtime) or mujoco.__version__ != "3.3.7":
        raise ValueError("native backend did not originate from the registered runtime")
    xml = runtime / reg["current_asset"]
    if sha(xml) != reg["current_asset_sha256"]:
        raise ValueError("current assembly drift")
    args.out.mkdir(parents=True, exist_ok=True)
    case = next(c for c in reg["cases"] if c["name"] == args.case)
    modes = (
        ("archived_or_retained", "last_valid_fixed_wrist") if args.case == "t01" else ("archived",)
    )
    for mode in modes:
        run_case(root, runtime, xml, reg, case, mode, args.out)


if __name__ == "__main__":
    main()
