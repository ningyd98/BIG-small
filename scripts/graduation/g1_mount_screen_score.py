"""Unblind screened mounts and independently check pose, depth ordering and qualification."""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

import numpy as np
from scripts.graduation import g1_mount_geometry as geo
from scripts.graduation import proposal_camera as cam
from scripts.graduation.g1_mount_screen import MOUNT_IDS, PLAN_SHA, choose, source_states
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write
from scripts.graduation.proposal_terminal_visibility import HAND

from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration


def validate_role(f, r, g, expected_file_sha, decision):
    geo.require(cam.camera_meta(f) == g["camera"], "foreign camera or calibration")
    geo.require(
        (
            r["episode"],
            r["scene"],
            r["frame_id"],
            r["checksum"],
            r["sim_time_s"],
            r["calibration_version"],
        )
        == (
            f.episode_id,
            f.scene_id,
            f.frame_id,
            f.checksum_sha256,
            f.sim_time_s,
            f.calibration_version,
        )
        and decision["checksum"] == f.checksum_sha256
        and decision["frame_id"] == f.frame_id
        and decision["frame_sha256"] == expected_file_sha,
        "foreign episode, frame or SHA",
    )


class Evidence:
    def __init__(self, raw, h):
        self.raw = raw
        self.seal = read(raw / "decision-seal.json")
        cap = pinned(raw / "capture-seal.json", self.seal["capture_sha256"])
        idx = pinned(raw / "pixels/index.json", cap["index_sha256"])
        roles = pinned(raw / "roles.json", cap["roles_sha256"])
        dec = pinned(raw / "blind-decisions.json", self.seal["decisions_sha256"])
        self.frames, self.roles, self.decisions = idx["frames"], roles["roles"], dec["results"]
        ids = [r["key"] for r in self.roles.values()]
        geo.require(
            all(d["allocation_sha256"] == h for d in (cap, idx, roles, dec))
            and dec["index_sha256"] == cap["index_sha256"]
            and len(ids) == len(set(ids))
            and set(ids) == set(self.frames) == set(self.decisions)
            and len({r["frame_id"] for r in self.roles.values()}) == len(ids),
            "mixed/duplicate/missing actual frame or source seal",
        )

    def get(self, role, g):
        r = self.roles[role]
        k = r["key"]
        file = self.frames[k]
        f = cam.load_frame(self.raw / "pixels", file)
        d = self.decisions[k]
        validate_role(f, r, g, file["sha256"], d)
        return f, r, d


def area_counts(area, ids, names, arm_geoms, z, optical, codes, goal_cells):
    n = int(area.sum())
    roles, near5, near20, behind5 = Counter(), Counter(), Counter(), Counter()
    with_depth, exact = Counter(), 0
    depth_difference = z - optical
    for idx, count in zip(*np.unique(ids[area], return_counts=True), strict=True):
        name = names.get(str(idx), "background")
        cell = re.fullmatch(geo.PREFIX + r"r([0-5])c([0-5])", name)
        if cell:
            row, col = map(int, cell.groups())
            label = "white_cell" if codes[row, col] else "black_cell"
            exact += int((area & (ids == idx) & (goal_cells == row * 6 + col)).sum())
        elif name == geo.PREFIX + "quiet":
            label = "white_board"
            exact += int((area & (ids == idx) & (goal_cells == -1)).sum())
        elif name in HAND:
            label = name
        elif name in arm_geoms:
            label = "other_robot"
        else:
            label = name
        roles[label] += int(count)
        valid = area & (ids == idx) & (optical > 0)
        with_depth[label] += int(valid.sum())
        near5[label] += int((valid & (depth_difference > 0.005)).sum())
        near20[label] += int((valid & (depth_difference > 0.020)).sum())
        behind5[label] += int((valid & (depth_difference < -0.005)).sum())
    geo.require(sum(roles.values()) == n and n > 0, "incomplete projected cells/quiet")
    geometric = area & (optical > 0)
    return {
        "pixels": n,
        "correct_instance_pixels": exact,
        "role_pixels": dict(roles),
        "role_fraction": {r: c / n for r, c in roles.items()},
        "positive_depth_pixels": dict(with_depth),
        "nearer_5mm_by_role": dict(near5),
        "nearer_20mm_by_role": dict(near20),
        "behind_5mm_by_role": dict(behind5),
        "plane_minus_observed_depth_p50_m": float(np.median(depth_difference[geometric]))
        if np.any(geometric)
        else None,
    }


