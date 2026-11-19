"""Read the recorded hard-finger stop and resume the same isolated simulation owner."""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import asdict
from pathlib import Path
from xml.etree import ElementTree

from cloud_edge_robot_arm.harness.checkout import verify_checkout
from cloud_edge_robot_arm.harness.config import load_config
from cloud_edge_robot_arm.harness.evidence import EpisodeExpectation
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    PhysicalSample,
    evaluate_evidence,
)
from cloud_edge_robot_arm.vision.marker_families import marker_family

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "round-p1-resume-receipt-canonical-20261120"))
import resume_v2 as v2  # noqa: E402

original = v2.original
v1 = v2.v1
sha = v2.sha
require = v2.require
PLAN_SHA = "94eb2ca3aeb2cf2952f6335f77422c7836382f34d96979746a53151a829b4267"
FINGER_SLOT = "development-18"
FINGER_LIMIT = "HARD_FINGER_LIMIT"
STRICT_PREFIX_ERROR = "initialization prefix must contain only one unreturned action"
FINGER_SOURCE = "src/cloud_edge_robot_arm/research/sol_molmo_components.py"


def attest():
    path = HERE / "plan.json"
    require(sha(path) == PLAN_SHA, "finger-stop plan changed")
    plan = original.read(path)
    require(sha(path.with_suffix(".md")) == plan["plan_md_sha256"], "plan Markdown changed")
    for name, expected in plan["inputs_sha256"].items():
        require(sha(original.REPO / name) == expected, f"finger-stop plan input differs: {name}")
    v2.attest()


def exact_action_prefix(episode, commands):
    finished, partial = episode["actions"]
    require(
        (
            finished["step_id"],
            finished["skill"],
            finished["start_step"],
            finished["controller_return_step"],
            finished["end_step"],
        )
        == ("step-01", "MOVE_ABOVE", 120, 880, 904)
        and finished["controller_result"]["success"] is True
        and finished["visual_servo"]["terminal_reason"] == "SUCCEEDED"
        and (partial["step_id"], partial["skill"], partial["start_step"], partial["end_step"])
        == ("step-02", "APPROACH", 904, 1218)
        and "controller_return_step" not in partial
        and "controller_result" not in partial
        and len(partial["visual_servo"]["control_samples"]) == 40
        and partial["visual_servo"]["terminal_reason"] == "ComponentStopped:HARD_FINGER_LIMIT",
        "actual returned plus unreturned controller prefix differs",
    )
    require(
        [
            (r["step_id"], r["phase"], r["verdict"]["allowed"])
            for r in episode["safety_checks"]
            if r["phase"] != "SERVO"
        ]
        == [("step-01", "PRE", True), ("step-01", "POST", True), ("step-02", "PRE", True)],
        "actual PRE and POST structure differs",
    )
    tail = [
        (
            row["command_seq"],
            row["type"],
            row["physics_step"],
            row["accepted"],
            row["after_emergency_stop"],
        )
        for row in commands[-4:]
    ]
    require(
        tail
        == [
            (216, "joint_target", 1214, True, False),
            (217, "hold_current_joints", 1218, True, False),
            (218, "hold_current_joints", 1218, True, False),
            (219, "emergency_stop", 1218, True, False),
        ]
        and [r["command_seq"] for r in commands] == list(range(1, 220))
        and all(
            row["physics_step"] >= 120 and row["physics_step"] <= 1214
            for row in commands
            if row["type"] == "joint_target"
        ),
        "accepted joint targets or terminal hold/stop sequence differs",
    )
    return {
        "completed_action_steps": [finished["step_id"]],
        "unreturned_action_step": partial["step_id"],
        "terminal_command_sequence": tail,
    }


