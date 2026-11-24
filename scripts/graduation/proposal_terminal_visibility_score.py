"""Read same-step two-camera decisions and independent physical outcomes from sealed evidence."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

import numpy as np
from scripts.graduation import dynamic_vision_score as vision
from scripts.graduation import proposal_scoring as base
from scripts.graduation import proposal_terminal_visibility_switch as sw
from scripts.graduation.dynamic_physics import CRITERIA
from scripts.graduation.guarded_clock_score import source_ledger, stop_cause
from scripts.graduation.perception_io import pinned, read, sha, write
from scripts.graduation.perception_pixels import measure
from scripts.graduation.proposal_closed_loop import readback_reset
from scripts.graduation.proposal_terminal_visibility import slots

from cloud_edge_robot_arm.research.native_collection_grounding import validate_camera
from cloud_edge_robot_arm.simulation.mujoco.backend import PhysicsStepObservation
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    evaluate_evidence,
    sample_physical_observation,
)


def frame_geo(case, reg, label):
    skill, _, role = label.partition("/")
    if role != "feedback_reobserve":
        return reg[case["view"]]
    if case["method"] != "bounded" or skill not in sw.SCOPE:
        raise ValueError("alternate observation outside registered treatment sample")
    return reg[sw.other_view(case["view"])]


def bound_frame(case, d, row, idx, reg):
    geometry = frame_geo(case, reg, row["label"])
    f = vision.frame_from_row(d, row, idx["episode"], idx["scene"], geometry)
    validate_camera(f, geometry)
    return f


def pixels(case, path, d, reg):
    seal = read(d / "acquisition-seal.json")
    idx = pinned(d / "pixel-index.json", seal["index_sha256"])
    if idx["allocation_sha256"] != case["allocation_sha256"]:
        raise ValueError("foreign blind allocation")
    ids = set()
    dec = []
    for r in idx["frames"]:
        f = bound_frame(case, d, r, idx, reg)
        if f.frame_id in ids:
            raise ValueError("duplicate real camera frame")
        ids.add(f.frame_id)
        dec.append({**r, "estimate": measure(f, frame_geo(case, reg, r["label"]), "SUBPIX")})
    write(d / "decisions.json", {"index_sha256": seal["index_sha256"], "decisions": dec})
    write(
        d / "decision-seal.json",
        {
            "sha256": sha(d / "decisions.json"),
            "acquisition_sha256": sha(d / "acquisition-seal.json"),
        },
    )


def read_one(case, a, d, reg):
    rec = read(d / "receipt.json")
    dec_seal = read(d / "decision-seal.json")
    seal = pinned(d / "acquisition-seal.json", dec_seal["acquisition_sha256"])
    idx = pinned(d / "pixel-index.json", seal["index_sha256"])
    truth = pinned(d / "offline-truth.json", seal["truth_sha256"])
    run = pinned(d / "run.json", seal["run_sha256"])
    dec = pinned(d / "decisions.json", dec_seal["sha256"])
    audit = pinned(d / "online-audit.json", seal["audit_sha256"])
    reset = readback_reset(case, read(d / "reset-observed.json"))
    if (
        reset != rec["reset"]
        or reset["episode_id"] != idx["episode"]
        or truth["episode"] != idx["episode"]
        or sha(d / "reset-observed.json") != rec["reset_sha256"]
        or rec["acquisition_sha256"] != dec_seal["acquisition_sha256"]
        or sha(d / "started.json") != rec["started_sha256"]
        or sha(d / "camera-setup.json") != rec["camera_setup_sha256"]
        or dec["index_sha256"] != seal["index_sha256"]
        or idx["allocation_sha256"] != case["allocation_sha256"]
        or truth["allocation_sha256"] != case["allocation_sha256"]
    ):
        raise ValueError("episode, clock or recorded reset mismatch")
    states = vision.checked_steps(
        truth["samples"], idx["episode"], a["asset_sha256"], truth["asset_sha256"]
    )
    captured = {}
    frame_rows = {}
    times = {}
    for src, row in zip(idx["frames"], dec["decisions"], strict=True):
        if any(row[k] != v for k, v in src.items()) or row["physics_step"] not in states:
            raise ValueError("pixel/truth source mismatch")
        f = bound_frame(case, d, src, idx, reg)
        if f.frame_id in captured:
            raise ValueError("duplicate raw frame")
        captured[f.frame_id] = f.checksum_sha256
        frame_rows[f.frame_id] = row
        times[f.frame_id] = f.captured_at
    if idx["frames"][0]["physics_step"] != 0 or idx["frames"][-1]["physics_step"] != max(states):
        raise ValueError("missing reset or terminal source")
    stages = run["actions"]
    if [s["skill"] for s in stages] != a["case"]["visual_stages_in_order"]:
        raise ValueError("order differs from frozen original stages")
    source_ledger(run["frame_roles"], idx["frames"], a["case"]["visual_stages_in_order"])
    base.check_audit(stages, audit)
    posts = base.score_admissions(stages, captured)
    lease = run["lease_summary"]
    if lease["attempt"] != 1 or lease["lease_released"] is not True:
        raise ValueError("retry or open lease")
    online = (
        posts == len(stages) and not run.get("stop") and lease["final_job_status"] == "SUCCEEDED"
    )
    samples = [
        sample_physical_observation(PhysicsStepObservation(**v), CRITERIA) for v in truth["samples"]
    ]
    phys = evaluate_evidence(samples, CRITERIA)
    windows = base.registered_windows(samples, {s["skill"]: s for s in stages})
    physical = phys.success and all(v["qualified"] for v in windows.values())
    coverage, _ = base.localization(dec["decisions"], states)
    checks = {
        r["frame_id"]: r["shield"] for r in audit if r.get("phase") == "FEEDBACK" and "shield" in r
    }
    comparisons = []
    all_samples = []
    alternate_ids = set()
    for sample in [r for r in audit if r.get("phase") == "bounded_camera_sample"]:
        if case["method"] != "bounded" or sample["skill"] not in sw.SCOPE:
            raise ValueError("unregistered camera event")
        ids = sample["frame_ids"]
        if not ids or len(ids) > 2 or len(set(ids)) != len(ids):
            raise ValueError("bad frame count or copies")
        if sample["checksums"] != [captured[i] for i in ids] or any(
            frame_rows[i]["physics_step"] != sample["step"] for i in ids
        ):
            raise ValueError("sample frame does not match sealed same-step original")
        switched = len(ids) == 2
        expected = [case["view"]] + ([sw.other_view(case["view"])] if switched else [])
        if sample["views"] != expected or sample["returned_to_starting_view"] is not True:
            raise ValueError("unexpected camera order")
        if switched and (
            sample["reason"] not in sw.RECOVERABLE_CAMERA_VIEW_ERRORS
            or times[ids[0]] >= times[ids[-1]]
            or sample["end_cursor"] != sample["first_cursor"] + 2
            or frame_rows[ids[1]]["label"] != sample["skill"] + "/feedback_reobserve"
        ):
            raise ValueError("unregistered, duplicated or untimed camera excursion")
        if not switched and not sample["error"] and sample["end_cursor"] != sample["first_cursor"]:
            raise ValueError("camera command without reobservation")
        chosen = sample["accepted_frame_id"]
        if chosen is not None and chosen != ids[-1]:
            raise ValueError("accepted source not final observed frame")
        shield = checks.get(chosen)
        timely = sample["elapsed_s"] <= 0.1
        if timely != sample["timely"]:
            raise ValueError("deadline accounting mismatch")
        finished = bool(chosen and shield and shield["allowed"] and timely and not sample["error"])
        if switched:
            alternate_ids.add(ids[-1])
            comparisons.append({**sample, "accepted_and_shield_allowed_in_time": finished})
        all_samples.append(sample["elapsed_s"] * 1000)
    if alternate_ids != {
        i for i, row in frame_rows.items() if row["label"].endswith("/feedback_reobserve")
    }:
        raise ValueError("extra frame absent from sample readback")
    return {
        "id": case["id"],
        "group": case["group"],
        "method": case["method"],
        "view": case["view"],
        "acquired": True,
        "episode": idx["episode"],
        "actual_physics_steps": max(states),
        "physics_samples": len(samples),
        "verified_posts": posts,
        "dispatched": sum(s.get("executor_entered") is True for s in stages),
        "online_success": online,
        "physical_success": physical,
        "joint_success": online and physical and phys.safety_assessment == "SCOPED_NO_VIOLATION",
        "windows": windows,
        "physical_outcome": asdict(phys),
        "stop": stop_cause(run, audit),
        "coverage": coverage,
        "servo_stops": {
            s["skill"]: s.get("servo_terminal_reason") for s in stages if s["status"] == "STOPPED"
        },
        "bounded_samples": len(all_samples),
        "sample_time_ms_p95": float(np.quantile(all_samples, 0.95)) if all_samples else None,
        "switches": comparisons,
        "accepted_switches": sum(s["accepted_and_shield_allowed_in_time"] for s in comparisons),
        "switches_attempted": len(comparisons),
        "source_seals": {**seal, "decisions_sha256": dec_seal["sha256"]},
        "stage_status": {s["skill"]: s["status"] for s in stages},
    }


def run(mode, raw, p, h, out):
    b = sw.master(raw, p, h)
    rows = []
    for case in b["cases"]:
        path = raw / "episodes" / case["allocation_file"]
        d = path.parent / "instance"
        a = pinned(path, case["allocation_sha256"])
        reg = b["registered_views"]
        if not (d / "acquisition-seal.json").is_file():
            rows.append({**case, "acquired": False})
            continue
        if mode == "pixels":
            pixels(case, path, d, reg)
        else:
            rows.append(read_one(case, a, d, reg))
    if mode == "pixels":
        return
    checked = [r for r in rows if r["acquired"]]
    if len({r["episode"] for r in checked}) != len(checked) or [r["id"] for r in rows] != [
        r["id"] for r in slots()
    ]:
        raise ValueError("reused case or lost denominator")
    by_method = {}
    for method in ("fixed", "bounded"):
        members = [r for r in rows if r["method"] == method]
        got = [r for r in members if r["acquired"]]
        by_method[method] = {
            "allocated": len(members),
            "acquired": len(got),
            "not_acquired": len(members) - len(got),
            "joint_successes": sum(r["joint_success"] for r in got),
            "switches": sum(r["switches_attempted"] for r in got),
            "accepted_switches": sum(r["accepted_switches"] for r in got),
        }
    write(
        out,
        {
            "schema": "proposal.terminal-switch.results.v1",
            "batch_sha256": h,
            "cases": rows,
            "by_method": by_method,
            "design": "one group per direction, paired fixed and bounded methods in both groups",
            "formal_claims": 0,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["pixels", "score"])
    parser.add_argument("raw", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("digest")
    parser.add_argument("--out", type=Path)
    a = parser.parse_args()
    run(a.mode, a.raw, a.manifest, a.digest, a.out)


if __name__ == "__main__":
    main()
