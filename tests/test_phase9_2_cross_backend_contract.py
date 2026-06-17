from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from cloud_edge_robot_arm.simulation.phase9_2.verification import (
    PHASE9_2_REQUIRED_METRICS,
    Phase92RuntimeConfig,
    phase9_2_status,
    run_phase9_2_paired_experiments,
    verify_cross_backend_artifacts,
    verify_phase9_2_acceptance,
)


def test_cross_backend_rejects_backend_identity_mismatch(tmp_path: Path) -> None:
    _write_runs(
        tmp_path, [_run("mujoco", "S01_NORMAL_STATIC", 0)], [_run("mujoco", "S01_NORMAL_STATIC", 0)]
    )

    result = verify_cross_backend_artifacts(tmp_path)

    assert result["status"] == "REJECTED"
    blockers = cast(list[str], result["blockers"])
    assert "Isaac artifact backend identity mismatch" in blockers


def test_cross_backend_rejects_scenario_seed_pairing_mismatch(tmp_path: Path) -> None:
    _write_runs(
        tmp_path, [_run("mujoco", "S01_NORMAL_STATIC", 0)], [_run("isaac", "S14_EMERGENCY_STOP", 0)]
    )

    result = verify_cross_backend_artifacts(tmp_path)

    assert result["status"] == "REJECTED"
    blockers = cast(list[str], result["blockers"])
    assert "scenario/seed pairing mismatch" in blockers


def test_cross_backend_rejects_static_result_hashes(tmp_path: Path) -> None:
    mujoco = [_run("mujoco", "S01_NORMAL_STATIC", seed, result_hash="same") for seed in range(2)]
    isaac = [_run("isaac", "S01_NORMAL_STATIC", seed, result_hash="same") for seed in range(2)]
    _write_runs(tmp_path, mujoco, isaac)

    result = verify_cross_backend_artifacts(tmp_path)

    assert result["status"] == "REJECTED"
    blockers = cast(list[str], result["blockers"])
    assert "result hashes are static" in blockers


def test_cross_backend_validates_metric_complete_paired_runs(tmp_path: Path) -> None:
    mujoco = [_run("mujoco", "S01_NORMAL_STATIC", seed) for seed in range(2)]
    isaac = [_run("isaac", "S01_NORMAL_STATIC", seed) for seed in range(2)]
    _write_runs(tmp_path, mujoco, isaac)

    result = verify_cross_backend_artifacts(tmp_path)

    assert result["status"] == "CROSS_BACKEND_VALIDATED"
    assert result["validation_claimed"] is True
    assert result["artifact_provenance_complete"] is True
    metric_deltas = cast(dict[str, object], result["metric_deltas"])
    assert set(PHASE9_2_REQUIRED_METRICS).issubset(metric_deltas)
    assert (tmp_path / "paired_runs.jsonl").exists()
    assert (tmp_path / "metric_deltas.json").exists()
    assert (tmp_path / "statistical_summary.json").exists()
    assert (tmp_path / "cross_backend_report.md").exists()
    assert (tmp_path / "reproducibility_manifest.json").exists()


