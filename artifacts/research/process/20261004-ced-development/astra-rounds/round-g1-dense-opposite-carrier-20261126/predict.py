"""Add registered opposite-carrier print edges to the sealed local ID8 prediction."""

import argparse
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from scripts.graduation import g1_complete_cv_handoff_optics as optics
from scripts.graduation.perception_io import ROOT, read, sha, write

HERE = Path(__file__).resolve().parent
PLAN_PATH = HERE / "plan.json"
PLAN = read(PLAN_PATH)
OUT = ROOT / PLAN["out"]
BASE = ROOT / PLAN["local_out"] / "prediction.json"
OUTPUTS = {"prediction.json", "prediction.cold.json"}
P = PLAN["support"]
SCALE = PLAN["subgrid_scale"]
PHASE = np.asarray(PLAN["subgrid_phase_uv"])
DATA_ROOT = ROOT / "experiments/results"


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def dependencies():
    sys.path.insert(0, str(ROOT / PLAN["local_round"]))
    import seeded_grid

    return seeded_grid.dependencies()


def local_gray(rgb):
    # Match the original PNG IMREAD_GRAYSCALE route, using only authorized samples.
    bgr = np.ascontiguousarray(rgb.reshape(-1, 1, 3)[:, :, ::-1])
    ok, encoded = cv2.imencode(".png", bgr)
    require(ok, "unable to encode checked native gray samples")
    return cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE).ravel().reshape(rgb.shape[:-1])


def sub_camera(meta):
    f = np.asarray(meta["intrinsics"][:2]) / SCALE
    center = (np.asarray(meta["intrinsics"][2:]) - PHASE) / SCALE
    return np.r_[f, center]


def project(world, eye, rotation, intrinsics):
    z = (world - eye) @ rotation
    require((z[:, 2] > 0).all(), "edge search endpoint behind camera")
    return z[:, :2] / z[:, 2, None] * intrinsics[:2] + intrinsics[2:]


def footprint_columns(x, probe_y, forbidden):
    xx = x[:, None, None] * SCALE + PHASE[0]
    yy = probe_y * SCALE + PHASE[1]
    h, w = forbidden.shape
    outside = (xx < 0) | (xx >= w) | (yy < 0) | (yy >= h)
    clipped_x, clipped_y = np.clip(xx, 0, w - 1), np.clip(yy, 0, h - 1)
    allowed = ~(outside | forbidden[clipped_y, clipped_x]).any(axis=(1, 2))
    return allowed, np.broadcast_to(xx, yy.shape), yy


def transition_flags(depth, color, plane):
    return (
        (abs(depth[..., 0] - plane) < P["near_band_m"])
        & (abs(depth[..., 1] - plane) < P["near_band_m"])
        & (depth[..., 2] > plane + P["outside_offset_m"])
        & (depth[..., 3] > plane + P["outside_offset_m"])
        & (color[..., 1] - color[..., 3] > P["contrast_far_dn"])
        & (color[..., 0] - color[..., 2] > P["contrast_transition_dn"])
    )


def ink_flags(depth, color, plane):
    return (
        (abs(depth[..., 4] - plane) < P["near_band_m"])
        & (abs(depth[..., 5] - plane) < P["near_band_m"])
        & (color[..., 4] - color[..., 5] > P["contrast_ink_dn"])
    )


def supported(cols):
    return len(cols) >= P["min_columns_each"] and np.ptp(cols) >= P["min_projected_span_px"]


def one_transition(flags):
    return flags.sum(axis=-1) == 1


def capture_binds(job, forecast):
    return (forecast["original_frame_id"], forecast["original_checksum_sha256"]) == (
        job["frame_id"],
        job["checksum_sha256"],
    )


