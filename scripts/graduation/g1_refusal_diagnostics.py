"""Unblind native-size ID7 image, segmentation, plane-depth and hand-only interventions."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from scripts.graduation import g1_refusal_capture as source
from scripts.graduation import g1_refusal_score as scoring
from scripts.graduation import proposal_camera as cam
from scripts.graduation.g1_mount_geometry import require
from scripts.graduation.g1_mount_screen_score import projected_regions
from scripts.graduation.g1_mount_screen_verify import local_points
from scripts.graduation.g1_refusal_pixels import depth_patches
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write
from scripts.graduation.proposal_terminal_visibility import HAND

AREAS = ("black_cells", "white_cells", "quiet_white_margin")


def attribute(normal, hidden, foreground, neighbors, shifts, paper_hand_total=None):
    recovered = not normal["usable"] and hidden["usable"]
    supported = [label for label in AREAS if foreground[label] > 0 and recovered]
    paper = sum(foreground.values()) if paper_hand_total is None else paper_hand_total
    if normal["usable"]:
        intervention = "already_usable"
    elif supported:
        intervention = "foreground_hand_contributes_in_listed_projected_regions"
    elif recovered and paper == 0:
        intervention = "hand_appearance_only"
    elif recovered:
        intervention = "hand_appearance_with_inconclusive_paper_depth"
    else:
        intervention = "unresolved"
    return dict(
        hand_intervention=intervention,
        source_usable=normal["usable"],
        hand_hidden_usable=hidden["usable"],
        hand_hiding_recovers_usable=recovered,
        supported_paper_regions=supported,
        paper_foreground_hand_pixels_nearer_5mm=foreground,
        adjacent_hand_pixels_by_shell=neighbors,
        sampling_interpolation_id_sensitive=any(
            s["decode"]["observed_ids"] != normal["ids"] for s in shifts
        ),
        shifted_id7=sum(s["decode"]["observed_ids"] == [7] for s in shifts),
        shift_denominator=len(shifts),
    )


def quad_overlap(target, quad):
    a, b = (np.asarray(p, dtype=np.float32).reshape(4, 2) for p in (target, quad))
    aa, bb = cv2.contourArea(a), cv2.contourArea(b)
    intersect = float(cv2.intersectConvexConvex(cv2.convexHull(a), cv2.convexHull(b))[0])
    intersect = min(max(0.0, intersect), aa, bb)
    rms = min(
        float(np.sqrt(np.mean(np.sum((a - np.roll(q, i, axis=0)) ** 2, axis=1))))
        for q in (b, b[::-1])
        for i in range(4)
    )
    return dict(
        intersection_over_union=intersect / (aa + bb - intersect) if aa + bb > intersect else 0.0,
        printed_area_fraction=intersect / aa,
        center_distance_px=float(np.linalg.norm(a.mean(axis=0) - b.mean(axis=0))),
        best_corner_rms_px=rms,
    )


def project(f, world_marker, half):
    cam_marker = np.linalg.inv(np.asarray(f.camera_to_world).reshape(4, 4)) @ world_marker
    points = (
        np.array(
            [[-half, half, 0, 1], [half, half, 0, 1], [half, -half, 0, 1], [-half, -half, 0, 1]]
        )
        @ cam_marker.T
    )
    fx, fy, cx, cy = f.intrinsics
    require((points[:, 2] > 0).all(), "projected board behind camera")
    return np.column_stack(
        (fx * points[:, 0] / points[:, 2] + cx, fy * points[:, 1] / points[:, 2] + cy)
    )


def outside_pixels(quad, width, height):
    if (quad >= 0).all() and (quad < [width, height]).all():
        return 0
    left, top = np.floor(quad.min(axis=0)).astype(int)
    right, bottom = np.ceil(quad.max(axis=0)).astype(int)
    return sum(
        cv2.pointPolygonTest(quad.astype(np.float32), (float(x), float(y)), False) >= 0
        for y in range(top, bottom + 1)
        for x in range(left, right + 1)
        if not (0 <= x < width and 0 <= y < height)
    )


def edge_bins(quad, hand, gray, depth, near5):
    y, x = np.indices(hand.shape)
    records = []
    for start, end in zip(quad, np.roll(quad, -1, axis=0), strict=True):
        u, v = end - start
        norm = np.hypot(u, v)
        t = ((x - start[0]) * u + (y - start[1]) * v) / norm**2
        band = (t >= 0) & (t <= 1) & (np.abs((x - start[0]) * v - (y - start[1]) * u) <= 1.5 * norm)
        records.append(
            dict(
                pixel_centers=int(band.sum()),
                hand_pixels=int((band & hand).sum()),
                foreground_hand_5mm=int((band & hand & near5).sum()),
                positive_depth=int((band & (depth > 0)).sum()),
                gray_mean=float(gray[band].mean()),
                gray_min=int(gray[band].min()),
                gray_max=int(gray[band].max()),
            )
        )
    return records


def spatial(frame, row, g, state, mask, decision):
    labels = row["segmentation"]["labels"]
    world_object = np.eye(4)
    world_object[:3, :3] = np.asarray(state["object_geom_rotation_row_major"]).reshape(3, 3)
    world_object[:3, 3] = state["object_geom_position_m"]
    world_marker = world_object @ np.asarray(g["marker_to_object"]).reshape(4, 4)
    regions = projected_regions(frame, state, g, mask, labels, row["arm_geoms"])
    printed, board = (project(frame, world_marker, half) for half in (0.0375, 0.05))
    require(
        np.allclose(regions["board_corners_px"], board, rtol=0, atol=1e-9),
        "board reprojection mismatch",
    )
    lx, ly, plane = local_points(frame, world_marker)
    finite = plane > 0
    edge = np.maximum(abs(lx), abs(ly))
    board_area = (edge <= 0.05) & finite
    print_area = (edge <= 0.0375) & finite
    distance = cv2.distanceTransform(
        (~board_area).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE
    )
    from_print = cv2.distanceTransform(
        (~print_area).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE
    )
    d = cam.depth(frame)
    gray = cv2.cvtColor(cam.rgb(frame), cv2.COLOR_RGB2GRAY)
    near5 = (d > 0) & ((plane - d) > 0.005)
    near20 = (d > 0) & ((plane - d) > 0.020)
    hand_names = {
        name: np.isin(mask, [int(i) for i, n in labels.items() if n == name]) for name in HAND
    }
    hand = np.logical_or.reduce(list(hand_names.values()))
    shells = []
    for inner, outer in ((0, 1.5), (1.5, 3), (3, 6)):
        b = (distance > inner) & (distance <= outer) & finite
        shells.append(
            dict(
                distance_px_open_closed=[inner, outer],
                pixel_centers=int(b.sum()),
                hand_pixels=int((b & hand).sum()),
                hand_nearer_5mm=int((b & hand & near5).sum()),
                hand_nearer_20mm=int((b & hand & near20).sum()),
                hand_by_geom={n: int((b & m).sum()) for n, m in hand_names.items()},
            )
        )
    nearest = {
        n: dict(
            to_board_mask_px=float(distance[m].min()), to_print_mask_px=float(from_print[m].min())
        )
        if m.any()
        else dict(to_board_mask_px=None, to_print_mask_px=None)
        for n, m in hand_names.items()
    }
    areas = regions["areas"]
    for label in AREAS:
        r = areas[label]
        r["correct_instance_fraction"] = r["correct_instance_pixels"] / r["pixels"]
        r["expected_color_surface_fraction"] = (
            r["role_pixels"].get(
                {
                    "black_cells": "black_cell",
                    "white_cells": "white_cell",
                    "quiet_white_margin": "white_board",
                }[label],
                0,
            )
            / r["pixels"]
        )
    detection = decision["detection"]
    comparisons = {
        k: [quad_overlap(printed, q) for q in detection[k]]
        for k in ("direct_quads_px", "rejected_quads_px", "recovered_quads_px")
    }
    return dict(
        **regions,
        registered_print_corners_px=printed.tolist(),
        print_corner_pixel_phases_xy=(printed - np.floor(printed)).tolist(),
        print_edge_pixels_per_cell=(
            np.linalg.norm(printed - np.roll(printed, -1, axis=0), axis=1) / 6
        ).tolist(),
        board_pixels_projected_outside_image=outside_pixels(board, frame.width, frame.height),
        print_pixels_projected_outside_image=outside_pixels(printed, frame.width, frame.height),
        nominal_board_to_hand_geometric_surface_distance_m=row["geometry"][
            "board_to_hand_surface_distance_m"
        ],
        projected_hand_nearest_distance=nearest,
        adjacent_outside_board_shells=shells,
        print_edge_bands_1p5px=edge_bins(printed, hand, gray, d, near5),
        board_edge_bands_1p5px=edge_bins(board, hand, gray, d, near5),
        projected_print_five_patches_offline=depth_patches(printed, d),
        candidate_overlap_with_projected_print=comparisons,
    )


def sums(areas, key):
    return {label: sum(areas[label][key].get(n, 0) for n in HAND) for label in AREAS}


def diagnose(plan_file, raw):
    plan, _, ev, gs = scoring.open_evidence(plan_file, raw)
    pub = plan_file.parent
    gate = read(pub / "refusal-decision.public.json")
    pairs = pinned(pub / "refusal-pairs.public.json", gate["paired_readings_sha256"])[
        "normal_pairs"
    ]
    by_pair = {(p["case"], p["time_role"]): p for p in pairs}
    details = []
    mechanisms = []
    for case in plan["source_cases"]:
        name = case["case"]
        truth = pinned(
            ROOT / plan["prior_private"] / "trials" / name / "instance/offline-truth.json",
            case["state_file_sha256"],
        )
        for t in source.TIMES:
            pair = by_pair[name, t]
            state = truth["samples"][pair["step"]]
            require(
                source.digest_state(state) == pair["source_state_sha256"], "wrong archived pose"
            )
            for side in scoring.SIDES:
                normal, hidden = (
                    ev.get(f"{name}/{t}/{side}/{kind}", gs[side])
                    for kind in ("normal", "hand_hidden")
                )
                f0, r0, d0 = normal
                f1, r1, d1 = hidden
                require(
                    r0["condition"] == "normal"
                    and r1["condition"] == "hand_hidden"
                    and r0["frame_id"] != r1["frame_id"]
                    and all(
                        r0[k] == r1[k]
                        for k in (
                            "source_episode",
                            "source_state_sha256",
                            "state_sha256",
                            "seed",
                            "time_role",
                            "step",
                            "mount_side",
                            "asset_sha256",
                            "geometry",
                            "sim_time_s",
                            "episode",
                        )
                    )
                    and r0["state_sha256"] == pair["normal_frames"][side]["state_sha256"]
                    and r0["frame_id"] == pair["normal_frames"][side]["frame_id"]
                    and len(d0["shifts"]) == 4
                    and not d1["shifts"],
                    "foreign paired diagnostic intervention or pressure case",
                )
                records = {}
                for f, r, dest in (normal, hidden):
                    seg = r["segmentation"]
                    path = raw / "segmentation" / seg["file"]
                    require(sha(path) == seg["sha256"], "segmentation differs")
                    mask = np.load(path, allow_pickle=False)
                    view = spatial(f, r, gs[side], state, mask, dest)
                    if r["condition"] == "hand_hidden":
                        require(
                            set(seg["labels"].values()).isdisjoint(HAND),
                            "hand visible in hidden mask",
                        )
                    records[r["condition"]] = {
                        **scoring.brief(r, dest, side),
                        "segmentation_sha256": seg["sha256"],
                        "projected": view,
                        "candidate_decode": dest["detection"],
                    }
                areas = records["normal"]["projected"]["areas"]
                shells = records["normal"]["projected"]["adjacent_outside_board_shells"]
                hand_pixels = sums(areas, "role_pixels")
                interpreted = attribute(
                    records["normal"],
                    records["hand_hidden"],
                    sums(areas, "nearer_5mm_by_role"),
                    [s["hand_pixels"] for s in shells],
                    d0["shifts"],
                    sum(hand_pixels.values()),
                )
                rejected = records["normal"]["projected"]["candidate_overlap_with_projected_print"][
                    "rejected_quads_px"
                ]
                best = max((q["intersection_over_union"] for q in rejected), default=None)
                differences = cam.rgb(f0) != cam.rgb(f1)
                entry = dict(
                    case=name,
                    time_role=t,
                    source_side=case["source_side"],
                    mount_side=side,
                    step=r0["step"],
                    source_state_sha256=r0["source_state_sha256"],
                    rendered_state_sha256=r0["state_sha256"],
                    noise_seed=r0["seed"],
                    **records,
                    shifted_grayscale_diagnostics=d0["shifts"],
                    hand_hiding_changed_rgb_pixels=int(differences.any(axis=2).sum()),
                    interpretation=interpreted,
                )
                details.append(entry)
                if t == "refused" and side == case["source_side"]:
                    mechanisms.append(
                        dict(
                            case=name,
                            step=r0["step"],
                            side=side,
                            **interpreted,
                            paper_hand_pixels=hand_pixels,
                            foreground_hand_20mm=sums(areas, "nearer_20mm_by_role"),
                            normal_raw_rejected_quad_count=len(rejected),
                            normal_best_rejected_quad_projected_print_iou=best,
                            hand_hidden_direct_ids=d1["detection"]["direct_ids"],
                            normal_direct_ids=d0["detection"]["direct_ids"],
                            normal_exact_recovered_ids=d0["detection"]["recovered_ids"],
                            normal_depth_fit_entered=bool(d0["depth_fit"]["five_patches"]),
                            native_print_pixels_per_cell=records["normal"]["projected"][
                                "print_edge_pixels_per_cell"
                            ],
                            out_of_frame_pixels=records["normal"]["projected"][
                                "board_pixels_projected_outside_image"
                            ],
                            sampled_shift_recoveries=[
                                (s["dx_px"], s["dy_px"])
                                for s in d0["shifts"]
                                if s["decode"]["observed_ids"] == [7]
                            ],
                        )
                    )
    counts = {
        c: dict(allocated=len(details), usable=sum(e[c]["usable"] for e in details))
        for c in ("normal", "hand_hidden")
    }
    counts["offline_translations"] = dict(
        allocated=sum(len(e["shifted_grayscale_diagnostics"]) for e in details),
        id7=sum(e["interpretation"]["shifted_id7"] for e in details),
    )
    counts["actual_camera_packets"] = dict(previous=8, first_refusal=8, independent_terminal=8)
    counts["source_refusal_mechanisms"] = dict(Counter(m["hand_intervention"] for m in mechanisms))
    require(
        len(details) == 32
        and len(mechanisms) == 8
        and counts["offline_translations"]["allocated"] == 128,
        "incomplete diagnosis",
    )
    write(
        pub / "refusal-diagnostics.public.json",
        dict(
            schema="g1.first-refusal.static-pixel-diagnosis.v1",
            plan_sha256=source.PLAN_SHA,
            capture_seal_sha256=gate["capture_seal_sha256"],
            normal_pair_result_sha256=gate["paired_readings_sha256"],
            blind_decisions_sha256=gate["blind_decisions_sha256"],
            camera_audit_sha256=sha(raw / "camera-commands.json"),
            diagnostic_reader_sha256=sha(Path(__file__)),
            counts=counts,
            source_first_refusal_mechanisms=mechanisms,
            paired_diagnostics=details,
            interpretation_notes=[
                "All boards use the registered 6 by 6 print on a 100 mm backing. Projection "
                "and geometric attribution consume sealed truth after blind RGB-D measurement.",
                "Near-depth compares observed optical depth to the plane at integer pixel centres. "
                "A paper contribution needs a hand-only recovery with the same seed and a hand "
                "or finger pixel over 5 mm closer in the corresponding region.",
                "Coverage uses normal renders. The hand intervention removes hand and both "
                "finger geoms. Recovery with no on-paper hand pixels establishes an appearance "
                "effect. The individual contour edge remains unresolved.",
                "Quarter-pixel grayscale shifts change sampling and bilinear interpolation. "
                "Their ID and candidate outcomes are offline diagnostics.",
                "The two feedback endpoints span eight physics steps. The seven intervening "
                "states have no camera packet. Individual hand parts and overlapping causal "
                "mechanisms remain coupled.",
            ],
        ),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("plan", type=Path)
    p.add_argument("raw", type=Path)
    args = p.parse_args()
    diagnose(args.plan.resolve(), args.raw.resolve())


if __name__ == "__main__":
    main()
