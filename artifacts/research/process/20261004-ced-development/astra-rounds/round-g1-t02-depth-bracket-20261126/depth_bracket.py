"""Audit an adjacent carrier edge as a range of pixel positions in a CPU-only shadow."""

import argparse
import inspect
import subprocess
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scripts.graduation import g1_complete_cv_handoff_optics as optics
from scripts.graduation.perception_io import sha

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "round-g1-opposite-edge-color-support-20261126"
sys.path.insert(0, str(OLD))
import shadow_readback as reader  # noqa: E402

ROOT = Path.cwd()
OUT = ROOT / "experiments/results/g1-t02-depth-bracket-20261126/fit-01"
SEALED = ROOT / "experiments/results/g1-opposite-edge-color-support-20261126/shadow-01"
PLAN = reader.read(HERE / "plan.json")
T = PLAN["thresholds"]
NATIVE_ANCHOR = "match &= (fg - bg > 22) & (last - first > 9)"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def original_state(frame, marker, geometry):
    source, start = inspect.getsourcelines(optics._opposite_edges)
    locations = [start + i for i, line in enumerate(source) if NATIVE_ANCHOR in line]
    require(len(locations) == 1, "frozen color/depth conjunction changed")
    states = {}

    def trace(call, event, _):
        if event == "line" and call.f_lineno == locations[0]:
            state = dict(call.f_locals)
            side = state["side"]
            require(side not in states, "duplicate original edge side")
            state["depth_ok"] = state["match"].copy()
            states[side] = state
        return trace

    def tracer(call, event, _):
        return trace if event == "call" and call.f_code is optics._opposite_edges.__code__ else None

    previous = sys.gettrace()
    try:
        sys.settrace(tracer)
        measured = optics.measured_pose(frame, marker, geometry)
    finally:
        sys.settrace(previous)
    return measured, states


def native_mask(state):
    return state["depth_ok"] & (state["fg"] - state["bg"] > 22) & (
        state["last"] - state["first"] > 9
    )


def original_pixels(state):
    mask = native_mask(state)
    accepted = mask & (mask.sum(axis=1) == 1)[:, None]
    ij = np.nonzero(accepted)
    ix, iy = state["xx"][ij], state["yy"][ij]
    middle = (state["fg"][ij] + state["bg"][ij]) / 2
    blend = np.clip((middle - state["first"][ij]) / (state["last"][ij] - state["first"][ij]), 0, 1)
    return np.column_stack((ix, iy)), np.column_stack((ix, iy - state["sign"] * blend))


def edge_support(state, table, x, y, plane):
    sign, depth, gray = state["sign"], state["depth"], state["gray"]
    quiet, ink = [int(np.rint(y - sign * state["half"] * t)) for t in (0.14, 0.36)]
    ordered = [y + sign * offset for offset in (-2, -1, 0, 1)]
    if not all(0 <= row < depth.shape[0] for row in (*ordered, quiet, ink)):
        return None
    near0, near1, far0, far1 = (float(depth[row, x]) for row in ordered)
    table0, table1 = (float(table[row, x]) for row in ordered[2:])
    quiet_d, ink_d = float(depth[quiet, x]), float(depth[ink, x])
    samples = [near0, near1, far0, far1, table0, table1, quiet_d, ink_d]
    if not np.all(np.isfinite(samples)) or min(samples) <= 0:
        return None
    ink_dn = int(gray[quiet, x]) - int(gray[ink, x])
    local_dn = int(gray[ordered[1], x]) - int(gray[ordered[2], x])
    depth_support = (
        max(abs(near0 - plane), abs(near1 - plane), abs(quiet_d - plane), abs(ink_d - plane))
        < 0.004 and min(far0, far1) > plane + 0.006
        and max(abs(near0 - near1), abs(far0 - far1)) < 0.004
        and max(abs(table0 - far0), abs(table1 - far1)) <= 0.004
    )
    return {"edge_xy": [x, y], "quiet_minus_ink_dn": ink_dn, "local_drop_dn": local_dn,
            "table_error_m": [abs(table0 - far0), abs(table1 - far1)],
            "registered_depth_support": bool(depth_support),
            "has_support": bool(depth_support and ink_dn > 42 and local_dn > 9)}


