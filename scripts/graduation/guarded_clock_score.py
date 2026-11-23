"""Read r2's sealed pixel/truth join and replay its actual per-consumer timing."""

from __future__ import annotations

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.graduation import dynamic_vision_score as original
from scripts.graduation.perception_io import pinned, read, write


def source_ledger(roles, frames, stages):
    by_frame = {row["frame_id"]: row for row in frames}
    if len(frames) != len(by_frame):
        raise ValueError("duplicate source acquisition")
    actual = set()
    by_skill = {name: [] for name in stages}
    for event in roles:
        source = by_frame[event["frame_id"]]
        if any(
            source[key] != event[key] for key in ("physics_step", "frame_id", "checksum_sha256")
        ):
            raise ValueError("consumer did not reference the original step/frame/bytes")
        if event["acquired_for_this_role"]:
            if event["label"] != source["label"] or event["frame_id"] in actual:
                raise ValueError("acquisition was duplicated or renamed")
            actual.add(event["frame_id"])
        elif source["frame_id"] not in actual:
            raise ValueError("consumer preceded capture")
        skill = event["label"].partition("/")[0]
        if skill in by_skill and source["frame_id"] not in by_skill[skill]:
            by_skill[skill].append(source["frame_id"])
    if len(actual) != len(by_frame):
        raise ValueError("missing acquisition provenance")
    return by_skill


def stop_cause(run, audit):
    stop = run.get("stop")
    if not stop:
        return {"kind": "COMPONENT_SEQUENCE_RETURNED"}
    name = stop.get("skill")
    stage = next((row for row in run["actions"] if row["skill"] == name), {})
    kind = "ENGINEERING_BLOCKED"
    phase = stop["phase"]
    receipt = stage.get("return_evidence")
    decision = stage.get(phase.lower(), {})
    if (
        stop["type"] == "ComponentStopped"
        and phase in {"PRE", "POST"}
        and decision
        and (
            not decision["shield"]["allowed"]
            or not decision["shield"]["unmodified"]
            or any(c["status"] != "PASS" for c in decision["conditions"])
        )
    ):
        kind = "REGISTERED_CONDITION_OR_SHIELD_STOP"
    if (
        stop["type"] == "ComponentStopped"
        and phase == "CONTROLLER"
        and receipt
        and not receipt["success"]
        and receipt["action_result_present"]
    ):
        kind = "PRODUCTION_CONTROLLER_REPORTED_FAILURE"
    if (
        phase == "SERVO_REFERENCE"
        and stop["type"] == "ValueError"
        and stop["origin"] == "servo.py"
        and stop["reason"]
        in {
            "servo initial target/registered marker identity unavailable",
            "servo frame not fresh",
            "servo repeated frame",
        }
    ):
        kind = "SERVO_SOURCE_REJECTED"
    last = next((x for x in reversed(audit) if "shield" in x), None)
    trace = next((x["stop_stack"] for x in reversed(audit) if "stop_stack" in x), [])
    return {
        "kind": kind,
        "actual_stop": stop,
        "trace": trace,
        "last_shield": None
        if last is None
        else {
            "phase": last["phase"],
            "frame_id": last["frame_id"],
            "allowed": last["shield"]["allowed"],
            "decision": last["shield"]["decision"],
        },
    }


