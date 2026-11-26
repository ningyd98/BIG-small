"""Estimate an offline dense pose from complete original tags outside the tested surfaces."""

import argparse
import base64
import gzip
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from xml.etree import ElementTree as ET

import cv2
import numpy as np
from scripts.graduation import g1_complete_cv_handoff_optics as optics
from scripts.graduation.g1_complete_cv_calibrate import axial
from scripts.graduation.g1_dual_observer import _decode, _measure_side
from scripts.graduation.perception_io import ROOT, read, sha, write

from cloud_edge_robot_arm.vision.observations import RGBDObservation

HERE = Path(__file__).resolve().parent
PLAN_PATH = HERE / "plan.json"
PLAN = read(PLAN_PATH)
OUT = ROOT / PLAN["output"]
DENSE = ROOT / PLAN["dense"]
NEEDLE = ROOT / PLAN["old_needle"]
OPTICAL = DENSE / "optical-input.json"
ASSET = ROOT / PLAN["asset"]
RESULTS = {"prediction.json", "prediction.cold.json"}
CORNERS = np.array([[i, j, k] for i in (-1, 1) for j in (-1, 1) for k in (-1, 1)])


def require(value, reason):
    if not value:
        raise ValueError(reason)


def checked(path, expected):
    return path.is_file() and sha(path) == expected


def snapshot_sources():
    optical = read(OPTICAL)
    index = read(DENSE / "native/index.json")
    dense_seal = read(DENSE / "native/seal.json")["members"]
    needle_seal = read(NEEDLE / "seal.json")["members"]
    require(
        checked(DENSE / "native/index.json", dense_seal["index.json"])
        and checked(NEEDLE / "index.json", needle_seal["index.json"])
        and index["optical_input_sha256"] == sha(OPTICAL),
        "frozen dense index differs",
    )
    live = {x["key"]: x for x in index["frames"]}
    require(len(live) == len(index["frames"]) == 10, "wrong dense archive coverage")
    controls = [
        x
        for x in read(NEEDLE / "index.json")["frames"]
        if (x["step"], x["scale"]) == (2112, PLAN["capture_scale"])
    ]
    require(
        len(controls) == 2 and {x["model"] for x in controls} == {"bare", "pin"},
        "needle optical control missing",
    )
    worlds = set()
    observations = []
    for job in optical["jobs"]:
        if job["key"] in live:
            dense = live[job["key"]]
            require(
                (dense["source_frame_id"], dense["source_checksum_sha256"], dense["source_time_s"])
                == (job["frame_id"], job["checksum_sha256"], job["time_s"]),
                "dense ordinary observation detached from the original",
            )
            path = DENSE / "native" / dense["file"]
            require(dense["file_sha256"] == dense_seal[dense["file"]], "dense record unbound")
            observations.append((job, dense, path, dense["dense_frame_id"]))
            worlds.add(job["key"])
        else:
            for item in controls:
                require(
                    (
                        item["original_frame_id"],
                        item["original_checksum_sha256"],
                        item["source_time_s"],
                    )
                    == (job["frame_id"], job["checksum_sha256"], job["time_s"])
                    and item["file_sha256"] == needle_seal[item["file"]],
                    "needle control detached from the original",
                )
                observations.append((job, item, NEEDLE / item["file"], item["frame_id"]))
            worlds.add(job["key"])
    require(len(worlds) == 11 and len(observations) == 12, "wrong optical job count")
    return optical["camera"], observations


def old_source_paths():
    mapping = {}
    for relative in PLAN["original_archives"].values():
        folder = ROOT / relative
        seal = read(folder / "seal.json")
        for case in seal["cases"]:
            path = folder / case / "rgbd-index.json"
            require(
                checked(path, seal["sealed_sha256"][f"{case}/rgbd-index.json"]),
                "unbound 320-packet index",
            )
            for rec in read(path)["rows"]:
                raw = folder / case / rec["file"]
                require(
                    rec["file_sha256"] == seal["sealed_sha256"][f"{case}/{rec['file']}"],
                    "unbound historical 320-packet hash",
                )
                key = rec["robot"]["frame_id"]
                require(key not in mapping, "reused frame id")
                mapping[key] = (raw, rec)
    return mapping


