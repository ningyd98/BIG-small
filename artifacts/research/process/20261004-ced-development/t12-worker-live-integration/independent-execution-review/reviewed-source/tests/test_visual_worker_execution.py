"""SOFTWARE_ONLY orchestration boundaries; spies never authenticate a worker."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from cloud_edge_robot_arm.cloud.planning.models import PlannerDraft
from cloud_edge_robot_arm.contracts import RobotState
from cloud_edge_robot_arm.edge.recovery.verification_router import (
    VerificationBudget,
    VerificationBudgetState,
)
from cloud_edge_robot_arm.vision.execution import _EpisodeStopped, _VisualEpisode
from tests.test_opencv_target_evidence import scene
from tests.test_visual_worker_runtime import runtime_source as shared_runtime_source

runtime_source = shared_runtime_source


class RuntimeSpy:
    """Only asserts wiring order, with no repository/lease/evidence acceptance."""

    def __init__(self, calls):
        self.calls = calls
        self.episode_id = "software-runtime-episode"
        self.is_adopted = False
        self.bootstrap = SimpleNamespace(planning_source_usable=True, digest=lambda: "a" * 64)
        self.verification_state = VerificationBudgetState.start(VerificationBudget(2, 0, 3, 120))

    def check_active(self, state):
        self.calls.append("source_check")

    def reserve_capture(self, state, *, initial=False):
        self.calls.append("reserve_initial" if initial else "reserve_reobservation")
        return "capture-claim"

    def complete_capture(self, claim, observation, state):
        assert claim == "capture-claim"
        self.calls.append("complete_capture")

    def reserve_plan(self, state):
        self.calls.append("reserve_plan")
        return "plan-claim"

    def complete_plan(self, claim, draft, state):
        assert claim == "plan-claim"
        self.calls.append("complete_plan")


def episode():
    import time

    calls = []
    run = _VisualEpisode.__new__(_VisualEpisode)
    run.worker_runtime = RuntimeSpy(calls)
    run.policy = SimpleNamespace(
        cancelled=None,
        output_dir=None,
        role_binding=None,
        instruction="SOFTWARE_ONLY",
        raw_recorder=None,
    )
    run.robot = SimpleNamespace(get_state=lambda: RobotState(connected=True))
    run.backend = SimpleNamespace(_episode_id=run.worker_runtime.episode_id)
    run.observation = None
    run.count = run.calls = run.actions = 0
    run.records = []
    run.budget = run.worker_runtime.verification_state
    run.deadline = time.monotonic() + 120
    run.wait_clock = None
    run.capture = SimpleNamespace(capture=lambda: calls.append("capture") or scene())
    run.validate_role_boundary = lambda: calls.append("role_check")
    return run, calls


def test_initial_capture_is_claimed_before_real_effect_and_completed_after_source_recheck():
    run, calls = episode()
    observation = run.recapture()
    assert observation is run.observation
    assert calls.index("reserve_initial") < calls.index("capture") < calls.index("complete_capture")
    assert "source_check" in calls[calls.index("capture") + 1 : calls.index("complete_capture")]


def test_unavailable_capture_claim_prevents_sensor_read():
    run, calls = episode()

    def denied(*_, **__):
        raise ValueError("pending claim cannot be replayed")

    run.worker_runtime.reserve_capture = denied
    with pytest.raises(_EpisodeStopped, match="WORKER_RUNTIME"):
        run.recapture()
    assert "capture" not in calls


def test_capture_failure_keeps_spent_claim_and_has_no_completion():
    run, calls = episode()

    def failed_capture():
        calls.append("capture")
        raise RuntimeError("sensor unavailable")

    run.capture.capture = failed_capture
    with pytest.raises(RuntimeError, match="sensor unavailable"):
        run.recapture()
    assert "reserve_initial" in calls
    assert "complete_capture" not in calls


def test_source_loss_during_capture_does_not_complete_or_install_frame():
    run, calls = episode()

    def check(state):
        calls.append("source_check")
        if "capture" in calls:
            raise ValueError("lease lost")

    run.worker_runtime.check_active = check
    with pytest.raises(_EpisodeStopped, match="WORKER_RUNTIME"):
        run.recapture()
    assert "capture" in calls and "complete_capture" not in calls
    assert run.observation is None and run.count == 0


def test_plan_claim_surrounds_provider_and_durable_completion_replaces_memory_route():
    run, calls = episode()
    run.observation = scene()
    draft = PlannerDraft(raw_text="SOFTWARE_ONLY", parsed_json={"not_executable": True})
    run.planner = SimpleNamespace(
        base_url="software-only://planner", plan=lambda _: calls.append("provider") or draft
    )
    run.route = lambda *_: pytest.fail("bootstrap must use its persisted state")
    assert run.plan() is draft
    assert calls.index("reserve_plan") < calls.index("provider") < calls.index("complete_plan")


def test_durable_deadline_is_not_restarted_by_episode_or_source_check():
    run, _ = episode()
    run.worker_runtime.verification_state.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
    run.budget = VerificationBudgetState.start(VerificationBudget(2, 0, 3, 120))
    with pytest.raises(_EpisodeStopped, match="VERIFICATION_TIMEOUT"):
        run.check_active()


def test_canonical_worker_route_uses_current_checkpoint_context_not_role_digest():
    from cloud_edge_robot_arm.auto_mode.runtime_events import DecisionAction
    from tests.test_visual_owner_registration import values

    run, calls = episode()
    data = values()
    contract = data["original"].contract
    run.observation = scene()
    run.tracker = None
    run.worker_runtime.publication = SimpleNamespace(checkpoint=data["source_checkpoint"])
    seen = []

    def route(online, **kwargs):
        seen.append((online, kwargs))
        return SimpleNamespace(
            record=SimpleNamespace(
                route="STOP",
                to_payload=lambda: {"scope": "SOURCE_ROUTE_ONLY"},
            ),
            write_disposition="NEW_COMMIT",
        )

    run.worker_runtime.route = route
    action = run.worker_route("PRECONDITION", contract, contract.steps[0])
    assert action == DecisionAction.STOP
    online, args = seen[0]
    assert online.context_hash == data["source_checkpoint"].checkpoint_hash
    assert args["phase"] == "PRECONDITION"
    assert args["execution_contract"] == contract
    assert "verdicts" not in args and "source_check" in calls


def test_worker_adoption_preserves_full_original_contract_before_native_boundary(monkeypatch):
    from tests.test_visual_owner_registration import values

    run, calls = episode()
    run.observation = scene()
    contract = values()["original"].contract
    run.worker_runtime.adopt_plan = lambda _: (
        contract,
        SimpleNamespace(
            to_payload=lambda: {"binding_scope": "DURABLE_BINDING_ONLY"},
        ),
    )
    monkeypatch.setattr(
        "cloud_edge_robot_arm.vision.execution.grounded_contract",
        lambda *_: pytest.fail("legacy compiler changed original policy"),
    )
    monkeypatch.setattr(
        "cloud_edge_robot_arm.vision.execution.make_target_tracker", lambda *_: SimpleNamespace()
    )
    seen = []

    def native(current, step, *, boundary):
        seen.append((current, step, boundary))
        raise _EpisodeStopped("native evidence unavailable")

    run.require_native_action_evidence = native
    with pytest.raises(_EpisodeStopped, match="native evidence unavailable"):
        run.run_worker_online(PlannerDraft(raw_text="SOFTWARE_ONLY"))
    assert seen == [(contract, contract.steps[0], "CLOUD_RETURN")]
    assert "capture" not in calls


@pytest.mark.parametrize("source_route", ["STOP", "CONTINUE"])
def test_source_route_cannot_authorize_native_unknown_action(tmp_path, source_route):
    from cloud_edge_robot_arm.vision.evaluation import ExecutionPolicy
    from tests.test_ced_runtime_binding import role_binding
    from tests.test_visual_owner_registration import values

    run, calls = episode()
    planner, binding = role_binding(tmp_path)
    run.planner = planner
    run.policy = ExecutionPolicy(
        "SOFTWARE_ONLY",
        model_snapshot_hash="a" * 64,
        device_pipeline="OPENCV",
        role_binding=binding,
    )
    run.observation = scene()
    run.tracker = None
    data = values()
    run.worker_runtime.publication = SimpleNamespace(checkpoint=data["source_checkpoint"])
    run.worker_runtime.route = lambda *_, **__: SimpleNamespace(
        record=SimpleNamespace(route=source_route, to_payload=lambda: {}),
        write_disposition="NEW_COMMIT",
    )
    contract = data["original"].contract
    with pytest.raises(
        _EpisodeStopped, match="ACTION_EVIDENCE_UNKNOWN|WORKER_NATIVE_VERDICT_MISMATCH"
    ):
        run.require_native_action_evidence(contract, contract.steps[0], boundary="CLOUD_RETURN")
    assert "capture" not in calls
    assert run.actions == 0


def test_real_repositories_are_used_by_capture_plan_adoption_and_native_stop(
    runtime_source,
    monkeypatch,
):
    """Real durable joins, explicitly synthetic sensor/provider, zero physical actions."""
    from tests.test_visual_owner_registration import values
    from tests.test_visual_worker_runtime import frame, runtime

    run, calls = episode()
    owner = runtime(runtime_source)
    run.worker_runtime = owner
    run.budget = owner.verification_state
    run.policy.role_binding = runtime_source["binding"]
    run.policy.device_pipeline = "OPENCV"
    run.policy.instruction = "move the visible box"
    run.policy.model_snapshot_hash = "5" * 64
    index = 0

    def capture():
        nonlocal index
        index += 1
        calls.append("synthetic_sensor")
        return frame(f"software-integration-frame-{index}")

    def plan(request):
        calls.append("synthetic_provider")
        return PlannerDraft(
            raw_text="SOFTWARE_ONLY integration reply",
            parsed_json={
                **values()["original"].contract.model_dump(mode="json"),
                "user_instruction": run.policy.instruction,
            },
            observation_evidence={
                **request.observation.evidence(),
                "model_snapshot_hash": "5" * 64,
            },
        )

    run.capture.capture = capture
    run.planner = SimpleNamespace(base_url="software-only://durable-integration", plan=plan)
    run.backend = SimpleNamespace(
        _episode_id=owner.episode_id,
        step=lambda **_: calls.append("synthetic_physics_advance"),
    )
    monkeypatch.setattr(
        "cloud_edge_robot_arm.vision.execution.make_target_tracker",
        lambda *_: SimpleNamespace(facts=lambda *_: {}),
    )
    monkeypatch.setattr(
        "cloud_edge_robot_arm.vision.execution.grounded_contract",
        lambda *_: pytest.fail("durable worker must preserve the original plan"),
    )
    run.recapture()
    draft = run.plan()
    original_deadline = owner.verification_state.deadline_at
    with pytest.raises(_EpisodeStopped, match="ACTION_EVIDENCE_UNKNOWN"):
        run.run_worker_online(draft)
    current = owner.publication
    assert calls.count("synthetic_provider") == 1
    assert calls.count("synthetic_sensor") == 3
    assert calls.count("synthetic_physics_advance") == 2
    assert current.verification_budget.state.remaining_reobservations == 0
    assert current.verification_budget.state.deadline_at == original_deadline
    assert current.checkpoint.completed_step_ids == []
    assert current.retry_budget.task_retry_count == 0
    assert current.retry_budget.retry_count_used == 0
    assert run.calls == 1 and run.count == 3 and run.actions == 0


def test_dispatch_guard_rejects_cleared_source_binding_before_executor():
    from tests.test_visual_owner_registration import values

    run, calls = episode()
    run.worker_runtime.publication = SimpleNamespace(to_payload=lambda: {"grounding": None})
    contract = values()["original"].contract
    with pytest.raises(_EpisodeStopped, match="WORKER_DISPATCH_GROUNDING_INVALIDATED"):
        run.worker_dispatch_guard(contract, contract.steps[0])
    assert run.actions == 0 and "source_check" in calls


def test_actual_backend_episode_replacement_stops_before_new_capture_claim():
    run, calls = episode()
    run.backend._episode_id = "replacement-episode"
    with pytest.raises(_EpisodeStopped, match="WORKER_BACKEND_EPISODE_CHANGED"):
        run.recapture()
    assert "capture" not in calls and "reserve_initial" not in calls


@pytest.mark.parametrize(
    "options",
    [
        {"supervision_period_s": 0.01},
        {"advance_physics_during_wait": True},
    ],
)
def test_worker_rejects_optional_effects_until_their_durable_claims_are_implemented(
    tmp_path,
    options,
):
    from cloud_edge_robot_arm.vision.evaluation import ExecutionPolicy
    from tests.test_ced_runtime_binding import role_binding

    _, binding = role_binding(tmp_path)
    with pytest.raises(ValueError, match="durable supervision and wait claims"):
        ExecutionPolicy(
            "SOFTWARE_ONLY",
            model_snapshot_hash="a" * 64,
            device_pipeline="OPENCV",
            role_binding=binding,
            worker_runtime=RuntimeSpy([]),
            **options,
        )