def report(raw, allocation, alloc_sha, out):
    a = pinned(allocation, alloc_sha)
    with TemporaryDirectory() as temp:
        first = Path(temp) / "base-score.json"
        original.score(raw, allocation, alloc_sha, first)
        result = read(first)
    seal = read(raw / "acquisition-seal.json")
    run = pinned(raw / "run.json", seal["run_sha256"])
    truth = pinned(raw / "offline-truth.json", seal["truth_sha256"])
    decision = pinned(raw / "decisions.json", result["source_seals"]["decisions_sha256"])
    audit = pinned(raw / "online-audit.json", seal["audit_sha256"])
    frames = decision["decisions"]
    by_id = {row["frame_id"]: row for row in frames}
    states = {row["physics_step"]: row for row in truth["samples"]}
    roles = run["frame_roles"]
    by_skill = source_ledger(roles, frames, a["case"]["visual_stages_in_order"])
    for event in roles:
        if event["episode_id"] != truth["episode"]:
            raise ValueError("foreign evidence role")
    for stage in result["stages"]:
        ids = by_skill[stage["skill"]]
        stage["sampling"] = original.subset([by_id[k] for k in ids], states)
        stage["physically_acquired_for_stage"] = sum(
            f["label"].startswith(stage["skill"] + "/") for f in frames
        )
        stage["distinct_frames_consumed"] = len(ids)
    clocks = run["action_clock_contexts"]
    candidates = {row["skill"]: row for row in run["grounding_contracts"]}
    actions = {row["skill"]: row for row in run["actions"]}
    last_feedback = {}
    for value in clocks:
        stage = actions[value["skill"]]
        src = by_id[value["frame_id"]]
        if (
            value["episode"] != truth["episode"]
            or value["origin"] != stage["entered_step"]
            or value["absolute"] != src["physics_step"]
            or value["absolute"] not in states
            or value["checksum_sha256"] != src["checksum_sha256"]
            or value["binding_sha256"] != candidates[value["skill"]]["binding_sha256"]
            or value["relative"] != value["absolute"] - value["origin"]
            or value["relative"] < 0
        ):
            raise ValueError("action clock differs from independent acquisition/trajectory")
        phase = value["phase"]
        if phase == "PRE" and value["relative"] != 0:
            raise ValueError("PRE does not start the recorded action")
        if phase in {"FEEDBACK", "POST"} and stage["dispatch_step"] != value["origin"]:
            raise ValueError("recorded dispatch differs from registered origin")
        if phase == "FEEDBACK":
            if value["absolute"] <= last_feedback.get(value["skill"], -1):
                raise ValueError("feedback physical step did not advance")
            last_feedback[value["skill"]] = value["absolute"]
        if phase == "POST" and value["absolute"] < stage["backend_return_step"]:
            raise ValueError("postcondition precedes measured controller return")
    accepted = {}
    for k in ("PRE", "POST", "FEEDBACK"):
        checked = [row["shield"] for row in audit if row.get("phase") == k and "shield" in row]
        accepted[k] = {"calls": len(checked), "allowed": sum(bool(z["allowed"]) for z in checked)}
    gates = {k: sum(k.lower() in s for s in run["actions"]) for k in ("PRE", "POST")}
    samples = [s for s in run["actions"] if s.get("dispatched")]
    motion_frames = [
        f
        for f in frames
        if any(
            f["label"].startswith(s["skill"] + "/")
            and s["dispatch_step"]
            <= f["physics_step"]
            <= s.get("controller_return_step", s["end_step"])
            for s in samples
        )
    ]
    timing_rows = [
        {"label": v["label"], "physics_step": v["physics_step"], "frame_id": v["frame_id"]}
        for v in roles
        if v["label"]
        in {
            "bootstrap",
            "registration-handoff",
            "registered_reference",
            "color_reference",
            "MOVE_ABOVE/PRE",
            "MOVE_ABOVE/PRE_conditions",
            "MOVE_ABOVE/PRE_Shield",
        }
    ]
    if gates["PRE"] and len({v["frame_id"] for v in timing_rows if v["label"] != "bootstrap"}) != 1:
        raise ValueError("first role consumers did not share the registered handoff")
    servo_callback = [
        float(r["sample_and_ik_s"])
        for row in audit
        if row.get("phase") == "servo"
        for r in row["control_samples"]
        if "sample_and_ik_s" in r
    ]
    result.update(
        {
            "schema": "graduation.guarded-clock-r2.development.v1",
            "observed_outcome": stop_cause(run, audit),
            "executor_entries": sum(bool(row.get("executor_entered")) for row in run["actions"]),
            "handler_returns": sum(
                bool(row.get("return_evidence", {}).get("action_result_present"))
                for row in run["actions"]
            ),
            "accepted_joint_target_commands": sum(
                row.get("accepted_command_types", {}).get("joint_target", 0)
                for row in run["actions"]
            ),
            "all_controller_command_records": sum(
                row.get("command_records", 0) for row in run["actions"]
            ),
            "registered_grounding_count": len(run["grounding_contracts"]),
            "condition_evaluations": gates,
            "physics_clock": {
                "contexts": len(clocks),
                "stages": {
                    name: {
                        phase: [
                            v["relative"]
                            for v in clocks
                            if v["skill"] == name and v["phase"] == phase
                        ]
                        for phase in ("PRE", "FEEDBACK", "POST")
                    }
                    for name in candidates
                },
                "independent_source_step_and_hash_checks": len(clocks),
            },
            "research_shield": accepted,
            "actual_dispatch_period": original.subset(motion_frames, states),
            "grounding_contracts": run["grounding_contracts"],
            "first_source_consumers": timing_rows,
            "dispatch_reference": run.get("dispatch_reference"),
            "sensor_feedback_time": {
                "accepted_control_durations_s": servo_callback,
                "max_feedback_capture_to_shield_s": max(
                    (
                        r["elapsed_from_capture_start_s"]
                        for r in roles
                        if "elapsed_from_capture_start_s" in r
                    ),
                    default=None,
                ),
            },
            "role_ledger_sha256": seal["run_sha256"],
            "r1_allocation_sha256": a["r1_allocation_sha256"],
            "software_preflight_sha256": a["software_receipt_sha256"],
            "formal_claims": 0,
            "canonical_repeated": 0,
            "task_model_calls": 0,
            "hardware_actions": 0,
        }
    )
    write(out, result)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["pixels", "score"])
    p.add_argument("raw", type=Path)
    p.add_argument("allocation", type=Path)
    p.add_argument("sha256")
    p.add_argument("--output", type=Path)
    arg = p.parse_args()
    if arg.mode == "pixels":
        original.pixels(arg.raw, arg.allocation, arg.sha256)
    else:
        report(arg.raw, arg.allocation, arg.sha256, arg.output)


if __name__ == "__main__":
    main()
