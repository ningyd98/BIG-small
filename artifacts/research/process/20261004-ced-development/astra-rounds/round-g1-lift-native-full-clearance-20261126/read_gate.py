"""Verify the sealed current-clearance outcomes and their native command boundaries."""

import argparse
from collections import Counter

from gate_lift import HERE, LAST, OUT, PLAN, prior
from scripts.graduation.g1_complete_cv_handoff import binding_error
from scripts.graduation.perception_io import read, sha, write

ROOT = prior.ROOT
RESULT = OUT.parent / "readback.json"


def checked_sources():
    declared = read(OUT / "seal.json")
    for relative, expected in declared["sealed_sha256"].items():
        path = (OUT / relative).resolve()
        prior.require(
            path.is_relative_to(OUT) and sha(path) == expected,
            f"captured member differs: {relative}",
        )
    actual = read(OUT / "registration.json")
    prior.require(
        declared["registration_sha256"] == sha(OUT / "registration.json")
        and actual["plan_sha256"] == sha(HERE / "plan.json")
        and actual["driver_sha256"] == sha(HERE / "gate_lift.py"),
        "unbound driver, plan or seal",
    )
    return declared


def verify_handoff(robot, gate):
    handoff = robot["handoff"]
    # binding_error only reads these two immutable frame attributes.
    from types import SimpleNamespace

    exposure = SimpleNamespace(frame_id=gate["frame_id"], checksum_sha256=gate["checksum_sha256"])
    prior.require(
        binding_error(handoff, gate["skill"], gate["phase"], exposure) is None,
        "packet did not satisfy original native identity/entry binding",
    )
    prior.require(
        handoff["current_step"] == gate["step"]
        and handoff["last_command_seq"]
        == robot["native_last_command_seq"]
        == gate["native_last_command_seq"],
        "live command sequence changed",
    )
    return handoff["entry_step"]


