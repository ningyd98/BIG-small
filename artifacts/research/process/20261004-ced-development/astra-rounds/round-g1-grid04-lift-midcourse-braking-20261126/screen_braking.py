"""Bracket one grid-04 lift reference under original native physics and commands."""

import argparse
import hashlib
import importlib
import importlib.util
from collections import Counter, defaultdict
from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np
from numpy.polynomial import Polynomial
from scripts.graduation.g1_complete_cv_clearance import camera_encoder_pose
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry
from scripts.graduation.g1_complete_cv_payload import (
    AXES,
    PayloadClearance,
    object_matrix,
    positive_support,
    snapshot,
)
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import (
    GripperCommand,
    JointCommand,
    PhysicalScenarioConfig,
)
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.clearance_control import CartesianMotionReference
from cloud_edge_robot_arm.simulation.mujoco.motion_controller import _rotation_error

HERE = Path(__file__).resolve().parent
PLAN = read(HERE / "plan.json")
SETUP = PLAN["candidate"]
ENTRY = PLAN["baseline"]["entry_tick"]
ORIGINAL_END = PLAN["baseline"]["original_reject_tick"]
HZ, CONTROL, FEEDBACK = (SETUP[k] for k in ("hz", "control_ticks", "vision_ticks"))
LIMIT_V = SETUP["joint_velocity_limit_rad_s"]
LIMIT_A = SETUP["joint_acceleration_limit_rad_s2"]
PANDA = (
    "assets/robots/franka_panda/"
    "scene_g1_development_dual_id7_minusx130_id8_plusx130_end_wings_v1.xml"
)
FINGER_CONTACTS = {("left_finger_geom", "object_geom"), ("object_geom", "right_finger_geom")}
TABLE_CONTACT = ("object_geom", "table")
ROOTS = {"repo": ROOT, **{k: ROOT / v for k, v in PLAN["root_paths"].items()}}
OUT = ROOTS["output"]
ASSET = ROOTS["runtime"] / PANDA
EPS = 1e-10


def require(condition, message):
    if not condition:
        raise ValueError(message)


def deny_render(*args, **kwargs):
    raise AssertionError("this phase is CPU only")


def rooted(base, name):
    path = (base / name).resolve()
    require(path.is_relative_to(base.resolve()), f"foreign input path: {name}")
    return path


def verify_inputs():
    require(HERE.is_relative_to(ROOT), "wrong supplemental optical runtime")
    for key, expected in PLAN["hashes"].items():
        group, member = key.split("/", 1)
        require(sha(rooted(ROOTS[group], member)) == expected, f"input mismatch: {key}")
    runtime = ROOTS["runtime"]
    locked = read(runtime / "runtime-build.json")
    for name, expected in locked["runtime_files_sha256"].items():
        require(sha(rooted(runtime, name)) == expected, f"runtime mismatch: {name}")
    for module in ("backend", "clearance_control", "visual_servo", "skill_robot"):
        archive_origin = runtime / f"src/cloud_edge_robot_arm/simulation/mujoco/{module}.py"
        m = importlib.import_module(f"cloud_edge_robot_arm.simulation.mujoco.{module}")
        require(Path(m.__file__).resolve() == archive_origin.resolve(), f"wrong import: {module}")
    capture = read(ROOTS["parent"] / "seal.json")
    require(
        capture["registration_sha256"] == sha(ROOTS["parent"] / "registration.json"),
        "allocation lineage",
    )
    for name, expected in capture["sealed_sha256"].items():
        if name.startswith(PLAN["baseline"]["case"] + "/"):
            require(sha(rooted(ROOTS["parent"], name)) == expected, f"capture mismatch: {name}")


