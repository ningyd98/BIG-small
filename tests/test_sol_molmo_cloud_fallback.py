"""Real MuJoCo/worker route; external models are explicit software fixtures."""

from __future__ import annotations

import base64
import hashlib
import io
import json

import numpy as np
import pytest
from PIL import Image

from cloud_edge_robot_arm.vision.molmo_pointing import BoundPointResult, parse_native_point
from tests.test_sol_molmo_single_episode import selected_profile


class AbsentNativeFixture:
    model_loads_started = 0

    def __init__(self):
        self.generation_calls_started = 0
        self.generation_calls_completed = 0

    def point(self, observation, phrase):
        self.generation_calls_started += 1
        self.generation_calls_completed += 1
        return BoundPointResult(
            parse_native_point("ABSENT"), observation.checksum_sha256,
            observation.evidence()["rgb_sha256"], hashlib.sha256(phrase.encode()).hexdigest(),
            {"evidence_scope": "SOFTWARE_FIXTURE_NATIVE_ABSENCE"},
        )


@pytest.mark.parametrize("flag", [True, 1, "true"])
def test_fallback_requires_explicit_component_execution_before_files(tmp_path, flag):
    from cloud_edge_robot_arm.research.sol_molmo_single_episode import run_single_episode

    with pytest.raises(ValueError, match="cloud vision fallback"):
        run_single_episode(output=tmp_path / "out", cloud_vision_fallback=flag)
    assert not (tmp_path / "out").exists()


def test_fallback_cli_recognizes_flag_and_rejects_missing_scope(tmp_path, capsys):
    from scripts.run_sol_molmo_single_episode import main

    assert main(["--output", str(tmp_path / "out"), "--cloud-vision-fallback"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "NOT_STARTED"
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("seed,split,action,completed", [
    (42001, None, "CANDIDATE", True),
    (42001, None, "REOBSERVE", False),
    (43001, "development", "CANDIDATE", False),
])
def test_actual_worker_cloud_image_route_preserves_geometry_and_one_request_budget(
    tmp_path, monkeypatch, seed, split, action, completed
):
    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository
    from cloud_edge_robot_arm.research import sol_molmo_single_episode as entry

    monkeypatch.setenv("MUJOCO_GL", "egl")
    database, profile, secrets = selected_profile(tmp_path)
    service = ModelControlService(
        repository=SQLiteModelProfileRepository(database), secret_store=secrets
    )
    requests = []

    class Opener:
        def open(self, request, **kwargs):
            body = json.loads(request.data)
            requests.append(body)
            content = body["messages"][1]["content"]
            images = [part for part in content if part["type"] == "image_url"]
            assert images and body["model"] == "gpt-6.1-sol"
            raw = base64.b64decode(images[0]["image_url"]["url"].split(",", 1)[1])
            rgb = np.asarray(Image.open(io.BytesIO(raw)).convert("RGB"), dtype=float)
            r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
            reply = {"action": action, "target_normalized_1000": None,
                     "destination_normalized_1000": None, "skills": [],
                     "reason": "software cloud boundary fixture"}
            if action == "CANDIDATE":
                for key, mask in [
                    ("target_normalized_1000", (r > 1.5*g) & (r > 1.5*b) & (r > 80)),
                    ("destination_normalized_1000", (g > 1.3*r) & (g > 1.3*b) & (g > 50)),
                ]:
                    y, x = np.nonzero(mask)
                    reply[key] = [round(float(np.median(x))*1000/rgb.shape[1]),
                                  round(float(np.median(y))*1000/rgb.shape[0])]
                reply["skills"] = ["MOVE_ABOVE", "APPROACH", "GRASP", "LIFT",
                                   "MOVE_TO_REGION", "PLACE", "RELEASE", "RETREAT"]
            return io.BytesIO(json.dumps({"choices": [{"message": {
                "content": json.dumps(reply)
            }}]}).encode())

    monkeypatch.setattr("urllib.request.build_opener", lambda *a: Opener())
    assignment = entry.scene_assignment(
        seed, "side_y_plus_id7_75mm_component_v1", scene_split=split
    )
    assignment.update(component_diagnostic=True, cloud_vision_fallback=True)
    output = tmp_path / "worker-run"
    output.mkdir()
    points = AbsentNativeFixture()
    planner, binding = entry.create_molmo_opencv_bridge(
        service=service, profile_id=profile.profile_id, points=points,
        assignment=assignment, output=output, asset_manifest_sha256="a"*64,
    )
    assert planner.grounded.cloud_vision_fallback is True
    assert binding.edge_policy["perception_binding"]["cloud_vision_fallback"] is True
    assert binding.edge_policy["perception_binding"]["cloud_requests"] == 1
    result = {"executed_actions": 0, "model_calls": 0}
    entry.run_worker_episode(assignment, output, result, planner=planner, binding=binding)
    assert len(requests) == 1
    assert result["cloud_requests"] == result["cloud_request_reservations"] == 1
    assert result["outcome"]["native_action_qualification"] == "UNKNOWN_NOT_GRANTED"
    assert points.generation_calls_started == 1
    if completed:
        assert result["physical_success"] is True
        assert result["executed_actions"] == 8
        second = json.loads((output / "planning/planning-stage-02.json").read_text())
        e = second["attempts"][-1]["draft"]["observation_evidence"]
        assert e["grounding_point_source"] == "CLOUD_VISION_CANDIDATE"
        assert e["post_cloud_revalidation"]["status"] == "PASSED"
    else:
        assert result["executed_actions"] == 0
        assert result["planning_passed"] is False
        if action == "CANDIDATE":
            second = json.loads((output / "planning/planning-stage-02.json").read_text())
            assert "target_contour_incomplete_or_occluded" in second["reason"]
    assert (output / "raw/cloud/request.json").is_file()
    assert (output / "raw/cloud/response.json").is_file()