def controls():
    table = np.array([[1.0, 1.0, 1.1, 1.1, 1.0, 1.0]])
    colors = np.array([[190, 200, 100, 100, 220, 50]])
    forward = np.array([[120.5, 480.5, 639.5, 479.5]])
    meta = {"intrinsics": forward.ravel()}
    f = sub_camera(meta)
    point = np.array([[0.24, -0.15, 1.25]])
    uv = project(point, np.zeros(3), np.eye(3), f)
    exact = project(point, np.zeros(3), np.eye(3), forward.ravel())
    mask = np.zeros((50, 50), bool)
    y = np.array([[[2, 3], [4, 5]], [[2, 3], [4, 5]]])
    allowed, _, _ = footprint_columns(np.array([4, 5]), y, mask)
    mask[SCALE * 3 + PHASE[1], SCALE * 4 + PHASE[0]] = True
    with_mask, _, _ = footprint_columns(np.array([4, 5]), y, mask)
    color_fixture = (np.arange(12 * 15 * 3).reshape(12, 15, 3) % 256).astype(np.uint8)
    rng = np.random.default_rng(1502)
    coords = (rng.integers(0, 12, 12), rng.integers(0, 15, 12))
    hits = transition_flags(table, colors, np.array([1.0]))
    summary = {
        "physical_projection_roundtrip": np.allclose(uv * SCALE + PHASE, exact, atol=1e-12, rtol=0),
        "one_masked_probe_eliminates_whole_column": allowed.tolist() == [True, True]
        and with_mask.tolist() == [False, True],
        "guarded_gray_uses_native_png_values": np.array_equal(
            local_gray(color_fixture[coords]),
            local_gray(color_fixture)[coords],
        ),
        "valid_pair_accepted": bool(hits[0] and ink_flags(table, colors, np.array([1.0]))[0]),
        "wrong_polarity_rejected": not bool(
            transition_flags(table, 255 - colors, np.array([1.0]))[0]
        ),
        "duplicate_transition_not_unique": not one_transition(np.r_[hits, hits]),
        "missing_side_insufficient": not (supported(np.arange(6)) and supported(np.arange(4))),
        "wrong_exposure_refused": not capture_binds(
            {"frame_id": "original", "checksum_sha256": "checksum"},
            {"original_frame_id": "different", "original_checksum_sha256": "checksum"},
        ),
    }
    require(all(summary.values()), "guarded original metric controls failed")
    return {key: bool(value) for key, value in summary.items()}