def activate_blind_read(allow, destination):
    raw = ROOT / "experiments/results"
    allow = set(allow) | {destination}

    def deny_raw(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).resolve()
            if path.is_relative_to(raw) and path not in allow:
                raise PermissionError(f"outside registered optical inputs: {path.name}")

    sys.addaudithook(deny_raw)
    denied = 0
    for p in (DENSE / "capture-input.json", ROOT / PLAN["original_truth_t02"]):
        try:
            p.read_bytes()
        except PermissionError:
            denied += 1
        else:
            raise ValueError("optical predictor opened a physical label")
    return denied


def mask_rect(mask, u0, v0, u1, v1):
    height, width = mask.shape
    require(u0 <= u1 and v0 <= v1, "invalid exclusion footprint")
    left, top, right, bottom = max(0, u0), max(0, v0), min(width, u1 + 1), min(height, v1 + 1)
    if left < right and top < bottom:
        mask[top:bottom, left:right] = True


def exclusions(job, meta):
    raw_xml = ET.parse(ASSET).getroot()
    obj = raw_xml.find("./worldbody/body[@name='object']")
    pose = job["optical"]
    rotation = np.array(pose["rotation"])
    anchor = np.array(pose["anchor_object_m"])
    error, basis = np.array(pose["anchor_error_object_m"]), np.array(pose["basis_error_object"])
    center = np.array(pose["center_m"])
    world = np.array(meta["camera_to_world"]).reshape(4, 4)
    fx, fy, cx, cy = meta["intrinsics"]
    mask = np.zeros((meta["height"], meta["width"]), dtype=bool)
    pad = PLAN["mask_padding_dense_px"]
    footprints = []
    for name in PLAN["excluded_geometry"]:
        geom = obj.find(f"geom[@name='{name}']")
        require(
            geom is not None
            and geom.get("type") == "box"
            and not (set(geom.attrib) & {"quat", "euler", "axisangle", "xyaxes", "zaxis"}),
            "unknown exclusion geometry poses",
        )
        local = np.fromstring(geom.get("pos", "0 0 0"), sep=" ")
        half = np.fromstring(geom.attrib["size"], sep=" ")
        bounds = half + error + basis @ (abs(local - anchor) + half)
        corners = center + (local + CORNERS * bounds) @ rotation.T
        view = (corners - world[:3, 3]) @ world[:3, :3]
        require((view[:, 2] > 0).all(), "exclusion behind camera")
        uv = view[:, :2] / view[:, 2, None] * [fx, fy] + [cx, cy]
        u0, v0 = (np.floor(uv.min(axis=0)) - pad).astype(int)
        u1, v1 = (np.ceil(uv.max(axis=0)) + pad).astype(int)
        mask_rect(mask, u0, v0, u1, v1)
        footprints.append({"geom": name, "bounds_uv": [[int(u0), int(v0)], [int(u1), int(v1)]]})
    scale = PLAN["capture_scale"]
    for u, v in job["pixels_original_uv"]:
        mask_rect(
            mask,
            scale * u - pad,
            scale * v - pad,
            scale * (u + 1) - 1 + pad,
            scale * (v + 1) - 1 + pad,
        )
    chunks = np.packbits(mask, axis=None).tobytes()
    import hashlib

    return mask, {
        "roi_geometry": footprints,
        "pixel_count": int(mask.sum()),
        "packed_mask_sha256": hashlib.sha256(chunks).hexdigest(),
    }


class DiagnosticFrame(SimpleNamespace):
    def model_dump(self, *, mode, include):
        require(mode == "json", "diagnostic metadata adapter cannot imply production binding")
        return {name: getattr(self, name) for name in include}


