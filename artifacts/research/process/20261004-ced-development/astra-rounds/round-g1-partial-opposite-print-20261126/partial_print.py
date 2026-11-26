"""Measure identifiable partial-print constraints without issuing optical authority."""
import argparse
import base64
from itertools import product
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

import cv2
import numpy as np

from scripts.graduation import g1_complete_cv_handoff_optics as optics
from scripts.graduation.g1_complete_cv_payload_observation import red_face_pose
from scripts.graduation.g1_complete_cv_red_geometry import _SAMPLES

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "round-g1-opposite-edge-color-support-20261126"))
import shadow_readback as source

PLAN_PATH = HERE / "plan.json"
PLAN = source.read(PLAN_PATH)
PRIVATE = source.ROOT / "experiments/results"
OUTPUT = PRIVATE / "g1-partial-opposite-print-20261126" / "audit-01"
OLD_REGISTER = PRIVATE / "g1-opposite-edge-color-support-20261126" / "shadow-01" / "registration.json"
ACTIONS = tuple(
    (code, turn)
    for code in range(50)
    for turn in range(4)
)
DICTIONARY = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
CODES = np.array([
    np.r_[np.rot90(cv2.aruco.generateImageMarker(DICTIONARY, code, 6) > 0, turn).ravel(), True]
    for code, turn in ACTIONS
])


def closed_range(key):
    lo, hi, step = PLAN["grid"][key]
    return np.arange(lo, hi + step, step)


GRID = np.array(list(product(closed_range("x_mm"), closed_range("y_mm"), closed_range("yaw_deg"))))
BASELINE_XY_WIDTH_MM = np.ptp(GRID[:, :2], axis=0)
ID7_NATIVE = ACTIONS.index((7, 0))


def template_samples(points, hypotheses):
    """Resolve which of the same 36 print cells each original optical sample crosses."""
    shifted = points[None] - hypotheses[:, None, None, :2] / 1000
    angle = np.deg2rad(hypotheses[:, 2])[:, None, None]
    cosine, sine = np.cos(angle), np.sin(angle)
    x = cosine * shifted[..., 0] + sine * shifted[..., 1]
    y = -sine * shifted[..., 0] + cosine * shifted[..., 1]
    col = np.floor((x + 0.0375) / 0.0125).astype(int)
    row = np.floor((0.0375 - y) / 0.0125).astype(int)
    within_code = (col >= 0) & (col < 6) & (row >= 0) & (row < 6)
    return np.where(within_code, 6 * row + col, 36)


def batches(xy, subpixels, gray, groups, grid):
    """Fit one contrast per template after removing shared linear illumination nuisance."""
    fit, check = groups
    basis = np.column_stack((np.ones(len(gray)), xy / 0.05))
    q, r = np.linalg.qr(basis[fit])
    if np.min(abs(np.diag(r))) < 1e-8:
        return [], None
    white_data = gray[fit] - q @ (q.T @ gray[fit])
    linear_fit = basis[check] @ np.linalg.solve(r, q.T)
    null = [
        float(np.sqrt(np.mean(white_data**2))),
        float(np.sqrt(np.mean((gray[check] - linear_fit @ gray[fit])**2))),
    ]
    passing = []
    batch_size = 8
    for offset in range(0, len(grid), batch_size):
        batch = grid[offset : offset + batch_size]
        cells = template_samples(subpixels, batch)
        intensities = CODES[:, cells].mean(axis=-1).reshape(-1, len(gray))
        train = intensities[:, fit]
        residual_template = train - (train @ q) @ q.T
        information = np.sum(residual_template**2, axis=1)
        contrast = np.divide(
            residual_template @ white_data, information, where=information > 1e-12,
            out=np.zeros_like(information),
        )
        physical = contrast >= PLAN["min_contrast_dn"]
        fit_error = np.sqrt(np.mean(
            (white_data[None, :] - contrast[:, None] * residual_template)**2, axis=1
        ))
        subset = np.flatnonzero(physical & (null[0] - fit_error >= PLAN["min_rmse_gain_over_null_dn"]))
        if not len(subset):
            continue
        held_res = (gray[fit][None, :] - contrast[subset, None] * train[subset]) @ linear_fit.T
        held_pred = held_res + contrast[subset, None] * intensities[subset][:, check]
        test_error = np.sqrt(np.mean((held_pred - gray[check][None, :])**2, axis=1))
        for index, error in zip(subset, test_error, strict=True):
            if null[1] - error >= PLAN["min_rmse_gain_over_null_dn"]:
                code, hypothesis = divmod(int(index), len(batch))
                passing.append((code, offset + hypothesis, float(fit_error[index]), float(error),
                                float(contrast[index])))
    if passing:
        best = min(row[2] for row in passing)
        passing = [row for row in passing if row[2] <= best + PLAN["feasible_fit_rmse_from_best_dn"]]
    return passing, null


