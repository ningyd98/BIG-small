#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.simulation.phase9_1.verification import (
    run_safety_pressure,
    verify_cross_backend,
    verify_isaac_smoke,
    verify_moveit_safety,
    verify_ros2_integration,
)

TIME_DOMAINS = [
    "simulation_time",
    "ros_time",
    "wall_clock_time",
    "sensor_timestamp",
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Phase 9.1 ROS/MoveIt/Isaac readiness evidence."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/phase9_1"),
        help="Directory for verifier artifacts.",
    )
    parser.add_argument(
        "--skip-history",
        action="store_true",
        help="Skip Phase 9 core history regression when only checking Phase 9.1 artifacts.",
    )
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    history = _run_history(args.output) if not args.skip_history else _skipped_history()
    ros2 = verify_ros2_integration(args.output / "ros2")
    moveit = verify_moveit_safety(args.output / "moveit")
    isaac = verify_isaac_smoke(args.output / "isaac")
    cross_backend = verify_cross_backend(args.output / "cross_backend")
    safety_pressure = run_safety_pressure(args.output / "safety_pressure", trials=100)

    components = {
        "ros2": ros2.to_jsonable(),
        "moveit": moveit.to_jsonable(),
        "isaac": isaac.to_jsonable(),
    }
    component_statuses = {name: item["status"] for name, item in components.items()}
    all_validated = all(item["validation_claimed"] is True for item in components.values())
    any_rejected = history["returncode"] != 0 or safety_pressure["status"] != "PASSED"
    any_blocked = any(status == "BLOCKED_BY_ENV" for status in component_statuses.values())
    status = (
        "PHASE9_1_REJECTED"
        if any_rejected
        else "PHASE9_1_ACCEPTED"
        if all_validated and cross_backend["status"] == "CROSS_BACKEND_VALIDATED"
        else "PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK"
        if any_blocked
        else "PHASE9_1_REJECTED"
    )
    summary: dict[str, Any] = {
        "status": status,
        "components": components,
        "cross_backend": cross_backend,
        "safety_pressure": safety_pressure,
        "history": history,
        "time_domains": TIME_DOMAINS,
        "validation_claimed": status == "PHASE9_1_ACCEPTED",
    }
    (args.output / "phase9_1_summary.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output / "phase9_1_report.md").write_text(_render_report(summary), encoding="utf-8")
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 1 if status == "PHASE9_1_REJECTED" else 0


def _run_history(output_dir: Path) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "scripts/verify_phase9.py"],
        check=False,
        text=True,
        capture_output=True,
    )
    payload = {
        "command": ["python", "scripts/verify_phase9.py"],
        "returncode": result.returncode,
        "stdout_tail": _sanitize_text(result.stdout[-4000:]),
        "stderr_tail": _sanitize_text(result.stderr[-4000:]),
    }
    (output_dir / "phase9_history_check.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def _skipped_history() -> dict[str, object]:
    return {
        "command": [],
        "returncode": 0,
        "stdout_tail": "",
        "stderr_tail": "",
        "skipped": True,
    }


def _sanitize_text(value: str) -> str:
    home = str(Path.home())
    sanitized = value.replace(sys.executable, "python")
    if home:
        sanitized = sanitized.replace(home, "$HOME")
    return sanitized


def _render_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Phase 9.1 Verification Report",
        "",
        f"Status: `{summary['status']}`",
        "",
        "## Components",
        "",
    ]
    components = summary["components"]
    for name in ("ros2", "moveit", "isaac"):
        item = components[name]
        lines.append(
            f"- `{name}`: `{item['status']}`, validation_claimed={item['validation_claimed']}"
        )
        blockers = item.get("blockers", [])
        if blockers:
            lines.append(f"  blockers: {', '.join(str(blocker) for blocker in blockers)}")
    lines.extend(
        [
            "",
            "## Time Domains",
            "",
            *[f"- `{domain}`" for domain in summary["time_domains"]],
            "",
            "## Cross Backend",
            "",
            f"- status: `{summary['cross_backend']['status']}`",
            f"- Isaac comparison: `{summary['cross_backend']['isaac_comparison_status']}`",
            "",
            "This report does not claim real Isaac Sim, ROS 2, MoveIt 2, "
            "or hardware validation when a component is blocked by environment.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
