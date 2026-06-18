#!/usr/bin/env python
"""项目级验证编排脚本，按固定 allowlist 执行检查命令并汇总 artifact。"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SUMMARY_DIR = Path("artifacts/project_verification")
PHASE10_PROJECT_DIR = Path("artifacts/project_verification/phase10")
PHASE10_2A_FRAMEWORK_ARGV = [
    "python",
    "scripts/verify_phase10_2a.py",
    "--skip-runtime",
    "--output",
    str(PHASE10_PROJECT_DIR / "phase10_2a"),
    "--phase10-0-dir",
    str(PHASE10_PROJECT_DIR / "phase10_0"),
    "--phase10-1-dir",
    str(PHASE10_PROJECT_DIR / "phase10_1"),
]
PHASE10_0_PROJECT_ARGV = [
    "python",
    "scripts/verify_phase10_0.py",
    "--output",
    str(PHASE10_PROJECT_DIR / "phase10_0"),
]
PHASE10_1_PROJECT_ARGV = [
    "python",
    "scripts/verify_phase10_1.py",
    "--output",
    str(PHASE10_PROJECT_DIR / "phase10_1"),
]


@dataclass(frozen=True)
class ProjectCommand:
    name: str
    argv: list[str]
    ci_safe: bool
    may_touch_real_hardware: bool = False


def profile_commands(profile: str) -> list[ProjectCommand]:
    profiles: dict[str, list[ProjectCommand]] = {
        "ci": [
            _cmd("compileall", ["python", "-m", "compileall", "src", "scripts", "tests"]),
            _cmd("ruff-format", ["python", "-m", "ruff", "format", "--check", "."]),
            _cmd("ruff-check", ["python", "-m", "ruff", "check", "."]),
            _cmd("mypy", ["python", "-m", "mypy", "."]),
            _cmd("pytest", ["python", "-m", "pytest", "-q"]),
            _cmd("docs", ["python", "scripts/check_docs.py"]),
            _cmd("phase10-0", PHASE10_0_PROJECT_ARGV),
            _cmd("phase10-1", PHASE10_1_PROJECT_ARGV),
            _cmd("phase10-2a-framework", PHASE10_2A_FRAMEWORK_ARGV),
        ],
        "simulation": [
            _cmd("phase9", ["python", "scripts/verify_phase9.py"]),
            _cmd(
                "phase9-2-final",
                [
                    "python",
                    "scripts/verify_phase9_2.py",
                    "--output",
                    "artifacts/phase9_2/final",
                ],
            ),
        ],
        "ros2-moveit": [
            _cmd(
                "phase9-1",
                ["python", "scripts/verify_phase9_1.py", "--skip-history"],
                ci_safe=False,
            ),
            _cmd(
                "phase10-moveit-dry-run",
                [
                    "python",
                    "scripts/verify_phase10_moveit_dry_run.py",
                    "--output",
                    "artifacts/phase10/moveit_dry_run",
                ],
                ci_safe=False,
            ),
        ],
        "isaac": [
            _cmd(
                "phase9-2-environment",
                [
                    "python",
                    "scripts/verify_phase9_2_environment.py",
                    "--output",
                    "artifacts/phase9_2/environment",
                ],
                ci_safe=False,
            ),
            _cmd(
                "phase9-2-smoke",
                [
                    "python",
                    "scripts/verify_phase9_2_isaac_smoke.py",
                    "--output",
                    "artifacts/phase9_2/isaac",
                ],
                ci_safe=False,
            ),
        ],
        "phase10-dry-run": [
            _cmd("phase10-0", PHASE10_0_PROJECT_ARGV),
            _cmd("phase10-1", PHASE10_1_PROJECT_ARGV),
            _cmd("phase10-2a-framework", PHASE10_2A_FRAMEWORK_ARGV),
        ],
    }
    if profile == "all-available":
        return [
            *profiles["ci"],
            *profiles["simulation"],
            *profiles["phase10-dry-run"],
        ]
    if profile not in profiles:
        raise ValueError(f"unknown profile: {profile}")
    return profiles[profile]


def run_profile(profile: str, *, output: Path | None = None) -> dict[str, object]:
    commands = profile_commands(profile)
    results: list[dict[str, object]] = []
    ok = True
    for command in commands:
        result = subprocess.run(command.argv, check=False, text=True, capture_output=True)
        command_ok = result.returncode == 0
        ok = ok and command_ok
        results.append(
            {
                "name": command.name,
                "argv": command.argv,
                "ci_safe": command.ci_safe,
                "may_touch_real_hardware": command.may_touch_real_hardware,
                "returncode": result.returncode,
                "stdout_tail": result.stdout[-4000:],
                "stderr_tail": result.stderr[-4000:],
                "status": "PASSED" if command_ok else "FAILED",
            }
        )
        if not command_ok:
            break
    payload: dict[str, object] = {
        "profile": profile,
        "status": "PASSED" if ok else "FAILED",
        "validation_claimed": ok,
        "real_hardware_commands_run": any(item["may_touch_real_hardware"] for item in results),
        "commands": results,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    summary_path = output or SUMMARY_DIR / f"{profile}_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run BIG-small verification profiles.")
    parser.add_argument(
        "--profile",
        choices=[
            "ci",
            "simulation",
            "ros2-moveit",
            "isaac",
            "phase10-dry-run",
            "all-available",
        ],
        required=True,
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = run_profile(args.profile, output=args.output)
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0 if payload["status"] == "PASSED" else 1


def _cmd(name: str, argv: list[str], *, ci_safe: bool = True) -> ProjectCommand:
    return ProjectCommand(name=name, argv=argv, ci_safe=ci_safe)


if __name__ == "__main__":
    raise SystemExit(main())
