"""Online evidence may authorize actions only from fresh, attributed RGB-D facts."""

from __future__ import annotations

import base64
import struct
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from importlib import import_module

import pytest

from cloud_edge_robot_arm.contracts import Pose, RobotState
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from tests.test_rgbd_observations import observation_payload


def evidence(*, facts=None, observation=None, state=None):
    module = import_module("cloud_edge_robot_arm.edge.evidence.conditions")
    return module.OnlineEvidenceSnapshot(
        observation=observation or RGBDObservation.model_validate(observation_payload()),
        robot_state=state or RobotState(connected=True, tcp_pose=Pose(x=0, y=0, z=10)),
        visual_facts=facts or {},
        plan_version=1,
        command_seq=1,
        context_hash="test",
    )


def fact(observation, value=True, **changes):
    return {
        "source": "rgbd_estimate",
        "observation_id": observation.observation_id,
        "target_id": "cube",
        "identity_confirmed": True,
        "value": value,
        "pixel": [0, 0],
        **changes,
    }


def verdict(name, snapshot, **kwargs):
    module = import_module("cloud_edge_robot_arm.edge.evidence.conditions")
    return module.evaluate_conditions(
        [module.ConditionSpec(name, target_id="cube", **kwargs)], snapshot
    )[0]


def test_visibility_is_not_tcp_height():
    assert verdict("target_visible", evidence()).status == "UNKNOWN"


def test_unknown_condition_or_missing_timestamp_cannot_pass():
    snap = evidence()
    assert verdict("invented_condition", snap).status == "UNKNOWN"
    broken = snap.observation.model_copy(update={"captured_at": None})
    assert verdict("gripper_open", replace(snap, observation=broken)).status == "UNKNOWN"


@pytest.mark.parametrize(
    "changes",
    [
        {"source": "oracle"},
        {"source": "physical_evaluator"},
        {"source": None},
        {"observation_id": "old"},
        {"identity_confirmed": False},
        {"identity_confirmed": None},
        {"target_id": "decoy"},
        {"pixel": [1, 1]},
        {"pixel": None},
        {"value": "true"},
    ],
)
def test_unattributed_wrong_identity_or_invalid_depth_cannot_pass(changes):
    snap = evidence()
    snap = replace(snap, visual_facts={"target_visible": fact(snap.observation, **changes)})
    assert verdict("target_visible", snap).status == "UNKNOWN"


def test_rgbd_positive_and_negative_facts_are_three_valued():
    snap = evidence()
    for value, expected in [(True, "PASS"), (False, "FAIL")]:
        current = replace(snap, visual_facts={"target_visible": fact(snap.observation, value)})
        result = verdict("target_visible", current)
        assert result.status == expected
        assert result.observation_id == snap.observation.observation_id


def test_frame_without_depth_cannot_authorize_visual_condition():
    payload = observation_payload()
    payload["depth_float32_base64"] = base64.b64encode(struct.pack("<4f", 0, 0, 0, 0)).decode()
    snap = evidence(observation=RGBDObservation.model_validate(payload))
    snap = replace(snap, visual_facts={"target_visible": fact(snap.observation)})
    assert verdict("target_visible", snap).status == "UNKNOWN"


def test_release_does_not_prove_placement():
    snap = evidence(state=RobotState(connected=True, gripper_open=True, holding_object_id=None))
    assert verdict("gripper_released", snap).status == "PASS"
    assert verdict("object_placed", snap).status == "UNKNOWN"
    snap = replace(snap, visual_facts={"object_inside_target_region": fact(snap.observation)})
    assert verdict("object_placed", snap).status == "PASS"


def test_skill_completed_marker_needs_effect_evidence():
    snap = evidence()
    assert verdict("skill_grasp_completed", snap).status == "UNKNOWN"
    snap = replace(snap, visual_facts={"object_held": fact(snap.observation)})
    assert (
        verdict(
            "skill_grasp_completed", snap, tolerances={"effect_condition": "object_held"}
        ).status
        == "PASS"
    )


def test_timestamp_freshness_and_calibration_requirements_fail_closed():
    snap = evidence()
    for captured_at in [
        datetime.now(),
        datetime.now(UTC) + timedelta(days=1),
        datetime.now(UTC) - timedelta(days=1),
    ]:
        obs = snap.observation.model_copy(update={"captured_at": captured_at})
        current = replace(snap, observation=obs, visual_facts={"target_visible": fact(obs)})
        assert verdict("target_visible", current).status == "UNKNOWN"
    current = replace(snap, visual_facts={"target_visible": fact(snap.observation)})
    assert (
        verdict(
            "target_visible", current, tolerances={"calibration_version": "new-calibration"}
        ).status
        == "UNKNOWN"
    )


