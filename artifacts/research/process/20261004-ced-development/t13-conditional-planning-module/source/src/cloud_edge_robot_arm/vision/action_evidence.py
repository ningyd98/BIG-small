"""Bind native action evidence without promoting model claims to sensor bounds.

The current native pipeline has no independently validated geometric/motion bound
certificate. Those quantities therefore stay unavailable even when a grounding
reply or fact map includes a number or a caller VALID flag. A future certified
source requires its own frozen implementation and acceptance before enabling it.
"""

from collections.abc import Mapping

from cloud_edge_robot_arm.contracts.models import TaskContract, TaskStep
from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec, OnlineEvidenceSnapshot
from cloud_edge_robot_arm.edge.evidence.models import ActionEvidenceContract, VisualEvidence
from cloud_edge_robot_arm.vision.observations import RGBDObservation


def native_action_contract(
    online: OnlineEvidenceSnapshot, contract: TaskContract, step: TaskStep,
) -> ActionEvidenceContract:
    observation = RGBDObservation.model_validate(online.observation.model_dump())
    fact = online.visual_facts.get("target_visible")
    confirmed = isinstance(fact, Mapping) and (
        fact.get("source") == "rgbd_estimate"
        and fact.get("observation_id") == observation.observation_id
        and fact.get("target_id") == contract.task_target.object_id
        and fact.get("identity_confirmed") is True
        and fact.get("value") is True
    )

    def specs(names: list[str]) -> tuple[ConditionSpec, ...]:
        return tuple(ConditionSpec(
            name,
            target_id=(contract.task_target.target_region_id if name == "tcp_above_region"
                       else contract.task_target.object_id),
            tolerances={"calibration_version": observation.calibration_version,
                        "minimum_safe_height": contract.safety_constraints.minimum_safe_height},
        ) for name in names)

    evidence = VisualEvidence(
        observation.observation_id, observation.calibration_version or "",
        observation.captured_at,
        geometric_error_bound_m=None, motion_bound_m_s=None,
        identity_status="CONFIRMED" if confirmed else "UNKNOWN",
        sensor_status=("VALID" if any(depth > 0 for depth in observation.depth_values())
                       else "UNKNOWN"),
    )
    return ActionEvidenceContract(
        evidence, max(step.timeout_ms, step.expected_duration_ms) / 1000,
        0.01, ("rgbd",), specs(step.preconditions), specs(step.success_conditions),
        contract.plan_version, contract.command_seq, online.context_hash,
    )
