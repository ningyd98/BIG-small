"""Independently decode frozen diagnostic packets and exercise explicit depth dropouts."""

import argparse
import base64
import gzip
import io
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scripts.graduation import g1_dual_asset as asset
from scripts.graduation import g1_visibility_grid as grid
from scripts.graduation.g1_dual_observer import measure_frame
from scripts.graduation.perception_io import sha, write

from cloud_edge_robot_arm.research.native_collection_grounding import collection_bootstrap_evidence
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.servo_region import measure_servo_region
from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker


def packet(path):
    return RGBDObservation.model_validate_json(gzip.decompress(path.read_bytes()))


def geometry_only_reference(frame, geometry):
    """Replicate initial pixel geometry without making a claim about an unrecorded lease clock."""
    evidence = collection_bootstrap_evidence(frame, geometry)
    tracker = OpenCVTargetTracker.__new__(OpenCVTargetTracker)
    tracker._configure_initial_geometry(frame, evidence)
    tracker._acquire_initial_geometry(frame)
    return tracker


def helper_result(cap, geometry):
    records = []
    for row in json.loads((cap / "summary.json").read_bytes())["rows"]:
        label = row["role"]
        path = cap / (label + ".rgbd.json.gz")
        if sha(path) != row["raw_sha256"]:
            raise ValueError("optics input hash differs")
        obs = packet(path)
        live = measure_frame(obs, geometry)
        if not live["usable"]:
            raise ValueError("real frozen current marker unavailable: " + label)
        initial = cap / (label + ".bootstrap.json.gz")
        region_ok, region_reason = None, "corresponding original reference not retained"
        if initial.is_file():
            ref = geometry_only_reference(packet(initial), geometry)
            region, region_reason = measure_servo_region(obs, ref)
            region_ok = region is not None
            if not region_ok:
                raise ValueError("real frozen region unavailable: " + str(region_reason))
        records.append(
            dict(
                role=label,
                rgbd_sha256=sha(path),
                reference_sha256=sha(initial) if initial.is_file() else None,
                previous_ids=row["observed_ids"],
                previous_reason=row["marker_reason"],
                ids=live["observed_ids"],
                selected=live["selected_id"],
                previous_region_reason=row["destination_reason"],
                region_ok=region_ok,
                region_reason=region_reason,
                discarded=live["rejected_nonphysical_grids"],
            )
        )
    return records


def with_dropout(frame, uv):
    data = frame.model_dump()
    depth = (
        np.frombuffer(base64.b64decode(frame.depth_float32_base64), "<f4")
        .copy()
        .reshape(frame.height, frame.width)
    )
    depth[uv[:, 1], uv[:, 0]] = 0
    data.update(
        depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
        valid_mask_base64=None,
        checksum_sha256="",
    )
    return RGBDObservation.model_validate(data)


