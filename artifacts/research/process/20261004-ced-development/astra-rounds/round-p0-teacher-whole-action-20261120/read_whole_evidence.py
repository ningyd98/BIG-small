"""Read physical originals of the registered first-action EGL development run."""

from __future__ import annotations

import argparse
import base64
import json
import sqlite3
from collections import Counter
from datetime import datetime
from importlib import util
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from cloud_edge_robot_arm.contracts.models import RobotState
from cloud_edge_robot_arm.edge.evidence.conditions import (
    ConditionSpec,
    OnlineEvidenceSnapshot,
    evaluate_conditions,
    evaluate_registered_conditions_v2,
)
from cloud_edge_robot_arm.edge.safety.models import SafetyContext
from cloud_edge_robot_arm.research.native_calibration_collection import detached
from cloud_edge_robot_arm.research.native_collection_grounding import (
    registered_expected_conditions_v2,
)
from cloud_edge_robot_arm.research.native_full_horizon_originals import (
    _Audit,
    _legacy_shield_hashes,
    _shield_recipe,
)
from cloud_edge_robot_arm.research.raw_episode_v3 import _owner_decode
from cloud_edge_robot_arm.vision.execution import research_safety_shield
from cloud_edge_robot_arm.vision.owner_registration import (
    RegisteredGroundingFrameInputsV2,
    VisualOriginalPlan,
)

SCHEMA = "native.whole-action-egl.development.v1"
SCOPE = "WHOLE_ACTION_DEVELOPMENT"
ASSIGNMENT = "native-dev-whole-action-20261120-0001"
SEED = 11920067
WALL_NS = 8_000_000_000
TOTAL = 1920
PARENT_FREEZE_SHA256 = "41d28dde96b867c314767185e0d4f620fbbc1421313f7dfb05ff308fce47165b"
RECIPE_CONFIG = "configs/research/native_registered_single_teacher_p0_20261119.yaml"
HERE = Path(__file__).resolve().parent


def _prior_reader():
    path = (
        HERE.parent / "round-p0-teacher-checkpoint-egl-development-20261120/read_checkpoint_egl.py"
    )
    spec = util.spec_from_file_location("checkpoint_independent_readonly", path)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = _prior_reader()
require = base.require
read_json = base.read_json
original = base.original
sha_file = base.digest_file
digest = base.canonical_digest


def registration(protocol: Any, claim: Any, root: Path) -> str:
    fixed = {
        "schema_version": SCHEMA,
        "scope": SCOPE,
        "assignment_id": ASSIGNMENT,
        "seed": SEED,
        "qualification_credit": 0,
        "step_wall_budget_ns": WALL_NS,
        "png_compress_level": 1,
        "first_action": "MOVE_ABOVE",
        "step_wall_budget_kind": "ORIGINAL_POST_STEP_TIMEOUT",
        "parent_source_freeze_sha256": PARENT_FREEZE_SHA256,
    }
    require(
        all(
            type(protocol.get(key)) is type(value) and protocol[key] == value
            for key, value in fixed.items()
        ),
        "foreign or changed whole-action registration",
    )
    require(
        protocol["registration_directory"] == str(root) and protocol["output"] == str(root / "run"),
        "registered directory differs",
    )
    result = digest(protocol)
    require(
        claim.get("scope") == SCOPE
        and claim.get("assignment_id") == ASSIGNMENT
        and claim.get("seed") == SEED
        and claim.get("registration_sha256") == result
        and claim.get("output") == str(root / "run"),
        "claim does not bind this whole-action release",
    )
    recipe = protocol["recipe"]
    move = recipe["actions"][0]
    require(
        recipe["scope"] == SCOPE
        and recipe["released_assignments"] == []
        and len(recipe["assignments"]) == 1
        and recipe["assignments"][0]["assignment_id"] == ASSIGNMENT
        and recipe["assignments"][0]["seed"] == SEED
        and recipe["settings"]["png_compress_level"] == 1
        and move["skill"] == "MOVE_ABOVE"
        and move["original_timeout_ms"] == 8000
        and move["horizon"]["total_steps"] == TOTAL
        and recipe["role"]["model_requests"] == 0,
        "internal recipe or single-action boundary differs",
    )
    return result


