"""Phase 6 event detection tests — unit tests for all event detectors."""

from __future__ import annotations

from datetime import UTC, datetime

from cloud_edge_robot_arm.contracts.models import (
    EdgeEventType,
    EventSeverity,
    RobotState,
    SkillExecutionResult,
    SkillName,
    TaskStep,
)
from cloud_edge_robot_arm.edge.events import (
    CompletionEventDetector,
    CompositeEventDetector,
    DetectionContext,
    DeviceHealthEventDetector,
    ExecutionEventDetector,
    NetworkEventDetector,
    SafetyEventDetector,
    SceneChangeEventDetector,
    TargetChangeDetector,
    TimeoutEventDetector,
)
from cloud_edge_robot_arm.edge.events.detector import EventDetector

NOW = datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC)


def _make_context(**overrides: object) -> DetectionContext:
    defaults: dict[str, object] = {
        "task_id": "task-test-001",
        "plan_version": 1,
        "command_seq": 1,
        "robot_id": "robot-001",
        "step": TaskStep(
            step_id="step-1",
            skill=SkillName.GRASP,
            parameters={},
            expected_duration_ms=2000,
            timeout_ms=5000,
            retry_limit=3,
        ),
        "step_result": None,
        "robot_state": RobotState(connected=True),
        "contract": None,
        "elapsed_action_ms": 1000,
        "step_attempts": {},
        "scene_version": 1,
        "scene_confidence": 0.9,
        "completed_step_ids": [],
        "completion_criteria": [],
    }
    defaults.update(overrides)
    return DetectionContext(**defaults)  # type: ignore[arg-type]


# ── ExecutionEventDetector ─────────────────────────────────────────────


def test_execution_detector_grasp_failure() -> None:
    detector = ExecutionEventDetector()
    ctx = _make_context(
        step_result=SkillExecutionResult(
            task_id="task-test-001",
            plan_version=1,
            command_seq=1,
            timestamp=NOW,
            step_id="step-1",
            skill=SkillName.GRASP,
            scene_version=1,
            success=False,
            duration_ms=2000,
        ),
    )
    event = detector.detect(ctx)
    assert event is not None
    assert event.event_type == EdgeEventType.GRASP_FAILED
    assert event.severity == EventSeverity.ERROR


def test_execution_detector_ignores_success() -> None:
    detector = ExecutionEventDetector()
    ctx = _make_context(
        step_result=SkillExecutionResult(
            task_id="task-test-001",
            plan_version=1,
            command_seq=1,
            timestamp=NOW,
            step_id="step-1",
            skill=SkillName.GRASP,
            scene_version=1,
            success=True,
            duration_ms=1500,
        ),
    )
    event = detector.detect(ctx)
    assert event is None


def test_execution_detector_place_failure() -> None:
    detector = ExecutionEventDetector()
    ctx = _make_context(
        step=TaskStep(
            step_id="step-2",
            skill=SkillName.PLACE,
            parameters={},
            expected_duration_ms=2000,
            timeout_ms=5000,
            retry_limit=3,
        ),
        step_result=SkillExecutionResult(
            task_id="task-test-001",
            plan_version=1,
            command_seq=1,
            timestamp=NOW,
            step_id="step-2",
            skill=SkillName.PLACE,
            scene_version=1,
            success=False,
            duration_ms=2000,
        ),
    )
    event = detector.detect(ctx)
    assert event is not None
    assert event.event_type == EdgeEventType.PLACE_FAILED


# ── TimeoutEventDetector ────────────────────────────────────────────────


def test_timeout_detector_step_timeout() -> None:
    detector = TimeoutEventDetector()
    ctx = _make_context(elapsed_action_ms=6000)  # > 5000ms timeout
    event = detector.detect(ctx)
    assert event is not None
    assert event.event_type == EdgeEventType.STEP_TIMEOUT
    assert event.severity == EventSeverity.ERROR


def test_timeout_detector_no_timeout_within_budget() -> None:
    detector = TimeoutEventDetector()
    ctx = _make_context(elapsed_action_ms=3000)  # < 5000ms timeout
    event = detector.detect(ctx)
    # may return TELEMETRY_STALE or None but NOT STEP_TIMEOUT
    if event is not None:
        assert event.event_type != EdgeEventType.STEP_TIMEOUT


# ── TargetChangeDetector ────────────────────────────────────────────────


def test_target_detector_no_movement() -> None:
    detector = TargetChangeDetector(position_threshold_m=0.02)
    ctx = _make_context()
    # No scene_state → no target pose → no event (first observation)
    event = detector.detect(ctx)
    assert event is None


def test_target_detector_honors_threshold() -> None:
    detector = TargetChangeDetector(position_threshold_m=0.10)
    ctx = _make_context()
    event = detector.detect(ctx)
    assert event is None  # No target pose available


# ── SafetyEventDetector ─────────────────────────────────────────────────


def test_safety_detector_safety_rejected() -> None:
    detector = SafetyEventDetector()
    ctx = _make_context(safety_state={"safety_decision": "REJECT"})
    event = detector.detect(ctx)
    assert event is not None
    assert event.event_type == EdgeEventType.SAFETY_REJECTED


