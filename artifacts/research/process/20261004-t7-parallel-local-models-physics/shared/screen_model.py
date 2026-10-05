"""Immutable-bank, strict-contract development screen for loopback VLMs.

This does not execute actions or measure physical task success. Oracle sidecars
are opened only after the model response, for offline scoring.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import struct
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

BASE = Path(__file__).resolve().parents[1]
SOURCE = BASE / "source-snapshot"
sys.path[:0] = [str(SOURCE), str(SOURCE / "src")]
os.chdir(SOURCE)

from scripts import evaluate_rgbd_model_scenes as scene_eval
from scripts import probe_rgbd_model as probe
from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
from cloud_edge_robot_arm.vision.capture import CapturedFrame
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot
from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values, quantile):
    if not values:
        return None
    values = sorted(values)
    index = (len(values) - 1) * quantile
    lo, hi = math.floor(index), math.ceil(index)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)


def transport_image_hashes(calls):
    for call in calls:
        if call["path"] not in {"/api/chat", "/chat/completions", "/v1/chat/completions"}:
            continue
        images = []
        for message in call["request"].get("messages", []):
            images.extend(message.get("images", []))
            content = message.get("content")
            if isinstance(content, list):
                images.extend(item["image_url"]["url"].split(",", 1)[1]
                              for item in content if item.get("type") == "image_url")
        return [hashlib.sha256(base64.b64decode(value, validate=True)).hexdigest()
                for value in images]
    return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chat-path", default="/v1/chat/completions")
    parser.add_argument("--bank", type=Path, default=BASE / "shared/scene-bank")
    args = parser.parse_args()
    config, output, bank = args.config.resolve(), args.output.resolve(), args.bank.resolve()
    snapshot = ModelConfigSnapshot(**read(config))
    if urlsplit(snapshot.endpoint).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("this experiment permits local loopback endpoints only")
    manifest = read(bank / "bank-manifest.json")
    for relative, expected in manifest["files"].items():
        if sha(bank / relative) != expected:
            raise ValueError(f"bank hash mismatch: {relative}")
    if output.exists():
        raise FileExistsError("refusing to overwrite prior model evidence")
    assignments = read(bank / "assignments.json")
    write(output / "protocol.json", {
        "created_at": datetime.now(UTC).isoformat(),
        "model": {**snapshot.evidence(), "endpoint": snapshot.endpoint},
        "config_sha256": sha(config), "harness_sha256": sha(Path(__file__)),
        "bank_manifest_sha256": sha(bank / "bank-manifest.json"),
        "source_snapshot_manifest_sha256": sha(BASE / "source-snapshot-manifest.json"),
        "held_out_test": False, "physical_actions": 0,
        "formal_G1_qualification": False,
        "local_API_cost_CNY": 0, "total_running_cost_CNY": None,
        "cost_limitation": "User supplied no machine-hour rate; electricity/depreciation unmeasured",
        "localization_reference": "offline physical target top-center in world coordinates",
        "first_call": "cold or current runtime state; recorded, excluded from warm latency",
    })
    records = []
    for case in assignments["cases"]:
        case_path = bank / "cases" / case["case_id"]
        observation = RGBDObservation.model_validate(read(case_path / "observation-transport.json"))
        request = InitialPlanningRequest(
            request_id="parallel-local-model-screen-" + case["case_id"],
            user_instruction=case["instruction"], observation=observation,
            scene=SceneSummary(scene_version=1, updated_at=datetime.now(UTC)),
        )
        planner = RGBDPlannerAdapter(
            base_url=snapshot.endpoint, model=snapshot.model, provider=snapshot.provider,
            model_snapshot=snapshot, timeout_s=snapshot.timeout_s,
            chat_path=args.chat_path, allow_paid=snapshot.provider == "openai_compatible",
        )
        calls, original_post = [], planner._post

        def post(path, body):
            entry = {"path": path, "request": body}
            calls.append(entry)
            start = time.perf_counter()
            try:
                entry["response"] = original_post(path, body)
                return entry["response"]
            except Exception as exc:
                entry["error"] = repr(exc)
                raise
            finally:
                entry["wall_latency_s"] = time.perf_counter() - start

        planner._post = post
        attempt = {key: False for key in (
            "transport_two_images", "observed_scene_present", "parsed", "grounded",
            "target_hit", "destination_hit",
        )}
        started = time.perf_counter()
        try:
            draft = planner.plan(request)
            evidence = draft.observation_evidence
            decision = evidence.get("visual_decision", {})
            parsed = draft.parse_error is None and draft.observed_scene is not None
            attempt.update(
                observed_scene_present=draft.observed_scene is not None,
                raw_model_output=draft.raw_text, parse_error=draft.parse_error,
                parsed=parsed, grounded=parsed and draft.parsed_json is not None,
                observation_evidence=evidence, visual_decision=decision,
            )
        except Exception as exc:
            attempt["error"] = repr(exc)
        attempt["wall_latency_s"] = time.perf_counter() - started
        # Offline mask/geometry access begins after inference; never enters request.
        metadata = read(case_path / "initial-offline/observation.json")
        binding = read(case_path / "frame-binding.json")
        ids = (case_path / "initial-offline/instance_geom_ids.i32").read_bytes()
        frame = CapturedFrame(observation, struct.unpack(f"<{len(ids)//4}i", ids),
            {int(key): value for key, value in metadata["instance_labels"].items()},
            binding["physics_state_hash"], tuple(binding["pass_state_hashes"]))
        decision, evidence = attempt.get("visual_decision", {}), attempt.get("observation_evidence", {})
        for kind, label in (("target", "object_geom"), ("destination", "target_region_geom")):
            hit, check = probe._pixel_hit(frame,
                probe._original_decision_pixel(planner, frame, evidence, decision, kind), label)
            attempt[kind + "_hit"], attempt[kind + "_offline_check"] = hit, check
        hashes = transport_image_hashes(calls)
        attempt["transport_image_sha256"] = hashes
        attempt["transport_two_images"] = hashes == [
            sha(case_path / "initial-offline/rgb.png"), sha(case_path / "initial-offline/depth.png")]
        record = {
            "case_id": case["case_id"], "kind": case["kind"],
            "scene_sha256": case.get("scene_sha256"),
            "rgb_sha256": metadata["rgb_sha256"],
            "complete": not attempt.get("error"), "attempt": attempt,
            "capture": {**observation.evidence(), "synchronized": binding["synchronized"],
                        "source": "mujoco_camera"},
            "diagnostics": scene_eval.offline_diagnostics(frame, attempt),
        }
        record["passed"] = scene_eval.case_passes(case, record) if case["kind"] != "FIXED_S01" else (
            all(attempt.get(key) is True for key in ("transport_two_images", "parsed", "grounded",
                                                    "target_hit", "destination_hit"))
            and scene_eval._calibrated_offset(attempt))
        truth = read(case_path / "initial-truth.json")
        target = next(item for item in truth["instances"] if item["role"] == "target")
        world = attempt["target_offline_check"].get("world_surface_point_m")
        top = [*target["position"][:2], target["position"][2] + target["half_size"][2]]
        record["target_top_center_error_mm"] = (
            1000 * math.dist([world[key] for key in ("x", "y", "z")], top)
            if isinstance(world, dict) else None)
        directory = output / "cases" / case["case_id"]
        write(directory / "requests.json", calls)
        write(directory / "outcome.json", record)
        records.append(record)
        print(case["case_id"], record["passed"], attempt.get("parse_error") or attempt.get("error"), flush=True)
    write(output / "results.json", records)
    scored = [record for record in records if record["kind"] != "FIXED_S01"]
    scored_assignments = {**assignments, "cases": [case for case in assignments["cases"]
                                                 if case["kind"] != "FIXED_S01"]}
    summary = scene_eval.summarize_results(scored_assignments, scored)
    positives = [record for record in scored if record["kind"] == "positive"]
    errors = [record["target_top_center_error_mm"] for record in positives
              if record["target_top_center_error_mm"] is not None]
    negatives = [record for record in scored if record["kind"] == "negative_absent"]
    summary.update(
        fixed_passed=sum(record["passed"] for record in records if record["kind"] == "FIXED_S01"),
        fixed_cases=4, target_error_p90_mm=percentile(errors, .90),
        target_error_coverage=f"{len(errors)}/{len(positives)}",
        warm_wall_latency_p95_s=percentile([r["attempt"]["wall_latency_s"] for r in records[1:]], .95),
        negative_explicit_refusal=sum(scene_eval._explicit_refusal(r["attempt"]) for r in negatives),
        negative_grounded_action_proposals=sum(r["attempt"].get("grounded") is True for r in negatives),
        physical_task_success_rate=None, physical_misoperation_rate=None,
        physical_actions=0, local_API_cost_CNY_per_task=0, total_cost_CNY_per_task=None,
    )
    write(output / "summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
