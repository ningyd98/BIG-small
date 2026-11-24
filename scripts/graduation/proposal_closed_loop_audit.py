"""Read back the complete held-out acquisition, initial states and isolated worker databases."""

from __future__ import annotations

import argparse
import sqlite3
from collections import Counter
from pathlib import Path

from scripts.graduation.dynamic_vision_score import checked_steps, frame_from_row
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write
from scripts.graduation.proposal_closed_loop import allocated_cases, readback_reset


def check_denominator(cases, rows):
    size = len(cases)
    if [r["case_id"] for r in rows] != [c["id"] for c in cases] or any(
        len({r[key] for r in rows}) != size for key in ("episode_id", "job_id")
    ):
        raise ValueError(
            "assigned denominator differs in cases, ordering or physical/worker identities"
        )


def verify_worker(path, lease, row, release):
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        jobs = conn.execute(
            "SELECT job_id,run_id,backend,seed,reproducibility_hash,attempt,max_attempts,status,"
            "source_commit FROM simulation_jobs"
        ).fetchall()
        attempts = conn.execute(
            "SELECT job_id,run_id,attempt,result,ended_at FROM simulation_job_attempts"
        ).fetchall()
        leases = conn.execute(
            "SELECT job_id,worker_id,released_at FROM simulation_job_leases"
        ).fetchall()
    expected = (
        lease["job_id"],
        lease["run_id"],
        "MUJOCO",
        row["seed"],
        row["allocation_sha256"],
        1,
        1,
        lease["final_job_status"],
        release["baseline"],
    )
    if (
        jobs != [expected]
        or len(attempts) != 1
        or attempts[0][0:4] != (expected[0], expected[1], 1, expected[7])
        or not attempts[0][4]
        or len(leases) != 1
        or leases[0][:2] != (expected[0], lease["worker"])
        or not leases[0][2]
        or lease["lease_released"] is not True
        or expected[1] != release["case"]["visual_id"].replace("/", ":")
    ):
        raise ValueError("actual job, single attempt or released lease differs from the run")


