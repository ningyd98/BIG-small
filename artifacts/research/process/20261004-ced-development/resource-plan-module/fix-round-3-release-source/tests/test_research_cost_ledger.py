"""Actual bytes, attempt denominators, and logical cloud roles."""

import json
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from cloud_edge_robot_arm.research.cost_ledger import CostLedger, RequestCost
from cloud_edge_robot_arm.vision.planner import RGBDModelUnavailable, RGBDPlannerAdapter


def cost(request_id="r1", **overrides):
    now = datetime.now(UTC)
    return RequestCost(
        **{
            "request_id": request_id,
            "sent_at": now,
            "finished_at": now + timedelta(seconds=1),
            "is_cloud_model": True,
            "model_role": "PLANNER",
            "deployment": "CLOUD",
            "provider_location": "LOCAL_HOST",
            "provider_version": "frozen-v1",
            "status": "SUCCESS",
            "serialized_sent_bytes": 30,
            "serialized_received_bytes": 20,
            **overrides,
        }
    )


def test_all_sent_retries_timeouts_count():
    ledger = CostLedger()
    for i, status in enumerate(("SUCCESS", "TIMEOUT", "ERROR")):
        ledger.record_request(cost(str(i), status=status))
    assert ledger.snapshot().cloud_model_requests == 3
    assert ledger.snapshot().application_bytes == 150


def test_unsent_cancel_is_not_model_request():
    ledger = CostLedger()
    ledger.record_request(cost(sent_at=None, status="CANCELLED", serialized_sent_bytes=0,
                               serialized_received_bytes=0))
    assert ledger.snapshot().model_requests == 0
    assert ledger.snapshot().application_bytes == 0


def test_telemetry_is_separate_from_model_calls():
    ledger = CostLedger()
    ledger.record_telemetry(10, 20)
    assert ledger.snapshot().telemetry_messages == 1
    assert ledger.snapshot().model_requests == 0
    assert ledger.snapshot().application_bytes == 30


def test_remote_judge_counts_in_cloud_total():
    ledger = CostLedger()
    ledger.record_request(cost())
    for i in range(2):
        ledger.record_request(cost(f"judge-{i}", model_role="JUDGE",
                                   provider_location="REMOTE_SERVICE"))
    ledger.record_request(cost("local", model_role="JUDGE", deployment="EDGE",
                               is_cloud_model=False))
    assert ledger.snapshot().model_requests == 4
    assert ledger.snapshot().cloud_model_requests == 3
    assert ledger.snapshot().requests_by_role == {"PLANNER": 1, "JUDGE": 3}


def test_local_host_cloud_vlm_still_counts_as_cloud():
    ledger = CostLedger()
    ledger.record_request(cost())
    assert ledger.snapshot().cloud_model_requests == 1
    with pytest.raises(ValueError):
        cost(deployment="EDGE")


def test_decision_latency_includes_queue_network_and_commit():
    ledger = CostLedger()
    ledger.record_timing(queue_s=.1, inference_s=.2, network_s=.3,
                         commit_check_s=.4, switch_s=.5)
    assert ledger.snapshot().decision_latency_s == pytest.approx(1.5)


def test_duplicate_attempt_is_idempotent_but_conflict_is_rejected():
    ledger = CostLedger()
    row = cost()
    ledger.record_request(row)
    ledger.record_request(row)
    assert ledger.snapshot().model_requests == 1
    with pytest.raises(ValueError):
        ledger.record_request(row.model_copy(update={"serialized_sent_bytes": 31}))


def test_inflight_sent_request_counts_before_response_and_finishes_once():
    ledger = CostLedger()
    complete = cost()
    pending = complete.model_copy(update={"finished_at": None, "status": "IN_FLIGHT",
                                           "serialized_received_bytes": 0})
    ledger.record_request(pending)
    assert ledger.snapshot().cloud_model_requests == 1
    assert ledger.snapshot().application_bytes == 30
    ledger.record_request(complete)
    assert ledger.snapshot().cloud_model_requests == 1
    assert ledger.snapshot().application_bytes == 50


@pytest.mark.parametrize("malformed", [False, True])
def test_application_bytes_are_actual_payload_lengths(malformed):
    sent = []
    raw_response = b"not json" if malformed else b'{"message":{"content":"ok"}}'

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            sent.append(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw_response)))
            self.end_headers()
            self.wfile.write(raw_response)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    ledger = CostLedger()
    planner = RGBDPlannerAdapter(base_url=f"http://127.0.0.1:{server.server_port}",
                                 cost_ledger=ledger)
    body = {"model": "unit", "messages": [{"content": "真实图片"}]}
    try:
        if malformed:
            with pytest.raises(RGBDModelUnavailable):
                planner._post("/api/chat", body)
        else:
            assert planner._post("/api/chat", body)["message"]["content"] == "ok"
        expected = json.dumps(body).encode()
        assert sent == [expected]
        snapshot = ledger.snapshot()
        assert snapshot.model_requests == 1
        assert snapshot.application_bytes == len(expected) + len(raw_response)
        assert ledger.requests()[0].status == ("ERROR" if malformed else "SUCCESS")
        assert snapshot.inference_s is None
        assert snapshot.provider_roundtrip_s > 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
