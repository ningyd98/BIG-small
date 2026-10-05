"""Exercise real HTTP image transport, metric grounding and planning gates."""

from __future__ import annotations

import base64
import io
import json
import struct
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from cloud_edge_robot_arm.cloud.api.app import create_app
from cloud_edge_robot_arm.cloud.planning.models import (
    InitialPlanningRequest,
    SceneObjectSummary,
    SceneSummary,
    TargetRegionSummary,
)
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
from cloud_edge_robot_arm.contracts import Pose
from tests.test_rgbd_observations import observation_payload


def test_planning_http_sends_both_images_and_grounds_selected_depth() -> None:
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter

    received: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append(body)
            if self.path == "/api/show":
                response = {"capabilities": ["vision"]}
            else:
                response = {
                    "message": {
                        "content": json.dumps(
                            {
                                "target_pixel": [1, 0],
                                "destination_pixel": [0, 1],
                                "target_label": "red cube",
                                "confidence": 0.9,
                                "skills": [
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
                                ],
                            }
                        )
                    }
                }
            encoded = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        planner = RGBDPlannerAdapter(base_url=f"http://127.0.0.1:{server.server_port}")
        observation = RGBDObservation.model_validate(observation_payload())
        request = InitialPlanningRequest(
            request_id="rgbd-http",
            user_instruction="将红色方块放到绿色区域",
            observation=observation,
            scene=SceneSummary(scene_version=1, updated_at=datetime.now(UTC)),
        )
        draft = planner.plan(request)
        assert draft.observed_scene is not None
        assert draft.observed_scene.objects[0].pose is None
        assert draft.observation_evidence["target_visible_surface"]["x"] == 2
        assert draft.observation_evidence["target_visible_surface"]["z"] == 5
        assert draft.observation_evidence["top_grasp_offset_from_surface_m"] is None
        images = received[-1]["messages"][-1]["images"]
        assert len(images) == 2
        assert images[0] == observation.rgb_png_base64
        assert images[1] != images[0]
        assert "objects" not in received[-1]["messages"][-1]["content"]
        result = PlanningPipeline(planner=planner).process(request)
        assert result.outcome == "PLANNED"
        assert result.contract is not None
        assert result.contract.task_target.object_id == "visual_target"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_wire_payload_contains_two_images_no_truth(monkeypatch: pytest.MonkeyPatch) -> None:
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter

    bodies: list[dict[str, Any]] = []

    def fake_post(path: str, body: dict[str, Any]) -> dict[str, Any]:
        if path == "/api/show":
            return {"capabilities": ["vision"]}
        bodies.append(body)
        return {
            "message": {
                "content": json.dumps(
                    {
                        "target_pixel": None,
                        "destination_pixel": None,
                        "target_label": "unknown",
                        "reported_confidence": 0,
                        "skills": [],
                        "reason": "uncertain",
                    }
                )
            }
        }

    monkeypatch.setattr(RGBDPlannerAdapter, "_post", staticmethod(fake_post))
    request = InitialPlanningRequest(
        request_id="decoy",
        user_instruction="把红色方块放到绿色区域",
        observation=RGBDObservation.model_validate(observation_payload()),
        scene=SceneSummary(
            scene_version=1,
            updated_at=datetime.now(UTC),
            objects=[
                SceneObjectSummary(
                    object_id="SECRET_ORACLE_OBJECT",
                    object_class="red cube",
                    pose=Pose(x=99, y=98, z=97),
                    pose_confidence=1,
                )
            ],
            regions=[
                TargetRegionSummary(
                    region_id="SECRET_ORACLE_REGION",
                    center=Pose(x=88, y=87, z=86),
                )
            ],
        ),
    )
    RGBDPlannerAdapter().plan(request)

    assert len(bodies) == 1
    assert bodies[0]["stream"] is False
    messages = bodies[0]["messages"]
    assert len(messages) == 2
    assert len(messages[1]["images"]) == 2
    assert messages[1]["images"][0] != messages[1]["images"][1]
    wire = json.dumps(bodies[0])
    assert "SECRET_ORACLE_OBJECT" not in wire
    assert "SECRET_ORACLE_REGION" not in wire
    assert '"x": 99' not in wire
    assert '"x": 88' not in wire