def verify_outer_source(
    release: Path, source_root: Path, recipe: dict, registration_sha: str
) -> dict:
    top = release.parent
    run = release / "run"
    freeze = read_json(top, "source-freeze.json")
    end = read_json(top, "process-end.json")
    freeze_sha = sha_file(original(top, "source-freeze.json"))
    require(
        freeze["scope"] == SCOPE
        and freeze["source_path"] == str(source_root)
        and freeze["diagnostic_seed"] == SEED
        and freeze["source_generation"] == recipe["source_generation"]
        and freeze["parent_source_freeze_sha256"] == PARENT_FREEZE_SHA256
        and end["freeze_sha256"] == freeze_sha
        and end["source_match"] is True
        and end["registration_file_sha256"] == sha_file(original(release, "protocol.json"))
        and end["imported_source_manifest_sha256"]
        == sha_file(original(run, "imported-source-manifest.json")),
        "process originals do not join frozen source and release",
    )
    frozen = freeze["source_files_sha256"]
    protected = freeze["protected_inputs_sha256"]
    require(
        type(frozen) is dict
        and set(recipe["source_hashes"]) <= set(frozen)
        and all(frozen[name] == sha for name, sha in recipe["source_hashes"].items())
        and len(frozen) == end["before_and_after_source_files"]
        and type(protected) is dict
        and len(protected) == end["protected_previous_inputs"],
        "source/protected file receipts disagree with frozen manifest",
    )
    for directory, expected in (
        (source_root, frozen),
        (Path(freeze["operational_worktree"]), protected),
    ):
        for name, value in expected.items():
            require(
                sha_file(original(directory, name)) == value,
                f"frozen or protected source SHA256 differs: {name}",
            )
    attempts = end["network_attempts"]
    require(type(attempts) is list and not attempts, "unexpected recorded network use")
    return {
        "source_freeze_file_sha256": freeze_sha,
        "registration_sha256": registration_sha,
        "verified_frozen_files": len(frozen),
        "verified_protected_inputs": len(protected),
        "network_attempts_observed": len(attempts),
    }


def exact_reference(root: Path, files: dict, ref: dict, expected: str | None = None) -> str:
    path = ref["path"]
    require(
        path in files
        and (expected is None or expected == path)
        and files[path]["sha256"] == ref["sha256"],
        "source reference does not join original inventory",
    )
    original(root, path)
    return path


def check_png(data: bytes, level: int) -> dict[str, Any]:
    with Image.open(BytesIO(data)) as image:
        require(image.format == "PNG" and image.mode == "RGB", "original is not lossless RGB PNG")
        fresh = BytesIO()
        image.save(fresh, format="PNG", compress_level=level)
        require(data == fresh.getvalue(), "original PNG differs from registered encoder bytes")
        return {"width": image.width, "height": image.height}


