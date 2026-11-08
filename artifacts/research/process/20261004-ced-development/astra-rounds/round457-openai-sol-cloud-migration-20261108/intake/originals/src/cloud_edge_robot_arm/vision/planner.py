"""Visual decisions from paired images, grounded using raw metric depth."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import statistics
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError

from cloud_edge_robot_arm.cloud.planning.adapter import (
    _build_pick_place_steps,
    _build_safety_constraints,
)
from cloud_edge_robot_arm.cloud.planning.models import (
    InitialPlanningRequest,
    PlannerDraft,
    SceneObjectSummary,
    SceneSummary,
    TargetRegionSummary,
)
from cloud_edge_robot_arm.model_control.endpoint_security import EndpointSecurityPolicy
from cloud_edge_robot_arm.model_control.models import PlannerProviderKind
from cloud_edge_robot_arm.vision.defaults import DEFAULT_VISUAL_MODEL
from cloud_edge_robot_arm.vision.messages import (
    VISUAL_PROMPT_VERSION,
    build_visual_messages,
    model_to_observation_pixel,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.top_grasp import calibration_asset_sha256, resolve_top_grasp

if TYPE_CHECKING:
    from cloud_edge_robot_arm.research.cost_ledger import CostLedger
    from cloud_edge_robot_arm.research.network import NetworkInjector
    from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot


SkillIntent = Literal[
    "HOME",
    "MOVE_ABOVE",
    "APPROACH",
    "GRASP",
    "LIFT",
    "MOVE_TO_REGION",
    "PLACE",
    "RELEASE",
    "RETREAT",
]


class VisualDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_pixel: tuple[int, int] | None
    destination_pixel: tuple[int, int] | None
    target_label: str = Field(min_length=1, max_length=100)
    reported_confidence: float = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
        validation_alias=AliasChoices("reported_confidence", "confidence"),
    )
    skills: list[SkillIntent] = Field(max_length=20)
    reason: str = Field(default="", max_length=500)


def image_messages(instruction: str, observation: RGBDObservation) -> list[dict[str, Any]]:
    """Retained for prior imports; T3 uses the shared message builder."""
    return build_visual_messages(instruction, observation)


def compatible_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = copy.deepcopy(messages)
    for message in result:
        images = message.pop("images", [])
        if images:
            message["content"] = [{"type": "text", "text": message["content"]}] + [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{value}"}}
                for value in images
            ]
    return result


class RGBDModelUnavailable(RuntimeError):
    """No usable vision service; callers must not substitute Mock output."""


class RGBDModelCallFailed(RGBDModelUnavailable):
    """A model attempt failed; retain it as an episode failure, not infrastructure blocking."""


def _target_relief_above_local_support(
    observation: RGBDObservation, pixel: tuple[int, int]
) -> tuple[float, float] | None:
    """Estimate raised top-surface height using RGB-D only, without object oracle labels.

    A small frame cannot support this spatial check and is retained only for
    legacy unit fixtures. Normal camera frames fail closed if the surrounding
    support surface cannot be measured.
    """
    if min(observation.width, observation.height) < 64:
        return None
    u, v = pixel
    depths = observation.depth_values()
    fx, fy, cx, cy = observation.intrinsics
    transform = observation.camera_to_world
    radii = [max(8, round(min(observation.width, observation.height) * 0.05))]
    radii += [round(radii[0] * 1.5), radii[0] * 2]
    neighbors: set[tuple[int, int]] = set()
    for radius in radii:
        for index in range(24):
            theta = 2 * math.pi * index / 24
            x = round(u + radius * math.cos(theta))
            y = round(v + radius * math.sin(theta))
            if 0 <= x < observation.width and 0 <= y < observation.height:
                neighbors.add((x, y))
    heights: list[float] = []
    for x, y in neighbors:
        depth = depths[y * observation.width + x]
        if depth <= 0:
            continue
        heights.append(
            transform[8] * (x - cx) * depth / fx
            + transform[9] * (y - cy) * depth / fy
            + transform[10] * depth
            + transform[11]
        )
    if len(heights) < 12:
        raise ValueError("target local support surface is unavailable")
    support_z = statistics.median(heights)
    relief = observation.world_point(pixel).z - support_z
    return relief, support_z


class RGBDPlannerAdapter:
    requires_rgbd = True
    planner_name = "rgbd_visual"

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        model: str = DEFAULT_VISUAL_MODEL,
        provider: Literal["ollama", "openai_compatible"] = "ollama",
        api_key: str = "",
        timeout_s: float = 180,
        allow_paid: bool = False,
        chat_path: str = "/chat/completions",
        model_snapshot: ModelConfigSnapshot | None = None,
        cost_ledger: CostLedger | None = None,
        network_injector: NetworkInjector | None = None,
        model_role: Literal["PLANNER", "SUPERVISOR", "REPLANNER", "JUDGE"] = "PLANNER",
        raw_transport_observer: Callable[[Literal["REQUEST", "RESPONSE"], str, bytes], None]
        | None = None,
    ) -> None:
        kind = (
            PlannerProviderKind.OLLAMA
            if provider == "ollama"
            else PlannerProviderKind.OPENAI_COMPATIBLE
        )
        self.base_url = EndpointSecurityPolicy().validate(kind, base_url)
        self.model_name = model
        self.provider = provider
        self._api_key = api_key
        self.timeout_s = timeout_s
        self.allow_paid = allow_paid
        self.model_snapshot = model_snapshot
        self.cost_ledger = cost_ledger
        self.network_injector = network_injector
        self.model_role = model_role
        self.raw_transport_observer = raw_transport_observer
        if chat_path not in {"/chat/completions", "/v1/chat/completions"}:
            raise ValueError("unsupported visual chat path")
        self.chat_path = chat_path

    @classmethod
    def from_environment(cls) -> RGBDPlannerAdapter:
        from cloud_edge_robot_arm.vision.defaults import DEFAULT_FROZEN_DIR
        from cloud_edge_robot_arm.vision.frozen_model import load_frozen_planner

        frozen = os.environ.get("BIGSMALL_VLM_FROZEN_DIR")
        if frozen:
            return load_frozen_planner(Path(frozen))
        if frozen is None and not any(
            name in os.environ
            for name in (
                "BIGSMALL_VLM_PROVIDER",
                "BIGSMALL_VLM_MODEL",
                "BIGSMALL_VLM_BASE_URL",
                "BIGSMALL_VLM_API_KEY",
            )
        ):
            return load_frozen_planner(DEFAULT_FROZEN_DIR)
        provider = os.environ.get("BIGSMALL_VLM_PROVIDER", "ollama")
        if provider not in {"ollama", "openai_compatible"}:
            raise ValueError("unsupported visual provider")
        return cls(
            base_url=os.environ.get("BIGSMALL_VLM_BASE_URL", "http://127.0.0.1:11434"),
            model=os.environ.get("BIGSMALL_VLM_MODEL", DEFAULT_VISUAL_MODEL),
            provider=cast('Literal["ollama", "openai_compatible"]', provider),
            api_key=os.environ.get("BIGSMALL_VLM_API_KEY", ""),
            allow_paid=os.environ.get("BIGSMALL_VLM_ALLOW_PAID_CALL", "").lower() == "true",
        )

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        from cloud_edge_robot_arm.research.cost_ledger import RequestCost

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload = json.dumps(body).encode()
        request = urllib.request.Request(
            self.base_url + path, data=payload, headers=headers, method="POST"
        )

        def observe(phase: Literal["REQUEST", "RESPONSE"], data: bytes) -> None:
            if self.raw_transport_observer is not None:
                try:
                    self.raw_transport_observer(phase, path, data)
                except Exception:
                    raise RGBDModelUnavailable("raw transport observer failed") from None

        # A request-observer failure occurs before transmission and records no sent call.
        if self.raw_transport_observer is not None:
            if len(payload) > 2_000_000:
                raise RGBDModelUnavailable("observed request exceeds body limit")
            observe("REQUEST", payload)
        # Registry probes are telemetry. Only actual inference endpoints are model attempts.
        is_model = path in {"/api/chat", "/chat/completions", "/v1/chat/completions"}
        sent_at, started = datetime.now(UTC), time.monotonic()
        request_cost = None
        if is_model and self.cost_ledger is not None:
            from urllib.parse import urlparse

            local = urlparse(self.base_url).hostname in {"localhost", "127.0.0.1", "::1"}
            request_cost = RequestCost(
                request_id=uuid.uuid4().hex,
                sent_at=sent_at,
                finished_at=None,
                is_cloud_model=True,
                model_role=self.model_role,
                deployment="CLOUD",
                provider_location="LOCAL_HOST" if local else "REMOTE_SERVICE",
                provider_version=self.model_snapshot.digest()
                if self.model_snapshot
                else self.model_name,
                status="IN_FLIGHT",
                serialized_sent_bytes=len(payload),
                serialized_received_bytes=0,
                monetary_cost=0 if local else None,
            )
            self.cost_ledger.record_request(request_cost)
        raw = b""
        status: Literal["SUCCESS", "ERROR", "TIMEOUT", "CANCELLED"] = "ERROR"
        network_s = 0.0
        try:
            transfer = None
            if is_model and self.network_injector is not None:
                before = time.monotonic()
                try:
                    transfer = self.network_injector.begin(len(payload))
                finally:
                    network_s += time.monotonic() - before
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                request, timeout=self.timeout_s
            ) as response:
                raw = response.read(2_000_001)
                observe("RESPONSE", raw)
                if transfer is not None:
                    before = time.monotonic()
                    try:
                        assert self.network_injector is not None
                        self.network_injector.finish(transfer, len(raw))
                    finally:
                        network_s += time.monotonic() - before
                if len(raw) > 2_000_000:
                    raise RGBDModelUnavailable("RGBD_MODEL_UNAVAILABLE: oversized response")
                decoded = json.loads(raw)
                if not isinstance(decoded, dict):
                    raise ValueError("non-object model response")
                status = "SUCCESS"
                return decoded
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            status = "TIMEOUT" if isinstance(exc, TimeoutError) else "ERROR"
            if isinstance(exc, urllib.error.HTTPError):
                raw = exc.read(2_000_001)
                observe("RESPONSE", raw)
            # Do not expose endpoint credentials or remote response bodies.
            exception_type = (
                RGBDModelCallFailed
                if is_model
                and (
                    isinstance(exc, (TimeoutError, ValueError))
                    or isinstance(getattr(exc, "reason", None), TimeoutError)
                )
                else RGBDModelUnavailable
            )
            raise exception_type(
                f"RGBD_MODEL_UNAVAILABLE: {type(exc).__name__}; "
                "check vision service and installed model"
            ) from exc
        finally:
            ledger = self.cost_ledger
            if ledger is not None:
                if is_model:
                    assert request_cost is not None
                    ledger.record_request(
                        request_cost.model_copy(
                            update={
                                "finished_at": datetime.now(UTC),
                                "status": status,
                                "serialized_received_bytes": len(raw),
                            }
                        )
                    )
                    ledger.record_timing(
                        network_s=network_s,
                        provider_roundtrip_s=max(0.0, time.monotonic() - started - network_s),
                    )
                else:
                    ledger.record_telemetry(len(payload), len(raw))

    def _get(self, path: str) -> dict[str, Any]:
        raw = b""
        try:
            request = urllib.request.Request(self.base_url + path, method="GET")
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                request, timeout=self.timeout_s
            ) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ValueError("oversized response")
                decoded = json.loads(raw)
                if not isinstance(decoded, dict):
                    raise ValueError("non-object model response")
                return decoded
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise RGBDModelUnavailable(
                f"RGBD_MODEL_UNAVAILABLE: {type(exc).__name__}; check model registry"
            ) from exc
        finally:
            if self.cost_ledger is not None:
                self.cost_ledger.record_telemetry(0, len(raw))

    def plan(self, request: InitialPlanningRequest) -> PlannerDraft:
        observation = request.observation
        if observation is None:
            raise ValueError("RGBD observation required")
        image_size = self.model_snapshot.image_size if self.model_snapshot else None
        coordinate_system = (
            self.model_snapshot.coordinate_system if self.model_snapshot else "pixel"
        )
        grasp_profile = self.model_snapshot.grasp_profile if self.model_snapshot else "unconfigured"
        messages = build_visual_messages(
            request.user_instruction,
            observation,
            image_size=image_size,
            coordinate_system=coordinate_system,
            decision_schema=VisualDecision.model_json_schema(),
        )
        started = time.monotonic()
        response = self._request_visual(messages, VisualDecision.model_json_schema())
        latency_ms = round((time.monotonic() - started) * 1000)
        return self._ground_response(
            request,
            response,
            latency_ms,
            observation,
            messages,
            image_size,
            coordinate_system,
            grasp_profile,
        )

    def _request_visual(
        self, messages: list[dict[str, Any]], decision_schema: dict[str, Any]
    ) -> dict[str, Any]:
        if self.provider == "ollama":
            info = self._post("/api/show", {"model": self.model_name})
            if "vision" not in info.get("capabilities", []):
                raise RGBDModelUnavailable(
                    "RGBD_MODEL_UNAVAILABLE: selected model does not advertise vision capability"
                )
            if self.model_snapshot and self.model_snapshot.weight_digest:
                matches = [
                    item
                    for item in self._get("/api/tags").get("models", [])
                    if isinstance(item, dict) and item.get("name") == self.model_name
                ]
                if (
                    len(matches) != 1
                    or matches[0].get("digest") != self.model_snapshot.weight_digest
                ):
                    raise RGBDModelUnavailable(
                        "RGBD_MODEL_UNAVAILABLE: model digest differs from frozen snapshot"
                    )
                quantization = info.get("details", {}).get("quantization_level")
                if quantization != self.model_snapshot.quantization:
                    raise RGBDModelUnavailable(
                        "RGBD_MODEL_UNAVAILABLE: quantization differs from frozen snapshot"
                    )
            generation = (
                dict(self.model_snapshot.generation_parameters)
                if self.model_snapshot
                else {"temperature": 0, "num_ctx": 4096, "num_predict": 512}
            )
            body = {
                "model": self.model_name,
                "messages": messages,
                "stream": False,
                "format": decision_schema,
                "think": generation.pop("think", False),
                "keep_alive": "10m",
                "options": generation,
            }
            path = "/api/chat"
        else:
            if not self.allow_paid:
                raise RGBDModelUnavailable(
                    "RGBD_MODEL_UNAVAILABLE: compatible provider requires "
                    "BIGSMALL_VLM_ALLOW_PAID_CALL=true"
                )
            generation = (
                dict(self.model_snapshot.generation_parameters) if self.model_snapshot else {}
            )
            body = {
                "model": self.model_name,
                "messages": compatible_messages(messages),
                "temperature": generation.get("temperature", 0),
                "max_tokens": generation.get("num_predict", 512),
                "response_format": {"type": "json_object"},
            }
            if "think" in generation:
                body["enable_thinking"] = generation["think"]
            path = self.chat_path
        return self._post(path, body)

    def supervise(self, observation: RGBDObservation, context: Any) -> Any:
        from cloud_edge_robot_arm.vision.supervision import SupervisionContext, SupervisionDecision

        context = SupervisionContext.model_validate(context)
        if (context.observation_id, context.episode_id) != (
            observation.observation_id,
            observation.episode_id,
        ):
            raise ValueError("supervision context does not bind its RGB-D observation")
        messages = build_visual_messages(
            "Inspect the current task and robot state. " + context.model_dump_json(),
            observation,
            image_size=self.model_snapshot.image_size if self.model_snapshot else None,
            coordinate_system=self.model_snapshot.coordinate_system
            if self.model_snapshot
            else "pixel",
            decision_schema=SupervisionDecision.model_json_schema(),
        )
        messages[0]["content"] = (
            "You supervise a running robot using only the paired current RGB and depth images "
            "and provided observable context. Return the supplied JSON schema, copying all "
            "identity/version fields exactly. CONTINUE means the current step remains appropriate; "
            "REOBSERVE means evidence is insufficient; REPLAN means the task/target/action must "
            "change; STOP means unsafe. Never declare task completion or emit a replacement plan."
        )
        response = self._request_visual(messages, SupervisionDecision.model_json_schema())
        raw = (
            response["message"]["content"]
            if self.provider == "ollama"
            else response["choices"][0]["message"]["content"]
        )
        return SupervisionDecision.model_validate_json(raw, strict=True)

    def _ground_response(
        self,
        request: InitialPlanningRequest,
        response: dict[str, Any],
        latency_ms: int,
        observation: RGBDObservation,
        messages: list[dict[str, Any]],
        image_size: tuple[int, int] | None,
        coordinate_system: str,
        grasp_profile: str,
    ) -> PlannerDraft:
        try:
            raw = (
                response["message"]["content"]
                if self.provider == "ollama"
                else response["choices"][0]["message"]["content"]
            )
            decision = VisualDecision.model_validate_json(raw, strict=True)
        except (KeyError, IndexError, TypeError, ValidationError) as exc:
            return PlannerDraft(
                raw_text="",
                parse_error=f"invalid visual decision: {type(exc).__name__}",
                observation_evidence=observation.evidence(),
            )
        evidence = {
            **observation.evidence(),
            "model": self.model_name,
            "provider": self.provider,
            "coordinate_system": coordinate_system,
            "grasp_profile": grasp_profile,
            "prompt_version": VISUAL_PROMPT_VERSION,
            "valid_decision_latency_ms": latency_ms,
            "visual_decision": decision.model_dump(mode="json"),
            "prompt_hash": hashlib.sha256(
                json.dumps(messages, sort_keys=True).encode()
            ).hexdigest(),
        }
        if self.model_snapshot:
            evidence["model_snapshot"] = self.model_snapshot.evidence()
            evidence["model_snapshot_hash"] = self.model_snapshot.digest()
        if min(observation.width, observation.height) >= 64 and (
            calibration_asset_sha256(grasp_profile) is None or observation.source != "mujoco_camera"
        ):
            evidence["top_grasp_offset_from_surface_m"] = None
            evidence["top_grasp_offset_status"] = "NOT_CONFIGURED"
            return self._more_observation(
                raw,
                "top grasp requires a trusted MuJoCo upright-box calibration profile",
                evidence,
            )
        if (
            decision.reported_confidence < 0.5
            or decision.target_pixel is None
            or decision.destination_pixel is None
        ):
            return self._more_observation(
                raw, decision.reason or "visual identification confidence too low", evidence
            )
        try:
            target_pixel = model_to_observation_pixel(
                decision.target_pixel,
                observation,
                image_size=image_size,
                coordinate_system=coordinate_system,
            )
            destination_pixel = model_to_observation_pixel(
                decision.destination_pixel,
                observation,
                image_size=image_size,
                coordinate_system=coordinate_system,
            )
            target = observation.world_point(target_pixel)
            destination = observation.world_point(destination_pixel)
        except ValueError as exc:
            return self._more_observation(raw, str(exc), evidence)
        evidence["model_pixel_target"] = list(decision.target_pixel)
        evidence["model_pixel_destination"] = list(decision.destination_pixel)
        evidence["original_pixel_target"] = list(target_pixel)
        evidence["original_pixel_destination"] = list(destination_pixel)
        evidence["target_visible_surface"] = target.model_dump()
        try:
            relief = _target_relief_above_local_support(observation, target_pixel)
        except ValueError as exc:
            return self._more_observation(raw, str(exc), evidence)
        if relief is None:
            evidence["target_relief_status"] = "NOT_MEASURED_SMALL_FRAME"
            evidence["top_grasp_offset_from_surface_m"] = None
            evidence["top_grasp_offset_status"] = "REQUIRES_OBJECT_AND_TOOL_GEOMETRY"
        else:
            evidence["target_relief_above_support_m"] = round(relief[0], 6)
            evidence["local_support_height_m"] = round(relief[1], 6)
            if relief[0] < 0.01:
                return self._more_observation(
                    raw, "selected target pixel is not a raised visible top surface", evidence
                )
            try:
                evidence.update(resolve_top_grasp(observation, target_pixel, relief[1]))
                evidence["grasp_calibration_asset_sha256"] = calibration_asset_sha256(grasp_profile)
            except ValueError as exc:
                return self._more_observation(raw, str(exc), evidence)
        evidence["grounding_semantics"] = "VISIBLE_SURFACE_NOT_OBJECT_CENTER"
        evidence["reported_confidence_semantics"] = "MODEL_SELF_REPORT_NOT_SUCCESS_PROBABILITY"
        required: list[SkillIntent] = [
            "MOVE_ABOVE",
            "APPROACH",
            "GRASP",
            "LIFT",
            "MOVE_TO_REGION",
            "PLACE",
            "RELEASE",
            "RETREAT",
        ]
        order = decision.skills
        core = order[1:] if order and order[0] == "HOME" else order[:]
        if core and core[-1] == "HOME":
            core = core[:-1]
        if core != required:
            return PlannerDraft(
                raw_text=raw,
                parse_error="visual skill sequence is incomplete or out of order",
                observation_evidence=evidence,
            )
        scene = SceneSummary(
            scene_version=request.scene.scene_version,
            updated_at=observation.captured_at,
            objects=[
                SceneObjectSummary(
                    object_id="visual_target",
                    object_class=decision.target_label,
                    pose=None,
                    pose_confidence=0.0,
                )
            ],
            regions=[TargetRegionSummary(region_id="visual_destination", center=destination)],
            scene_confidence=0.5,
        )
        templates = {
            s["skill"]: s for s in _build_pick_place_steps("visual_target", "visual_destination")
        }
        steps = [
            dict(copy.deepcopy(templates[skill]), step_id=f"step-{i:02d}")
            for i, skill in enumerate(order, 1)
        ]
        contract = {
            "task_id": "",
            "plan_version": 0,
            "command_seq": 0,
            "timestamp": "",
            "issued_at": "",
            "valid_until": "",
            "control_mode": request.control_mode,
            "user_instruction": request.user_instruction,
            "scene_version": scene.scene_version,
            "expected_scene_version": scene.scene_version,
            "task_target": {
                "object_id": "visual_target",
                "object_class": decision.target_label,
                "target_region_id": "visual_destination",
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
        evidence["grounded_target"] = target.model_dump()
        evidence["grounded_destination"] = destination.model_dump()
        return PlannerDraft(
            raw_text=raw, parsed_json=contract, observed_scene=scene, observation_evidence=evidence
        )

    @staticmethod
    def _more_observation(raw: str, reason: str, evidence: dict[str, Any]) -> PlannerDraft:
        return PlannerDraft(
            raw_text=raw,
            parsed_json={"_sentinel": "REQUEST_MORE_OBSERVATION", "_reason": reason},
            observation_evidence=evidence,
        )
