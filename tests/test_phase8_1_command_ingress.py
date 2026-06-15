from __future__ import annotations

from pathlib import Path

from cloud_edge_robot_arm.contracts import CommandAckStatus
from cloud_edge_robot_arm.experiments.models import (
    CachePolicy,
    ExperimentConfig,
    ExperimentMode,
    FaultProfile,
    NetworkProfileName,
    TaskProfile,
)
from cloud_edge_robot_arm.experiments.runtime_harness import RuntimeExperimentHarness
from cloud_edge_robot_arm.simulation.clock import VirtualClock


def _config(tmp_path: Path) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="phase81-command",
        scenario_id="S10_STALE_DUPLICATE_REORDERED_COMMAND",
        mode=ExperimentMode.PCSC,
        seed=0,
        repetitions=1,
        network_profile=NetworkProfileName.NORMAL,
        fault_profile=FaultProfile(name="commands"),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=1_000,
        timeout_ms=30_000,
        artifact_dir=tmp_path,
    )


def test_s10_command_rejections_are_real_command_acks(tmp_path: Path) -> None:
    harness = RuntimeExperimentHarness(config=_config(tmp_path), clock=VirtualClock())
    contract = harness.create_contract()
    accepted = harness.deliver_cloud_command(contract, request_id="accepted")
    expired = harness.deliver_cloud_command(
        contract.model_copy(update={"command_seq": 2, "valid_until": contract.issued_at}),
        request_id="expired",
    )
    duplicate = harness.deliver_cloud_command(contract, request_id="duplicate")
    conflict = harness.deliver_cloud_command(
        contract.model_copy(update={"user_instruction": "changed"}),
        request_id="conflict",
    )
    stale_seq = harness.deliver_cloud_command(
        contract.model_copy(update={"command_seq": 1, "plan_version": 2}),
        request_id="stale-seq",
    )
    stale_plan = harness.deliver_cloud_command(
        contract.model_copy(update={"command_seq": 3, "plan_version": 0}),
        request_id="stale-plan",
    )
    scene_mismatch = harness.deliver_cloud_command(
        contract.model_copy(update={"command_seq": 4, "scene_version": 99}),
        request_id="scene-mismatch",
    )

    assert accepted.accepted is True
    assert expired.status == CommandAckStatus.REJECTED_EXPIRED.value
    assert duplicate.status == CommandAckStatus.REJECTED_DUPLICATE.value
    assert conflict.status == "REJECTED_IDEMPOTENCY_CONFLICT"
    assert stale_seq.status == "REJECTED_STALE_SEQUENCE"
    assert stale_plan.status == "REJECTED_STALE_PLAN"
    assert scene_mismatch.status == CommandAckStatus.REJECTED_SCENE_MISMATCH.value
    assert harness.observer.task_executor_calls == 0
    assert harness.command_ack_rejection_counts()["REJECTED_EXPIRED"] == 1