def audit_frames(audit: Any, raw: dict, files: dict) -> tuple[dict, dict]:
    states = base._strict_steps(raw["physics"], raw["total_physics_steps"])
    states[0] = raw["reset"]["physics_state"]
    audit.raw = raw
    audit.states = states
    audit.intervals = {row["interval_id"]: row for row in raw["intervals"]}
    require(len(audit.intervals) == len(raw["intervals"]), "duplicate original interval")
    names, sources = raw["allocated_frames"], raw["frame_sources"]
    require(
        len(names) == len(set(names)) and set(sources) <= set(names),
        "invalid acquisition allocation",
    )
    events = {
        e["acquisition_id"]: e for e in raw["operational_events"] if e["acquisition_id"] is not None
    }
    require(
        len(events)
        == len([e for e in raw["operational_events"] if e["acquisition_id"] is not None]),
        "more than one source event for a frame",
    )
    summaries, boundary, marked, role_counts = {}, {}, set(), Counter()
    scheduled, passes, missing = [], 0, []
    for aid in names:
        if aid not in sources:
            missing.append(aid)
            continue
        frame_path = f"frames/{aid}/source-frame.json"
        require(
            sources[aid] == frame_path and frame_path in files,
            "frame is outside original inventory",
        )
        saved = read_json(audit.directory, frame_path)
        if saved["frame"]["observation_payload"] is None:
            require(
                bool(events[aid]["error_type"]), "missing payload has no failed capture original"
            )
            missing.append(aid)
            continue
        observation, meta, state = audit.frame(aid)
        key = observation.observation_id
        require(key not in marked, "frame reused an original observation identity")
        marked.add(key)
        capture = meta["capture_source"]
        event = events[aid]
        require(
            event["operation_id"] == capture["operation_id"]
            and event["begin_step"] == event["end_step"] == state["physics_step"]
            and event["episode_id"] == observation.episode_id
            and not event["error_type"],
            "capture event does not join its recorded physical state",
        )
        for name in meta["frame"]["file_hashes"]:
            require(name in files, "capture blob absent from inventory")
        path = meta["encoded_fields"]["rgb_png_base64"]
        image_bytes = original(audit.directory, path).read_bytes()
        require(
            base64.b64decode(observation.rgb_png_base64, validate=True) == image_bytes,
            "consumer changed original RGB bytes",
        )
        dims = check_png(image_bytes, level=1)
        require(
            dims == {"width": observation.width, "height": observation.height},
            "decoded frame dimensions differ",
        )
        role = capture["role"]
        if role == "REGISTERED_PER_PHYSICS_STEP":
            require(
                capture["sample_slot"] == state["physics_step"],
                "physical frame sample slot differs",
            )
            scheduled.append(state["physics_step"])
        if role == "REGISTERED_ACTION_BOUNDARY":
            boundary[aid] = (observation, meta, state)
        summaries[aid] = state["physics_step"]
        role_counts[role] += 1
        passes += meta["pass_count"]
    require(scheduled == sorted(set(scheduled)), "per-step frame ordering is not exact")
    remaining = sorted(set(range(1, raw["total_physics_steps"] + 1)) - set(scheduled))
    return {
        "allocated": len(names),
        "reconstructed": len(summaries),
        "missing": missing,
        "scheduled_per_step": len(scheduled),
        "missing_physical_steps": remaining,
        "render_passes_from_sources": passes,
        "verified_png_level_1": len(summaries),
        "role_counts": dict(role_counts),
    }, boundary


def capture_join(
    item: dict, worker: dict, source: dict, observation: Any, frame_state: dict
) -> dict:
    receipt = item["capture"]
    signals = receipt["live_owner"]
    lease = signals["lease"]
    require(
        all(
            lease[key] == worker[key]
            for key in ("job_id", "run_id", "lease_id", "worker_id", "attempt")
        ),
        "boundary frame has a foreign lease",
    )
    require(
        receipt["step"] == frame_state["physics_step"]
        and receipt["capture"]["domain"]
        == receipt["consumed"]["domain"]
        == source["origin"]["domain"],
        "boundary frame does not bind owner clock and step",
    )
    require(
        0 <= receipt["consumed"]["upper_ns"] - receipt["capture"]["lower_ns"] < 5_000_000_000
        and receipt["consumed"]["upper_ns"] < source["deadline"]["deadline_ns"],
        "boundary frame outside original freshness or owner deadline",
    )
    evaluated = datetime.fromisoformat(item["evaluation_at"])
    observed_at, expires_at = (
        datetime.fromisoformat(lease[key]) for key in ("observed_at", "expires_at")
    )
    require(
        observed_at <= evaluated < expires_at
        and 0 <= (evaluated - observation.captured_at).total_seconds() < 5,
        "boundary evaluation expired the original frame or lease",
    )
    return {
        "evaluation_age_s": (evaluated - observation.captured_at).total_seconds(),
        "lease_fresh_at_evaluation": True,
    }


