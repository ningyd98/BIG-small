"""Recompute the registered t01 LIFT prefix and stop branches without a backend."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath

HERE = Path(__file__).resolve().parent
# The pinned sampler prepends the Cartesian product of hand and both fingers
# with object, six carrier geoms and table. Table is the eighth column per geom.
FINGER_TABLE = (15, 23)
ROW_SHAPES = {"tcp": (241, 3), "pair_gap": (241, 30), "engine_gap": (241, 30),
              "q": (241, 16), "qvel": (241, 15), "contacts": (241, 4)}
ORIGIN_TICK = 1632
TERMINAL_TICK = 1640


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def rows_checked(arrays):
    for name, shape in ROW_SHAPES.items():
        require(arrays[name].shape == shape and np.isfinite(arrays[name]).all(), f"bad rows: {name}")
    require(np.all(arrays["contacts"] >= 0), "invalid contact counter")


def guard_event(path, position, peak):
    try:
        path.check_position(tuple(position), peak_z=peak)
    except ValueError as error:
        return str(error)
    return None


def scalar(path, points, start_step, peak):
    transverse, descent = [], []
    first = None
    for step, (x, y, z) in enumerate(points, start_step):
        transverse.append(math.hypot(x - path.start_m[0], y - path.start_m[1]))
        descent.append(max(0.0, peak - z))
        reason = guard_event(path, (x, y, z), peak)
        if reason and first is None:
            first = {"step": step, "reason": reason}
        peak = max(peak, z)
    return first, max(transverse, default=0.0), max(descent, default=0.0), peak


def vector(path, points, start_step, peak):
    if not len(points):
        return None, 0.0, 0.0, peak
    xx, yy, zz = np.asarray(points).T
    transverse = np.hypot(xx - path.start_m[0], yy - path.start_m[1])
    preceding_peak = np.maximum.accumulate(np.r_[peak, zz])[:-1]
    descent = np.maximum(0.0, preceding_peak - zz)
    failures = (
        transverse > path.lateral_tolerance_m,
        zz < preceding_peak - path.backtrack_tolerance_m,
        zz > path.target_m[2] + 0.005,
    )
    indices = np.flatnonzero(np.logical_or.reduce(failures))
    first = None
    if indices.size:
        index = indices[0]
        reasons = ("clearance left its 1 mm lateral corridor",
                   "clearance descended by more than 1 mm",
                   "clearance exceeded its target height tolerance")
        first = {"step": int(start_step + index),
                 "reason": next(reason for reason, mask in zip(reasons, failures) if mask[index])}
    return first, float(transverse.max()), float(descent.max()), float(max(peak, zz.max()))


def summarize_path(calc, path, points, start_step, peak):
    first, lateral, descent, peak = calc(path, points, start_step, peak)
    return {
        "samples": len(points), "first_event": first,
        "max_lateral_mm": round(lateral * 1000, 12),
        "max_descent_mm": round(descent * 1000, 12),
        "max_height_m": max((float(p[2]) for p in points), default=None),
    }, peak


def stop_windows(plan, base, receipt):
    windows = {}
    for record in receipt["stages"]:
        mode = record["mode"]
        expected = expected_steps(plan, mode)
        require(mode not in windows and [row["step"] for row in record["stops"]] == expected,
                "incomplete or reordered branch inventory")
        branch = {}
        for row in record["stops"]:
            path = base / f"{mode}-{row['step']}.npz"
            require(sha(path) == row["sha256"], "stop evidence digest mismatch")
            with np.load(path, allow_pickle=False) as data:
                arrays = {key: data[key] for key in ROW_SHAPES}
            rows_checked(arrays)
            check_side_minima(arrays, row)
            branch[row["step"]] = row, arrays
        windows[mode] = branch
    require(set(windows) == {"observed", "retained", "last_accepted_visual_target"}, "wrong modes")
    return windows


def expected_steps(plan, mode):
    require(mode in ("observed", "retained", "last_accepted_visual_target"), "unknown stop mode")
    return list(range(plan["comparison"][mode][0], plan["comparison"][mode][1] + 1))


def check_side_minima(arrays, row):
    require(np.array_equal(arrays["pair_gap"][:, FINGER_TABLE].min(axis=0), row["finger_table_min_m"])
            and int(np.count_nonzero(arrays["contacts"][:, 3])) == row["unplanned_contact_ticks"],
            "side order, geometry or contact count differs from source receipt")


def rejected(operation):
    try:
        operation()
    except ValueError:
        return True
    return False


def controls(plan, windows, calc):
    row, arrays = windows["observed"][1639]
    path = VerticalClearancePath("control", "control", "LIFT", (0.0, 0.0, 0.125),
                                (0.0, 0.0, 0.25), 0.08)
    equal = [(0.001, 0.0, 0.125), (0.0, 0.0, 0.125 - 0.001), (0.0, 0.0, 0.25 + 0.005)]
    beyond = [(np.nextafter(x, math.inf), y, z) for x, y, z in equal[:1]]
    beyond += [(0.0, 0.0, np.nextafter(equal[1][2], -math.inf)),
               (0.0, 0.0, np.nextafter(equal[2][2], math.inf))]
    switched = arrays["pair_gap"].copy()
    switched[:, FINGER_TABLE] = switched[:, FINGER_TABLE[::-1]]
    missing = arrays["tcp"][:-1]
    nonfinite = arrays["tcp"].copy()
    nonfinite[0, 1] = np.nan
    moved_origin = VerticalClearancePath("control","control","LIFT",(0.002,0.0,0.125),
                                        (0.002,0.0,0.25),0.08)
    continued = [(0.0, 0.0, 0.127), (0.0, 0.0, 0.125)]
    result = {
        "wrong_mode": rejected(lambda: expected_steps(plan, "swapped")),
        "shifted_start_changes_inventory": expected_steps(plan, "observed") != list(range(1633, 1642)),
        "missing_row": rejected(lambda: rows_checked(arrays | {"tcp": missing})),
        "nonfinite_row": rejected(lambda: rows_checked(arrays | {"tcp": nonfinite})),
        "side_swap": rejected(lambda: check_side_minima(arrays | {"pair_gap": switched}, row)),
        "threshold_equality": all(calc(path, [p], 0, 0.125)[0] is None for p in equal),
        "past_threshold": all(calc(path, [p], 0, 0.125)[0] is not None for p in beyond),
        "wrong_origin_changes_classification": calc(moved_origin, [equal[0]], 0, 0.125)[0] is None
        and calc(path, [(0.002, 0.0, 0.125)], 0, 0.125)[0] is not None,
        "preserve_peak": calc(path, continued, 0, 0.125)[0]["step"] == 1
        and calc(path, continued[1:], 1, 0.125)[0] is None,
    }
    require(all(result.values()), "registered guard controls failed")
    return result


def reduce(plan, calc):
    roots = {key: Path(value) for key, value in plan["roots"].items()}
    for token, expected in plan["inputs_sha256"].items():
        first, suffix = token.split("/", 1)
        require(sha(roots.get(first, Path(first)) / suffix) == expected, f"wrong source: {token}")
    receipt = read(roots["S"] / "receipt.json")
    require(receipt["case"] == "cvfix-t01" and receipt["terminal"] == TERMINAL_TICK, "wrong t01")
    for name, expected in receipt["original_sha256"].items():
        require(sha(roots["T"] / name) == expected, f"wrong original: {name}")
    windows = stop_windows(plan, roots["S"], receipt)
    origin0 = windows["observed"][TERMINAL_TICK]
    for kind in ("retained", "last_accepted_visual_target"):
        require(windows[kind][TERMINAL_TICK][0]["sha256"] == origin0[0]["sha256"], "nonidentical delay-zero stop")

    truth = read(roots["T"] / "offline-truth.json")
    original = {row["physics_step"]: row for row in truth["samples"]}
    audit = [row for row in read(roots["T"] / "local-clearance.json")["rows"] if row["skill"] == "LIFT"]
    require([(r["physics_step"],r["phase"],r["status"]) for r in audit] ==
            [(1632,"PRE","CLEAR"),(1632,"FEEDBACK","CLEAR"),(1640,"FEEDBACK","UNKNOWN")], "unexpected gate trace")
    require(len({r["frame_id"] for r in audit}) == 3, "duplicate gate frame")
    for r in audit:
        measured = original[r["physics_step"]]
        require(r["sim_time_s"] == measured["sim_time_s"]
                and r["robot"]["tcp_position_m"] == measured["tcp_position_m"], "invalid camera/physics join")
    stop = audit[-1]["evidence"]["short_motion"]
    require(stop["limiting_pair"] == ["left_finger_geom", "table"]
            and round(stop["minimum_gap_m"] * 1000, 3) == -0.388, "different refusal")
    commands = read(roots["T"] / "backend-commands.json")
    terminal = [cmd["type"] for cmd in commands if cmd["physics_step"] == TERMINAL_TICK and cmd["accepted"]]
    require(terminal == ["hold_current_joints", "hold_current_joints", "emergency_stop"], "different terminal")
    start = tuple(original[ORIGIN_TICK]["tcp_position_m"])
    goal = tuple(audit[0]["target_xyz"][a] for a in "xyz")
    require(all(tuple(r["target_xyz"][a] for a in "xyz") == goal for r in audit), "target drift")
    path = VerticalClearancePath(truth["episode"], "original-t01-lift", "LIFT", start, goal, 0.08)

    phase_deltas = {}
    for step, (_, arr) in windows["observed"].items():
        measured = original[step]
        require(np.array_equal(arr["q"][0, :9], measured["joint_positions_rad"] + measured["finger_positions_m"])
                and np.array_equal(arr["qvel"][0,:9], measured["joint_velocities_rad_s"] + measured["finger_velocities_m_s"]),
                "stop pose does not bind the native feedback step")
        phase_deltas[step] = math.dist(arr["tcp"][0], measured["tcp_position_m"])

    branches = []
    for mode, anchors in windows.items():
        for step, (receipt_row, arrays) in anchors.items():
            prefix_end = min(step, TERMINAL_TICK)
            prefix = [original[t]["tcp_position_m"] for t in range(ORIGIN_TICK, prefix_end + 1)]
            prefix_data, peak = summarize_path(calc, path, prefix, ORIGIN_TICK, start[2])
            extended = [anchors[t][1]["tcp"][0] for t in range(TERMINAL_TICK + 1, step + 1)]
            extended_data, peak = summarize_path(calc, path, extended, TERMINAL_TICK + 1, peak)
            stop_data, _ = summarize_path(calc, path, arrays["tcp"], step, peak)
            if stop_data["first_event"]:
                stop_data["first_event"]["stop_row"] = stop_data["first_event"]["step"] - step
            gap = arrays["pair_gap"][:, FINGER_TABLE]
            minimum_index = gap.argmin(axis=0)
            branches.append({
                "mode": mode, "anchor_step": step, "sha256": receipt_row["sha256"],
                "prefix": prefix_data, "continued": extended_data, "stop": stop_data,
                "finger_table": [
                    {"finger": side, "gap_mm": float(gap[i,k] * 1000), "stop_row": int(i),
                     "step": int(step+i), "raw_engine_at_gap_m": float(arrays["engine_gap"][i,FINGER_TABLE[k]]),
                     "engine_min_m": float(arrays["engine_gap"][:,FINGER_TABLE[k]].min())}
                    for k,(i,side) in enumerate(zip(minimum_index, ("left","right"), strict=True))
                ],
                "unplanned_contact_states": receipt_row["unplanned_contact_ticks"],
            })
    require(len(branches) == 27, "lost branches")
    extremum = min((g | {"mode": row["mode"], "anchor_step": row["anchor_step"], "sha256": row["sha256"]}
                    for row in branches for g in row["finger_table"]), key=lambda g:g["gap_mm"])
    require(round(extremum["gap_mm"], 3) == 14.480
            and (extremum["mode"],extremum["anchor_step"],extremum["stop_row"]) == ("observed",1639,2),
            "historical finger/table control changed")
    return {
        "case": "cvfix-t01", "source_gate": [{k:r[k] for k in ("physics_step","phase","status","frame_id")} for r in audit],
        "refused_gap_mm": stop["minimum_gap_m"] * 1000,
        "origin_m": start, "target_m": goal, "stop_state_rows": 6507,
        "stop_tick0_tcp_recomputed_vs_native_l2_m": phase_deltas, "minimum_finger_table": extremum,
        "controls": controls(plan, windows, calc), "branches": branches,
        "new_exposures": 0, "new_integration_steps": 0, "online_qualification": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("method", choices=("scalar", "vector"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = reduce(read(HERE / "plan.json"), scalar if args.method == "scalar" else vector)
    with args.output.open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
