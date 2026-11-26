"""Cold necessary handoff checks on four sealed B03 exposure states."""

# ruff: noqa: E402
import argparse
import gzip
import json
import os
import subprocess
import sys
from copy import deepcopy
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
from scripts.graduation.perception_io import ROOT, read, sha

HERE = Path(__file__).resolve().parent
PLAN = read(HERE / "plan.json")
OUT = ROOT / PLAN["output"]
ARCHIVE = ROOT / PLAN["archive"]
ASSET = ROOT / PLAN["asset"]
ALLOCATION = ROOT / PLAN["allocation"]
CALIBRATION = ROOT / PLAN["calibration"]
DYNAMIC = HERE.parent / "round-g1-release-fit03-dwell-20261126"
sys.path.insert(0, str(DYNAMIC))

from native_dwell import inputs, optics, store_json
from read_dwell import fixture
from replay_exposure import checked_witness
from scripts.graduation.g1_complete_cv_clearance import BAND, _covers
from scripts.graduation.g1_complete_cv_geometry import Box, Model
from scripts.graduation.g1_complete_cv_handoff import (
    GROUPS,
    SCALES,
    binding_error,
    features,
    geometry,
    handoff_motion,
    nearby_rows,
    profile,
    required_delays,
)
from scripts.graduation.g1_complete_cv_handoff_optics import rigid_pose

from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend


def require(ok, message):
    if not ok:
        raise ValueError(message)


def verify_all_inputs():
    require(
        subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        == PLAN["baseline"],
        "worktree differs from the registered baseline",
    )
    for key, expected in PLAN["inputs_sha256"].items():
        require(sha(ROOT / key) == expected, f"changed source: {key}")
    seal = read(ARCHIVE / "capture-seal.json")
    require(
        seal["complete"] and all(sha(ARCHIVE / k) == v for k, v in seal["members"].items()),
        "dynamic capture seal changed",
    )
    require(
        read(ARCHIVE / "registration.json")["program_sha256"] == sha(DYNAMIC / "native_dwell.py"),
        "dynamic capture no longer binds its original program",
    )
    return seal


def one_tick_rows(file, requested_ticks):
    picked = {}
    with gzip.open(file, "rt") as stream:
        for line in stream:
            source = json.loads(line)
            tick = source["tick"]
            if tick in requested_ticks:
                require(tick not in picked, "duplicate source physics step")
                picked[tick] = {
                    key: source[key]
                    for key in (
                        "q",
                        "dq",
                        "control",
                        "arm_target",
                        "open_command",
                        "tick",
                        "time_s",
                    )
                }
    require(set(picked) == requested_ticks, "missing source physics step")
    return picked


def command_prefix(commands, actions, observable, role, step):
    if role == "PRE":
        place, release = actions[-2:]
        require(
            place["skill"] == "PLACE"
            and place["success"]
            and place["return_step"] == step
            and release["skill"] == "RELEASE"
            and release["start_step"] == step,
            "no real PLACE-to-RELEASE boundary at this clock",
        )
        hold, opened = commands[-2:]
        require(
            [r["type"] for r in commands[-3:]] == ["joint_target", "hold_current_joints", "gripper"]
            and all(r["accepted"] and r["physics_step"] == step for r in commands[-3:])
            and opened["target_open"] is True
            and observable["gripper"][-1] == opened,
            "terminal operations do not authenticate true PRE order",
        )
        require(hold["command_seq"] == opened["command_seq"] - 1, "hold/open changed")
        prefix = commands[:-2]
    else:
        require(
            actions[-1]["skill"] == "RELEASE"
            and actions[-1]["success"]
            and step == actions[-1]["return_step"] + 240
            and all(r["physics_step"] <= step for r in commands),
            "last DWELL is not the real release endpoint",
        )
        prefix = commands
    arm = [
        r for r in prefix if r["accepted"] and r["type"] in {"hold_current_joints", "joint_target"}
    ]
    grip = next(r for r in reversed(prefix) if r["accepted"] and r["type"] == "gripper")
    require(
        len(arm) >= 2 and all(not r["reason"].startswith("queued_") for r in arm[-2:]),
        "native arm goal/actuator delay cannot be reconstructed",
    )
    return prefix[-1]["command_seq"], arm[-2:], grip


