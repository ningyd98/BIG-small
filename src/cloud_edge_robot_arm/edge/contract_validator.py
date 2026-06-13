from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from cloud_edge_robot_arm.contracts import SkillName, TaskContract
from cloud_edge_robot_arm.errors import StructuredError


class ContractValidationResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    accepted: bool
    contract: TaskContract | None = None
    error: StructuredError | None = None


class EdgeContractValidator:
    def __init__(
        self,
        *,
        supported_skills: Iterable[SkillName] | None = None,
        min_plan_version: int = 1,
    ) -> None:
        skill_source = supported_skills if supported_skills is not None else SkillName
        self._supported_skill_values = {skill.value for skill in skill_source}
        self._min_plan_version = min_plan_version
        self._last_command_seq_by_task: dict[str, int] = {}

    def accept_payload(
        self,
        payload: Mapping[str, Any],
        *,
        now: datetime | None = None,
    ) -> ContractValidationResult:
        checked_at = now if now is not None else datetime.now(UTC)
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=UTC)

        unsupported_skill = self._find_unsupported_skill(payload)
        if unsupported_skill is not None:
            return self._reject(
                "UNSUPPORTED_SKILL",
                f"skill {unsupported_skill!r} is not registered on this edge node",
                {"skill": unsupported_skill},
            )

        expired = self._is_expired(payload, checked_at)
        if expired is not None:
            return expired

        try:
            contract = TaskContract.model_validate(payload)
        except ValidationError as exc:
            return self._reject(
                "CONTRACT_SCHEMA_INVALID",
                "task contract does not match the required schema",
                {"errors": exc.errors(include_url=False)},
            )

        if contract.plan_version < self._min_plan_version:
            return self._reject(
                "STALE_PLAN_VERSION",
                "contract plan_version is older than the edge minimum",
                {"plan_version": contract.plan_version, "minimum": self._min_plan_version},
            )

        if contract.valid_until <= checked_at:
            return self._reject(
                "CONTRACT_EXPIRED",
                "contract valid_until is not later than the validation time",
                {
                    "valid_until": contract.valid_until.isoformat(),
                    "checked_at": checked_at.isoformat(),
                },
            )

        last_seq = self._last_command_seq_by_task.get(contract.task_id, 0)
        if contract.command_seq <= last_seq:
            return self._reject(
                "COMMAND_SEQ_REPLAYED",
                "command_seq must be strictly greater than the last accepted sequence",
                {"command_seq": contract.command_seq, "last_command_seq": last_seq},
            )

        self._last_command_seq_by_task[contract.task_id] = contract.command_seq
        return ContractValidationResult(accepted=True, contract=contract, error=None)

    def _find_unsupported_skill(self, payload: Mapping[str, Any]) -> str | None:
        steps = payload.get("steps")
        if not isinstance(steps, list):
            return None
        for step in steps:
            if not isinstance(step, Mapping):
                continue
            skill = step.get("skill")
            skill_value = skill.value if isinstance(skill, SkillName) else str(skill)
            if skill_value not in self._supported_skill_values:
                return skill_value
        return None

    def _is_expired(
        self,
        payload: Mapping[str, Any],
        checked_at: datetime,
    ) -> ContractValidationResult | None:
        raw_valid_until = payload.get("valid_until")
        if raw_valid_until is None:
            return None
        if isinstance(raw_valid_until, datetime):
            valid_until = raw_valid_until
        elif isinstance(raw_valid_until, str):
            try:
                valid_until = datetime.fromisoformat(raw_valid_until)
            except ValueError:
                return self._reject(
                    "CONTRACT_SCHEMA_INVALID",
                    "task contract does not match the required schema",
                    {"errors": [{"loc": ["valid_until"], "msg": "invalid datetime format"}]},
                )
        else:
            return None
        if valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=UTC)
        if valid_until > checked_at:
            return None
        return self._reject(
            "CONTRACT_EXPIRED",
            "contract valid_until is not later than the validation time",
            {"valid_until": valid_until.isoformat(), "checked_at": checked_at.isoformat()},
        )

    def _reject(self, code: str, message: str, details: dict[str, Any]) -> ContractValidationResult:
        return ContractValidationResult(
            accepted=False,
            contract=None,
            error=StructuredError(
                code=code,
                message=message,
                category="CONTRACT_VALIDATION",
                details=details,
            ),
        )