def marker_pose(gray, depth, frame, geometry, mask):
    # Both the coarse decoder and its subpixel refinement see a neutral hole.
    image = gray.copy()
    image[mask] = 127
    candidates, ambiguous, rejected = _decode(image)
    result = {"detected": [x["id"] for x in candidates], "rejected_candidates": rejected}
    ids = result["detected"]
    if ambiguous or sorted(ids) not in ([7], [8], [7, 8]):
        return result | {"reason": "missing_or_ambiguous_registered_tag"}
    marker = {
        "usable": True,
        "frame_id": frame.frame_id,
        "checksum": frame.checksum_sha256,
        "asset_sha256": geometry["pose_marker"]["marked_asset_sha256"],
        "registration_id": geometry["registration_id"],
        "observed_ids": ids,
        "usable_ids": ids,
        "by_id": {},
    }
    closure, planes = [], []
    for item in candidates:
        code = item["id"]
        if item["origins"] != ["direct"]:
            return result | {"reason": "not_a_complete_direct_tag", "marker": code}
        uv = item["corners"]
        samples = optics._pixels(uv, frame.width, frame.height)
        pad = PLAN["corner_neighborhood_px"]
        photometry_uv = []
        for u, v in np.rint(np.vstack((uv, uv.mean(axis=0)))).astype(int):
            if (
                u < pad
                or v < pad
                or u + pad >= frame.width
                or v + pad >= frame.height
                or mask[v - pad : v + pad + 1, u - pad : u + pad + 1].any()
            ):
                return result | {"reason": "corner_neighborhood_touches_exclusion", "marker": code}
            photometry_uv.append([int(u), int(v)])
        if samples is None or mask[samples[:, 1], samples[:, 0]].any():
            return result | {"reason": "depth_plane_touches_exclusion", "marker": code}
        side = _measure_side(frame, geometry, item, depth)
        if not side["usable"]:
            return result | {"reason": side["reason"], "marker": code}
        marker["by_id"][str(code)] = side
        z = depth[samples[:, 1], samples[:, 0]]
        points = optics._rays(samples, *frame.intrinsics) * z[:, None]
        planes.append(points)
        closure.append(
            {
                "marker_id": code,
                "corners_px": side["ordered_corners_px"],
                "depth_plane_sample_uv": samples.tolist(),
                "corner_and_center_bound_neighborhood_centers": photometry_uv,
                "corner_and_center_depth_radius_px": 1,
                "excluded_pixel_overlap": 0,
            }
        )
    xy = np.concatenate(planes, axis=0)
    design = np.column_stack((xy[:, :2] - xy[:, :2].mean(axis=0), np.ones(len(xy))))
    condition = np.linalg.svd(design, compute_uv=False)
    frame.depth_float32_base64 = base64.b64encode(depth.astype("<f4", copy=False).tobytes())
    with patch.object(optics, "_opposite_edges", return_value=None):
        pose = optics.measured_pose(frame, marker, geometry)
    if pose is None:
        return result | {"reason": "registered_print_plane_or_edge_failed"}
    return result | {
        "reason": None,
        "pose": pose,
        "samples": closure,
        "plane_design_singular_values": condition.tolist(),
    }


def diag_frame(frame_id, checksum, camera):
    return DiagnosticFrame(frame_id=frame_id, checksum_sha256=checksum, **camera)


def compare_320(path, packet, camera, geometry):
    require(checked(path, packet["file_sha256"]), "320 source optical frame differs")
    frame = RGBDObservation.model_validate_json(gzip.decompress(path.read_bytes()))
    require(
        frame.frame_id == packet["robot"]["frame_id"]
        and frame.checksum_sha256 == packet["robot"]["checksum_sha256"]
        and frame.model_dump(mode="json", include=set(camera)) == camera,
        "320 adapter cannot substitute for the original frame",
    )
    png = base64.b64decode(frame.rgb_png_base64)
    color = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
    dense_adapter = diag_frame(frame.frame_id, frame.checksum_sha256, camera)
    result = marker_pose(
        gray,
        axial(frame),
        dense_adapter,
        geometry | {"camera": camera},
        np.zeros_like(gray, dtype=bool),
    )
    if result["reason"] is not None:
        return result
    actual_marker = {
        "usable": True,
        "frame_id": frame.frame_id,
        "checksum": frame.checksum_sha256,
        "asset_sha256": geometry["pose_marker"]["marked_asset_sha256"],
        "registration_id": geometry["registration_id"],
        "observed_ids": result["detected"],
        "usable_ids": result["detected"],
        "by_id": {
            str(row["marker_id"]): {"ordered_corners_px": row["corners_px"]}
            for row in result["samples"]
        },
    }
    with patch.object(optics, "_opposite_edges", return_value=None):
        old_entry = optics.measured_pose(frame, actual_marker, geometry | {"camera": camera})
    require(old_entry == result["pose"], "original and diagnostic common-path pose differ")
    return {
        "detected": result["detected"],
        "reason": None,
        "uncertified_marker_only_pose": old_entry,
        "shared_native_measured_pose_identical": True,
    }


