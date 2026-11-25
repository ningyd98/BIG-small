"""Read archived pre-descent RGB-D in two passes. All dimensions are in metres."""

import argparse
import base64
import math
from pathlib import Path
from xml.etree import ElementTree

import cv2
import numpy as np
from scripts.graduation.perception_io import pinned, sha, write

from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.point_association import _HUE_BOUNDS
from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker, _rgb

ROUND = Path(__file__).resolve().parent
PLAN_SHA = "a9d0e2f6f334ae6faeca4039b4580fe7fde30c20a2424c881c8cd554c170c4c4"


def fit_surface(frame, component, depth, valid, expected_sides, band):
    interior = cv2.erode(
        component.astype(np.uint8),
        np.ones((3, 3), np.uint8),
        borderType=cv2.BORDER_CONSTANT,
        borderValue=0,
    ).astype(bool)
    y, x = np.nonzero(component & valid)
    core = interior[y, x]
    stats = dict(
        area_px=int(component.sum()),
        interior_depth_px=int(core.sum()),
        plane_inliers=0,
        accepted=False,
    )
    if core.sum() < 8:
        return stats | {"reason": "insufficient_interior_depth"}
    points = OpenCVTargetTracker._points(frame, x, y, depth[y, x].astype(float))
    top = points[np.abs(points[:, 2] - np.median(points[core, 2])) <= band]
    stats["plane_inliers"] = len(top)
    if len(top) < 8:
        return stats | {"reason": "insufficient_plane_support"}
    xy = top[:, :2]
    origin = xy.mean(axis=0)
    design = np.column_stack((xy - origin, np.ones(len(xy))))
    fit, _, rank, _ = np.linalg.lstsq(design, top[:, 2], rcond=None)
    if rank != 3:
        return stats | {"reason": "degenerate_xy"}
    tilt = math.degrees(math.atan(np.linalg.norm(fit[:2])))
    rms = float(np.sqrt(np.mean((design @ fit - top[:, 2]) ** 2)))
    center, size, _ = cv2.minAreaRect(xy.astype(np.float32))
    stats.update(tilt_deg=tilt, vertical_rms_m=rms, rectangle_sides_m=sorted(size))
    if tilt > 10 or rms > 0.004:
        return stats | {"reason": "unsupported_plane"}
    if np.any(np.abs(np.sort(size) / np.sort(expected_sides) - 1) > 0.15):
        return stats | {"reason": "unsupported_extent"}
    height = float(fit[:2] @ (center - origin) + fit[2])
    return stats | {"accepted": True, "center_m": [*center, height]}


def color_surface(frame, rgb, depth, valid, expected_sides, band):
    hue = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)[:, :, 0]
    red = np.logical_or.reduce([(lo <= hue) & (hue <= hi) for lo, hi in _HUE_BOUNDS["red"]])
    mask = (red & (np.ptp(rgb, axis=2) >= 35)).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    # Components with fewer than 8 pixels cannot satisfy the interior support rule.
    candidates = [
        fit_surface(frame, labels == i, depth, valid, expected_sides, band)
        for i in range(1, count)
        if stats[i, cv2.CC_STAT_AREA] >= 8
    ]
    accepted = [c["center_m"] for c in candidates if c["accepted"]]
    return dict(
        component_count=count - 1,
        candidates=candidates,
        status="SUPPORTED" if len(accepted) == 1 else "UNKNOWN",
        reason=(
            "unique_surface"
            if len(accepted) == 1
            else "multiple_qualifying_surfaces"
            if accepted
            else "no_qualifying_surface"
        ),
        top_center_m=accepted[0] if len(accepted) == 1 else None,
    )


