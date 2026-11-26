"""Verify a fixed ID8 hypothesis with guarded dense samples and the original grid fitter."""

import argparse
import base64
import gzip
import hashlib
import sys
from itertools import product
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from scripts.graduation import g1_complete_cv_handoff_optics as optics
from scripts.graduation import g1_visibility_grid as grid
from scripts.graduation.g1_dual_observer import _decode, _measure_side
from scripts.graduation.perception_io import ROOT, read, sha, write

from cloud_edge_robot_arm.vision.observations import RGBDObservation

HERE = Path(__file__).resolve().parent
PLAN_PATH = HERE / "plan.json"
PLAN = read(PLAN_PATH)
HAND_PLAN = HERE / "plan-handedness.json"
OUT = ROOT / PLAN["out"]
ORIGINAL_SAMPLE = grid._sample
OUTPUTS = {"prediction.json", "prediction.cold.json"}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def dependencies():
    sys.path.insert(0, str(ROOT / PLAN["prior_round"]))
    import masked_support
    import predict

    return predict, masked_support


class OutsideSupport(ValueError):
    def __init__(self, details):
        self.details = details
        super().__init__("guarded sampling footprint leaves allowed optical pixels")


class RegisteredSampler:
    """Populate the gray scratch array only at proven unmasked interpolation pixels."""

    def __init__(self, rgb, exclusion):
        self.rgb, self.exclusion = rgb, exclusion
        self.gray = np.zeros(exclusion.shape, dtype=np.uint8)
        self.calls = []
        self.pixels = set()

    def __call__(self, gray, xy):
        require(gray is self.gray, "native grid tried to bypass guarded gray storage")
        q = np.ascontiguousarray(xy, dtype=np.float32).reshape(-1, 2)
        if not np.isfinite(q).all():
            raise OutsideSupport({"call": len(self.calls), "reason": "nonfinite_grid_coordinate"})
        integer, _ = cv2.convertMaps(q[None, :, :], None, cv2.CV_16SC2)
        integer = integer[0].astype(int)
        floor = np.floor(q).astype(int)
        offsets = np.array(list(product((0, 1), repeat=2)))
        # Check both the exact quantized OpenCV footprint and the floating-point footprint.
        footprint = np.concatenate(
            (integer[:, None, :] + offsets, floor[:, None, :] + offsets), axis=1
        )
        width, height = self.gray.shape[::-1]
        outside = np.any((footprint < 0) | (footprint >= [width, height]), axis=2)
        clamped = np.clip(footprint, [0, 0], [width - 1, height - 1])
        forbidden = outside | self.exclusion[clamped[:, :, 1], clamped[:, :, 0]]
        stage = (
            "cell_centers"
            if xy.ndim == 2
            else (
                "transition_profiles"
                if xy.shape[-2] == len(grid.PROFILE_OFFSETS)
                else "cell_footprints"
            )
        )
        self.calls.append({"stage": stage, "query_count": len(q)})
        if forbidden.any():
            i, j = np.argwhere(forbidden)[0]
            raise OutsideSupport(
                {
                    "call": len(self.calls) - 1,
                    "stage": stage,
                    "query_index": int(i),
                    "query_center_uv": q[i].tolist(),
                    "unavailable_pixel_uv": footprint[i, j].tolist(),
                    "reason": "outside_image" if outside[i, j] else "touches_exclusion",
                }
            )
        unique = np.unique(footprint.reshape(-1, 2), axis=0)
        u, v = unique.T
        allowed_rgb = np.ascontiguousarray(self.rgb[v, u]).reshape(-1, 1, 3)
        self.gray[v, u] = cv2.cvtColor(allowed_rgb, cv2.COLOR_RGB2GRAY).ravel()
        self.pixels.update(map(tuple, unique.tolist()))
        return ORIGINAL_SAMPLE(self.gray, xy)

    def receipt(self):
        footprint = np.asarray(sorted(self.pixels), dtype="<i4").reshape(-1, 2)
        return {
            "interpolation_calls": self.calls,
            "unique_source_pixels": len(footprint),
            "allowed_footprint_sha256": hashlib.sha256(footprint.tobytes()).hexdigest(),
            "ordered_source_pixels_uv": footprint.tolist(),
        }


def dictionary_matches(observed):
    """Read actual cell signs against all 50 registrations, rotations and reflections."""
    bits = np.asarray(observed).reshape(6, 6)
    matches = []
    if bits[0].any() or bits[-1].any() or bits[:, 0].any() or bits[:, -1].any():
        return []
    for reflected in (False, True):
        bitmap = bits[:, ::-1] if reflected else bits
        for turn in range(4):
            probe = np.rot90(bitmap, turn)
            known = np.flatnonzero(np.all(grid.SYMBOLS == probe, axis=(1, 2)))
            matches.extend((int(base), turn, reflected) for base in known)
    return matches