def actuator_values(slot):
    raw = slot["physical_robot"]
    command_seq, records, grip = slot["command_seq"], slot["arm_commands"], slot["gripper_command"]
    # Dispatch the actual method with its minimum read-only interface. This cannot step MuJoCo.
    readonly = SimpleNamespace(_require_loaded=lambda: None, _command_records=records)
    state = MuJoCoPhysicsBackend.get_joint_command_state(readonly)
    prev, tail = records
    goal = tail["applied_target_positions_rad"]
    dq = np.zeros(7)
    if tail["type"] == "joint_target":
        dt = tail["sim_time_s"] - prev["sim_time_s"]
        if dt > 0:
            dq = (np.array(goal) - prev["applied_target_positions_rad"]) / dt
        else:
            require(
                dt == 0 and goal == prev["applied_target_positions_rad"],
                "conflicting command clock",
            )
    open_state = slot["role"] == "DWELL-30"
    require(
        np.array_equal(dq, state.velocity_rad_s)
        and tuple(goal) == state.positions_rad
        and grip["target_open"] == raw["open_command"] == open_state
        and command_seq == (grip["command_seq"] if open_state else tail["command_seq"])
        and len(raw["control"]) == len(raw["q"]) == len(raw["dq"]) == 9
        and raw["tick"] == slot["robot"]["physics_step"]
        and raw["time_s"]
        == slot["robot"]["sim_time_s"]
        == slot["robot"]["camera_encoder_sim_time_s"],
        "measured control, goal, opened state or actuator velocity did not join",
    )
    require(
        grip["physics_step"] == slot["robot"]["last_accepted_gripper_command_step"]
        and grip["target_open"] == slot["robot"]["last_accepted_gripper_open"],
        "real frame's gripper state differs",
    )
    return {
        "command_seq": command_seq,
        "goal": goal,
        "velocity": dq.tolist(),
        "applied_arm": raw["control"][:7],
        "applied_fingers": raw["control"][7:9],
    }


def prepare():
    verify_all_inputs()
    require(not OUT.exists() and OUT.resolve() == OUT, "cold allocation already used")
    archive_seal = sha(ARCHIVE / "capture-seal.json")
    replay = read(ARCHIVE.parent / "exposure-replay.json")
    optical_path = ARCHIVE.parent / "prediction.primary.json"
    predicted = read(optical_path)
    require(
        replay["complete"]
        and replay["capture_sha256"] == archive_seal
        and predicted["capture_seal_sha256"] == archive_seal,
        "predecessor witness or optical prediction used a different capture",
    )
    source_codes = [("b1", "PRE"), ("b0", "DWELL-30"), ("b1", "DWELL-30"), ("b0", "PRE")]
    groups = {}
    for code in PLAN["native_groups"]:
        folder = ARCHIVE / code
        index = {record["role"]: record for record in read(folder / "frames.json")}
        catalog = [index[role] for role in PLAN["input_roles"]]
        receipt = read(folder / "native.json")
        observable = read(folder / "observable.json")
        rows = one_tick_rows(
            folder / "physical.jsonl.gz", {r["robot"]["physics_step"] for r in catalog}
        )
        groups[code] = (folder, index, receipt, observable, rows)
    OUT.mkdir(parents=True)
    catalog, keymap = [], {}
    for i, (code, role) in enumerate(source_codes):
        folder, index, receipt, observable, physical = groups[code]
        row = index[role]
        robot = row["robot"]
        file = folder / row["path"]
        step = robot["physics_step"]
        key = f"c{i}"
        keymap[key] = {"source_group": code, "role": role, "tick": step, "file_sha256": sha(file)}
        (event,) = [e for e in observable["events"] if e.get("frame_id") == robot["frame_id"]]
        (witness,) = [s for s in replay["routes"][code]["shots"] if s["role"] == role]
        checked_witness(code, row, event, witness)
        command_seq, arm, gripper = command_prefix(
            receipt["commands"], receipt["actions"], observable, role, step
        )
        (pose,) = [x["pose"] for x in predicted["routes"][code]["rows"] if x["role"] == role]
        require(sha(file) == row["sha256"], "RGB-D packet changed before blinding")
        target = OUT / f"{key}.json.gz"
        with target.open("xb") as stream:
            stream.write(file.read_bytes())
        visible = {
            "key": key,
            "role": role,
            "frame_file": target.name,
            "frame_sha256": sha(target),
            "robot": robot,
            "command_seq": command_seq,
            "gripper_command": gripper,
            "arm_commands": arm,
            "physical_robot": physical[step],
            "pose_baseline": pose,
            "witness_camera_hash": witness["camera_state_sha256"],
            "witness_encoder_f64": witness["encoder_f64_hex"],
            "observable_reset": {"resets": observable["resets"], "episode": observable["episode"]},
        }
        visible["registered_actuation"] = actuator_values(visible)
        catalog.append(visible)
    store_json(OUT / "blinded.json", {"source_capture_sha256": archive_seal, "frames": catalog})
    store_json(OUT / "source-key.json", keymap)
    members = {p.name: sha(p) for p in sorted(OUT.iterdir())}
    store_json(
        OUT / "preflight-seal.json",
        {
            "inputs": members,
            "program_sha256": sha(Path(__file__).resolve()),
            "plan_sha256": sha(HERE / "plan.json"),
            "source_capture_sha256": archive_seal,
        },
    )