def find_neighbors(state, table, anchors):
    old = native_mask(state)
    eligible = state["depth_ok"] & ((old.sum(axis=1) == 0)[:, None])
    options = []
    for i, j in zip(*np.nonzero(eligible), strict=True):
        x, y = int(state["xx"][i, j]), int(state["yy"][i, j])
        neighbor = (np.abs(anchors[:, 0] - x) == 1) & (np.abs(anchors[:, 1] - y) <= 1)
        if not np.any(neighbor):
            continue
        evidence = edge_support(state, table, x, y, float(state["plane"][i, j]))
        if evidence is not None:
            options.append(evidence)
    return options


def metric(state, uv):
    ray = optics._rays(uv, *state["frame"].intrinsics) @ state["rotation"].T
    denom = ray @ state["normal"]
    require(np.all(np.isfinite(denom)) and np.all(abs(denom) > 0.1) and
            (np.all(denom > 0) or np.all(denom < 0)), "unbounded plane projection")
    distance = ((state["pivot"] - state["eye"]) @ state["normal"]) / denom
    require(np.all(distance > 0) and np.isfinite(distance).all(), "invalid plane distance")
    local = state["eye"] + ray * distance[:, None] - state["opposite"]
    along = local @ state["forward"]
    transverse = local @ state["across"] - state["side"] * 0.05
    return np.column_stack((along, transverse))


def pixel_domain(x, y, sign):
    inner, outer = sorted((y - sign, y))
    e = T["pixel_half_extent"]
    centers = np.array([[x, inner], [x, outer]], dtype=float)
    corners = np.array([[dx, dy] for dx in (x - e, x + e)
                        for dy in (inner - e, outer + e)], dtype=float)
    return centers, corners


def min_residual_span(centers):
    along, across = abs(centers[1] - centers[0])
    return float(max(0, across - T["native_slope"] * along))


def bracket(state, point, line):
    centers, corners = pixel_domain(*point, state["sign"])
    center_world, footprint = metric(state, centers), metric(state, corners)
    slope, intercept = line
    lower, upper = np.sort(footprint[:, 1] - slope * footprint[:, 0] - intercept)[[0, -1]]
    width = min_residual_span(center_world)
    limit = T["native_residual_m"]
    return {
        "center_pixels": centers.tolist(), "pixel_footprint_corners": corners.tolist(),
        "center_metric_coordinates_m": center_world.tolist(),
        "footprint_metric_corners_m": footprint.tolist(),
        "fixed_rgb_line_residual_interval_m": [float(lower), float(upper)],
        "two_center_residual_span_lower_m_for_any_native_slope": width,
        "native_residual_span_budget_m": 2 * limit,
        "full_footprint_meets_native_residual": bool(max(abs(lower), abs(upper)) <= limit),
    }


def fiducial_fit(states, projected):
    rows = np.vstack([metric(states[side], projected[side]) for side in (-1, 1)])
    slope, intercept = np.polyfit(rows[:, 0], rows[:, 1], 1)
    error = float(np.max(abs(rows[:, 1] - (slope * rows[:, 0] + intercept))))
    accepted = (error <= T["native_residual_m"] and abs(slope) <= T["native_slope"]
                and abs(intercept) <= T["native_intercept_m"])
    return (float(slope), float(intercept)), {
        "rgb_slope": float(slope), "rgb_intercept_m": float(intercept), "max_rgb_residual_m": error,
        "same_native_metric_limits": bool(accepted),
    }


def point_diagnostic(measured, basis_state, offset):
    distance = basis_state["distance"]
    require(abs(offset) < abs(distance), "point diagnostic outside registered carrier span")
    angle = np.arcsin(offset / distance)
    forward = (np.cos(angle) * basis_state["forward"] + np.sin(angle) * basis_state["across"])
    normal = basis_state["normal"]
    rot = np.column_stack((forward, np.cross(normal, forward), normal))
    lever = np.asarray(measured["anchor_object_m"])
    anchor = np.asarray(measured["anchor_world_m"])
    return {"method": "fixed_rgb_anchors_diagnostic", "anchor_world_m": anchor.tolist(),
            "anchor_object_m": lever.tolist(), "center_m": (anchor - rot @ lever).tolist(),
            "rotation": rot.tolist()}