def packets(plan):
    for sample in plan["planning_inputs"]:
        file = Path(sample["file"])
        pins = plan["inputs_sha256"]
        bound = pinned(Path(sample["registration_file"]), pins[sample["registration_file"]])
        index_path = file.parent.parent / "pixel-index.json"
        index = pinned(index_path, pins[str(index_path)])
        (entry,) = (e for e in index["frames"] if e["frame_id"] == sample["frame_id"])
        assert file == index_path.parent / entry["file"] and entry["file_sha256"] == pins[str(file)]
        assert (entry["label"], entry["physics_step"]) == (sample["role"], sample["step"])
        frame = RGBDObservation.model_validate(pinned(file, pins[str(file)]))
        assert (frame.frame_id, frame.checksum_sha256) == (
            entry["frame_id"],
            sample["payload_sha256"],
        )
        assert frame.checksum_sha256 == entry["checksum_sha256"]
        geometry = bound["geometry"]
        assert (frame.episode_id, frame.scene_id) == (index["episode"], index["scene"])
        assert bound["asset_sha256"] == pins[sample["assembly_xml"]]
        yield sample, frame, geometry


def estimate(plan):
    rows = []
    for sample, frame, geometry in packets(plan):
        calibrated = (
            frame.model_dump(mode="json", include=set(geometry["camera"])) == geometry["camera"]
        )
        if calibrated:
            shape = (frame.height, frame.width)
            depth = np.frombuffer(base64.b64decode(frame.depth_float32_base64), "<f4").reshape(
                shape
            )
            valid = np.frombuffer(frame.valid_mask_bytes(), np.uint8).reshape(shape).astype(bool)
            valid &= np.isfinite(depth) & (depth > 0)
            band = min(0.004, geometry.get("depth_error_bound_m") or 0.004)
            surface = color_surface(
                frame,
                _rgb(frame),
                depth,
                valid,
                2 * np.asarray(geometry["object_half_extent_m"][:2]),
                band,
            )
        else:
            surface = dict(status="UNKNOWN", reason="invalid_calibration", top_center_m=None)
        rows.append(
            dict(
                frame_id=frame.frame_id,
                checksum=frame.checksum_sha256,
                captured_at=frame.captured_at.isoformat(),
                sim_time_s=frame.sim_time_s,
                phase=sample["role"],
                step=sample["step"],
                surface=surface,
            )
        )
    return dict(plan_sha256=PLAN_SHA, source_sha256=sha(Path(__file__)), frames=rows)


def aperture(path, expected_hash):
    if sha(path) != expected_hash:
        raise ValueError("registered assembly XML differs")
    root = ElementTree.parse(path)
    hand = root.find(".//body[@name='panda_hand']")
    edges = []
    for finger, sign in (("left_finger", 1), ("right_finger", -1)):
        body = hand.find(f"body[@name='{finger}']")
        joint = body.find("joint")
        geom = body.find(f"geom[@name='{finger}_geom']")
        axis = np.fromstring(joint.attrib["axis"], sep=" ")
        assert joint.get("type") == "slide" and np.array_equal(axis, [0, sign, 0])
        assert geom.get("type") == "box"
        for element in (body, geom):
            assert (
                not {"quat", "euler", "axisangle", "xyaxes", "zaxis", "fromto"}
                & element.attrib.keys()
            )
        upper = max(map(float, joint.get("range").split()))
        opened_y = (
            float(body.get("pos").split()[1]) + float(geom.get("pos").split()[1]) + sign * upper
        )
        edges.append(opened_y - sign * float(geom.get("size").split()[1]))
    target = root.find(".//geom[@name='object_geom']")
    assert target.get("type") == "box"
    a, b = (2 * float(s) for s in target.get("size").split()[:2])
    return a, b, edges[0] - edges[1]