def decision_phase(
    audit: Any,
    files: dict,
    raw_row: dict,
    frames: dict,
    recipe: dict,
    worker: dict,
    source: dict,
) -> tuple[dict, Any]:
    item, decision = raw_row["inputs"], raw_row["decision"]
    phase = item["phase"]
    require(
        phase in ("PRE", "POST")
        and item["skill"] == "MOVE_ABOVE"
        and decision["step_id"] == "step-1"
        and decision["phase"] == phase
        and decision["original_inputs_sha256"] == digest(item),
        "admission is not the original first-action phase",
    )
    aid = item["capture"]["acquisition_id"]
    observation, meta, frame_state = frames[aid]
    fresh = capture_join(item, worker, source, observation, frame_state)
    witnesses = [row for row in audit.raw["operational_events"] if row["acquisition_id"] == aid]
    require(
        len(witnesses) == 1 and witnesses[0]["bracket"] == item["capture"]["capture"],
        "boundary admission did not use the original capture operation clock",
    )
    shield = research_safety_shield(recipe["settings"]["task_timeout_s"])
    refs = item["shield_source"]
    stem = f"shield/step-1-{phase.lower()}"
    root = audit.directory
    shield_config = read_json(root, "shield/config.json")
    require(
        {k: v for k, v in shield_config.items() if k != "policy_hash"}
        == _shield_recipe(shield, recipe["source_generation"])
        and shield_config["policy_hash"] in _legacy_shield_hashes(shield_config),
        "original Shield policy configuration differs",
    )
    saved_input = read_json(root, exact_reference(root, files, refs["input"], stem + "-input.json"))
    output = read_json(root, exact_reference(root, files, refs["result"], stem + "-result.json"))
    require(
        output["input_sha256"] == refs["input"]["sha256"]
        and output["error_type"] is None
        and output["error"] is None
        and saved_input["method"] == phase.lower() + "_check"
        and saved_input["index"] == 0
        and saved_input["step_id"] == "step-1"
        and saved_input["source_generation"] == recipe["source_generation"],
        "Shield original input and output do not join",
    )
    exact_reference(root, files, saved_input["config"], "shield/config.json")
    grounding_path = exact_reference(root, files, saved_input["grounding"], "grounding/step-1.json")
    exact_reference(root, files, saved_input["acquisition"], f"frames/{aid}/source-frame.json")
    require(
        saved_input["acquisition"]["acquisition_id"] == aid
        and saved_input["grounding"] == refs["grounding"],
        "Shield used another acquisition or grounding",
    )
    grounding = read_json(root, grounding_path)
    require("original-plan.json" in files, "Shield has no original owned plan")
    original_plan = _owner_decode(VisualOriginalPlan, read_json(root, "original-plan.json"))
    binding = audit.grounding_binding(item["grounding"])
    specs = registered_expected_conditions_v2(original_plan, binding, phase)
    require(
        original_plan.digest() == item["original_plan_sha256"]
        and detached(specs) == item["conditions"]
        and grounding["original_plan_sha256"] == item["original_plan_sha256"]
        and grounding["acquisition"]["acquisition_id"]
        == (
            aid
            if phase == "PRE"
            else audit.raw["decisions"][0]["inputs"]["capture"]["acquisition_id"]
        ),
        "admission conditions do not bind the original plan and grounding",
    )
    context = SafetyContext.model_validate(saved_input["context"])
    step = context.contract.steps[0]
    require(
        step.step_id == "step-1"
        and step.skill.value == "MOVE_ABOVE"
        and step.timeout_ms == 8000
        and context.parameters == item["step"]["parameters"],
        "Shield step or original limit changed",
    )
    require(
        [context.tcp_x, context.tcp_y, context.tcp_z] == frame_state["tcp_position_m"],
        "Shield proprioceptive position differs from original physical state",
    )
    replay = getattr(shield, saved_input["method"])(context)
    require(
        detached(replay) == output["result"] == item["shield"],
        "physical Shield decision replay differs",
    )
    state = RobotState.model_validate(item["robot_state"])
    require(
        [state.tcp_pose.x, state.tcp_pose.y, state.tcp_pose.z] == frame_state["tcp_position_m"]
        and state.estop_engaged == frame_state["estop_engaged"],
        "admission feedback differs from physical source",
    )
    tracked = item["registered_inputs"]
    inputs = RegisteredGroundingFrameInputsV2.from_payload(tracked) if tracked is not None else None
    if inputs is not None:
        require(
            inputs.matches_observation(observation),
            "registered conditions switched their frame bytes",
        )
    facts = item["facts"]
    snapshot = OnlineEvidenceSnapshot(observation, state, facts, 1, 1, item["original_plan_sha256"])
    now = datetime.fromisoformat(item["evaluation_at"])
    verdicts = evaluate_registered_conditions_v2(
        specs,
        snapshot,
        grounding_inputs=inputs,
        now=now,
    )
    supplemental = evaluate_conditions(
        [
            ConditionSpec("gripper_holding", "object"),
            ConditionSpec("gripper_released", "object"),
            ConditionSpec("robot_in_safe_pose", "object", {"minimum_safe_height": 0.0}),
        ],
        snapshot,
        now=now,
    )
    require(
        detached(verdicts) == item["verdicts"] and detached(supplemental) == item["supplemental"],
        "original condition outcomes do not replay on their own current frame",
    )
    require(not decision["allowed"] or replay.allowed, "admission bypassed the original Shield")
    require(
        decision["native_qualification"] == "UNKNOWN" and not decision["execution_admitted"],
        "development admission reports formal authorization",
    )
    return {
        "phase": phase,
        "acquisition_id": aid,
        "frame_sha256": files[saved_input["acquisition"]["path"]]["sha256"],
        "physical_step": meta["capture_source"]["physics_step"],
        "shield_allowed": replay.allowed,
        "admission_allowed": decision["allowed"],
        "admission_reasons": decision["reasons"],
        "condition_verdicts": {v.condition_name: v.status.value for v in verdicts},
        "supplemental_verdicts": {v.condition_name: v.status.value for v in supplemental},
        "original_rules": [
            {"id": v.rule_id, "decision": v.decision.value, "reason": v.reason_code}
            for v in replay.evaluated_rules
        ],
        "limiting_rule": detached(replay.limiting_rule),
        **fresh,
    }, context


