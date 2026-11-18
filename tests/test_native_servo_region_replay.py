"""Opt-in regression using the frozen native fixed-01 provider responses."""

import hashlib
import io
import json
import os
import sys
from pathlib import Path

import pytest

from cloud_edge_robot_arm.research.sol_molmo_single_episode import (
    create_molmo_opencv_bridge,
    run_worker_episode,
    scene_assignment,
)
from cloud_edge_robot_arm.vision.molmo_pointing import BoundPointResult, parse_native_point
from tests.test_sol_molmo_single_episode import selected_profile

SCOPE = "MODEL_PROTOCOL_REPLAY_NOT_REAL_MODEL"
ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / "experiments/results/phase9/real-harness-20261118/native/fixed-01"


def _read_json(path):
    return json.loads(path.read_bytes())


def _sha(data):
    return hashlib.sha256(data).hexdigest()


class ArchivedMolmo:
    def __init__(self, original, output):
        self.original = original
        self.output = output
        self.calls = []

    @property
    def generation_calls_started(self):
        """The worker records this provider counter as protocol occupancy."""
        return len(self.calls)

    def point(self, observation, phrase):
        index = len(self.calls) + 1
        assert 1 <= index <= 4, "unallocated Molmo protocol request"
        source = self.original / "raw/molmo" / f"request-{index:04d}"
        started = _read_json(source / "started.json")
        result = _read_json(source / "result.json")
        raw = (source / "raw-response.txt").read_bytes()
        rgb_sha = observation.evidence()["rgb_sha256"]
        query_sha = _sha(phrase.encode())
        assert phrase == started["phrase"]
        assert rgb_sha == started["rgb_sha256"] == result["rgb_sha256"]
        assert query_sha == started["query_sha256"] == result["query_sha256"]
        assert _sha(raw) == result["raw_sha256"] and result["reached_cap"] is False
        archived_frame = self.original / ("before" if index < 3 else "component/frames/post-cloud")
        assert rgb_sha == _sha((archived_frame / "rgb.png").read_bytes())
        current = self.output / ("before" if index < 3 else "component/frames/post-cloud")
        assert (current / "rgb.png").read_bytes() == (archived_frame / "rgb.png").read_bytes()
        stored = self.output / "raw/molmo-replay" / source.name
        stored.mkdir(parents=True, exist_ok=False)
        (stored / "raw-response.txt").write_bytes(raw)
        binding = {
            "scope": SCOPE,
            "source": str(source.relative_to(ROOT)),
            "raw_sha256": _sha(raw),
            "phrase": phrase,
            "query_sha256": query_sha,
            "rgb_sha256": rgb_sha,
            "original_observation_checksum": started["observation_checksum"],
            "replay_observation_checksum": observation.checksum_sha256,
        }
        self.calls.append(binding)
        (stored / "binding.json").write_text(json.dumps(binding, indent=2) + "\n")
        return BoundPointResult(
            parse_native_point(raw.decode()), observation.checksum_sha256, rgb_sha, query_sha,
            {"scope": SCOPE, "raw_sha256": binding["raw_sha256"], "model_image_count": 1},
        )


