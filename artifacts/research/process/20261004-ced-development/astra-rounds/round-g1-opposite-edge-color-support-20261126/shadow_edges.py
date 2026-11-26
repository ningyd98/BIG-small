"""Read-only candidate built around the pinned original optical geometry."""
import inspect

import numpy as np

from scripts.graduation import g1_complete_cv_handoff_optics as original


def extend_edges(state, table_depth, evidence):
    x, y, sign = (state[key] for key in ("xx", "yy", "sign"))
    depth, gray, plane = (state[key] for key in ("depth", "gray", "plane"))
    native = state["match"]
    fg, bg, last, first = (state[key] for key in ("fg", "bg", "last", "first"))
    near = last - first > 9
    old = native & near & (fg - bg > 22)
    old_count = old.sum(axis=1)

    def adjacent_to_original():
        anchored = old & (old_count == 1)[:, None]
        result = np.zeros_like(anchored)
        for direction in (-1, 1):
            shifted = np.roll(anchored, direction, axis=0)
            shifted[0 if direction == 1 else -1] = False
            neighbor_y = np.roll(y, direction, axis=0)
            neighbor_x = np.roll(x, direction, axis=0)
            for position in (-1, 0, 1):
                active = np.roll(shifted, position, axis=1)
                if position:
                    active[:, 0 if position == 1 else -1] = False
                result |= (
                    active
                    & (abs(np.roll(neighbor_x, position, axis=1) - x) == 1)
                    & (abs(np.roll(neighbor_y, position, axis=1) - y) <= 1)
                )
        return result

    inner, inner_near = y - 3 * sign, y - 2 * sign
    outer_near, outer = y + sign, y + 2 * sign
    quiet = np.rint(y - sign * state["half"] * 0.14).astype(int)
    ink = np.rint(y - sign * state["half"] * 0.36).astype(int)
    rows = (inner, inner_near, y - sign, y, outer_near, outer, quiet, ink)
    in_image = np.logical_and.reduce([(z >= 0) & (z < gray.shape[0]) for z in rows])
    rgb_values = [gray[np.clip(z, 0, gray.shape[0] - 1), x].astype(float) for z in rows]
    d = [depth[np.clip(z, 0, gray.shape[0] - 1), x] for z in rows]
    t1 = table_depth[np.clip(outer_near, 0, gray.shape[0] - 1), x]
    t2 = table_depth[np.clip(outer, 0, gray.shape[0] - 1), x]
    finite = np.logical_and.reduce([np.isfinite(z) & (z > 0) for z in (*d, t1, t2)])
    same_surface = (
        (abs(d[0] - plane) < 0.004) & (abs(d[0] - d[1]) < 0.004)
        & (d[5] > plane + 0.006) & (abs(d[5] - d[4]) < 0.004)
        & (abs(t1 - d[4]) <= 0.004) & (abs(t2 - d[5]) <= 0.004)
    )
    samples = rgb_values[:6]
    extended_contrast = (
        np.logical_and.reduce([a >= b for a, b in zip(samples[:-1], samples[1:], strict=True)])
        & (samples[0] - samples[1] <= 3) & (samples[4] - samples[5] <= 3)
        & (samples[0] - samples[5] > 22)
    )
    ink_evidence = (abs(d[6] - plane) < 0.004) & (abs(d[7] - plane) < 0.004) & (
        rgb_values[6] - rgb_values[7] > 42
    )
    middle = (fg + bg) / 2
    in_transition = (middle >= first) & (middle <= last)
    nearby_measured = native & near & (old_count == 0)[:, None] & adjacent_to_original()
    extended = nearby_measured & in_image & finite & same_surface & extended_contrast & ink_evidence & in_transition
    extended &= (extended.sum(axis=1) == 1)[:, None]
    yy, xx = np.nonzero(extended)

    def count_and_span(mask):
        columns = x[:, 0][mask.sum(axis=1) == 1]
        return [int(columns.size), int(np.ptp(columns)) if columns.size else 0]

    evidence.append({
        "side": state["side"], "native_count_span": count_and_span(old),
        "proposed_count_span": count_and_span(old | extended),
        "new_edge_xy": [[int(x[a, b]), int(y[a, b])] for a, b in zip(yy, xx, strict=True)],
        "new_column_filter_counts": {
            "native_depth_near_edge_and_adjacent": int(nearby_measured.sum()),
            "with_registered_surfaces": int((nearby_measured & in_image & finite & same_surface).sum()),
            "with_extended_contrast": int((nearby_measured & in_image & finite & same_surface & extended_contrast).sum()),
            "with_native_ink_and_interpolation": int(extended.sum()),
        },
    })
    return old | extended