def optical_registration(meta, old):
    s = PLAN["capture_scale"]
    require(
        (meta["width"], meta["height"]) == (old["width"] * s, old["height"] * s)
        and meta["camera_to_world"] == old["camera_to_world"]
        and np.allclose(
            meta["intrinsics"],
            [
                old["intrinsics"][0] * s,
                old["intrinsics"][1] * s,
                (meta["width"] - 1) / 2,
                (meta["height"] - 1) / 2,
            ],
            rtol=0,
            atol=1e-12,
        ),
        "dense image does not share registered optical center",
    )
    return {key: meta[key] if key in meta else old[key] for key in old}


def fit_dense(job, meta, path, frame_id, camera, geometry):
    require(checked(path, meta["file_sha256"]), "dense native bytes differ")
    new = optical_registration(meta, camera)
    with np.load(path, allow_pickle=False) as f:
        rgb, z, valid = (f[k] for k in ("rgb", "depth_m", "valid"))
    require(
        rgb.shape == (new["height"], new["width"], 3)
        and z.shape == valid.shape == rgb.shape[:2]
        and rgb.dtype == np.uint8
        and z.dtype == np.dtype("<f4")
        and np.isfinite(z).all()
        and np.array_equal(z > 0, valid.astype(bool)),
        "dense native validity or depth format differs",
    )
    mask, record = exclusions(job, new)
    frame = diag_frame(frame_id, meta["file_sha256"], new)
    fit = marker_pose(
        cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), z, frame, geometry | {"camera": new}, mask
    )
    return fit | {
        "key": job["key"],
        "dense_frame_id": frame_id,
        "dense_raw_sha256": meta["file_sha256"],
        "original_frame_id": job["frame_id"],
        "original_checksum_sha256": job["checksum_sha256"],
        "exclusions": record,
    }


def run(path):
    read_allow = {
        OPTICAL,
        DENSE / "native/index.json",
        DENSE / "native/seal.json",
        NEEDLE / "index.json",
        NEEDLE / "seal.json",
        ASSET,
        ROOT / PLAN["original_allocation"],
    }
    for root in PLAN["original_archives"].values():
        source = ROOT / root
        read_allow.add(source / "seal.json")
        require(
            checked(source / "seal.json", PLAN["sha256"][f"{root}/seal.json"]),
            "unbound original aperture archive",
        )
    for p in read_allow:
        relative = p.relative_to(ROOT).as_posix()
        if relative in PLAN["sha256"]:
            require(checked(p, PLAN["sha256"][relative]), f"old optical source differs: {p.name}")
    camera, specs = snapshot_sources()
    old_cases = old_source_paths()
    for job, _meta, dense, _ in specs:
        read_allow.add(dense)
        if job["frame_id"] in old_cases:
            read_allow.add(old_cases[job["frame_id"]][0])
    blind = activate_blind_read(read_allow, path)
    require(blind == 2, "blind prediction controls missing")
    allocation = read(ROOT / PLAN["original_allocation"])
    geometry = allocation["geometry"]
    require(
        geometry["camera"] == camera, "dense source must be rooted in original 320 registration"
    )
    cv2.setNumThreads(1)
    standard = {}
    for job, _, _, _ in specs:
        key = job["key"]
        if key not in standard and job["frame_id"] in old_cases:
            raw, packet = old_cases[job["frame_id"]]
            standard[key] = compare_320(raw, packet, camera, geometry)
    dense = [
        fit_dense(job, meta, raw, frame_id, camera, geometry) for job, meta, raw, frame_id in specs
    ]
    require(len(standard) == 10 and len(dense) == 12, "original shape or density budget changed")
    write(
        path,
        {
            "plan_sha256": sha(PLAN_PATH),
            "prediction_source_sha256": sha(Path(__file__)),
            "optical_input_sha256": sha(OPTICAL),
            "blocked_file_accesses": blind,
            "standard_path_controls": standard,
            "dense": dense,
            "scope": PLAN["scope"],
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", choices=sorted(RESULTS))
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    run(OUT / args.output)
