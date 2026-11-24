"""Observe both registered upright cameras on the eight frozen r593 stopping states."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import mujoco
import numpy as np
from scripts.graduation import proposal_camera as cam
from scripts.graduation import proposal_translated as translated
from scripts.graduation.dynamic_vision_score import checked_steps, frame_from_row
from scripts.graduation.perception_io import ROOT, check_sources, pinned, read, sha, write
from scripts.graduation.perception_pixels import measure

from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame
from cloud_edge_robot_arm.vision.servo import measure_registered_marker_grasp

VIEWS = tuple(translated.POSITION)
HAND = ("hand", "left_finger_geom", "right_finger_geom")
POSES = ((0.439, -0.016, 0.035, 0.09), (0.461, 0.016, 0.035, -0.09))
SRC = "scripts/graduation/proposal_terminal_visibility.py"


def bucket(verified, normal):
    if set(normal) != set(VIEWS) or any(type(v) is not bool for v in normal.values()):
        raise ValueError("both registered normal views required")
    if not verified:
        return "reconstruction_unknown"
    return {
        (True, True): "both",
        (True, False): "nominal_only",
        (False, True): "translated_only",
        (False, False): "neither",
    }[tuple(normal[n] for n in VIEWS)]


def slots():
    rows = []
    for i, (x, y, z, yaw) in enumerate(POSES):
        group = f"v{i + 1:02}"
        for method in ("fixed", "bounded") if i == 0 else ("bounded", "fixed"):
            rows.append(
                {
                    "id": group + "-" + method,
                    "group": group,
                    "method": method,
                    "view": VIEWS[i],
                    "seed": 24112701 + i,
                    "reset_fixture_center_m": [x, y, z],
                    "yaw_rad": yaw,
                }
            )
    return rows


def allocate(raw, plan, h, episodes, master):
    spec = pinned(plan, h)
    if sha(plan.with_suffix(".md")) != spec["plan_md_sha256"]:
        raise ValueError("Astra plan mismatch")
    check_sources({"sources_sha256": spec["input_sha256"]})
    cases = pinned(master, spec["input_sha256"][str(master.resolve().relative_to(ROOT))])
    if sha(episodes / "allocation.json") != sha(master):
        raise ValueError("wrong experimental evidence root")
    if os.environ.get("MUJOCO_GL") != "egl" or shutil.disk_usage(raw).free < 2**29:
        raise ValueError("EGL and local evidence storage required")
    terminal = {row[0]: row[1:] for row in spec["source_terminal"]}
    sources = []
    for rec in cases["cases"]:
        name = rec["id"]
        step, label = terminal[name]
        root = episodes / name / "instance"
        old = pinned(root.parent / "allocation.json", rec["allocation_sha256"])
        seal = read(root / "acquisition-seal.json")
        idx = pinned(root / "pixel-index.json", seal["index_sha256"])
        trace = pinned(root / "offline-truth.json", seal["truth_sha256"])
        if (
            idx["allocation_sha256"] != rec["allocation_sha256"]
            or trace["episode"] != idx["episode"]
            or trace["samples"][-1]["physics_step"] != step
            or trace["asset_sha256"] != old["asset_sha256"]
        ):
            raise ValueError("mixed instance/stop/trajectory")
        ref = idx["frames"][-3:]
        if [(r["physics_step"], r["label"]) for r in ref] != [
            (step - 8, label),
            (step, label),
            (step, "terminal"),
        ]:
            raise ValueError("old positive/negative frame role sequence changed")
        for row in ref:
            f = frame_from_row(root, row, idx["episode"], idx["scene"], old["geometry"])
            translated.check_view(
                rec["view"],
                cam.camera_meta(f),
                old["geometry"] if rec["view"] == "nominal" else cases["geometry"]["nominal"],
            )
        sources.append(
            {
                "id": name,
                "step": step,
                "label": label,
                "source_view": rec["view"],
                "episode": idx["episode"],
                "scene": idx["scene"],
                "references": ref,
                "registration_sha256": rec["allocation_sha256"],
                "seal_sha256": sha(root / "acquisition-seal.json"),
            }
        )
    if len({s["episode"] for s in sources}) != 8 or len(sources) != len(terminal):
        raise ValueError("omitted or duplicated terminal poses")
    write(
        raw / "observation-allocation.json",
        {
            "schema": "proposal.terminal-visibility.v1",
            "created": datetime.now(UTC).isoformat(),
            "plan_sha256": h,
            "baseline": spec["baseline"],
            "master_sha256": sha(master),
            "slots": slots(),
            "source_terminals": sources,
            "episodes": os.path.relpath(episodes, ROOT),
            "geometry": cases["geometry"],
            "asset_sha256": old["asset_sha256"],
            "state_limits": cam.CHECK_LIMITS,
            "hand_geoms": HAND,
            "noise_std_m": 0.001,
            "paired_seed_offset": 241127000,
            "view_order": VIEWS,
            "render_conditions": ["normal", "hand_hidden"],
            "separate_normal_segmentation": True,
            "sources_sha256": {
                **old["sources_sha256"],
                SRC: sha(ROOT / SRC),
                "scripts/graduation/proposal_camera.py": sha(
                    ROOT / "scripts/graduation/proposal_camera.py"
                ),
            },
            "new_formal_claims": 0,
        },
    )


def observe(raw, a, h):
    dest = raw / "observation"
    dest.mkdir()
    pixels = dest / "pixels"
    pixels.mkdir()
    masks = dest / "segmentation"
    masks.mkdir()
    backend = MuJoCoPhysicsBackend()
    geometry = a["geometry"]["nominal"]
    backend.initialize(translated.config({"geometry": geometry}, 24112700))
    model, data = backend._model, backend._data
    renderer = MuJoCoRGBDCamera(
        mujoco, model, width=geometry["camera"]["width"], height=geometry["camera"]["height"]
    )
    hand = [model.geom(n).id for n in HAND]
    alpha = model.geom_rgba[hand, 3].copy()
    arm_names = list(cam.arm_geometries(model).values())
    states, role_map, index, segs = {}, {}, {}, {}

    def save(role, frame):
        nonce = hashlib.sha256((h + role).encode()).hexdigest()[:20]
        p = pixels / (nonce + ".json")
        write(p, frame.model_dump(mode="json"))
        role_map[role] = nonce
        index[nonce] = {"file": p.name, "sha256": sha(p)}

    try:
        for i, s in enumerate(a["source_terminals"]):
            name = s["id"]
            step = s["step"]
            root = ROOT / a["episodes"] / name / "instance"
            old = pinned(root / "acquisition-seal.json", s["seal_sha256"])
            truth = pinned(root / "offline-truth.json", old["truth_sha256"])
            tr = checked_steps(
                truth["samples"], s["episode"], a["asset_sha256"], truth["asset_sha256"]
            )
            for role, ref in zip(
                ("previous", "rejected", "terminal"), s["references"], strict=True
            ):
                save(
                    name + "/" + role,
                    frame_from_row(
                        root, ref, s["episode"], s["scene"], a["geometry"][s["source_view"]]
                    ),
                )
            for j, view in enumerate(VIEWS):
                backend.set_camera_position(translated.POSITION[view])
                residual = cam.restore(model, data, tr[step])
                if name in states and states[name] != residual:
                    raise ValueError("camera modified physical pose")
                states[name] = residual
                for mode in ("normal", "hand_hidden"):
                    role = name + "/" + view + "/" + mode
                    model.geom_rgba[hand, 3] = alpha if mode == "normal" else 0
                    kp = dict(
                        rng=np.random.default_rng(a["paired_seed_offset"] + i * 2 + j),
                        noise_std_m=a["noise_std_m"],
                        scene_id="terminal-diagnostic",
                        episode_id="reconstruct-" + name + "-" + h[:12],
                    )
                    if mode == "normal":
                        sensor, instances, labels, hashes = renderer.capture_with_instances(
                            data, **kp
                        )
                        mask_path = masks / (name + "-" + view + ".npy")
                        with mask_path.open("xb") as f:
                            np.save(
                                f,
                                np.asarray(instances, dtype="<i2").reshape(
                                    sensor.height, sensor.width
                                ),
                            )
                        segs[name + "/" + view] = {
                            "file": mask_path.name,
                            "sha256": sha(mask_path),
                            "labels": labels,
                            "state_hash": hashes[0],
                        }
                        if len(set(hashes)) != 1:
                            raise ValueError("segmentation and RGB-D physics diverged")
                    else:
                        sensor = renderer.capture(data, **kp)
                        if (
                            renderer._physics_state_hash(data)
                            != segs[name + "/" + view]["state_hash"]
                        ):
                            raise ValueError("hand visibility altered kinematics")
                    f = observation_from_sensor_frame(sensor, source="mujoco_camera")
                    if cam.camera_meta(f) != a["geometry"][view]["camera"]:
                        raise ValueError("incorrect actual camera")
                    save(role, f)
                    model.geom_rgba[hand, 3] = alpha
    finally:
        model.geom_rgba[hand, 3] = alpha
        renderer.close()
        backend.shutdown()
    write(
        pixels / "index.json",
        {
            "allocation_sha256": h,
            "frames": index,
            "marker_geometry": {
                k: geometry[k]
                for k in (
                    "pose_marker",
                    "object_half_extent_m",
                    "marker_to_object",
                    "marker_family",
                )
            },
        },
    )
    write(
        dest / "roles.json",
        {
            "allocation_sha256": h,
            "residuals": states,
            "role_map": role_map,
            "segmentation": segs,
            "arm_names": arm_names,
        },
    )
    write(
        raw / "observation-seal.json",
        {
            "allocation_sha256": h,
            "frames_sha256": sha(pixels / "index.json"),
            "roles_sha256": sha(dest / "roles.json"),
        },
    )


def pixels(raw, h):
    seal = read(raw / "observation-seal.json")
    p = raw / "observation/pixels"
    idx = pinned(p / "index.json", seal["frames_sha256"])
    if idx["allocation_sha256"] != h or len(idx["frames"]) != 56:
        raise ValueError("incomplete blind frame index")
    rows = {}
    for k, r in idx["frames"].items():
        f = cam.load_frame(p, r)
        geo = idx["marker_geometry"]
        e = measure(f, geo, "SUBPIX")
        try:
            grasp, reg = measure_registered_marker_grasp(f, geo["marker_family"])
            reason = reg.reason
            point = grasp.tolist() if grasp is not None else None
        except ValueError as exc:
            point = None
            reason = str(exc)
        rows[k] = {
            "frame_sha256": r["sha256"],
            "frame_id": f.frame_id,
            "source_checksum": f.checksum_sha256,
            "estimate": e,
            "grasp_world_m": point,
            "grasp_reason": reason,
            "usable": bool(
                cam.valid(e) and e["marker_center_optical_depth_m"] > 0 and point is not None
            ),
        }
    write(
        raw / "blind-decisions.json",
        {"allocation_sha256": h, "frames_sha256": seal["frames_sha256"], "decisions": rows},
    )
    write(
        raw / "decision-seal.json",
        {
            "capture_sha256": sha(raw / "observation-seal.json"),
            "decisions_sha256": sha(raw / "blind-decisions.json"),
        },
    )


def score(raw, a, h, out):
    d = read(raw / "decision-seal.json")
    cap = pinned(raw / "observation-seal.json", d["capture_sha256"])
    dest = raw / "observation"
    px = dest / "pixels"
    decisions = pinned(raw / "blind-decisions.json", d["decisions_sha256"])
    idx = pinned(px / "index.json", cap["frames_sha256"])
    meta = pinned(dest / "roles.json", cap["roles_sha256"])
    if (
        any(v["allocation_sha256"] != h for v in (cap, decisions, idx, meta))
        or decisions["frames_sha256"] != cap["frames_sha256"]
    ):
        raise ValueError("mismatched role, acquisition or blind-decision seals")
    by = meta["role_map"]
    if (
        len(by) != 56
        or set(by.values()) != set(idx["frames"])
        or set(idx["frames"]) != set(decisions["decisions"])
    ):
        raise ValueError("unaccounted pixel or role")

    def evidence(role):
        k = by[role]
        rec = decisions["decisions"][k]
        fr = cam.load_frame(px, idx["frames"][k])
        if (
            rec["frame_sha256"] != idx["frames"][k]["sha256"]
            or fr.checksum_sha256 != rec["source_checksum"]
        ):
            raise ValueError("estimate source mismatch")
        return rec, fr

    table = []
    counts = Counter()
    complementary = []
    for s in a["source_terminals"]:
        name = s["id"]
        view = s["source_view"]
        root = ROOT / a["episodes"] / name / "instance"
        old = pinned(root / "acquisition-seal.json", s["seal_sha256"])
        truth = pinned(root / "offline-truth.json", old["truth_sha256"])
        state = truth["samples"][s["step"]]
        if state["physics_step"] != s["step"] or state["episode_id"] != s["episode"]:
            raise ValueError("foreign endpoint physics")
        prev, prev_f = evidence(name + "/previous")
        reject, orig = evidence(name + "/rejected")
        end, terminal = evidence(name + "/terminal")
        rec, f = evidence(name + "/" + view + "/normal")
        if [x.frame_id for x in (prev_f, orig, terminal)] != [
            r["frame_id"] for r in s["references"]
        ]:
            raise ValueError("foreign original frame evidence")
        errs = {**meta["residuals"][name], **cam.compare(orig, f)}
        verified = (
            all(errs[k] <= v for k, v in cam.CHECK_LIMITS.items())
            and prev["usable"]
            and not reject["usable"]
            and not end["usable"]
            and rec["estimate"]["status"] == reject["estimate"]["status"]
            and rec["estimate"]["ids"] == reject["estimate"]["ids"] == end["estimate"]["ids"]
        )
        all_views = {}
        normal = {}
        for v in VIEWS:
            vals = {}
            seg = meta["segmentation"][name + "/" + v]
            sp = dest / "segmentation" / seg["file"]
            if sha(sp) != seg["sha256"]:
                raise ValueError("segmentation digest changed")
            for mode in ("normal", "hand_hidden"):
                row, f = evidence(name + "/" + v + "/" + mode)
                if (
                    f.sim_time_s != state["sim_time_s"]
                    or cam.camera_meta(f) != a["geometry"][v]["camera"]
                ):
                    raise ValueError("wrong camera or rendering time")
                e = row["estimate"]
                vals[mode] = {
                    "ids": e["ids"],
                    "status": e["status"],
                    "grasp_usable": row["usable"],
                    "grasp_reason": row["grasp_reason"],
                    "grasp_world_m": row["grasp_world_m"],
                    "depth_m": e["marker_center_optical_depth_m"],
                    "marker_reason": e["reason"],
                    "observation_checksum": row["source_checksum"],
                }
                if mode == "normal":
                    normal[v] = row["usable"]
                    rings = cam.regions(
                        f,
                        a["geometry"][v],
                        state,
                        np.load(sp, allow_pickle=False),
                        seg["labels"],
                        meta["arm_names"],
                    )
                    for area in rings.values():
                        robot = area["robot_by_geom"]
                        area["hand_pixels"] = sum(robot.get(x, 0) for x in HAND)
                        area["other_robot_pixels"] = sum(
                            n for k, n in robot.items() if k not in HAND
                        )
                        if sum(area["role_pixels"].values()) != area["pixels"]:
                            raise ValueError("segmentation coverage")
                    vals["normal_region_labels"] = rings
            all_views[v] = vals
        code = bucket(verified, normal)
        counts[code] += 1
        other = next(x for x in VIEWS if x != view)
        if verified and not normal[view] and normal[other]:
            complementary.append(name)
        table.append(
            {
                "id": name,
                "source_view": view,
                "episode": s["episode"],
                "step": s["step"],
                "role": s["label"],
                "original_previous": prev["usable"],
                "original_rejected": reject["usable"],
                "original_terminal": end["usable"],
                "verified": verified,
                "residuals": errs,
                "bucket": code,
                "views": all_views,
            }
        )
    write(
        out,
        {
            "schema": "proposal.terminal-visibility.readback.v1",
            "allocation_sha256": h,
            "plan_sha256": a["plan_sha256"],
            "counts": {
                k: counts[k]
                for k in (
                    "both",
                    "nominal_only",
                    "translated_only",
                    "neither",
                    "reconstruction_unknown",
                )
            },
            "complementary_original_trajectories": complementary,
            "physical_visibility_prerequisite": bool(complementary),
            "endpoints": table,
            "captured": {
                "normal": 16,
                "hand_hidden": 16,
                "normal_segmentation": 16,
                "original_controls": 24,
            },
            "blind_decision_seal": d,
            "capture_seal": cap,
            "formal_claims": 0,
            "scope": "terminal states from four paired development placements",
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="name", required=True)
    p = sub.add_parser("allocate")
    for n in ("raw", "plan", "plan_sha", "episodes", "master"):
        p.add_argument(n, type=str if n == "plan_sha" else Path)
    for n in ("observe", "pixels", "score"):
        p = sub.add_parser(n)
        p.add_argument("raw", type=Path)
        p.add_argument("digest")
        if n == "score":
            p.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.name == "allocate":
        allocate(args.raw, args.plan, args.plan_sha, args.episodes, args.master)
        return
    a = pinned(args.raw / "observation-allocation.json", args.digest)
    check_sources(a)
    if args.name == "observe":
        observe(args.raw, a, args.digest)
    elif args.name == "pixels":
        pixels(args.raw, args.digest)
    else:
        score(args.raw, a, args.digest, args.output)


if __name__ == "__main__":
    main()
