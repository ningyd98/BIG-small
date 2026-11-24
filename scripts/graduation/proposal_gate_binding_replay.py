"""Reconstruct the bound historical PRE input and invoke both unmodified native gates."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from scripts.graduation.dynamic_vision import plain
from scripts.graduation.perception_io import ROOT, pinned, sha, write
from scripts.graduation.proposal_gate_binding import (
    FACTS_SOURCE,
    PRE_COLUMNS,
    RAW,
    clock_window,
    digest,
    fresh_track_interval,
    require,
    utc,
    validate_facts_envelope,
)

from cloud_edge_robot_arm.contracts import RobotState, TaskContract, TaskStep
from cloud_edge_robot_arm.edge.evidence.conditions import OnlineEvidenceSnapshot
from cloud_edge_robot_arm.edge.evidence.validator import validate_b3, validate_evidence
from cloud_edge_robot_arm.edge.safety.rules import ALL_RULES
from cloud_edge_robot_arm.research.native_archived_tracker import _ArchivedTargetTracker
from cloud_edge_robot_arm.research.native_collection_grounding import (
    collection_bootstrap_evidence,
    registered_expected_conditions_v2,
    validate_camera,
)
from cloud_edge_robot_arm.research.raw_episode_v3 import _owner_decode
from cloud_edge_robot_arm.vision.action_evidence import native_action_contract
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.owner_registration import (
    RegisteredCollectionStepBindingV2,
    VisualOriginalPlan,
)


def inspect_prequest(v, frame):
    require(
        set(v) == PRE_COLUMNS and v["provenance"]["facts"] == FACTS_SOURCE,
        "wrong PRE phase or non-whitelisted columns",
    )
    original = _owner_decode(VisualOriginalPlan, v["original"])
    binding = RegisteredCollectionStepBindingV2.from_payload(v["registered_binding"])
    require(
        original.to_payload() == v["original"] and binding.to_payload() == v["registered_binding"],
        "noncanonical original or registered binding",
    )
    contract = TaskContract.model_validate(v["executed_contract"])
    step = TaskStep.model_validate(v["grounded_step"])
    prepared = binding.to_payload()["prepared"]
    clock, first_role, index = v["clock"], v["roles"][0], v["source_frame"]
    window = clock_window(v["roles"])
    dispatch, command = v["dispatch"], v["first_command"]
    reference, candidate, grounding = (
        v["dispatch_reference"],
        v["candidate"],
        v["grounding_reference"],
    )
    require(
        frame.observation_id == frame.frame_id and frame.episode_id and frame.calibration_version,
        "original RGB-D identity missing",
    )
    require(
        all(
            row["frame_id"] == frame.frame_id and row["checksum_sha256"] == frame.checksum_sha256
            for row in (index, first_role, reference, candidate, grounding, clock)
        )
        and utc(first_role["captured_at"]) == frame.captured_at
        and frame.sim_time_s == first_role["sim_time_s"],
        "swapped observation, checksum or time",
    )
    identity = v["identity"]
    require(
        identity == original.to_payload()["identity"] == prepared["current_identity"]
        and identity["episode_id"]
        == frame.episode_id
        == first_role["episode_id"]
        == clock["episode"]
        == command["episode_id"]
        and identity["run_id"].endswith(":" + v["case"]["id"]),
        "original owner or episode mismatch",
    )
    require(
        prepared["observation_id"] == frame.observation_id
        and prepared["observation_checksum_sha256"] == frame.checksum_sha256
        and prepared["calibration_version"] == frame.calibration_version,
        "wrong bound evidence",
    )
    require(
        v["inventory_digest"]
        == digest(v["original"]["source_hashes"])
        == digest(prepared["grounding_source_hashes"])
        and digest(v["geometry"]["camera"]) == v["case"]["camera_configuration_sha256"],
        "different registration or camera inventory",
    )
    require(
        binding.digest()
        == v["binding_sha256"]
        == candidate["binding_sha256"]
        == grounding["binding_sha256"]
        == clock["binding_sha256"]
        and original.digest() == v["original_sha256"] == prepared["original_plan_hash"],
        "unbound original plan",
    )
    require(
        v["grounded_step"] == v["executed_contract"]["steps"][0] == prepared["grounded_step"]
        and step == contract.steps[0]
        and step.step_id == clock["step_id"]
        and contract.current_step_id in (None, step.step_id)
        and original.contract.steps[0].step_id == step.step_id
        and clock["phase"] == "PRE"
        and step.skill.value
        == clock["skill"]
        == dispatch["skill"]
        == candidate["skill"]
        == grounding["skill"]
        == "MOVE_ABOVE",
        "wrong grounded contract step",
    )
    require(
        candidate["target_pose_m"] == step.parameters["target_pose"]
        and contract.plan_version
        == original.contract.plan_version
        == prepared["plan_version"]
        == clock["plan_version"]
        == 1
        and contract.command_seq
        == original.contract.command_seq
        == prepared["command_seq"]
        == clock["command_seq"]
        == 1
        and contract.task_id == clock["task_id"] == identity["task_id"],
        "wrong target or task command",
    )
    require(
        first_role["physics_step"]
        == index["physics_step"]
        == reference["physics_step"]
        == clock["origin"]
        == clock["absolute"]
        == dispatch["entered_step"]
        == dispatch["dispatch_step"]
        == command["physics_step"]
        and clock["relative"] == 0
        and dispatch["dispatched"] is True
        and dispatch["executor_entered"] is True
        and command["accepted"] is True
        and command["type"] == "joint_target",
        "archived first actual command does not bind to the PRE opportunity",
    )
    require(
        utc(window["bootstrap_end"])
        <= utc(prepared["created_at"])
        <= utc(window["conditions_begin"])
        <= utc(v["pre_preview_time"])
        <= utc(window["pre_shield"])
        and utc(grounding["valid_until"]) == binding.valid_until == utc(prepared["valid_until"]),
        "chronology of PRE binding or registered preview differs",
    )
    expected = plain(registered_expected_conditions_v2(original, binding, "PRE"))
    require(
        expected == v["registered_requirements"]
        and [x["name"] for x in expected] == [x["condition_name"] for x in v["registered_verdicts"]]
        and all(x["observation_id"] == frame.observation_id for x in v["registered_verdicts"]),
        "wrong registered conditions or condition receipts",
    )
    shield = v["shield"]
    result = shield["result"]
    require(
        shield["allowed"] is result["allowed"]
        and shield["unmodified"] is (result["limited_parameters"] is None)
        and [row["rule_id"] for row in result["evaluated_rules"]]
        == [rule.rule_id for rule in ALL_RULES],
        "incomplete original Shield rules or mismatched decision",
    )
    validate_camera(frame, v["geometry"])
    return original, contract, step, window


def reconstruct_facts(v, frame, state, window):
    # The live wrapper constructs exactly one OpenCVTargetTracker with the following evidence.
    # The byte-reader subclass substitutes only the binding UTC for its original implementation.
    evidence = collection_bootstrap_evidence(frame, v["geometry"])
    reference = v["dispatch_reference"]
    require(
        list(evidence["original_pixel_target"]) == reference["target_pixel"]
        and list(evidence["original_pixel_destination"]) == reference["destination_pixel"]
        and plain(evidence["resolved_top_grasp_tcp"]) == reference["top_grasp_tcp_m"],
        "original color tracker reference geometry differs",
    )
    for start, end in (("bootstrap_begin", "bootstrap_end"), ("conditions_begin", "pre_shield")):
        fresh_track_interval(frame.captured_at, utc(window[start]), utc(window[end]))
    results = []
    for create, calc in (("bootstrap_begin", "conditions_begin"), ("bootstrap_end", "pre_shield")):
        tracker = _ArchivedTargetTracker(frame, evidence, evaluated_at=utc(window[create]))
        facts = tracker.facts_at(frame, state, evaluated_at=utc(window[calc]))
        require(
            tracker.last_binding_evaluated_at == utc(window[calc]), "archived time adapter mismatch"
        )
        results.append(plain(facts))
    require(results[0] == results[1], "facts not invariant across historical timestamp bounds")
    result = {"source": FACTS_SOURCE, "facts": results[0]}
    validate_facts_envelope(result)
    return result


def replay(v, frame):
    original, contract, step, window = inspect_prequest(v, frame)
    state = RobotState.model_validate(v["pre_state"])
    envelope = reconstruct_facts(v, frame, state, window)
    snap = OnlineEvidenceSnapshot(
        frame,
        state,
        envelope["facts"],
        contract.plan_version,
        contract.command_seq,
        original.digest(),
    )
    native = native_action_contract(snap, contract, step)
    now = utc(window["dispatch_recheck"])
    method_args = (native, now, original.digest(), frame.calibration_version)
    verdicts = {
        "B3": plain(validate_b3(*method_args, online_evidence=snap)),
        "JOINT": plain(validate_evidence(*method_args, online_evidence=snap)),
    }
    expiry = utc(v["grounding_reference"]["valid_until"])
    return {
        "event": {
            **v["case"],
            "frame_id": frame.frame_id,
            "checksum_sha256": frame.checksum_sha256,
            "episode_id": frame.episode_id,
            "binding_sha256": v["binding_sha256"],
            "original_sha256": original.digest(),
        },
        "clocks": {
            **window,
            "captured_at": frame.captured_at.isoformat(),
            "binding_valid_until": expiry.isoformat(),
            "capture_age_s": (now - frame.captured_at).total_seconds(),
            "binding_remaining_s": (expiry - now).total_seconds(),
        },
        "facts": envelope,
        "facts_sha256": digest(envelope),
        "native": plain(native),
        "native_sha256": digest(plain(native)),
        "verdicts": verdicts,
        "historic_shield": v["shield"],
        "registered_requirements": v["registered_requirements"],
        "registered_verdicts": v["registered_verdicts"],
        "first_command": v["first_command"],
        "dispatch": v["dispatch"],
        "target_pose_m": v["candidate"]["target_pose_m"],
        "tracker_clock_method": (
            "both recorded interval endpoints have identical full facts; "
            "geometry and clock branch invariant"
        ),
    }


def restrict_archive_reads(blind, output):
    # Audited process restriction for mixed and oracle archives, including sibling studies.
    private_root = (ROOT / RAW).resolve().parents[1]
    require(
        blind.is_relative_to(private_root / "gate-binding")
        and output.is_relative_to(private_root / "gate-binding")
        and not blind.is_relative_to(output)
        and not output.is_relative_to(blind),
        "dedicated blind input and verdict stores required",
    )
    blocked_tree = [ROOT / "artifacts", ROOT / "experiments/results", ROOT / "results"]

    def audit(event, args):
        if event != "open" or isinstance(args[0], int):
            return
        path = Path(os.fsdecode(args[0])).resolve()
        if path.is_relative_to(private_root):
            if not (path.is_relative_to(blind) or path.is_relative_to(output)):
                raise PermissionError("blind input protocol forbids reading this private archive")
        elif any(path.is_relative_to(p) for p in blocked_tree):
            raise PermissionError("blind input protocol forbids reading study reports or results")

    sys.addaudithook(audit)


def gates(blind, output, seal_sha):
    blind, output = blind.resolve(), output.resolve()
    restrict_archive_reads(blind, output)
    seal = pinned(blind / "seal.json", seal_sha)
    require(seal["stage"] == "PRE_WHITELIST_ONLY", "wrong blind input stage")
    output.mkdir(exist_ok=True)
    require(not any(output.iterdir()), "gate directory already contains method outputs")
    cases = []
    for row in seal["cases"]:
        path = blind / row["id"]
        v = pinned(path / "pre.json", row["pre_sha256"])
        frame = RGBDObservation.model_validate(pinned(path / "frame.json", row["frame_sha256"]))
        require(
            row["id"] == v["case"]["id"]
            and row["frame_sha256"] == v["source_frame"]["file_sha256"],
            "swapped sealed event",
        )
        result = replay(v, frame)
        name = row["id"] + ".json"
        write(output / name, result)
        cases.append({"id": row["id"], "file": name, "output_sha256": sha(output / name)})
    write(output / "seal.json", {"input_sha256": seal_sha, "cases": cases})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("blind", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("seal_sha256")
    args = parser.parse_args()
    gates(args.blind, args.output, args.seal_sha256)
