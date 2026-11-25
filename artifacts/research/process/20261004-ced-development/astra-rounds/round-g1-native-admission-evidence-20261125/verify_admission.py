"""Recheck the native two-slot admission fix directly against the sealed worker records."""

from copy import deepcopy
from pathlib import Path

from scripts.graduation.g1_complete_trials import PRIVATE, write_once
from scripts.graduation.perception_io import ROOT, pinned, read, sha
from scripts.graduation.proposal_scoring import check_audit


def refused(actions, audit):
    try:
        check_audit(actions, audit)
    except ValueError as error:
        return str(error)
    raise ValueError("a missing or crossed native record was accepted")


def check(cid):
    outputs = []
    for label in ("train-preflight-02", "train-preflight-03"):
        case = ROOT / PRIVATE / "batches" / label / cid
        raw = case / "instance"
        seal = read(raw / "acquisition-seal.json")
        run = pinned(raw / "run.json", seal["run_sha256"])
        audit = pinned(raw / "online-audit.json", seal["audit_sha256"])
        assert all(not row.get("dispatched") for row in run["actions"])
        assert run["stop"]["reason"] == "DEVELOPMENT_PREFLIGHT_PASSED_BEFORE_FIRST_DISPATCH"
        row = dict(
            batch=label,
            native_seal_sha256=sha(raw / "acquisition-seal.json"),
            stop=run["stop"],
            bootstrap_ms=run["registered_handoff_clock"]["capture_through_bootstrap_ms"],
        )
        if label.endswith("02"):
            row["original_cold_error"] = refused(run["actions"], audit)
        else:
            check_audit(run["actions"], audit)
            verdicts = [r for r in audit if r.get("phase") == "PRE" and "shield" in r]
            assert len(verdicts) == 1
            shield = verdicts[0]
            pre = run["actions"][0]["pre"]
            assert pre["frame_id"] == shield["frame_id"]
            score = read(case / "independent-score.json")
            hashes = [v["result_sha256"] for v in score["independent_reads"]]
            assert len(hashes) == 2 and len(set(hashes)) == 1 and not score["qualified"]
            changed = deepcopy(audit)
            next(r for r in changed if r.get("phase") == "PRE" and "shield" in r)["frame_id"] += (
                "-other"
            )
            row.update(
                cold_hashes=hashes,
                score_sha256=sha(case / "independent-score.json"),
                pre_frame_id=pre["frame_id"],
                receipt_sha256=sha(raw / "receipt.json"),
                missing_negative=refused(run["actions"], [r for r in audit if r is not shield]),
                crossed_negative=refused(run["actions"], changed),
            )
        outputs.append(row)
    return {"id": cid, "runs": outputs}


if __name__ == "__main__":
    out = Path(__file__).resolve().parent
    plan = pinned(
        out / "plan.json", "6114da30cb828d0b1a17e9f2d4bdb9c687d9f2f5e53f13f957b79975cce5411d"
    )
    write_once(
        out / "qualification.public.json",
        dict(
            baseline=plan["baseline_commit"],
            registered_preconditions=[check(cid) for cid in ("cvfix-t01", "cvfix-t02")],
            preflight_commands=0,
            active_feedback_samples=0,
            formal_claims=0,
        ),
    )