def finger_window(feedback, limits, tolerance):
    require(
        limits == ((0.0, 0.04), (0.0, 0.04)) and tolerance == 0.0001,
        "original frozen finger guard does not match",
    )
    require(
        bool(feedback)
        and [r["physics_step"] for r in feedback] == list(range(feedback[0]["physics_step"], 1219)),
        "feedback time boundary differs",
    )
    violations = []
    for row in feedback:
        positions = row["finger_positions_m"]
        require(
            len(positions) == 2
            and all(type(x) in {int, float} and math.isfinite(x) for x in positions),
            "original finger feedback invalid",
        )
        for i, (value, (low, high)) in enumerate(zip(positions, limits, strict=True)):
            if not low - tolerance <= value <= high + tolerance:
                violations.append((row["physics_step"], i, value))
    require(
        violations == [(1218, 1, 0.040258176386462306)]
        and feedback[-2]["finger_positions_m"][1] == 0.040081167963833625,
        "no exact first right-finger excess",
    )
    return {
        "finger": "right",
        "first_offending_step": 1218,
        "prior_right_m": feedback[-2]["finger_positions_m"][1],
        "actual_right_m": violations[0][2],
        "normal_upper_m": limits[1][1],
        "allowed_upper_with_original_tolerance_m": limits[1][1] + tolerance,
        "excess_over_guard_m": violations[0][2] - limits[1][1] - tolerance,
    }


def original_receipts(freeze, slot, paths, source, config):
    begin, end, launch = (original.read(paths[k]) for k in ("begin", "end", "stdout"))
    unresolved_path = paths["audit"].with_suffix(".unresolved.json")
    old_failure = original.read(unresolved_path)
    binding = original.bound_slot(slot, v1.FREEZE_SHA)
    require(
        all(begin[key] == end[key] == value for key, value in binding.items())
        and end["begin_sha256"] == sha(paths["begin"])
        and all(end[k + "_sha256"] == sha(paths[k]) for k in ("stdout", "stderr")),
        "finger-stop ownership receipt differs",
    )
    require(
        old_failure["error_type"] == "ValueError"
        and old_failure["message"] == STRICT_PREFIX_ERROR
        and old_failure["original_end_sha256"] == sha(paths["end"])
        and old_failure["status"] == "STARTED_UNRESOLVED"
        and launch["status"] == "FAILED"
        and launch["signal"] is None
        and launch["wrapper_stop_reason"] is None
        and end["returncode"] == launch["wrapper_exit_code"] == launch["episode_exit_code"] == 2,
        "finger-stop original failure/exit signature differs",
    )
    native = launch["native_python"]
    require(
        Path(launch["output"]) == paths["episode"]
        and launch["source"]["git_revision"] == freeze["commit"]
        and launch["source"]["files"] == source.files == freeze["checkout_selected_files"]
        and launch["planned_configuration"] == config.model_dump(mode="json")
        and launch["planned_configuration_sha256"] == config.fingerprint()
        and launch["model_asset_manifest_sha256"] == freeze["asset_manifest_sha256"]
        and native["status"] == "READY_TO_DELEGATE"
        and native["executable_sha256"] == freeze["native_python_sha256"]
        and native["registered_overlay"]["sha256"] == freeze["overlay_sha256"],
        "finger-stop wrapper asset, product or configuration differs",
    )
    return {
        **{k + "_sha256": sha(paths[k]) for k in ("begin", "end", "stdout", "stderr")},
        "original_unresolved_sha256": sha(unresolved_path),
        "process_exit": 2,
        "wrapper_exit": 2,
        "native_exit": 2,
        "original_wrapper_status": launch["status"],
    }, launch


def native_finger_fields(result, episode, job, worker_result, slot):
    error = episode["exception"]
    require(
        result["status"]
        == episode["status"]
        == job["status"]
        == result["worker_status"]
        == "FAILED"
        and result["job_id"] == job["job_id"]
        and result["episode_id"] == episode["episode_id"]
        and result["terminal_reason"] == episode["terminal_reason"] == FINGER_LIMIT
        and result["component_success"] is False
        and result["physical_success"] is episode["physical_success"] is False
        and episode["executed_actions"] == result["executed_actions"] == 2
        and result["physics_steps"] == episode["physics_steps"] == 1218
        and job["seed"] == slot["runtime_seed"]
        and job["attempt"] == 1
        and job["hardware_write_operations"] == []
        and job["real_controller_contacted"] is False
        and job["hardware_motion_observed"] is False
        and result["source_snapshot_status"] == "COMPLETE"
        and result["changed_source_paths"] == []
        and not episode.get("secondary_exceptions")
        and worker_result["exception"] == error
        and (error["type"], error["message"], error["phase"], error["step_id"], error["skill"])
        == ("ComponentStopped", FINGER_LIMIT, "CONTROLLER", "step-02", "APPROACH")
        and error["traceback"][-1]
        == {"file": FINGER_SOURCE, "function": "check_component_hard_state", "line": 202},
        "native finger-stop result, worker or controller exception differs",
    )