def dropout_controls(cap, geometry):
    original = packet(cap / "over-region-held.rgbd.json.gz")
    initial = packet(cap / "over-region-held.bootstrap.json.gz")
    ref = geometry_only_reference(initial, geometry)
    old = json.loads((cap / "summary.json").read_bytes())
    miss = next(r for r in old["rows"] if r["role"] == "over-region-held")[
        "unexplained_destination_pixels"
    ]
    changed = with_dropout(original, np.asarray([m["pixel_xy"] for m in miss]))
    region, why = measure_servo_region(changed, ref)
    if region is not None:
        raise ValueError("missing green-plane ray accepted")
    samples = [
        {
            "name": "missing_green_ray",
            "checksum": changed.checksum_sha256,
            "reason": why,
            "removed": len(miss),
        }
    ]
    rgb = np.asarray(Image.open(io.BytesIO(base64.b64decode(original.rgb_png_base64))))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    z = np.frombuffer(base64.b64decode(original.depth_float32_base64), "<f4").reshape(gray.shape)
    candidates = grid.find_grids(gray, z, np.sqrt(np.prod(original.intrinsics[:2])), 0.075)[0]
    dark = [c for c in candidates if c["origins"] == ["internal_white_component"]]
    if not dark:
        raise ValueError("expected original optical contradiction")
    candidate = dark[0]
    # One actual cell on the outer black frame of an island candidate loses its depth.
    uv = np.rint(grid.CELLS[:1] @ candidate["basis"] + candidate["center"]).astype(int)
    changed = with_dropout(original, uv)
    measured = measure_frame(changed, geometry)
    if measured["usable"]:
        raise ValueError("incomplete foreign-grid depth contradiction accepted")
    samples.append(
        dict(
            name="incomplete_false_grid_witness",
            checksum=changed.checksum_sha256,
            reason=measured["reason"],
            ids=measured["observed_ids"],
            removed=len(uv),
        )
    )
    single = packet(cap / "lift-with-hold.rgbd.json.gz")
    initial_mark = measure_frame(single, geometry)
    outline = np.array(
        next(c for c in initial_mark["candidates"] if c["id"] == initial_mark["selected_id"])[
            "ordered_corners_px"
        ]
    )
    left, top = np.floor(outline.min(axis=0)).astype(int)
    right, bottom = np.ceil(outline.max(axis=0)).astype(int)
    uv = np.mgrid[left : right + 1, top : bottom + 1].reshape(2, -1).T
    changed = with_dropout(single, uv)
    measured = measure_frame(changed, geometry)
    if measured["usable"]:
        raise ValueError("visible tag without current depth supplied a 3D grasp")
    samples.append(
        dict(
            name="single_visible_print_no_depth",
            checksum=changed.checksum_sha256,
            reason=measured["reason"],
            ids=measured["observed_ids"],
            removed=len(uv),
        )
    )
    return samples


def summary(path, geometry):
    variants = {}
    for variant, record in json.loads((path / "summary.json").read_bytes()).items():
        if sha(path / variant / "scene.xml") != record["scene_sha256"]:
            raise ValueError("diagnostic physical source differs")
        rows = []
        for r in record["rows"]:
            src = path / variant / (r["role"] + ".rgbd.json.gz")
            if sha(src) != r["raw_sha256"]:
                raise ValueError("diagnostic packet differs")
            decoded = measure_frame(packet(src), geometry)
            if decoded["usable"] != r["usable"] or decoded["observed_ids"] != r["measured_ids"]:
                raise ValueError("independent cold optics differs")
            rows.append(
                {
                    k: r[k]
                    for k in (
                        "role",
                        "measured_ids",
                        "usable",
                        "marker_reason",
                        "marker_tcp_error_mm",
                        "destination_ok",
                        "destination_reason",
                        "camera_and_both_estimators_ms",
                        "raw_sha256",
                        "renderer",
                    )
                }
            )
        if variant in {"original", "dark-region"}:
            if not all(rr["usable"] and rr["destination_ok"] for rr in rows):
                raise ValueError("accepted fixture regression")
        elif "foreign" in variant or variant == "shifted-print-on-wing":
            if any(rr["usable"] for rr in rows):
                raise ValueError("foreign/conflicting physical identity accepted")
        elif any(rr["destination_ok"] for rr in rows):
            raise ValueError("unregistered region accepted")
        variants[variant] = dict(scene_sha256=record["scene_sha256"], rows=rows)
    return variants


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original_root", type=Path)
    parser.add_argument("gpu_detailed", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("qualification", nargs="+", type=Path)
    args = parser.parse_args()
    geo = asset.geometry_descriptor()
    original = {
        c.name: helper_result(c, geo)
        for c in (args.original_root / "capture", args.original_root / "capture-gpu")
    }
    detailed = helper_result(args.gpu_detailed, geo)
    controls = dropout_controls(args.gpu_detailed, geo)
    rows = {p.name: summary(p, geo) for p in args.qualification}
    write(
        args.out,
        dict(
            original=original,
            original_gpu_with_reference=detailed,
            depth_dropout=controls,
            tested_physical_fixtures=rows,
            formal_runs=0,
            skill_dispatches=0,
            diagnostic_scope="frozen and rendered RGB-D with current-frame geometric measurements",
        ),
    )
