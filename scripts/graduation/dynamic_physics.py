"""Preallocate, capture, or independently score the six canonical fixed-TCP cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from scripts.graduation.perception_io import ROOT, check_sources, pinned, read, sha, write

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import PhysicsStepObservation
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    evaluate_evidence,
    sample_physical_observation,
)

CASES = (
    "positive_pick_place",
    "grasp_without_contact",
    "unreachable_target",
    "timed_out_motion_holds",
    "emergency_stop",
    "empty_hand_place",
)
STAGES = (
    "move_above",
    "approach",
    "grasp",
    "lift_and_hold_0_5_s",
    "post_lift_dwell_0_5_s",
    "move_to_region",
    "place",
    "release",
    "stable_1_s_after_release",
)
CRITERIA = CompletionCriteria(object_id="object", target_region_id="target_region")
ASSET = "assets/robots/franka_panda/scene.xml"
VERIFY = "scripts/verify_rgbd_physical_skills.py"
HERE = "scripts/graduation/dynamic_physics.py"
TEST = "tests/test_graduation_dynamic_physics.py"
PREFIX = "graduation-dev-dynamic-r1-20261123/"
CASE_SUFFIX = (
    "t4-positive",
    "t4-no-contact",
    "t4-unreachable",
    "t4-timeout",
    "t4-estop",
    "t4-empty-place",
)


def utc():
    return datetime.now(UTC).isoformat()


def path_pin(path):
    return hashlib.sha256(os.fsencode(path.resolve())).hexdigest()


def emit(stream, row):
    stream.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")


def lines(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def allocate(plan_path, private, output):
    import cv2
    import mujoco
    import numpy as np
    from OpenGL import GL

    plan = read(plan_path)
    ids = plan["allocation"]["canonical_case_ids"]
    if ids != [PREFIX + suffix for suffix in CASE_SUFFIX]:
        raise ValueError("canonical identities differ from registration")
    if os.getenv("MUJOCO_GL") != "egl":
        raise ValueError("EGL environment required")
    free = shutil.disk_usage(private.parent).free
    if free < 2**30 or private.exists():
        raise ValueError("fresh raw directory and 1 GiB free space required")
    context = mujoco.GLContext(320, 240)
    try:
        context.make_current()
        gl = {
            "vendor": GL.glGetString(GL.GL_VENDOR).decode(),
            "renderer": GL.glGetString(GL.GL_RENDERER).decode(),
            "version": GL.glGetString(GL.GL_VERSION).decode(),
        }
    finally:
        context.free()
    original = {row["path"]: row["sha256"] for row in plan["inputs"]}
    sources = [k for k in original if k.startswith(("src/", "assets/"))]
    sources += [VERIFY, HERE, TEST, "scripts/graduation/perception_io.py"]
    hashes = {p: sha(ROOT / p) for p in sources}
    for path in original:
        if path != VERIFY and sha(ROOT / path) != original[path]:
            raise ValueError(f"plan input changed: {path}")
    write(
        output,
        {
            "schema": "graduation.canonical.allocation.v1",
            "created_at": utc(),
            "plan_sha256": sha(plan_path),
            "product_baseline": plan["baseline"],
            "registration": plan["allocation"],
            "case_ids": dict(zip(CASES, ids, strict=True)),
            "stage_order": STAGES,
            "positive_dwell_steps": {"lift": 120, "release": 240},
            "case_cap_each": 1,
            "time_budget_s": 3600,
            "minimum_free_bytes": 2**30,
            "output_directory_sha256": path_pin(private),
            "sources_sha256": hashes,
            "original_verifier_sha256": original[VERIFY],
            "scenario": "S01_NORMAL_STATIC",
            "asset": ASSET,
            "physics_dt_s": SimulatorConfig().physics_dt_s,
            "camera": {"rgbd_requested_by_audit": False, "width": 320, "height": 240},
            "initial_center_m": [0.45, 0, 0.035],
            "yaw_rad": 0,
            "fixed_positive_tcp_m": {
                "move_above": [0.45, 0, 0.16],
                "approach": [0.45, 0, 0.045],
                "lift_height": 0.10,
                "move_to_region": [0.20, 0.25, 0.16],
                "place": [0.20, 0.25, 0.045],
            },
            "positive_timeouts_ms": [8000, 8000, 1000, 8000, 10000, 8000, 1000],
            "negative_protocol": "Original five functions and assertions in the frozen verifier.",
            "observation": "After reset and every positive mj_step. No data fed back to control.",
            "analysis": {
                "criteria": asdict(CRITERIA),
                "evaluator_reference": "reset step 0",
                "lift_window": "LIFT return through additional 120 steps inclusive",
                "release_window": "RELEASE return through additional 240 steps inclusive",
            },
            "environment": {
                "python": platform.python_version(),
                "mujoco": mujoco.__version__,
                "numpy": np.__version__,
                "opencv": cv2.__version__,
                "gl": gl,
                "free_disk_bytes": free,
            },
        },
    )


class CanonicalAudit:
    """Write-only sidecar for the original verifier. Control consumes no audit return values."""

    def __init__(self, private):
        request = read(private / "request.json")
        self.alloc = pinned(Path(request["path"]), request["sha256"])
        if path_pin(private) != self.alloc["output_directory_sha256"]:
            raise ValueError("unregistered canonical directory")
        check_sources(self.alloc)
        self.private = private
        self.current = None
        self.count = 0
        write(private / "audit-start.json", {"at": utc(), "allocation": request["sha256"]})

    def event(self, name, row):
        with (self.private / name).open("a", encoding="utf-8") as stream:
            emit(stream, {"utc": utc(), **row})

    def run_case(self, name, action):
        if self.count >= len(CASES) or name != CASES[self.count]:
            raise ValueError("case order changed")
        case_id = self.alloc["case_ids"][name]
        self.current = case_id
        self.count += 1
        self.event("cases.jsonl", {"event": "BEGIN", "case": name, "case_id": case_id})
        try:
            result = action()
        except Exception as error:
            self.event(
                "cases.jsonl",
                {"event": "ERROR", "case": name, "case_id": case_id, "reason": repr(error)},
            )
            raise
        self.event(
            "cases.jsonl", {"event": "RETURN", "case": name, "case_id": case_id, "result": result}
        )
        return result

    @contextmanager
    def observe(self, backend):
        sample0 = backend.current_physics_observation()
        asset = self.alloc["sources_sha256"][ASSET]
        write(
            self.private / "origin.json",
            {
                "episode": sample0.episode_id,
                "case_id": self.current,
                "asset_sha256": asset,
                "step": sample0.physics_step,
                "time": sample0.sim_time_s,
                "at": utc(),
            },
        )
        with (self.private / "steps.jsonl").open("x", encoding="utf-8") as stream:

            def store(observation):
                emit(
                    stream,
                    {
                        "case_id": self.current,
                        "asset_sha256": asset,
                        "snapshot": asdict(observation),
                    },
                )

            store(sample0)
            with backend.observe_physics_steps(store):
                yield

    @contextmanager
    def stage(self, backend, stage):
        entry = {"stage": stage, "case_id": self.current, "start_step": backend.total_physics_steps}
        self.event("stages.jsonl", {"event": "BEGIN", **entry})
        try:
            yield
        except Exception as error:
            self.event(
                "stages.jsonl",
                {
                    "event": "END",
                    "status": "ERROR",
                    "error": repr(error),
                    "end_step": backend.total_physics_steps,
                    **entry,
                },
            )
            raise
        else:
            self.event(
                "stages.jsonl",
                {
                    "event": "END",
                    "status": "RETURNED",
                    "end_step": backend.total_physics_steps,
                    **entry,
                },
            )


def capture(allocation, allocation_sha, private):
    alloc = pinned(allocation, allocation_sha)
    check_sources(alloc)
    if path_pin(private) != alloc["output_directory_sha256"]:
        raise ValueError("output is outside the frozen allocation")
    if shutil.disk_usage(private.parent).free < alloc["minimum_free_bytes"]:
        raise ValueError("insufficient evidence storage")
    private.mkdir(exist_ok=False)
    write(private / "request.json", {"path": str(allocation.resolve()), "sha256": allocation_sha})
    command = [
        sys.executable,
        VERIFY,
        "--audit-dir",
        str(private.resolve()),
        "--output",
        str((private / "canonical.json").resolve()),
    ]
    started = time.perf_counter()
    with (private / "original.log").open("xb") as log:
        try:
            result = subprocess.run(
                command,
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=alloc["time_budget_s"],
                check=False,
            )
            code = result.returncode
        except subprocess.TimeoutExpired:
            code = 124
    write(
        private / "command.json",
        {"argv": command, "exit_code": code, "elapsed_wall_s": time.perf_counter() - started},
    )
    files = {p.name: sha(p) for p in sorted(private.iterdir()) if p.is_file()}
    write(
        private / "seal.json",
        {"allocation_sha256": allocation_sha, "files": files, "closed": utc()},
    )
    return code


def read_seal(private, expected):
    seal = pinned(private / "seal.json", expected)
    for name, digest in seal["files"].items():
        if Path(name).name != name or sha(private / name) != digest:
            raise ValueError(f"sealed bytes differ in {name}")
    return seal


def validate_series(envelopes, case_id, asset, episode, final_step, dt):
    result = []
    for index, row in enumerate(envelopes):
        if row["case_id"] != case_id or row["asset_sha256"] != asset:
            raise ValueError("foreign case or asset in canonical evidence")
        snapshot = PhysicsStepObservation(**row["snapshot"])
        if snapshot.episode_id != episode or snapshot.physics_step != index:
            raise ValueError("missing, duplicate or foreign observation")
        if not math.isclose(snapshot.sim_time_s, index * dt, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("physics observation time outside the registered clock")
        result.append(sample_physical_observation(snapshot, CRITERIA))
    if len(result) != final_step + 1 or not result:
        raise ValueError("canonical step sequence is incomplete")
    return result


def stage_windows(spans):
    windows = {"lift": None, "release": None}
    previous_end = 0
    for index, span in enumerate(spans):
        if index >= len(STAGES) or STAGES[index] != span["stage"]:
            raise ValueError("stage sequence differs from registration")
        start, end = span["start_step"], span["end_step"]
        if start != previous_end or end < start or span["status"] not in {"RETURNED", "ERROR"}:
            raise ValueError("stage interval differs from registered predecessor")
        if span["status"] == "ERROR" and index != len(spans) - 1:
            raise ValueError("work follows a failed canonical stage")
        if span["status"] == "RETURNED" and index in {4, 8}:
            key, extra = ("lift", 120) if index == 4 else ("release", 240)
            if end - start != extra:
                raise ValueError("registered dwell length changed")
            windows[key] = (start, end)
        previous_end = end
    return windows


def stage_receipts(events, case_id):
    if len(events) % 2:
        raise ValueError("missing stage return")
    spans = []
    for begin, end in zip(events[::2], events[1::2], strict=True):
        if (begin["event"], end["event"]) != ("BEGIN", "END"):
            raise ValueError("stage entry/exit not paired")
        for key in ("case_id", "stage", "start_step"):
            if begin[key] != end[key]:
                raise ValueError("inconsistent stage entry/exit identity")
        if begin["case_id"] != case_id or end["utc"] < begin["utc"]:
            raise ValueError("foreign or reversed stage receipt")
        spans.append(
            {k: end[k] for k in ("stage", "start_step", "end_step", "status")}
            | {
                "start_utc": begin["utc"],
                "end_utc": end["utc"],
            }
        )
    return spans


def sample_diagnostics(sample, reset_z, dispatch_z):
    pos = sample.object_position_m
    bottom = sample.object_bottom_z_m - sample.table_height_m
    margins = [
        region_half - (abs(value - center) + extent)
        for value, center, extent, region_half in zip(
            pos[:2],
            sample.region_center_xy_m,
            sample.object_half_extent_xy_m,
            sample.region_half_extent_xy_m,
            strict=True,
        )
    ]
    return {
        "step": sample.physics_step,
        "time_s": sample.sim_time_s,
        "delta_height_reset_m": pos[2] - reset_z,
        "delta_height_lift_dispatch_m": pos[2] - dispatch_z,
        "left_contact": sample.left_finger_contact,
        "right_contact": sample.right_finger_contact,
        "gripper_open": sample.gripper_open,
        "linear_speed_m_s": sample.object_linear_speed_m_s,
        "angular_speed_rad_s": sample.object_angular_speed_rad_s,
        "region_margin_xy_m": margins,
        "bottom_minus_table_m": bottom,
    }


def window_report(kind, samples, reset_z, dispatch_z, prior_hold):
    rows = []
    first_time = None
    longest = 0.0
    reasons = Counter()
    for sample in samples:
        row = sample_diagnostics(sample, reset_z, dispatch_z)
        checks = {
            "linear_speed": row["linear_speed_m_s"] <= CRITERIA.max_stable_linear_speed_m_s,
            "angular_speed": row["angular_speed_rad_s"] <= CRITERIA.max_stable_angular_speed_rad_s,
        }
        if kind == "lift":
            checks.update(
                {
                    "height_from_reset": row["delta_height_reset_m"] >= CRITERIA.lift_m - 1e-12,
                    "bilateral_contact": row["left_contact"] and row["right_contact"],
                    "gripper_closed": not row["gripper_open"],
                }
            )
        else:
            checks.update(
                {
                    "prior_qualified_hold": prior_hold,
                    "gripper_open": row["gripper_open"],
                    "free_of_fingers": not row["left_contact"] and not row["right_contact"],
                    "full_projected_region": min(row["region_margin_xy_m"]) >= -1e-9,
                    "bottom_on_table": abs(row["bottom_minus_table_m"]) <= 0.005,
                }
            )
        ok = all(checks.values())
        row.update({"window": kind, "predicates": checks, "all_pass": ok})
        rows.append(row)
        reasons.update(key for key, value in checks.items() if not value)
        if ok:
            if first_time is None:
                first_time = sample.sim_time_s
            longest = max(longest, sample.sim_time_s - first_time)
        else:
            first_time = None
    failed = [r for r in rows if not r["all_pass"]]
    keys = (
        "delta_height_reset_m",
        "delta_height_lift_dispatch_m",
        "linear_speed_m_s",
        "angular_speed_rad_s",
        "bottom_minus_table_m",
    )
    target = CRITERIA.hold_s if kind == "lift" else CRITERIA.placed_stable_s
    return {
        "status": "MEASURED",
        "samples": len(rows),
        "first_step": rows[0]["step"],
        "last_step": rows[-1]["step"],
        "duration_s": rows[-1]["time_s"] - rows[0]["time_s"],
        "passed_samples": len(rows) - len(failed),
        "failed_samples": len(failed),
        "first_failed_step": failed[0]["step"] if failed else None,
        "first_failed_predicates": [k for k, v in failed[0]["predicates"].items() if not v]
        if failed
        else [],
        "first_failed_sample": failed[0] if failed else None,
        "failures_by_predicate": dict(reasons),
        "longest_s": longest,
        "entire_registered_duration_met": longest >= target - 1e-12,
        "min_max": {k: [min(r[k] for r in rows), max(r[k] for r in rows)] for k in keys},
        "left_contact_n": sum(r["left_contact"] for r in rows),
        "right_contact_n": sum(r["right_contact"] for r in rows),
        "gripper_open_n": sum(r["gripper_open"] for r in rows),
        "full_region_n": sum(min(r["region_margin_xy_m"]) >= -1e-9 for r in rows),
        "bottom_on_table_n": sum(abs(r["bottom_minus_table_m"]) <= 0.005 for r in rows),
        "height_at_least_50mm_from_dispatch_n": sum(
            r["delta_height_lift_dispatch_m"] >= CRITERIA.lift_m - 1e-12 for r in rows
        ),
    }, rows


def score(allocation, allocation_sha, private, seal_sha, output):
    alloc = pinned(allocation, allocation_sha)
    check_sources(alloc)
    seal = read_seal(private, seal_sha)
    if seal["allocation_sha256"] != allocation_sha:
        raise ValueError("seal belongs to a different allocation")
    case_ids, asset = alloc["case_ids"], alloc["sources_sha256"][ASSET]
    original = read(private / "canonical.json")
    if (original["asset_sha256"], original["seed"], original["scenario_id"]) != (
        asset,
        alloc["registration"]["canonical_seed"],
        alloc["scenario"],
    ):
        raise ValueError("canonical scene, seed or asset changed")
    if list(original["cases"]) != list(CASES):
        raise ValueError("canonical case order or count changed")
    events = list(lines(private / "cases.jsonl"))
    if len(events) != 2 * len(CASES):
        raise ValueError("missing canonical case receipts")
    cases = {}
    for i, name in enumerate(CASES):
        begin, end = events[2 * i : 2 * i + 2]
        if (
            (begin["event"], end["event"]) != ("BEGIN", "RETURN")
            or any(
                (event["case_id"], event["case"]) != (case_ids[name], name)
                for event in (begin, end)
            )
            or end["result"] != original["cases"][name]
        ):
            raise ValueError("original report differs from the independent case receipts")
        result = end["result"]
        cases[name] = {
            "case_id": case_ids[name],
            "start_utc": begin["utc"],
            "end_utc": end["utc"],
            **{k: v for k, v in result.items() if k not in {"trace", "active_hold_ctrl"}},
        }
    positive = original["cases"][CASES[0]]
    source = read(private / "origin.json")
    if (source["case_id"], source["asset_sha256"], source["step"], source["time"]) != (
        case_ids[CASES[0]],
        asset,
        0,
        0,
    ):
        raise ValueError("foreign reset observation")
    spans = stage_receipts(list(lines(private / "stages.jsonl")), case_ids[CASES[0]])
    windows = stage_windows(spans)
    trace = positive["trace"]
    reported = [(r["stage"], r["physics_steps_total"]) for r in trace[1:]]
    actual = [(r["stage"], r["end_step"]) for r in spans]
    if reported != actual or trace[0]["stage"] != "reset" or trace[0]["physics_steps_total"] != 0:
        raise ValueError("canonical stage snapshots disagree with observer intervals")
    samples = validate_series(
        lines(private / "steps.jsonl"),
        case_ids[CASES[0]],
        asset,
        source["episode"],
        trace[-1]["physics_steps_total"],
        alloc["physics_dt_s"],
    )
    outcome = evaluate_evidence(samples, CRITERIA)
    output.mkdir(exist_ok=False)
    summaries = {}
    with (output / "window-samples.jsonl").open("x", encoding="utf-8") as rows_out:
        for kind, bounds in windows.items():
            if bounds is None:
                summaries[kind] = {"status": "NOT_RUN", "samples": 0, "longest_s": None}
                continue
            lo, hi = bounds
            dispatch = spans[3]["start_step"]
            prior_hold = (
                evaluate_evidence(samples[: lo + 1], CRITERIA).hold_s >= CRITERIA.hold_s - 1e-12
            )
            summary, rows = window_report(
                kind,
                samples[lo : hi + 1],
                samples[0].object_position_m[2],
                samples[dispatch].object_position_m[2],
                prior_hold,
            )
            summaries[kind] = summary
            for row in rows:
                emit(rows_out, row)
    public = {
        "schema": "graduation.canonical.dynamic-physics.v1",
        "scope": "FIXED_TCP_DEVELOPMENT",
        "allocation_sha256": allocation_sha,
        "capture_seal_sha256": seal_sha,
        "private_file_sha256": seal["files"],
        "case_count": len(cases),
        "original_status": original["status"],
        "cases": cases,
        "episode": source["episode"],
        "original_positive_trace": trace,
        "stage_receipts": spans,
        "original_positive_passed": positive["passed"],
        "independent_outcome": asdict(outcome),
        "samples": len(samples),
        "actual_physics_steps": samples[-1].physics_step,
        "actual_dt_s": alloc["physics_dt_s"],
        "max_sample_gap_s": max(
            (b.sim_time_s - a.sim_time_s for a, b in zip(samples, samples[1:], strict=False)),
            default=None,
        ),
        "windows": summaries,
        "window_samples_sha256": sha(output / "window-samples.jsonl"),
        "task_model_calls": 0,
        "hardware_dispatches": 0,
        "formal_claims": 0,
        "visual_feedback_frames_requested": 0,
        "online_physical_truth_inputs": 0,
        "scope_note": "Offline fixture TCPs. Safety/effect qualification and RGB-D feedback "
        "of the separate r593 path are not measured by this branch.",
    }
    write(output / "physics.public.json", public)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    a = sub.add_parser("allocate")
    a.add_argument("--plan", type=Path, required=True)
    for subparser in (a, sub.add_parser("capture"), sub.add_parser("score")):
        subparser.add_argument("--private", type=Path, required=True)
    scor = sub.choices["score"]
    for subparser in (a, scor):
        subparser.add_argument("--output", type=Path, required=True)
    for subparser in (sub.choices["capture"], scor):
        subparser.add_argument("--allocation", type=Path, required=True)
        subparser.add_argument("--allocation-sha256", required=True)
    scor.add_argument("--seal-sha256", required=True)
    args = parser.parse_args()
    if args.mode == "allocate":
        allocate(args.plan, args.private, args.output)
    elif args.mode == "capture":
        return capture(args.allocation, args.allocation_sha256, args.private)
    else:
        score(args.allocation, args.allocation_sha256, args.private, args.seal_sha256, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
