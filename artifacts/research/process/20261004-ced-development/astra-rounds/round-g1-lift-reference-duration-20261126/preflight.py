"""Read frozen LIFT entries and construct the original and slower reference on CPU."""

import argparse
import gzip
import hashlib
import inspect
import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import mujoco
import numpy as np
from scripts.graduation.g1_complete_cv_handoff import binding_error
from scripts.graduation.perception_io import ROOT, read, sha, write

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.clearance_control import CartesianMotionReference
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD
from cloud_edge_robot_arm.vision.observations import RGBDObservation

HERE = Path(__file__).resolve().parent
PLAN_PATH = HERE / "plan.json"
PLAN = read(PLAN_PATH)
CAPTURE = ROOT / PLAN["original_capture"]
RUNTIME = ROOT / PLAN["runtime"]
SEAL_PATH = CAPTURE / "seal.json"


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


class SlowerReference(CartesianMotionReference):
    duration_s = PLAN["reference_seconds"]["variant"]


def inputs():
    for relative, expected in PLAN["sha256"].items():
        path = (ROOT / relative).resolve()
        require(path.is_relative_to(ROOT) and sha(path) == expected, f"unbound input {relative}")
    seal = read(SEAL_PATH)
    require(len(seal["sealed_sha256"]) == 233, "original seal count changed")
    for name, expected in seal["sealed_sha256"].items():
        path = (CAPTURE / name).resolve()
        require(path.is_relative_to(CAPTURE) and sha(path) == expected, f"unbound capture {name}")
    registration = read(CAPTURE / "registration.json")
    slot_ids = [row["id"] for row in PLAN["slots"]]
    require(
        sha(CAPTURE / "registration.json") == seal["registration_sha256"]
        and [r["id"] for r in registration["slots"] if r["id"] in slot_ids] == slot_ids
        and inspect.getfile(CartesianMotionReference)
        == str(RUNTIME / "src/cloud_edge_robot_arm/simulation/mujoco/clearance_control.py")
        and mujoco.__version__ == "3.3.7",
        "original runtime or registration changed",
    )
    allocation = read(CAPTURE / slot_ids[0] / "optical-allocation.json")
    asset = (RUNTIME / allocation["geometry"]["asset_path"]).resolve()
    require(
        asset.is_relative_to(RUNTIME)
        and sha(asset) == registration["asset_sha256"] == allocation["asset_sha256"]
        and allocation["geometry"]["camera"] == registration["camera"],
        "original asset or camera changed",
    )
    return asset, registration


def original_slot(slot, registration):
    folder = CAPTURE / slot["id"]
    index = read(folder / "rgbd-index.json")
    check = read(folder / "clearance-gate.json")["checks"]
    (pre,) = [r for r in check if (r["skill"], r["phase"]) == ("LIFT", "PRE")]
    refusal = check[-1]
    joined = []
    for gate in (pre, refusal):
        (row,) = [r for r in index["rows"] if r["robot"]["frame_id"] == gate["frame_id"]]
        path = folder / row["file"]
        require(sha(path) == row["file_sha256"], "compressed original differs")
        frame = RGBDObservation.model_validate_json(gzip.decompress(path.read_bytes()))
        robot = row["robot"]
        h = robot["handoff"]
        require(
            robot["physics_step"] == h["current_step"] == gate["step"]
            and robot["native_last_command_seq"] == h["last_command_seq"]
            and robot["sim_time_s"] == frame.sim_time_s == robot["camera_encoder_sim_time_s"]
            and frame.frame_id == robot["frame_id"] == gate["frame_id"]
            and frame.checksum_sha256 == robot["checksum_sha256"] == gate["checksum_sha256"]
            and frame.model_dump(include=set(registration["camera"]), mode="json")
            == registration["camera"]
            and binding_error(h, "LIFT", gate["phase"], frame) is None,
            f"original pose or exposure does not bind {slot['id']}/{gate['step']}",
        )
        joined.append((gate, robot))
    require(
        pre["status"] == "CLEAR"
        and pre["step"] == slot["entry"]
        and refusal["status"] in {"UNKNOWN", "BLOCKED"}
        and refusal["reason"] == slot["reason"]
        and refusal["step"] == slot["rejection"],
        "original stop changed",
    )
    return joined


def angle_deg(left, right):
    return math.degrees(2 * math.acos(min(1.0, abs(float(np.dot(left, right))))))


