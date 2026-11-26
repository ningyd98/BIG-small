"""Compare original immediate braking with one isolated retained-target CPU branch."""

import argparse
import importlib.util
from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np
from scripts.graduation.dynamic_vision import plain
from scripts.graduation.g1_clearance_score import verify_generation
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry
from scripts.graduation.g1_complete_cv_payload import (
    object_matrix,
    snapshot,
)
from scripts.graduation.g1_dual_trials import RegisteredAssemblyBackend
from scripts.graduation.perception_io import ROOT, read, sha, write

from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
from cloud_edge_robot_arm.simulation.config import SimulatorConfig

HERE = Path(__file__).resolve().parent
REPO = next(path for path in HERE.parents if (path / ".git").exists())
PLAN = read(HERE / "plan.json")
RAW = REPO / PLAN["instance"]
OUT = REPO / PLAN["output"]
ANCHOR = PLAN["anchor"]
PAIR = ("object_geom", "table")
FINGERS = {("left_finger_geom", "object_geom"), ("object_geom", "right_finger_geom")}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def companion(round_name, file):
    path = HERE.parent / round_name / file
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def inputs():
    require(ROOT == (REPO / PLAN["runtime"]).resolve(), "wrong frozen import root")
    verify_generation(ROOT, PLAN["sha256"][PLAN["runtime"] + "/runtime-build.json"])
    for rel, expected in PLAN["sha256"].items():
        require(sha(REPO / rel) == expected, "source changed: " + rel)
    cfg = read(RAW.parent / "allocation.json")["case"]
    asset = ROOT / cfg["asset_path"]
    require(cfg["view"] == "nominal" and asset.is_file(), "wrong original assembly")
    trace = read(RAW.parent / "lift-qualification-trace.json")
    (entrance,) = [r["state"] for r in trace["frames"] if r["state"]["physics_step"] == ANCHOR]
    (control,) = [r for r in trace["before_integrations"] if r["physics_step"] == ANCHOR]
    return asset, entrance, control


def linear_prediction(asset, entrance, control):
    model = mujoco.MjModel.from_xml_path(str(asset))
    data = mujoco.MjData(model)
    mujoco.mj_setState(
        model, data, np.asarray(entrance["integration"]), mujoco.mjtState.mjSTATE_INTEGRATION
    )
    mujoco.mj_kinematics(model, data)
    mujoco.mj_comPos(model, data)
    goal = np.asarray(entrance["arm_target"])
    q = data.qpos[:7]
    gains = model.actuator_gainprm[:7, 0]
    low, high = model.actuator_ctrlrange[:7].T
    bias = np.asarray(entrance["qfrc_bias_arm"]) / gains
    retained = np.clip(q + np.clip(goal - q, -0.1, 0.1) + bias, low, high)
    hold = np.clip(q + bias, low, high)
    require(np.array_equal(retained, control["ctrl"][:7]), "frozen original retained drive differs")
    with np.load(REPO / PLAN["original_stop"], allow_pickle=False) as old:
        require(np.array_equal(hold, old["ctrl"][0, :7]), "frozen first HOLD drive differs")
    displacement = retained - hold
    jacp, jacr = np.zeros((3, model.nv)), np.zeros((3, model.nv))
    mujoco.mj_jacSite(model, data, jacp, jacr, model.site("tcp").id)
    translation = jacp[:, :7] @ displacement
    rotation = jacr[:, :7] @ displacement
    motion = MotionGeometry(Model(asset))
    part = motion.names.index("g1_dual_id8_plate")
    q = data.qpos[None].copy()
    v, _, _, _ = snapshot(motion, q, data.qvel[None], q[:, 9:12], object_matrix(q))
    tcp = data.site("tcp").xpos.copy()
    predicted = translation + np.cross(rotation, v[0, part] - tcp)
    load = translation + np.cross(rotation, data.qpos[9:12] - tcp)
    return {
        "old_target_minus_hold_rad": (goal - data.qpos[:7]).tolist(),
        "retained_minus_hold_ctrl_rad": displacement.tolist(),
        "instantaneous_position_feedback_delta_nm": (gains * displacement).tolist(),
        "linear_TCP_retained_minus_hold_Z_m": float(translation[2]),
        "linear_origin_retained_minus_hold_Z_m": float(load[2]),
        "linear_ID8_retained_minus_hold_Z_each_corner_m": predicted[:, 2].tolist(),
        "linear_rotation_retained_minus_hold_rad": rotation.tolist(),
        "interpretation": "Initial sign prediction only.",
    }


