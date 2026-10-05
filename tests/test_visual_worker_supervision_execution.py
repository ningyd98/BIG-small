"""Orchestration-only spies; durable source validation is tested separately."""

from types import SimpleNamespace

import pytest

from cloud_edge_robot_arm.contracts import RobotState
from cloud_edge_robot_arm.vision.execution import _EpisodeStopped
from tests.test_visual_worker_execution import episode
from tests.test_visual_worker_supervision_runtime import (
    configured as shared_configured,
)
from tests.test_visual_worker_supervision_runtime import (
    runtime_source as runtime_source,
)

configured = shared_configured


def supervised_episode():
    run, calls = episode()
    run.policy.supervision_period_s = 0.3
    runtime = run.worker_runtime
    runtime.source = SimpleNamespace(task_started_at=run.budget.deadline_at.replace(year=2025))
    runtime.publication = SimpleNamespace(
        state_generation=7,
        checkpoint=SimpleNamespace(current_step_id="approach", completed_step_ids=[]),
        digest=lambda: "b" * 64,
    )
    runtime.supervision_source_publication = runtime.publication
    runtime.classify_supervision_reply = lambda frame: "CURRENT"
    runtime.original = SimpleNamespace(
        contract=SimpleNamespace(
            plan_version=1,
            steps=[SimpleNamespace(step_id="approach", skill=SimpleNamespace(value="APPROACH"))],
        )
    )
    run._active_step_id, run._active_skill = "approach", "APPROACH"
    run._plan_version, run._state_version = 1, 2
    run._worker_supervision_frames = {}
    claim = SimpleNamespace(claim_id="c" * 64)
    runtime.reserve_supervision_capture = (
        lambda *args: calls.append("reserve_tick_capture") or claim
    )
    captured = {}

    def complete(_claim, observation, context, state):
        calls.append("complete_tick_capture")
        captured.update(observation=observation, context=context)

    runtime.complete_supervision_capture = complete
    runtime.reserve_supervision_plan = lambda *args: calls.append(
        "reserve_tick_plan"
    ) or SimpleNamespace(claim_id=claim.claim_id, publication_hash="b" * 64, **captured)
    return run, calls


def test_supervision_capture_and_plan_are_claimed_on_owner_before_provider():
    run, calls = supervised_episode()
    frame = run.capture_supervision_frame()
    assert calls.index("reserve_tick_capture") < calls.index("capture")
    assert (
        calls.index("capture")
        < calls.index("complete_tick_capture")
        < calls.index("reserve_tick_plan")
    )
    assert frame.context.state_version == 7
    assert run._worker_supervision_frames[frame.claim_id] is frame


def test_missing_periodic_capture_claim_prevents_camera_read():
    run, calls = supervised_episode()

    def denied(*_args):
        raise ValueError("lost pending source claim")

    run.worker_runtime.reserve_supervision_capture = denied
    with pytest.raises(_EpisodeStopped, match="WORKER_RUNTIME"):
        run.capture_supervision_frame()
    assert "capture" not in calls


def test_initial_plan_wait_checks_owned_claim_and_records_wait_purpose():
    from contextlib import contextmanager

    run, calls = episode()
    run._worker_plan_wait_claim = "owned-plan-claim"
    run.worker_runtime.assert_owned_plan_wait = lambda claim, state: calls.append("validate_wait")
    run.backend.step = lambda steps: calls.append(("passive_wait_steps", steps))

    @contextmanager
    def purpose(name):
        calls.append(("begin_purpose", name))
        yield
        calls.append(("end_purpose", name))

    run.policy.raw_recorder = SimpleNamespace(purpose=purpose)
    run._advance_wait_steps(2)
    assert calls.index("validate_wait") < calls.index(("passive_wait_steps", 2))
    assert ("begin_purpose", "WAIT") in calls and ("end_purpose", "WAIT") in calls
    assert calls.count("validate_wait") == 2


def test_missing_owned_plan_wait_claim_stops_before_physics():
    run, calls = episode()
    run.backend.step = lambda steps: calls.append("physics")
    with pytest.raises(_EpisodeStopped, match="WORKER_WAIT_SOURCE_MISSING"):
        run._advance_wait_steps(2)
    assert "physics" not in calls


def test_supervisor_provider_uses_owned_frame_without_backend_access():
    from cloud_edge_robot_arm.vision.supervision import SupervisionDecision

    run, calls = supervised_episode()
    frame = run.capture_supervision_frame()
    run.supervision = SimpleNamespace(snapshot=lambda: {"closed": False})
    run.robot.get_state = lambda: (_ for _ in ()).throw(AssertionError("provider read backend"))
    run.worker_runtime.assert_supervision_plan_pending = lambda owned: calls.append(
        "check_pending_plan"
    )
    decision = SupervisionDecision(
        episode_id=frame.context.episode_id,
        plan_version=frame.context.plan_version,
        state_version=frame.context.state_version,
        observation_id=frame.observation.observation_id,
        next_step_id=frame.context.next_step_id,
        recommendation="CONTINUE",
        reason="software fixture",
    )
    run.planner = SimpleNamespace(
        base_url="software-supervisor-only", supervise=lambda *args: decision
    )
    response = run.supervise_frame(frame)
    assert calls.count("check_pending_plan") == 2
    assert response["worker_claim_id"] == frame.claim_id


