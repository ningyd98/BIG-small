"""Inspect current-frame depth and the projection of the registered fixture."""

import argparse
import base64
import io
from itertools import product
from pathlib import Path
from xml.etree import ElementTree

import cv2
import numpy as np
from PIL import Image
from scripts.graduation.perception_io import pinned, sha, write

from cloud_edge_robot_arm.vision.observations import RGBDObservation

ROUND = Path(__file__).resolve().parent
PLAN_SHA = "5fa96d30fb48f1b673b24d32ddfbc7a7394f177f84b70dfd0680b5b0f326c4d5"
PRIVATE = Path("experiments/results/g1-visibility-pose-repair-20261124/batches")
BATCHES = {"115mm": "train-radial15-timing-01", "130mm": "train-radial30-contact-d02-02"}
NAMES = [
    "object_geom",
    *(f"g1_dual_id{i}_{part}" for i, part in product((7, 8), ("plate", "crossbar", "upright"))),
]
TOLERANCES_MM = (5, 20)


def camera_rays(frame):
    v, u = np.indices((frame.height, frame.width))
    fx, fy, cx, cy = frame.intrinsics
    optical = np.stack(((u - cx) / fx, (v - cy) / fy, np.ones_like(u)), axis=-1)
    transform = np.reshape(frame.camera_to_world, (4, 4))
    return transform[:3, 3], optical @ transform[:3, :3].T


