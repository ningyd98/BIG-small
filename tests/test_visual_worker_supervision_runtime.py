"""Actual job/event repositories, synthetic effect sources, no effects or models."""

from __future__ import annotations

import json
import sqlite3

import pytest

from cloud_edge_robot_arm.contracts.models import RobotState
from cloud_edge_robot_arm.vision.supervision import SupervisionContext, SupervisionDecision
from cloud_edge_robot_arm.vision.worker_runtime import VisualWorkerRuntime
from tests.test_visual_owner_repository import boundary
from tests.test_visual_worker_runtime import (
    adopted_owner,
    capture,
    frame,
    runtime,
)
from tests.test_visual_worker_runtime import (
    runtime_source as runtime_source,
)


def test_live_worker_has_owned_optional_source_bridge_before_enabling_effects():
    assert hasattr(VisualWorkerRuntime, "initialize_supervision"), (
        "worker cannot bridge persistent supervision/wait claims yet"
    )


def set_job_policy(data, *, period_ms=10, waits=True):
    source = data["source"]
    with sqlite3.connect(data["jobs"].database_path) as connection:
        connection.execute(
            "UPDATE simulation_jobs SET draft_json=? WHERE job_id=?",
            (
                json.dumps(
                    {
                        "parameter_overrides": {
                            "supervision_period_ms": period_ms,
                            "advance_physics_during_wait": waits,
                        }
                    }
                ),
                source.job_id,
            ),
        )


@pytest.fixture
def configured(runtime_source):  # noqa: F811 - pytest imports and injects this fixture.
    set_job_policy(runtime_source)
    return runtime_source


def context_for(claim, observation):
    publication = claim.publication
    original = claim.original
    step = next(s for s in original.contract.steps if s.step_id == claim.step_id)
    return SupervisionContext(
        episode_id=observation.episode_id,
        plan_version=publication.checkpoint.plan_version,
        state_version=publication.state_generation,
        next_step_id=claim.step_id,
        next_skill=step.skill.value,
        task_instruction="move the visible box",
        observation_id=observation.observation_id,
        captured_at=observation.captured_at,
        proprioception={"estop_engaged": False, "collision_detected": False},
    )


def supervisor_source(data):
    owner, _, _, _ = adopted_owner(data)
    owner.initialize_supervision(0.01, RobotState(connected=True))
    claim = owner.reserve_supervision_capture(1, RobotState(connected=True))
    observation = frame("software-supervision")
    context = context_for(claim, observation)
    owner.complete_supervision_capture(claim, observation, context, RobotState(connected=True))
    source = owner.reserve_supervision_plan(claim, RobotState(connected=True))
    return owner, claim, source


def decision_for(source):
    context = source.context
    return SupervisionDecision(
        episode_id=context.episode_id,
        plan_version=context.plan_version,
        state_version=context.state_version,
        next_step_id=context.next_step_id,
        observation_id=context.observation_id,
        recommendation="CONTINUE",
        reason="SOFTWARE_ONLY",
    )


def test_owned_capture_then_provider_receipt_bridges_once_without_reactive_pool_debit(configured):
    owner, claim, source = supervisor_source(configured)
    before = owner.publication.digest()
    result = owner.complete_supervision_plan(
        source, decision_for(source), RobotState(connected=True)
    )
    assert result.to_payload()["captures_reserved"] == 1
    assert result.to_payload()["supervisor_calls_reserved"] == 1
    assert owner.publication.digest() == before
    assert owner.verification_state.remaining_reobservations == 2
    with pytest.raises(RuntimeError):
        owner.complete_supervision_plan(source, decision_for(source), RobotState(connected=True))
    with pytest.raises(RuntimeError):
        owner.reserve_supervision_plan(claim, RobotState(connected=True))


def test_provider_source_getters_detach_nested_model_data(configured):
    owner, _, source = supervisor_source(configured)
    original = source.context.model_dump(mode="json")
    source.context.proprioception["estop_engaged"] = True
    source.observation.__dict__["frame_id"] = "caller-frame"
    assert source.context.model_dump(mode="json") == original
    assert source.observation.frame_id != "caller-frame"
    assert (
        owner.complete_supervision_plan(
            source, decision_for(source), RobotState(connected=True)
        ).to_payload()["supervisor_calls_reserved"]
        == 1
    )


