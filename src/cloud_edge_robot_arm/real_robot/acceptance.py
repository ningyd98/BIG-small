from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path


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

    def mark_passed(self, level: RealRobotAcceptanceLevel, *, evidence_path: str) -> None:
        if level == RealRobotAcceptanceLevel.NONE:
            raise ValueError("NONE cannot be marked as passed")
        existing = self.current_level()
        highest = level if _LEVEL_ORDER[level] > _LEVEL_ORDER[existing] else existing
        payload = {
            "highest_passed_level": highest.value,
            "last_passed_level": level.value,
            "evidence_path": evidence_path,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )


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
