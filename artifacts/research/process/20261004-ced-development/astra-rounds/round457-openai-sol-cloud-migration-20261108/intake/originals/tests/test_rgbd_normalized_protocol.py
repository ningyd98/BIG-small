"""Normalized VLM coordinates must preserve metric grounding and safe skill order."""

from __future__ import annotations

import base64
import io
import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from PIL import Image

from cloud_edge_robot_arm.cloud.planning.models import (
    InitialPlanningRequest,
    SceneObjectSummary,
    SceneSummary,
    TargetRegionSummary,
)
from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.vision import messages
from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot, resolve_visual_planner
from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter
from tests.test_rgbd_messages import _observation

REQUIRED_SKILLS = [
    "MOVE_ABOVE", "APPROACH", "GRASP", "LIFT", "MOVE_TO_REGION", "PLACE", "RELEASE", "RETREAT",
]


def _snapshot(**changes: Any) -> ModelConfigSnapshot:
    values = {
        "provider": "ollama", "model": "qwen3.5:4b",
        "endpoint": "http://127.0.0.1:11434", "weight_digest": "",
        "quantization": "Q4_K_M", "image_size": (4, 4),
        "generation_parameters": {"temperature": 0, "num_ctx": 4096, "num_predict": 128},
        "timeout_s": 60.0,
    }
    return ModelConfigSnapshot(**{**values, **changes})


@pytest.mark.parametrize("point,expected", [
    ((0, 0), (0, 0)),
    ((1000, 1000), (7, 3)),
    ((999, 999), (7, 3)),
    ((250, 250), (2, 1)),
    ((499, 749), (3, 2)),
])
def test_normalized_coordinates_map_directly_to_non_square_original_depth(
    point: tuple[int, int], expected: tuple[int, int],
) -> None:
    """Catches swapped axes, 1000 wrapping and a lossy intermediate image-pixel rounding."""
    converter = getattr(messages, "model_to_observation_pixel", None)
    assert callable(converter), "the model-coordinate protocol converter is missing"
    observation = _observation()
    assert converter(point, observation, coordinate_system="normalized_1000") == expected
    assert converter(
        point, observation, image_size=(4, 4), coordinate_system="normalized_1000",
    ) == expected
    assert converter((1, 0), observation, image_size=(4, 4)) == (3, 1)


@pytest.mark.parametrize("point", [
    (-1, 0), (1001, 0), (0, -1), (0, 1001),
    (True, 0), (0, False), (1.5, 0), ("500", 0), (0,), (0, 0, 0), None,
])
def test_invalid_normalized_coordinates_cannot_select_metric_depth(point: Any) -> None:
    converter = getattr(messages, "model_to_observation_pixel", None)
    assert callable(converter), "the model-coordinate protocol converter is missing"
    with pytest.raises(ValueError):
        converter(point, _observation(), coordinate_system="normalized_1000")


def test_frozen_snapshot_distinguishes_coordinate_protocols() -> None:
    pixel = _snapshot()
    normalized = _snapshot(coordinate_system="normalized_1000")
    assert pixel.coordinate_system == "pixel"
    assert normalized.evidence()["coordinate_system"] == "normalized_1000"
    assert pixel.digest() != normalized.digest()
    with pytest.raises(ValueError):
        replace(normalized, coordinate_system="unknown")


def test_normalized_messages_send_two_registered_images_without_truth() -> None:
    observation = _observation()
    result = messages.build_visual_messages(
        "Move the red cube to the green region", observation,
        image_size=(4, 4), coordinate_system="normalized_1000",
    )
    wire = json.dumps(result)
    assert all(secret not in wire for secret in (
        "oracle-target-secret", "oracle-scene-secret", "oracle-episode-secret",
        "oracle-calibration-secret", "depth_float32_base64", "camera_to_world",
    ))
    assert "1000" in wire
    images = result[-1]["images"]
    assert len(images) == 2 and images[0] != images[1]
    with Image.open(io.BytesIO(base64.b64decode(images[0]))) as rgb:
        assert rgb.size == (4, 2) and rgb.mode == "RGB"
        assert rgb.getpixel((0, 0)) == (240, 10, 10)
        assert rgb.getpixel((3, 0)) == (10, 240, 10)
    with Image.open(io.BytesIO(base64.b64decode(images[1]))) as depth:
        assert depth.size == (4, 2) and depth.mode == "L"
        assert depth.getpixel((0, 0)) == 255 and depth.getpixel((3, 0)) == 1


