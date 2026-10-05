"""Phase 9 物理仿真和跨后端验证回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from pathlib import Path

from cloud_edge_robot_arm.experiments.models import ExperimentMode, NetworkProfileName
from cloud_edge_robot_arm.experiments.runner import ExperimentRunner
from tests.phase9_helpers import phase9_experiment_config


def test_phase9_preserves_phase8_multi_crash_recovery(tmp_path: Path) -> None:
    result = ExperimentRunner(
        phase9_experiment_config(
            tmp_path,
            scenario_id="S15_SQLITE_RESTART_DURING_RUN",
            mode=ExperimentMode.AUTO,
            network_profile=NetworkProfileName.NORMAL,
        )
    ).run()
    points = {
        event.payload["crash_point"]
        for event in result.events
        if event.event_type == "sqlite_restart_recovered"
    }

    assert len(points) == 9
    assert result.result.repeated_completed_step_count == 0
