"""Independently recount the sealed selection from RGB-D, instance labels, XML and old states."""

from __future__ import annotations

import argparse
import base64
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker
from cloud_edge_robot_arm.vision.servo import measure_registered_marker_grasp

PLAN_SHA = "62e4c93a03f37fcb1ebd20ac660c09837c225f2b9651960701725c742914bef7"
HAND = {"hand", "left_finger_geom", "right_finger_geom"}


def check(ok, reason):
    if not ok:
        raise ValueError(reason)


def local_points(f, world_marker):
    """Invert the 3×3 plane homography at all integer pixel centers."""
    fx, fy, cx, cy = f.intrinsics
    K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]])
    camera_marker = np.linalg.inv(np.asarray(f.camera_to_world).reshape(4, 4)) @ world_marker
    xy1 = K @ camera_marker[:3, [0, 1, 3]]
    v, u = np.indices((f.height, f.width))
    coordinates = np.linalg.solve(xy1, np.stack((u.ravel(), v.ravel(), np.ones(u.size))))
    optical = 1 / coordinates[2].reshape(u.shape)
    return (
        coordinates[0].reshape(u.shape) * optical,
        coordinates[1].reshape(u.shape) * optical,
        optical,
    )


def independent_areas(f, world_marker, ids, labels, bits):
    x, y, plane = local_points(f, world_marker)
    d = np.frombuffer(base64.b64decode(f.depth_float32_base64), "<f4").reshape(ids.shape)
    half = np.maximum(abs(x), abs(y))
    within = half <= 0.0375
    r = np.clip(np.floor((0.0375 - y) / 0.0125).astype(int), 0, 5)
    c = np.clip(np.floor((x + 0.0375) / 0.0125).astype(int), 0, 5)
    hand_ids = [int(k) for k, n in labels.items() if n in HAND]
    hand = np.isin(ids, hand_ids)
    out = {}
    for name, region in (
        ("black_cells", within & ~bits[r, c]),
        ("white_cells", within & bits[r, c]),
        ("quiet_white_margin", (half <= 0.05) & ~within),
    ):
        mask = region & (plane > 0)
        out[name] = {
            "pixels": int(mask.sum()),
            "hand_finger": int((mask & hand).sum()),
            "hand_finger_nearer_5mm": int((mask & hand & (d > 0) & (plane - d > 0.005)).sum()),
        }
    return out


def raw_frame(raw, roles, index, role):
    r = roles[role]
    row = index[r["key"]]
    f = RGBDObservation.model_validate(pinned(raw / "pixels" / row["file"], row["sha256"]))
    check(
        (r["frame_id"], r["episode"], r["checksum"], r["scene"], r["sim_time_s"])
        == (f.frame_id, f.episode_id, f.checksum_sha256, f.scene_id, f.sim_time_s),
        "foreign raw frame",
    )
    return f, row["sha256"], r


def capture_indexes(raw, selection, key):
    sealed = selection[key]
    cap = pinned(raw / "capture-seal.json", sealed["capture_sha256"])
    index = pinned(raw / "pixels/index.json", cap["index_sha256"])
    roles = pinned(raw / "roles.json", cap["roles_sha256"])
    decisions = pinned(raw / "blind-decisions.json", sealed["decisions_sha256"])
    check(
        all(
            r["allocation_sha256"] == selection["allocation_sha256"]
            for r in (cap, index, roles, decisions)
        ),
        "mixed bundle",
    )
    keys = [r["key"] for r in roles["roles"].values()]
    check(
        len(keys) == len(set(keys))
        and set(keys) == set(index["frames"]) == set(decisions["results"]),
        "missing or repeated frame",
    )
    return roles["roles"], index["frames"]