def sample_side(side, camera, plane_pivot, frame, depth, rgb, valid, mask):
    eye, camera_rotation, f = camera
    normal, anchor, forward, across = frame
    opposite = anchor + P["distance_m"] * forward
    endpoints = np.vstack(
        [
            opposite + side * P["half_width_m"] * across + longitudinal * forward
            for longitudinal in (-P["span_half_m"], P["span_half_m"])
        ]
    )
    ends = project(endpoints, eye, camera_rotation, f)
    if abs(ends[1, 0] - ends[0, 0]) < 8:
        return {"side": side, "reason": "projected_edge_too_short"}
    x0, x1 = np.sort(ends[:, 0])
    x = np.arange(int(np.ceil(x0)), int(np.floor(x1)) + 1)
    slope = (ends[1, 1] - ends[0, 1]) / (ends[1, 0] - ends[0, 0])
    estimated_y = ends[0, 1] + (x - ends[0, 0]) * slope
    sign = int(
        np.sign(estimated_y.mean() - project(opposite[None, :], eye, camera_rotation, f)[0, 1])
    )
    require(sign != 0, "degenerate registered side orientation")
    z_plate = abs((endpoints.mean(0) - eye) @ camera_rotation[:, 2])
    half = P["half_width_m"] * f[1] / z_plate
    rad = max(4, int(np.ceil(P["search_half_m"] * f[1] / z_plate)))
    center = np.rint(estimated_y).astype(int)[:, None] + np.arange(-rad, rad + 1)
    probes = np.stack(
        (
            center - sign,
            center - 2 * sign,
            center,
            center + sign,
            np.rint(center - sign * half * P["quiet_fraction"]).astype(int),
            np.rint(center - sign * half * P["ink_fraction"]).astype(int),
        ),
        axis=-1,
    )
    allowed, dense_x, dense_y = footprint_columns(x, probes, mask)
    eligible = np.flatnonzero(allowed)
    summary = {
        "side": side,
        "searched_columns": len(x),
        "masked_columns": x[~allowed].tolist(),
        "allowed_columns": x[allowed].tolist(),
    }
    if not len(eligible):
        return summary | {"reason": "no_safe_full_search_column"}
    dense_x, dense_y = dense_x[eligible], dense_y[eligible]
    observed_depth = depth[dense_y, dense_x]
    validity = valid[dense_y, dense_x].astype(bool)
    actual_color = local_gray(rgb[dense_y, dense_x]).astype(float)
    source_u, source_v = np.broadcast_arrays(x[eligible, None], center[eligible])
    location = np.column_stack((source_u.ravel(), source_v.ravel()))
    rays = optics._rays(location, *f) @ camera_rotation.T
    denominator = rays @ normal
    require(np.all(abs(denominator) > 0.1), "grazing board edge neighborhood")
    plane = ((plane_pivot - eye) @ normal) / denominator
    plane = plane.reshape(source_u.shape)

    # A competing root may only be excluded by evidence, never by deleting one probe.
    valid_cols = (validity & (observed_depth > 0) & np.isfinite(observed_depth)).all(axis=(1, 2))
    candidate = transition_flags(observed_depth, actual_color, plane)
    unique = one_transition(candidate)
    ink = ink_flags(observed_depth, actual_color, plane)
    accepted = candidate & ink & (valid_cols & unique)[:, None]
    i, j = np.nonzero(accepted)
    columns = source_u[i, j]
    span = int(np.ptp(columns)) if len(columns) else 0
    summary |= {
        "complete_rgbd_columns": x[eligible[valid_cols]].tolist(),
        "multiple_transition_columns": x[eligible[candidate.sum(axis=1) > 1]].tolist(),
        "ink_supported_columns": columns.tolist(),
        "columns_span_subgrid": span,
        "probe_pixels_uv": np.stack((dense_x, dense_y), axis=-1).tolist(),
        "probe_validity": validity.tolist(),
    }
    if not supported(columns):
        return summary | {"reason": "insufficient_two_class_edge_columns"}
    color = actual_color[i, j]
    alpha = np.clip(
        ((color[:, 1] + color[:, 3]) * 0.5 - color[:, 2]) / (color[:, 0] - color[:, 2]), 0, 1
    )
    edges = np.column_stack((columns, source_v[i, j] - sign * alpha))
    directions = optics._rays(edges, *f) @ camera_rotation.T
    denom = directions @ normal
    require(np.all(abs(denom) > 0.1), "unbound interpolation of board edges")
    world = eye + directions * (((plane_pivot - eye) @ normal) / denom)[:, None]
    relative = world - opposite
    points = np.column_stack((relative @ forward, relative @ across - side * P["half_width_m"]))
    behind = np.column_stack((columns, source_v[i, j] - 2 * sign))
    rr = optics._rays(behind, *f) @ camera_rotation.T
    observed = eye + rr * observed_depth[i, j, 1, None]
    return summary | {
        "reason": None,
        "edge_uv": edges.tolist(),
        "metric_xy_m": points.tolist(),
        "inner_two_cells_physical_m": observed.tolist(),
    }


