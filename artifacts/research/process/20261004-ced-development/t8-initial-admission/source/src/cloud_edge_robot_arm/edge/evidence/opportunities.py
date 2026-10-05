"""离线固定机会回放；真实标签仅供评价，不输入在线门控。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass, replace
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Literal

from pydantic import ConfigDict

from cloud_edge_robot_arm.contracts import Pose, RobotState
from cloud_edge_robot_arm.edge.evidence.conditions import OnlineEvidenceSnapshot
from cloud_edge_robot_arm.edge.evidence.models import (
    ActionEvidenceContract,
    EvidenceVerdict,
    _freeze,
)
from cloud_edge_robot_arm.edge.evidence.validator import validate_b3, validate_evidence
from cloud_edge_robot_arm.vision.observations import RGBDObservation


def _canonical(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _canonical(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


class _FrozenPose(Pose):
    model_config = ConfigDict(frozen=True)


class _FrozenRobotState(RobotState):
    model_config = ConfigDict(frozen=True)


def _snapshot_payload(value: OnlineEvidenceSnapshot | None) -> Any:
    if value is None:
        return None
    return {
        "observation_checksum": value.observation.checksum_sha256,
        "robot_state": value.robot_state.model_dump(mode="json"),
        "visual_facts": _canonical(value.visual_facts),
        "plan_version": value.plan_version,
        "command_seq": value.command_seq,
        "context_hash": value.context_hash,
    }


@dataclass(frozen=True)
class Opportunity:
    """保持原始候选、来源组、快照和独立标签的不可变离线机会。"""

    opportunity_id: str
    group_id: str
    observation: RGBDObservation
    action_contract: ActionEvidenceContract
    oracle_label: Literal["VALID", "INVALID", "UNKNOWN"]
    replay_at: datetime = field(kw_only=True)
    replay_calibration_version: str = field(kw_only=True)
    online_evidence: OnlineEvidenceSnapshot | None = field(default=None, kw_only=True)

    def __post_init__(self) -> None:
        evidence = self.action_contract.evidence
        if not self.opportunity_id or not self.group_id:
            raise ValueError("fixed opportunity identity missing")
        if self.oracle_label not in {"VALID", "INVALID", "UNKNOWN"}:
            raise ValueError("unsupported independent oracle label")
        if (
            evidence.observation_id != self.observation.observation_id
            or evidence.captured_at != self.observation.captured_at
            or evidence.calibration_version != self.observation.calibration_version
        ):
            raise ValueError("action evidence snapshot binding mismatch")
        if self.replay_at.tzinfo is None or self.replay_at.utcoffset() is None:
            raise ValueError("fixed replay clock must be timezone aware")
        if not self.replay_calibration_version:
            raise ValueError("fixed replay calibration configuration missing")
        if self.online_evidence is not None:
            online = self.online_evidence
            if (
                online.observation.checksum_sha256 != self.observation.checksum_sha256
                or online.context_hash != self.action_contract.context_hash
                or online.plan_version != self.action_contract.plan_version
                or online.command_seq != self.action_contract.command_seq
            ):
                raise ValueError("fixed online evidence snapshot binding mismatch")
            state = _FrozenRobotState.model_validate(online.robot_state.model_dump())
            state = state.model_copy(
                update={
                    "tcp_pose": _FrozenPose.model_validate(online.robot_state.tcp_pose.model_dump())
                }
            )
            object.__setattr__(
                self,
                "online_evidence",
                replace(
                    online,
                    robot_state=state,
                    visual_facts=MappingProxyType(
                        {key: _freeze(value) for key, value in online.visual_facts.items()}
                    ),
                ),
            )

    @property
    def content_hash(self) -> str:
        """绑定机会的全部不可变输入，阻止混用已变更的机会和旧判定。"""
        payload = {
            "opportunity_id": self.opportunity_id,
            "group_id": self.group_id,
            "observation_checksum": self.observation.checksum_sha256,
            "action_contract": _canonical(self.action_contract),
            "oracle_label": self.oracle_label,
            "replay_at": self.replay_at.isoformat(),
            "replay_calibration_version": self.replay_calibration_version,
            "online_evidence": _snapshot_payload(self.online_evidence),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()


@dataclass(frozen=True)
class GateReplayRecord:
    """固定机会判定记录；附属输入散列只供完整性审计。"""

    opportunity_id: str
    method_id: str
    verdict: EvidenceVerdict
    opportunity_hash: str

    def __post_init__(self) -> None:
        if self.method_id not in {"JOINT", "B3"}:
            raise ValueError("unsupported gate replay method")
        if not self.opportunity_id or not self.opportunity_hash:
            raise ValueError("gate replay identity missing")


def _unique(values: Sequence[Opportunity]) -> dict[str, Opportunity]:
    result = {value.opportunity_id: value for value in values}
    if len(result) != len(values):
        raise ValueError("duplicate fixed opportunity")
    if not result:
        raise ValueError("fixed opportunities missing")
    return result


def replay_opportunities(
    values: Sequence[Opportunity],
    method_id: Literal["JOINT", "B3"],
    now: datetime,
    calibration_version: str,
) -> list[GateReplayRecord]:
    """对全部固定机会回放，不按政策选择或独立标签过滤分母。"""
    _unique(values)
    if method_id not in {"JOINT", "B3"}:
        raise ValueError("unsupported gate replay method")
    validator = validate_b3 if method_id == "B3" else validate_evidence
    if any(
        value.replay_at != now or value.replay_calibration_version != calibration_version
        for value in values
    ):
        raise ValueError("replay clock or configuration differs from fixed inputs")
    return [
        GateReplayRecord(
            value.opportunity_id,
            method_id,
            validator(
                value.action_contract,
                now,
                value.action_contract.context_hash,
                calibration_version,
                online_evidence=value.online_evidence,
            ),
            value.content_hash,
        )
        for value in values
    ]


def summarize_gate_replay(
    values: Sequence[Opportunity],
    records: Sequence[GateReplayRecord],
) -> dict[str, Any]:
    """分列误放行、错误拒绝与未知层；UNKNOWN 不计作错误拒绝。"""
    fixed = _unique(values)
    by_id = {record.opportunity_id: record for record in records}
    if len(by_id) != len(records) or set(by_id) != set(fixed):
        raise ValueError("replay must contain exactly the complete fixed opportunity set")
    if len({record.method_id for record in records}) != 1:
        raise ValueError("mixed replay methods")
    if any(by_id[key].opportunity_hash != value.content_hash for key, value in fixed.items()):
        raise ValueError("changed opportunity snapshot or candidate")
    valid = invalid = oracle_unknown = false_acceptance = false_rejection = 0
    unknown_on_valid = unknown_on_invalid = 0
    for key, value in fixed.items():
        status = by_id[key].verdict.status
        if value.oracle_label == "VALID":
            valid += 1
            false_rejection += status == "INVALID"
            unknown_on_valid += status == "UNKNOWN"
        elif value.oracle_label == "INVALID":
            invalid += 1
            false_acceptance += status == "VALID"
            unknown_on_invalid += status == "UNKNOWN"
        else:
            oracle_unknown += 1
    return {
        "total": len(fixed),
        "method_id": records[0].method_id,
        "eligible_valid": valid,
        "eligible_invalid": invalid,
        "oracle_unknown": oracle_unknown,
        "false_acceptance": false_acceptance,
        "false_rejection": false_rejection,
        "unknown_on_valid": unknown_on_valid,
        "unknown_on_invalid": unknown_on_invalid,
        "false_acceptance_rate": false_acceptance / invalid if invalid else None,
        "false_rejection_rate": false_rejection / valid if valid else None,
    }