def test_paired_experiment_preserves_isaac_failure_artifact(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from cloud_edge_robot_arm.simulation.evaluation import metrics

    monkeypatch.setattr(
        metrics,
        "run_mujoco_physical_trial",
        lambda scenario_id, *, seed: SimpleNamespace(
            metrics=_metrics(seed), result_hash=f"mujoco-{scenario_id}-{seed}"
        ),
    )

    def fail_isaac(_scenario_id: str, *, seed: int, process_argv: list[str]) -> object:
        raise RuntimeError(f"isaac failed seed={seed}; argv={process_argv[0]}")

    monkeypatch.setattr(metrics, "run_isaac_physical_trial", fail_isaac)
    config = Phase92RuntimeConfig(
        mode="standalone",
        repo_root=Path("."),
        output_dir=tmp_path,
        isaac_sim_root=tmp_path / "isaac",
    )

    result = run_phase9_2_paired_experiments(
        tmp_path, config=config, scenarios=("S01_NORMAL_STATIC",), seeds=(0,)
    )

    assert result["status"] == "REJECTED"
    rows = [
        json.loads(line)
        for line in (tmp_path / "isaac_runs.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["validation_claimed"] is False
    assert rows[0]["final_state"] == "FAILED"
    assert "isaac failed seed=0" in rows[0]["failure_reason"]


def test_phase9_2_status_requires_full_runtime_acceptance() -> None:
    summary = {
        "ros2_status": "ROS2_INTEGRATION_VALIDATED",
        "moveit_status": "MOVEIT_SAFETY_VALIDATED",
        "isaac_status": "ISAAC_SMOKE_VALIDATED",
        "isaac_benchmark_status": "PASSED",
        "cross_backend_status": "CROSS_BACKEND_VALIDATED",
        "phase9_1_status": "PHASE9_1_ACCEPTED",
        "safety_pressure_status": "PASSED",
        "artifact_provenance_complete": True,
    }

    assert phase9_2_status(summary) == "PHASE9_2_ACCEPTED"
    summary["cross_backend_status"] = "BLOCKED_BY_ENV"
    assert phase9_2_status(summary) == "PHASE9_2_REJECTED"


def test_phase9_2_acceptance_reads_component_artifacts(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    phase9_1 = artifact_root / "phase9_1"
    isaac = artifact_root / "phase9_2" / "isaac"
    benchmark = artifact_root / "phase9_2" / "isaac_benchmark"
    cross = artifact_root / "phase9_2" / "cross_backend"
    for path in (phase9_1, isaac, benchmark, cross):
        path.mkdir(parents=True, exist_ok=True)
    (phase9_1 / "phase9_1_summary.json").write_text(
        json.dumps(
            {
                "status": "PHASE9_1_ACCEPTED",
                "components": {
                    "ros2": {"status": "ROS2_INTEGRATION_VALIDATED"},
                    "moveit": {"status": "MOVEIT_SAFETY_VALIDATED"},
                },
                "isaac_benchmark_guard": {"benchmark_status": "PASSED"},
                "safety_pressure": {"status": "PASSED"},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (isaac / "isaac_verification.json").write_text(
        json.dumps(
            {
                "status": "ISAAC_SMOKE_VALIDATED",
                "validation_claimed": True,
                "artifact_provenance_complete": True,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (benchmark / "summary.json").write_text(
        json.dumps({"status": "PASSED", "validation_claimed": True}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (cross / "cross_backend_verification.json").write_text(
        json.dumps(
            {
                "status": "CROSS_BACKEND_VALIDATED",
                "validation_claimed": True,
                "artifact_provenance_complete": True,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = verify_phase9_2_acceptance(tmp_path / "final", artifacts_root=artifact_root)

    assert result["status"] == "PHASE9_2_ACCEPTED"
    assert result["phase9_1_status"] == "PHASE9_1_ACCEPTED"
    assert (tmp_path / "final" / "phase9_2_summary.json").exists()


def _write_runs(
    output_dir: Path, mujoco: list[dict[str, object]], isaac: list[dict[str, object]]
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in (("mujoco_runs.jsonl", mujoco), ("isaac_runs.jsonl", isaac)):
        (output_dir / name).write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )


def _run(
    backend: str,
    scenario_id: str,
    seed: int,
    *,
    result_hash: str | None = None,
) -> dict[str, object]:
    metrics: dict[str, object] = {name: float(seed + 1) for name in PHASE9_2_REQUIRED_METRICS}
    metrics["illegal_collision_count"] = 0
    metrics["emergency_stop_post_command_count"] = 0
    metrics["final_state"] = "SUCCESS"
    metrics["auto_mode_selection"] = "AUTO"
    return {
        "backend_name": backend,
        "run_id": f"{backend}-{scenario_id}-{seed}",
        "scenario_id": scenario_id,
        "seed": seed,
        "process_provenance": {"runtime": backend, "pid": 100 + seed},
        "environment_provenance": {"os": "ubuntu-24.04"},
        "config_hash": "config-a",
        "code_commit_sha": "commit-a",
        "result_hash": result_hash or f"{backend}-hash-{scenario_id}-{seed}",
        "validation_claimed": True,
        "metrics": metrics,
    }


def _metrics(seed: int) -> dict[str, object]:
    metrics: dict[str, object] = {name: float(seed + 1) for name in PHASE9_2_REQUIRED_METRICS}
    metrics["illegal_collision_count"] = 0
    metrics["emergency_stop_post_command_count"] = 0
    metrics["final_state"] = "SUCCESS"
    metrics["auto_mode_selection"] = "AUTO"
    return metrics
