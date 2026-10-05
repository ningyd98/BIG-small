"""Role-bound planning-only future intentions; no action or authenticated owner authority."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cloud_edge_robot_arm.cloud.replanning.conditional_intent import (
    SCHEMA,
    ConditionalRepairPlanningIntent,
    _context,
    build_conditional_repair_intent,
)
from cloud_edge_robot_arm.contracts.models import ExecutionCheckpoint, SkillName
from cloud_edge_robot_arm.edge.evidence.conditions import OnlineEvidenceSnapshot
from cloud_edge_robot_arm.research.cost_ledger import CostLedger
from cloud_edge_robot_arm.vision.messages import (
    build_visual_messages,
    display_image_size,
    model_to_observation_pixel,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.owner_registration import (
    VisualOriginalPlan,
    VisualOwnerIdentity,
    _model_json,
    _plain,
    freeze_original_visual_plan,
)
from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter
from cloud_edge_robot_arm.vision.runtime_binding import RoleRuntimeBinding

PROMPT_VERSION = "role.conditional-repair-planning.v1"
REQUIRED_SOURCES = frozenset(
    {
        "src/cloud_edge_robot_arm/cloud/replanning/role_conditional_planning.py",
        "src/cloud_edge_robot_arm/cloud/replanning/conditional_intent.py",
        "src/cloud_edge_robot_arm/cloud/replanning/visual_dependencies.py",
        "src/cloud_edge_robot_arm/vision/owner_registration.py",
        "src/cloud_edge_robot_arm/vision/planner.py",
        "src/cloud_edge_robot_arm/vision/messages.py",
        "src/cloud_edge_robot_arm/vision/runtime_binding.py",
        "src/cloud_edge_robot_arm/research/cost_ledger.py",
    }
)


def _json_value(value: Any) -> Any:
    if hasattr(value, "to_payload"):
        return _json_value(value.to_payload())
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return _plain({key: _json_value(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if is_dataclass(value):
        return {item.name: _json_value(getattr(value, item.name)) for item in fields(value)}
    return _plain(value)


def _canonical(value: Any) -> str:
    return json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class RoleConditionalPlanningSource:
    """Detached structural source, explicitly separate from real worker authentication."""

    original: VisualOriginalPlan
    current_identity: VisualOwnerIdentity
    source_checkpoint: ExecutionCheckpoint
    online: OnlineEvidenceSnapshot
    owner_revision: int
    state_generation: int
    invalid_evidence_ids: Sequence[str]
    source_scope: Literal["UNAVAILABLE", "SOFTWARE_ONLY", "SOURCE_BINDING_ONLY"] = field(
        default="UNAVAILABLE", kw_only=True
    )
    source_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.source_scope not in {"UNAVAILABLE", "SOFTWARE_ONLY", "SOURCE_BINDING_ONLY"}:
            raise ValueError("unsupported conditional planning source scope")
        object.__setattr__(
            self, "original", freeze_original_visual_plan(**self.original.freeze_inputs())
        )
        object.__setattr__(
            self, "current_identity", VisualOwnerIdentity(**self.current_identity.to_payload())
        )
        cp = ExecutionCheckpoint.model_validate_json(
            _model_json(self.source_checkpoint, ExecutionCheckpoint)
        )
        observation = RGBDObservation.model_validate_json(
            _model_json(self.online.observation, RGBDObservation)
        )
        robot = type(self.online.robot_state).model_validate_json(
            _model_json(self.online.robot_state, type(self.online.robot_state))
        )
        online = OnlineEvidenceSnapshot(
            observation,
            robot,
            json.loads(_canonical(self.online.visual_facts)),
            self.online.plan_version,
            self.online.command_seq,
            self.online.context_hash,
        )
        ids = tuple(self.invalid_evidence_ids)
        if (
            not ids
            or any(not isinstance(name, str) or not name.strip() for name in ids)
            or len(set(ids)) != len(ids)
        ):
            raise ValueError("explicit unique invalid evidence identities required")
        object.__setattr__(self, "source_checkpoint", cp)
        object.__setattr__(self, "online", online)
        object.__setattr__(self, "invalid_evidence_ids", tuple(sorted(ids)))
        object.__setattr__(self, "source_hash", _digest(self.payload()))

    def context_inputs(self, now: datetime) -> dict[str, Any]:
        return {
            "original": self.original,
            "current_identity": self.current_identity,
            "source_checkpoint": self.source_checkpoint,
            "online": self.online,
            "owner_revision": self.owner_revision,
            "state_generation": self.state_generation,
            "invalid_evidence_ids": self.invalid_evidence_ids,
            "now": now,
        }

    def payload(self) -> dict[str, Any]:
        return {
            **self.context_inputs(datetime.min.replace(tzinfo=UTC)),
            "now": None,
            "source_scope": self.source_scope,
        }


class _Replacement(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    step_id: str = Field(min_length=1, max_length=100)
    skill: SkillName
    target_pixel: tuple[int, int] | None
    destination_pixel: tuple[int, int] | None


class _Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: Literal["role.conditional-repair-planning.v1"]
    binding_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    replacements: list[_Replacement] = Field(min_length=1, max_length=100)


class RoleConditionalPlanningUnavailable(RuntimeError):
    """Constant reason only; never include a credential or remote body."""


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate assistant decision key")
        result[key] = value
    return result


def _assistant_decision(response: dict[str, Any]) -> _Decision:
    """Strict inner JSON only: the existing adapter already parsed outer API JSON."""
    if (
        "error" in response
        or not isinstance(response.get("choices"), list)
        or len(response["choices"]) != 1
    ):
        raise ValueError("single synchronous assistant decision required")
    choice = response["choices"][0]
    if not isinstance(choice, dict) or choice.get("finish_reason", "stop") != "stop":
        raise ValueError("incomplete assistant response")
    message = choice.get("message")
    if (
        not isinstance(message, dict)
        or set(message) - {"role", "content"}
        or message.get("role", "assistant") != "assistant"
        or not isinstance(message.get("content"), str)
    ):
        raise ValueError("plain assistant decision JSON required")
    content = json.loads(message["content"], object_pairs_hook=_unique)
    return _Decision.model_validate_json(_canonical(content))


def _request_visual_json(
    planner: RGBDPlannerAdapter, messages: list[dict[str, Any]], schema: dict[str, Any]
) -> dict[str, Any]:
    """Sole remote private seam; no alternative transport or fallback."""
    return planner._request_visual(messages, schema)


class RoleConditionalPlanningProvider:
    def __init__(
        self,
        *,
        planner: RGBDPlannerAdapter,
        binding: RoleRuntimeBinding | None,
        source: RoleConditionalPlanningSource | None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.planner = planner
        self.binding = binding
        self.source = source
        self.clock = clock or (lambda: datetime.now(UTC))
        self.last_binding_hash: str | None = None
        self._last_clock: datetime | None = None

    def _now(self) -> datetime:
        now = self.clock()
        if (
            not isinstance(now, datetime)
            or now.tzinfo is None
            or now.utcoffset() is None
            or (self._last_clock is not None and now < self._last_clock)
        ):
            raise RoleConditionalPlanningUnavailable("conditional_clock_unavailable_or_reversed")
        self._last_clock = now
        return now

    def _validate(self) -> Any:
        source, binding, planner = self.source, self.binding, self.planner
        if not isinstance(source, RoleConditionalPlanningSource) or binding is None:
            raise RoleConditionalPlanningUnavailable("conditional_role_or_source_missing")
        # This independent state guard runs before every possible paid request/reservation.
        robot = source.online.robot_state
        if not robot.connected or robot.estop_engaged or robot.collision_detected:
            raise RoleConditionalPlanningUnavailable("conditional_robot_hard_stop")
        if source.source_scope not in {"SOFTWARE_ONLY", "SOURCE_BINDING_ONLY"}:
            raise RoleConditionalPlanningUnavailable("conditional_source_unavailable")
        if (
            planner.provider != "openai_compatible"
            or planner.model_role != "REPLANNER"
            or not planner._api_key
            or not planner.allow_paid
            or not isinstance(planner.cost_ledger, CostLedger)
            or planner.model_snapshot is None
            or "max" not in planner.model_name.lower()
        ):
            raise RoleConditionalPlanningUnavailable(
                "conditional_max_profile_or_transport_unavailable"
            )
        try:
            if source.source_hash != _digest(source.payload()):
                raise ValueError("source changed")
            lexical_root = binding.root.absolute()
            if any(path.is_symlink() for path in (lexical_root, *lexical_root.parents)):
                raise ValueError("aliased role source root")
            binding.validate(planner)
            if not REQUIRED_SOURCES <= binding.bundle.cloud_snapshot.source_hashes.keys():
                raise ValueError("request source inventory missing")
            inventories = {
                **binding.bundle.cloud_snapshot.source_hashes,
                **binding.edge_snapshot.source_hashes,
                **binding.device_source_hashes,
            }
            if source.original.role_bundle_hash != binding.bundle.digest() or any(
                inventories.get(name) != expected
                for name, expected in source.original.source_hashes.items()
            ):
                raise ValueError("original source or role identity differs")
            cp, contract = source.source_checkpoint, source.original.contract
            if cp.scene_version != contract.scene_version or source.owner_revision < 1:
                raise ValueError("current scene/source revision differs")
            return _context(**source.context_inputs(self._now()))
        except Exception:
            raise RoleConditionalPlanningUnavailable(
                "conditional_current_role_source_or_clock_invalid"
            ) from None

    def plan(self) -> ConditionalRepairPlanningIntent:
        local = self._validate()
        assert self.source is not None and self.binding is not None
        source = self.source
        schema = _Decision.model_json_schema()
        snapshot = self.planner.model_snapshot
        assert snapshot is not None
        bundle_hash = self.binding.bundle.digest()
        binding_hash = _digest(
            {
                "schema_version": PROMPT_VERSION,
                "conditional_context_hash": local.binding_hash,
                "source_hash": source.source_hash,
                "bundle_hash": bundle_hash,
                "schema": schema,
            }
        )
        self.last_binding_hash = binding_hash
        originals = {step.step_id: step for step in local.original.contract.steps}
        envelope = {
            "schema_version": PROMPT_VERSION,
            "binding_hash": binding_hash,
            "frame_binding_hash": _digest(local.online.observation.evidence()),
            "window_binding_hash": _digest(local.window),
            "source_binding_hash": source.source_hash,
            "bundle_hash": bundle_hash,
            "schema_hash": _digest(schema),
            "authorized_steps": [
                {"step_id": name, "skill": originals[name].skill.value}
                for name in local.window.replace_step_ids
            ],
        }
        instruction = (
            local.original.contract.user_instruction
            + "\nROLE_CONDITIONAL_CONTEXT="
            + _canonical(envelope)
        )
        messages = build_visual_messages(
            instruction,
            local.online.observation,
            image_size=snapshot.image_size,
            coordinate_system=snapshot.coordinate_system,
            decision_schema=schema,
        )
        # Keep authorized images; replace legacy full-task/depth-range prompt text.
        size = display_image_size(local.online.observation, image_size=snapshot.image_size)
        units = (
            "normalized integer coordinates in [0,1000]"
            if snapshot.coordinate_system == "normalized_1000"
            else f"integer pixels in transmitted {size[0]}x{size[1]} image"
        )
        messages[0]["content"] = (
            "Use only the paired RGB/depth-derived images and instruction. "
            "Return planning-only intentions matching the exact ordered authorized step IDs/skills "
            "and binding_hash. Coordinates are " + units + "; use null when unobservable. "
            "Do not output commands, tokens, conditions or permission fields. Schema: "
            + _canonical(schema)
        )
        messages[1]["content"] = instruction
        before = self._validate()
        if before.binding_hash != local.binding_hash or self.source is not source:
            raise RoleConditionalPlanningUnavailable("conditional_request_source_changed")
        try:
            decision = _assistant_decision(_request_visual_json(self.planner, messages, schema))
        except Exception:
            raise RoleConditionalPlanningUnavailable(
                "conditional_remote_decision_invalid_or_unavailable"
            ) from None
        after = self._validate()
        if (
            after.binding_hash != local.binding_hash
            or self.source is not source
            or self.binding.bundle.digest() != bundle_hash
        ):
            raise RoleConditionalPlanningUnavailable("conditional_return_source_changed")
        if decision.binding_hash != binding_hash or [
            r.step_id for r in decision.replacements
        ] != list(local.window.replace_step_ids):
            raise RoleConditionalPlanningUnavailable("conditional_remote_binding_or_order_changed")
        try:
            converted = []
            for replacement in decision.replacements:
                if replacement.skill != originals[replacement.step_id].skill:
                    raise ValueError("original skill changed")
                payload = replacement.model_dump(mode="json")
                for field_name in ("target_pixel", "destination_pixel"):
                    pixel = getattr(replacement, field_name)
                    if pixel is not None:
                        payload[field_name] = model_to_observation_pixel(
                            pixel,
                            local.online.observation,
                            image_size=snapshot.image_size,
                            coordinate_system=snapshot.coordinate_system,
                        )
                converted.append(payload)
            return build_conditional_repair_intent(
                intent_json=_canonical(
                    {
                        "schema_version": SCHEMA,
                        "binding_hash": after.binding_hash,
                        "replacements": converted,
                    }
                ),
                **source.context_inputs(self._now()),
            )
        except Exception:
            raise RoleConditionalPlanningUnavailable(
                "conditional_intent_builder_rejected"
            ) from None
