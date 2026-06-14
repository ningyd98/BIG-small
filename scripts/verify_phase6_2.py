#!/usr/bin/env python3
"""Phase 6.2 final acceptance verification."""

from __future__ import annotations

import ast
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from cloud_edge_robot_arm.cloud.api.app import create_app
from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
from cloud_edge_robot_arm.cloud.replanning.adapters import RuleBasedReplannerAdapter
from cloud_edge_robot_arm.cloud.replanning.apply_service import ReplanApplyService
from cloud_edge_robot_arm.cloud.replanning.merge import ReplanMergeValidator
from cloud_edge_robot_arm.cloud.replanning.service import LocalReplanningService
from cloud_edge_robot_arm.config import AppConfig
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
from cloud_edge_robot_arm.edge.completion_evaluator import CompletionEvaluation, CompletionEvaluator
from cloud_edge_robot_arm.edge.event_mode.controller import EventTriggeredModeController
from cloud_edge_robot_arm.edge.runtime.task_executor import TaskExecutor
from cloud_edge_robot_arm.edge.safety.providers import MockSceneStateProvider, MockTelemetryProvider
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield
from cloud_edge_robot_arm.edge.summaries.completion import CompletionSummaryBuilder
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import (
    IdempotencyConflictError,
)
from cloud_edge_robot_arm.repositories.event_autonomy.sqlite import (
    SQLiteEventAutonomyRepository,
)
from cloud_edge_robot_arm.repositories.memory import InMemoryRepository
from cloud_edge_robot_arm.simulation.mock_robot import MockRobotAdapter, MockScene

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "cloud_edge_robot_arm"


