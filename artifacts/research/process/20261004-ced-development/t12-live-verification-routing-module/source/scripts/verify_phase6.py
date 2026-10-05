#!/usr/bin/env python3
"""Phase 6 执行与恢复验证入口，按固定检查流程生成验收证据，不执行未授权硬件动作。

Phase 6.1 acceptance verification.

The script performs behavioral checks against production code paths. It prints
one line per check immediately and exits non-zero if any check fails."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def asgi_request(
    app: Any,
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return asyncio.run(_asgi_request(app, method, path, json_body=json_body))


async def _asgi_request(
    app: Any,
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = b"" if json_body is None else json.dumps(json_body).encode("utf-8")
    sent = False
    status_code = 0
    response_body = bytearray()

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        nonlocal status_code
        if message["type"] == "http.response.start":
            status_code = int(message["status"])
        elif message["type"] == "http.response.body":
            response_body.extend(message.get("body", b""))

    headers = [(b"content-type", b"application/json")] if json_body is not None else []
    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": b"",
            "headers": headers,
            "client": ("verify", 50000),
            "server": ("testserver", 80),
            "root_path": "",
            "state": {},
        },
        receive,
        send,
    )
    text = response_body.decode("utf-8")
    return {"status_code": status_code, "json": json.loads(text) if text else None}


def report(index: int, name: str, func: Callable[[], None]) -> bool:
    label = f"{index}. {name}"
    try:
        func()
    except Exception as exc:
        print(f"✗ {label}: {type(exc).__name__}: {exc}", flush=True)
        return False
    print(f"✓ {label}", flush=True)
    return True


def make_contract(**overrides: Any) -> Any:
    from cloud_edge_robot_arm.contracts import (
        ControlMode,
        FailurePolicy,
        SafetyConstraints,
        SkillName,
        TaskContract,
        TaskStep,
        TaskTarget,
    )

    now = datetime.now(UTC)
    data: dict[str, Any] = {
        "task_id": "phase6-task",
        "plan_version": 1,
        "command_seq": 1,
        "timestamp": now,
        "control_mode": ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        "issued_at": now,
        "valid_until": now + timedelta(seconds=60),
        "user_instruction": "pick and place object",
        "scene_version": 1,
        "expected_scene_version": 1,
        "task_target": TaskTarget(
            object_id="red_cube", object_class="cube", target_region_id="bin_a"
        ),
        "steps": [
            TaskStep(
                step_id="approach",
                skill=SkillName.APPROACH,
                parameters={"object_id": "red_cube"},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=0,
            ),
            TaskStep(
                step_id="grasp",
                skill=SkillName.GRASP,
                parameters={"object_id": "red_cube"},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=1,
            ),
            TaskStep(
                step_id="lift",
                skill=SkillName.LIFT,
                parameters={"height_m": 0.16},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=0,
                preconditions=["object_attached"],
            ),
            TaskStep(
                step_id="move-region",
                skill=SkillName.MOVE_TO_REGION,
                parameters={"region_id": "bin_a"},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=0,
                preconditions=["object_attached"],
            ),
            TaskStep(
                step_id="place",
                skill=SkillName.PLACE,
                parameters={"region_id": "bin_a"},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=0,
                preconditions=["object_attached"],
            ),
            TaskStep(
                step_id="release",
                skill=SkillName.RELEASE,
                parameters={},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=0,
            ),
            TaskStep(
                step_id="verify",
                skill=SkillName.VERIFY_RESULT,
                parameters={"object_id": "red_cube", "region_id": "bin_a"},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=0,
            ),
        ],
        "safety_constraints": SafetyConstraints(
            max_joint_velocity=1.0,
            max_tcp_velocity=0.5,
            minimum_safe_height=0.08,
            workspace_id="workspace_a",
        ),
        "failure_policy": FailurePolicy(
            local_retry_limit=1,
            on_timeout="pause",
            on_safety_rejection="stop",
            on_network_loss="pause",
        ),
        "completion_criteria": ["object_inside_target_region"],
    }
    data.update(overrides)
    return TaskContract(**data)


def run_event_executor(grasp_failures: int = 1) -> tuple[Any, Any, Any, Any, Any]:
    from cloud_edge_robot_arm.edge.event_mode.controller import EventTriggeredModeController
    from cloud_edge_robot_arm.edge.runtime.task_executor import TaskExecutor
    from cloud_edge_robot_arm.edge.safety.shield import SafetyShield
    from cloud_edge_robot_arm.repositories.event_autonomy.memory import (
        InMemoryEventAutonomyRepository,
    )
    from cloud_edge_robot_arm.repositories.memory import InMemoryRepository
    from cloud_edge_robot_arm.simulation.mock_robot import MockRobotAdapter, MockScene

    contract = make_contract()
    robot = MockRobotAdapter(
        scene=MockScene.with_default_pick_place_scene(),
        auto_connect=True,
        grasp_failures_remaining=grasp_failures,
    )
    runtime_repo = InMemoryRepository()
    event_repo = InMemoryEventAutonomyRepository()
    controller = EventTriggeredModeController(repository=event_repo)
    result = TaskExecutor(
        robot=robot,
        shield=SafetyShield(),
        repository=runtime_repo,
        event_controller=controller,
    ).submit_contract(contract.model_dump(mode="json"))
    return contract, robot, runtime_repo, event_repo, result


def check_compile_self() -> None:
    compile(Path(__file__).read_text(), str(Path(__file__)), "exec")


def check_capabilities() -> None:
    from cloud_edge_robot_arm.cloud.api.app import create_app
    from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
    from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
    from cloud_edge_robot_arm.repositories.event_autonomy.memory import (
        InMemoryEventAutonomyRepository,
    )

    app = create_app(
        PlanningPipeline(planner=MockPlannerAdapter()),
        event_repo=InMemoryEventAutonomyRepository(),
    )
    modes = asgi_request(app, "GET", "/api/v1/planning/capabilities")["json"][
        "supported_control_modes"
    ]
    assert modes == ["PERIODIC_CLOUD_SUPERVISION", "EVENT_TRIGGERED_EDGE_AUTONOMY"]


def check_no_auto() -> None:
    from cloud_edge_robot_arm.cloud.api.app import create_app
    from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
    from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
    from cloud_edge_robot_arm.repositories.event_autonomy.memory import (
        InMemoryEventAutonomyRepository,
    )

    app = create_app(
        PlanningPipeline(planner=MockPlannerAdapter()),
        event_repo=InMemoryEventAutonomyRepository(),
    )
    payload = asgi_request(app, "GET", "/api/v1/planning/capabilities")["json"]
    assert "AUTO" not in payload["supported_control_modes"]


def check_retry_sequence() -> None:
    _, robot, _, _, result = run_event_executor(1)
    assert result.success is True
    assert [a.action_type for a in robot.history][:3] == ["APPROACH", "GRASP", "GRASP"]


def check_retry_not_skip() -> None:
    _, robot, _, _, _ = run_event_executor(1)
    sequence = [a.action_type for a in robot.history]
    assert sequence.index("PLACE") > sequence.index("GRASP")
    assert sequence[:6] == ["APPROACH", "GRASP", "GRASP", "LIFT", "MOVE_TO_REGION", "PLACE"]


def check_safety_rechecked() -> None:
    contract, _, runtime_repo, _, _ = run_event_executor(1)
    safety_starts = [
        e
        for e in runtime_repo.list_audit_events(contract.task_id)
        if e.event_type == "SAFETY_EVALUATION_STARTED"
    ]
    grasp_starts = [e for e in safety_starts if e.details.get("step_id") == "grasp"]
    assert len(grasp_starts) == 2


def check_no_fake_recovery_execute() -> None:
    from cloud_edge_robot_arm.edge.recovery.manager import LocalRecoveryManager

    assert not hasattr(LocalRecoveryManager(), "execute")


def check_budget_atomic() -> None:
    from cloud_edge_robot_arm.contracts.models import RecoveryBudget
    from cloud_edge_robot_arm.repositories.event_autonomy.memory import (
        InMemoryEventAutonomyRepository,
    )

    repo = InMemoryEventAutonomyRepository()
    repo.save_retry_budget(
        RecoveryBudget(budget_id="b", task_id="t", retry_count_used=0, remaining_retries=2)
    )
    consumed1, _ = repo.consume_retry_if_available("t", "s", "GRASP", 0)
    consumed2, _ = repo.consume_retry_if_available("t", "s", "GRASP", 0)
    assert consumed1 is True and consumed2 is False


def check_budget_restart() -> None:
    from cloud_edge_robot_arm.contracts.models import RecoveryBudget
    from cloud_edge_robot_arm.repositories.event_autonomy.sqlite import (
        SQLiteEventAutonomyRepository,
    )

    db = tempfile.mktemp(suffix=".sqlite3")
    try:
        repo1 = SQLiteEventAutonomyRepository(db)
        repo1.save_retry_budget(
            RecoveryBudget(budget_id="b", task_id="t", retry_count_used=0, remaining_retries=2)
        )
        repo1.consume_retry_if_available("t", "s", "GRASP", 0)
        repo1.close()
        repo2 = SQLiteEventAutonomyRepository(db)
        budget = repo2.get_retry_budget("t")
        repo2.close()
        assert budget is not None and budget.retry_count_used == 1 and budget.remaining_retries == 1
    finally:
        if os.path.exists(db):
            os.unlink(db)


def check_event_persistence() -> None:
    contract, _, _, event_repo, _ = run_event_executor(1)
    assert len(event_repo.list_events(contract.task_id)) == 1


def check_state_persistence() -> None:
    contract, _, _, event_repo, _ = run_event_executor(1)
    assert event_repo.get_state(contract.task_id) in {"EXECUTING_AUTONOMOUSLY", "COMPLETED"}
    assert event_repo.list_state_transitions(contract.task_id)


def check_failure_summary_persistence() -> None:
    contract, _, _, event_repo, _ = run_event_executor(2)
    messages = event_repo.list_pending_outbox(contract.task_id)
    summary_ids = [m.summary_id for m in messages if m.summary_id]
    assert summary_ids
    assert event_repo.get_failure_summary(summary_ids[0]) is not None
    assert event_repo.get_state(contract.task_id) == "WAITING_CLOUD_REPLAN"


def check_replan_request_persistence() -> None:
    contract, _, _, event_repo, _ = run_event_executor(2)
    request_ids = [
        m.request_id for m in event_repo.list_pending_outbox(contract.task_id) if m.request_id
    ]
    assert request_ids
    assert event_repo.get_replan_request(request_ids[0]) is not None


def check_outbox_persistence() -> None:
    contract, _, _, event_repo, _ = run_event_executor(2)
    assert event_repo.list_pending_outbox(contract.task_id)


def check_network_recovery_idempotent_send() -> None:
    from cloud_edge_robot_arm.contracts.models import MessageStatus, PendingMessage
    from cloud_edge_robot_arm.repositories.event_autonomy.memory import (
        InMemoryEventAutonomyRepository,
    )

    repo = InMemoryEventAutonomyRepository()
    repo.enqueue_outbox(
        PendingMessage(
            message_id="m",
            task_id="t",
            message_type="TEST",
            payload={},
            status=MessageStatus.PENDING,
        )
    )
    assert repo.claim_outbox_message() is not None
    assert repo.claim_outbox_message() is None
    assert repo.mark_outbox_sent("m") is True
    assert repo.mark_outbox_sent("m") is True


def check_api_persistence() -> None:
    from cloud_edge_robot_arm.cloud.api.app import create_app
    from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
    from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
    from cloud_edge_robot_arm.repositories.event_autonomy.memory import (
        InMemoryEventAutonomyRepository,
    )

    repo = InMemoryEventAutonomyRepository()
    app = create_app(PlanningPipeline(planner=MockPlannerAdapter()), event_repo=repo)
    payload = {
        "event_id": "evt-api",
        "task_id": "task-api",
        "event_type": "GRASP_FAILED",
        "severity": "ERROR",
        "robot_id": "robot-api",
        "step_id": "grasp",
        "plan_version": 1,
        "command_seq": 1,
    }
    assert (
        asgi_request(app, "POST", "/api/v1/robots/robot-api/events", json_body=payload)[
            "status_code"
        ]
        == 201
    )
    assert asgi_request(app, "GET", "/api/v1/events/evt-api")["json"]["event_id"] == "evt-api"
    assert len(asgi_request(app, "GET", "/api/v1/tasks/task-api/events")["json"]["events"]) == 1
    assert (
        asgi_request(app, "POST", "/api/v1/robots/robot-api/events", json_body=payload)[
            "status_code"
        ]
        == 201
    )
    mismatch = dict(payload, event_id="evt-api-2", robot_id="other")
    assert (
        asgi_request(app, "POST", "/api/v1/robots/robot-api/events", json_body=mismatch)[
            "status_code"
        ]
        == 409
    )
    assert asgi_request(app, "GET", "/api/v1/events/missing")["status_code"] == 404


def check_replan_service_adapter() -> None:
    from cloud_edge_robot_arm.cloud.replanning.adapters import MockReplannerAdapter
    from cloud_edge_robot_arm.cloud.replanning.service import LocalReplanningService
    from cloud_edge_robot_arm.contracts.models import (
        EdgeEvent,
        EdgeEventType,
        ExecutionCheckpoint,
        FailureSummary,
        LocalReplanningRequest,
    )
    from cloud_edge_robot_arm.repositories.event_autonomy.memory import (
        InMemoryEventAutonomyRepository,
    )

    repo = InMemoryEventAutonomyRepository()
    now = datetime.now(UTC)
    contract = make_contract(task_id="task-rp")
    repo.save_active_contract(contract, plan_id="plan-rp", robot_id="robot-rp")
    repo.save_event(
        EdgeEvent(
            event_id="evt-rp",
            task_id="task-rp",
            event_type=EdgeEventType.GRASP_FAILED,
            severity="ERROR",
            plan_version=1,
            command_seq=1,
            timestamp=now,
            robot_id="robot-rp",
            plan_id="plan-rp",
            step_id="grasp",
        )
    )
    repo.save_failure_summary(
        FailureSummary(
            summary_id="fs-rp",
            task_id="task-rp",
            failure_event_id="evt-rp",
            failed_step_id="grasp",
            reason="failed",
            recovery_hint="replan",
            local_retry_count=1,
            plan_version=1,
            command_seq=1,
            timestamp=now,
            robot_id="robot-rp",
            plan_id="plan-rp",
        )
    )
    repo.save_execution_checkpoint(
        ExecutionCheckpoint(
            checkpoint_id="ckpt-rp",
            task_id="task-rp",
            plan_id="plan-rp",
            robot_id="robot-rp",
            plan_version=1,
            command_seq=1,
            current_step_id="grasp",
            current_step_index=1,
            failed_step_id="grasp",
            last_successful_step_id="approach",
            completed_step_ids=["approach"],
            pending_step_ids=["grasp", "lift", "move-region", "place", "release", "verify"],
            scene_version=1,
            execution_state="WAITING_CLOUD_REPLAN",
        )
    )
    req = LocalReplanningRequest(
        request_id="req-rp",
        trigger_event_id="evt-rp",
        failure_summary_id="fs-rp",
        robot_id="robot-rp",
        task_id="task-rp",
        plan_id="plan-rp",
        current_plan_version=1,
        current_command_seq=1,
        completed_step_ids=["approach"],
        failed_step_id="grasp",
        last_successful_step_id="approach",
        current_scene_version=1,
    )
    result = LocalReplanningService(adapter=MockReplannerAdapter(), repository=repo).process(req)
    assert result.outcome == "REPLANNED"
    assert repo.get_replan_result("req-rp") is not None


def check_completed_steps_immutable() -> None:
    from cloud_edge_robot_arm.cloud.replanning.validators import CompletedStepsProtectionValidator
    from cloud_edge_robot_arm.contracts import SkillName, TaskStep

    validator = CompletedStepsProtectionValidator()
    original = [
        TaskStep(
            step_id="s1",
            skill=SkillName.APPROACH,
            parameters={},
            expected_duration_ms=1,
            timeout_ms=1,
            retry_limit=0,
        )
    ]
    changed = [
        TaskStep(
            step_id="s1",
            skill=SkillName.GRASP,
            parameters={},
            expected_duration_ms=1,
            timeout_ms=1,
            retry_limit=0,
        )
    ]
    ok, _ = validator.validate(["s1"], original, changed)
    assert ok is False


def check_cas_upgrade() -> None:
    from cloud_edge_robot_arm.repositories.event_autonomy.memory import (
        InMemoryEventAutonomyRepository,
    )

    assert (
        InMemoryEventAutonomyRepository().advance_plan_version_if_current("t", 0, 0, 1, 1) is True
    )


def check_old_result_rejected() -> None:
    from cloud_edge_robot_arm.repositories.event_autonomy.memory import (
        InMemoryEventAutonomyRepository,
    )

    repo = InMemoryEventAutonomyRepository()
    assert repo.advance_plan_version_if_current("t", 0, 0, 2, 2) is True
    assert repo.advance_plan_version_if_current("t", 0, 0, 1, 1) is False


def check_completion_evaluated() -> None:
    from cloud_edge_robot_arm.edge.completion_evaluator import CompletionEvaluator

    contract = make_contract(steps=make_contract().steps[:2], completion_criteria=["done"])
    result = CompletionEvaluator().evaluate(
        contract=contract,
        completed_step_ids=[s.step_id for s in contract.steps],
        completion_criteria_results={"done": False},
        final_safety_decision="ALLOW",
        final_robot_state={"connected": True},
        scene_version=1,
    )
    assert result.completed is False


def check_production_rejects_inmemory() -> None:
    from cloud_edge_robot_arm.edge.event_mode.controller import EventTriggeredModeController

    try:
        EventTriggeredModeController(runtime_profile="production")
    except ValueError:
        return
    raise AssertionError("production accepted default in-memory repository")


def check_openai_config_failfast() -> None:
    from cloud_edge_robot_arm.cloud.replanning.adapters import OpenAICompatibleReplannerAdapter

    try:
        OpenAICompatibleReplannerAdapter(base_url="", api_key="")
    except ValueError:
        return
    raise AssertionError("OpenAICompatibleReplannerAdapter accepted missing config")


def check_phase_regression(script: str) -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-1000:]


def check_phase_regressions() -> None:
    check_phase_regression("verify_phase3.py")
    check_phase_regression("verify_phase3_1.py")
    check_phase_regression("verify_phase3_2.py")
    check_phase_regression("verify_phase4.py")


def main() -> int:
    print("Phase 6.1 Acceptance Verification", flush=True)
    print("=" * 60, flush=True)
    checks: list[tuple[str, Callable[[], None]]] = [
        ("script self-compiles", check_compile_self),
        ("Phase 6 capabilities correct", check_capabilities),
        ("AUTO not advertised", check_no_auto),
        ("local failed step retries", check_retry_sequence),
        ("local retry does not skip step", check_retry_not_skip),
        ("retry re-runs safety checks", check_safety_rechecked),
        ("no unexecuted recovery success", check_no_fake_recovery_execute),
        ("retry budget atomic consumption", check_budget_atomic),
        ("retry budget restart recovery", check_budget_restart),
        ("event persistence", check_event_persistence),
        ("state machine persistence", check_state_persistence),
        ("FailureSummary persistence", check_failure_summary_persistence),
        ("LocalReplanningRequest persistence", check_replan_request_persistence),
        ("Outbox persistence", check_outbox_persistence),
        ("network recovery idempotent sending", check_network_recovery_idempotent_send),
        ("API persists events", check_api_persistence),
        ("Replan service calls adapter", check_replan_service_adapter),
        ("completed steps immutable", check_completed_steps_immutable),
        ("CAS version upgrade", check_cas_upgrade),
        ("old replan result rejected", check_old_result_rejected),
        ("completion criteria evaluated", check_completion_evaluated),
        ("production rejects default InMemory", check_production_rejects_inmemory),
        ("OpenAICompatible config fail-fast", check_openai_config_failfast),
        ("Phase 5 no regression", lambda: check_phase_regression("verify_phase5.py")),
        ("Phase 3/3.1/3.2/4 no regression", check_phase_regressions),
    ]
    passed = 0
    for i, (name, func) in enumerate(checks, start=1):
        if report(i, name, func):
            passed += 1
    total = len(checks)
    print(f"\n{passed}/{total} checks passed", flush=True)
    success = passed == total
    print(f"success={str(success).lower()}", flush=True)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
