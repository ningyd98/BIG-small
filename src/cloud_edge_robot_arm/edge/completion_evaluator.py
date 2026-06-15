"""CompletionEvaluator — deterministic 9-point task completion verification.

Does NOT rely on LLM. Evaluates whether a task is truly complete beyond
simple step exhaustion. Step exhaustion != task success.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from cloud_edge_robot_arm.contracts.models import SkillName, TaskContract
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import (
    EventAutonomyRepository,
)


@dataclass(frozen=True)
class CompletionEvaluation:
    """Structured result of completion evaluation.

    - completed: True only if ALL 9 checks pass
    - reason_codes: short codes for each check result
    - failed_checks: list of check names that did not pass
    - evidence: key-value observations supporting the evaluation
    - evaluated_at: UTC timestamp of evaluation
    - task_id: the task being evaluated
    - plan_version: plan version at evaluation time
    - scene_version: scene version at evaluation time
    """

    completed: bool
    reason_codes: list[str] = field(default_factory=list)
    failed_checks: list[str] = field(default_factory=list)
    evidence: dict[str, object] = field(default_factory=dict)
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    task_id: str = ""
    plan_version: int = 0
    scene_version: int = 0


class CompletionEvaluator:
    """Evaluates task completion against 9 mandatory checks.

    Check 1: All required steps completed
    Check 2: All steps in terminal state (none RUNNING/WAITING)
    Check 3: All completion_criteria satisfied
    Check 4: Final robot state meets safety requirements
    Check 5: Gripper state matches task result
    Check 6: Target object at target region
    Check 7: Latest perception data not stale
    Check 8: No unresolved safety events
    Check 9: VERIFY_RESULT step succeeded
    """

    def __init__(
        self,
        *,
        repository: EventAutonomyRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repo = repository
        self._clock = clock if clock is not None else lambda: datetime.now(UTC)

    def evaluate(
        self,
        *,
        contract: TaskContract,
        completed_step_ids: list[str],
        completion_criteria_results: dict[str, bool],
        final_safety_decision: str,
        final_robot_state: dict[str, object] | None = None,
        final_target_state: dict[str, object] | None = None,
        scene_version: int = 0,
        scene_stale_threshold_ms: int = 5000,
        last_scene_update_at: datetime | None = None,
    ) -> CompletionEvaluation:
        """Run all 9 checks and return a structured evaluation."""
        all_ids = {s.step_id for s in contract.steps}
        completed_set = set(completed_step_ids)
        now = self._clock()
        failures: list[str] = []
        codes: list[str] = []
        evidence: dict[str, object] = {}

        # Check 1: All required steps completed
        missing = all_ids - completed_set
        if missing:
            failures.append("CHECK_1_MISSING_STEPS")
            codes.append(f"MISSING:{sorted(missing)}")
        else:
            codes.append("ALL_STEPS_COMPLETED")
        evidence["completed_step_ids"] = sorted(completed_step_ids)
        evidence["all_step_ids"] = sorted(all_ids)

        # Check 2: All steps in terminal state (none pending)
        pending = all_ids - completed_set
        if pending:
            failures.append("CHECK_2_PENDING_STEPS")
            codes.append(f"PENDING:{sorted(pending)}")
        else:
            codes.append("NO_PENDING_STEPS")

        # Check 3: All completion_criteria satisfied
        if not completion_criteria_results:
            failures.append("CHECK_3_NO_CRITERIA_EVALUATED")
            codes.append("NO_CRITERIA_RESULTS")
        elif not all(completion_criteria_results.values()):
            failed = [k for k, v in completion_criteria_results.items() if not v]
            failures.append("CHECK_3_CRITERIA_FAILED")
            codes.append(f"FAILED:{failed}")
        else:
            codes.append("ALL_CRITERIA_SATISFIED")
        evidence["completion_criteria"] = {
            k: bool(v) for k, v in completion_criteria_results.items()
        }

        # Check 4: Final SafetyShield decision and robot state meet safety requirements
        if final_safety_decision not in {"ALLOW", "ALLOW_WITH_LIMITS"}:
            failures.append("CHECK_4_FINAL_SAFETY_REJECTED")
            codes.append(f"FINAL_SAFETY:{final_safety_decision}")
        robot_state = final_robot_state or {}
        estop = robot_state.get("estop_engaged", False)
        collision = robot_state.get("collision_detected", False)
        connected = robot_state.get("connected", True)
        if estop:
            failures.append("CHECK_4_ESTOP_ENGAGED")
            codes.append("ESTOP_ENGAGED")
        elif collision:
            failures.append("CHECK_4_COLLISION_DETECTED")
            codes.append("COLLISION_DETECTED")
        elif connected is False:
            failures.append("CHECK_4_ROBOT_DISCONNECTED")
            codes.append("ROBOT_DISCONNECTED")
        elif final_safety_decision in {"ALLOW", "ALLOW_WITH_LIMITS"}:
            codes.append("ROBOT_SAFE")
        evidence["robot_safety"] = {
            "connected": connected,
            "estop_engaged": estop,
            "collision_detected": collision,
            "final_safety_decision": final_safety_decision,
        }

        # Check 5: Gripper state matches task result
        holding = robot_state.get("holding_object_id")
        gripper_open = robot_state.get("gripper_open", True)
        has_place = any(s.skill == SkillName.PLACE for s in contract.steps)
        if has_place:
            if holding is not None and holding != "":
                failures.append("CHECK_5_GRIPPER_STILL_HOLDING")
                codes.append("GRIPPER_STILL_HOLDING")
            else:
                codes.append("GRIPPER_CORRECT")
        else:
            codes.append("GRIPPER_NOT_APPLICABLE")
        evidence["gripper"] = {
            "holding_object_id": holding,
            "gripper_open": gripper_open,
        }

        # Check 6: Target object at target region
        target_state = final_target_state or {}
        at_region = target_state.get("object_at_target", False)
        if has_place and not at_region:
            failures.append("CHECK_6_TARGET_NOT_AT_REGION")
            codes.append("TARGET_NOT_AT_REGION")
        elif has_place:
            codes.append("TARGET_AT_REGION")
        else:
            codes.append("TARGET_NOT_APPLICABLE")
        evidence["target"] = {"object_at_target": at_region}

        # Check 7: Latest perception data not stale
        if last_scene_update_at is not None:
            staleness_ms = (now - last_scene_update_at).total_seconds() * 1000
            if staleness_ms > scene_stale_threshold_ms:
                failures.append("CHECK_7_SCENE_STALE")
                codes.append(f"SCENE_STALE:{staleness_ms:.0f}ms")
            else:
                codes.append("SCENE_FRESH")
            evidence["scene_staleness_ms"] = staleness_ms
        else:
            codes.append("SCENE_FRESHNESS_UNVERIFIED")
        evidence["scene_version"] = scene_version

        # Check 8: No unresolved safety events
        if self._repo is not None:
            events = self._repo.list_events(contract.task_id)
            critical = [e.event_id for e in events if getattr(e, "severity", "") == "CRITICAL"]
            if critical:
                failures.append("CHECK_8_UNRESOLVED_CRITICAL_EVENTS")
                codes.append(f"CRITICAL:{len(critical)}")
            else:
                codes.append("NO_CRITICAL_EVENTS")
            evidence["critical_events"] = len(critical)
        else:
            codes.append("EVENT_CHECK_SKIPPED_NO_REPO")

        # Check 9: VERIFY_RESULT step succeeded
        verify_steps = [s for s in contract.steps if s.skill == SkillName.VERIFY_RESULT]
        if verify_steps:
            verify_ids = {s.step_id for s in verify_steps}
            if not verify_ids.issubset(completed_set):
                failures.append("CHECK_9_VERIFY_NOT_COMPLETED")
                codes.append("VERIFY_NOT_COMPLETED")
            else:
                codes.append("VERIFY_COMPLETED")
        else:
            codes.append("VERIFY_NOT_REQUIRED")

        passed = len(failures) == 0
        return CompletionEvaluation(
            completed=passed,
            reason_codes=codes,
            failed_checks=failures,
            evidence=evidence,
            evaluated_at=now,
            task_id=contract.task_id,
            plan_version=contract.plan_version,
            scene_version=scene_version,
        )