def make_contract(*, task_id: str = "phase62-task", retry_limit: int = 1) -> TaskContract:
    now = datetime.now(UTC)
    return TaskContract(
        task_id=task_id,
        plan_version=1,
        command_seq=1,
        timestamp=now,
        control_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        issued_at=now,
        valid_until=now + timedelta(seconds=180),
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


def make_robot(*, grasp_failures: int = 0) -> MockRobotAdapter:
    scene = MockScene.with_default_pick_place_scene()
    obj = scene.objects.pop("red_cube")
    obj.object_id = "obj-1"
    scene.objects["obj-1"] = obj
    region = scene.regions.pop("bin_a")
    scene.regions["bin-a"] = type(region)(
        region_id="bin-a", center=region.center, radius_m=region.radius_m
    )
    return MockRobotAdapter(
        scene=scene,
        auto_connect=True,
        grasp_failures_remaining=grasp_failures,
    )


def response_for(request: LocalReplanningRequest, *, step_id: str) -> LocalReplanningResponse:
    return LocalReplanningResponse(
        request_id=request.request_id,
        outcome="REPLANNED",
        reason="phase 6.2 verification replan",
        new_steps=[
            TaskStep(
                step_id=step_id,
                skill=SkillName.GRASP,
                parameters={"object_id": "obj-1"},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=1,
            )
        ],
        new_plan_version=request.current_plan_version + 1,
        new_command_seq=request.current_command_seq + 1,
        planner_name="rule_based_replanner",
        created_at=datetime.now(UTC),
    )


def seed_replan_context(
    repo: SQLiteEventAutonomyRepository,
    *,
    task_id: str,
    include_active: bool = True,
    include_event: bool = True,
    include_summary: bool = True,
    include_checkpoint: bool = True,
) -> tuple[TaskContract, ExecutionCheckpoint, LocalReplanningRequest]:
    contract = make_contract(task_id=task_id)
    plan_id = f"plan-{task_id}"
    robot_id = "robot-unknown"
    now = datetime.now(UTC)
    if include_active:
        repo.save_active_contract(contract, plan_id=plan_id, robot_id=robot_id)
    if include_event:
        repo.save_event(
            EdgeEvent(
                event_id=f"evt-{task_id}",
                task_id=task_id,
                plan_id=plan_id,
                robot_id=robot_id,
                event_type=EdgeEventType.GRASP_FAILED,
                step_id="grasp",
                severity="ERROR",
                plan_version=1,
                command_seq=1,
                timestamp=now,
            )
        )
    if include_summary:
        repo.save_failure_summary(
            FailureSummary(
                summary_id=f"fs-{task_id}",
                task_id=task_id,
                plan_id=plan_id,
                robot_id=robot_id,
                failure_event_id=f"evt-{task_id}",
                failed_step_id="grasp",
                completed_step_ids=["approach"],
                reason="grasp failed after local retry",
                local_retry_count=1,
                recovery_hint="replan failed grasp",
                requested_replan_scope="CURRENT_STEP",
                plan_version=1,
                command_seq=1,
                timestamp=now,
            )
        )
    checkpoint = ExecutionCheckpoint(
        checkpoint_id=f"ckpt-{task_id}",
        task_id=task_id,
        plan_id=plan_id,
        robot_id=robot_id,
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
    if include_checkpoint:
        repo.save_execution_checkpoint(checkpoint)
    request = LocalReplanningRequest(
        request_id=f"req-{task_id}",
        trigger_event_id=f"evt-{task_id}",
        failure_summary_id=f"fs-{task_id}",
        robot_id=robot_id,
        task_id=task_id,
        plan_id=plan_id,
        current_plan_version=1,
        current_command_seq=1,
        requested_replan_scope="CURRENT_STEP",
        completed_step_ids=["approach"],
        failed_step_id="grasp",
        last_successful_step_id="approach",
        current_scene_version=1,
        idempotency_key=f"{task_id}:evt-{task_id}:replan",
    )
    return contract, checkpoint, request


def request_from_outbox(
    repo: SQLiteEventAutonomyRepository, task_id: str
) -> LocalReplanningRequest:
    request_ids = [m.request_id for m in repo.list_pending_outbox(task_id) if m.request_id]
    assert request_ids, "edge did not enqueue a LocalReplanningRequest"
    request = repo.get_replan_request(request_ids[-1])
    assert request is not None, "queued LocalReplanningRequest was not persisted"
    return request


def expect_conflict(func: Callable[[], object]) -> None:
    try:
        func()
    except IdempotencyConflictError:
        return
    raise AssertionError("expected IdempotencyConflictError")


def expect_value_error(func: Callable[[], object], message: str) -> None:
    try:
        func()
    except ValueError:
        return
    raise AssertionError(message)


def check_sqlite_restart_replan_resume() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "phase62.sqlite3")
        repo1 = SQLiteEventAutonomyRepository(db_path)
        robot = make_robot(grasp_failures=2)
        contract = make_contract(task_id="phase62-sqlite")
        first = TaskExecutor(
            robot=robot,
            shield=SafetyShield(),
            repository=InMemoryRepository(),
            event_controller=EventTriggeredModeController(repository=repo1),
        ).submit_contract(contract.model_dump(mode="json"))
        assert first.success is False
        assert first.error is not None and first.error.code == "CLOUD_REPLAN_REQUIRED"
        request = request_from_outbox(repo1, contract.task_id)
        checkpoint = repo1.get_latest_execution_checkpoint(contract.task_id)
        assert checkpoint is not None
        assert checkpoint.completed_step_ids == ["approach"]
        assert checkpoint.failed_step_id == "grasp"
        assert repo1.get_failure_summary(request.failure_summary_id) is not None
        assert repo1.get_active_contract(contract.task_id) is not None
        repo1.close()

        repo2 = SQLiteEventAutonomyRepository(db_path)
        persisted_request = repo2.get_replan_request(request.request_id)
        persisted_checkpoint = repo2.get_latest_execution_checkpoint(contract.task_id)
        persisted_active = repo2.get_active_contract(contract.task_id)
        persisted_event = repo2.get_event(request.trigger_event_id)
        persisted_summary = repo2.get_failure_summary(request.failure_summary_id)
        assert persisted_request is not None
        assert persisted_checkpoint is not None
        assert persisted_active is not None
        assert persisted_event is not None
        assert persisted_summary is not None
        response = LocalReplanningService(
            adapter=RuleBasedReplannerAdapter(),
            repository=repo2,
            apply_service=ReplanApplyService(repository=repo2, dispatcher=None),
        ).process(persisted_request, apply=True, dispatch=False)
        assert response.outcome == "REPLANNED"
        active = repo2.get_active_contract(contract.task_id)
        assert active is not None
        assert active.plan_version == 2
        assert active.command_seq == 2
        assert active.contract.steps[0].step_id == "approach"
        assert active.contract.steps[1].step_id != "grasp"
        assert repo2.get_replan_result(request.request_id) is not None
        assert repo2.get_replan_apply_record_for_request(request.request_id) is not None
        repo2.close()

        repo3 = SQLiteEventAutonomyRepository(db_path)
        active_after_restart = repo3.get_active_contract(contract.task_id)
        checkpoint_after_restart = repo3.get_latest_execution_checkpoint(contract.task_id)
        assert active_after_restart is not None
        assert checkpoint_after_restart is not None
        resumed = TaskExecutor(
            robot=robot,
            shield=SafetyShield(),
            repository=InMemoryRepository(),
            event_controller=EventTriggeredModeController(repository=repo3),
        ).resume_from_checkpoint(active_after_restart.contract, checkpoint_after_restart)
        assert resumed.success is True
        sequence = [entry.action_type for entry in robot.history]
        assert sequence == [
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
        assert sequence.count("APPROACH") == 1
        summary = repo3.get_completion_summary_for_task(contract.task_id)
        assert summary is not None
        assert summary.result == "SUCCESS_WITH_RECOVERY"
        assert repo3.list_events(contract.task_id)
        assert repo3.get_replan_result(request.request_id) is not None
        assert repo3.get_completion_summary(summary.summary_id) is not None
        repo3.close()


def check_completed_steps_and_cas() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = SQLiteEventAutonomyRepository(str(Path(tmp) / "cas.sqlite3"))
        contract, checkpoint, request = seed_replan_context(repo, task_id="phase62-cas")
        bad_response = response_for(request, step_id="approach")
        ok, errors = ReplanMergeValidator().validate_candidate(
            request=request,
            response=bad_response,
            active_contract=contract,
            checkpoint=checkpoint,
        )
        assert ok is False
        assert any("completed step approach" in error for error in errors)

        service = ReplanApplyService(repository=repo, dispatcher=None)
        first = service.apply(
            request=request,
            response=response_for(request, step_id="grasp-a"),
            checkpoint=checkpoint,
            dispatch=False,
        )
        assert first.applied is True
        stale_request = request.model_copy(
            update={"request_id": "req-phase62-cas-stale", "idempotency_key": "phase62-cas:stale"}
        )
        second = service.apply(
            request=stale_request,
            response=response_for(stale_request, step_id="grasp-b"),
            checkpoint=checkpoint,
            dispatch=False,
        )
        assert second.applied is False
        assert second.record.status == "VERSION_CONFLICT"
        active = repo.get_active_contract(request.task_id)
        assert active is not None
        assert active.plan_version == 2
        assert active.command_seq == 2
        assert active.contract.steps[1].step_id == "grasp-a"
        repo.close()


def check_idempotency_and_completion_dedup() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "idempotency.sqlite3"
        repo = SQLiteEventAutonomyRepository(str(db))
        _, _, request = seed_replan_context(repo, task_id="phase62-idem")
        saved = repo.save_replan_request(request)
        duplicate = repo.save_replan_request(request)
        assert duplicate == saved
        expect_conflict(
            lambda: repo.save_replan_request(
                request.model_copy(
                    update={
                        "request_id": "req-phase62-idem-other",
                        "failed_step_id": "lift",
                    }
                )
            )
        )

        contract = make_contract(task_id="phase62-completion")
        summary_a = CompletionSummaryBuilder().build(
            contract=contract,
            completed_step_ids=[step.step_id for step in contract.steps],
            completion_criteria_results={"object_inside_target_region": True},
            final_robot_state={"connected": True, "holding_object_id": None},
            final_target_state={"object_at_target": True},
            final_safety_decision="ALLOW",
        )
        summary_b = CompletionSummaryBuilder().build(
            contract=contract,
            completed_step_ids=[step.step_id for step in contract.steps],
            completion_criteria_results={"object_inside_target_region": True},
            final_robot_state={"connected": True, "holding_object_id": None},
            final_target_state={"object_at_target": True},
            final_safety_decision="ALLOW",
        )
        assert repo.save_completion_summary(summary_a) == repo.save_completion_summary(summary_b)
        count = sqlite3.connect(db).execute("SELECT COUNT(*) FROM completion_summaries").fetchone()
        assert count is not None and count[0] == 1
        repo.close()


def check_fail_closed_missing_context_and_identity() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        missing_cases = {
            "active contract not found": {"include_active": False},
            "trigger_event_id not found": {"include_event": False},
            "failure_summary_id not found": {"include_summary": False},
            "checkpoint not found": {"include_checkpoint": False},
        }
        for expected_error, options in missing_cases.items():
            repo = SQLiteEventAutonomyRepository(str(Path(tmp) / f"{expected_error[:6]}.sqlite3"))
            _, _, request = seed_replan_context(repo, task_id=expected_error[:12], **options)
            result = LocalReplanningService(
                adapter=RuleBasedReplannerAdapter(),
                repository=repo,
            ).process(request, apply=True)
            assert result.outcome == "REJECTED"
            assert expected_error in result.validation_errors
            repo.close()

        repo = SQLiteEventAutonomyRepository(str(Path(tmp) / "identity.sqlite3"))
        _, _, request = seed_replan_context(repo, task_id="phase62-identity")
        robot_bad = request.model_copy(update={"robot_id": "robot-other"})
        robot_result = LocalReplanningService(
            adapter=RuleBasedReplannerAdapter(),
            repository=repo,
        ).process(robot_bad, apply=True)
        assert robot_result.outcome == "REJECTED"
        assert "robot_id mismatch" in robot_result.validation_errors
        plan_bad = request.model_copy(
            update={
                "request_id": "req-phase62-plan-bad",
                "plan_id": "plan-other",
                "idempotency_key": "phase62-plan-bad",
            }
        )
        plan_result = LocalReplanningService(
            adapter=RuleBasedReplannerAdapter(),
            repository=repo,
        ).process(plan_bad, apply=True)
        assert plan_result.outcome == "REJECTED"
        assert "summary.plan_id mismatch" in plan_result.validation_errors
        repo.close()


def check_completion_evidence_model() -> None:
    contract = make_contract(task_id="phase62-evidence")
    completed = [step.step_id for step in contract.steps]
    evaluator = CompletionEvaluator()

    def evaluate(
        *,
        completed_step_ids: list[str] = completed,
        completion_criteria_results: dict[str, bool] | None = None,
        final_safety_decision: str = "ALLOW",
        final_robot_state: dict[str, object] | None = None,
        final_target_state: dict[str, object] | None = None,
        last_scene_update_at: datetime | None = None,
        scene_stale_threshold_ms: int = 5000,
    ) -> CompletionEvaluation:
        return evaluator.evaluate(
            contract=contract,
            completed_step_ids=completed_step_ids,
            completion_criteria_results=completion_criteria_results
            if completion_criteria_results is not None
            else {"object_inside_target_region": True},
            final_safety_decision=final_safety_decision,
            final_robot_state=final_robot_state
            if final_robot_state is not None
            else {"connected": True, "holding_object_id": None},
            final_target_state=final_target_state
            if final_target_state is not None
            else {"object_at_target": True},
            scene_version=1,
            last_scene_update_at=last_scene_update_at,
            scene_stale_threshold_ms=scene_stale_threshold_ms,
        )

    stale = evaluator.evaluate(
        contract=contract,
        completed_step_ids=completed,
        completion_criteria_results={"object_inside_target_region": True},
        final_safety_decision="ALLOW",
        final_robot_state={"connected": True, "holding_object_id": None},
        final_target_state={"object_at_target": True},
        scene_version=1,
        last_scene_update_at=datetime.now(UTC) - timedelta(seconds=10),
        scene_stale_threshold_ms=1,
    )
    assert stale.completed is False
    assert "CHECK_7_SCENE_STALE" in stale.failed_checks
    unverified_scene = evaluate()
    assert "SCENE_FRESHNESS_UNVERIFIED" in unverified_scene.reason_codes
    assert evaluate(completion_criteria_results={}).completed is False
    assert evaluate(completed_step_ids=completed[:-1]).completed is False
    assert evaluate(final_safety_decision="REJECT").completed is False
    assert evaluate(final_robot_state={"connected": False}).completed is False
    assert evaluate(final_target_state={"object_at_target": False}).completed is False
    assert evaluate().completed is True

    repo = SQLiteEventAutonomyRepository(":memory:")
    client = TestClient(create_app(PlanningPipeline(planner=MockPlannerAdapter()), event_repo=repo))
    forged = client.post(
        "/api/v1/tasks/phase62-forged/completion",
        json={"task_id": "phase62-forged", "completed_step_ids": [], "result": "SUCCESS"},
    )
    assert forged.status_code == 422
    assert repo.get_completion_summary_for_task("phase62-forged") is None
    repo.close()


def check_production_config_blocks_test_doubles() -> None:
    expect_value_error(
        lambda: EventTriggeredModeController(runtime_profile="production"),
        "production controller accepted default repository",
    )
    expect_value_error(
        lambda: AppConfig.from_env(
            {
                "RUNTIME_PROFILE": "production",
                "DATABASE_URL": "sqlite:////var/lib/big-small/robot_control.db",
                "MQTT_BROKER_URL": "mqtt://broker.internal:1883",
                "PLANNER_API_ENDPOINT": "https://planner.internal/v1/chat/completions",
                "PLANNER_API_KEY": "prod-secret-key",
                "ROBOT_ADAPTER": "mock_robot",
                "TELEMETRY_PROVIDER": "robot_sdk",
                "SCENE_STATE_PROVIDER": "vision_pipeline",
                "SUPERVISION_REPOSITORY": "sqlite",
                "SUPERVISION_SCHEDULER": "asyncio",
            }
        ),
        "production config accepted a test double",
    )
    robot = make_robot()
    expect_value_error(
        lambda: TaskExecutor(
            robot=robot,
            shield=SafetyShield(),
            runtime_profile="production",
            telemetry_provider=MockTelemetryProvider(),
            scene_provider=MockSceneStateProvider(robot),
        ),
        "production executor accepted mock providers",
    )


def check_phase5_regression() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_phase5.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-1000:]


def check_no_stub_success_paths() -> None:
    skipped_parts = {"simulation"}
    skipped_files = {
        SRC / "repositories" / "base.py",
    }
    markers = ("TODO", "FIXME", "placeholder", "NotImplemented")
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if skipped_parts.intersection(path.parts) or path in skipped_files:
            continue
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {marker}")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Pass):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} contains pass")
    task_executor = (SRC / "edge" / "runtime" / "task_executor.py").read_text(encoding="utf-8")
    assert "CompletionEvaluator(repository=completion_repository).evaluate" in task_executor
    assert offenders == [], "\n".join(offenders)