def split_spatial(xy):
    axis = int(np.argmax(np.ptp(xy, axis=0)))
    coordinate = xy[:, axis]
    middle = float(np.median(coordinate))
    gap = PLAN["partition_gap_half_width_m"]
    return axis, (coordinate < middle - gap, coordinate > middle + gap)


def directional_edges(uv, xy, gray, code, hypothesis):
    """Count native-pixel pairs straddling each model cell boundary with measured contrast."""
    lookup = {tuple(pixel): index for index, pixel in enumerate(uv.tolist())}
    pairs = np.array([
        (i, lookup[neighbor])
        for (x, y), i in lookup.items()
        for neighbor in ((x + 1, y), (x, y + 1))
        if neighbor in lookup
    ], dtype=int).reshape(-1, 2)
    a, b = pairs.T
    cells = template_samples(xy[:, None, :], hypothesis[None, :])[0, :, 0]
    expected = CODES[code, cells].astype(int)
    consistent = (gray[b] - gray[a]) * (
        expected[b] - expected[a]
    ) > PLAN["native_transition_edge_difference_strict_gt_dn"]
    row, col = np.divmod(cells, 6)
    same_row = row[a] == row[b]
    same_col = col[a] == col[b]
    common = (cells[a] == 36) | (cells[b] == 36)
    border = (row == 0) | (row == 5) | (col == 0) | (col == 5)
    interior = ~(common | border[a] | border[b])
    return np.array([
        int(np.count_nonzero(consistent & same_row & interior & (abs(col[a] - col[b]) == 1))),
        int(np.count_nonzero(consistent & same_col & interior & (abs(row[a] - row[b]) == 1))),
        int(np.count_nonzero(consistent & common)),
    ])


def summarize(uv, xy, subpixel, gray, mm_per_pixel, grid=GRID):
    result = {
        "native_pixels": int(len(gray)), "unconstrained_xy_width_mm": BASELINE_XY_WIDTH_MM.tolist(),
        "without_opposite_print_xy_width_mm": BASELINE_XY_WIDTH_MM.tolist(),
        "status": "no_metric_increment",
    }
    if len(gray) < 2 * PLAN["min_native_pixels_per_block"]:
        return dict(result, reason="insufficient_coplanar_native_samples")
    split_axis, groups = split_spatial(xy)
    sizes = [int(group.sum()) for group in groups]
    result.update(spatial_split_axis=split_axis, fit_and_held_native_pixels=sizes)
    if min(sizes) < PLAN["min_native_pixels_per_block"]:
        return dict(result, reason="insufficient_separate_spatial_coverage")
    feasible, null = batches(xy, subpixel, gray, groups, grid)
    result["null_fit_and_held_rmse_dn"] = null
    if not feasible:
        return dict(result, reason="no_code_hypothesis_beats_smooth_null_in_both_blocks")

    code_indices = sorted({row[0] for row in feasible})
    hypotheses = grid[[row[1] for row in feasible]]
    lower, upper = hypotheses.min(axis=0), hypotheses.max(axis=0)
    widths = upper - lower
    conditional = [row[1] for row in feasible if row[0] == ID7_NATIVE]
    supports = np.stack([
        directional_edges(uv, xy, gray, code, grid[index])
        for code, index, *_ in feasible
    ])
    min_support = supports.min(axis=0)
    before, after = grid.min(axis=0), grid.max(axis=0)
    touches_boundary = (lower == before) | (upper == after)
    bound_axes = (
        (~touches_boundary[:2])
        & (min_support[:2] > 0)
        & (BASELINE_XY_WIDTH_MM - widths[:2] >= mm_per_pixel)
    )
    strongest = min(feasible, key=lambda row: (row[2], row[3], row[0], row[1]))
    return dict(
        result, reason="all_grid_branches_retained",
        status="discrete_metric_increment" if bound_axes.any() else "no_metric_increment",
        options=[ACTIONS[index] for index in code_indices],
        candidate_count=len(feasible), physical_mm_per_native_pixel=mm_per_pixel,
        all_pose_grid_min_mm_deg=lower.tolist(), all_pose_grid_max_mm_deg=upper.tolist(),
        all_pose_grid_width_mm_deg=widths.tolist(), all_pose_grid_touches_boundary=touches_boundary.tolist(),
        conditional_id7_grid_width_mm_deg=np.ptp(grid[conditional], axis=0).tolist() if conditional else None,
        minimum_measured_ink_x_ink_y_quiet_boundary_per_candidate=min_support.tolist(),
        axis_with_discrete_metric_increment=bound_axes.tolist(),
        best={"code_and_quarter_turns": ACTIONS[strongest[0]], "pose_mm_deg": grid[strongest[1]].tolist(),
              "fit_rmse_dn": strongest[2], "held_rmse_dn": strongest[3], "contrast_dn": strongest[4]},
    )