def test_restart_never_recovers_pending_capture_or_provider_effect_handle(configured):
    owner, claim, source = supervisor_source(configured)
    restarted = runtime(configured)
    restored = restarted.initialize_supervision(0.01, RobotState(connected=True))
    assert restored.to_payload()["captures_reserved"] == 1
    assert restored.to_payload()["supervisor_calls_reserved"] == 1
    with pytest.raises(RuntimeError):
        restarted.reserve_supervision_capture(1, RobotState(connected=True))
    with pytest.raises(RuntimeError):
        restarted.complete_supervision_capture(
            claim, frame("software-stolen"), source.context, RobotState(connected=True)
        )
    with pytest.raises(RuntimeError):
        restarted.complete_supervision_plan(
            source, decision_for(source), RobotState(connected=True)
        )


def test_job_period_mismatch_or_unrequested_supervision_cannot_allocate(configured):
    owner, _, _, _ = adopted_owner(configured)
    with pytest.raises((RuntimeError, ValueError)):
        owner.initialize_supervision(0.02, RobotState(connected=True))
    with pytest.raises((RuntimeError, ValueError)):
        owner.initialize_supervision(None, RobotState(connected=True))
    assert configured["events"].get_visual_supervision(owner.episode_id) is None


def test_cancel_or_job_configuration_drift_between_provider_call_and_receipt_retains_cost(
    configured,
):
    owner, _, source = supervisor_source(configured)
    set_job_policy(configured, period_ms=20)
    with pytest.raises(RuntimeError, match="configuration"):
        owner.complete_supervision_plan(source, decision_for(source), RobotState(connected=True))
    record = configured["events"].get_visual_supervision(owner.episode_id)
    assert record.to_payload()["supervisor_calls_reserved"] == 1
    assert record.to_payload()["claims"][source.claim_id]["status"] == "PLAN_PENDING"


def test_initial_passive_wait_reuses_only_this_instances_current_durable_plan_claim(configured):
    owner = runtime(configured)
    capture(owner, initial=True)
    robot = RobotState(connected=True)
    claim = owner.reserve_plan(robot)
    before = owner.bootstrap.digest()
    owner.assert_owned_plan_wait(claim, robot)
    assert owner.bootstrap.digest() == before
    restarted = runtime(configured)
    with pytest.raises(RuntimeError):
        restarted.assert_owned_plan_wait(claim, robot)
    with pytest.raises(RuntimeError):
        owner.assert_owned_plan_wait("f" * 64, robot)
    assert owner.bootstrap.digest() == before


def test_wait_flag_is_real_job_source_and_live_config_must_stay_frozen(configured):
    owner = runtime(configured)
    capture(owner, initial=True)
    claim = owner.reserve_plan(RobotState(connected=True))
    set_job_policy(configured, waits=False)
    with pytest.raises(RuntimeError, match="configuration"):
        owner.assert_owned_plan_wait(claim, RobotState(connected=True))


def test_post_adoption_wait_claim_is_exact_owned_and_preserves_lost_allocations(configured):
    owner, _, _, _ = adopted_owner(configured)
    owner.initialize_supervision(0.01, RobotState(connected=True))
    claim = owner.reserve_wait(0.05, RobotState(connected=True))
    record = owner.complete_wait(claim, 0.02, RobotState(connected=True))
    assert record.to_payload()["wait_seconds_reserved"] == 0.05
    with pytest.raises(RuntimeError):
        owner.complete_wait(claim, 0.02, RobotState(connected=True))
    pending = owner.reserve_wait(0.05, RobotState(connected=True))
    restarted = runtime(configured)
    restored = restarted.initialize_supervision(0.01, RobotState(connected=True))
    assert restored.to_payload()["wait_seconds_reserved"] == 0.1
    with pytest.raises(RuntimeError):
        restarted.complete_wait(pending, 0.01, RobotState(connected=True))


