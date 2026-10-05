"""Independent terminal instruction scoring for the fixed MuJoCo S01 task.

This module performs no I/O and supplies no online routing evidence. Its caller
must already have restricted execution to the registered S01 asset. It does not
prevent a model from moving the wrong object before terminal scoring.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_CRITERIA_VERSION = "s01-task-semantics-v1"
_S01_ASSET_SHA256 = "182fb2bc068ba44de394622f819ae444eb7fbe51df5c5311591a8abb97bf6a08"
_COLORS = (
    ("red", "红色"),
    ("blue", "蓝色"),
    ("yellow", "黄色"),
    ("purple", "紫色"),
    ("orange", "橙色"),
    ("green", "绿色"),
    ("cyan", "青色"),
    ("pink", "粉色"),
    ("brown", "棕色"),
    ("black", "黑色"),
    ("white", "白色"),
)
_CANONICAL_INSTRUCTIONS = {
    instruction: english
    for english, chinese in _COLORS
    for instruction in (
        f"Move the {english} block to the green region.",
        f"将{chinese}方块放到绿色区域",
    )
}


def evaluate_s01_task_semantics(instruction: str) -> dict[str, Any]:
    """Score an entire canonical sentence; unsupported language remains UNKNOWN.

    Only outer whitespace is ignored. Negation, multiple tasks, different
    destinations and unlisted paraphrases cannot pass via substring matching.
    """
    target_color = _CANONICAL_INSTRUCTIONS.get(instruction.strip())
    if target_color is None:
        status, reason = "UNKNOWN", "INSTRUCTION_OUTSIDE_S01_ALLOWLIST"
    elif target_color == "red":
        status, reason = "PASS", "CANONICAL_S01_TASK_MATCH"
    else:
        status, reason = "FAIL", "S01_TARGET_COLOR_MISMATCH"
    return {
        "semantic_status": status,
        "semantic_success": status == "PASS",
        "semantic_reason": reason,
        "semantic_criteria_version": _CRITERIA_VERSION,
        "semantic_reference": {
            "scenario_id": "S01_NORMAL_STATIC",
            "asset_path": "assets/robots/franka_panda/scene.xml",
            "asset_sha256": _S01_ASSET_SHA256,
            "target_id": "object",
            "target_color": "red",
            "destination_id": "target_region",
            "destination_color": "green",
            "scope": "FIXED_REGISTERED_S01_ASSET_ONLY",
        },
        "semantic_instruction_target_color": target_color,
        "semantic_used_for_online_routing": False,
    }


def apply_s01_task_semantics(result: Mapping[str, Any], instruction: str) -> dict[str, Any]:
    """Conjoin terminal evidence without mutating the visual episode or its routes."""
    semantics = evaluate_s01_task_semantics(instruction)
    episode_success = result.get("success") is True
    online_complete = result.get("online_reported_complete") is True
    task_success = (
        episode_success
        and online_complete
        and result.get("physical_success") is True
        and result.get("terminal_reason") is None
        and semantics["semantic_success"] is True
    )
    scored = {
        **result,
        **semantics,
        "visual_episode_success": episode_success,
        "visual_episode_status": result.get("status"),
        "success": task_success,
        "task_success": task_success,
        "false_completion": online_complete and not task_success,
    }
    if not task_success:
        if scored.get("status") == "SUCCESS":
            scored["status"] = "FAILED"
        if not scored.get("failure_reason") and not semantics["semantic_success"]:
            scored["failure_reason"] = semantics["semantic_reason"]
    return scored
