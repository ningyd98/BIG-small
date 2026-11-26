"""Read the original LIFT stop and construct two nominal references on CPU."""

import argparse
import hashlib
import inspect
import json
import math
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import mujoco
import numpy as np
from scripts.graduation.perception_io import pinned, read, sha

from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.clearance_control import CartesianMotionReference

HERE = Path(__file__).resolve().parent
REPO = next(path for path in HERE.parents if (path / ".git").exists())
PLAN = read(HERE / "plan.json")
RAW = REPO / PLAN["raw"]
OUT = REPO / PLAN["output"]


class SlowerReference(CartesianMotionReference):
    duration_s = 5.5


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def load():
    for rel, expected in PLAN["input_sha256"].items():
        require(sha(REPO / rel) == expected, f"original changed: {rel}")
    runtime = REPO / PLAN["runtime"]
    require(
        Path(inspect.getfile(CartesianMotionReference)).is_relative_to(runtime)
        and Path(inspect.getfile(VerticalClearancePath)).is_relative_to(runtime),
        "unregistered reference or clearance path implementation",
    )
    lock = read(runtime / "runtime-build.json")
    allocation = read(RAW.parent / "allocation.json")
    asset = runtime / allocation["case"]["asset_path"]
    require(
        sha(asset)
        == lock["runtime_files_sha256"][allocation["case"]["asset_path"]]
        == allocation["asset_sha256"],
        "original assembly differs",
    )
    receipt = read(RAW / "receipt.json")
    seal = pinned(RAW / "acquisition-seal.json", receipt["capture_sha256"])
    truth = pinned(RAW / "offline-truth.json", seal["truth_sha256"])
    run = pinned(RAW / "run.json", seal["run_sha256"])
    audit = pinned(RAW / "online-audit.json", seal["audit_sha256"])
    index = pinned(RAW / "pixel-index.json", seal["index_sha256"])
    local_seal = read(RAW / "local-clearance-seal.json")
    require(
        local_seal["acquisition_seal_sha256"] == receipt["capture_sha256"], "foreign local gate"
    )
    local = pinned(RAW / "local-clearance.json", local_seal["local_clearance_sha256"])
    cmds = pinned(RAW / "backend-commands.json", receipt["full_commands_sha256"])
    return asset, run, audit, index, truth, local, cmds


def frame_index(index, record):
    (source,) = [r for r in index["frames"] if r["frame_id"] == record["frame_id"]]
    require(
        source["physics_step"] == record["physics_step"]
        and source["checksum_sha256"] == record["checksum_sha256"]
        and source["file_sha256"] == sha(RAW / source["file"]),
        "foreign exposure or clock",
    )


def lateral_guard(path, position, peak, reader):
    if reader == "native":
        try:
            path.check_position(tuple(position), peak_z=peak)
        except ValueError as exc:
            return str(exc)
    else:
        x, y, z = position
        sx, sy, sz = path.start_m
        if math.hypot(x - sx, y - sy) > 0.001:
            return "clearance left its 1 mm lateral corridor"
        if z < max(sz, peak) - 0.001:
            return "clearance descended by more than 1 mm"
        if z > path.target_m[2] + 0.005:
            return "clearance exceeded its target height tolerance"
    return None


def profile(reference, data, site, model, start, target, first_window_steps, control_ticks):
    poses = []
    for joints in reference.positions:
        data.qpos[:7] = joints
        mujoco.mj_forward(model, data)
        poses.append(data.site_xpos[site].copy())
    positions = np.array(poses)
    delta = positions - start
    norms = np.linalg.norm(delta[:, :2], axis=1)
    i = int(norms.argmax())
    end_error = float(np.linalg.norm(positions[-1] - target))
    require(end_error <= 1e-9 and norms[i] <= 0.001, "nominal reference geometric rejection")
    digest = hashlib.sha256()
    for values in (reference.positions, reference.velocities, reference.accelerations):
        digest.update(np.asarray(values, dtype="<f8").tobytes())
    prefix = first_window_steps // control_ticks + 1
    return {
        "duration_s": reference.duration_s,
        "settle_s": reference.settle_s,
        "control_dt_s": reference.control_dt,
        "points": len(positions),
        "endpoint_error_m": end_error,
        "nominal_lateral_peak_m": float(norms[i]),
        "nominal_lateral_peak_time_s": i * reference.control_dt,
        "joint_velocity_peak_rad_s": float(abs(reference.velocities).max()),
        "joint_acceleration_peak_rad_s2": float(abs(reference.accelerations).max()),
        "joint_velocity_peak_in_first_115_ticks_rad_s": float(
            abs(reference.velocities[:prefix]).max()
        ),
        "state_vectors_sha256": digest.hexdigest(),
    }


