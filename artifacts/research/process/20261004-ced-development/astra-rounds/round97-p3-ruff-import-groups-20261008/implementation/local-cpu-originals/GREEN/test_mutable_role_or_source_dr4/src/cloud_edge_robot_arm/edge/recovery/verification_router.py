"""Capability-gated verification routing with consumable episode-level budgets.

Keep the same state for every frame and failure within an episode. Routing
reserves an allowance before returning an action, so a caller cannot collect a
third frame when max_reobservations=2. The absolute UTC deadline and remaining
counts are serializable; reconstruction must preserve them rather than start a
new state. Progress changes only the no-progress counter, never spent quotas.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from math import isfinite

from cloud_edge_robot_arm.auto_mode.runtime_events import DecisionAction
from cloud_edge_robot_arm.edge.evidence.conditions import ConditionStatus, ConditionVerdict


@dataclass(frozen=True)
class VerificationBudget:
    max_reobservations: int
    max_retries: int
    max_no_progress: int
    deadline_s: float

    def __post_init__(self) -> None:
        for value in (self.max_reobservations, self.max_retries, self.max_no_progress):
            if type(value) is not int or value < 0:
                raise ValueError("verification allowances must be nonnegative integers")
        if (
            type(self.deadline_s) not in (int, float)
            or not isfinite(self.deadline_s)
            or self.deadline_s <= 0
        ):
            raise ValueError("deadline_s must be finite and positive")


@dataclass
class VerificationBudgetState:
    remaining_reobservations: int
    remaining_retries: int
    consecutive_no_progress: int
    deadline_at: datetime
    limits: VerificationBudget
    previous_conditions: dict[str, tuple[str, float | None]] = field(default_factory=dict)
    exhausted_reason: str | None = None
    verification_rounds: int = 0

    def __post_init__(self) -> None:
        for value in (
            self.remaining_reobservations,
            self.remaining_retries,
            self.consecutive_no_progress,
            self.verification_rounds,
        ):
            if type(value) is not int or value < 0:
                raise ValueError("remaining allowances and no-progress count must be nonnegative")
        if (
            self.remaining_reobservations > self.limits.max_reobservations
            or self.remaining_retries > self.limits.max_retries
        ):
            raise ValueError("remaining allowances cannot exceed configured limits")
        if self.deadline_at.tzinfo is None:
            raise ValueError("deadline_at must include timezone")

    @classmethod
    def start(
        cls,
        limits: VerificationBudget,
        *,
        now: datetime | None = None,
    ) -> VerificationBudgetState:
        start = now or datetime.now(UTC)
        return cls(
            limits.max_reobservations,
            limits.max_retries,
            0,
            start + timedelta(seconds=limits.deadline_s),
            limits,
        )


def route_verification(
    verdicts: Sequence[ConditionVerdict],
    budget: VerificationBudgetState,
    capabilities: set[DecisionAction],
) -> DecisionAction:
    """UNKNOWN only reobserves; FAIL may use a supported, budgeted recovery."""
    if budget.exhausted_reason is not None:
        return DecisionAction.STOP
    if datetime.now(UTC) >= budget.deadline_at:
        budget.exhausted_reason = "deadline_exhausted"
        return DecisionAction.STOP
    if any(verdict.measured_values.get("hard_safety_fault") is True for verdict in verdicts):
        budget.exhausted_reason = "hard_safety_fault"
        return DecisionAction.STOP
    if verdicts and all(verdict.status == ConditionStatus.PASS for verdict in verdicts):
        return (
            DecisionAction.CONTINUE
            if DecisionAction.CONTINUE in capabilities
            else DecisionAction.STOP
        )

    current: dict[str, tuple[str, float | None]] = {}
    for verdict in verdicts:
        value = verdict.measured_values.get("residual_m")
        residual = (
            float(value)
            if isinstance(value, (int, float))
            and not isinstance(value, bool)
            and isfinite(value)
            and value >= 0
            and verdict.measured_values.get("source") == "rgbd_estimate"
            else None
        )
        current[verdict.condition_name] = (str(verdict.status), residual)
    if budget.verification_rounds > 0:
        progress = False
        for name, (status, residual) in current.items():
            previous = budget.previous_conditions.get(name)
            if previous is None:
                continue
            old_status, old_residual = previous
            if (
                (old_status == "UNKNOWN" and status in {"FAIL", "PASS"})
                or (old_status == "FAIL" and status == "PASS")
                or (
                    status != "UNKNOWN"
                    and residual is not None
                    and old_residual is not None
                    and residual < old_residual - 1e-6
                )
            ):
                progress = True
        budget.consecutive_no_progress = 0 if progress else budget.consecutive_no_progress + 1
    budget.verification_rounds += 1
    # Keep the best verified state per condition: oscillation or omission is
    # not fresh progress when a previously seen status/residual returns.
    rank = {"UNKNOWN": 0, "FAIL": 1, "PASS": 2}
    for name, (status, residual) in current.items():
        previous = budget.previous_conditions.get(name)
        if previous is None:
            budget.previous_conditions[name] = (status, residual)
        else:
            old_status, old_residual = previous
            best_status = status if rank[status] > rank[old_status] else old_status
            candidates = [item for item in (old_residual, residual) if item is not None]
            budget.previous_conditions[name] = (
                best_status,
                min(candidates) if candidates else None,
            )
    if budget.consecutive_no_progress >= budget.limits.max_no_progress:
        budget.exhausted_reason = "no_progress_exhausted"
        return DecisionAction.STOP

    if not verdicts or any(verdict.status == ConditionStatus.UNKNOWN for verdict in verdicts):
        if DecisionAction.REOBSERVE in capabilities and budget.remaining_reobservations > 0:
            budget.remaining_reobservations -= 1
            return DecisionAction.REOBSERVE
        budget.exhausted_reason = "reobservation_unavailable_or_exhausted"
        return DecisionAction.STOP
    if budget.remaining_retries > 0:
        for candidate in (DecisionAction.LOCAL_RECOVER, DecisionAction.REQUEST_CLOUD):
            if candidate in capabilities:
                budget.remaining_retries -= 1
                return candidate
    # No supported recovery is a terminal outcome. Missing capabilities do not
    # invent a physical recovery, and failure never silently authorizes CONTINUE.
    budget.exhausted_reason = "recovery_unavailable_or_exhausted"
    return DecisionAction.STOP
