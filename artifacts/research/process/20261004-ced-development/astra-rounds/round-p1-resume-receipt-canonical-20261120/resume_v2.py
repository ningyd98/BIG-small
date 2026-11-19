"""Preserve the exact serialized receipts when resuming the original owner."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "round-p1-oversized-audit-resume-20261119"))
import resume_development as v1  # noqa: E402

original = v1.original
canonical = v1.canonical
sha = v1.sha
require = v1.require
PLAN_SHA = "c4ea817c424a56b3cb46cde6da474947dce6d04849f2764ace6b94fa3528a448"
V1_SHA = "5f3a5289654fd41e76734e9151a7c88fbb7abc41e026b6c5313931a58826e4b3"
FIXED_SUPPLEMENT_SHA = "d1758e7137ec0f11a880893933f5b3d026188389b2830b88674e07a8e53be637"


def attest():
    path = HERE / "plan.json"
    require(sha(path) == PLAN_SHA, "canonical replay plan changed")
    plan = original.read(path)
    require(sha(path.with_suffix(".md")) == plan["plan_md_sha256"], "plan Markdown changed")
    for name, expected in plan["inputs_sha256"].items():
        require(sha(original.REPO / name) == expected, f"canonical plan input differs: {name}")
    require(sha(Path(v1.__file__)) == V1_SHA, "v1 reader byte identity differs")
    v1.attest_plan()


def compare_checkpoint(path, fresh):
    require(path.is_file() and not path.is_symlink(), "checkpoint absent or not a regular file")
    saved = path.read_bytes()
    v1.strict_json(saved)
    require(saved == canonical(fresh), "saved checkpoint bytes differ from canonical fresh audit")
    return v1.digest(saved)


def check_supplement_source(identity, evidence):
    require(evidence["supplemental_reader_sha256"] == V1_SHA, "supplemental v1 reader SHA differs")
    if identity == "development-11":
        require(
            v1.digest(canonical(evidence)) == FIXED_SUPPLEMENT_SHA,
            "development-11 original supplement differs",
        )


def supplemental_checkpoint(identity, evidence, *, save=False):
    check_supplement_source(identity, evidence)
    directory = original.OWNER / "verification" / "oversized-audit-v1"
    require(directory.resolve() == directory, "supplemental evidence directory moved")
    path = directory / (identity + ".json")
    if path.exists() or path.is_symlink():
        return compare_checkpoint(path, evidence)
    if save:
        directory.mkdir(exist_ok=True)
        original.persist(path, evidence)
        return compare_checkpoint(path, evidence)
    return v1.digest(canonical(evidence))


def fresh_assessment(freeze, slot, *, save_supplement=False):
    paths = original.slot_paths(original.OWNER, slot)
    state = original.claim_presence(paths)
    if state == "NOT_EXECUTED":
        return state, None, None
    if state == "AUDITED":
        report = original.audit_originals(freeze, slot, v1.FREEZE_SHA, paths)
        evidence_sha = compare_checkpoint(paths["audit"], report)
        require(report["recognized_terminal"], "strict predecessor terminal not recognized")
        return "STRICT", report, evidence_sha
    require(state == "ENDED_UNVERIFIED", "started slot lacks complete END")
    report = v1.supplemental_audit(freeze, slot, paths)
    evidence_sha = supplemental_checkpoint(
        slot["assignment_id"],
        report,
        save=save_supplement,
    )
    return "SUPPLEMENTAL", report, evidence_sha


def verified_prefix(freeze, *, save_supplement=False):
    slots = original.registered_slots(freeze["allocation"])
    v1.expected_started_prefix(
        [original.claim_presence(original.slot_paths(original.OWNER, slot)) for slot in slots]
    )
    verified = {}
    for index, slot in enumerate(slots[:11]):
        route, _, evidence_sha = fresh_assessment(freeze, slot, save_supplement=save_supplement)
        require(route == ("STRICT" if index < 10 else "SUPPLEMENTAL"), "prior audit route changed")
        verified[slot["assignment_id"]] = {"route": route, "sha256": evidence_sha}
    return {
        "checked_prefix_count": len(verified),
        "checkpoints": verified,
        "v1_reader_sha256": V1_SHA,
        "frozen_owner_sha256": v1.FREEZE_SHA,
    }


def resume(freeze, descriptor):
    prefix = verified_prefix(freeze, save_supplement=True)
    print(
        f"CHECKPOINTS_VERIFIED {prefix['checked_prefix_count']} "
        f"{prefix['checkpoints']['development-11']['sha256']}",
        flush=True,
    )
    for slot in original.registered_slots(freeze["allocation"])[11:]:
        route, _, _ = fresh_assessment(freeze, slot, save_supplement=True)
        if route != "NOT_EXECUTED":
            continue
        try:
            original.launch_slot(freeze, slot, v1.FREEZE_SHA, descriptor)
        except ValueError as exc:
            if str(exc) != v1.LIMIT_ERROR:
                raise
            route, _, evidence_sha = fresh_assessment(freeze, slot, save_supplement=True)
            require(route == "SUPPLEMENTAL", "size-dependent supplemental verification failed")
            print(f"SUPPLEMENTAL {slot['assignment_id']} {evidence_sha}", flush=True)


def report(freeze):
    allocation = freeze["allocation"]
    slots = original.registered_slots(allocation)
    records, readings, routes = [], {}, {}
    for slot in slots:
        identity = slot["assignment_id"]
        route, value, evidence_sha = fresh_assessment(freeze, slot)
        routes[identity] = route
        if value is None:
            continue
        readings[identity] = value
        if route == "STRICT":
            records.append(original.completed_row(slot, value, evidence_sha))
        else:
            records.append(
                {
                    **{k: slot[k] for k in ("assignment_id", "run_instance_id", "pose_seed")},
                    "status": "STARTED_UNRESOLVED",
                    "component_completed": None,
                    "independent_physical_success": None,
                    "audit_sha256": None,
                }
            )
    primary = v1.score_outcomes(allocation, records, closed=False)
    fresh = [slot["assignment_id"] for slot in allocation["development"]]
    repeated = [slot["assignment_id"] for slot in allocation["repeats_1802"]]
    known = [readings[key] for key in fresh if key in readings]

    def metric(key):
        n = sum(row[key] is True for row in known)
        return {
            "successes": n,
            "audited": len(known),
            "wilson95": v1.wilson95(n, len(fresh)) if len(known) == len(fresh) else None,
        }

    episode_ids = [row["episode_id"] for row in readings.values()]
    job_ids = [row["job_id"] for row in readings.values()]
    request_ids = [item["request_id"] for row in readings.values() for item in row["ledger"]]
    require(
        len(episode_ids) == len(set(episode_ids)) == len(set(job_ids))
        and all(request_ids)
        and len(set(request_ids)) == len(request_ids),
        "trial or request identity is reused",
    )
    return {
        "owner_freeze_sha256": v1.FREEZE_SHA,
        "canonical_comparator_plan_sha256": PLAN_SHA,
        "original_strict_readout": primary,
        "independent_development": {
            "component_complete": metric("component_success"),
            "physical_success": metric("independent_physical_success"),
        },
        "original_wrapper_complete": {
            "passed": sum(
                routes[key] == "STRICT"
                and readings[key]["component_success"] is True
                and readings[key]["wrapper_exit_code"] == 0
                for key in fresh
            ),
            "assigned": len(fresh),
        },
        "repeats_1802": {key: readings.get(key) for key in repeated},
        "routes": routes,
        "individual_audits": readings,
        "counts": {
            key: sum(row["observed_counters"][key] for row in readings.values())
            for key in ("cloud_requests", "local_generations", "model_loads")
        },
        "billing": original.bill_totals(readings),
        "dispatch_retries": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("verify-prefix", "resume", "audit"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    attest()
    with original.exclusive_owner() as descriptor:
        freeze = original.freeze_at(v1.FREEZE_SHA)
        if args.action == "resume":
            resume(freeze, descriptor)
            return
        require(args.output is not None, "readback requires a new output path")
        result = verified_prefix(freeze) if args.action == "verify-prefix" else report(freeze)
        original.persist(args.output, result)
        print(sha(args.output), flush=True)


if __name__ == "__main__":
    main()