@pytest.mark.parametrize("stale", [False, True])
def test_supervision_result_completed_once_or_stopped_when_source_changed(stale):
    from cloud_edge_robot_arm.vision.supervision import SupervisionDecision

    run, calls = supervised_episode()
    frame = run.capture_supervision_frame()
    run.observation = frame.observation
    decision = SupervisionDecision(
        episode_id=frame.context.episode_id,
        plan_version=frame.context.plan_version,
        state_version=frame.context.state_version,
        observation_id=frame.observation.observation_id,
        next_step_id=frame.context.next_step_id,
        recommendation="CONTINUE",
        reason="software fixture",
    )
    response = {
        "episode_id": frame.observation.episode_id,
        "captured_at": frame.observation.captured_at,
        "context": frame.context.model_dump(mode="json"),
        "decision": decision.model_dump(mode="json"),
        "worker_claim_id": frame.claim_id,
    }
    run.supervision = SimpleNamespace(poll=lambda **kwargs: [response])
    run.worker_runtime.complete_supervision_plan = lambda *args: calls.append("complete_tick_plan")
    if stale:
        run.worker_runtime.publication.digest = lambda: "changed-source"
    if stale:
        with pytest.raises(_EpisodeStopped, match="WORKER_SUPERVISION_SOURCE_CHANGED"):
            run.apply_supervision()
    else:
        run.apply_supervision()
    assert calls.count("complete_tick_plan") == int(not stale)
    assert frame.claim_id not in run._worker_supervision_frames


def test_changed_supervisor_wire_context_stops_instead_of_discarding_as_old_state():
    from cloud_edge_robot_arm.vision.supervision import SupervisionDecision

    run, calls = supervised_episode()
    frame = run.capture_supervision_frame()
    run.observation = frame.observation
    changed = frame.context.model_copy(update={"state_version": 6})
    decision = SupervisionDecision(
        episode_id=changed.episode_id,
        plan_version=changed.plan_version,
        state_version=changed.state_version,
        observation_id=changed.observation_id,
        next_step_id=changed.next_step_id,
        recommendation="CONTINUE",
        reason="SOFTWARE_ONLY",
    )
    response = {
        "episode_id": changed.episode_id,
        "captured_at": changed.captured_at,
        "context": changed.model_dump(mode="json"),
        "decision": decision.model_dump(mode="json"),
        "worker_claim_id": frame.claim_id,
    }
    run.supervision = SimpleNamespace(poll=lambda **kwargs: [response])
    with pytest.raises(_EpisodeStopped, match="WORKER_SUPERVISION_CONTEXT_CHANGED"):
        run.apply_supervision()
    assert "complete_tick_plan" not in calls


@pytest.mark.parametrize("second_classification", ["EXPIRED", "CURRENT"])
def test_discard_rechecks_ttl_before_recording_its_owned_reason(monkeypatch, second_classification):
    from cloud_edge_robot_arm.vision.supervision import SupervisionDecision

    run, calls = supervised_episode()
    frame = run.capture_supervision_frame()
    run.observation = frame.observation
    decision = SupervisionDecision(
        episode_id=frame.context.episode_id,
        plan_version=frame.context.plan_version,
        state_version=frame.context.state_version,
        observation_id=frame.context.observation_id,
        next_step_id=frame.context.next_step_id,
        recommendation="CONTINUE",
        reason="SOFTWARE_ONLY",
    )
    response = {
        "episode_id": frame.context.episode_id,
        "captured_at": frame.observation.captured_at,
        "context": frame.context.model_dump(mode="json"),
        "decision": decision.model_dump(mode="json"),
        "worker_claim_id": frame.claim_id,
    }
    run.supervision = SimpleNamespace(poll=lambda **kwargs: [response])
    classifications = iter(["CURRENT", second_classification])
    run.worker_runtime.classify_supervision_reply = lambda owned: next(classifications)
    monkeypatch.setattr(
        "cloud_edge_robot_arm.vision.supervision.decide_supervision",
        lambda *args, **kwargs: "DISCARD",
    )
    if second_classification == "EXPIRED":
        run.apply_supervision()
        assert run.records[-1]["reason"] == "original_frame_ttl_expired"
        assert run.records[-1]["worker_claim_id"] == frame.claim_id
    else:
        with pytest.raises(_EpisodeStopped, match="WORKER_SUPERVISION_CONTEXT_CHANGED"):
            run.apply_supervision()
        assert not any(record.get("action") == "DISCARD" for record in run.records)
    assert "complete_tick_plan" not in calls