def projected_regions(f, state, g, ids, names, arms):
    H = np.asarray(f.camera_to_world).reshape(4, 4)
    rot = np.asarray(state["object_geom_rotation_row_major"]).reshape(3, 3)
    mount = np.asarray(g["marker_to_object"]).reshape(4, 4)
    center = np.asarray(state["object_geom_position_m"]) + rot @ mount[:3, 3]
    orientation = rot @ mount[:3, :3]
    fx, fy, cx, cy = f.intrinsics
    y, x = np.indices(ids.shape)
    rays = np.stack(((x - cx) / fx, (y - cy) / fy, np.ones_like(x)), axis=-1) @ H[:3, :3].T
    normal = orientation[:, 2]
    camera = H[:3, 3]
    z = ((center - camera) @ normal) / (rays @ normal)
    xy = (camera - center + z[..., None] * rays) @ orientation[:, :2]
    away = np.abs(xy).max(axis=2)
    printed, board = (away <= 0.0375) & (z > 0), (away <= 0.05) & (z > 0)
    col = np.clip(np.floor((xy[:, :, 0] + 0.0375) / 0.0125).astype(int), 0, 5)
    row = np.clip(np.floor((0.0375 - xy[:, :, 1]) / 0.0125).astype(int), 0, 5)
    codes = geo.bits()
    white = codes[row, col]
    target = np.where(printed, row * 6 + col, -1)
    depth = cam.depth(f)
    out = {}
    for label, mask in (
        ("black_cells", printed & ~white),
        ("white_cells", printed & white),
        ("quiet_white_margin", board & ~printed),
    ):
        out[label] = area_counts(mask, ids, names, arms, z, depth, codes, target)
    # Check the projected corners, including the quiet edge, against the actual image.
    corners = np.array(
        [
            center + orientation @ [i * 0.05, j * 0.05, 0]
            for i, j in ((-1, 1), (1, 1), (1, -1), (-1, -1))
        ]
    )
    optical = (corners - camera) @ H[:3, :3]
    uv = np.column_stack(
        (fx * optical[:, 0] / optical[:, 2] + cx, fy * optical[:, 1] / optical[:, 2] + cy)
    )
    return {
        "areas": out,
        "board_corners_px": uv.tolist(),
        "all_board_corners_in_frustum": bool(
            (optical[:, 2] > 0).all() and ((uv >= 0) & (uv < [f.width, f.height])).all()
        ),
        "front_normal_to_camera_dot_m": float(normal @ (camera - center)),
    }


def rejected(call, *args):
    try:
        call(*args)
    except ValueError as exc:
        return str(exc)
    raise ValueError("negative control unexpectedly accepted")


def pose_errors(e, truth, g):
    R = np.asarray(truth["object_rotation"]).reshape(3, 3)
    center = np.asarray(truth["object_center_m"])
    attach = np.asarray(g["marker_to_object"]).reshape(4, 4)
    tcp = np.asarray(g["object_to_tcp"]).reshape(4, 4)
    expected = {
        "marker_center_world_m": center + R @ attach[:3, 3],
        "object_center_world_m": center,
        "object_top_center_world_m": center + R[:, 2] * g["object_half_extent_m"][2],
        "grasp_world_m": center + R @ tcp[:3, 3],
    }
    val = {**e["estimates"]["SUBPIX"], "grasp_world_m": e["grasp_world_m"]}
    errors = {
        k: None if val[k] is None else float(np.linalg.norm(np.asarray(val[k]) - v))
        for k, v in expected.items()
    }
    measured = val["rotation_to_world"]
    errors["object_rotation_geodesic_rad"] = (
        None
        if measured is None
        else float(
            np.arccos(np.clip((np.trace(R.T @ np.asarray(measured).reshape(3, 3)) - 1) / 2, -1, 1))
        )
    )
    return errors


