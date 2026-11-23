"""Replay the thesis' software controls from a source checkout, without model or robot I/O.

Run with PYTHONPATH=src:. python -m scripts.graduation.decision_replay --output NEW_DIRECTORY.
The numerical and RGB-D fixtures are deliberately the ones shipped with the regression suite.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tests.test_decision_judgment import prepared_context, weights
from tests.test_joint_visual_policy import ledger as policy_history
from tests.test_joint_visual_policy import policy
from tests.test_phase6_recovery_replanning import _make_contract
from tests.test_replan_activation import NOW, MockStagedGateway, submit_proof
from tests.test_research_risk_replay import numeric_fixture, parameters
from tests.test_visual_repair_builder import fixture as repair_fixture
from tests.test_visual_repair_builder import provider as software_provider

from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService
from cloud_edge_robot_arm.cloud.replanning.role_visual_repair import plain
from cloud_edge_robot_arm.cloud.replanning.visual_dependencies import StepDependency
from cloud_edge_robot_arm.cloud.replanning.visual_repair import (
    RepairProposal,
    build_visual_repair,
    repair_window,
)
from cloud_edge_robot_arm.contracts.models import (
    EdgeEvent,
    EdgeEventType,
    FailureSummary,
    SkillName,
)
from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec
from cloud_edge_robot_arm.edge.evidence.models import ActionEvidenceContract, VisualEvidence
from cloud_edge_robot_arm.edge.evidence.validator import validate_b3, validate_evidence
from cloud_edge_robot_arm.edge.recovery.retry_budget import RetryBudgetService
from cloud_edge_robot_arm.repositories.event_autonomy.sqlite import SQLiteEventAutonomyRepository
from cloud_edge_robot_arm.research.cost_ledger import CostLedger, RequestCost
from cloud_edge_robot_arm.research.risk_replay import (
    replay_diagnostic_candidates,
    required_replay_source_paths,
    risk_replay_environment,
)
from cloud_edge_robot_arm.vision.risk.models import RiskEstimate

ROOT = Path(__file__).resolve().parents[2]
SOURCES = (
    "scripts/graduation/decision_replay.py",
    "src/cloud_edge_robot_arm/auto_mode/joint_policy.py",
    "src/cloud_edge_robot_arm/auto_mode/candidates.py",
    "src/cloud_edge_robot_arm/auto_mode/judgment.py",
    "src/cloud_edge_robot_arm/auto_mode/runtime_events.py",
    "src/cloud_edge_robot_arm/cloud/replanning/apply_service.py",
    "src/cloud_edge_robot_arm/cloud/replanning/merge.py",
    "src/cloud_edge_robot_arm/cloud/replanning/role_visual_repair.py",
    "src/cloud_edge_robot_arm/cloud/replanning/visual_dependencies.py",
    "src/cloud_edge_robot_arm/cloud/replanning/visual_repair.py",
    "src/cloud_edge_robot_arm/edge/evidence/validator.py",
    "src/cloud_edge_robot_arm/edge/evidence/conditions.py",
    "src/cloud_edge_robot_arm/edge/evidence/models.py",
    "src/cloud_edge_robot_arm/edge/recovery/retry_budget.py",
    "src/cloud_edge_robot_arm/research/cost_ledger.py",
    "src/cloud_edge_robot_arm/repositories/event_autonomy/sqlite.py",
    *required_replay_source_paths(),
    "tests/test_research_risk_replay.py",
    "tests/test_replan_activation.py",
    "tests/test_visual_repair_builder.py",
    "tests/test_decision_judgment.py",
    "tests/test_joint_visual_policy.py",
    "tests/test_phase6_recovery_replanning.py",
    "tests/test_phase6_2_replan_resume.py",
    "tests/test_visual_evidence_contract.py",
    "tests/test_rgbd_observations.py",
    "tests/test_runtime_auto_baselines.py",
)


def wire(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save(path: Path, value) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(
            plain(value), stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        )
        stream.write("\n")


def risk_controls(root: Path) -> dict:
    controls = {}
    grid = [parameters(7), parameters(11)]
    for case in (
        "complete",
        "eight_calibration_groups",
        "outside_support",
        "truth_in_online_features",
    ):
        allocations, rows = numeric_fixture()
        if case == "eight_calibration_groups":
            for row in rows:
                if row["group_id"] == "calibration-g-8":
                    row["group_id"] = "calibration-g-7"
                    row["scene_hash"] = digest(row["group_id"].encode())
        elif case == "outside_support":
            selected = next(row for row in rows if row["sample_id"] == "selection-0")
            selected["online_features"]["depth_median_m"] = 99.0
        elif case == "truth_in_online_features":
            rows[0]["online_features"]["true_error_m"] = 0.0
        inputs = {
            "allocations": [asdict(a) for a in allocations],
            "observations": rows,
            "candidates": grid,
        }
        save(root / f"risk-{case}-input.json", inputs)
        entry = {"input_sha256": digest(wire(inputs))}
        controls[case] = entry
        try:
            result = replay_diagnostic_candidates(allocations, rows, grid)
        except ValueError as exc:
            if case != "truth_in_online_features":
                raise
            entry.update(status="REJECTED", exception=type(exc).__name__, reason=str(exc))
            continue
        if case == "truth_in_online_features":
            raise AssertionError("online true_error_m passed the feature boundary")
        save(root / f"risk-{case}-result.json", result)
        entry.update(
            status=result["status"],
            scope=result["scope"],
            counts=result["counts"],
            winner=result["diagnostic_winner_hash"],
            split_allocations={
                s: values["allocated"] for s, values in result["split_counts"].items()
            },
            calibration_groups=len(
                {row["group_id"] for row in rows if row["split"] == "calibration"}
            ),
            candidates=[
                {
                    "parameters_hash": c["parameters_hash"],
                    "status": c["status"],
                    "selection_brier": c["selection_brier"],
                    "test_brier": c["test_brier"],
                    "selection_probabilities": [
                        p["failure_probability"] for p in c["selection_results"]
                    ],
                    "marker_center_bound_m": (c["calibration"] or {}).get(
                        "marker_point_error_bound_m"
                    ),
                    "motion_residual_bound_m_s": (c["calibration"] or {}).get(
                        "motion_residual_bound_m_s"
                    ),
                    "reasons": c["reasons"],
                }
                for c in result["candidate_results"]
            ],
        )
    return controls


def cost_controls(root: Path) -> dict:
    """Persist serialized UTF-8 bodies; cancellation and timeout do not produce response bodies."""
    spool = root / "payloads"
    spool.mkdir()
    bodies = {
        "success-request": {"id": "p1", "target": "红块", "role": "planner"},
        "success-response": {"id": "p1", "reply": "抓取"},
        "timeout-request": {"id": "p2", "target": "红块", "role": "replanner"},
    }
    payloads, sizes = [], {}
    for name, value in bodies.items():
        path = spool / f"{name}.json"
        path.write_bytes(wire(value))
        actual = path.read_bytes()
        sizes[name] = len(actual)
        payloads.append(
            {
                "file": path.relative_to(root).as_posix(),
                "body": value,
                "utf8_bytes": len(actual),
                "sha256": digest(actual),
            }
        )
    common = dict(
        is_cloud_model=True,
        deployment="CLOUD",
        provider_location="LOCAL_HOST",
        provider_version="fixture.v1",
        finished_at=NOW + timedelta(seconds=1),
    )
    success = RequestCost(
        **common,
        request_id="p1",
        model_role="PLANNER",
        sent_at=NOW,
        status="SUCCESS",
        serialized_sent_bytes=sizes["success-request"],
        serialized_received_bytes=sizes["success-response"],
    )
    timeout = RequestCost(
        **common,
        request_id="p2",
        model_role="REPLANNER",
        sent_at=NOW,
        status="TIMEOUT",
        serialized_sent_bytes=sizes["timeout-request"],
        serialized_received_bytes=0,
    )
    cancelled = RequestCost(
        **common,
        request_id="p3",
        model_role="PLANNER",
        sent_at=None,
        status="CANCELLED",
        serialized_sent_bytes=0,
        serialized_received_bytes=0,
    )
    ledger = CostLedger()
    events = []
    for name, row in (
        ("success", success),
        ("sent_timeout", timeout),
        ("unsent_cancel", cancelled),
        ("exact_replay", success),
        ("same_id_different_status", success.model_copy(update={"status": "ERROR"})),
    ):
        event = {"case": name, "input": row.model_dump(mode="json")}
        try:
            ledger.record_request(row)
        except ValueError as exc:
            if name != "same_id_different_status":
                raise
            event.update(exception=type(exc).__name__, reason=str(exc))
        snapshot = ledger.snapshot()
        event.update(
            sent_attempts_after=snapshot.model_requests, bytes_after=snapshot.application_bytes
        )
        events.append(event)
    return {
        "payloads": payloads,
        "events": events,
        "ledger": ledger.export(),
        "transport": "local files containing serialized application bodies",
        "status_and_timestamps": "fixture inputs",
        "physical_network_requests": 0,
        "billing": "UNKNOWN",
    }


def policy_controls(root: Path) -> list:
    """Counterfactual cost changes hold the numerical risk pair and all other inputs fixed."""
    rows = []
    for name, local, cloud, extra_network_s, software in (
        ("low_risk", 0.01, 0.09, 0.0, True),
        ("high_risk", 0.9, 0.01, 0.0, True),
        ("low_transfer_cost", 0.09, 0.01, 0.0, True),
        ("high_transfer_cost", 0.09, 0.01, 5.0, True),
        ("no_accepted_selection", 0.09, 0.01, 0.0, False),
    ):
        risk = RiskEstimate(
            local, {"CONTINUE": local, "REQUEST_CLOUD": cloud}, 0.001, 0.001, "VALID"
        )
        context = prepared_context(risk_estimate=risk)
        ledger = policy_history()
        ledger.record_timing(network_s=extra_network_s)
        chooser = policy(costs=ledger, software_only=software)
        before = ledger.snapshot()
        inputs = plain(
            {
                "context": context,
                "ledger": ledger.export(),
                "weights": weights(),
                "software_only": software,
            }
        )
        save(root / f"policy-{name}-input.json", inputs)
        action = chooser.decide(context)
        trace = chooser.last_trace
        save(root / f"policy-{name}-trace.json", trace)
        rows.append(
            {
                "case": name,
                "input_sha256": digest(wire(inputs)),
                "fixture_probabilities": risk.failure_probability_by_action.copy(),
                "fixture_ledger": before.model_dump(),
                "weights": weights(),
                "action": action.value,
                "disposition": trace.disposition,
                "reasons": trace.reason_codes,
                "model_request_delta": ledger.snapshot().model_requests - before.model_requests,
                "valid_after_decision": trace.envelope.valid_until > trace.envelope.created_at,
            }
        )
    return rows


def gate_controls() -> list:
    rows = []
    for name, duration, motion in (
        ("short", 0.2, 0.02),
        ("long", 0.4, 0.02),
        ("no_motion", 0.2, None),
    ):
        evidence = VisualEvidence(
            "frame", "cal", NOW - timedelta(seconds=0.1), 0.002, motion, "CONFIRMED", "VALID"
        )
        action = ActionEvidenceContract(evidence, duration, 0.01, ("rgbd",), (), (), 1, 1, "ctx")
        args = (action, NOW, "ctx", "cal")
        rows.append(
            {
                "case": name,
                "fixture_frame_age_s": 0.1,
                "fixture_error_m": 0.002,
                "fixture_motion_m_s": motion,
                "fixture_duration_s": duration,
                "fixture_action": plain(action),
                "tolerance_m": 0.01,
                "joint": asdict(validate_evidence(*args)),
                "b3": asdict(validate_b3(*args)),
            }
        )
    return rows


def release_failure():
    """A completed RELEASE, a failed VERIFY_RESULT and an independent pending monitoring step."""
    request, base, _, observation = repair_fixture()
    release, verify, telemetry = base.active_contract.steps
    release = release.model_copy(
        update={
            "step_id": "release",
            "skill": SkillName.RELEASE,
            "parameters": {},
            "success_conditions": ["object_released"],
        }
    )
    verify = verify.model_copy(update={"step_id": "verify", "skill": SkillName.VERIFY_RESULT})
    contract = base.active_contract.model_copy(update={"steps": [release, verify, telemetry]})
    graph = (
        StepDependency("release", (), ("effect-proof",), "one-release", True),
        StepDependency("verify", ("release",), ("target-image",), None, False),
        StepDependency("telemetry", (), ("telemetry",), None, False),
    )
    updates = {"completed_step_ids": ["release"], "failed_step_id": "verify"}
    context = replace(
        base,
        active_contract=contract,
        checkpoint=base.checkpoint.model_copy(update=updates),
        dependencies=graph,
        invalid_evidence_ids=frozenset({"target-image"}),
        completed_effect_conditions={"release": (ConditionSpec("object_released"),)},
    )
    return request.model_copy(update=updates), context, observation


class SoftwareGateway(MockStagedGateway):
    """Capture the actual staged contract and bind the simulated ACK to its issuance time."""

    def stage(self, contract, repair_id):
        self.staged_contract = contract.model_copy(deep=True)
        ack = super().stage(contract, repair_id)
        self.stage_ack = ack.model_copy(update={"timestamp": contract.issued_at})
        return self.stage_ack


def repair_controls(root: Path) -> dict:
    request, context, observation = release_failure()
    window = repair_window(context)
    proof_time = NOW + timedelta(seconds=0.2)
    inputs = plain(
        {
            "request": request,
            "observation": observation,
            "context": context,
            "window": window,
            "fixture_check_time": proof_time,
        }
    )
    save(root / "repair-input.json", inputs)
    rows = []
    for method, full in (("local", False), ("full_remaining", True)):
        response = build_visual_repair(
            request,
            window,
            observation,
            context=context,
            provider=software_provider,
            full_remaining=full,
            clock=lambda: proof_time,
        )
        save(root / f"repair-{method}-candidate.json", response.model_dump(mode="json"))
        pending = [
            s for s in context.active_contract.steps if s.step_id not in request.completed_step_ids
        ]
        changed = [
            old.step_id
            for old, new in zip(pending, response.new_steps, strict=True)
            if old.model_dump() != new.model_dump()
        ]
        db = root / f"{method}.sqlite"
        repo = SQLiteEventAutonomyRepository(db)
        gateway = SoftwareGateway()
        try:
            repo.save_active_contract(
                context.active_contract, plan_id=request.plan_id, robot_id=request.robot_id
            )
            repo.save_event(
                EdgeEvent(
                    task_id=request.task_id,
                    plan_version=1,
                    command_seq=1,
                    timestamp=NOW,
                    event_id=request.trigger_event_id,
                    step_id="verify",
                    event_type=EdgeEventType.VERIFY_FAILED,
                    severity="ERROR",
                )
            )
            repo.save_failure_summary(
                FailureSummary(
                    task_id=request.task_id,
                    plan_version=1,
                    command_seq=1,
                    timestamp=NOW,
                    summary_id=request.failure_summary_id,
                    failure_event_id=request.trigger_event_id,
                    failed_step_id="verify",
                    completed_step_ids=["release"],
                    local_retry_count=0,
                    reason="fixture missing target image",
                    recovery_hint="verify again",
                )
            )
            repo.save_execution_checkpoint(context.checkpoint)
            service = ReplanApplyService(
                repository=repo,
                dispatcher=gateway,
                submit_guard=submit_proof,
                clock=lambda: proof_time,
            )
            first = service.apply(request=request, response=response)
        finally:
            repo.close()
        reopened = SQLiteEventAutonomyRepository(db)
        retry_gateway = SoftwareGateway()
        try:
            service = ReplanApplyService(
                repository=reopened,
                dispatcher=retry_gateway,
                submit_guard=submit_proof,
                clock=lambda: proof_time,
            )
            repeated = service.apply(request=request, response=response)
            stale_request = request.model_copy(update={"request_id": "stale-request"})
            stale = service.apply(
                request=stale_request,
                response=response.model_copy(update={"request_id": "stale-request"}),
            )
            active = reopened.get_active_contract(request.task_id).contract
        finally:
            reopened.close()
        if not first.applied or first.contract is None:
            raise ValueError(f"{method} failed software activation: {first.errors}")
        completed = set(context.checkpoint.completed_step_ids)
        done_effects = {s.skill for s in context.active_contract.steps if s.step_id in completed}
        pending_after = [s for s in gateway.staged_contract.steps if s.step_id not in completed]
        rows.append(
            {
                "method": method,
                "input_sha256": digest(wire(inputs)),
                "outcome": response.outcome,
                "actual_replaced_ids": changed,
                "new_candidate_steps": [s.step_id for s in response.new_steps],
                "current_step": active.current_step_id,
                "activation": first.record.status,
                "active_plan_version": active.plan_version,
                "command_seq": active.command_seq,
                "completed_nonrepeatable_in_pending": sum(
                    s.skill in done_effects for s in pending_after
                ),
                "first_gateway_calls": gateway.calls,
                "after_restart": repeated.record.status,
                "restart_gateway_calls": retry_gateway.calls,
                "execution_start_receipt": first.record.start_receipt,
                "stale_request": {"status": stale.record.status, "reason": stale.record.reason},
            }
        )
    aliased = replace(context.dependencies[1], physical_effect_id="one-release")
    try:
        repair_window(
            replace(
                context, dependencies=(context.dependencies[0], aliased, context.dependencies[2])
            )
        )
    except ValueError as exc:
        alias_result = {"status": "REJECTED", "exception": type(exc).__name__, "reason": str(exc)}
    else:
        raise AssertionError("duplicate completed effect identity admitted to repair graph")

    def duplicate_release(req, allowed, frame, active):
        replacements = dict(software_provider(req, allowed, frame, active).replacements)
        replacements["verify"] = replacements["verify"].model_copy(
            update={"skill": SkillName.RELEASE}
        )
        return RepairProposal(replacements)

    double_release = build_visual_repair(
        request,
        window,
        observation,
        context=context,
        provider=duplicate_release,
        clock=lambda: proof_time,
    )
    return {
        "paired": rows,
        "completed_effect_alias": alias_result,
        "proposed_second_release": double_release.model_dump(mode="json"),
        "provider": "deterministic replacement fixture",
        "gateway": "MOCK stage/resume receipts",
    }


def budget_controls(root: Path) -> list:
    contract = _make_contract()
    save(root / "retry-contract.json", contract)
    path = root / "retry.sqlite"
    rows = []
    # Opening a new connection and service each time exercises persistent budget ownership.
    for event_id in ("failure-1", "failure-1", "failure-2", "failure-3", "failure-4"):
        repo = SQLiteEventAutonomyRepository(path)
        try:
            service = RetryBudgetService(repository=repo)
            before = service.initialize(contract.task_id, contract)
            allowed, reason = service.can_attempt(contract.task_id, "s2", "GRASP", event_id)
            consumed, _ = service.consume_if_available(contract.task_id, "s2", "GRASP", event_id)
            after = repo.get_retry_budget(contract.task_id)
            rows.append(
                {
                    "event_id": event_id,
                    "before": before.remaining_retries,
                    "allowed": allowed,
                    "consumed": consumed,
                    "reason": reason,
                    "remaining": after.remaining_retries,
                    "event_counts": after.event_retry_counts,
                }
            )
        finally:
            repo.close()
    return rows


def run(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=False)
    result = {
        "schema": "bigsmall.graduation.decision-replay.v1",
        "scope": "SOFTWARE_ONLY",
        "environment": risk_replay_environment(),
        "source_sha256": {path: digest((ROOT / path).read_bytes()) for path in SOURCES},
        "formal_trials": 0,
        "physical_executions": 0,
        "external_model_requests": 0,
    }
    timings = {
        "started_at": datetime.now(UTC).isoformat(),
        "clock": "time.perf_counter",
        "scope": "offline operations including local artifact I/O",
        "elapsed_s": {},
    }
    for name, job in (
        ("risk", lambda: risk_controls(root)),
        ("cost", lambda: cost_controls(root)),
        ("policy", lambda: policy_controls(root)),
        ("completion_gate", gate_controls),
        ("repair", lambda: repair_controls(root)),
        ("retry_budget", lambda: budget_controls(root)),
    ):
        started = time.perf_counter()
        result[name] = job()
        timings["elapsed_s"][name] = time.perf_counter() - started
    save(root / "decisions.public.json", result)
    save(root / "timing.json", timings)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
