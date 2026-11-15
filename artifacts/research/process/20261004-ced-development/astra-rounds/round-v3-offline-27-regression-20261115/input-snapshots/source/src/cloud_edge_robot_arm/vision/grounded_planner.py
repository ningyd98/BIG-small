"""Molmo 识别定位、OpenCV 米制几何与现有云端技能规划的显式组合。"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from cloud_edge_robot_arm.cloud.planning.models import (
    FinalPlanAdmission,
    InitialPlanningRequest,
    PlannerDraft,
)
from cloud_edge_robot_arm.model_control.service import ModelControlService
from cloud_edge_robot_arm.vision.cloud_vision_fallback import (
    CloudVisionDecision,
    fallback_messages,
)
from cloud_edge_robot_arm.vision.messages import model_to_observation_pixel
from cloud_edge_robot_arm.vision.molmo_pointing import (
    MODEL_ID,
    BoundPointResult,
    PointProvider,
    parse_native_point,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.planner import (
    GroundedScene,
    RGBDPlannerAdapter,
    SkillIntent,
    build_grounded_contract,
    ground_observation,
    validate_grounded_skill_order,
)
from cloud_edge_robot_arm.vision.point_association import (
    PointAssociationError,
    associate_target_point,
)
from cloud_edge_robot_arm.vision.revalidation import validate_post_cloud_observation
from cloud_edge_robot_arm.vision.role_models import (
    cloud_request_settings,
    configuration_hash,
    resolve_cloud_role,
)
from cloud_edge_robot_arm.vision.top_grasp import calibration_asset_sha256
from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _strict_skill_json(raw: str) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate skill JSON key")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError("nonfinite skill JSON value")

    return json.loads(raw, object_pairs_hook=unique, parse_constant=reject_constant)


class GroundingTaskDescriptor(BaseModel):
    """显式任务语义；指令必须逐字绑定，禁止从场景真值或评测标签生成。"""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    instruction: str = Field(min_length=1, max_length=2000)
    target_phrase: str = Field(min_length=1, max_length=160)
    destination_phrase: str = Field(min_length=1, max_length=160)
    target_label: str = Field(min_length=1, max_length=100)

    @field_validator("instruction", "target_phrase", "destination_phrase", "target_label")
    @classmethod
    def validate_plain_text(cls, value: str) -> str:
        """保留原始任务文字，拒绝空白、控制字符和标签注入。"""
        if not value.strip() or any(ord(c) < 32 or c in "<>" for c in value):
            raise ValueError("task descriptor requires bounded plain text")
        return value


class SkillDecision(BaseModel):
    """云端仅提出技能意图；坐标、几何、身份和可信字段不属于此接口。"""

    model_config = ConfigDict(extra="forbid", strict=True)
    skills: list[SkillIntent] = Field(max_length=20)
    reason: str = Field(default="", max_length=500)


@dataclass(frozen=True)
class _PlanBinding:
    request: InitialPlanningRequest
    request_hash: str
    task: GroundingTaskDescriptor
    task_hash: str
    points: PointProvider
    cloud: RGBDPlannerAdapter
    supplier: Callable[[], RGBDObservation] | None
    role: Any
    role_hash: str | None
    cloud_hash: str
    route_options: tuple[bool, bool, bool]


class _NativePerceptionFailure(RuntimeError):
    def __init__(self, cause: Exception) -> None:
        super().__init__(type(cause).__name__)
        # 超时可交由图像候选补充；线程、预算和未知执行/I/O 错误必须先停止。
        self.category = (
            "INFERENCE_TIMEOUT" if isinstance(cause, TimeoutError) else "EXECUTION_OR_IO_FAILURE"
        )


@dataclass(frozen=True)
class _OwnedRefreshPlan:
    binding: _PlanBinding
    decision: SkillDecision
    raw: str
    reference: dict[str, Any]
    cloud_started: dict[str, Any]
    cloud_returned: dict[str, Any]
    not_before: datetime
    vision_points: tuple[tuple[int, int], tuple[int, int]] | None = None


class MolmoGroundedPlannerAdapter:
    """显式启用的新规划入口；无硬件派发权限，输出仍经过原规划管线。"""

    requires_rgbd = True
    planner_name = "molmo_opencv_grounded"

    def __init__(
        self,
        *,
        point_provider: PointProvider,
        cloud: RGBDPlannerAdapter,
        task: GroundingTaskDescriptor,
        post_cloud_observation_supplier: Callable[[], RGBDObservation] | None = None,
        worker_owned_refresh: bool = False,
        component_diagnostic: bool = False,
        cloud_vision_fallback: bool = False,
    ) -> None:
        if cloud.provider != "openai_compatible" or cloud.model_snapshot is None:
            raise ValueError("grounded planning requires an explicit compatible cloud snapshot")
        if post_cloud_observation_supplier is not None and not callable(
            post_cloud_observation_supplier
        ):
            raise ValueError("post-cloud observation supplier must be callable")
        if type(worker_owned_refresh) is not bool or (
            worker_owned_refresh and post_cloud_observation_supplier is not None
        ):
            raise ValueError("worker-owned refresh requires its own capture protocol")
        if type(component_diagnostic) is not bool or (
            component_diagnostic and not worker_owned_refresh
        ):
            raise ValueError("component diagnostic requires explicit worker-owned refresh")
        self.component_diagnostic = component_diagnostic
        if type(cloud_vision_fallback) is not bool or (
            cloud_vision_fallback and not component_diagnostic
        ):
            raise ValueError("cloud vision fallback requires explicit component diagnostic")
        self.cloud_vision_fallback = cloud_vision_fallback
        self.worker_owned_refresh = worker_owned_refresh
        self._owned_refresh: _OwnedRefreshPlan | None = None
        self._owned_started = False
        self.post_cloud_observation_supplier = post_cloud_observation_supplier
        self.point_provider = point_provider
        self.cloud = cloud
        self.task = task
        self.model_name = cloud.model_name
        self._cloud_hash = configuration_hash(cloud_request_settings(cloud))

    @property
    def requires_final_plan_admission(self) -> bool:
        """显式补帧结果必须在最终合同及缓存返回前检查。"""
        return self.post_cloud_observation_supplier is not None or self.worker_owned_refresh

    @property
    def awaiting_owned_refresh(self) -> bool:
        """仅待worker真实补帧时为真，不包含派发权限。"""
        return self._owned_refresh is not None

    def _resume_owned(
        self, request: InitialPlanningRequest, pending: _OwnedRefreshPlan
    ) -> PlannerDraft:
        raw = pending.raw
        evidence = copy.deepcopy(pending.reference)
        try:
            self._context(pending.binding)
            reference = pending.binding.request.observation
            fresh = request.observation
            if reference is None or fresh is None:
                raise ValueError("owned_refresh_rgbd_required")
            if request.user_instruction != pending.binding.task.instruction:
                raise ValueError("owned_refresh_task_changed")
            policy = validate_post_cloud_observation(
                reference, fresh, not_before=pending.not_before
            )
            binding = _PlanBinding(
                request,
                configuration_hash(request.model_dump(mode="json")),
                pending.binding.task,
                pending.binding.task_hash,
                pending.binding.points,
                pending.binding.cloud,
                pending.binding.supplier,
                pending.binding.role,
                pending.binding.role_hash,
                pending.binding.cloud_hash,
                pending.binding.route_options,
            )
            evidence = self._evidence(fresh, binding)
            evidence.update(
                cloud_reference=copy.deepcopy(pending.reference),
                cloud_request_invoked=True,
                cloud_messages_sha256=pending.reference["cloud_messages_sha256"],
                cloud_response_content_sha256=pending.reference["cloud_response_content_sha256"],
                post_cloud_revalidation={
                    "status": "STARTED",
                    "capture_protocol": "WORKER_OWNED_REOBSERVATION",
                    "cloud_started": pending.cloud_started,
                    "cloud_returned": pending.cloud_returned,
                    "not_before": pending.not_before.isoformat(),
                    "policy": policy,
                },
                model_image_count=2,
                perception_model_image_count=2,
            )
            if pending.vision_points is None:
                measured = self._ground(request, binding.task, binding, evidence)
            else:
                audit = copy.deepcopy(pending.reference["cloud_vision_fallback"])
                evidence.update(
                    cloud_vision_fallback=audit,
                    cloud_model_image_count=audit["image_count"],
                    perception_model_image_count=int(bool(pending.reference["native_results"])),
                    model_image_count=audit["image_count"]
                    + int(bool(pending.reference["native_results"])),
                    perception_input_mode="CLOUD_RGB_CANDIDATE_LOCAL_RGBD_RECHECK",
                    grounding_point_source="CLOUD_VISION_CANDIDATE",
                )
                self._grounding_scope(request, binding.task, binding, evidence)
                points = [model_to_observation_pixel(p, fresh, coordinate_system="normalized_1000")
                          for p in pending.vision_points]
                evidence["cloud_original_pixel_target"] = list(points[0])
                evidence["cloud_original_pixel_destination"] = list(points[1])
                measured = self._measure_points(request, binding.task, binding, evidence, points)
            if pending.vision_points is None and (
                evidence["opencv_support_mask_sha256"]
                != pending.reference["opencv_support_mask_sha256"]
            ):
                raise ValueError("post_cloud_support_mask_changed")
            draft = build_grounded_contract(
                request, measured, pending.decision.skills, raw_text=raw
            )
            self._fresh(fresh, binding)
            evidence["post_cloud_revalidation"]["status"] = "PASSED"
            evidence["perception_query_count"] = len(evidence["native_results"]) + len(
                pending.reference["native_results"]
            )
            draft.observation_evidence = evidence
            draft._final_plan_admission = self._make_final_plan_admission(binding, fresh)
            return draft
        except (_NativePerceptionFailure, ValueError) as exc:
            return RGBDPlannerAdapter._more_observation(raw, str(exc), evidence)

    def _make_final_plan_admission(
        self, binding: _PlanBinding, observation: RGBDObservation
    ) -> FinalPlanAdmission:
        retained = RGBDObservation.model_validate(observation.model_dump())
        checksum = retained.checksum_sha256

        def admit(original_request: InitialPlanningRequest, active_planner: object) -> None:
            if active_planner is not self or (
                configuration_hash(original_request.model_dump(mode="json")) != binding.request_hash
            ):
                raise ValueError("inflight_planning_context_changed")
            try:
                checked = RGBDObservation.model_validate(retained.model_dump())
            except ValueError:
                raise ValueError("final_plan_admission_observation_changed") from None
            if checked.checksum_sha256 != checksum:
                raise ValueError("final_plan_admission_observation_changed")
            self._fresh(retained, binding)

        return admit

    def _context(self, binding: _PlanBinding) -> None:
        if (
            any(type(value) is not bool or value is not expected for value, expected in zip(
                (self.cloud_vision_fallback, self.component_diagnostic, self.worker_owned_refresh),
                binding.route_options, strict=True,
            ))
            or
            self.point_provider is not binding.points
            or self.cloud is not binding.cloud
            or self.task is not binding.task
            or self.post_cloud_observation_supplier is not binding.supplier
            or getattr(self.cloud, "role_snapshot", None) is not binding.role
            or configuration_hash(binding.request.model_dump(mode="json")) != binding.request_hash
            or configuration_hash(self.task.model_dump()) != binding.task_hash
        ):
            raise ValueError("inflight_planning_context_changed")
        if binding.role is not None and binding.role.digest() != binding.role_hash:
            raise ValueError("inflight_planning_context_changed")
        if (
            self._cloud_hash != binding.cloud_hash
            or configuration_hash(cloud_request_settings(self.cloud)) != binding.cloud_hash
        ):
            raise ValueError("selected_cloud_configuration_changed")

    def _fresh(self, observation: RGBDObservation, binding: _PlanBinding) -> None:
        self._context(binding)
        age = (_utcnow() - observation.captured_at).total_seconds()
        if age < -0.05 or age > 5:
            raise ValueError("capture_time_not_fresh")

    @staticmethod
    def _bound(point: BoundPointResult, observation: RGBDObservation, phrase: str) -> None:
        if not isinstance(point, BoundPointResult) or (
            point.observation_checksum != observation.checksum_sha256
            or point.rgb_sha256 != observation.evidence()["rgb_sha256"]
            or point.query_sha256 != hashlib.sha256(phrase.encode()).hexdigest()
        ):
            raise ValueError("native_point_binding_mismatch")
        parsed = parse_native_point(point.result.raw_text)
        # provider 在达到 512 token 上限时主动判为 INVALID，保留其有界生成证据。
        output_tokens = point.evidence.get("output_tokens")
        capped = (
            point.result.status == "INVALID"
            and point.result.normalized_1000 is None
            and point.result.object_index is None
            and point.result.error == "output token cap"
            and point.evidence.get("reached_cap") is True
            and type(output_tokens) is int
            and output_tokens >= 512
            and point.evidence.get("raw_sha256")
            == hashlib.sha256(point.result.raw_text.encode()).hexdigest()
        )
        if parsed != point.result and not capped:
            raise ValueError("native_point_raw_result_mismatch")
        if point.result.status != "POINT" or point.result.normalized_1000 is None:
            raise ValueError("native_target_absent_or_invalid")

    def _evidence(
        self, observation: RGBDObservation | None, binding: _PlanBinding
    ) -> dict[str, Any]:
        snapshot = binding.cloud.model_snapshot
        return {
            **(observation.evidence() if observation else {}),
            "acquisition_schema": "RGBD_SOURCE_AND_MODEL_INPUTS_V1",
            "acquisition_evidence": observation.evidence() if observation else {},
            "model_image_count": 1,
            "perception_model_image_count": 1,
            "cloud_model_image_count": 0,
            "perception_input_mode": "NATIVE_RGB",
            "perception_model": MODEL_ID,
            "depth_consumed_by": "DETERMINISTIC_RGBD_OPENCV",
            "cloud_model": binding.cloud.model_name,
            "cloud_request_settings_hash": binding.cloud_hash,
            "task_descriptor_sha256": binding.task_hash,
            "native_results": [],
            "hardware_dispatch": False,
            "cloud_model_snapshot": snapshot.evidence(),
            "cloud_model_snapshot_hash": snapshot.digest(),
            "cloud_role_snapshot": binding.role.evidence() if binding.role is not None else None,
            "cloud_role_snapshot_hash": binding.role_hash,
        }

    def _ground(
        self,
        request: InitialPlanningRequest,
        task: GroundingTaskDescriptor,
        binding: _PlanBinding,
        evidence: dict[str, Any],
    ) -> GroundedScene:
        observation = request.observation
        try:
            self._grounding_scope(request, task, binding, evidence)
            assert observation is not None
            queries = (
                f"visible top center of {task.target_phrase}",
                f"interior of {task.destination_phrase}",
            )
            points = []
            for query in queries:
                self._fresh(observation, binding)
                try:
                    point = binding.points.point(observation, query)
                except (RuntimeError, OSError, TimeoutError) as exc:
                    failure = _NativePerceptionFailure(exc)
                    evidence["native_failure_category"] = failure.category
                    raise failure from None
                evidence["native_results"].append(
                    {
                        "status": point.result.status,
                        "normalized_1000": point.result.normalized_1000,
                        "raw_sha256": hashlib.sha256(point.result.raw_text.encode()).hexdigest(),
                        "query_sha256": point.query_sha256,
                        "provider_evidence": dict(point.evidence),
                    }
                )
                self._bound(point, observation, query)
                self._fresh(observation, binding)
                points.append(
                    model_to_observation_pixel(
                        point.result.normalized_1000,
                        observation,
                        coordinate_system="normalized_1000",
                    )
                )
            evidence["native_original_pixel_target"] = list(points[0])
            evidence["native_original_pixel_destination"] = list(points[1])
            return self._measure_points(request, task, binding, evidence, points)
        except ValueError as exc:
            evidence.update(getattr(exc, "evidence", {}))
            raise

    def _grounding_scope(
        self, request: InitialPlanningRequest, task: GroundingTaskDescriptor,
        binding: _PlanBinding, evidence: dict[str, Any],
    ) -> None:
        observation = request.observation
        if observation is None or request.user_instruction != task.instruction:
            raise ValueError("task_instruction_or_observation_binding_missing")
        RGBDObservation.model_validate(observation.model_dump())
        self._fresh(observation, binding)
        profile = binding.cloud.model_snapshot.grasp_profile
        if (
            min(observation.width, observation.height) < 64
            or observation.source != "mujoco_camera"
            or not observation.episode_id or not observation.episode_id.strip()
            or not observation.calibration_version or not observation.calibration_version.strip()
            or calibration_asset_sha256(profile) is None
        ):
            raise ValueError("native_grounding_domain_or_calibration_unavailable")
        evidence["grasp_profile"] = profile

    def _measure_points(
        self, request: InitialPlanningRequest, task: GroundingTaskDescriptor,
        binding: _PlanBinding, evidence: dict[str, Any], points: list[tuple[int, int]],
    ) -> GroundedScene:
        observation = request.observation
        assert observation is not None
        snapshot = binding.cloud.model_snapshot
        assert snapshot is not None
        try:
            try:
                association = associate_target_point(
                    observation, points[0], target_phrase=task.target_phrase
                )
            except PointAssociationError as exc:
                evidence["target_point_association"] = exc.evidence
                raise ValueError(str(exc)) from exc
            evidence["associated_pixel_target"] = list(association.pixel)
            evidence["target_point_association"] = association.evidence
            measured = ground_observation(
                request,
                observation,
                target_pixel=association.pixel,
                destination_pixel=points[1],
                target_label=task.target_label,
                grasp_profile=snapshot.grasp_profile,
                evidence=evidence,
            )
            # Keep partial geometry visible even if the following tracker rejects it.
            evidence.update(measured.evidence)
            tracker = OpenCVTargetTracker(observation, evidence)
            evidence["opencv_initial_geometry"] = {
                "target": tracker._public(tracker.initial),
                "destination": tracker._public(tracker.destination),
                "algorithm_sha256": tracker.algorithm_sha256,
                "calibration_sha256": tracker.calibration_sha256,
            }
            evidence["opencv_support_mask_sha256"] = {
                name: hashlib.sha256(
                    json.dumps(list(geometry["mask"].shape)).encode()
                    + b"\x00"
                    + geometry["mask"].astype("uint8").tobytes()
                ).hexdigest()
                for name, geometry in (
                    ("target", tracker.initial),
                    ("destination", tracker.destination),
                )
            }
            self._fresh(observation, binding)
            return GroundedScene(measured.scene, evidence)
        except ValueError as exc:
            evidence.update(getattr(exc, "evidence", {}))
            raise

    @staticmethod
    def _fallback_eligible(error: Exception, evidence: dict[str, Any]) -> bool:
        reason = str(error)
        return (
            (isinstance(error, _NativePerceptionFailure) and error.category == "INFERENCE_TIMEOUT")
            or reason == "native_target_absent_or_invalid"
            or reason.startswith("initial RGB-D identity/extent unavailable:")
            or reason == evidence.get("target_point_association", {}).get("reason")
            or reason in {
                "selected target pixel is not a raised visible top surface",
                "selected pixel has invalid depth",
                "target local support surface is unavailable",
                "top grasp patch contains invalid metric depth",
                "top grasp patch is not flat within calibrated world-z variation",
            }
        )

    def _plan_vision_fallback(
        self, request: InitialPlanningRequest, task: GroundingTaskDescriptor,
        binding: _PlanBinding, evidence: dict[str, Any], error: Exception,
    ) -> PlannerDraft:
        raw = ""
        try:
            self._grounding_scope(request, task, binding, evidence)
            assert request.observation is not None
            messages, audit = fallback_messages(
                request.observation, instruction=task.instruction,
                target_phrase=task.target_phrase, destination_phrase=task.destination_phrase,
                local_failure=str(error),
                nominated_pixel=evidence.get("native_original_pixel_target"),
            )
            evidence.update(
                cloud_vision_fallback=audit,
                cloud_model_image_count=audit["image_count"],
                perception_model_image_count=int(bool(evidence["native_results"])),
                model_image_count=audit["image_count"] + int(bool(evidence["native_results"])),
                cloud_messages_sha256=configuration_hash({"messages": messages}),
                cloud_request_invoked=True,
            )
            started = {"utc": _utcnow().isoformat(), "monotonic_s": monotonic()}
            self._context(binding)
            response = binding.cloud._request_visual(
                messages, CloudVisionDecision.model_json_schema()
            )
            returned = {"utc": _utcnow().isoformat(), "monotonic_s": monotonic()}
            self._context(binding)
            raw = response["choices"][0]["message"]["content"]
            if not isinstance(raw, str):
                raise ValueError("invalid cloud vision response content")
            evidence["cloud_response_content_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
            candidate = CloudVisionDecision.model_validate(_strict_skill_json(raw), strict=True)
            audit["action"] = candidate.action
            if candidate.action != "CANDIDATE":
                return RGBDPlannerAdapter._more_observation(
                    raw, candidate.reason or "cloud vision requests another observation", evidence
                )
            assert candidate.target_normalized_1000 is not None
            assert candidate.destination_normalized_1000 is not None
            target = candidate.target_normalized_1000
            destination = candidate.destination_normalized_1000
            audit["target_normalized_1000"] = list(target)
            audit["destination_normalized_1000"] = list(destination)
            evidence["owned_refresh_required"] = True
            self._owned_refresh = _OwnedRefreshPlan(
                binding, SkillDecision(skills=list(candidate.skills), reason=candidate.reason),
                raw, copy.deepcopy(evidence), started, returned, _utcnow(),
                ((target[0], target[1]), (destination[0], destination[1])),
            )
            return RGBDPlannerAdapter._more_observation(
                raw, "WORKER_OWNED_POST_CLOUD_CAPTURE_REQUIRED", evidence
            )
        except Exception as exc:
            evidence.setdefault("cloud_vision_fallback", {"local_failure": str(error)})[
                "failure_type"
            ] = type(exc).__name__
            return RGBDPlannerAdapter._more_observation(
                raw, "cloud vision fallback unavailable or invalid", evidence
            )

    def plan(self, request: InitialPlanningRequest) -> PlannerDraft:
        """一次云端技能意图；可选真实新采集及独立定位后再构造候选。"""
        if self.worker_owned_refresh:
            pending, self._owned_refresh = self._owned_refresh, None
            if pending is not None:
                return self._resume_owned(request, pending)
            if self._owned_started:
                return PlannerDraft(raw_text="", parse_error="owned planning budget exhausted")
            self._owned_started = True
        role = getattr(self.cloud, "role_snapshot", None)
        binding = _PlanBinding(
            request=request,
            request_hash=configuration_hash(request.model_dump(mode="json")),
            task=self.task,
            task_hash=configuration_hash(self.task.model_dump()),
            points=self.point_provider,
            cloud=self.cloud,
            supplier=self.post_cloud_observation_supplier,
            role=role,
            role_hash=role.digest() if role is not None else None,
            cloud_hash=self._cloud_hash,
            route_options=(self.cloud_vision_fallback, self.component_diagnostic,
                           self.worker_owned_refresh),
        )
        working = request.model_copy(deep=True)
        task = binding.task.model_copy(deep=True)
        observation = working.observation
        evidence = self._evidence(observation, binding)
        raw = ""
        try:
            measured = self._ground(working, task, binding, evidence)
        except (_NativePerceptionFailure, ValueError) as exc:
            if self.cloud_vision_fallback and self._fallback_eligible(exc, evidence):
                return self._plan_vision_fallback(working, task, binding, evidence, exc)
            if not isinstance(exc, _NativePerceptionFailure):
                return RGBDPlannerAdapter._more_observation(raw, str(exc), evidence)
            return PlannerDraft(
                raw_text=raw,
                parse_error=f"native perception failed: {exc}",
                observation_evidence=evidence,
            )
        facts = {
            key: evidence[key]
            for key in (
                "grounded_target",
                "grounded_destination",
                "resolved_top_grasp_tcp",
                "estimated_object_height_m",
                "grasp_geometry_assumption",
            )
        }
        messages = [
            {
                "role": "system",
                "content": (
                    (
                        "This is a MuJoCo software component diagnostic only. "
                        "Skills are evaluated only in simulation; no physical robot is dispatched. "
                        "Development geometry does not grant physical execution qualification. "
                        if self.component_diagnostic else ""
                    )
                    + "Plan a pick-and-place using the supplied measured geometry. "
                    "Return only a JSON object with skills and reason. "
                    "Skills must be "
                    + (
                        "MOVE_ABOVE, APPROACH, GRASP, LIFT, MOVE_TO_REGION, PLACE, RELEASE, RETREAT"
                        if self.worker_owned_refresh
                        else "HOME, MOVE_ABOVE, APPROACH, GRASP, LIFT, MOVE_TO_REGION, "
                        "PLACE, RELEASE, RETREAT, HOME"
                    )
                    + " in that order. "
                    "If uncertain return skills []. Do not output coordinates, targets, "
                    "confidence, safety overrides, identity, timestamps or low-level controls. "
                    "Schema: " + json.dumps(SkillDecision.model_json_schema())
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        **({
                            "execution_scope": "MUJOCO_COMPONENT_DIAGNOSTIC",
                            "hardware_dispatch": False,
                        } if self.component_diagnostic else {}),
                        "instruction": working.user_instruction,
                        "geometry": facts,
                        "geometry_status": (
                            "CALIBRATED_DEVELOPMENT_ESTIMATE_NOT_PHYSICAL_ACCEPTANCE"
                        ),
                    },
                    ensure_ascii=False,
                    allow_nan=False,
                ),
            },
        ]
        evidence["cloud_messages_sha256"] = configuration_hash({"messages": messages})
        evidence["cloud_request_invoked"] = True
        cloud_started = {"utc": _utcnow().isoformat(), "monotonic_s": monotonic()}
        try:
            self._context(binding)
            response = binding.cloud._request_visual(messages, SkillDecision.model_json_schema())
        except Exception as exc:
            return PlannerDraft(
                raw_text="",
                parse_error=f"cloud skill request failed: {type(exc).__name__}",
                observation_evidence=evidence,
            )
        cloud_returned = {"utc": _utcnow().isoformat(), "monotonic_s": monotonic()}
        try:
            raw = response["choices"][0]["message"]["content"]
            if not isinstance(raw, str):
                raise TypeError("cloud content must be text")
            evidence["cloud_response_content_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
            if binding.supplier is None and not self.worker_owned_refresh:
                self._fresh(observation, binding)
            else:
                self._context(binding)
        except ValueError as exc:
            return RGBDPlannerAdapter._more_observation(raw, str(exc), evidence)
        except (KeyError, IndexError, TypeError):
            return PlannerDraft(
                raw_text="",
                parse_error="invalid cloud response envelope",
                observation_evidence=evidence,
            )
        try:
            decision = SkillDecision.model_validate(_strict_skill_json(raw), strict=True)
            if not decision.skills:
                return RGBDPlannerAdapter._more_observation(
                    raw, decision.reason or "cloud requests observation", evidence
                )
            validate_grounded_skill_order(decision.skills)
            if self.worker_owned_refresh and "HOME" in decision.skills:
                raise ValueError("worker requires core skills without optional HOME")
        except (ValidationError, ValueError):
            return PlannerDraft(
                raw_text=raw,
                parse_error="invalid cloud skill-only decision or sequence",
                observation_evidence=evidence,
            )
        if self.worker_owned_refresh:
            evidence["owned_refresh_required"] = True
            self._owned_refresh = _OwnedRefreshPlan(
                binding,
                decision,
                raw,
                copy.deepcopy(evidence),
                cloud_started,
                cloud_returned,
                _utcnow(),
            )
            return RGBDPlannerAdapter._more_observation(
                raw, "WORKER_OWNED_POST_CLOUD_CAPTURE_REQUIRED", evidence
            )
        refresh = None
        try:
            if binding.supplier is not None:
                self._context(binding)
                reference = copy.deepcopy(evidence)
                refresh = {
                    "status": "STARTED",
                    "cloud_started": cloud_started,
                    "cloud_returned": cloud_returned,
                    "supplier_invoked": {"utc": _utcnow().isoformat(), "monotonic_s": monotonic()},
                    "supplier_calls_started": 1,
                }
                evidence["cloud_reference"] = reference
                evidence["post_cloud_revalidation"] = refresh
                try:
                    fresh = binding.supplier()
                except Exception as exc:
                    raise ValueError(f"post_cloud_capture_failed:{type(exc).__name__}") from None
                refresh["supplier_returned"] = {
                    "utc": _utcnow().isoformat(),
                    "monotonic_s": monotonic(),
                }
                self._context(binding)
                policy = validate_post_cloud_observation(
                    observation,
                    fresh,
                    not_before=datetime.fromisoformat(refresh["supplier_invoked"]["utc"]),
                )
                refresh["policy"] = policy
                refresh["fresh_checksum"] = fresh.checksum_sha256
                self._fresh(fresh, binding)
                evidence = self._evidence(fresh, binding)
                evidence.update(
                    {
                        "model_image_count": 2,
                        "perception_model_image_count": 2,
                        "cloud_reference": reference,
                        "post_cloud_revalidation": refresh,
                        "cloud_messages_sha256": reference["cloud_messages_sha256"],
                        "cloud_request_invoked": True,
                        "cloud_response_content_sha256": reference["cloud_response_content_sha256"],
                    }
                )
                working = working.model_copy(update={"observation": fresh})
                measured = self._ground(working, task, binding, evidence)
                if (
                    evidence["opencv_support_mask_sha256"]
                    != reference["opencv_support_mask_sha256"]
                ):
                    raise ValueError("post_cloud_support_mask_changed")
                observation = fresh
            self._fresh(observation, binding)
            draft = build_grounded_contract(working, measured, decision.skills, raw_text=raw)
            self._fresh(observation, binding)
            if refresh is not None:
                refresh["status"] = "PASSED"
                refresh["completed"] = {"utc": _utcnow().isoformat(), "monotonic_s": monotonic()}
                evidence["post_cloud_revalidation"] = copy.deepcopy(refresh)
                evidence["perception_query_count"] = len(evidence["native_results"]) + len(
                    evidence["cloud_reference"]["native_results"]
                )
                draft.observation_evidence = copy.deepcopy(evidence)
                draft._final_plan_admission = self._make_final_plan_admission(binding, observation)
            return draft
        except _NativePerceptionFailure as exc:
            if refresh is not None:
                refresh["status"] = "REJECTED"
                evidence["post_cloud_revalidation"] = copy.deepcopy(refresh)
            return PlannerDraft(
                raw_text=raw,
                parse_error=f"native perception failed: {exc}",
                observation_evidence=evidence,
            )
        except ValueError as exc:
            if refresh is not None:
                refresh["status"] = "REJECTED"
                refresh["reason"] = str(exc)
                evidence["post_cloud_revalidation"] = copy.deepcopy(refresh)
            return RGBDPlannerAdapter._more_observation(raw, str(exc), evidence)


def build_molmo_grounded_planner(
    *,
    service: ModelControlService,
    profile_id: str,
    point_provider: PointProvider,
    task: GroundingTaskDescriptor,
    grasp_profile: str,
    allow_paid: bool = False,
    post_cloud_observation_supplier: Callable[[], RGBDObservation] | None = None,
    worker_owned_refresh: bool = False,
    component_diagnostic: bool = False,
    cloud_vision_fallback: bool = False,
) -> MolmoGroundedPlannerAdapter:
    """复用既有 profile 与密钥服务，保持所选云端身份；默认不允许付费调用。"""
    if calibration_asset_sha256(grasp_profile) is None:
        raise ValueError("explicit registered grasp profile required")
    root = Path(__file__).resolve().parents[3]
    paths = [
        "src/cloud_edge_robot_arm/cloud/planning/models.py",
        "src/cloud_edge_robot_arm/cloud/planning/pipeline.py",
    ] + [
        f"src/cloud_edge_robot_arm/vision/{name}.py"
        for name in (
            "capture",
            "grounded_planner",
            "cloud_vision_fallback",
            "molmo_pointing",
            "point_association",
            "planner",
            "observations",
            "messages",
            "top_grasp",
            "tracking",
            "model_resolver",
            "revalidation",
            "role_models",
        )
    ]
    sources = {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths}
    cloud, _ = resolve_cloud_role(
        service,
        profile_id,
        source_hashes=sources,
        allow_paid=allow_paid,
        grasp_profile=grasp_profile,
        coordinate_system="normalized_1000",
    )
    return MolmoGroundedPlannerAdapter(
        point_provider=point_provider,
        cloud=cloud,
        task=task,
        post_cloud_observation_supplier=post_cloud_observation_supplier,
        worker_owned_refresh=worker_owned_refresh,
        component_diagnostic=component_diagnostic,
        cloud_vision_fallback=cloud_vision_fallback,
    )