def original_id8_plane(job, forecast, depth, mask, meta):
    seed = forecast["pose"]
    require(
        forecast["reason"] is None
        and seed["method"] == "id8"
        and seed["frame_id"] == forecast["dense_frame_id"]
        and seed["checksum_sha256"] == forecast["dense_raw_sha256"],
        "sealed local ID8 point estimate detached",
    )
    coordinates = np.asarray(forecast["samples"][0]["depth_plane_sample_uv"], dtype=int)
    x, y = coordinates.T
    require(
        (x >= 0).all()
        and (x < meta["width"]).all()
        and (y >= 0).all()
        and (y < meta["height"]).all()
        and not mask[y, x].any(),
        "initial marker samples intersect excluded scene",
    )
    tf = np.asarray(meta["camera_to_world"]).reshape(4, 4)
    eye, rotation = tf[:3, 3], tf[:3, :3]
    original_intrinsics = np.array(meta["intrinsics"])
    clouds = (
        optics._rays(coordinates, *original_intrinsics) * depth[y, x, None]
    ) @ rotation.T + eye
    fit = optics._fit_plane(clouds)
    require(fit is not None, "initial ID8 plane cannot be reproduced")
    n, pivot, inliers = fit
    old = forecast["plane_details"]
    require(
        np.array_equal(n, old["normal"])
        and np.array_equal(pivot, old["pivot"])
        and np.array_equal(inliers, old["inliers"]),
        "frozen local ID8 plane changed",
    )
    corners = np.asarray(forecast["samples"][0]["corners_px"])
    rays = optics._rays(np.vstack((corners, corners.mean(0))), *original_intrinsics) @ rotation.T
    front = eye + rays * (((pivot - eye) @ n) / (rays @ n))[:, None]
    anchor = front[-1]
    vector = (front[1] - front[0] + front[2] - front[3]) / 2
    vector -= n * (n @ vector)
    vector /= np.linalg.norm(vector)
    require(
        np.allclose(anchor, seed["anchor_world_m"], atol=1e-12, rtol=0)
        and np.allclose(
            vector, np.asarray(seed["rotation_object_to_world"])[:, 0], atol=1e-12, rtol=0
        )
        and seed["ids"] == job["optical"]["ids"] == [8],
        "frozen ID8 subpixel anchor or orientation did not reproduce",
    )
    return clouds, n, pivot, anchor, vector, eye, rotation


def pair_pose(support, job, forecast, meta, path):
    require(
        sha(path) == meta["file_sha256"] == forecast["dense_raw_sha256"],
        "wrong source image for opposite-carrier prediction",
    )
    require(capture_binds(job, forecast), "original frame binding differs")
    mask, proof = support.exclusions(job, meta)
    require(proof == forecast["exclusions"], "changed exclusion mask around guarded surfaces")
    with np.load(path, allow_pickle=False) as native:
        rgb, depth, valid = (native[k] for k in ("rgb", "depth_m", "valid"))
    require(rgb.shape[:2] == depth.shape == valid.shape == mask.shape, "dense source shape differs")
    clouds, normal, pivot, anchor, forward, eye, rotation = original_id8_plane(
        job,
        forecast,
        depth,
        mask,
        meta,
    )
    f = sub_camera(meta)
    across = np.cross(normal, forward)
    sides = [
        sample_side(
            side,
            (eye, rotation, f),
            pivot,
            (normal, anchor, forward, across),
            depth,
            rgb,
            valid,
            mask,
        )
        for side in (-1, 1)
    ]
    result = {
        "key": job["key"],
        "dense_frame_id": forecast["dense_frame_id"],
        "source_shutter_checksum": job["checksum_sha256"],
        "dense_raw_sha256": forecast["dense_raw_sha256"],
        "side_results": sides,
        "sample_phase_dense_uv": PHASE.tolist(),
    }
    if any(s["reason"] is not None for s in sides):
        return result | {"reason": "opposite_both_edges_required"}
    points = np.vstack([np.asarray(s["metric_xy_m"]) for s in sides])
    t, lateral = points.T
    slope, intercept = np.polyfit(t, lateral, 1)
    residual = float(abs(lateral - (slope * t + intercept)).max())
    result |= {
        "fit_slope": float(slope),
        "fit_lateral_intercept_m": float(intercept),
        "fit_maximum_residual_m": residual,
    }
    if (
        residual > P["max_fit_residual_m"]
        or abs(slope) > P["max_fit_slope"]
        or abs(intercept) > P["max_abs_offset_m"]
    ):
        return result | {"reason": "opposite_metric_fit_outside_registered_bounds"}
    distance = P["distance_m"]
    baseline = (
        np.sign(distance) * np.sqrt(distance**2 - intercept**2) * forward + intercept * across
    )
    new_direction = baseline / distance
    far_points = [np.asarray(s["inner_two_cells_physical_m"]) for s in sides]
    fit = optics._fit_plane(np.vstack([clouds, *far_points]))
    if fit is None:
        return result | {"reason": "common_plane_refit_failed"}
    n, _, inliers = fit
    new_direction -= n * (n @ new_direction)
    new_direction /= np.linalg.norm(new_direction)
    rot = np.column_stack((new_direction, np.cross(n, new_direction), n))
    lever = np.asarray(forecast["pose"]["anchor_object_m"])
    pose = forecast["pose"] | {
        "center_world_m": (anchor - rot @ lever).tolist(),
        "rotation_object_to_world": rot.tolist(),
        "method": "id8_with_guarded_opposite_carrier_edges",
    }
    return result | {"reason": None, "pose": pose, "refitted_plane_inliers": int(inliers.sum())}


