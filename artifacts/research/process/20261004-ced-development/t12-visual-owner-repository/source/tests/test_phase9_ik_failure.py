"""Phase 9 物理仿真和跨后端验证回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.mujoco.backend import joint_targets_for_pose


def test_phase9_ik_surrogate_clips_unreachable_target_to_limits() -> None:
    targets = joint_targets_for_pose(Pose(x=10.0, y=10.0, z=5.0))

    assert len(targets) == 7
    assert all(-2.9 <= target <= 2.9 for target in targets)
