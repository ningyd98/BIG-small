"""Development-only RGB-D cloud comparison; no control actions or G1 claims.

This experiment reuses recorded MuJoCo frames and the repository's actual
RGBDPlannerAdapter. It does not change production profiles or frozen models.
Credentials are read from a non-echoing prompt / environment and never saved.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import socket
import struct
import sys
import time
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx

ARTIFACT = Path(__file__).resolve().parent
ROOT = ARTIFACT / "token-plan"
REPO = ARTIFACT.parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest
from cloud_edge_robot_arm.datasets.external.network import create_direct_transport
from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot, resolve_visual_planner
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.planner import VisualDecision
from scripts import evaluate_rgbd_model_scenes as evaluation
from scripts import probe_rgbd_model as probe

BASE = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
SOURCE = REPO / "artifacts/research/process/20261003-t3-small-model-optimization/scene-validation"
MODELS = {
    "qwen38_flash": ("qwen3.8-flash", None, None),
    "qwen38_max": ("qwen3.8-max", None, None),
    "qwen37_plus": ("qwen3.7-plus", None, None),
    "qwen36_flash": ("qwen3.6-flash", None, None),
}
NETWORK = {"mode": "direct", "interface": "enp7s0",
           "dns_servers": ["223.5.5.5", "223.6.6.6"],
           "allowed_hosts": [BASE.split("/")[2]]}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def load_frame(directory):
    metadata = read(directory / "observation.json")
    values = {key: value for key, value in metadata.items() if key in RGBDObservation.model_fields}
    for field, name in (("rgb_png_base64", "rgb.png"),
                        ("depth_float32_base64", "depth.f32"),
                        ("valid_mask_base64", "valid_mask.u8")):
        values[field] = base64.b64encode((directory / name).read_bytes()).decode()
    observation = RGBDObservation.model_validate(values)
    assert sha((directory / "rgb.png").read_bytes()) == metadata["rgb_sha256"]
    assert sha((directory / "depth.f32").read_bytes()) == metadata["depth_sha256"]
    return SimpleNamespace(
        observation=observation,
        instance_ids=tuple(x[0] for x in struct.iter_unpack("<i", (directory / "instance_geom_ids.i32").read_bytes())),
        instance_labels={int(key): value for key, value in metadata["instance_labels"].items()},
    )


def planner_for(model):
    snapshot = ModelConfigSnapshot(
        provider="openai_compatible", model=model, endpoint=BASE, weight_digest="",
        quantization="HOSTED_UNKNOWN", image_size=(320, 240),
        generation_parameters={"temperature": 0, "num_predict": 512},
        timeout_s=90, coordinate_system="normalized_1000", grasp_profile="mujoco_upright_box_v1",
    )
    return resolve_visual_planner(snapshot, chat_path="/chat/completions", allow_paid=True)


class RequestReady(Exception):
    pass


def prepare():
    assignments = read(SOURCE / "assignments.json")
    source_files = ["src/cloud_edge_robot_arm/vision/" + name + ".py" for name in
                    ("planner", "messages", "observations", "model_resolver", "top_grasp")]
    source_files += ["scripts/evaluate_rgbd_model_scenes.py", "scripts/probe_rgbd_model.py",
                     "src/cloud_edge_robot_arm/datasets/external/network.py"]
    protocol = {
        "schema_version": "rgbd.cloud-development-comparison.v1",
        "created_at": datetime.now(UTC).isoformat(), "held_out_test": False,
        "physical_actions": False, "formal_G1": False, "weight_freeze": False,
        "scope": "Recorded MuJoCo RGB-D perception and initial-plan compatibility only",
        "source": str(SOURCE.relative_to(REPO)), "source_assignments_sha256": sha((SOURCE / "assignments.json").read_bytes()),
        "models": {key: {"id": value[0], "input_cny_per_million": value[1],
                          "output_cny_per_million": value[2]} for key, value in MODELS.items()},
        "endpoint": BASE, "billing_channel": "Token Plan",
        "cost_semantics": "token usage recorded; subscription Credits and billed cost NOT_MEASURED",
        "model_selection": "intersection of supplied Token Plan catalog and documented vision models; VL-Plus/VL-Flash/date snapshots absent from this catalog",
        "generation": {"temperature": 0, "max_tokens": 512, "enable_thinking": False,
                       "response_format": {"type": "json_object"}},
        "coordinate_system": "normalized_1000", "image_size": [320, 240],
        "network_policy": NETWORK, "one_call_per_model_per_case": True,
        "max_inference_requests": 64, "automatic_retries": 0,
        "latency_semantics": "non-streaming HTTPS wall time including connection; TTFT not measured",
        "score_policy": "existing T3 case_passes; model refusal distinct from downstream geometric rejection",
        "metric_limit": "visible-surface-centroid error is diagnostic, not independent top-center G1 error",
        "source_fingerprints": {name: sha((REPO / name).read_bytes()) for name in source_files},
        "experiment_sha256": sha(Path(__file__).read_bytes()), "cases": assignments["cases"],
    }
    write(ROOT / "protocol.json", protocol)
    jobs = []
    for case in protocol["cases"]:
        case_id = case["case_id"]
        old = SOURCE / "cases" / case_id
        local = ROOT / "inputs" / case_id
        shutil.copytree(old / "captures/attempt-01", local)
        for name in ("scene.json", "capture.json", "outcome.json", "attempt.json"):
            shutil.copyfile(old / name, local / ("baseline-" + name))
        frame = load_frame(local)
        original = read(old / "attempt.json")
        for alias, (model, _, _) in MODELS.items():
            planner = planner_for(model)
            captured = {}
            def capture(path, body):
                assert path == "/chat/completions"
                captured.update(body)
                raise RequestReady()
            planner._post = capture
            try:
                planner.plan(InitialPlanningRequest(request_id="cloud-development", user_instruction=case["instruction"], observation=frame.observation))
            except RequestReady:
                pass
            assert captured
            images = [part["image_url"]["url"] for message in captured["messages"]
                      if isinstance(message["content"], list) for part in message["content"] if part["type"] == "image_url"]
            hashes = [sha(base64.b64decode(url.split(",", 1)[1])) for url in images]
            assert hashes == original["request_summary"]["image_sha256"]
            assert captured["messages"][0]["content"] == original["request_texts"][0]["content"]
            assert captured["messages"][1]["content"][0]["text"] == original["request_texts"][1]["content"]
            captured["enable_thinking"] = False
            request_path = ROOT / "requests" / alias / (case_id + ".json")
            write(request_path, captured)
            jobs.append({"label": alias + "/" + case_id, "body": str(request_path),
                         "output": str(ROOT / "responses" / alias / (case_id + ".json"))})
    write(ROOT / "jobs.json", jobs)
    print(json.dumps({"prepared_cases": len(protocol["cases"]), "models": len(MODELS), "requests": len(jobs), "prompt_and_image_parity_with_local_baseline": True}))


def replay(case, alias, receipt):
    local = ROOT / "inputs" / case["case_id"]
    frame = load_frame(local)
    planner = planner_for(MODELS[alias][0])
    request_body = read(ROOT / "requests" / alias / (case["case_id"] + ".json"))
    assert receipt["request_sha256"] == sha(json.dumps(request_body, sort_keys=True).encode())
    record = {"case_id": case["case_id"], "kind": case["kind"], "scene_sha256": case["scene_sha256"],
              "rgb_sha256": sha((local / "rgb.png").read_bytes()), "complete": False,
              "latency_ms": receipt.get("latency_ms"), "http_status": receipt.get("http_status")}
    if not receipt.get("ok"):
        record["error"] = receipt.get("error", receipt.get("response", {}).get("error", "HTTP_ERROR"))
        return record
    response = receipt["response"]
    raw = response.get("choices", [{}])[0].get("message", {}).get("content")
    try:
        VisualDecision.model_validate_json(raw, strict=True)
        record["schema_valid"] = True
    except Exception:
        record["schema_valid"] = False
    def saved_response(path, body):
        assert path == "/chat/completions"
        assert {**body, "enable_thinking": False} == request_body
        return response
    planner._post = saved_response
    draft = planner.plan(InitialPlanningRequest(request_id="cloud-development", user_instruction=case["instruction"], observation=frame.observation))
    evidence = draft.observation_evidence
    decision = evidence.get("visual_decision", {})
    attempt = {"raw_model_output": raw, "visual_decision": decision, "observation_evidence": evidence,
               "observed_scene_present": draft.observed_scene is not None,
               "parsed": draft.parse_error is None and draft.observed_scene is not None,
               "grounded": draft.parse_error is None and draft.observed_scene is not None and draft.parsed_json is not None,
               "parse_error": draft.parse_error,
               "contract_step_count": len(draft.parsed_json.get("steps", [])) if draft.parsed_json else 0,
               "transport_two_images": True}
    for kind, label in (("target", "object_geom"), ("destination", "target_region_geom")):
        pixel = probe._original_decision_pixel(planner, frame, evidence, decision, kind)
        attempt[kind + "_hit"], attempt[kind + "_offline_check"] = probe._pixel_hit(frame, pixel, label)
    record.update(complete=True, attempt=attempt, capture=read(local / "baseline-capture.json"),
                  diagnostics=evaluation.offline_diagnostics(frame, attempt), usage=response.get("usage"),
                  response_model=response.get("model"), finish_reason=response["choices"][0].get("finish_reason"))
    record["case_passed"] = evaluation.case_passes(case, record)
    record["explicit_refusal"] = evaluation._explicit_refusal(attempt)
    return record


def percentile(values, quantile):
    if not values:
        return None
    values = sorted(values)
    pos = (len(values) - 1) * quantile
    lo = math.floor(pos)
    return round(values[lo] + (values[math.ceil(pos)] - values[lo]) * (pos-lo), 3)


def analyze():
    protocol = read(ROOT / "protocol.json")
    assert all(sha((REPO / path).read_bytes()) == digest for path, digest in protocol["source_fingerprints"].items())
    output = {"status": "DEVELOPMENT_ONLY", "formal_G1": False, "models": {}, "local_historical_reference": {},
              "evaluator_sha256_at_analysis": sha(Path(__file__).read_bytes())}
    baselines = [read(ROOT / "inputs" / case["case_id"] / "baseline-outcome.json") for case in protocol["cases"]]
    baseline_summary = evaluation.summarize_results({"cases": protocol["cases"]}, baselines)
    assert baseline_summary["positive_passed"] == 12 and baseline_summary["negative_passed"] == 3
    output["local_historical_reference"] = baseline_summary
    for alias, (_, input_price, output_price) in MODELS.items():
        records = []
        for case in protocol["cases"]:
            path = ROOT / "responses" / alias / (case["case_id"] + ".json")
            if path.exists():
                records.append(replay(case, alias, read(path)))
        summary = evaluation.summarize_results({"cases": protocol["cases"]}, records)
        errors = [r["diagnostics"]["target"]["pixel_center_error_px"] for r in records
                  if r.get("kind") == "positive" and r.get("attempt", {}).get("target_hit")
                  and r.get("diagnostics", {}).get("target", {}).get("pixel_center_error_px") is not None]
        prompt_tokens = sum((r.get("usage") or {}).get("prompt_tokens", 0) for r in records)
        completion_tokens = sum((r.get("usage") or {}).get("completion_tokens", 0) for r in records)
        summary.update(status="NOT_RUN" if not records else "COMPLETE" if len(records) == 16 else "PARTIAL",
                       model=MODELS[alias][0], schema_valid=sum(r.get("schema_valid", False) for r in records),
                       latency_p50_ms=percentile([r["latency_ms"] for r in records], .5),
                       latency_p95_ms=percentile([r["latency_ms"] for r in records], .95),
                       hit_subset_pixel_centroid_p90_px=percentile(errors, .9), diagnostic_error_samples=len(errors),
                       prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                       estimated_list_cost_cny=None,
                       unsafe_negative_contracts=sum(r["kind"] == "negative_absent" and r.get("attempt", {}).get("contract_step_count", 0) > 0 for r in records))
        output["models"][alias] = summary
        if records:
            write(ROOT / "analysis" / (alias + "-records.json"), records)
    write(ROOT / "summary.json", output)
    print(json.dumps(output, ensure_ascii=False, indent=2))


def run():
    protocol = read(ROOT / "protocol.json")
    key = os.environ.get("BIGSMALL_QWEN_API_KEY") or getpass.getpass("API key (memory only): ")
    if not key.startswith("sk-sp-"):
        raise SystemExit("This experiment is configured for the supplied Token Plan endpoint; provide its matching credential.")
    if not key:
        raise SystemExit("Missing API credential")
    jobs = read(ROOT / "jobs.json")
    assert len(jobs) <= protocol["max_inference_requests"]
    with httpx.Client(transport=create_direct_transport(NETWORK), trust_env=False, follow_redirects=False,
                      timeout=httpx.Timeout(90, connect=15), headers={"Authorization": "Bearer " + key}) as client:
        for job in jobs:
            path = Path(job["output"])
            if path.exists():
                continue
            body = read(Path(job["body"]))
            started = time.perf_counter()
            receipt = {"label": job["label"], "started_at": datetime.now(UTC).isoformat(),
                       "request_sha256": sha(json.dumps(body, sort_keys=True).encode()), "trust_env": False}
            try:
                with client.stream("POST", BASE + "/chat/completions", json=body) as response:
                    stream = response.extensions["network_stream"]
                    sock = stream.get_extra_info("socket")
                    receipt["network"] = {"bound_interface": sock.getsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, 256).rstrip(b"\0").decode(), "peer": sock.getpeername()}
                    assert receipt["network"]["bound_interface"] == NETWORK["interface"]
                    receipt["http_status"] = response.status_code
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > 2_000_000:
                            raise ValueError("oversized response")
                    receipt["response"] = json.loads(data.decode().replace(key, "[REDACTED]"))
                    receipt["ok"] = response.status_code == 200
            except Exception as exc:
                receipt.update(ok=False, error={"type": type(exc).__name__})
            receipt["latency_ms"] = round((time.perf_counter()-started)*1000, 3)
            write(path, receipt)
            print(job["label"], receipt.get("http_status"), receipt["latency_ms"], flush=True)
            if receipt.get("http_status") in (401, 403, 429):
                raise SystemExit("Stopped on authentication, permission or quota error; receipt retained.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare", "run", "analyze"))
    args = parser.parse_args()
    {"prepare": prepare, "run": run, "analyze": analyze}[args.phase]()
