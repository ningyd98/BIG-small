from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


class Phase9ArtifactCollector:
    REQUIRED_FILES = {
        "run_manifest.json",
        "environment.json",
        "config.json",
        "randomization.json",
        "events.jsonl",
        "raw_runs.jsonl",
        "summary.csv",
        "summary.json",
        "result_hashes.txt",
        "report.md",
        "joint_trajectory.csv",
        "tcp_trajectory.csv",
        "contacts.jsonl",
        "sensor_timing.csv",
        "safety_decisions.jsonl",
        "fault_timeline.jsonl",
    }

    def __init__(self, artifact_dir: Path) -> None:
        self._artifact_dir = artifact_dir
        self._artifact_dir.mkdir(parents=True, exist_ok=True)

    def write_minimal_run(
        self,
        *,
        run_id: str,
        backend: str,
        scenario: str,
        seed: int,
        metrics: dict[str, Any],
    ) -> None:
        manifest = {
            "run_id": run_id,
            "backend": backend,
            "backend_version": "phase9.local",
            "scenario": scenario,
            "seed": seed,
            "environment_level": "CORE_READY",
            "result_hash": self._hashable(metrics),
        }
        self._write_json("run_manifest.json", manifest)
        self._write_json("environment.json", {"environment_level": "CORE_READY"})
        self._write_json("config.json", {"backend": backend, "scenario": scenario, "seed": seed})
        self._write_json("randomization.json", {"level": "NONE", "seed": seed})
        self._append_jsonl("events.jsonl", {"event_type": "run_started", "run_id": run_id})
        self._append_jsonl("raw_runs.jsonl", {"run_id": run_id, "metrics": metrics})
        self._write_json("summary.json", {"run_count": 1, "metrics": metrics})
        (self._artifact_dir / "result_hashes.txt").write_text(
            f"{run_id} {manifest['result_hash']}\n", encoding="utf-8"
        )
        (self._artifact_dir / "report.md").write_text(
            f"# Phase 9 Run Report\n\nBackend: {backend}\nScenario: {scenario}\n",
            encoding="utf-8",
        )
        self._write_csv("summary.csv", [{"run_id": run_id, **metrics}])
        self._write_csv("joint_trajectory.csv", [{"sim_time_s": 0, "joint1": 0}])
        self._write_csv("tcp_trajectory.csv", [{"sim_time_s": 0, "x": 0, "y": 0, "z": 0}])
        self._append_jsonl("contacts.jsonl", {"contacts": []})
        self._write_csv("sensor_timing.csv", [{"sim_time_s": 0, "latency_ms": 0}])
        self._append_jsonl("safety_decisions.jsonl", {"decision": "ALLOW"})
        self._append_jsonl("fault_timeline.jsonl", {"faults": []})

    def _write_json(self, name: str, payload: dict[str, Any]) -> None:
        (self._artifact_dir / name).write_text(
            json.dumps(payload, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    def _append_jsonl(self, name: str, payload: dict[str, Any]) -> None:
        with (self._artifact_dir / name).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def _write_csv(self, name: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            (self._artifact_dir / name).write_text("", encoding="utf-8")
            return
        with (self._artifact_dir / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _hashable(payload: dict[str, Any]) -> str:
        import hashlib

        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
