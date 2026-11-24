"""Independently read back the registered November 24 static pick-and-place trials."""

from __future__ import annotations

import argparse
import math
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import numpy as np
from scripts.graduation import dynamic_vision_score as vision
from scripts.graduation.dynamic_physics import CRITERIA, window_report
from scripts.graduation.guarded_clock_score import source_ledger, stop_cause
from scripts.graduation.perception_io import pinned, read, sha, write

from cloud_edge_robot_arm.experiments.statistics import wilson_interval
from cloud_edge_robot_arm.research.native_collection_grounding import validate_camera
from cloud_edge_robot_arm.simulation.mujoco.backend import PhysicsStepObservation
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    evaluate_evidence,
    sample_physical_observation,
)


def registered_windows(samples, stages):
    results = {}
    for name, steps in (("lift", 120), ("release", 240)):
        stage = stages[name.upper()]
        start = stage.get("dwell_start_step")
        if start is None:
            results[name] = {"status": "NOT_REACHED", "actual_samples": 0, "qualified": False}
            continue
        end = min(len(samples) - 1, stage["end_step"], start + steps)
        window = samples[start : end + 1]
        if len(window) != steps + 1:
            results[name] = {
                "status": "INCOMPLETE",
                "actual_samples": len(window),
                "qualified": False,
            }
            continue
        lift_dispatch = stages["LIFT"]["dispatch_step"]
        if not 0 <= lift_dispatch <= start or not stage["dispatch_step"] <= start:
            raise ValueError("dwell precedes dispatch")
        prior = name == "release" and results["lift"]["qualified"]
        summary, _ = window_report(
            name,
            window,
            samples[0].object_position_m[2],
            samples[lift_dispatch].object_position_m[2],
            prior,
        )
        results[name] = {
            "status": "COMPLETE",
            "actual_samples": len(window),
            "qualified": summary["entire_registered_duration_met"],
            "passed_samples": summary["passed_samples"],
            "longest_s": summary["longest_s"],
            "first_step": start,
            "last_step": end,
            "failures": summary["failures_by_predicate"],
        }
    return results


def score_admissions(stages, captured):
    passed = 0
    for stage in stages:
        checks = []
        for phase in ("pre", "post"):
            decision = stage.get(phase)
            if decision is None:
                checks.append(False)
                continue
            if captured.get(decision["frame_id"]) != decision["checksum_sha256"]:
                raise ValueError("admission frame digest differs from acquisition")
            checks.append(
                decision["shield"]["allowed"] is True
                and decision["shield"]["unmodified"] is True
                and bool(decision["conditions"])
                and all(c["status"] == "PASS" for c in decision["conditions"])
            )
        returned = stage.get("return_evidence", {})
        if (
            all(checks)
            and stage["status"] == "PASS"
            and stage.get("executor_entered") is True
            and returned.get("success") is True
            and returned.get("action_result_present") is True
            and returned["original_window_error"] is None
        ):
            passed += 1
    return passed


def check_audit(stages, audit):
    """Check that the saved row contains the complete conditions and live Shield receipt."""
    admissions = [(s, p) for s in stages for p in ("pre", "post") if s.get(p) is not None]
    traces = [r for r in audit if "requirements" in r and "verdicts" in r]
    shields = [r for r in audit if "shield" in r and r["phase"] in ("PRE", "POST")]
    if len(admissions) != len(traces) or len(admissions) != len(shields):
        raise ValueError("admission evidence count differs from live observations")
    for (stage, phase), trace, shield in zip(admissions, traces, shields, strict=True):
        row = stage[phase]
        if (
            trace["phase"] != phase.upper()
            or shield["phase"] != phase.upper()
            or shield["frame_id"] != row["frame_id"]
            or shield["shield"] != row["shield"]["result"]
            or [r["name"] for r in trace["requirements"]] != [r["name"] for r in row["conditions"]]
            or [(r["condition_name"], r["status"], r["reasons"]) for r in trace["verdicts"]]
            != [(r["name"], r["status"], r["reasons"]) for r in row["conditions"]]
            or any(r["observation_id"] != row["frame_id"] for r in trace["verdicts"])
        ):
            raise ValueError("registered condition or live Shield record is inconsistent")