def test_default_api_rejects_text_only_planning() -> None:
    with TestClient(create_app()) as client:
        result = client.post(
            "/api/v1/plans",
            json={
                "request_id": "text-only",
                "user_instruction": "pick red cube",
                "scene": {"scene_version": 1, "updated_at": datetime.now(UTC).isoformat()},
            },
        )
    assert result.status_code == 201
    assert result.json()["outcome"] == "REQUEST_MORE_OBSERVATION"
    assert "RGBD" in result.json()["reason"]


def test_stale_rgbd_blocks_before_model_call() -> None:
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter

    payload = observation_payload()
    payload["captured_at"] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    request = InitialPlanningRequest(
        request_id="stale",
        user_instruction="pick",
        observation=RGBDObservation.model_validate(payload),
        scene=SceneSummary(scene_version=1, updated_at=datetime.now(UTC)),
    )
    result = PlanningPipeline(planner=RGBDPlannerAdapter(base_url="http://127.0.0.1:1")).process(
        request
    )
    assert result.outcome == "REQUEST_MORE_OBSERVATION"
    assert "stale" in result.reason


def test_model_control_default_dry_run_does_not_return_fake_contract(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cloud_edge_robot_arm.model_control.secret_store import InMemorySecretStore
    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository

    # Keep this failure-path assertion deterministic when a real local model is installed.
    monkeypatch.setenv("BIGSMALL_VLM_BASE_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("BIGSMALL_VLM_MODEL", "unavailable-vision-model")
    service = ModelControlService(
        repository=SQLiteModelProfileRepository(tmp_path / "models.db"),
        secret_store=InMemorySecretStore(),
    )
    result = service.planner_dry_run(
        user_instruction="pick cube", sample_scene="S01_NORMAL_STATIC", control_mode="ETEAC"
    )
    assert result["input_mode"] == "RGBD"
    assert result["parse_result"] != "NOT_DISPATCHED"
    assert result["final_contract"] is None
    assert result["dispatch"] is False


def test_scaled_pixels_map_to_original_depth(monkeypatch: pytest.MonkeyPatch) -> None:
    from cloud_edge_robot_arm.vision.model_resolver import (
        ModelConfigSnapshot,
        resolve_visual_planner,
    )
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter

    payload = observation_payload()
    image = io.BytesIO()
    Image.new("RGB", (4, 4), (255, 0, 0)).save(image, format="PNG")
    payload.update(
        width=4,
        height=4,
        rgb_png_base64=base64.b64encode(image.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(struct.pack("<16f", *([2.0] * 16))).decode(),
    )
    observation = RGBDObservation.model_validate(payload)
    snapshot = ModelConfigSnapshot(
        provider="ollama",
        model="qwen3.5:4b",
        endpoint="http://127.0.0.1:11434",
        weight_digest="",
        quantization="Q4_K_M",
        image_size=(2, 2),
        generation_parameters={"temperature": 0, "num_ctx": 4096, "num_predict": 128},
        timeout_s=60.0,
    )
    planner = resolve_visual_planner(snapshot)
    posted: list[dict[str, Any]] = []

    def fake_post(path: str, body: dict[str, Any]) -> dict[str, Any]:
        if path == "/api/show":
            return {"capabilities": ["vision"]}
        posted.append(body)
        return {
            "message": {
                "content": json.dumps(
                    {
                        "target_pixel": [0, 0],
                        "destination_pixel": [1, 0],
                        "target_label": "red cube",
                        "reported_confidence": 0.9,
                        "skills": [
                            "HOME",
                            "MOVE_ABOVE",
                            "APPROACH",
                            "GRASP",
                            "LIFT",
                            "MOVE_TO_REGION",
                            "PLACE",
                            "RELEASE",
                            "RETREAT",
                        ],
                        "reason": "visible target",
                    }
                )
            }
        }

    monkeypatch.setattr(RGBDPlannerAdapter, "_post", staticmethod(fake_post))
    draft = planner.plan(
        InitialPlanningRequest(
            request_id="scaled",
            user_instruction="pick red cube",
            observation=observation,
            scene=SceneSummary(scene_version=1, updated_at=datetime.now(UTC)),
        )
    )
    assert draft.observed_scene is not None
    assert draft.observed_scene.objects[0].pose is None
    assert (
        draft.observation_evidence["target_visible_surface"]
        == observation.world_point((1, 1)).model_dump()
    )
    assert draft.observed_scene.regions[0].center == observation.world_point((3, 1))
    assert draft.observation_evidence["model_pixel_target"] == [0, 0]
    assert draft.observation_evidence["original_pixel_target"] == [1, 1]
    assert len(posted[0]["messages"][-1]["images"]) == 2
    for encoded in posted[0]["messages"][-1]["images"]:
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as delivered:
            assert delivered.size == (2, 2)


@pytest.mark.parametrize(
    "target,skills,expected",
    [
        (
            [99, 0],
            [
                "HOME",
                "MOVE_ABOVE",
                "APPROACH",
                "GRASP",
                "LIFT",
                "MOVE_TO_REGION",
                "PLACE",
                "RELEASE",
                "RETREAT",
            ],
            "REQUEST_MORE_OBSERVATION",
        ),
        ([1, 0], ["OVERRIDE_SAFETY"], "PLANNER_FAILED"),
    ],
)
def test_invalid_pixel_or_skill_blocks_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    target: list[int],
    skills: list[str],
    expected: str,
) -> None:
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter

    def fake_post(path: str, body: dict[str, Any]) -> dict[str, Any]:
        if path == "/api/show":
            return {"capabilities": ["vision"]}
        return {
            "message": {
                "content": json.dumps(
                    {
                        "target_pixel": target,
                        "destination_pixel": [0, 1],
                        "target_label": "red cube",
                        "reported_confidence": 0.9,
                        "skills": skills,
                        "reason": "",
                    }
                )
            }
        }

    monkeypatch.setattr(RGBDPlannerAdapter, "_post", staticmethod(fake_post))
    request = InitialPlanningRequest(
        request_id="invalid-" + expected,
        user_instruction="pick red cube",
        observation=RGBDObservation.model_validate(observation_payload()),
        scene=SceneSummary(scene_version=1, updated_at=datetime.now(UTC)),
    )
    result = PlanningPipeline(planner=RGBDPlannerAdapter()).process(request)
    assert result.outcome == expected
    assert result.contract is None


def test_active_profile_snapshot_is_stable(tmp_path) -> None:
    from cloud_edge_robot_arm.model_control.models import PlannerProviderKind
    from cloud_edge_robot_arm.model_control.secret_store import InMemorySecretStore
    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository

    service = ModelControlService(
        repository=SQLiteModelProfileRepository(tmp_path / "profiles.db"),
        secret_store=InMemorySecretStore(),
    )
    first = service.create_profile(
        display_name="first",
        provider_kind=PlannerProviderKind.OLLAMA,
        model_name="qwen3.5:4b",
        base_url="http://127.0.0.1:11434",
    )
    service.activate_profile(first.profile_id)
    running = service.visual_planner()
    service.update_profile(first.profile_id, model_name="another-vision-model")
    later = service.visual_planner()
    assert running.model_name == "qwen3.5:4b"
    assert running.model_snapshot.model == "qwen3.5:4b"
    assert later.model_name == "another-vision-model"


def test_frozen_weight_digest_rejects_replaced_local_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    from cloud_edge_robot_arm.vision.model_resolver import (
        ModelConfigSnapshot,
        resolve_visual_planner,
    )
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from cloud_edge_robot_arm.vision.planner import RGBDModelUnavailable, RGBDPlannerAdapter

    snapshot = ModelConfigSnapshot(
        provider="ollama",
        model="qwen3.5:4b",
        endpoint="http://127.0.0.1:11434",
        weight_digest="a" * 64,
        quantization="Q4_K_M",
        image_size=(2, 2),
        generation_parameters={"temperature": 0},
        timeout_s=60.0,
    )
    planner = resolve_visual_planner(snapshot)
    calls: list[str] = []

    def fake_post(path: str, body: dict[str, Any]) -> dict[str, Any]:
        calls.append(path)
        if path == "/api/show":
            return {"capabilities": ["vision"]}
        raise AssertionError("chat cannot run after digest mismatch")

    monkeypatch.setattr(RGBDPlannerAdapter, "_post", staticmethod(fake_post))
    monkeypatch.setattr(
        RGBDPlannerAdapter,
        "_get",
        lambda self, path: {"models": [{"name": "qwen3.5:4b", "digest": "b" * 64}]},
    )
    with pytest.raises(RGBDModelUnavailable, match="digest"):
        planner.plan(
            InitialPlanningRequest(
                request_id="replaced",
                user_instruction="pick",
                observation=RGBDObservation.model_validate(observation_payload()),
                scene=SceneSummary(scene_version=1, updated_at=datetime.now(UTC)),
            )
        )
    assert "/api/chat" not in calls


@pytest.mark.parametrize("target,allowed", [((48, 48), False), ((32, 32), True)])
def test_visible_top_surface_must_rise_above_local_support(
    monkeypatch: pytest.MonkeyPatch,
    target: tuple[int, int],
    allowed: bool,
) -> None:
    """A VLM pointing at nearby flat table cannot produce an object grasp target."""
    from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter

    image = Image.new("RGB", (64, 64), (130, 130, 130))
    depths = [2.0] * (64 * 64)
    for v in range(28, 36):
        for u in range(28, 36):
            image.putpixel((u, v), (240, 30, 20))
            depths[v * 64 + u] = 1.9
    png = io.BytesIO()
    image.save(png, format="PNG")
    payload = observation_payload()
    payload.update(
        width=64,
        height=64,
        rgb_png_base64=base64.b64encode(png.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(struct.pack("<4096f", *depths)).decode(),
        intrinsics=[64, 64, 31.5, 31.5],
        camera_to_world=[1, 0, 0, 0, 0, -1, 0, 0, 0, 0, -1, 3, 0, 0, 0, 1],
    )
    observation = RGBDObservation.model_validate(payload)

    def fake_post(path: str, body: dict[str, Any]) -> dict[str, Any]:
        if path == "/api/show":
            return {"capabilities": ["vision"]}
        return {
            "message": {
                "content": json.dumps(
                    {
                        "target_pixel": target,
                        "destination_pixel": [8, 8],
                        "target_label": "red cube",
                        "reported_confidence": 0.95,
                        "skills": [
                            "HOME",
                            "MOVE_ABOVE",
                            "APPROACH",
                            "GRASP",
                            "LIFT",
                            "MOVE_TO_REGION",
                            "PLACE",
                            "RELEASE",
                            "RETREAT",
                        ],
                        "reason": "",
                    }
                )
            }
        }

    monkeypatch.setattr(RGBDPlannerAdapter, "_post", staticmethod(fake_post))
    snapshot = ModelConfigSnapshot(
        provider="ollama", model="qwen3.5:4b", endpoint="http://127.0.0.1:11434",
        weight_digest="", quantization="UNKNOWN", image_size=(64, 64),
        generation_parameters={"temperature": 0}, timeout_s=60,
        grasp_profile="mujoco_upright_box_v1",
    )
    draft = RGBDPlannerAdapter(model_snapshot=snapshot).plan(
        InitialPlanningRequest(
            request_id="flat-vs-raised",
            user_instruction="pick red cube",
            observation=observation,
            scene=SceneSummary(scene_version=1, updated_at=datetime.now(UTC)),
        )
    )
    if allowed:
        assert draft.observed_scene is not None
        assert draft.observation_evidence["target_relief_above_support_m"] > 0.05
        assert (
            draft.observation_evidence["top_grasp_offset_status"] == "CALIBRATED_RGBD_TOP_GRASP_V1"
        )
        tcp = draft.observation_evidence["resolved_top_grasp_tcp"]
        assert tcp["z"] == pytest.approx(1.06, abs=1e-6)
        assert draft.observation_evidence["top_grasp_offset_from_surface_m"] == pytest.approx(
            -0.04, abs=1e-6
        )
    else:
        assert (
            draft.parsed_json and draft.parsed_json.get("_sentinel") == "REQUEST_MORE_OBSERVATION"
        )
        assert draft.observed_scene is None
