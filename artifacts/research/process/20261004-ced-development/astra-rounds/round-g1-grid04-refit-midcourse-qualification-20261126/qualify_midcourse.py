"""Mechanical screening of the single grid-04 candidate with challenged source bounds."""

import argparse
import gzip
import hashlib
import importlib.util
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np
from scripts.graduation.g1_complete_cv_geometry import Box, Model
from scripts.graduation.g1_complete_cv_handoff import handoff_motion
from scripts.graduation.g1_complete_cv_motion import MotionGeometry
from scripts.graduation.g1_complete_cv_payload import (
    AXES,
    SPEED_CLASSES,
    PayloadClearance,
    object_matrix,
    positive_support,
    snapshot,
)
from scripts.graduation.perception_io import read, sha, write

from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.clearance_control import CartesianMotionReference
from cloud_edge_robot_arm.vision.observations import RGBDObservation

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / ".git").exists())
PLAN = read(HERE / "plan.json")
ROOTS = {k: REPO / p for k, p in PLAN["roots"].items()}
OUT = REPO / PLAN["output"]
ENTRY = PLAN["entry_tick"]
ORIGINAL_END = PLAN["original_rejection_tick"]
END = PLAN["candidate_end_tick"]
STOP = PLAN["budget"]["original_stop_ticks"]
STATE = mujoco.mjtState.mjSTATE_INTEGRATION
BILATERAL = {("left_finger_geom", "object_geom"), ("object_geom", "right_finger_geom")}
TABLE = ("object_geom", "table")


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def deny(*args, **kwargs):
    raise AssertionError("CPU candidate precheck cannot render")


def source(key):
    root, name = key.split("/", 1)
    file = (ROOTS[root] / name).resolve()
    require(file.is_relative_to(ROOTS[root].resolve()), "foreign source")
    require(sha(file) == PLAN["hashes"][key], f"changed source: {key}")
    return file


def module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def pack_hash(b):
    d = np.empty(mujoco.mj_stateSize(b._model, STATE), dtype="<f8")
    mujoco.mj_getState(b._model, b._data, d, STATE)
    return hashlib.sha256(d.tobytes()).hexdigest()


def pairs(b):
    return sorted(tuple(sorted((r.geom1, r.geom2))) for r in b.get_contacts())


def prepare_profiles(motion):
    old = read(source("profiles/g1_complete_cv_source_motion_profile.json"))
    generic = read(source("profiles/g1_complete_cv_payload_profile.json"))
    n = read(source("refit_raw/fit/candidate-profile.json"))
    challenge = read(source("refit_raw/challenge/reader-1.json"))
    seal = read(source("refit_raw/fit/fit-seal.json"))
    live_classes = PLAN["world_refit_classes"]
    require(
        challenge["passed"]
        and challenge["challenge_eligible_classes"] == live_classes
        and seal["profile_sha256"]
        == challenge["profile_sha256"]
        == sha(source("refit_raw/fit/candidate-profile.json"))
        and old["parts"] == n["parts"] == motion.names
        and old["asset_sha256"] == n["asset_sha256"] == generic["asset_sha256"]
        and old["source_support_sha256"]
        == n["source_support_sha256"]
        == sha(source("profiles/g1_complete_cv_source_support_profile.json")),
        "refit eligibility or geometry differs",
    )
    require(
        list(AXES[3]) == [0, -1, 0]
        and list(AXES[5]) == [0, 0, -1]
        and all(
            (np.array(n["classes"][c]["world"]) >= np.array(old["classes"][c]["world"])).all()
            for c in live_classes
        ),
        "world direction order changed or source allowance shrank",
    )
    picked = dict(
        old,
        classes={
            key: (n["classes"][key] if key in live_classes else value)
            for key, value in old["classes"].items()
        },
    )
    require(
        all(picked["classes"][k] == old["classes"][k] for k in PLAN["keep_original_classes"]),
        "unchallenged class changed",
    )
    return PayloadClearance(motion, generic, old), PayloadClearance(motion, generic, picked)