def original_prefix(backend, original, commands, truth, saved, native):
    by_tick = {}
    for cmd in commands:
        if 1632 <= cmd["physics_step"] < ANCHOR:
            by_tick.setdefault(cmd["physics_step"], []).append(cmd)
    for tick in range(1632, ANCHOR):
        for cmd in by_tick.get(tick, []):
            original.replay_command(backend, cmd)
        require(backend.step(1).physics_steps == 1, "multistep prefix")
        row = plain(backend.current_physics_observation())
        require(
            all(row[k] == truth[tick + 1][k] for k in row if k != "episode_id"),
            f"original trajectory diverged at {tick + 1}",
        )
    require(
        native.packed(backend).tolist() == saved["integration"]
        and backend._data.qfrc_bias[:7].tolist() == saved["qfrc_bias_arm"]
        and backend._target_positions.tolist() == saved["arm_target"]
        and backend._pending_joint_targets == saved["pending"] == []
        and len(backend.command_records) == saved["command_count"],
        "stop anchor state, original feedback or command queue differ",
    )


def sample(backend, motion):
    d = backend._data
    physical = plain(backend.current_physics_observation())
    q = d.qpos[None].copy()
    v, _, _, _ = snapshot(motion, q, d.qvel[None], q[:, 9:12], object_matrix(q))
    part = motion.names.index("g1_dual_id8_plate")
    return {
        "motion": physical,
        "ctrl": d.ctrl.tolist(),
        "ID8_corner_Z_m": v[0, part, :, 2].tolist(),
    }


def velocities(physical):
    return np.array(
        [
            abs(np.asarray(physical["joint_velocities_rad_s"])).max(),
            np.linalg.norm(physical["object_linear_velocity_m_s"]),
            np.linalg.norm(physical["object_angular_velocity_rad_s"]),
        ]
    )


def match(anchor, final, original_last):
    requested = PLAN["matching"]
    eps = requested["each_world_height_or_plate_corner_atol_m"]
    count = requested["frames"]
    threshold = requested["arm_object_linear_and_angular_speed_fraction_of_original"]
    if len(final) != count:
        return {"matched": False, "reason": "fixed waiting horizon did not create eight samples"}
    physical = anchor["motion"]
    top = np.stack([velocities(r) for r in original_last]).max(axis=0)
    last = [r["motion"] for r in final]
    v = np.stack([velocities(r) for r in last]).max(axis=0)
    diff_z = max(abs(r["tcp_position_m"][2] - physical["tcp_position_m"][2]) for r in last)
    diff_object = max(
        abs(r["object_geom_position_m"][2] - physical["object_geom_position_m"][2]) for r in last
    )
    diff_board = max(
        abs(np.asarray(r["ID8_corner_Z_m"]) - anchor["ID8_corner_Z_m"]).max() for r in final
    )
    contact_ok = all({tuple(sorted(a)) for a in r["contact_pairs"]} == FINGERS for r in last)
    same_geometry = bool(max(diff_z, diff_object, diff_board) <= eps)
    low_motion = (v <= top * threshold).tolist()
    return {
        "matched": contact_ok and same_geometry and all(low_motion),
        "bilateral_and_suspended": contact_ok,
        "same_height_all": same_geometry,
        "same_height_max_delta_m": {"tcp": diff_z, "object": diff_object, "ID8": float(diff_board)},
        "B_velocity_peaks": v.tolist(),
        "A_velocity_peaks": top.tolist(),
        "low_motion_per_dimension": low_motion,
    }