def read_case(root, row, manifest_sha):
    folder = root / row["id"]
    raw = folder / "instance"
    allocation = pinned(root / row["allocation_file"], row["allocation_sha256"])
    invocation = read(folder / "invocation.json")
    process = read(folder / "process-receipt.json")
    receipt = read(raw / "capture-receipt.json")
    start = pinned(raw / "started.json", receipt["start_receipt_sha256"])
    if (
        start["case_id"] != receipt["case_id"]
        or start["case_id"] != row["id"]
        or receipt["view"] != row["view"]
        or start["allocation_sha256"] != row["allocation_sha256"]
        or receipt["allocation_sha256"] != row["allocation_sha256"]
        or start["master_sha256"] != manifest_sha
        or receipt["master_sha256"] != manifest_sha
        or start["attempt"] != 1
        or process["returncode"] != 0
        or invocation["argv"][-4:] != start["command"][-4:]
    ):
        raise ValueError("heldout command, job scope, process receipt or manifest mismatch")
    seal = pinned(raw / "acquisition-seal.json", receipt["source_seal_sha256"])
    if seal != receipt["original_data"]:
        raise ValueError("capture receipt differs from the original acquisition seal")
    audit = pinned(raw / "online-audit.json", seal["audit_sha256"])
    run = pinned(raw / "run.json", seal["run_sha256"])
    truth = pinned(raw / "offline-truth.json", seal["truth_sha256"])
    index = pinned(raw / "pixel-index.json", seal["index_sha256"])
    resets = pinned(raw / "reset-observed.json", receipt["reset_observed_sha256"])
    reset = readback_reset(row, resets)
    setup = pinned(raw / "camera-setup.json", receipt["camera_setup_sha256"])
    if (
        setup != []
        or row["view"] != "nominal"
        or reset != receipt["physical_reset"]
        or reset["episode_id"] != truth["episode"]
        or index["episode"] != truth["episode"]
        or truth["allocation_sha256"] != row["allocation_sha256"]
        or index["allocation_sha256"] != row["allocation_sha256"]
    ):
        raise ValueError("camera setup, original reset, truth and frame source mismatch")
    steps = checked_steps(
        truth["samples"], truth["episode"], allocation["asset_sha256"], truth["asset_sha256"]
    )
    if steps[0] != resets[1]["result"]["physics_state"]:
        raise ValueError("reset operation return and step-zero independent measurement differ")
    ids = set()
    files = set()
    for frame_row in index["frames"]:
        frame = frame_from_row(
            raw, frame_row, index["episode"], index["scene"], allocation["geometry"]
        )
        if (
            frame.frame_id in ids
            or frame_row["file"] in files
            or frame_row["physics_step"] not in steps
        ):
            raise ValueError("duplicate frame or frame missing from the complete trajectory")
        ids.add(frame.frame_id)
        files.add(frame_row["file"])
    if files != {str(p.relative_to(raw)) for p in (raw / "frames").glob("*.json")}:
        raise ValueError("frame index does not cover every retained frame")
    lease = run["lease_summary"]
    verify_worker(raw / "development-worker.db", lease, row, allocation)
    if (
        run.get("stop") != receipt["stop"]
        or receipt["frames"] != len(ids)
        or receipt["last_step"] != max(steps)
        or receipt["lease"] != lease
    ):
        raise ValueError("captured results disagree with originals")
    commands = Counter(
        r["type"]
        for event in audit
        if event.get("phase") == "actual_command_records"
        for r in event["rows"]
        if r["accepted"]
    )
    stages = run["actions"]
    safe = run.get("safe_stop")
    if safe is not None and not (
        safe["success"] and safe["state_after"]["estop_engaged"] and safe["state_after"]["stopped"]
    ):
        raise ValueError("recorded terminal stop did not engage")
    return {
        "case_id": row["id"],
        "group": row["group"],
        "view": row["view"],
        "seed": row["seed"],
        "episode_id": index["episode"],
        "job_id": lease["job_id"],
        "worker_status": lease["final_job_status"],
        "worker_attempt": 1,
        "worker_released": True,
        "actual_reset": reset,
        "frames": len(ids),
        "physics_steps": max(steps),
        "dense_state_samples": len(steps),
        "executor_entries": sum(s.get("executor_entered", False) for s in stages),
        "post_passes": sum(s["status"] == "PASS" for s in stages),
        "actions": receipt["stages"],
        "stop": run.get("stop"),
        "servo_terminal_reason": next(
            (s["servo_terminal_reason"] for s in stages if s.get("servo_terminal_reason")), None
        ),
        "accepted_executor_command_counts": dict(commands),
        "safe_stop_engaged": safe is not None,
        "wall_s": receipt["wall_s"],
        "independent_frames_read": len(ids),
        "original_source_sha256": seal,
        "job_database_sha256": sha(raw / "development-worker.db"),
        "allocation_sha256": row["allocation_sha256"],
        "capture_receipt_sha256": sha(raw / "capture-receipt.json"),
        "reset_observed_sha256": receipt["reset_observed_sha256"],
        "console_sha256": sha(folder / "capture-console.log"),
        "invocation_sha256": sha(folder / "invocation.json"),
        "process_receipt_sha256": sha(folder / "process-receipt.json"),
    }


def audit(manifest, manifest_sha, root, output):
    master = pinned(manifest, manifest_sha)
    if sha(root / "allocation.public.json") != manifest_sha:
        raise ValueError("allocated public and local manifests differ")
    cases = allocated_cases(master["online_selected_view"])
    entries = master["cases"]
    if [{k: r[k] for k in cases[0]} for r in entries] != cases:
        raise ValueError("issued groups differ from the committed preallocation")
    rows = [read_case(root, r, manifest_sha) for r in entries]
    check_denominator(cases, rows)
    write(
        output,
        {
            "schema": "proposal.heldout.development.acquisition.v1",
            "scope": master["scope"],
            "source_manifest_sha256": manifest_sha,
            "offline_selected_view": master["offline_selected_view"],
            "online_view": master["online_selected_view"],
            "allocated_groups": len(cases),
            "completed_acquisitions": len(rows),
            "physical_steps_executed": sum(r["physics_steps"] for r in rows),
            "dense_state_samples": sum(r["dense_state_samples"] for r in rows),
            "rgbd_frames_independently_read": sum(r["independent_frames_read"] for r in rows),
            "cases": rows,
            "formal_claims": 0,
            "hardware_actions": 0,
            "model_calls": 0,
            "readback_script_sha256": sha(Path(__file__)),
            "readback_test_sha256": sha(
                ROOT / "tests/test_graduation_proposal_closed_loop_audit.py"
            ),
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("manifest_sha")
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    audit(**vars(parser.parse_args()))
