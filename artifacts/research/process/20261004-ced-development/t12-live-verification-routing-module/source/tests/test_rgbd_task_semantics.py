"""Independent S01 instruction scoring cannot turn a wrong-object move into success."""

import copy

import pytest


@pytest.mark.parametrize(
    "instruction",
    ["将红色方块放到绿色区域", "Move the red block to the green region."],
)
def test_canonical_s01_instruction_matches_fixed_reference(instruction: str) -> None:
    from cloud_edge_robot_arm.vision.task_semantics import evaluate_s01_task_semantics

    result = evaluate_s01_task_semantics(instruction)
    assert result["semantic_status"] == "PASS"
    assert result["semantic_success"] is True
    assert result["semantic_criteria_version"] == "s01-task-semantics-v2"
    assert result["semantic_reference"]["scenario_id"] == "S01_NORMAL_STATIC"
    assert result["semantic_reference"]["target_color"] == "red"
    assert result["semantic_reference"]["destination_color"] == "green"
    assert len(result["semantic_reference"]["asset_sha256"]) == 64
    assert result["semantic_used_for_online_routing"] is False


@pytest.mark.parametrize(
    "instruction",
    [
        "Move the purple block to the green region.",
        "Move the blue block to the green region.",
        "Move the yellow block to the green region.",
        "Move the orange block to the green region.",
        "将紫色方块放到绿色区域",
        "将蓝色方块放到绿色区域",
        "将黄色方块放到绿色区域",
    ],
)
def test_other_canonical_target_colors_fail_independent_s01_semantics(instruction: str) -> None:
    from cloud_edge_robot_arm.vision.task_semantics import evaluate_s01_task_semantics

    result = evaluate_s01_task_semantics(instruction)
    assert result["semantic_status"] == "FAIL"
    assert result["semantic_success"] is False
    assert result["semantic_reason"] == "S01_TARGET_COLOR_MISMATCH"


@pytest.mark.parametrize(
    "instruction",
    [
        "Do not move the red block to the green region.",
        "不要将红色方块放到绿色区域",
        "Move the red block to the green region. Then move the blue block.",
        "将红色方块放到绿色区域，并抓取蓝色方块",
        "Move the red and blue blocks to the green region.",
        "Move the red block to the blue region.",
        "Move the purple block to the green region. Do not move the red one.",
        "pick and place",
        "",
    ],
)
def test_unrecognized_negated_or_multiple_tasks_remain_unknown(instruction: str) -> None:
    from cloud_edge_robot_arm.vision.task_semantics import evaluate_s01_task_semantics

    result = evaluate_s01_task_semantics(instruction)
    assert result["semantic_status"] == "UNKNOWN"
    assert result["semantic_success"] is False
    assert result["semantic_reason"] == "INSTRUCTION_OUTSIDE_S01_ALLOWLIST"


def test_wrong_object_online_completion_is_retained_as_false_completion() -> None:
    from cloud_edge_robot_arm.vision.task_semantics import apply_s01_task_semantics

    original = {
        "success": True,
        "status": "SUCCESS",
        "online_reported_complete": True,
        "physical_success": True,
        "terminal_reason": None,
        "verification_records": [{"route": "CONTINUE"}],
    }
    before = copy.deepcopy(original)
    scored = apply_s01_task_semantics(original, "Move the purple block to the green region.")
    assert original == before
    assert scored["visual_episode_success"] is True
    assert scored["visual_episode_status"] == "SUCCESS"
    assert scored["online_reported_complete"] is True
    assert scored["physical_success"] is True
    assert scored["semantic_success"] is False
    assert scored["success"] is scored["task_success"] is False
    assert scored["status"] == "FAILED"
    assert scored["false_completion"] is True
    assert scored["verification_records"] == before["verification_records"]


@pytest.mark.parametrize(
    "online,physical,terminal,expected",
    [
        (True, True, None, True),
        (False, True, None, False),
        (True, False, None, False),
        (True, True, "CANCELLED", False),
    ],
)
def test_semantic_match_never_overrides_online_physical_or_terminal_failure(
    online: bool,
    physical: bool,
    terminal: str | None,
    expected: bool,
) -> None:
    from cloud_edge_robot_arm.vision.task_semantics import apply_s01_task_semantics

    scored = apply_s01_task_semantics(
        {
            "success": online and physical and terminal is None,
            "status": "SUCCESS" if expected else "FAILED",
            "online_reported_complete": online,
            "physical_success": physical,
            "terminal_reason": terminal,
        },
        "将红色方块放到绿色区域",
    )
    assert scored["semantic_success"] is True
    assert scored["task_success"] is expected
    assert scored["false_completion"] is (online and not expected)


def test_unknown_instruction_cannot_upgrade_successful_physics() -> None:
    from cloud_edge_robot_arm.vision.task_semantics import apply_s01_task_semantics

    scored = apply_s01_task_semantics(
        {"success": True, "status": "SUCCESS", "online_reported_complete": True},
        "Do not move the red block to the green region.",
    )
    assert scored["semantic_status"] == "UNKNOWN"
    assert scored["task_success"] is False
    assert scored["false_completion"] is True
