"""Read anonymous RGB-D, preserving actual decoder candidates and offline-only translations."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import cv2
import numpy as np
from scripts.graduation import g1_mount_screen_pixels as single
from scripts.graduation import proposal_camera as cam
from scripts.graduation.g1_mount_geometry import require
from scripts.graduation.perception_io import pinned, read, sha, write

from cloud_edge_robot_arm.vision.pose_markers import (
    PoseMarkerRegistration,
    _decode_subpix_rejected_candidates,
    detect_pose_marker,
)

SHIFTS = ((0.25, 0), (-0.25, 0), (0, 0.25), (0, -0.25))


def quads(values):
    return [np.asarray(v).reshape(4, 2).tolist() for v in values]


def decode(gray):
    params = cv2.aruco.DetectorParameters()
    params.errorCorrectionRate = 0.0
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    detector = cv2.aruco.ArucoDetector(dictionary, params)
    direct, ids, rejected = detector.detectMarkers(gray)
    direct_ids = [] if ids is None else ids.ravel().tolist()
    recovered_ids, recovered, found_at = [], [], []
    if not direct_ids:
        for i, quad in enumerate(rejected):
            corners, found = _decode_subpix_rejected_candidates(gray, [quad], dictionary)
            if found is not None:
                recovered_ids.extend(found.ravel().tolist())
                recovered.extend(quads(corners))
                found_at.append(i)
    return dict(
        direct_ids=direct_ids,
        direct_quads_px=quads(direct),
        rejected_quads_px=quads(rejected),
        recovered_ids=recovered_ids,
        recovered_quads_px=recovered,
        recovered_candidate_indices=found_at,
        exact_rejected_attempted=bool(rejected) and not direct_ids,
        observed_ids=direct_ids or recovered_ids,
    )


def shift_decodes(gray):
    out = []
    for dx, dy in SHIFTS:
        shifted = cv2.warpAffine(
            gray,
            np.float32([[1, 0, dx], [0, 1, dy]]),
            (gray.shape[1], gray.shape[0]),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        out.append(
            dict(
                dx_px=dx,
                dy_px=dy,
                grayscale_sha256=hashlib.sha256(shifted.tobytes()).hexdigest(),
                decode=decode(shifted),
            )
        )
    return out


def depth_patches(uv, depth):
    points = np.asarray(uv, dtype=float)
    patches = []
    for x, y in [*points, points.mean(axis=0)]:
        u, v = round(x), round(y)
        patch = depth[max(0, v - 1) : v + 2, max(0, u - 1) : u + 2]
        positive = np.isfinite(patch) & (patch > 0)
        patches.append(
            dict(
                pixel=[float(x), float(y)],
                sample_count=int(patch.size),
                positive_count=int(positive.sum()),
                median_positive_m=float(np.median(patch[positive])) if positive.any() else None,
            )
        )
    return patches


def geometry_fit(frame, geometry, detection):
    diagnostics = {}
    marker = detect_pose_marker(
        frame,
        PoseMarkerRegistration(**geometry["pose_marker"]),
        corner_refinement="SUBPIX",
        diagnostics=diagnostics,
    )
    require(
        list(marker.observed_marker_ids) == detection["observed_ids"],
        "decoder diagnostics differ from native measurement",
    )
    corners = detection["direct_quads_px"] or detection["recovered_quads_px"]
    pts = np.asarray(corners[0]) if len(corners) == 1 else None
    return dict(
        ordered_corners_px=None if pts is None else pts.tolist(),
        four_sides_px=None
        if pts is None
        else np.linalg.norm(pts - np.roll(pts, 1, axis=0), axis=1).tolist(),
        five_patches=[] if pts is None else depth_patches(pts, cam.depth(frame)),
        plane=diagnostics.get("plane"),
        measured_edge_lengths_m=marker.measured_edge_lengths_m,
        status=marker.status,
        reason=marker.reason,
    )


def make_shift_index(raw):
    cap = read(raw / "capture-seal.json")
    roles = pinned(raw / "roles.json", cap["roles_sha256"])["roles"]
    keys = [r["key"] for r in roles.values() if r["condition"] == "normal"]
    require(
        len(set(keys)) == len(keys) == 32 and len(roles) == 88, "wrong normal/hidden allocation"
    )
    write(
        raw / "pixels/shift-keys.json",
        dict(index_sha256=cap["index_sha256"], shifts=SHIFTS, keys=sorted(keys)),
    )


def blind(pixels, index_sha, shift_sha, output):
    index = pinned(pixels / "index.json", index_sha)
    shifts = pinned(pixels / "shift-keys.json", shift_sha)
    keys = set(shifts["keys"])
    require(
        shifts["index_sha256"] == index_sha
        and shifts["shifts"] == [list(d) for d in SHIFTS]
        and keys <= set(index["frames"])
        and len(keys) == 32,
        "foreign shift subset",
    )
    results = {}
    for key, row in sorted(index["frames"].items()):
        f = cam.load_frame(pixels, row)
        gray = cv2.cvtColor(cam.rgb(f), cv2.COLOR_RGB2GRAY)
        detected = decode(gray)
        fits = geometry_fit(f, next(iter(index["hypotheses"].values())), detected)
        results[key] = dict(
            frame_sha256=row["sha256"],
            frame_id=f.frame_id,
            checksum=f.checksum_sha256,
            by_mount={m: single.estimate(f, g) for m, g in index["hypotheses"].items()},
            detection=detected,
            depth_fit=fits,
            shifts=shift_decodes(gray) if key in keys else [],
        )
    write(
        output,
        dict(
            allocation_sha256=index["allocation_sha256"],
            index_sha256=index_sha,
            shift_keys_sha256=shift_sha,
            reader_source_sha256=sha(Path(__file__)),
            opencv_version=cv2.__version__,
            results=results,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    for mode in ("prepare", "seal"):
        sub.add_parser(mode).add_argument("raw", type=Path)
    p = sub.add_parser("blind")
    p.add_argument("pixels", type=Path)
    p.add_argument("index_sha")
    p.add_argument("shift_sha")
    p.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.mode == "prepare":
        make_shift_index(args.raw)
    elif args.mode == "blind":
        blind(args.pixels, args.index_sha, args.shift_sha, args.output)
    else:
        raw = args.raw
        cap = read(raw / "capture-seal.json")
        dec = read(raw / "blind-decisions.json")
        require(
            dec["index_sha256"] == cap["index_sha256"]
            and dec["allocation_sha256"] == cap["allocation_sha256"]
            and dec["shift_keys_sha256"] == sha(raw / "pixels/shift-keys.json")
            and len(dec["results"]) == 88,
            "foreign blind input",
        )
        write(
            raw / "decision-seal.json",
            dict(
                capture_sha256=sha(raw / "capture-seal.json"),
                decisions_sha256=sha(raw / "blind-decisions.json"),
                source_seal_sha256=sha(raw / "source-seal.json"),
                shift_keys_sha256=dec["shift_keys_sha256"],
            ),
        )


if __name__ == "__main__":
    main()
