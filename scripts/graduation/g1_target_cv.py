"""Depth and printed-border contradictions for current-frame development RGB-D observations."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np
from scripts.graduation import g1_visibility_grid as grid

from cloud_edge_robot_arm.vision.top_grasp import _MAX_TOP_PATCH_Z_SPAN_M


def incompatible_print(z, border_contrast, *, marker_size_m, edge_contrast):
    """Disprove a fully observed island grid only with contradictory metric and ink support."""
    depth = np.asarray(z)
    contrast = np.asarray(border_contrast)
    if (
        depth.shape != (36,)
        or contrast.shape != (4, 7)
        or not np.isfinite(depth).all()
        or np.any(depth <= 0)
        or not np.isfinite(contrast).all()
    ):
        return False
    q1, q3 = np.quantile(depth, [0.25, 0.75])
    diagonal_limit = math.sqrt(2) * marker_size_m + 0.006
    # The quiet side is lighter than the outer ink. A positive border witness on any side
    # preserves the candidate, including a partially occluded actual foreign print.
    rim = np.median(contrast, axis=1)
    return bool(q3 - q1 > diagonal_limit and np.all(rim < 0.5 * edge_contrast))


def _sample_contradiction(gray, depth, candidate, marker_size_m):
    center, basis = candidate["center"], candidate["basis"]
    core = np.rint(grid.CELLS @ basis + center).astype(int)
    s = np.linspace(-2.4, 2.4, 7)
    delta = []
    for axis in (0, 1):
        for sign in (-1, 1):
            edge = []
            for offset in (2.6, 3.45):
                ring = np.stack((np.full_like(s, sign * offset), s), axis=1)
                xy = (ring if axis == 0 else ring[:, ::-1]) @ basis + center
                if np.any(xy < 1) or np.any(xy >= [gray.shape[1] - 1, gray.shape[0] - 1]):
                    return None
                edge.append(grid._sample(gray, xy).astype(float))
            delta.append(edge[1] - edge[0])
    z = depth[core[:, 1], core[:, 0]]
    if not incompatible_print(
        z, delta, marker_size_m=marker_size_m, edge_contrast=grid.MIN_CONTRAST
    ):
        return None
    return dict(
        id=candidate["id"],
        center_px=center.tolist(),
        source="internal_white_component",
        physical_diagonal_limit_m=math.sqrt(2) * marker_size_m + 0.006,
        axial_quartiles_m=np.quantile(z, [0.25, 0.75]).tolist(),
        outer_minus_inner_side_medians=np.median(delta, axis=1).tolist(),
    )


def screened_grids(gray, depth, candidates, ambiguous, marker_size_m):
    """Keep the original ambiguity, direct detections and unknowns unless disproved."""
    retained, rejected = [], []
    for candidate in candidates:
        witness = None
        if candidate["origins"] == ["internal_white_component"]:
            witness = _sample_contradiction(gray, depth, candidate, marker_size_m)
        if witness is None:
            retained.append(candidate)
        else:
            rejected.append(witness)
    if not rejected:
        return candidates, ambiguous, rejected
    remaining_ambiguous = any(c["front_face_ambiguous"] for c in retained) or any(
        grid._inside(a, *b["center"]) for i, a in enumerate(retained) for b in retained[i + 1 :]
    )
    return retained, remaining_ambiguous, rejected


def current_shaded_green(colors, reference_color, plane_error_m, plane_span_m):
    """Test the frozen reference hue under illumination after paired depth establishes the plane."""
    colors = np.asarray(colors, dtype=float)
    ref = np.asarray(reference_color, dtype=float)
    ref = ref - ref.min()
    pure = colors - colors.min(axis=1, keepdims=True)
    hue = pure / np.maximum(1.0, pure.sum(axis=1, keepdims=True))
    return (
        (np.linalg.norm(hue - ref / max(1e-9, ref.sum()), axis=1) <= 0.060)
        & (np.ptp(colors, axis=1) >= 60)
        & (np.abs(plane_error_m) <= plane_span_m)
    )


def same_region(reference, current):
    """A full-color rectangle also has to occupy the initially bound world-space footprint."""
    tolerance = np.asarray(reference["uncertainty_m"]) + np.asarray(current["uncertainty_m"])
    tolerance[2] = max(tolerance[2], _MAX_TOP_PATCH_Z_SPAN_M)
    return all(
        np.all(np.abs(np.subtract(reference[k], current[k])) <= tolerance) for k in ("min", "max")
    )


VISION = "scripts/graduation/g1_visibility_vision.py"
REGION = "src/cloud_edge_robot_arm/vision/servo_region.py"
PINS = {
    VISION: "2e98bd0d96e4b8aa58a58b0ef1d959a8b3fde259f3ae7b948eb68ce4ffa6a169",
    REGION: "17be952ca97ce313e2f32b37d8a951150563509857878fa7284b51fc73915f77",
}


def overlays(parent_runtime: Path) -> dict[str, bytes]:
    sources = {}
    for name, digest in PINS.items():
        raw = (parent_runtime / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("frozen target visibility input changed: " + name)
        sources[name] = raw.decode()

    def edit(name, old, new):
        if sources[name].count(old) != 1:
            raise ValueError("target visibility anchor changed: " + name)
        sources[name] = sources[name].replace(old, new)

    anchor = '    result["rejected_candidate_count"] = rejected_count'
    edit(
        VISION,
        anchor,
        "    from scripts.graduation.g1_target_cv import screened_grids\n"
        "    candidates, ambiguous, contradicted = screened_grids(\n"
        '        gray, depth, candidates, ambiguous, pose["marker_size_m"])\n'
        '    result["rejected_nonphysical_grids"] = contradicted\n' + anchor,
    )
    edit(
        REGION,
        "    reference = tracker._reference",
        "    from scripts.graduation.g1_target_cv import current_shaded_green, same_region\n"
        "    reference = tracker._reference",
    )
    edit(
        REGION,
        "        if complete is not None:\n            return complete",
        "        if complete is not None:\n"
        "            if not same_region(region, complete):\n"
        '                return None, "region_moved_from_bound_world_reference"\n'
        "            return complete",
    )
    anchor = "    if np.any(~high_foreground[ys, xs] & ~sidewall & ~mixed_footprint):"
    edit(
        REGION,
        anchor,
        "    coplanar_green = near_measured_foreground[ys, xs] & current_shaded_green(\n"
        "        colors, tracker.destination_color, foreground[:, 2] - plane, span)\n"
        '    result["current_coplanar_shaded_pixels"] = int(coplanar_green.sum())\n'
        "    if np.any(~high_foreground[ys, xs] & ~sidewall & ~mixed_footprint & ~coplanar_green):",
    )
    return {
        "scripts/graduation/g1_target_cv.py": Path(__file__).read_bytes(),
        **{name: source.encode() for name, source in sources.items()},
    }