def main_result(reader):
    asset, run, audit, index, truth, local, commands = load()
    action = next(a for a in run["actions"] if a["skill"] == "LIFT")
    entry, stop = action["dispatch_step"], action["controller_return_step"]
    require(
        entry == PLAN["lift_start"]
        and stop == PLAN["first_refusal"]
        and run["stop"]["physics_step"] == stop
        and action["controller_result"]["code"] == "CLEARANCE_PATH_VIOLATION",
        "wrong owner or physical first refusal",
    )
    (pre,) = [r for r in local["rows"] if (r["skill"], r["phase"]) == ("LIFT", "PRE")]
    frames = [r for r in local["rows"] if (r["skill"], r["phase"]) == ("LIFT", "FEEDBACK")]
    require(
        len(frames) == action["feedback_accepted"] == 15
        and frames[-1]["physics_step"] == 1744
        and all(r["status"] == "CLEAR" for r in frames)
        and pre["frame_id"] == action["pre"]["frame_id"]
        and pre["checksum_sha256"] == action["pre"]["checksum_sha256"]
        and pre["physics_step"] == entry
        and pre["robot"]["handoff"]["entry_step"] == entry,
        "local admission or frame ownership differs",
    )
    for r in [pre, *frames]:
        frame_index(index, r)
    start = tuple(pre["robot"]["tcp_position_m"])
    target = tuple(pre["target_xyz"][axis] for axis in ("x", "y", "z"))
    require(start[:2] == target[:2], "native owner target not vertical")
    path = VerticalClearancePath("sealed-t01-audit", "LIFT", "LIFT", start, target, 0.08)
    (servo,) = [r for r in audit if r.get("phase") == "servo" and r.get("skill") == "LIFT"]
    controls = servo["control_samples"]
    visuals = servo["visual_samples"]
    require(
        [r["physics_step"] for r in controls] == list(range(entry, 1745, PLAN["vision_ticks"]))
        and len(controls) == len(visuals) == len(frames)
        and all(
            tuple(c["target_pose"][axis] for axis in ("x", "y", "z")) == target
            and tuple(v["target_pose"][axis] for axis in ("x", "y", "z")) == target
            and c["physics_step"] == f["physics_step"]
            and v["checksum_sha256"] == f["checksum_sha256"]
            and v["observation_id"] == f["frame_id"]
            for c, v, f in zip(controls, visuals, frames, strict=True)
        ),
        "physical controller feedback targets or frame clock changed",
    )
    require(
        pre["robot"]["tcp_position_m"] == truth["samples"][entry]["tcp_position_m"],
        "physical origin and original path start differ",
    )
    tail = [r for r in commands if r["physics_step"] >= stop]
    require(
        [r["type"] for r in tail]
        == ["hold_current_joints", "hold_current_joints", "emergency_stop"]
        and all(r["accepted"] for r in tail),
        "ordinary commands issued after the refusal",
    )
    model = mujoco.MjModel.from_xml_path(str(asset))
    pose_data = mujoco.MjData(model)
    site = model.site("tcp").id

    def fk(q, f):
        pose_data.qpos[:7] = q
        pose_data.qpos[7:9] = f
        mujoco.mj_forward(model, pose_data)
        return pose_data.site_xpos[site].copy()

    prior = [
        r
        for r in commands
        if r["accepted"]
        and r["type"] in ("joint_target", "hold_current_joints")
        and r["physics_step"] < stop
    ]
    used = Counter()
    all_rows = []
    peak = start[2]
    for step in range(entry, stop + 1):
        row = truth["samples"][step]
        require(row["physics_step"] == step, "missing physical row")
        measured = row["tcp_position_m"]
        issue = lateral_guard(path, measured, peak, reader)
        peak = max(peak, measured[2])
        require(
            issue == ("clearance left its 1 mm lateral corridor" if step == stop else None),
            "first refusal is neither at the expected step nor solely lateral",
        )
        effective = next(c for c in reversed(prior) if c["physics_step"] < step)
        staged = next((c for c in reversed(prior) if c["physics_step"] == step), None)
        used[effective["command_seq"]] += 1
        q, f = row["joint_positions_rad"], row["finger_positions_m"]
        actual = fk(q, f)
        drive = fk(effective["applied_target_positions_rad"], f)
        closure = float(np.linalg.norm(actual - measured))
        require(closure <= 1e-5, "FK disagrees with original TCP")
        xy_target = drive[:2] - start[:2]
        xy_tracking = actual[:2] - drive[:2]
        pairs = {frozenset(x) for x in row["contact_pairs"]}
        all_rows.append(
            {
                "step": step,
                "origin_error_xy_m": (np.asarray(measured[:2]) - start[:2]).tolist(),
                "tcp_lateral_m": math.hypot(measured[0] - start[0], measured[1] - start[1]),
                "joint_target_fk_offset_xy_m": xy_target.tolist(),
                "fk_tracking_residual_xy_m": xy_tracking.tolist(),
                "fk_native_error_m": closure,
                "joint_error_rad": (
                    np.asarray(q) - effective["applied_target_positions_rad"]
                ).tolist(),
                "joint_velocity_rad_s": row["joint_velocities_rad_s"],
                "effective_command_sequence": effective["command_seq"],
                "new_command_after_snapshot": staged["command_seq"] if staged else None,
                "table_contact": frozenset(("table", "object_geom")) in pairs,
                "bilateral_contact": all(
                    frozenset((name, "object_geom")) in pairs
                    for name in ("left_finger_geom", "right_finger_geom")
                ),
                "object_center_m": row["object_geom_position_m"],
                "object_bottom_m": row["object_bottom_z_m"],
                "original_guard_error": issue,
            }
        )
    require(
        sum(used.values()) == stop - entry + 1
        and [r["physics_step"] for r in prior if entry <= r["physics_step"]]
        == list(range(entry, stop, PLAN["control_ticks"]))
        and all_rows[-1]["bilateral_contact"],
        "original 5-step command grid or held state changed",
    )
    robot = pre["robot"]
    handoff = robot["handoff"]
    state = mujoco.MjData(model)
    state.qpos[:7] = robot["joint_positions_rad"]
    state.qpos[7:9] = robot["finger_positions_m"]
    state.qvel[:7] = robot["joint_velocities_rad_s"]
    state.qvel[7:9] = robot["finger_velocities_m_s"]
    state.ctrl[:7] = handoff["entry_target_rad"]
    state.ctrl[7:9] = handoff["entry_finger_target_m"]
    state.time = robot["sim_time_s"]
    mujoco.mj_forward(model, state)
    wrist = np.array(robot["tcp_quaternion_wxyz"])
    dot = float(np.dot(wrist, np.array([math.sqrt(0.5), 0.0, math.sqrt(0.5), 0.0])))
    require(abs(dot) >= math.cos(math.radians(5) / 2), "unqualified original wrist attitude")
    micro = SimulatorConfig(physics_dt_s=1 / 240)
    backend = SimpleNamespace(
        _model=model,
        _data=state,
        _mujoco=mujoco,
        _config=micro,
        _joint_names=[f"joint{i}" for i in range(1, 8)],
        total_physics_steps=entry,
    )
    profiles = {}
    for cls, duration in zip(
        (CartesianMotionReference, SlowerReference), PLAN["reference_seconds"], strict=True
    ):
        require(cls.duration_s == duration, "reference duration source mismatch")
        ref = cls(
            backend,
            start,
            target,
            wrist,
            control_steps=PLAN["control_ticks"],
            timeout_s=PLAN["original_timeout_s"],
            max_velocity=PLAN["original_ctrl_vel_limit_rad_s"],
            max_acceleration=PLAN["original_ctrl_acc_limit_rad_s2"],
            initialize_load_from_feedback=False,
        )
        profiles[str(duration)] = profile(
            ref, pose_data, site, model, start, target, stop - entry, PLAN["control_ticks"]
        )
    return {
        "first_refusal": stop,
        "lift_start": entry,
        "start_m": start,
        "target_m": target,
        "control_calls": stop - entry,
        "visual_feedback_samples": len(controls),
        "max_sample_through_ik_s": max(r["sample_and_ik_s"] for r in controls),
        "last_visual_checksum_sha256": frames[-1]["checksum_sha256"],
        "last_occlusion_and_local_clearance": frames[-1]["reason"],
        "last_local_minimum_gap_m": frames[-1]["evidence"]["short_motion"]["minimum_gap_m"],
        "physical_rows": all_rows,
        "reference_profiles": profiles,
        "actual_candidate_dynamic_run": False,
        "native_camera_calls": 0,
        "integration_steps": 0,
    }


def prohibited(*_args, **_kwargs):
    raise RuntimeError("zero-integration CPU reader attempted control or rendering")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reader", choices=("native", "independent"))
    args = parser.parse_args()
    with patch.multiple(
        mujoco,
        mj_step=prohibited,
        mj_step1=prohibited,
        mj_step2=prohibited,
        Renderer=prohibited,
        mjr_render=prohibited,
    ):
        result = main_result(args.reader)
    OUT.mkdir(exist_ok=True, parents=True)
    with (OUT / f"{args.reader}.json").open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")


if __name__ == "__main__":
    main()
