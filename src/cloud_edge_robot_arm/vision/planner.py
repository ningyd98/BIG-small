"""Visual decisions from paired images, grounded using raw metric depth."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from cloud_edge_robot_arm.cloud.planning.adapter import (
    _build_pick_place_steps,
    _build_safety_constraints,
)
from cloud_edge_robot_arm.cloud.planning.models import (
    InitialPlanningRequest, PlannerDraft, SceneObjectSummary, SceneSummary, TargetRegionSummary,
)
from cloud_edge_robot_arm.model_control.endpoint_security import EndpointSecurityPolicy
from cloud_edge_robot_arm.model_control.models import PlannerProviderKind
from cloud_edge_robot_arm.vision.observations import RGBDObservation


class VisualDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_pixel: tuple[int, int] | None
    destination_pixel: tuple[int, int] | None
    target_label: str = Field(min_length=1, max_length=100)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    skills: list[Literal["HOME", "MOVE_ABOVE", "APPROACH", "GRASP", "LIFT", "MOVE_TO_REGION", "PLACE", "RELEASE", "RETREAT"]] = Field(max_length=20)
    reason: str = Field(default="", max_length=500)


def image_messages(instruction: str, observation: RGBDObservation) -> list[dict[str, Any]]:
    """The second image contains the entire aligned depth plane, not text detections."""
    near, far = observation.depth_range()
    system = (
        "You are a visual pick-and-place planner. Inspect both images: first RGB, second registered depth. "
        "Return JSON matching the supplied schema. Select [u,v] integer pixels in the ORIGINAL image, "
        "u increasing right, v increasing down. Select the visible target's top surface center and a free "
        "point on the requested destination surface. Never guess world coordinates. If the target or "
        "destination cannot be identified, return null pixels, confidence 0, skills [], and a reason. "
        "Choose an ordered sequence of high-level skills to complete the instruction; typical skills are "
        "HOME,MOVE_ABOVE,APPROACH,GRASP,LIFT,MOVE_TO_REGION,PLACE,RELEASE,RETREAT,HOME. "
        "Do not emit motor controls or safety overrides."
    )
    user = (
        f"Instruction: {instruction}\nOriginal image size: {observation.width}x{observation.height}. "
        f"Depth is optical-axis metres: grayscale 255={near:.6f}m, 1={far:.6f}m, 0=invalid; "
        "linear mapping. Both images use identical pixel coordinates."
    )
    return [{"role": "system", "content": system},
            {"role": "user", "content": user,
             "images": [observation.rgb_png_base64, observation.depth_png_base64()]}]


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


class RGBDPlannerAdapter:
    requires_rgbd = True
    planner_name = "rgbd_visual"

    def __init__(self, *, base_url: str = "http://127.0.0.1:11434", model: str = "qwen3-vl:4b-instruct",
                 provider: Literal["ollama", "openai_compatible"] = "ollama", api_key: str = "",
                 timeout_s: float = 60, allow_paid: bool = False, chat_path: str = "/chat/completions") -> None:
        kind = PlannerProviderKind.OLLAMA if provider == "ollama" else PlannerProviderKind.OPENAI_COMPATIBLE
        self.base_url = EndpointSecurityPolicy().validate(kind, base_url)
        self.model_name = model
        self.provider = provider
        self._api_key = api_key
        self.timeout_s = timeout_s
        self.allow_paid = allow_paid
        if chat_path not in {"/chat/completions", "/v1/chat/completions"}:
            raise ValueError("unsupported visual chat path")
        self.chat_path = chat_path

    @classmethod
    def from_environment(cls) -> RGBDPlannerAdapter:
        return cls(base_url=os.environ.get("BIGSMALL_VLM_BASE_URL", "http://127.0.0.1:11434"),
                   model=os.environ.get("BIGSMALL_VLM_MODEL", "qwen3-vl:4b-instruct"),
                   provider=os.environ.get("BIGSMALL_VLM_PROVIDER", "ollama"),
                   api_key=os.environ.get("BIGSMALL_VLM_API_KEY", ""),
                   allow_paid=os.environ.get("BIGSMALL_VLM_ALLOW_PAID_CALL", "").lower() == "true")

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        request = urllib.request.Request(self.base_url + path, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise RGBDModelUnavailable("RGBD_MODEL_UNAVAILABLE: oversized response")
                return json.loads(raw)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            # Do not expose endpoint credentials or remote response bodies.
            raise RGBDModelUnavailable(f"RGBD_MODEL_UNAVAILABLE: {type(exc).__name__}; check vision service and installed model") from exc

    def plan(self, request: InitialPlanningRequest) -> PlannerDraft:
        observation = request.observation
        if observation is None:
            raise ValueError("RGBD observation required")
        messages = image_messages(request.user_instruction, observation)
        if self.provider == "ollama":
            info = self._post("/api/show", {"model": self.model_name})
            if "vision" not in info.get("capabilities", []):
                raise RGBDModelUnavailable("RGBD_MODEL_UNAVAILABLE: selected model does not advertise vision capability")
            body = {"model": self.model_name, "messages": messages, "stream": False,
                    "format": VisualDecision.model_json_schema(), "think": False, "keep_alive": "10m",
                    "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 512}}
            path = "/api/chat"
        else:
            if not self.allow_paid:
                raise RGBDModelUnavailable("RGBD_MODEL_UNAVAILABLE: compatible provider requires BIGSMALL_VLM_ALLOW_PAID_CALL=true")
            body = {"model": self.model_name, "messages": compatible_messages(messages), "temperature": 0,
                    "max_tokens": 512, "response_format": {"type": "json_object"}}
            path = self.chat_path
        started = time.monotonic()
        response = self._post(path, body)
        latency_ms = round((time.monotonic() - started) * 1000)
        try:
            raw = (response["message"]["content"] if self.provider == "ollama"
                   else response["choices"][0]["message"]["content"])
            decision = VisualDecision.model_validate_json(raw, strict=True)
        except (KeyError, IndexError, TypeError, ValidationError) as exc:
            return PlannerDraft(raw_text="", parse_error=f"invalid visual decision: {type(exc).__name__}",
                                observation_evidence=observation.evidence())
        evidence = {**observation.evidence(), "model": self.model_name, "provider": self.provider,
                    "valid_decision_latency_ms": latency_ms, "visual_decision": decision.model_dump(mode="json"),
                    "prompt_hash": hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()}
        if decision.confidence < 0.5 or decision.target_pixel is None or decision.destination_pixel is None:
            return self._more_observation(raw, decision.reason or "visual identification confidence too low", evidence)
        try:
            target = observation.world_point(decision.target_pixel)
            destination = observation.world_point(decision.destination_pixel)
        except ValueError as exc:
            return self._more_observation(raw, str(exc), evidence)
        required = ["MOVE_ABOVE", "APPROACH", "GRASP", "LIFT", "MOVE_TO_REGION", "PLACE", "RELEASE", "RETREAT"]
        order = decision.skills
        if any(skill not in order for skill in required) or any(order.index(a) >= order.index(b) for a, b in zip(required, required[1:])):
            return PlannerDraft(raw_text=raw, parse_error="visual skill sequence is incomplete or out of order", observation_evidence=evidence)
        scene = SceneSummary(scene_version=request.scene.scene_version, updated_at=observation.captured_at,
                             objects=[SceneObjectSummary(object_id="visual_target", object_class=decision.target_label,
                                                         pose=target, pose_confidence=decision.confidence)],
                             regions=[TargetRegionSummary(region_id="visual_destination", center=destination)],
                             scene_confidence=decision.confidence)
        templates = {s["skill"]: s for s in _build_pick_place_steps("visual_target", "visual_destination")}
        steps = [dict(copy.deepcopy(templates[skill]), step_id=f"step-{i:02d}") for i, skill in enumerate(order, 1)]
        contract = {"task_id": "", "plan_version": 0, "command_seq": 0, "timestamp": "",
                    "issued_at": "", "valid_until": "", "control_mode": request.control_mode,
                    "user_instruction": request.user_instruction, "scene_version": scene.scene_version,
                    "expected_scene_version": scene.scene_version,
                    "task_target": {"object_id": "visual_target", "object_class": decision.target_label,
                                    "target_region_id": "visual_destination"}, "current_step_id": None,
                    "steps": steps, "safety_constraints": _build_safety_constraints(request),
                    "failure_policy": {"local_retry_limit": 2, "on_timeout": "REQUEST_CLOUD_REPLAN",
                                       "on_safety_rejection": "PAUSE_AND_REPORT", "on_network_loss": "SAFE_STOP"},
                    "completion_criteria": ["object_inside_target_region", "gripper_released", "robot_in_safe_pose"]}
        evidence["grounded_target"] = target.model_dump()
        evidence["grounded_destination"] = destination.model_dump()
        return PlannerDraft(raw_text=raw, parsed_json=contract, observed_scene=scene, observation_evidence=evidence)

    @staticmethod
    def _more_observation(raw: str, reason: str, evidence: dict[str, Any]) -> PlannerDraft:
        return PlannerDraft(raw_text=raw, parsed_json={"_sentinel": "REQUEST_MORE_OBSERVATION", "_reason": reason},
                            observation_evidence=evidence)