def localization(frames, states):
    errors = []
    missing = Counter()
    for row in frames:
        estimate = row["estimate"]
        pos = estimate["object_top_center_world_m"]
        if pos is None:
            missing[estimate["reason"]] += 1
            continue
        if (
            estimate["status"] != "OBSERVED"
            or 7 not in estimate["ids"]
            or not 0 < estimate["marker_center_optical_depth_m"] < math.inf
        ):
            raise ValueError("pose lacks registered identity or finite positive optical depth")
        actual = states[row["physics_step"]]
        rotation = np.reshape(actual["object_geom_rotation_row_major"], (3, 3))
        top = actual["object_geom_position_m"] + rotation[:, 2] * actual["object_half_extent_m"][2]
        residual = float(np.linalg.norm(top - pos))
        if not math.isfinite(residual):
            raise ValueError("nonfinite position error")
        errors.append(residual)
    return {
        "acquired": len(frames),
        "valid": len(errors),
        "missing_reasons": dict(missing),
        "conditional_top_center_p90_mm": 1000 * float(np.quantile(errors, 0.9)) if errors else None,
    }, errors


def read_case(case, alloc_path, raw):
    alloc_sha = case["allocation_sha256"]
    alloc = pinned(alloc_path, alloc_sha)
    allocation = alloc["case"]
    for key in ("reset_fixture_center_m", "yaw_rad"):
        if allocation[key] != case[key]:
            raise ValueError("case reset disagrees with allocation")
    if (
        allocation["visual_seed"] != case["seed"]
        or allocation["id"] != case["id"]
        or allocation["visual_id"] != f"{allocation['release']}/{case['id']}"
        or allocation["group"] != case["group"]
        or allocation["view"] != case["view"]
    ):
        raise ValueError("case seed or ID disagrees with allocation")
    pixels = read(raw / "decision-seal.json")
    seal = pinned(raw / "acquisition-seal.json", pixels["acquisition_sha256"])
    index = pinned(raw / "pixel-index.json", seal["index_sha256"])
    decision = pinned(raw / "decisions.json", pixels["sha256"])
    truth = pinned(raw / "offline-truth.json", seal["truth_sha256"])
    run = pinned(raw / "run.json", seal["run_sha256"])
    audit = pinned(raw / "online-audit.json", seal["audit_sha256"])
    if (
        index["allocation_sha256"] != alloc_sha
        or truth["allocation_sha256"] != alloc_sha
        or truth["episode"] != index["episode"]
        or decision["index_sha256"] != seal["index_sha256"]
        or index["scene"] != "S01_NORMAL_STATIC"
    ):
        raise ValueError("source does not belong to this allocated case")
    states = vision.checked_steps(
        truth["samples"], index["episode"], alloc["asset_sha256"], truth["asset_sha256"]
    )
    yaw = case["yaw_rad"]
    c, s = math.cos(yaw), math.sin(yaw)
    if not (
        np.allclose(
            states[0]["object_geom_position_m"], case["reset_fixture_center_m"], rtol=0, atol=1e-9
        )
        and np.allclose(
            states[0]["object_geom_rotation_row_major"],
            [c, -s, 0, s, c, 0, 0, 0, 1],
            rtol=0,
            atol=1e-9,
        )
    ):
        raise ValueError("physical reset pose differs from preallocation")
    captured = {}
    frames = decision["decisions"]
    for source, row in zip(index["frames"], frames, strict=True):
        if any(row[k] != v for k, v in source.items()) or row["physics_step"] not in states:
            raise ValueError("pixel decision not bound to an original physics step")
        frame = vision.frame_from_row(
            raw, source, index["episode"], index["scene"], alloc["geometry"]
        )
        validate_camera(frame, alloc["geometry"])
        if frame.frame_id in captured:
            raise ValueError("duplicate acquisition")
        captured[frame.frame_id] = frame.checksum_sha256
    if not frames or frames[0]["physics_step"] != 0 or frames[-1]["physics_step"] != max(states):
        raise ValueError("reset or terminal acquisition missing")
    stages = run["actions"]
    order = allocation["visual_stages_in_order"]
    if [s["skill"] for s in stages] != order:
        raise ValueError("registered stage list changed")
    source_ledger(run["frame_roles"], frames, order)
    check_audit(stages, audit)
    passed = score_admissions(stages, captured)
    lease = run["lease_summary"]
    if lease["attempt"] != 1 or lease["lease_released"] is not True:
        raise ValueError("unexpected retry or lease state")
    online = passed == len(order) and "stop" not in run and lease["final_job_status"] == "SUCCEEDED"
    samples = [
        sample_physical_observation(PhysicsStepObservation(**row), CRITERIA)
        for row in truth["samples"]
    ]
    outcome = evaluate_evidence(samples, CRITERIA)
    windows = registered_windows(samples, {s["skill"]: s for s in stages})
    physical = outcome.success and all(win["qualified"] for win in windows.values())
    cov, errors = localization(frames, states)
    return {
        "acquired": True,
        "episode": index["episode"],
        "coverage": cov,
        "acquisition_seal_sha256": pixels["acquisition_sha256"],
        "decisions_sha256": pixels["sha256"],
        "physical_truth_sha256": seal["truth_sha256"],
        "actual_physics_steps": max(states),
        "physics_samples": len(samples),
        "verified_posts": passed,
        "online_success": online,
        "physical_success": physical,
        "joint_success": online and physical and outcome.safety_assessment == "SCOPED_NO_VIOLATION",
        "windows": windows,
        "independent_physical_outcome": asdict(outcome),
        "stage_status": {s["skill"]: s["status"] for s in stages},
        "stop": stop_cause(run, audit),
        "dispatched_actions": sum(s.get("executor_entered") is True for s in stages),
        "accepted_joint_targets": sum(
            s.get("accepted_command_types", {}).get("joint_target", 0) for s in stages
        ),
    }, errors