def result_window(pre: Any, post: Any, decoded_post: dict) -> dict:
    require(
        pre.step_started_at == post.step_started_at
        and pre.step_started_at is not None
        and post.monotonic_now is not None
        and pre.monotonic_now is not None
        and pre.step_started_at <= pre.monotonic_now <= post.monotonic_now,
        "POST used a different or invalid PRE monotonic anchor",
    )
    elapsed_ms = (post.monotonic_now - pre.step_started_at) * 1000
    rule = [row for row in decoded_post["original_rules"] if row["id"] == "STEP_TIMEOUT"]
    # Shield returns early on stricter independent violations. Such a terminal
    # can establish elapsed time, with StepTimeoutRule explicitly unevaluated.
    require(len(rule) <= 1, "invalid STEP_TIMEOUT rule multiplicity")
    if rule:
        require(
            (rule[0]["decision"] == "REJECT") == (elapsed_ms > 8000),
            "original strict STEP_TIMEOUT gate was changed",
        )
    limiter = decoded_post["limiting_rule"]
    if limiter and limiter["rule_id"] == "STEP_TIMEOUT":
        require(
            limiter["measured_value"] == elapsed_ms and limiter["limit_value"] == 8000,
            "stored STEP_TIMEOUT measurement differs from the original window",
        )
    return {
        "elapsed_ms": elapsed_ms,
        "limit_ms": 8000,
        "elapsed_to_limit_ratio": elapsed_ms / 8000,
        "step_timeout_rule_reached": bool(rule),
        "step_timeout": bool(rule and rule[0]["decision"] == "REJECT"),
    }