def retained_branch(b, motion, truth, result):
    samples = []
    anchor = sample(b, motion)
    frozen = list(b.command_records)
    target = b._target_positions.copy()
    src = read(ROOT / "scripts/graduation/g1_lift55_entry.json")
    path = VerticalClearancePath(
        "mechanical-identification",
        "LIFT",
        "LIFT",
        tuple(src["robot"]["tcp_position_m"]),
        tuple(src["target"][ax] for ax in "xyz"),
        0.08,
    )
    max_z = max(t["tcp_position_m"][2] for t in truth[1632 : ANCHOR + 1])
    for offset in range(1, 241):
        b.step(1)
        row = sample(b, motion)
        samples.append(row)
        physical = row["motion"]
        pairs = {tuple(sorted(p)) for p in physical["contact_pairs"]}
        require(
            np.array_equal(b._target_positions, target) and list(b.command_records) == frozen,
            "diagnostic branch issued a new ordinary target",
        )
        try:
            tcp = tuple(physical["tcp_position_m"])
            path.check_position(tcp, peak_z=max_z)
            max_z = max(max_z, tcp[2])
            require(FINGERS <= pairs <= FINGERS | {PAIR}, "unplanned or missing contact")
        except ValueError as why:
            result["retained_first_obstruction"] = {
                "offset": offset,
                "step": ANCHOR + offset,
                "reason": str(why),
            }
            break
        if PAIR in pairs:
            result["retained_first_obstruction"] = {
                "offset": offset,
                "step": ANCHOR + offset,
                "reason": "first return to source table",
            }
            break
    if len(samples) < 240:
        check = {"matched": False, "reason": "retained branch ended before 240"}
    else:
        check = match(anchor, samples[-8:], truth[ANCHOR - 7 : ANCHOR + 1])
    result["retained_steps"] = len(samples)
    result["retained_fixed_window_match"] = check
    return anchor, samples


def run(asset, entrance, control):
    cfgdir = OUT / "cpu-identification"
    cfgdir.mkdir()
    results = {
        "source_phase_exact": False,
        "original_stop_states_exact": 0,
        "B_stop_steps": 0,
        "retained_first_obstruction": None,
        "new_exposures": 0,
        "new_live_slots": 0,
    }
    a, z = OUT / "reader-1.json", OUT / "reader-2.json"
    require(a.read_bytes() == z.read_bytes(), "cold control arithmetic differs")
    require(
        read(a)["prediction"] == linear_prediction(asset, entrance, control),
        "cold prediction changed",
    )
    src = companion(
        "round-g1-t01-lift55-force-init-qualification-20261126", "screen_force_initialization.py"
    )
    replay = companion("round-g1-t01-lift-entry-force-cache-20261126", "replay_entry_cache.py")
    paired = companion(
        "round-g1-t01-lift-stop-motion-decomposition-20261126", "read_stop_dynamics.py"
    )
    put = companion("round-g1-t01-lift-finger-inertia-20261126", "identify_finger_inertia.py")
    helper = companion("round-g1-t01-lift55-native-qualification-20261126", "stop_readback.py")
    allocation, commands, truth, reset = src.source_inputs()
    cfg = allocation["case"]
    b = RegisteredAssemblyBackend(cfgdir, cfg)
    try:
        with patch.multiple(mujoco, Renderer=replay.prohibited, mjr_render=replay.prohibited):
            b.initialize(
                SimulatorConfig(
                    model_path=str(asset),
                    seed=cfg["visual_seed"],
                    physics_dt_s=1 / 240,
                    render_rgb=True,
                    render_depth=True,
                    domain_randomization=False,
                )
            )
            with replay.no_render_context()(b, b.shutdown):
                src.cpu_entry(b, replay, commands, truth, reset)
                original_prefix(b, replay, commands, truth, entrance, replay)
                results["source_phase_exact"] = True
                retained = paired.clone_context(b, replay)
                frozen_stop = paired.stop_dynamics(b, REPO / PLAN["original_stop"])
                results["original_stop_states_exact"] = len(frozen_stop)
                paired.enter_context(b, retained)
                motion = MotionGeometry(Model(asset))
                anchor, samples = retained_branch(b, motion, truth, results)
                write(cfgdir / "B-retained.json", {"anchor": anchor, "samples": samples})
                if results["retained_fixed_window_match"]["matched"]:
                    native_result, pairs = put.capture_stop(b, helper, asset, cfgdir / "B-stop.npz")
                    write(cfgdir / "B-stop.json", {"result": native_result, "pairs": pairs})
                    results.update(B_stop_steps=240, B_stop=native_result)
                results["cpu_integrations"] = (
                    1840 + 240 + results["retained_steps"] + results["B_stop_steps"]
                )
    except BaseException as exc:
        write(cfgdir / "failure.json", dict(results, error=str(exc)))
        raise
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("cold", "run"))
    parser.add_argument("--reader", choices=("reader-1", "reader-2"))
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    asset, state, drive = inputs()
    links = {"source_sha256": sha(Path(__file__)), "plan_sha256": sha(HERE / "plan.json")}
    if args.mode == "cold":
        write(
            OUT / f"{args.reader}.json",
            dict(links, prediction=linear_prediction(asset, state, drive)),
        )
    else:
        write(OUT / "result.json", dict(links, result=run(asset, state, drive)))


if __name__ == "__main__":
    main()