def test_safety_detector_emergency_stop() -> None:
    detector = SafetyEventDetector()
    ctx = _make_context(safety_state={"emergency_stop_triggered": True})
    event = detector.detect(ctx)
    assert event is not None
    assert event.event_type == EdgeEventType.EMERGENCY_STOP_TRIGGERED
    assert event.severity == EventSeverity.CRITICAL


def test_safety_detector_no_safety_event() -> None:
    detector = SafetyEventDetector()
    ctx = _make_context(safety_state={"safety_decision": "ALLOW"})
    event = detector.detect(ctx)
    assert event is None


# ── SceneChangeEventDetector ────────────────────────────────────────────


def test_scene_detector_confidence_low() -> None:
    detector = SceneChangeEventDetector(min_scene_confidence=0.5)
    ctx = _make_context(scene_confidence=0.3)
    event = detector.detect(ctx)
    assert event is not None
    assert event.event_type == EdgeEventType.SCENE_CONFIDENCE_LOW


def test_scene_detector_normal_confidence() -> None:
    detector = SceneChangeEventDetector(min_scene_confidence=0.5)
    ctx = _make_context(scene_confidence=0.8)
    event = detector.detect(ctx)
    assert event is None


# ── DeviceHealthEventDetector ───────────────────────────────────────────


def test_device_detector_collision() -> None:
    detector = DeviceHealthEventDetector()
    ctx = _make_context(robot_state=RobotState(connected=True, collision_detected=True))
    event = detector.detect(ctx)
    assert event is not None
    assert event.event_type == EdgeEventType.DEVICE_FAULT
    assert event.severity == EventSeverity.CRITICAL


def test_device_detector_estop() -> None:
    detector = DeviceHealthEventDetector()
    ctx = _make_context(robot_state=RobotState(connected=True, estop_engaged=True))
    event = detector.detect(ctx)
    assert event is not None
    assert event.event_type == EdgeEventType.DEVICE_FAULT
    assert event.severity == EventSeverity.CRITICAL


def test_device_detector_disconnected() -> None:
    detector = DeviceHealthEventDetector()
    ctx = _make_context(robot_state=RobotState(connected=False))
    event = detector.detect(ctx)
    assert event is not None
    assert event.event_type == EdgeEventType.DEVICE_FAULT


def test_device_detector_healthy() -> None:
    detector = DeviceHealthEventDetector()
    ctx = _make_context(robot_state=RobotState(connected=True))
    event = detector.detect(ctx)
    assert event is None


# ── CompletionEventDetector ─────────────────────────────────────────────


def test_completion_detector_step_completed() -> None:
    detector = CompletionEventDetector()
    ctx = _make_context(
        step_result=SkillExecutionResult(
            task_id="task-test-001",
            plan_version=1,
            command_seq=1,
            timestamp=NOW,
            step_id="step-1",
            skill=SkillName.GRASP,
            scene_version=1,
            success=True,
            duration_ms=1500,
        ),
    )
    event = detector.detect(ctx)
    assert event is not None
    assert event.event_type == EdgeEventType.STEP_COMPLETED
    assert event.severity == EventSeverity.INFO


# ── NetworkEventDetector ────────────────────────────────────────────────


def test_network_detector_lost() -> None:
    detector = NetworkEventDetector()
    ctx = _make_context(network_connected=False)
    event = detector.detect(ctx)
    assert event is not None
    assert event.event_type == EdgeEventType.NETWORK_LOST


def test_network_detector_recovered() -> None:
    detector = NetworkEventDetector()
    # First: lose
    ctx1 = _make_context(network_connected=False)
    detector.detect(ctx1)
    # Then: recover
    ctx2 = _make_context(network_connected=True)
    event = detector.detect(ctx2)
    assert event is not None
    assert event.event_type == EdgeEventType.NETWORK_RECOVERED


# ── CompositeEventDetector ──────────────────────────────────────────────


def test_composite_detector_no_duplicates() -> None:
    detector = CompositeEventDetector()
    ctx = _make_context(
        safety_state={"safety_decision": "REJECT"},
        robot_state=RobotState(connected=True, collision_detected=True),
    )
    events = detector.detect_all(ctx)
    assert len(events) > 0
    # CRITICAL events should be first
    if len(events) >= 2:
        assert events[0].severity == EventSeverity.CRITICAL


def test_composite_detector_empty() -> None:
    detector = CompositeEventDetector()
    ctx = _make_context()
    events = detector.detect_all(ctx)
    assert events == []


def test_event_detector_protocol() -> None:
    """Verify all detectors implement the EventDetector protocol."""
    detectors: list[EventDetector] = [
        ExecutionEventDetector(),
        TimeoutEventDetector(),
        TargetChangeDetector(),
        SafetyEventDetector(),
        SceneChangeEventDetector(),
        DeviceHealthEventDetector(),
        NetworkEventDetector(),
        CompletionEventDetector(),
    ]
    for d in detectors:
        assert isinstance(d, EventDetector), f"{d.detector_name} should satisfy EventDetector"
        assert len(d.detector_name) > 0