def native_stop(backend, bridge, tick, dest, entry_tool=None):
    before = pack_hash(backend)
    live, saved = bridge.cloned(backend)
    bridge.restore(backend, saved)
    backend._actuator_observer = None
    q, dq, ctrl, records, entry = [], [], [], [], []
    try:
        seq = len(backend.command_records)
        backend.emergency_stop()
        require(
            [c["type"] for c in backend.command_records[seq:]]
            == ["hold_current_joints", "emergency_stop"]
            and np.array_equal(backend._target_positions, backend._data.qpos[:7])
            and not backend._gripper_open
            and not backend._pending_joint_targets
            and backend.estop_engaged,
            "original native HOLD transition differs",
        )
        for offset in range(STOP + 1):
            require(backend.total_physics_steps == tick + offset, "stop clock differs")
            q.append(backend._data.qpos.copy())
            dq.append(backend._data.qvel.copy())
            ctrl.append(backend._data.ctrl.copy())
            records.append(pairs(backend))
            if entry_tool:
                entry.append(entry_tool.sample(backend)[0])
            if offset < STOP:
                require(backend.step(1).physics_steps == 1, "wrong stop integration")
    finally:
        bridge.restore(backend, live)
    require(pack_hash(backend) == before, "stop damaged normal candidate state")
    q, dq, ctrl = map(np.asarray, (q, dq, ctrl))
    raw = dest / f"stop-{tick}.npz"
    contact = dest / f"stop-{tick}.json"
    with raw.open("xb") as stream:
        np.savez_compressed(stream, q=q, dq=dq, ctrl=ctrl)
    write(contact, records)
    return (
        q,
        dq,
        records,
        entry,
        {"state_sha256": sha(raw), "contacts_sha256": sha(contact), "phase_sha256": before},
    )


def map_source_steps(optics, check):
    max_gap = read(source("profiles/g1_complete_cv_source_support_profile.json"))[
        "max_current_gap_m"
    ]
    return {
        tick
        for tick, row in check.items()
        if row["status"] == "CLEAR"
        and row["current"]["payload_observation"]["evidence"].get("cube_bottom_interval_m")
        is not None
        and row["current"]["payload_observation"]["evidence"]["cube_bottom_interval_m"][0] > max_gap
        and optics[tick][1]["source_table_support"]["qualified"] is False
    }


def entry_optics(bridge, optics, model, views, calibration):
    index = read(ROOTS["grid"] / "rgbd-index.json")
    gate = read(source("grid/clearance-gate.json"))["checks"]
    results = []
    volume = optics.volume_check(model, views, {})

    def handoff_volume(box, pad):
        require(
            np.shape(pad) == (3,) and np.isfinite(pad).all() and (pad >= 0).all(),
            "unregistered handoff volume padding",
        )
        enclosure = Box(box.name, box.c, box.h + abs(box.r).T @ pad, box.r)
        return volume(enclosure, np.zeros(3))

    for phase in ("PRE", "FEEDBACK"):
        (item,) = [
            x
            for x in index["rows"]
            if x["skill"] == "LIFT" and x["phase"] == phase and x["robot"]["physics_step"] == ENTRY
        ]
        (old,) = [
            x["current"]
            for x in gate
            if x["skill"] == "LIFT" and x["phase"] == phase and x["step"] == ENTRY
        ]
        robot = item["robot"]
        frame = RGBDObservation.model_validate_json(
            gzip.decompress((ROOTS["grid"] / item["file"]).read_bytes())
        )
        require(
            sha(ROOTS["grid"] / item["file"]) == item["file_sha256"]
            and frame.checksum_sha256 == robot["checksum_sha256"] == old["checksum_sha256"]
            and frame.frame_id == robot["frame_id"] == old["frame_id"]
            and frame.sim_time_s == robot["sim_time_s"] == robot["camera_encoder_sim_time_s"]
            and frame.episode_id == index["episode_id"]
            and frame.scene_id == index["scene_id"]
            and frame.model_dump(mode="json", include=set(calibration["primary_camera"]))
            == calibration["primary_camera"]
            and old["source_table_support"]["qualified"]
            and old["depth"]["unknown_pixels"] == 0,
            "entry evidence cannot be attached to the original PRE or FEEDBACK",
        )
        pose = old["payload_observation"]["pose"]
        x = handoff_motion(
            frame,
            {"frame_id": frame.frame_id, "checksum": frame.checksum_sha256},
            robot["handoff"],
            "LIFT",
            phase,
            np.asarray(robot["joint_positions_rad"]),
            np.asarray(robot["finger_positions_m"]),
            np.asarray(robot["joint_velocities_rad_s"]),
            np.asarray(robot["finger_velocities_m_s"]),
            np.asarray(pose["center_m"]),
            np.asarray(pose["rotation"]),
            model,
            optical=pose,
            volume_check=handoff_volume,
        )
        expected = old["short_motion"]
        require(
            x["reason"] == expected["reason"]
            and x["matching_trajectories"] == expected["matching_trajectories"]
            and abs(x["minimum_gap_m"] - expected["minimum_gap_m"]) <= 1e-12
            and x["limiting_pair"] == expected["limiting_pair"]
            and x["validated_stop_delays"] == 9,
            "original optical-conditioned handoff spatial gate differs",
        )
        results.append(
            {
                "phase": phase,
                "minimum_gap_m": x["minimum_gap_m"],
                "trajectories": x["matching_trajectories"],
            }
        )
    return results