def slot_report(case):
    folder = OUT / case
    r = read(folder / "sensor-receipt.json")
    shutter = read(folder / "rgbd-index.json")
    labels = read(folder / "offline-physics.json")
    commands = read(folder / "native-commands.json")
    gate = read(folder / "clearance-gate.json")
    frames = {p["robot"]["frame_id"]: p["robot"] for p in shutter["rows"]}
    truth = {p["frame_id"]: p for p in labels["frame_labels"]}
    prior.require(
        len(frames) == len(shutter["rows"]) == len(truth),
        f"duplicated or missing shutter labels in {case}",
    )
    totals = Counter()
    stages = {}
    withheld = []
    samples = []
    gaps = []
    after = []
    gate_refusals = []
    feedback_steps = []
    handoff_entry_by_stage = {}
    for evidence in gate["checks"]:
        exposure = evidence["frame_id"]
        robot, label = frames[exposure], truth[exposure]
        phase, skill = evidence["phase"], evidence["skill"]
        prior.require(
            evidence["step"] == label["physics_step"] == robot["physics_step"]
            and evidence["checksum_sha256"] == label["checksum_sha256"] == robot["checksum_sha256"]
            and robot["sim_time_s"] == robot["camera_encoder_sim_time_s"]
            and evidence["gate_finish_ns"] >= evidence["capture_begin_ns"],
            "receipt frame, physical label, sequence or acquisition clock differs",
        )
        kind = f"{skill}/{phase}"
        stages.setdefault(kind, Counter())[evidence["status"] or "OBSERVED"] += 1
        if phase != "POST":
            entry = verify_handoff(robot, evidence)
            prior.require(
                handoff_entry_by_stage.setdefault(skill, entry) == entry,
                "one stage mixed registration entry states",
            )
        if evidence["status"] in ("BLOCKED", "UNKNOWN"):
            gate_refusals.append(evidence)
        hand = evidence["current"].get("payload_observation", {})
        if hand.get("relation") == "held" or phase == "POST":
            contacts = {frozenset(p) for p in label["touching"]}
            if all(
                frozenset((pad, "object_geom")) in contacts
                for pad in ("left_finger_geom", "right_finger_geom")
            ):
                totals["physical_bilateral_observed"] += 1
        if phase != "FEEDBACK":
            continue
        feedback_steps.append(evidence["step"])
        totals["lift_feedback"] += 1
        totals[f"lift_{evidence['status'].lower()}"] += 1
        clearance = evidence["current"].get("short_motion", {})
        if "minimum_gap_m" in clearance:
            gaps.append((clearance["minimum_gap_m"], clearance.get("limiting_pair")))
        if evidence.get("released_to_boundary"):
            prior.require(
                evidence["status"] == "CLEAR"
                and evidence["sample_ik_ms"] <= PLAN["maximum_feedback_ms"]
                and evidence["before_next_boundary_ms"] <= PLAN["maximum_feedback_ms"]
                and evidence["next_boundary_ns"] >= evidence["gate_finish_ns"],
                "native motion continued through unsafe or late feedback",
            )
            samples.append(evidence)
        else:
            withheld.append(evidence)
    prior.require(
        len(feedback_steps) == gate["sample_count"] <= PLAN["max_lift_feedback_per_case"]
        and all(b - a == 8 for a, b in zip(feedback_steps[:-1], feedback_steps[1:], strict=True)),
        f"feedback cap or native steps changed: {case}",
    )
    stop = gate_refusals[0] if gate_refusals else withheld[0] if withheld else None
    command_types = {"joint_target", "gripper"}
    if stop is not None:
        after = [
            cmd["command_seq"]
            for cmd in commands
            if cmd["accepted"]
            and cmd["type"] in command_types
            and cmd["command_seq"] > stop["native_last_command_seq"]
        ]
        prior.require(not after, f"accepted drive command after recorded refusal: {case}")
    stats = {
        "case": case,
        "stages": stages,
        "counts": dict(totals),
        "repeated_initial_pose": r["slot"]["center_m"],
        "controller_calls": sum(a["controller_called"] for a in r["actions"]),
        "actual_termination": r["termination"],
        "emergency_stop": r["native_emergency_stop"],
        "native_physics_steps": r["physics_steps"],
        "original_camera_calls": len(r["camera_calls"]),
        "reference_projections": Counter(read(folder / "reference-projections.json")["passes"]),
        "minimum_loaded_gap_while_checked": min(gaps, default=None, key=lambda x: x[0]),
        "max_feedback_before_boundary_ms": max(
            (r["before_next_boundary_ms"] for r in samples), default=None
        ),
        "boundary_releases": len(samples),
        "drive_commands_after_first_refusal": after,
        "first_refusal_or_cutoff": (
            {
                k: stop.get(k)
                for k in (
                    "step",
                    "skill",
                    "phase",
                    "status",
                    "reason",
                    "next_boundary",
                    "sample_ik_ms",
                    "before_next_boundary_ms",
                )
            }
            if stop
            else None
        ),
        "full_80_checked_prefix": r["termination"] == LAST
        and totals["lift_clear"] == 80
        and len(samples) == 79
        and len(withheld) == 1,
    }
    return stats


def run():
    seal = checked_sources()
    outcomes = {case: slot_report(case) for case in seal["cases"]}
    prior.require(
        len(outcomes) <= PLAN["max_slots"] and all(c in PLAN["slots"] for c in outcomes),
        "unregistered trials appeared",
    )
    write(
        RESULT,
        {
            "seal_sha256": sha(OUT / "seal.json"),
            "outcomes": outcomes,
            "attempted_without_terminal_receipt": sorted(
                p.name for p in OUT.iterdir() if p.is_dir() and p.name not in outcomes
            ),
            "whole_system": 0,
            "formal": 0,
            "hardware": 0,
            "remote": 0,
            "independent_formal_scoring": 0,
        },
    )


if __name__ == "__main__":
    import argparse

    cli = argparse.ArgumentParser(description=__doc__)
    cli.parse_args()
    run()
