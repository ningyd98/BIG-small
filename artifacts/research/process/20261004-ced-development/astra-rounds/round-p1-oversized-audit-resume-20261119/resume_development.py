"""Read oversized results from the frozen owner and resume only never-started slots."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

from cloud_edge_robot_arm.harness.checkout import verify_checkout
from cloud_edge_robot_arm.harness.config import load_config, strict_json
from cloud_edge_robot_arm.harness.evidence import (
    ASSIGNMENT,
    MANIFEST,
    RESULT,
    SOURCES,
    EpisodeExpectation,
    _artifact,
    _episode_result,
    _json_bytes,
    verify_evidence,
)
from cloud_edge_robot_arm.research.sol_molmo_offline_regression import FrozenCase

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "round-p1-development-readiness-20261119/development"))
import run_development as original  # noqa: E402
from development_plan import canonical, digest, require, score_outcomes, sha, wilson95  # noqa: E402

PLAN_SHA = "0fc36d7ca1ff393c893b6b30fb8cb565b8b0c4cf76671056eeed7fd4e0b20572"
FREEZE_SHA = "ec0f7b0ab2306c3ff838d5cdbea6ee244a68d0ab6fe42e4780599ae9180b23f4"
REGISTERED_LIMIT = 8 * 1024 * 1024
SUPPLEMENTAL_LIMIT = 16 * 1024 * 1024
LIMIT_ERROR = "evidence JSON exceeds 8 MiB"


def attest_plan():
    plan = original.read(HERE / "plan.json")
    require(sha(HERE / "plan.json") == PLAN_SHA, "oversized admission plan changed")
    require(sha(HERE / "plan.md") == plan["plan_md_sha256"], "plan Markdown changed")
    for name, expected in plan["inputs_sha256"].items():
        require(sha(original.REPO / name) == expected, f"oversize plan input differs: {name}")


def bounded_index(root, expectation):
    """Borrow the production path protections and extend only the verified result length."""
    raw_result_size = None
    files = {}
    parsed = {}
    root_fd = os.open(root, os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with _artifact(root_fd, MANIFEST) as stream:
            manifest_raw = _json_bytes(stream)
        manifest = strict_json(manifest_raw)
        require(
            isinstance(manifest, dict)
            and manifest.get("schema_version") == "local.files.v1"
            and isinstance(manifest.get("files"), list),
            "invalid bounded manifest",
        )
        for record in manifest["files"]:
            require(isinstance(record, dict), "invalid bounded manifest row")
            name, size, checksum = (record.get(k) for k in ("path", "bytes", "sha256"))
            require(
                isinstance(name, str)
                and name not in files
                and name != MANIFEST
                and type(size) is int
                and size >= 0
                and isinstance(checksum, str)
                and re.fullmatch("[a-f0-9]{64}", checksum),
                "invalid or duplicate bounded manifest row",
            )
            with _artifact(root_fd, name) as stream:
                require(os.fstat(stream.fileno()).st_size == size, "manifested file length differs")
                if name == RESULT:
                    require(
                        REGISTERED_LIMIT < size <= SUPPLEMENTAL_LIMIT,
                        "result size outside the supplemental range",
                    )
                    data = stream.read(size + 1)
                    require(
                        len(data) == size and digest(data) == checksum,
                        "large result bytes differ from manifest",
                    )
                    parsed[name] = strict_json(data)
                    raw_result_size = size
                elif name in (ASSIGNMENT, SOURCES):
                    data = _json_bytes(stream)
                    require(
                        len(data) == size and digest(data) == checksum,
                        "strict structured original differs from manifest",
                    )
                    parsed[name] = strict_json(data)
                else:
                    require(
                        hashlib.file_digest(stream, "sha256").hexdigest() == checksum,
                        "indexed original SHA differs",
                    )
            files[name] = record
    finally:
        os.close(root_fd)
    require(raw_result_size is not None, "manifested result file is absent")
    result = _episode_result(parsed[RESULT])
    expectation.check(result, parsed.get(ASSIGNMENT), parsed.get(SOURCES))
    return FrozenCase(root, files, {}), result, digest(manifest_raw), raw_result_size


def owned_wrapper(freeze, slot, paths, source, config):
    begin, end, wrapper = (original.read(paths[key]) for key in ("begin", "end", "stdout"))
    unresolved = original.read(paths["audit"].with_suffix(".unresolved.json"))
    require(not paths["audit"].exists(), "normal audit unexpectedly exists")
    claim = original.bound_slot(slot, FREEZE_SHA)
    require(
        all(begin[k] == end[k] == value for k, value in claim.items())
        and end["begin_sha256"] == sha(paths["begin"])
        and all(end[k + "_sha256"] == sha(paths[k]) for k in ("stdout", "stderr")),
        "BEGIN, END, wrapper or assigned identity differs",
    )
    require(
        end["returncode"] == wrapper["wrapper_exit_code"] == 2
        and wrapper["episode_exit_code"] == 0
        and wrapper["signal"] is None
        and wrapper["wrapper_stop_reason"] is None
        and wrapper["status"] == "INCOMPLETE_UNKNOWN"
        and "episode" not in wrapper
        and "evidence" not in wrapper,
        "wrapper did not terminate with the exact known 2/2/0 signature",
    )
    require(
        unresolved["status"] == "STARTED_UNRESOLVED"
        and unresolved["error_type"] == "ValueError"
        and unresolved["message"] == LIMIT_ERROR
        and unresolved["original_end_sha256"] == sha(paths["end"]),
        "original unresolved receipt does not prove the known size limit",
    )
    require(
        Path(wrapper["output"]) == paths["episode"]
        and wrapper["source"]["git_revision"] == freeze["commit"]
        and wrapper["source"]["files"] == source.files == freeze["checkout_selected_files"]
        and wrapper["planned_configuration"] == config.model_dump(mode="json")
        and wrapper["planned_configuration_sha256"] == config.fingerprint()
        and wrapper["model_asset_manifest_sha256"] == freeze["asset_manifest_sha256"],
        "original wrapper ownership, product or configuration differs",
    )
    native = wrapper["native_python"]
    require(
        native["status"] == "READY_TO_DELEGATE"
        and native["executable_sha256"] == freeze["native_python_sha256"]
        and native["registered_overlay"]["sha256"] == freeze["overlay_sha256"]
        and native["r545_admission"]["status"] == "IMPORT_AND_CPU_ABI_PASS",
        "original native receipts differ",
    )
    return {key + "_sha256": sha(paths[key]) for key in ("begin", "end", "stdout", "stderr")} | {
        "original_unresolved_receipt_sha256": sha(paths["audit"].with_suffix(".unresolved.json")),
        "original_wrapper_status": wrapper["status"],
        "process_exit": end["returncode"],
        "wrapper_exit": wrapper["wrapper_exit_code"],
        "native_exit": wrapper["episode_exit_code"],
        "signal": wrapper["signal"],
        "wrapper_stop_reason": wrapper["wrapper_stop_reason"],
    }


def supplemental_audit(freeze, slot, paths):
    _, reader = original.legacy_readers()
    config_path = original.OWNER / "configs" / slot["config"]
    require(sha(config_path) == slot["config_sha256"], "active slot config bytes differ")
    config = load_config(config_path)
    source = verify_checkout(Path(freeze["source"]), config)
    owner = owned_wrapper(freeze, slot, paths, source, config)
    expectation = EpisodeExpectation(source, config, True)
    with_same_cap = paths["episode"]
    try:
        verify_evidence(with_same_cap, expected=expectation)
    except ValueError as exc:
        require(
            str(exc) == LIMIT_ERROR, "strict audit did not reproduce the exact known size limit"
        )
    else:
        raise ValueError("strict audit unexpectedly passed")
    case, result, manifest_sha, size = bounded_index(with_same_cap, expectation)
    episode, job, assignment, role = (
        case.json(name)
        for name in (
            "component/episode.json",
            "worker/job.json",
            "scene-assignment.json",
            "role-binding.json",
        )
    )
    require(
        case.json("worker/runtime_job.json") == job
        and result["job_id"] == job["job_id"]
        and result["episode_id"] == episode["episode_id"]
        and job["status"] == result["worker_status"] == "SUCCEEDED"
        and result["status"] == episode["status"] == "COMPONENTS_COMPLETED"
        and result["terminal_reason"] is None
        and episode.get("terminal_reason") is None
        and job["seed"] == slot["runtime_seed"]
        and job["attempt"] == 1
        and job["source_tree_hash"] == role["bundle_hash"]
        and job["hardware_write_operations"] == []
        and job["real_controller_contacted"] is False
        and job["hardware_motion_observed"] is False
        and result["source_snapshot_status"] == "COMPLETE"
        and not result["changed_source_paths"],
        "native terminal/ownership is outside the exact supplemental window",
    )
    applied = case.json("component/scene-application.json")
    require(applied == episode["scene_application"], "native applied scene copies differ")
    pose = reader.check_pose(slot["scene"], config, assignment, applied)
    source_count = reader.check_sources(role, case.json(SOURCES), freeze["product_sources"], slot)
    models = reader.check_model_evidence(case, result, freeze)
    physical = reader.check_component(case, result, episode)
    backend = original.terminal_attempt(case, job)
    require(
        result["component_success"] is True
        and physical["physical"]["success"] is True
        and physical["physical"]["safety_violation"] is False
        and physical["executed_actions"] == 9
        and physical["terminal_marker_status"] == "OBSERVED",
        "supplemental native success does not independently meet the original criteria",
    )
    ledger = [
        {key: item.get(key) for key in ("request_id", "monetary_cost", "currency", "status")}
        for item in case.json("costs.json")["requests"]
        if item["is_cloud_model"] is True
    ]
    return {
        **owner,
        "scope": "SUPPLEMENTAL_NATIVE_AND_PHYSICAL_AUDIT",
        "strict_audit": "STARTED_UNRESOLVED",
        "strict_failure": LIMIT_ERROR,
        "product_commit": freeze["commit"],
        "freeze_sha256": FREEZE_SHA,
        "supplemental_plan_sha256": PLAN_SHA,
        "supplemental_reader_sha256": sha(Path(__file__)),
        "assignment_id": slot["assignment_id"],
        "pose_seed": slot["pose_seed"],
        "run_instance_id": slot["run_instance_id"],
        "job_id": job["job_id"],
        "episode_id": result["episode_id"],
        "manifest_sha256": manifest_sha,
        "manifest_files": len(case.files),
        "result_bytes": size,
        "result_sha256": case.files[RESULT]["sha256"],
        "supplemental_limit_bytes": SUPPLEMENTAL_LIMIT,
        "source_files_checked": source_count,
        "observed_counters": models,
        "ledger": ledger,
        "applied_pose": pose,
        "terminal_attempt": backend,
        "component_success": result["component_success"],
        "independent_physical_success": physical["physical"]["success"],
        "terminal_reason": result["terminal_reason"],
        **physical,
    }


def prior_assessment(freeze, slot):
    paths = original.slot_paths(original.OWNER, slot)
    status = original.claim_presence(paths)
    if status == "NOT_EXECUTED":
        return status, paths, None
    saved = None
    if status == "AUDITED":
        saved = original.read(paths["audit"])
        audit = original.audit_originals(freeze, slot, FREEZE_SHA, paths)
        require(saved == audit and audit["recognized_terminal"], "strict predecessor audit differs")
        return "STRICT", paths, audit
    require(status == "ENDED_UNVERIFIED", "BEGIN without independent terminal evidence")
    audit = supplemental_audit(freeze, slot, paths)
    return "SUPPLEMENTAL", paths, audit


def supplement_if_missing(slot, evidence):
    directory = original.OWNER / "verification" / "oversized-audit-v1"
    directory.mkdir(exist_ok=True)
    require(directory.resolve() == directory, "supplemental directory redirected")
    path = directory / (slot["assignment_id"] + ".json")
    if path.exists():
        require(original.read(path) == evidence, "prior supplemental audit differs")
    else:
        original.persist(path, evidence)
    return sha(path)


def assessment_rows(freeze):
    records, originals, routes = [], {}, {}
    for slot in original.registered_slots(freeze["allocation"]):
        route, _, result = prior_assessment(freeze, slot)
        identity = slot["assignment_id"]
        routes[identity] = route
        if result is None:
            continue
        originals[identity] = result
        if route == "SUPPLEMENTAL":
            records.append(
                {
                    **{key: slot[key] for key in ("assignment_id", "run_instance_id", "pose_seed")},
                    "status": "STARTED_UNRESOLVED",
                    "component_completed": None,
                    "independent_physical_success": None,
                    "audit_sha256": None,
                }
            )
        else:
            records.append(original.completed_row(slot, result, digest(canonical(result))))
    return records, originals, routes


def layered_report(freeze):
    records, originals, routes = assessment_rows(freeze)
    primary = score_outcomes(freeze["allocation"], records, closed=False)
    fresh = [slot["assignment_id"] for slot in freeze["allocation"]["development"]]
    repeats = [slot["assignment_id"] for slot in freeze["allocation"]["repeats_1802"]]
    native_audited = [originals[key] for key in fresh if key in originals]
    closed = len(native_audited) == len(fresh)

    def metric(key):
        successes = sum(row[key] is True for row in native_audited)
        return {
            "successes": successes,
            "audited": len(native_audited),
            "wilson95": wilson95(successes, len(fresh)) if closed else None,
        }

    all_ids = [row["job_id"] for row in originals.values()]
    episode_ids = [row["episode_id"] for row in originals.values()]
    cloud_ids = [item["request_id"] for row in originals.values() for item in row["ledger"]]
    require(
        len(set(all_ids)) == len(all_ids) == len(set(episode_ids))
        and all(cloud_ids)
        and len(set(cloud_ids)) == len(cloud_ids),
        "trial/request IDs reused",
    )
    return {
        "freeze_sha256": FREEZE_SHA,
        "assembly_scope": "INDEPENDENT_DEVELOPMENT_MUJOCO",
        "preregistered_strict_readout": primary,
        "independent_combined_development": {
            "state": "CLOSED" if closed else "OPEN",
            "assigned": len(fresh),
            "component_complete": metric("component_success"),
            "physical_success": metric("independent_physical_success"),
        },
        "repeats_1802": {identity: originals.get(identity) for identity in repeats},
        "routes": routes,
        "individual_audits": originals,
        "counts": {
            key: sum(row["observed_counters"][key] for row in originals.values())
            for key in ("cloud_requests", "local_generations", "model_loads")
        },
        "billing": original.bill_totals(originals),
        "dispatch_retries": 0,
    }


def expected_started_prefix(states):
    require(len(states) == 22, "expected exactly the original 22 slots")
    require(
        states[:11] == ["AUDITED"] * 10 + ["ENDED_UNVERIFIED"],
        "frozen slots 01–10 and 11 do not have their required prior receipts",
    )
    if "NOT_EXECUTED" in states:
        first_new = states.index("NOT_EXECUTED")
        require(
            all(state == "NOT_EXECUTED" for state in states[first_new:]),
            "already-started slots do not form a prefix",
        )


def resume(freeze, descriptor):
    slots = original.registered_slots(freeze["allocation"])
    expected_started_prefix(
        [original.claim_presence(original.slot_paths(original.OWNER, slot)) for slot in slots]
    )
    for index, slot in enumerate(slots):
        route, paths, result = prior_assessment(freeze, slot)
        if index < 11:
            require(
                route == ("STRICT" if index < 10 else "SUPPLEMENTAL"),
                "initial verified receipt route changed",
            )
        if route == "SUPPLEMENTAL":
            receipt = supplement_if_missing(slot, result)
            print(f"SUPPLEMENTAL {slot['assignment_id']} {receipt}", flush=True)
        if route != "NOT_EXECUTED":
            continue
        try:
            original.launch_slot(freeze, slot, FREEZE_SHA, descriptor)
        except ValueError as exc:
            if str(exc) != LIMIT_ERROR:
                raise
            evidence = supplemental_audit(freeze, slot, paths)
            receipt = supplement_if_missing(slot, evidence)
            print(f"SUPPLEMENTAL {slot['assignment_id']} {receipt}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("verify-11", "resume", "audit"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    attest_plan()
    with original.exclusive_owner() as descriptor:
        freeze = original.freeze_at(FREEZE_SHA)
        if args.action == "resume":
            resume(freeze, descriptor)
            return
        if args.action == "verify-11":
            slot = original.registered_slots(freeze["allocation"])[10]
            require(slot["assignment_id"] == "development-11", "wrong original allocation entry")
            route, _, evidence = prior_assessment(freeze, slot)
            require(route == "SUPPLEMENTAL", "slot 11 did not match the named oversize scope")
        else:
            evidence = layered_report(freeze)
        require(args.output is not None, "readback requires a new output path")
        original.persist(args.output, evidence)
        print(sha(args.output), flush=True)


if __name__ == "__main__":
    main()