def check_step(motion, directions, q0, dq0, stop, rows):
    q, dq, contacts, *_ = stop
    mq = np.concatenate((np.asarray([x["q"] for x in rows]).reshape(-1, 16), q), axis=0)
    md = np.concatenate((np.asarray([x["dq"] for x in rows]).reshape(-1, 15), dq), axis=0)
    origin, _, rel, _ = snapshot(
        motion, q0[None], dq0[None], q0[None, 9:12], object_matrix(q0[None])
    )
    w, v, r, rv = snapshot(motion, mq, md, mq[:, 9:12], object_matrix(mq))
    return (
        positive_support(w, v, origin[0], AXES),
        positive_support(r, rv, rel[0], directions),
        contacts,
    )


def stop_from_refit(tick, data, normal):
    seal, baseline_q, directory = data
    d = normal[-1]
    require(
        np.array_equal(d["q"], baseline_q["q"][tick])
        and np.array_equal(d["dq"], baseline_q["dq"][tick])
        and np.array_equal(d["ctrl"], baseline_q["ctrl"][tick]),
        f"refit stop source tick {tick} changed",
    )
    raw = directory / "stops" / f"stop-{tick}.npz"
    contact = raw.with_suffix(".json")
    if str(tick) in seal["new_stops"]:
        item = seal["new_stops"][str(tick)]
        path, h, ch = raw, item["state_sha256"], item["contacts_sha256"]
    else:
        diag = read(
            REPO
            / "experiments/results/g1-grid04-lift-midcourse-braking-20261126/cpu-02/reader-1.json"
        )
        require(
            sha(
                REPO
                / "experiments/results/g1-grid04-lift-midcourse-braking-20261126"
                / "cpu-02/reader-1.json"
            )
            == "a15c824cabf10c3de62e16b03808502bbd417ae5ec1127147c93039cb4c1233c",
            "reuse receipt changed",
        )
        path = (
            REPO
            / "experiments/results/g1-grid04-lift-midcourse-braking-20261126/cpu-02"
            / "stops"
            / raw.name
        )
        h = diag["all_file_sha256"]["stops/" + path.name]
        ch = diag["all_file_sha256"]["stops/" + contact.name]
    require(sha(path) == h and sha(path.with_suffix(".json")) == ch, "old stop raw bytes changed")
    with np.load(path, allow_pickle=False) as f:
        q, dq = f["q"], f["dq"]
    require(
        np.array_equal(q[0], d["q"]) and np.array_equal(dq[0], d["dq"]), "old stop origin differs"
    )
    return q, dq, read(path.with_suffix(".json")), [], {"state_sha256": h, "contacts_sha256": ch}


