"""规划适配器协议，隔离 LLM/规则规划器与合同校验管线。

PlannerAdapter Protocol and concrete implementations.

The PlannerAdapter is the *only* module that may call an LLM — and even then
it produces unvalidated JSON.  That JSON MUST pass through the planning
pipeline (schema validation → semantic validation → trusted-field completion)
before a TaskContract is created.

Implementations:
- MockPlannerAdapter: deterministic canned response
- RuleBasedPlannerAdapter: rule-based, no LLM — builds contracts from
  structured heuristics
- OpenAICompatiblePlannerAdapter: calls any OpenAI-compatible chat-completions
  endpoint

CI must only use Mock and RuleBased.  API keys are read from environment
variables only; they are never logged.
"""

from __future__ import annotations

import json
import os
import time
from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from cloud_edge_robot_arm.cloud.planning.models import (
    InitialPlanningRequest,
    PlannerDraft,
)

# ── Circuit breaker ──────────────────────────────────────────────────────────


@dataclass
class _CircuitBreaker:
    failure_threshold: int = 3
    reset_timeout_s: float = 30.0
    _failure_count: int = 0
    _last_failure_time: float = 0.0
    _open: bool = False

    def call(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        if self._open:
            if time.monotonic() - self._last_failure_time >= self.reset_timeout_s:
                self._open = False
                self._failure_count = 0
            else:
                raise RuntimeError("Circuit breaker is open")
        try:
            result = fn(*args, **kwargs)
            self._failure_count = 0
            return result
        except Exception:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self.failure_threshold:
                self._open = True
            raise


# ── Retry policy ─────────────────────────────────────────────────────────────


@dataclass
class _RetryPolicy:
    max_retries: int = 2
    base_delay_s: float = 0.5

    def execute(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(self.base_delay_s * (2**attempt))
        raise RuntimeError(f"All {self.max_retries + 1} attempts failed") from last_exc


# ── Protocol ─────────────────────────────────────────────────────────────────


@runtime_checkable
class PlannerAdapter(Protocol):
    """Contract every planner adapter must fulfil.

    ``plan()`` receives a validated request and returns an unvalidated draft.
    The caller is responsible for schema validation, semantic checks, repair,
    and trusted-field completion.
    """

    @abstractmethod
    def plan(self, request: InitialPlanningRequest) -> PlannerDraft: ...

    @property
    @abstractmethod
    def planner_name(self) -> str: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...


# ── Mock ─────────────────────────────────────────────────────────────────────


class MockPlannerAdapter:
    """Deterministic, canned-output planner for CI/testing.

    The raw output is a syntactically valid JSON TaskContract-like dict.
    """

    def __init__(self, canned_output: dict[str, Any] | None = None) -> None:
        self._canned = canned_output or _DEFAULT_MOCK_OUTPUT

    @property
    def planner_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock"

    def plan(self, request: InitialPlanningRequest) -> PlannerDraft:
        raw = json.dumps(self._canned, indent=2)
        return PlannerDraft(raw_text=raw, parsed_json=dict(self._canned))


_MOCK_DEFAULT_STEPS: list[dict[str, Any]] = [
    {
        "step_id": "step-01",
        "skill": "HOME",
        "parameters": {},
        "expected_duration_ms": 1000,
        "timeout_ms": 3000,
        "retry_limit": 1,
        "preconditions": [],
        "success_conditions": ["robot_at_home"],
    },
    {
        "step_id": "step-02",
        "skill": "MOVE_ABOVE",
        "parameters": {"object_id": "red_cube", "height_m": 0.15},
        "expected_duration_ms": 2000,
        "timeout_ms": 5000,
        "retry_limit": 2,
        "preconditions": ["target_visible", "target_reachable"],
        "success_conditions": ["tcp_above_target", "gripper_open"],
    },
    {
        "step_id": "step-03",
        "skill": "APPROACH",
        "parameters": {"object_id": "red_cube"},
        "expected_duration_ms": 1500,
        "timeout_ms": 4000,
        "retry_limit": 1,
        "preconditions": ["target_visible", "target_reachable", "gripper_open"],
        "success_conditions": ["tcp_near_target"],
    },
    {
        "step_id": "step-04",
        "skill": "GRASP",
        "parameters": {"object_id": "red_cube", "grasp_type": "top_grasp"},
        "expected_duration_ms": 2000,
        "timeout_ms": 5000,
        "retry_limit": 2,
        "preconditions": ["target_visible", "target_reachable", "gripper_open"],
        "success_conditions": ["gripper_closed", "object_attached"],
    },
    {
        "step_id": "step-05",
        "skill": "LIFT",
        "parameters": {"height_m": 0.18},
        "expected_duration_ms": 1500,
        "timeout_ms": 3000,
        "retry_limit": 1,
        "preconditions": ["gripper_closed", "object_attached"],
        "success_conditions": ["tcp_above_safe_height"],
    },
    {
        "step_id": "step-06",
        "skill": "MOVE_TO_REGION",
        "parameters": {"region_id": "bin_a", "height_m": 0.15},
        "expected_duration_ms": 2500,
        "timeout_ms": 5000,
        "retry_limit": 1,
        "preconditions": ["gripper_closed", "object_attached"],
        "success_conditions": ["tcp_above_region"],
    },
    {
        "step_id": "step-07",
        "skill": "PLACE",
        "parameters": {"region_id": "bin_a"},
        "expected_duration_ms": 2000,
        "timeout_ms": 5000,
        "retry_limit": 1,
        "preconditions": ["tcp_above_region", "gripper_closed"],
        "success_conditions": ["object_placed"],
    },
    {
        "step_id": "step-08",
        "skill": "RELEASE",
        "parameters": {},
        "expected_duration_ms": 500,
        "timeout_ms": 2000,
        "retry_limit": 1,
        "preconditions": ["object_placed"],
        "success_conditions": ["gripper_open", "object_released"],
    },
    {
        "step_id": "step-09",
        "skill": "RETREAT",
        "parameters": {"height_m": 0.18},
        "expected_duration_ms": 1000,
        "timeout_ms": 3000,
        "retry_limit": 1,
        "preconditions": ["gripper_open"],
        "success_conditions": ["tcp_above_safe_height"],
    },
    {
        "step_id": "step-10",
        "skill": "HOME",
        "parameters": {},
        "expected_duration_ms": 1000,
        "timeout_ms": 3000,
        "retry_limit": 0,
        "preconditions": [],
        "success_conditions": ["robot_at_home"],
    },
]


_DEFAULT_MOCK_OUTPUT: dict[str, Any] = {
    "task_id": "",
    "plan_version": 0,
    "command_seq": 0,
    "timestamp": "",
    "control_mode": "EVENT_TRIGGERED_EDGE_AUTONOMY",
    "issued_at": "",
    "valid_until": "",
    "user_instruction": "pick red cube and place into bin_a",
    "scene_version": 1,
    "expected_scene_version": 1,
    "task_target": {
        "object_id": "red_cube",
        "object_class": "cube",
        "target_region_id": "bin_a",
    },
    "current_step_id": None,
    "steps": _MOCK_DEFAULT_STEPS,
    "safety_constraints": {
        "max_joint_velocity": 0.5,
        "max_tcp_velocity": 0.15,
        "minimum_safe_height": 0.08,
        "workspace_id": "workspace_a",
        "collision_check_required": True,
    },
    "failure_policy": {
        "local_retry_limit": 2,
        "on_timeout": "REQUEST_CLOUD_REPLAN",
        "on_safety_rejection": "PAUSE_AND_REPORT",
        "on_network_loss": "SAFE_STOP",
    },
    "completion_criteria": [
        "object_inside_target_region",
        "gripper_released",
        "robot_in_safe_pose",
    ],
}


# ── Rule-based ───────────────────────────────────────────────────────────────


class RuleBasedPlannerAdapter:
    """No-LLM planner that constructs TaskContracts from heuristics.

    It inspects the scene, checks for target object / region, and builds a
    canonical pick-and-place sequence.  Unknown scenes return
    REQUEST_MORE_OBSERVATION via a sentinel field that the pipeline translates.
    """

    @property
    def planner_name(self) -> str:
        return "rule_based"

    @property
    def model_name(self) -> str:
        return "rule_based"

    def plan(self, request: InitialPlanningRequest) -> PlannerDraft:
        scene = request.scene
        instruction = request.user_instruction.lower()

        # --- Detect intent ---
        target_object_id: str | None = None
        target_region_id: str | None = None

        for obj in scene.objects:
            for keyword in _pick_keywords(instruction):
                if keyword in obj.object_class.lower() or keyword in obj.object_id.lower():
                    target_object_id = obj.object_id
                    break
            if target_object_id:
                break

        for region in scene.regions:
            for keyword in _place_keywords(instruction):
                if keyword in region.region_id.lower():
                    target_region_id = region.region_id
                    break
            if target_region_id:
                break

        # Fallback: use first available object / region
        if target_object_id is None and scene.objects:
            target_object_id = scene.objects[0].object_id
        if target_region_id is None and scene.regions:
            target_region_id = scene.regions[0].region_id

        if target_object_id is None:
            return PlannerDraft(
                raw_text="",
                parsed_json={
                    "_sentinel": "REQUEST_MORE_OBSERVATION",
                    "_reason": "no objects in scene",
                },
            )
        if target_region_id is None:
            return PlannerDraft(
                raw_text="",
                parsed_json={
                    "_sentinel": "REQUEST_MORE_OBSERVATION",
                    "_reason": "no regions in scene",
                },
            )

        # Determine object class
        object_class = "unknown"
        for obj in scene.objects:
            if obj.object_id == target_object_id:
                object_class = obj.object_class
                break

        steps = _build_pick_place_steps(target_object_id, target_region_id)

        raw: dict[str, Any] = {
            "task_id": "",
            "plan_version": 0,
            "command_seq": 0,
            "timestamp": "",
            "control_mode": request.control_mode,
            "issued_at": "",
            "valid_until": "",
            "user_instruction": request.user_instruction,
            "scene_version": scene.scene_version,
            "expected_scene_version": scene.scene_version,
            "task_target": {
                "object_id": target_object_id,
                "object_class": object_class,
                "target_region_id": target_region_id,
            },
            "current_step_id": None,
            "steps": steps,
            "safety_constraints": _build_safety_constraints(request),
            "failure_policy": {
                "local_retry_limit": 2,
                "on_timeout": "REQUEST_CLOUD_REPLAN",
                "on_safety_rejection": "PAUSE_AND_REPORT",
                "on_network_loss": "SAFE_STOP",
            },
            "completion_criteria": [
                "object_inside_target_region",
                "gripper_released",
                "robot_in_safe_pose",
            ],
        }
        raw_text = json.dumps(raw, indent=2)
        return PlannerDraft(raw_text=raw_text, parsed_json=raw)


def _pick_keywords(instruction: str) -> list[str]:
    """Extract candidate object-class keywords from the instruction."""
    # Simple heuristic — real version would use NLP
    words = instruction.replace(",", " ").replace(".", " ").split()
    return words


def _place_keywords(instruction: str) -> list[str]:
    """Extract candidate region keywords."""
    words = instruction.replace(",", " ").replace(".", " ").split()
    return words


def _build_pick_place_steps(object_id: str, region_id: str) -> list[dict[str, Any]]:
    return [
        {
            "step_id": "step-01",
            "skill": "HOME",
            "parameters": {},
            "expected_duration_ms": 1000,
            "timeout_ms": 3000,
            "retry_limit": 1,
            "preconditions": [],
            "success_conditions": ["robot_at_home"],
        },
        {
            "step_id": "step-02",
            "skill": "MOVE_ABOVE",
            "parameters": {"object_id": object_id, "height_m": 0.15},
            "expected_duration_ms": 2000,
            "timeout_ms": 5000,
            "retry_limit": 2,
            "preconditions": ["target_visible", "target_reachable"],
            "success_conditions": ["tcp_above_target", "gripper_open"],
        },
        {
            "step_id": "step-03",
            "skill": "APPROACH",
            "parameters": {"object_id": object_id},
            "expected_duration_ms": 1500,
            "timeout_ms": 4000,
            "retry_limit": 1,
            "preconditions": ["target_visible", "target_reachable", "gripper_open"],
            "success_conditions": ["tcp_near_target"],
        },
        {
            "step_id": "step-04",
            "skill": "GRASP",
            "parameters": {"object_id": object_id, "grasp_type": "top_grasp"},
            "expected_duration_ms": 2000,
            "timeout_ms": 5000,
            "retry_limit": 2,
            "preconditions": ["target_visible", "target_reachable", "gripper_open"],
            "success_conditions": ["gripper_closed", "object_attached"],
        },
        {
            "step_id": "step-05",
            "skill": "LIFT",
            "parameters": {"height_m": 0.18},
            "expected_duration_ms": 1500,
            "timeout_ms": 3000,
            "retry_limit": 1,
            "preconditions": ["gripper_closed", "object_attached"],
            "success_conditions": ["tcp_above_safe_height"],
        },
        {
            "step_id": "step-06",
            "skill": "MOVE_TO_REGION",
            "parameters": {"region_id": region_id, "height_m": 0.15},
            "expected_duration_ms": 2500,
            "timeout_ms": 5000,
            "retry_limit": 1,
            "preconditions": ["gripper_closed", "object_attached"],
            "success_conditions": ["tcp_above_region"],
        },
        {
            "step_id": "step-07",
            "skill": "PLACE",
            "parameters": {"region_id": region_id},
            "expected_duration_ms": 2000,
            "timeout_ms": 5000,
            "retry_limit": 1,
            "preconditions": ["tcp_above_region", "gripper_closed"],
            "success_conditions": ["object_placed"],
        },
        {
            "step_id": "step-08",
            "skill": "RELEASE",
            "parameters": {},
            "expected_duration_ms": 500,
            "timeout_ms": 2000,
            "retry_limit": 1,
            "preconditions": ["object_placed"],
            "success_conditions": ["gripper_open", "object_released"],
        },
        {
            "step_id": "step-09",
            "skill": "RETREAT",
            "parameters": {"height_m": 0.18},
            "expected_duration_ms": 1000,
            "timeout_ms": 3000,
            "retry_limit": 1,
            "preconditions": ["gripper_open"],
            "success_conditions": ["tcp_above_safe_height"],
        },
        {
            "step_id": "step-10",
            "skill": "HOME",
            "parameters": {},
            "expected_duration_ms": 1000,
            "timeout_ms": 3000,
            "retry_limit": 0,
            "preconditions": [],
            "success_conditions": ["robot_at_home"],
        },
    ]


def _build_safety_constraints(request: InitialPlanningRequest) -> dict[str, Any]:
    sc: dict[str, Any] = {
        "max_joint_velocity": 0.5,
        "max_tcp_velocity": 0.15,
        "minimum_safe_height": 0.08,
        "workspace_id": "workspace_a",
        "collision_check_required": True,
    }
    if request.safety_policy is not None:
        sp = request.safety_policy
        sc["max_tcp_velocity"] = min(sc["max_tcp_velocity"], sp.hard_limit_max_tcp_velocity)
        sc["max_joint_velocity"] = min(sc["max_joint_velocity"], sp.hard_limit_max_joint_velocity)
        sc["minimum_safe_height"] = max(sc["minimum_safe_height"], sp.minimum_safe_height)
    return sc


# ── OpenAI-compatible ────────────────────────────────────────────────────────


class OpenAICompatiblePlannerAdapter:
    """Calls an OpenAI-compatible chat-completions endpoint.

    API key is read from environment ONLY.  It is never logged, displayed,
    or serialized.

    Includes timeout, retry, and circuit breaker.
    """

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        timeout_s: float = 30.0,
        max_retries: int = 2,
        circuit_failure_threshold: int = 3,
        circuit_reset_s: float = 30.0,
    ) -> None:
        self._endpoint = endpoint or os.environ.get("PLANNER_API_ENDPOINT", "")
        self._api_key = api_key or os.environ.get("PLANNER_API_KEY", "")
        self._model = model or os.environ.get("PLANNER_MODEL", "gpt-4o-mini")
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout_s = timeout_s
        self._retry = _RetryPolicy(max_retries=max_retries)
        self._breaker = _CircuitBreaker(
            failure_threshold=circuit_failure_threshold,
            reset_timeout_s=circuit_reset_s,
        )
        if not self._endpoint:
            raise ValueError("PLANNER_API_ENDPOINT is required for OpenAICompatiblePlannerAdapter")
        if not self._api_key:
            raise ValueError("PLANNER_API_KEY is required for OpenAICompatiblePlannerAdapter")

    @property
    def planner_name(self) -> str:
        return "openai_compatible"

    @property
    def model_name(self) -> str:
        return self._model

    def plan(self, request: InitialPlanningRequest) -> PlannerDraft:
        import urllib.request

        system_prompt = _build_system_prompt(request)
        user_prompt = _build_user_prompt(request)

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }
        body = json.dumps(payload).encode("utf-8")

        def _call() -> tuple[str, int]:
            started = time.monotonic()
            req = urllib.request.Request(
                self._endpoint,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_key}",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                    raw_response = resp.read().decode("utf-8")
            except Exception as exc:
                raise RuntimeError(f"API call failed: {exc}") from exc
            elapsed_ms = int((time.monotonic() - started) * 1_000)
            return raw_response, elapsed_ms

        try:
            raw_response, latency_ms = self._breaker.call(self._retry.execute, _call)
        except Exception as exc:
            return PlannerDraft(
                raw_text="",
                parse_error=f"Planner call failed: {exc}",
            )

        try:
            parsed = json.loads(raw_response)
            content = parsed["choices"][0]["message"]["content"]
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            return PlannerDraft(
                raw_text=raw_response,
                parse_error=f"Failed to extract content from response: {exc}",
            )

        # Try to extract JSON from model output (may be wrapped in markdown)
        parsed_json: dict[str, Any] | None = None
        parse_error: str | None = None
        try:
            parsed_json = _extract_json(content)
        except ValueError as exc:
            parse_error = str(exc)

        draft = PlannerDraft(
            raw_text=content,
            parsed_json=parsed_json,
            parse_error=parse_error,
        )
        return draft


