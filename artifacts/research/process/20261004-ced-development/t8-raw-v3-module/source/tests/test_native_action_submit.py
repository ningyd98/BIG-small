"""Native RGB-D claims cannot replace independently supported action bounds."""

from dataclasses import replace
from datetime import UTC, datetime
from importlib import import_module
from types import SimpleNamespace

import pytest

from cloud_edge_robot_arm.edge.evidence.validator import validate_evidence
from tests.test_phase6_2_replan_resume import _contract
from tests.test_visual_evidence_contract import online_evidence


def sample():
    online = online_evidence()
    observation = type(online.observation).model_validate({
        **online.observation.model_dump(), "captured_at": datetime.now(UTC),
        "episode_id": "episode", "checksum_sha256": "",
    })
    contract = _contract(task_id="task")
    facts = {"target_visible": {**online.visual_facts["target_visible"],
                               "target_id": contract.task_target.object_id},
             "depth_error_bound_m": 0.000001, "motion_bound_m_s": 0.000001,
             "calibration_verified": True, "bound_proof": {"status": "VALID"}}
    online = replace(online, observation=observation, visual_facts=facts,
                     plan_version=contract.plan_version, command_seq=contract.command_seq,
                     context_hash="frozen-role-bundle")
    return online, contract, contract.steps[1]


def api():
    return import_module("cloud_edge_robot_arm.vision.action_evidence")


def test_unsupported_native_bounds_stay_unknown_despite_claimed_valid():
    online, contract, step = sample()
    action = api().native_action_contract(online, contract, step)
    assert action.evidence.geometric_error_bound_m is None
    assert action.evidence.motion_bound_m_s is None
    verdict = validate_evidence(action, datetime.now(UTC), online.context_hash,
                                online.observation.calibration_version, online_evidence=online)
    assert verdict.status == "UNKNOWN"


def test_action_end_bound_uses_full_timeout_and_exact_current_versions():
    online, contract, step = sample()
    step = step.model_copy(update={"expected_duration_ms": 10, "timeout_ms": 7000})
    action = api().native_action_contract(online, contract, step)
    assert action.expected_duration_s == 7
    assert (action.plan_version, action.command_seq) == (
        contract.plan_version, contract.command_seq)
    assert action.context_hash == "frozen-role-bundle"


def test_region_tcp_spec_and_object_extent_spec_have_distinct_targets():
    online, contract, step = sample()
    step = step.model_copy(update={"preconditions": ["tcp_above_region",
                                                     "object_inside_target_region"]})
    action = api().native_action_contract(online, contract, step)
    assert [spec.target_id for spec in action.preconditions] == [
        contract.task_target.target_region_id, contract.task_target.object_id]


@pytest.mark.parametrize("change", ["decoy", "oracle", "false", "frame", "identity"])
def test_identity_is_derived_from_exact_native_frame_fact(change):
    online, contract, step = sample()
    facts = dict(online.visual_facts)
    fact = dict(facts["target_visible"])
    fact.update({"target_id": "decoy"} if change == "decoy" else
                {"source": "oracle"} if change == "oracle" else
                {"value": False} if change == "false" else
                {"observation_id": "old"} if change == "frame" else
                {"identity_confirmed": False})
    facts["target_visible"] = fact
    action = api().native_action_contract(replace(online, visual_facts=facts), contract, step)
    assert action.evidence.identity_status == "UNKNOWN"


def test_native_gate_is_called_before_safety_and_skill_and_cannot_dispatch_unknown():
    from cloud_edge_robot_arm.vision.execution import _EpisodeStopped, _VisualEpisode
    online, contract, step = sample()
    episode = _VisualEpisode.__new__(_VisualEpisode)
    episode.policy = SimpleNamespace(device_pipeline="OPENCV",
                                     role_binding=SimpleNamespace(
                                         bundle=SimpleNamespace(
                                             digest=lambda: online.context_hash)))
    episode.observation = online.observation
    episode.robot = SimpleNamespace(get_state=lambda: online.robot_state)
    episode.tracker = SimpleNamespace(facts=lambda *args: online.visual_facts)
    episode.check_active = lambda: None
    episode.validate_role_boundary = lambda: None
    episode.records = []
    episode.route = lambda *args, **kwargs: "STOP"
    touched = []
    episode.shield = SimpleNamespace(pre_check=lambda *args: touched.append("safety"))
    episode.executor = SimpleNamespace(execute_attempt=lambda **kwargs: touched.append("skill"))
    with pytest.raises(_EpisodeStopped, match="ACTION_EVIDENCE"):
        episode.execute(contract, step)
    assert touched == []
    gate = [row for row in episode.records if row.get("layer") == "ACTION_EVIDENCE_GATE"]
    assert gate and gate[0]["status"] == "UNKNOWN"
    assert gate[0]["boundary"] == "PRE_SAFETY"