def run():
    for path in PLAN["hashes"]:
        source(path)
    bridge = module(source("original/screen_braking.py"))
    bridge.verify_inputs()
    renderer = module(
        source("rounds/round-g1-release-terminal-rebound-20261125/terminal_rebound.py")
    )
    handoff_tools = module(
        source("rounds/round-g1-skill-handoff-20261125/handoff-physics-stops.py")
    )
    handoff_compare = module(
        source("rounds/round-g1-t01-lift55-native-qualification-20261126/stop_readback.py")
    )
    fit_home = ROOTS["refit_raw"] / "fit" / "grid04"
    fit = read(fit_home / "seal.json")
    require(
        sha(fit_home / "seal.json")
        == "1cb9174edf21bbdad015c0fcf6ad3846d267f5ebb9a16dbda43b850f8024b65a",
        "wrong reusable source branch seal",
    )
    require(sha(fit_home / "normal.npz") == fit["normal_sha256"], "wrong reusable dense track")
    with np.load(fit_home / "normal.npz", allow_pickle=False) as f:
        fitting_state = {a: f[a] for a in ("q", "dq", "ctrl")}
    sar = ROOTS["refit"]
    sys.path.insert(0, str(sar))
    try:
        optics = module(sar / "precheck_expansion.py")
        optical_check = module(sar / "read_refit_stops.py")
    finally:
        sys.path.pop(0)
    cal, views = optical_check.load_optics()
    old_optics = optical_check.frame_sources("grid04")
    samples, commands, feedback, scenario = bridge.archived()
    retirement = map_source_steps(old_optics, feedback)
    asset = bridge.ASSET
    motion = MotionGeometry(Model(asset))
    parent, new = prepare_profiles(motion)
    entry_stage = read(source("profiles/g1_complete_cv_handoff_profile.json"))["stages"]["LIFT"]
    original_stage_optics = entry_optics(bridge, optics, motion.model, views, cal)
    dest = OUT / "native"
    dest.mkdir(parents=True, exist_ok=False)
    b = MuJoCoPhysicsBackend()
    raw_steps = 0
    step_impl = mujoco.mj_step

    def counted(model, data):
        nonlocal raw_steps
        raw_steps += 1
        require(raw_steps <= PLAN["budget"]["total_cpu_ticks_max"], "CPU stop cap exceeded")
        return step_impl(model, data)

    with patch.multiple(mujoco, mj_step=counted, Renderer=deny, mjr_render=deny):
        b.initialize(
            SimulatorConfig(
                model_path=str(asset),
                seed=scenario.seed,
                physics_dt_s=1 / 240,
                render_rgb=True,
                render_depth=True,
                domain_randomization=False,
                camera_width=320,
                camera_height=240,
            )
        )
        with renderer.render_free(b, b.shutdown):
            b.reset(scenario)
            seen = set()
            bridge.early_replay(b, samples, commands, seen)
            require(
                len(b.command_records) == 236 and b.total_physics_steps == ENTRY,
                "wrong native handoff",
            )
            start = tuple(b.current_physics_observation().tcp_position_m)
            path = VerticalClearancePath(
                task_id=PLAN["only_case"],
                step_id="LIFT",
                skill="LIFT",
                start_m=start,
                target_m=(*start[:2], PLAN["original_unchanged_grounded_z_m"]),
                minimum_height_m=0.08,
            )
            quat = np.empty(4)
            mujoco.mju_mat2Quat(quat, b._data.site("tcp").xmat)

            def ref():
                return CartesianMotionReference(
                    b,
                    path.start_m,
                    path.target_m,
                    quat,
                    control_steps=bridge.CONTROL,
                    timeout_s=8,
                    max_velocity=bridge.LIMIT_V,
                    max_acceleration=bridge.LIMIT_A,
                )

            _, saved = bridge.cloned(b)
            a, c = ref(), ref()
            reference = bridge.candidate_reference(b, c, path, quat)
            previous = {}
            recorded_ctrl = {}

            def original(step, row):
                bridge.audit_samples(b, samples, seen)
                previous[step] = (
                    b._data.qpos.tolist(),
                    b._data.qvel.tolist(),
                    b._data.ctrl.tolist(),
                )

            def command_old(tick):
                require(len(commands[tick]) == 1, "wrong command phase")
                bridge.command_match(b.command_records[-1], commands[tick][0])

            def drive(event):
                recorded_ctrl[event.physics_step - 1] = b._data.ctrl.tolist()

            with b.observe_actuator_steps(drive):
                bridge.shadow(b, path, a, ORIGINAL_END - ENTRY, original, audit_after=command_old)
            require(
                len(seen) == 78 and len(b.command_records) == 355 and len(recorded_ctrl) == 592,
                "original baseline did not close",
            )
            bridge.restore(b, saved)
            instrument = handoff_tools.Instrument(b)
            instrument.io_names = handoff_tools.io.NAMES
            require(
                entry_stage["pairs"] == [list(p) for p in instrument.pairs],
                "handoff pair ordering differs",
            )
            entry_start = instrument.sample(b)[0]
            entry_normal = []
            entry_checks = []
            windows = []
            history = []
            pending = []
            retired_at = None
            differences = {}
            restored = {}
            archives = {}
            old_truth = read(ROOTS["refit_raw"] / "scope-reader-1.json")["results"]
            require(
                2112 in [row["tick"] for row in old_truth["grid04"]["original_rejections"]],
                "historical optical refusal lost",
            )

            def check_entry(tick, branch, prefix):
                pair = handoff_compare.compare_handoff(
                    entry_stage, instrument, entry_start, prefix + branch[3]
                )
                hit = next(
                    (
                        i
                        for i, cs in enumerate(branch[2])
                        if not BILATERAL <= set(cs) <= BILATERAL | {TABLE}
                    ),
                    None,
                )
                entry_checks.append(
                    {
                        "trigger": tick,
                        "delay": tick - ENTRY,
                        "minima": pair,
                        "first_invalid_contact": hit,
                    }
                )
                require(
                    hit is None and all(v["margin_m"] >= 0 for v in pair.values()),
                    f"original entry stop undercoverage at {tick}",
                )

            def next_command(tick):
                if tick == ENTRY:
                    branch = native_stop(b, bridge, tick, dest, instrument)
                    archives[str(tick)] = branch[-1]
                    check_entry(tick, branch, [])
                if (
                    tick in commands
                    and "first_command" not in differences
                    and b.command_records[-1]["target_positions_rad"]
                    != commands[tick][0]["target_positions_rad"]
                ):
                    differences["first_command"] = tick

            def candidate_drive(event):
                tick = event.physics_step - 1
                if (
                    tick in recorded_ctrl
                    and "first_ctrl" not in differences
                    and b._data.ctrl.tolist() != recorded_ctrl[tick]
                ):
                    differences["first_ctrl"] = tick

            def current(tick, row):
                nonlocal retired_at
                actual = b._data
                item = {
                    "tick": tick,
                    "q": actual.qpos.tolist(),
                    "dq": actual.qvel.tolist(),
                    "ctrl": actual.ctrl.tolist(),
                    "t": float(actual.time),
                    "tcp": list(row.tcp_position_m),
                    "cube": list(row.object_geom_position_m),
                    "contacts": pairs(b),
                    "phase_sha256": pack_hash(b),
                    "pending_count": len(b._pending_joint_targets),
                }
                history.append(item)
                same = (
                    tick in previous
                    and previous[tick] == (item["q"], item["dq"], item["ctrl"])
                    and "first_ctrl" not in differences
                )
                if tick in previous and not same:
                    differences.setdefault("first_integrated_state", tick)
                if tick in retirement and same and retired_at is None:
                    retired_at = tick
                if tick > ENTRY and (tick - ENTRY) % 8 == 0:
                    if same and tick in feedback and feedback[tick]["status"] == "CLEAR":
                        robot, e = optical_check.gate_source("grid04", tick, old_optics[tick], cal)
                        active = e["short_motion"]
                        speed = active["speed_class"]
                        source_class = active.get("registered_source_speed_class")
                        allowed = e["source_table_support"]["qualified"]
                        old_check = (
                            optics.evaluate(parent, robot, e, views, source_class, 0, 0, None)
                            if allowed
                            else None
                        )
                        if allowed:
                            wider = optics.evaluate(new, robot, e, views, source_class, 0, 0, None)
                            require(
                                old_check["predicate"]["reason"] == active["reason"]
                                and wider["predicate"]["reason"] is None,
                                f"shared frame failed volume check at {tick}",
                            )
                        schema = (
                            [("source_" + source_class, speed)] if allowed else [("generic", speed)]
                        )
                        pending.append((tick, schema, "archived_matching_feedback"))
                    else:
                        differences.setdefault("first_missing_candidate_exposure", tick)
                        v = float(abs(actual.qvel[:7]).max())
                        programs = new.data["LIFT"]
                        peak = float(abs(programs["references"][:, 7:14]).max()) + 0.002
                        require(v <= peak, "candidate exceeds original trained speed domain")
                        speeds = [
                            str(k)
                            for k in SPEED_CLASSES
                            if v <= k and str(k) in programs["classes"]
                        ]
                        speed = speeds[0] if speeds else "all"
                        options = [("generic", speed)]
                        if retired_at is None:
                            check = [
                                str(k)
                                for k in SPEED_CLASSES
                                if v <= k and str(k) in new.source_classes
                            ]
                            options.append(("source_" + (check[0] if check else "all"), speed))
                        pending.append((tick, options, "mechanical_only_optics_not_known"))
                pending[:] = [x for x in pending if tick - x[0] <= 8]
                is_entry = ENTRY < tick <= ENTRY + 8
                if not (is_entry or pending):
                    return
                if is_entry:
                    entry_normal.append(instrument.sample(b)[0])
                if not is_entry and same and 1528 <= tick <= 1848:
                    branch = stop_from_refit(tick, (fit, fitting_state, fit_home), history)
                    restored[str(tick)] = branch[-1]
                else:
                    branch = native_stop(b, bridge, tick, dest, instrument if is_entry else None)
                    archives[str(tick)] = branch[-1]
                if is_entry:
                    check_entry(tick, branch, [entry_start, *entry_normal[:-1]])
                for at, modes, scope in pending:
                    row = history[at - ENTRY]
                    world, relative, contacts = check_step(
                        motion,
                        new.axes,
                        np.array(row["q"]),
                        np.array(row["dq"]),
                        branch,
                        history[at - ENTRY : tick - ENTRY],
                    )
                    wins = []
                    for mode, speed in modes:
                        stage = new.data["LIFT"]["classes"][speed]
                        kind = mode.removeprefix("source_") if mode != "generic" else None
                        limit = new.source_classes[kind][0] if kind else stage["world"]
                        old_limit = parent.source_classes[kind][0] if kind else stage["world"]
                        residual = limit - world
                        i, j = np.unravel_index(residual.argmin(), residual.shape)
                        allowed = BILATERAL | ({TABLE} if kind else set())
                        bad = next(
                            (
                                i
                                for i, x in enumerate(contacts)
                                if not BILATERAL <= set(map(tuple, x)) <= allowed
                            ),
                            None,
                        )
                        wins.append(
                            {
                                "mode": mode,
                                "speed_class": speed,
                                "worst_part": motion.names[i],
                                "world_axis": AXES[j].tolist(),
                                "world_min_m": float(residual[i, j]),
                                "old_world_min_m": float((old_limit - world).min()),
                                "relative_min_m": float((stage["relative"] - relative).min()),
                                "first_invalid_contact": bad,
                            }
                        )
                    windows.append(
                        {
                            "anchor": at,
                            "trigger": tick,
                            "delay": tick - at,
                            "scope": scope,
                            "modes": wins,
                        }
                    )
                    require(
                        any(
                            z["world_min_m"] >= 0
                            and z["relative_min_m"] >= 0
                            and z["first_invalid_contact"] is None
                            for z in wins
                        ),
                        f"no applicable mechanical stop envelope covers {at} / {tick}",
                    )

            status = {"status": "CPU_REFERENCE_END"}
            with b.observe_actuator_steps(candidate_drive):
                try:
                    bridge.shadow(b, path, c, END - ENTRY, current, audit_after=next_command)
                except ValueError as err:
                    status = {"status": "CPU_REJECTED", "reason": str(err)}
            status.update(
                native_clock=b.total_physics_steps,
                integrations=raw_steps,
                new_stops=len(archives),
                reused_stops=len(restored),
                verified_original_exposures=len(seen),
                verified_original_commands=355,
                verified_original_drives=len(recorded_ctrl),
                new_exposures=0,
                source_grasp_permanently_retired_at=retired_at,
                differences=differences,
                qualified_native_lift=False,
                qualified_dwell=False,
                qualified_post=False,
            )
            result = {
                "status": status,
                "entry_checks": entry_checks,
                "entry_original_spatial": original_stage_optics,
                "ordinary_windows": windows,
                "reference": reference,
                "archives": archives,
                "reused": restored,
            }
            write(dest / "normal.json", history)
            write(dest / "result.json", result)


