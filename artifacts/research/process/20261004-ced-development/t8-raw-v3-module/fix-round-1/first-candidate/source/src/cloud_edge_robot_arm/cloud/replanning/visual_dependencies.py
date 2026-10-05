"""Compute a candidate repair window without replaying completed physical effects."""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class StepDependency:
    step_id: str
    depends_on: Sequence[str]
    evidence_ids: Sequence[str]
    physical_effect_id: str | None
    completed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.step_id, str) or not self.step_id.strip():
            raise ValueError("step identity is required")
        for name in ("depends_on", "evidence_ids"):
            values = getattr(self, name)
            if isinstance(values, str) or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise ValueError("dependency/evidence identities must be nonempty strings")
            if len(values) != len(set(values)):
                raise ValueError("duplicate dependency/evidence identity")
            object.__setattr__(self, name, tuple(values))
        if type(self.completed) is not bool:
            raise ValueError("completed must be a boolean")
        if self.physical_effect_id is not None and (
            not isinstance(self.physical_effect_id, str) or not self.physical_effect_id.strip()
        ):
            raise ValueError("physical effect identity must be nonempty when present")


@dataclass(frozen=True)
class RepairWindow:
    first_affected_step_id: str
    replace_step_ids: Sequence[str]
    preserved_step_ids: Sequence[str]
    expected_plan_version: int
    expected_command_seq: int

    def __post_init__(self) -> None:
        _versions(self.expected_plan_version, self.expected_command_seq)
        replacement = tuple(self.replace_step_ids)
        preserved = tuple(self.preserved_step_ids)
        all_ids = replacement + preserved
        if any(not isinstance(value, str) or not value.strip() for value in all_ids):
            raise ValueError("repair step identities must be nonempty")
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("repair step identities must be disjoint and unique")
        if self.first_affected_step_id != (replacement[0] if replacement else ""):
            raise ValueError("first affected step must agree with the repair window")
        object.__setattr__(self, "replace_step_ids", replacement)
        object.__setattr__(self, "preserved_step_ids", preserved)


def _versions(plan_version: int | None, command_seq: int | None) -> None:
    if type(plan_version) is not int or plan_version < 0:
        raise ValueError("repair requires the current nonnegative plan version")
    if type(command_seq) is not int or command_seq < 1:
        raise ValueError("repair requires the current positive command sequence")


def find_repair_window(
    steps: Sequence[StepDependency],
    invalid_evidence_ids: set[str],
    *,
    expected_plan_version: int | None = None,
    expected_command_seq: int | None = None,
) -> RepairWindow:
    """Propagate invalid evidence through a topologically ordered dependency graph.

    This produces a version-bound candidate description, never an action. Completed
    effects stay in the preserved set even when their evidence was invalidated:
    a caller must confirm them on a fresh observation or create separately identified
    compensation. The ordinary repair window cannot repeat them. Version keywords
    are required because StepDependency intentionally carries no mutable plan state.
    """
    _versions(expected_plan_version, expected_command_seq)
    if any(not isinstance(value, str) or not value.strip() for value in invalid_evidence_ids):
        raise ValueError("invalid evidence identities must be nonempty strings")
    seen: set[str] = set()
    effects: set[str] = set()
    affected: set[str] = set()
    replacement: list[str] = []
    preserved: list[str] = []
    for step in tuple(steps):
        if not isinstance(step, StepDependency):
            raise ValueError("repair graph requires typed dependencies")
        if step.step_id in seen:
            raise ValueError("duplicate step identity")
        if not set(step.depends_on) <= seen:
            raise ValueError("dependency must name an earlier step; missing/cyclic graph")
        if step.physical_effect_id is not None:
            if step.physical_effect_id in effects:
                raise ValueError("a physical effect cannot be reused under another step identity")
            effects.add(step.physical_effect_id)
        seen.add(step.step_id)
        if set(step.evidence_ids) & invalid_evidence_ids or set(step.depends_on) & affected:
            affected.add(step.step_id)
        if step.step_id in affected and not step.completed:
            replacement.append(step.step_id)
        else:
            preserved.append(step.step_id)
    assert expected_plan_version is not None and expected_command_seq is not None
    return RepairWindow(
        replacement[0] if replacement else "",
        tuple(replacement), tuple(preserved), expected_plan_version, expected_command_seq,
    )
