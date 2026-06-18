"""Phase 6.2 重规划恢复回归测试，覆盖安全边界、证据契约和关键失败路径。

Phase 6.2 replanning apply and checkpoint resume tests."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from cloud_edge_robot_arm.cloud.api.app import create_app
from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
from cloud_edge_robot_arm.cloud.replanning.adapters import (
    RuleBasedReplannerAdapter,
)
from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService
from cloud_edge_robot_arm.cloud.replanning.service import LocalReplanningService
from cloud_edge_robot_arm.contracts import (
    ControlMode,
    FailurePolicy,
    SafetyConstraints,
    SkillName,
    TaskContract,
    TaskStep,
    TaskTarget,
)
from cloud_edge_robot_arm.contracts.models import (
    EdgeEvent,
    EdgeEventType,
    ExecutionCheckpoint,
    FailureSummary,
    LocalReplanningRequest,
    LocalReplanningResponse,
)
from cloud_edge_robot_arm.edge.event_mode.controller import EventTriggeredModeController
from cloud_edge_robot_arm.edge.runtime.task_executor import TaskExecutor
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield
from cloud_edge_robot_arm.repositories.event_autonomy.memory import InMemoryEventAutonomyRepository
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import IdempotencyConflictError
from cloud_edge_robot_arm.repositories.memory import InMemoryRepository
from cloud_edge_robot_arm.simulation.mock_robot import MockRobotAdapter, MockScene


def _request(
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
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "root_path": "",
            "state": {},
        },
        receive,
        send,
    )
    text = response_body.decode("utf-8")
    return {"status_code": status_code, "json": json.loads(text) if text else None}


def _contract(*, task_id: str = "task-phase62", retry_limit: int = 1) -> TaskContract:
    now = datetime.now(UTC)
    return TaskContract(
        task_id=task_id,
        plan_version=1,
        command_seq=1,
        timestamp=now,
        control_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        issued_at=now,
        valid_until=now + timedelta(seconds=120),
        user_instruction="Pick object and place it in bin",
        scene_version=1,
        expected_scene_version=1,
        task_target=TaskTarget(object_id="obj-1", object_class="cube", target_region_id="bin-a"),
        steps=[
            TaskStep(
                step_id="approach",
                skill=SkillName.APPROACH,
                parameters={"object_id": "obj-1"},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=0,
            ),
            TaskStep(
                step_id="grasp",
                skill=SkillName.GRASP,
                parameters={"object_id": "obj-1"},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=retry_limit,
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
                parameters={"region_id": "bin-a"},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=0,
                preconditions=["object_attached"],
            ),
            TaskStep(
                step_id="place",
                skill=SkillName.PLACE,
                parameters={"region_id": "bin-a"},
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
                parameters={"object_id": "obj-1", "region_id": "bin-a"},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=0,
            ),
        ],
        safety_constraints=SafetyConstraints(
            max_joint_velocity=1.0,
            max_tcp_velocity=0.5,
            minimum_safe_height=0.08,
            workspace_id="ws-1",
        ),
        failure_policy=FailurePolicy(
            local_retry_limit=retry_limit,
            on_timeout="pause",
            on_safety_rejection="stop",
            on_network_loss="pause",
        ),
        completion_criteria=["object_inside_target_region"],
    )


def _robot(*, grasp_failures: int = 0) -> MockRobotAdapter:
    scene = MockScene.with_default_pick_place_scene()
    obj = scene.objects.pop("red_cube")
    obj.object_id = "obj-1"
    scene.objects["obj-1"] = obj
    region = scene.regions.pop("bin_a")
    scene.regions["bin-a"] = type(region)(
        region_id="bin-a", center=region.center, radius_m=region.radius_m
    )
    return MockRobotAdapter(scene=scene, auto_connect=True, grasp_failures_remaining=grasp_failures)


def _request_from_outbox(
    repo: InMemoryEventAutonomyRepository, task_id: str
) -> LocalReplanningRequest:
    request_ids = [m.request_id for m in repo.list_pending_outbox(task_id) if m.request_id]
    assert request_ids
    request = repo.get_replan_request(request_ids[-1])
    assert request is not None
    return request


def test_phase62_full_replan_apply_resume_closure() -> None:
    contract = _contract(retry_limit=1)
    robot = _robot(grasp_failures=2)
    runtime_repo = InMemoryRepository()
    event_repo = InMemoryEventAutonomyRepository()
    controller = EventTriggeredModeController(repository=event_repo)

    first = TaskExecutor(
        robot=robot,
        shield=SafetyShield(),
        repository=runtime_repo,
        event_controller=controller,
    ).submit_contract(contract.model_dump(mode="json"))

    assert first.success is False
    assert first.error is not None and first.error.code == "CLOUD_REPLAN_REQUIRED"
    assert [entry.action_type for entry in robot.history] == ["APPROACH", "GRASP", "GRASP"]
    request = _request_from_outbox(event_repo, contract.task_id)
    failed_checkpoint = event_repo.get_latest_execution_checkpoint(contract.task_id)
    assert failed_checkpoint is not None
    assert failed_checkpoint.completed_step_ids == ["approach"]
    assert failed_checkpoint.failed_step_id == "grasp"
    assert event_repo.get_failure_summary(request.failure_summary_id) is not None
    assert event_repo.get_active_contract(contract.task_id).plan_version == 1  # type: ignore[union-attr]

    response = LocalReplanningService(
        adapter=RuleBasedReplannerAdapter(),
        repository=event_repo,
        apply_service=ReplanApplyService(repository=event_repo, dispatcher=None),
    ).process(request, apply=True, dispatch=False)

    assert response.outcome == "REPLANNED"
    active = event_repo.get_active_contract(contract.task_id)
    assert active is not None
    assert active.plan_version == 2
    assert active.command_seq == 2
    assert active.contract.steps[0].step_id == "approach"
    assert active.contract.steps[1].skill == SkillName.GRASP
    assert active.contract.steps[1].step_id != "grasp"
    ack = event_repo.get_command_ack(request.request_id)
    assert ack is not None and ack.accepted and ack.status == "ACCEPTED"

    resumed = TaskExecutor(
        robot=robot,
        shield=SafetyShield(),
        repository=runtime_repo,
        event_controller=controller,
    ).resume_from_checkpoint(active.contract, failed_checkpoint)

    assert resumed.success is True
    assert [entry.action_type for entry in robot.history] == [
        "APPROACH",
        "GRASP",
        "GRASP",
        "GRASP",
        "LIFT",
        "MOVE_TO_REGION",
        "PLACE",
        "RELEASE",
        "VERIFY_RESULT",
    ]
    assert [entry.action_type for entry in robot.history].count("APPROACH") == 1
    summary = event_repo.get_completion_summary_for_task(contract.task_id)
    assert summary is not None
    assert summary.result == "SUCCESS_WITH_RECOVERY"
    final_checkpoint = event_repo.get_latest_execution_checkpoint(contract.task_id)
    assert final_checkpoint is not None
    assert final_checkpoint.execution_state == "COMPLETED"
    assert final_checkpoint.plan_version == 2


def test_phase62_completed_grasp_not_regenerated_after_place_failure() -> None:
    contract = _contract(task_id="task-place-fail", retry_limit=1)
    repo = InMemoryEventAutonomyRepository()
    repo.save_active_contract(contract, plan_id="plan-task-place-fail", robot_id="robot-unknown")
    now = datetime.now(UTC)
    event = repo.save_event(
        EdgeEvent(
            task_id=contract.task_id,
            plan_version=1,
            command_seq=1,
            timestamp=now,
            event_id="evt-place",
            event_type=EdgeEventType.PLACE_FAILED,
            step_id="place",
            severity="ERROR",
            robot_id="robot-unknown",
            plan_id="plan-task-place-fail",
            scene_version=1,
        )
    )
    summary = repo.save_failure_summary(
        FailureSummary(
            task_id=contract.task_id,
            plan_version=1,
            command_seq=1,
            timestamp=now,
            summary_id="fs-place",
            failure_event_id=event.event_id,
            failed_step_id="place",
            completed_step_ids=["approach", "grasp", "lift", "move-region"],
            reason="place failed",
            local_retry_count=1,
            recovery_hint="replan place",
            robot_id="robot-unknown",
            plan_id="plan-task-place-fail",
            requested_replan_scope="CURRENT_STEP",
        )
    )
    checkpoint = ExecutionCheckpoint(
        checkpoint_id="ckpt-place",
        task_id=contract.task_id,
        plan_id="plan-task-place-fail",
        robot_id="robot-unknown",
        plan_version=1,
        command_seq=1,
        current_step_id="place",
        current_step_index=4,
        failed_step_id="place",
        last_successful_step_id="move-region",
        completed_step_ids=["approach", "grasp", "lift", "move-region"],
        pending_step_ids=["place", "release", "verify"],
        scene_version=1,
        execution_state="WAITING_CLOUD_REPLAN",
    )
    repo.save_execution_checkpoint(checkpoint)
    request = repo.save_replan_request(
        LocalReplanningRequest(
            request_id="req-place",
            trigger_event_id=event.event_id,
            failure_summary_id=summary.summary_id,
            robot_id="robot-unknown",
            task_id=contract.task_id,
            plan_id="plan-task-place-fail",
            current_plan_version=1,
            current_command_seq=1,
            requested_replan_scope="CURRENT_STEP",
            completed_step_ids=list(checkpoint.completed_step_ids),
            failed_step_id="place",
            last_successful_step_id="move-region",
            current_scene_version=1,
        )
    )
    response = LocalReplanningService(adapter=RuleBasedReplannerAdapter(), repository=repo).process(
        request,
        apply=True,
        dispatch=False,
    )
    assert response.outcome == "REPLANNED"
    active = repo.get_active_contract(contract.task_id)
    assert active is not None
    grasp_steps = [step for step in active.contract.steps if step.skill == SkillName.GRASP]
    assert len(grasp_steps) == 1
    assert grasp_steps[0].step_id == "grasp"


def test_phase62_old_replan_late_result_is_rejected() -> None:
    contract = _contract(task_id="task-late", retry_limit=1)
    repo = InMemoryEventAutonomyRepository()
    repo.save_active_contract(contract, plan_id="plan-task-late", robot_id="robot-unknown")
    now = datetime.now(UTC)
    event = repo.save_event(
        EdgeEvent(
            task_id=contract.task_id,
            plan_version=1,
            command_seq=1,
            timestamp=now,
            event_id="evt-late",
            event_type=EdgeEventType.GRASP_FAILED,
            step_id="grasp",
            severity="ERROR",
            robot_id="robot-unknown",
            plan_id="plan-task-late",
        )
    )
    summary = repo.save_failure_summary(
        FailureSummary(
            task_id=contract.task_id,
            plan_version=1,
            command_seq=1,
            timestamp=now,
            summary_id="fs-late",
            failure_event_id=event.event_id,
            failed_step_id="grasp",
            completed_step_ids=["approach"],
            reason="failed",
            local_retry_count=1,
            recovery_hint="replan",
            robot_id="robot-unknown",
            plan_id="plan-task-late",
        )
    )
    checkpoint = repo.save_execution_checkpoint(
        ExecutionCheckpoint(
            checkpoint_id="ckpt-late",
            task_id=contract.task_id,
            plan_id="plan-task-late",
            robot_id="robot-unknown",
            plan_version=1,
            command_seq=1,
            current_step_id="grasp",
            current_step_index=1,
            failed_step_id="grasp",
            completed_step_ids=["approach"],
            pending_step_ids=["grasp", "lift", "move-region", "place", "release", "verify"],
            scene_version=1,
            execution_state="WAITING_CLOUD_REPLAN",
        )
    )
    req_a = LocalReplanningRequest(
        request_id="req-a",
        trigger_event_id=event.event_id,
        failure_summary_id=summary.summary_id,
        robot_id="robot-unknown",
        task_id=contract.task_id,
        plan_id="plan-task-late",
        current_plan_version=1,
        current_command_seq=1,
        requested_replan_scope="CURRENT_STEP",
        completed_step_ids=["approach"],
        failed_step_id="grasp",
        current_scene_version=1,
    )
    req_b = req_a.model_copy(update={"request_id": "req-b", "idempotency_key": "req-b"})
    service = ReplanApplyService(repository=repo, dispatcher=None)
    resp_b = LocalReplanningResponse(
        request_id="req-b",
        outcome="REPLANNED",
        reason="new",
        new_steps=[
            TaskStep(
                step_id="grasp-b",
                skill=SkillName.GRASP,
                parameters={"object_id": "obj-1"},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=1,
            )
        ],
        new_plan_version=2,
        new_command_seq=2,
    )
    applied_b = service.apply(request=req_b, response=resp_b, checkpoint=checkpoint, dispatch=False)
    assert applied_b.applied
    resp_a = resp_b.model_copy(
        update={
            "request_id": "req-a",
            "new_steps": [resp_b.new_steps[0].model_copy(update={"step_id": "grasp-a"})],
        }
    )
    applied_a = service.apply(request=req_a, response=resp_a, checkpoint=checkpoint, dispatch=False)
    assert not applied_a.applied
    assert applied_a.record.status == "VERSION_CONFLICT"
    assert repo.get_active_contract(contract.task_id).contract.steps[1].step_id == "grasp-b"  # type: ignore[union-attr]


def test_phase62_idempotency_conflict() -> None:
    repo = InMemoryEventAutonomyRepository()
    now = datetime.now(UTC)
    event = EdgeEvent(
        task_id="task-idem",
        plan_version=1,
        command_seq=1,
        timestamp=now,
        event_id="evt-idem",
        event_type=EdgeEventType.GRASP_FAILED,
        severity="ERROR",
    )
    repo.save_event(event)
    assert repo.save_event(event).event_id == "evt-idem"
    with pytest.raises(IdempotencyConflictError):
        repo.save_event(event.model_copy(update={"severity": "WARNING"}))


def test_phase62_completion_api_rejects_forged_success() -> None:
    repo = InMemoryEventAutonomyRepository()
    app = create_app(PlanningPipeline(planner=MockPlannerAdapter()), event_repo=repo)
    response = _request(
        app,
        "POST",
        "/api/v1/tasks/task-forged/completion",
        json_body={"task_id": "task-forged", "completed_step_ids": [], "result": "SUCCESS"},
    )
    assert response["status_code"] == 422
    assert repo.get_completion_summary_for_task("task-forged") is None


def test_phase62_scene_stale_blocks_completion_evaluator() -> None:
    from cloud_edge_robot_arm.edge.completion_evaluator import CompletionEvaluator

    contract = _contract(task_id="task-stale", retry_limit=1)
    old = datetime.now(UTC) - timedelta(seconds=10)
    result = CompletionEvaluator().evaluate(
        contract=contract,
        completed_step_ids=[step.step_id for step in contract.steps],
        completion_criteria_results={"object_inside_target_region": True},
        final_safety_decision="ALLOW",
        final_robot_state={"connected": True, "holding_object_id": None},
        final_target_state={"object_at_target": True},
        scene_version=1,
        last_scene_update_at=old,
        scene_stale_threshold_ms=1,
    )
    assert not result.completed
    assert "CHECK_7_SCENE_STALE" in result.failed_checks


def test_phase62_two_fastapi_apps_have_isolated_repositories() -> None:
    repo_a = InMemoryEventAutonomyRepository()
    repo_b = InMemoryEventAutonomyRepository()
    app_a = create_app(PlanningPipeline(planner=MockPlannerAdapter()), event_repo=repo_a)
    app_b = create_app(PlanningPipeline(planner=MockPlannerAdapter()), event_repo=repo_b)
    payload = {
        "event_id": "evt-app-a",
        "task_id": "task-app-a",
        "event_type": "GRASP_FAILED",
        "severity": "ERROR",
        "robot_id": "robot-a",
        "plan_version": 1,
        "command_seq": 1,
    }
    assert (
        _request(app_a, "POST", "/api/v1/robots/robot-a/events", json_body=payload)["status_code"]
        == 201
    )
    assert _request(app_a, "GET", "/api/v1/events/evt-app-a")["status_code"] == 200
    assert _request(app_b, "GET", "/api/v1/events/evt-app-a")["status_code"] == 404


def test_phase62_replanned_empty_steps_rejected() -> None:
    contract = _contract(task_id="task-empty", retry_limit=1)
    repo = InMemoryEventAutonomyRepository()
    repo.save_active_contract(contract, plan_id="plan-task-empty", robot_id="robot-unknown")
    now = datetime.now(UTC)
    event = repo.save_event(
        EdgeEvent(
            task_id=contract.task_id,
            plan_version=1,
            command_seq=1,
            timestamp=now,
            event_id="evt-empty",
            event_type=EdgeEventType.GRASP_FAILED,
            step_id="grasp",
            severity="ERROR",
            robot_id="robot-unknown",
            plan_id="plan-task-empty",
        )
    )
    summary = repo.save_failure_summary(
        FailureSummary(
            task_id=contract.task_id,
            plan_version=1,
            command_seq=1,
            timestamp=now,
            summary_id="fs-empty",
            failure_event_id=event.event_id,
            failed_step_id="grasp",
            completed_step_ids=["approach"],
            reason="failed",
            local_retry_count=1,
            recovery_hint="replan",
            robot_id="robot-unknown",
            plan_id="plan-task-empty",
        )
    )
    checkpoint = repo.save_execution_checkpoint(
        ExecutionCheckpoint(
            checkpoint_id="ckpt-empty",
            task_id=contract.task_id,
            plan_id="plan-task-empty",
            robot_id="robot-unknown",
            plan_version=1,
            command_seq=1,
            current_step_id="grasp",
            current_step_index=1,
            failed_step_id="grasp",
            completed_step_ids=["approach"],
            pending_step_ids=["grasp"],
            scene_version=1,
            execution_state="WAITING_CLOUD_REPLAN",
        )
    )
    request = LocalReplanningRequest(
        request_id="req-empty",
        trigger_event_id=event.event_id,
        failure_summary_id=summary.summary_id,
        robot_id="robot-unknown",
        task_id=contract.task_id,
        plan_id="plan-task-empty",
        current_plan_version=1,
        current_command_seq=1,
        requested_replan_scope="CURRENT_STEP",
        completed_step_ids=["approach"],
        failed_step_id="grasp",
        current_scene_version=1,
    )
    response = LocalReplanningResponse(
        request_id="req-empty",
        outcome="REPLANNED",
        reason="bad",
        new_steps=[],
        new_plan_version=2,
        new_command_seq=2,
    )
    applied = ReplanApplyService(repository=repo).apply(
        request=request,
        response=response,
        checkpoint=checkpoint,
        dispatch=False,
    )
    assert not applied.applied
    assert repo.get_active_contract(contract.task_id).plan_version == 1  # type: ignore[union-attr]
