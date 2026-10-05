"""One-off, frozen paired holdout evaluation; no production behavior changes."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
import urllib.request
from collections import Counter
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import numpy as np

from scripts.run_rgbd_smoke import smoke_dataset_config
from cloud_edge_robot_arm.datasets.rgbd.capture import OfflineSceneAdapter
from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec
from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import sample_scene
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession, save_captured_frame
from cloud_edge_robot_arm.vision.evaluation import ExecutionPolicy, independent_top_center
from cloud_edge_robot_arm.vision.execution import run_visual_episode
from cloud_edge_robot_arm.vision.frozen_model import load_frozen_planner
from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot
from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter

BASE = Path(__file__).parent
FROZEN = ROOT / "artifacts/research/process/20261003-t7-visual-closed-loop/model-probe"
METHODS = ("qwen3vl", "qwen35")


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                indent=2, allow_nan=False) + "\n")


def scene_entries(value):
    if isinstance(value, dict):
        if "scene_parameters" in value and "seed" in value:
            yield value
        for child in value.values():
            yield from scene_entries(child)
    elif isinstance(value, list):
        for child in value:
            yield from scene_entries(child)


def historical_sources():
    paths = set()
    for tree in (ROOT / "datasets", ROOT / "artifacts/research"):
        for pattern in ("scene.json", "assignments.json", "manifest.json"):
            paths.update(tree.rglob(pattern))
    return sorted(paths)


def preregister():
    output = BASE / "independent-60"
    if output.exists():
        raise FileExistsError(output)
    load_frozen_planner(FROZEN)  # Verify the accepted T7 bundle, no inference.
    snapshot = ModelConfigSnapshot(**read(FROZEN / "model-frozen.json"))
    tags = json.load(urllib.request.urlopen(snapshot.endpoint + "/api/tags", timeout=10))
    tag = next(item for item in tags["models"] if item["name"] == "qwen3.5:4b")
    comparison = replace(snapshot, model="qwen3.5:4b", weight_digest=tag["digest"],
                         quantization=tag["details"]["quantization_level"])
    previous, source_files = [], {}
    for path in historical_sources():
        previous.extend(scene_entries(read(path)))
        source_files[str(path.relative_to(ROOT))] = digest(path)
    seeds = {row["seed"] for row in previous}
    geometry = {canonical(row["scene_parameters"]) for row in previous}
    config = smoke_dataset_config().model_copy(update={
        "dataset_id": "t7-independent-comparison-20261004-v1", "groups": 60, "seed": 901001,
    })
    cases = []
    for index in range(60):
        scene = sample_scene(config, 901001 + index)
        if scene.seed in seeds or canonical(scene.scene_parameters) in geometry:
            raise ValueError("holdout scene overlaps previously recorded sources")
        kind = "NORMAL" if index < 40 else "MISSING_TARGET"
        color = scene.scene_parameters["target"]["color_name"] if kind == "NORMAL" else "purple"
        cases.append({"case_id": f"holdout-{index + 1:02d}", "kind": kind,
                      "seed": scene.seed, "scene": scene.model_dump(mode="json"),
                      "scene_hash": scene.scene_hash,
                      "instruction": f"Move the {color} block to the green region."})
    permutation = np.random.default_rng(20261004).permutation(60).tolist()
    cases = [cases[index] for index in permutation]
    for index, case in enumerate(cases):
        case["method_order"] = list(METHODS if index % 2 == 0 else METHODS[::-1])
    if len({canonical(row["scene"]["scene_parameters"]) for row in cases}) != 60:
        raise ValueError("duplicate holdout geometry")
    output.mkdir()
    snapshots = {"qwen3vl": asdict_json(snapshot), "qwen35": asdict_json(comparison)}
    write(output / "models.json", snapshots)
    write(output / "assignments.json", {"assigned_scenes": 60, "assigned_runs": 120,
          "counts": {"NORMAL": 40, "MISSING_TARGET": 20}, "cases": cases,
          "config": config.model_dump(mode="json")})
    write(output / "protocol.json", {
        "created_at": datetime.now(UTC).isoformat(), "formal_g1": False,
        "purpose": "exploratory independent paired model comparison; not T8 or formal G1",
        "policy": "all 120 retained; no tuning, retries, exclusions or sample-size changes",
        "online_policy": {"timeout_s": 120, "max_reobservations": 2, "max_retries": 0,
                          "max_no_progress": 3, "deadline_s": 120},
        "localization": "first response only, correct target geom hit and valid metric point; "
                        "Euclidean distance to independent settled rigid-box top center; mm; "
                        "report coverage over all 40 NORMAL assignments",
        "misoperation": "MISSING_TARGET with >=1 executed physics skill / all 20 MISSING_TARGET",
        "success": "online AND independent physical AND target-present; normal /40 primary; /60 also",
        "latency": "wall seconds from initial capture through terminal evaluation and evidence write; "
                   "all 60 per method including failures; setup and warmup excluded",
        "penalized_latency": "120s for each unsuccessful NORMAL case; successful NORMAL wall time",
        "quantiles": "numpy.quantile(method='linear'); no frame/request pseudo-replication",
        "intervals": "Wilson two-sided 95% proportions; paired scene bootstrap 10000 draws seed 20261004",
        "cost": "measured local provider API invoice cost CNY 0; total including electricity and "
                "hardware depreciation unavailable; report actual requests, tokens and inference seconds",
        "missing_target": "purple not in registered red/blue/yellow palette; scoped absence test only",
        "same_scene_pairing": "same SceneSpec/seed/settle steps and initial RGB/depth SHA required",
        "models_sha256": digest(output / "models.json"),
        "assignments_sha256": digest(output / "assignments.json"),
        "historical_scene_records": len(previous), "historical_source_sha256": source_files,
        "seed_overlap": 0, "exact_geometry_overlap": 0,
        "source_sha256": {str(p.relative_to(ROOT)): digest(p) for p in [
            *sorted((ROOT / "src/cloud_edge_robot_arm/vision").glob("*.py")),
            *sorted((ROOT / "src/cloud_edge_robot_arm/edge/evidence").glob("*.py")),
            *sorted((ROOT / "src/cloud_edge_robot_arm/edge/recovery").glob("*.py")),
            *sorted((ROOT / "src/cloud_edge_robot_arm/edge/runtime").glob("*.py")),
            *sorted((ROOT / "src/cloud_edge_robot_arm/edge/safety").glob("*.py")),
            *sorted((ROOT / "src/cloud_edge_robot_arm/simulation/mujoco").glob("*.py")),
            *sorted((ROOT / "src/cloud_edge_robot_arm/datasets/rgbd").glob("*.py")),
            ROOT / "src/cloud_edge_robot_arm/auto_mode/runtime_events.py",
            ROOT / "src/cloud_edge_robot_arm/simulation/config.py",
            ROOT / "assets/robots/franka_panda/scene.xml", Path(__file__),
        ]},
    })
    print("PREREGISTERED", digest(output / "protocol.json"), len(previous), flush=True)


def asdict_json(snapshot):
    return {**snapshot.evidence(), "endpoint": snapshot.endpoint} | {
        "endpoint_hash": None
    }


def load_snapshot(value):
    return ModelConfigSnapshot(**{key: item for key, item in value.items()
                                  if key != "endpoint_hash"})


class MeteredPlanner(RGBDPlannerAdapter):
    def __init__(self, snapshot):
        super().__init__(base_url=snapshot.endpoint, model=snapshot.model,
                         provider=snapshot.provider, timeout_s=snapshot.timeout_s,
                         model_snapshot=snapshot)
        self.calls = []

    def _post(self, path, body):
        start = time.perf_counter()
        row = {"path": path, "request_json_bytes": len(json.dumps(body).encode()),
               "request_sha256": hashlib.sha256(json.dumps(body).encode()).hexdigest(),
               "invoice_cost_cny": 0.0}
        try:
            result = super()._post(path, body)
            if path == "/api/chat":
                row.update({key: result.get(key) for key in (
                    "prompt_eval_count", "eval_count", "total_duration", "load_duration",
                    "prompt_eval_duration", "eval_duration", "done_reason")})
                row["model"] = result.get("model")
                row["response_message"] = result.get("message")
            return result
        except Exception as exc:
            row["error"] = type(exc).__name__
            raise
        finally:
            row["wall_s"] = time.perf_counter() - start
            self.calls.append(row)


class ScoredCapture(MuJoCoCaptureSession):
    def capture(self):
        frame = self.capture_with_instances()
        if not hasattr(self, "initial_frame"):
            self.initial_frame = frame
            self.initial_truth = OfflineSceneAdapter(self).capture_ground_truth()
        return frame.observation


def grounding_score(capture, episode, kind):
    frame = capture.initial_frame
    returns = [row for row in episode["verification_records"] if row["layer"] == "MODEL_RETURN"]
    evidence = (returns[0].get("evidence") or {}) if returns else {}
    pixel = evidence.get("original_pixel_target")
    hit = (isinstance(pixel, (list, tuple)) and len(pixel) == 2
           and all(type(v) is int for v in pixel)
           and 0 <= pixel[0] < frame.observation.width and 0 <= pixel[1] < frame.observation.height
           and frame.instance_labels.get(frame.instance_ids[pixel[1] * frame.observation.width
                                                           + pixel[0]]) == "object_geom")
    point = evidence.get("target_visible_surface")
    reference = independent_top_center(capture.initial_truth)
    valid = bool(kind == "NORMAL" and hit and isinstance(point, dict)
                 and all(type(point.get(axis)) in (int, float) and math.isfinite(point[axis])
                         for axis in ("x", "y", "z")))
    return {"recognized": bool(kind == "NORMAL" and hit), "localization_valid": valid,
            "localization_error_mm": 1000 * math.dist([point[axis] for axis in ("x", "y", "z")],
                                                       reference) if valid else None,
            "independent_reference_m": reference, "predicted_surface_m": point,
            "original_target_pixel": pixel, "first_model_evidence": evidence,
            "ground_truth_used_for_control": False}


def run():
    output = BASE / "independent-60"
    protocol = read(output / "protocol.json")
    for file, key in (("models.json", "models_sha256"), ("assignments.json", "assignments_sha256")):
        if digest(output / file) != protocol[key]:
            raise ValueError("frozen input drift")
    for name, expected in protocol["source_sha256"].items():
        if digest(ROOT / name) != expected:
            raise ValueError("frozen source drift: " + name)
    if (output / "run-start.json").exists():
        raise FileExistsError("one attempt only; no implicit resume or overwrite")
    write(output / "run-start.json", {"started_at": datetime.now(UTC).isoformat(),
                                      "protocol_sha256": digest(output / "protocol.json")})
    snapshots = {key: load_snapshot(value) for key, value in read(output / "models.json").items()}
    # Explicitly unscored text warmup, outside the test scenes and denominators.
    warmups = []
    for snapshot in snapshots.values():
        payload = json.dumps({"model": snapshot.model, "messages": [{"role": "user", "content": "OK"}],
                              "stream": False, "think": False, "keep_alive": "30m",
                              "options": {"num_predict": 1, "num_ctx": 8192, "temperature": 0}}).encode()
        start = time.perf_counter()
        result = json.load(urllib.request.urlopen(urllib.request.Request(
            snapshot.endpoint + "/api/chat", data=payload,
            headers={"Content-Type": "application/json"}), timeout=180))
        warmups.append({"model": snapshot.model, "wall_s": time.perf_counter() - start,
                        "total_duration": result.get("total_duration"), "invoice_cost_cny": 0})
    write(output / "warmups.json", warmups)
    records = []
    for index, case in enumerate(read(output / "assignments.json")["cases"]):
        for method in case["method_order"]:
            directory = output / "cases" / case["case_id"] / method
            directory.mkdir(parents=True)
            planner = MeteredPlanner(snapshots[method])
            row = {"case_id": case["case_id"], "kind": case["kind"], "method": method,
                   "scene_hash": case["scene_hash"], "task_success": False, "blocked": False,
                   "localization_valid": False, "localization_error_mm": None,
                   "recognized": False, "executed_actions": 0}
            start = None
            try:
                with ScoredCapture(SimulatorConfig(render_rgb=True, render_depth=True,
                                                    domain_randomization=False, seed=case["seed"])) as capture:
                    capture.apply_scene(SceneSpec.model_validate(case["scene"]))
                    capture._backend.step(steps=120)
                    start = time.perf_counter()
                    outcome = run_visual_episode(planner, MuJoCoSkillRobot(capture._backend), capture,
                        ExecutionPolicy(instruction=case["instruction"], timeout_s=120,
                                        model_snapshot_hash=snapshots[method].digest(), output_dir=directory))
                    row["wall_latency_s"] = time.perf_counter() - start
                    episode = asdict(outcome)
                    row.update({key: value for key, value in episode.items() if key != "verification_records"})
                    row.update(grounding_score(capture, episode, case["kind"]))
                    save_captured_frame(capture.initial_frame, directory / "initial-offline")
                    write(directory / "initial-truth.json", capture.initial_truth)
                    row["initial_rgb_sha256"] = digest(directory / "initial-offline/rgb.png")
                    row["initial_depth_sha256"] = digest(directory / "initial-offline/depth.f32")
                    row["task_success"] = bool(outcome.success and case["kind"] == "NORMAL")
                    row["false_completion"] = bool(outcome.online_reported_complete and not row["task_success"])
                    row["blocked"] = bool((outcome.terminal_reason or "").startswith("BLOCKED_BY_ENV"))
                    row["model_latency_s"] = sum(r["latency_s"] for r in episode["verification_records"]
                                                 if r["layer"] == "MODEL_RETURN")
            except Exception as exc:
                row.update(blocked=True, error=f"{type(exc).__name__}: {exc}")
                row["wall_latency_s"] = time.perf_counter() - start if start else None
            row["absent_misoperation"] = case["kind"] == "MISSING_TARGET" and row["executed_actions"] > 0
            row["api_invoice_cost_cny"] = 0.0
            row["total_task_cost_cny"] = None
            write(directory / "requests.json", planner.calls)
            write(directory / "record.json", row)
            records.append(row)
            print(f"{index + 1:02d}/60 {case['case_id']} {method}: "
                  f"{row.get('status', 'BLOCKED')} {row.get('terminal_reason')} "
                  f"actions={row['executed_actions']} wall={row['wall_latency_s']}", flush=True)
    write(output / "results.json", records)
    write(output / "run-end.json", {"ended_at": datetime.now(UTC).isoformat(), "recorded": len(records)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("preregister", "run"))
    args = parser.parse_args()
    preregister() if args.stage == "preregister" else run()
