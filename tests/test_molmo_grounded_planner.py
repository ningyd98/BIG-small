"""识别点到原始深度几何及云端技能的真实代码契约测试。"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

import numpy as np
import pytest

from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest
from tests.test_opencv_target_evidence import scene

SKILLS = [
    "HOME",
    "MOVE_ABOVE",
    "APPROACH",
    "GRASP",
    "LIFT",
    "MOVE_TO_REGION",
    "PLACE",
    "RELEASE",
    "RETREAT",
    "HOME",
]


def request_scene(**kwargs):
    observation = scene(started=datetime.now(UTC), source="mujoco_camera", **kwargs)
    return InitialPlanningRequest(
        request_id="grounded-test",
        user_instruction="Move the red block to the green region.",
        observation=observation,
    )


def grounded(request):
    from cloud_edge_robot_arm.vision.planner import ground_observation

    return ground_observation(
        request,
        request.observation,
        target_pixel=(12, 26),
        destination_pixel=(52, 27),
        target_label="red block",
        grasp_profile="mujoco_upright_box_v2",
        evidence={"source_marker": "CPU_GEOMETRY_FIXTURE"},
    )


def test_grounding_helper_has_no_model_confidence():
    result = grounded(request_scene())
    e = result.evidence
    assert e["original_pixel_target"] == [12, 26]
    assert e["grounded_target"] == pytest.approx({"x": -0.2632, "y": 0.0564, "z": 0.06}, abs=1e-7)
    assert e["grounded_destination"] == pytest.approx({"x": 0.12, "y": 0.05, "z": 0})
    assert e["resolved_top_grasp_tcp"]["z"] == pytest.approx(0.04, abs=1e-7)
    assert e["estimated_object_height_m"] == pytest.approx(0.06, abs=1e-7)
    assert "reported_confidence" not in json.dumps(e)
    assert result.scene.objects[0].pose is None


@pytest.mark.parametrize("endpoint", [(12, 26), (52, 27)])
def test_grounding_rejects_zero_depth_at_either_endpoint(endpoint):
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    request = request_scene()
    payload = request.observation.model_dump()
    depth = np.asarray(request.observation.depth_values(), dtype="<f4").reshape(64, 80)
    depth[endpoint[1], endpoint[0]] = 0
    payload.update(
        depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
        valid_mask_base64=None,
        checksum_sha256="",
    )
    request = request.model_copy(update={"observation": RGBDObservation.model_validate(payload)})
    with pytest.raises(ValueError, match="invalid depth"):
        grounded(request)


@pytest.mark.parametrize("change", ["profile", "source", "table", "patch", "height"])
def test_grounding_rejects_invalid_depth_and_profile(change):
    from cloud_edge_robot_arm.vision.planner import ground_observation

    request = request_scene(
        damage="depth_spike" if change == "patch" else None, lift=0.15 if change == "height" else 0
    )
    observation = request.observation
    if change == "source":
        observation = observation.model_copy(update={"source": "rgbd_camera"})
    with pytest.raises(ValueError):
        ground_observation(
            request,
            observation,
            target_pixel=(30, 40) if change == "table" else (12, 26),
            destination_pixel=(52, 27),
            target_label="red block",
            grasp_profile="bad" if change == "profile" else "mujoco_upright_box_v2",
            evidence={},
        )


@pytest.mark.parametrize("order", [SKILLS, SKILLS[1:], SKILLS[:-1], SKILLS[1:-1]])
def test_contract_builder_preserves_whitelist_and_trusted_fields(order):
    from cloud_edge_robot_arm.vision.planner import build_grounded_contract

    request = request_scene()
    draft = build_grounded_contract(
        request, grounded(request), order, raw_text="actual cloud content"
    )
    assert draft.raw_text == "actual cloud content"
    assert [s["skill"] for s in draft.parsed_json["steps"]] == order
    assert draft.parsed_json["task_id"] == "" and draft.parsed_json["plan_version"] == 0
    assert draft.parsed_json["issued_at"] == "" and draft.parsed_json["command_seq"] == 0


@pytest.mark.parametrize(
    "order", [[], ["GRASP"], list(reversed(SKILLS)), SKILLS + ["HOME"], ["HOME"] + SKILLS]
)
def test_contract_builder_rejects_bad_skill_order(order):
    from cloud_edge_robot_arm.vision.planner import build_grounded_contract

    request = request_scene()
    with pytest.raises(ValueError, match="sequence"):
        build_grounded_contract(request, grounded(request), order, raw_text="actual cloud content")
