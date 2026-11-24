"""Zero-step optical comparisons and dense MuJoCo geometry screens at pinned historical poses."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from collections import Counter
from contextlib import ExitStack
from pathlib import Path

import mujoco
import numpy as np
from scripts.graduation import g1_formal_failure_occlusion as optical
from scripts.graduation import g1_visibility_radial as radial
from scripts.graduation import g1_visibility_replay as reference
from scripts.graduation import proposal_camera as cam
from scripts.graduation.dynamic_vision_score import frame_from_row
from scripts.graduation.g1_dual_asset import compiled_world_bounds
from scripts.graduation.g1_dual_asset_v2 import ASSET_PATH, ASSET_SHA
from scripts.graduation.g1_visibility_replay import read, require, sha, write
from scripts.graduation.g1_visibility_vision import measure_frame

from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera

ROOT = reference.ROOT
BASE = ROOT / "experiments/results/g1-visibility-pose-repair-20261124"
ROUND = reference.ROUNDS / "round-g1-visibility-approach-geometry-20261125"
PLAN = "f73a383f23408f6d53d30677928545ed4e515419ab0ed16da7b391c1275ed015"
D02 = BASE / "batches/train-feedback-deadline-01/d02"
D01 = ROOT / "../../local-verification/g1-first-refusal-dual-20261124.mynavkg6/trials/d01-dual"
FINGERS = {"left_finger_geom", "right_finger_geom"}
PARTS = [f"g1_dual_id{i}_{part}" for i in (7, 8) for part in ("plate", "crossbar", "upright")]
ARCHIVE = reference.RAW
OLD_ROUND = reference.ROUNDS / "round-g1-formal-failure-observation-20261124"
FORMAL = reference.ROUNDS / "round-g1-formal-paired-20261124"


def contact_category(a, b):
    names = {a, b}
    if names == {"table", "object_geom"}:
        return "object_on_table"
    if "object_geom" in names and names & FINGERS:
        return "finger_object"
    return "unauthorized"


def visual_qualified(result, truth, both):
    valid = result["usable_ids"]
    if not (
        result["usable"]
        and valid
        and result["selected_id"] in valid
        and truth["correct_registered_id"]
    ):
        return False
    if both and valid != [7, 8]:
        return False
    if len(valid) == 2 and (
        result["target_disagreement_m"] is None or result["target_disagreement_m"] > 0.010
    ):
        return False
    return all(
        e["tcp_error_mm"] <= 10 and e["top_error_mm"] <= 10 for e in truth["per_id"].values()
    )


def box_separation(c1, r1, s1, c2, r2, s2):
    """Maximum separating-axis gap; positive certifies a lower bound to Euclidean distance."""
    normals = np.concatenate(
        (r1.T, r2.T, np.cross(r1.T[:, None, :], r2.T[None, :, :]).reshape(-1, 3))
    )
    lengths = np.linalg.norm(normals, axis=1)
    axes = normals[lengths > 1e-10] / lengths[lengths > 1e-10, None]
    gaps = abs(axes @ (c2 - c1)) - abs(axes @ r1) @ s1 - abs(axes @ r2) @ s2
    return float(max(gaps))


def pins():
    plan = read(ROUND / "plan.json", PLAN)
    require(sha(ROUND / "plan.md") == plan["plan_md_sha256"], "Astra plan text changed")
    direct = plan["inputs_sha256"]
    for name, h in direct.items():
        source = ROOT / name
        # The approved new runtime/runner adapt identities concurrently. Their exact
        # original bytes remain in the failed, input-pinned runtime and are not read for control.
        if name in {
            "scripts/graduation/g1_visibility_runtime.py",
            "scripts/graduation/g1_visibility_trials.py",
        }:
            source = BASE / "builds" / plan["failed_generation"] / "runtime-source" / name
        require(sha(source) == h, f"changed Astra input {name}")
    return plan


def restore(model, data, row):
    residual = cam.restore(model, data, row)
    q = int(model.joint("object_free").dofadr[0])
    data.qvel[q : q + 6] = row["object_linear_velocity_m_s"] + row["object_angular_velocity_rad_s"]
    mujoco.mj_forward(model, data)
    return residual


def checked_case(folder):
    inst = folder / "instance"
    index = read(inst / "pixel-index.json")
    truth = read(inst / "offline-truth.json")
    allocation = read(folder / "allocation.json", index["allocation_sha256"])
    receipt = read(inst / "receipt.json")
    seal = read(inst / "acquisition-seal.json", receipt["capture_sha256"])
    require(
        receipt["allocation_sha256"] == truth["allocation_sha256"] == index["allocation_sha256"]
        and sha(inst / "offline-truth.json") == seal["truth_sha256"]
        and sha(inst / "pixel-index.json") == seal["index_sha256"]
        and truth["asset_sha256"] == allocation["asset_sha256"]
        and truth["episode"] == index["episode"],
        "inconsistent allocation, episode or state",
    )
    states = truth["samples"]
    require(
        all(
            s["physics_step"] == i
            and s["episode_id"] == truth["episode"]
            and abs(i / 240 - s["sim_time_s"]) < 1e-8
            for i, s in enumerate(states)
        ),
        "incomplete dense state sequence",
    )
    return {
        "folder": folder,
        "geometry": allocation["geometry"],
        "index": index,
        "states": states,
        "asset_sha256": allocation["asset_sha256"],
        "truth_sha256": seal["truth_sha256"],
        "index_sha256": seal["index_sha256"],
    }


def collect():
    plan = pins()
    source_manifest = read(
        ARCHIVE / "originals-manifest.json",
        plan["inputs_sha256"][(ARCHIVE / "originals-manifest.json").relative_to(ROOT).as_posix()],
    )["files"]
    old_parent = read(reference.ROUND / "plan.json", reference.PLAN_SHA)
    timeline = OLD_ROUND / "episode-timelines.public.json"
    formal = read(timeline, old_parent["inputs_sha256"][timeline.relative_to(ROOT).as_posix()])[
        "cases"
    ]
    cases = {}
    anchors = []
    for previous in formal:
        name = previous["id"]
        folder = ARCHIVE / "trials" / name
        for suffix in (
            "allocation.json",
            "instance/receipt.json",
            "instance/acquisition-seal.json",
            "instance/offline-truth.json",
            "instance/pixel-index.json",
        ):
            f = folder / suffix
            require(
                sha(f) == source_manifest[f.relative_to(ARCHIVE).as_posix()]["sha256"],
                "changed formal source",
            )
        case = cases[name] = checked_case(folder)
        byid = {r["frame_id"]: r for r in case["index"]["frames"]}
        for role in ("last_accepted", "first_refused"):
            anchor = previous["anchors"][role]
            row = byid[anchor["frame_id"]]
            require(
                row["physics_step"] == anchor["physics_step"]
                and row["label"].endswith("/feedback"),
                "misjoined formal feedback pose",
            )
            anchors.append(
                (name, role, row, role == "first_refused" and name in {"f01-dual", "f04-dual"})
            )
    for name, folder, expected in (("d01", D01, 1121), ("d02", D02, 1089)):
        case = cases[name] = checked_case(folder)
        require(
            len(case["states"]) == expected and case["asset_sha256"] == ASSET_SHA,
            "wrong development trajectory",
        )
    for row in cases["d02"]["index"]["frames"]:
        if row["label"] == "APPROACH/feedback" and 1056 <= row["physics_step"] <= 1088:
            anchors.append(
                (
                    "d02",
                    "approach_ambiguity" if row["physics_step"] == 1088 else "approach_previous",
                    row,
                    False,
                )
            )
    row = cases["d01"]["index"]["frames"][-1]
    require(
        row["label"] == "terminal" and row["physics_step"] == 1120 and len(anchors) == 21,
        "wrong collision/approach anchors",
    )
    anchors.append(("d01", "collision_terminal", row, False))
    return cases, anchors


def reference_geometry(offset, original):
    if offset == 0:
        return original
    return radial.geometry_for_screen(original, offset)


def physical_root(offset):
    return ROOT / (ASSET_PATH if offset == 0 else radial.details(offset)["asset_path"])


def checked_model(path, geometry):
    require(
        sha(path) == geometry["pose_marker"]["marked_asset_sha256"],
        "model differs from registered print",
    )
    return mujoco.MjModel.from_xml_path(str(path))


def sensor_record(private, key, frame, features, geometric, require_both):
    result = measure_frame(frame, geometric)
    per_id = {
        str(i): reference.independent_pose(geometric, i, result["by_id"][str(i)])
        for i in result["usable_ids"]
    }
    measured = {**result, "per_id": per_id}
    truth = reference.truth_errors(geometric, features, measured)
    path = private / (key + ".json")
    write(path, frame.model_dump(mode="json"))
    return {
        "packet_file": path.name,
        "packet_sha256": sha(path),
        "frame_checksum": frame.checksum_sha256,
        "camera": frame.calibration_version,
        "measurement": {
            k: result[k]
            for k in (
                "observed_ids",
                "usable_ids",
                "selected_id",
                "reason",
                "usable",
                "target_disagreement_m",
                "object_top_world_m",
                "grasp_world_m",
                "by_id",
                "candidates",
            )
        },
        "truth": truth,
        "requires_both_codes": require_both,
        "qualified": visual_qualified(result, truth, require_both),
    }


def cameras_for(stack, cache, geometry):
    path = ROOT / geometry["asset_path"]
    if path not in cache:
        model = checked_model(path, geometry)
        camera = MuJoCoRGBDCamera(
            mujoco, model, width=geometry["camera"]["width"], height=geometry["camera"]["height"]
        )
        stack.callback(camera.close)
        cache[path] = (model, mujoco.MjData(model), camera)
    return cache[path]


def render_anchors(offset, private, output):
    cases, anchors = collect()
    source_v2 = cases["d02"]["geometry"]
    geometry = reference_geometry(offset, source_v2)
    require(os.environ.get("MUJOCO_GL") == "egl", "registered EGL renderer required")
    private.mkdir(parents=True, exist_ok=False)
    frames = []
    with ExitStack() as stack:
        lock = stack.enter_context((BASE / "egl.lock").open("rb"))
        fcntl.flock(lock, fcntl.LOCK_EX)
        models = {}
        for name, role, ref, both in anchors:
            case = cases[name]
            original_geometry = case["geometry"]
            f = frame_from_row(
                case["folder"] / "instance",
                ref,
                case["index"]["episode"],
                case["index"]["scene"],
                original_geometry,
            )
            require(
                f.model_dump(mode="json", include=set(geometry["camera"])) == geometry["camera"],
                "camera registration differs",
            )
            idx = ref["physics_step"]
            s = case["states"][idx]
            key = f"{name}-{role}-{idx}"
            source_model, source_data, source_camera = cameras_for(stack, models, original_geometry)
            residual = restore(source_model, source_data, s)
            src = optical.render(
                source_camera,
                source_model,
                source_data,
                f,
                (),
                source_camera._physics_state_hash(source_data),
            )
            new_model, new_data, new_camera = cameras_for(stack, models, geometry)
            candidate_residual = restore(new_model, new_data, s)
            state_hash = new_camera._physics_state_hash(new_data)
            new = optical.render(new_camera, new_model, new_data, f, (), state_hash)
            frozen_depth = cam.depth(f)
            paired = optical.paired_depth(frozen_depth, src["depth"], new["depth"])
            clean_packet = optical.packet(f, new["rgb"], new["depth"], key + "-clean")
            matched_packet = optical.packet(f, new["rgb"], paired, key + "-paired")
            clean = sensor_record(private, key + "-clean", clean_packet, s, geometry, both)
            matched = sensor_record(private, key + "-paired", matched_packet, s, geometry, both)
            baseline = optical.packet(f, src["rgb"], frozen_depth, key + "-source-matched")
            source_read = sensor_record(private, key + "-native", f, s, original_geometry, both)
            matched_base = sensor_record(
                private, key + "-source-normal", baseline, s, original_geometry, both
            )
            orig_rgb = cam.rgb(f)
            valid = (frozen_depth > 0) & (src["depth"] > 0)
            delta = np.abs(frozen_depth[valid] - src["depth"][valid])
            frames.append(
                {
                    "case": name,
                    "role": role,
                    "step": idx,
                    "frame_id": f.frame_id,
                    "physics_state_sha256": state_hash,
                    "original_file_sha256": ref["file_sha256"],
                    "original_truth_sha256": case["truth_sha256"],
                    "asset_sha256": sha(physical_root(offset)),
                    "historical_asset_sha256": case["asset_sha256"],
                    "source_restore_residual": residual,
                    "candidate_restore_residual": candidate_residual,
                    "normal_vs_original": {
                        "rgb_pixels_differ": int(np.any(orig_rgb != src["rgb"], axis=2).sum()),
                        "positive_depth_pairs": int(valid.sum()),
                        "depth_p99_mm": float(np.quantile(delta, 0.99) * 1000),
                        "depth_max_mm": float(delta.max() * 1000),
                        "source_rgb_sha256": optical.digest_array(orig_rgb),
                        "normal_rgb_sha256": optical.digest_array(src["rgb"]),
                        "source_clean_depth_sha256": optical.digest_array(src["depth"]),
                        "original_depth_sha256": optical.digest_array(frozen_depth),
                    },
                    "source_original": source_read,
                    "source_matched_normal": matched_base,
                    "candidate_clean": clean,
                    "candidate_matched_noise": matched,
                    "qualified": clean["qualified"] and matched["qualified"],
                }
            )
    details = output / f"screen-optical-{offset:02d}.public.json.gz"
    write(details, {"plan_sha256": PLAN, "radial_offset_mm": offset, "frames": frames})
    failure = [
        {
            "case": r["case"],
            "step": r["step"],
            "role": r["role"],
            "clean_reason": r["candidate_clean"]["measurement"]["reason"],
            "paired_reason": r["candidate_matched_noise"]["measurement"]["reason"],
        }
        for r in frames
        if not r["qualified"]
    ]
    summary = {
        "schema": "g1.visibility.radial-optical-screen.v1",
        "plan_sha256": PLAN,
        "offset_mm": offset,
        "frame_details_sha256": sha(details),
        "frame_count": len(frames),
        "qualified_anchors": len(frames) - len(failure),
        "failures": failure,
        "eligible": not failure,
        "camera_calibration": "f33940579c533afe",
        "physics_integrations": 0,
        "formal_or_new_placements": 0,
        "packet_count": len(frames) * 4,
        "detectors": pins()["inputs_sha256"]["scripts/graduation/g1_visibility_grid.py"],
    }
    write(output / f"screen-optical-{offset:02d}-summary.public.json", summary)
    print(json.dumps(summary), flush=True)


def measured_pairs(model):
    robot = list(cam.arm_geometries(model).values())
    partners = [*robot, "table", "target_region_geom"]
    pairs = [(p, b, True) for p in PARTS for b in partners]
    pairs += [
        ("object_geom", b, False) for b in (*sorted(FINGERS), "hand", "table", "target_region_geom")
    ]
    return [(a, b, model.geom(a).id, model.geom(b).id, gate) for a, b, gate in pairs]


def geometric_witness(model, data, a, b, raw, contacts):
    """Retain raw MuJoCo distance and certify separation when its solver returns a spurious zero."""
    if raw != 0 or (min(a, b), max(a, b)) in contacts:
        return raw, "mj_geomDistance"
    left, right = model.geom(a), model.geom(b)
    w1, w2 = data.geom(a), data.geom(b)
    r1, r2 = w1.xmat.reshape(3, 3), w2.xmat.reshape(3, 3)
    if int(left.type[0]) == int(right.type[0]) == int(mujoco.mjtGeom.mjGEOM_BOX):
        gap = box_separation(w1.xpos, r1, left.size, w2.xpos, r2, right.size)
        if gap > 1e-12:
            return gap - 1e-12, "box_separating_axis_lower_bound"
    shapes = [
        compiled_world_bounds(g.type[0], g.size, w.xpos, w.xmat.reshape(3, 3))
        for g, w in ((left, w1), (right, w2))
    ]
    lo1, lo2 = (np.asarray(s["expanded_minimum_world_m"]) for s in shapes)
    hi1, hi2 = (np.asarray(s["expanded_maximum_world_m"]) for s in shapes)
    gap = float(np.linalg.norm(np.maximum(0, np.maximum(lo1 - hi2, lo2 - hi1))))
    return (gap, "world_aabb_lower_bound") if gap > 0 else (0.0, "separation_unproved")


def dense_case(case, name, offset):
    geometry = reference_geometry(offset, case["geometry"])
    model = checked_model(physical_root(offset), geometry)
    data = mujoco.MjData(model)
    pairs = measured_pairs(model)
    pair_stats = {}
    rows = []
    failures = []
    nonmatching = []
    contact_counts = Counter()
    fk_max = Counter()
    for state in case["states"]:
        step = state["physics_step"]
        residual = restore(model, data, state)
        for field, error in residual.items():
            fk_max[field] = max(fk_max[field], error)
        actual = []
        contact_ids = set()
        for c in data.contact:
            a, b = int(c.geom1), int(c.geom2)
            g1, g2 = model.geom(a).name, model.geom(b).name
            contact_ids.add((min(a, b), max(a, b)))
            category = contact_category(g1, g2)
            actual.append(
                {"pair": [g1, g2], "signed_dist_mm": float(c.dist) * 1000, "category": category}
            )
        for cat in {p["category"] for p in actual}:
            contact_counts[cat] += 1

        def signature(records):
            return sorted(tuple(sorted(r)) for r in records)

        archived = [(a, b) for a, b in state["contact_pairs"]]
        matched = signature(archived) == signature(r["pair"] for r in actual)
        if not matched:
            nonmatching.append(step)
        raw_mm = []
        fallbacks = []
        hazards = [
            {"type": "engine_contact", "pair": event["pair"], "signed_mm": event["signed_dist_mm"]}
            for event in actual
            if event["category"] == "unauthorized"
        ]
        for j, (a, b, i1, i2, gate) in enumerate(pairs):
            d = mujoco.mj_geomDistance(model, data, i1, i2, 3.0, None)
            require(np.isfinite(d) and d < 3, "MuJoCo distance unmeasured")
            raw_mm.append(float(d) * 1000)
            value, method = geometric_witness(model, data, i1, i2, d, contact_ids)
            vv = value * 1000
            if method != "mj_geomDistance":
                fallbacks.append([j, vv, method])
            if gate and value <= 0:
                hazards.append(
                    {
                        "type": "nonpositive_or_unproved_part_separation",
                        "pair": [a, b],
                        "signed_mm": vv,
                        "method": method,
                    }
                )
            if (a, b) not in pair_stats or vv < pair_stats[a, b]["signed_clearance_mm"]:
                pair_stats[a, b] = {
                    "pair": [a, b],
                    "step": step,
                    "signed_clearance_mm": vv,
                    "raw_mj_geomDistance_mm": d * 1000,
                    "method": method,
                }
        if hazards:
            failures.append({"step": step, "hazards": hazards})
        rows.append(
            {
                "step": step,
                "raw_signed_mm": raw_mm,
                "fallbacks": fallbacks,
                "contacts": actual,
                "archived_contacts": archived,
                "original_contacts_match": matched,
                "fk_residual": residual,
            }
        )
    relevant = [v for (a, b), v in pair_stats.items() if a in PARTS and b in {"hand", *FINGERS}]
    ordered = sorted(relevant, key=lambda x: x["signed_clearance_mm"])
    return (
        {
            "case": name,
            "first_step": 0,
            "last_step": rows[-1]["step"],
            "states": len(rows),
            "registered_asset_sha256": sha(physical_root(offset)),
            "source_truth_sha256": case["truth_sha256"],
            "query_pairs": len(pairs),
            "closest_hand_or_finger": ordered[0],
            "minimum_each_pair": list(pair_stats.values()),
            "first_failure": failures[0] if failures else None,
            "failed_steps": len(failures),
            "contact_steps": dict(contact_counts),
            "differing_contact_multiplicity_vs_source_steps": nonmatching,
            "max_restore_residual": dict(fk_max),
            "eligible": not failures,
        },
        {
            "case": name,
            "pair_order": [[a, b] for a, b, *_ in pairs],
            "states": rows,
            "violations": failures,
        },
    )


def dense(offset, output):
    cases, _ = collect()
    info = []
    details = []
    for name in ("d01", "d02"):
        r, rows = dense_case(cases[name], name, offset)
        info.append(r)
        details.append(rows)
    path = output / f"screen-clearance-{offset:02d}.public.json.gz"
    write(
        path,
        {
            "schema": "g1.visibility.dense-radial-distances.v1",
            "plan_sha256": PLAN,
            "offset_mm": offset,
            "units": (
                "millimetres for raw_signed_mm and fallback values. Pair order fixed per "
                "trajectory. Negative values denote penetration."
            ),
            "distance_source": (
                "MuJoCo mj_geomDistance cutoff 3m. Each zero without actual contact "
                "also has a separately reported conservative geometric witness."
            ),
            "trajectories": details,
        },
    )
    baseline = offset != 0 or (
        info[0]["first_failure"] is not None
        and info[0]["contact_steps"].get("unauthorized") == 1
        and info[1]["contact_steps"].get("unauthorized", 0) == 0
        and any(
            set(contact["pair"]) == {"left_finger_geom", "g1_dual_id7_plate"}
            for contact in details[0]["states"][1120]["contacts"]
        )
    )
    summary = {
        "schema": "g1.visibility.radial-clearance-screen.v1",
        "plan_sha256": PLAN,
        "offset_mm": offset,
        "detail_sha256": sha(path),
        "total_states": sum(r["states"] for r in info),
        "zero_integrations": True,
        "baseline_collision_reproduced": baseline if offset == 0 else None,
        "eligible": all(r["eligible"] for r in info),
        "trajectories": info,
    }
    write(output / f"screen-clearance-{offset:02d}-summary.public.json", summary)
    print(
        json.dumps(
            {
                k: summary[k]
                for k in ("offset_mm", "total_states", "eligible", "baseline_collision_reproduced")
            }
        ),
        flush=True,
    )
    for r in info:
        print(r["case"], r["closest_hand_or_finger"], r["first_failure"], flush=True)


def selection(output):
    original = read(output / "screen-clearance-00-summary.public.json")
    v2 = read(output / "screen-optical-00-summary.public.json")
    require(
        original["baseline_collision_reproduced"]
        and len(v2["failures"]) == 1
        and v2["failures"][0]["case"] == "d02"
        and v2["failures"][0]["step"] == 1088
        and v2["failures"][0]["paired_reason"] == "ambiguous_marker_identity",
        "baseline failures not reproduced",
    )
    outcomes = []
    selected = None
    for offset in (15, 30):
        a = output / f"screen-optical-{offset:02d}-summary.public.json"
        b = output / f"screen-clearance-{offset:02d}-summary.public.json"
        opt, clearance = read(a), read(b)
        require(
            opt["offset_mm"] == clearance["offset_mm"] == offset
            and opt["frame_count"] == 22
            and clearance["total_states"] == 2210
            and sha(output / f"screen-optical-{offset:02d}.public.json.gz")
            == opt["frame_details_sha256"]
            and sha(output / f"screen-clearance-{offset:02d}.public.json.gz")
            == clearance["detail_sha256"],
            "incomplete or mixed candidate screen",
        )
        valid = opt["eligible"] and clearance["eligible"]
        spec = radial.details(offset)
        outcomes.append(
            {
                "offset_mm": offset,
                "assembly_sha256": spec["asset_sha256"],
                "optical_pass": opt["eligible"],
                "clearance_pass": clearance["eligible"],
                "optical_summary_sha256": sha(a),
                "clearance_summary_sha256": sha(b),
                "first_failed_optical": next(iter(opt["failures"]), None),
                "first_failed_mechanical": {
                    r["case"]: r["first_failure"] for r in clearance["trajectories"]
                },
            }
        )
        if valid:
            selected = offset
            break
    summary = {
        "schema": "g1.visibility.radial-static-selection.v1",
        "plan_sha256": PLAN,
        "attempted": outcomes,
        "selected_offset_mm": selected,
        "eligible": selected is not None,
        "source_sha256": sha(Path(__file__)),
        "baseline_optical_summary_sha256": sha(output / "screen-optical-00-summary.public.json"),
        "baseline_clearance_summary_sha256": sha(
            output / "screen-clearance-00-summary.public.json"
        ),
        "scope": (
            "historical frozen-state static screens. New sensing, moving dynamics, grasp, "
            "lift, placement and release require separate development execution."
        ),
        "new_formal_or_hardware_trials": 0,
    }
    write(output / "screen-selection.public.json", summary)
    print(json.dumps(summary), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    for name in ("dense", "render"):
        cmd = sub.add_parser(name)
        cmd.add_argument("offset", type=int, choices=(0, 15, 30))
        if name == "render":
            cmd.add_argument("private", type=Path)
        cmd.add_argument("--output", type=Path, default=ROUND)
    pick = sub.add_parser("select")
    pick.add_argument("--output", type=Path, default=ROUND)
    args = parser.parse_args()
    if args.mode == "render":
        render_anchors(args.offset, args.private, args.output)
    elif args.mode == "dense":
        dense(args.offset, args.output)
    else:
        selection(args.output)


if __name__ == "__main__":
    main()
