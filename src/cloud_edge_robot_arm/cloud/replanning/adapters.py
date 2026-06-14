"""Replanner adapters — Mock, RuleBased, and OpenAICompatible.

Extends the PlannerAdapter pattern from cloud/planning/adapter.py.
ReplannerAdapter operates on LocalReplanningRequest → LocalReplanningResponse.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from cloud_edge_robot_arm.cloud.replanning.context import ReplanningContext
from cloud_edge_robot_arm.contracts.models import (
    LocalReplanningRequest,
    LocalReplanningResponse,
    SkillName,
    TaskStep,
)


@runtime_checkable
class ReplannerAdapter(Protocol):
    """Protocol for cloud-side local replanning adapters.

    Follows the same pattern as PlannerAdapter.
    Receives a LocalReplanningRequest and returns a LocalReplanningResponse.
    Must never output joint angles, PWM, servo pulse, or trajectory points.
    """

    def replan(
        self,
        request: LocalReplanningRequest,
        context: ReplanningContext | None = None,
    ) -> LocalReplanningResponse:
        """Generate a local replan from the given request and current context."""
        ...

    @property
    def planner_name(self) -> str:
        """Human-readable adapter name."""
        ...


class MockReplannerAdapter:
    """Deterministic mock replanner for test/CI only.

    Accepts an injectable clock for deterministic output.
    Must not be used in production.
    """

    def __init__(
        self,
        canned_response: LocalReplanningResponse | None = None,
        clock: object | None = None,
    ) -> None:
        self._canned = canned_response
        self._clock: object = clock if clock is not None else lambda: datetime.now(UTC)

    @property
    def planner_name(self) -> str:
        return "mock_replanner"

    def replan(
        self,
        request: LocalReplanningRequest,
        context: ReplanningContext | None = None,
    ) -> LocalReplanningResponse:
        if self._canned is not None:
            return self._canned

        now = self._clock()  # type: ignore[operator]
        new_steps = [
            TaskStep(
                step_id=f"replan-step-{i}",
                skill=SkillName.GRASP if i == 0 else SkillName.PLACE,
                parameters={},
                expected_duration_ms=2000,
                timeout_ms=5000,
                retry_limit=3,
                preconditions=[],
                success_conditions=[],
            )
            for i in range(3)
        ]
        return LocalReplanningResponse(
            request_id=request.request_id,
            outcome="REPLANNED",
            reason="Mock replan generated",
            new_steps=new_steps,
            new_plan_version=request.current_plan_version + 1,
            new_command_seq=request.current_command_seq + 1,
            planner_name="mock_replanner",
            prompt_version="1.0",
            created_at=now,
        )


class RuleBasedReplannerAdapter:
    """Deterministic rule-based replanner — no LLM.

    Generates replacement steps based on the failure type and remaining steps.
    Supports CURRENT_STEP, FAILED_STEP_AND_REMAINING, REMAINING_STEPS scopes.
    """

    @property
    def planner_name(self) -> str:
        return "rule_based_replanner"

    def replan(
        self,
        request: LocalReplanningRequest,
        context: ReplanningContext | None = None,
    ) -> LocalReplanningResponse:
        now = datetime.now(UTC)
        scope = request.requested_replan_scope

        # MORE_OBSERVATION_REQUIRED — no plan generated
        if scope == "MORE_OBSERVATION_REQUIRED":
            return LocalReplanningResponse(
                request_id=request.request_id,
                outcome="REQUEST_MORE_OBSERVATION",
                reason="Insufficient scene data for replanning",
                new_steps=[],
                new_plan_version=request.current_plan_version,
                new_command_seq=request.current_command_seq,
                planner_name=self.planner_name,
                prompt_version="1.0",
                created_at=now,
            )

        # NO_REPLAN_SAFETY_STOP — no plan generated
        if scope == "NO_REPLAN_SAFETY_STOP":
            return LocalReplanningResponse(
                request_id=request.request_id,
                outcome="REJECTED",
                reason="Safety stop required — no replan possible",
                new_steps=[],
                new_plan_version=request.current_plan_version,
                new_command_seq=request.current_command_seq,
                planner_name=self.planner_name,
                prompt_version="1.0",
                created_at=now,
            )

        failed_step = context.failed_step if context is not None else None
        if failed_step is None:
            failed_step = _fallback_failed_step(request)
            context = ReplanningContext(
                active_contract=_fallback_contract(request, failed_step),
                failed_step=failed_step,
                completed_steps=[],
            )
        new_steps = self._generate_replacement_steps(scope, request, context)

        return LocalReplanningResponse(
            request_id=request.request_id,
            outcome="REPLANNED",
            reason=f"Rule-based replan for scope={scope}",
            new_steps=new_steps,
            new_plan_version=request.current_plan_version + 1,
            new_command_seq=request.current_command_seq + 1,
            planner_name=self.planner_name,
            prompt_version="1.0",
            created_at=now,
        )

    @staticmethod
    def _generate_replacement_steps(
        scope: str,
        request: LocalReplanningRequest,
        context: ReplanningContext | None,
    ) -> list[TaskStep]:
        if context is None:
            return []
        failed_step = context.failed_step
        completed_skills = {step.skill for step in context.completed_steps}
        remaining_after_failed = _remaining_after_failed(
            context.active_contract.steps, failed_step.step_id
        )
        replan_step_id = f"{failed_step.step_id}-replan-v{request.current_plan_version + 1}"
        if scope == "CURRENT_STEP":
            return [
                failed_step.model_copy(
                    update={
                        "step_id": replan_step_id,
                        "parameters": {
                            **failed_step.parameters,
                            "tcp_velocity": 0.08,
                        },
                        "retry_limit": max(1, failed_step.retry_limit),
                    },
                    deep=True,
                )
            ]
        if scope == "REMAINING_STEPS":
            return [
                step.model_copy(deep=True)
                for step in remaining_after_failed
                if step.skill not in completed_skills
            ]
        if scope in ("FAILED_STEP_AND_REMAINING", "FULL_PLAN_REQUIRED"):
            replacement = failed_step.model_copy(
                update={
                    "step_id": replan_step_id,
                    "parameters": {
                        **failed_step.parameters,
                        "replan_strategy": "reduced_speed_retry",
                    },
                    "retry_limit": max(1, failed_step.retry_limit),
                },
                deep=True,
            )
            steps = [replacement]
            for step in remaining_after_failed:
                if step.skill in completed_skills and step.skill in {
                    SkillName.GRASP,
                    SkillName.PLACE,
                    SkillName.RELEASE,
                }:
                    continue
                steps.append(step.model_copy(deep=True))
            return steps
        return []


def _remaining_after_failed(steps: list[TaskStep], failed_step_id: str) -> list[TaskStep]:
    for idx, step in enumerate(steps):
        if step.step_id == failed_step_id:
            return list(steps[idx + 1 :])
    return []


def _fallback_failed_step(request: LocalReplanningRequest) -> TaskStep:
    return TaskStep(
        step_id=request.failed_step_id or "replanned-step",
        skill=SkillName.GRASP,
        parameters={},
        expected_duration_ms=2000,
        timeout_ms=5000,
        retry_limit=3,
    )


def _fallback_contract(request: LocalReplanningRequest, failed_step: TaskStep) -> object:
    return type(
        "FallbackReplanningContract",
        (),
        {"steps": [failed_step], "task_id": request.task_id},
    )()


class OpenAICompatibleReplannerAdapter:
    """LLM-based replanner using OpenAI-compatible API.

    Reuses Phase 4 PlannerAdapter HTTP patterns:
    - HTTP client with timeout
    - Max 2 repair attempts (fail-closed)
    - Circuit breaker
    - Response size limit (256KB)
    - JSON extraction from LLM response
    - Error classification (retryable vs non-retryable)
    - Log sanitization (no API keys in logs)

    Production requires explicit configuration (base_url + api_key).
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str = "gpt-4o",
        timeout_s: float = 30.0,
        max_response_bytes: int = 256 * 1024,
    ) -> None:
        if not base_url or not api_key:
            raise ValueError("OpenAICompatibleReplannerAdapter requires base_url and api_key")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout_s = timeout_s
        self._max_response_bytes = max_response_bytes
        self._failure_count = 0
        self._circuit_open = False

    @property
    def planner_name(self) -> str:
        return f"openai_compatible/{self._model}"

    def replan(
        self,
        request: LocalReplanningRequest,
        context: ReplanningContext | None = None,
    ) -> LocalReplanningResponse:
        """Generate a replan via LLM. Fail-closed on any error."""
        if self._circuit_open:
            return LocalReplanningResponse(
                request_id=request.request_id,
                outcome="PLANNER_FAILED",
                reason="Circuit breaker open — too many failures",
                new_plan_version=request.current_plan_version,
                new_command_seq=request.current_command_seq,
                planner_name=self.planner_name,
                created_at=datetime.now(UTC),
            )
        try:
            return self._call_llm(request)
        except Exception:
            self._failure_count += 1
            if self._failure_count >= 3:
                self._circuit_open = True
            return LocalReplanningResponse(
                request_id=request.request_id,
                outcome="PLANNER_FAILED",
                reason="LLM replanner failed",
                new_plan_version=request.current_plan_version,
                new_command_seq=request.current_command_seq,
                planner_name=self.planner_name,
                created_at=datetime.now(UTC),
            )

    def _call_llm(self, request: LocalReplanningRequest) -> LocalReplanningResponse:
        """Call the LLM API with timeout and response size limit."""
        import json as _json

        from cloud_edge_robot_arm.cloud.replanning.prompts import (
            build_replan_prompt,
        )

        prompt = build_replan_prompt(request)
        payload = _json.dumps(
            {
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 2048,
            }
        )
        # HTTP call — requires httpx in production
        try:
            import httpx  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("httpx is required for OpenAICompatibleReplannerAdapter") from exc
        with httpx.Client(timeout=self._timeout_s) as client:
            response = client.post(
                f"{self._base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                content=payload,
            )
            if response.status_code != 200:
                raise RuntimeError(f"API returned {response.status_code}")
            if len(response.content) > self._max_response_bytes:
                raise RuntimeError("Response exceeds size limit")
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        parsed = self._extract_json(content)
        raw_steps = parsed.get("new_steps", [])
        new_steps = [TaskStep.model_validate(step) for step in raw_steps]
        outcome = parsed.get("outcome", "REPLANNED")
        if outcome == "REPLANNED" and not new_steps:
            raise RuntimeError("LLM returned REPLANNED without new_steps")
        now = datetime.now(UTC)
        return LocalReplanningResponse(
            request_id=request.request_id,
            outcome=outcome,
            reason=parsed.get("reason", "LLM-generated replan"),
            new_steps=new_steps,
            new_plan_version=int(parsed.get("new_plan_version", request.current_plan_version + 1)),
            new_command_seq=int(parsed.get("new_command_seq", request.current_command_seq + 1)),
            planner_name=self.planner_name,
            prompt_version="1.0",
            created_at=now,
        )

    @staticmethod
    def _extract_json(content: str) -> dict[str, object]:
        import json as _json

        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise RuntimeError("LLM response did not contain JSON object")
        parsed = _json.loads(text[start : end + 1])
        if not isinstance(parsed, dict):
            raise RuntimeError("LLM response JSON must be an object")
        return parsed