def candidate_measured_pose(table_depth, evidence):
    namespace = vars(original).copy()

    def extended_mask(state):
        return extend_edges(state, table_depth, evidence)

    namespace["shadow_mask"] = extended_mask
    source = inspect.getsource(original._opposite_edges)
    anchor = "match &= (fg - bg > 22) & (last - first > 9)"
    if source.count(anchor) != 1:
        raise ValueError("pinned original mask location changed")
    source = source.replace(anchor, "match = shadow_mask(locals())")
    filename = inspect.getsourcefile(original)
    exec(compile(source, filename, "exec"), namespace)
    exec(compile(inspect.getsource(original.measured_pose), filename, "exec"), namespace)
    return namespace["measured_pose"]


def pose_readback(frame, marker, geometry, identity, step, table_depth, negative):
    baseline = original.rigid_pose(frame, marker, geometry, identity=identity, physics_step=step)
    if negative or baseline or not identity.matches(frame, marker, geometry, step):
        return baseline, None, [], "excluded_unknown_near" if negative else "original_result_retained"
    measured = original.measured_pose(frame, marker, geometry)
    if measured is None or measured["method"] != "id8":
        return baseline, None, [], "no_original_unqualified_id8"
    evidence = []
    candidate = candidate_measured_pose(table_depth, evidence)(frame, marker, geometry)
    if candidate is None or candidate["method"] != "id8_opposite_edges" or not any(
        row["new_edge_xy"] for row in evidence
    ):
        return baseline, None, evidence, "full_two_sided_edge_fit_unavailable"
    return baseline, candidate, evidence, "uncertified_shadow_pose"


def controls():
    # A native column followed by two weak columns. Only the immediate neighbor may be added.
    gray = np.zeros((30, 5), dtype=np.uint8)
    depth = np.zeros((30, 5))
    table = np.zeros_like(depth)
    y = np.full((3, 1), 12)
    x = np.arange(1, 4)[:, None]
    gray[9:15, 1:4] = np.array([103, 100, 99, 81, 78, 76])[:, None]
    gray[13, 1] = 77
    gray[8, 1:4] = 40
    depth[8:14, 1:4] = 1.25
    depth[12:15, 1:4] = 1.40
    table[13:15, 1:4] = 1.40

    def run():
        fg, bg = gray[y - 2, x].astype(float), gray[y + 1, x].astype(float)
        last, first = gray[y - 1, x].astype(float), gray[y, x].astype(float)
        state = dict(xx=x, yy=y, sign=1, depth=depth, gray=gray, plane=np.full_like(x, 1.25, dtype=float),
                     match=np.ones(x.shape, dtype=bool), fg=fg, bg=bg, last=last, first=first, half=10, side=-1)
        proof = []
        mask = extend_edges(state, table, proof)
        return mask[:, 0].tolist(), proof[0]["new_edge_xy"]

    assert run() == ([True, True, False], [[2, 12]])
    table[14, 2] = 1.39
    assert run() == ([True, False, False], [])
    table[14, 2] = 1.40
    gray[12, 2] = 90  # Native local drop now equals 9.
    assert run() == ([True, False, False], [])
    gray[12, 2] = 81
    gray[13, 2] = 77  # This column already passes the original, so it cannot be replaced.
    assert run() == ([True, True, True], [[3, 12]])
    gray[13, 2] = 78
    gray[8, 2] = 70
    assert run() == ([True, False, False], [])
    return True