def optical_check(frame, robot, measured, identity, geom):
    return (
        frame.frame_id == robot["frame_id"]
        and frame.checksum_sha256 == robot["checksum_sha256"]
        and frame.sim_time_s == robot["sim_time_s"]
        and identity.matches(frame, measured, geom, robot["physics_step"])
    )


def scope_for_math(skill, slot, frame):
    current = slot["physical_robot"]
    actuators = actuator_values(slot)
    require(
        actuators == slot["registered_actuation"],
        "sealed independent actuator reconstruction differs",
    )
    source = "PLACE" if skill == "RELEASE" else "RELEASE"
    return {
        "source_skill": source,
        "destination_skill": skill,
        "prior_end_step": current["tick"],
        "entry_step": current["tick"],
        "current_step": current["tick"],
        "entry_command_seq": actuators["command_seq"],
        "last_command_seq": actuators["command_seq"],
        "entry_gripper_open": current["open_command"],
        "entry_frame_id": frame.frame_id,
        "entry_checksum_sha256": frame.checksum_sha256,
        "entry_target_rad": actuators["applied_arm"],
        "entry_finger_target_m": actuators["applied_fingers"],
        "effective_joint_target_rad": actuators["applied_arm"],
        "effective_finger_target_m": actuators["applied_fingers"],
        "entry_effective_arm_goal_rad": actuators["goal"],
        "entry_native_arm_velocity_rad_s": actuators["velocity"],
        "entry_joint_positions_rad": current["q"][:7],
        "entry_joint_velocities_rad_s": current["dq"][:7],
        "entry_finger_positions_m": current["q"][7:9],
        "entry_finger_velocities_m_s": current["dq"][7:9],
    }


def calibration_maps():
    manifest = read(CALIBRATION / "manifest.json")
    require(
        manifest["asset_sha256"] == sha(ASSET) and manifest["optical_band_m"] == BAND,
        "wrong frozen calibration authority",
    )
    views = {}
    for label in ("panel-primary", "panel-start"):
        row = manifest["maps"][label]
        path = CALIBRATION / row["depth_file"]
        require(
            path.parent.resolve() == CALIBRATION and sha(path) == row["depth_sha256"],
            "calibration map digest or parent differs",
        )
        depth = np.load(path, allow_pickle=False)
        cam = row["camera"]
        require(depth.shape == (cam["height"], cam["width"]), "invalid calibration dimensions")
        views[label] = cam, depth
    return views


def volume_callback(model, maps, floor_permitted):
    floor = model.table.c[2] + model.table.h[2]

    def check(box, pad):
        c = np.asarray(pad)
        if c.shape != (3,) or not np.isfinite(c).all() or np.any(c < 0):
            return False
        hull = Box(box.name, box.c, box.h + abs(box.r).T @ c, box.r)
        corners = hull.corners()
        active = box.name == "object_geom" and floor_permitted
        if active:
            corners[:, 2] = np.maximum(corners[:, 2], floor)
        return any(
            _covers(corners, cam, depth, 2 * BAND if active else 0.0)
            for cam, depth in maps.values()
        )

    return check


