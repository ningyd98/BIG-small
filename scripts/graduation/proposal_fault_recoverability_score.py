"""Read frozen fault cases using independent physical states and the original T5 audit."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from scripts.graduation.perception_io import read, sha

from cloud_edge_robot_arm.research.protocol_evidence import RECOVERY_FILES, _recovery, _trace
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    evaluate_evidence,
    sample_physical_observation,
)

CRITERIA = CompletionCriteria("object", "target_region")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def check_actuators(states, controls):
    require(len(controls) == len(states) - 1, "incomplete PRE-actuator denominator")
    for index, control in enumerate(controls, 1):
        previous = states[index - 1]
        require(
            control["episode_id"] == previous.episode_id
            and type(control["physics_step"]) is int
            and control["physics_step"] == states[index].physics_step == index
            and abs(control["sim_time_s"] - previous.sim_time_s) <= 1e-9,
            "wrong actuator step, episode or PRE clock",
        )


def measured_fault(states, events, fault, teacher_start):
    (started,) = [r for r in events if r["event"] == "TARGET_MOTION_STARTED"]
    (finished,) = [r for r in events if r["event"] == "TARGET_MOTION_FINISHED"]
    left, right = started["physics_step"], finished["physics_step"]
    params = fault["parameters"]
    require(
        0 <= left < right <= teacher_start < len(states)
        and fault["fault_type"] == "TARGET_MOTION"
        and all(started.get(k) == v for k, v in params.items()),
        "fault direction, inputs or end mismatch",
    )
    first, last = states[left], states[right]
    require(
        first.physics_step == left
        and last.physics_step == right
        and first.sim_time_s == started["sim_time_s"]
        and last.sim_time_s == finished["sim_time_s"],
        "fault does not join original physical timestamps",
    )
    signed = last.object_position_m[1] - first.object_position_m[1]
    return {
        "start_step": left,
        "end_step": right,
        "start_sim_s": first.sim_time_s,
        "end_sim_s": last.sim_time_s,
        "signed_delta_y_m": signed,
        "directional_displacement_m": signed * params["direction_y"],
        "teacher_start_step": teacher_start,
        "teacher_start_sim_s": states[teacher_start].sim_time_s,
    }


def read_actions(bundle, states):
    actions = read(bundle / "teacher-actions.json")
    commands = read(bundle / "commands.json")
    offset = 1
    rows = []
    for action in actions:
        require(
            action["episode_id"] == states[0].episode_id
            and action["command_seq_start"] == offset
            and action["start_step"] <= action["end_step"] < len(states),
            "foreign action or broken half-open sequence",
        )
        upper = action["command_seq_end"]
        require(type(upper) is int and upper >= offset, "invalid half-open command interval")
        joined = commands[offset - 1 : upper - 1]
        require(len(joined) == upper - offset, "truncated command interval")
        for pos, item in enumerate(joined, offset):
            original = item["backend_record"]
            require(
                item["action_id"] == action["action_id"]
                and original["command_seq"] == pos
                and item["episode_id"] == original["episode_id"] == states[0].episode_id
                and original["physics_step"] == item["physics_step"]
                and action["start_step"] <= item["physics_step"] <= action["end_step"]
                and original["sim_time_s"] == states[item["physics_step"]].sim_time_s,
                "command identity or time does not align",
            )
        release = [
            item["backend_record"]["command_seq"]
            for item in joined
            if item["type"] == "gripper"
            and item["accepted"]
            and item["backend_record"].get("target_open") is True
        ]
        rows.append(
            {
                "type": action["action_type"],
                "start_step": action["start_step"],
                "end_step": action["end_step"],
                "command_half_open": [offset, upper],
                "success": action["result"]["success"],
                "release_gripper_seq": release,
            }
        )
        offset = upper
    require(offset == len(commands) + 1, "unassigned commands")
    return rows, len(commands)


def audit(bundle: Path, row, fault, rules):
    header = read(bundle / "attempt.json")
    states = _trace(bundle, row, header)
    controls = read(bundle / "actuator-provenance.json")
    check_actuators(states, controls["steps"])
    require(controls["episode_id"] == header["episode_id"], "actuator header mismatch")
    events = read(bundle / "fault-events.json")
    injection = measured_fault(states, events, fault, header["recovery_start_step"])
    actions, command_count = read_actions(bundle, states)
    samples = [sample_physical_observation(s, CRITERIA) for s in states]
    outcome = evaluate_evidence(
        samples, CRITERIA, evaluation_start_step=header["recovery_start_step"]
    )
    require(
        all(
            math.isfinite(s.object_linear_speed_m_s) and math.isfinite(s.object_angular_speed_rad_s)
            for s in samples
        ),
        "nonfinite physical samples",
    )
    try:
        _, proof = _recovery(bundle, row, fault, rules)
        require(
            proof["independent_outcome"]["status"] == outcome.status
            and outcome.success
            and math.isclose(
                proof["measured_displacement_m"], injection["directional_displacement_m"]
            ),
            "independent reader and qualified outcome disagree",
        )
    except ValueError as exc:
        status, reason = "REJECTED", str(exc)
    else:
        status, reason = "PROVEN", None
    release_commands = [s for a in actions for s in a["release_gripper_seq"]]
    measured_time = states[-1].sim_time_s - injection["start_sim_s"]
    return {
        "status": status,
        "audit_rejection": reason,
        "episode": header["episode_id"],
        "group": row["scene"]["group_id"],
        "scene_hash": row["scene_hash"],
        "source_sha256": {n: sha(bundle / n) for n in RECOVERY_FILES},
        "fault": injection,
        "measured_minimum_displacement_met": injection["directional_displacement_m"]
        >= rules["minimum_measured_displacement_m"],
        "reset_xyz_m": list(states[0].object_position_m),
        "states": len(states),
        "actuators": len(controls["steps"]),
        "terminal_step": states[-1].physics_step,
        "terminal_sim_s": states[-1].sim_time_s,
        "commands": command_count,
        "actions": actions,
        "release_action_count": sum(a["type"] == "RELEASE" for a in actions),
        "accepted_gripper_open_sequences": release_commands,
        "repeated_release_commands": max(0, len(release_commands) - 1),
        "sim_s_from_fault_start": measured_time,
        "sim_s_from_teacher_start": states[-1].sim_time_s - injection["teacher_start_sim_s"],
        "failure_penalized_sim_s_from_fault_start": measured_time
        if status == "PROVEN"
        else rules["maximum_recovery_s"],
        "estop_samples": sum(s.estop_engaged for s in states),
        "collision_pairs": len(outcome.self_collision_checked_pairs),
        "independent_outcome": {
            k: v for k, v in asdict(outcome).items() if k != "self_collision_checked_pairs"
        },
    }


def count_cases(rows):
    require(
        [r["ordinal"] for r in rows] == [1, 2, 3, 4]
        and Counter(r["case"] for r in rows) == {"NORMAL": 2, "NO_CONTACT": 2},
        "unallocated/missing cases",
    )
    return {
        c: {"allocated": 2, "proven": sum(r["case"] == c and r["status"] == "PROVEN" for r in rows)}
        for c in ("NORMAL", "NO_CONTACT")
    }
