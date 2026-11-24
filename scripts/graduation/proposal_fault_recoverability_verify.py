"""Cross-check public T5 results from sealed scalar states, commands and RGB-D originals."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from scripts.graduation.perception_io import pinned, sha, write

from cloud_edge_robot_arm.datasets.rgbd.models import TrajectoryFrame


def check(condition, reason):
    if not condition:
        raise ValueError(reason)


def durations(rows, first):
    z0 = rows[first]["object_position_m"][2]
    hold = placed = None
    longest_hold = longest_placed = terminal_placed = lift_max = 0.0
    for row in rows[first:]:
        z = row["object_position_m"][2] - z0
        lift_max = max(z, lift_max)
        stable = (
            math.hypot(*row["object_linear_velocity_m_s"]) <= 0.02
            and math.hypot(*row["object_angular_velocity_rad_s"]) <= 0.5
        )
        contacts = {frozenset(pair) for pair in row["contact_pairs"]}
        fingers = [
            frozenset((finger, "object_geom")) in contacts
            for finger in ("left_finger_geom", "right_finger_geom")
        ]
        t = row["sim_time_s"]
        if stable and all(fingers) and not row["gripper_open"] and z >= 0.05 - 1e-12:
            hold = t if hold is None else hold
            longest_hold = max(longest_hold, t - hold)
        else:
            hold = None
        rotation = row["object_geom_rotation_row_major"]
        half = row["object_half_extent_m"]
        inside = all(
            abs(row["object_position_m"][k] - row["region_center_m"][k])
            + sum(abs(rotation[3 * k + i]) * half[i] for i in range(3))
            <= row["region_half_extent_m"][k] + 1e-9
            for k in (0, 1)
        )
        if (
            longest_hold >= 0.5 - 1e-12
            and stable
            and not any(fingers)
            and row["gripper_open"]
            and abs(row["object_bottom_z_m"] - row["table_top_m"]) <= 0.005
            and inside
        ):
            placed = t if placed is None else placed
            terminal_placed = t - placed
            longest_placed = max(longest_placed, terminal_placed)
        else:
            placed = None
            terminal_placed = 0.0
    return lift_max, longest_hold, longest_placed, terminal_placed


def verify(raw, allocation, allocation_sha, report, report_sha, out):
    alloc = pinned(allocation, allocation_sha)
    result = pinned(report, report_sha)
    check(result["allocation_sha256"] == allocation_sha, "unbound result")
    verified = []
    for case, row in zip(alloc["cases"], result["teacher_cases"], strict=True):
        root = raw / case["id"]
        seal = pinned(root / "seal.json", row["seal_sha256"])
        check(sha(root / "begin.json") == seal["files"]["begin.json"], "begin seal")

        def source(name, directory=root, pins=seal["files"]):
            return pinned(directory / name, pins[name])

        header = source("source/attempt.json")
        observations = source("source/physical-observations.json")
        actuators = source("source/actuator-provenance.json")["steps"]
        commands = source("source/commands.json")
        events = source("source/fault-events.json")
        teacher = source("source/teacher-actions.json")
        check(
            header["episode_id"] == row["episode"]
            and len(observations) == len(actuators) + 1 == row["states"],
            "independent reset to terminal state/actuator coverage",
        )
        pairs = None
        for i, s in enumerate(observations):
            check(
                s["physics_step"] == i
                and s["episode_id"] == row["episode"]
                and abs(s["sim_time_s"] - i * header["physics_dt_s"]) < 1e-9,
                "wrong physics clock",
            )
            if i:
                ctl = actuators[i - 1]
                check(
                    ctl["physics_step"] == i
                    and ctl["episode_id"] == row["episode"]
                    and ctl["sim_time_s"] == observations[i - 1]["sim_time_s"],
                    "incorrect PRE actuator clock",
                )
            measured = {(x, y) for x, y, _ in s["self_collision_distances_m"]}
            pairs = measured if pairs is None else pairs
            check(len(pairs) == 33 and measured == pairs, "collision pair coverage changed")
        lift, held, placed, tail = durations(observations, header["recovery_start_step"])
        actual = row["independent_outcome"]
        check(
            all(
                math.isclose(x, actual[k], rel_tol=0, abs_tol=1e-8)
                for x, k in (
                    (lift, "measured_lift_m"),
                    (held, "hold_s"),
                    (placed, "placed_stable_s"),
                )
            ),
            "independent physical durations differ",
        )
        achieved = (
            lift >= 0.05 - 1e-12
            and held >= 0.5 - 1e-12
            and tail >= 1.0 - 1e-12
            and actual["safety_assessment"] == "SCOPED_NO_VIOLATION"
        )
        check(actual["success"] == achieved, "terminal physical task label differs")
        check(
            [c["backend_record"]["command_seq"] for c in commands]
            == list(range(1, len(commands) + 1)),
            "command ordinal coverage",
        )
        releases = [
            c["backend_record"]["command_seq"]
            for c in commands
            if c["type"] == "gripper" and c["accepted"] and c["backend_record"]["target_open"]
        ]
        check(releases == row["accepted_gripper_open_sequences"], "actual release dispatch count")
        frames = [TrajectoryFrame.model_validate(f) for f in source("teacher-frames.json")]
        for a, b in zip(frames, frames[1:], strict=False):
            check(
                a.next_observation.checksum_sha256 == b.observation.checksum_sha256,
                "broken RGB-D chain",
            )
        last_step = header["recovery_start_step"]
        trajectory = {f.action.action_id: f for f in frames}
        unframed = {a["action_id"] for a in source("unframed-actions.json")}
        for a in teacher:
            check(
                a["start_step"] == last_step and a["episode_id"] == row["episode"],
                "action step relationship",
            )
            f = trajectory.get(a["action_id"])
            if f is not None:
                check(
                    f.observation.episode_id == row["episode"]
                    and f.observation.sim_time_s == observations[a["start_step"]]["sim_time_s"]
                    and f.next_observation.sim_time_s == observations[a["end_step"]]["sim_time_s"],
                    "frame/action timestamp or episode mismatch",
                )
            else:
                check(a["action_id"] in unframed, "action missing both frame and lost-frame record")
            last_step = a["end_step"]
        start, finish = events
        delta = (
            observations[finish["physics_step"]]["object_position_m"][1]
            - observations[start["physics_step"]]["object_position_m"][1]
        )
        check(
            start["direction_y"] == row["direction"]
            and delta == row["fault"]["signed_delta_y_m"]
            and delta * row["direction"] >= 0.005,
            "fault direction or measured displacement",
        )
        verified.append(
            {
                "ordinal": case["ordinal"],
                "states": len(observations),
                "actuators": len(actuators),
                "commands": len(commands),
                "teacher_transitions_checked": len(frames),
                "actions_without_transition": len(unframed),
                "unique_rgbd_acquisitions": len(
                    {o.frame_id for f in frames for o in (f.observation, f.next_observation)}
                ),
                "signed_displacement_m": delta,
                "maximum_lift_m": lift,
                "longest_hold_s": held,
                "longest_placement_s": placed,
                "terminal_placement_s": tail,
                "accepted_release_command_sequences": releases,
            }
        )
    write(
        out,
        {
            "schema": "graduation.proposal-fault-independent-verification.v1",
            "status": "PASS",
            "allocation_sha256": allocation_sha,
            "results_sha256": report_sha,
            "verifier_sha256": sha(Path(__file__)),
            "cases": verified,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("allocation", type=Path)
    parser.add_argument("allocation_sha")
    parser.add_argument("result", type=Path)
    parser.add_argument("result_sha")
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    verify(args.raw, args.allocation, args.allocation_sha, args.result, args.result_sha, args.out)