def profile_matches(skill, scope, pose, model):
    refs = [
        ref["features"]
        for ref in profile()["stages"][skill]["references"]
        if ref["open"] is scope["entry_gripper_open"]
    ]
    require(bool(refs), "missing original opening-class reference")
    q, dq, f, df = [
        np.asarray(scope[f"entry_{suffix}"])
        for suffix in (
            "joint_positions_rad",
            "joint_velocities_rad_s",
            "finger_positions_m",
            "finger_velocities_m_s",
        )
    ]
    if pose is None:
        return {
            "grouped_squared_norm": None,
            "matched_reference_indices": [],
            "ref_count": len(refs),
        }
    center, rot = np.asarray(pose["center_m"]), np.asarray(pose["rotation"])
    _, _, tcp, wrist = geometry(model).solids(q[None], f[None], center[None], rot[None])
    state = features(
        q,
        dq,
        f,
        df,
        np.array(scope["entry_target_rad"]),
        np.array(scope["entry_effective_arm_goal_rad"]),
        np.array(scope["entry_native_arm_velocity_rad_s"]),
        np.array(scope["entry_finger_target_m"]),
        tcp[0],
        wrist[0],
        center,
        rot,
    )
    anchor = np.asarray(pose["anchor_object_m"])
    aerr, berr = np.asarray(pose["anchor_error_object_m"]), np.asarray(pose["basis_error_object"])
    axes = abs(wrist[0].T @ rot)
    error = np.zeros_like(state)
    error[-12:-9] = axes @ (aerr + berr @ abs(anchor))
    error[-9:] = (axes @ berr).ravel()
    scale = np.repeat(SCALES, GROUPS)
    upper = (abs(np.array(refs) - state) + error) / scale
    values = np.column_stack(
        [part.max(axis=1) for part in np.split(upper, np.cumsum(GROUPS)[:-1], axis=1)]
    )
    score = np.sum(values**2, axis=1)
    matches = nearby_rows(state, error, refs, scale, GROUPS)
    require(
        matches == np.flatnonzero(score <= 1).tolist(), "distance audit differs from frozen domain"
    )
    return {
        "grouped_squared_norm": score.tolist(),
        "matched_reference_indices": matches,
        "ref_count": len(refs),
        "per_group_max_normalized": values.tolist(),
    }


def profile_controls():
    stage_results = {}
    for skill in ("RELEASE", "RETREAT"):
        stage = profile()["stages"][skill]
        registered = 242 if skill == "RELEASE" else 9
        require(
            len(required_delays(skill)) == stage["delays"] == registered,
            "full original handoff stop delays not present",
        )
        scale = np.repeat(SCALES, GROUPS)
        reference = np.asarray(stage["references"][0]["features"])
        zeros = np.zeros_like(reference)
        require(
            nearby_rows(reference, zeros, [reference], scale, GROUPS) == [0],
            "original self-reference refused",
        )
        outside = reference.copy()
        outside[0] += 2 * scale[0]
        require(
            not nearby_rows(outside, zeros, [reference], scale, GROUPS),
            "out-of-domain control admitted",
        )
        stage_results[skill] = registered
    return stage_results