def profile(reference, backend, goal):
    digest = hashlib.sha256()
    for values in (reference.positions, reference.velocities, reference.accelerations):
        digest.update(np.asarray(values, dtype="<f8").tobytes())
    scratch = mujoco.MjData(backend._model)
    scratch.qpos[:7] = reference.positions[-1]
    mujoco.mj_forward(backend._model, scratch)
    error = float(np.linalg.norm(scratch.site("tcp").xpos - goal))
    require(error <= 1e-9, "native final reference FK failed")
    return {
        "duration_s": reference.duration_s,
        "control_dt_s": reference.control_dt,
        "states": len(reference.positions),
        "position_velocity_acceleration_sha256": digest.hexdigest(),
        "peak_joint_velocity_rad_s": float(abs(reference.velocities).max()),
        "peak_joint_acceleration_rad_s2": float(abs(reference.accelerations).max()),
        "endpoint_fk_error_m": error,
    }


def preflight():
    asset, registration = inputs()
    settings = PLAN["command"]
    config = SimulatorConfig(physics_dt_s=1.0 / settings["physics_hz"])
    control_steps = round(config.control_dt_s / config.physics_dt_s)
    require(
        control_steps == settings["control_ticks"]
        and CartesianMotionReference.duration_s == PLAN["reference_seconds"]["original"]
        and CartesianMotionReference.settle_s == PLAN["reference_seconds"]["settle"],
        "original control grid changed",
    )
    model = mujoco.MjModel.from_xml_path(str(asset))
    cases = {}
    for slot in PLAN["slots"]:
        (entry, robot), (stop, final) = original_slot(slot, registration)
        data = mujoco.MjData(model)
        data.qpos[:7] = robot["joint_positions_rad"]
        data.qpos[7:9] = robot["finger_positions_m"]
        data.qvel[:7] = robot["joint_velocities_rad_s"]
        data.time = robot["sim_time_s"]
        mujoco.mj_forward(model, data)
        orientation = np.asarray(robot["tcp_quaternion_wxyz"])
        actual = np.empty(4)
        mujoco.mju_mat2Quat(actual, data.site("tcp").xmat)
        start, goal = robot["tcp_position_m"], entry["current"]["commanded_target_xyz_m"]
        closure = float(np.linalg.norm(data.site("tcp").xpos - start))
        angle = angle_deg(actual, orientation)
        require(
            closure <= 1e-5
            and angle <= 0.01
            and angle_deg(orientation, _DOWNWARD) <= 5.0
            and np.max(abs(data.qvel[:7])) <= 0.02
            and start[:2] == goal[:2],
            f"original LIFT PRE not restored {slot['id']}",
        )
        backend = SimpleNamespace(
            _model=model,
            _data=data,
            _mujoco=mujoco,
            _config=config,
            _joint_names=[f"joint{i}" for i in range(1, 8)],
            total_physics_steps=entry["step"],
        )
        variants = []
        for cls in (CartesianMotionReference, SlowerReference):
            reference = cls(
                backend,
                start,
                goal,
                orientation,
                control_steps=control_steps,
                timeout_s=settings["timeout_ms"] / 1000,
                max_velocity=settings["tcp_velocity_m_s"] / 0.3,
                max_acceleration=settings["acceleration_m_s2"] / 0.3,
            )
            variants.append(profile(reference, backend, goal))
        old, new = variants
        require(
            new["peak_joint_velocity_rad_s"] < old["peak_joint_velocity_rad_s"]
            and new["peak_joint_acceleration_rad_s2"] < old["peak_joint_acceleration_rad_s2"],
            "candidate did not lower reference derivatives",
        )
        cases[slot["id"]] = {
            "entry_step": entry["step"],
            "entry_checksum_sha256": entry["checksum_sha256"],
            "original_stop_step": stop["step"],
            "original_stop_reason": stop["reason"],
            "original_stop_lift_m": final["tcp_position_m"][2] - start[2],
            "initial_tcp_m": start,
            "target_xyz_m": goal,
            "reconstructed_fk_difference_m": closure,
            "reconstructed_fk_difference_deg": angle,
            "reference": old,
            "slower_reference": new,
            "cap_only": {
                str(cap): (
                    "same_reference"
                    if old["peak_joint_velocity_rad_s"] <= cap / 0.3
                    else "constructor_rejects"
                )
                for cap in PLAN["counter_only_caps_m_s"]
            },
        }
    return {
        "cases": cases,
        "plan_sha256": sha(PLAN_PATH),
        "capture_seal_sha256": sha(SEAL_PATH),
        "mujoco": mujoco.__version__,
        "physics_steps": 0,
        "camera_calls": 0,
    }


def prohibited(*_args, **_kwargs):
    raise AssertionError("CPU preflight cannot integrate or render")


def check_cpu():
    with patch.multiple(
        mujoco,
        mj_step=prohibited,
        mj_step1=prohibited,
        mj_step2=prohibited,
        Renderer=prohibited,
        mjr_render=prohibited,
    ):
        return preflight()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write(args.output, check_cpu())
