"""Verify the tail's return predicate and stop geometry from sealed arrays."""

import argparse
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np
import qualify_tail as tail
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry
from scripts.graduation.perception_io import read, sha, write

from cloud_edge_robot_arm.simulation.mujoco.clearance_control import _rotation_error

require = tail.require


def indexed(path, phase):
    rows = {int(k): v for k, v in read(path).items()}
    require(sorted(rows) == list(range(min(rows), max(rows) + 1)), "phase gaps")
    require(
        all(v["tick"] == k and v["phase"] == phase for k, v in rows.items()), "phase tags differ"
    )
    return rows


def proof(result, moving, hold, bridge):
    previous = read(tail.earlier.OUT / "native/normal.json")
    start = previous[0]
    ground_z = tail.earlier.PLAN["original_unchanged_grounded_z_m"]
    position = np.array([*start["tcp"][:2], ground_z])
    quat = np.array(tail._DOWNWARD)
    registered = {e["tick"]: e for e in result["conditional_feedback"]}
    expected = list(range(tail.ANCHOR, max(moving) + 1, tail.V))
    require(expected == sorted(registered), "wrong feedback grid")
    r = result["return"]
    continuous = 0
    eligible = []
    prehistory = read(tail.earlier.OUT / "native/normal.json")
    prefix = {row["tick"]: row for row in prehistory if row["tick"] < tail.ANCHOR}
    # The exact TCP pose cache is archived for every terminal sample. By the
    # earliest return, the streak starts well inside this retained window.
    require(
        tail.PLAN["earliest_condition_tick"] - tail.ANCHOR > 3 * tail.V, "short feedback prefix"
    )
    for k, row in moving.items():
        if k in registered:
            e = registered[k]
            error = float(np.linalg.norm(position - np.asarray(row["site_position"])))
            angle = float(
                np.degrees(np.linalg.norm(_rotation_error(quat, np.asarray(row["site_rotation"]))))
            )
            continuous = (
                continuous + 1
                if (
                    error <= tail.PLAN["position_max_m"]
                    and angle <= tail.PLAN["orientation_max_deg"]
                )
                else 0
            )
            require(
                e["position_error_m"] == error and e["orientation_error_deg"] == angle,
                "cached feedback error differs",
            )
            if k >= tail.ANCHOR + 3 * tail.V or continuous == 0:
                require(
                    min(e["conditional_consecutive_pose_matches"], tail.PLAN["stable_samples"])
                    == min(continuous, tail.PLAN["stable_samples"]),
                    "inaccurate stability predicate",
                )
        if (
            (k - tail.ENTRY) % tail.C == 0
            and (k - tail.ENTRY) * (1 / 240) >= r["reference_duration_s"] + r["reference_settle_s"]
            and continuous >= tail.PLAN["stable_samples"]
            and abs(np.array(row["controller_command_velocity"])).max()
            <= bridge.LIMIT_A * tail.C / 240
        ):
            eligible.append(k)
    at = max(moving)
    require(
        eligible == [at] and at == min(hold) == r["condition_tick"], "conditional return not unique"
    )
    before, after = moving[at], hold[at]
    require(
        before["q"] == after["q"]
        and before["dq"] == after["dq"]
        and before["t"] == after["t"]
        and before["contacts"] == after["contacts"]
        and before["retained_command"] == after["retained_command"] == r["command_positions_rad"]
        and after["command_seq"] == before["command_seq"] + 1
        and after["command_kind"] == "joint_target"
        and after["retained_velocity"] == [0.0] * 7,
        "duplicate final command did not preserve physical phase/target",
    )
    peak = max(x["tcp"][2] for x in prefix.values())
    pos0 = np.asarray(start["tcp"])
    path = tail.VerticalClearancePath(
        task_id=tail.earlier.PLAN["only_case"],
        step_id="LIFT",
        skill="LIFT",
        start_m=tuple(pos0),
        target_m=tuple(position),
        minimum_height_m=0.08,
    )
    for row in [*moving.values(), *hold.values()]:
        require(
            set(map(tuple, row["contacts"])) == tail.earlier.BILATERAL
            and row["pending_count"] == 0,
            "physical guard data differs",
        )
        path.check_position(row["tcp"], peak_z=peak)
        peak = max(peak, row["tcp"][2])
    require(
        len(hold) == tail.HOLD + 1
        and result["hold_feedback_candidate_ticks"]
        == list(range(at + tail.V, at + tail.HOLD + 1, tail.V))
        and max(hold) == result["hold_end_tick"]
        and result["last_motion_to_first_hold_gap_ticks"] == at + tail.V - max(registered),
        "hold guide differs",
    )
    require(
        all(
            row["command_seq"] == after["command_seq"]
            and row["retained_command"] == after["retained_command"]
            for row in hold.values()
        ),
        "hold commands changed",
    )
    return float(hold[max(hold)]["cube"][2] - start["cube"][2])


