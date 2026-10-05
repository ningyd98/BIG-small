"""Fixed candidate screening and new paired holdout using unchanged online execution."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
import urllib.request
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from scripts import run_rgbd_smoke as smoke

from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec
from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import sample_scene
from cloud_edge_robot_arm.edge.recovery.verification_router import VerificationBudget
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.vision.capture import save_captured_frame
from cloud_edge_robot_arm.vision.evaluation import ExecutionPolicy
from cloud_edge_robot_arm.vision.execution import run_visual_episode
from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot
from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter

HERE = Path(__file__).parent
OLD = HERE.parent / "20261004-t7-retest-comparison"
spec = importlib.util.spec_from_file_location("previous_comparison", OLD / "compare.py")
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
METHODS = ("qwen8", "qwen4")


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("x") as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)


def post(endpoint, path, body):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(
        urllib.request.Request(
            endpoint + path,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        ),
        timeout=180,
    ) as r:
        return json.load(r)


def sources():
    files = [
        *sorted((ROOT / "src/cloud_edge_robot_arm").rglob("*.py")),
        ROOT / "assets/robots/franka_panda/scene.xml",
        Path(__file__),
        OLD / "compare.py",
        OLD / "analyze.py",
        HERE / "internvl_bridge.py",
        HERE / "internvl_screen.py",
        HERE / "candidate_analyze.py",
        HERE / "internvl8-runtime.json",
        HERE / "internvl8-download-protocol.json",
    ]
    return {str(p.relative_to(ROOT)): sha(p) for p in files}


def snapshot(method):
    file = {
        "internvl8": HERE / "internvl8-normalized.json",
        "qwen8": HERE / "qwen8-probe/model-frozen.json",
        "qwen4": HERE.parent / "20261003-t7-visual-closed-loop/model-probe/model-frozen.json",
    }[method]
    return ModelConfigSnapshot(**read(file))


class Metered(RGBDPlannerAdapter):
    def __init__(self, snapshot):
        if (
            snapshot.provider == "openai_compatible"
            and snapshot.endpoint != "http://127.0.0.1:11436"
        ):
            raise ValueError("nonlocal compatible endpoint forbidden")
        super().__init__(
            base_url=snapshot.endpoint,
            model=snapshot.model,
            provider=snapshot.provider,
            model_snapshot=snapshot,
            timeout_s=snapshot.timeout_s,
            allow_paid=snapshot.provider == "openai_compatible",
        )
        self.calls = []

    def _post(self, path, body):
        start = time.perf_counter()
        row = {"path": path, "request": body, "invoice_cost_cny": 0}
        try:
            response = super()._post(path, body)
            row["response"] = response
            if path == "/api/chat":
                row.update(
                    {
                        k: response.get(k)
                        for k in (
                            "prompt_eval_count",
                            "eval_count",
                            "total_duration",
                            "load_duration",
                            "prompt_eval_duration",
                            "eval_duration",
                        )
                    }
                )
            elif path == "/chat/completions":
                row.update(
                    prompt_eval_count=response["usage"]["prompt_tokens"],
                    eval_count=response["usage"]["completion_tokens"],
                    total_duration=int(response["native_inference_wall_s"] * 1e9),
                    load_duration=0,
                    prompt_eval_duration=None,
                    eval_duration=None,
                )
            return response
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {e}"
            raise
        finally:
            row["wall_s"] = time.perf_counter() - start
            self.calls.append(row)


def run_cases(output, assignments, snap, *, development=False):
    records = []
    for index, case in enumerate(assignments["cases"]):
        directory = output / "cases" / case["case_id"]
        directory.mkdir(parents=True)
        write(directory / "assignment.json", case)
        planner = Metered(snap)
        row = {
            "case_id": case["case_id"],
            "kind": case["kind"],
            "method": next(
                m for m in ("internvl8", "qwen8", "qwen4") if snapshot(m).model == snap.model
            ),
            "scene_hash": case["scene_hash"],
            "task_success": False,
            "blocked": False,
            "localization_valid": False,
            "localization_error_mm": None,
            "recognized": False,
            "executed_actions": 0,
            "false_completion": False,
            "model_latency_s": 0,
        }
        start = None
        try:
            factory = smoke._FaultCapture if development else old.ScoredCapture
            with factory(
                SimulatorConfig(
                    render_rgb=True,
                    render_depth=True,
                    domain_randomization=False,
                    seed=case["seed"],
                )
            ) as capture:
                capture.apply_scene(SceneSpec.model_validate(case["scene"]))
                capture._backend.step(steps=120)
                if development:
                    capture.fault = case["kind"] == "INVALID_DEPTH"
                    capture.raw_output = directory / "raw-fault-frames"
                    if case["kind"] == "SAFETY_STOP":
                        capture._backend.emergency_stop()
                start = time.perf_counter()
                outcome = run_visual_episode(
                    planner,
                    MuJoCoSkillRobot(capture._backend),
                    capture,
                    ExecutionPolicy(
                        instruction=case["instruction"],
                        timeout_s=120,
                        model_snapshot_hash=snap.digest(),
                        output_dir=directory,
                        verification_budget=VerificationBudget(
                            max_reobservations=2, max_retries=0, max_no_progress=3, deadline_s=120
                        ),
                    ),
                )
                row["wall_latency_s"] = time.perf_counter() - start
                episode = asdict(outcome)
                row.update({k: v for k, v in episode.items() if k != "verification_records"})
                if not development:
                    row.update(old.grounding_score(capture, episode, case["kind"]))
                    save_captured_frame(capture.initial_frame, directory / "initial-offline")
                    write(directory / "initial-truth.json", capture.initial_truth)
                    row["initial_rgb_sha256"] = sha(directory / "initial-offline/rgb.png")
                    row["initial_depth_sha256"] = sha(directory / "initial-offline/depth.f32")
                row["task_success"] = bool(outcome.success and case["kind"] != "MISSING_TARGET")
                row["false_completion"] = bool(
                    outcome.online_reported_complete and not row["task_success"]
                )
                row["blocked"] = bool((outcome.terminal_reason or "").startswith("BLOCKED_BY_ENV"))
                row["model_latency_s"] = sum(
                    r["latency_s"]
                    for r in episode["verification_records"]
                    if r["layer"] == "MODEL_RETURN"
                )
        except Exception as e:
            row.update(
                blocked=True,
                error=f"{type(e).__name__}: {e}",
                wall_latency_s=time.perf_counter() - start if start else None,
            )
        row["absent_misoperation"] = (
            case["kind"] == "MISSING_TARGET" and row["executed_actions"] > 0
        )
        row["api_invoice_cost_cny"] = 0
        row["total_task_cost_cny"] = None
        write(directory / "requests.json", planner.calls)
        write(directory / "record.json", row)
        records.append(row)
        print(
            f"{index + 1}/{len(assignments['cases'])} {row['method']} {case['case_id']}: "
            f"{row.get('status')} {row.get('terminal_reason')} "
            f"actions={row['executed_actions']} wall={row['wall_latency_s']}",
            flush=True,
        )
    write(output / "results.json", records)
    return records


def development():
    gate = read(HERE / "internvl8-scene-screen/fixed-summary.json")
    if not gate["passed"]:
        write(
            HERE / "internvl8-closed20-not-run.json",
            {
                "run": False,
                "reason": "fixed S01 target/destination geometric and contract gate failed",
                "performance_measured": False,
                "formal_g1": False,
            },
        )
        print("NOT_RUN: InternVL fixed geometric/contract gate failed", flush=True)
        return
    output = HERE / "internvl8-closed20"
    settings = yaml.safe_load((ROOT / "configs/research/visual_smoke.yaml").read_text())
    assignments = smoke.build_assignments(settings)
    write(output / "assignments.json", assignments)
    snap = snapshot("internvl8")
    write(
        output / "provenance.json",
        {
            "snapshot": {**snap.evidence(), "endpoint": snap.endpoint},
            "source_sha256": sources(),
            "settings": settings,
            "formal_g1": False,
            "accepted_T5_bundle": False,
            "purpose": "native candidate development screening only",
        },
    )
    records = run_cases(output, assignments, snap, development=True)
    write(
        output / "summary.json",
        {
            "assigned": 20,
            "normal_success": sum(r["task_success"] for r in records if r["kind"] == "NORMAL"),
            "normal_count": 12,
            "missing_misoperation": sum(r["absent_misoperation"] for r in records),
            "missing_count": 4,
            "blocked": sum(r["blocked"] for r in records),
            "false_completions": sum(r["false_completion"] for r in records),
            "formal_g1": False,
        },
    )


def preregister():
    output = HERE / "independent-60"
    if output.exists():
        raise FileExistsError(output)
    historical = old.historical_sources()
    previous = []
    for p in historical:
        previous.extend(old.scene_entries(read(p)))
    seeds = {r["seed"] for r in previous}
    geometry = {old.canonical(r["scene_parameters"]) for r in previous}
    config = smoke.smoke_dataset_config().model_copy(
        update={"dataset_id": "t7-larger-vlm-independent-20261004-v1", "groups": 60, "seed": 902001}
    )
    cases = []
    for i in range(60):
        scene = sample_scene(config, 902001 + i)
        if scene.seed in seeds or old.canonical(scene.scene_parameters) in geometry:
            raise ValueError("historical overlap")
        kind = "NORMAL" if i < 40 else "MISSING_TARGET"
        color = scene.scene_parameters["target"]["color_name"] if kind == "NORMAL" else "purple"
        cases.append(
            {
                "case_id": f"holdout-{i + 1:02d}",
                "kind": kind,
                "seed": scene.seed,
                "scene": scene.model_dump(mode="json"),
                "scene_hash": scene.scene_hash,
                "instruction": f"Move the {color} block to the green region.",
            }
        )
    order = np.random.default_rng(2026100402).permutation(60)
    cases = [cases[i] for i in order]
    write(
        output / "assignments.json",
        {
            "assigned_scenes": 60,
            "assigned_runs": 120,
            "counts": {"NORMAL": 40, "MISSING_TARGET": 20},
            "cases": cases,
            "config": config.model_dump(mode="json"),
        },
    )
    write(
        output / "models.json",
        {m: {**snapshot(m).evidence(), "endpoint": snapshot(m).endpoint} for m in METHODS},
    )
    protocol = {
        **read(OLD / "independent-60/protocol.json"),
        "created_at": datetime.now(UTC).isoformat(),
        "purpose": (
            "fresh paired comparison: original4B and Qwen3VL8B Q8_0; "
            "InternVL and Llama excluded at pre-holdout entry gates; exploratory, not G1"
        ),
        "policy": (
            "all 120 retained, one attempt per assignment/method; no tuning, "
            "retries, exclusions or sample changes"
        ),
        "execution_order": list(METHODS),
        "scheduling": (
            "serial model blocks to exclude switch reloads; same randomized scene order; "
            "startup/warmup "
            "excluded; block time/thermal confounding disclosed"
        ),
        "models_sha256": sha(output / "models.json"),
        "assignments_sha256": sha(output / "assignments.json"),
        "historical_scene_records": len(previous),
        "historical_source_sha256": {str(p.relative_to(ROOT)): sha(p) for p in historical},
        "source_sha256": sources(),
        "selection": (
            "development scenes separate; all settings fixed before this holdout; "
            "inadequate candidates still measured, no selection from test"
        ),
        "provider_difference": (
            "both measured methods Ollama0.35.1 schema-constrained GGUF, same prompt, parser "
            "and image processor; size and quantization differ; rejected InternVL not measured"
        ),
        "excluded_before_holdout": {
            "internvl8": (
                "S01 four target/destination misses plus development output contract failure"
            ),
            "llama11": "runtime architecture and same-message dual-image compatibility blocked",
        },
        "selection_gate": (
            "accepted fixed S01 bundle for comparable closed-loop planning; "
            "quality can remain inadequate, retained as failure"
        ),
        "candidate_protocol_amendment_sha256": sha(HERE / "candidate-protocol-amendment-json.json"),
        "selection_amendment_sha256": sha(HERE / "candidate-protocol-amendment-selection.json"),
    }
    write(output / "protocol.json", protocol)
    print("PREREGISTERED", sha(output / "protocol.json"), len(previous), flush=True)


def run(method):
    output = HERE / "independent-60"
    protocol = read(output / "protocol.json")
    for key in ["source_sha256", "historical_source_sha256"]:
        for p, expected in protocol[key].items():
            if sha(ROOT / p) != expected:
                raise ValueError("source drift: " + p)
    for name in ["models", "assignments"]:
        if sha(output / (name + ".json")) != protocol[name + "_sha256"]:
            raise ValueError("input drift")
    snap = ModelConfigSnapshot(
        **{k: v for k, v in read(output / "models.json")[method].items() if k != "endpoint_hash"}
    )
    target = output / method
    write(
        target / "run-start.json",
        {
            "started_at": datetime.now(UTC).isoformat(),
            "protocol_sha256": sha(output / "protocol.json"),
        },
    )
    if snap.provider == "ollama":
        tags = json.load(urllib.request.urlopen(snap.endpoint + "/api/tags"))["models"]
        for tag in tags:
            post(snap.endpoint, "/api/generate", {"model": tag["name"], "keep_alive": 0})
        start = time.perf_counter()
        response = post(
            snap.endpoint,
            "/api/chat",
            {
                "model": snap.model,
                "messages": [{"role": "user", "content": "OK"}],
                "stream": False,
                "think": False,
                "keep_alive": "30m",
                "options": {"num_ctx": 8192, "num_predict": 1, "temperature": 0},
            },
        )
        write(
            target / "warmup.json",
            {"wall_s": time.perf_counter() - start, "response": response, "scored": False},
        )
    else:
        health = json.load(urllib.request.urlopen(snap.endpoint + "/health"))
        if health["weight_digest"] != snap.weight_digest:
            raise ValueError("native identity drift")
    records = run_cases(target, read(output / "assignments.json"), snap)
    write(
        target / "run-end.json",
        {"ended_at": datetime.now(UTC).isoformat(), "retained": len(records)},
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("stage", choices=["development", "preregister", "run"])
    p.add_argument("--method", choices=METHODS)
    a = p.parse_args()
    if a.stage == "development":
        development()
    elif a.stage == "preregister":
        preregister()
    else:
        run(a.method)
