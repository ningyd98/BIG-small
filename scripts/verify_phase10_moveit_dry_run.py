#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.real_robot.provenance import current_source_provenance  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Phase 10 MoveIt dry-run planning evidence."
    )
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase10/moveit_dry_run"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    payload = _run_or_block(args.output)
    payload["provenance"] = current_source_provenance(
        command=[
            "python",
            "scripts/verify_phase10_moveit_dry_run.py",
            "--output",
            str(args.output),
        ],
        verifier_version="phase10.2a-moveit-dry-run-1",
    ).model_dump(mode="json")
    (args.output / "moveit_dry_run_verification.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0 if payload["validation_claimed"] else 1


def _run_or_block(output_dir: Path) -> dict[str, object]:
    command = (
        "source scripts/phase9/activate_ros2_moveit_env.sh >/dev/null && "
        "export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-45} && "
        f"python scripts/phase10/run_moveit_dry_run_runtime.py --output {output_dir}"
    )
    result = subprocess.run(
        ["bash", "-lc", command],
        check=False,
        text=True,
        capture_output=True,
        timeout=180,
        env=os.environ.copy(),
    )
    evidence = _load_json(output_dir / "moveit_dry_run_evidence.json")
    if result.returncode == 0 and isinstance(evidence, dict) and evidence.get("validation_claimed"):
        payload = dict(evidence)
        payload["command"] = ["bash", "-lc", command.replace(str(Path.home()), "$HOME")]
        payload["stdout_tail"] = result.stdout[-2000:].replace(str(Path.home()), "$HOME")
        payload["stderr_tail"] = result.stderr[-2000:].replace(str(Path.home()), "$HOME")
        return payload
    return {
        "status": "MOVEIT_DRY_RUN_BLOCKED_BY_ENV",
        "validation_claimed": False,
        "planner_backend": "MOVEIT_RUNTIME",
        "moveit_runtime_used": False,
        "sent_to_hardware": False,
        "hardware_motion_observed": False,
        "execution_status": "PLANNED_ONLY",
        "blockers": ["ROS 2 / MoveIt runtime dry-run evidence was not produced"],
        "command": ["bash", "-lc", command.replace(str(Path.home()), "$HOME")],
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-2000:].replace(str(Path.home()), "$HOME"),
        "stderr_tail": result.stderr[-2000:].replace(str(Path.home()), "$HOME"),
    }


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