def width_check(a, b, gap):
    diagonal, phi = math.hypot(a, b), math.degrees(math.atan2(b, a))
    if gap >= diagonal:
        intervals = [[0.0, 90.0]]
    else:
        delta = math.degrees(math.acos(gap / diagonal))
        intervals = [[lo, hi] for lo, hi in [(0.0, phi - delta), (phi + delta, 90.0)] if lo <= hi]
    values = []
    for deg in range(91):
        theta = math.radians(deg)
        needed = a * abs(math.cos(theta)) + b * abs(math.sin(theta))
        values.append(
            dict(angle_deg=deg, required_mm=needed * 1000, remaining_mm=(gap - needed) * 1000)
        )
    return dict(
        opening_mm=gap * 1000,
        target_sides_mm=[a * 1000, b * 1000],
        allowed_by_width_deg_inclusive=intervals,
        sweep=values,
    )


def compare(plan, seal_path, seal_sha):
    from scripts.graduation import g1_visibility_grid, g1_visibility_replay, g1_visibility_vision

    for module in (g1_visibility_grid, g1_visibility_replay, g1_visibility_vision):
        source = Path(module.__file__)
        pins = {v for k, v in plan["inputs_sha256"].items() if Path(k).name == source.name}
        assert pins == {sha(source)}
    sealed = pinned(seal_path, seal_sha)
    assert sealed["source_sha256"] == sha(Path(__file__)) and sealed["plan_sha256"] == PLAN_SHA
    rows, assemblies, dimensions = [], {}, set()
    for color, (sample, frame, geometry) in zip(sealed["frames"], packets(plan), strict=True):
        assert (color["frame_id"], color["checksum"]) == (frame.frame_id, frame.checksum_sha256)
        marker = g1_visibility_replay.measure(frame, geometry)
        row = dict(
            frame_id=frame.frame_id,
            frame=sample["file"],
            phase=sample["role"],
            step=sample["step"],
            color_status=color["surface"]["status"],
            color_reason=color["surface"]["reason"],
            color_center_m=color["surface"]["top_center_m"],
            marker_usable=marker["usable"],
            marker_reason=marker["reason"],
            marker_id=marker["selected_id"],
            marker_center_m=marker["top_m"],
            delta_color_minus_marker_mm=None,
            distance_mm=None,
            within_10mm=None,
        )
        if row["color_center_m"] is not None and marker["usable"]:
            delta = 1000 * np.subtract(row["color_center_m"], row["marker_center_m"])
            row.update(
                delta_color_minus_marker_mm=delta.tolist(),
                distance_mm=float(np.linalg.norm(delta)),
                within_10mm=bool(np.linalg.norm(delta) <= 10),
            )
        rows.append(row)
        key = sample["assembly_xml"]
        if key not in assemblies:
            sizes = aperture(Path(key), plan["inputs_sha256"][key])
            assemblies[key] = dict(
                asset_sha256=plan["inputs_sha256"][key], dimensions_m=list(sizes)
            )
            dimensions.add(sizes)
    distances = [r["distance_mm"] for r in rows if r["distance_mm"] is not None]
    summary = dict(
        frames=len(rows),
        color_supported=sum(bool(r["color_center_m"]) for r in rows),
        marker_supported=sum(r["marker_usable"] for r in rows),
        paired=len(distances),
        within_10mm=sum(d <= 10 for d in distances),
        median_mm=float(np.median(distances)) if distances else None,
        max_mm=max(distances, default=None),
    )
    return dict(
        plan_sha256=PLAN_SHA,
        color_seal_sha256=seal_sha,
        frames=rows,
        summary=summary,
        assemblies=assemblies,
        aperture_profiles=[width_check(*s) for s in sorted(dimensions)],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("surface").add_argument("output", type=Path)
    sub = modes.add_parser("compare")
    sub.add_argument("surface", type=Path)
    sub.add_argument("seal")
    sub.add_argument("output", type=Path)
    args = parser.parse_args()
    spec = pinned(ROUND / "plan.json", PLAN_SHA)
    result = estimate(spec) if args.mode == "surface" else compare(spec, args.surface, args.seal)
    write(args.output, result)
    print(sha(args.output))
