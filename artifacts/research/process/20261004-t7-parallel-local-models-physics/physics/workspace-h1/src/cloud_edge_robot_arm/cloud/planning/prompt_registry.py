"""提示词注册表，集中管理规划提示和版本，避免散落硬编码。

Prompt registry for cloud planner prompts.

Every prompt has a version, hash, and template.  Every model call records
the prompt version used, enabling full traceability.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class PromptTemplate:
    prompt_name: str
    prompt_version: str
    prompt_hash: str
    system_prompt: str
    user_template: str


@dataclass
class PromptCallRecord:
    planner_name: str
    model_name: str
    prompt_version: str
    prompt_hash: str
    temperature: float
    max_tokens: int
    latency_ms: int
    attempt: int
    raw_output_hash: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class PromptRegistry:
    """In-memory registry of known prompt templates."""

    def __init__(self) -> None:
        self._templates: dict[str, PromptTemplate] = {}
        self._history: list[PromptCallRecord] = []

    def register(self, template: PromptTemplate) -> None:
        self._templates[template.prompt_name] = template

    def get(self, name: str) -> PromptTemplate | None:
        return self._templates.get(name)

    def record_call(self, record: PromptCallRecord) -> None:
        self._history.append(record)

    @property
    def call_count(self) -> int:
        return len(self._history)

    def list_templates(self) -> list[PromptTemplate]:
        return list(self._templates.values())

    def history_for_planner(self, planner_name: str) -> list[PromptCallRecord]:
        return [r for r in self._history if r.planner_name == planner_name]


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def default_prompt_registry() -> PromptRegistry:
    """Build a registry preloaded with the Phase 4 planning prompt."""
    registry = PromptRegistry()
    system = (
        "You are a cloud task planner for a small robot arm.\n"
        "You generate high-level TaskContract JSON. "
        "You DO NOT output joint angles, motor commands, PWM, servo pulse, "
        "trajectory points, or low-level control.\n"
        "Allowed skills: {{ALLOWED_SKILLS}}\n"
        "You must output ONLY a valid JSON object conforming to the TaskContract "
        "schema. Do NOT wrap in markdown code fences.\n"
        "If the scene is insufficient, set "
        '"_sentinel": "REQUEST_MORE_OBSERVATION".\n'
    )
    user = (
        "User instruction: {{USER_INSTRUCTION}}\n"
        "Control mode: {{CONTROL_MODE}}\n"
        "Scene summary:\n{{SCENE_SUMMARY}}\n"
        "Generate the TaskContract JSON.\n"
    )
    prompt_hash = _hash(system + user)
    template = PromptTemplate(
        prompt_name="initial_planning",
        prompt_version="1.0",
        prompt_hash=prompt_hash,
        system_prompt=system,
        user_template=user,
    )
    registry.register(template)
    return registry
