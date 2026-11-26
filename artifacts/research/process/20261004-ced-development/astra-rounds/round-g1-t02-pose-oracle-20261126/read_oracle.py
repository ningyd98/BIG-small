"""Compare the original t02 relation with a single offline physical-pose oracle."""
import argparse
import json
import os
import sys
from copy import deepcopy
from dataclasses import replace
from functools import partial
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from scripts.graduation import g1_complete_cv_clearance as clearance
from scripts.graduation import g1_complete_cv_handoff_optics as optics
from scripts.graduation import g1_complete_cv_payload_observation as payload
from scripts.graduation.dynamic_vision import plain
from scripts.graduation.g1_complete_cv_optical_identity import bind_allocation
from scripts.graduation.perception_io import sha

from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD
from cloud_edge_robot_arm.vision.observations import RGBDObservation

HERE = Path(__file__).resolve().parent
ROOT = Path.cwd()
CV = ROOT / "experiments/results/g1-complete-cv-repair-20261125"
CASE = CV / "batches/train-full-04/cvfix-t02"
CURRENT = ROOT / "experiments/results/g1-lift-registered-volume-20261126/offline-fit-01"
DIRECTORIES = {"cv": CV, "case": CASE, "current": CURRENT, "rounds": HERE.parent, "repo": ROOT}
ROLES = (
    (1264, "GRASP/PRE", "0151"),
    (1504, "GRASP/POST", "0152"),
    (1504, "LIFT/PRE", "0152"),
    (1504, "LIFT/feedback", "0154"),
    (1512, "LIFT/feedback", "0155"),
    (1520, "LIFT/feedback", "0156"),
)
ARMS = ("original", "oracle_exact", "oracle_profile")
sys.path.insert(0, str(HERE.parent / "round-g1-continuous-payload-observation-20261125"))
from read_pose_coverage import native_marker  # noqa: E402


def read(path):
    return json.loads(path.read_bytes())


PLAN = read(HERE / "plan.json")


def require(valid, reason):
    if not valid:
        raise ValueError(reason)