def unique_orientation(observed, code, original_direction_bound):
    matches = dictionary_matches(observed)
    direct = [match for match in matches if not match[2]]
    reverse = [match for match in matches if match[2]]
    return (
        original_direction_bound
        and direct == [(code, 0, False)]
        and all(match[0] == code for match in reverse)
    )


def registered_order(observed, expected):
    def basis(points):
        u = points[1] - points[0] + points[2] - points[3]
        v = points[3] - points[0] + points[2] - points[1]
        return np.stack((u, v))

    actual, registered = basis(observed), basis(expected)
    denominator = np.linalg.norm(actual, axis=1) * np.linalg.norm(registered, axis=1)
    return (
        np.linalg.det(actual) > 0
        and np.linalg.det(registered) > 0
        and np.all(np.einsum("ij,ij->i", actual, registered) > denominator / np.sqrt(2))
    )


def valid_binding(source_id, checksum, camera, job, old_camera):
    pose = job["optical"]
    return (
        source_id == job["frame_id"] == pose["frame_id"]
        and checksum == job["checksum_sha256"] == pose["checksum_sha256"]
        and camera == old_camera
        and abs(np.linalg.det(np.asarray(camera["camera_to_world"]).reshape(4, 4)[:3, :3]) - 1.0)
        < 1e-9
        and pose["ids"] == [PLAN["expected_code"]]
    )


def registered_quad(job, camera, geometry):
    p = job["optical"]
    marker = geometry["development_dual"]["markers"][str(PLAN["expected_code"])]
    marker_to_object = np.asarray(marker["object_T_marker"]).reshape(4, 4)
    corners = np.asarray(marker["ordered_corners_marker_m"])
    local = corners @ marker_to_object[:3, :3].T + marker_to_object[:3, 3]
    world = local @ np.asarray(p["rotation"]).T + p["center_m"]
    tf = np.asarray(camera["camera_to_world"]).reshape(4, 4)
    camera_points = (world - tf[:3, 3]) @ tf[:3, :3]
    fx, fy, cx, cy = camera["intrinsics"]
    require((camera_points[:, 2] > 0).all(), "bound marker prediction behind camera")
    return camera_points[:, :2] / camera_points[:, 2, None] * [fx, fy] + [cx, cy]


def sampler_controls():
    image = (np.arange(21 * 23 * 3).reshape(21, 23, 3) % 256).astype(np.uint8)
    query = np.array([[[4.125, 6.875], [8.98, 9.999]], [[13.49, 14.51], [4.0, 5.0]]])
    mask = np.zeros(image.shape[:2], bool)
    fixture = RegisteredSampler(image, mask)
    equivalent = np.array_equal(
        fixture(fixture.gray, query),
        ORIGINAL_SAMPLE(cv2.cvtColor(image, cv2.COLOR_RGB2GRAY), query),
    )
    mask[5, 4] = True
    guarded = False
    try:
        fixture(fixture.gray, np.array([[4.0, 5.0]]))
    except OutsideSupport:
        guarded = True
    code = PLAN["expected_code"]
    marker = grid.SYMBOLS[code].copy()
    corrupt = marker.copy()
    corrupt[2, 2] ^= True
    reversed_and_rotated = np.rot90(marker[:, ::-1])
    proper_camera = {"camera_to_world": np.eye(4).ravel().tolist()}
    reflected_camera = {"camera_to_world": np.diag([-1, 1, 1, 1]).ravel().tolist()}
    fake = {
        "frame_id": "source",
        "checksum_sha256": "sha",
        "optical": {
            "frame_id": "source",
            "checksum_sha256": "sha",
            "ids": [8],
        },
    }
    square = np.array([[10, 10], [16, 10], [16, 16], [10, 16]])
    outcomes = {
        "native_gray_and_interpolation_equal": equivalent,
        "touching_mask_refused_before_rgb": guarded,
        "known_marker_positive": unique_orientation(marker, code, True),
        "wrong_orientation_refused": not unique_orientation(np.rot90(marker), code, True),
        "unrotated_mirror_refused": not unique_orientation(marker[:, ::-1], code, True),
        "one_bit_change_refused": not unique_orientation(corrupt, code, True),
        "rotated_reflection_is_same_unresolvable_word": np.array_equal(reversed_and_rotated, marker)
        and (code, 1, True) in dictionary_matches(marker),
        "missing_external_direction_refused": not unique_orientation(marker, code, False),
        "valid_external_pair": valid_binding("source", "sha", proper_camera, fake, proper_camera),
        "reflected_camera_refused": not valid_binding(
            "source",
            "sha",
            reflected_camera,
            fake,
            reflected_camera,
        ),
        "swapped_source_refused": not valid_binding(
            "other", "sha", proper_camera, fake, proper_camera
        ),
        "correct_corner_order": bool(registered_order(square, square)),
        "cycled_or_reflected_corner_order_refused": not (
            registered_order(np.roll(square, 1, axis=0), square)
            or registered_order(square[::-1], square)
        ),
    }
    require(all(outcomes.values()), "registered sampling/identity controls failed")
    return outcomes