def routing(status="UNKNOWN", *, max_reobservations=2, max_retries=2, max_no_progress=5):
    conditions = import_module("cloud_edge_robot_arm.edge.evidence.conditions")
    router = import_module("cloud_edge_robot_arm.edge.recovery.verification_router")
    events = import_module("cloud_edge_robot_arm.auto_mode.runtime_events")
    limits = router.VerificationBudget(max_reobservations, max_retries, max_no_progress, 60.0)
    budget = router.VerificationBudgetState.start(limits)
    result = conditions.ConditionVerdict(status, "target_visible", "frame-1")
    return router, events.DecisionAction, budget, result


def test_final_unknown_reobserves_without_completing():
    router, action, budget, result = routing()
    assert router.route_verification([result], budget, set(action)) == action.REOBSERVE
    assert budget.remaining_reobservations == 1
    assert router.route_verification([], budget, {action.CONTINUE}) == action.STOP


def test_verification_fail_routes_before_terminal_failure():
    router, action, budget, result = routing("FAIL")
    assert router.route_verification([result], budget, set(action)) == action.LOCAL_RECOVER
    assert budget.remaining_retries == 1


def test_missing_recovery_capability_is_not_selected():
    router, action, budget, result = routing("FAIL")
    assert router.route_verification([result], budget, {action.STOP}) == action.STOP
    assert budget.remaining_retries == 2
    _, _, budget, _ = routing("FAIL")
    assert (
        router.route_verification([result], budget, {action.REQUEST_CLOUD}) == action.REQUEST_CLOUD
    )


def test_reobserve_budget_exhaustion_terminates():
    router, action, budget, result = routing()
    assert [router.route_verification([result], budget, {action.REOBSERVE}) for _ in range(3)] == [
        action.REOBSERVE,
        action.REOBSERVE,
        action.STOP,
    ]
    assert budget.remaining_reobservations == 0


def test_retry_budget_and_wall_clock_deadline_are_enforced():
    router, action, budget, result = routing("FAIL", max_retries=1)
    assert router.route_verification([result], budget, set(action)) == action.LOCAL_RECOVER
    assert router.route_verification([result], budget, set(action)) == action.STOP
    _, _, budget, _ = routing()
    budget.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
    assert router.route_verification([result], budget, set(action)) == action.STOP


def test_new_frame_or_confidence_cannot_reset_no_progress_budget():
    router, action, budget, result = routing(max_reobservations=10, max_no_progress=2)
    choices = []
    for number in range(4):
        current = replace(
            result, observation_id=f"frame-{number}", measured_values={"confidence": number / 10}
        )
        choices.append(router.route_verification([current], budget, set(action)))
    assert choices == [action.REOBSERVE, action.REOBSERVE, action.STOP, action.STOP]
    assert budget.remaining_reobservations == 8


def test_verified_improvement_resets_only_no_progress_not_spent_allowances():
    router, action, budget, result = routing(max_reobservations=5, max_no_progress=3)
    router.route_verification([result], budget, set(action))
    router.route_verification([result], budget, set(action))
    assert budget.consecutive_no_progress == 1
    improved = replace(result, status="FAIL")
    assert router.route_verification([improved], budget, set(action)) == action.LOCAL_RECOVER
    assert budget.consecutive_no_progress == 0
    assert budget.remaining_reobservations == 3
    assert budget.remaining_retries == 1


def test_oracle_outcome_cannot_change_online_routing():
    router, action, budget, _ = routing()
    snap = evidence()
    snap = replace(
        snap,
        visual_facts={
            "object_inside_target_region": fact(snap.observation, source="physical_evaluator")
        },
    )
    result = verdict("object_inside_target_region", snap)
    assert router.route_verification([result], budget, set(action)) == action.REOBSERVE


@pytest.mark.parametrize(
    "args",
    [
        (-1, 1, 1, 1),
        (1, -1, 1, 1),
        (1, 1, -1, 1),
        (1, 1, 1, 0),
        (1.5, 1, 1, 1),
        (True, 1, 1, 1),
        (1, 1, 1, float("inf")),
    ],
)
def test_invalid_verification_budgets_are_rejected(args):
    router = import_module("cloud_edge_robot_arm.edge.recovery.verification_router")
    with pytest.raises(ValueError):
        router.VerificationBudget(*args)


def test_completion_missing_timestamp_cannot_pass():
    from cloud_edge_robot_arm.edge.completion_evaluator import CompletionEvaluator
    from tests.test_phase6_e2e_executor import _event_contract

    contract = _event_contract()
    result = CompletionEvaluator().evaluate(
        contract=contract,
        completed_step_ids=[step.step_id for step in contract.steps],
        completion_criteria_results={"object_placed": True},
        final_safety_decision="ALLOW",
        final_robot_state={"connected": True, "holding_object_id": None},
        final_target_state={"object_at_target": True},
    )
    assert not result.completed
    assert "CHECK_7_SCENE_TIMESTAMP_MISSING" in result.failed_checks