def blinded(allow, output):
    allowed = set(allow) | {output}

    def deny(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            target = Path(os.fsdecode(args[0])).resolve()
            if target.is_relative_to(DATA_ROOT) and target not in allowed:
                raise PermissionError(f"outside guarded optical data: {target.name}")

    sys.addaudithook(deny)
    checked = 0
    for p in (
        ROOT / PLAN["dense"] / "capture-input.json",
        ROOT / PLAN["local_out"] / "readback.json",
    ):
        try:
            p.read_bytes()
        except PermissionError:
            checked += 1
        else:
            raise ValueError("blind edge estimate opened a label or prior score")
    return checked


def run(output):
    for file in ("native/seal.json", "native/index.json", "optical-input.json"):
        relative = f"{PLAN['dense']}/{file}"
        require(sha(ROOT / relative) == PLAN["sha256"][relative], "dense optical source changed")
    needle_seal = PLAN["needle"] + "/seal.json"
    require(sha(ROOT / needle_seal) == PLAN["sha256"][needle_seal], "needle archive changed")
    sys.path.insert(0, str(ROOT / PLAN["stored_marker_round"]))
    import predict as support

    source = PLAN["local_out"]
    cold = ROOT / source / "prediction.cold.json"
    require(
        sha(BASE) == sha(cold) == PLAN["sha256"][f"{source}/prediction.json"]
        and sha(Path(optics.__file__))
        == PLAN["sha256"]["scripts/graduation/g1_complete_cv_handoff_optics.py"],
        "sealed ID8 baseline, source or thresholds differ",
    )
    _, entries = support.snapshot_sources()
    allowed = [BASE, support.ASSET, *(path for _, _, path, _ in entries)]
    denied = blinded(allowed, output)
    marker = {r["dense_frame_id"]: r for r in read(BASE)["dense"]}
    control = controls()
    require(
        len(marker) == len(entries) == 12 and denied == 2, "forecast budget or blindness changed"
    )
    cv2.setNumThreads(1)
    predictions = [
        pair_pose(support, job, marker[frame], meta, path) for job, meta, path, frame in entries
    ]
    write(
        output,
        {
            "plan_sha256": sha(PLAN_PATH),
            "source_sha256": sha(Path(__file__)),
            "initial_prediction_sha256": sha(BASE),
            "controls": control,
            "denied_label_accesses": denied,
            "predictions": predictions,
            "scope": PLAN["scope"],
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", choices=sorted(OUTPUTS))
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    run(OUT / args.output)
