"""R505 offline contracts. This module never loads a model or chooses by oracle."""

import json
import math
import re


def _numbers(values, count):
    if not isinstance(values, (list, tuple)) or len(values) != count:
        raise ValueError("wrong coordinate arity")
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in values):
        raise ValueError("coordinates must be finite numbers")
    return tuple(float(x) for x in values)


def _continuous(values, width, height, space, *, edges=False):
    if width < 1 or height < 1:
        raise ValueError("invalid original image dimensions")
    result = []
    for i, value in enumerate(values):
        size = width if i % 2 == 0 else height
        if space in ("unit", "normalized_1000", "normalized_999"):
            scale = {"unit": 1, "normalized_1000": 1000, "normalized_999": 999}[space]
            if not 0 <= value <= scale:
                raise ValueError("normalized coordinate outside declared domain")
            mapped = value / scale * size
            result.append(mapped if edges or mapped < size else size - 1)
        elif space == "pixel":
            if not 0 <= value <= size or (not edges and value == size):
                raise ValueError("pixel outside original canvas")
            result.append(value)
        else:
            raise ValueError("unknown explicit coordinate space")
    return tuple(result)


def point_pixel(point, width, height, space):
    mapped = _continuous(_numbers(point, 2), width, height, space)
    return tuple(math.floor(x) for x in mapped)


def box_pixel(box, width, height, space):
    box = _continuous(_numbers(box, 4), width, height, space, edges=True)
    x1, y1, x2, y2 = box
    if x2 <= x1 or y2 <= y1:
        raise ValueError("box must have positive area and ordered axes")
    return box, (math.floor((x1 + x2) / 2), math.floor((y1 + y2) / 2))


def mask_pixel(value, width, height, *, kind, threshold):
    rows = value.tolist() if hasattr(value, "tolist") else value
    if not rows or not rows[0] or len({len(row) for row in rows}) != 1:
        raise ValueError("mask must be nonempty and rectangular")
    sh, sw = len(rows), len(rows[0])
    if kind not in ("probability", "logit", "binary") or not math.isfinite(threshold):
        raise ValueError("unknown mask threshold contract")
    for row in rows:
        for x in row:
            if not isinstance(x, (int, float, bool)) or not math.isfinite(x):
                raise ValueError("nonfinite mask value")
            if kind in ("probability", "binary") and not 0 <= x <= 1:
                raise ValueError("probability outside unit domain")
    mask = [[rows[min(sh - 1, math.floor((y + 0.5) * sh / height))]
                  [min(sw - 1, math.floor((x + 0.5) * sw / width))] >= threshold
             for x in range(width)] for y in range(height)]
    foreground = [(x, y) for y, row in enumerate(mask) for x, present in enumerate(row) if present]
    if not foreground:
        return mask, None
    cx = sum(x for x, _ in foreground) / len(foreground)
    cy = sum(y for _, y in foreground) / len(foreground)
    point = min(foreground, key=lambda p: ((p[0] - cx) ** 2 + (p[1] - cy) ** 2, p[1], p[0]))
    return mask, point


def select_candidate(candidates):
    if not candidates:
        return None
    if any("score" in row for row in candidates):
        for row in candidates:
            if "score" in row and (isinstance(row["score"], bool) or not math.isfinite(row["score"])):
                raise ValueError("invalid candidate score")
        return max(candidates, key=lambda row: row.get("score", -math.inf))
    return candidates[0]


def native_status(candidates, *, explicit_absence, parse_error):
    if parse_error is not None:
        return "INVALID"
    if candidates:
        return "DETECTED"
    return "REFUSAL" if explicit_absence else "EMPTY"


def assert_public_inputs(manifest):
    if set(manifest) != {"schema", "cases"} or manifest["schema"] != "r505-public-v1":
        raise ValueError("wrong public input schema/source generation")
    expected = {"index", "id", "rgb_path", "rgb_sha256", "rgb_bytes", "instruction", "target_phrase", "destination_phrase"}
    ids = []
    for row in manifest["cases"]:
        if set(row) != expected or not re.fullmatch(r"case-\d{4}", row.get("id", "")):
            raise ValueError("unexpected model-visible key or nonopaque identity")
        if re.search(r"positive|negative|absent|oracle|instance", row["rgb_path"], re.I):
            raise ValueError("oracle or labeled path exposed to runner")
        if not re.fullmatch(r"[a-f0-9]{64}", row["rgb_sha256"]):
            raise ValueError("missing frozen RGB hash")
        ids.append(row["id"])
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate opaque case identity")


def strict_json(text):
    def invalid(value):
        raise ValueError("nonfinite JSON constant: " + value)
    return json.loads(text, parse_constant=invalid)


def box_iou(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union > 0 else 0.0


def pixel_assessment(point, instances, valid_mask, depth, width, height, expected_id):
    if point is None:
        return {"hit": False, "valid_depth": False, "actual_geom_id": None}
    x, y = point
    if not 0 <= x < width or not 0 <= y < height:
        raise ValueError("mapped point outside original image")
    index = y * width + x
    return {"hit": instances[index] == expected_id,
            "valid_depth": bool(valid_mask[index]) and math.isfinite(depth[index]) and depth[index] > 0,
            "actual_geom_id": instances[index]}
