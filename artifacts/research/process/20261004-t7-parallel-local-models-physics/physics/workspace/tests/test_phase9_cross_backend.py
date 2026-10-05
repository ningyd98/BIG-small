"""Phase 9 物理仿真和跨后端验证回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from cloud_edge_robot_arm.simulation.evaluation.cross_backend import compare_backend_results


def test_phase9_cross_backend_reports_blocked_isaac_without_success_claim() -> None:
    report = compare_backend_results(scenario_id="S01_NORMAL_STATIC", seed=0, isaac_ready=False)

    assert report["mujoco_status"] in {"SUCCESS", "SAFETY_STOPPED"}
    assert report["isaac_status"] == "BLOCKED_BY_ENV"
    assert report["semantic_comparison"] == "NOT_RUN_BLOCKED_BY_ENV"