def eligible_side(counts):
    good = [side for side, pair in counts.items() if pair[0] >= 5 and pair[1] >= 4]
    return -good[0] if len(good) == 1 and counts[-good[0]] == (4, 3) else None


def audit(frame, marker, geometry, identity, step, table, negative):
    old = optics.rigid_pose(frame, marker, geometry, identity=identity, physics_step=step)
    if negative or old is not None:
        status = "excluded_unknown_near" if negative else "original_result_retained"
        return old, None, [], status
    if not identity.matches(frame, marker, geometry, step) or marker.get("usable_ids") != [8]:
        return old, None, [], "not_current_bound_single_id8"
    measured, states = original_state(frame, marker, geometry)
    if not measured or measured["method"] != "id8" or set(states) != {-1, 1}:
        return old, None, [], "native_two_side_geometry_unavailable"
    original, fractional = {}, {}
    for side, state in states.items():
        original[side], fractional[side] = original_pixels(state)
    counts = {side: (len(uv), int(np.ptp(uv[:, 0])) if len(uv) else 0)
              for side, uv in original.items()}
    result = {"counts_and_spans": counts}
    side = eligible_side(counts)
    if side is None:
        return old, None, [result], "no_single_missing_edge_column"
    options = find_neighbors(states[side], table, original[side])
    result["weak_side"] = side
    result["adjacent_candidates"] = options
    accepted = [entry for entry in options if entry["has_support"]]
    if len(accepted) != 1:
        return old, None, [result], "no_unique_physically_supported_transition"
    candidate, = accepted
    x = candidate["edge_xy"][0]
    if np.ptp(np.r_[original[side][:, 0], x]) < 4:
        return old, None, [result], "original_column_span_still_missing"
    line, result["rgb_fit"] = fiducial_fit(states, fractional)
    result["depth_bracket"] = bracket(states[side], candidate["edge_xy"], line)
    if result["rgb_fit"]["same_native_metric_limits"]:
        result["diagnostic_rgb_line_pose"] = point_diagnostic(measured, states[side], line[1])
    fits = (result["depth_bracket"]["full_footprint_meets_native_residual"]
            and result["rgb_fit"]["same_native_metric_limits"])
    status = ("footprint_sensitive_no_calibrated_continuous_edge" if fits
              else "depth_footprint_exceeds_native_tube")
    return old, None, [result], status


def controls():
    table = np.full((20, 8), 1.4)
    depth = table.copy()
    depth[:10] = 1.25
    gray = np.full(depth.shape, 209)
    gray[8:10] = 250
    gray[10] = 225
    gray[6:8] = 176
    state = {"sign": 1, "depth": depth, "gray": gray, "half": 10.,
             "xx": np.array([[2], [3], [4]]), "yy": np.full((3, 1), 10),
             "plane": np.full((3, 1), 1.25), "depth_ok": np.ones((3, 1), bool),
             "fg": np.array([[250.], [231.], [231.]]), "bg": np.full((3, 1), 209.),
             "last": np.full((3, 1), 250.), "first": np.full((3, 1), 225.)}
    def probe():
        return edge_support(state, table, 3, 10, 1.25)

    require(probe()["has_support"], "synthetic physical transition lost")
    for array, index, val in ((table, (11, 3), 1.38), (depth, (8, 3), 1.39),
                              (gray, (6, 3), 250), (gray, (10, 3), 252),
                              (depth, (10, 3), 1.25)):
        old = array[index]
        array[index] = val
        require(not probe()["has_support"], "synthetic foreign, blank or inverted edge admitted")
        array[index] = old
    depth[9, 3] = 0.0
    require(probe() is None, "invalid depth must reject without an edge measurement")
    depth[9, 3] = 1.25
    require([o["edge_xy"] for o in find_neighbors(state, table, np.array([[2, 10]]))]
            == [[3, 10]], "neighbor selection recursed beyond original evidence")
    ambiguous = {1: (5, 4), -1: (5, 4)}
    require(eligible_side(ambiguous) is None and eligible_side({1: (5, 4), -1: (3, 2)}) is None,
            "wrong column count admitted")
    for sign in (-1, 1):
        centers, corners = pixel_domain(153, 128, sign)
        require(np.ptp(centers[:, 1]) == 1 and np.ptp(corners[:, 1]) == 2,
                "depth support dropped part of a pixel")
    require(min_residual_span(np.array([[0., 0.], [.002, .005]])) > 2 * T["native_residual_m"],
            "minimum residual span positive control failed")
    return True


