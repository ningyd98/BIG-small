"""Simulator truth is consumed only by offline labels, never online observations."""

from __future__ import annotations

from typing import Any

import numpy as np

from cloud_edge_robot_arm.vision.capture import CapturedFrame


def label_frame(frame: CapturedFrame, truth: dict[str, Any]) -> dict[str, Any]:
    observation = frame.observation
    ids = np.asarray(frame.instance_ids).reshape(observation.height, observation.width)
    valid = np.frombuffer(observation.valid_mask_bytes(), dtype=np.uint8).reshape(ids.shape) > 0
    instances = []
    chosen = {}
    for obj in truth["instances"]:
        mask = np.isin(ids, obj["geom_ids"])
        ys, xs = np.where(mask)
        count = len(xs)
        bbox = ([int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
                if count else None)
        useful = mask & valid
        vy, vx = np.where(useful)
        pixel = None
        if len(vx):
            # A visible, valid pixel nearest the visible centroid cannot fall into an occluder.
            index = int(np.argmin((vx - xs.mean()) ** 2 + (vy - ys.mean()) ** 2))
            pixel = [int(vx[index]), int(vy[index])]
        chosen[obj["semantic_id"]] = pixel
        instances.append({**obj, "bbox_xyxy": bbox, "visible_pixels": count,
                          "valid_depth_fraction": float(len(vx) / count) if count else 0.})
    target = next(obj for obj in instances if obj["role"] == "target")
    destination = next(obj for obj in instances if obj["role"] == "destination")
    reasons = []
    if target["visible_pixels"] < 100:
        reasons.append("TARGET_TOO_SMALL_OR_OCCLUDED")
    if target["valid_depth_fraction"] < .95:
        reasons.append("TARGET_DEPTH_INVALID")
    if destination["visible_pixels"] < 100 or destination["valid_depth_fraction"] < .95:
        reasons.append("DESTINATION_NOT_OBSERVABLE")
    pixel = chosen[1]
    point = observation.world_point((pixel[0], pixel[1])) if pixel is not None else None
    color = truth["target_color_name"]
    color_zh = {"red": "红色", "blue": "蓝色", "yellow": "黄色"}[color]
    return {"instruction": f"将{color_zh}方块移动到绿色区域。",
            "instruction_en": f"Move the {color} block to the green region.",
            "target_instance_id": 1, "destination_instance_id": 5, "instances": instances,
            "target_pixel": chosen[1], "destination_pixel": chosen[5],
            "surface_point": [point.x, point.y, point.z] if point else None,
            "object_center": target["position"], "positive": not reasons,
            "negative_reasons": reasons,
            "suggested_action": "REQUEST_MORE_OBSERVATION" if reasons else "GROUND_TARGET",
            "label_source": "SIMULATOR_GROUND_TRUTH", "execution_verified": False,
            "settling": truth["settling"]}