def test_proprioceptive_motion_and_grasp_checks_verify_effect():
    snap = evidence(
        state=RobotState(
            connected=True,
            tcp_pose=Pose(x=0.2, y=0.3, z=0.4),
            gripper_open=False,
            holding_object_id="cube",
        )
    )
    assert verdict("gripper_holding", snap).status == "PASS"
    target = {"target_x": 0.2, "target_y": 0.3, "target_z": 0.4, "max_distance_m": 0.015}
    assert verdict("tcp_at_resolved_target", snap, tolerances=target).status == "PASS"
    far = replace(
        snap,
        robot_state=snap.robot_state.model_copy(
            update={"tcp_pose": Pose(x=0.2, y=0.3, z=0.5), "holding_object_id": None}
        ),
    )
    assert verdict("gripper_holding", far).status == "FAIL"
    assert verdict("tcp_at_resolved_target", far, tolerances=target).status == "FAIL"
    assert verdict("tcp_at_resolved_target", snap).status == "UNKNOWN"


def test_unknown_fail_oscillation_is_not_repeated_progress():
    router, action, budget, result = routing(
        max_reobservations=10, max_retries=10, max_no_progress=2
    )
    choices = [
        router.route_verification([replace(result, status=status)], budget, set(action))
        for status in ["UNKNOWN", "FAIL", "UNKNOWN", "FAIL"]
    ]
    assert choices == [action.REOBSERVE, action.LOCAL_RECOVER, action.REOBSERVE, action.STOP]


def test_hard_safety_fault_stops_even_when_other_conditions_are_unknown():
    router, action, budget, result = routing()
    unsafe = replace(
        result,
        condition_name="robot_safe",
        status="FAIL",
        measured_values={"hard_safety_fault": True},
    )
    assert router.route_verification([result, unsafe], budget, set(action)) == action.STOP
    assert budget.remaining_reobservations == 2


def test_runtime_condition_evaluator_requires_evidence_by_default():
    from cloud_edge_robot_arm.edge.runtime.condition_evaluator import ConditionEvaluator
    from tests.test_phase6_e2e_executor import _event_contract

    class Robot:
        def get_state(self):
            return RobotState(connected=True, tcp_pose=Pose(x=0, y=0, z=10))

    strict = ConditionEvaluator()
    result = strict.evaluate_preconditions(
        robot=Robot(), contract=_event_contract(), conditions=["target_visible"]
    )
    assert not result.success
    assert result.status == "UNKNOWN"
    legacy = ConditionEvaluator(evaluation_scope="LEGACY_PIPELINE")
    assert legacy.evaluate_preconditions(
        robot=Robot(), contract=_event_contract(), conditions=["target_visible"]
    ).success


def test_missing_verdicts_still_spend_no_progress_budget():
    router, action, budget, _ = routing(max_reobservations=10, max_no_progress=2)
    choices = [router.route_verification([], budget, set(action)) for _ in range(3)]
    assert choices == [action.REOBSERVE, action.REOBSERVE, action.STOP]
    assert budget.exhausted_reason == "no_progress_exhausted"


def test_retry_exhaustion_is_terminal_even_if_later_call_claims_pass():
    router, action, budget, result = routing("FAIL", max_retries=0)
    assert router.route_verification([result], budget, set(action)) == action.STOP
    assert (
        router.route_verification([replace(result, status="PASS")], budget, set(action))
        == action.STOP
    )


def test_budget_reconstruction_preserves_deadline_and_consumption():
    router, action, budget, result = routing(max_reobservations=2)
    assert router.route_verification([result], budget, set(action)) == action.REOBSERVE
    restored = replace(budget)
    assert restored.deadline_at == budget.deadline_at
    assert router.route_verification([result], restored, set(action)) == action.REOBSERVE
    assert router.route_verification([result], restored, set(action)) == action.STOP


def test_event_preserves_online_verification_identity():
    events = import_module("cloud_edge_robot_arm.auto_mode.runtime_events")
    event = events.DecisionEvent(
        "event-1", "VERIFICATION_FAILED", datetime.now(UTC), "frame-1", False, "UNKNOWN"
    )
    assert event.kind == events.DecisionEventKind.VERIFICATION_FAILED
    assert event.observation_id == "frame-1"
    assert event.verification_status == "UNKNOWN"
    with pytest.raises(ValueError):
        replace(event, occurred_at=datetime.now())