def read_branch(dest, phase, tick, pin, row):
    path = dest / phase / f"stop-{tick}.npz"
    contact = path.with_suffix(".json")
    require(
        sha(path) == pin["state_sha256"] and sha(contact) == pin["contacts_sha256"],
        "stop file drift",
    )
    contacts = read(contact)
    with np.load(path, allow_pickle=False) as f:
        q, dq, ctrl = f["q"], f["dq"], f["ctrl"]
    require(
        len(q) == len(dq) == len(ctrl) == len(contacts) == tail.STOP + 1
        and np.array_equal(q[0], row["q"])
        and np.array_equal(dq[0], row["dq"]),
        "stop origin or length mismatch",
    )
    return q, dq, contacts


def check(reader):
    tail.checked_inputs()
    dest = tail.OUT / "native"
    result = read(dest / "result.json")
    moving = indexed(dest / "motion.json", "motion")
    hold = indexed(dest / "retained_hold.json", "retained_hold")
    bridge = tail.earlier.module(tail.earlier.source("original/screen_braking.py"))
    lift = proof(result, moving, hold, bridge)
    _, gate = tail.earlier.prepare_profiles(MotionGeometry(Model(bridge.ASSET)))
    bins = {}
    for key, pin in result["archives"].items():
        phase, tick = key.split("/")
        tick = int(tick)
        rows = moving if phase == "motion" else hold
        bins[phase, tick] = read_branch(dest, phase, tick, pin, rows[tick])
    expected = {("motion", k) for k in range(tail.END + 1, max(moving) + 1)}
    expected.update(("retained_hold", k) for k in hold)
    require(set(bins) == expected, "missing or unknown native trigger")
    rows_by_scope = {"motion": moving, "retained_hold": hold, "handoff_overlap": moving | hold}
    keys = set()
    seen = Counter()
    world, relative = [], []
    for row in result["comparisons"]:
        phase = row["phase"]
        key = phase, row["anchor"], row["trigger"]
        require(key not in keys, "repeated comparison")
        keys.add(key)
        underlying = "retained_hold" if phase == "handoff_overlap" else phase
        reference = tail.compare(
            gate,
            rows_by_scope[phase],
            row["anchor"],
            row["trigger"],
            bins[underlying, row["trigger"]],
            phase,
        )
        require(
            reference == row and tail.acceptable(reference), f"cold stop comparison differs: {key}"
        )
        seen[phase, row["anchor"]] += 1
        world.append(row["world_min_m"])
        relative.append(row["relative_min_m"])
    expected_rows = set()
    for phase, grid in [
        ("motion", range(tail.ANCHOR, max(moving) + 1, tail.V)),
        ("retained_hold", range(min(hold), max(hold) + 1, tail.V)),
    ]:
        last = max(moving) if phase == "motion" else max(hold)
        begin = tail.END + 1 if phase == "motion" else min(hold)
        expected_rows.update(
            (phase, k, n) for k in grid for n in range(max(k, begin), min(k + tail.V, last) + 1)
        )
    last_feedback = result["last_motion_feedback_tick"]
    expected_rows.update(
        ("handoff_overlap", last_feedback, k) for k in range(min(hold), last_feedback + tail.V + 1)
    )
    require(expected_rows == keys, "a registered stop window is missing")
    require(
        result["total_cpu"] == result["normal_cpu"] + len(bins) * tail.STOP, "lost integrations"
    )
    write(
        tail.OUT / f"{reader}.json",
        {
            "compared": len(keys),
            "stops": len(bins),
            "normal_steps": result["normal_cpu"],
            "integrations": result["total_cpu"],
            "conditional_return_tick": max(moving),
            "hold_end_tick": max(hold),
            "end_hold_lift_m": lift,
            "minimum_world_m": min(world),
            "minimum_relative_m": min(relative),
            "moving_to_hold_gap_ticks": result["last_motion_to_first_hold_gap_ticks"],
            "new_live_exposures": 0,
            "new_cpu_steps_in_reader": 0,
            "code_sha256": sha(Path(__file__)),
            "native_run_code_sha256": sha(Path(tail.__file__)),
            "sources_sha256": {
                name: sha(dest / name)
                for name in ("result.json", "motion.json", "retained_hold.json")
            },
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reader", choices=("reader-1", "reader-2"))
    args = parser.parse_args()
    with patch.multiple(
        mujoco,
        mj_step=tail.earlier.deny,
        mj_step1=tail.earlier.deny,
        mj_step2=tail.earlier.deny,
        Renderer=tail.earlier.deny,
        mjr_render=tail.earlier.deny,
    ):
        check(args.reader)