def test_publication_change_after_claim_commit_cannot_return_an_effect_handle(configured):
    owner, _, _, _ = adopted_owner(configured)
    owner.initialize_supervision(0.01, RobotState(connected=True))
    repo = configured["events"]
    actual_transition = repo.transition_visual_supervision_if_current

    def publish_after_commit(*, request):
        result = actual_transition(request=request)
        pub = owner.publication
        changed = boundary(pub.checkpoint, suffix="source-drift")
        assert (
            repo.publish_visual_boundary_if_current(
                task_id=pub.identity.task_id,
                owner_epoch=pub.identity.owner_epoch,
                expected_owner_revision=pub.owner_revision,
                expected_contract_hash=pub.to_payload()["contract_hash"],
                expected_checkpoint_hash=pub.checkpoint.checkpoint_hash,
                checkpoint=changed,
                grounding=None,
                state_generation=pub.state_generation + 1,
            )
            is not None
        )
        return result

    repo.transition_visual_supervision_if_current = publish_after_commit
    with pytest.raises(RuntimeError, match="source"):
        owner.reserve_supervision_capture(1, RobotState(connected=True))
    assert repo.get_visual_supervision(owner.episode_id).to_payload()["captures_reserved"] == 1


def test_reply_classification_preserves_late_cost_and_never_hides_config_drift(configured):
    from datetime import timedelta
    from unittest.mock import patch

    import cloud_edge_robot_arm.vision.worker_runtime as worker_module

    owner, _, source = supervisor_source(configured)
    assert owner.classify_supervision_reply(source) == "CURRENT"
    real_datetime = worker_module.datetime

    class LaterDatetime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return source.observation.captured_at + timedelta(seconds=6)

    with patch.object(worker_module, "datetime", LaterDatetime):
        assert owner.classify_supervision_reply(source) == "EXPIRED"
        set_job_policy(configured, period_ms=20)
        with pytest.raises(RuntimeError, match="configuration"):
            owner.classify_supervision_reply(source)
    assert (
        configured["events"]
        .get_visual_supervision(owner.episode_id)
        .to_payload()["supervisor_calls_reserved"]
        == 1
    )


def test_provider_read_only_boundary_refuses_current_event_repository_cancellation(configured):
    owner, _, source = supervisor_source(configured)
    configured["events"].save_state(owner.episode_id, "CANCELLED", "SOFTWARE_ONLY")
    with pytest.raises(RuntimeError, match="cancel"):
        owner.assert_supervision_plan_pending(source)
    assert (
        configured["events"]
        .get_visual_supervision(owner.episode_id)
        .to_payload()["supervisor_calls_reserved"]
        == 1
    )


def test_provider_entry_requires_the_actual_current_publication_not_only_pending_claim(configured):
    owner, _, source = supervisor_source(configured)
    repository = configured["events"]
    publication = owner.supervision_source_publication
    advanced = repository.publish_visual_boundary_if_current(
        task_id=publication.identity.task_id,
        owner_epoch=publication.identity.owner_epoch,
        expected_owner_revision=publication.owner_revision,
        expected_contract_hash=publication.to_payload()["contract_hash"],
        expected_checkpoint_hash=publication.checkpoint.checkpoint_hash,
        checkpoint=boundary(publication.checkpoint, suffix="provider-entry-source-drift"),
        grounding=None,
        state_generation=publication.state_generation + 1,
    )
    assert advanced is not None and advanced.digest() != source.publication_hash
    pending = repository.get_visual_supervision(owner.episode_id).to_payload()
    assert pending["claims"][source.claim_id]["status"] == "PLAN_PENDING"
    assert pending["claims"][source.claim_id]["publication_hash"] == source.publication_hash
    assert pending["supervisor_calls_reserved"] == 1
    with pytest.raises(RuntimeError, match="source|publication"):
        owner.assert_supervision_plan_pending(source)
    assert repository.get_visual_supervision(owner.episode_id).to_payload() == pending