def cold(reader):
    dest = OUT / "native"
    history = read(dest / "normal.json")
    r = read(dest / "result.json")
    s = r["status"]
    require(
        [row["tick"] for row in history] == list(range(ENTRY, ENTRY + len(history))),
        "candidate chronology changed",
    )
    require(
        s["integrations"] == ORIGINAL_END + (s["native_clock"] - ENTRY) + s["new_stops"] * STOP,
        "integration receipt differs",
    )
    for tick, pin in r["archives"].items():
        require(
            sha(dest / f"stop-{tick}.npz") == pin["state_sha256"]
            and sha(dest / f"stop-{tick}.json") == pin["contacts_sha256"],
            "brake raw bytes changed",
        )
    table = [x for x in r["ordinary_windows"] if x["anchor"] == 1744 and x["trigger"] == 1747]
    if history[-1]["tick"] >= 1747:
        require(
            len(table) == 1
            and table[0]["modes"][0]["old_world_min_m"] < 0 <= table[0]["modes"][0]["world_min_m"],
            "known source rebuttal not closed",
        )
    rise = np.array([row["cube"][2] - history[0]["cube"][2] for row in history])
    lat = np.linalg.norm(
        np.array([row["tcp"][:2] for row in history]) - history[0]["tcp"][:2], axis=1
    )
    counts = Counter(z["anchor"] for z in r["ordinary_windows"])
    write(
        OUT / f"{reader}.json",
        {
            "status": s,
            "reference": r["reference"],
            "entry_checks": r["entry_checks"],
            "entry_original_spatial": r["entry_original_spatial"],
            "last_measured_tick": history[-1]["tick"],
            "first_cube_50mm": next(
                (row["tick"] for row, x in zip(history, rise, strict=True) if x >= 0.05), None
            ),
            "max_cube_lift_m": float(rise.max()),
            "terminal_cube_lift_m": float(rise[-1]),
            "maximum_lateral_m": float(lat.max()),
            "last_check": r["ordinary_windows"][-1] if r["ordinary_windows"] else None,
            "known_rebuttal": table,
            "full_windows": sum(n == 9 for n in counts.values()),
            "window_count": len(counts),
            "normal_sha256": sha(dest / "normal.json"),
            "result_sha256": sha(dest / "result.json"),
        },
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("phase", choices=("run", "read"))
    cli.add_argument("--reader", choices=("reader-1", "reader-2"))
    args = cli.parse_args()
    OUT.mkdir(exist_ok=True)
    if args.phase == "run":
        try:
            run()
        except BaseException as e:
            write(OUT / "failure.json", {"type": type(e).__name__, "reason": str(e)})
            raise
    else:
        cold(args.reader)
