"""Bounded image-only candidates; metric evidence and execution stay local."""

from __future__ import annotations

import base64
import hashlib
import io
import json
from typing import Any, Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.planner import SkillIntent, validate_grounded_skill_order


class CloudVisionDecision(BaseModel):
    """Cloud points nominate visible pixels, never metric poses or safety facts."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    action: Literal["CANDIDATE", "REOBSERVE", "ABSENT"]
    target_normalized_1000: list[int] | None = Field(default=None, min_length=2, max_length=2)
    destination_normalized_1000: list[int] | None = Field(
        default=None, min_length=2, max_length=2
    )
    skills: list[SkillIntent] = Field(default_factory=list, max_length=8)
    reason: str = Field(default="", max_length=500)

    @field_validator("target_normalized_1000", "destination_normalized_1000")
    @classmethod
    def bounded_point(cls, value: list[int] | None) -> list[int] | None:
        if value is not None and any(not 0 <= v <= 1000 for v in value):
            raise ValueError("cloud image coordinate outside [0,1000]")
        return value

    @model_validator(mode="after")
    def conditional_candidate(self) -> CloudVisionDecision:
        if self.action == "CANDIDATE":
            if self.target_normalized_1000 is None or self.destination_normalized_1000 is None:
                raise ValueError("candidate requires both image points")
            validate_grounded_skill_order(self.skills)
            if "HOME" in self.skills:
                raise ValueError("component candidate requires core skills only")
        elif self.target_normalized_1000 is not None or (
            self.destination_normalized_1000 is not None or self.skills
        ):
            raise ValueError("refusal cannot include candidate points or skills")
        return self


def fallback_messages(
    observation: RGBDObservation,
    *,
    instruction: str,
    target_phrase: str,
    destination_phrase: str,
    local_failure: str,
    nominated_pixel: list[int] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Send original RGB and an optional crop; retain exact full-image mapping."""
    images = [observation.rgb_png_base64]
    image_evidence: list[dict[str, Any]] = [{
        "role": "FULL_ORIGINAL_RGB",
        "width": observation.width,
        "height": observation.height,
        "sha256": observation.evidence()["rgb_sha256"],
    }]
    if nominated_pixel is not None and len(nominated_pixel) == 2 and all(
        type(v) is int for v in nominated_pixel
    ):
        u, v = nominated_pixel
        if 0 <= u < observation.width and 0 <= v < observation.height:
            box = (max(0, u - 48), max(0, v - 48),
                   min(observation.width, u + 49), min(observation.height, v + 49))
            if box != (0, 0, observation.width, observation.height):
                with Image.open(io.BytesIO(base64.b64decode(images[0]))) as original:
                    buffer = io.BytesIO()
                    original.crop(box).save(buffer, format="PNG")
                raw = buffer.getvalue()
                images.append(base64.b64encode(raw).decode("ascii"))
                image_evidence.append({
                    "role": "RGB_CROP_CONTEXT_ONLY", "full_image_box_xyxy": list(box),
                    "width": box[2] - box[0], "height": box[3] - box[1],
                    "sha256": hashlib.sha256(raw).hexdigest(),
                })
    audit: dict[str, Any] = {
        "schema": "cloud_vision_fallback.v1", "local_failure": local_failure,
        "reference_observation_id": observation.observation_id,
        "reference_checksum": observation.checksum_sha256,
        "coordinate_system": "normalized_1000_full_original_image",
        "images": image_evidence, "image_count": len(images),
        "metric_geometry_source": "FRESH_LOCAL_ORIGINAL_DEPTH_ONLY",
        "hardware_dispatch": False,
    }
    messages: list[dict[str, Any]] = [{
        "role": "system",
        "content": (
            "This is a paused MuJoCo software component diagnostic. No hardware is dispatched. "
            "Review the original RGB because local perception was insufficient. Return JSON only. "
            "CANDIDATE requires visible target and destination points in normalized [0,1000] "
            "coordinates of the FIRST FULL ORIGINAL image; any second image is crop context only. "
            "Nominate an interior target top point and a destination interior point. "
            "Skills are conditional intentions only: MOVE_ABOVE, APPROACH, GRASP, LIFT, "
            "MOVE_TO_REGION, PLACE, RELEASE, RETREAT, in that order. "
            "Local fresh RGB-D geometry must independently validate before simulated execution. "
            "Use REOBSERVE or ABSENT with null points and skills [] if evidence is insufficient. "
            "Do not infer hidden surfaces or missing depth. Do not output metric coordinates, "
            "confidence, timestamps, identity, safety overrides or low-level controls. Schema: "
            + json.dumps(CloudVisionDecision.model_json_schema())
        ),
    }, {
        "role": "user",
        "content": json.dumps({
            "instruction": instruction, "target_phrase": target_phrase,
            "destination_phrase": destination_phrase, "local_failure": local_failure,
            "images": image_evidence,
        }, ensure_ascii=False, allow_nan=False),
        "images": images,
    }]
    return messages, audit
