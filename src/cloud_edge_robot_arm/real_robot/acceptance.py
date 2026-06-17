from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


class RealRobotAcceptanceLevel(StrEnum):
    NONE = "NONE"
    LEVEL_0 = "LEVEL_0"
    LEVEL_1 = "LEVEL_1"
    LEVEL_2 = "LEVEL_2"
    LEVEL_3 = "LEVEL_3"
    LEVEL_4 = "LEVEL_4"
    LEVEL_5 = "LEVEL_5"
    LEVEL_6 = "LEVEL_6"


_LEVEL_ORDER: dict[RealRobotAcceptanceLevel, int] = {
    level: index for index, level in enumerate(RealRobotAcceptanceLevel)
}


class RealRobotAcceptanceStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def current_level(self) -> RealRobotAcceptanceLevel:
        if not self._path.exists():
            return RealRobotAcceptanceLevel.NONE
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        return RealRobotAcceptanceLevel(payload.get("highest_passed_level", "NONE"))

    def is_allowed(self, required: RealRobotAcceptanceLevel) -> bool:
        return _LEVEL_ORDER[self.current_level()] >= _LEVEL_ORDER[required]

    def mark_passed(
        self,
        level: RealRobotAcceptanceLevel,
        *,
        evidence_path: str | Path,
        config_hash: str,
        source_tree_hash: str,
        robot_identity_hash: str,
        operator_confirmation: dict[str, object],
    ) -> None:
        if level == RealRobotAcceptanceLevel.NONE:
            raise ValueError("NONE cannot be marked as passed")
        path = Path(evidence_path)
        if not path.exists():
            raise ValueError("acceptance evidence file does not exist")
        evidence = _read_json(path)
        _validate_acceptance_evidence(
            evidence,
            level=level,
            config_hash=config_hash,
            source_tree_hash=source_tree_hash,
            robot_identity_hash=robot_identity_hash,
            operator_confirmation=operator_confirmation,
        )
        existing_payload = self._payload()
        existing = RealRobotAcceptanceLevel(existing_payload.get("highest_passed_level", "NONE"))
        if _LEVEL_ORDER[level] > _LEVEL_ORDER[existing] + 1:
            raise ValueError("acceptance levels must be passed sequentially")
        if existing != RealRobotAcceptanceLevel.NONE:
            if existing_payload.get("config_hash") != config_hash:
                existing = RealRobotAcceptanceLevel.NONE
            if existing_payload.get("robot_identity_hash") != robot_identity_hash:
                existing = RealRobotAcceptanceLevel.NONE
        highest = level if _LEVEL_ORDER[level] > _LEVEL_ORDER[existing] else existing
        history = existing_payload.get("history", [])
        if not isinstance(history, list):
            history = []
        record = {
            "level": level.value,
            "evidence_path": str(path),
            "config_hash": config_hash,
            "source_tree_hash": source_tree_hash,
            "robot_identity_hash": robot_identity_hash,
            "operator_confirmation": operator_confirmation,
            "accepted_at": datetime.now(UTC).isoformat(),
        }
        history.append(record)
        payload = {
            "highest_passed_level": highest.value,
            "last_passed_level": level.value,
            "evidence_path": str(path),
            "config_hash": config_hash,
            "source_tree_hash": source_tree_hash,
            "robot_identity_hash": robot_identity_hash,
            "operator_confirmation": operator_confirmation,
            "history": history,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(self._path, payload)

    def _payload(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"highest_passed_level": RealRobotAcceptanceLevel.NONE.value, "history": []}
        payload = _read_json(self._path)
        if not isinstance(payload, dict):
            return {"highest_passed_level": RealRobotAcceptanceLevel.NONE.value, "history": []}
        return payload


def required_level_for_skill(skill_name: str) -> RealRobotAcceptanceLevel:
    mapping = {
        "read_only_state": RealRobotAcceptanceLevel.LEVEL_0,
        "safe_stop": RealRobotAcceptanceLevel.LEVEL_1,
        "single_joint_small_motion": RealRobotAcceptanceLevel.LEVEL_2,
        "tcp_free_space_small_motion": RealRobotAcceptanceLevel.LEVEL_3,
        "named_pose_home": RealRobotAcceptanceLevel.LEVEL_4,
        "empty_grasp_flow": RealRobotAcceptanceLevel.LEVEL_5,
        "soft_object_low_speed_grasp": RealRobotAcceptanceLevel.LEVEL_6,
    }
    return mapping.get(skill_name, RealRobotAcceptanceLevel.LEVEL_6)


def level_definition(level: RealRobotAcceptanceLevel) -> dict[str, object]:
    definitions: dict[RealRobotAcceptanceLevel, dict[str, object]] = {
        RealRobotAcceptanceLevel.LEVEL_0: {
            "motion_allowed": False,
            "actions": ["read_controller_state", "read_estop_state", "read_joint_state"],
        },
        RealRobotAcceptanceLevel.LEVEL_1: {
            "motion_allowed": False,
            "actions": ["safe_stop", "controller_enable_disable"],
        },
        RealRobotAcceptanceLevel.LEVEL_2: {
            "motion_allowed": True,
            "actions": ["single_joint_small_motion"],
            "max_displacement_rad": 0.05,
        },
        RealRobotAcceptanceLevel.LEVEL_3: {
            "motion_allowed": True,
            "actions": ["tcp_free_space_small_motion"],
            "max_tcp_displacement_m": 0.03,
        },
        RealRobotAcceptanceLevel.LEVEL_4: {
            "motion_allowed": True,
            "actions": ["named_pose_home", "named_pose_safe"],
        },
        RealRobotAcceptanceLevel.LEVEL_5: {
            "motion_allowed": True,
            "actions": ["empty_grasp_flow"],
        },
        RealRobotAcceptanceLevel.LEVEL_6: {
            "motion_allowed": True,
            "actions": ["soft_object_low_speed_grasp"],
        },
    }
    return definitions.get(level, {"motion_allowed": False, "actions": []})


def _validate_acceptance_evidence(
    evidence: dict[str, Any],
    *,
    level: RealRobotAcceptanceLevel,
    config_hash: str,
    source_tree_hash: str,
    robot_identity_hash: str,
    operator_confirmation: dict[str, object],
) -> None:
    if evidence.get("status") not in {"ACCEPTED", "LEVEL_ACCEPTED"}:
        raise ValueError("acceptance evidence status is not accepted")
    if evidence.get("requested_level") != level.value:
        raise ValueError("acceptance evidence requested_level mismatch")
    if evidence.get("config_hash") != config_hash:
        raise ValueError("acceptance evidence config_hash mismatch")
    if evidence.get("source_tree_hash") != source_tree_hash:
        raise ValueError("acceptance evidence source_tree_hash mismatch")
    if evidence.get("robot_identity_hash") != robot_identity_hash:
        raise ValueError("acceptance evidence robot_identity_hash mismatch")
    evidence_confirmation = evidence.get("operator_confirmation")
    if not isinstance(evidence_confirmation, dict):
        raise ValueError("acceptance evidence operator_confirmation is missing")
    expected_confirmation = operator_confirmation.get("confirmation_id")
    if (
        not expected_confirmation
        or evidence_confirmation.get("confirmation_id") != expected_confirmation
    ):
        raise ValueError("acceptance evidence operator_confirmation mismatch")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("acceptance JSON must be an object")
    return payload


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        delete=False,
        prefix=f".{path.name}.",
    ) as handle:
        handle.write(json.dumps(payload, sort_keys=True, indent=2) + "\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)
