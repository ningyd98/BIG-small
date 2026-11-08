"""R460 one-shot recorded-input API replay; never a live role qualification."""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import sys
import time
from datetime import UTC, datetime
from types import SimpleNamespace

ROOT = Path.cwd().resolve()
HERE = Path(__file__).resolve().parent
ROUND = HERE.parent
RAW = ROOT / "cache/research/r460-openai-sol-real-replay-20261108"
for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[name] = "1"
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
from cloud_edge_robot_arm.model_control.models import ModelProviderProfile
from cloud_edge_robot_arm.model_control.secret_store import InMemorySecretStore
from cloud_edge_robot_arm.research.freeze_evidence import _read_frame
from cloud_edge_robot_arm.vision.messages import build_visual_messages
from cloud_edge_robot_arm.vision.model_resolver import compatible_chat_generation, validate_sol_route
from cloud_edge_robot_arm.vision.planner import VisualDecision, compatible_messages
from cloud_edge_robot_arm.vision.role_models import cloud_request_settings, resolve_cloud_role
from scripts.probe_rgbd_roles import _attempt, source_fingerprints, summarize_role_request

PLAN = json.loads((ROUND / "plan.json").read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def event(**value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def json_body(path):
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_bytes())
        return value if isinstance(value, dict) else {}
    except (ValueError, UnicodeError):
        return {}


def inputs():
    pins = json.loads((ROUND / PLAN["input_pins"]).read_text())
    for pin in pins:
        path = ROOT / pin["path"]
        assert path.stat().st_size == pin["bytes"] and sha(path) == pin["sha256"], "PIN_DRIFT"
    profile = PLAN["profile_metadata"]
    assert (profile["enabled"], profile["config_version"], profile["max_tokens"],
            profile["timeout_seconds"], profile["max_retries"]) == (True, 1, 4096, 180, 0)
    validate_sol_route("openai_compatible", profile["model_name"], profile["base_url"],
                       profile["chat_completions_path"])
    result = []
    for case in PLAN["cases"]:
        frame = _read_frame(ROOT / case["input_directory"])
        observation = frame.observation
        assert observation.captured_at.isoformat() == case["original_captured_at"]
        assert observation.episode_id == case["episode_id"] and observation.scene_id == case["scene_id"]
        messages = build_visual_messages(case["instruction"], observation, image_size=(320, 240),
                                         coordinate_system="normalized_1000",
                                         decision_schema=VisualDecision.model_json_schema())
        body = {"model": "gpt-6.1-sol", "messages": compatible_messages(messages),
                **compatible_chat_generation("gpt-6.1-sol", {
                    "reasoning_effort": "low", "max_completion_tokens": 4096}),
                "response_format": {"type": "json_object"}}
        summary = summarize_role_request(body)
        text_size = sum(len(part["text"].encode()) for message in body["messages"]
                        for part in (message["content"] if isinstance(message["content"], list)
                                     else [{"text": message["content"]}]) if "text" in part)
        assert summary["image_count"] == summary["distinct_image_count"] == 2
        assert len(json.dumps(body).encode()) <= 131072 and text_size <= 16384
        result.append((case, frame, body, summary))
    return result


def preflight():
    started = time.monotonic()
    signal.alarm(60)
    items = inputs()
    assert shutil.disk_usage(ROOT).free >= 268435456
    RAW.mkdir(parents=True, exist_ok=False)
    result = {"status": "PASS", "scope": "CPU_ONLY_NO_NETWORK_NO_SECRET_NO_RENDER",
              "pin_count": 73, "runner_sha256": sha(Path(__file__)),
              "plan_sha256": sha(ROUND / "plan.json"), "source_hashes": source_fingerprints(),
              "raw_directory": str(RAW.relative_to(ROOT)), "elapsed_s": time.monotonic() - started,
              "cases": [{"case_id": case["case_id"], "observation_sha256": frame.observation.checksum_sha256,
                         "expected_request_summary": summary} for case, frame, _, summary in items]}
    write(HERE / "preflight.json", result)
    event(status="PREFLIGHT_PASS", cases=len(items), pins=73)


def execute_child(key):
    started = time.monotonic()
    report = {"scope": "RECORDED_INPUT_REAL_API_REPLAY", "status": "RUNNING", "planned": 4,
              "started_at": datetime.now(UTC).isoformat(), "attempts": [],
              "raw_directory": str(RAW.relative_to(ROOT)), "physical_acceptance": False,
              "formal_research": "NOT_ACCEPTED", "native": "UNKNOWN", "R439_full": "NOT_RUN",
              "new_render": 0, "physics_steps": 0, "dispatch": 0, "gpu_service_operations": 0,
              "billing_cost": None, "pure_inference_duration_s": None,
              "capture_mode": "original historical frames and timestamps; no fresh capture",
              "phase_label_note": "_attempt first/warm labels retained verbatim; these are four distinct historical cases",
              "grasp_profile": "mujoco_upright_box_v1", "current_v2_configuration_changed": False}
    store = InMemorySecretStore()
    profile_id = PLAN["profile_metadata"]["profile_id"]
    try:
        before = json.loads((HERE / "preflight.json").read_text())
        assert before["status"] == "PASS" and before["runner_sha256"] == sha(Path(__file__))
        assert before["plan_sha256"] == sha(ROUND / "plan.json")
        items = inputs()
        assert not any(RAW.iterdir()), "RAW_DIRECTORY_NOT_FRESH"
        write(RAW / "execution-start.json", {"at": report["started_at"], "runner_sha256": sha(Path(__file__))})
        metadata = PLAN["profile_metadata"]
        profile = ModelProviderProfile(**{k: v for k, v in metadata.items()
                                          if k in ModelProviderProfile.model_fields},
                                       display_name="OpenAI GPT-6.1-SOL (R460 read-only view)")
        store.set_secret(profile_id, key)
        def selected(pid):
            assert pid == profile_id
            return profile
        service = SimpleNamespace(get_profile=selected, secret_store=store)
        planner, cloud = resolve_cloud_role(service, profile_id, source_hashes=source_fingerprints(),
                                           allow_paid=True, image_size=(320, 240),
                                           coordinate_system="normalized_1000",
                                           grasp_profile="mujoco_upright_box_v1",
                                           expected_model_family="gpt-6.1-sol")
        settings = cloud_request_settings(planner)
        assert settings["generation_parameters"] == {"reasoning_effort": "low", "max_completion_tokens": 4096}
        assert settings["timeout_s"] == 180
        report.update(cloud_snapshot=cloud.evidence(), request_settings=settings,
                      source_hashes=source_fingerprints(), runner_sha256=sha(Path(__file__)))
        for index, (case, frame, expected_body, expected_summary) in enumerate(items):
            event(event="CASE_START", case_id=case["case_id"], index=index)
            request = InitialPlanningRequest(request_id=f"r460-{case['case_id']}",
                user_instruction=case["instruction"], observation=frame.observation,
                scene=SceneSummary(scene_version=1, updated_at=frame.observation.captured_at))
            attempt = _attempt(planner, request, frame, RAW, index, cloud, request_settings=settings)
            directory = RAW / f"attempt-{index:02d}"
            contract = attempt.get("parsed_json") or {}
            evidence = attempt.get("observation_evidence") or {}
            rows = attempt.get("cost_ledger", {}).get("requests", [])
            received = directory / "response.raw"
            response = json_body(received)
            request_path = directory / "request.raw"
            actual_body = json_body(request_path)
            geometry_pass = (not contract.get("_sentinel") and bool(contract.get("steps"))
                             and "grounded_target" in evidence and "grounded_destination" in evidence)
            checks = {"complete": attempt.get("status") == "COMPLETE",
                      **{name: attempt.get(name) is True for name in (
                          "transport_two_images", "parsed", "grounded", "target_hit", "destination_hit")},
                      "geometry_gate": geometry_pass, "wire_body_matches": actual_body == expected_body,
                      "summary_matches": attempt.get("request_summary") == expected_summary,
                      "one_successful_request": len(rows) == 1 and rows[0]["status"] == "SUCCESS",
                      "originals_unsuppressed": not attempt.get("wire_artifact_suppressed", False)}
            entry = {"case_id": case["case_id"], "passed": all(checks.values()), "checks": checks,
                     "source_input": case["input_directory"], "observation_sha256": frame.observation.checksum_sha256,
                     "request_sha256": attempt.get("request_sha256"), "response_sha256": attempt.get("response_sha256"),
                     "sent_bytes": attempt.get("serialized_sent_bytes", 0),
                     "received_bytes": attempt.get("serialized_received_bytes", 0),
                     "attempt_sha256": sha(directory / "attempt.json"),
                     "request_count": len(rows), "wall_latency_ms": attempt.get("wall_latency_ms"),
                     "parse_error": attempt.get("parse_error"), "sentinel": contract.get("_sentinel"),
                     "geometry_reason": contract.get("_reason"), "failure_type": attempt.get("failure_type"),
                     "reported_model": response.get("model"), "usage": response.get("usage"),
                     "response_error": response.get("error", {}).get("code") if isinstance(response.get("error"), dict) else None,
                     "finish_reason": (response.get("choices") or [{}])[0].get("finish_reason"),
                     "target_pixel": evidence.get("original_pixel_target"),
                     "destination_pixel": evidence.get("original_pixel_destination"),
                     "top_grasp_status": evidence.get("top_grasp_offset_status"),
                     "visual_decision": evidence.get("visual_decision"),
                     "compiled_step_count": len(contract.get("steps", []))}
            report["attempts"].append(entry)
            event(event="CASE_FINISH", case_id=case["case_id"], passed=entry["passed"],
                  checks=checks, latency_ms=entry["wall_latency_ms"], error_code=entry["response_error"])
            if not entry["passed"]:
                break
        report["status"] = ("RECORDED_INPUT_API_REPLAY_PASS" if len(report["attempts"]) == 4
                            and all(row["passed"] for row in report["attempts"]) else "FAILED_STOPPED")
    except BaseException as error:
        report.update(status="FAILED_STOPPED", safe_failure_class=type(error).__name__)
    finally:
        store.delete_secret(profile_id)
        report.update(finished_at=datetime.now(UTC).isoformat(), wall_s=time.monotonic() - started,
                      attempted=len(report["attempts"]), unexecuted=4-len(report["attempts"]),
                      inference_requests=sum(row["request_count"] for row in report["attempts"]))
        write(HERE / "replay-report.json", report)
    return 0 if report["status"] == "RECORDED_INPUT_API_REPLAY_PASS" else 2


def execute():
    assert sys.stdin.isatty(), "HIDDEN_TTY_REQUIRED"
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    key = getpass.getpass("OpenAI credential (hidden, memory only): ")
    assert key and len(key) <= 512
    pid = os.fork()
    if pid == 0:
        os.setsid()
        os._exit(execute_child(key))
    key = ""
    started = time.monotonic()
    peak_rss = 0
    reason = None
    while True:
        done, status = os.waitpid(pid, os.WNOHANG)
        if done:
            break
        try:
            values = Path(f"/proc/{pid}/statm").read_text().split()
            rss = int(values[1]) * os.sysconf("SC_PAGE_SIZE")
            peak_rss = max(peak_rss, rss)
        except (FileNotFoundError, ProcessLookupError):
            rss = 0
        raw_bytes = sum(path.stat().st_size for path in RAW.rglob("*") if path.is_file())
        if time.monotonic()-started > 900 or rss > 2147483648 or raw_bytes > 67108864:
            reason = "RESOURCE_BUDGET_EXCEEDED"
            os.killpg(pid, signal.SIGTERM)
            time.sleep(1)
            done, status = os.waitpid(pid, os.WNOHANG)
            if not done:
                os.killpg(pid, signal.SIGKILL)
                _, status = os.waitpid(pid, 0)
            break
        time.sleep(0.2)
    code = os.waitstatus_to_exitcode(status)
    write(HERE / "supervisor-result.json", {"child_pid": pid, "returncode": code,
          "reaped": True, "wall_s": time.monotonic()-started, "peak_rss_bytes": peak_rss,
          "budget_failure": reason, "raw_bytes": sum(p.stat().st_size for p in RAW.rglob("*") if p.is_file())})
    event(status="PROCESS_COMPLETE", returncode=code, reaped=True)
    return code


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        result = preflight() if args.preflight else execute()
        sys.exit(result or 0)
    except Exception as error:
        event(status="STOPPED", safe_failure_class=type(error).__name__)
        sys.exit(2)
