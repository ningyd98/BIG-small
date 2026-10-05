"""Candidate repair changes scope, never executes or resolves an event."""

from dataclasses import replace
from datetime import timedelta
from importlib import import_module

import pytest

from cloud_edge_robot_arm.cloud.replanning.visual_dependencies import StepDependency
from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec
from tests.test_replan_activation import NOW, setup_replan
from tests.test_visual_evidence_contract import online_evidence


def api():
    return import_module("cloud_edge_robot_arm.cloud.replanning.visual_repair")


def fixture():
    from cloud_edge_robot_arm.contracts.models import SkillName, TaskStep
    from cloud_edge_robot_arm.repositories.event_autonomy.memory import (
        InMemoryEventAutonomyRepository,
    )
    repo = InMemoryEventAutonomyRepository()
    request, _ = setup_replan(repo)
    contract = repo.get_active_contract("task").contract
    completed = contract.steps[0].model_copy(update={"success_conditions": ["target_visible"]})
    pending = contract.steps[1]
    unrelated = TaskStep(step_id="telemetry", skill=SkillName.VERIFY_RESULT, parameters={},
                         expected_duration_ms=100, timeout_ms=1000, retry_limit=0)
    contract = contract.model_copy(update={"steps": [completed, pending, unrelated]}, deep=True)
    checkpoint = repo.get_latest_execution_checkpoint("task")
    online = online_evidence()
    observation = type(online.observation).model_validate({
        **online.observation.model_dump(), "captured_at": NOW + timedelta(seconds=.1),
        "episode_id": "episode", "checksum_sha256": "",
    })
    facts = {"target_visible": {**online.visual_facts["target_visible"],
                               "target_id": "obj-1"}}
    online = replace(online, observation=observation, plan_version=1, command_seq=1,
                     visual_facts=facts)
    graph = (StepDependency("approach", (), ("old",), "approach-effect", True),
             StepDependency("grasp", ("approach",), ("lost",), "grasp-effect", False),
             StepDependency("telemetry", (), (), None, False))
    context = api().VisualRepairContext(
        contract, checkpoint, graph, frozenset({"lost"}), online,
        {"approach": (ConditionSpec("target_visible", "obj-1"),)},
    )
    window = api().repair_window(context)
    return request, context, window, observation


def provider(request, window, observation, context):
    del request, observation
    originals = {step.step_id: step for step in context.active_contract.steps}
    return api().RepairProposal({
        identity: originals[identity].model_copy(update={"step_id": f"repair-{identity}"},
                                               deep=True)
        for identity in window.replace_step_ids
    })


def build(values=None, **kwargs):
    request, context, window, observation = values or fixture()
    return api().build_visual_repair(request, window, observation, context=context,
                                    provider=provider, clock=lambda: NOW + timedelta(seconds=.2),
                                    **kwargs)


def test_minimal_repair_retains_unrelated_pending_and_completed_effects():
    request, context, window, observation = fixture()
    result = build((request, context, window, observation))
    assert result.outcome == "REPLANNED"
    assert [step.step_id for step in result.new_steps] == ["repair-grasp", "telemetry"]
    assert result.new_steps[1].model_dump() == context.active_contract.steps[2].model_dump()
    assert result.new_plan_version == 2 and result.new_command_seq == 2
    assert "approach" not in [step.step_id for step in result.new_steps]


def test_full_remaining_uses_same_failure_and_observation_but_expands_scope():
    values = fixture()
    seen = []
    def record(request, window, observation, context):
        seen.append((request.trigger_event_id, observation.checksum_sha256,
                     tuple(window.replace_step_ids)))
        return provider(request, window, observation, context)
    request, context, window, observation = values
    for full in (False, True):
        result = api().build_visual_repair(request, window, observation, context=context,
                                          provider=record, full_remaining=full,
                                          clock=lambda: NOW + timedelta(seconds=.2))
        assert result.outcome == "REPLANNED"
    assert seen[0][:2] == seen[1][:2]
    assert seen[0][2] == ("grasp",) and seen[1][2] == ("grasp", "telemetry")