def blinded_read(output):
    preflight_path = OUT / "preflight-seal.json"
    preflight = read(preflight_path)
    bound = sha(preflight_path)
    require(
        preflight["program_sha256"] == sha(Path(__file__).resolve())
        and preflight["plan_sha256"] == sha(HERE / "plan.json")
        and preflight["source_capture_sha256"]
        == PLAN["inputs_sha256"][PLAN["archive"] + "/capture-seal.json"],
        "blinded registration does not match this plan",
    )
    visible_path = OUT / "blinded.json"
    require(
        sha(visible_path) == preflight["inputs"][visible_path.name], "allowlisted inputs changed"
    )
    visible = read(visible_path)
    allowed = {
        ALLOCATION,
        ALLOCATION.parents[1] / "allocation.json",
        ASSET,
        inputs.expand("{D}/runtime-build.json"),
        inputs.expand("{D}/scripts/graduation/g1_visibility_vision.py"),
        *(CALIBRATION / name for name in ("manifest.json", "panel-primary.npy", "panel-start.npy")),
        output.resolve(),
        *(OUT / row["frame_file"] for row in visible["frames"]),
    }
    private = ARCHIVE.parents[1].parent

    def audit(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            target = Path(os.fsdecode(args[0])).resolve()
            if target.is_relative_to(private) and target not in allowed:
                raise PermissionError("outside blinded exposure inputs")

    sys.addaudithook(audit)
    for test in (OUT / "source-key.json", ARCHIVE / "b1/physical.jsonl.gz"):
        try:
            test.open("rb").close()
        except PermissionError:
            continue
        raise ValueError("blind read admitted private truth or route labels")
    measure = optics.sealed_optics()
    maps = calibration_maps()
    model = Model(ASSET)
    delay_controls = profile_controls()
    results = {}
    for slot in visible["frames"]:
        skill = "RELEASE" if slot["role"] == "PRE" else "RETREAT"
        file = OUT / slot["frame_file"]
        require(
            sha(file) == slot["frame_sha256"] == preflight["inputs"][file.name],
            "original RGB-D packet hash changed",
        )
        frame = inputs.packet(file)
        identity, geometry_config = fixture(slot["observable_reset"])
        measured = measure(frame, geometry_config)
        robot = slot["robot"]
        require(
            optical_check(frame, robot, measured, identity, geometry_config),
            "original exposure unbound",
        )
        require(
            not optical_check(
                frame, robot | {"frame_id": "wrong"}, measured, identity, geometry_config
            ),
            "foreign frame negative failed",
        )
        require(
            not optical_check(
                frame, robot | {"checksum_sha256": "0" * 64}, measured, identity, geometry_config
            ),
            "wrong frame checksum negative failed",
        )
        pose = rigid_pose(
            frame, measured, geometry_config, identity=identity, physics_step=robot["physics_step"]
        )
        require(
            pose == slot["pose_baseline"], "independent pose differs from frozen blind prediction"
        )
        scope = scope_for_math(skill, slot, frame)
        changed = scope | {
            "effective_joint_target_rad": [v + 0.01 for v in scope["entry_target_rad"]]
        }
        require(
            binding_error(changed, skill, "PRE", frame) == "stage_entry_source_or_drive_changed",
            "fixed actual drive negative failed",
        )
        swapped = deepcopy(slot)
        swapped["registered_actuation"]["velocity"][0] += 0.01
        require(
            optics.rejected(scope_for_math, skill, swapped, frame),
            "manipulated entry speed accepted",
        )
        if skill == "RELEASE":
            later = slot | {"gripper_command": slot["gripper_command"] | {"target_open": True}}
            require(
                optics.rejected(actuator_values, later), "moving true exposure past OPEN accepted"
            )
        center = measured.get("object_center_world_m")
        region_hint = center is not None and np.all(
            abs(np.asarray(center)[:2] - model.region.c[:2]) <= model.region.h[:2]
        )
        metrics = profile_matches(skill, scope, pose, model)
        q, dq, f, df = [
            np.asarray(scope[f"entry_{suffix}"])
            for suffix in (
                "joint_positions_rad",
                "joint_velocities_rad_s",
                "finger_positions_m",
                "finger_velocities_m_s",
            )
        ]

        frozen = partial(
            handoff_motion,
            frame,
            measured,
            scope,
            skill,
            "PRE",
            q,
            f,
            dq,
            df,
            None,
            None,
            model,
            optical=pose,
        )
        require(
            handoff_motion(
                frame,
                measured,
                scope,
                skill,
                "PRE",
                q,
                f,
                dq,
                df,
                None,
                None,
                model,
                optical=None,
                volume_check=volume_callback(model, maps, False),
            )["reason"]
            == "no_current_handoff_pose_interval",
            "missing current certification accepted",
        )
        strict = frozen(volume_check=volume_callback(model, maps, False))
        conditional = (
            frozen(volume_check=volume_callback(model, maps, True)) if region_hint else None
        )
        if pose is not None and not metrics["matched_reference_indices"]:
            require(
                strict["reason"] == "outside_continuous_handoff_state_domain",
                "domain metrics and frozen verdict disagree",
            )
        results[slot["key"]] = {
            "source_role": slot["role"],
            "tick": robot["physics_step"],
            "frame_id": frame.frame_id,
            "inferred_skill_scope": skill,
            "pose_method": pose["method"] if pose else None,
            "actuation": slot["registered_actuation"],
            "strict": strict,
            "conditional_floor": conditional,
            "domain": metrics,
            "region_centroid_hint": bool(region_hint),
            "authorized_live_pre": False,
        }
    store_json(
        output,
        {
            "preflight_sha256": bound,
            "delay_controls": delay_controls,
            "slots": results,
            "all_checks_are_necessary_only": True,
            "actual_stage_passes": 0,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "cold"))
    parser.add_argument("output", type=Path, nargs="?")
    args = parser.parse_args()
    cv2.setNumThreads(1)
    if args.mode == "prepare":
        prepare()
    else:
        blinded_read(args.output)


if __name__ == "__main__":
    main()