def run_check(index: int, name: str, func: Callable[[], None]) -> None:
    print(f"{index}. {name} ...", flush=True)
    func()
    print(f"{index}. {name}: OK", flush=True)


def main() -> int:
    checks: list[tuple[str, Callable[[], None]]] = [
        (
            "SQLite restart, persisted context, replan apply, and checkpoint resume",
            check_sqlite_restart_replan_resume,
        ),
        ("completed steps are immutable and stale CAS loses", check_completed_steps_and_cas),
        (
            "idempotency conflicts and duplicate completion evidence",
            check_idempotency_and_completion_dedup,
        ),
        (
            "missing context and identity mismatches fail closed",
            check_fail_closed_missing_context_and_identity,
        ),
        ("completion evidence model fails closed", check_completion_evidence_model),
        (
            "production configuration blocks test doubles",
            check_production_config_blocks_test_doubles,
        ),
        ("Phase 5 regression script", check_phase5_regression),
        ("no stub success paths in production source", check_no_stub_success_paths),
    ]
    print("Phase 6.2 Final Acceptance Verification", flush=True)
    print("=" * 60, flush=True)
    for index, (name, func) in enumerate(checks, start=1):
        run_check(index, name, func)
    print(f"\n{len(checks)}/{len(checks)} checks passed", flush=True)
    print("success=true", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
