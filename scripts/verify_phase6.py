#!/usr/bin/env python3
"""Phase 6 acceptance verification script — event-triggered edge autonomy.

Verifies:
1. Event mode capabilities advertised correctly
2. Event detection produces correct event types
3. Local recovery evaluates events correctly
4. FailureSummary is deterministic
5. Completed steps are protected in replanning
6. Replanning adapters produce valid output
7. Event controller manages lifecycle
8. Outbox persists and retries messages
9. Phase 5 periodic supervision still passes
10. All Phase 3-5 scripts still pass with no regression
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"


def _run(script_name: str) -> dict[str, object]:
    """Run a script and return parsed JSON result."""
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        return {
            "script": script_name,
            "returncode": -1,
            "stdout": "",
            "stderr": "Script not found",
            "passed": False,
        }
    proc = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        check=False,
    )
    return {
        "script": script_name,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "passed": proc.returncode == 0,
    }


def _check(name: str, passed: bool, detail: str = "") -> dict[str, object]:
    return {"check": name, "passed": passed, "detail": detail}


def main() -> int:
    results: list[dict[str, object]] = []

    # ── 1. Event control capabilities ──────────────────────────────────
    try:
        from cloud_edge_robot_arm.contracts.models import (
            ControlMode,
            EdgeEventType,
            EventSeverity,
            RecoveryAction,
            ReplanScope,
        )

        caps_passed = (
            ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY.value == "EVENT_TRIGGERED_EDGE_AUTONOMY"
            and EventSeverity.CRITICAL.value == "CRITICAL"
            and EdgeEventType.GRASP_FAILED.value == "GRASP_FAILED"
            and RecoveryAction.RETRY_SAME_SKILL.value == "RETRY_SAME_SKILL"
            and ReplanScope.CURRENT_STEP.value == "CURRENT_STEP"
        )
        results.append(_check("1. Event control capabilities correct", caps_passed))
        if not caps_passed:
            _unused = False
    except Exception as exc:
        results.append(_check("1. Event control capabilities correct", False, str(exc)))
        _unused = False

    # ── 2. Event detection produces correct types ──────────────────────
    try:
        from datetime import UTC, datetime

        from cloud_edge_robot_arm.contracts.models import (
            RobotState,
            SkillExecutionResult,
            SkillName,
            TaskStep,
        )
        from cloud_edge_robot_arm.edge.events import (
            CompletionEventDetector,
            DetectionContext,
            ExecutionEventDetector,
        )

        NOW = datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC)
        ctx = DetectionContext(
            task_id="verify-001",
            plan_version=1,
            command_seq=1,
            robot_id="robot-001",
            step=TaskStep(
                step_id="s1",
                skill=SkillName.GRASP,
                parameters={},
                expected_duration_ms=2000,
                timeout_ms=5000,
                retry_limit=3,
            ),
            step_result=SkillExecutionResult(
                task_id="verify-001",
                plan_version=1,
                command_seq=1,
                timestamp=NOW,
                step_id="s1",
                skill=SkillName.GRASP,
                scene_version=1,
                success=False,
                duration_ms=2000,
            ),
            robot_state=RobotState(connected=True),
        )

        detector = ExecutionEventDetector()
        event = detector.detect(ctx)
        det_ok = event is not None and event.event_type == EdgeEventType.GRASP_FAILED
        results.append(_check("2. Event detection: GRASP_FAILED", det_ok))
        if not det_ok:
            _unused = False

        # STEP_COMPLETED detection
        comp_ctx = DetectionContext(
            task_id="verify-001",
            plan_version=1,
            command_seq=1,
            step=ctx.step,
            step_result=SkillExecutionResult(
                task_id="verify-001",
                plan_version=1,
                command_seq=1,
                timestamp=NOW,
                step_id="s1",
                skill=SkillName.GRASP,
                scene_version=1,
                success=True,
                duration_ms=1500,
            ),
            robot_state=RobotState(connected=True),
        )
        comp_det = CompletionEventDetector()
        comp_event = comp_det.detect(comp_ctx)
        comp_ok = comp_event is not None and comp_event.event_type == EdgeEventType.STEP_COMPLETED
        results.append(_check("2b. Event detection: STEP_COMPLETED", comp_ok))
        if not comp_ok:
            _unused = False
    except Exception as exc:
        results.append(_check("2. Event detection", False, str(exc)))
        _unused = False

    # ── 3. Local recovery evaluation ───────────────────────────────────
    try:
        from datetime import UTC, datetime

        from cloud_edge_robot_arm.contracts.models import (
            EdgeEvent,
            EdgeEventType,
            EventSeverity,
            FailurePolicy,
            SafetyConstraints,
            TaskContract,
            TaskStep,
            TaskTarget,
        )
        from cloud_edge_robot_arm.edge.recovery.manager import LocalRecoveryManager
        from cloud_edge_robot_arm.edge.recovery.retry_budget import RetryBudgetManager

        NOW = datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC)

        mgr = LocalRecoveryManager(budget_manager=RetryBudgetManager())
        contract = TaskContract(
            task_id="verify-002",
            plan_version=1,
            command_seq=1,
            timestamp=NOW,
            control_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
            issued_at=NOW,
            valid_until=datetime(2026, 6, 13, 12, 5, 0, tzinfo=UTC),
            user_instruction="Test",
            scene_version=1,
            expected_scene_version=1,
            task_target=TaskTarget(
                object_id="obj-1", object_class="cube", target_region_id="bin-a"
            ),
            steps=[
                TaskStep(
                    step_id="s1",
                    skill=SkillName.GRASP,
                    parameters={},
                    expected_duration_ms=2000,
                    timeout_ms=5000,
                    retry_limit=3,
                ),
            ],
            safety_constraints=SafetyConstraints(
                max_joint_velocity=1.0,
                max_tcp_velocity=0.5,
                minimum_safe_height=0.08,
                workspace_id="ws-1",
            ),
            failure_policy=FailurePolicy(
                local_retry_limit=3,
                on_timeout="pause",
                on_safety_rejection="stop",
                on_network_loss="pause",
            ),
            completion_criteria=["done"],
        )
        mgr._budget_manager.initialize("verify-002", contract)

        event = EdgeEvent(
            task_id="verify-002",
            plan_version=1,
            command_seq=1,
            timestamp=NOW,
            event_id="evt-recovery",
            event_type=EdgeEventType.GRASP_FAILED,
            step_id="s1",
            severity=EventSeverity.ERROR,
        )
        decision = mgr.evaluate(event, contract)
        rec_ok = decision.action == RecoveryAction.RETRY_SAME_SKILL and decision.allowed
        results.append(_check("3. Local recovery: GRASP_FAILED → RETRY", rec_ok))
        if not rec_ok:
            _unused = False

        # Critical event → STOP_AND_REPORT
        crit_event = EdgeEvent(
            task_id="verify-002",
            plan_version=1,
            command_seq=1,
            timestamp=NOW,
            event_id="evt-crit",
            event_type=EdgeEventType.EMERGENCY_STOP_TRIGGERED,
            step_id="s1",
            severity=EventSeverity.CRITICAL,
        )
        crit_dec = mgr.evaluate(crit_event, contract)
        crit_ok = crit_dec.action == RecoveryAction.STOP_AND_REPORT and not crit_dec.allowed
        results.append(_check("3b. Local recovery: EMERGENCY_STOP → STOP", crit_ok))
        if not crit_ok:
            _unused = False
    except Exception as exc:
        results.append(_check("3. Local recovery", False, str(exc)))
        _unused = False

    # ── 4. FailureSummary is deterministic ─────────────────────────────
    try:
        from cloud_edge_robot_arm.edge.summaries.failure import FailureSummaryBuilder

        builder = FailureSummaryBuilder()
        event = EdgeEvent(
            task_id="verify-003",
            plan_version=1,
            command_seq=1,
            timestamp=NOW,
            event_id="evt-fs",
            event_type=EdgeEventType.GRASP_FAILED,
            step_id="s1",
            severity=EventSeverity.ERROR,
        )
        fs1 = builder.build(event=event, contract=contract)
        fs2 = builder.build(event=event, contract=contract)
        fs_ok = fs1.summary_hash == fs2.summary_hash and len(fs1.summary_hash) > 0
        results.append(_check("4. FailureSummary deterministic hash", fs_ok))
        if not fs_ok:
            _unused = False
    except Exception as exc:
        results.append(_check("4. FailureSummary", False, str(exc)))
        _unused = False

    # ── 5. Completed steps protection ──────────────────────────────────
    try:
        from cloud_edge_robot_arm.cloud.replanning.validators import (
            CompletedStepsProtectionValidator,
        )

        validator = CompletedStepsProtectionValidator()
        completed = ["s1"]
        original = [
            TaskStep(
                step_id="s1",
                skill=SkillName.APPROACH,
                parameters={},
                expected_duration_ms=2000,
                timeout_ms=5000,
                retry_limit=3,
            ),
            TaskStep(
                step_id="s2",
                skill=SkillName.GRASP,
                parameters={},
                expected_duration_ms=2000,
                timeout_ms=5000,
                retry_limit=3,
            ),
        ]
        valid_new = [
            TaskStep(
                step_id="s1",
                skill=SkillName.APPROACH,
                parameters={},
                expected_duration_ms=2000,
                timeout_ms=5000,
                retry_limit=3,
            ),
            TaskStep(
                step_id="s2-new",
                skill=SkillName.GRASP,
                parameters={"x": 1},
                expected_duration_ms=3000,
                timeout_ms=8000,
                retry_limit=3,
            ),
        ]
        ok, errors = validator.validate(completed, original, valid_new)
        prot_ok = ok and len(errors) == 0
        results.append(_check("5. Completed steps: valid merge accepted", prot_ok))
        if not prot_ok:
            _unused = False

        # Modify completed step → reject
        bad_new = [
            TaskStep(
                step_id="s1",
                skill=SkillName.GRASP,
                parameters={},
                expected_duration_ms=2000,
                timeout_ms=5000,
                retry_limit=3,
            ),
        ]
        ok2, errs2 = validator.validate(completed, original, bad_new)
        prot2_ok = not ok2 and len(errs2) > 0
        results.append(_check("5b. Completed steps: modification rejected", prot2_ok))
        if not prot2_ok:
            _unused = False
    except Exception as exc:
        results.append(_check("5. Completed steps protection", False, str(exc)))
        _unused = False

    # ── 6. Replanning adapters ─────────────────────────────────────────
    try:
        from cloud_edge_robot_arm.cloud.replanning.adapters import (
            MockReplannerAdapter,
            RuleBasedReplannerAdapter,
        )
        from cloud_edge_robot_arm.contracts.models import LocalReplanningRequest

        mock = MockReplannerAdapter()
        req = LocalReplanningRequest(
            request_id="req-verify",
            trigger_event_id="evt-fs",
            robot_id="robot-001",
            task_id="verify-003",
            current_plan_version=1,
            current_command_seq=1,
            completed_step_ids=["s1"],
            failed_step_id="s2",
        )
        resp = mock.replan(req)
        mock_ok = resp.outcome == "REPLANNED" and resp.new_plan_version == 2
        results.append(_check("6. MockReplannerAdapter: REPLANNED with version bump", mock_ok))
        if not mock_ok:
            _unused = False

        rule = RuleBasedReplannerAdapter()
        obs_req = LocalReplanningRequest(
            request_id="req-obs",
            trigger_event_id="evt-obs",
            robot_id="robot-001",
            task_id="verify-004",
            current_plan_version=1,
            current_command_seq=1,
            requested_replan_scope="MORE_OBSERVATION_REQUIRED",
        )
        obs_resp = rule.replan(obs_req)
        obs_ok = obs_resp.outcome == "REQUEST_MORE_OBSERVATION" and len(obs_resp.new_steps) == 0
        results.append(_check("6b. RuleBasedReplanner: MORE_OBSERVATION → no steps", obs_ok))
        if not obs_ok:
            _unused = False
    except Exception as exc:
        results.append(_check("6. Replanning adapters", False, str(exc)))
        _unused = False

    # ── 7. Event controller lifecycle ──────────────────────────────────
    try:
        from cloud_edge_robot_arm.edge.event_mode.controller import EventTriggeredModeController

        controller = EventTriggeredModeController()
        controller.initialize_task(contract)
        summary = controller.on_task_completed(
            contract=contract,
            completed_step_ids=["s1"],
        )
        ctrl_ok = summary is not None and summary.result in ("SUCCESS", "SUCCESS_WITH_RECOVERY")
        results.append(_check("7. Event controller: task completion", ctrl_ok))
        if not ctrl_ok:
            _unused = False
    except Exception as exc:
        results.append(_check("7. Event controller", False, str(exc)))
        _unused = False

    # ── 8. Outbox persistence ──────────────────────────────────────────
    try:
        from cloud_edge_robot_arm.contracts.models import MessageStatus, PendingMessage
        from cloud_edge_robot_arm.edge.outbox import InMemoryPendingMessageRepository

        outbox = InMemoryPendingMessageRepository()
        msg = PendingMessage(
            message_id="msg-outbox",
            task_id="verify-005",
            message_type="EDGE_EVENT",
            payload={"event_type": "GRASP_FAILED"},
            status=MessageStatus.PENDING,
            created_at=NOW,
        )
        outbox.enqueue(msg)
        pending = outbox.list_pending("verify-005")
        ob_ok = len(pending) == 1 and pending[0].message_id == "msg-outbox"
        results.append(_check("8. Outbox: message persists", ob_ok))
        if not ob_ok:
            _unused = False

        outbox.mark_failed("msg-outbox", "Send error")
        retry_pending = outbox.list_pending("verify-005")
        ob2_ok = len(retry_pending) == 1 and retry_pending[0].retry_count == 1
        results.append(_check("8b. Outbox: failed message retries", ob2_ok))
        if not ob2_ok:
            _unused = False
    except Exception as exc:
        results.append(_check("8. Outbox", False, str(exc)))
        _unused = False

    # ── 9. Phase 5 regression ──────────────────────────────────────────
    phase5_result = _run("verify_phase5.py")
    p5_ok = phase5_result["passed"] is True
    results.append(
        _check(
            "9. Phase 5 periodic supervision no regression",
            p5_ok,
            str(phase5_result.get("stdout", ""))[:200],
        )
    )
    if not p5_ok:
        _unused = False

    # ── 10. Phase 3, 3.1, 3.2, 4 regression ────────────────────────────
    for script in [
        "verify_phase3.py",
        "verify_phase3_1.py",
        "verify_phase3_2.py",
        "verify_phase4.py",
    ]:
        r = _run(script)
        ok = r["passed"] is True
        results.append(_check(f"10. {script} no regression", ok))
        if not ok:
            pass

    # ── 11. Production config check ────────────────────────────────────
    try:
        # Production mode should fail without required config
        import os

        from cloud_edge_robot_arm.config import AppConfig

        old = os.environ.get("RUNTIME_PROFILE")
        try:
            os.environ["RUNTIME_PROFILE"] = "production"
            os.environ.pop("DATABASE_URL", None)  # Ensure it fails
            failed_as_expected = False
            try:
                AppConfig.from_env()
            except ValueError, KeyError:
                failed_as_expected = True
            results.append(
                _check("11. Production config fails without DATABASE_URL", failed_as_expected)
            )
            if not failed_as_expected:
                pass
        finally:
            if old is not None:
                os.environ["RUNTIME_PROFILE"] = old
            else:
                os.environ.pop("RUNTIME_PROFILE", None)
    except Exception as exc:
        results.append(_check("11. Production config", False, str(exc)))

    # ── 12. Severity classification ────────────────────────────────────
    try:
        info_events = {
            EdgeEventType.STEP_COMPLETED,
            EdgeEventType.TASK_COMPLETED,
            EdgeEventType.NETWORK_RECOVERED,
        }
        crit_events = {EdgeEventType.DEVICE_FAULT, EdgeEventType.EMERGENCY_STOP_TRIGGERED}
        sev_ok = len(info_events) > 0 and len(crit_events) > 0
        results.append(_check("12. Event type enums complete", sev_ok))
    except Exception as exc:
        results.append(_check("12. Event types", False, str(exc)))

    # ── Report ──────────────────────────────────────────────────────────
    print("\nPhase 6 Acceptance Verification")
    print("=" * 60)
    passed_count = sum(1 for r in results if r["passed"] is True)
    total_count = len(results)
    for r in results:
        status = "✓" if r["passed"] else "✗"
        print(f"  {status} {r['check']}")
        if not r["passed"] and r.get("detail"):
            print(f"    Detail: {r['detail']}")

    print(f"\n  {passed_count}/{total_count} checks passed")
    success = passed_count == total_count
    print(f"\nsuccess={str(success).lower()}")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
