"""Assemble T6a acceptance from completed CLI artifacts, without inventing results."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from cloud_edge_robot_arm.datasets.rgbd.models import canonical_json
from cloud_edge_robot_arm.datasets.rgbd.writer import load_manifest, save_manifest

out = Path(__file__).resolve().parent
frozen = json.loads((out / "frozen-source-hashes.json").read_text())
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in frozen.items())
datasets = []
for label, expected in (("smoke", 100), ("validation", 1000)):
    root = Path(f"datasets/rgbd-{label}-20261003")
    manifest = load_manifest(root)
    assert manifest is not None and manifest.status == "COMPLETE"
    report = json.loads((out / f"{label}-validate.json").read_text())
    assert report["valid"] and not report["errors"] and not report["warnings"]
    assert report["group_count"] == report["sample_count"] == expected
    assert report["duplicate_count"] == 0
    assert manifest.completed_groups == manifest.sample_count == expected
    assert manifest.attempts <= expected * 5
    assert manifest.positive_count > 0 and manifest.negative_count > 0
    assert report["split_counts"] == {"train": expected * 80 // 100,
                                      "calibration": expected * 5 // 100,
                                      "selection": expected * 5 // 100,
                                      "test": expected * 10 // 100}
    resources = json.loads((out / f"{label}-resources.json").read_text())
    assert resources["exit_code"] == 0 and resources["peak_bytes"] > 0
    audit = json.loads((out / f"{label}-cli-audit.json").read_text())
    assert audit["replay_timestamp_preserved"] and audit["replay_rgb_and_depth_exact"]
    assert audit["train_examples"] == expected * 80 // 100
    source = manifest.source
    assert source["model_calls"] == 0 and source["evidence_kind"] == "REAL_CAPTURE"
    for name, digest in source["source_files"].items():
        assert hashlib.sha256((Path("src/cloud_edge_robot_arm") / name).read_bytes()).hexdigest() == digest
    records = [json.loads(line) for line in (root / "samples.jsonl").read_text().splitlines()]
    assert all(r["execution_verified"] is False for r in records)
    assert all(r["source"] == "mujoco_camera" for r in records)
    # Independent GPU measurements add manifest fields after CLI completion.
    # Reconcile the durable-byte measurement once these annotations are final.
    other = sum(p.stat().st_size for p in root.rglob("*") if p.is_file() and p.name != "manifest.json")
    manifest.resources["dataset_bytes_measurement"] = "final retained files including acceptance GPU annotations"
    for _ in range(10):
        size = other + len((canonical_json(manifest.model_dump(mode="json")) + "\n").encode())
        if manifest.resources["dataset_bytes"] == size:
            break
        manifest.resources["dataset_bytes"] = size
        manifest.resources["bytes_per_sample"] = size / expected
    save_manifest(root, manifest)
    actual_bytes = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
    assert actual_bytes == manifest.resources["dataset_bytes"] <= manifest.config.max_bytes
    datasets.append({"name": label, "path": str(root), "status": "COMPLETE",
                     "groups": expected, "attempts": manifest.attempts,
                     "positive_count": manifest.positive_count,
                     "negative_count": manifest.negative_count,
                     "split_counts": report["split_counts"], "duplicate_count": 0,
                     "total_bytes": actual_bytes, "bytes_per_group": actual_bytes / expected,
                     "generation_wall_time_s": manifest.resources["generation_wall_time_s"],
                     "cli_wall_time_s": resources["wall_time_s"],
                     "gpu_observed_peak_bytes": resources["peak_bytes"],
                     "gpu_measurement_limitation": resources["limitation"],
                     "source_hash": source["source_hash"], "content_hash": manifest.content_hash,
                     "raw_evidence_samples": sum("raw_depth" in r["paths"] for r in records),
                     "target_colors": dict(Counter(r["scene"]["scene_parameters"]["target"]["color_name"] for r in records)),
                     "distractor_counts": dict(Counter(str(len(r["scene"]["scene_parameters"]["distractors"])) for r in records)),
                     "validation": f"{label}-validate.json", "cli_audit": f"{label}-cli-audit.json",
                     "resources": f"{label}-resources.json"})
assert datasets[0]["source_hash"] == datasets[1]["source_hash"]
denial = json.loads((out / "test-export-denied.json").read_text())
assert denial["denied"] and not denial["output_created"] and denial["exit_code"] != 0
report = {"task": "T6a", "status": "DONE", "date": "2026-10-03",
          "scope": "static RGB-D dataset factory; real MuJoCo capture and offline labels",
          "datasets": datasets,
          "tests": {"dataset": {"passed": 124, "duration_s": 103.63,
                                  "log": "dataset-acceptance-tests.log"},
                    "regression": {"passed": 123, "warnings": 1, "duration_s": 51.35,
                                   "log": "regression-123.log"},
                    "complete_full_suite_passed": False},
          "ruff": {"status": "PASS", "log": "final-ruff.log"},
          "mypy": {"status": "PASS", "source_files": 18, "log": "final-mypy.log"},
          "review": {"status": "PASS", "report": "final-review.md",
                     "capture_review": "capture-review.md", "storage_review": "storage-review.md"},
          "source_hashes": "frozen-source-hashes.json", "snapshot": "source-snapshot/",
          "patch": "implementation.patch", "test_export_denied": True,
          "early_five_group_pilot": "integration evidence only; superseded before final schema freeze",
          "boundaries": ["T6b 10000 groups and teacher integration NOT_RUN",
                         "No VLM calls, model training, physical task-success acceptance or hardware actions",
                         "GPU figures are sampled observed per-process peaks, not continuous maxima",
                         "Single writer/render process; full repository suite not claimed passing"],
          "next_ready": ["T3", "T4"], "committed": False, "pushed": False}
(out / "acceptance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": report["status"], "datasets": datasets}, ensure_ascii=False, indent=2))
