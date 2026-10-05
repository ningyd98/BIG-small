"""Read-only physical replay, denominator audit and paired statistics for this run."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import numpy as np
from pydantic import TypeAdapter

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (  # noqa: E402
    CompletionCriteria,
    PhysicalSample,
    evaluate_evidence,
)

BASE = Path(__file__).parent
ROOT = BASE.parents[3]
# Same metric/replay implementation as the prior 60-scene comparison; paths/providers expanded.
RUN = BASE / "independent-60"
METHODS = ("qwen8", "qwen4")


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def quantile(values, probability):
    if not values:
        return None
    if any(value is None or not math.isfinite(value) for value in values):
        raise ValueError("quantile includes missing/nonfinite measurements")
    return float(np.quantile(values, probability, method="linear"))


def proportion(count, denominator):
    if not 0 <= count <= denominator or denominator <= 0:
        raise ValueError("invalid proportion denominator")
    z = 1.959963984540054
    p = count / denominator
    center = (p + z * z / (2 * denominator)) / (1 + z * z / denominator)
    half = z * math.sqrt(p * (1 - p) / denominator + z * z / (4 * denominator**2))
    half /= 1 + z * z / denominator
    return {
        "count": count,
        "denominator": denominator,
        "rate": p,
        "wilson_95": [max(0, center - half), min(1, center + half)],
    }


def audit():
    assignments, protocol = read(RUN / "assignments.json"), read(RUN / "protocol.json")
    errors, cases, samples_count, frame_count, action_count = [], [], 0, 0, 0
    for file, key in (("models.json", "models_sha256"), ("assignments.json", "assignments_sha256")):
        if digest(RUN / file) != protocol[key]:
            errors.append("frozen input drift: " + file)
    for field in ("source_sha256", "historical_source_sha256"):
        for name, expected in protocol[field].items():
            if digest(ROOT / name) != expected:
                errors.append("source drift: " + name)
    rows = read(RUN / "results.json")
    expected_keys = {
        (case["case_id"], method) for case in assignments["cases"] for method in METHODS
    }
    keys = [(row["case_id"], row["method"]) for row in rows]
    if set(keys) != expected_keys or len(keys) != 120 or len(set(keys)) != 120:
        errors.append("not exactly one retained result per assigned case/method")
    indexed = {(row["case_id"], row["method"]): row for row in rows}
    historical_rgb = {digest(path) for path in (ROOT / "datasets").rglob("rgb.png")}
    historical_rgb.update(
        digest(path)
        for path in (ROOT / "artifacts/research").rglob("rgb.png")
        if BASE not in path.parents
    )
    rgb_overlap = []
    for case in assignments["cases"]:
        pair = [indexed[(case["case_id"], method)] for method in METHODS]
        if any(
            pair[0].get(key) != other.get(key)
            for other in pair[1:]
            for key in ("scene_hash", "initial_rgb_sha256", "initial_depth_sha256")
        ):
            errors.append(case["case_id"] + ": paired scene or initial pixels differ")
        if pair[0].get("initial_rgb_sha256") in historical_rgb:
            rgb_overlap.append(case["case_id"])
        for row in pair:
            before = len(errors)
            directory = RUN / row["method"] / "cases" / case["case_id"]
            if row != read(directory / "record.json"):
                errors.append("result differs from individual record")
            if row["scene_hash"] != case["scene_hash"] or row["kind"] != case["kind"]:
                errors.append("assignment/result binding differs")
            if row["blocked"] or row.get("error"):
                errors.append(f"{case['case_id']} {row['method']}: environment blocked")
                continue
            episode = read(directory / "episode.json")
            samples = TypeAdapter(list[PhysicalSample]).validate_python(
                read(directory / "physical-evidence.json")
            )
            physical = asdict(
                evaluate_evidence(
                    samples,
                    CompletionCriteria(object_id="object", target_region_id="target_region"),
                    evaluation_start_step=samples[0].physics_step,
                )
            )
            if canonical(physical) != canonical(read(directory / "physical-outcome.json")):
                errors.append("physical replay differs")
            records = episode["verification_records"]
            expected_success = bool(
                episode["online_reported_complete"]
                and physical["success"]
                and episode["terminal_reason"] is None
                and case["kind"] == "NORMAL"
            )
            if row["task_success"] != expected_success:
                errors.append("task success conjunction differs")
            if row["false_completion"] != bool(
                episode["online_reported_complete"] and not expected_success
            ):
                errors.append("false completion differs")
            frames = [r for r in records if r["layer"] == "OBSERVATION"]
            actions = [
                r
                for r in records
                if r["layer"] in ("SKILL_RETURN", "PARTIAL_SKILL_RETURN") and r["physics_steps"] > 0
            ]
            if len(frames) != row["observation_count"] or len(actions) != row["executed_actions"]:
                errors.append("frame/action count differs")
            if len({r["frame_id"] for r in frames}) != len(frames):
                errors.append("reused frame ID")
            if {r["episode_id"] for r in frames} != {episode["episode_id"]}:
                errors.append("foreign episode frame")
            for previous, current in zip(frames, frames[1:], strict=False):
                if (
                    current["captured_at"] <= previous["captured_at"]
                    or current["sim_time_s"] < previous["sim_time_s"]
                ):
                    errors.append("nonmonotonic frames")
            for index, frame in enumerate(frames, 1):
                for key, file in (("rgb_sha256", "rgb.png"), ("depth_sha256", "depth.f32")):
                    if digest(directory / "frames" / f"{index:03d}" / file) != frame[key]:
                        errors.append("frame payload hash differs")
            for key, file in (
                ("initial_rgb_sha256", "rgb.png"),
                ("initial_depth_sha256", "depth.f32"),
            ):
                if digest(directory / "initial-offline" / file) != row[key]:
                    errors.append("initial payload hash differs")
            first = next(r for r in records if r["layer"] == "MODEL_RETURN")
            evidence = first.get("evidence") or {}
            pixel = evidence.get("original_pixel_target")
            metadata = read(directory / "initial-offline/observation.json")
            instance_ids = np.fromfile(
                directory / "initial-offline/instance_geom_ids.i32", dtype="<i4"
            )
            hit = bool(
                isinstance(pixel, list)
                and len(pixel) == 2
                and all(type(v) is int for v in pixel)
                and 0 <= pixel[0] < metadata["width"]
                and 0 <= pixel[1] < metadata["height"]
                and metadata["instance_labels"].get(
                    str(int(instance_ids[pixel[1] * metadata["width"] + pixel[0]]))
                )
                == "object_geom"
            )
            truth = read(directory / "initial-truth.json")
            target = next(item for item in truth["instances"] if item["role"] == "target")
            reference = [*target["position"][:2], target["position"][2] + target["half_size"][2]]
            point = evidence.get("target_visible_surface")
            valid = bool(
                case["kind"] == "NORMAL"
                and hit
                and isinstance(point, dict)
                and all(
                    type(point.get(axis)) in (int, float) and math.isfinite(point[axis])
                    for axis in ("x", "y", "z")
                )
            )
            error = (
                1000 * math.dist([point[a] for a in ("x", "y", "z")], reference) if valid else None
            )
            if (
                row["recognized"] != bool(hit and case["kind"] == "NORMAL")
                or row["localization_valid"] != valid
                or row["localization_error_mm"] != error
            ):
                errors.append("independent localization replay differs")
            missing_actions = bool(case["kind"] == "MISSING_TARGET" and len(actions) > 0)
            if row["absent_misoperation"] != missing_actions:
                errors.append("misoperation count differs")
            chats = [
                r
                for r in read(directory / "requests.json")
                if r["path"] in {"/api/chat", "/chat/completions"}
            ]
            if len(chats) != row["model_calls"] or any(r.get("error") for r in chats):
                errors.append("chat request count or completion differs")
            expected_model = read(RUN / "models.json")[row["method"]]["model"]
            if any(r.get("response", {}).get("model") != expected_model for r in chats):
                errors.append("response model differs")
            if records[-1]["layer"] != "INDEPENDENT_PHYSICAL_RESULT":
                errors.append("independent scoring did not run last")
            stopped = False
            for record in records:
                if record["layer"] == "ONLINE_VERIFICATION" and record["route"] == "STOP":
                    stopped = True
                elif record["layer"] == "ACTION_STARTED" and stopped:
                    errors.append("action started after STOP")
            samples_count += len(samples)
            frame_count += len(frames)
            action_count += len(actions)
            cases.append(
                {
                    "case_id": case["case_id"],
                    "method": row["method"],
                    "valid": before == len(errors),
                }
            )
    if rgb_overlap:
        errors.append("initial RGB overlap with historical data")
    return {
        "valid": not errors,
        "errors": errors,
        "assigned_scenes": 60,
        "recorded_runs": len(rows),
        "physical_samples": samples_count,
        "frames": frame_count,
        "actions": action_count,
        "historical_unique_rgb_sha256": len(historical_rgb),
        "initial_rgb_overlap": rgb_overlap,
        "paired_initial_pixels_identical": not any("paired scene" in e for e in errors),
        "cases": cases,
    }


def summarize(rows):
    summaries = {}
    for method in METHODS:
        selected = [r for r in rows if r["method"] == method]
        normal = [r for r in selected if r["kind"] == "NORMAL"]
        absent = [r for r in selected if r["kind"] == "MISSING_TARGET"]
        if len(selected) != 60 or len(normal) != 40 or len(absent) != 20:
            raise ValueError("incomplete fixed denominators")
        chats = [
            chat
            for r in selected
            for chat in read(RUN / method / "cases" / r["case_id"] / "requests.json")
            if chat["path"] in {"/api/chat", "/chat/completions"}
        ]
        errors = [r["localization_error_mm"] for r in normal if r["localization_valid"]]
        summaries[method] = {
            "absent_misoperation": proportion(sum(r["absent_misoperation"] for r in absent), 20),
            "normal_task_success": proportion(sum(r["task_success"] for r in normal), 40),
            "all_assigned_task_success": proportion(sum(r["task_success"] for r in selected), 60),
            "localization_coverage": proportion(len(errors), 40),
            "localization_p90_mm": quantile(errors, 0.90),
            "wall_latency_p95_s": quantile([r["wall_latency_s"] for r in selected], 0.95),
            "model_latency_p95_s": quantile([r["model_latency_s"] for r in selected], 0.95),
            "failure_penalized_normal_latency_p95_s": quantile(
                [r["wall_latency_s"] if r["task_success"] else 120 for r in normal], 0.95
            ),
            "false_completions": sum(r["false_completion"] for r in selected),
            "blocked": sum(r["blocked"] for r in selected),
            "safety_violations": sum(r["safety_violation"] for r in selected),
            "absent_first_response_null_target": sum(
                "target_pixel" in r["first_model_evidence"].get("visual_decision", {})
                and r["first_model_evidence"]["visual_decision"]["target_pixel"] is None
                for r in absent
            ),
            "absent_first_response_low_confidence": sum(
                r["first_model_evidence"].get("visual_decision", {}).get("reported_confidence", 1)
                < 0.5
                for r in absent
            ),
            "api_invoice_cost_cny_per_task": 0.0,
            "total_cost_cny_per_task": None,
            "chat_requests": len(chats),
            "chat_requests_per_task": len(chats) / 60,
            "input_tokens": sum(r["prompt_eval_count"] for r in chats),
            "output_tokens": sum(r["eval_count"] for r in chats),
            "provider_inference_s": sum(r["total_duration"] for r in chats) / 1e9,
            "provider_load_s": sum(r["load_duration"] for r in chats) / 1e9,
            "provider_prompt_eval_s": sum(r["prompt_eval_duration"] for r in chats) / 1e9
            if all(r["prompt_eval_duration"] is not None for r in chats)
            else None,
            "provider_output_eval_s": sum(r["eval_duration"] for r in chats) / 1e9
            if all(r["eval_duration"] is not None for r in chats)
            else None,
            "model_load_requests": sum(r["load_duration"] > 100_000_000 for r in chats),
            "wall_task_seconds": sum(r["wall_latency_s"] for r in selected),
            "failure_reasons": dict(
                Counter(r.get("terminal_reason") or "SUCCESS" for r in selected)
            ),
        }
    return summaries


def bootstrap(rows, left, right):
    by_key = {(row["case_id"], row["method"]): row for row in rows}
    cases = read(RUN / "assignments.json")["cases"]
    normal = [r["case_id"] for r in cases if r["kind"] == "NORMAL"]
    absent = [r["case_id"] for r in cases if r["kind"] == "MISSING_TARGET"]
    rng = np.random.default_rng(20261004)
    samples = {
        name: []
        for name in (
            "absent_misoperation_rate",
            "normal_success_rate",
            "localization_p90_mm",
            "wall_latency_p95_s",
            "model_latency_p95_s",
        )
    }
    for _ in range(10000):
        ns = rng.choice(normal, 40).tolist()
        ab = rng.choice(absent, 20).tolist()
        group = ns + ab
        for metric, field, subset in (
            ("absent_misoperation_rate", "absent_misoperation", ab),
            ("normal_success_rate", "task_success", ns),
        ):
            samples[metric].append(
                float(np.mean([by_key[c, left][field] - by_key[c, right][field] for c in subset]))
            )
        for metric, field, subset, q in (
            ("localization_p90_mm", "localization_error_mm", ns, 0.9),
            ("wall_latency_p95_s", "wall_latency_s", group, 0.95),
            ("model_latency_p95_s", "model_latency_s", group, 0.95),
        ):
            values = [
                [by_key[c, m][field] for c in subset if by_key[c, m].get(field) is not None]
                for m in (left, right)
            ]
            if all(values):
                samples[metric].append(quantile(values[0], q) - quantile(values[1], q))
    return {
        name: {
            "difference": left + " minus " + right,
            "valid_bootstrap_draws": len(values),
            "percentile_95": [quantile(values, 0.025), quantile(values, 0.975)],
        }
        for name, values in samples.items()
    }


def math_checks():
    assert quantile([1, 2, 3, 4, 5], 0.90) == 4.6
    assert quantile([], 0.90) is None
    assert abs(proportion(0, 20)["wilson_95"][1] - 0.16112515805281938) < 1e-10
    assert abs(proportion(20, 20)["wilson_95"][0] - 0.8388748419471806) < 1e-10
    try:
        quantile([1, None], 0.95)
    except ValueError:
        pass
    else:
        raise AssertionError("missing latency silently removed")
    try:
        proportion(0, 0)
    except ValueError:
        pass
    else:
        raise AssertionError("zero denominator silently accepted")


if __name__ == "__main__":
    math_checks()
    if "--math-only" in sys.argv:
        print("6 mathematical/denominator checks passed")
        raise SystemExit(0)
    rows = [row for method in METHODS for row in read(RUN / method / "results.json")]
    (RUN / "results.json").write_text(json.dumps(rows, indent=2, allow_nan=False) + "\n")
    validation = audit()
    (BASE / "independent-validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    if not validation["valid"]:
        print(json.dumps(validation, indent=2))
        raise SystemExit(1)
    rows = read(RUN / "results.json")
    summary = {
        "methods": summarize(rows),
        "paired_bootstrap": {
            left + "_minus_" + right: bootstrap(rows, left, right)
            for left, right in (("qwen8", "qwen4"),)
        },
        "protocol_sha256": digest(RUN / "protocol.json"),
        "formal_g1": False,
    }
    (BASE / "comparison-summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n"
    )
    print(json.dumps(summary, indent=2, allow_nan=False))