def primitive_controls(frame, r, decision, measurement, geometry, wrong_geo):
    point = measurement["grasp_world_m"]
    e = measurement["estimates"]["SUBPIX"]
    marker = e["marker_center_world_m"]
    rot = measurement["marker_rotation_row_major"]
    geo.require(
        point is not None
        and measurement["wrong_id8"]["status"] == "UNKNOWN"
        and measurement["wrong_id8"]["observed_ids"] == [7],
        "missing positive wrong-ID control",
    )
    expected = decision["frame_sha256"]
    return {
        "wrong_id8": measurement["wrong_id8"],
        "wrong_attachment_at_tcp": rejected(geo.verify_target, wrong_geo, marker, rot, point),
        "marker_center_as_tcp": rejected(geo.verify_target, geometry, marker, rot, marker),
        "wrong_episode": rejected(
            validate_role, frame, {**r, "episode": "foreign"}, geometry, expected, decision
        ),
        "wrong_frame": rejected(
            validate_role, frame, {**r, "frame_id": "foreign"}, geometry, expected, decision
        ),
        "wrong_sha": rejected(validate_role, frame, r, geometry, "0" * 64, decision),
        "wrong_camera": rejected(
            validate_role,
            frame,
            r,
            {**geometry, "camera": {**geometry["camera"], "calibration_version": "foreign"}},
            expected,
            decision,
        ),
        "wrong_native_asset": rejected(
            NativeGeometryRegistration, {**geometry, "asset_path": wrong_geo["asset_path"]}
        ),
        "wrong_native_attachment": rejected(
            NativeGeometryRegistration,
            {**geometry, "marker_to_object": wrong_geo["marker_to_object"]},
        ),
    }


