"""在固定彩色方块范围内，将背景或边缘点关联到唯一完整可见支撑。"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.tracking import _rgb

_HUE_BOUNDS = {
    "red": ((0, 10), (170, 179)),
    "green": ((35, 85),),
    "blue": ((100, 130),),
    "yellow": ((20, 34),),
}
_DESCRIPTOR = re.compile(r"(red|green|blue|yellow) (block|box|cube)", re.IGNORECASE)


@dataclass(frozen=True)
class PointAssociation:
    """记录几何采样点及其来源，不将局部关联冒充原生模型预测。"""

    pixel: tuple[int, int]
    evidence: dict[str, object]


class PointAssociationError(ValueError):
    """保留拒绝关联时的候选区域和原生点证据。"""

    def __init__(self, reason: str, evidence: dict[str, object]) -> None:
        self.evidence = evidence
        super().__init__(reason)


def associate_target_point(
    observation: RGBDObservation,
    native_pixel: tuple[int, int],
    *,
    target_phrase: str,
) -> PointAssociation:
    """只关联局部唯一完整颜色区域；后续深度与跟踪门保持独立有效。"""
    source = observation.evidence()
    evidence: dict[str, object] = {
        "schema": "bounded_local_component.v1",
        "status": "REJECTED",
        "observation_checksum": observation.checksum_sha256,
        "rgb_sha256": source["rgb_sha256"],
        "depth_sha256": source["depth_sha256"],
        "native_pixel": list(native_pixel),
        "selected_pixel": None,
        "helper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "candidate_count": 0,
        "candidates": [],
        "policy": {
            "radius_fraction": 0.08,
            "minimum_radius_px": 8,
            "maximum_radius_px": 24,
            "minimum_area_px": 8,
            "chroma_direct_ge": 35,
            "chroma_nomination_gt": 35,
            "minimum_interior_distance_px": 2,
            "hue_bounds": _HUE_BOUNDS,
        },
    }

    def reject(reason: str) -> None:
        evidence["reason"] = reason
        raise PointAssociationError(reason, evidence)

    if len(native_pixel) != 2 or any(type(value) is not int for value in native_pixel):
        reject("native association pixel must contain two integers")
    u, v = native_pixel
    if not (0 <= u < observation.width and 0 <= v < observation.height):
        reject("native association pixel is outside image")
    depth = np.asarray(observation.depth_values()).reshape(observation.height, observation.width)
    valid = np.frombuffer(observation.valid_mask_bytes(), dtype=np.uint8).reshape(depth.shape)
    if not (valid[v, u] > 0 and np.isfinite(depth[v, u]) and depth[v, u] > 0):
        reject("native association pixel has invalid original depth")
    evidence["native_world_sample"] = observation.world_point(native_pixel).model_dump()
    rgb = _rgb(observation)
    chroma = np.ptp(rgb, axis=2)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    match = _DESCRIPTOR.fullmatch(target_phrase.strip())
    color = match.group(1).lower() if match else None
    evidence["descriptor_color"] = color

    def hue_matches(values: np.ndarray) -> np.ndarray:
        return np.logical_or.reduce(
            [(values >= lower) & (values <= upper) for lower, upper in _HUE_BOUNDS[color]]
        )

    native_colored = int(chroma[v, u]) >= 35
    if native_colored:
        if color is not None and not bool(hue_matches(hsv[v, u, 0:1])[0]):
            reject("native colored pixel contradicts explicit descriptor color")
        if color is not None:
            # RGB alone decides whether to relocate; invalid/nonflat depth must
            # still reject downstream instead of initiating another search.
            evidence["native_rgb_patch_complete"] = bool(
                1 <= u < observation.width - 1
                and 1 <= v < observation.height - 1
                and np.all(chroma[v - 1 : v + 2, u - 1 : u + 2] >= 35)
                and np.all(hue_matches(hsv[v - 1 : v + 2, u - 1 : u + 2, 0]))
            )
        if color is None or evidence["native_rgb_patch_complete"]:
            evidence.update(
                status="UNCHANGED",
                selected_pixel=[u, v],
                selected_source="NATIVE_POINT",
                selected_rgb=rgb[v, u].tolist(),
                selected_hsv=hsv[v, u].tolist(),
                displacement_px=0.0,
                descriptor_color_status="MATCHED" if color else "UNSUPPORTED_DIRECT_UNCHANGED",
            )
            return PointAssociation(native_pixel, evidence)
    if color is None:
        reject("background association requires explicit supported color/object descriptor")
    evidence["association_trigger"] = (
        "NATIVE_COLORED_BOUNDARY" if native_colored else "NEAR_BACKGROUND"
    )

    radius = min(24, max(8, round(0.08 * min(observation.width, observation.height))))
    left, top, right, bottom = u - radius, v - radius, u + radius, v + radius
    evidence.update(radius_px=radius, window_xyxy=[left, top, right, bottom])
    mask = (chroma > 35).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    candidates = []
    rows = []
    for index in range(1, count):
        if stats[index, cv2.CC_STAT_AREA] < 8:
            continue
        ys, xs = np.nonzero(labels == index)
        distance_sq = (xs - u) ** 2 + (ys - v) ** 2
        if int(distance_sq.min()) > radius**2:
            continue
        candidates.append(index)
        rows.append(
            {
                "bbox_xywh": stats[index, :4].tolist(),
                "area_px": int(stats[index, cv2.CC_STAT_AREA]),
                "minimum_distance_px": math.sqrt(int(distance_sq.min())),
            }
        )
    evidence.update(candidate_count=len(candidates), candidates=rows)
    if len(candidates) != 1:
        reject("background association requires exactly one local component")
    if left < 0 or top < 0 or right >= observation.width or bottom >= observation.height:
        reject("association window is truncated by image boundary")
    index = candidates[0]
    if native_colored and (labels[v, u] == 0 or labels[v, u] != index):
        reject("colored boundary association must retain its native component")
    x, y, width, height, area = (int(value) for value in stats[index])
    if not (
        left < x
        and top < y
        and x + width - 1 < right
        and y + height - 1 < bottom
        and 0 < x
        and 0 < y
        and x + width - 1 < observation.width - 1
        and y + height - 1 < observation.height - 1
    ):
        reject("local component crosses association window or image boundary")
    component = labels == index
    evidence.update(
        component_area_px=area,
        component_mask_sha256=hashlib.sha256(component.astype(np.uint8).tobytes()).hexdigest(),
    )
    if not bool(np.all(hue_matches(hsv[:, :, 0][component]))):
        reject("local component contradicts explicit descriptor color")
    evidence["descriptor_color_status"] = "MATCHED"
    if not bool(
        np.all((valid[component] > 0) & np.isfinite(depth[component]) & (depth[component] > 0))
    ):
        invalid = (valid == 0) | ~np.isfinite(depth) | (depth <= 0)
        interior = cv2.erode(component.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        invalid_component = invalid & component
        exterior = cv2.dilate(component.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        exterior &= ~component
        adjacent = cv2.dilate(invalid_component.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        exterior_invalid = adjacent & exterior & invalid
        interior_count = int(np.count_nonzero(invalid_component & interior))
        evidence["invalid_depth_diagnosis"] = {
            "classification": "INTERIOR_INVALID_DEPTH"
            if interior_count
            else (
                "BOUNDARY_ADJACENT_INVALID_BACKGROUND"
                if exterior_invalid.any()
                else "BOUNDARY_INVALID_DEPTH"
            ),
            "invalid_component_pixels": int(invalid_component.sum()),
            "invalid_interior_pixels": interior_count,
            "adjacent_invalid_exterior_pixels": int(exterior_invalid.sum()),
            "physical_occluder_identity": "UNKNOWN",
            "original_depth_preserved": True,
        }
        reject("local component has invalid original depth")
    distances = cv2.distanceTransform(
        component.astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE
    )
    maximum = float(distances.max())
    ys, xs = np.nonzero(distances == maximum)
    ordering = np.lexsort((xs, ys, (xs - u) ** 2 + (ys - v) ** 2))
    sx, sy = int(xs[ordering[0]]), int(ys[ordering[0]])
    displacement = math.hypot(sx - u, sy - v)
    evidence.update(interior_distance_px=maximum, displacement_px=displacement)
    if (
        maximum < 2
        or displacement > radius
        or not bool(component[sy - 1 : sy + 2, sx - 1 : sx + 2].all())
    ):
        reject("associated pixel lacks complete bounded 3x3 interior")
    evidence.update(
        status="ASSOCIATED",
        selected_pixel=[sx, sy],
        selected_source="RGB_LOCAL_COMPONENT_ASSOCIATION",
        selected_rgb=rgb[sy, sx].tolist(),
        selected_hsv=hsv[sy, sx].tolist(),
    )
    return PointAssociation((sx, sy), evidence)