def test_commit_crossing_original_ttl_is_classifiable_after_local_handle_consumption(configured):
    from datetime import timedelta
    from unittest.mock import patch

    import cloud_edge_robot_arm.vision.worker_runtime as worker_module

    owner, _, source = supervisor_source(configured)
    repository_module = __import__(
        type(owner.source.event_repository).__module__, fromlist=["datetime"]
    )
    real_datetime = worker_module.datetime

    class LaterDatetime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return source.observation.captured_at + timedelta(seconds=6)

    with (
        patch.object(worker_module, "datetime", LaterDatetime),
        patch.object(repository_module, "datetime", LaterDatetime),
    ):
        with pytest.raises(worker_module.VisualSupervisionReplyExpired):
            owner.complete_supervision_plan(
                source, decision_for(source), RobotState(connected=True)
            )
        assert owner.classify_supervision_reply(source) == "EXPIRED"
        with pytest.raises(RuntimeError, match="owned"):
            owner.complete_supervision_plan(
                source, decision_for(source), RobotState(connected=True)
            )
    record = owner.source.event_repository.get_visual_supervision(owner.episode_id).to_payload()
    assert record["claims"][source.claim_id]["status"] == "PLAN_PENDING"
    assert record["supervisor_calls_reserved"] == 1


def test_expired_grounding_preserves_observer_budget_and_valid_effect_source_only(configured):
    from datetime import timedelta
    from unittest.mock import patch

    import cloud_edge_robot_arm.repositories.event_autonomy.visual_owner as owner_module
    import cloud_edge_robot_arm.vision.worker_runtime as worker_module
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import digest
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_verification import (
        VisualEffectCompletion,
    )
    from cloud_edge_robot_arm.vision.owner_registration import StepGroundingBinding
    from tests.test_visual_worker_runtime import completion_for

    owner, observation, contract, publication = adopted_owner(configured)
    step = contract.steps[0].model_copy(
        update={"preconditions": [], "success_conditions": []}, deep=True
    )
    now = worker_module.datetime.now(worker_module.UTC)
    binding = StepGroundingBinding(
        owner.original.digest(),
        owner.original.identity,
        owner.original.requirements[step.step_id],
        publication.owner_revision,
        publication.state_generation + 1,
        publication.checkpoint.checkpoint_hash,
        observation.observation_id,
        observation.checksum_sha256,
        observation.calibration_version,
        contract.plan_version,
        contract.command_seq,
        "6" * 64,
        "7" * 64,
        None,
        owner.source.source_hashes,
        step.model_dump_json(),
        owner.original.requirements[step.step_id].expected_duration_s,
        now,
        now + timedelta(seconds=3),
    )
    owner.publish_grounding(binding, RobotState(connected=True))
    completion = completion_for(owner, observation, contract)
    raw = completion.to_payload()
    grounded = contract.model_copy(update={"steps": [step, *contract.steps[1:]]})
    raw["execution_payload_hash"] = digest(grounded.model_dump(mode="json"))
    completion = VisualEffectCompletion.from_payload(raw)
    real_datetime = worker_module.datetime

    class ClockMeta(type):
        def __instancecheck__(cls, value):
            return isinstance(value, real_datetime)

    class LaterDatetime(real_datetime, metaclass=ClockMeta):
        @classmethod
        def now(cls, tz=None):
            return binding.valid_until + timedelta(seconds=1)

    with (
        patch.object(owner_module, "datetime", LaterDatetime),
        patch.object(worker_module, "datetime", LaterDatetime),
    ):
        with pytest.raises(RuntimeError, match="publication"):
            _ = owner.publication
        assert owner.supervision_source_publication.to_payload()["grounding"] is not None
        assert owner.verification_state.remaining_reobservations == 2
        assert owner.original.requirements[step.step_id].ordinary_ttl_s == 5.0
        owner.initialize_supervision(0.01, RobotState(connected=True))
        assert owner.reserve_supervision_capture(1, RobotState(connected=True)).claim_id
        late = completion.to_payload()
        late.update(
            started_at=binding.valid_until.isoformat(),
            returned_at=(binding.valid_until + timedelta(milliseconds=20)).isoformat(),
        )
        late["result"]["timestamp"] = (
            (binding.valid_until + timedelta(milliseconds=10)).isoformat().replace("+00:00", "Z")
        )
        with pytest.raises(RuntimeError):
            owner.reserve_effect_capture(
                VisualEffectCompletion.from_payload(late), RobotState(connected=True)
            )
        foreign = completion.to_payload()
        foreign["source_checkpoint_hash"] = "f" * 64
        with pytest.raises(RuntimeError):
            owner.reserve_effect_capture(
                VisualEffectCompletion.from_payload(foreign), RobotState(connected=True)
            )
        assert owner.reserve_effect_capture(completion, RobotState(connected=True))