def score(raw, a, h, out):
    ev = Evidence(raw, h)
    pv = Evidence(raw / "probes", h)
    reg = read(raw / "probes/registration.json")
    geo.require(
        reg["capture_sha256"] == pv.seal["capture_sha256"]
        and reg["screen_decisions_sha256"] == ev.seal["decisions_sha256"]
        and reg["physics_steps"] == reg["dispatched_actions"] == 0,
        "mixed tracker evidence",
    )
    geom = {m: d["descriptor"] for m, d in a["families"].items()}
    native = {m: d["native_error"] is None for m, d in a["families"].items()}
    spec = pinned(ROOT / a["plan"], PLAN_SHA)
    results, controls = [], {}
    summary = {
        m: dict(
            evaluated=0,
            usable=0,
            default_observed=0,
            subpix_unique_id=0,
            positive_marker_depth=0,
            native=native[m],
            probe_successes=0,
        )
        for m in MOUNT_IDS
    }
    for s in a["source_terminals"]:
        ident = s["id"]
        location, states = source_states(a, s)
        state = states[s["step"]]
        vg = a["historical_geometry"][s["source_view"]]
        old_decisions = Path(a["episodes"]) / ident / "instance/decisions.json"
        archived = pinned(location / "decisions.json", spec["input_sha256"][str(old_decisions)])
        stored = {r["frame_id"]: r["estimate"] for r in archived["decisions"]}
        evidence = {}
        for role, ref in zip(("previous", "rejected", "terminal"), s["references"], strict=True):
            f, r, d = ev.get(f"{ident}/source/{role}", vg)
            measure = d["by_mount"]["original"]
            geo.require(
                f.frame_id == ref["frame_id"]
                and r["original_sha256"] == ref["file_sha256"]
                and f.episode_id == s["episode"]
                and measure["estimates"]["SUBPIX"] == stored[f.frame_id],
                "archived RGB-D decision/identity changed",
            )
            use_replay = role == "previous" or s["source_view"] == "translated"
            replay_role = (
                f"{ident}/replay/" + ("previous" if role == "previous" else "rejected")
                if use_replay
                else f"{ident}/original/normal"
            )
            new, rr, dd = ev.get(replay_role, vg)
            candidate = dd["by_mount"]["original"]
            residuals = {**rr["residuals"], **cam.compare(f, new)}
            verified = (
                all(residuals[k] <= limit for k, limit in cam.CHECK_LIMITS.items())
                and measure["usable"] == candidate["usable"] == (role == "previous")
                and measure["estimates"]["SUBPIX"]["ids"] == candidate["estimates"]["SUBPIX"]["ids"]
            )
            evidence[role] = {
                "verified": verified,
                "usable": measure["usable"],
                "replay_usable": candidate["usable"],
                "source_checksum": f.checksum_sha256,
                "replay_checksum": new.checksum_sha256,
                "residuals": residuals,
            }
        old, _, old_dec = ev.get(f"{ident}/archived-nominal", geom["original"])
        nominal, _, nom_dec = ev.get(f"{ident}/original/normal", geom["original"])
        residuals = cam.compare(old, nominal)
        evidence["prior_nominal_replay"] = {
            "residuals": residuals,
            "verified": all(v <= cam.CHECK_LIMITS[k] for k, v in residuals.items())
            and old_dec["by_mount"]["original"]["usable"]
            == nom_dec["by_mount"]["original"]["usable"],
        }
        geo.require(
            all(r["verified"] for r in evidence.values()),
            "archived same-state reconstruction failed: " + ident,
        )
        rows, pair_hashes, seeds = {}, set(), set()
        for m, g in geom.items():
            f, r, d = ev.get(f"{ident}/{m}/normal", g)
            item = d["by_mount"][m]
            e = item["estimates"]["SUBPIX"]
            seg = r["segmentation"]
            file = raw / "segmentation" / seg["file"]
            geo.require(
                sha(file) == seg["sha256"]
                and r["step"] == state["physics_step"]
                and r["source_episode"] == s["episode"]
                and f.sim_time_s == state["sim_time_s"],
                "wrong segmentation or dense state",
            )
            pair_hashes.add(r["state_sha256"])
            seeds.add(r["seed"])
            rows[m] = {
                "frame_sha256": d["frame_sha256"],
                "frame_id": f.frame_id,
                "sensor_checksum": f.checksum_sha256,
                "observed": item,
                "errors_m_except_rotation_rad": pose_errors(item, r["geometry"], g),
                "regions": projected_regions(
                    f, state, g, np.load(file, allow_pickle=False), seg["labels"], r["arm_geoms"]
                ),
                "board_to_hand_surface_distance_m": r["geometry"][
                    "board_to_hand_surface_distance_m"
                ],
                "fk_residuals": r["residuals"],
                "segmentation_sha256": seg["sha256"],
            }
            summary[m]["evaluated"] += 1
            summary[m]["usable"] += int(item["usable"])
            summary[m]["default_observed"] += int(item["estimates"]["NONE"]["status"] == "OBSERVED")
            summary[m]["subpix_unique_id"] += int(e["ids"] == [7])
            summary[m]["positive_marker_depth"] += int(
                (e["marker_center_optical_depth_m"] or 0) > 0
            )
        geo.require(len(pair_hashes) == len(seeds) == 1, "mount state/time/noise mismatch")
        results.append(
            {
                "id": ident,
                "source_episode": s["episode"],
                "source_step": s["step"],
                "source_role": s["label"],
                "source_view": s["source_view"],
                "reconstructions": evidence,
                "seed": next(iter(seeds)),
                "same_kinematic_state_sha256": next(iter(pair_hashes)),
                "mounts": rows,
            }
        )
    zero = {}
    for m, g in geom.items():
        wrong = geom["r579" if m == "original" else "original"]
        zero[m] = {"native_error": a["families"][m]["native_error"], "poses": []}
        for i, pose in enumerate(a["probe_poses"]):
            given = {}
            for mode in ("normal", "absent", "invalid-depth"):
                key = f"{m}/{i}/{mode}"
                f, r, d = pv.get(key, g)
                e = d["by_mount"][m]
                live = reg["results"][key]
                if mode == "normal":
                    normal = r
                    truth = r["geometry"]
                    geo.require(
                        np.allclose(truth["object_center_m"], pose[:3], atol=1e-12, rtol=0)
                        and math.isclose(
                            np.arctan2(truth["object_rotation"][3], truth["object_rotation"][0]),
                            pose[3],
                            abs_tol=1e-12,
                        ),
                        "wrong neutral reset/yaw",
                    )
                    if native[m] and not live["ok"]:
                        # A supported reset may fail current-image detector or region checks.
                        reasons = (
                            "initial registered geometry unavailable:",
                            "registered marker unavailable:",
                            "registered v2 reference unavailable:",
                            "unique registered green region unavailable",
                        )
                        geo.require(
                            live["stage"] == "tracker_bootstrap"
                            and live["reason"].startswith(reasons),
                            "unexpected native probe failure: " + live["reason"],
                        )
                    summary[m]["probe_successes"] += int(live["ok"])
                    if e["usable"]:
                        controls[key] = primitive_controls(f, r, d, e, g, wrong)
                else:
                    geo.require(
                        r["state_sha256"] == normal["state_sha256"]
                        and not e["usable"]
                        and not live["ok"],
                        "negative control accepted or changed physical state",
                    )
                    if mode == "invalid-depth":
                        geo.require(
                            r["parent_checksum"] == normal["checksum"]
                            and np.count_nonzero(cam.depth(f)) == 0,
                            "invalid-depth control differs from normal source",
                        )
                if not native[m]:
                    geo.require(
                        live["stage"] == "native_geometry"
                        and live["reason"] == a["families"][m]["native_error"],
                        "unregistered family crossed native policy",
                    )
                given[mode] = {
                    "tracker": live,
                    "subpix": e["estimates"]["SUBPIX"],
                    "none": e["estimates"]["NONE"],
                    "tcp": e["grasp_world_m"],
                    "usable": e["usable"],
                    "frame_sha256": d["frame_sha256"],
                    "checksum": f.checksum_sha256,
                    "state_sha256": r["state_sha256"],
                    "errors_m_except_rotation_rad": pose_errors(e, truth, g),
                }
            zero[m]["poses"].append({"xyz_yaw": pose, "results": given})
    # If a real reset has no marker pixels, retain that rejection. Sealed positive historical
    # frames also exercise the independent source and TCP controls with the correct family.
    for rr in results:
        for m, mr in rr["mounts"].items():
            if mr["observed"]["usable"]:
                key = f"{rr['id']}/{m}/normal"
                f, r, d = ev.get(key, geom[m])
                controls[key] = primitive_controls(
                    f,
                    r,
                    d,
                    mr["observed"],
                    geom[m],
                    geom["r579" if m == "original" else "original"],
                )
    geo.require(controls, "no measured positive for the independent negative controls")
    for m in MOUNT_IDS:
        errors = [
            row["mounts"][m]["errors_m_except_rotation_rad"]["object_top_center_world_m"]
            for row in results
        ]
        valid = [x for x in errors if x is not None]
        summary[m]["conditional_top_error_n"] = len(valid)
        summary[m]["conditional_top_error_p90_mm"] = (
            float(1000 * np.quantile(valid, 0.9)) if valid else None
        )
    selected = choose(summary)
    prefix = {
        "plan_sha256": PLAN_SHA,
        "allocation_sha256": h,
        "screen_decision_seal": ev.seal,
        "probe_decision_seal": pv.seal,
        "sources_sha256": a["sources_sha256"],
    }
    files = {
        "screen-geometry.public.json": {
            "geometry": a["mechanics"],
            "scope": (
                "Massless, noncolliding board geoms share the cube free body. A physical support "
                "spanning each gap would require independent mass and interference measurements."
            ),
        },
        "screen-results.public.json": {
            "cases": results,
            "by_mount": summary,
            "verified_source_positive_rejected_terminal_and_prior_nominal": len(results),
            "normal_mount_frames": sum(r["evaluated"] for r in summary.values()),
            "controls_and_robot_visible": True,
            "noise_std_m": a["noise_std_m"],
            "decision_index_frame_count": len(ev.frames),
        },
        "screen-controls.public.json": {
            "zero_step": zero,
            "controls_from_real_positives": controls,
            "dispatched_actions": reg["dispatched_actions"],
            "physics_steps": reg["physics_steps"],
            "registration_sha256": sha(raw / "probes/registration.json"),
            "native_inventory_sha256": reg["native_inventory_sha256"],
        },
    }
    for filename, data in files.items():
        write(out / filename, {**prefix, **data})
    mount = next(m for m in a["mounts"] if m["id"] == selected)
    write(
        out / "selection.public.json",
        {
            **prefix,
            "schema": "g1.marker-mount.selection.v1",
            "selected_mount": selected,
            "selected_family": mount["family"],
            "selected_asset_sha256": mount["asset_sha256"],
            "selection_basis": "legal reset fallback"
            if not summary[selected]["probe_successes"]
            else "real native probe and eight fixed stopping states",
            "ranking": summary,
            "native_reasons": {m: z["native_error"] for m, z in zero.items()},
            "public_results_sha256": {name: sha(out / name) for name in files},
            "screen_inputs_and_outputs_sealed_before_fresh_trials": True,
            "formal_claims": 0,
        },
    )
