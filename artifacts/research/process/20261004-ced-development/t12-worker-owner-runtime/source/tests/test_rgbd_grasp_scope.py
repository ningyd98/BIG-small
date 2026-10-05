"""Only trusted, explicit MuJoCo box profiles may claim calibrated grasp geometry."""

from __future__ import annotations

import base64
import io
import json
import struct
from datetime import UTC, datetime
from typing import Any, Literal

import pytest
from PIL import Image

from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
from cloud_edge_robot_arm.vision.model_resolver import resolve_visual_planner
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter
from tests.test_rgbd_normalized_protocol import REQUIRED_SKILLS, _snapshot


def _scene(source: Literal["mujoco_camera", "rgbd_camera", "isaac_camera"]) -> RGBDObservation:
    png = io.BytesIO()
    Image.new("RGB", (64, 64), (180, 50, 40)).save(png, format="PNG")
    depths = [2.0] * 4096
    for v in range(28, 37):
        for u in range(28, 37):
            depths[v * 64 + u] = 1.92
    return RGBDObservation(
        frame_id="scope-test", captured_at=datetime.now(UTC), sim_time_s=0,
        width=64, height=64, rgb_png_base64=base64.b64encode(png.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(struct.pack("<4096f", *depths)).decode(),
        intrinsics=(64, 64, 31.5, 31.5),
        camera_to_world=(1, 0, 0, 0, 0, -1, 0, 0, 0, 0, -1, 3, 0, 0, 0, 1),
        source=source,
    )


def _decision(monkeypatch: pytest.MonkeyPatch, label: str) -> None:
    def fake_post(path: str, body: dict[str, Any]) -> dict[str, Any]:
        if path == "/api/show":
            return {"capabilities": ["vision"]}
        assert path == "/api/chat"
        return {"message": {"content": json.dumps({
            "target_pixel": [32, 32], "destination_pixel": [8, 8],
            "target_label": label, "reported_confidence": 0.95, "skills": REQUIRED_SKILLS,
        })}}

    monkeypatch.setattr(RGBDPlannerAdapter, "_post", staticmethod(fake_post))


def _request(
    source: Literal["mujoco_camera", "rgbd_camera", "isaac_camera"],
) -> InitialPlanningRequest:
    return InitialPlanningRequest(
        request_id="scope-test", user_instruction="Move the requested object",
        observation=_scene(source),
        scene=SceneSummary(scene_version=1, updated_at=datetime.now(UTC)),
    )


def test_snapshot_requires_explicit_grasp_profile_and_hashes_it() -> None:
    unconfigured = _snapshot()
    assert unconfigured.grasp_profile == "unconfigured"
    configured = _snapshot(grasp_profile="mujoco_upright_box_v1")
    assert configured.evidence()["grasp_profile"] == "mujoco_upright_box_v1"
    assert configured.digest() != unconfigured.digest()


@pytest.mark.parametrize("profile", ["other_robot", None, True, []])
def test_invalid_grasp_profile_is_rejected(profile: Any) -> None:
    with pytest.raises(ValueError, match="grasp profile"):
        _snapshot(grasp_profile=profile)


@pytest.mark.parametrize("label", ["red cube", "fragile glass cup"])
@pytest.mark.parametrize("with_snapshot", [False, True])
def test_model_label_cannot_enable_an_unconfigured_grasp(
    monkeypatch: pytest.MonkeyPatch, label: str, with_snapshot: bool,
) -> None:
    _decision(monkeypatch, label)
    planner = (
        resolve_visual_planner(_snapshot(image_size=(64, 64)))
        if with_snapshot else RGBDPlannerAdapter()
    )
    draft = planner.plan(_request("mujoco_camera"))
    assert draft.observed_scene is None
    assert draft.parsed_json and draft.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert draft.observation_evidence["top_grasp_offset_status"] == "NOT_CONFIGURED"
    assert "resolved_top_grasp_tcp" not in draft.observation_evidence


@pytest.mark.parametrize("source", ["rgbd_camera", "isaac_camera"])
def test_mujoco_grasp_profile_cannot_calibrate_other_camera_sources(
    monkeypatch: pytest.MonkeyPatch,
    source: Literal["rgbd_camera", "isaac_camera"],
) -> None:
    _decision(monkeypatch, "red cube")
    planner = resolve_visual_planner(
        _snapshot(image_size=(64, 64), grasp_profile="mujoco_upright_box_v1")
    )
    draft = planner.plan(_request(source))
    assert draft.observed_scene is None
    assert draft.parsed_json and draft.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert draft.observation_evidence["top_grasp_offset_status"] == "NOT_CONFIGURED"
    assert "resolved_top_grasp_tcp" not in draft.observation_evidence


def test_trusted_mujoco_box_profile_records_approved_calibration_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _decision(monkeypatch, "red cube")
    planner = resolve_visual_planner(
        _snapshot(image_size=(64, 64), grasp_profile="mujoco_upright_box_v1")
    )
    draft = planner.plan(_request("mujoco_camera"))
    assert draft.observed_scene is not None
    evidence = draft.observation_evidence
    assert evidence["grasp_profile"] == "mujoco_upright_box_v1"
    assert evidence["top_grasp_offset_status"] == "CALIBRATED_RGBD_TOP_GRASP_V1"
    assert evidence["grasp_calibration_asset_sha256"] == (
        "182fb2bc068ba44de394622f819ae444eb7fbe51df5c5311591a8abb97bf6a08"
    )
    assert evidence["resolved_top_grasp_tcp"]["z"] == pytest.approx(1.05, abs=1e-7)