def test_supervisor_reobservation_waits_for_owned_fresh_effect_frame():
    from datetime import UTC, datetime

    from cloud_edge_robot_arm.vision.supervision import SupervisionDecision

    run, calls = supervised_episode()
    frame = run.capture_supervision_frame()
    run.observation = frame.observation
    completion = SimpleNamespace(step_id="approach", digest=lambda: "d" * 64)
    run._worker_completion = completion
    decision = SupervisionDecision(
        episode_id=frame.context.episode_id,
        plan_version=1,
        state_version=7,
        observation_id=frame.observation.observation_id,
        next_step_id="approach",
        recommendation="REOBSERVE",
        reason="software fixture",
    )
    response = {
        "episode_id": frame.observation.episode_id,
        "captured_at": frame.observation.captured_at,
        "context": frame.context.model_dump(mode="json"),
        "decision": decision.model_dump(mode="json"),
        "worker_claim_id": frame.claim_id,
    }
    run.supervision = SimpleNamespace(poll=lambda **kwargs: [response])
    run.worker_runtime.complete_supervision_plan = lambda *args: calls.append("complete_tick_plan")
    run.apply_supervision()
    assert run._worker_supervision_reobserve_pending[0].digest() == completion.digest()
    run.worker_runtime.reserve_effect_capture = (
        lambda *args, **kwargs: calls.append("reserve_effect") or "capture-claim"
    )
    fresh = frame.observation.model_copy(
        update={
            "frame_id": "later-frame",
            "observation_id": "later-frame",
            "captured_at": datetime.now(UTC),
        }
    )
    run.capture.capture = lambda: calls.append("capture_effect") or fresh
    run.recapture(completion=completion)
    assert run._worker_supervision_reobserve_pending is None
    assert (
        calls.index("complete_tick_plan")
        < calls.index("reserve_effect")
        < calls.index("capture_effect")
    )


@pytest.mark.parametrize("cancel_after_return", [False, True])
def test_actual_repositories_capture_provider_owner_receipt_and_cancellation(
    configured,
    cancel_after_return,
):
    from cloud_edge_robot_arm.vision.evaluation import ExecutionPolicy
    from cloud_edge_robot_arm.vision.supervision import SupervisionDecision
    from tests.test_visual_worker_runtime import adopted_owner
    from tests.test_visual_worker_runtime import frame as synthetic_frame

    owner, initial, _, _ = adopted_owner(configured)
    owner.initialize_supervision(0.01, RobotState(connected=True))
    run, calls = episode()
    run.worker_runtime = owner
    run.backend._episode_id = owner.episode_id
    run.budget = owner.verification_state
    run.observation = initial
    run.policy = ExecutionPolicy(
        "move the visible box",
        model_snapshot_hash="5" * 64,
        role_binding=owner.role_binding,
        device_pipeline="OPENCV",
        worker_runtime=owner,
        supervision_period_s=0.01,
        advance_physics_during_wait=True,
    )
    run._worker_supervision_frames = {}
    run._state_version = 0
    run.capture.capture = lambda: synthetic_frame("actual-repository-software-camera")
    source = run.capture_supervision_frame()
    run.supervision = SimpleNamespace(snapshot=lambda: {"closed": False})
    provider_calls = []

    def software_provider(observation, context):
        provider_calls.append(observation.observation_id)
        return SupervisionDecision(
            episode_id=context.episode_id,
            plan_version=context.plan_version,
            state_version=context.state_version,
            observation_id=context.observation_id,
            next_step_id=context.next_step_id,
            recommendation="CONTINUE",
            reason="SOFTWARE_ONLY",
        )

    run.planner = SimpleNamespace(
        base_url="software-only://supervised-owner", supervise=software_provider
    )
    response = run.supervise_frame(source)
    run.supervision.poll = lambda **kwargs: [response]
    original_publication = owner.publication.digest()
    if cancel_after_return:
        configured["jobs"].request_cancel(owner.source.job_id)
        with pytest.raises(_EpisodeStopped, match="WORKER_RUNTIME"):
            run.apply_supervision()
    else:
        run.apply_supervision()
        assert owner.publication.digest() == original_publication
        assert owner.verification_state.remaining_reobservations == 2
    record = configured["events"].get_visual_supervision(owner.episode_id).to_payload()
    assert record["captures_reserved"] == record["supervisor_calls_reserved"] == 1
    status = record["claims"][source.claim_id]["status"]
    if cancel_after_return:
        assert status == "PLAN_PENDING"
    elif status == "PLAN_PENDING":
        assert run.records[-1]["action"] == "DISCARD"
        assert run.records[-1]["reason"].startswith("original_frame_ttl_expired")
    else:
        assert status == "PLAN_COMPLETE"
    assert len(provider_calls) == 1 and run.actions == 0