def sensor_samples(frame, marker, geometry):
    with patch.object(optics, "_opposite_edges", return_value=None):
        base = optics.measured_pose(frame, marker, geometry)
    if not base or base["ids"] != [8]:
        return None
    rigid = np.asarray(base["rotation_object_to_world"])
    anchor = np.asarray(base["anchor_world_m"])
    camera = np.asarray(frame.camera_to_world).reshape(4, 4)
    depth = optics.axial(frame)
    rgb_bgr = cv2.imdecode(
        np.frombuffer(base64.b64decode(frame.rgb_png_base64), np.uint8), cv2.IMREAD_COLOR
    )
    gray = cv2.cvtColor(rgb_bgr, cv2.COLOR_BGR2GRAY)
    red_diag = red_face_pose(frame, marker, geometry, rgb_bgr[:, :, ::-1], depth, base)[1]
    yy, xx = np.indices(depth.shape)
    uv = np.column_stack((xx.ravel(), yy.ravel()))
    offset = (
        np.asarray(geometry["development_dual"]["markers"]["8"]["object_T_marker"]).reshape(4, 4)[:2, 3]
        - np.asarray(geometry["development_dual"]["markers"]["7"]["object_T_marker"]).reshape(4, 4)[:2, 3]
    )
    assert np.array_equal(offset, [0.26, 0.0])

    def plane_at(pixels):
        rays = (optics._rays(pixels.reshape(-1, 2), *frame.intrinsics) @ camera[:3, :3].T)
        axial = ((anchor - camera[:3, 3]) @ rigid[:, 2]) / (rays @ rigid[:, 2])
        points = camera[:3, 3] + rays * axial[:, None]
        xy = (points - anchor) @ rigid[:, :2] + offset
        return xy.reshape(pixels.shape), axial.reshape(pixels.shape[:-1])

    coordinates, plane = plane_at(uv)
    roi = np.max(abs(coordinates), axis=1) < PLAN["roi_max_abs_center_m"]
    finite = np.isfinite(depth.ravel()) & (depth.ravel() > 0)
    mask = np.frombuffer(frame.valid_mask_bytes(), np.uint8).astype(bool)
    neutral = np.ptp(rgb_bgr, axis=2).ravel() < PLAN["neutral_rgb_max_channel_spread_dn_strict"]
    wanted = roi & finite & mask & neutral & (
        abs(depth.ravel() - plane) < PLAN["common_plane_axis_depth_band_m_strict"]
    )
    projected, _ = plane_at(uv[wanted, None, :] + _SAMPLES)
    summary = summarize(
        uv[wanted], coordinates[wanted], projected, gray.ravel()[wanted].astype(float),
        float(1000 * np.median(plane[roi]) / frame.intrinsics[0]),
    )
    return dict(summary, original_single_id8_and_red_face_samples=red_diag["red_top_samples"] if red_diag else 0)


