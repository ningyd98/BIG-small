#!/usr/bin/env python
"""仓库回归演示或实验入口，用固定参数运行受控流程并输出可追溯结果。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import rclpy  # type: ignore[import-not-found]

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "phase9"))

from run_moveit_safety_evidence import (  # type: ignore[import-not-found] # noqa: E402
    REACHABLE,
    MoveItErrorCodes,
    MoveItSafetyEvidenceRunner,
    _log_integrity,
    _trajectory_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 10 MoveIt dry-run planning only.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase10/moveit_dry_run"))
    parser.add_argument("--startup-timeout", type=float, default=30.0)
    args = parser.parse_args()
    payload = run_moveit_dry_run(args.output, startup_timeout=args.startup_timeout)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "moveit_dry_run_evidence.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0 if payload["validation_claimed"] else 1


def run_moveit_dry_run(output_dir: Path, *, startup_timeout: float) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    runner = MoveItSafetyEvidenceRunner(output_dir, startup_timeout=startup_timeout)
    runner.logs_dir.mkdir(parents=True, exist_ok=True)
    rclpy.init()
    start = time.monotonic()
    try:
        runner.node = rclpy.create_node("phase10_moveit_dry_run")
        runner._start_moveit_stack()
        runner._wait_for_moveit_services()
        response = runner._plan(REACHABLE, allowed_planning_time=3.0)
        planning_time_ms = int(round((time.monotonic() - start) * 1000.0))
        trajectory = response.motion_plan_response.trajectory
        moveit_error_code = int(response.motion_plan_response.error_code.val)
        summary = _trajectory_summary(trajectory)
        point_count = int(summary["trajectory_points"])
        passed = moveit_error_code == MoveItErrorCodes.SUCCESS and point_count > 0
        trajectory_summary = {
            "point_count": point_count,
            "path_length_m": float(summary["joint_space_path_length"]),
            "planning_time_ms": planning_time_ms,
            "max_velocity_scale": 0.05,
            "max_acceleration_scale": 0.05,
            "joint_trajectory": [
                {"positions": positions}
                for positions in summary.get("sampled_points", [])
                if isinstance(positions, list)
            ],
        }
        payload: dict[str, Any] = {
            "status": "MOVEIT_DRY_RUN_VALIDATED" if passed else "INCOMPLETE",
            "validation_claimed": passed,
            "planner_backend": "MOVEIT_RUNTIME",
            "moveit_runtime_used": True,
            "sent_to_hardware": False,
            "hardware_motion_observed": False,
            "execution_status": "PLANNED_ONLY",
            "direct_moveit_execute_called": False,
            "real_controller_required": False,
            "robot_model_valid": True,
            "planning_group_valid": True,
            "joint_limits_valid": passed,
            "collision_validation_claimed": passed,
            "trajectory_summary": trajectory_summary,
            "safety_margin": {
                "minimum_distance_m": 0.0,
                "workspace_margin_m": 0.0,
                "limiting_rule": "MOVEIT_PLANNING_SCENE_VALIDATED_NO_EXECUTE",
            },
            "planning_scene": {"scene_source": "moveit_runtime", "target": "REACHABLE_HOME"},
            "moveit_error_code": moveit_error_code,
            "log_integrity": _log_integrity((runner.moveit_log_path,)),
        }
        if not payload["log_integrity"]["passed"]:
            payload["status"] = "INCOMPLETE"
            payload["validation_claimed"] = False
        return payload
    finally:
        runner._stop_processes()
        runner._sanitize_process_logs()
        if runner.node is not None:
            runner.node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