def test_post_safety_gate_cannot_recapture_and_reuse_old_safety_context():
    from cloud_edge_robot_arm.auto_mode.runtime_events import DecisionAction
    from cloud_edge_robot_arm.vision.execution import _EpisodeStopped, _VisualEpisode
    online, contract, step = sample()
    episode = _VisualEpisode.__new__(_VisualEpisode)
    episode.policy = SimpleNamespace(device_pipeline="OPENCV",
                                     role_binding=SimpleNamespace(bundle=SimpleNamespace(
                                         digest=lambda: "role-bundle")))
    episode.observation = online.observation
    episode.robot = SimpleNamespace(get_state=lambda: online.robot_state)
    episode.tracker = SimpleNamespace(facts=lambda *args: online.visual_facts)
    episode.check_active = lambda: None
    episode.validate_role_boundary = lambda: None
    episode.records = []
    routed = iter((DecisionAction.REOBSERVE, DecisionAction.STOP))
    episode.route = lambda *args, **kwargs: next(routed)
    touched = []
    episode.backend = SimpleNamespace(step=lambda **kwargs: touched.append("physics"))
    episode.recapture = lambda: touched.append("recapture")
    with pytest.raises(_EpisodeStopped, match="POST_SAFETY"):
        episode.require_native_action_evidence(contract, step, boundary="PRE_SKILL")
    assert touched == []


@pytest.mark.parametrize("flag", ["estop_engaged", "collision_detected", "connected"])
def test_hard_stop_cannot_be_masked_by_unknown_evidence_or_reobserve(flag):
    from cloud_edge_robot_arm.auto_mode.runtime_events import DecisionAction
    from cloud_edge_robot_arm.vision.execution import _EpisodeStopped, _VisualEpisode
    online, contract, step = sample()
    state = online.robot_state.model_copy(update={flag: flag != "connected"})
    episode = _VisualEpisode.__new__(_VisualEpisode)
    episode.policy = SimpleNamespace(device_pipeline="OPENCV", role_binding=SimpleNamespace(
        bundle=SimpleNamespace(digest=lambda: "role-bundle")))
    episode.observation = online.observation
    episode.robot = SimpleNamespace(get_state=lambda: state)
    episode.tracker = SimpleNamespace(facts=lambda *args: online.visual_facts)
    episode.check_active = lambda: None
    episode.validate_role_boundary = lambda: None
    episode.records = []
    touched = []
    def route(*args, **kwargs):
        touched.append("route-budget")
        return (DecisionAction.REOBSERVE if touched.count("route-budget") == 1
                else DecisionAction.STOP)
    episode.route = route
    episode.backend = SimpleNamespace(step=lambda **kwargs: touched.append("physics"))
    episode.recapture = lambda: touched.append("recapture")
    # An immediate fault must stop before even a passive backend step.
    with pytest.raises(_EpisodeStopped, match="HARD_SAFETY"):
        episode.require_native_action_evidence(contract, step, boundary="PRE_SAFETY")
    assert touched == []


def test_new_hard_fault_after_route_stops_before_passive_physics_step():
    from cloud_edge_robot_arm.auto_mode.runtime_events import DecisionAction
    from cloud_edge_robot_arm.vision.execution import _EpisodeStopped, _VisualEpisode
    online, contract, step = sample()
    states = [online.robot_state]
    episode = _VisualEpisode.__new__(_VisualEpisode)
    episode.policy = SimpleNamespace(device_pipeline="OPENCV", role_binding=SimpleNamespace(
        bundle=SimpleNamespace(digest=lambda: "role-bundle")))
    episode.observation = online.observation
    episode.robot = SimpleNamespace(get_state=lambda: states[0])
    episode.tracker = SimpleNamespace(facts=lambda *args: online.visual_facts)
    episode.check_active = lambda: None
    episode.validate_role_boundary = lambda: None
    episode.records = []
    def route(*args, **kwargs):
        states[0] = states[0].model_copy(update={"estop_engaged": True})
        return DecisionAction.REOBSERVE
    episode.route = route
    touched = []
    episode.backend = SimpleNamespace(step=lambda **kwargs: touched.append("physics"))
    episode.recapture = lambda: touched.append("recapture")
    with pytest.raises(_EpisodeStopped, match="HARD_SAFETY"):
        episode.require_native_action_evidence(contract, step, boundary="PRE_SAFETY")
    assert touched == []