def canonical(data):
    return (json.dumps(plain(data), sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def write(path, data):
    path.parent.mkdir(exist_ok=True, parents=True)
    with path.open("xb") as stream:
        stream.write(canonical(data))


def preceding_jaw(commands, seq):
    return next((j for j in reversed(commands) if j["type"] == "gripper"
                 and j["accepted"] and j["command_seq"] <= seq), {})


def inputs():
    for reference, expected in PLAN["sha256"].items():
        folder, name = reference.split("/", 1)
        path = DIRECTORIES[folder] / name
        require(path.resolve().is_relative_to(ROOT) and sha(path) == expected,
                f"frozen input changed: {reference}")
    for name, expected in read(CURRENT / "sealed.json").items():
        require(sha(CURRENT / name) == expected, f"earlier whole gate seal member changed: {name}")

    folder = CASE / "instance"
    alloc = read(CASE / "allocation.json")
    index = read(folder / "pixel-index.json")
    scene = alloc["geometry"]
    asset = ROOT / scene["asset_path"]
    run = read(folder / "run.json")
    truth = read(folder / "offline-truth.json")
    source_rows = read(folder / "local-clearance.json")["rows"]
    reset = next(r for r in read(folder / "reset-observed.json") if r["phase"] == "END")
    camera = Path(alloc["calibration_directory"])
    identity = bind_allocation(
        (CASE / "allocation.json").read_bytes(),
        allocation_sha256=index["allocation_sha256"],
        generation_sha256=alloc["runtime_build_sha256"],
        calibration_sha256=sha(camera / "manifest.json"),
        asset_sha256=sha(asset),
        reset_scene_id=reset["parameters"]["requested"]["scenario_id"],
        reset_episode_id=reset["episode_id"],
    )
    measure, _ = native_marker(alloc["runtime_build_sha256"])
    require(not payload._profile()["single_id8_red_print"]["enabled"], "red certificate enabled")
    require(truth["asset_sha256"] == sha(asset) and truth["allocation_sha256"] ==
            index["allocation_sha256"] and truth["episode"] == identity.episode_id,
            "truth allocation differs")
    archived = read(CURRENT / "t02.json")["rows"]
    index_by_id = {r["frame_id"]: r for r in index["frames"]}
    local = {(r["skill"], r["phase"], r["frame_id"]): r for r in source_rows}
    raw_commands = read(folder / "backend-commands.json")
    commands = [r for r in raw_commands
                if r["type"] == "gripper" and r["accepted"]]
    require(all(type(r["target_open"]) is bool and type(r["physics_step"]) is int
                for r in commands), "incomplete accepted gripper command")
    close, = commands
    require((close["command_seq"], close["physics_step"], close["target_open"]) ==
            (233, 1264, False), "original gripper command changed")
    denied = {**close, "command_seq": 232, "accepted": False}
    require(preceding_jaw([denied, close], 232) == {}, "jaw control used denied or future command")
    actions = {a["skill"]: a for a in run["actions"]}
    recorded_roles = [(r["label"], r["frame_id"]) for r in run["frame_roles"]
                      if r["label"] in {role for _, role, _ in ROLES}]
    require(recorded_roles[:len(ROLES)] ==
            [(r["phase"], r["frame"]) for r in archived[:len(ROLES)]], "archive role order differs")

    result = []
    for prior, (tick, role, filename) in zip(archived[:len(ROLES)], ROLES, strict=True):
        skill, phase = role.upper().split("/")
        indexed = index_by_id[prior["frame"]]
        require(indexed["file"] == f"frames/{filename}.json" and
                indexed["physics_step"] == prior["step"] == tick and prior["phase"] == role and
                sha(folder / indexed["file"]) ==
                indexed["file_sha256"] == prior["native_frame_sha256"], "archived frame order")
        frame = RGBDObservation.model_validate_json((folder / indexed["file"]).read_bytes())
        item = local[("LIFT", "PRE", frame.frame_id) if role == "GRASP/POST" else
                     (skill, phase, frame.frame_id)]
        robot = item["robot"]
        require(frame.frame_id == robot["frame_id"] == prior["frame"] and
                frame.checksum_sha256 == robot["checksum_sha256"] == indexed["checksum_sha256"] and
                frame.sim_time_s == robot["sim_time_s"] == robot["camera_encoder_sim_time_s"] and
                robot["physics_step"] == tick, "unbound exposure encoder")
        seq = robot["handoff"]["last_command_seq"]
        command = preceding_jaw(raw_commands, seq)
        require(command == ({} if role == "GRASP/PRE" else close),
                f"wrong causally available gripper command: {role} {tick}")
        parent = actions["APPROACH" if role == "GRASP/PRE" else "GRASP"]
        packet = dict(
            robot, native_last_command_seq=seq,
            last_accepted_gripper_open=command.get("target_open"),
            last_accepted_gripper_command_step=command.get("physics_step"),
            previous_native_successful_skill=parent["skill"],
            previous_native_return_step=parent["controller_return_step"],
            previous_native_terminal_step=None if role == "GRASP/POST" else parent["end_step"],
        )
        marker = measure(frame, scene)
        require(identity.matches(frame, marker, scene, tick), "unregistered measured marker")
        result.append({"frame": frame, "marker": marker, "robot": packet, "skill": skill,
                       "phase": phase, "target": item["target_xyz"], "step": tick,
                       "previous": prior["current"]})
    sample, = [r for r in truth["samples"] if r["physics_step"] == PLAN["target_step"]]
    require(sample["episode_id"] == identity.episode_id and
            sample["sim_time_s"] == result[4]["frame"].sim_time_s, "unbound physical label")
    late = archived[-1]
    require(late["step"] == 2112 and late["current"]["reason"] == "unregistered_near_surface"
            and late["current"]["depth"]["unmatched_pixels_uv"] == [[171, 122]], "2112 boundary")
    return result, scene, identity, asset, camera, sample, late


def oracle(target, scene, truth, mode):
    frame, marker = target["frame"], target["marker"]
    center = np.asarray(truth["object_geom_position_m"])
    rotation = np.asarray(truth["object_geom_rotation_row_major"]).reshape(3, 3)
    require(center.shape == (3,) and np.isfinite(center).all() and np.isfinite(rotation).all()
            and np.allclose(rotation.T @ rotation, np.eye(3), rtol=0, atol=1e-12)
            and abs(np.linalg.det(rotation) - 1) <= 1e-12, "invalid physical pose")
    measured = optics.measured_pose(frame, marker, scene)
    require(measured is not None and measured["method"] == "id8" and measured["ids"] == [8],
            "original single-board geometry changed")
    lever = np.asarray(measured["anchor_object_m"])
    profile = optics.CALIBRATION["id8_opposite_edges"]
    anchor = np.asarray(profile["anchor"] if mode == "oracle_profile" else np.zeros(3))
    basis = np.asarray(profile["basis"] if mode == "oracle_profile" else np.zeros((3, 3)))
    angle = 2 * np.arcsin(min(1.0, np.linalg.norm(basis) / (2 * np.sqrt(2))))
    return {
        "frame_id": frame.frame_id, "checksum_sha256": frame.checksum_sha256, "method": mode,
        "ids": [8], "center_m": center.tolist(), "rotation": rotation.tolist(),
        "center_world_m": center.tolist(), "rotation_object_to_world": rotation.tolist(),
        "anchor_object_m": lever.tolist(), "anchor_world_m": (center + rotation @ lever).tolist(),
        "anchor_error_object_m": anchor.tolist(), "basis_error_object": basis.tolist(),
        "center_error_m": float(np.linalg.norm(anchor + basis @ abs(lever))),
        "rotation_error_rad": float(angle),
    }


def observe(row, scene, identity, history, optical):
    return payload.payload_observation(
        row["frame"], row["marker"], scene, row["robot"], row["skill"], row["phase"],
        identity=identity, physics_step=row["step"], history=history, optical=optical,
    )


def original_optical(row, scene, identity):
    return optics.rigid_pose(
        row["frame"], row["marker"], scene, identity=identity, physics_step=row["step"]
    )


def compare_observation(row, answer):
    previous = row["previous"].get("payload_observation", row["previous"])
    require(plain(answer) == previous, f"frozen observer differs at {row['phase']} {row['step']}")


def gap_details(row, pose, history, asset, relation):
    rig = payload._model(str(asset))
    robot = row["robot"]
    tcp, wrist, _ = rig.forward(robot["camera_joint_positions_rad"])
    center = np.asarray(pose["center_m"])
    rotation = np.asarray(pose["rotation"])
    last = history["recent_held"]
    ev = relation["evidence"]
    return {
        "history_age_steps": row["step"] - last["step"],
        "relative_shift_m": float(np.linalg.norm((center - tcp) @ wrist - last["relative"])),
        "relative_rotation_frobenius": float(np.linalg.norm(wrist.T @ rotation - last["rotation"])),
        "abs_jaw_center_offset_m": float(abs((center - tcp) @ wrist[:, 1])),
        "max_abs_inner_gap_limit_m": max(0.0025, ev["finger_axis_uncertainty_m"] + 0.0008),
    }


def negative_controls(row, scene, identity, pose, before):
    variants = {
        "bad_pose_frame": (row, {**pose, "frame_id": "foreign"}, before, identity),
        "bad_pose_checksum": (row, {**pose, "checksum_sha256": "0" * 64}, before, identity),
        "bad_episode": (row, pose, before, replace(identity, episode_id="foreign")),
        "cleared_history": (row, pose, {}, identity),
        "reversed_history": (row, pose, {**before, "last_step": row["step"] + 1}, identity),
        "opened": ({**row, "robot": dict(row["robot"], last_accepted_gripper_open=True)},
                   pose, before, identity),
    }
    evidence = {}
    for name, (item, data, history, binding) in variants.items():
        observed = observe(item, scene, binding, deepcopy(history), data)
        require(observed["relation"] != "held", f"false-held negative control: {name}")
        evidence[name] = observed["evidence"].get("reason") or observed["relation"]
    return evidence


def cpu(loaded):
    rows, scene, identity, asset, _, truth, late = loaded
    history = {}
    prefix = []
    for row in rows[:4]:
        got = observe(row, scene, identity, history, original_optical(row, scene, identity))
        compare_observation(row, got)
        prefix.append([row["step"], f"{row['skill']}/{row['phase']}", got["relation"]])
    require([p[-1] for p in prefix] == ["unknown", "held", "held", "held"], "held history absent")
    target, later = rows[4:]
    outputs = {}
    for mode in ARMS:
        track = deepcopy(history)
        optical = None if mode == "original" else oracle(target, scene, truth, mode)
        if mode == "original":
            require(original_optical(target, scene, identity) is None, "original refusal changed")
        relation = observe(target, scene, identity, track, optical)
        follow = observe(later, scene, identity, track, original_optical(later, scene, identity))
        if mode == "original":
            compare_observation(target, relation)
            compare_observation(later, follow)
        outputs[mode] = {
            "relation_1512": relation, "archived_followup_1520": follow,
            "predicate_details": gap_details(target, optical, history, asset, relation) if optical
            else None,
        }
    controls = negative_controls(target, scene, identity, oracle(target, scene, truth, ARMS[-1]),
                                 history)
    return {
        "classification": "isolated_offline_oracle_not_an_online_certificate",
        "prefix": prefix, "original_late_2112": late["current"]["reason"],
        "known_late_obstacle_uv": late["current"]["depth"]["unmatched_pixels_uv"],
        "observed_truth_contacts_1512": truth["contact_pairs"], "negative_controls": controls,
        "cases": outputs, "new_exposures": 0, "integration": 0, "robot_only_renders": 0,
    }


def selected_pose(probe, _marker, _geometry, *, identity, physics_step, row, pose):
    require(probe is row["frame"] and identity is not None and physics_step == PLAN["target_step"],
            "unexpected oracle call")
    return pose


def whole(loaded, cpu_result, journal):
    import mujoco
    from OpenGL import GL
    from scripts.graduation import g1_complete_cv_carried_surface as carried
    from scripts.graduation.g1_visibility_trials import device

    from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera

    require(mujoco.__version__ == "3.3.7", "unexpected MuJoCo")
    require(os.environ.get("MUJOCO_GL") == os.environ.get("PYOPENGL_PLATFORM") == "egl",
            "registered EGL required")
    require(any(cpu_result["cases"][k]["relation_1512"]["relation"] == "held" for k in ARMS[1:]),
            "no relation passes to verify under the full gate")
    rows, scene, identity, asset, camera, truth, _ = loaded
    expected_gl = read(camera / "manifest.json")["renderer"]
    render_count = {}
    results = {}

    class RegisteredDepth(clearance.RobotDepthReference):
        def project(self, joints, fingers):
            require(render_count[mode] < 4 and sum(render_count.values()) <
                    PLAN["max_robot_only_renders"], "registered render cap")
            render_count[mode] += 1
            value = super().project(joints, fingers)
            actual = {k: GL.glGetString(v).decode() for k, v in (
                ("renderer", GL.GL_RENDERER), ("vendor", GL.GL_VENDOR), ("version", GL.GL_VERSION),
            )}
            require(actual == expected_gl, "original EGL fingerprint changed")
            return value

    def forbidden(*args, **kwargs):
        raise RuntimeError("unregistered camera projection, exposure or physics call")

    lock = ROOT / "experiments/results/g1-visibility-pose-repair-20261124"
    with (
        device(lock),
        patch.object(clearance, "RobotDepthReference", RegisteredDepth),
        patch.object(carried.CarriedSurface, "project", forbidden),
        patch.object(mujoco, "mj_step", forbidden),
        patch.object(mujoco, "mj_step1", forbidden),
        patch.object(mujoco, "mj_step2", forbidden),
        patch.object(MuJoCoRGBDCamera, "_capture", forbidden),
    ):
        for mode in ARMS:
            render_count[mode] = 0
            cert = clearance.LocalClearance(
                scene, asset, camera, calibration_sha256=sha(camera / "manifest.json"),
                isolated_scene=True, optical_identity=identity,
            )
            result = []
            try:
                for row in rows[:5]:
                    frame, marker, robot, skill, phase = (
                        row[k] for k in ("frame", "marker", "robot", "skill", "phase")
                    )

                    pose = optics.rigid_pose
                    if mode != "original" and row["step"] == PLAN["target_step"]:
                        pose = partial(selected_pose, row=row, pose=oracle(row, scene, truth, mode))
                    with patch.object(clearance, "rigid_pose", pose):
                        if (skill, phase) == ("GRASP", "POST"):
                            observed = cert.observe_payload_frame(
                                frame, marker, robot, skill, phase,
                            )
                        else:
                            observed = cert.check(
                                frame, marker, robot, skill, row["target"], _DOWNWARD, phase=phase,
                            )
                    receipt = {"step": row["step"], "skill": skill, "phase": phase,
                               "frame_id": frame.frame_id, "robot_only_renders": render_count[mode],
                               "current": {k: v for k, v in observed.items() if k != "check_ms"}}
                    write(journal / mode / f"{len(result)}.json", receipt)
                    if mode == "original" or row["step"] < PLAN["target_step"]:
                        previous = row["previous"]
                        if "status" in previous:
                            for key in ("status", "reason", "depth"):
                                require(plain(observed[key]) == previous[key],
                                        f"original complete gate changed at {phase} {row['step']}")
                            compare_observation(row, observed["payload_observation"])
                        else:
                            compare_observation(row, observed)
                    result.append(receipt)
                results[mode] = result
            finally:
                cert.close()
    return {"classification": "offline_gate_oracle", "renderer": expected_gl,
            "robot_only_renders": render_count, "original_exposures": 0, "integrations": 0,
            "control": 0, "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("cpu", "whole"))
    parser.add_argument("name", choices=("first", "second", "complete"))
    parser.add_argument("--expected-cpu-sha256")
    args = parser.parse_args()
    cv2.setNumThreads(1)
    root = ROOT / "experiments/results/g1-t02-pose-oracle-20261126"
    loaded = inputs()
    if args.mode == "cpu":
        require(args.name in ("first", "second"), "unregistered cold-read name")
        write(root / f"{args.name}.json", cpu(loaded))
    else:
        require(args.name == "complete", "unregistered complete gate name")
        require(sha(root / "first.json") == sha(root / "second.json") == args.expected_cpu_sha256,
                "CPU oracle results do not cold-read or match registration")
        require(not (root / "whole-attempt.json").exists(), "whole-gate attempt already consumed")
        write(root / "whole-attempt.json", {"cpu_sha256": args.expected_cpu_sha256,
              "plan_sha256": sha(HERE / "plan.json"), "driver_sha256": sha(Path(__file__))})
        try:
            result = whole(loaded, read(root / "first.json"), root / "whole-journal")
            members = sorted((root / "whole-journal").rglob("*.json"))
            write(root / "complete.json", dict(
                result, journal_sha256={p.relative_to(root).as_posix(): sha(p) for p in members},
            ))
        except BaseException as error:
            write(root / "whole-failure.json", {"type": type(error).__name__, "error": str(error)})
            raise
