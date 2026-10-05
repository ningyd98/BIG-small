"""Phase 9 物理仿真和跨后端验证回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from pathlib import Path

from cloud_edge_robot_arm.experiments.models import ExperimentMode, NetworkProfileName
from cloud_edge_robot_arm.experiments.runner import ExperimentRunner
from tests.phase9_helpers import phase9_experiment_config


def test_phase9_auto_mode_commits_only_at_safe_boundary(tmp_path: Path) -> None:
    result = ExperimentRunner(
        phase9_experiment_config(
            tmp_path,
            scenario_id="S01_NORMAL_STATIC",
            mode=ExperimentMode.AUTO,
            network_profile=NetworkProfileName.NORMAL,
        )
    ).run()
    names = [event.event_type for event in result.events]

    assert "mode_transition_prepared" in names
    assert "mode_transition_deferred" in names
    assert names.index("mode_transition_committed") > names.index("step_completed")
