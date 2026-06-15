from __future__ import annotations


def metric_provenance() -> dict[str, str]:
    return {
        "joint_tracking_rmse": "physics_state",
        "tcp_position_error_m": "physics_state",
        "tcp_orientation_error_deg": "physics_state",
        "trajectory_duration_ms": "task_executor_event",
        "max_joint_velocity": "physics_state",
        "max_joint_acceleration": "physics_state",
        "max_tcp_velocity": "physics_state",
        "min_obstacle_distance_m": "physics_state",
        "illegal_collision_count": "contact",
        "illegal_collision_impulse": "contact",
        "expected_contact_count": "contact",
        "grasp_contact_count": "contact",
        "object_slip_distance_m": "physics_state",
        "object_drop_count": "physics_state",
        "grasp_stability_duration_ms": "contact",
        "final_object_position_error_m": "physics_state",
        "object_detection_recall": "sensor_frame",
        "pose_position_error_m": "sensor_frame",
        "pose_orientation_error_deg": "sensor_frame",
        "depth_valid_ratio": "sensor_frame",
        "dropped_frame_count": "sensor_frame",
        "sensor_latency_ms": "sensor_frame",
        "sensor_timestamp_skew_ms": "sensor_frame",
        "scene_confidence": "sensor_frame",
        "fault_detection_latency_ms": "audit_event",
        "recovery_latency_ms": "audit_event",
        "cloud_invocation_count": "network_event",
    }