def run_archived_native_protocol(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository

    output = Path(os.environ["BIGSMALL_NATIVE_SERVO_REPLAY_DIR"]).resolve()
    output.mkdir(parents=True, exist_ok=False)
    original = _read_json(ORIGINAL / "scene-assignment.json")
    assignment = scene_assignment(42001, "side_y_plus_id7_75mm_component_v1") | {
        "component_diagnostic": True,
        "cloud_vision_fallback": False,
        "visual_servo": True,
        "camera_position_m": [0.35, 0.0, 1.35],
    }
    assert assignment == original
    manifest_sha = _read_json(ORIGINAL / "raw/molmo/initial.json")["asset_manifest_sha256"]
    (output / "scene-assignment.json").write_text(json.dumps(assignment, indent=2) + "\n")
    database, profile, secrets = selected_profile(tmp_path)
    service = ModelControlService(
        repository=SQLiteModelProfileRepository(database), secret_store=secrets,
    )
    cloud = ORIGINAL / "raw/cloud"
    archived_request = (cloud / "request.json").read_bytes()
    archived_response = (cloud / "response.json").read_bytes()
    requests = []
    network_calls = []
    model_load_attempts = []
    guard_active = True

    def block_network(event, _args):
        if guard_active and event in {
            "socket.connect", "socket.sendto", "socket.sendmsg", "socket.getaddrinfo",
            "socket.gethostbyname", "socket.gethostbyaddr", "socket.getnameinfo",
        }:
            network_calls.append(event)
            raise RuntimeError(f"network denied during {SCOPE}: {event}")

    def block_model_load(*_args, **_kwargs):
        model_load_attempts.append("MolmoPointProvider")
        raise AssertionError("native model load denied during protocol replay")

    class ArchivedSol:
        def open(self, request, **_kwargs):
            requests.append(_sha(request.data))
            assert len(requests) == 1
            assert request.full_url == "https://api.openai.com/v1/chat/completions"
            assert json.loads(request.data) == json.loads(archived_request)
            return io.BytesIO(archived_response)

    monkeypatch.setattr("urllib.request.build_opener", lambda *_: ArchivedSol())
    monkeypatch.setattr(
        "cloud_edge_robot_arm.vision.molmo_pointing.MolmoPointProvider", block_model_load,
    )
    sys.addaudithook(block_network)
    points = ArchivedMolmo(ORIGINAL, output)
    result = {"evidence_scope": SCOPE, "executed_actions": 0, "model_calls": 0}
    try:
        planner, binding = create_molmo_opencv_bridge(
            service=service, profile_id=profile.profile_id, points=points,
            assignment=assignment, output=output, asset_manifest_sha256=manifest_sha,
        )
        run_worker_episode(assignment, output, result, planner=planner, binding=binding)
    finally:
        guard_active = False
        result.update({
            "network_requests": 0,
            "denied_network_attempts": network_calls,
            "actual_model_loads": 0,
            "denied_model_load_attempts": model_load_attempts,
            "actual_local_generations": 0,
            "local_protocol_replies": len(points.calls),
            "cloud_protocol_requests": len(requests),
            "cloud_original_request_sha256": _sha(archived_request),
            "cloud_original_response_sha256": _sha(archived_response),
        })
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")

    assert len(points.calls) == 4 and len(requests) == 1
    assert network_calls == model_load_attempts == []
    assert (output / "raw/cloud/response.json").read_bytes() == archived_response
    assert result["planning_passed"] is True
    return result


@pytest.mark.skipif(
    not os.getenv("BIGSMALL_NATIVE_SERVO_REPLAY_DIR"),
    reason="requires frozen local native fixed-01 raw and shared renderer admission",
)
def test_native_points_complete_pick_and_place(tmp_path, monkeypatch):
    result = run_archived_native_protocol(tmp_path, monkeypatch)
    assert result["worker_status"] == "SUCCEEDED", (
        result["worker_status"], result["terminal_reason"],
        [
            (action["step_id"], action["skill"], action.get("controller_return_step"),
             action.get("visual_servo", {}).get("terminal_reason"))
            for action in result["outcome"]["actions"]
        ],
    )
    outcome = result["outcome"]
    actions = outcome["actions"]
    assert list(dict.fromkeys(action["skill"] for action in actions)) == [
        "MOVE_ABOVE", "APPROACH", "GRASP", "LIFT", "MOVE_TO_REGION", "PLACE", "RELEASE", "RETREAT",
    ]
    assert len({action["source_step_id"] for action in actions}) == 8
    assert all(action["controller_result"]["success"] for action in actions)
    clearance, lateral = [action for action in actions if action["skill"] == "RETREAT"]
    assert clearance["source_step_id"] == lateral["source_step_id"]
    assert "vertical_clearance" in clearance and "vertical_clearance" not in lateral
    assert clearance["continuation"] is False and lateral["continuation"] is True
    assert outcome["diagnostic_complete"] is True and outcome["terminal_reason"] is None
    terminal, after = outcome["marker_frames"][-2:]
    assert terminal["label"] == "terminal-stability" and after["label"] == "after"
    assert terminal["physics_step"] > lateral["controller_return_step"]
    assert after["status"] == "OBSERVED"
    for action in actions:
        servo = action.get("visual_servo", {})
        assert all(len(sample.get("camera_recovery", [])) <= 2
                   for sample in servo.get("visual_samples", []))
        assert all(sample["sample_and_ik_s"] <= 0.1 for sample in servo.get("control_samples", []))
    assert result["physical_success"] is True
    assert outcome["independent_physical_outcome"]["success"] is True
    assert outcome["independent_physical_outcome"]["safety_violation"] is False
    assert outcome["formal_research"] == "NOT_ACCEPTED"
