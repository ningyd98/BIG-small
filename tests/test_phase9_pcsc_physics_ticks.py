"""Phase 9 物理仿真和跨后端验证回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from pathlib import Path

from cloud_edge_robot_arm.experiments.models import ExperimentMode, NetworkProfileName
from cloud_edge_robot_arm.experiments.runner import ExperimentRunner
from tests.phase9_helpers import phase9_experiment_config


def test_phase9_pcsc_retains_multiple_supervision_ticks_with_physics_profile(
    tmp_path: Path,
) -> None:
    result = ExperimentRunner(
        phase9_experiment_config(
            tmp_path,
            scenario_id="S02_TARGET_MOVED",
            mode=ExperimentMode.PCSC,
            network_profile=NetworkProfileName.NORMAL,
            supervision_period_ms=300,
        )
    ).run()

    assert sum(1 for event in result.events if event.event_type == "pcsc_tick") >= 2
