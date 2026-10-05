"""Independent read-only audit of the completed 20-episode experiment."""
from __future__ import annotations

import base64
import hashlib
import io
import ipaddress
import json
import math
import re
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import numpy as np
from PIL import Image
from pydantic import TypeAdapter

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]
RUN = BASE / "run-v2"
HISTORICAL = ROOT / "artifacts/research/process/20261003-t7-visual-closed-loop/smoke-20-v2"
sys.path.insert(0, str(ROOT / "src"))
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import CompletionCriteria, PhysicalSample, evaluate_evidence
from cloud_edge_robot_arm.vision.planner import VisualDecision


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def proportion(count, denominator):
    z = 1.959963984540054
    p = count / denominator
    center = (p + z*z/(2*denominator)) / (1 + z*z/denominator)
    half = z * math.sqrt(p*(1-p)/denominator + z*z/(4*denominator**2)) / (1 + z*z/denominator)
    return {"count": count, "denominator": denominator, "rate": p,
            "wilson_95": [max(0, center-half), min(1, center+half)]}


def quantiles(values):
    return {"p50": float(np.quantile(values, 0.5)), "p95": float(np.quantile(values, 0.95))}


def main():
    errors = []

    def check(condition, message):
        if not condition:
            errors.append(message)

    protocol = read(RUN / "protocol.json")
    assignments = read(RUN / "assignments.json")
    rows = read(RUN / "results.json")
    check(read(RUN / "run-end.json")["recorded"] == 20, "incomplete run")
    check(read(RUN / "run-start.json")["protocol_sha256"] == digest(RUN / "protocol.json"), "protocol drift")
    for name in ("assignments", "model", "config"):
        check(digest(RUN / (name + (".yaml" if name == "config" else ".json"))) == protocol[name + "_sha256"], name + " drift")
    for name, expected in protocol["source_sha256"].items():
        check(digest(ROOT / name) == expected, "source drift: " + name)
    check(not protocol["historical_source_differences"], "historical pipeline source differs")
    check(assignments == read(HISTORICAL / "assignments.json"), "historical assignments differ")
    check(len(rows) == 20 and {r["case_id"] for r in rows} == {c["case_id"] for c in assignments["cases"]}, "not exactly one result per assigned case")
    indexed = {r["case_id"]: r for r in rows}
    sample_count = frame_count = action_count = 0
    calls, details, baseline = [], [], []
    for case in assignments["cases"]:
        cid = case["case_id"]
        directory = RUN / "cases" / cid
        row = indexed[cid]
        episode = read(directory / "episode.json")
        records = episode["verification_records"]
        check(read(directory / "assignment.json") == case, cid + " assignment differs")
        check(read(directory / "case-result.json") == row, cid + " record differs")
        check(row["scene_hash"] == case["scene_hash"], cid + " scene hash differs")
        samples = TypeAdapter(list[PhysicalSample]).validate_python(read(directory / "physical-evidence.json"))
        physical = asdict(evaluate_evidence(samples, CompletionCriteria(object_id="object", target_region_id="target_region"),
                                            evaluation_start_step=samples[0].physics_step))
        check(canonical(physical) == canonical(read(directory / "physical-outcome.json")), cid + " physical replay differs")
        check(records[-1]["layer"] == "INDEPENDENT_PHYSICAL_RESULT" and records[-1]["used_for_online_routing"] is False,
              cid + " offline verdict entered online routing")
        success = bool(episode["online_reported_complete"] and physical["success"] and episode["terminal_reason"] is None and case["kind"] != "MISSING_TARGET")
        check(row["task_success"] == row["success"] == success, cid + " success differs")
        check(row["false_completion"] == bool(episode["online_reported_complete"] and not success), cid + " false completion differs")
        frames = [r for r in records if r["layer"] == "OBSERVATION"]
        actions = [r for r in records if r["layer"] in ("SKILL_RETURN", "PARTIAL_SKILL_RETURN") and r["physics_steps"] > 0]
        model_returns = [r for r in records if r["layer"] == "MODEL_RETURN"]
        check(len(frames) == row["observation_count"] and len(actions) == row["executed_actions"], cid + " frame/action count differs")
        check(len({r["frame_id"] for r in frames}) == len(frames), cid + " frame ID reused")
        check({r["episode_id"] for r in frames} == {episode["episode_id"]}, cid + " episode mismatch")
        frame_index = {r["observation_id"]: index for index, r in enumerate(frames, 1)}
        for previous, current in zip(frames, frames[1:]):
            check(current["captured_at"] > previous["captured_at"] and current["sim_time_s"] >= previous["sim_time_s"], cid + " nonmonotonic capture")
        for index, frame in enumerate(frames, 1):
            check(frame["ground_truth_used_for_control"] is False, cid + " ground truth control")
            for key, file in (("rgb_sha256", "rgb.png"), ("depth_sha256", "depth.f32")):
                check(digest(directory / "frames" / f"{index:03d}" / file) == frame[key], cid + " frame payload drift")
        for file in ("rgb.png", "depth.f32"):
            check(digest(directory / "frames/001" / file) == digest(HISTORICAL / "cases" / cid / "frames/001" / file), cid + " historical initial sensor pixels differ")
        receipts = sorted(directory.glob("api/*/receipt.json"))
        check(len(receipts) == len(model_returns) == row["model_calls"] == row["api_calls_recorded"], cid + " model call count differs")
        decisions = []
        for receipt_path, returned in zip(receipts, model_returns):
            receipt = read(receipt_path)
            request_path = receipt_path.parent / "request.json"
            request = read(request_path)
            check(digest(request_path) == receipt["request_sha256"], cid + " request drift")
            check(receipt["http_status"] == 200 and receipt["ok"], cid + " API error")
            check(receipt["network"]["bound_interface"] == "enp7s0", cid + " wrong network interface")
            check(ipaddress.ip_address(receipt["network"]["peer"][0]).is_global, cid + " nonpublic peer")
            response = receipt["response"]
            check(request["model"] == response["model"] == "qwen3.8-max", cid + " wrong model")
            check(request["max_tokens"] == 512 and request["temperature"] == 0 and request["enable_thinking"] is False, cid + " generation drift")
            content = response["choices"][0]["message"]["content"]
            check(content == returned["raw_text"], cid + " adapter raw text differs from receipt")
            check(response["choices"][0]["finish_reason"] == "stop", cid + " truncated response")
            decision = VisualDecision.model_validate_json(content)
            evidence = returned["evidence"]
            check(evidence["model_snapshot_hash"] == protocol["model_snapshot_hash"], cid + " model settings drift")
            images = [item["image_url"]["url"] for message in request["messages"] if isinstance(message["content"], list)
                      for item in message["content"] if item["type"] == "image_url"]
            check(len(images) == 2, cid + " model did not receive RGB and depth")
            idx = frame_index[returned["request_observation_id"]]
            actual_rgb = np.asarray(Image.open(io.BytesIO(base64.b64decode(images[0].split(",", 1)[1]))).convert("RGB"))
            expected_rgb = np.asarray(Image.open(directory / "frames" / f"{idx:03d}" / "rgb.png").convert("RGB"))
            check(np.array_equal(actual_rgb, expected_rgb), cid + " request RGB differs from observed frame")
            decisions.append({"call_index": returned["call_index"], "target_pixel": evidence.get("original_pixel_target"),
                "destination_pixel": evidence.get("original_pixel_destination"), "reported_confidence": decision.reported_confidence,
                "skills": decision.skills, "reason": decision.reason, "parse_error": returned["parse_error"],
                "target_relief_m": evidence.get("target_relief_above_support_m"),
                "target_visible_surface": evidence.get("target_visible_surface")})
            calls.append(receipt)
        stopped = False
        for record in records:
            if record["layer"] == "ONLINE_VERIFICATION" and record["route"] == "STOP":
                stopped = True
            if record["layer"] == "ACTION_STARTED":
                check(not stopped, cid + " action after STOP")
        misoperation = case["kind"] == "MISSING_TARGET" and bool(actions)
        check(row["absent_misoperation"] == misoperation, cid + " missing-target misoperation differs")
        details.append({"case_id": cid, "kind": case["kind"], "success": success,
            "online_reported_complete": episode["online_reported_complete"],
            "final_region_margin_mm": [1000 * (region_extent - abs(position - center) - extent)
                for position, center, extent, region_extent in zip(samples[-1].object_position_m[:2],
                    samples[-1].region_center_xy_m, samples[-1].object_half_extent_xy_m, samples[-1].region_half_extent_xy_m)],
            "terminal_reason": row["terminal_reason"], "actions": len(actions), "model_calls": len(receipts),
            "lift_mm": 1000 * physical["measured_lift_m"], "hold_s": physical["hold_s"],
            "placed_stable_s": physical["placed_stable_s"], "physical_failure_reason": physical["failure_reason"],
            "decisions": decisions})
        baseline.append(read(HISTORICAL / "cases" / cid / "case-result.json"))
        sample_count += len(samples)
        frame_count += len(frames)
        action_count += len(actions)
    normal = [r for r in rows if r["kind"] == "NORMAL"]
    missing = [r for r in rows if r["kind"] == "MISSING_TARGET"]
    faults = [r for r in rows if r["kind"] in ("INVALID_DEPTH", "SAFETY_STOP")]
    check(len(normal) == 12 and len(missing) == 4 and len(faults) == 4, "denominators differ")
    check(len(calls) <= 60, "request budget exceeded")
    secret_files = []
    for path in BASE.rglob("*"):
        if path.is_file() and path.suffix in (".json", ".py", ".md", ".yaml"):
            if re.search(rb"sk-(?:sp|ws)-[A-Za-z0-9_.-]{15,}|Bearer [A-Za-z0-9_.-]{20,}", path.read_bytes()):
                secret_files.append(str(path.relative_to(BASE)))
    check(not secret_files, "credential patterns persisted")
    report = {
        "valid": not errors, "errors": errors, "formal_g1": False,
        "assigned": 20, "normal_success": proportion(sum(r["success"] for r in normal), 12),
        "all_assigned_success": proportion(sum(r["success"] for r in rows), 20),
        "missing_target_no_action": proportion(sum(not r["absent_misoperation"] for r in missing), 4),
        "missing_target_explicit_refusal_all_calls": sum(all(d["target_pixel"] is None and not d["skills"] for d in c["decisions"]) for c in details if c["kind"] == "MISSING_TARGET"),
        "fault_no_action": proportion(sum(r["executed_actions"] == 0 for r in faults), 4),
        "false_completions": sum(r["false_completion"] for r in rows), "environment_blocked": sum(r["blocked"] for r in rows),
        "normal_failure_reasons": dict(Counter(r["terminal_reason"] or r["failure_reason"] or "SUCCESS" for r in normal)),
        "model_calls": len(calls), "api_wall_s": quantiles([r["wall_s"] for r in calls]),
        "normal_episode_wall_s": quantiles([r["wall_latency_s"] for r in normal]),
        "usage": {k: sum(r["response"]["usage"][k] for r in calls) for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
        "invoice_cost_cny": None, "physical_samples": sample_count, "frames": frame_count, "actions": action_count,
        "historical_normal_success": proportion(sum(r["success"] for r in baseline if r["kind"] == "NORMAL"), 12),
        "historical_missing_target_misoperation": sum(r["executed_actions"] > 0 for r in baseline if r["kind"] == "MISSING_TARGET"),
        "same_assignments_source_and_initial_sensor_pixels": not any("historical" in error for error in errors),
        "direct_network": {"interface": "enp7s0", "peers": sorted({r["network"]["peer"][0] for r in calls})},
        "credential_patterns_found": secret_files, "cases": details,
    }
    (BASE / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
