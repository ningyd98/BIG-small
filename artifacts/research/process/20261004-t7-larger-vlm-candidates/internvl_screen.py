"""Real native-provider fixed probe and development screen, no Ollama freeze claim."""

from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from scripts import evaluate_rgbd_model_scenes as scene_eval
from scripts import probe_rgbd_model as probe

from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import sample_scene
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession, save_captured_frame
from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot
from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter

HERE = Path(__file__).parent


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)


def main():
    snapshot = ModelConfigSnapshot(**json.loads((HERE / "internvl8-normalized.json").read_text()))
    if snapshot.endpoint != "http://127.0.0.1:11436":
        raise ValueError("local endpoint changed")
    assignments = scene_eval.build_assignments(seed_start=439001)
    config = scene_eval.nominal_dataset_config()
    out = HERE / "internvl8-scene-screen"
    scene_eval.preregister(out, assignments)
    write(
        out / "provenance.json",
        {
            "candidate": {**snapshot.evidence(), "endpoint": snapshot.endpoint},
            "source_sha256": {
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in [
                    Path(__file__),
                    HERE / "internvl_bridge.py",
                    *sorted((ROOT / "src/cloud_edge_robot_arm/vision").glob("*.py")),
                ]
            },
            "held_out_test": False,
            "native_runtime": json.loads((HERE / "internvl8-runtime.json").read_text()),
            "created_at": datetime.now(UTC).isoformat(),
        },
    )
    records = []
    fixed_cases = [
        {
            "case_id": f"fixed-s01-{i + 1}",
            "kind": "FIXED_S01",
            "seed": 0,
            "instruction": "把图中的红色方块放到绿色方形目标区域。",
        }
        for i in range(4)
    ]
    write(
        out / "fixed-protocol.json",
        {
            "scenario": "S01_NORMAL_STATIC",
            "cases": fixed_cases,
            "first_inference": "warm; unscored startup and interface diagnostic measured separately",
            "warm_runs": 3,
        },
    )
    fixed_records = []
    for case in fixed_cases + assignments["cases"]:
        directory = out / "cases" / case["case_id"]
        directory.mkdir(parents=True)
        scene = sample_scene(config, case["seed"]) if case["kind"] != "FIXED_S01" else None
        if scene is not None:
            write(directory / "scene.json", scene.model_dump(mode="json"))
        with MuJoCoCaptureSession(
            SimulatorConfig(
                render_rgb=True, render_depth=True, domain_randomization=False, seed=case["seed"]
            )
        ) as capture:
            if scene is not None:
                capture.apply_scene(scene)
                capture._backend.step(steps=config.settle_steps)
            frame = capture.capture_with_instances()
            save_captured_frame(frame, directory / "initial-offline")
            evidence = frame.observation.evidence()
            capture_data = {
                **evidence,
                "synchronized": len(set(frame.pass_state_hashes)) == 1,
                "source": "mujoco_camera",
            }
            request = InitialPlanningRequest(
                request_id="internvl-native-development-screen",
                user_instruction=case["instruction"],
                observation=frame.observation,
                scene=SceneSummary(scene_version=1, updated_at=datetime.now(UTC)),
            )
            planner = RGBDPlannerAdapter(
                base_url=snapshot.endpoint,
                model=snapshot.model,
                provider=snapshot.provider,
                model_snapshot=snapshot,
                timeout_s=180,
                allow_paid=True,
            )
            calls = []
            original = planner._post

            def post(path, body, _original=original, _calls=calls):
                response = _original(path, body)
                _calls.append({"path": path, "request": body, "response": response})
                return response

            planner._post = post
            start = time.perf_counter()
            attempt = {
                "transport_two_images": False,
                "parsed": False,
                "grounded": False,
                "target_hit": False,
                "destination_hit": False,
            }
            try:
                draft = planner.plan(request)
                ev = draft.observation_evidence
                decision = ev.get("visual_decision", {})
                attempt.update(
                    observed_scene_present=draft.observed_scene is not None,
                    raw_model_output=draft.raw_text,
                    parse_error=draft.parse_error,
                    parsed=draft.parse_error is None and draft.observed_scene is not None,
                    grounded=draft.parse_error is None and draft.parsed_json is not None,
                    observation_evidence=ev,
                    visual_decision=decision,
                )
                for kind, label in [
                    ("target", "object_geom"),
                    ("destination", "target_region_geom"),
                ]:
                    hit, check = probe._pixel_hit(
                        frame,
                        probe._original_decision_pixel(planner, frame, ev, decision, kind),
                        label,
                    )
                    attempt[kind + "_hit"] = hit
                    attempt[kind + "_offline_check"] = check
                request_sent = calls[0]["request"]
                images = [
                    r["image_url"]["url"]
                    for r in request_sent["messages"][1]["content"]
                    if r.get("type") == "image_url"
                ]
                attempt["transport_two_images"] = len(images) == 2 and len(set(images)) == 2
            except Exception as e:
                attempt["error"] = str(e)
            attempt["wall_latency_s"] = time.perf_counter() - start
            write(directory / "attempt.json", attempt)
            write(directory / "requests.json", calls)
            record = {
                "case_id": case["case_id"],
                "kind": case["kind"],
                "scene_sha256": scene.scene_hash if scene is not None else None,
                "rgb_sha256": evidence["rgb_sha256"],
                "complete": not attempt.get("error"),
                "attempt": attempt,
                "capture": capture_data,
                "diagnostics": scene_eval.offline_diagnostics(frame, attempt),
            }
            record["passed"] = (
                scene_eval.case_passes(case, record)
                if scene is not None
                else all(
                    attempt.get(k) is True
                    for k in (
                        "transport_two_images",
                        "parsed",
                        "grounded",
                        "target_hit",
                        "destination_hit",
                    )
                )
                and scene_eval._calibrated_offset(attempt)
            )
            write(directory / "outcome.json", record)
            if scene is None:
                fixed_records.append(record)
            else:
                records.append(record)
            print(case["case_id"], record["passed"], attempt.get("parse_error"), flush=True)
    write(out / "fixed-results.json", fixed_records)
    write(
        out / "fixed-summary.json",
        {
            "passed": all(r["passed"] for r in fixed_records),
            "calls": 4,
            "latencies_s": [r["attempt"]["wall_latency_s"] for r in fixed_records],
            "formal_freeze": False,
        },
    )
    write(out / "results.json", records)
    summary = scene_eval.summarize_results(assignments, records)
    write(out / "summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