def audit_frames(case, reader, result, episode):
    frames = {}
    prefix = "component/servo-frames/"
    for name in sorted(case.files):
        if name.startswith(prefix) and name.endswith("/observation.json"):
            frame = reader.read_frame(
                case.root,
                case.files,
                name.removesuffix("/observation.json"),
                result["episode_id"],
            )
            reader._frame_calibration(frame)
            require(frame.observation_id not in frames, "duplicate servo observation")
            frames[frame.observation_id] = frame
    for action in episode["actions"]:
        servo = action["visual_servo"]
        for row in servo["visual_samples"]:
            frame = frames[row["observation_id"]]
            require(
                frame.checksum_sha256 == row["checksum_sha256"]
                and frame.calibration_version == row["calibration_version"]
                and frame.sim_time_s == row["sim_time_s"],
                "servo frame binding differs",
            )
        require(
            all(0 <= row["sample_and_ik_s"] <= 0.1 for row in servo["control_samples"]),
            "accepted sample exceeds original wall-clock guard",
        )
    servo_safety = [row for row in episode["safety_checks"] if row["phase"] == "SERVO"]
    require(
        len(frames) == 138
        and all(
            row["verdict"]["allowed"] is True and row["observation_id"] in frames
            for row in servo_safety
        ),
        "incomplete archived servo or safety frame coverage",
    )
    return len(frames), len(servo_safety)


def validate_physical(score, archived):
    require(
        score["success"] is False
        and archived["success"] is False
        and score["safety_violation"] is archived["safety_violation"] is True
        and list(score["safety_events"]) == archived["safety_events"] == ["HARD_JOINT_LIMIT"]
        and all(
            math.isclose(score[key], archived[key])
            for key in (
                "measured_lift_m",
                "hold_s",
                "placed_stable_s",
            )
        ),
        "real independent physical violation must remain in the record",
    )


