"""Project frozen G1 RGB-D onto its prints and test named zero-step visual interventions."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path
from xml.etree import ElementTree

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "experiments/results/g1-formal-paired-20261124"
RUNTIME = ARCHIVE / "runtime-source"
ROUND = (
    ROOT
    / "artifacts/research/process/20261004-ced-development/astra-rounds"
    / "round-g1-formal-failure-observation-20261124"
)
PLAN_SHA = "31d5db8c1fea5aa9bdccdef8a2ccceac66dabaa5382ad5488ca2d6bc2d5f4767"
HAND = ("hand", "left_finger_geom", "right_finger_geom")
SIDE = ("plus_y", "plus_x", "minus_y", "minus_x")
SIGN = np.array([[-1, 1], [1, 1], [1, -1], [-1, -1]])
CASES = [f"f{i:02}-{arm}" for i in range(1, 5) for arm in ("original", "dual")]
LABELS = {"7": (255, 220, 55), "8": (80, 242, 252)}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(value):
    if isinstance(value, Path):
        with value.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest_array(value):
    return sha(np.ascontiguousarray(value).tobytes())


def json_file(path, value, *, compact=False):
    data = (
        canonical(value)
        if compact
        else json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode()
    )
    data += b"\n"
    if path.suffix == ".gz":
        data = gzip.compress(data, compresslevel=6, mtime=0)
    with path.open("xb") as stream:
        stream.write(data)
    return sha(data)


def read_pinned(path, expected):
    content = path.read_bytes()
    require(sha(content) == expected, "source digest differs: " + str(path))
    return json.loads(content)


def transforms(model, geometry):
    """Bind the polygons to the compiled asset, including the 20 µm print relief."""
    dual = geometry.get("development_dual", {}).get("markers")
    markers = dual or {"7": {"object_T_marker": geometry["marker_to_object"]}}
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    result = {}
    for code, registration in markers.items():
        prefix = f"g1_dual_id{code}_" if dual else "pose_marker_outboard_v3_"
        quiet = model.geom(prefix + "quiet")
        paper = np.eye(4)
        paper[:3, 3] = quiet.pos + [0, 0, quiet.size[2]]
        marker = np.reshape(registration["object_T_marker"], (4, 4))
        half = geometry["pose_marker"]["marker_size_m"] / 2
        bits = cv2.aruco.generateImageMarker(dictionary, int(code), 6) > 0
        require(
            np.allclose(quiet.quat, [1, 0, 0, 0]) and np.allclose(quiet.size[:2], [0.05, 0.05]),
            "unexpected paper",
        )
        require(
            np.allclose(paper[:2, 3], marker[:2, 3]) and np.allclose(marker[:3, :3], np.eye(3)),
            "unexpected mounting",
        )
        for y in range(6):
            for x in range(6):
                cell = model.geom(prefix + f"r{y}c{x}")
                expected = marker @ [(x - 2.5) * half / 3, (2.5 - y) * half / 3, 0, 1]
                require(
                    np.allclose(cell.pos + [0, 0, cell.size[2]], expected[:3], rtol=0, atol=1e-10)
                    and np.allclose(cell.size[:2], half / 6)
                    and bool(cell.rgba[0] > 0.5) == bool(bits[y, x]),
                    "registered ink differs from compiled cell",
                )
        result[code] = dict(
            paper=paper,
            marker=marker,
            paper_half=float(quiet.size[0]),
            print_half=float(half),
            bits=bits,
        )
    return result


def project_plane(camera_object, transform, half, K):
    h = K @ (camera_object @ transform)[:3, [0, 1, 3]]
    quad_h = np.column_stack([SIGN * half, np.ones(4)]) @ h.T
    require((quad_h[:, 2] > 0).all(), "board lies behind camera")
    return h, quad_h[:, :2] / quad_h[:, 2, None]


def edge_distances(u, v, quad):
    bands, closest = {}, np.full(u.shape, np.inf)
    for label, start, end in zip(SIDE, quad, np.roll(quad, -1, axis=0), strict=True):
        edge = end - start
        dx, dy = u - start[0], v - start[1]
        t = (dx * edge[0] + dy * edge[1]) / np.dot(edge, edge)
        dist = np.hypot(dx - np.clip(t, 0, 1) * edge[0], dy - np.clip(t, 0, 1) * edge[1])
        bands[label] = (t >= 0) & (t <= 1) & (dist <= 1.5)
        closest = np.minimum(closest, dist)
    return bands, closest


def polygon_geometry(frame, state, spec):
    fx, fy, cx, cy = frame.intrinsics
    K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]])
    obj = np.eye(4)
    obj[:3, :3] = np.reshape(state["object_geom_rotation_row_major"], (3, 3))
    obj[:3, 3] = state["object_geom_position_m"]
    cam_obj = np.linalg.solve(np.reshape(frame.camera_to_world, (4, 4)), obj)
    paper_h, paper_xy = project_plane(cam_obj, spec["paper"], spec["paper_half"], K)
    print_h, print_xy = project_plane(cam_obj, spec["marker"], spec["print_half"], K)
    low = np.maximum(0, np.floor(paper_xy.min(axis=0)).astype(int) - 8)
    high = np.minimum([frame.width, frame.height], np.ceil(paper_xy.max(axis=0)).astype(int) + 9)
    require(np.all(high > low), "projected paper is outside frame")
    roi = np.s_[low[1] : high[1], low[0] : high[0]]
    v, u = np.mgrid[roi]
    pixels = np.stack((u.ravel(), v.ravel(), np.ones(u.size)))

    def coordinates(homography):
        local = (np.linalg.inv(homography) @ pixels).reshape(3, *u.shape)
        return local[0] / local[2], local[1] / local[2], 1 / local[2]

    px, py, paper_z = coordinates(paper_h)
    x, y, print_z = coordinates(print_h)
    hp, hi = spec["paper_half"], spec["print_half"]
    paper, ink = np.maximum(abs(px), abs(py)) <= hp, np.maximum(abs(x), abs(y)) <= hi
    row = np.clip(np.floor((hi - y) * 3 / hi).astype(int), 0, 5)
    col = np.clip(np.floor((x + hi) * 3 / hi).astype(int), 0, 5)
    border = (row == 0) | (row == 5) | (col == 0) | (col == 5)
    bits = spec["bits"][row, col]
    areas = dict(
        paper=paper,
        printed=ink,
        quiet=paper & ~ink,
        black_border=ink & border,
        payload_4x4=ink & ~border,
        black_cells=ink & ~bits,
        white_cells=ink & bits,
    )
    for purpose, quad in (("paper", paper_xy), ("print", print_xy)):
        bands, distance = edge_distances(u, v, quad)
        for name, mask in bands.items():
            areas[f"{purpose}_edge_{name}"] = mask
        for i, point in enumerate(quad):
            ux, vy = np.rint(point).astype(int)
            areas[f"{purpose}_corner_{i}"] = (abs(u - ux) <= 1) & (abs(v - vy) <= 1)
        if purpose == "paper":
            for a, b in ((0, 1.5), (1.5, 3), (3, 6)):
                areas[f"outside_paper_{a:g}_{b:g}px"] = ~paper & (distance > a) & (distance <= b)
    plane = np.where(ink, print_z, paper_z)
    require((plane > 0).all(), "invalid optical-Z projection")
    return dict(roi=roi, areas=areas, plane=plane, paper_xy=paper_xy, print_xy=print_xy)


def geometry_evidence(frame, geom, depth):
    z = depth[geom["roi"]]
    valid = (z > 0) & np.isfinite(z)
    delta = geom["plane"] - z
    near5, near20 = valid & (delta > 0.005), valid & (delta > 0.020)
    entries = {}
    for name, mask in geom["areas"].items():
        n, nvalid = int(mask.sum()), int((mask & valid).sum())
        f5, f20 = int((mask & near5).sum()), int((mask & near20).sum())
        entries[name] = dict(
            pixel_centers=n,
            valid=nvalid,
            foreground_gt5mm=f5,
            foreground_gt20mm=f20,
            fraction_gt5mm_of_valid=f5 / nvalid if nvalid else None,
            fraction_gt20mm_of_valid=f20 / nvalid if nvalid else None,
        )
    paper = geom["paper_xy"]
    bounds = np.r_[
        paper[:, 0].min(),
        paper[:, 1].min(),
        frame.width - 1 - paper[:, 0].max(),
        frame.height - 1 - paper[:, 1].max(),
    ]
    meta = dict(
        paper_corners_px=paper.tolist(),
        print_corners_px=geom["print_xy"].tolist(),
        paper_image_margins_ltrb_px=bounds.tolist(),
        frozen_depth_regions=entries,
    )
    return meta, near5, near20


def geom_hist(ids, mask, labels):
    values, counts = np.unique(ids[mask], return_counts=True)
    return {labels.get(int(i), "background"): int(n) for i, n in zip(values, counts, strict=True)}


def static_area_evidence(geom, source, normal, hidden, near5, near20):
    roi = geom["roi"]
    rgb, observed_depth = source
    baseline = normal["rgb"][roi]
    ids, labels = normal["geom"][roi], normal["labels"]
    rgb_diff = np.max(abs(rgb[roi].astype(int) - baseline.astype(int)), axis=2)
    dz = abs(observed_depth[roi] - normal["depth"][roi])
    aligned = (
        (rgb_diff <= 2) & (observed_depth[roi] > 0) & (normal["depth"][roi] > 0) & (dz <= 0.005)
    )
    hand_ids = [gid for gid, name in labels.items() if name in HAND]
    hand = np.isin(ids, hand_ids)
    delta_rgb = np.any(baseline != hidden["rgb"][roi], axis=2)
    evidence = {}
    for name, a in geom["areas"].items():
        evidence[name] = {
            "pixel_centers": int(a.sum()),
            "normal_source_rgb_different_px": int((a & (rgb_diff > 0)).sum()),
            "normal_source_rgb_max_abs_uint8": int(rgb_diff[a].max()) if a.any() else None,
            "aligned_rgb2_depth5mm_px": int((a & aligned).sum()),
            "named_hand_pixels": geom_hist(ids, a & hand, labels),
            "geom_at_original_foreground_gt5mm": geom_hist(ids, a & near5, labels),
            "geom_at_original_foreground_gt20mm": geom_hist(ids, a & near20, labels),
            "aligned_geom_at_original_foreground_gt5mm": geom_hist(
                ids, a & near5 & aligned, labels
            ),
            "normal_to_combined_hidden_rgb_changed_px": int((a & delta_rgb).sum()),
        }
    return evidence


def edge_alignment(original, normal, paper):
    x, y = np.maximum(np.floor(paper.min(axis=0)).astype(int) - 5, 0)
    xx, yy = np.minimum(
        np.ceil(paper.max(axis=0)).astype(int) + 6, [original.shape[1], original.shape[0]]
    )
    crop = np.s_[y:yy, x:xx]
    edges = [
        cv2.Canny(cv2.cvtColor(rgb[crop], cv2.COLOR_RGB2GRAY), 40, 100) != 0
        for rgb in (original, normal)
    ]

    def distances(first, second):
        if not first.any() or not second.any():
            return None
        d = cv2.distanceTransform((~second).astype("uint8"), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)[
            first
        ]
        return dict(
            median_px=float(np.median(d)), p95_px=float(np.quantile(d, 0.95)), max_px=float(d.max())
        )

    return dict(
        frozen_edges=int(edges[0].sum()),
        normal_edges=int(edges[1].sum()),
        differing_edge_px=int((edges[0] != edges[1]).sum()),
        frozen_to_normal=distances(*edges),
        normal_to_frozen=distances(*edges[::-1]),
    )


def render(camera, model, data, frame, hidden, state_sha):
    rgba = model.geom_rgba.copy()
    try:
        for name in hidden:
            model.geom_rgba[model.geom(name).id, 3] = 0
        sensor, ids, labels, state_hashes = camera.capture_with_instances(
            data,
            rng=np.random.default_rng(0),
            noise_std_m=0,
            scene_id=frame.scene_id,
            episode_id=frame.episode_id,
        )
    finally:
        model.geom_rgba[:] = rgba
    require(
        tuple(state_hashes) == (state_sha,) * 3
        and data.time == sensor.sim_time_s == frame.sim_time_s
        and tuple(sensor.intrinsics) == frame.intrinsics
        and tuple(sensor.camera_to_world) == frame.camera_to_world
        and sensor.calibration_version == frame.calibration_version
        and set(hidden).isdisjoint(labels.values()),
        "render advanced physics, crossed calibration, or included a hidden geometry",
    )
    shape = frame.height, frame.width
    return dict(
        rgb=np.frombuffer(sensor.rgb, dtype=np.uint8).reshape(*shape, 3),
        depth=np.reshape(sensor.depth, shape).astype("<f4"),
        geom=np.reshape(ids, shape).astype("<i2"),
        labels=labels,
    )


def paired_depth(frozen, normal, changed):
    valid = (frozen > 0) & (normal > 0) & (changed > 0)
    result = changed.copy()
    # A zero rendered surface displacement preserves the original depth bits on that ray.
    result[valid] = frozen[valid] + (changed[valid] - normal[valid])
    result[result <= 0] = 0
    return result


def packet(frame, rgb, depth, key):
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="PNG", compress_level=1)
    return type(frame).model_validate(
        {
            **frame.model_dump(),
            "frame_id": "offline-" + key + "-" + frame.frame_id,
            "observation_id": "",
            "checksum_sha256": "",
            "rgb_png_base64": base64.b64encode(buf.getvalue()).decode(),
            "depth_float32_base64": base64.b64encode(
                depth.astype("<f4", copy=False).tobytes()
            ).decode(),
            "valid_mask_base64": None,
        }
    )


def read_decision(frame, geometry, arm):
    from scripts.graduation.g1_dual_pixel_readback import dual_read, single_read
    from scripts.graduation.g1_formal_runtime import bind_scene

    with bind_scene(frame.scene_id):
        m = (dual_read if arm == "dual" else single_read)(frame, geometry)
    output = {k: m[k] for k in ("observed_ids", "usable_ids", "selected_id", "usable", "reason")}
    if set(m["per_id"]) == {"7", "8"}:
        output["two_grasp_separation_mm"] = float(
            np.linalg.norm(np.subtract(m["per_id"]["7"]["tcp_m"], m["per_id"]["8"]["tcp_m"])) * 1000
        )
    return output


def select(index, audit, run):
    """Use the ordered feedback IDs and the accepted sample IDs; stage handoffs can share steps."""
    feedback = [r for r in index["frames"] if r["label"].endswith("/feedback")]
    tags = defaultdict(list)
    last = feedback[-1]
    terminal = index["frames"][-1]
    require(
        run["stop"]["physics_step"] == last["physics_step"] == terminal["physics_step"]
        and last["label"] == run["stop"]["skill"] + "/feedback"
        and last["frame_id"] != terminal["frame_id"]
        and terminal["label"] == "terminal",
        "refusal / terminal binding differs",
    )
    accepted = {
        s["observation_id"]: s
        for a in audit
        if a.get("phase") == "servo"
        for s in a["visual_samples"]
    }
    require(
        set(accepted) == {r["frame_id"] for r in feedback[:-1]}, "accepted feedback is incomplete"
    )
    for r in feedback[:-1]:
        require(
            accepted[r["frame_id"]]["checksum_sha256"] == r["checksum_sha256"],
            "crossed accepted sample",
        )
    phases = {}
    for row in feedback:
        if row["label"] not in phases:
            tags[row["frame_id"]].append("first_" + row["label"].split("/")[0])
            phases[row["label"]] = True
    require(
        feedback[-2]["label"] == last["label"]
        and last["physics_step"] == feedback[-2]["physics_step"] + 8,
        "wrong previous feedback",
    )
    tags[feedback[-2]["frame_id"]].append("previous")
    tags[last["frame_id"]].append("refused")
    # Cover the first loss of either previously detected print and its previous control, plus
    # each change of the accepted ID set in the final APPROACH. Duplicate step IDs stay separate.
    seen = set()
    for previous, row in zip(feedback[:-2], feedback[1:-1], strict=True):
        a, b = [accepted[r["frame_id"]].get("development_dual_marker") for r in (previous, row)]
        if a is None:
            continue
        before, after = set(a["observed_ids"]), set(b["observed_ids"])
        lost = before - after
        if lost - seen or (before != after and row["label"] == "APPROACH/feedback"):
            tags[previous["frame_id"]].append("before_ID_change")
            tags[row["frame_id"]].append("ID_change")
        seen.update(lost)
    return tags, accepted


def reconstruction(
    camera, model, data, state, frame, geometry, arm, specs, geoms, fronts, meta, tags, store
):
    import mujoco
    from scripts.graduation import proposal_camera as cam

    residuals = cam.restore(model, data, state)
    q = int(model.joint("object_free").dofadr[0])
    data.qvel[q : q + 6] = (
        state["object_linear_velocity_m_s"] + state["object_angular_velocity_rad_s"]
    )
    mujoco.mj_forward(model, data)
    state_sha = camera._physics_state_hash(data)
    frozen = cam.rgb(frame), cam.depth(frame)
    source_decision = read_decision(frame, geometry, arm)
    results, views, compressed = {}, {}, {}
    modes = {"normal": (), "hide_hand_and_fingers": HAND}
    if "previous" in tags or "refused" in tags:
        modes.update({"hide_" + name: (name,) for name in HAND})
        modes["hide_entire_arm"] = tuple(cam.arm_geometries(model).values())
    for method, names in modes.items():
        observed = render(camera, model, data, frame, names, state_sha)
        if method in {"normal", "hide_hand_and_fingers"}:
            views[method] = observed
        baseline = views["normal"]
        paired = paired_depth(frozen[1], baseline["depth"], observed["depth"])
        if method == "normal":
            require(
                np.array_equal(paired, frozen[1]), "normal paired depth is not identical to source"
            )
        clean_decision = read_decision(
            packet(frame, observed["rgb"], observed["depth"], method + "-clean"), geometry, arm
        )
        matched_decision = read_decision(
            packet(frame, observed["rgb"], paired, method + "-paired"), geometry, arm
        )
        results[method] = dict(
            hidden_geom=list(names),
            rgb_sha256=digest_array(observed["rgb"]),
            clean_depth_f32le_sha256=digest_array(observed["depth"]),
            geom_i16le_sha256=digest_array(observed["geom"]),
            paired_depth_f32le_sha256=digest_array(paired),
            labels=observed["labels"],
            clean=clean_decision,
            paired=matched_decision,
            newly_valid_without_source_noise=int(
                ((observed["depth"] > 0) & ((baseline["depth"] <= 0) | (frozen[1] <= 0))).sum()
            ),
        )
        for key in ("rgb", "geom", "depth"):
            compressed[method + "_" + key] = observed[key]
    np.savez_compressed(store / (frame.frame_id + ".npz"), **compressed)
    normal, hidden = views["normal"], views["hide_hand_and_fingers"]
    fdepth, ndepth = frozen[1], normal["depth"]
    good = (fdepth > 0) & (ndepth > 0)
    delta = abs(fdepth[good] - ndepth[good])
    d_rgb = np.max(abs(frozen[0].astype(int) - normal["rgb"].astype(int)), axis=2)
    summary = dict(
        global_rgb_different_pixels=int((d_rgb > 0).sum()),
        global_total_pixels=int(d_rgb.size),
        global_rgb_max_channel_difference=int(d_rgb.max()),
        valid_mask_disagreement_pixels=int(((fdepth > 0) != (ndepth > 0)).sum()),
        common_valid_depth_pixels=int(good.sum()),
        absolute_clean_depth_error_p99_mm=float(np.quantile(delta, 0.99) * 1000),
        absolute_clean_depth_error_p50_mm=float(np.median(delta) * 1000),
        frozen_normal_same_ids=source_decision["observed_ids"]
        == results["normal"]["paired"]["observed_ids"],
        frozen_normal_same_usable_ids=source_decision["usable_ids"]
        == results["normal"]["paired"]["usable_ids"],
        frozen_normal_same_reason=source_decision["reason"]
        == results["normal"]["paired"]["reason"],
    )
    by_id = {}
    for code in specs:
        geom = geoms[code]
        evidence = static_area_evidence(geom, frozen, normal, hidden, *fronts[code])
        edges = edge_alignment(frozen[0], normal["rgb"], geom["paper_xy"])
        by_id[code] = dict(
            edge_alignment=edges,
            regions=evidence,
            fitted_marker_distance_from_image_edge_px=min(
                meta[code]["paper_image_margins_ltrb_px"]
            ),
        )
    return dict(
        anchors=tags,
        frozen_native_decision=source_decision,
        restore_fk=residuals,
        rendered_state_sha256=state_sha,
        alignment=summary,
        by_id=by_id,
        interventions=results,
    ), (frozen[0], normal, hidden["rgb"])


def summarize_anchor(row, projections):
    alignment = row["alignment"]
    from scripts.graduation.proposal_camera import CHECK_LIMITS

    fit = (
        alignment["global_rgb_different_pixels"] / alignment["global_total_pixels"]
        <= CHECK_LIMITS["rgb_changed_pixel_fraction"]
        and alignment["valid_mask_disagreement_pixels"] / alignment["global_total_pixels"]
        <= CHECK_LIMITS["valid_mask_disagreement_fraction"]
        and alignment["absolute_clean_depth_error_p99_mm"] / 1000
        <= CHECK_LIMITS["common_valid_depth_abs_p99_m"]
        and all(v <= CHECK_LIMITS[k] for k, v in row["restore_fk"].items())
    )
    readings = {m: r["paired"] for m, r in row["interventions"].items()}
    by_id = {}
    for code, detail in row["by_id"].items():
        marker = int(code)
        edge_check = detail["edge_alignment"]
        usable_alignment = (
            fit
            and alignment["frozen_normal_same_ids"]
            and alignment["frozen_normal_same_usable_ids"]
            and all(
                edge_check[k] is not None and edge_check[k]["p95_px"] <= 0.5
                for k in ("frozen_to_normal", "normal_to_frozen")
            )
        )
        by_area = {}
        for name in (
            "paper",
            "printed",
            "quiet",
            "black_border",
            "payload_4x4",
            "outside_paper_0_1.5px",
            "outside_paper_1.5_3px",
            "outside_paper_3_6px",
        ):
            raw = projections[code]["frozen_depth_regions"][name]
            a = detail["regions"][name]
            by_area[name] = dict(
                pixel_centers=raw["pixel_centers"],
                valid=raw["valid"],
                foreground_gt5mm=raw["foreground_gt5mm"],
                foreground_gt20mm=raw["foreground_gt20mm"],
                named_geom_foreground_gt5mm=a["geom_at_original_foreground_gt5mm"],
                aligned_named_geom_foreground_gt5mm=a["aligned_geom_at_original_foreground_gt5mm"],
                combined_hide_changed_rgb=a["normal_to_combined_hidden_rgb_changed_px"],
            )
        observed = marker in row["frozen_native_decision"]["observed_ids"]
        recovered = marker in readings["hide_hand_and_fingers"]["observed_ids"]
        confirmed = {
            name: {n: v for n, v in a["aligned_named_geom_foreground_gt5mm"].items() if n in HAND}
            for name, a in by_area.items()
        }
        if not usable_alignment:
            evidence = "alignment_limited"
        elif observed:
            evidence = "decoded_control"
        elif not recovered:
            evidence = "combined_hiding_did_not_recover_this_ID"
        elif confirmed["printed"]:
            evidence = "combined_hiding_recovers_ID_with_projected_print_foreground"
        elif confirmed["quiet"]:
            evidence = "combined_hiding_recovers_ID_with_projected_quiet_margin_foreground"
        elif by_area["paper"]["foreground_gt5mm"] == 0:
            evidence = "combined_hiding_recovers_ID_without_original_paper_foreground"
        else:
            evidence = "combined_hiding_recovers_ID_with_unresolved_foreground"
        by_id[code] = dict(
            attribution=evidence,
            alignment_eligible=bool(usable_alignment),
            frozen_ID_observed=observed,
            combined_hidden_ID_observed=recovered,
            combined_hidden_side_usable=marker in readings["hide_hand_and_fingers"]["usable_ids"],
            singleton_hidden_ID_observed={
                name: marker in readings["hide_" + name]["observed_ids"]
                for name in HAND
                if "hide_" + name in readings
            },
            edge_alignment=edge_check,
            regions=by_area,
        )
    return dict(
        frame_id=row["frame_id"],
        physics_step=row["physics_step"],
        label=row["label"],
        anchors=row["anchors"],
        frozen=row["frozen_native_decision"],
        normal=readings["normal"],
        hand_and_fingers_hidden=readings["hide_hand_and_fingers"],
        all_arm_hidden=readings.get("hide_entire_arm"),
        alignment=alignment,
        by_id=by_id,
    )


def plot(cases, path):
    font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

    def font(size):
        return ImageFont.truetype(font_path, size, index=2)

    title_font, body, small = font(27), font(18), font(15)
    left, dx, dh = 190, 210, 180
    image = Image.new("RGB", (left + dx * 4 + 15, 169 + dh * len(cases)), (249, 249, 247))
    draw = ImageDraw.Draw(image)
    draw.text((17, 9), "G1 冻结反馈与同姿态零步复拍", font=title_font, fill="#1a272c")
    draw.text(
        (18, 53),
        "全部裁图将原始 RGB 像素放大 3 倍。前三列对应前一有效反馈或首拒，右列隐藏手掌及两只手指。",
        font=small,
        fill="#374552",
    )
    for idx, text in enumerate(
        ("前一反馈 · 原图", "首拒反馈 · 原图", "首拒 · 重建几何分割", "首拒 · 去手复拍")
    ):
        draw.text((left + idx * dx, 80), text, font=body, fill="#182626")
    colors = {
        "hand": (221, 64, 133),
        "left_finger_geom": (255, 124, 55),
        "right_finger_geom": (42, 183, 98),
    }
    for i, (color, name) in enumerate(
        (
            ("#dd4085", "手掌"),
            ("#ff7c37", "左指"),
            ("#2ab762", "右指"),
            ("#ffdc37", "ID7 边界"),
            ("#50f2fc", "ID8 边界"),
        )
    ):
        x = left + 133 * i
        draw.rectangle((x, 120, x + 12, 132), fill=color, outline="#55636a")
        draw.text((x + 18, 113), name, font=small, fill="#334148")
    for n, (case, anchors) in enumerate(cases.items()):
        prev, stop = anchors["previous"], anchors["refused"]
        src, normal, hidden = stop["views"]
        quads = stop["quads"]
        projected = np.vstack([x["paper_xy"] for x in quads.values()])
        center = np.rint((projected.min(axis=0) + projected.max(axis=0)) / 2).astype(int)
        x0, y0 = center - [29, 25]
        box = (x0, y0, x0 + 58, y0 + 50)
        ytop = 148 + n * dh
        textcolor = "#25353b"
        group, arm = case.split("-")
        draw.text(
            (18, ytop + 12),
            group + " · " + ("双标" if arm == "dual" else "单标"),
            font=body,
            fill=textcolor,
        )
        draw.text(
            (18, ytop + 41), f"步 {prev['step']} → {stop['step']}", font=small, fill=textcolor
        )

        def idstr(ids):
            return "/".join(str(i) for i in ids) if ids else "∅"

        draw.text((18, ytop + 70), "首拒 ID  " + idstr(stop["ids"]), font=small, fill=textcolor)
        draw.text(
            (18, ytop + 95), "去手 ID  " + idstr(stop["recovered"]), font=small, fill=textcolor
        )
        overlay = normal["rgb"].copy()
        for gid, name in normal["labels"].items():
            if name in colors:
                pix = normal["geom"] == gid
                overlay[pix] = np.rint(0.42 * overlay[pix] + 0.58 * np.array(colors[name])).astype(
                    np.uint8
                )
        for j, rgb in enumerate([prev["views"][0], src, overlay, hidden]):
            crop = Image.fromarray(rgb).crop(box).resize((174, 150), Image.Resampling.NEAREST)
            if j == 2:
                lines = ImageDraw.Draw(crop)
                for k, geom in quads.items():
                    for key in ("paper_xy", "print_xy"):
                        points = (geom[key] - [x0, y0] + 0.5) * 3 - 0.5
                        xy = [tuple(row) for row in points]
                        lines.line(xy + xy[:1], fill=LABELS[k], width=1)
            image.paste(crop, (left + j * dx, ytop))
        draw.line((17, ytop + 162, image.width - 15, ytop + 162), fill=(218, 220, 217))
    with path.open("xb") as stream:
        image.save(stream, format="PNG", optimize=True)


def analyze_case(case, files, plan, store):
    import mujoco
    from scripts.graduation import proposal_camera as cam
    from scripts.graduation.dynamic_vision_score import checked_steps, frame_from_row
    from scripts.graduation.g1_mount_score import check_clocks

    from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera

    folder = ARCHIVE / "trials" / case
    raw = folder / "instance"

    def original(p):
        key = str(p.relative_to(ARCHIVE))
        h = files[key]["sha256"]
        if str(p.relative_to(ROOT)) in plan["inputs_sha256"]:
            require(
                plan["inputs_sha256"][str(p.relative_to(ROOT))] == h,
                "plan/manifest digest mismatch",
            )
        return read_pinned(p, h)

    a = original(folder / "allocation.json")
    g = a["geometry"]
    arc = {
        k: original(raw / (k + ".json"))
        for k in (
            "pixel-index",
            "offline-truth",
            "run",
            "online-audit",
            "receipt",
            "acquisition-seal",
        )
    }
    index, truth, run, audit = [
        arc[k] for k in ("pixel-index", "offline-truth", "run", "online-audit")
    ]
    seal, receipt = arc["acquisition-seal"], arc["receipt"]
    for key, p in (
        ("index", "pixel-index"),
        ("truth", "offline-truth"),
        ("run", "run"),
        ("audit", "online-audit"),
    ):
        require(
            seal[key + "_sha256"]
            == files[str((raw / (p + ".json")).relative_to(ARCHIVE))]["sha256"],
            "foreign sealed source",
        )
    require(
        index["episode"] == truth["episode"] == receipt["physical_reset"]["episode_id"]
        and index["scene"] == truth["scene"] == a["case"]["scene_id"]
        and case == a["case"]["id"] == receipt["id"]
        and index["allocation_sha256"]
        == truth["allocation_sha256"]
        == sha(folder / "allocation.json")
        and a["asset_sha256"]
        == sha(RUNTIME / g["asset_path"])
        == plan["inputs_sha256"][str((RUNTIME / g["asset_path"]).relative_to(ROOT))],
        "mixed slot/asset/episode/registration",
    )
    steps = checked_steps(
        truth["samples"], index["episode"], a["asset_sha256"], truth["asset_sha256"]
    )
    check_clocks(run, audit, {r["frame_id"]: r for r in index["frames"]}, index["episode"])
    tags, accepted = select(index, audit, run)
    registered = {str((raw / r["file"]).relative_to(ARCHIVE)) for r in index["frames"]}
    manifest_frames = {k for k in files if k.startswith("trials/" + case + "/instance/frames/")}
    require(registered == manifest_frames, "unexpected source frame attachment")
    db = raw / "development-worker.db"
    require(sha(db) == files[str(db.relative_to(ARCHIVE))]["sha256"], "foreign job database")
    with closing(sqlite3.connect(db.as_uri() + "?mode=ro&immutable=1", uri=True)) as connection:
        artifacts = connection.execute(
            "select name, relative_path from simulation_artifacts"
        ).fetchall()
    require(not artifacts, "job database has an additional artifact to examine")
    model = mujoco.MjModel.from_xml_path(str(RUNTIME / g["asset_path"]))
    data = mujoco.MjData(model)
    specs = transforms(model, g)
    camera = MuJoCoRGBDCamera(
        mujoco, model, width=g["camera"]["width"], height=g["camera"]["height"]
    )
    rows, statics, ends, images = [], [], {}, {}
    folder_stats = dict(
        episode=index["episode"],
        scene=index["scene"],
        asset_sha256=a["asset_sha256"],
        allocation_sha256=index["allocation_sha256"],
        truth_sha256=seal["truth_sha256"],
        pixel_index_sha256=seal["index_sha256"],
    )
    try:
        for r in index["frames"]:
            frame = frame_from_row(raw, r, index["episode"], index["scene"], g)
            require(
                files[str((raw / r["file"]).relative_to(ARCHIVE))]["sha256"] == r["file_sha256"]
                and frame.model_dump(mode="json", include=set(g["camera"])) == g["camera"]
                and frame.depth_convention == "optical_z_m",
                "frozen packet/geometry differs",
            )
            state = steps[r["physics_step"]]
            require(state["sim_time_s"] == frame.sim_time_s, "unsynchronized state")
            depth = cam.depth(frame)
            geoms = {k: polygon_geometry(frame, state, s) for k, s in specs.items()}
            projections, fronts = {}, {}
            for code, geom in geoms.items():
                projection, f5, f20 = geometry_evidence(frame, geom, depth)
                projections[code] = projection
                fronts[code] = (f5, f20)
            identity = dict(
                case=case,
                episode=index["episode"],
                scene=index["scene"],
                **r,
                source_state_canonical_sha256=sha(canonical(state)),
            )
            rows.append(dict(**identity, by_id=projections))
            frame_id = r["frame_id"]
            if frame_id not in tags:
                continue
            detail, views = reconstruction(
                camera,
                model,
                data,
                state,
                frame,
                g,
                a["case"]["arm"],
                specs,
                geoms,
                fronts,
                projections,
                tags[frame_id],
                store,
            )
            if frame_id in accepted and "development_dual_marker" in accepted[frame_id]:
                m = accepted[frame_id]["development_dual_marker"]
                require(
                    m["observed_ids"] == detail["frozen_native_decision"]["observed_ids"],
                    "original decision and stored ID sample differ",
                )
            detail.update(identity)
            statics.append(detail)
            for time_role in set(tags[frame_id]) & {"previous", "refused"}:
                ends[time_role] = summarize_anchor(detail, projections)
                images[time_role] = dict(
                    views=views,
                    step=r["physics_step"],
                    ids=detail["frozen_native_decision"]["observed_ids"],
                    recovered=detail["interventions"]["hide_hand_and_fingers"]["paired"][
                        "observed_ids"
                    ],
                    quads=geoms,
                )
    finally:
        camera.close()
    require(len(ends) == 2 and len(statics) == len(tags), "missing requested anchors")
    folder_stats.update(
        all_packets=len(rows),
        registered_frame_attachments=len(registered),
        sqlite_registered_artifact_rows=len(artifacts),
        minimum_projected_paper_image_margin_px=min(
            min(m["paper_image_margins_ltrb_px"]) for r in rows for m in r["by_id"].values()
        ),
        feedback_packets=len(accepted) + 1,
        rendered_poses=len(statics),
        static_captures=sum(len(s["interventions"]) for s in statics),
        **ends,
    )
    return rows, statics, folder_stats, images


def independent_rays(frame, state, marker_transform, quiet_transform, half):
    """Intersect calibrated optical rays with the two planes in world coordinates."""
    att = np.array(state["object_geom_rotation_row_major"]).reshape(3, 3)
    center = np.array(state["object_geom_position_m"])
    extrinsics = np.reshape(frame.camera_to_world, (4, 4))
    fx, fy, cx, cy = frame.intrinsics
    uvs, transforms = {}, {}
    for label, box, h in (("paper", quiet_transform, 0.05), ("printed", marker_transform, half)):
        axes = att @ box[:3, :3]
        position = center + att @ box[:3, 3]
        local = np.column_stack([SIGN * h, np.zeros(4)])
        world = position + local @ axes.T
        optical = (world - extrinsics[:3, 3]) @ extrinsics[:3, :3]
        uvs[label] = optical[:, :2] * np.array([fx, fy]) / optical[:, 2, None] + [cx, cy]
        transforms[label] = (axes, position, h)
    x, y = np.maximum(np.floor(uvs["paper"].min(axis=0)).astype(int) - 1, 0)
    xx, yy = np.minimum(
        np.ceil(uvs["paper"].max(axis=0)).astype(int) + 2, [frame.width, frame.height]
    )
    sl = np.s_[y:yy, x:xx]
    v, u = np.mgrid[sl]
    rays = np.stack(((u - cx) / fx, (v - cy) / fy, np.ones_like(u)), axis=2) @ extrinsics[:3, :3].T
    corners, planes = {}, {}
    for label, (axes, position, h) in transforms.items():
        origin = (extrinsics[:3, 3] - position) @ axes
        local_rays = rays @ axes
        optical_z = -origin[2] / local_rays[:, :, 2]
        hit = origin + optical_z[:, :, None] * local_rays
        require(np.max(abs(hit[:, :, 2])) < 1e-12, "rays do not intersect registered plane")
        corners[label] = (abs(hit[:, :, 0]) <= h) & (abs(hit[:, :, 1]) <= h)
        planes[label] = optical_z
    corners["quiet"] = corners["paper"] & ~corners["printed"]
    return sl, uvs, corners, np.where(corners["printed"], planes["printed"], planes["paper"])


def verify(out, store, files):
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    summary = json.loads((out / "occlusion.public.json").read_bytes())
    require(
        summary["plan_sha256"] == PLAN_SHA
        and summary["analysis_source_sha256"] == sha(Path(__file__)),
        "original analysis source changed",
    )
    for file, digest in summary["derived_sha256"].items():
        require(sha(out / file) == digest, "derived file changed")
    static_records = json.loads(
        gzip.decompress((out / "occlusion-reconstructions.public.json.gz").read_bytes())
    )
    lookup = {s["frame_id"]: s for s in static_records}
    rows = json.loads(gzip.decompress((out / "occlusion-frames.public.json.gz").read_bytes()))
    previous = None
    checks = Counter()
    max_corner_px = 0.0
    for row in rows:
        case = row["case"]
        raw = ARCHIVE / "trials" / case / "instance"

        def original(path):
            return read_pinned(path, files[str(path.relative_to(ARCHIVE))]["sha256"])

        if case != previous:
            alloc = original(raw.parent / "allocation.json")
            geometry = alloc["geometry"]
            truth = original(raw / "offline-truth.json")
            spec = ElementTree.parse(RUNTIME / geometry["asset_path"])
            dual = geometry.get("development_dual", {}).get("markers")
            transforms_by_id = {}
            for code in ("7", "8") if dual else ("7",):
                prefix = f"g1_dual_id{code}_" if dual else "pose_marker_outboard_v3_"
                quiet_node = spec.find(f".//geom[@name='{prefix}quiet']")
                quiet = np.eye(4)
                quiet[:3, 3] = np.fromstring(quiet_node.get("pos"), sep=" ")
                quiet[2, 3] += np.fromstring(quiet_node.get("size"), sep=" ")[2]
                marker = dual[code]["object_T_marker"] if dual else geometry["marker_to_object"]
                transforms_by_id[code] = (
                    np.reshape(marker, (4, 4)),
                    quiet,
                    geometry["pose_marker"]["marker_size_m"] / 2,
                )
            previous = case
        frame = RGBDObservation.model_validate(original(raw / row["file"]))
        require(
            frame.frame_id == row["frame_id"]
            and frame.checksum_sha256 == row["checksum_sha256"]
            and frame.episode_id == truth["episode"] == row["episode"],
            "different verification packet",
        )
        state = truth["samples"][row["physics_step"]]
        require(
            sha(canonical(state)) == row["source_state_canonical_sha256"], "state binding differs"
        )
        depth = np.frombuffer(base64.b64decode(frame.depth_float32_base64), dtype="<f4").reshape(
            frame.height, frame.width
        )
        static = lookup.get(frame.frame_id)
        normal_ids = None
        if static is not None:
            with np.load(store / (frame.frame_id + ".npz"), allow_pickle=False) as captured:
                for method, info in static["interventions"].items():
                    for field, expected in (
                        ("rgb", "rgb_sha256"),
                        ("depth", "clean_depth_f32le_sha256"),
                        ("geom", "geom_i16le_sha256"),
                    ):
                        require(
                            digest_array(captured[method + "_" + field]) == info[expected],
                            "private reconstructed array differs",
                        )
                        checks["private_array_sha256"] += 1
                normal_ids = captured["normal_geom"]
            labels = {int(k): v for k, v in static["interventions"]["normal"]["labels"].items()}
        for code, pair in transforms_by_id.items():
            sl, quads, areas, plane = independent_rays(frame, state, *pair)
            entry = row["by_id"][code]
            for k, quad in quads.items():
                target = entry["paper_corners_px" if k == "paper" else "print_corners_px"]
                residual = float(np.max(abs(quad - target)))
                require(residual < 1e-8, "independent polygon projection differs")
                max_corner_px = max(max_corner_px, residual)
                checks["projected_quads"] += 1
            valid = depth[sl] > 0
            near5 = valid & (plane - depth[sl] > 0.005)
            near20 = valid & (plane - depth[sl] > 0.020)
            for key, area in areas.items():
                counts = [
                    int(area.sum()),
                    int((area & valid).sum()),
                    int((area & near5).sum()),
                    int((area & near20).sum()),
                ]
                archived = entry["frozen_depth_regions"][key]
                require(
                    counts
                    == [
                        archived[k]
                        for k in ("pixel_centers", "valid", "foreground_gt5mm", "foreground_gt20mm")
                    ],
                    "independent projected area / original foreground counts differ",
                )
                checks["area_denominator_depth_threshold_checks"] += 4
                if normal_ids is not None:
                    for mask, field in (
                        (near5, "geom_at_original_foreground_gt5mm"),
                        (near20, "geom_at_original_foreground_gt20mm"),
                    ):
                        counter = Counter(
                            labels.get(int(g), "background") for g in normal_ids[sl][area & mask]
                        )
                        require(
                            dict(counter) == static["by_id"][code]["regions"][key][field],
                            "geom identity count differs",
                        )
                        checks["named_foreground_histograms"] += 1
        checks["frames"] += 1
    require(
        checks["frames"] == 778 and len(lookup) == summary["reconstructed_poses"],
        "incomplete verification",
    )
    json_file(
        out / "occlusion-verification.public.json",
        dict(
            plan_sha256=PLAN_SHA,
            verification_method=(
                "Separate world-ray/plane intersection and direct archived optical-Z recount. "
                "Read stored static geometry-ID, depth and RGB arrays and independently recount "
                "paired labels."
            ),
            summary_sha256=sha(out / "occlusion.public.json"),
            max_projected_corner_error_px=max_corner_px,
            original_cases=8,
            counts=dict(checks),
            verified=True,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="destination for public observations and annotated crops",
    )
    parser.add_argument(
        "--private",
        type=Path,
        required=True,
        help="new directory for private reconstructed RGB/depth/geom arrays",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="verify stored outputs using world rays, original depths and static rendering arrays",
    )
    args = parser.parse_args()
    out, store = args.out.resolve(), args.private.resolve()
    require(
        not out.is_relative_to(ARCHIVE) and not store.is_relative_to(ARCHIVE) and out != store,
        "outputs must be separate from the original archive",
    )
    plan = read_pinned(ROUND / "plan.json", PLAN_SHA)
    manifest = ARCHIVE / "originals-manifest.json"
    manifest_sha = plan["inputs_sha256"][str(manifest.relative_to(ROOT))]
    files = read_pinned(manifest, manifest_sha)["files"]
    lockfile = RUNTIME / "runtime-build.json"
    lock = read_pinned(lockfile, plan["inputs_sha256"][str(lockfile.relative_to(ROOT))])
    require(
        len(files) == 919
        and all(sha(RUNTIME / k) == v for k, v in lock["runtime_files_sha256"].items()),
        "frozen runtime tree differs",
    )
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(RUNTIME), str(RUNTIME / "src")]
    if args.verify:
        verify(out, store, files)
        return
    os.environ.setdefault("MUJOCO_GL", "egl")
    require(os.environ["MUJOCO_GL"] == "egl", "registered static renderer uses EGL")
    import mujoco
    from scripts.graduation import proposal_camera as cam

    require(
        Path(cam.__file__).resolve().is_relative_to(RUNTIME),
        "run this file directly with the frozen imports first",
    )
    out.mkdir(exist_ok=True, parents=True)
    store.mkdir(parents=True, exist_ok=False)
    cv2.setNumThreads(1)
    all_rows, all_static, case_rows, images = [], [], {}, {}
    for case in CASES:
        rows, statics, result, samples = analyze_case(case, files, plan, store)
        all_rows.extend(rows)
        all_static.extend(statics)
        case_rows[case] = result
        images[case] = samples
        print(f"{case}: {len(rows)} frozen frames; {len(statics)} static poses", flush=True)
    require(
        len(all_rows) == 778 and len(set(r["frame_id"] for r in all_rows)) == 778,
        "wrong frozen frame denominator",
    )
    modules = {}
    for name, module in sys.modules.items():
        if not (name.startswith("scripts.") or name.startswith("cloud_edge_robot_arm")):
            continue
        path = getattr(module, "__file__", None)
        if path is None:
            continue
        rel = Path(path).resolve().relative_to(RUNTIME).as_posix()
        require(
            rel in lock["runtime_files_sha256"]
            and sha(Path(path)) == lock["runtime_files_sha256"][rel],
            "foreign frozen import",
        )
        modules[rel] = lock["runtime_files_sha256"][rel]
    evidence = {}
    evidence["occlusion-frames.public.json.gz"] = json_file(
        out / "occlusion-frames.public.json.gz", all_rows, compact=True
    )
    evidence["occlusion-reconstructions.public.json.gz"] = json_file(
        out / "occlusion-reconstructions.public.json.gz", all_static, compact=True
    )
    plot(images, out / "occlusion-comparison.public.png")
    evidence["occlusion-comparison.public.png"] = sha(out / "occlusion-comparison.public.png")
    summary = dict(
        schema="g1.formal-failure-occlusion.v1",
        plan_sha256=PLAN_SHA,
        originals_manifest_sha256=manifest_sha,
        analysis_source_sha256=sha(Path(__file__)),
        frozen_runtime_build_sha256=sha(lockfile),
        frozen_imports_sha256=modules,
        renderer="EGL",
        mujoco=mujoco.__version__,
        numpy=np.__version__,
        opencv=cv2.__version__,
        frozen_image_packets=len(all_rows),
        reconstructed_poses=len(all_static),
        static_render_captures=sum(r["static_captures"] for r in case_rows.values()),
        frozen_archive_files_by_kind=dict(
            Counter(
                "indexed RGB-D packet"
                if "/frames/" in k
                else "formal claim"
                if k.startswith("claims/")
                else Path(k).name
                for k in files
            )
        ),
        integrated_steps=0,
        action_dispatches=0,
        formal_claims=0,
        calibration="f33940579c533afe",
        figure_note=(
            "Raw native RGB crops in columns 1/2. Column 3 blends only the zero-step normal "
            "geom-ID map over its RGB and projects the paper and print edges. Column 4 hides "
            "hand and both fingers."
        ),
        methods=dict(
            original_modalities=(
                "Frozen packets carry native RGB, optical_z_m and a valid mask. Registered "
                "pixel-index rows bind only these RGB-D files; the originals manifest has no "
                "per-frame geom/segmentation sidecar. Named geom values are from the zero-step "
                "reconstruction only."
            ),
            coordinate_rule=(
                "Integer pixel centers. Project the actual 100 mm quiet substrate top and 75 mm "
                "printed top from frozen object pose, corresponding object-to-marker "
                "registration and checked compiled geoms. Ink sits 0.020 mm above quiet "
                "substrate."
            ),
            areas=(
                "6x6 including the 1-cell black border surrounding the 4x4 payload. Quiet is "
                "paper minus print. Paper/print edges use +/-1.5 px measured perpendicular to "
                "each finite segment, sides +Y,+X,-Y,-X in marker coordinates. Corner order "
                "(-X,+Y), (+X,+Y), (+X,-Y), (-X,-Y); each samples a 3x3 patch centered on its "
                "nearest integer pixel. Outside shells use Euclidean distance to the polygon, "
                "excluding its interior. Edge/corner statistics overlap and are not additive."
            ),
            foreground=(
                "Positive original optical-Z pixels more than 5 or 20 mm closer than their "
                "predicted print (inside print) or quiet (elsewhere) plane. Individual "
                "proportions divide by the positive depths of that area."
            ),
            pose=(
                "Restore seven arm joint and two finger positions/velocities, object free "
                "pose/velocity and time via mj_forward. No backend, integration, or commands. "
                "Unrecorded actuator/solver internal state is not needed for drawing; only "
                "visible kinematics and calibration are verified."
            ),
            noise=(
                "Paired metric depth = frozen depth + (hidden clean depth - normal clean depth) "
                "on common valid rays; depth perturbation is identical on unchanged surfaces. "
                "Newly visible rays lacking a positive source/normal depth take the clean "
                "hidden depth. Thus the local measured residual, including rendering mismatch, "
                "is transported. Clean decisions are also reported independently. Render "
                "times/frame IDs are diagnostic."
            ),
            alignment=(
                "Report global RGB changes, common-depth P99 and valid-mask disagreement, "
                "symmetric Canny distances within each paper bounding rectangle plus 5 px, same "
                "frozen/normal marker decisions. Eligibility uses inherited camera/FK limits, "
                "the same observed/usable ID set and local p95 edge deviation <=0.5 px in both "
                "directions. Count individually aligned named foreground where source/render "
                "RGB differ by at most 2/255 per channel and source/raw-render depth by at most "
                "5 mm."
            ),
            attribution=(
                "A recovered ID plus aligned named foreground in print or quiet supports a "
                "local foreground contribution; the contact pixel need not be the sole cause. "
                "Recovery with zero paper foreground demonstrates a hand/finger appearance "
                "effect but does not distinguish shadows, antialiasing and adjacent contour "
                "grouping. Each singleton hides only that named geom. An individual ID may be "
                "usable even when the dual arbitration refuses the frame."
            ),
        ),
        derived_sha256=evidence,
        cases=case_rows,
    )
    json_file(out / "occlusion.public.json", summary)


if __name__ == "__main__":
    main()