def _extract_json(text: str) -> dict[str, Any]:
    """Extract a JSON object from model output, handling markdown fences."""
    cleaned = text.strip()
    # Remove ```json / ``` fences
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines)
    result: dict[str, Any] = json.loads(cleaned)
    return result


def _build_system_prompt(request: InitialPlanningRequest) -> str:
    capabilities = request.capabilities
    skills = ", ".join(capabilities.supported_skills)
    return (
        "You are a cloud task planner for a small robot arm.\n"
        "You generate high-level TaskContract JSON. You DO NOT output joint angles, "
        "motor commands, PWM, servo pulse, trajectory points, or low-level control.\n"
        f"Allowed skills: {skills}\n"
        "You must output ONLY a valid JSON object conforming to the TaskContract schema.\n"
        "Do NOT wrap in markdown code fences.\n"
        "If the scene is insufficient (missing target, ambiguous, low confidence), "
        'set "_sentinel": "REQUEST_MORE_OBSERVATION".\n'
        "Every step must have step_id, skill, parameters, expected_duration_ms, timeout_ms, "
        "retry_limit, preconditions, success_conditions.\n"
    )


def _build_user_prompt(request: InitialPlanningRequest) -> str:
    import json as _json

    scene_json = request.scene.model_dump(mode="json", exclude_none=True)
    return (
        f"User instruction: {request.user_instruction}\n"
        f"Control mode: {request.control_mode}\n"
        f"Scene summary:\n{_json.dumps(scene_json, indent=2, default=str)}\n"
        "Generate the TaskContract JSON.\n"
    )
