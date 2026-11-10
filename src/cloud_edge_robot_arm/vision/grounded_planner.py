"""Molmo 识别定位、OpenCV 米制几何与现有云端技能规划的显式组合。"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
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
    RGBDPlannerAdapter,
    SkillIntent,
    build_grounded_contract,
    ground_observation,
)
from cloud_edge_robot_arm.vision.role_models import (
    cloud_request_settings,
    configuration_hash,
    resolve_cloud_role,
)
from cloud_edge_robot_arm.vision.top_grasp import calibration_asset_sha256
from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker


def _utcnow() -> datetime:
    return datetime.now(UTC)


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
    ) -> None:
        if cloud.provider != "openai_compatible" or cloud.model_snapshot is None:
            raise ValueError("grounded planning requires an explicit compatible cloud snapshot")
        self.point_provider = point_provider
        self.cloud = cloud
        self.task = task
        self.model_name = cloud.model_name
        self._cloud_hash = configuration_hash(cloud_request_settings(cloud))

    def _fresh(self, observation: RGBDObservation) -> None:
        age = (_utcnow() - observation.captured_at).total_seconds()
        if age < -0.05 or age > 5:
            raise ValueError("capture_time_not_fresh")
        if configuration_hash(cloud_request_settings(self.cloud)) != self._cloud_hash:
            raise ValueError("selected_cloud_configuration_changed")

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

    def plan(self, request: InitialPlanningRequest) -> PlannerDraft:
        """定位与几何先成立，再请求云端；任一绑定或测量失败均停止候选生成。"""
        observation = request.observation
        evidence: dict[str, Any] = {
            **(observation.evidence() if observation else {}),
            "model_image_count": 1,
            "perception_model_image_count": 1,
            "cloud_model_image_count": 0,
            "perception_input_mode": "NATIVE_RGB",
            "perception_model": MODEL_ID,
            "depth_consumed_by": "DETERMINISTIC_RGBD_OPENCV",
            "cloud_model": self.cloud.model_name,
            "cloud_request_settings_hash": self._cloud_hash,
            "task_descriptor_sha256": configuration_hash(self.task.model_dump()),
            "native_results": [],
            "hardware_dispatch": False,
        }
        raw = ""
        try:
            if observation is None or request.user_instruction != self.task.instruction:
                raise ValueError("task_instruction_or_observation_binding_missing")
            # model_copy 不能绕过采集校验；重新验证原 checksum，绝不刷新时间戳。
            RGBDObservation.model_validate(observation.model_dump())
            self._fresh(observation)
            profile = self.cloud.model_snapshot.grasp_profile
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
                f"visible top center of {self.task.target_phrase}",
                f"interior of {self.task.destination_phrase}",
            )
            points = []
            for query in queries:
                self._fresh(observation)
                try:
                    point = self.point_provider.point(observation, query)
                except (RuntimeError, OSError, TimeoutError) as exc:
                    return PlannerDraft(
                        raw_text="",
                        parse_error=(f"native perception failed: {type(exc).__name__}"),
                        observation_evidence=evidence,
                    )
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
                self._fresh(observation)
                points.append(
                    model_to_observation_pixel(
                        point.result.normalized_1000,
                        observation,
                        coordinate_system="normalized_1000",
                    )
                )
            measured = ground_observation(
                request,
                observation,
                target_pixel=points[0],
                destination_pixel=points[1],
                target_label=self.task.target_label,
                grasp_profile=profile,
                evidence=evidence,
            )
            evidence = measured.evidence
            tracker = OpenCVTargetTracker(observation, evidence)
            evidence["opencv_initial_geometry"] = {
                "target": tracker._public(tracker.initial),
                "destination": tracker._public(tracker.destination),
                "algorithm_sha256": tracker.algorithm_sha256,
                "calibration_sha256": tracker.calibration_sha256,
            }
            self._fresh(observation)
        except ValueError as exc:
            # 共享几何异常可携带部分测量证据；不把部分结果提升为可执行合同。
            evidence = getattr(exc, "evidence", evidence)
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
                    "Schema: "
                    + json.dumps(SkillDecision.model_json_schema())
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "instruction": request.user_instruction,
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
        try:
            response = self.cloud._request_visual(messages, SkillDecision.model_json_schema())
        except Exception as exc:
            return PlannerDraft(
                raw_text="",
                parse_error=f"cloud skill request failed: {type(exc).__name__}",
                observation_evidence=evidence,
            )
        try:
            raw = response["choices"][0]["message"]["content"]
            if not isinstance(raw, str):
                raise TypeError("cloud content must be text")
            evidence["cloud_response_content_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
            self._fresh(observation)
        except ValueError as exc:
            return RGBDPlannerAdapter._more_observation(raw, str(exc), evidence)
        except (KeyError, IndexError, TypeError):
            return PlannerDraft(
                raw_text="",
                parse_error="invalid cloud response envelope",
                observation_evidence=evidence,
            )
        try:
            decision = SkillDecision.model_validate_json(raw, strict=True)
            if not decision.skills:
                return RGBDPlannerAdapter._more_observation(
                    raw, decision.reason or "cloud requests observation", evidence
                )
            return build_grounded_contract(request, measured, decision.skills, raw_text=raw)
        except (ValidationError, ValueError):
            return PlannerDraft(
                raw_text=raw,
                parse_error="invalid cloud skill-only decision or sequence",
                observation_evidence=evidence,
            )


def build_molmo_grounded_planner(
    *,
    service: ModelControlService,
    profile_id: str,
    point_provider: PointProvider,
    task: GroundingTaskDescriptor,
    grasp_profile: str,
    allow_paid: bool = False,
) -> MolmoGroundedPlannerAdapter:
    """复用既有 profile 与密钥服务，保持所选云端身份；默认不允许付费调用。"""
    if calibration_asset_sha256(grasp_profile) is None:
        raise ValueError("explicit registered grasp profile required")
    root = Path(__file__).resolve().parents[3]
    paths = [
        f"src/cloud_edge_robot_arm/vision/{name}.py"
        for name in (
            "grounded_planner",
            "molmo_pointing",
            "planner",
            "observations",
            "messages",
            "top_grasp",
            "tracking",
            "model_resolver",
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
    return MolmoGroundedPlannerAdapter(point_provider=point_provider, cloud=cloud, task=task)
