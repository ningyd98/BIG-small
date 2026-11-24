"""Score frozen decisions and independently read back source receipts, clocks and gates."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path

from scripts.graduation.dynamic_vision import plain
from scripts.graduation.perception_io import ROOT, check_sources, pinned, read, sha, write
from scripts.graduation.proposal_gate_binding import (
    FACTS_SOURCE,
    FILES,
    PLAN,
    RAW,
    ROUND,
    digest,
    require,
    require_event_identity,
    utc,
    validate_facts_envelope,
)
from scripts.graduation.proposal_gate_binding_replay import inspect_prequest

from cloud_edge_robot_arm.contracts import RobotState, TaskContract, TaskStep
from cloud_edge_robot_arm.edge.evidence.conditions import OnlineEvidenceSnapshot
from cloud_edge_robot_arm.edge.evidence.validator import validate_b3, validate_evidence
from cloud_edge_robot_arm.research.native_archived_tracker import _ArchivedTargetTracker
from cloud_edge_robot_arm.research.native_collection_grounding import collection_bootstrap_evidence
from cloud_edge_robot_arm.research.raw_episode_v3 import _owner_decode
from cloud_edge_robot_arm.vision.action_evidence import native_action_contract
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.owner_registration import (
    RegisteredCollectionStepBindingV2,
    VisualOriginalPlan,
)


def check_again(raw, case, input_row, output_row):
    case_id = case["id"]
    mixed = ROOT / RAW / case_id / "instance"
    pre = pinned(raw / "blind" / case_id / "pre.json", input_row["pre_sha256"])
    file = mixed / FILES[-1]
    require(
        sha(file) == input_row["frame_sha256"] == sha(raw / "blind" / case_id / "frame.json"),
        "independent source frame mismatch",
    )
    frame = RGBDObservation.model_validate(pinned(file, case["files"][FILES[-1]]))
    archived = pinned(raw / "verdicts" / output_row["file"], output_row["output_sha256"])
    audit = pinned(mixed / "online-audit.json", case["files"]["online-audit.json"])
    run = pinned(mixed / "run.json", case["files"]["run.json"])
    idx = pinned(mixed / "pixel-index.json", case["files"]["pixel-index.json"])
    seal = pinned(mixed / "acquisition-seal.json", case["files"]["acquisition-seal.json"])
    require(
        seal["run_sha256"] == case["files"]["run.json"]
        and seal["audit_sha256"] == case["files"]["online-audit.json"]
        and seal["index_sha256"] == case["files"]["pixel-index.json"]
        and idx["frames"][2] == pre["source_frame"],
        "source acquisition seal mismatch",
    )
    original = _owner_decode(VisualOriginalPlan, audit[0]["original"])
    first = next(x for x in audit if x.get("schema_version") == "native.registered.grounding.v2")
    binding = RegisteredCollectionStepBindingV2.from_payload(first["binding"])
    dispatch = next(x for x in run["actions"] if x["dispatched"])
    command = next(x for x in audit if x.get("phase") == "actual_command_records")
    shield = next(x for x in audit if x.get("phase") == "PRE" and "shield" in x)
    truth_free_pre = next(x for x in audit if x.get("phase") == "PRE" and "state" in x)
    require(
        first["executed_contract"] == pre["executed_contract"]
        and first["grounded_step"] == pre["grounded_step"]
        and first["identity"] == original.to_payload()["identity"]
        and first["binding"] == pre["registered_binding"]
        and first["index"] == 0,
        "independent contract/binding extraction mismatch",
    )
    identity = {
        **pre["case"],
        "frame_id": frame.frame_id,
        "checksum_sha256": frame.checksum_sha256,
        "episode_id": frame.episode_id,
        "binding_sha256": binding.digest(),
        "original_sha256": original.digest(),
    }
    require_event_identity(identity, archived["event"])
    require(
        archived["historic_shield"] == dispatch["pre"]["shield"]
        and archived["historic_shield"]["result"] == shield["shield"]
        and archived["first_command"] == command["rows"][0]
        and command["first_seq"] == command["rows"][0]["command_seq"]
        and archived["dispatch"] == {k: dispatch[k] for k in archived["dispatch"]}
        and archived["registered_requirements"] == truth_free_pre["requirements"]
        and archived["registered_verdicts"] == truth_free_pre["verdicts"]
        and pre["pre_state"] == truth_free_pre["state"],
        "independent original state/conditions/Shield/command readback differs",
    )
    labels = {x["label"]: x for x in run["frame_roles"]}
    now = utc(labels["MOVE_ABOVE/dispatch_source_recheck"]["checked_at"])
    clocks = archived["clocks"]
    require(
        utc(clocks["dispatch_recheck"]) == now
        and utc(clocks["pre_shield"]) == utc(labels["MOVE_ABOVE/PRE_Shield"]["checked_at"])
        and utc(clocks["binding_valid_until"]) == binding.valid_until
        and clocks["capture_age_s"] == (now - frame.captured_at).total_seconds()
        and clocks["binding_remaining_s"] == (binding.valid_until - now).total_seconds(),
        "independent dispatch-recheck time mismatch",
    )
    # Use the other pair of recorded interval endpoints, directly from the mixed source.
    geometry = pinned(ROOT / RAW / case["allocation_file"], case["allocation_sha256"])["geometry"]
    reference = collection_bootstrap_evidence(frame, geometry)
    tracker = _ArchivedTargetTracker(
        frame, reference, evaluated_at=utc(labels["registration-handoff"]["checked_at"])
    )
    actual_state = RobotState.model_validate(truth_free_pre["state"])
    alternate = plain(
        tracker.facts_at(
            frame, actual_state, evaluated_at=utc(labels["MOVE_ABOVE/PRE_Shield"]["checked_at"])
        )
    )
    envelope = {"source": FACTS_SOURCE, "facts": alternate}
    validate_facts_envelope(archived["facts"])
    require(
        archived["facts"] == envelope and archived["facts_sha256"] == digest(envelope),
        "independent color reconstruction mismatch",
    )
    contract, step = (
        TaskContract.model_validate(first["executed_contract"]),
        TaskStep.model_validate(first["grounded_step"]),
    )
    snap = OnlineEvidenceSnapshot(
        frame,
        actual_state,
        alternate,
        contract.plan_version,
        contract.command_seq,
        original.digest(),
    )
    native = native_action_contract(snap, contract, step)
    require(
        plain(native) == archived["native"] and digest(plain(native)) == archived["native_sha256"],
        "independent native evidence contract mismatch",
    )
    for name, method in (("JOINT", validate_evidence), ("B3", validate_b3)):
        result = method(
            native, now, original.digest(), frame.calibration_version, online_evidence=snap
        )
        require(plain(result) == archived["verdicts"][name], "independent native verdict mismatch")
    rules = shield["shield"]["evaluated_rules"]
    return (
        {
            **identity,
            "target_pose_m": archived["target_pose_m"],
            "comparison_now": clocks["dispatch_recheck"],
            "captured_at": clocks["captured_at"],
            "pre_shield_checked_at": clocks["pre_shield"],
            "valid_until": clocks["binding_valid_until"],
            "capture_age_s": clocks["capture_age_s"],
            "remaining_binding_s": clocks["binding_remaining_s"],
            "tracker_clock_intervals_utc": {
                "bootstrap": [clocks["bootstrap_begin"], clocks["bootstrap_end"]],
                "facts": [clocks["conditions_begin"], clocks["pre_shield"]],
            },
            "actual_shield_decision": shield["shield"]["decision"],
            "unmodified": dispatch["pre"]["shield"]["unmodified"],
            "actual_rule_count": len(rules),
            "actual_rule_ids": [x["rule_id"] for x in rules],
            "rule_decisions": dict(Counter(x["decision"] for x in rules)),
            "registered_conditions": dispatch["pre"]["conditions"],
            "grounded_step_preconditions": step.preconditions,
            "contract_command_seq": contract.command_seq,
            "backend_first_command_seq": command["first_seq"],
            "dispatch_step": dispatch["dispatch_step"],
            "first_command_type": command["rows"][0]["type"],
            "ordinary_ttl_s": native.ordinary_ttl_s,
            "expected_duration_s": native.expected_duration_s,
            "tolerance_m": native.allowed_error_m,
            "identity_status": native.evidence.identity_status,
            "sensor_status": native.evidence.sensor_status,
            "geometric_error_bound_m": native.evidence.geometric_error_bound_m,
            "motion_bound_m_s": native.evidence.motion_bound_m_s,
            "facts_sha256": archived["facts_sha256"],
            "native_sha256": archived["native_sha256"],
            "methods": archived["verdicts"],
        },
        pre,
        frame,
    )


def rejected(call):
    try:
        call()
    except (ValueError, PermissionError) as error:
        return {"rejected": True, "reason": str(error)}
    raise ValueError("negative control accepted")


def negatives(raw, all_inputs):
    first, frame = all_inputs[0]
    second, other = all_inputs[1]
    wrong_step = deepcopy(first)
    wrong_step["grounded_step"] = first["executed_contract"]["steps"][1]
    bad_time = deepcopy(first)
    bad_time["roles"][-1]["checked_at"] = first["roles"][0]["checked_at"]
    thin = deepcopy(first)
    thin["shield"]["result"]["evaluated_rules"].pop()
    ground = deepcopy(first)
    ground["provenance"]["facts"] = "GROUNDING_PREPARATION"
    mixed_step = deepcopy(first)
    mixed_step["clock"]["absolute"] += 1
    controls = {
        "different_source_frame": rejected(lambda: inspect_prequest(first, other)),
        "foreign_registered_contract_step": rejected(lambda: inspect_prequest(wrong_step, frame)),
        "nonchronological_dispatch_clock": rejected(lambda: inspect_prequest(bad_time, frame)),
        "wrong_physics_step": rejected(lambda: inspect_prequest(mixed_step, frame)),
        "truncated_original_shield_rules": rejected(lambda: inspect_prequest(thin, frame)),
        "prepared_phase_as_PRE": rejected(lambda: inspect_prequest(ground, frame)),
        "empty_grounding_facts": rejected(
            lambda: validate_facts_envelope({"source": FACTS_SOURCE, "facts": {}})
        ),
        "external_MOVE_TCP_label": rejected(
            lambda: require_event_identity(
                first["case"], dict(first["case"], oracle_label="VALID", skill="MOVE_TCP")
            )
        ),
        "opportunity_swap": rejected(lambda: require_event_identity(first["case"], second["case"])),
    }
    command = [
        sys.executable,
        "-c",
        "from pathlib import Path; import sys; "
        "from scripts.graduation.proposal_gate_binding_replay import restrict_archive_reads; "
        "base=Path(sys.argv[1]); restrict_archive_reads(base/'blind',base/'verdicts'); "
        "Path(sys.argv[2]).open('rb')",
        str(raw.resolve()),
        str((ROOT / RAW / first["case"]["id"] / "instance/run.json").resolve()),
    ]
    done = subprocess.run(command, text=True, capture_output=True, cwd=ROOT)
    require(
        done.returncode != 0
        and "PermissionError: blind input protocol forbids reading this private archive"
        in done.stderr,
        "blind process could access the mixed recording",
    )
    controls["blind_process_mixed_archive_access"] = {
        "rejected": True,
        "reason": "PermissionError in fresh replay process",
    }
    return controls


def score(raw, public):
    plan = pinned(ROUND / "plan.json", PLAN)
    check_sources({"sources_sha256": plan["input_sha256"]})
    alloc = pinned(raw / "allocation.json", sha(ROUND / "allocation.public.json"))
    check_sources({"sources_sha256": alloc["archive_dependencies"]})
    inputs = pinned(raw / "blind/seal.json", sha(ROUND / "blind-inputs.public.json"))
    outputs = read(raw / "verdicts/seal.json")
    require(
        outputs["input_sha256"] == sha(raw / "blind/seal.json")
        and inputs["allocation_sha256"] == sha(raw / "allocation.json"),
        "broken stage receipt chain",
    )
    cohorts = [x["cases"] for x in (alloc, inputs, outputs)]
    ordered = [[row["id"] for row in cases] for cases in cohorts]
    require(
        ordered[0] == ordered[1] == ordered[2] and len(set(ordered[0])) == 8,
        "missing or reordered opportunities",
    )
    results, all_inputs = [], []
    for case, a, b in zip(*cohorts, strict=True):
        result, pre, frame = check_again(raw, case, a, b)
        results.append(result)
        all_inputs.append((pre, frame))
    controls = negatives(raw, all_inputs)
    methods = {}
    for method in ("B3", "JOINT"):
        counts = Counter(x["methods"][method]["status"] for x in results)
        methods[method] = {
            "called": len(results),
            "missing_input": 0,
            "not_called": 0,
            **{status: counts[status] for status in ("VALID", "INVALID", "UNKNOWN")},
            "reasons": dict(
                Counter(reason for x in results for reason in x["methods"][method]["reasons"])
            ),
            "false_accept_rate": None,
            "false_reject_rate": None,
        }
    ages = [v["capture_age_s"] for v in results]
    remaining = [v["remaining_binding_s"] for v in results]
    table = Counter(
        v["methods"]["B3"]["status"] + "|" + v["methods"]["JOINT"]["status"] for v in results
    )
    write(public / "blind-verdicts.public.json", outputs)
    summary = {
        "scope": (
            "offline blind engineering comparison at genuine first MOVE_ABOVE submissions in E"
        ),
        "allocation_sha256": sha(raw / "allocation.json"),
        "blind_input_seal_sha256": sha(raw / "blind/seal.json"),
        "blind_verdict_seal_sha256": sha(raw / "verdicts/seal.json"),
        "plan_sha256": PLAN,
        "placements": len({x["group"] for x in results}),
        "views": dict(Counter(v["view"] for v in results)),
        "allocated_episodes": len(ordered[0]),
        "unique_episodes": len({x["episode_id"] for x in results}),
        "events": len(results),
        "common_historical_shield": len(results),
        "actual_first_submissions": len(results),
        "per_rule_decisions": dict(sum((Counter(v["rule_decisions"]) for v in results), Counter())),
        "historical_shield_decisions": dict(Counter(v["actual_shield_decision"] for v in results)),
        "age_s_range": [min(ages), max(ages)],
        "binding_remaining_s_range": [min(remaining), max(remaining)],
        "methods": methods,
        "paired_B3_JOINT": dict(table),
        "rows": results,
        "matching_independent_oracle_events": 0,
        "unestimable_rates_reason": (
            "no independent outcome labels for these specific MOVE_ABOVE opportunities"
        ),
        "legacy_fixed_MOVE_TCP": (
            "four different physical opportunities; independent labels and gates "
            "have no matching key"
        ),
        "grounded_step_and_registered_preconditions": (
            "report both exactly as recorded; historical Shield receipt is distinct from "
            "the offline method returns"
        ),
        "clock_basis": (
            "last recorded dispatch-source recheck at original UTC; command is recorded "
            "at the corresponding simulation step"
        ),
        "facts_provenance": (
            "reconstructed with registered evidence, original PRE robot state and the same "
            "handoff observation object; full facts equal across observed clock bounds"
        ),
        "new_simulations": 0,
        "new_dispatches": 0,
        "hardware_actions": 0,
        "model_calls": 0,
        "formal_claims": 0,
    }
    write(public / "results.public.json", summary)
    verify = {
        "plan_inputs_rehashed": 77,
        "original_r593_registration_entries": len(all_inputs[0][0]["original"]["source_hashes"]),
        "additional_archive_source_sha256": alloc["archive_dependencies"],
        "positive": dict(
            direct_source_episode_readbacks=len(results),
            paired_native_verdicts_recomputed=2 * len(results),
            original_registered_PRE_receipts=sum(len(v["registered_conditions"]) for v in results),
            original_full_Shield_rules=sum(v["actual_rule_count"] for v in results),
            complete_clock_endpoint_color_fact_checks=3 * len(results),
        ),
        "negative": controls,
        "negative_passed": len(controls),
        "results_sha256": sha(public / "results.public.json"),
        "development_only": True,
        "historical_originals_rehashed_after_scoring": True,
    }
    check_sources({"sources_sha256": plan["input_sha256"]})
    write(public / "verification.public.json", verify)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    score(parser.parse_args().raw, ROUND)
