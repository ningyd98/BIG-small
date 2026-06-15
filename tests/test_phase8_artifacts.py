from __future__ import annotations

import csv
import json
from pathlib import Path

from cloud_edge_robot_arm.experiments.batch_runner import run_suite


def test_smoke_suite_writes_parseable_artifacts(tmp_path: Path) -> None:
    summary = run_suite("smoke", output_dir=tmp_path, seeds=[0], network_names=["NORMAL"])

    manifest = tmp_path / "run_manifest.json"
    raw_runs = tmp_path / "raw_runs.jsonl"
    events = tmp_path / "events.jsonl"
    summary_csv = tmp_path / "summary.csv"
    summary_json = tmp_path / "summary.json"
    report = tmp_path / "report.md"

    for path in (manifest, raw_runs, events, summary_csv, summary_json, report):
        assert path.exists(), path

    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_payload["git_sha"]
    assert manifest_payload["experiment_schema_version"] == "phase8.v1"

    raw_lines = raw_runs.read_text(encoding="utf-8").strip().splitlines()
    assert raw_lines
    assert all(json.loads(line)["config_hash"] for line in raw_lines)

    with summary_csv.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames is not None
        assert "task_success" in reader.fieldnames
        assert list(reader)

    summary_payload = json.loads(summary_json.read_text(encoding="utf-8"))
    assert summary_payload["run_count"] == summary.run_count
    assert "Mock/仿真实验" in report.read_text(encoding="utf-8")
