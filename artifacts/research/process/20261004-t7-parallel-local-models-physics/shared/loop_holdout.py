"""Fresh paired closed-loop holdout, using immutable original-asset source.

Preregister only after the candidate configurations and bridges are frozen.
Failed and blocked assignments are retained; no tuning or retries in this test.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
import numpy as np

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[3]
SOURCE = BASE / "source-snapshot"
sys.path[:0] = [str(SOURCE), str(SOURCE / "src")]
os.chdir(SOURCE)
os.environ.setdefault("MUJOCO_GL", "egl")
from scripts.run_rgbd_smoke import smoke_dataset_config
from cloud_edge_robot_arm.datasets.rgbd.capture import OfflineSceneAdapter
from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec
from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import sample_scene
from cloud_edge_robot_arm.edge.recovery.verification_router import VerificationBudget
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession, save_captured_frame
from cloud_edge_robot_arm.vision.evaluation import ExecutionPolicy, independent_top_center
from cloud_edge_robot_arm.vision.execution import run_visual_episode
from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot
from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)


def scene_entries(value):
    if isinstance(value, dict):
        if "scene_parameters" in value and "seed" in value:
            yield value
        for child in value.values():
            yield from scene_entries(child)
    elif isinstance(value, list):
        for child in value:
            yield from scene_entries(child)


def canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


class ScoredCapture(MuJoCoCaptureSession):
    def capture(self):
        frame = self.capture_with_instances()
        if not hasattr(self, "initial_frame"):
            self.initial_frame = frame
            self.initial_truth = OfflineSceneAdapter(self).capture_ground_truth()
        return frame.observation


class MeteredPlanner(RGBDPlannerAdapter):
    def __init__(self, snapshot):
        if urlsplit(snapshot.endpoint).hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("loopback local models only")
        super().__init__(base_url=snapshot.endpoint, model=snapshot.model,
                         provider=snapshot.provider, timeout_s=snapshot.timeout_s,
                         model_snapshot=snapshot, allow_paid=snapshot.provider == "openai_compatible",
                         chat_path="/v1/chat/completions")
        self.calls = []

    def _post(self, path, body):
        row = {"path": path, "request": body, "invoice_cost_cny": 0}
        start = time.perf_counter()
        try:
            row["response"] = super()._post(path, body)
            return row["response"]
        except Exception as exc:
            row["error"] = repr(exc)
            raise
        finally:
            row["wall_s"] = time.perf_counter() - start
            self.calls.append(row)


def preregister(args):
    if args.output.exists():
        raise FileExistsError(args.output)
    selected = read(args.selected)
    if not selected:
        raise ValueError("no qualified models selected")
    for config in selected.values():
        ModelConfigSnapshot(**config)
    previous, sources = [], {}
    for tree in (ROOT / "datasets", ROOT / "artifacts/research"):
        for pattern in ("scene.json", "assignments.json", "manifest.json"):
            for path in sorted(tree.rglob(pattern)):
                previous.extend(scene_entries(read(path)))
                sources[str(path.relative_to(ROOT))] = sha(path)
    seeds = {row["seed"] for row in previous}
    geometry = {canonical(row["scene_parameters"]) for row in previous}
    config = smoke_dataset_config().model_copy(update={
        "dataset_id": "t7-parallel-independent-original-asset-v1", "groups": 60, "seed": 903001})
    cases = []
    for i in range(60):
        scene = sample_scene(config, 903001 + i)
        if scene.seed in seeds or canonical(scene.scene_parameters) in geometry:
            raise ValueError("historical scene overlap")
        kind = "NORMAL" if i < 40 else "MISSING_TARGET"
        color = scene.scene_parameters["target"]["color_name"] if i < 40 else "purple"
        cases.append({"case_id": f"holdout-{i+1:02d}", "kind": kind,
                      "seed": scene.seed, "scene": scene.model_dump(mode="json"),
                      "scene_hash": scene.scene_hash,
                      "instruction": f"Move the {color} block to the green region."})
    cases = [cases[i] for i in np.random.default_rng(2026100403).permutation(60)]
    write(args.output / "models.json", selected)
    write(args.output / "assignments.json", {"cases": cases, "counts": {"NORMAL":40,"MISSING_TARGET":20},
          "config": config.model_dump(mode="json"), "held_out_test":True})
    write(args.output / "protocol.json", {
        "created_at": datetime.now(UTC).isoformat(), "formal_G1":False,
        "models_sha256":sha(args.output / "models.json"),
        "assignments_sha256":sha(args.output / "assignments.json"),
        "harness_sha256":sha(Path(__file__)),
        "frozen_runtime_files": {str(Path(path).resolve()):sha(Path(path).resolve())
                                 for path in read(args.runtime_files)},
        "snapshot_sha256":read(BASE / "source-snapshot-manifest.json")["source_sha256"],
        "historical_sources":sources,"historical_scene_records":len(previous),
        "seed_overlap":0,"exact_geometry_overlap":0,
        "policy":"One attempt per method/assignment; no retries, tuning, exclusions or stopping after failure",
        "execution":"Serial model blocks, same randomized scene order; block-time thermal confounding disclosed",
        "online_policy":{"timeout_s":120,"max_reobservations":2,"max_retries":0,"max_no_progress":3},
        "misoperation":"At least one executed physical skill / all20 missing-target assignments",
        "success":"Online completion AND independent physical success, target present / all40 normal assignments",
        "localization":"First response, correct target geom hit and valid depth; conditional top-center P90 mm with coverage/40",
        "latency":"All60 terminal wall times including failures, initial capture through physical evaluation/evidence write; setup excluded",
        "cost":"Local provider API cost0 CNY; electricity/depreciation total unknown, user has no billing rate",
    })
    print("PREREGISTERED",sha(args.output / "protocol.json"),len(previous),flush=True)


def run(args):
    protocol = read(args.output / "protocol.json")
    for name in ("models", "assignments"):
        if sha(args.output / (name+".json")) != protocol[name+"_sha256"]:
            raise ValueError("frozen inputs changed")
    if sha(Path(__file__)) != protocol["harness_sha256"]:
        raise ValueError("harness drift")
    for path, expected in protocol["frozen_runtime_files"].items():
        if sha(Path(path)) != expected:
            raise ValueError("runtime drift: "+path)
    for path, expected in protocol["snapshot_sha256"].items():
        if sha(SOURCE / path) != expected:
            raise ValueError("snapshot drift: "+path)
    snapshot = ModelConfigSnapshot(**read(args.output / "models.json")[args.method])
    target = args.output / args.method
    write(target / "run-start.json",{"started_at":datetime.now(UTC).isoformat(),
          "protocol_sha256":sha(args.output / "protocol.json")})
    records=[]
    for case in read(args.output / "assignments.json")["cases"]:
        directory=target / "cases" / case["case_id"]
        write(directory / "assignment.json",case)
        planner=MeteredPlanner(snapshot)
        row={"case_id":case["case_id"],"kind":case["kind"],"method":args.method,
             "scene_hash":case["scene_hash"],"task_success":False,"blocked":False,
             "localization_valid":False,"localization_error_mm":None,"recognized":False,
             "executed_actions":0,"false_completion":False,"model_latency_s":0}
        start=None
        try:
            with ScoredCapture(SimulatorConfig(render_rgb=True,render_depth=True,
                 domain_randomization=False,seed=case["seed"],camera_width=320,camera_height=240)) as capture:
                capture.apply_scene(SceneSpec.model_validate(case["scene"]))
                capture._backend.step(steps=120)
                start=time.perf_counter()
                outcome=run_visual_episode(planner,MuJoCoSkillRobot(capture._backend),capture,
                    ExecutionPolicy(instruction=case["instruction"],timeout_s=120,
                        model_snapshot_hash=snapshot.digest(),output_dir=directory,
                        verification_budget=VerificationBudget(max_reobservations=2,max_retries=0,
                                                               max_no_progress=3,deadline_s=120)))
                row["wall_latency_s"]=time.perf_counter()-start
                episode=asdict(outcome)
                row.update({k:v for k,v in episode.items() if k!="verification_records"})
                frame=capture.initial_frame
                returns=[r for r in episode["verification_records"] if r["layer"]=="MODEL_RETURN"]
                evidence=(returns[0].get("evidence") or {}) if returns else {}
                pixel=evidence.get("original_pixel_target")
                hit=bool(isinstance(pixel,(list,tuple)) and len(pixel)==2
                    and all(type(v)is int for v in pixel)
                    and 0<=pixel[0]<320 and 0<=pixel[1]<240
                    and frame.instance_labels.get(frame.instance_ids[pixel[1]*320+pixel[0]])=="object_geom")
                point=evidence.get("target_visible_surface")
                valid=bool(case["kind"]=="NORMAL" and hit and isinstance(point,dict)
                    and all(type(point.get(a))in(int,float) and math.isfinite(point[a]) for a in("x","y","z")))
                reference=independent_top_center(capture.initial_truth)
                row.update(recognized=bool(hit and case["kind"]=="NORMAL"),localization_valid=valid,
                    localization_error_mm=1000*math.dist([point[a] for a in("x","y","z")],reference) if valid else None,
                    independent_reference_m=reference,ground_truth_used_for_control=False)
                save_captured_frame(frame,directory / "initial-offline")
                write(directory / "initial-truth.json",capture.initial_truth)
                row["initial_rgb_sha256"]=sha(directory / "initial-offline/rgb.png")
                row["initial_depth_sha256"]=sha(directory / "initial-offline/depth.f32")
                row["task_success"]=bool(outcome.success and case["kind"]=="NORMAL")
                row["false_completion"]=bool(outcome.online_reported_complete and not row["task_success"])
                row["blocked"]=bool((outcome.terminal_reason or "").startswith("BLOCKED_BY_ENV"))
                row["model_latency_s"]=sum(r["latency_s"] for r in episode["verification_records"] if r["layer"]=="MODEL_RETURN")
        except Exception as exc:
            row.update(blocked=True,error=repr(exc),wall_latency_s=time.perf_counter()-start if start else None)
        row["absent_misoperation"]=bool(case["kind"]=="MISSING_TARGET" and row["executed_actions"]>0)
        row.update(api_invoice_cost_cny=0,total_task_cost_cny=None)
        write(directory / "requests.json",planner.calls)
        write(directory / "record.json",row)
        records.append(row)
        print(case["case_id"],row.get("status"),row.get("terminal_reason"),row["executed_actions"],flush=True)
    write(target / "results.json",records)
    write(target / "run-end.json",{"ended_at":datetime.now(UTC).isoformat(),"retained":len(records)})


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("stage",choices=["preregister","run"])
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--selected",type=Path)
    parser.add_argument("--runtime-files",type=Path)
    parser.add_argument("--method")
    args=parser.parse_args()
    args.output=args.output.resolve()
    preregister(args) if args.stage=="preregister" else run(args)