def full_horizon(audit: Any, raw: dict, recipe: dict, phases: dict) -> dict:
    require(
        len(raw["horizons"]) == len(raw["actions"]) == len(raw["allocated_actions"]) == 1,
        "whole-action record has another or missing action",
    )
    h, action = raw["horizons"][0], raw["actions"][0]
    require(
        h["skill"] == "MOVE_ABOVE"
        and h["step_id"] == action["step_id"] == "step-1"
        and h["complete"] is True
        and h["failure_type"] is None
        and not h["reasons"]
        and json.loads(h["horizon_json"]) == recipe["actions"][0]["horizon"]
        and h["executed_step_sha256"] == digest(action["executed_step_payload"]),
        "original whole action did not complete the registered horizon",
    )
    controller = json.loads(h["controller_result_json"])
    require(
        action["disposition"] == "RETURNED"
        and controller["success"] is True
        and controller["action_result"] == action["returned_result"],
        "actual controller did not return success",
    )
    start, returned, end = (
        h[name] for name in ("dispatch_step", "controller_return_step", "terminal_step")
    )
    attempt = audit.intervals[action["interval_id"]]
    hold = audit.intervals[h["padding_interval_id"]]
    require(
        start == attempt["start_step"] == phases["PRE"]["physical_step"]
        and returned == attempt["end_step"] == hold["start_step"]
        and start <= returned <= end
        and end == hold["end_step"] == phases["POST"]["physical_step"] == raw["total_physics_steps"]
        and end - start == TOTAL
        and hold["kind"] == "HOLD"
        and h["terminal_acquisition_id"] == phases["POST"]["acquisition_id"],
        "control, HOLD and terminal physical steps do not join",
    )
    require(
        sum(
            row["interval_id"] == hold["interval_id"]
            and row["action_span_id"] == action["span_id"]
            and row["semantic_kind"] == "FULL_HORIZON_HOLD"
            for row in raw["hold_mappings"]
        )
        == 1,
        "original HOLD association missing",
    )
    before = [
        row
        for row in raw["joins"]
        if row["span_id"] == action["span_id"] and row["relation"] == "BEFORE_SUBMIT"
    ]
    require(
        len(before) == 1
        and before[0]["acquisition_id"] == phases["PRE"]["acquisition_id"]
        and len(raw["joins"]) == 2
        and any(
            row["span_id"] == action["span_id"]
            and row["relation"] == "AFTER_RETURN"
            and row["acquisition_id"] == phases["POST"]["acquisition_id"]
            for row in raw["joins"]
        ),
        "controller before-submit or terminal association differs",
    )
    return {
        "dispatch_step": start,
        "controller_return_step": returned,
        "terminal_step": end,
        "controller_steps": returned - start,
        "hold_steps": end - returned,
        "observed_steps": end - start,
        "original_required_steps": TOTAL,
        "terminal_acquisition_id": h["terminal_acquisition_id"],
        "controller_returned_success": True,
    }


