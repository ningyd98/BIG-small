"""A periodic response must actually govern its matching action boundary."""

from datetime import UTC, datetime

import pytest

from cloud_edge_robot_arm.vision.supervision import (
    SupervisionContext,
    SupervisionDecision,
    decide_supervision,
)


def context(version=3):
    return SupervisionContext(episode_id="ep", plan_version=1, state_version=version,
        next_step_id="approach", next_skill="APPROACH", observation_id="obs",
        task_instruction="Move the red block to the green region.",
        captured_at=datetime.now(UTC), proprioception={"gripper_open": True})


@pytest.mark.parametrize("recommendation,expected", [
    ("CONTINUE", "CONTINUE"), ("REOBSERVE", "REOBSERVE"),
    ("REPLAN", "STOP"), ("STOP", "STOP"),
])
def test_response_content_changes_boundary_decision(recommendation, expected):
    current = context()
    reply = SupervisionDecision(episode_id="ep", plan_version=1, state_version=3,
        observation_id="obs", next_step_id="approach", recommendation=recommendation,
        reason="unit fixture")
    assert decide_supervision(reply, current, current, maximum_age_s=5) == expected


def test_old_state_or_mismatched_step_can_never_authorize_motion():
    captured = context(2)
    reply = SupervisionDecision(episode_id="ep", plan_version=1, state_version=2,
        observation_id="obs", next_step_id="approach", recommendation="CONTINUE", reason="")
    assert decide_supervision(reply, captured, context(3), maximum_age_s=5) == "DISCARD"
    wrong_step = reply.model_copy(update={"next_step_id": "place"})
    assert decide_supervision(wrong_step, captured, captured, maximum_age_s=5) == "REJECT"


def test_supervisor_input_schema_rejects_oracle_fields():
    with pytest.raises(ValueError):
        SupervisionContext.model_validate({**context().model_dump(), "physical_success": True})


def test_matching_stop_response_terminates_the_real_episode_boundary():
    from types import SimpleNamespace

    from cloud_edge_robot_arm.vision.evaluation import ExecutionPolicy
    from cloud_edge_robot_arm.vision.execution import _EpisodeStopped, _VisualEpisode

    captured = context()
    reply = SupervisionDecision(episode_id="ep", plan_version=1, state_version=3,
        observation_id="obs", next_step_id="approach", recommendation="STOP", reason="unsafe")
    response = {"episode_id": "ep", "captured_at": captured.captured_at,
                "context": captured.model_dump(), "decision": reply.model_dump()}
    run = _VisualEpisode.__new__(_VisualEpisode)
    run.policy = ExecutionPolicy("pick red", model_snapshot_hash="a" * 64)
    run.supervision = SimpleNamespace(poll=lambda **_: [response])
    run.observation = SimpleNamespace(episode_id="ep")
    run.supervision_context = lambda _: captured
    run.records = []
    run._state_version = 3
    with pytest.raises(_EpisodeStopped, match="SUPERVISION_STOPPED_SEQUENCE"):
        run.apply_supervision()
    assert run.records[-1]["action"] == "STOP"


def test_supervision_http_carries_two_images_bound_context_and_actual_costs():
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from cloud_edge_robot_arm.research.cost_ledger import CostLedger
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter
    from tests.test_rgbd_observations import observation_payload

    observation = RGBDObservation.model_validate({**observation_payload(), "episode_id": "ep"})
    captured = context().model_copy(update={"episode_id": observation.episode_id,
        "observation_id": observation.observation_id, "captured_at": observation.captured_at})
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/api/show":
                response = {"capabilities": ["vision"]}
            else:
                received.append(body)
                reply = {k: getattr(captured, k) for k in ("episode_id", "plan_version",
                    "state_version", "observation_id", "next_step_id")}
                reply.update(recommendation="STOP", reason="software transport fixture")
                response = {"message": {"content": json.dumps(reply)}}
            raw = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    ledger = CostLedger()
    try:
        adapter = RGBDPlannerAdapter(base_url=f"http://127.0.0.1:{server.server_port}",
            cost_ledger=ledger, model_role="SUPERVISOR")
        assert adapter.supervise(observation, captured).recommendation == "STOP"
        assert len(received[0]["messages"][1]["images"]) == 2
        assert captured.observation_id in received[0]["messages"][1]["content"]
        assert ledger.snapshot().requests_by_role == {"SUPERVISOR": 1}
        assert ledger.snapshot().application_bytes > 0
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
