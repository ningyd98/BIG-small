"""Exercise real HTTP image transport, metric grounding and planning gates."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from fastapi.testclient import TestClient

from cloud_edge_robot_arm.cloud.api.app import create_app
from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
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
                response = {"message": {"content": json.dumps({
                    "target_pixel": [1, 0], "destination_pixel": [0, 1],
                    "target_label": "red cube", "confidence": 0.9,
                    "skills": ["HOME", "MOVE_ABOVE", "APPROACH", "GRASP", "LIFT", "MOVE_TO_REGION", "PLACE", "RELEASE", "RETREAT", "HOME"],
                })}}
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
            request_id="rgbd-http", user_instruction="将红色方块放到绿色区域", observation=observation,
            scene=SceneSummary(scene_version=1, updated_at=datetime.now(UTC)),
        )
        draft = planner.plan(request)
        assert draft.observed_scene is not None
        assert draft.observed_scene.objects[0].pose.x == 2
        assert draft.observed_scene.objects[0].pose.z == 5
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


def test_default_api_rejects_text_only_planning() -> None:
    with TestClient(create_app()) as client:
        result = client.post("/api/v1/plans", json={
            "request_id": "text-only", "user_instruction": "pick red cube",
            "scene": {"scene_version": 1, "updated_at": datetime.now(UTC).isoformat()},
        })
    assert result.status_code == 201
    assert result.json()["outcome"] == "REQUEST_MORE_OBSERVATION"
    assert "RGBD" in result.json()["reason"]


def test_stale_rgbd_blocks_before_model_call() -> None:
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter

    payload = observation_payload()
    payload["captured_at"] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    request = InitialPlanningRequest(
        request_id="stale", user_instruction="pick", observation=RGBDObservation.model_validate(payload),
        scene=SceneSummary(scene_version=1, updated_at=datetime.now(UTC)),
    )
    result = PlanningPipeline(planner=RGBDPlannerAdapter(base_url="http://127.0.0.1:1")).process(request)
    assert result.outcome == "REQUEST_MORE_OBSERVATION"
    assert "stale" in result.reason


def test_model_control_default_dry_run_does_not_return_fake_contract(tmp_path) -> None:
    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from cloud_edge_robot_arm.model_control.secret_store import InMemorySecretStore
    from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository

    service = ModelControlService(repository=SQLiteModelProfileRepository(tmp_path / "models.db"), secret_store=InMemorySecretStore())
    result = service.planner_dry_run(user_instruction="pick cube", sample_scene="S01_NORMAL_STATIC", control_mode="ETEAC")
    assert result["input_mode"] == "RGBD"
    assert result["parse_result"] != "NOT_DISPATCHED"
    assert result["final_contract"] is None
    assert result["dispatch"] is False