def read_run(root: Path, source_root: Path) -> dict:
    root, source_root = root.absolute(), source_root.absolute()
    run = root / "run"
    directory = run / "originals"
    protocol = read_json(root, "protocol.json")
    claim = read_json(root, "diagnostic-claim.json")
    registration_sha = registration(protocol, claim, root)
    recipe = protocol["recipe"]
    startup = read_json(run, "startup.json")
    lifecycle = read_json(run, "collection-result.json")
    require(
        lifecycle["scope"] == SCOPE
        and lifecycle["qualification_credit"] == 0
        and lifecycle["native_qualification"] == "UNKNOWN"
        and lifecycle["qualified_group_score"] is None
        and lifecycle["joint_bound_m"] is None
        and lifecycle["execution_admitted"] is False
        and lifecycle["teacher_collection_admitted"] is False,
        "development lifecycle overstates formal authority",
    )
    require(
        startup["application_id"] == claim["application_id"]
        and startup["registration_sha256"] == registration_sha
        and startup["assignment"]["assignment_id"] == lifecycle["assignment_id"] == ASSIGNMENT
        and startup["assignment"]["seed"] == SEED
        and startup["role"]["model_requests"] == 0
        and startup["role"]["provider"] is None,
        "job startup is foreign or requested a model",
    )
    worker = base.verified_worker(run, lifecycle)
    require(
        startup["job_basis"]["job_id"] == worker["job_id"]
        and startup["job_basis"]["run_id"] == worker["run_id"]
        and startup["job_basis"]["max_attempts"] == 1,
        "claim startup job is not the single persisted worker job",
    )
    require(lifecycle["owner_closure"]["completed"] is True, "lifecycle owner did not close")
    environment = protocol["expected_environment"]
    interpreter = Path(environment["interpreter"])
    require(
        environment["source_root"] == str(source_root)
        and environment["mujoco_gl"] == "egl"
        and sha_file(original(source_root, RECIPE_CONFIG)) == environment["recipe_config_sha256"]
        and sha_file(original(interpreter.parent, interpreter.name))
        == environment["interpreter_sha256"],
        "whole-action environment changed",
    )
    imports = base.verify_imports(run, source_root, registration_sha)
    outer_source = verify_outer_source(root, source_root, recipe, registration_sha)
    result = {
        "status": "WHOLE_ACTION_ORIGINALS_READ",
        "scope": SCOPE,
        "assignment_id": ASSIGNMENT,
        "seed": SEED,
        "qualification_credit": 0,
        "native_qualification": "UNKNOWN",
        "formal_eligibility": False,
        "worker": worker,
        "actual_imports": imports,
        "source_closure": outer_source,
        "registration_sha256": registration_sha,
        "protocol_file_sha256": sha_file(original(root, "protocol.json")),
        "claim_file_sha256": sha_file(original(root, "diagnostic-claim.json")),
        "lifecycle_file_sha256": sha_file(original(run, "collection-result.json")),
        "measurement_complete": False,
        "action_pass": None,
        "window": None,
        "horizon": None,
        "first_original_failure": next(iter(lifecycle["failures"]), None),
    }
    if not (directory / "inventory.json").exists():
        require(
            not lifecycle["whole_action_diagnostic"]["measurement_complete"]
            and lifecycle["failures"],
            "missing original inventory in declared complete measurement",
        )
        return {
            **result,
            "unavailable": ["inventory", "physical originals", "PRE", "controller", "HOLD", "POST"],
        }
    inventory = read_json(directory, "inventory.json")
    files = base.verify_inventory(directory, inventory)
    require(
        {str(path.relative_to(directory)) for path in directory.rglob("*") if path.is_file()}
        == {*files, "inventory.json"},
        "original inventory omits on-disk files",
    )
    raw = read_json(directory, "partial-originals.json")
    require(
        raw["source_scope"] == SCOPE and len(raw["actions"]) <= 1 and len(raw["horizons"]) <= 1,
        "original source scope or action limit changed",
    )
    require(
        lifecycle["lifecycle_links"]["originals/inventory.json"]
        == sha_file(original(directory, "inventory.json"))
        and lifecycle["lifecycle_links"]["collection-body-result.json"]
        == sha_file(original(run, "collection-body-result.json"))
        and lifecycle["physics_steps"] == raw["total_physics_steps"],
        "lifecycle inventory, body or step count differs from original",
    )
    result.update(
        inventory_file_sha256=sha_file(original(directory, "inventory.json")),
        files_verified=len(files),
        bytes_verified=inventory["original_bytes"],
        total_physics_steps=raw["total_physics_steps"],
        frozen_source=base.verify_source(source_root, recipe, raw),
    )
    if "source-binding.json" not in files:
        require(
            not lifecycle["whole_action_diagnostic"]["measurement_complete"],
            "declared completion has no recorder source",
        )
        return {
            **result,
            "unavailable": ["recorder source binding", "certified boundary frames", "POST"],
        }
    source = read_json(directory, "source-binding.json")
    identity = raw["identity"]["owner_identity"]
    require(
        source["scope"] == SCOPE
        and source["assignment_id"] == ASSIGNMENT
        and source["protocol_sha256"] == startup["protocol_sha256"]
        and source["source_generation"]
        == lifecycle["source_generation"]
        == recipe["source_generation"]
        and raw["reset_count"] == 1
        and raw["reset_metadata"]["config"]["seed"] == SEED
        and raw["reset_metadata"]["config"]["domain_randomization"] is False
        and all(
            worker[key] == identity[key]
            for key in ("job_id", "run_id", "lease_id", "worker_id", "attempt")
        ),
        "recorder owner is foreign to persisted SQLite worker",
    )
    audit = _Audit(recipe, {"assignment_id": ASSIGNMENT, "seed": SEED}, run)
    frames, boundary_frames = audit_frames(audit, raw, files)
    result["frames"] = frames
    if raw["guard_events"]:
        result["stop"] = base.verify_stop(raw, raw["total_physics_steps"])
    if "active-checks.json" in files:
        result["active_checks"] = base.verify_active(
            read_json(directory, "active-checks.json"), raw, worker, source
        )
    rows = raw["decisions"]
    names = [row["inputs"]["phase"] for row in rows]
    require(names in ([], ["PRE"], ["PRE", "POST"]), "original grew beyond one PRE/POST pair")
    decisions, contexts = {}, {}
    for row in rows:
        phase = row["inputs"]["phase"]
        decisions[phase], contexts[phase] = decision_phase(
            audit, files, row, boundary_frames, recipe, worker, source
        )
    result["decisions"] = decisions
    if "POST" not in decisions:
        require(
            not lifecycle["whole_action_diagnostic"]["measurement_complete"],
            "declared complete measurement lacks POST",
        )
        return {**result, "unavailable": ["complete controller/HOLD/terminal/POST chain"]}
    require(
        decisions["PRE"]["shield_allowed"] and decisions["PRE"]["admission_allowed"],
        "POST followed denied PRE",
    )
    require(
        not frames["missing"]
        and not frames["missing_physical_steps"]
        and frames["render_passes_from_sources"]
        == lifecycle["render_passes"]
        == audit.render_accounting()
        and "active_checks" in result
        and not raw["pending_operation_ids"]
        and not raw["observer_failures"]
        and not raw["audit_failures"],
        "full measurement has an incomplete acquisition or observer ledger",
    )
    require(
        all(
            lifecycle["progress"].get(k) is True
            for k in (
                "backend_shutdown_completed",
                "recorder_close_completed",
                "capture_close_completed",
            )
        ),
        "full measurement omitted native cleanup",
    )
    return {
        **result,
        "measurement_complete": True,
        "action_pass": decisions["POST"]["admission_allowed"],
        "window": result_window(contexts["PRE"], contexts["POST"], decisions["POST"]),
        "horizon": full_horizon(audit, raw, recipe, decisions),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registration", type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = read_run(args.registration, args.source_root)
    except (
        AttributeError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
        IndexError,
        sqlite3.Error,
    ) as error:
        print(
            json.dumps(
                {
                    "status": "ORIGINALS_REJECTED",
                    "error": str(error),
                    "error_type": type(error).__name__,
                    "measurement_complete": False,
                    "native_qualification": "UNKNOWN",
                    "qualification_credit": 0,
                },
                indent=2,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
