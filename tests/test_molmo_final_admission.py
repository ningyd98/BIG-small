"""最终合同及缓存出口的新帧准入回归；全部为 CPU 夹具。"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

import cloud_edge_robot_arm.cloud.planning.pipeline as pipeline_module
from cloud_edge_robot_arm.cloud.planning.models import PlannerDraft
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
from tests.test_molmo_grounded_planner import adapter_fixture, refresh_fixture, request_scene
from tests.test_molmo_revalidation import rebuild


def assert_counts(state, *, count=1):
    assert len(state.calls) == count
    assert len(state.queries) == 4 * count
    assert len(state.captures) == count


def assert_rejected(response, *, phase, reason=None):
    assert response.outcome == "REQUEST_MORE_OBSERVATION"
    assert response.contract is None and response.dispatch is None
    assert not response.validation.passed
    attempt = response.attempts[-1]
    assert not attempt.validation.passed
    assert attempt.draft.observation_evidence["post_cloud_revalidation"]["status"] == "PASSED"
    terminal = attempt.draft.observation_evidence["final_plan_admission"]
    assert terminal["status"] == "REJECTED" and terminal["phase"] == phase
    assert response.validation.errors[-1]["field"] == "final_plan_admission"
    if reason:
        assert response.reason == reason == terminal["reason"]


@pytest.mark.parametrize("stage", ["build", "semantic", "trusted-prefill", "trusted-final"])
def test_actual_pipeline_stages_cannot_return_a_contract_after_fresh_ttl(monkeypatch, stage):
    state = refresh_fixture(monkeypatch)
    name = {
        "build": "build_task_contract",
        "semantic": "semantic_validate",
        "trusted-prefill": "complete_trusted_fields",
        "trusted-final": "complete_trusted_fields",
    }[stage]
    original = getattr(pipeline_module, name)
    calls = 0

    def delayed(*args, **kwargs):
        nonlocal calls
        result = original(*args, **kwargs)
        calls += 1
        if stage in {"build", "semantic"} or calls == (1 if stage.endswith("prefill") else 2):
            state.clock += timedelta(seconds=6)
        return result

    monkeypatch.setattr(pipeline_module, name, delayed)
    response = PlanningPipeline(planner=state.adapter).process(state.request)
    assert_rejected(response, phase="final_contract", reason="capture_time_not_fresh")
    assert state.request.model_dump_json() == state.original_json
    assert_counts(state)


@pytest.mark.parametrize("phase", ["final_contract", "cache_hit"])
@pytest.mark.parametrize(
    "age,passed", [(5.0, True), (-0.05, True), (5.000001, False), (-0.050001, False)]
)
def test_final_age_boundaries_use_fixed_fresh_capture(monkeypatch, phase, age, passed):
    state = refresh_fixture(monkeypatch)
    pipeline = PlanningPipeline(planner=state.adapter)
    if phase == "final_contract":
        original = pipeline_module.build_task_contract

        def delayed(*args, **kwargs):
            result = original(*args, **kwargs)
            state.clock = state.captures[0].captured_at + timedelta(seconds=age)
            return result

        monkeypatch.setattr(pipeline_module, "build_task_contract", delayed)
    else:
        first = pipeline.process(state.request)
        assert first.outcome == "PLANNED"
        original_json = first.model_dump_json()
        state.clock = state.captures[0].captured_at + timedelta(seconds=age)
    response = pipeline.process(state.request)
    if passed:
        assert response.outcome == "PLANNED" and response.contract is not None
        terminal = response.attempts[0].draft.observation_evidence["final_plan_admission"]
        assert terminal == {"status": "PASSED", "phase": "final_contract"}
        if phase == "cache_hit":
            assert response is first and response.model_dump_json() == original_json
    else:
        assert_rejected(response, phase=phase, reason="capture_time_not_fresh")
        if phase == "cache_hit":
            assert response is not first and first.model_dump_json() == original_json
    assert_counts(state)


@pytest.mark.parametrize(
    "drift",
    [
        "age",
        "settings",
        "task",
        "provider",
        "supplier",
        "cloud",
        "role",
        "planner",
        "retained-request",
    ],
)
def test_cached_success_checks_bound_context_and_keeps_prior_response_immutable(monkeypatch, drift):
    state = refresh_fixture(monkeypatch)
    pipeline = PlanningPipeline(planner=state.adapter)
    first = pipeline.process(state.request)
    original_json = first.model_dump_json()
    caller = state.request.model_copy(deep=True)
    planner = state.adapter
    if drift == "age":
        state.clock += timedelta(seconds=6)
    elif drift == "settings":
        state.cloud.timeout_s += 1
    elif drift == "task":
        state.adapter.task = state.adapter.task.model_copy(update={"target_label": "blue block"})
    elif drift == "provider":
        state.adapter.point_provider = object()
    elif drift == "supplier":
        state.adapter.post_cloud_observation_supplier = None
    elif drift == "cloud":
        state.adapter.cloud = object()
    elif drift == "role":
        state.cloud.role_snapshot = SimpleNamespace(digest=lambda: "changed")
    elif drift == "planner":
        planner = object()
    else:
        state.request.user_instruction = "different retained request"
    response = pipeline.process(caller, planner=planner)
    assert_rejected(response, phase="cache_hit")
    assert response is not first and first.model_dump_json() == original_json
    assert pipeline.process(caller, planner=planner) is response
    assert_counts(state)


def test_valid_cache_uses_private_retained_guard_despite_public_evidence_edits(monkeypatch):
    state = refresh_fixture(monkeypatch)
    pipeline = PlanningPipeline(planner=state.adapter)
    first = pipeline.process(state.request)
    draft = first.attempts[0].draft
    assert callable(draft._final_plan_admission)
    draft._final_plan_admission = None
    draft.observation_evidence["captured_at"] = "forged"
    state.clock += timedelta(seconds=6)
    response = pipeline.process(state.request)
    assert_rejected(response, phase="cache_hit", reason="capture_time_not_fresh")
    assert first.contract is not None and first.outcome == "PLANNED"
    assert_counts(state)


def test_changed_same_id_request_remains_a_conflict_without_running_gate(monkeypatch):
    state = refresh_fixture(monkeypatch)
    pipeline = PlanningPipeline(planner=state.adapter)
    first = pipeline.process(state.request)
    changed = state.request.model_copy(update={"user_instruction": "another instruction"})
    response = pipeline.process(changed)
    assert response.outcome == "REJECTED" and "CONFLICT" in response.reason
    assert pipeline.process(state.request) is first
    assert_counts(state)


@pytest.mark.parametrize("mode", ["missing", "noncallable", "exception", "result", "roundtrip"])
def test_required_private_guard_failures_close_actual_final_contract(monkeypatch, mode):
    state = refresh_fixture(monkeypatch)
    original = state.adapter.plan

    def plan(request):
        draft = original(request)
        draft.observation_evidence["final_plan_admission"] = {"status": "PASSED"}
        if mode == "roundtrip":
            return PlannerDraft.model_validate_json(draft.model_dump_json())
        if mode == "exception":

            def fail(*args):
                raise RuntimeError("SECRET-MUST-NOT-APPEAR")

            value = fail
        else:
            value = {"missing": None, "noncallable": 42, "result": lambda *args: True}[mode]
        draft._final_plan_admission = value
        return draft

    monkeypatch.setattr(state.adapter, "plan", plan)
    response = PlanningPipeline(planner=state.adapter).process(state.request)
    assert_rejected(response, phase="final_contract")
    assert "SECRET-MUST-NOT-APPEAR" not in response.model_dump_json()
    assert response.attempts[0].draft._final_plan_admission is None
    assert_counts(state)


def test_guard_exception_is_consumed_once_and_negative_cache_does_not_retry(monkeypatch):
    state = refresh_fixture(monkeypatch)
    original = state.adapter.plan
    checks = []

    def plan(request):
        draft = original(request)

        def fail(*args):
            checks.append(args)
            raise RuntimeError("private failure")

        draft._final_plan_admission = fail
        return draft

    monkeypatch.setattr(state.adapter, "plan", plan)
    pipeline = PlanningPipeline(planner=state.adapter)
    first = pipeline.process(state.request)
    assert_rejected(first, phase="final_contract", reason="final_plan_admission_error:RuntimeError")
    assert pipeline.process(state.request) is first
    assert len(checks) == 1
    assert_counts(state)


def test_private_admission_is_not_in_transport_fields_or_schema(monkeypatch):
    state = refresh_fixture(monkeypatch)
    response = PlanningPipeline(planner=state.adapter).process(state.request)
    draft = response.attempts[0].draft
    assert callable(draft._final_plan_admission)
    assert "_final_plan_admission" not in PlannerDraft.model_fields
    assert "_final_plan_admission" not in str(PlannerDraft.model_json_schema())
    assert "_final_plan_admission" not in draft.model_dump_json()
    assert "_final_plan_admission" not in response.model_dump_json()
    assert PlannerDraft.model_validate_json(draft.model_dump_json())._final_plan_admission is None
    assert_counts(state)


def test_interleaved_requests_retain_each_invocations_own_fresh_binding(monkeypatch):
    state = refresh_fixture(monkeypatch)
    pipeline = PlanningPipeline(planner=state.adapter)
    first_request = state.request
    first = pipeline.process(first_request)
    second_observation = rebuild(
        first_request.observation, frame_id="second-reference", captured_at=state.clock
    )
    second_request = first_request.model_copy(
        update={"request_id": "second-invocation", "observation": second_observation}
    )
    state.request = second_request
    second = pipeline.process(second_request)
    assert first.outcome == second.outcome == "PLANNED"
    assert (
        first.attempts[0].draft._final_plan_admission
        is not second.attempts[0].draft._final_plan_admission
    )
    assert_rejected(
        pipeline.process(first_request), phase="cache_hit", reason="capture_time_not_fresh"
    )
    assert pipeline.process(second_request) is second
    assert first.contract is not None and first.outcome == "PLANNED"
    assert_counts(state, count=2)


def test_legacy_default_none_keeps_its_original_same_object_cache(monkeypatch):
    adapter, _, _ = adapter_fixture(monkeypatch)
    request = request_scene()
    pipeline = PlanningPipeline(planner=adapter)
    first = pipeline.process(request)
    assert first.outcome == "PLANNED"
    assert first.attempts[0].draft._final_plan_admission is None
    assert pipeline.process(request) is first
    assert "final_plan_admission" not in first.attempts[0].draft.observation_evidence


def test_factory_hash_inventory_includes_final_admission_sources(monkeypatch):
    import cloud_edge_robot_arm.vision.grounded_planner as module

    state = refresh_fixture(monkeypatch)
    captured = {}

    def resolve(*args, **kwargs):
        captured.update(kwargs)
        return state.cloud, None

    monkeypatch.setattr(module, "resolve_cloud_role", resolve)
    supplier = state.adapter.post_cloud_observation_supplier
    adapter = module.build_molmo_grounded_planner(
        service=object(),
        profile_id="test",
        point_provider=state.adapter.point_provider,
        task=state.adapter.task,
        grasp_profile="mujoco_upright_box_v2",
        post_cloud_observation_supplier=supplier,
    )
    assert adapter.post_cloud_observation_supplier is supplier
    for name in ["models", "pipeline"]:
        assert f"src/cloud_edge_robot_arm/cloud/planning/{name}.py" in captured["source_hashes"]