def _request() -> InitialPlanningRequest:
    return InitialPlanningRequest(
        request_id="coordinate-protocol", user_instruction="Move the red cube to the green region",
        observation=_observation(),
        scene=SceneSummary(
            scene_version=1, updated_at=datetime.now(UTC),
            objects=[SceneObjectSummary(
                object_id="SECRET_ORACLE_OBJECT", object_class="red cube",
                pose=Pose(x=99, y=98, z=97), pose_confidence=1,
            )],
            regions=[TargetRegionSummary(
                region_id="SECRET_ORACLE_REGION", center=Pose(x=88, y=87, z=86),
            )],
        ),
    )


def _stub_model(
    monkeypatch: pytest.MonkeyPatch, *, target: list[int], destination: list[int],
    skills: list[str],
) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []

    def fake_post(path: str, body: dict[str, Any]) -> dict[str, Any]:
        if path == "/api/show":
            return {"capabilities": ["vision"]}
        assert path == "/api/chat"
        requests.append(body)
        return {"message": {"content": json.dumps({
            "target_pixel": target, "destination_pixel": destination,
            "target_label": "red cube", "reported_confidence": 0.9,
            "skills": skills, "reason": "visible surfaces",
        })}}

    monkeypatch.setattr(RGBDPlannerAdapter, "_post", staticmethod(fake_post))
    return requests


def test_planner_grounds_normalized_points_and_preserves_raw_model_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A normalized value must neither index raw depth nor become a resized pixel center."""
    posted = _stub_model(
        monkeypatch, target=[250, 250], destination=[750, 750], skills=REQUIRED_SKILLS,
    )
    planner = resolve_visual_planner(_snapshot(coordinate_system="normalized_1000"))
    draft = planner.plan(_request())
    assert draft.observed_scene is not None
    evidence = draft.observation_evidence
    assert evidence["visual_decision"]["target_pixel"] == [250, 250]
    assert evidence["model_pixel_target"] == [250, 250]
    assert evidence["model_pixel_destination"] == [750, 750]
    assert evidence["original_pixel_target"] == [2, 1]
    assert evidence["original_pixel_destination"] == [6, 3]
    assert evidence["target_visible_surface"] == {"x": 1.5, "y": 2.5, "z": 5.0}
    assert draft.observed_scene.regions[0].center == Pose(x=4.0, y=5.0, z=7.0)
    assert len(posted[0]["messages"][-1]["images"]) == 2
    wire = json.dumps(posted[0])
    assert "SECRET_ORACLE_OBJECT" not in wire and "SECRET_ORACLE_REGION" not in wire


@pytest.mark.parametrize("skills,allowed", [
    (REQUIRED_SKILLS, True),
    (["HOME", *REQUIRED_SKILLS], True),
    ([*REQUIRED_SKILLS, "HOME"], True),
    (["HOME", *REQUIRED_SKILLS, "HOME"], True),
    ([*REQUIRED_SKILLS, "GRASP"], False),
    (["MOVE_ABOVE", *REQUIRED_SKILLS], False),
    ([*REQUIRED_SKILLS[:3], "GRASP", *REQUIRED_SKILLS[3:]], False),
    ([*REQUIRED_SKILLS[:3], "HOME", *REQUIRED_SKILLS[3:]], False),
    (["HOME", "HOME", *REQUIRED_SKILLS], False),
    (REQUIRED_SKILLS[:-1], False),
    (["APPROACH", "MOVE_ABOVE", *REQUIRED_SKILLS[2:]], False),
])
def test_planner_allows_one_ordered_skill_sequence_with_optional_boundary_home(
    monkeypatch: pytest.MonkeyPatch, skills: list[str], allowed: bool,
) -> None:
    """Catches extra actuations hidden behind an otherwise correctly ordered subsequence."""
    _stub_model(monkeypatch, target=[2, 1], destination=[6, 3], skills=skills)
    draft = RGBDPlannerAdapter().plan(_request())
    assert (draft.observed_scene is not None) is allowed
    if allowed:
        assert draft.parsed_json is not None
        assert [step["skill"] for step in draft.parsed_json["steps"]] == skills
    else:
        assert draft.parse_error is not None
        assert draft.parsed_json is None
