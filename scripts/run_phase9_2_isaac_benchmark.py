#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.simulation.phase9_2.verification import (  # noqa: E402
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

    command = [
        sys.executable,
        "scripts/run_phase9_benchmarks.py",
        "--backend",
        "isaac",
        "--suite",
        "smoke",
        "--output",
        str(args.output),
    ]
    result = subprocess.run(command, check=False, text=True, capture_output=True, timeout=900)
    (args.output / "process_stdout.log").write_text(result.stdout, encoding="utf-8")
    (args.output / "process_stderr.log").write_text(result.stderr, encoding="utf-8")
    payload = {
        "status": "PASSED" if result.returncode == 0 else "FAILED",
        "benchmark_status": "PASSED" if result.returncode == 0 else "FAILED",
        "validation_claimed": result.returncode == 0,
        "command": command,
        "exit_code": result.returncode,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    _write(args.output, payload)
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0 if result.returncode == 0 else 1


def _write(output: Path, payload: dict[str, object]) -> None:
    (output / "summary.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
