from __future__ import annotations

import json
import logging

from cloud_edge_robot_arm.config import AppConfig, CoordinationModeDefaults
from cloud_edge_robot_arm.logging_utils import build_json_log_record


def test_app_config_has_safe_phase_zero_defaults() -> None:
    config = AppConfig.from_env({})

    assert config.app_name == "small-robot-arm-cloud-edge-control"
    assert config.mqtt_broker_url == "mqtt://localhost:1883"
    assert config.database_url == "sqlite:///./data/robot_control.db"
    assert config.mode_defaults == CoordinationModeDefaults(
        periodic_supervision_ms=1_000,
        command_ttl_ms=2_500,
        network_loss_grace_ms=3_000,
    )
    assert config.safety_shield_enabled is True


def test_json_log_record_contains_traceability_fields() -> None:
    record = build_json_log_record(
        level=logging.INFO,
        event="contract.accepted",
        message="contract accepted by edge validator",
        task_id="task-red-cube",
        plan_version=1,
        command_seq=3,
        extra={"scene_version": 7},
    )
    parsed = json.loads(record)

    assert parsed["level"] == "INFO"
    assert parsed["event"] == "contract.accepted"
    assert parsed["task_id"] == "task-red-cube"
    assert parsed["plan_version"] == 1
    assert parsed["command_seq"] == 3
    assert parsed["scene_version"] == 7
    assert parsed["timestamp"].endswith("+00:00")
