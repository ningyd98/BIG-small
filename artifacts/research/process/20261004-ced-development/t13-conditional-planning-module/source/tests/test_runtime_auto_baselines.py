"""共同在线基线的软件边界，不把离线物理结果交给决策器。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path

import pytest

from cloud_edge_robot_arm.auto_mode.runtime_events import (
    DecisionAction,
    DecisionEvent,
    DecisionEventKind,
)
from cloud_edge_robot_arm.contracts import ControlMode, Pose, RobotState
from cloud_edge_robot_arm.edge.evidence.conditions import (
    ConditionStatus,
    ConditionVerdict,
    OnlineEvidenceSnapshot,
)
from cloud_edge_robot_arm.edge.evidence.models import EvidenceVerdict
from cloud_edge_robot_arm.edge.recovery.verification_router import (
    VerificationBudget,
    VerificationBudgetState,
)
from cloud_edge_robot_arm.research.network import NetworkCostSnapshot
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.risk.models import RiskEstimate, RiskFeatures
from tests.test_rgbd_observations import observation_payload

NOW = datetime(2026, 10, 4, tzinfo=UTC)


def context(kind=DecisionEventKind.SKILL_BOUNDARY, **changes):
    events = import_module("cloud_edge_robot_arm.auto_mode.runtime_events")
    assert hasattr(events, "DecisionContext"), "T11 DecisionContext is missing"
    payload = observation_payload()
    payload.update(
        frame_id="fresh",
        observation_id="",
        captured_at=NOW,
        episode_id="episode",
        calibration_version="cal",
    )
    obs = RGBDObservation.model_validate(payload)
    values = dict(
        task_id="task",
        episode_id="episode",
        mode=ControlMode.PERIODIC_CLOUD_SUPERVISION,
        mode_version=1,
        plan_version=1,
        command_seq=1,
        event=DecisionEvent("event", kind, NOW, "fresh", False, ConditionStatus.PASS),
        online_evidence=OnlineEvidenceSnapshot(
            obs, RobotState(connected=True, tcp_pose=Pose(x=0.2, y=0, z=0.3)), {}, 1, 1, "ctx"
        ),
        evidence_verdict=EvidenceVerdict("VALID", ()),
        condition_verdicts=(ConditionVerdict(ConditionStatus.PASS, "target_visible", "fresh"),),
        risk_features=RiskFeatures({}, "fresh"),
        risk_estimate=RiskEstimate(0.1, {"CONTINUE": 0.1}, 0.001, 0.001, "VALID"),
        network_cost=NetworkCostSnapshot(
            observed_rtt_s=None,
            observed_loss_rate=None,
            observed_bandwidth_bytes_s=None,
            sampled_at=NOW,
        ),
        capabilities={
            DecisionAction.CONTINUE,
            DecisionAction.REOBSERVE,
            DecisionAction.REQUEST_CLOUD,
            DecisionAction.STOP,
        },
        verification_budget=VerificationBudgetState.start(VerificationBudget(2, 2, 2, 60), now=NOW),
    )
    values.update(changes)
    return events.DecisionContext(**values)


def policies():
    module = import_module("cloud_edge_robot_arm.auto_mode.baseline_policies")
    return [
        module.PeriodicPolicy(1),
        module.ThresholdPolicy(0.5),
        module.FrozenRuleAutoPolicy(module.freeze_legacy_rule_snapshot()),
    ]


@pytest.mark.parametrize("kind", list(DecisionEventKind))
def test_every_policy_receives_same_runtime_events(kind):
    for policy in policies():
        action = policy.decide(context(kind))
        assert action in DecisionAction


def test_successful_step_with_moved_target_redecides():
    for policy in policies()[:2]:
        ctx = context(evidence_verdict=EvidenceVerdict("INVALID", ("target_moved",)))
        assert policy.decide(ctx) == DecisionAction.REQUEST_CLOUD


def test_final_verification_failure_reenters_policy():
    for policy in policies()[:2]:
        ctx = context(
            DecisionEventKind.VERIFICATION_FAILED,
            condition_verdicts=(ConditionVerdict("FAIL", "object_placed", "fresh"),),
        )
        assert policy.decide(ctx) == DecisionAction.REQUEST_CLOUD


@pytest.mark.parametrize("period", [0.5, 1, 2, 5])
def test_b0_ticks_independently_of_skill_completion(period):
    module = import_module("cloud_edge_robot_arm.auto_mode.baseline_policies")
    policy = module.PeriodicPolicy(period)
    with policy.supervision(lambda frame: frame, lambda: "fresh") as ticker:
        assert ticker.period_s == period
        # The existing independent ticker is the only timing engine; converting
        # its counters must not depend on a successful atomic skill return.
        ticks = policy.tick_events(
            {"ticks": 3}, occurred_at=NOW, observation_id="fresh", atomic_action_active=True
        )
        assert len(ticks) == 1 and ticks[0].kind == DecisionEventKind.SUPERVISION_TICK
        assert ticks[0].atomic_action_active is True
        assert (
            policy.tick_events(
                {"ticks": 3}, occurred_at=NOW, observation_id="fresh", atomic_action_active=False
            )
            == ()
        )
        assert (
            policy.decide(context(event=replace(ticks[0], atomic_action_active=False)))
            == DecisionAction.REQUEST_CLOUD
        )


def test_non_safety_decision_waits_for_atomic_boundary():
    for policy in policies():
        ctx = context(
            event=DecisionEvent("atomic", DecisionEventKind.ANOMALY, NOW, "fresh", True, "FAIL")
        )
        assert policy.decide(ctx) == DecisionAction.CONTINUE


def test_hard_stop_bypasses_atomic_dwell_and_capability_filter():
    for policy in policies():
        ctx = context(
            capabilities=set(),
            event=DecisionEvent("atomic", DecisionEventKind.ANOMALY, NOW, "fresh", True, "FAIL"),
        )
        ctx = replace(
            ctx,
            online_evidence=replace(
                ctx.online_evidence,
                robot_state=ctx.online_evidence.robot_state.model_copy(
                    update={"estop_engaged": True}
                ),
            ),
        )
        assert policy.decide(ctx) == DecisionAction.STOP


def test_unknown_evidence_reserves_budget_and_never_continues():
    for policy in policies()[:2]:
        ctx = context(evidence_verdict=EvidenceVerdict("UNKNOWN", ("depth_missing",)))
        assert policy.decide(ctx) == DecisionAction.REOBSERVE
        assert ctx.verification_budget.remaining_reobservations == 1
        assert policy.decide(ctx) == DecisionAction.REOBSERVE
        assert ctx.verification_budget.remaining_reobservations == 1
        ctx = replace(ctx, event=replace(ctx.event, event_id="next"))
        assert policy.decide(ctx) == DecisionAction.REOBSERVE
        ctx = replace(ctx, event=replace(ctx.event, event_id="third"))
        assert policy.decide(ctx) == DecisionAction.STOP


def test_unaccepted_recovery_never_appears_in_baselines():
    for policy in policies()[:2]:
        ctx = context(
            evidence_verdict=EvidenceVerdict("INVALID", ("moved",)),
            capabilities={DecisionAction.LOCAL_RECOVER, DecisionAction.STOP},
        )
        assert policy.decide(ctx) == DecisionAction.STOP


@pytest.mark.parametrize(
    "invalid",
    [
        {"oracle": True},
        {"nested": {"ground_truth": (1, 2, 3)}},
        {"fault_schedule": [(3, "move")]},
        {"source": "physical_evaluator"},
    ],
)
def test_oracle_and_future_schedule_are_rejected_before_policy(invalid):
    ctx = context()
    with pytest.raises(ValueError, match="online"):
        replace(ctx, online_evidence=replace(ctx.online_evidence, visual_facts=invalid))


def test_observation_and_version_mismatch_cannot_construct_context():
    with pytest.raises(ValueError, match="identity|version"):
        context(
            event=DecisionEvent("old", DecisionEventKind.CLOUD_RETURN, NOW, "old", False, "PASS")
        )
    with pytest.raises(ValueError, match="identity|version"):
        context(plan_version=2)


def test_deadline_exhaustion_prevents_all_ordinary_decisions():
    for policy in policies():
        ctx = context()
        ctx.verification_budget.deadline_at = NOW
        assert policy.decide(ctx) == DecisionAction.STOP


def test_b1_requires_calibrated_continue_risk():
    module = import_module("cloud_edge_robot_arm.auto_mode.baseline_policies")
    assert (
        module.ThresholdPolicy(0.5).decide(
            context(risk_estimate=RiskEstimate(0.1, {}, 0.01, 0.01, "VALID"))
        )
        == DecisionAction.REOBSERVE
    )
    assert (
        module.ThresholdPolicy(0.5).decide(
            context(risk_estimate=RiskEstimate(0.1, {"CONTINUE": 0.8}, 0.01, 0.01, "VALID"))
        )
        == DecisionAction.REQUEST_CLOUD
    )


def test_b2_missing_legacy_online_inputs_is_unavailable():
    assert policies()[2].decide(context()) == DecisionAction.STOP


def test_b2_rule_snapshot_unchanged():
    module = import_module("cloud_edge_robot_arm.auto_mode.baseline_policies")
    snapshot = module.freeze_legacy_rule_snapshot()
    old = snapshot.digest()
    with pytest.raises((AttributeError, TypeError, ValueError)):
        snapshot.risk_policy["network_weight"] = 0.9
    assert snapshot.digest() == old
    damaged = replace(
        snapshot, source_hashes={**snapshot.source_hashes, "auto_mode/selector.py": "0" * 64}
    )
    with pytest.raises(ValueError, match="source"):
        module.FrozenRuleAutoPolicy(damaged)


def test_no_feasible_baseline_disables_savings_claim(tmp_path: Path):
    module = import_module("cloud_edge_robot_arm.auto_mode.baseline_policies")
    result = module.select_b0(
        {0.5: tmp_path / "a", 1: tmp_path / "b", 2: tmp_path / "c", 5: tmp_path / "d"}
    )
    assert result["status"] == "INCOMPLETE"
    assert result["savings_claim_allowed"] is False
    assert result["selected_period_s"] is None


def test_selection_requires_all_registered_curves(tmp_path: Path):
    module = import_module("cloud_edge_robot_arm.auto_mode.baseline_policies")
    result = module.select_b0({2: tmp_path})
    assert result["status"] == "INCOMPLETE" and result["selected_period_s"] is None


def test_hard_stop_overrides_a_cached_ordinary_decision():
    for policy in policies()[:2]:
        ctx = context()
        assert policy.decide(ctx) == DecisionAction.CONTINUE
        fault = ctx.online_evidence.robot_state.model_copy(update={"collision_detected": True})
        same_event = replace(ctx, online_evidence=replace(ctx.online_evidence, robot_state=fault))
        assert policy.decide(same_event) == DecisionAction.STOP


def test_event_unknown_verification_cannot_continue():
    for policy in policies()[:2]:
        ctx = context(
            event=DecisionEvent(
                "unknown", DecisionEventKind.RESULT_VERIFIED, NOW, "fresh", False, "UNKNOWN"
            )
        )
        assert policy.decide(ctx) == DecisionAction.REOBSERVE


def test_b2_reuses_original_weights_and_online_mode_selection():
    from cloud_edge_robot_arm.auto_mode.models import AutoModeState
    from cloud_edge_robot_arm.risk.models import RiskPolicy
    from cloud_edge_robot_arm.skill_cache.models import SkillCacheLookupResult
    from tests.test_phase7_auto_mode_repository import _risk_input

    module = import_module("cloud_edge_robot_arm.auto_mode.baseline_policies")
    original = _risk_input().model_copy(
        update={
            "task_id": "task",
            "current_time": NOW,
            "scene_updated_at": NOW,
            "last_heartbeat_at": NOW,
            "current_mode": ControlMode.PERIODIC_CLOUD_SUPERVISION,
        }
    )
    state = AutoModeState(
        task_id="task",
        current_mode=ControlMode.PERIODIC_CLOUD_SUPERVISION,
        mode_version=1,
        last_switch_at=NOW - timedelta(minutes=10),
    )
    legacy = module.LegacyRuleEvidence(
        state, original, SkillCacheLookupResult(match_type="exact_match"), True, True, True, True
    )
    snapshot = module.freeze_legacy_rule_snapshot(RiskPolicy(version="risk-v1"))
    policy = module.FrozenRuleAutoPolicy(snapshot)
    ctx = context(legacy_rule_evidence=legacy)
    assert policy.decide(ctx) == DecisionAction.CONTINUE
    assert policy.last_mode_decision.selected_mode == ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY
    assert policy.last_mode_decision.risk_score == pytest.approx(11.95)
    # Model-calibrated probability cannot alter frozen B2 legacy rule scores.
    ctx = replace(
        ctx,
        event=replace(ctx.event, event_id="different"),
        risk_estimate=RiskEstimate(0.99, {"CONTINUE": 0.99}, 0.1, 0.1, "VALID"),
    )
    assert policy.decide(ctx) == DecisionAction.CONTINUE
    assert policy.last_mode_decision.risk_score == pytest.approx(11.95)


def _selection_tree(
    root: Path, period: float, *, failed: int = 0, requests: int = 1, duration: float = 10
):
    """构造完整独立评分输入；此合成测试fixture绝不写入研究产物。"""
    import hashlib
    import json
    from dataclasses import asdict

    from cloud_edge_robot_arm.research.cost_ledger import CostLedger, RequestCost
    from cloud_edge_robot_arm.research.protocol import build_scene_pools
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
        CompletionCriteria,
        evaluate_evidence,
    )
    from tests.test_rgbd_trajectory_dataset import _sample, _sequence

    root.mkdir()
    assignments = build_scene_pools(908, set(), protocol_version="ced.research.v2")["selection"]
    successes = [
        replace(s, self_collision_checked_pairs=(("link4", "link6"),)) for s in _sequence()
    ]
    failure = [
        replace(_sample(step), self_collision_checked_pairs=(("link4", "link6"),))
        for step in (0, 1)
    ]

    def write(path, value):
        path.write_text(json.dumps(value, sort_keys=True))

    write(root / "good.json", [asdict(s) for s in successes])
    write(root / "bad.json", [asdict(s) for s in failure])
    result = []
    for index, assignment in enumerate(assignments):
        case = root / "cases" / assignment["assignment_id"]
        case.mkdir(parents=True)
        template = failure if index < failed else successes
        scene = assignment["scene"]["scene_parameters"]
        target, destination = scene["target"], scene["destination"]
        episode_id = assignment["assignment_id"]
        samples = []
        for sample in template:
            placed = sample.physics_step > 101
            height = target["half_size"][2] + (
                0.05 if sample.physics_step > 0 and not placed else 0
            )
            xy = destination["position"][:2] if placed else target["position"][:2]
            samples.append(
                replace(
                    sample,
                    episode_id=episode_id,
                    object_position_m=(*xy, height),
                    object_bottom_z_m=height - target["half_size"][2],
                    object_half_extent_xy_m=tuple(target["half_size"][:2]),
                    region_center_xy_m=tuple(destination["position"][:2]),
                    region_half_extent_xy_m=tuple(destination["half_size"][:2]),
                )
            )
        outcome = asdict(
            evaluate_evidence(
                samples, CompletionCriteria("object", "target_region"), evaluation_start_step=0
            )
        )
        success = index >= failed
        assert outcome["success"] is success
        write(case / "physical-evidence.json", [asdict(sample) for sample in samples])
        write(case / "physical-outcome.json", outcome)
        write(
            case / "episode.json",
            {
                "episode_id": episode_id,
                "online_reported_complete": success,
                "terminal_reason": None,
                "success": success,
                "verification_records": [],
            },
        )
        ledger = CostLedger()
        for n in range(requests):
            ledger.record_request(
                RequestCost(
                    request_id=f"{index}-{n}",
                    sent_at=NOW,
                    finished_at=NOW + timedelta(seconds=1),
                    is_cloud_model=True,
                    model_role="PLANNER",
                    deployment="CLOUD",
                    provider_location="REMOTE_SERVICE",
                    provider_version="frozen-cloud",
                    status="SUCCESS",
                    serialized_sent_bytes=100,
                    serialized_received_bytes=10,
                )
            )
        summary = ledger.snapshot().model_dump(mode="json")
        costs = {
            "summary": summary,
            "requests": [r.model_dump(mode="json") for r in ledger.requests()],
        }
        write(case / "costs.json", costs)
        row = {
            "assignment_id": assignment["assignment_id"],
            "stratum_id": assignment["stratum_id"],
            "success": success,
            "wall_duration_s": duration,
            "costs": summary,
            "terminal_reason": None,
        }
        write(case / "case-result.json", row)
        result.append(row)
    write(root / "assignments.json", assignments)
    write(root / "results.json", result)
    write(
        root / "selection-manifest.json",
        {
            "stage": "SELECTION",
            "period_s": period,
            "snapshot_id": "common",
            "role_bundle_hash": "c" * 64,
            "device_pipeline_hash": "d" * 64,
            "edge_provider_hash": "e" * 64,
            "assignments_sha256": hashlib.sha256(
                (root / "assignments.json").read_bytes()
            ).hexdigest(),
            "results_sha256": hashlib.sha256((root / "results.json").read_bytes()).hexdigest(),
        },
    )
    return root


def test_b0_selected_from_feasible_periods(tmp_path: Path):
    module = import_module("cloud_edge_robot_arm.auto_mode.baseline_policies")
    curves = {
        0.5: _selection_tree(tmp_path / "half", 0.5, requests=1, failed=20),
        1: _selection_tree(tmp_path / "one", 1, requests=2, duration=4),
        2: _selection_tree(tmp_path / "two", 2, requests=1, duration=8),
        5: _selection_tree(tmp_path / "five", 5, requests=1, duration=9),
    }
    result = module.select_b0(curves)
    assert result["errors"] == []
    assert result["status"] == "SELECTED" and result["selected_period_s"] == 2
    assert len(result["curves"]) == 4 and all(row["assigned"] == 120 for row in result["curves"])


def test_complete_no_feasible_baseline_disables_savings_claim(tmp_path: Path):
    module = import_module("cloud_edge_robot_arm.auto_mode.baseline_policies")
    curves = {p: _selection_tree(tmp_path / str(p), p, failed=30) for p in [0.5, 1, 2, 5]}
    result = module.select_b0(curves)
    assert result["status"] == "NO_FEASIBLE_BASELINE"
    assert result["selected_period_s"] is None and result["savings_claim_allowed"] is False


def test_selection_rejects_published_success_without_raw_physical_success(tmp_path: Path):
    import json

    module = import_module("cloud_edge_robot_arm.auto_mode.baseline_policies")
    curves = {p: _selection_tree(tmp_path / str(p), p) for p in [0.5, 1, 2, 5]}
    root = curves[1]
    assignments = json.loads((root / "assignments.json").read_text())
    case = root / "cases" / assignments[0]["assignment_id"]
    (case / "physical-evidence.json").unlink()
    (case / "physical-evidence.json").write_bytes((root / "bad.json").read_bytes())
    result = module.select_b0(curves)
    assert result["status"] == "INCOMPLETE" and result["selected_period_s"] is None
    assert result["errors"]


def mode_policy_snapshot(root: Path, **updates):
    """合成完整selection目录供事务软件测试，不输出真实方法验收。"""
    import hashlib
    import json

    from cloud_edge_robot_arm.auto_mode.models import (
        ModeSwitchPolicySnapshot,
        ModeTransitionCheckpoint,
    )
    from cloud_edge_robot_arm.contracts import AutoModeTransition, AutoModeTransitionStatus

    module = import_module("cloud_edge_robot_arm.auto_mode.baseline_policies")
    root.mkdir()
    params = dict(
        method_id="B2",
        policy_version="auto-v1",
        min_dwell_s=120.0,
        cooldown_s=300.0,
        max_switches=5,
        confirmation_count=2,
    )
    params.update(updates)
    source_hashes = module.mode_switch_source_hashes()
    raw = _selection_tree(root / "candidate", 1)
    assignments = json.loads((raw / "assignments.json").read_text())
    for assignment in assignments:
        transition = AutoModeTransition(
            transition_id=assignment["assignment_id"],
            task_id=assignment["assignment_id"],
            from_mode=ControlMode.PERIODIC_CLOUD_SUPERVISION,
            to_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
            status=AutoModeTransitionStatus.COMMITTED,
            expected_mode_version=1,
            new_mode_version=2,
            idempotency_key=assignment["assignment_id"],
            decision_id="d",
            prepared_at=NOW - timedelta(seconds=1),
            committed_at=NOW,
            payload_hash="a" * 64,
        )
        checkpoint = ModeTransitionCheckpoint(
            task_id=assignment["assignment_id"],
            checkpoint_id="cp",
            plan_version=1,
            command_seq=1,
            mode_version=1,
            atomic_action_active=False,
            confirmation_count=2,
            persisted_at=NOW,
        )
        log = {
            "policy_parameters": params,
            "source_hashes": source_hashes,
            "initial_last_switch_at": (NOW - timedelta(seconds=600)).isoformat(),
            "initial_current_mode": ControlMode.PERIODIC_CLOUD_SUPERVISION.value,
            "initial_mode_version": 1,
            "committed_transitions": [transition.model_dump(mode="json")],
            "checkpoints": [checkpoint.model_dump(mode="json")],
        }
        (raw / "cases" / assignment["assignment_id"] / "mode-transition-events.json").write_text(
            json.dumps(log)
        )
    manifest = {
        "schema_version": "ced.mode-selection.v1",
        "stage": "SELECTION",
        "selected_candidate_id": "original",
        "candidates": [
            {
                "candidate_id": "original",
                "directory": "candidate",
                "b0_period_s": 1,
                "parameters": params,
                "source_hashes": source_hashes,
            }
        ],
    }
    path = root / "mode-policy-selection.json"
    path.write_text(json.dumps(manifest))
    return ModeSwitchPolicySnapshot(
        **params,
        source_hashes=source_hashes,
        selection_directory=str(root),
        selection_manifest_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def test_mode_policy_requires_raw_selection_not_a_bare_manifest_hash(tmp_path: Path):
    module = import_module("cloud_edge_robot_arm.auto_mode.baseline_policies")
    snapshot = mode_policy_snapshot(tmp_path / "mode")
    assert module.verify_mode_switch_policy(snapshot)["accepted"] is True
    assignments = __import__("json").loads(
        (Path(snapshot.selection_directory) / "candidate" / "assignments.json").read_text()
    )
    missing = (
        Path(snapshot.selection_directory)
        / "candidate"
        / "cases"
        / assignments[0]["assignment_id"]
        / "physical-evidence.json"
    )
    missing.unlink()
    verdict = module.verify_mode_switch_policy(snapshot)
    assert verdict["accepted"] is False


@pytest.mark.parametrize(
    "damage", ["missing_checkpoint", "atomic_checkpoint", "unconfirmed_checkpoint"]
)
def test_mode_selection_rejects_unverified_boundary_trace(tmp_path: Path, damage):
    import json

    module = import_module("cloud_edge_robot_arm.auto_mode.baseline_policies")
    snapshot = mode_policy_snapshot(tmp_path / "mode")
    raw = Path(snapshot.selection_directory) / "candidate"
    assignment = json.loads((raw / "assignments.json").read_text())[0]
    path = raw / "cases" / assignment["assignment_id"] / "mode-transition-events.json"
    log = json.loads(path.read_text())
    if damage == "missing_checkpoint":
        log["checkpoints"] = []
    elif damage == "atomic_checkpoint":
        log["checkpoints"][0]["atomic_action_active"] = True
    else:
        log["checkpoints"][0]["confirmation_count"] = 1
    path.write_text(json.dumps(log))
    assert module.verify_mode_switch_policy(snapshot)["accepted"] is False


def test_b2_mode_selection_cannot_rewrite_original_dwell_rule(tmp_path: Path):
    module = import_module("cloud_edge_robot_arm.auto_mode.baseline_policies")
    snapshot = mode_policy_snapshot(tmp_path / "mode", min_dwell_s=0)
    assert module.verify_mode_switch_policy(snapshot)["accepted"] is False


def test_context_freezes_calibrated_action_probabilities():
    module = import_module("cloud_edge_robot_arm.auto_mode.baseline_policies")
    probabilities = {"CONTINUE": 0.1}
    ctx = context(risk_estimate=RiskEstimate(0.1, probabilities, 0.001, 0.001, "VALID"))
    probabilities["CONTINUE"] = 0.99
    assert module.ThresholdPolicy(0.5).decide(ctx) == DecisionAction.CONTINUE
    with pytest.raises(TypeError):
        ctx.risk_estimate.failure_probability_by_action["CONTINUE"] = 0.99


@pytest.mark.parametrize(
    "changed_risk",
    [
        RiskEstimate(None, {"CONTINUE": None}, None, None, "UNKNOWN"),
        RiskEstimate(0.9, {"CONTINUE": 0.9}, 0.02, 0.05, "VALID"),
    ],
)
def test_duplicate_event_rejects_replaced_calibrated_risk(changed_risk):
    module = import_module("cloud_edge_robot_arm.auto_mode.baseline_policies")
    policy = module.ThresholdPolicy(0.5)
    ctx = context()
    assert policy.decide(ctx) == DecisionAction.CONTINUE
    altered = replace(ctx, risk_estimate=changed_risk)
    assert policy.decide(altered) == DecisionAction.STOP
    assert ctx.verification_budget.remaining_reobservations == 2
    fresh = replace(altered, event=replace(altered.event, event_id="new-risk-event"))
    expected = (
        DecisionAction.REOBSERVE
        if changed_risk.status == "UNKNOWN"
        else DecisionAction.REQUEST_CLOUD
    )
    assert policy.decide(fresh) == expected


@pytest.mark.parametrize(
    "damage", ["chain_from_mode", "initial_mode", "initial_version", "missing_initial_mode"]
)
def test_mode_selection_rejects_impossible_initial_or_chained_state(tmp_path: Path, damage):
    import json

    module = import_module("cloud_edge_robot_arm.auto_mode.baseline_policies")
    snapshot = mode_policy_snapshot(tmp_path / "mode")
    raw = Path(snapshot.selection_directory) / "candidate"
    assignment = json.loads((raw / "assignments.json").read_text())[0]
    path = raw / "cases" / assignment["assignment_id"] / "mode-transition-events.json"
    log = json.loads(path.read_text())
    if damage == "chain_from_mode":
        row = dict(log["committed_transitions"][0])
        row.update(
            transition_id="second",
            idempotency_key="second",
            expected_mode_version=2,
            new_mode_version=3,
            prepared_at=(NOW + timedelta(seconds=599)).isoformat(),
            committed_at=(NOW + timedelta(seconds=600)).isoformat(),
        )
        cp = dict(log["checkpoints"][0])
        cp.update(
            checkpoint_id="second",
            mode_version=2,
            persisted_at=(NOW + timedelta(seconds=600)).isoformat(),
        )
        log["committed_transitions"].append(row)
        log["checkpoints"].append(cp)
    elif damage == "initial_mode":
        log["initial_current_mode"] = ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY.value
    elif damage == "initial_version":
        log["initial_mode_version"] = 2
    else:
        log.pop("initial_current_mode", None)
    path.write_text(json.dumps(log))
    assert module.verify_mode_switch_policy(snapshot)["accepted"] is False
