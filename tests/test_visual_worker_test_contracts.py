"""测试替身遵循真实消费者接口，不授予worker或实体执行资格。"""

from dataclasses import asdict
from datetime import UTC, datetime, timedelta

import pytest

from cloud_edge_robot_arm.edge.recovery.verification_router import (
    VerificationBudget,
    VerificationBudgetState,
)
from cloud_edge_robot_arm.vision.execution import _EpisodeStopped
from tests.test_rgbd_closed_loop import _safety_gate_run
from tests.test_visual_worker_execution import episode


def test_nonlocal_spy_enforces_runtime_deadline_before_capture():
    """新episode预算不能刷新runtime持有的原截止时间。"""
    run, calls = episode()
    owned_budget = run.worker_runtime.verification_state
    owned_budget.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
    run.budget = VerificationBudgetState.start(VerificationBudget(2, 0, 3, 120))
    with pytest.raises(_EpisodeStopped, match="VERIFICATION_TIMEOUT"):
        run.recapture()
    assert run.budget is owned_budget
    assert calls == ["source_check"]
    assert run.observation is None and run.count == 0


def test_nonlocal_spy_uses_durable_budget_and_capture_order():
    """真实消费者使用durable预算与采集顺序，不进入local时间路径。"""
    run, calls = episode()

    def forbidden_local_clock():
        pytest.fail("nonlocal orchestration must not use local owner time")

    run.worker_runtime.remaining_app_seconds = forbidden_local_clock
    run.check_active()
    assert run.budget is run.worker_runtime.verification_state
    assert run.budget_payload() == asdict(run.worker_runtime.verification_state)
    observation = run.recapture()
    assert observation is run.observation and run.count == 1
    assert calls.index("reserve_initial") < calls.index("capture") < calls.index("complete_capture")
    assert "source_check" in calls[calls.index("capture") + 1 : calls.index("complete_capture")]


def test_recapture_completion_keyword_reaches_real_postcheck():
    """completion明确转发后，原负超速必须由真实post安全门拒绝。"""
    run, contract, dispatched = _safety_gate_run("post")
    original = run.recapture
    with pytest.raises(TypeError):
        original(unexpected_keyword=True)
    received = []

    def recapture(*, completion=None):
        received.append(completion)
        return original(completion=completion)

    run.recapture = recapture
    assert run.execute(contract, contract.steps[0]) is False
    assert received == [None] and len(dispatched) == 1
    layers = [row["layer"] for row in run.records]
    assert layers.index("SAFETY_PRECHECK") < layers.index("SKILL_RETURN")
    assert layers.index("SKILL_RETURN") < layers.index("SAFETY_POSTCHECK")
    postcheck = next(row for row in run.records if row["layer"] == "SAFETY_POSTCHECK")
    assert postcheck["evaluation"]["decision"] == "REJECT"
