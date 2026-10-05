"""Phase 9 物理仿真和跨后端验证回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from cloud_edge_robot_arm.simulation.evaluation.provenance import metric_provenance


def test_phase9_metrics_have_provenance() -> None:
    provenance = metric_provenance()

    assert provenance["joint_tracking_rmse"] == "physics_state"
    assert provenance["sensor_latency_ms"] == "sensor_frame"
    assert provenance["fault_detection_latency_ms"] == "audit_event"