def ordered_original_seed(path, digest, job, old_camera, geometry):
    require(sha(path) == digest, "original 320 source differs")
    payload = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
    frame = RGBDObservation.model_validate_json(payload)
    require(
        frame.sim_time_s == job["time_s"]
        and valid_binding(
            frame.frame_id,
            frame.checksum_sha256,
            frame.model_dump(mode="json", include=set(old_camera)),
            job,
            old_camera,
        ),
        "seed cannot be traced to the original certified marker observation",
    )
    raw = np.frombuffer(base64.b64decode(frame.rgb_png_base64), dtype=np.uint8)
    gray = cv2.cvtColor(cv2.imdecode(raw, cv2.IMREAD_COLOR), cv2.COLOR_BGR2GRAY)
    candidates, ambiguous, _ = _decode(gray)
    if ambiguous or len(candidates) != 1 or candidates[0]["id"] != PLAN["expected_code"]:
        return None
    if candidates[0]["origins"] != ["direct"]:
        return None
    quad = np.asarray(candidates[0]["corners"])
    if not registered_order(quad, registered_quad(job, old_camera, geometry)):
        return None
    return quad


def pose_from_grid(result, frame, geometry, depth, mask, support, profile):
    corners = np.asarray(result["corners"])
    margin = support.PLAN["corner_neighborhood_px"]
    footprint_centers = np.rint(np.vstack((corners, corners.mean(axis=0)))).astype(int)
    for u, v in footprint_centers:
        if (
            u < margin
            or v < margin
            or u + margin >= frame.width
            or v + margin >= frame.height
            or mask[v - margin : v + margin + 1, u - margin : u + margin + 1].any()
        ):
            return {"reason": "plane_check_neighborhood_touches_exclusion"}
    entire = optics._pixels(corners, frame.width, frame.height)
    if entire is None:
        return {"reason": "no_original_marker_plane_support"}
    kept = entire[~mask[entire[:, 1], entire[:, 0]]]
    if len(kept) < profile.FOLLOWUP["original_interior_min_samples"]:
        return {"reason": "unmasked_depth_count_insufficient"}
    selected = depth[kept[:, 1], kept[:, 0]]
    if not (np.isfinite(selected) & (selected > 0)).all():
        return {"reason": "unmasked_depth_invalid"}
    observation = {"id": 8, "corners": corners, "origins": ["registered_dense_grid"]}
    side = _measure_side(frame, geometry, observation, depth)
    if not side["usable"]:
        return {"reason": side["reason"]}
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
    reason, answer = profile.fit_geometry(frame, geometry, marker, kept, depth)
    if answer is None:
        return {"reason": reason}
    return {
        "reason": None,
        "pose": answer.pop("pose"),
        "plane_details": answer,
        "original_interior_count": len(entire),
        "retained_depth_count": len(kept),
        "samples": [
            {
                "marker_id": 8,
                "corners_px": corners.tolist(),
                "depth_plane_sample_uv": kept.tolist(),
                "corner_and_center_bound_neighborhood_centers": footprint_centers.tolist(),
                "excluded_pixel_overlap": 0,
            }
        ],
    }