@pytest.mark.parametrize("change", ["version", "command", "window", "complete", "graph"])
def test_stale_or_forged_context_cannot_plan(change):
    request, context, window, observation = fixture()
    if change in {"version", "command"}:
        request = request.model_copy(update={
            "current_plan_version" if change == "version" else "current_command_seq": 8})
    elif change == "window":
        window = replace(window, replace_step_ids=("grasp", "telemetry"),
                         preserved_step_ids=("approach",))
    elif change == "complete":
        request = request.model_copy(update={"completed_step_ids": []})
    else:
        context = replace(context, dependencies=context.dependencies[:-1])
    result = build((request, context, window, observation))
    assert result.outcome != "REPLANNED" and not result.new_steps


@pytest.mark.parametrize("change", ["old", "future", "different", "unknown", "fail", "decoy"])
def test_completed_effect_requires_current_exact_canonical_pass(change):
    request, context, window, observation = fixture()
    if change in {"old", "future"}:
        observation = type(observation).model_validate({
            **observation.model_dump(), "captured_at": NOW + timedelta(
                seconds=-1 if change == "old" else 1), "checksum_sha256": ""})
        context = replace(context, online_evidence=replace(context.online_evidence,
                                                           observation=observation))
    elif change == "different":
        observation = type(observation).model_validate({
            **observation.model_dump(), "frame_id": "another", "observation_id": "",
            "checksum_sha256": ""})
    else:
        facts = dict(context.online_evidence.visual_facts)
        facts["target_visible"] = {**facts["target_visible"],
                                    **({"value": False} if change == "fail" else
                                       {"target_id": "decoy"} if change == "decoy" else
                                       {"source": "oracle"})}
        context = replace(context, online_evidence=replace(context.online_evidence,
                                                           visual_facts=facts))
    result = build((request, context, window, observation))
    assert result.outcome != "REPLANNED" and result.new_steps == []


def test_missing_provider_or_context_produces_no_executable_candidate():
    request, _, window, observation = fixture()
    result = api().build_visual_repair(request, window, observation)
    assert result.outcome == "MORE_OBSERVATION_REQUIRED" and not result.new_steps


@pytest.mark.parametrize("change", ["omit", "extra", "replay", "low_level", "precondition"])
def test_provider_cannot_change_unrelated_steps_or_replay_completed_effect(change):
    request, context, window, observation = fixture()
    def bad(request, window, observation, context):
        replacements = dict(provider(request, window, observation, context).replacements)
        if change == "omit":
            replacements.clear()
        elif change == "extra":
            replacements["telemetry"] = context.active_contract.steps[2]
        else:
            update = ({"step_id": "approach"} if change == "replay" else
                      {"parameters": {"force_execute": True}} if change == "low_level" else
                      {"preconditions": []})
            replacements["grasp"] = replacements["grasp"].model_copy(update=update, deep=True)
        return api().RepairProposal(replacements)
    context.active_contract.steps[1].preconditions.append("target_visible")
    result = api().build_visual_repair(request, window, observation, context=context,
                                      provider=bad, clock=lambda: NOW + timedelta(seconds=.2))
    assert result.outcome != "REPLANNED" and not result.new_steps


def test_provider_cannot_mutate_request_or_context():
    request, context, window, observation = fixture()
    original_request = request.model_dump()
    original_contract = context.active_contract.model_dump()
    def bad(request, window, observation, context):
        proposal = provider(request, window, observation, context)
        request.current_plan_version = 99
        context.active_contract.steps[2].parameters["mutation"] = True
        return proposal
    result = api().build_visual_repair(request, window, observation, context=context,
                                      provider=bad, clock=lambda: NOW + timedelta(seconds=.2))
    assert result.outcome != "REPLANNED" and not result.new_steps
    assert request.model_dump() == original_request
    assert context.active_contract.model_dump() == original_contract


def test_late_provider_return_cannot_use_old_frame_or_expired_contract():
    request, context, window, observation = fixture()
    clock = [NOW + timedelta(seconds=.2)]
    def slow(*args):
        result = provider(*args)
        clock[0] = NOW + timedelta(seconds=61)
        return result
    result = api().build_visual_repair(request, window, observation, context=context,
                                      provider=slow, clock=lambda: clock[0])
    assert result.outcome != "REPLANNED" and result.new_steps == []


def test_provider_exception_does_not_create_a_fallback_action():
    request, context, window, observation = fixture()
    def failed(*args):
        raise TimeoutError("SOFTWARE_FIXTURE")
    result = api().build_visual_repair(request, window, observation, context=context,
                                      provider=failed, clock=lambda: NOW + timedelta(seconds=.2))
    assert result.outcome == "PLANNER_FAILED" and result.new_steps == []
