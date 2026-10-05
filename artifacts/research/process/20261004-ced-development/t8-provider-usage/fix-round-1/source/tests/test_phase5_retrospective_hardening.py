"""Phase 5 监督控制回归测试，覆盖安全边界、证据契约和关键失败路径。

Retrospective hardening tests for the Phase 0-5 audit."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from cloud_edge_robot_arm.cloud.api.app import create_app
from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
from cloud_edge_robot_arm.cloud.planning.models import (
    InitialPlanningRequest,
    PlannerDraft,
    RobotCapabilities,
    SceneObjectSummary,
    SceneSummary,
    TargetRegionSummary,
)
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
from cloud_edge_robot_arm.cloud.supervision.core import FakeClock
from cloud_edge_robot_arm.cloud.supervision.models import EdgeStatusSnapshot
from cloud_edge_robot_arm.cloud.supervision.repository import (
    InMemorySupervisionRepository,
    SQLiteSupervisionRepository,
)
from cloud_edge_robot_arm.cloud.supervision.service import PeriodicSupervisorService
from cloud_edge_robot_arm.config import AppConfig
from cloud_edge_robot_arm.contracts import Pose, SkillName
from tests.test_phase5_supervision import _make_contract, _make_snapshot


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
    sent = False
    status_code = 0
    response_body = bytearray()

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        nonlocal status_code
        if message["type"] == "http.response.start":
            status_code = int(message["status"])
        elif message["type"] == "http.response.body":
            response_body.extend(message.get("body", b""))

    headers = [(b"content-type", b"application/json")] if json_body is not None else []
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
    return {"status_code": status_code, "json": json.loads(text) if text else None}


class BrokenPlannerAdapter:
    planner_name = "broken"
    model_name = "broken"

    def plan(self, request: InitialPlanningRequest) -> PlannerDraft:
        return PlannerDraft(raw_text="not-json", parsed_json=None, parse_error="not JSON")


def _planning_request_payload() -> dict[str, object]:
    scene = SceneSummary(
        scene_version=1,
        updated_at=datetime.now(UTC),
        objects=[
            SceneObjectSummary(
                object_id="red_cube",
                object_class="cube",
                pose=Pose(x=0.2, y=0.0, z=0.02),
                pose_confidence=0.95,
            )
        ],
        regions=[TargetRegionSummary(region_id="bin_a", center=Pose(x=-0.2, y=0.18, z=0.02))],
        scene_confidence=1.0,
    )
    return {
        "request_id": "req-supervision-api",
        "user_instruction": "pick red cube and place into bin_a",
        "control_mode": "PERIODIC_CLOUD_SUPERVISION",
        "scene": scene.model_dump(mode="json"),
        "capabilities": RobotCapabilities(
            supported_skills=[skill.value for skill in SkillName]
        ).model_dump(mode="json"),
    }


def _snapshot_payload(
    *,
    task_id: str,
    robot_id: str = "robot-001",
    timestamp: datetime,
    plan_version: int = 1,
    command_seq: int = 1,
) -> dict[str, object]:
    snapshot = EdgeStatusSnapshot(
        robot_id=robot_id,
        task_id=task_id,
        plan_version=plan_version,
        command_seq=command_seq,
        scene_version=1,
        timestamp=timestamp,
        current_step_id="step-01",
        robot_state={"connected": True, "estop_engaged": False},
        network_state={"degraded": False, "rtt_ms": 50},
    )
    return snapshot.model_dump(mode="json")


def test_sqlite_supervision_repository_persists_decisions_across_instances(
    tmp_path: Path,
) -> None:
    """Decisions survive service/repository restart instead of living only in memory."""
    db_path = tmp_path / "supervision.sqlite3"
    repo = SQLiteSupervisionRepository(db_path)
    clock = FakeClock()
    service = PeriodicSupervisorService(
        planner=MockPlannerAdapter(),
        clock=clock,
        repository=repo,
    )
    contract = _make_contract()
    service.start(contract)
    decision = service.evaluate_snapshot(_make_snapshot(timestamp=clock.now()), contract)
    repo.close()

    restarted = SQLiteSupervisionRepository(db_path)
    persisted = restarted.list_decisions(contract.task_id)
    status = restarted.get_status(contract.task_id)

    assert [item.decision_id for item in persisted] == [decision.decision_id]
    assert status is not None
    assert status.running is True
    assert status.last_plan_version == decision.resulting_plan_version
    restarted.close()


def test_sqlite_supervision_repository_persists_updated_contract(
    tmp_path: Path,
) -> None:
    """Updated contracts survive restart with trusted supervision metadata."""
    db_path = tmp_path / "supervision.sqlite3"
    repo = SQLiteSupervisionRepository(db_path)
    clock = FakeClock()
    contract = _make_contract(plan_version=3, command_seq=7)
    replanned = contract.model_dump(mode="json")
    replanned["steps"][1]["parameters"] = {"object_id": "red_cube", "height_m": 0.22}
    replanned["plan_version"] = 999
    replanned["command_seq"] = 999
    service = PeriodicSupervisorService(
        planner=MockPlannerAdapter(canned_output=replanned),
        clock=clock,
        repository=repo,
    )
    service.start(contract, initial_target=Pose(x=0.0, y=0.0, z=0.02))
    snapshot = _make_snapshot(
        task_id=contract.task_id,
        plan_version=contract.plan_version,
        command_seq=contract.command_seq,
        current_step_id="step-02",
        completed_step_ids=["step-01"],
        timestamp=clock.now(),
        target_state={
            "object_id": "red_cube",
            "object_class": "cube",
            "x": 0.5,
            "y": 0.5,
            "z": 0.02,
            "region_id": "bin_a",
            "region_center": {"x": -0.2, "y": 0.18, "z": 0.02},
        },
    )
    decision = service.evaluate_snapshot(snapshot, contract)
    repo.close()

    restarted = SQLiteSupervisionRepository(db_path)
    persisted_contract = restarted.get_contract(contract.task_id)

    assert persisted_contract is not None
    assert persisted_contract.plan_version == decision.resulting_plan_version
    assert persisted_contract.command_seq == decision.command_seq
    assert persisted_contract.steps[0] == contract.steps[0]
    assert persisted_contract.steps[1].parameters["height_m"] == 0.22
    restarted.close()


def test_supervision_repository_cas_allows_only_one_version_update() -> None:
    """Concurrent supervision cycles cannot both advance the same version tuple."""
    repo = InMemorySupervisionRepository()
    contract = _make_contract(plan_version=1, command_seq=1)
    repo.start_task(contract)

    first = repo.advance_version_if_current(
        task_id=contract.task_id,
        expected_plan_version=1,
        expected_command_seq=1,
        new_plan_version=2,
        new_command_seq=2,
    )
    second = repo.advance_version_if_current(
        task_id=contract.task_id,
        expected_plan_version=1,
        expected_command_seq=1,
        new_plan_version=2,
        new_command_seq=2,
    )

    status = repo.get_status(contract.task_id)
    assert first is True
    assert second is False
    assert status is not None
    assert status.last_plan_version == 2


def test_update_preserves_completed_steps_and_uses_trusted_versions() -> None:
    """Planner output cannot rewrite completed steps or choose supervision metadata."""
    clock = FakeClock()
    repository = InMemorySupervisionRepository()
    contract = _make_contract(plan_version=3, command_seq=7)
    malicious = contract.model_dump(mode="json")
    malicious["steps"][0]["skill"] = "SAFE_STOP"
    malicious["steps"][0]["parameters"] = {"force_execute": True}
    malicious["steps"][1]["parameters"] = {"object_id": "red_cube", "height_m": 0.22}
    malicious["plan_version"] = 999
    malicious["command_seq"] = 999
    service = PeriodicSupervisorService(
        planner=MockPlannerAdapter(canned_output=malicious),
        clock=clock,
        repository=repository,
    )
    service.start(contract, initial_target=Pose(x=0.0, y=0.0, z=0.02))
    snapshot = _make_snapshot(
        task_id=contract.task_id,
        plan_version=contract.plan_version,
        command_seq=contract.command_seq,
        current_step_id="step-02",
        completed_step_ids=["step-01"],
        timestamp=clock.now(),
        target_state={
            "object_id": "red_cube",
            "object_class": "cube",
            "x": 0.5,
            "y": 0.5,
            "z": 0.02,
            "region_id": "bin_a",
            "region_center": {"x": -0.2, "y": 0.18, "z": 0.02},
        },
    )

    decision = service.evaluate_snapshot(snapshot, contract)

    assert decision.resulting_plan_version == 4
    assert decision.command_seq == 8
    assert decision.updated_steps[0] == contract.steps[0]
    assert decision.updated_steps[1].parameters["height_m"] == 0.22


def test_replan_failure_fails_closed_without_version_advance() -> None:
    """Malformed planner output produces a safe non-update decision."""
    clock = FakeClock()
    repository = InMemorySupervisionRepository()
    contract = _make_contract(plan_version=1, command_seq=1)
    service = PeriodicSupervisorService(
        planner=BrokenPlannerAdapter(),
        clock=clock,
        repository=repository,
    )
    service.start(contract, initial_target=Pose(x=0.0, y=0.0, z=0.02))
    snapshot = _make_snapshot(
        timestamp=clock.now(),
        target_state={
            "object_id": "red_cube",
            "object_class": "cube",
            "x": 0.5,
            "y": 0.5,
            "z": 0.02,
            "region_id": "bin_a",
            "region_center": {"x": -0.2, "y": 0.18, "z": 0.02},
        },
    )

    decision = service.evaluate_snapshot(snapshot, contract)
    status = repository.get_status(contract.task_id)

    assert decision.planner_invoked is False
    assert decision.updated_steps == []
    assert decision.resulting_plan_version == 1
    assert status is not None
    assert status.last_plan_version == 1


def test_duplicate_snapshot_reuses_persisted_decision() -> None:
    clock = FakeClock()
    repository = InMemorySupervisionRepository()
    contract = _make_contract()
    service = PeriodicSupervisorService(
        planner=MockPlannerAdapter(),
        clock=clock,
        repository=repository,
    )
    service.start(contract)
    snapshot = _make_snapshot(timestamp=clock.now())

    first = service.evaluate_snapshot(snapshot, contract)
    second = service.evaluate_snapshot(snapshot, contract)

    assert second.decision_id == first.decision_id
    assert len(repository.list_decisions(contract.task_id)) == 1


def test_supervision_api_endpoints_form_closed_loop() -> None:
    """API exposes status intake, manual supervision, decisions, and lifecycle endpoints."""
    clock = FakeClock()
    repository = InMemorySupervisionRepository()
    pipeline = PlanningPipeline(planner=MockPlannerAdapter())
    supervisor = PeriodicSupervisorService(
        planner=MockPlannerAdapter(),
        clock=clock,
        repository=repository,
    )
    app = create_app(pipeline, supervisor=supervisor)

    capabilities = _request(app, "GET", "/api/v1/supervision/capabilities")
    assert capabilities["status_code"] == 200
    assert "KEEP_CURRENT_PLAN" in capabilities["json"]["supported_decisions"]

    planning = _request(app, "POST", "/api/v1/plans", json_body=_planning_request_payload())
    assert planning["status_code"] == 201
    contract = planning["json"]["contract"]
    task_id = contract["task_id"]

    start = _request(app, "POST", f"/api/v1/plans/{task_id}/supervision/start")
    assert start["status_code"] == 200
    assert start["json"]["running"] is True

    snapshot = _snapshot_payload(task_id=task_id, timestamp=clock.now())
    status = _request(app, "POST", "/api/v1/robots/robot-001/status", json_body=snapshot)
    assert status["status_code"] == 202

    decision = _request(app, "POST", f"/api/v1/plans/{task_id}/supervise", json_body=snapshot)
    assert decision["status_code"] == 200
    assert decision["json"]["decision"] == "KEEP_CURRENT_PLAN"

    listed = _request(app, "GET", f"/api/v1/plans/{task_id}/supervision/decisions")
    assert listed["status_code"] == 200
    assert [item["decision_id"] for item in listed["json"]["decisions"]] == [
        decision["json"]["decision_id"]
    ]

    running = _request(app, "GET", f"/api/v1/plans/{task_id}/supervision/status")
    assert running["status_code"] == 200
    assert running["json"]["running"] is True

    stop = _request(app, "POST", f"/api/v1/plans/{task_id}/supervision/stop")
    assert stop["status_code"] == 200
    assert stop["json"]["running"] is False


def test_supervision_api_rejects_robot_status_path_mismatch() -> None:
    clock = FakeClock()
    app = create_app(
        PlanningPipeline(planner=MockPlannerAdapter()),
        supervisor=PeriodicSupervisorService(
            planner=MockPlannerAdapter(),
            clock=clock,
            repository=InMemorySupervisionRepository(),
        ),
    )
    response = _request(
        app,
        "POST",
        "/api/v1/robots/robot-other/status",
        json_body=_snapshot_payload(
            task_id="task-001", robot_id="robot-001", timestamp=clock.now()
        ),
    )
    assert response["status_code"] == 409
    assert response["json"]["error"] == "robot_id_mismatch"


def test_planning_capabilities_advertise_phase6_without_auto_mode() -> None:
    app = create_app(PlanningPipeline(planner=MockPlannerAdapter()))
    response = _request(app, "GET", "/api/v1/planning/capabilities")
    assert response["status_code"] == 200
    modes = response["json"]["supported_control_modes"]
    assert modes == ["PERIODIC_CLOUD_SUPERVISION", "EVENT_TRIGGERED_EDGE_AUTONOMY"]
    assert "AUTO" not in modes


def test_production_config_requires_explicit_integrations() -> None:
    with pytest.raises(ValueError, match="DATABASE_URL"):
        AppConfig.from_env({"RUNTIME_PROFILE": "production"})

    with pytest.raises(ValueError, match="test-double"):
        AppConfig.from_env(
            {
                "RUNTIME_PROFILE": "production",
                "DATABASE_URL": "sqlite:////var/lib/big-small/robot_control.db",
                "MQTT_BROKER_URL": "mqtt://broker.internal:1883",
                "PLANNER_API_ENDPOINT": "https://planner.internal/v1/chat/completions",
                "PLANNER_API_KEY": "prod-secret-key",
                "ROBOT_ADAPTER": "mock_robot",
                "TELEMETRY_PROVIDER": "robot_sdk",
                "SCENE_STATE_PROVIDER": "vision_pipeline",
                "SUPERVISION_REPOSITORY": "sqlite",
                "SUPERVISION_SCHEDULER": "asyncio",
            }
        )

    cfg = AppConfig.from_env(
        {
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
        }
    )
    assert cfg.runtime_profile == "production"
    assert cfg.robot_adapter == "real_robot_sdk"
    assert cfg.supervision_repository == "sqlite"


def test_pose_rejects_nan_and_infinity() -> None:
    with pytest.raises(ValidationError):
        Pose(x=float("nan"), y=0.0, z=0.0)
    with pytest.raises(ValidationError):
        Pose(x=0.0, y=float("inf"), z=0.0)


def test_local_quality_scripts_include_phase5_verification() -> None:
    ci = Path(".github/workflows/ci.yml").read_text()
    local = Path("scripts/run_checks.sh").read_text()
    assert "scripts/verify_phase5.py" in ci
    assert "scripts/verify_phase5.py" in local
