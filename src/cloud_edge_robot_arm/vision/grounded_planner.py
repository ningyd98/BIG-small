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

from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, PlannerDraft
from cloud_edge_robot_arm.model_control.service import ModelControlService
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


class _NativePerceptionFailure(RuntimeError):
    pass


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
    ) -> None:
        if cloud.provider != "openai_compatible" or cloud.model_snapshot is None:
            raise ValueError("grounded planning requires an explicit compatible cloud snapshot")
        if post_cloud_observation_supplier is not None and not callable(
            post_cloud_observation_supplier
        ):
            raise ValueError("post-cloud observation supplier must be callable")
        self.post_cloud_observation_supplier = post_cloud_observation_supplier
        self.point_provider = point_provider
        self.cloud = cloud
        self.task = task
        self.model_name = cloud.model_name
        self._cloud_hash = configuration_hash(cloud_request_settings(cloud))

    def _context(self, binding: _PlanBinding) -> None:
        if (
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
        if point.result.status != "POINT" or point.result.normalized_1000 is None:
            raise ValueError("native_target_absent_or_invalid")
        if parse_native_point(point.result.raw_text) != point.result:
            raise ValueError("native_point_raw_result_mismatch")

    def _evidence(
        self, observation: RGBDObservation | None, binding: _PlanBinding
    ) -> dict[str, Any]:
        snapshot = binding.cloud.model_snapshot
        return {
            **(observation.evidence() if observation else {}),
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
            if observation is None or request.user_instruction != task.instruction:
                raise ValueError("task_instruction_or_observation_binding_missing")
            RGBDObservation.model_validate(observation.model_dump())
            self._fresh(observation, binding)
            profile = binding.cloud.model_snapshot.grasp_profile
            if (
                min(observation.width, observation.height) < 64
                or observation.source != "mujoco_camera"
                or not observation.episode_id
                or not observation.episode_id.strip()
                or not observation.calibration_version
                or not observation.calibration_version.strip()
                or calibration_asset_sha256(profile) is None
            ):
                raise ValueError("native_grounding_domain_or_calibration_unavailable")
            evidence["grasp_profile"] = profile
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
                    raise _NativePerceptionFailure(type(exc).__name__) from None
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
                grasp_profile=profile,
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

    def plan(self, request: InitialPlanningRequest) -> PlannerDraft:
        """一次云端技能意图；可选真实新采集及独立定位后再构造候选。"""
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
        )
        working = request.model_copy(deep=True)
        task = binding.task.model_copy(deep=True)
        observation = working.observation
        evidence = self._evidence(observation, binding)
        raw = ""
        try:
            measured = self._ground(working, task, binding, evidence)
        except _NativePerceptionFailure as exc:
            return PlannerDraft(
                raw_text=raw,
                parse_error=f"native perception failed: {exc}",
                observation_evidence=evidence,
            )
        except ValueError as exc:
            return RGBDPlannerAdapter._more_observation(raw, str(exc), evidence)
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
                    "Plan a pick-and-place using the supplied measured geometry. "
                    "Return only a JSON object with skills and reason. "
                    "Skills must be HOME, MOVE_ABOVE, APPROACH, GRASP, LIFT, MOVE_TO_REGION, "
                    "PLACE, RELEASE, RETREAT, HOME in that order. "
                    "If uncertain return skills []. Do not output coordinates, targets, "
                    "confidence, safety overrides, identity, timestamps or low-level controls. "
                    "Schema: " + json.dumps(SkillDecision.model_json_schema())
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "instruction": working.user_instruction,
                        "geometry": facts,
                        "geometry_status": (
                            "CALIBRATED_DEVELOPMENT_ESTIMATE_"
                            "NOT_PHYSICAL_ACCEPTANCE"
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
            if binding.supplier is None:
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
        except (ValidationError, ValueError):
            return PlannerDraft(
                raw_text=raw,
                parse_error="invalid cloud skill-only decision or sequence",
                observation_evidence=evidence,
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
) -> MolmoGroundedPlannerAdapter:
    """复用既有 profile 与密钥服务，保持所选云端身份；默认不允许付费调用。"""
    if calibration_asset_sha256(grasp_profile) is None:
        raise ValueError("explicit registered grasp profile required")
    root = Path(__file__).resolve().parents[3]
    paths = [
        f"src/cloud_edge_robot_arm/vision/{name}.py"
        for name in (
            "capture",
            "grounded_planner",
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
    )