def measurement(f, mount):
    from cloud_edge_robot_arm.vision.marker_families import marker_family

    fam = marker_family(mount["family"])
    reg = PoseMarkerRegistration(fam.marker_id, fam.marker_size_m, fam.asset_sha256)
    normal = detect_pose_marker(f, reg)
    servo = detect_pose_marker(f, reg, corner_refinement="SUBPIX")
    try:
        grasp, _ = measure_registered_marker_grasp(f, fam.family_id)
    except ValueError:
        grasp = None
    positive, top = False, None
    if servo.status == "OBSERVED":
        H = np.asarray(f.camera_to_world).reshape(4, 4)
        positive = (np.linalg.inv(H) @ [*servo.marker_center_world_m, 1])[2] > 0
        marker = np.eye(4)
        marker[:3, :3] = np.asarray(servo.rotation_marker_to_world).reshape(3, 3)
        marker[:3, 3] = servo.marker_center_world_m
        obj = marker @ np.linalg.inv(np.asarray(fam.marker_to_object).reshape(4, 4))
        top = (obj @ [0, 0, 0.035, 1])[:3]
        if grasp is not None:
            check(np.allclose(grasp, (obj @ [0, 0, 0.01, 1])[:3], rtol=0, atol=1e-10), "wrong TCP")
    return {
        "default_observed": normal.status == "OBSERVED",
        "subpix_unique_id": list(servo.observed_marker_ids) == [7],
        "positive_marker_depth": bool(positive),
        "usable": bool(
            servo.status == "OBSERVED"
            and list(servo.observed_marker_ids) == [7]
            and positive
            and grasp is not None
        ),
    }, top


