"""Repeated paired runs must remain separate observations in exported statistics."""

from __future__ import annotations

import json
from pathlib import Path

from cloud_edge_robot_arm.final_evaluation.aggregation import write_aggregate
from cloud_edge_robot_arm.final_evaluation.models import Phase12Profile


def test_failed_repetition_is_not_hidden_by_first_successful_pair(tmp_path: Path) -> None:
    rows = [
        _row("MUJOCO", 0, "SUCCESS", 100.0),
        _row("ISAAC_SIM", 0, "SUCCESS", 90.0),
        _row("MUJOCO", 1, "SAFETY_STOPPED", 140.0),
        _row("ISAAC_SIM", 1, "SUCCESS", 110.0),
        _row("MUJOCO", 2, "SUCCESS", 150.0),
        _row("ISAAC_SIM", 2, "SUCCESS", 120.0),
    ]
    _write_rows(tmp_path, rows)

    paired = write_aggregate(tmp_path, Phase12Profile.FULL)["paired"]

    assert paired["pair_count"] == 3
    assert paired["usable_pair_count"] == 2
    assert paired["failed_pair_count"] == 1
    assert paired["mean_delta"] == 20.0
    assert paired["paired_backend_experiment_accepted"] is False


def test_missing_repetition_partner_is_not_borrowed_from_another_run(tmp_path: Path) -> None:
    rows = [
        _row("ISAAC_SIM", 1, "SUCCESS", 80.0),
        _row("MUJOCO", 0, "SUCCESS", 100.0),
    ]
    _write_rows(tmp_path, rows)

    paired = write_aggregate(tmp_path, Phase12Profile.FULL)["paired"]

    assert paired["pair_count"] == 2
    assert paired["usable_pair_count"] == 0
    assert paired["paired_row_structure_complete"] is False
    assert paired["paired_backend_experiment_accepted"] is False


def _row(backend: str, repetition: int, status: str, duration: float) -> dict[str, object]:
    return {
        "experiment_id": "F15_MUJOCO_ISAAC_PAIRED",
        "scenario_id": "S01_NORMAL_STATIC",
        "seed": 17,
        "control_mode": "PCSC",
        "repetition": repetition,
        "backend": backend,
        "status": status,
        "runtime_completed": True,
        "authoritative_for_thesis": True,
        "total_completion_time_ms": duration,
    }


def _write_rows(root: Path, rows: list[dict[str, object]]) -> None:
    (root / "runs").mkdir()
    (root / "runs/raw_runs.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
