"""Capture a shared, unscored development bank before accessing candidate models."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SOURCE = BASE / "source-snapshot"
sys.path[:0] = [str(SOURCE), str(SOURCE / "src")]
os.chdir(SOURCE)
os.environ.setdefault("MUJOCO_GL", "egl")

from scripts import evaluate_rgbd_model_scenes as scene_eval  # noqa: E402
from cloud_edge_robot_arm.datasets.rgbd.capture import OfflineSceneAdapter  # noqa: E402
from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import sample_scene  # noqa: E402
from cloud_edge_robot_arm.simulation.config import SimulatorConfig  # noqa: E402
from cloud_edge_robot_arm.vision.capture import (  # noqa: E402
    MuJoCoCaptureSession,
    save_captured_frame,
)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)


def main():
    output = BASE / "shared/scene-bank"
    if output.exists():
        raise FileExistsError("refusing to overwrite the shared bank")
    assignments = scene_eval.build_assignments(seed_start=519001)
    cases = [
        {"case_id": f"fixed-s01-{i + 1}", "kind": "FIXED_S01", "seed": 0,
         "instruction": "把图中的红色方块放到绿色方形目标区域。"}
        for i in range(4)
    ] + assignments["cases"]
    write(output / "assignments.json", {**assignments, "cases": cases})
    config = scene_eval.nominal_dataset_config()
    records = []
    for case in cases:
        directory = output / "cases" / case["case_id"]
        scene = None if case["kind"] == "FIXED_S01" else sample_scene(config, case["seed"])
        if scene is not None:
            write(directory / "scene.json", scene.model_dump(mode="json"))
        with MuJoCoCaptureSession(SimulatorConfig(
            render_rgb=True, render_depth=True, domain_randomization=False,
            seed=case["seed"], camera_width=320, camera_height=240,
        )) as capture:
            if scene is not None:
                capture.apply_scene(scene)
                capture._backend.step(steps=config.settle_steps)
            frame = capture.capture_with_instances()
            save_captured_frame(frame, directory / "initial-offline")
            write(directory / "observation-transport.json",
                  frame.observation.model_dump(mode="json"))
            write(directory / "frame-binding.json", {
                "physics_state_hash": frame.physics_state_hash,
                "pass_state_hashes": frame.pass_state_hashes,
                "synchronized": len(set(frame.pass_state_hashes)) == 1,
            })
            # Oracle object geometry is an offline scoring sidecar only.
            if scene is not None:
                truth = OfflineSceneAdapter(capture).capture_ground_truth()
            else:
                model, data = capture._backend._model, capture._backend._data
                truth = {"instances": [{
                    "role": role, "position": data.geom_xpos[model.geom(name).id].tolist(),
                    "half_size": model.geom(name).size.tolist(),
                } for role, name in [("target", "object_geom"),
                                     ("destination", "target_region_geom")]],
                    "source": "offline fixed-scene geom positions, never sent to model"}
            write(directory / "initial-truth.json", truth)
            records.append({
                **case, **frame.observation.evidence(),
                "scene_sha256": scene.scene_hash if scene else None,
            })
        print("CAPTURED", case["case_id"], flush=True)
    write(output / "bank-manifest.json", {
        "created_at": datetime.now(UTC).isoformat(), "held_out_test": False,
        "source_snapshot_manifest_sha256": hashlib.sha256(
            (BASE / "source-snapshot-manifest.json").read_bytes()).hexdigest(),
        "cases": records,
        "files": {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(output.rglob("*")) if p.is_file()},
        "policy": "Identical prerecorded synchronized images for model-only screening; "
                  "no physical actions, no fresh-frame closed-loop or G1 claim.",
    })
    print("BANK_COMPLETE", len(records))


if __name__ == "__main__":
    main()
