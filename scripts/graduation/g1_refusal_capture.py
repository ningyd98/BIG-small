"""Seal the first refused feedback, its preceding feedback, and paired static mount images."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
from pathlib import Path
from uuid import uuid4

import mujoco
import numpy as np
from scripts.graduation import g1_mount_geometry as geo
from scripts.graduation import g1_mount_screen as screen
from scripts.graduation import g1_mount_trials as trials
from scripts.graduation import proposal_camera as cam
from scripts.graduation import proposal_translated as translated
from scripts.graduation.dynamic_vision_score import checked_steps, frame_from_row
from scripts.graduation.g1_mount_score import check_clocks, first_feedback_refusal
from scripts.graduation.perception_io import ROOT, check_sources, pinned, read, sha, write
from scripts.graduation.proposal_terminal_visibility import HAND

from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera

PLAN_SHA = "85666eed1724a2c2280690de8ec55d35fe79b3d636982e35dd366d48e6534885"
AUDIT_SHA = "d46c9cb334281ed6ef1eb34dc457165f80511a6327c2cdfbff5e8c41b17395e4"
NOMINAL_CAMERA = dict(
    position_m=[0.35, 0, 1.4], quaternion_wxyz=[1, 0, 0, 0], fovy_deg=50, world_body_id=0, mode=0
)
SIDES = {"original": "Y", "r579": "X"}
TIMES = ("previous", "refused")
HISTORICAL = dict(
    previous="previous_accepted_feedback",
    refused="rejected_feedback",
    terminal="separate_terminal_capture",
)


def digest_state(row):
    return hashlib.sha256(
        json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def feedback_window(rows, accepted, stop_step):
    frames = [r for r in rows if r["label"] == "MOVE_ABOVE/feedback"]
    terminals = [r for r in rows if r["label"] == "terminal"]
    geo.require(
        len(frames) == len(accepted) + 1 and accepted and len(terminals) == 1,
        "expected ordered accepted samples, one refused feedback, and one terminal",
    )
    geo.require(
        [r["observation_id"] for r in accepted] == [r["frame_id"] for r in frames[:-1]],
        "foreign accepted feedback",
    )
    previous, refused, terminal = frames[-2], frames[-1], terminals[0]
    geo.require(
        refused["physics_step"]
        == terminal["physics_step"]
        == stop_step
        == previous["physics_step"] + 8
        and len({r["frame_id"] for r in (previous, refused, terminal)}) == 3
        and not any(previous["physics_step"] < r["physics_step"] < stop_step for r in rows),
        "wrong cadence, intervening camera sample, or duplicate terminal",
    )
    return previous, refused, terminal


def read_source(plan, case, assignment, store, families):
    path = ROOT / plan["prior_private"] / "trials" / case["case"]
    root = path / "instance"
    alloc = pinned(path / "allocation.json", case["allocation_sha256"])
    receipt = read(root / "receipt.json")
    recorded = trials.captured_evidence(root, assignment, alloc)
    side = case["source_side"]
    g = families[side]["descriptor"]
    geo.require(
        all(receipt[k] == v for k, v in recorded.items())
        and receipt["slot"] == case["slot"]
        and alloc["geometry"] == g
        and assignment["id"] == case["case"]
        and assignment["view"] == "nominal",
        "foreign source receipt, SQLite, allocation, or camera",
    )
    seal = pinned(root / "acquisition-seal.json", receipt["capture_sha256"])
    sign = read(root / "decision-seal.json")
    index = pinned(root / "pixel-index.json", seal["index_sha256"])
    truth = pinned(root / "offline-truth.json", case["state_file_sha256"])
    old = pinned(root / "decisions.json", sign["sha256"])
    run = pinned(root / "run.json", seal["run_sha256"])
    audit = pinned(root / "online-audit.json", seal["audit_sha256"])
    geo.require(
        index["episode"] == truth["episode"] == case["episode"]
        and index["scene"] == case["scene"]
        and seal["truth_sha256"] == case["state_file_sha256"]
        and old["index_sha256"] == seal["index_sha256"]
        and sign["acquisition_sha256"] == receipt["capture_sha256"],
        "crossed acquisition or historical decisions",
    )
    states = checked_steps(
        truth["samples"], case["episode"], alloc["asset_sha256"], truth["asset_sha256"]
    )
    packets = {d["frame_id"]: d for d in old["decisions"]}
    check_clocks(run, audit, packets, case["episode"])
    historic = first_feedback_refusal(run, audit, packets)
    (servo,) = [r for r in audit if r.get("phase") == "servo" and r["skill"] == "MOVE_ABOVE"]
    accepted = servo["visual_samples"]
    geo.require(
        receipt["stop"] == run["stop"]
        and run["stop"]["skill"] == "MOVE_ABOVE"
        and len(accepted) == case["accepted_feedback_count"]
        and historic["actual_servo_terminal_reason"] == case["servo_terminal_reason"]
        and accepted[-1]["target_pose"] == case["actual_last_accepted_target"],
        "actual servo or stop differs",
    )
    anchors = feedback_window(index["frames"], accepted, run["stop"]["physics_step"])
    start, stop = (anchors[k]["physics_step"] for k in (0, 1))
    dense = [states[s] for s in range(start, stop + 1)]
    geo.require(
        {str(r["physics_step"]): digest_state(r) for r in dense}
        == case["dense_previous_through_refusal"],
        "dense source rows differ from plan",
    )
    source_rows = {}
    feedback_states = {}
    for (role, historical), row in zip(HISTORICAL.items(), anchors, strict=True):
        step = row["physics_step"]
        pack = case["original_feedback"][historical]
        geo.require(
            all(pack[k] == v for k, v in historic[historical].items())
            and (root / row["file"]).resolve() == (ROOT / pack["packet_file"]).resolve()
            and row["file_sha256"] == pack["packet_sha256"]
            and pack["physics_step"] == step
            and pack["source_state_canonical_sha256"] == digest_state(states[step]),
            "original packet identity differs",
        )
        f = frame_from_row(root, row, case["episode"], case["scene"], g)
        d = packets[f.frame_id]
        geo.require(
            f.captured_at.isoformat() == pack["captured_at"] and f.sim_time_s == pack["sim_time_s"],
            "original clock differs",
        )
        source_rows[role] = store.add(
            f"{case['case']}/source/{role}",
            f,
            case=case["case"],
            time_role=role,
            mount_side=side,
            condition="actual",
            step=step,
            source_episode=case["episode"],
            original_sha256=row["file_sha256"],
            original_label=row["label"],
            original_path=pack["packet_file"],
            source_state_sha256=digest_state(states[step]),
            original_subpix=d["estimate"],
            original_grasp=d["servo_grasp_world_m"],
            original_depth_m=d["subpix_optical_depths_m"],
            captured_at=f.captured_at.isoformat(),
        )
        if role in TIMES:
            feedback_states[role] = states[step]
    public_dense = [
        dict(
            step=r["physics_step"],
            sim_time_s=r["sim_time_s"],
            state_sha256=digest_state(r),
            tcp_position_m=r["tcp_position_m"],
            finger_positions_m=r["finger_positions_m"],
            sampled_feedback_frame_id=next(
                (p["frame_id"] for p in anchors[:2] if p["physics_step"] == r["physics_step"]), None
            ),
        )
        for r in dense
    ]
    return feedback_states, dict(
        case=case["case"],
        source_side=side,
        episode=case["episode"],
        slot=case["slot"],
        dense=public_dense,
        original_accepted_samples=len(accepted),
        last_accepted_servo_sample=accepted[-1],
        first_refusal_reason=case["servo_terminal_reason"],
        closeup_feedback_steps=[start, stop],
        intervening_steps_without_acquired_pixels=7,
        acquisition_sha256=receipt["capture_sha256"],
        decision_sha256=sign["sha256"],
        receipt_sha256=sha(root / "receipt.json"),
        allocation_sha256=case["allocation_sha256"],
        sqlite_sha256=receipt["worker"]["sqlite_sha256"],
        source_state_file_sha256=case["state_file_sha256"],
    )


def live_snapshot(backend):
    model = backend._model
    camera = model.cam("rgbd").id
    return dict(
        episode_id=backend._episode_id,
        physics_step=backend.total_physics_steps,
        sim_time_s=backend.get_sim_time(),
        record_count=len(backend.command_records),
        next_seq=backend.next_command_sequence,
        camera=dict(
            position_m=model.cam_pos[camera].tolist(),
            quaternion_wxyz=model.cam_quat[camera].tolist(),
            fovy_deg=float(model.cam_fovy[camera]),
            world_body_id=int(model.cam_bodyid[camera]),
            mode=int(model.cam_mode[camera]),
        ),
    )


def audit_camera_commands(rows, records):
    geo.require(len(rows) == len(records) == 16, "wrong number of stationary restore commands")
    for i, (row, actual) in enumerate(zip(rows, records, strict=True)):
        before, after = row["before"], row["after_normal"]
        geo.require(
            row["after_hidden"] == after
            and before["episode_id"] == after["episode_id"]
            and before["physics_step"] == after["physics_step"] == 0
            and before["camera"] == after["camera"] == NOMINAL_CAMERA
            and (
                before["record_count"],
                before["next_seq"],
                after["record_count"],
                after["next_seq"],
            )
            == (i, i + 1, i + 1, i + 2)
            and after["sim_time_s"] == row["expected_source_time_s"]
            and (i == 0 or before == rows[i - 1]["after_hidden"]),
            "camera or zero-step boundaries differ",
        )
        expected = dict(
            type="camera_position",
            accepted=True,
            reason="development_camera_translation",
            after_emergency_stop=False,
            position_m=NOMINAL_CAMERA["position_m"],
            episode_id=before["episode_id"],
            physics_step=0,
            command_seq=i + 1,
            sim_time_s=before["sim_time_s"],
        )
        geo.require(
            actual == expected
            and actual["accepted"] is True
            and actual["after_emergency_stop"] is False,
            "unexpected command, identity, or clock in static evidence",
        )
    return dict(camera_records=16, integrated_steps=0, motion_dispatches=0, hidden_commands=0)


def capture_all(plan_file, raw):
    plan = pinned(plan_file, PLAN_SHA)
    supplement = (
        plan_file.parent.parent / "round-g1-first-refusal-camera-audit-20261124" / "plan.json"
    )
    audit = pinned(supplement, AUDIT_SHA)
    geo.require(
        sha(supplement.with_suffix(".md")) == audit["plan_md_sha256"]
        and audit["plan_parent_sha256"] == PLAN_SHA,
        "camera audit plan differs",
    )
    for name, expected in audit["failed_inputs_relative_to_private"].items():
        geo.require(sha(raw.parent / name) == expected, "failed capture evidence changed")
    geo.require(
        sha(plan_file.with_suffix(".md")) == plan["plan_md_sha256"], "plan markdown differs"
    )
    check_sources({"sources_sha256": plan["input_sha256"]})
    geo.require(
        raw.resolve() == (ROOT / plan["new_private"] / audit["new_capture"]).resolve()
        and os.environ.get("MUJOCO_GL") == "egl"
        and shutil.disk_usage(raw.parent).free > 2**29,
        "wrong output, EGL, or insufficient static image space",
    )
    raw.mkdir()
    families = {}
    mechanics = {}
    for mount in plan["single_mounts"]:
        side = SIDES[mount["id"]]
        geometry, refusal = geo.descriptor(mount)
        geo.require(refusal is None, "original single-marker registration rejected")
        families[side] = {"descriptor": geometry}
        mechanics[side] = geo.audit_mount(mount)
    geo.require(
        mechanics["Y"]["compiled_physics_sha256"] == mechanics["X"]["compiled_physics_sha256"],
        "single mounts have different dynamics",
    )
    store = screen.FrameStore(raw)
    maskdir = raw / "segmentation"
    maskdir.mkdir()
    batch = read(ROOT / plan["prior_private"] / "trials/allocation.json")
    states, archived = {}, []
    for i, (case, assignment) in enumerate(zip(plan["source_cases"], batch["cases"], strict=True)):
        geo.require(
            case["slot"] == i + 1
            and case["paired_noise_seeds"] == [24113000 + 2 * i, 24113001 + 2 * i],
            "wrong paired noise slot",
        )
        states[case["case"]], report = read_source(plan, case, assignment, store, families)
        archived.append(report)
    write(
        raw / "originals.json", {"plan_sha256": PLAN_SHA, "cases": archived, "mechanics": mechanics}
    )
    noise = plan["normal_scoring"]["noise_m"]
    camera_audits = {}
    for side, family in families.items():
        g = family["descriptor"]
        backend = MuJoCoPhysicsBackend()
        backend.initialize(translated.config({"geometry": g}, 24113000))
        initial = live_snapshot(backend)
        geo.require(
            initial["physics_step"] == 0
            and initial["record_count"] == 0
            and initial["next_seq"] == 1
            and initial["camera"] == NOMINAL_CAMERA,
            "nonempty backend or foreign camera",
        )
        boundaries = []
        model, data = backend._model, backend._data
        renderer = MuJoCoRGBDCamera(mujoco, model, width=320, height=240)
        arm_names = list(cam.arm_geometries(model).values())
        rgbs = model.geom_rgba.copy()
        hide = [model.geom(name).id for name in HAND]
        try:
            for case in plan["source_cases"]:
                name = case["case"]
                for k, time_role in enumerate(TIMES):
                    row = states[name][time_role]
                    seed = case["paired_noise_seeds"][k]
                    episode = uuid4().hex
                    before = live_snapshot(backend)
                    result, residuals = screen.restore_and_capture(
                        backend, renderer, row, seed, noise, episode, "nominal", g
                    )
                    expected_sha = result[3]
                    after = live_snapshot(backend)
                    facts = screen.geometry_at_frame(model, data)
                    for condition in ("normal", "hand_hidden"):
                        if condition == "hand_hidden":
                            model.geom_rgba[hide, 3] = 0
                            try:
                                result = screen.capture(
                                    renderer, data, seed, noise, "G1_SCREEN", episode
                                )
                            finally:
                                model.geom_rgba[:] = rgbs
                        f, mask, labels, state_sha = result
                        geo.require(
                            state_sha == expected_sha
                            and f.sim_time_s == row["sim_time_s"]
                            and np.array_equal(model.geom_rgba, rgbs)
                            and (condition == "normal" or set(HAND).isdisjoint(labels.values())),
                            "changed state or failed hand-only intervention",
                        )
                        screen.runtime.validate_camera(f, g)
                        geo.require(
                            cam.camera_meta(f) == g["camera"], "actual registered camera differs"
                        )
                        maskpath = maskdir / (uuid4().hex + ".npy")
                        with maskpath.open("xb") as stream:
                            np.save(stream, mask, allow_pickle=False)
                        store.add(
                            f"{name}/{time_role}/{side}/{condition}",
                            f,
                            condition=condition,
                            case=name,
                            time_role=time_role,
                            mount_side=side,
                            asset_sha256=g["pose_marker"]["marked_asset_sha256"],
                            source_episode=case["episode"],
                            source_state_sha256=digest_state(row),
                            seed=seed,
                            step=row["physics_step"],
                            state_sha256=state_sha,
                            residuals=residuals,
                            geometry=facts,
                            arm_geoms=arm_names,
                            segmentation=dict(
                                file=maskpath.name, sha256=sha(maskpath), labels=labels
                            ),
                        )
                    boundaries.append(
                        dict(
                            case=name,
                            time_role=time_role,
                            seed=seed,
                            before=before,
                            after_normal=after,
                            after_hidden=live_snapshot(backend),
                            expected_source_time_s=row["sim_time_s"],
                        )
                    )
            records = backend.command_records
            camera_audits[side] = dict(
                initial=initial,
                boundaries=boundaries,
                records=records,
                verified=audit_camera_commands(boundaries, records),
            )
        finally:
            renderer.close()
            backend.shutdown()
    store.seal({"families": families}, PLAN_SHA)
    write(raw / "camera-commands.json", dict(audit_plan_sha256=AUDIT_SHA, mounts=camera_audits))
    capture = read(raw / "capture-seal.json")
    write(
        raw / "source-seal.json",
        dict(
            plan_sha256=PLAN_SHA,
            originals_sha256=sha(raw / "originals.json"),
            audit_plan_sha256=AUDIT_SHA,
            camera_commands_sha256=sha(raw / "camera-commands.json"),
            capture_sha256=sha(raw / "capture-seal.json"),
            input_files=len(plan["input_sha256"]),
            capture_source_sha256=sha(Path(__file__)),
            **capture,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("raw", type=Path)
    args = parser.parse_args()
    with (args.raw.parent / "egl.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        capture_all(args.plan.resolve(), args.raw.resolve())


if __name__ == "__main__":
    main()
