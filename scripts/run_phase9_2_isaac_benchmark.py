#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.simulation.evaluation.metrics import (  # noqa: E402
    run_isaac_physical_trial,
)
from cloud_edge_robot_arm.simulation.phase9_2.verification import (  # noqa: E402
    PHASE9_2_SCENARIOS,
    build_isaac_runtime_command,
    run_isaac_smoke_runtime,
    runtime_config_from_env,
    verify_isaac_smoke_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 9.2 Isaac benchmark guard.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/phase9_2/isaac_benchmark"),
        help="Directory for Phase 9.2 Isaac benchmark summary.",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    config = runtime_config_from_env(
        repo_root=Path("."), output_dir=Path("artifacts/phase9_2/isaac")
    )
    if config is None:
        payload = {
            "status": "BLOCKED_BY_ENV",
            "benchmark_status": "BLOCKED_BY_ENV",
            "validation_claimed": False,
            "blockers": ["Isaac runtime is not configured"],
            "generated_at": datetime.now(UTC).isoformat(),
        }
        _write(args.output, payload)
        print(json.dumps(payload, sort_keys=True, indent=2))
        return 1

    smoke_output = Path("artifacts/phase9_2/isaac")
    smoke_payload = verify_isaac_smoke_evidence(smoke_output)
    if smoke_payload.get("status") != "ISAAC_SMOKE_VALIDATED":
        smoke_payload = run_isaac_smoke_runtime(smoke_output, config=config)
    if smoke_payload.get("status") != "ISAAC_SMOKE_VALIDATED":
        raw_blockers = smoke_payload.get("blockers", [])
        smoke_blockers = (
            [str(blocker) for blocker in raw_blockers if isinstance(blocker, str)]
            if isinstance(raw_blockers, list)
            else []
        )
        payload = {
            "status": "BLOCKED_BY_ENV",
            "benchmark_status": "BLOCKED_BY_ENV",
            "validation_claimed": False,
            "blockers": [
                "Isaac smoke runtime is not validated; benchmark was not run",
                *smoke_blockers,
            ],
            "smoke_status": str(smoke_payload.get("status", "")),
            "generated_at": datetime.now(UTC).isoformat(),
        }
        _write(args.output, payload)
        print(json.dumps(payload, sort_keys=True, indent=2))
        return 1

    process_argv = build_isaac_runtime_command(
        config,
        [
            "--output",
            str(args.output / "isaac_process"),
        ],
    ).argv
    rows: list[dict[str, object]] = []
    blockers: list[str] = []
    for index, scenario_id in enumerate(PHASE9_2_SCENARIOS):
        try:
            result = run_isaac_physical_trial(
                scenario_id,
                seed=0,
                process_argv=process_argv,
            )
        except Exception as exc:  # noqa: BLE001 - artifact must preserve failed benchmark reason.
            blockers.append(f"{scenario_id}: {type(exc).__name__}: {exc}")
            continue
        rows.append(
            {
                "backend_name": "isaac",
                "run_id": f"phase9-2-isaac-benchmark-{index:03d}",
                "scenario_id": scenario_id,
                "seed": 0,
                "metrics": result.metrics,
                "result_hash": result.result_hash,
                "validation_claimed": True,
            }
        )
    _write_jsonl(args.output / "runs.jsonl", rows)
    status = "PASSED" if len(rows) == len(PHASE9_2_SCENARIOS) and not blockers else "FAILED"
    payload = {
        "status": status,
        "benchmark_status": status,
        "validation_claimed": status == "PASSED",
        "backend_name": "isaac",
        "blockers": blockers,
        "run_count": len(rows),
        "scenario_count": len(PHASE9_2_SCENARIOS),
        "metrics_summary": _metrics_summary(rows),
        "process_provenance": {
            "runtime": "isaac_standalone",
            "launch_command": _sanitize_argv(process_argv),
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }
    _write(args.output, payload)
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0 if status == "PASSED" else 1


def _write(output: Path, payload: dict[str, object]) -> None:
    (output / "summary.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _metrics_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    metrics: list[dict[str, Any]] = []
    for row in rows:
        value = row.get("metrics", {})
        if isinstance(value, dict):
            metrics.append(value)
    if not metrics:
        return {}
    return {
        "illegal_collision_total": sum(
            int(_metric(row, "illegal_collision_count")) for row in metrics
        ),
        "mean_physics_steps": sum(float(_metric(row, "physics_steps")) for row in metrics)
        / len(metrics),
        "mean_trajectory_duration_ms": sum(
            float(_metric(row, "trajectory_duration_ms")) for row in metrics
        )
        / len(metrics),
    }


def _metric(row: dict[str, Any], key: str) -> float:
    return float(row.get(key, 0.0) or 0.0)


def _sanitize_argv(argv: list[str]) -> list[str]:
    home = str(Path.home())
    sanitized = []
    for item in argv:
        value = item.replace(sys.executable, "python")
        if home:
            value = value.replace(home, "$HOME")
        sanitized.append(value)
    return sanitized


if __name__ == "__main__":
    raise SystemExit(main())
