"""Derive a small shareable readback from the original development receipts and decisions."""

import argparse
from pathlib import Path

from scripts.graduation.g1_complete_trials import PRIVATE, ROUND, select_slots, write_once
from scripts.graduation.perception_io import ROOT, pinned, read, sha


def summarize(label):
    private = ROOT / PRIVATE
    directory = private / "batches" / label
    allocation = read(directory / "allocation.json")
    generation = allocation["runtime_build_sha256"]
    tree = private / "builds" / generation / "runtime-source"
    pinned(tree / "runtime-build.json", generation)
    registration = pinned(private / "registration.json", allocation["registration_sha256"])
    cases = []
    for slot in select_slots(registration, label):
        cid = slot["id"]
        row = next(r for r in allocation["cases"] if r["id"] == cid)
        case_dir = directory / cid
        pinned(case_dir / "allocation.json", row["allocation_sha256"])
        raw = case_dir / "instance"
        if not (case_dir / "attempt.json").exists():
            cases.append(dict(id=cid, claimed=False))
            continue
        attempt = sha(case_dir / "attempt.json")
        started = read(raw / "started.json")
        assert started["claim_sha256"] == attempt
        receipt = raw / "receipt.json"
        if not receipt.exists():
            cases.append(dict(id=cid, claimed=True, interruption=read(raw / "interrupted.json")))
            continue
        seal = read(raw / "acquisition-seal.json")
        evidence = pinned(raw / "run.json", seal["run_sha256"])
        local_seal = read(raw / "local-clearance-seal.json")
        assert local_seal["attempt_sha256"] == attempt
        assert local_seal["acquisition_seal_sha256"] == sha(raw / "acquisition-seal.json")
        local = pinned(raw / "local-clearance.json", local_seal["local_clearance_sha256"])
        assert local["calibration_sha256"] == allocation["calibration_sha256"]
        score_path = case_dir / "independent-score.json"
        result = None
        if score_path.exists():
            score = read(score_path)
            assert score["receipt_sha256"] == sha(receipt)
            assert score["runtime_build_sha256"] == generation
            actual = score["result"]
            outcome = actual.get("independent_physical_outcome", {})
            result = dict(
                score_sha256=sha(score_path),
                qualified=score["qualified"],
                complete_feedback_ok=score["complete_feedback_ok"],
                cold_passes=[s["result_sha256"] for s in score["independent_reads"]],
                dispatched=actual.get("dispatched"),
                verified_posts=actual.get("verified_posts"),
                physical_success=actual.get("physical_success"),
                lift_m=outcome.get("measured_lift_m"),
                hold_s=outcome.get("hold_s"),
                placed_stable_s=outcome.get("placed_stable_s"),
                bilateral_steps=actual.get("contacts", {}).get("bilateral_cube_steps"),
                forbidden_contact_steps=actual.get("hand_contacts", {}).get(
                    "board_or_support_hand_or_finger_steps"
                ),
                feedback=score["feedback"],
            )
        pre = [
            {
                k: r.get(k)
                for k in (
                    "phase",
                    "skill",
                    "physics_step",
                    "frame_id",
                    "checksum_sha256",
                    "reason",
                    "status",
                    "gate_ms",
                    "capture_through_gate_ms",
                )
            }
            for r in local["rows"]
            if r["phase"] != "FEEDBACK" or r["status"] != "CLEAR"
        ]
        errors = []
        for path in sorted(case_dir.glob("independent-readback-*/reader-*/process.log")):
            lines = path.read_text().splitlines()
            if lines and "Traceback (most recent call last):" in lines:
                errors.append(dict(process_sha256=sha(path), error=lines[-1]))
        cases.append(
            dict(
                id=cid,
                claimed=True,
                attempt_sha256=attempt,
                receipt_sha256=sha(receipt),
                acquisition_sha256=sha(raw / "acquisition-seal.json"),
                local_clearance_sha256=local_seal["local_clearance_sha256"],
                issued=sum(a.get("dispatched") is True for a in evidence["actions"]),
                stop=evidence.get("stop"),
                handoff=evidence.get("registered_handoff_clock"),
                renderer=evidence.get("development_environment", {}).get("renderer"),
                decisions=pre,
                failed_feedback=local.get("failed_feedback", []),
                independently_scored=result,
                cold_read_failures=errors,
            )
        )
    return dict(
        scope=allocation["scope"],
        label=label,
        runtime_build_sha256=generation,
        calibration_sha256=allocation["calibration_sha256"],
        batch_sha256=sha(directory / "allocation.json"),
        formal_claims=0,
        hardware_actions=0,
        cases=cases,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("label")
    args = parser.parse_args()
    destination = ROOT / ROUND / (args.label + ".public.json")
    write_once(destination, summarize(args.label))
    print(sha(Path(destination)))
