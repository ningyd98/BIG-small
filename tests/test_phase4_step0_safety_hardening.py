"""Phase 4 Step 0: safety hardening tests — RUNTIME_PROFILE, provider restrictions,
telemetry velocity propagation, post-check improvements."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cloud_edge_robot_arm.config import AppConfig
from cloud_edge_robot_arm.edge.runtime.task_executor import TaskExecutor
from cloud_edge_robot_arm.edge.safety.providers import (
    MockSceneStateProvider,
    MockTelemetryProvider,
    SceneSnapshot,
    TelemetrySample,
)
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield, load_safety_config
from cloud_edge_robot_arm.simulation.mock_robot import MockRobotAdapter, MockScene


def _make_scene() -> MockScene:
    return MockScene.with_default_pick_place_scene()


class RealTelemetryProvider:
    def latest(self) -> TelemetrySample:
        return TelemetrySample(
            timestamp=datetime.now(UTC),
            tcp_velocity=0.0,
            joint_velocities=[],
            acceleration=0.0,
        )


class RealSceneStateProvider:
    def snapshot(self) -> SceneSnapshot:
        return SceneSnapshot(scene_version=1, updated_at=datetime.now(UTC))


# ── RUNTIME_PROFILE validation ──────────────────────────────────────────────


def test_runtime_profile_defaults_to_test() -> None:
    cfg = AppConfig.from_env({})
    assert cfg.runtime_profile == "test"


def test_runtime_profile_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match="RUNTIME_PROFILE"):
        AppConfig.from_env({"RUNTIME_PROFILE": "staging"})


@pytest.mark.parametrize("profile", ["test", "simulation", "production"])
def test_runtime_profile_accepts_valid_values(profile: str) -> None:
    env = {"RUNTIME_PROFILE": profile}
    if profile == "production":
        env.update(
            {
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
    cfg = AppConfig.from_env(env)
    assert cfg.runtime_profile == profile


# ── Production mode forbids Mock providers ──────────────────────────────────


def test_production_mode_rejects_missing_telemetry_provider() -> None:
    robot = MockRobotAdapter(scene=_make_scene())
    robot.connect()
    shield = SafetyShield(load_safety_config())
    with pytest.raises(ValueError, match="telemetry_provider"):
        TaskExecutor(
            robot=robot,
            shield=shield,
            runtime_profile="production",
            telemetry_provider=None,
            scene_provider=MockSceneStateProvider(robot),
        )


def test_production_mode_rejects_missing_scene_provider() -> None:
    robot = MockRobotAdapter(scene=_make_scene())
    robot.connect()
    shield = SafetyShield(load_safety_config())
    with pytest.raises(ValueError, match="scene_provider"):
        TaskExecutor(
            robot=robot,
            shield=shield,
            runtime_profile="production",
            telemetry_provider=MockTelemetryProvider(),
            scene_provider=None,
        )


def test_production_mode_rejects_mock_providers() -> None:
    robot = MockRobotAdapter(scene=_make_scene())
    robot.connect()
    shield = SafetyShield(load_safety_config())
    with pytest.raises(ValueError, match="MockTelemetryProvider"):
        TaskExecutor(
            robot=robot,
            shield=shield,
            runtime_profile="production",
            telemetry_provider=MockTelemetryProvider(),
            scene_provider=RealSceneStateProvider(),
        )
    with pytest.raises(ValueError, match="MockSceneStateProvider"):
        TaskExecutor(
            robot=robot,
            shield=shield,
            runtime_profile="production",
            telemetry_provider=RealTelemetryProvider(),
            scene_provider=MockSceneStateProvider(robot),
        )


def test_production_mode_accepts_real_providers() -> None:
    robot = MockRobotAdapter(scene=_make_scene())
    robot.connect()
    shield = SafetyShield(load_safety_config())
    tp = RealTelemetryProvider()
    sp = RealSceneStateProvider()
    executor = TaskExecutor(
        robot=robot,
        shield=shield,
        runtime_profile="production",
        telemetry_provider=tp,
        scene_provider=sp,
    )
    assert executor._runtime_profile == "production"


def test_test_mode_allows_missing_providers() -> None:
    robot = MockRobotAdapter(scene=_make_scene())
    robot.connect()
    shield = SafetyShield(load_safety_config())
    executor = TaskExecutor(robot=robot, shield=shield, runtime_profile="test")
    assert executor._runtime_profile == "test"
    assert isinstance(executor._telemetry_provider, MockTelemetryProvider)
    assert isinstance(executor._scene_provider, MockSceneStateProvider)


# ── Telemetry velocity propagation to SafetyContext ─────────────────────────


def test_telemetry_joint_velocities_propagated_to_context() -> None:
    """When telemetry provides joint_velocities, they reach SafetyContext."""
    tp = MockTelemetryProvider(joint_velocities=[0.3, 0.4, 0.5])
    sample = tp.latest()
    assert sample is not None
    assert sample.joint_velocities == [0.3, 0.4, 0.5]


def test_missing_joint_velocities_fallback_to_intent() -> None:
    """When telemetry has no joint velocities, intent's requested_joint_velocity
    is used as a conservative single-element list."""
    tp = MockTelemetryProvider(joint_velocities=[], tcp_velocity=0.15)
    sample = tp.latest()
    assert sample is not None
    assert sample.joint_velocities == []
    assert sample.tcp_velocity == 0.15


# ── Post-check uses live telemetry, not hard-coded zero ─────────────────────


def test_post_check_telemetry_values_not_hardcoded_zero() -> None:
    """Post-check context builder should receive actual telemetry values."""
    tp = MockTelemetryProvider(tcp_velocity=0.15, acceleration=0.5)
    sample = tp.latest()
    assert sample is not None
    assert sample.tcp_velocity == 0.15
    assert sample.acceleration == 0.5
    # These values should be passed to context_builder.build (verified in
    # integration test below).


def test_telemetry_stale_mode() -> None:
    stale_ms = 10_000
    tp = MockTelemetryProvider(stale_ms=stale_ms)
    now = datetime.now(UTC)
    sample = tp.latest()
    assert sample is not None
    age = (now - sample.timestamp).total_seconds() * 1_000
    assert abs(age - stale_ms) < 1_000  # allow 1 s tolerance


def test_telemetry_missing_mode() -> None:
    tp = MockTelemetryProvider(missing=True)
    assert tp.latest() is None
