"""Check complete printed identity and fit the visible subset strictly outside the mask."""

import argparse
from itertools import product
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import predict as initial
from scripts.graduation import g1_complete_cv_handoff_optics as optics
from scripts.graduation.g1_dual_observer import _decode, _measure_side
from scripts.graduation.perception_io import read, sha, write

FOLLOWUP_PATH = initial.HERE / "plan-mask-support.json"
FOLLOWUP = read(FOLLOWUP_PATH)
FIRST = initial.OUT / "prediction.json"
FIRST_COLD = initial.OUT / "prediction.cold.json"
OUTPUTS = {"masked-support.json", "masked-support.cold.json"}
SQUARE = np.array([[0, 0], [6, 0], [6, 6], [0, 6]], np.float32)


def local_luminance(gray, coords, exclusion):
    u, v = coords.T
    iu, iv = np.floor(coords).astype(int).T
    if (
        (iu < 0).any()
        or (iv < 0).any()
        or (iu + 1 >= gray.shape[1]).any()
        or (iv + 1 >= gray.shape[0]).any()
    ):
        return None
    pixels = [(iv + j, iu + i) for j, i in product((0, 1), repeat=2)]
    if any(exclusion[y, x].any() for y, x in pixels):
        return None
    xx, yy = u - iu, v - iv
    weights = ((1 - xx) * (1 - yy), xx * (1 - yy), (1 - xx) * yy, xx * yy)
    return np.sum([gray[y, x] * w for (y, x), w in zip(pixels, weights, strict=True)], axis=0)