def depth_stats(frame, depth, valid, origin, rays):
    points = origin + depth[valid, None] * rays[valid]
    valid_v, valid_u = np.nonzero(valid)
    for i in (0, len(points) // 2, len(points) - 1):
        pose = frame.world_point((int(valid_u[i]), int(valid_v[i])))
        np.testing.assert_allclose(points[i], [pose.x, pose.y, pose.z], atol=1e-10, rtol=0)
    jumps = []
    edge = np.zeros(depth.shape, dtype=np.uint8)
    for axis in (0, 1):
        both = np.diff(valid.astype(int), axis=axis) == 0
        valid_pairs = both & (valid[:-1, :] if axis == 0 else valid[:, :-1])
        diff = np.abs(np.diff(depth, axis=axis))
        jumps.append(diff[valid_pairs] * 1000)
        mask = valid_pairs & (diff > 0.020)
        if axis == 0:
            edge[:-1, :] |= mask
            edge[1:, :] |= mask
        else:
            edge[:, :-1] |= mask
            edge[:, 1:] |= mask
    groups, _, component_stats, _ = cv2.connectedComponentsWithStats(edge, connectivity=8)
    changes = np.concatenate(jumps)
    return dict(
        valid_points=int(valid.sum()),
        invalid_pixels=int(valid.size - valid.sum()),
        axial_depth_range_m=[float(depth[valid].min()), float(depth[valid].max())],
        world_bounds_m=[points.min(axis=0).tolist(), points.max(axis=0).tolist()],
        adjacent_pairs=len(changes),
        p50_p95_p99_adjacent_depth_jump_mm=np.percentile(changes, [50, 95, 99]).tolist(),
        adjacent_jumps_gt_5mm=int((changes > 5).sum()),
        adjacent_jumps_gt_20mm=int((changes > 20).sum()),
        whole_image_20mm_edge_components=groups - 1,
        largest_edge_component_pixels=int(component_stats[1:, cv2.CC_STAT_AREA].max())
        if groups > 1
        else 0,
    )


def registered_boxes(case):
    path = Path(case["geometry"]["asset_path"])
    assert (
        sha(path) == case["asset_sha256"] == case["geometry"]["pose_marker"]["marked_asset_sha256"]
    )
    body = ElementTree.parse(path).find(".//body[@name='object']")
    boxes = {}
    for name in NAMES:
        geom = body.find(f"geom[@name='{name}']")
        assert geom is not None and geom.get("type") == "box"
        assert not {"quat", "euler", "axisangle", "xyaxes", "zaxis", "fromto"} & geom.attrib.keys()
        center = np.fromstring(geom.get("pos", "0 0 0"), sep=" ")
        extent = np.fromstring(geom.attrib["size"], sep=" ")
        boxes[name] = (center - extent, center + extent)
    assert np.allclose(boxes["object_geom"][0] + boxes["object_geom"][1], 0)
    return boxes


def box_depth(origin, rays, bounds):
    """Nearest positive optical Z of an intersection with this object-coordinate box."""
    lo, hi = bounds
    parallel = np.abs(rays) < 1e-12
    outside = parallel & ((origin < lo) | (origin > hi))
    divisor = np.where(parallel, 1.0, rays)
    a, b = (lo - origin) / divisor, (hi - origin) / divisor
    enter = np.where(parallel, -np.inf, np.minimum(a, b)).max(axis=-1)
    leave = np.where(parallel, np.inf, np.maximum(a, b)).min(axis=-1)
    nearest = np.where(enter > 0, enter, leave)
    return np.where(
        (~outside.any(axis=-1)) & (leave >= np.maximum(0, enter)) & (nearest > 0), nearest, np.inf
    )


def classify(actual, predicted, valid, mask):
    residual = 1000 * (actual[mask & valid] - predicted[mask & valid])
    counts = {}
    for mm in TOLERANCES_MM:
        bins = dict(
            nearer=int((residual < -mm).sum()),
            consistent=int((np.abs(residual) <= mm).sum()),
            farther=int((residual > mm).sum()),
        )
        assert sum(bins.values()) == len(residual)
        counts[str(mm)] = bins
    return dict(
        pixels=int(mask.sum()),
        invalid=int((mask & ~valid).sum()),
        tolerance_mm=counts,
        p10_p50_p90_residual_mm=np.percentile(residual, [10, 50, 90]).tolist()
        if len(residual)
        else None,
    )


def register_camera(frame, depth, valid, origin, rays, pose, boxes):
    assert pose["frame_id"] == frame.frame_id and pose["checksum"] == frame.checksum_sha256
    assert pose["usable"] and pose["selected_id"] in pose["usable_ids"]
    rot = np.reshape(pose["rotation_object_to_world"], (3, 3))
    np.testing.assert_allclose(rot.T @ rot, np.eye(3), atol=1e-8, rtol=0)
    assert np.linalg.det(rot) > 0.999999
    local_origin = (origin - np.array(pose["object_center_world_m"])) @ rot
    local_rays = rays @ rot
    surfaces = {name: box_depth(local_origin, local_rays, box) for name, box in boxes.items()}
    front = np.minimum.reduce(list(surfaces.values()))
    result = {}
    for name, predicted in surfaces.items():
        if name == "object_geom":
            continue
        projected = np.isfinite(predicted)
        exposed = projected & (predicted <= front + 1e-9)
        interior = cv2.erode(
            exposed.astype(np.uint8),
            np.ones((3, 3), np.uint8),
            borderType=cv2.BORDER_CONSTANT,
            borderValue=0,
        ).astype(bool)
        result[name] = dict(
            all_projected=classify(depth, predicted, valid, projected),
            first_registered_surface=classify(depth, predicted, valid, exposed),
            interior=classify(depth, predicted, valid, interior),
            edge_pixels=int((exposed & ~interior).sum()),
        )
    return dict(usable_ids=pose["usable_ids"], selected_id=pose["selected_id"], objects=result)


def estimate():
    plan = pinned(ROUND / "plan.json", PLAN_SHA)

    def source(path):
        return pinned(path, plan["inputs_sha256"][path.as_posix()])

    result = {}
    for name, batch in BATCHES.items():
        case_dir = PRIVATE / batch / "d02"
        raw = case_dir / "instance"
        case = source(case_dir / "allocation.json")
        boxes = registered_boxes(case)
        frames = {r["file"]: r for r in source(raw / "pixel-index.json")["frames"]}
        measured = source(raw / "online-vision.json")["frames"]
        rows = []
        for selected in plan["frame_samples"][name]:
            row = frames[selected["file"]]
            assert (
                row["file_sha256"] == selected["file_sha256"]
                and row["physics_step"] == selected["step"]
            )
            frame = RGBDObservation.model_validate(pinned(raw / row["file"], row["file_sha256"]))
            assert (frame.frame_id, frame.checksum_sha256) == (
                selected["frame_id"],
                selected["checksum"],
            )
            rgb = np.asarray(Image.open(io.BytesIO(base64.b64decode(frame.rgb_png_base64))))
            assert rgb.shape == (240, 320, 3) and (frame.height, frame.width) == (240, 320)
            depth = np.frombuffer(base64.b64decode(frame.depth_float32_base64), "<f4").reshape(
                240, 320
            )
            valid = np.frombuffer(frame.valid_mask_bytes(), np.uint8).reshape(240, 320).astype(bool)
            assert np.array_equal(valid, np.isfinite(depth) & (depth > 0))
            origin, rays = camera_rays(frame)
            entry = dict(
                step=selected["step"],
                role=selected["role"],
                frame=row["file"],
                file_sha256=row["file_sha256"],
                direct=depth_stats(frame, depth, valid, origin, rays),
                model=None,
            )
            if selected["role"] == "APPROACH/feedback":
                pose = measured[frame.frame_id]["measurement"]
                assert pose["asset_sha256"] == case["asset_sha256"]
                entry["model"] = register_camera(frame, depth, valid, origin, rays, pose, boxes)
            else:
                assert selected["role"] == "terminal" and frame.frame_id not in measured
            rows.append(entry)
        result[name] = dict(batch=batch, asset_sha256=case["asset_sha256"], frames=rows)
    return dict(
        schema="g1.rgbd.current-frame-feasibility.v1",
        plan_sha256=PLAN_SHA,
        analysis_source_sha256=sha(Path(__file__)),
        camera_only_named_part_pair=None,
        time_aligned_measured_hand_boxes=None,
        tolerances_for_surface_association_mm=TOLERANCES_MM,
        headline_counts_use_first_registered_surface=True,
        alarm_rule=None,
        cases=result,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    write(args.output, estimate())
    print(sha(args.output))
