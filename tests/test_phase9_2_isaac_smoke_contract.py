from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from cloud_edge_robot_arm.simulation.phase9_2.verification import verify_isaac_smoke_evidence


def test_isaac_smoke_rejects_missing_required_sensor(tmp_path: Path) -> None:
    evidence = _valid_smoke()
    sensor_samples = cast(dict[str, dict[str, object]], evidence["sensor_samples"])
    sensor_samples["depth"]["available"] = False
    _write_smoke(tmp_path, evidence)

    result = verify_isaac_smoke_evidence(tmp_path)

    assert result["status"] == "INCOMPLETE"
    assert result["validation_claimed"] is False
    blockers = cast(list[str], result["blockers"])
    assert "depth sensor sample is missing" in blockers


def test_isaac_smoke_rejects_forbidden_log_marker(tmp_path: Path) -> None:
    evidence = _valid_smoke()
    _write_smoke(tmp_path, evidence)
    (tmp_path / "process_stderr.log").write_text("CUDA error: device lost\n", encoding="utf-8")

    result = verify_isaac_smoke_evidence(tmp_path)

    assert result["status"] == "INCOMPLETE"
    blockers = cast(list[str], result["blockers"])
    assert "forbidden log marker" in " ".join(blockers)


def test_isaac_smoke_validates_complete_runtime_artifact(tmp_path: Path) -> None:
    _write_smoke(tmp_path, _valid_smoke())

    result = verify_isaac_smoke_evidence(tmp_path)

    assert result["status"] == "ISAAC_SMOKE_VALIDATED"
    assert result["validation_claimed"] is True
    assert result["real_isaac_run_count"] == 1


def _write_smoke(output_dir: Path, evidence: dict[str, object]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "isaac_smoke_evidence.json").write_text(
        json.dumps(evidence, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    for name in ("process_stdout.log", "process_stderr.log"):
        (output_dir / name).write_text("", encoding="utf-8")
    (output_dir / "rgb_sample.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (output_dir / "depth_sample.npy").write_bytes(b"NUMPY")
    (output_dir / "contact_sample.json").write_text('{"contacts": []}\n', encoding="utf-8")


def _valid_smoke() -> dict[str, Any]:
    return {
        "status": "ISAAC_SMOKE_VALIDATED",
        "validation_claimed": True,
        "artifact_provenance_complete": True,
        "isaac_sim_version": "6.0.0",
        "runtime_mode": "standalone",
        "process_id": 123,
        "run_id": "isaac-smoke-1",
        "executable": "/opt/isaac-sim/python.sh",
        "launch_command": ["/opt/isaac-sim/python.sh", "scripts/phase9/isaac_standalone_app.py"],
        "image_digest": "",
        "stage_path": "artifacts/phase9_2/isaac/stage.usd",
        "stage_loaded": True,
        "physics_steps": 12,
        "simulation_time": 0.2,
        "wall_clock_time": "2026-06-17T00:00:00Z",
        "robot_state_sample": True,
        "sensor_samples": {
            "rgb": {"available": True, "path": "rgb_sample.png", "width": 320, "height": 240},
            "depth": {"available": True, "path": "depth_sample.npy", "width": 320, "height": 240},
            "contact": {"available": True, "path": "contact_sample.json", "count": 0},
        },
        "reset_result": {"success": True},
        "emergency_stop_result": {"success": True, "post_command_accepted": False},
        "graceful_shutdown_result": {"success": True},
        "process_provenance": {
            "runtime": "isaac_standalone",
            "backend_name": "isaac",
            "code_commit_sha": "abc",
        },
        "forbidden_log_scan": {"passed": True, "violations": []},
    }