def controls():
    x, y = np.meshgrid(np.arange(-0.042, 0.044, 0.00457), np.arange(-0.042, 0.044, 0.00457))
    xy = np.column_stack((x.ravel(), y.ravel()))
    pixels = np.column_stack((np.tile(np.arange(x.shape[1]), x.shape[0]),
                              np.repeat(np.arange(x.shape[0]), x.shape[1])))
    subpixel = xy[:, None, :] + (_SAMPLES * 0.00457)
    position = np.array([[4, -2, 2]])
    cells = template_samples(subpixel, position)[0]
    gray = 22 + 150 * CODES[ID7_NATIVE, cells].mean(axis=1) + (xy * [20, -20]).sum(axis=1)
    fit, _ = batches(xy, subpixel, gray, split_spatial(xy)[1], GRID)
    identical = [row for row in fit if row[0] == ID7_NATIVE and np.array_equal(GRID[row[1]], position[0])]
    assert identical and identical[0][2] < 1e-9 and identical[0][3] < 1e-9
    blank = 55 + (xy * [20, -20]).sum(axis=1)
    assert summarize(pixels, xy, subpixel, blank, 4.57)["status"] == "no_metric_increment"
    assert summarize(pixels[:0], xy[:0], subpixel[:0], gray[:0], 4.57)["status"] == "no_metric_increment"

    alias = ACTIONS.index((28, 2))
    aliases = np.all(CODES[ID7_NATIVE, cells] == CODES[alias, cells], axis=1)
    coincident, _ = batches(xy[aliases], subpixel[aliases], gray[aliases], split_spatial(xy[aliases])[1], position)
    assert any(row[0] == ID7_NATIVE for row in coincident) and any(row[0] == alias for row in coincident)
    return {"known_displacement": True, "smooth_blank": True, "empty_input": True,
            "coincident_id7_id28_retained": True}


def freeze():
    for item, digest in PLAN["input_sha256"].items():
        source.pin(source.ROOT / item, digest)
    enrolled, _ = source.exposure_metadata()
    prior = source.read(OLD_REGISTER)["packets"]
    packets = {key: info for key, info in enrolled.items() if key.startswith(("A/", "B/", "t02/"))}
    assert len(packets) == 22 and all(prior[key] == value for key, value in packets.items())
    for entry in packets.values():
        source.pin(source.ROOT / entry["path"], entry["sha256"])
    checked = controls()
    OUTPUT.mkdir(parents=True, exist_ok=False)
    source.write(OUTPUT / "registration.json", {
        "plan_sha256": source.sha(PLAN_PATH), "reader_sha256": source.sha(Path(__file__)),
        "packets": packets, "controls": checked,
    })


def predict(digest, output):
    reg = source.read(source.pin(OUTPUT / "registration.json", digest))
    assert reg["plan_sha256"] == source.sha(PLAN_PATH) and reg["reader_sha256"] == source.sha(Path(__file__))
    _, bindings = source.exposure_metadata()
    packet_paths = {source.ROOT / row["path"] for row in reg["packets"].values()}
    binding_paths = {bind[0].resolve() for key, bind in bindings.items() if key != "val04"}
    allowed = packet_paths | binding_paths | {
        source.CV / "batches/train-full-04/allocation.json",
        source.CV / source.T02_REL / "allocation.json",
        source.RUNTIME / "runtime-build.json",
        source.RUNTIME / "scripts/graduation/g1_visibility_vision.py",
        output.resolve(),
    }

    def deny(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).resolve()
            if path.is_relative_to(PRIVATE) and path not in allowed:
                raise PermissionError("image-only prediction scope")

    sys.addaudithook(deny)
    try:
        (source.CV / source.T02_REL / "instance/offline-truth.json").open("rb").close()
    except PermissionError:
        pass
    else:
        raise ValueError("physical label isolation check failed")
    cv2.setNumThreads(1)
    detector, marker_hash = source.native_marker(source.GENER)
    assert marker_hash == source.PLAN["marker_sha256"]
    frames = {}
    for key, item in reg["packets"].items():
        path, scene, episode = bindings[item["binding"]]
        identity, geometry = (
            source.bound(path, scene, episode) if key.startswith("t02/")
            else source.bind_fixture(path.parent, {"id": scene, "episode_id": episode})
        )
        frame = source.checked_packet(source.ROOT / item["path"], item["sha256"])
        marker = detector(frame, geometry)
        assert frame.frame_id == item["frame_id"] and frame.checksum_sha256 == item["checksum"]
        assert identity.matches(frame, marker, geometry, item["step"])
        existing = optics.rigid_pose(frame, marker, geometry, identity=identity, physics_step=item["step"])
        frames[key] = dict(
            pose_before=existing["method"] if existing else None,
            partial_print=sensor_samples(frame, marker, geometry),
            online_qualification=False,
            retained_unknown_near=(key == "t02/2112"),
        )
    source.write(output, dict(registered_input_sha256=digest, controls=reg["controls"], frames=frames,
                             physical_labels_read=False, new_exposures=0, new_integrations=0,
                             new_online_qualifications=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("register", "predict"))
    parser.add_argument("registration_sha256", nargs="?")
    parser.add_argument("slot", nargs="?", choices=("first", "second"))
    args = parser.parse_args()
    if args.mode == "register":
        freeze()
    else:
        predict(args.registration_sha256, OUTPUT / ("prediction-" + args.slot + ".json"))
