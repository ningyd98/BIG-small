#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PHASE10_2B_CONSOLE_ACCEPTED = "PHASE10_2B_CONSOLE_ACCEPTED"


@dataclass(frozen=True)
class VerificationCommand:
    name: str
    argv: list[str]
    cwd: Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 10.2B dashboard console.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase10/phase10_2b"))
    parser.add_argument("--skip-e2e", action="store_true", help="Skip browser E2E checks.")
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    dashboard = repo / "dashboard"
    commands = [
        VerificationCommand(
            "dashboard-backend-tests",
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_phase10_2b_dashboard_backend.py",
                "tests/test_phase10_2b_dashboard_websocket.py",
                "-q",
            ],
            repo,
        ),
        VerificationCommand("dashboard-openapi-drift", ["npm", "run", "api:check"], dashboard),
        VerificationCommand("dashboard-format", ["npm", "run", "format:check"], dashboard),
        VerificationCommand("dashboard-lint", ["npm", "run", "lint"], dashboard),
        VerificationCommand("dashboard-typecheck", ["npm", "run", "typecheck"], dashboard),
        VerificationCommand("dashboard-unit-tests", ["npm", "run", "test"], dashboard),
        VerificationCommand("dashboard-build", ["npm", "run", "build"], dashboard),
    ]
    if not args.skip_e2e:
        commands.append(VerificationCommand("dashboard-e2e", ["npm", "run", "e2e"], dashboard))

    payload: dict[str, Any] = run_commands(commands)
    accepted = all(item["status"] == "PASSED" for item in payload["commands"])
    payload.update(
        {
            "status": PHASE10_2B_CONSOLE_ACCEPTED if accepted else "PHASE10_2B_CONSOLE_FAILED",
            "validation_claimed": accepted,
            "real_robot_validation": "NOT_STARTED",
            "highest_acceptance_level": "NONE",
            "hardware_motion_authorized": False,
            "generated_at": datetime.now(UTC).isoformat(),
        }
    )
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "phase10_2b_verification.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0 if accepted else 1


def run_commands(commands: list[VerificationCommand]) -> dict[str, Any]:
    results: list[dict[str, object]] = []
    for command in commands:
        result = subprocess.run(
            command.argv,
            cwd=command.cwd,
            check=False,
            text=True,
            capture_output=True,
            timeout=600,
        )
        passed = result.returncode == 0
        results.append(
            {
                "name": command.name,
                "argv": command.argv,
                "cwd": str(command.cwd),
                "returncode": result.returncode,
                "status": "PASSED" if passed else "FAILED",
                "stdout_tail": result.stdout[-4000:],
                "stderr_tail": result.stderr[-4000:],
            }
        )
        if not passed:
            break
    return {"commands": results}


if __name__ == "__main__":
    raise SystemExit(main())