def audit_finger_stop(freeze, slot, paths):
    require(
        slot["assignment_id"] == FINGER_SLOT, "finger-stop plan applies only to its recorded slot"
    )
    _, reader = original.legacy_readers()
    config = load_config(original.OWNER / "configs" / slot["config"])
    checkout = Path(freeze["source"])
    source = verify_checkout(checkout, config)
    claims, wrapped = original_receipts(freeze, slot, paths, source, config)
    summary, case = reader.read_index(
        paths["episode"], expected=EpisodeExpectation(source, config, True)
    )
    require(
        wrapped["episode"] == summary["episode"]
        and wrapped["evidence"]["manifest_sha256"] == summary["manifest_sha256"]
        and summary["file_count"] == 673,
        "finger-stop root manifest ownership differs",
    )
    result, episode, job, assignment, role, worker = (
        case.json(k)
        for k in (
            "result.json",
            "component/episode.json",
            "worker/job.json",
            "scene-assignment.json",
            "role-binding.json",
            "worker/result.json",
        )
    )
    require(
        case.json("worker/runtime_job.json") == job
        and job["source_tree_hash"] == role["bundle_hash"],
        "native role or worker duplicate differs",
    )
    native_finger_fields(result, episode, job, worker, slot)
    motions = exact_action_prefix(episode, case.json("component/commands.json"))
    asset = checkout / marker_family(config.marker_family).asset_path
    root = ElementTree.parse(asset)
    limits = tuple(
        tuple(map(float, root.find(f".//joint[@name='finger_{side}_joint']").get("range").split()))
        for side in ("left", "right")
    )
    require(
        freeze["product_sources"][FINGER_SOURCE] == sha(checkout / FINGER_SOURCE),
        "frozen producer finger guard changed",
    )
    window = finger_window(case.json("component/robot-feedback.json"), limits, 0.0001)
    frames, checks = audit_frames(case, reader, result, episode)
    prior = reader._legacy_verifier()
    physical = asdict(
        evaluate_evidence(
            [
                PhysicalSample(**{k: prior.PREVIOUS.tuples(v) for k, v in raw.items()})
                for raw in case.json("component/physical-evidence.json")
            ],
            CompletionCriteria("object", "target_region"),
        )
    )
    validate_physical(physical, episode["independent_physical_outcome"])
    applied = case.json("component/scene-application.json")
    require(applied == episode["scene_application"], "slot application state differs")
    pose = reader.check_pose(slot["scene"], config, assignment, applied)
    sources = reader.check_sources(
        role, case.json("source-hashes.json"), freeze["product_sources"], slot
    )
    counters = reader.check_model_evidence(case, result, freeze)
    ledger = [
        {key: row.get(key) for key in ("request_id", "monetary_cost", "currency", "status")}
        for row in case.json("costs.json")["requests"]
        if row["is_cloud_model"] is True
    ]
    return {
        **claims,
        **motions,
        "scope": "SUPPLEMENTAL_REAL_SIMULATED_FINGER_LIMIT",
        "finger_window": window,
        "terminal": original.terminal_attempt(case, job),
        "assignment_id": slot["assignment_id"],
        "run_instance_id": slot["run_instance_id"],
        "pose_seed": slot["pose_seed"],
        "freeze_sha256": v1.FREEZE_SHA,
        "component_success": False,
        "independent_physical_success": False,
        "physical": physical,
        "terminal_reason": FINGER_LIMIT,
        "strict_audit": "STARTED_UNRESOLVED",
        "manifest_sha256": summary["manifest_sha256"],
        "manifest_files": summary["file_count"],
        "source_files_checked": sources,
        "servo_frame_count": frames,
        "servo_safety_checks": checks,
        "job_id": job["job_id"],
        "episode_id": result["episode_id"],
        "observed_counters": counters,
        "ledger": ledger,
        "applied_pose": pose,
        "executed_actions": 2,
        "post_stop_physics_sample_available": False,
        "contact_cause": "UNKNOWN",
        "supplemental_tool_sha256": sha(Path(__file__)),
    }


def assessment(freeze, slot, *, save=False):
    if slot["assignment_id"] != FINGER_SLOT:
        return v2.fresh_assessment(freeze, slot, save_supplement=save)
    paths = original.slot_paths(original.OWNER, slot)
    require(original.claim_presence(paths) == "ENDED_UNVERIFIED", "original 18 claim differs")
    evidence = audit_finger_stop(freeze, slot, paths)
    root = original.OWNER / "verification"
    path = root / "development-18.finger-limit-supplement.json"
    if save and not path.exists():
        original.persist(path, evidence)
    digest = (
        v2.compare_checkpoint(path, evidence)
        if path.exists()
        else v1.digest(v2.canonical(evidence))
    )
    return "FINGER_SUPPLEMENTAL", evidence, digest


def initial_prefix(freeze, *, save=False):
    prefix = v2.verified_prefix(freeze, save_supplement=save)
    slots = original.registered_slots(freeze["allocation"])
    for index, slot in enumerate(slots[11:18], 11):
        route, _, checksum = assessment(freeze, slot, save=save)
        require(
            route == ("STRICT" if index < 17 else "FINGER_SUPPLEMENTAL"),
            "17 predecessors and the named 18 must have their original terminals",
        )
        prefix["checkpoints"][slot["assignment_id"]] = {"route": route, "sha256": checksum}
    prefix["checked_prefix_count"] = 18
    return prefix