def verify(raw, public, output):
    plan = pinned(public / "plan.json", PLAN_SHA)
    select = read(public / "selection.public.json")
    results = pinned(
        public / "screen-results.public.json",
        select["public_results_sha256"]["screen-results.public.json"],
    )
    controls = pinned(
        public / "screen-controls.public.json",
        select["public_results_sha256"]["screen-controls.public.json"],
    )
    src = Path(plan["private_source"]) / "translated/episodes"
    roles, index = capture_indexes(raw, select, "screen_decision_seal")
    pr, pi = capture_indexes(raw / "probes", select, "probe_decision_seal")
    live = pinned(raw / "probes/registration.json", controls["registration_sha256"])
    check(live["dispatched_actions"] == live["physics_steps"] == 0, "registration advanced")
    stats, area_total, cases = {}, {}, {c["id"]: c for c in results["cases"]}
    check(set(cases) == {s[0] for s in plan["source_terminal"]}, "wrong stop denominator")
    for mount in plan["mounts"]:
        name = mount["id"]
        original_asset = ROOT / mount["asset_path"]
        check(sha(original_asset) == mount["asset_sha256"], "asset digest changed")
        xml = ET.fromstring(original_asset.read_bytes())
        colors = np.array(
            [
                [
                    float(
                        xml.find(f".//geom[@name='pose_marker_outboard_v3_r{r}c{c}']")
                        .get("rgba")
                        .split()[0]
                    )
                    > 0.5
                    for c in range(6)
                ]
                for r in range(6)
            ]
        )
        counts, errors, per_area = Counter(), [], {}
        for ident, step, _ in plan["source_terminal"]:
            truth_file = src / ident / "instance/offline-truth.json"
            truth = pinned(ROOT / truth_file, plan["input_sha256"][str(truth_file)])
            state = truth["samples"][-1]
            rec = cases[ident]["mounts"][name]
            f, frame_sha, r = raw_frame(raw, roles, index, f"{ident}/{name}/normal")
            check(
                state["physics_step"] == step
                and f.sim_time_s == state["sim_time_s"]
                and f.calibration_version == plan["camera_calibration_version"]
                and r["source_episode"] == truth["episode"]
                and frame_sha == rec["frame_sha256"],
                "wrong state, pose or nominal frame identity",
            )
            metrics, top = measurement(f, mount)
            counts.update({k: int(v) for k, v in metrics.items()})
            counts["evaluated"] += 1
            check(metrics["usable"] == rec["observed"]["usable"], "per-frame decision differs")
            obj = np.eye(4)
            obj[:3, 3] = state["object_geom_position_m"]
            obj[:3, :3] = np.asarray(state["object_geom_rotation_row_major"]).reshape(3, 3)
            target = (obj @ [0, 0, state["object_half_extent_m"][2], 1])[:3]
            if top is not None:
                errors.append(float(np.linalg.norm(top - target)))
            local_attach = np.eye(4)
            local_attach[:3, 3] = mount["object_T_marker_translation_m"]
            seg = r["segmentation"]
            path = raw / "segmentation" / seg["file"]
            check(sha(path) == seg["sha256"] == rec["segmentation_sha256"], "wrong instance map")
            areas = independent_areas(
                f, obj @ local_attach, np.load(path, allow_pickle=False), seg["labels"], colors
            )
            for key, v in areas.items():
                reported = rec["regions"]["areas"][key]
                check(
                    v["pixels"] == reported["pixels"]
                    and v["hand_finger"] == sum(reported["role_pixels"].get(n, 0) for n in HAND)
                    and v["hand_finger_nearer_5mm"]
                    == sum(reported["nearer_5mm_by_role"].get(n, 0) for n in HAND),
                    "independent projected counts differ",
                )
                per_area.setdefault(key, Counter()).update(v)
        counts["probe_successes"] = 0
        for i in range(len(plan["qualification_probe_poses_xyz_yaw"])):
            for kind in ("normal", "absent", "invalid-depth"):
                key = f"{name}/{i}/{kind}"
                f, frame_sha, _ = raw_frame(raw / "probes", pr, pi, key)
                observed, _ = measurement(f, mount)
                registered = live["results"][key]
                result = controls["zero_step"][name]["poses"][i]["results"][kind]
                check(
                    registered == result["tracker"]
                    and frame_sha == result["frame_sha256"]
                    and observed["usable"] == result["usable"],
                    "wrong probe source/result",
                )
                if kind == "normal":
                    counts["probe_successes"] += int(registered["ok"])
                else:
                    check(
                        not observed["usable"] and not registered["ok"], "negative control accepted"
                    )
        p90 = float(1000 * np.quantile(errors, 0.9)) if errors else None
        registered_counts = select["ranking"][name]
        check(
            all(registered_counts[k] == v for k, v in counts.items())
            and registered_counts["conditional_top_error_n"] == len(errors)
            and (
                (p90 is None and registered_counts["conditional_top_error_p90_mm"] is None)
                or (
                    p90 is not None
                    and abs(registered_counts["conditional_top_error_p90_mm"] - p90) < 1e-9
                )
            ),
            "independent denominators/error distribution differ",
        )
        stats[name] = {
            **counts,
            "conditional_top_error_n": len(errors),
            "conditional_top_error_p90_mm": p90,
        }
        area_total[name] = per_area
    candidates = [
        m["id"]
        for m in plan["mounts"]
        if m["id"] != "original" and stats[m["id"]]["probe_successes"] > 0
    ]
    winner = (
        max(candidates, key=lambda n: (stats[n]["usable"], n == "r579")) if candidates else "r579"
    )
    check(winner == select["selected_mount"], "wrong selected family")
    write(
        output,
        {
            "schema": "g1.screen.independent-v1",
            "plan_sha256": PLAN_SHA,
            "selection_sha256": sha(public / "selection.public.json"),
            "selected_mount": winner,
            "verify_source_sha256": sha(Path(__file__)),
            "recount": stats,
            "homography_raw_hand_finger_counts": area_total,
            "normal_stopping_frames": 24,
            "zero_step_frames_and_control_derivatives": len(pi),
            "screen_packet_count": len(index),
            "evidence": (
                "Original RGB-D and native detector, archived truth and instance rasters, "
                "checked by inverse planar homography."
            ),
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("round", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    verify(args.raw, args.round, args.output)
