"""Phase 9.1 ROS2/Isaac/MoveIt 边界回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def _load_safety_limits() -> Any:
    module_path = Path("ros2_ws/src/bigsmall_sim_bridge/bigsmall_sim_bridge/safety_limits.py")
    spec = importlib.util.spec_from_file_location("phase9_1_safety_limits", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _trajectory(positions: list[float]) -> SimpleNamespace:
    return SimpleNamespace(
        joint_names=[f"panda_joint{i}" for i in range(1, 8)],
        points=[SimpleNamespace(positions=positions)],
    )


def test_phase9_1_bridge_accepts_nominal_panda_joint_trajectory() -> None:
    safety_limits = _load_safety_limits()

    assert (
        safety_limits.trajectory_joint_limit_violation(
            _trajectory([0.1, -0.6, 0.1, -2.0, 0.1, 1.7, 0.7])
        )
        is None
    )


def test_phase9_1_bridge_reports_first_panda_joint_limit_violation() -> None:
    safety_limits = _load_safety_limits()

    violation = safety_limits.trajectory_joint_limit_violation(
        _trajectory([0.1, -0.6, 0.1, 1.0, 0.1, 1.7, 0.7])
    )

    assert violation == {
        "joint_name": "panda_joint4",
        "point_index": 0,
        "position": 1.0,
        "lower": -3.1416,
        "upper": 0.0873,
    }