def pins():
    roots = {"old": OLD, "sealed": SEALED, "rounds": HERE.parent, "repo": ROOT}
    for alias, expected in PLAN["sha256"].items():
        folder, name = alias.split("/", 1)
        reader.pin(roots[folder] / name, expected)


def register():
    pins()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    require(head == PLAN["head"], "Astra baseline changed")
    old = reader.read(SEALED / "registration.json")
    packets, _ = reader.exposure_metadata()
    require(packets == old["packets"], "input registration changed")
    require(Counter(key.split("/")[0] for key in packets) == PLAN["counts"], "wrong packet counts")
    for entry in packets.values():
        reader.pin(ROOT / entry["path"], entry["sha256"])
    passed = controls()
    OUT.mkdir(exist_ok=False, parents=True)
    reader.write(OUT / "registration.json", {
        "packets": packets, "original_registration_sha256": sha(SEALED / "registration.json"),
        "source_sha256": sha(Path(__file__)), "plan_sha256": sha(HERE / "plan.json"),
        "controls": passed,
    })


def registered(expected):
    pins()
    record = reader.read(reader.pin(OUT / "registration.json", expected))
    require(record["source_sha256"] == sha(Path(__file__)) and
            record["plan_sha256"] == sha(HERE / "plan.json"), "registered shadow driver changed")
    return record


def score(expected, prediction):
    reader.score(expected, prediction, OUT / "offline-score.json")
    raw = reader.read(OUT / "predictions-first.json")
    baseline = reader.read(SEALED / "predictions-first.json")
    require(set(raw["rows"]) == set(baseline["rows"]), "prediction keys changed")
    require(all(new["old_pose"] == baseline["rows"][key]["old_pose"]
                and new["shadow_pose"] is None for key, new in raw["rows"].items()),
            "native optical certificates changed")
    target = raw["rows"]["t02/1512"]
    evidence, = target["edges"]
    diagnostic = evidence.get("diagnostic_rgb_line_pose")
    truth = reader.read(reader.cv_pin(reader.T02_REL + "/instance/offline-truth.json"))
    sample, = [row for row in truth["samples"] if row["physics_step"] == 1512]
    compare = None
    if diagnostic:
        real = {"center_m": sample["object_geom_position_m"],
                "rotation": np.reshape(sample["object_geom_rotation_row_major"], (3, 3))}
        profile = optics.CALIBRATION["id8_opposite_edges"]
        candidate = dict(diagnostic, anchor_error_object_m=profile["anchor"],
                         basis_error_object=profile["basis"])
        compare = reader.ratios(candidate, real)
    reader.write(OUT / "brackets.json", {
        "target": target, "truth_comparison_point_diagnostic_only": compare,
        "counts": {group: dict(sorted(Counter(v["status"] for key, v in raw["rows"].items()
                                              if key.split("/")[0] == group).items()))
                   for group in PLAN["counts"]},
        "permissions": PLAN["permissions"], "predictions_sha256": prediction,
        "registration_sha256": expected, "old_baseline_certificates_match_exactly": True,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("register", "predict", "score"))
    parser.add_argument("registration_sha256", nargs="?")
    parser.add_argument("argument", nargs="?")
    args = parser.parse_args()
    if args.mode == "register":
        register()
    elif args.mode == "predict":
        require(args.argument in ("first", "second"), "invalid cold process")
        with (patch.object(reader, "registration", registered),
              patch.object(reader, "pose_readback", audit)):
            reader.predict(args.registration_sha256, OUT / f"predictions-{args.argument}.json")
    else:
        with patch.object(reader, "registration", registered), patch.object(reader, "OUT", OUT):
            score(args.registration_sha256, args.argument)
