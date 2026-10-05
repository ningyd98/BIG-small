"""Linux experiment environments must preserve per-run SQLite isolation."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_common_linux_environment_keeps_experiment_databases_separate(tmp_path: Path) -> None:
    env = dict(os.environ)
    env.pop("SIMULATION_RUNTIME_DB", None)
    env.pop("MODEL_CONTROL_DB", None)
    code = """
import json, sys
from pathlib import Path
from cloud_edge_robot_arm.simulation_workbench.service import SimulationWorkbenchService
roots = [Path(sys.argv[1]) / name for name in ('run-a', 'run-b')]
services = [SimulationWorkbenchService(artifact_root=root) for root in roots]
print(json.dumps([str(service.runtime.repository.database_path) for service in services]))
"""
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source scripts/linux/env.sh; python -c "$1" "$2"',
            "linux-environment-test",
            code,
            str(tmp_path),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert json.loads(result.stdout) == [
        str(tmp_path / name / "simulation_runtime.db") for name in ("run-a", "run-b")
    ]