def proof_print(gray, corners, mask, registered):
    transform = cv2.getPerspectiveTransform(SQUARE, np.float32(corners))
    local = np.float32(
        [
            [i + 0.5 + x, j + 0.5 + y]
            for j, i in product(range(6), repeat=2)
            for y, x in product(FOLLOWUP["cell_offsets"], repeat=2)
        ]
    )
    sensor = cv2.perspectiveTransform(local[None, :, :], transform)[0]
    intensities = local_luminance(gray, sensor, mask)
    if intensities is None:
        return None
    signal = np.rint(intensities).astype(np.uint8)
    threshold, binary = cv2.threshold(signal, 0, 1, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    patch_size = len(FOLLOWUP["cell_offsets"]) ** 2
    bits = binary.reshape(6, 6, patch_size)
    valid = np.asarray([[int(c) for c in row] for row in registered], dtype=np.uint8)
    if not np.array_equal(bits, np.repeat(valid[:, :, None], patch_size, axis=2)):
        return None
    identity_count = sum(np.array_equal(valid, np.rot90(bits[:, :, 0], k)) for k in range(4))
    if identity_count != 1:
        return None
    return {
        "all_cells_verified_unique_orientation": True,
        "threshold_dn": threshold,
        "color_sample_center_uv": sensor.tolist(),
        "registered_bits": registered,
    }


def recognizable(gray, mask, fill):
    source = gray.copy()
    source[mask] = fill
    rows, ambiguous, count = _decode(source)
    ids = [r["id"] for r in rows]
    if ambiguous or ids != [8] or rows[0]["origins"] != ["direct"]:
        return ids, count, None
    return ids, count, rows[0]


def quadrants(samples, uv):
    to_marker = cv2.getPerspectiveTransform(np.float32(uv), SQUARE)
    coords = cv2.perspectiveTransform(np.float32(samples)[None, :, :], to_marker)[0]
    x, y = coords.T
    return [
        int(np.count_nonzero((sx * (x - 3) > 0) & (sy * (y - 3) > 0)))
        for sy, sx in product((-1, 1), repeat=2)
    ], coords


def fit_geometry(frame, geometry, marker, usable, z):
    tf = np.asarray(frame.camera_to_world).reshape(4, 4)
    points = (optics._rays(usable, *frame.intrinsics) * z[usable[:, 1], usable[:, 0], None]) @ tf[
        :3, :3
    ].T + tf[:3, 3]
    model = optics._fit_plane(points)
    if model is None:
        return "registered_plane_failed", None
    normal, pivot, inlier = model
    corner_uv = marker["by_id"]["8"]["ordered_corners_px"]
    counts, coords = quadrants(usable[inlier], corner_uv)
    hull = cv2.convexHull(coords)
    if (
        min(counts) == 0
        or np.linalg.matrix_rank(coords - coords.mean(0)) != 2
        or cv2.pointPolygonTest(hull, (3.0, 3.0), False) != 1
    ):
        return "unbalanced_unmasked_plane_support", None
    frame.depth_float32_base64 = initial.base64.b64encode(z.astype("<f4", copy=False).tobytes())
    with (
        patch.object(optics, "_pixels", return_value=usable),
        patch.object(optics, "_opposite_edges", return_value=None),
    ):
        pose = optics.measured_pose(frame, marker, geometry)
    if pose is None:
        return "single_tag_projection_unqualified", None
    residual = (points[inlier] - pivot) @ normal
    return None, {
        "pose": pose,
        "normal": normal.tolist(),
        "pivot": pivot.tolist(),
        "inliers": inlier.tolist(),
        "quadrants_inlier": counts,
        "maximum_inlier_normal_residual_m": float(abs(residual).max()),
        "inlier_design_singular_values": np.linalg.svd(
            coords - coords.mean(0), compute_uv=False
        ).tolist(),
    }


def partial_marker(gray, depth, frame, geometry, mask):
    ids, rejected, first = recognizable(gray, mask, 127)
    result = {"detected": ids, "rejected_candidates": rejected}
    if first is None:
        return result | {"reason": "missing_or_ambiguous_direct_id8"}
    uv = first["corners"]
    pad = initial.PLAN["corner_neighborhood_px"]
    accepted_windows = []
    for u, v in np.rint(np.vstack((uv, uv.mean(0)))).astype(int):
        if (
            u < pad
            or v < pad
            or u + pad >= frame.width
            or v + pad >= frame.height
            or mask[v - pad : v + pad + 1, u - pad : u + pad + 1].any()
        ):
            return result | {"reason": "corner_neighborhood_touches_exclusion"}
        accepted_windows.append([int(u), int(v)])
    for dn in FOLLOWUP["fill_dn"]:
        _, _, alternative = recognizable(gray, mask, dn)
        if alternative is None or not np.array_equal(alternative["corners"], uv):
            return result | {"reason": "ordered_corners_depend_on_excluded_fill"}
    registered = geometry["development_dual"]["markers"]["8"]["dictionary_rows"]
    print_proof = proof_print(gray, uv, mask, registered)
    if print_proof is None:
        return result | {"reason": "unproved_complete_print_outside_mask"}
    original = optics._pixels(uv, frame.width, frame.height)
    if original is None:
        return result | {"reason": "registered_marker_interior_unavailable"}
    usable = original[~mask[original[:, 1], original[:, 0]]]
    result |= {
        "original_depth_count": len(original),
        "retained_depth_count": len(usable),
        "quadrants_before_mask": quadrants(original, uv)[0],
        "print_independence": print_proof,
        "fill_controls_identical": True,
    }
    if len(usable) < FOLLOWUP["original_interior_min_samples"]:
        return result | {"reason": "unmasked_depth_count_insufficient"}
    result["quadrants_after_mask"] = quadrants(usable, uv)[0]
    z = depth[usable[:, 1], usable[:, 0]]
    if not (np.isfinite(z) & (z > 0)).all():
        return result | {"reason": "unmasked_depth_invalid"}
    side = _measure_side(frame, geometry, first, depth)
    if not side["usable"]:
        return result | {"reason": side["reason"]}
    marker = {
        "usable": True,
        "frame_id": frame.frame_id,
        "checksum": frame.checksum_sha256,
        "asset_sha256": geometry["pose_marker"]["marked_asset_sha256"],
        "registration_id": geometry["registration_id"],
        "observed_ids": [8],
        "usable_ids": [8],
        "by_id": {"8": side},
    }
    reason, fit = fit_geometry(frame, geometry, marker, usable, depth)
    if fit is None:
        return result | {"reason": reason}
    for value in FOLLOWUP["depth_poison_m"]:
        replacement = depth.copy()
        replacement[mask] = value
        after, variant = fit_geometry(frame, geometry, marker, usable, replacement)
        initial.require(
            after is None and variant == fit, "excluded depth affected retained plane or pose"
        )
    closure = {
        "marker_id": 8,
        "corners_px": uv.tolist(),
        "depth_plane_sample_uv": usable.tolist(),
        "corner_and_center_bound_neighborhood_centers": accepted_windows,
        "corner_and_center_depth_radius_px": 1,
        "excluded_pixel_overlap": 0,
    }
    return result | {
        "pose": fit.pop("pose"),
        "reason": None,
        "samples": [closure],
        "plane_details": fit,
        "depth_exclusion_poison_controls": len(FOLLOWUP["depth_poison_m"]),
    }


def run(out):
    require = initial.require
    require(
        initial.sha(FIRST) == initial.sha(FIRST_COLD) == FOLLOWUP["source_failed_sha256"],
        "original two failure predictions changed",
    )
    require(
        initial.sha(initial.OUT / "predict.executed.py") == FOLLOWUP["source_executed_sha256"],
        "source used for the first two predictions changed",
    )
    allowed = {
        initial.OPTICAL,
        initial.ASSET,
        initial.ROOT / initial.PLAN["original_allocation"],
        initial.DENSE / "native/seal.json",
        initial.DENSE / "native/index.json",
        initial.NEEDLE / "seal.json",
        initial.NEEDLE / "index.json",
    }
    for p in allowed:
        rel = p.relative_to(initial.ROOT).as_posix()
        if rel in initial.PLAN["sha256"]:
            require(initial.sha(p) == initial.PLAN["sha256"][rel], f"input drift: {p.name}")
    camera, specs = initial.snapshot_sources()
    allowed.update(path for _, _, path, _ in specs)
    denied = initial.activate_blind_read(allowed, out)
    geometry = read(initial.ROOT / initial.PLAN["original_allocation"])["geometry"]
    cv2.setNumThreads(1)
    with patch.object(initial, "marker_pose", partial_marker):
        rows = [initial.fit_dense(j, m, raw, frame, camera, geometry) for j, m, raw, frame in specs]
    write(
        out,
        {
            "followup_plan_sha256": sha(FOLLOWUP_PATH),
            "source_sha256": sha(Path(__file__)),
            "inherited_predictor_sha256": sha(initial.HERE / "predict.py"),
            "optical_input_sha256": sha(initial.OPTICAL),
            "blocked_file_accesses": denied,
            "dense": rows,
            "scope": FOLLOWUP["scope"],
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", choices=sorted(OUTPUTS))
    args = parser.parse_args()
    run(initial.OUT / args.output)
