from __future__ import annotations

from pathlib import Path

from scripts import verify_phase9

from cloud_edge_robot_arm.simulation.evaluation.collector import Phase9ArtifactCollector


def test_phase9_artifact_collector_writes_required_files(tmp_path: Path) -> None:
    collector = Phase9ArtifactCollector(tmp_path)
    collector.write_minimal_run(
        run_id="run-1",
        backend="mujoco",
        scenario="S01_NORMAL_STATIC",
        seed=0,
        metrics={"physics_steps": 10, "illegal_collision_count": 0},
    )

    expected = {
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
    assert expected.issubset({path.name for path in tmp_path.iterdir()})


def test_verify_phase9_summary_sanitizes_home_paths() -> None:
    home = str(Path.home())
    payload = {
        "command": f"{home}/anaconda3/bin/python scripts/verify_phase9.py",
        "stdout_tail": f"wrote {home}/repo/artifacts",
    }

    sanitized = verify_phase9._sanitize_summary_value(payload)

    rendered = str(sanitized)
    assert home not in rendered
    assert "$HOME/anaconda3/bin/python" in rendered