def round_tool(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def archived():
    raw = ROOTS["case"]
    receipt = read(raw / "sensor-receipt.json")
    index = pinned(raw / "rgbd-index.json", receipt["index_sha256"])
    require(index["episode_id"] == receipt["episode_id"], "case identity changed")
    labels = read(raw / "offline-physics.json")["frame_labels"]
    by_id = {x["frame_id"]: x for x in labels}
    samples = defaultdict(list)
    for entry in index["rows"]:
        robot = entry["robot"]
        label = by_id[robot["frame_id"]]
        require(
            label["checksum_sha256"] == robot["checksum_sha256"]
            and label["physics_step"] == robot["physics_step"],
            "old exposure and physical label do not join",
        )
        samples[robot["physics_step"], robot["native_last_command_seq"]].append((robot, label))
    commands = defaultdict(list)
    for record in read(raw / "native-commands.json"):
        require(record["episode_id"] == receipt["episode_id"], "old command episode differs")
        commands[record["physics_step"]].append(record)
    original = read(raw / "clearance-gate.json")["checks"]
    passed = {
        row["step"]: row
        for row in original
        if row["skill"] == "LIFT" and row["phase"] == "FEEDBACK"
    }
    require(
        len(passed) == 75
        and passed[ORIGINAL_END]["status"] == "BLOCKED"
        and all(row["status"] == "CLEAR" for tick, row in passed.items() if tick < ORIGINAL_END),
        "old 74+1 gate result changed",
    )
    reset, end = read(raw / "native-resets.json")
    require(
        (reset["phase"], end["phase"]) == ("BEGIN", "END")
        and reset["kind"] == end["kind"] == "RESET"
        and end["episode_id"] == receipt["episode_id"]
        and end["error"] is None
        and reset["parameters"] == end["parameters"],
        "wrong original reset operation",
    )
    config = reset["parameters"]["requested"].copy()
    for name in ("object_pose", "target_region_pose"):
        config[name] = Pose.model_validate(config[name])
    return samples, commands, passed, PhysicalScenarioConfig(**config)


def command_match(actual, original):
    require(
        {k: v for k, v in actual.items() if k != "episode_id"}
        == {k: v for k, v in original.items() if k != "episode_id"},
        f"original command {original['command_seq']} differs at {original['physics_step']}",
    )


def audit_samples(backend, samples, seen):
    d, m = backend._data, backend._model
    identity = (backend.total_physics_steps, len(backend.command_records))
    pose = d.geom("object_geom")
    robot_camera = camera_encoder_pose(m, d)
    row = backend.current_physics_observation()
    touching = sorted(sorted(p) for p in row.contact_pairs)
    for robot, label in samples.get(identity, ()):
        require(
            d.time == robot["sim_time_s"] == robot_camera["camera_encoder_sim_time_s"]
            and np.array_equal(d.qpos[:7], robot["joint_positions_rad"])
            and np.array_equal(d.qvel[:7], robot["joint_velocities_rad_s"])
            and np.array_equal(d.qpos[7:9], robot["finger_positions_m"])
            and np.array_equal(d.qvel[7:9], robot["finger_velocities_m_s"])
            and np.array_equal(
                robot_camera["camera_joint_positions_rad"], robot["camera_joint_positions_rad"]
            )
            and np.array_equal(
                robot_camera["camera_finger_positions_m"], robot["camera_finger_positions_m"]
            )
            and np.array_equal(pose.xpos, label["center_m"])
            and np.array_equal(pose.xmat.reshape(3, 3), label["rotation"])
            and touching == sorted(sorted(p) for p in label["touching"]),
            f"archived state or exact exposure buffer differs at {identity}",
        )
        h = robot.get("handoff")
        if h:
            require(
                np.array_equal(
                    d.ctrl, np.r_[h["effective_joint_target_rad"], h["effective_finger_target_m"]]
                ),
                f"archived applied ctrl differs at {identity}",
            )
        seen.add(robot["frame_id"])


def early_replay(backend, samples, commands, seen):
    for tick in range(ENTRY):
        audit_samples(backend, samples, seen)
        for old in commands.get(tick, ()):
            if old["type"] == "joint_target":
                backend.apply_joint_targets(JointCommand(positions=old["target_positions_rad"]))
            elif old["type"] == "gripper":
                backend.apply_gripper_command(GripperCommand(open=old["target_open"]))
            elif old["type"] == "hold_current_joints":
                backend.hold_current_joints()
            else:
                raise ValueError("unregistered early command kind")
            command_match(backend.command_records[-1], old)
            audit_samples(backend, samples, seen)
        require(backend.step(1).physics_steps == 1, "early steps differ")
    audit_samples(backend, samples, seen)


def polynomial_bounds(p):
    stationary = p.deriv().roots()
    arguments = [
        0.0,
        1.0,
        *(x.real for x in stationary if abs(x.imag) < 1e-10 and 0 <= x.real <= 1),
    ]
    values = p(np.array(arguments))
    return values.min(), values.max()


def schedule(z0, z1):
    t0 = SETUP["splice_relative_tick"] / HZ
    t1 = SETUP["zero_derivative_relative_tick"] / HZ
    te = SETUP["endpoint_relative_tick"] / HZ
    d = z1 - z0
    nominal = Polynomial([z0, 0, 0, 10 * d, -15 * d, 6 * d])
    u = t0 / 4
    dz = z0 + SETUP["midcourse_rise_m"]
    T = t1 - t0
    a = [nominal(u), nominal.deriv()(u) * T / 4, nominal.deriv(2)(u) * T * T / 32]
    extra = np.linalg.solve(
        [[1, 1, 1], [3, 4, 5], [6, 12, 20]],
        [dz - sum(a), -a[1] - 2 * a[2], -2 * a[2]],
    )
    brake = Polynomial(np.r_[a, extra])
    step = z1 - dz
    rise = Polynomial([dz, 0, 0, 10 * step, -15 * step, 6 * step])
    for curve, seconds in ((brake, T), (rise, te - t1)):
        vi = polynomial_bounds(curve.deriv() / seconds)
        ac = polynomial_bounds(curve.deriv(2) / (seconds * seconds))
        zone = polynomial_bounds(curve)
        require(
            vi[0] >= -EPS
            and vi[1] <= SETUP["command_tcp_velocity_m_s"]
            and max(abs(n) for n in ac) <= SETUP["command_tcp_acceleration_m_s2"]
            and zone[0] >= z0 - EPS
            and zone[1] <= z1 + EPS,
            "unqualified registered analytical segment",
        )

    def height(k):
        t = k / HZ
        return float(brake((t - t0) / T) if t <= t1 else rise(min(1.0, (t - t1) / (te - t1))))

    return height


def candidate_reference(backend, reference, path, quat):
    m = backend._model
    scratch = mujoco.MjData(m)
    z = schedule(path.start_m[2], path.target_m[2])
    start = SETUP["splice_relative_tick"] // CONTROL
    last = SETUP["endpoint_relative_tick"] // CONTROL
    anchors = list(reference.positions[: start + 1])
    q = anchors[-1].copy()
    lo, hi = m.jnt_range[:7].T
    site = m.site("tcp").id
    for k in range(start + 1, last + 4):
        pos = np.array([*path.start_m[:2], z(k * CONTROL)])
        for _ in range(50):
            scratch.qpos[:7] = q
            mujoco.mj_forward(m, scratch)
            error = np.r_[
                pos - scratch.site_xpos[site], 0.12 * _rotation_error(quat, scratch.site_xmat[site])
            ]
            if np.linalg.norm(error) < EPS:
                break
            jp, jr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
            mujoco.mj_jacSite(m, scratch, jp, jr, site)
            jac = np.vstack((jp[:, :7], 0.12 * jr[:, :7]))
            q = np.clip(
                q + jac.T @ np.linalg.solve(jac @ jac.T + 1e-10 * np.eye(6), error),
                lo + 0.001,
                hi - 0.001,
            )
        else:
            raise ValueError(f"candidate IK failed at reference {k}")
        anchors.append(q.copy())
    points = np.asarray(anchors)
    v = np.gradient(points, reference.control_dt, axis=0, edge_order=2)
    a = np.gradient(v, reference.control_dt, axis=0, edge_order=2)
    require(
        abs(v).max() <= LIMIT_V and abs(a).max() <= LIMIT_A,
        "candidate theoretical q/dq/ddq exceeds original limits",
    )
    bound = SETUP["unchanged_through_relative_tick_min"] // CONTROL
    arrays = (points, v, a)
    original = (reference.positions, reference.velocities, reference.accelerations)
    difference = [
        k
        for k in range(len(reference.positions))
        if any(not np.array_equal(x[k], y[k]) for x, y in zip(arrays, original, strict=True))
    ]
    require(
        difference
        and difference[0] > bound
        and reference.settle_s + last * CONTROL / HZ < SETUP["timeout_s"],
        "candidate changed the original prefix or its time contract",
    )
    reference.positions, reference.velocities, reference.accelerations = arrays
    reference.duration_s = last * CONTROL / HZ
    return {
        "first_changed_sample": difference[0],
        "first_changed_grid_tick": ENTRY + difference[0] * CONTROL,
        "maximum_joint_reference_speed_rad_s": float(abs(v).max()),
        "maximum_joint_reference_acceleration_rad_s2": float(abs(a).max()),
        "sha256": hashlib.sha256(b"".join(x.astype("<f8").tobytes() for x in arrays)).hexdigest(),
    }


def cloned(backend):
    names = (
        "_data",
        "_target_positions",
        "_total_physics_steps",
        "_gripper_open",
        "_command_records",
        "_last_contacts",
        "_estop_engaged",
        "_pending_joint_targets",
        "_sensor_frame",
        "_actuator_observer",
    )
    live = {n: getattr(backend, n) for n in names}
    b = live.copy()
    import copy

    b["_data"] = copy.copy(live["_data"])
    b["_target_positions"] = live["_target_positions"].copy()
    for n in ("_command_records", "_last_contacts", "_pending_joint_targets"):
        b[n] = list(live[n])
    require(
        not np.shares_memory(b["_data"].qpos, live["_data"].qpos)
        and all(
            np.array_equal(getattr(b["_data"], n), getattr(live["_data"], n))
            for n in ("qpos", "qvel", "ctrl", "qacc", "qM", "qfrc_bias", "qacc_warmstart")
        ),
        "inexact native branch clone",
    )
    return live, b


def restore(backend, values):
    for name, v in values.items():
        setattr(backend, name, v)


def check_mechanical(backend, path, peak_z):
    row = backend.current_physics_observation()
    pairs = {tuple(sorted(pair)) for pair in row.contact_pairs}
    require(
        not backend._pending_joint_targets and not backend.estop_engaged,
        "pending or stopped arm in moving reference",
    )
    require(
        np.isfinite(backend._data.qpos).all() and np.isfinite(backend._data.qvel).all(),
        "nonfinite native pose",
    )
    require(
        FINGER_CONTACTS <= pairs <= FINGER_CONTACTS | {TABLE_CONTACT},
        "lost native grasp or forbidden contact",
    )
    require(not any(c.illegal for c in backend.get_contacts()), "native illegal contact")
    path.check_position(row.tcp_position_m, peak_z=peak_z)
    lo, hi = backend._model.jnt_range[:7].T
    require(
        ((backend._data.qpos[:7] >= lo) & (backend._data.qpos[:7] <= hi)).all(),
        "physical joint limit",
    )
    return row


def shadow(backend, path, reference, endpoint, observe, audit_after=None):
    dt = CONTROL * backend._config.physics_dt_s
    state = backend.get_joint_command_state()
    position = np.array(state.positions_rad if state.retained_target else backend._data.qpos[:7])
    velocity = np.array(state.velocity_rad_s if state.retained_target else np.zeros(7))
    elapsed_hold = backend.get_sim_time() - state.sim_time_s
    reaffirm = state.retained_target and elapsed_hold > 1e-9
    require(
        elapsed_hold >= -1e-9 and abs(velocity).max() <= LIMIT_V + 1e-8, "invalid retained command"
    )
    if reaffirm:
        require(
            abs(velocity).max() <= LIMIT_A * elapsed_hold + 1e-8, "cannot settle previous drive"
        )
        velocity[:] = 0
    next_control = CONTROL if state.retained_target and not reaffirm else 0
    peak_z = path.start_m[2]
    for offset in range(endpoint + 1):
        tick = ENTRY + offset
        row = check_mechanical(backend, path, peak_z)
        peak_z = max(peak_z, row.tcp_position_m[2])
        observe(tick, row)
        if offset == endpoint:
            break
        if offset == next_control:
            goal = reference.joint_target(offset, CONTROL)
            if not reaffirm:
                needed = np.clip((goal - position) / dt, -LIMIT_V, LIMIT_V)
                velocity += np.clip(needed - velocity, -LIMIT_A * dt, LIMIT_A * dt)
                position += velocity * dt
            reaffirm = False
            lo, hi = backend._model.jnt_range[:7].T
            require(
                ((position >= lo + 0.001) & (position <= hi - 0.001)).all(),
                "grid target outside physical admissibility",
            )
            backend.apply_joint_targets(
                JointCommand(positions=position.tolist(), max_velocity=LIMIT_V)
            )
            if audit_after:
                audit_after(tick)
            next_control += CONTROL
        require(backend.step(1).physics_steps == 1, "off-grid movement")
        reference.observe_step()


def stop_trace(backend, tick, output):
    live, state = cloned(backend)
    restore(backend, state)
    backend._actuator_observer = None
    states, rates, contacts = [], [], []
    try:
        command_count = len(backend.command_records)
        backend.emergency_stop()
        require(
            [c["type"] for c in backend.command_records[command_count:]]
            == ["hold_current_joints", "emergency_stop"]
            and np.array_equal(backend._target_positions, backend._data.qpos[:7])
            and not backend._pending_joint_targets
            and not backend._gripper_open,
            "unexpected native stop contract",
        )
        for k in range(241):
            d = backend._data
            states.append(d.qpos.copy())
            rates.append(d.qvel.copy())
            pair = {tuple(sorted(p)) for p in backend.current_physics_observation().contact_pairs}
            contacts.append(sorted(pair))
            if k < 240:
                require(backend.step(1).physics_steps == 1, "off-grid native emergency stop")
    finally:
        restore(backend, live)
    q, dq = np.asarray(states), np.asarray(rates)
    with (output / f"stop-{tick}.npz").open("xb") as f:
        np.savez_compressed(f, q=q, dq=dq)
    write(output / f"stop-{tick}.json", contacts)
    return q, dq, contacts


def stop_margins(guard, tick, archive, bounds, source, anchor):
    q, dq, contacts = archive
    p, v, r, rv = snapshot(guard.motion, q, dq, q[:, 9:12], object_matrix(q))
    world = positive_support(p, v, anchor[0], AXES)
    relative = positive_support(r, rv, anchor[1], guard.axes)
    W, R = bounds
    reserve = W - world
    rp = R - relative
    i, j = np.unravel_index(reserve.argmin(), reserve.shape)
    result = {
        "stop_tick": tick,
        "source_profile_bound": source,
        "worst_world_margin_m": float(reserve[i, j]),
        "world_part": guard.motion.names[i],
        "world_axis": AXES[j].tolist(),
        "worst_relative_margin_m": float(rp.min()),
        "workpiece_ID8_down_mm": float(
            world[guard.motion.names.index("g1_dual_id8_plate"), 5] * 1000
        ),
        "first_table_contact": next(
            (k for k, pairs in enumerate(contacts) if TABLE_CONTACT in pairs), None
        ),
        "first_invalid_contact": next(
            (
                k
                for k, pairs in enumerate(contacts)
                if not FINGER_CONTACTS
                <= set(pairs)
                <= FINGER_CONTACTS | ({TABLE_CONTACT} if source is not None else set())
            ),
            None,
        ),
    }
    return result


def run(folder):
    samples, commands, clear, scenario = archived()
    step_counts = Counter()

    def counted(model, d):
        step_counts["integrations"] += 1
        require(
            step_counts["integrations"] <= PLAN["budget"]["maximum_CPU_ticks"],
            "CPU integration cap",
        )
        return step_impl(model, d)

    backend = MuJoCoPhysicsBackend()
    step_impl = mujoco.mj_step
    (ROOTS["output"] / folder.name).mkdir(exist_ok=False)
    render_free = round_tool(
        ROOTS["rounds"] / "round-g1-release-terminal-rebound-20261125/terminal_rebound.py"
    ).render_free
    with patch.multiple(mujoco, Renderer=deny_render, mjr_render=deny_render, mj_step=counted):
        backend.initialize(
            SimulatorConfig(
                model_path=str(ASSET),
                seed=scenario.seed,
                physics_dt_s=1 / HZ,
                render_rgb=True,
                render_depth=True,
                domain_randomization=False,
                camera_width=320,
                camera_height=240,
            )
        )
        with render_free(backend, backend.shutdown):
            backend.reset(scenario)
            seen = set()
            early_replay(backend, samples, commands, seen)
            require(
                len(backend.command_records) == 236 and backend.total_physics_steps == ENTRY,
                "wrong common entry",
            )
            start = tuple(backend.current_physics_observation().tcp_position_m)
            path = VerticalClearancePath(
                task_id=PLAN["baseline"]["case"],
                step_id="LIFT",
                skill="LIFT",
                start_m=start,
                target_m=(*start[:2], SETUP["grounded_endpoint_world_z_m"]),
                minimum_height_m=0.08,
            )
            quat = np.empty(4)
            mujoco.mju_mat2Quat(quat, backend._data.site("tcp").xmat)

            def make_ref():
                return CartesianMotionReference(
                    backend,
                    path.start_m,
                    path.target_m,
                    quat,
                    control_steps=CONTROL,
                    timeout_s=SETUP["timeout_s"],
                    max_velocity=LIMIT_V,
                    max_acceleration=LIMIT_A,
                )

            _, saved = cloned(backend)
            original = make_ref()
            chosen = make_ref()
            params = candidate_reference(backend, chosen, path, quat)
            write(folder / "preflight.json", params)
            states = {}
            actual_ctrl = {}

            def monitor_old(tick, row):
                audit_samples(backend, samples, seen)
                states[tick] = np.r_[backend._data.qpos, backend._data.qvel].tolist()

            def audit_command(tick):
                require(len(commands[tick]) == 1, "unexpected old command group")
                command_match(backend.command_records[-1], commands[tick][0])

            def audit_drive(event):
                actual_ctrl[event.physics_step - 1] = backend._data.ctrl.tolist()

            with backend.observe_actuator_steps(audit_drive):
                shadow(
                    backend,
                    path,
                    original,
                    ORIGINAL_END - ENTRY,
                    monitor_old,
                    audit_after=audit_command,
                )
            require(
                len(backend.command_records) == 355
                and len(actual_ctrl) == 592
                and len(seen) == sum(map(len, samples.values())),
                "original sealed feedback or applied command coverage is incomplete",
            )
            write(
                folder / "baseline.json",
                {
                    "archived_exposure_matches": len(seen),
                    "last_pre_refusal_command_seq": len(backend.command_records),
                    "old_applied_ctrl_digest": sha_array(list(actual_ctrl.values())),
                    "original_target": list(path.target_m),
                },
            )
            restore(backend, saved)
            guard = PayloadClearance(
                MotionGeometry(Model(ASSET)),
                read(ROOT / "scripts/graduation/g1_complete_cv_payload_profile.json"),
                read(ROOT / "scripts/graduation/g1_complete_cv_source_motion_profile.json"),
            )
            deltas = {}
            candidate_rows = []
            stop_results = []
            window_anchors = []
            original_entries = {t for t, v in clear.items() if v["status"] == "CLEAR"}
            read_dir = folder / "stops"
            read_dir.mkdir()

            def candidate_audit(tick):
                if tick < ORIGINAL_END and "first_actual_command_difference" not in deltas:
                    if (
                        backend.command_records[-1]["target_positions_rad"]
                        != commands[tick][0]["target_positions_rad"]
                    ):
                        deltas["first_actual_command_difference"] = tick

            def candidate_drive(event):
                k = event.physics_step - 1
                if (
                    k in actual_ctrl
                    and "first_actual_ctrl_difference" not in deltas
                    and backend._data.ctrl.tolist() != actual_ctrl[k]
                ):
                    deltas["first_actual_ctrl_difference"] = k

            def observe(tick, row):
                d = backend._data
                q = np.r_[d.qpos, d.qvel].tolist()
                if tick in states and q != states[tick] and "first_state_difference" not in deltas:
                    deltas["first_state_difference"] = tick
                if (tick - ENTRY) % FEEDBACK == 0:
                    common = (
                        tick in original_entries
                        and "first_state_difference" not in deltas
                        and "first_actual_ctrl_difference" not in deltas
                    )
                    if common and tick != ENTRY:
                        data = clear[tick]["current"]["short_motion"]
                        speed_class = data.get("speed_class")
                        registered_source = data.get("registered_source_speed_class")
                        stage = guard.data["LIFT"]["classes"][speed_class]
                        world = (
                            guard.source_classes[registered_source][0]
                            if registered_source is not None
                            else stage["world"]
                        )
                        p, _, r, _ = snapshot(
                            guard.motion,
                            d.qpos[None],
                            d.qvel[None],
                            d.qpos[None, 9:12],
                            object_matrix(d.qpos[None]),
                        )
                        window_anchors.append(
                            (
                                tick,
                                (world, stage["relative"]),
                                registered_source,
                                (p[0], r[0]),
                            )
                        )
                    elif not common:
                        deltas.setdefault(
                            "first_feedback_without_authenticated_candidate_optics", tick
                        )
                candidate_rows.append(
                    {
                        "tick": tick,
                        "tcp_m": list(row.tcp_position_m),
                        "cube_m": list(row.object_geom_position_m),
                        "q": d.qpos.tolist(),
                        "dq": d.qvel.tolist(),
                        "ctrl": d.ctrl.tolist(),
                    }
                )
                window_anchors[:] = [a for a in window_anchors if tick - a[0] <= 8]
                if window_anchors:
                    archive = stop_trace(backend, tick, read_dir)
                    for at, limits, src, anchor in window_anchors:
                        summary = stop_margins(guard, tick, archive, limits, src, anchor)
                        summary["feedback_tick"] = at
                        stop_results.append(summary)
                        require(
                            summary["worst_world_margin_m"] >= 0
                            and summary["worst_relative_margin_m"] >= 0
                            and summary["first_invalid_contact"] is None,
                            f"stop envelope undercoverage at feedback {at}, trigger {tick}",
                        )

            result = {"status": "MECHANICAL_REFERENCE_COMPLETE"}
            with backend.observe_actuator_steps(candidate_drive):
                try:
                    shadow(
                        backend,
                        path,
                        chosen,
                        SETUP["endpoint_relative_tick"],
                        observe,
                        audit_after=candidate_audit,
                    )
                except ValueError as error:
                    result = {"status": "CPU_STOPPED", "reason": str(error)}
            result.update(
                divergence=deltas,
                steps=step_counts["integrations"],
                last_step=backend.total_physics_steps,
                stop_count=len({s["stop_tick"] for s in stop_results}),
                initial_handoff_stop_coverage="NOT_SCORED_SEPARATE_PAIR_PROFILE",
                authenticated_online_training_runs=0,
                qualification=False,
                optical_and_time_accepted=False,
                terminal_TCP_m=list(backend.current_physics_observation().tcp_position_m),
                terminal_workpiece_m=list(
                    backend.current_physics_observation().object_geom_position_m
                ),
            )
            write(folder / "candidate-trace.json", candidate_rows)
            write(folder / "interchange.json", {"result": result, "stops": stop_results})


def sha_array(values):
    return hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest()


def cold(folder, reader):
    result = read(folder / "interchange.json")
    trace = read(folder / "candidate-trace.json")
    require(
        [x["tick"] for x in trace] == list(range(ENTRY, ENTRY + len(trace))),
        "nonconsecutive shadow evidence",
    )
    require(
        len(trace) > 0 and result["result"]["steps"] <= PLAN["budget"]["maximum_CPU_ticks"],
        "missing trace or overbudget",
    )
    start = trace[0]
    last = trace[-1]
    rise = np.array([x["cube_m"][2] - start["cube_m"][2] for x in trace])
    lateral = np.linalg.norm(np.array([x["tcp_m"][:2] for x in trace]) - start["tcp_m"][:2], axis=1)
    stops = result["stops"]
    require(
        len({s["stop_tick"] for s in stops}) == len(list((folder / "stops").glob("*.npz"))),
        "missing recorded stop states",
    )
    write(
        folder / f"{reader}.json",
        {
            "bound_inputs": {
                p.name: sha(p)
                for p in (
                    folder / "preflight.json",
                    folder / "baseline.json",
                    folder / "candidate-trace.json",
                    folder / "interchange.json",
                )
            },
            "last_sample": last["tick"],
            "max_lateral_m": float(lateral.max()),
            "end_cube_lift_m": float(rise[-1]),
            "max_cube_lift_m": float(rise.max()),
            "native_result": result,
            "source_sha256": sha(Path(__file__)),
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "read"))
    parser.add_argument("--attempt", default="cpu-01", choices=("cpu-01", "cpu-02", "cpu-03"))
    parser.add_argument("--reader", choices=("reader-1", "reader-2"))
    args = parser.parse_args()
    verify_inputs()
    OUT.mkdir(exist_ok=True)
    dest = OUT / args.attempt
    if args.mode == "run":
        try:
            run(dest)
        except BaseException as error:
            dest.mkdir(exist_ok=True)
            write(dest / "failure.json", {"reason": str(error), "type": type(error).__name__})
            raise
    else:
        cold(dest, args.reader)
