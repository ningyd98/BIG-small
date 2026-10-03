"""Read-only independent replay and consistency audit of the T7 development smoke."""

import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

from pydantic import TypeAdapter

from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    PhysicalSample,
    evaluate_evidence,
)


def read(path):
    return json.loads(path.read_text())


def canonical(value):
    return json.dumps(value, sort_keys=True)


def verify(root):
    errors, reports = [], []
    assignments = read(root / "assignments.json")
    provenance = read(root / "provenance.json")
    results = read(root / "results.json")
    summary = read(root / "summary.json")
    for name, key in (("assignments.json", "assignments_sha256"), ("config.yaml", "config_sha256")):
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != provenance[key]:
            errors.append(f"frozen input drift: {name}")
    for name, expected in provenance["frozen_bundle_sha256"].items():
        path = Path(provenance["frozen_dir"]) / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            errors.append(f"model bundle drift: {name}")
    for name, expected in provenance["source_sha256"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            errors.append(f"source drift: {name}")
    if len(assignments["cases"]) != 20 or len(results) != 20:
        errors.append("not all 20 assigned cases retained")
    if len({case["scene_hash"] for case in assignments["cases"]}) != 20:
        errors.append("scenes are not independent")
    by_id = {row["case_id"]: row for row in results}
    if len(by_id) != 20:
        errors.append("duplicate/missing result IDs")
    for case in assignments["cases"]:
        case_id = case["case_id"]
        directory = root / "cases" / case_id
        before = len(errors)
        if read(directory / "assignment.json") != case:
            errors.append(f"{case_id}: case assignment differs")
        if any(by_id[case_id].get(key) != case[key] for key in ("kind", "scene_hash")):
            errors.append(f"{case_id}: result assignment binding differs")
        episode = read(directory / "episode.json")
        records = episode["verification_records"]
        samples = TypeAdapter(list[PhysicalSample]).validate_python(
            read(directory / "physical-evidence.json")
        )
        physical = asdict(evaluate_evidence(
            samples,
            CompletionCriteria(object_id="object", target_region_id="target_region"),
            evaluation_start_step=samples[0].physics_step,
        ))
        if canonical(physical) != canonical(read(directory / "physical-outcome.json")):
            errors.append(f"{case_id}: independent physical replay differs")
        if episode["physical_success"] != physical["success"]:
            errors.append(f"{case_id}: physical_success differs")
        expected = (episode["online_reported_complete"] and physical["success"]
                    and episode["terminal_reason"] is None)
        if episode["success"] != expected:
            errors.append(f"{case_id}: combined episode success differs")
        semantic = case["kind"] != "MISSING_TARGET"
        if by_id[case_id].get("semantic_success") != semantic:
            errors.append(f"{case_id}: semantic verdict differs from assignment")
        if by_id[case_id]["success"] != bool(expected and semantic):
            errors.append(f"{case_id}: semantic task success differs")
        if records[-1]["layer"] != "INDEPENDENT_PHYSICAL_RESULT":
            errors.append(f"{case_id}: independent evaluator did not run last")
        frames = [row for row in records if row["layer"] == "OBSERVATION"]
        if len(frames) != episode["observation_count"]:
            errors.append(f"{case_id}: frame coverage differs")
        if len({row["frame_id"] for row in frames}) != len(frames):
            errors.append(f"{case_id}: repeated frame ID")
        if {row["episode_id"] for row in frames} != {episode["episode_id"]}:
            errors.append(f"{case_id}: foreign episode")
        for previous, current in zip(frames, frames[1:]):
            if (current["captured_at"] <= previous["captured_at"]
                    or current["sim_time_s"] < previous["sim_time_s"]):
                errors.append(f"{case_id}: nonmonotonic frames")
        for index, frame in enumerate(frames, 1):
            for key, name in (("rgb_sha256", "rgb.png"), ("depth_sha256", "depth.f32")):
                path = directory / "frames" / f"{index:03d}" / name
                if hashlib.sha256(path.read_bytes()).hexdigest() != frame[key]:
                    errors.append(f"{case_id}: frame {index} payload hash differs")
        actions = [row for row in records
                   if row["layer"] in {"SKILL_RETURN", "PARTIAL_SKILL_RETURN"}
                   and row["physics_steps"] > 0]
        if len(actions) != episode["executed_actions"]:
            errors.append(f"{case_id}: action coverage differs")
        event_ids, stopped, reobservations = [], False, 0
        for row in records:
            if row["layer"] == "ONLINE_VERIFICATION":
                event_ids.append(row["event"]["event_id"])
                reobservations += row["route"] == "REOBSERVE"
                stopped |= row["route"] == "STOP"
            elif row["layer"] in {"ACTION_STARTED", "SKILL_RETURN", "PARTIAL_SKILL_RETURN"} and stopped:
                errors.append(f"{case_id}: dispatched after STOP")
        if len(event_ids) != len(set(event_ids)) or reobservations > 2:
            errors.append(f"{case_id}: event ID or reobservation budget invalid")
        if episode["online_reported_complete"] and not any(
            row["layer"] == "ONLINE_VERIFICATION"
            and row["event"]["kind"] == "RESULT_VERIFIED"
            and row["route"] == "CONTINUE"
            and {v["condition_name"] for v in row["conditions"]}
            == {"object_inside_target_region", "gripper_released", "robot_in_safe_pose"}
            and all(v["status"] == "PASS"
                    and v["observation_id"] == row["event"]["observation_id"]
                    for v in row["conditions"])
            for row in records
        ):
            errors.append(f"{case_id}: online completion lacks verified effects")
        reports.append({
            "case_id": case_id, "valid": len(errors) == before,
            "physical_samples": len(samples), "frames": len(frames),
            "actions": len(actions), "reobservations": reobservations,
            "online_complete": episode["online_reported_complete"],
            "physical_success": physical["success"], "task_success": by_id[case_id]["success"],
        })
    if sum(row["success"] for row in results) != summary["succeeded"]:
        errors.append("summary success count differs")
    gate = (len(results) == 20
            and any(case["kind"] == "NORMAL" and by_id[case["case_id"]]["success"]
                    for case in assignments["cases"])
            and any(not row["success"] for row in results)
            and not any(row.get("blocked", False) for row in results))
    if summary["smoke_passed"] != gate:
        errors.append("summary smoke gate differs from independent recomputation")
    return {"valid": not errors, "accepted": not errors and gate,
            "formal_g1": False, "errors": errors, "cases": reports,
            "physical_samples": sum(row["physical_samples"] for row in reports),
            "frames": sum(row["frames"] for row in reports),
            "actions": sum(row["actions"] for row in reports)}


if __name__ == "__main__":
    report = verify(Path(sys.argv[1]))
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["accepted"] else 1)