def frame_forecast(support, profile, job, meta, path, dense_id, standard_seed, initial_camera, geo):
    require(sha(path) == meta["file_sha256"], "native dense packet changed")
    scoped = support.optical_registration(meta, initial_camera)
    mask, footprint = support.exclusions(job, scoped)
    result = {
        "key": job["key"],
        "dense_frame_id": dense_id,
        "dense_raw_sha256": meta["file_sha256"],
        "original_frame_id": job["frame_id"],
        "original_checksum_sha256": job["checksum_sha256"],
        "exclusions": footprint,
        "detected": [],
    }
    if standard_seed is None:
        return result | {"reason": "no_bound_unique_original_320_pose_seed"}
    scaled = PLAN["capture_scale"] * (standard_seed + 0.5) - 0.5
    center, basis = grid._quad_pose(scaled)
    result["original_320_seed_quad_px"] = standard_seed.tolist()
    result["mapped_1280_seed_quad_px"] = scaled.tolist()
    with np.load(path, allow_pickle=False) as data:
        rgb, z, valid = (data[k] for k in ("rgb", "depth_m", "valid"))
    size = (scoped["height"], scoped["width"])
    require(
        rgb.dtype == np.uint8
        and rgb.shape == size + (3,)
        and z.shape == valid.shape == size
        and np.array_equal(z > 0, valid.astype(bool)),
        "packed native dense evidence does not match camera",
    )
    sampler = RegisteredSampler(rgb, mask)
    try:
        with patch.object(grid, "_sample", sampler):
            verified = grid._verify(sampler.gray, PLAN["expected_code"], center, basis)
    except OutsideSupport as failure:
        return result | {
            "reason": "fixed_grid_touches_exclusion_or_image_edge",
            "rejected_footprint": failure.details,
            "sampler": sampler.receipt(),
        }
    result["sampler"] = sampler.receipt()
    if verified is None:
        return result | {"reason": "original_fixed_grid_verification_refused"}
    record = verified["grid_support"]
    bits = np.array(record["cell_values"]) > record["threshold_gray"]
    if not unique_orientation(bits, PLAN["expected_code"], True):
        return result | {"reason": "complete_dictionary_or_mirror_test_failed"}
    result["detected"] = [8]
    grid_corners = verified["corners"]
    result["max_seed_corner_displacement_dense_px"] = float(
        np.linalg.norm(grid_corners - scaled, axis=1).max()
    )
    result["grid_support"] = record
    result["word_does_not_determine_handedness"] = True
    result["dictionary_matches_including_mirrors"] = dictionary_matches(bits)
    use_frame = support.diag_frame(dense_id, meta["file_sha256"], scoped)
    return result | pose_from_grid(
        verified, use_frame, geo | {"camera": scoped}, z, mask, support, profile
    )


def run(destination):
    support, profile = dependencies()
    hand = read(HAND_PLAN)
    require(
        sha(OUT / "mirror-control.red.json") == hand["failure_sha256"]
        and sha(OUT / "seeded_grid.synthetic-failed.py") == hand["failed_driver_sha256"],
        "original handedness failure did not remain frozen",
    )
    dense_camera, specs = support.snapshot_sources()
    old_packets = support.old_source_paths()
    denied_paths = (
        support.DENSE / "capture-input.json",
        ROOT / PLAN["original_t02_label"],
        ROOT / PLAN["prior_output"] / "physical-readback.json",
    )
    by_key = {}
    allow = {
        support.OPTICAL,
        support.ASSET,
        ROOT / support.PLAN["original_allocation"],
        destination,
    }
    for job, _, path, _ in specs:
        allow.add(path)
        key = job["key"]
        if key not in by_key:
            if job["frame_id"] in old_packets:
                previous, packet = old_packets[job["frame_id"]]
                by_key[key] = (previous, packet["file_sha256"])
            else:
                named = PLAN["original_t02_frame"]
                by_key[key] = (ROOT / named, PLAN["sha256"][named])
            allow.add(by_key[key][0])
    for name, digest in PLAN["sha256"].items():
        path = (ROOT / name).resolve()
        if path not in denied_paths and "physical-readback" not in name:
            require(
                path.is_relative_to(ROOT) and sha(path) == digest,
                f"preflight source changed: {name}",
            )

    def guard(event, args):
        import os

        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).resolve()
            if path.is_relative_to(ROOT / "experiments/results") and path not in allow:
                raise PermissionError(f"not a registered optical input: {path.name}")

    sys.addaudithook(guard)
    denied = 0
    for file in denied_paths:
        try:
            file.read_bytes()
        except PermissionError:
            denied += 1
        else:
            raise ValueError("prediction opened a label or prior readback")
    cv2.setNumThreads(1)
    controls = sampler_controls()
    geo = read(ROOT / support.PLAN["original_allocation"])["geometry"]
    require(geo["camera"] == dense_camera, "old 320 camera registration differs")
    seeds = {}
    rows = []
    for job, packed, path, frame in specs:
        key = job["key"]
        if key not in seeds:
            previous, expected = by_key[key]
            seeds[key] = ordered_original_seed(previous, expected, job, dense_camera, geo)
        rows.append(
            frame_forecast(
                support, profile, job, packed, path, frame, seeds[key], dense_camera, geo
            )
        )
    require(
        len(seeds) == 11 and len(rows) == 12 and denied == len(denied_paths),
        "blind source denominator changed",
    )
    write(
        destination,
        {
            "plan_sha256": sha(PLAN_PATH),
            "handedness_plan_sha256": sha(HAND_PLAN),
            "source_sha256": sha(Path(__file__)),
            "unique_original_seeds": len(seeds),
            "refused_file_accesses": denied,
            "sampling_controls": controls,
            "dense": rows,
            "scope": PLAN["scope"],
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", choices=sorted(OUTPUTS))
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    run(OUT / args.output)
