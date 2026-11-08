"""Read exact R460 originals and reproduce parsing/geometry without network."""
import hashlib
import json
import os
from pathlib import Path
import sys

os.environ["OPENBLAS_NUM_THREADS"] = "1"
ROOT = Path.cwd().resolve()
ROUND = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
from cloud_edge_robot_arm.research.freeze_evidence import _read_frame
from cloud_edge_robot_arm.vision.messages import build_visual_messages
from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot, compatible_chat_generation
from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter, VisualDecision, compatible_messages
from scripts.probe_rgbd_model import _pixel_hit
from scripts.probe_rgbd_roles import source_fingerprints, summarize_role_request


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


plan = read(ROUND / "plan.json")
report = read(ROUND / "implementation/replay-report.json")
supervisor = read(ROUND / "implementation/supervisor-result.json")
raw_root = ROOT / report["raw_directory"]
assert report["status"] == "RECORDED_INPUT_API_REPLAY_PASS"
assert (report["planned"], report["attempted"], report["inference_requests"], report["unexecuted"]) == (4, 4, 4, 0)
assert supervisor["returncode"] == 0 and supervisor["reaped"] and not supervisor["budget_failure"]
assert report["source_hashes"] == source_fingerprints()
assert report["runner_sha256"] == digest((ROUND / "implementation/replay.py").read_bytes())
assert not list(ROUND.rglob("roles-frozen.json")) and not list(raw_root.rglob("roles-frozen.json"))
for pin in read(ROUND / "intake/input-pins.json"):
    content = (ROOT / pin["path"]).read_bytes()
    assert len(content) == pin["bytes"] and digest(content) == pin["sha256"]

settings = report["request_settings"]
snapshot = ModelConfigSnapshot(
    provider="openai_compatible", model="gpt-6.1-sol", endpoint="https://api.openai.com",
    weight_digest=None, quantization=None, image_size=(320, 240), timeout_s=180,
    generation_parameters=settings["generation_parameters"], coordinate_system="normalized_1000",
    grasp_profile="mujoco_upright_box_v1")
adapter = RGBDPlannerAdapter(base_url="https://api.openai.com", model="gpt-6.1-sol",
    provider="openai_compatible", api_key="", allow_paid=False, timeout_s=180,
    chat_path="/v1/chat/completions", model_snapshot=snapshot)
verified = []
totals = dict(prompt_tokens=0, completion_tokens=0, total_tokens=0, reasoning_tokens=0)
for index, (case, entry) in enumerate(zip(plan["cases"], report["attempts"], strict=True)):
    directory = raw_root / f"attempt-{index:02d}"
    attempt = read(directory / "attempt.json")
    request_raw = (directory / "request.raw").read_bytes()
    response_raw = (directory / "response.raw").read_bytes()
    body, response = json.loads(request_raw), json.loads(response_raw)
    assert entry["case_id"] == case["case_id"] and entry["passed"] and all(entry["checks"].values())
    for label, raw in (("request", request_raw), ("response", response_raw)):
        assert digest(raw) == attempt[label + "_sha256"] == entry[label + "_sha256"]
        assert read(directory / (label + ".json")) == json.loads(raw)
    assert digest((directory / "attempt.json").read_bytes()) == entry["attempt_sha256"]
    original = _read_frame(ROOT / case["input_directory"])
    copied = _read_frame(directory)
    assert copied == original
    frame = original.observation
    messages = build_visual_messages(case["instruction"], frame, image_size=(320, 240),
        coordinate_system="normalized_1000", decision_schema=VisualDecision.model_json_schema())
    expected = {"model": "gpt-6.1-sol", "messages": compatible_messages(messages),
        **compatible_chat_generation("gpt-6.1-sol", settings["generation_parameters"]),
        "response_format": {"type": "json_object"}}
    assert expected == body
    assert summarize_role_request(body) == attempt["request_summary"] == attempt["expected_request_summary"]
    assert response["model"] == "gpt-6.1-sol" and response["choices"][0]["finish_reason"] == "stop"
    decision = VisualDecision.model_validate_json(response["choices"][0]["message"]["content"], strict=True)
    request = InitialPlanningRequest(request_id=f"r460-{case['case_id']}",
        user_instruction=case["instruction"], observation=frame,
        scene=SceneSummary(scene_version=1, updated_at=frame.captured_at))
    draft = adapter._ground_response(request, response, 0, frame, messages, (320, 240),
                                    "normalized_1000", "mujoco_upright_box_v1")
    assert draft.parse_error is None and draft.parsed_json == attempt["parsed_json"]
    assert draft.parsed_json and not draft.parsed_json.get("_sentinel")
    evidence = draft.observation_evidence
    assert evidence and evidence["visual_decision"] == decision.model_dump(mode="json")
    assert evidence["grounded_target"] == attempt["observation_evidence"]["grounded_target"]
    assert evidence["grounded_destination"] == attempt["observation_evidence"]["grounded_destination"]
    assert _pixel_hit(original, evidence["original_pixel_target"], "object_geom")[0]
    assert _pixel_hit(original, evidence["original_pixel_destination"], "target_region_geom")[0]
    assert len(draft.parsed_json["steps"]) == entry["compiled_step_count"] == 10
    rows = attempt["cost_ledger"]["requests"]
    assert len(rows) == 1 and rows[0]["status"] == "SUCCESS"
    assert rows[0]["serialized_sent_bytes"] == len(request_raw) == entry["sent_bytes"]
    assert rows[0]["serialized_received_bytes"] == len(response_raw) == entry["received_bytes"]
    assert response["usage"] == entry["usage"]
    for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
        totals[name] += response["usage"][name]
    totals["reasoning_tokens"] += response["usage"]["completion_tokens_details"]["reasoning_tokens"]
    verified.append({"case_id": case["case_id"], "wire_integrity": True, "original_frame_equal": True,
                     "strict_parse_reproduced": True, "geometry_reproduced": True, "both_mask_hits": True})

manifest = []
for path in sorted(raw_root.rglob("*")):
    if path.is_file():
        raw = path.read_bytes()
        assert b"sk-proj-" not in raw and b'"Authorization"' not in raw
        manifest.append({"path": str(path.relative_to(ROOT)), "bytes": len(raw), "sha256": digest(raw)})
assert sum(row["bytes"] for row in manifest) == supervisor["raw_bytes"]
result = {"status": "PASS", "scope": "OFFLINE_ORIGINAL_WIRE_AND_GEOMETRY_REPRODUCTION",
    "network_calls": 0, "credentials_read": 0, "render": 0, "physics": 0,
    "cases": verified, "usage_totals_as_reported_by_provider": totals,
    "raw_files": len(manifest), "raw_bytes": supervisor["raw_bytes"],
    "formal_research": "NOT_ACCEPTED", "independent_calibration": False}
for filename, value in (("verification.json", result), ("local-raw-manifest.json", manifest)):
    with (ROUND / "validation" / filename).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
print(json.dumps(result, ensure_ascii=False))