def resume(freeze, descriptor):
    prefix = initial_prefix(freeze, save=True)
    runner, _ = original.legacy_readers()
    runner._verify_gpu_release(Path(freeze["resources"]["--gpu-lock"]))
    print(
        "CHECKPOINTS_VERIFIED",
        prefix["checked_prefix_count"],
        prefix["checkpoints"][FINGER_SLOT]["sha256"],
        flush=True,
    )
    for slot in original.registered_slots(freeze["allocation"])[18:]:
        route, _, _ = assessment(freeze, slot, save=True)
        if route != "NOT_EXECUTED":
            continue
        try:
            original.launch_slot(freeze, slot, v1.FREEZE_SHA, descriptor)
        except ValueError as exc:
            if str(exc) != v1.LIMIT_ERROR:
                raise
            route, _, checksum = assessment(freeze, slot, save=True)
            require(route == "SUPPLEMENTAL", "future oversized result did not independently match")
            print("SUPPLEMENTAL", slot["assignment_id"], checksum, flush=True)


def final_report(freeze):
    alloc = freeze["allocation"]
    slots = original.registered_slots(alloc)
    route_map, rows, original_rows, receipt_sha = {}, {}, [], {}
    for slot in slots:
        identity = slot["assignment_id"]
        route, row, checksum = assessment(freeze, slot)
        route_map[identity] = route
        receipt_sha[identity] = checksum
        if row is None:
            continue
        rows[identity] = row
        if route == "STRICT":
            original_rows.append(original.completed_row(slot, row, checksum))
        else:
            original_rows.append(
                {
                    **{key: slot[key] for key in ("assignment_id", "run_instance_id", "pose_seed")},
                    "status": "STARTED_UNRESOLVED",
                    "component_completed": None,
                    "independent_physical_success": None,
                    "audit_sha256": None,
                }
            )
    require(
        len({r["job_id"] for r in rows.values()})
        == len(rows)
        == len({r["episode_id"] for r in rows.values()}),
        "simulator run identity was reused",
    )
    cloud_ids = [r["request_id"] for row in rows.values() for r in row["ledger"]]
    require(
        all(cloud_ids) and len(set(cloud_ids)) == len(cloud_ids), "cloud dispatch identity reused"
    )
    fresh_ids = [slot["assignment_id"] for slot in alloc["development"]]
    fresh = [rows[k] for k in fresh_ids if k in rows]

    def metric(key):
        n = sum(r[key] is True for r in fresh)
        return {
            "successes": n,
            "audited": len(fresh),
            "wilson95": v1.wilson95(n, 20) if len(fresh) == 20 else None,
        }

    return {
        "freeze_sha256": v1.FREEZE_SHA,
        "original_strict": v1.score_outcomes(alloc, original_rows, closed=False),
        "native_component_completion": metric("component_success"),
        "independent_physical_success": metric("independent_physical_success"),
        "original_wrapper_complete": {
            "successes": sum(
                route_map[key] == "STRICT"
                and rows[key]["component_success"]
                and rows[key]["wrapper_exit_code"] == 0
                for key in fresh_ids
            ),
            "assigned": 20,
        },
        "observed_safety_violations": sum(row["physical"]["safety_violation"] for row in fresh),
        "routes": route_map,
        "audit_sha256": receipt_sha,
        "individual_outcomes": rows,
        "repeat_ids": [slot["assignment_id"] for slot in alloc["repeats_1802"]],
        "counts": {
            k: sum(row["observed_counters"][k] for row in rows.values())
            for k in ("cloud_requests", "local_generations", "model_loads")
        },
        "billing": original.bill_totals(rows),
        "dispatch_retries": 0,
    }


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("verify-18", "verify-prefix", "resume", "audit"))
    cli.add_argument("--output", type=Path)
    args = cli.parse_args()
    attest()
    with original.exclusive_owner() as descriptor:
        freeze = original.freeze_at(v1.FREEZE_SHA)
        if args.action == "resume":
            resume(freeze, descriptor)
            return
        require(args.output is not None, "must specify fresh result output")
        if args.action == "verify-18":
            slot = original.registered_slots(freeze["allocation"])[17]
            _, result, _ = assessment(freeze, slot)
        elif args.action == "verify-prefix":
            result = initial_prefix(freeze)
        else:
            result = final_report(freeze)
        original.persist(args.output, result)
        print(sha(args.output), flush=True)


if __name__ == "__main__":
    main()