def summarize_view(rows, errors):
    acquired = [r for r in rows if r["acquired"]]
    successes = sum(r["joint_success"] for r in acquired)
    return {
        "allocated": len(rows),
        "acquired": len(acquired),
        "unacquired": len(rows) - len(acquired),
        "joint_successes": successes,
        "joint_wilson95_by_placement": wilson_interval(successes, len(rows))
        if rows and len(acquired) == len(rows)
        else None,
        "online_successes": sum(r["online_success"] for r in acquired),
        "independent_physical_successes": sum(r["physical_success"] for r in acquired),
        "acquired_frames": sum(r["coverage"]["acquired"] for r in acquired),
        "valid_frames": sum(r["coverage"]["valid"] for r in acquired),
        "conditional_top_center_p90_mm": 1000 * float(np.quantile(errors, 0.9)) if errors else None,
    }


def check_batch(batch):
    from scripts.graduation.proposal_closed_loop import allocated_cases

    expected = allocated_cases(batch["selected_view"])
    cases = batch["cases"]
    if (
        batch["schema"] != "proposal.heldout.development.allocation.v1"
        or len(cases) != len(expected)
        or any(
            any(row.get(key) != value for key, value in registered.items())
            for row, registered in zip(cases, expected, strict=True)
        )
    ):
        raise ValueError("batch differs from the registered placement allocation")
    if any(row["allocation_file"] != row["id"] + "/allocation.json" for row in cases):
        raise ValueError("case does not own its private evidence directory")


def run(mode, allocation, allocation_sha256, root, output=None):
    batch = pinned(allocation, allocation_sha256)
    check_batch(batch)
    rows, errors_by_view = [], {}
    for case in batch["cases"]:
        path = root / case["allocation_file"]
        raw = path.parent / "instance"
        if not (raw / "acquisition-seal.json").is_file():
            rows.append({**case, "acquired": False})
            continue
        if mode == "pixels":
            vision.pixels(raw, path, case["allocation_sha256"])
            continue
        result, errors = read_case(case, path, raw)
        errors_by_view.setdefault(case["view"], []).extend(errors)
        rows.append({**case, **result})
    if mode == "pixels":
        return
    episodes = [r["episode"] for r in rows if r["acquired"]]
    if len(episodes) != len(set(episodes)):
        raise ValueError("one episode reused for multiple cases")
    by_view = {}
    for view in sorted({r["view"] for r in rows}):
        members = [r for r in rows if r["view"] == view]
        by_view[view] = summarize_view(members, errors_by_view.get(view, []))
    write(
        output,
        {
            "schema": "graduation.proposal.static-readback.v1",
            "scope": "DEVELOPMENT_HELDOUT_PLACEMENTS",
            "allocation_sha256": allocation_sha256,
            "scorer_sha256": sha(Path(__file__)),
            "views": by_view,
            "rows": rows,
            "denominators": (
                "One trial per allocated placement and view. P90 pools valid frame residuals "
                "within a view. Wilson intervals describe this small development sample."
            ),
        },
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["pixels", "score"])
    p.add_argument("allocation", type=Path)
    p.add_argument("sha256")
    p.add_argument("private", type=Path)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if args.mode == "score" and args.output is None:
        p.error("score requires --output")
    run(args.mode, args.allocation, args.sha256, args.private, args.output)


if __name__ == "__main__":
    main()
