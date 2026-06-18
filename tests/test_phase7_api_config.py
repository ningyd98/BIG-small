"""Phase 7 风险评估和 AUTO 模式回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from cloud_edge_robot_arm.auto_mode.models import AutoModePolicy, AutoModeState
from cloud_edge_robot_arm.auto_mode.repository import InMemoryAutoModeRepository
from cloud_edge_robot_arm.cloud.api.app import create_app
from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
from cloud_edge_robot_arm.config import AppConfig
from cloud_edge_robot_arm.contracts import ControlMode, SafetyDecision, SkillName
from cloud_edge_robot_arm.risk.models import RiskPolicy, RiskSnapshotInput
from cloud_edge_robot_arm.skill_cache.models import (
    SkillCacheKey,
    SkillExecutionRecord,
    SkillTemplate,
)
from cloud_edge_robot_arm.skill_cache.repository import InMemorySkillCacheRepository

NOW = datetime(2026, 6, 14, 13, 0, 0, tzinfo=UTC)


def _risk_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = RiskSnapshotInput(
        task_id="task-1",
        task_type="pick-place",
        skill_name="GRASP",
        workspace_id="ws-a",
        scene_version=1,
        scene_updated_at=NOW,
        scene_confidence=0.95,
        target_confidence=0.9,
        target_moved=False,
        obstacle_count=0,
        obstacle_change_rate=0.0,
        network_latency_ms=40,
        network_jitter_ms=5,
        packet_loss_rate=0.01,
        disconnected_seconds=0.0,
        last_heartbeat_at=NOW,
        execution_failures=0,
        timeout_count=0,
        replans_count=0,
        safety_rejections=0,
        estop_engaged=False,
        safety_decision=SafetyDecision.ALLOW,
        current_mode=ControlMode.PERIODIC_CLOUD_SUPERVISION,
        has_complete_contract=True,
        remaining_steps_persisted=True,
        edge_capability_ready=True,
        cloud_available=False,
        event_autonomy_ready=True,
        supervision_available=True,
        cache_confidence=0.95,
        cache_match_type="exact_match",
        policy_version="risk-v1",
        current_time=NOW,
    ).model_dump(mode="json")
    payload.update(overrides)
    return payload


def _template_payload() -> dict[str, object]:
    return SkillTemplate(
        template_id="tmpl-grasp",
        cache_key=SkillCacheKey(
            skill_name=SkillName.GRASP,
            robot_model="mock-arm-v1",
            end_effector_type="parallel_gripper",
            object_class="cube",
            task_intent="pick-place",
            workspace_id="ws-a",
            parameter_schema_version="schema-v1",
            robot_capability_hash="cap-v1",
            safety_policy_hash="safety-v1",
            calibration_version="cal-v1",
        ),
        skill_name=SkillName.GRASP,
        parameter_template={"object_id": "{object_id}"},
        required_preconditions=["target_visible"],
        expected_success_conditions=["object_attached"],
        expected_duration_ms=1_000,
        timeout_ms=3_000,
        source_contract_id="contract-1",
        source_plan_version=1,
        created_at=NOW,
        updated_at=NOW,
        expires_at=NOW + timedelta(days=1),
    ).model_dump(mode="json")


def _execution_payload() -> dict[str, object]:
    return SkillExecutionRecord(
        execution_id="exec-1",
        template_id="tmpl-grasp",
        task_id="task-1",
        plan_id="plan-1",
        step_id="step-grasp",
        success=True,
        safety_decision=SafetyDecision.ALLOW,
        duration_ms=900,
        local_retry_count=0,
        cloud_replan_count=0,
        scene_confidence=0.9,
        network_quality=0.8,
        executed_at=NOW,
        evidence_hash="evidence-ok",
    ).model_dump(mode="json")


def test_phase7_capabilities_do_not_advertise_auto_when_unconfigured() -> None:
    app = create_app(PlanningPipeline(planner=MockPlannerAdapter()))

    response = _request(app, "GET", "/api/v1/auto-mode/capabilities")

    assert response["status_code"] == 200
    assert response["json"]["configured"] is False
    assert response["json"]["auto_mode_enabled"] is False
    assert "AUTO" not in response["json"]["supported_control_modes"]


def test_phase7_risk_decide_and_transition_api_flow() -> None:
    auto_repo = InMemoryAutoModeRepository(clock=lambda: NOW)
    skill_repo = InMemorySkillCacheRepository(clock=lambda: NOW)
    app = create_app(
        PlanningPipeline(planner=MockPlannerAdapter()),
        auto_mode_repo=auto_repo,
        skill_cache_repo=skill_repo,
        auto_mode_enabled=True,
        risk_policy=RiskPolicy(version="risk-v1"),
        auto_mode_policy=AutoModePolicy(version="auto-v1", confirmation_count=1),
        clock=lambda: NOW,
    )

    template = _request(app, "POST", "/api/v1/skill-cache/templates", json_body=_template_payload())
    assert template["status_code"] == 201
    assert template["json"]["status"] == "CANDIDATE"

    risk = _request(app, "POST", "/api/v1/tasks/task-1/risk/evaluate", json_body=_risk_payload())
    assert risk["status_code"] == 201
    assert risk["json"]["task_id"] == "task-1"

    auto_repo.save_status(
        AutoModeState(
            task_id="task-1",
            current_mode=ControlMode.PERIODIC_CLOUD_SUPERVISION,
            mode_version=1,
            switch_count=0,
            last_switch_at=NOW - timedelta(minutes=10),
            policy_version="auto-v1",
            updated_at=NOW,
        )
    )

    decision = _request(
        app,
        "POST",
        "/api/v1/tasks/task-1/auto-mode/decide",
        json_body={
            "cache_key": _template_payload()["cache_key"],
            "active_contract_complete": True,
            "checkpoint_persisted": True,
            "event_autonomy_ready": True,
            "supervision_available": True,
            "atomic_step_active": False,
        },
    )
    assert decision["status_code"] == 201
    assert decision["json"]["task_id"] == "task-1"
    assert "decision_id" in decision["json"]

    transition = _request(
        app,
        "POST",
        "/api/v1/tasks/task-1/mode-transitions",
        json_body={
            "from_mode": "PERIODIC_CLOUD_SUPERVISION",
            "to_mode": "EVENT_TRIGGERED_EDGE_AUTONOMY",
            "expected_mode_version": 1,
            "idempotency_key": "transition-idem-1",
            "decision_id": decision["json"]["decision_id"],
            "reason": "api-flow",
        },
    )
    assert transition["status_code"] == 201
    assert transition["json"]["status"] == "PREPARED"

    fetched = _request(
        app,
        "GET",
        f"/api/v1/tasks/task-1/mode-transitions/{transition['json']['transition_id']}",
    )
    assert fetched["status_code"] == 200
    assert fetched["json"]["transition_id"] == transition["json"]["transition_id"]


def test_skill_cache_api_statistics_and_idempotency_conflict() -> None:
    skill_repo = InMemorySkillCacheRepository(clock=lambda: NOW)
    app = create_app(
        PlanningPipeline(planner=MockPlannerAdapter()),
        skill_cache_repo=skill_repo,
        clock=lambda: NOW,
    )
    template = _request(app, "POST", "/api/v1/skill-cache/templates", json_body=_template_payload())
    assert template["status_code"] == 201

    first = _request(
        app,
        "POST",
        "/api/v1/skill-cache/templates/tmpl-grasp/execution-records",
        json_body=_execution_payload(),
    )
    assert first["status_code"] == 201
    conflict_payload = _execution_payload()
    conflict_payload["success"] = False
    conflict = _request(
        app,
        "POST",
        "/api/v1/skill-cache/templates/tmpl-grasp/execution-records",
        json_body=conflict_payload,
    )

    stats = _request(app, "GET", "/api/v1/skill-cache/templates/tmpl-grasp/statistics")
    assert conflict["status_code"] == 409
    assert stats["status_code"] == 200
    assert stats["json"]["successful_executions"] == 1


def test_phase7_production_config_rejects_unsafe_auto_defaults() -> None:
    base = {
        "RUNTIME_PROFILE": "production",
        "DATABASE_URL": "sqlite:////var/lib/big-small/robot_control.db",
        "MQTT_BROKER_URL": "mqtt://broker.internal:1883",
        "PLANNER_API_ENDPOINT": "https://planner.internal/v1/chat/completions",
        "PLANNER_API_KEY": "prod-secret-key",
        "ROBOT_ADAPTER": "real_robot_sdk",
        "TELEMETRY_PROVIDER": "robot_sdk",
        "SCENE_STATE_PROVIDER": "vision_pipeline",
        "SUPERVISION_REPOSITORY": "sqlite",
        "SUPERVISION_SCHEDULER": "asyncio",
        "AUTO_MODE_ENABLED": "true",
        "RISK_POLICY_VERSION": "risk-v1",
        "RISK_COMPONENT_WEIGHTS": (
            "task=0.15,scene=0.15,perception=0.15,network=0.15,execution=0.2,safety=0.2"
        ),
        "RISK_LEVEL_THRESHOLDS": "low=25,medium=50,high=75,critical=90",
    }
    with pytest.raises(ValueError, match="SKILL_CACHE_BACKEND"):
        AppConfig.from_env(base)
    with pytest.raises(ValueError, match="InMemory"):
        AppConfig.from_env(
            {
                **base,
                "SKILL_CACHE_BACKEND": "inmemory",
                "SKILL_CACHE_DB_PATH": "/var/lib/big-small/skill-cache.db",
                "AUTO_MODE_REPOSITORY": "sqlite",
                "AUTO_MODE_DB_PATH": "/var/lib/big-small/auto-mode.db",
            }
        )
    cfg = AppConfig.from_env(
        {
            **base,
            "SKILL_CACHE_BACKEND": "sqlite",
            "SKILL_CACHE_DB_PATH": "/var/lib/big-small/skill-cache.db",
            "AUTO_MODE_REPOSITORY": "sqlite",
            "AUTO_MODE_DB_PATH": "/var/lib/big-small/auto-mode.db",
        }
    )
    assert cfg.auto_mode_enabled is True
    assert cfg.skill_cache_backend == "sqlite"


def _request(
    app: Any,
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return asyncio.run(_asgi_request(app, method, path, json_body=json_body))


async def _asgi_request(
    app: Any,
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = b"" if json_body is None else json.dumps(json_body).encode("utf-8")
    request_sent = False
    status_code = 0
    response_body = bytearray()
    response_headers: list[tuple[bytes, bytes]] = []

    async def receive() -> dict[str, Any]:
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        nonlocal status_code, response_headers
        if message["type"] == "http.response.start":
            status_code = int(message["status"])
            response_headers = list(message.get("headers", []))
        elif message["type"] == "http.response.body":
            response_body.extend(message.get("body", b""))

    headers = []
    if json_body is not None:
        headers.append((b"content-type", b"application/json"))
    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": b"",
            "headers": headers,
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "root_path": "",
            "state": {},
        },
        receive,
        send,
    )
    text = response_body.decode("utf-8")
    return {
        "status_code": status_code,
        "headers": response_headers,
        "body": text,
        "json": json.loads(text) if text else None,
    }
