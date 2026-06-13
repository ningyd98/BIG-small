from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cloud_edge_robot_arm.contracts import (
    CloudCommand,
    CloudDecision,
    CommandAck,
    ControlMode,
    EdgeEvent,
    EdgeEventType,
    FailurePolicy,
    FailureSummary,
    SafetyConstraints,
    SkillName,
    TaskContract,
    TaskState,
    TaskStep,
    TaskTarget,
    Telemetry,
)
from cloud_edge_robot_arm.edge.contract_validator import EdgeContractValidator


def _future_contract(now: datetime, command_seq: int = 1) -> TaskContract:
    return TaskContract(
        task_id="task-red-cube",
        plan_version=1,
        command_seq=command_seq,
        timestamp=now,
        control_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        issued_at=now,
        valid_until=now + timedelta(seconds=5),
        user_instruction="place the red cube into bin a",
        scene_version=7,
        expected_scene_version=7,
        task_target=TaskTarget(
            object_id="red_cube",
            object_class="cube",
            target_region_id="bin_a",
        ),
        steps=[
            TaskStep(
                step_id="step-001",
                skill=SkillName.HOME,
                parameters={},
                expected_duration_ms=500,
                timeout_ms=2_000,
                retry_limit=0,
                preconditions=[],
                success_conditions=["robot_in_safe_pose"],
            ),
            TaskStep(
                step_id="step-002",
                skill=SkillName.MOVE_ABOVE,
                parameters={"object_id": "red_cube", "z_offset_m": 0.12},
                expected_duration_ms=1_000,
                timeout_ms=3_000,
                retry_limit=1,
                preconditions=["target_visible"],
                success_conditions=["tcp_above_target"],
            ),
        ],
        safety_constraints=SafetyConstraints(
            max_joint_velocity=0.5,
            max_tcp_velocity=0.15,
            minimum_safe_height=0.08,
            workspace_id="workspace_a",
            collision_check_required=True,
        ),
        failure_policy=FailurePolicy(
            local_retry_limit=2,
            on_timeout="REQUEST_CLOUD_REPLAN",
            on_safety_rejection="PAUSE_AND_REPORT",
            on_network_loss="SAFE_STOP",
        ),
        completion_criteria=[
            "object_inside_target_region",
            "gripper_released",
            "robot_in_safe_pose",
        ],
    )


def test_contract_and_message_models_share_required_trace_fields() -> None:
    now = datetime(2026, 6, 13, 10, 30, tzinfo=UTC)
    contract = _future_contract(now)
    messages = [
        contract,
        Telemetry(
            task_id=contract.task_id,
            plan_version=contract.plan_version,
            command_seq=contract.command_seq,
            timestamp=now,
            control_mode=contract.control_mode,
            task_state=TaskState.EXECUTING,
            scene_version=contract.scene_version,
            current_step_id="step-001",
            completed_step_ids=[],
            robot_state={"pose": "home"},
            network_state={"online": True},
            diagnostics={},
        ),
        CloudCommand(
            task_id=contract.task_id,
            plan_version=contract.plan_version,
            command_seq=2,
            timestamp=now,
            decision=CloudDecision.KEEP,
            command_ttl_ms=2_500,
            valid_until=now + timedelta(milliseconds=2_500),
            reason="nominal",
        ),
        CommandAck(
            task_id=contract.task_id,
            plan_version=contract.plan_version,
            command_seq=2,
            timestamp=now,
            accepted=True,
            status="ACK",
            error=None,
        ),
        EdgeEvent(
            task_id=contract.task_id,
            plan_version=contract.plan_version,
            command_seq=3,
            timestamp=now,
            event_id="event-001",
            event_type=EdgeEventType.STEP_COMPLETED,
            step_id="step-001",
            severity="INFO",
            details={"duration_ms": 430},
        ),
        FailureSummary(
            task_id=contract.task_id,
            plan_version=contract.plan_version,
            command_seq=4,
            timestamp=now,
            failure_event_id="event-002",
            failed_step_id="step-002",
            completed_step_ids=["step-001"],
            reason="target moved",
            local_retry_count=1,
            current_scene_version=8,
            recovery_hint="request local replan from step-002",
        ),
    ]

    for message in messages:
        assert message.task_id == contract.task_id
        assert message.plan_version >= 1
        assert message.command_seq >= 1
        assert message.timestamp.tzinfo is not None


def test_contract_validator_accepts_valid_contract_and_rejects_replayed_sequence() -> None:
    now = datetime(2026, 6, 13, 10, 30, tzinfo=UTC)
    validator = EdgeContractValidator(min_plan_version=1)
    payload = _future_contract(now).model_dump(mode="json")

    first = validator.accept_payload(payload, now=now)
    second = validator.accept_payload(payload, now=now + timedelta(milliseconds=10))

    assert first.accepted is True
    assert first.contract is not None
    assert second.accepted is False
    assert second.error is not None
    assert second.error.code == "COMMAND_SEQ_REPLAYED"


def test_contract_validator_returns_structured_errors_for_expired_and_unsafe_payloads() -> None:
    now = datetime(2026, 6, 13, 10, 30, tzinfo=UTC)
    expired_payload = _future_contract(now).model_dump(mode="json")
    expired_payload["command_seq"] = 10
    expired_payload["valid_until"] = (now - timedelta(milliseconds=1)).isoformat()

    unknown_skill_payload = _future_contract(now, command_seq=11).model_dump(mode="json")
    unknown_skill_payload["steps"][0]["skill"] = "RUN_ARBITRARY_CODE"

    stale_plan_payload = _future_contract(now, command_seq=12).model_dump(mode="json")
    stale_plan_payload["plan_version"] = 0

    validator = EdgeContractValidator(min_plan_version=1)

    expired = validator.accept_payload(expired_payload, now=now)
    unknown_skill = validator.accept_payload(unknown_skill_payload, now=now)
    stale_plan = validator.accept_payload(stale_plan_payload, now=now)

    assert expired.accepted is False
    assert expired.error is not None
    assert expired.error.code == "CONTRACT_EXPIRED"
    assert unknown_skill.accepted is False
    assert unknown_skill.error is not None
    assert unknown_skill.error.code == "UNSUPPORTED_SKILL"
    assert stale_plan.accepted is False
    assert stale_plan.error is not None
    assert stale_plan.error.code == "STALE_PLAN_VERSION"
