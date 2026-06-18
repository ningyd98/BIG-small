"""重规划提示词定义，约束模型只能生成可验证的高层修复方案。

Prompt templates for local replanning.

System prompt enforces strict constraints:
- Preserve completed steps
- No joint angles / PWM / servo pulse / trajectory points
- Only modify within requested scope
- Must not repeat completed GRASP/PLACE/RELEASE
"""

SYSTEM_PROMPT_REPLANNING = (
    "You are a local task replanner for a small robotic arm cloud-edge system.\n"
    "\n"
    "The edge has already completed part of the task and is requesting a local update "
    "due to a specific event.\n"
    "You MUST preserve all successfully completed steps and only modify the failed step "
    "or subsequent steps within the requested scope.\n"
    "\n"
    "STRICT RULES:\n"
    "\n"
    "1. DO NOT modify, delete, or reorder any completed steps.\n"
    "2. DO NOT repeat any completed GRASP, PLACE, or RELEASE actions.\n"
    "3. Use the current robot state as the starting point for the new plan.\n"
    "4. Prefer the minimum scope fix; do NOT regenerate the full plan without "
    "justification.\n"
    "5. Only use allowed registered skills: HOME, OBSERVE, LOCATE_OBJECT, "
    "MOVE_ABOVE, APPROACH, GRASP, LIFT, MOVE_TO_REGION, PLACE, RELEASE, "
    "RETREAT, VERIFY_RESULT, SAFE_STOP.\n"
    "6. DO NOT output joint angles, PWM values, servo pulse widths, or low-level "
    "trajectories.\n"
    "7. Incorporate confirmed_facts from the failure summary; do NOT treat "
    "suspected_causes as facts.\n"
    "8. If scene data is insufficient, return MORE_OBSERVATION_REQUIRED.\n"
    "9. For severe safety events, return NO_REPLAN_SAFETY_STOP.\n"
    "10. Each new step MUST include preconditions, success_conditions, timeout_ms, "
    "and failure strategy.\n"
    "11. Output MUST be a single JSON object conforming to the TaskContract schema.\n"
    "12. DO NOT output Markdown or explanatory text.\n"
    "13. DO NOT bypass the edge safety shield.\n"
    "14. Trusted fields (task_id, plan_version, command_seq, issued_at, "
    "valid_until, timestamp) will be completed by application code.\n"
)

USER_PROMPT_TEMPLATE_REPLANNING = (
    "Original task: {{USER_INSTRUCTION}}\n"
    "\n"
    "Current task contract (completed steps marked):\n"
    "{{CURRENT_CONTRACT}}\n"
    "\n"
    "Completed step IDs: {{COMPLETED_STEP_IDS}}\n"
    "Last successful step ID: {{LAST_SUCCESSFUL_STEP_ID}}\n"
    "Failed step ID: {{FAILED_STEP_ID}}\n"
    "\n"
    "Failure summary:\n"
    "{{FAILURE_SUMMARY}}\n"
    "\n"
    "Current robot state:\n"
    "{{ROBOT_STATE}}\n"
    "\n"
    "Current target state:\n"
    "{{TARGET_STATE}}\n"
    "\n"
    "Current obstacle state:\n"
    "{{OBSTACLE_STATE}}\n"
    "\n"
    "Scene version: {{SCENE_VERSION}}\n"
    "Scene confidence: {{SCENE_CONFIDENCE}}\n"
    "\n"
    "Allowed replan scope: {{REPLAN_SCOPE}}\n"
    "Allowed skills: {{ALLOWED_SKILLS}}\n"
    "\n"
    "Safety constraints:\n"
    "{{SAFETY_CONSTRAINTS}}\n"
    "\n"
    "Return a JSON TaskContract with ONLY the steps that need to be executed "
    "(completed steps are already done).\n"
)


def build_replan_prompt(request: object) -> str:
    """Build the full replan prompt from a LocalReplanningRequest."""
    import json as _json

    template = USER_PROMPT_TEMPLATE_REPLANNING
    template = template.replace(
        "{{USER_INSTRUCTION}}",
        getattr(request, "failed_step_id", "unknown"),
    )
    template = template.replace(
        "{{COMPLETED_STEP_IDS}}",
        _json.dumps(getattr(request, "completed_step_ids", [])),
    )
    template = template.replace(
        "{{LAST_SUCCESSFUL_STEP_ID}}",
        getattr(request, "last_successful_step_id", ""),
    )
    template = template.replace(
        "{{FAILED_STEP_ID}}",
        getattr(request, "failed_step_id", ""),
    )
    template = template.replace(
        "{{REPLAN_SCOPE}}",
        getattr(request, "requested_replan_scope", "FAILED_STEP_AND_REMAINING"),
    )
    template = template.replace(
        "{{SCENE_VERSION}}",
        str(getattr(request, "current_scene_version", 0)),
    )
    template = template.replace(
        "{{SCENE_CONFIDENCE}}",
        str(getattr(request, "scene_confidence", 0.5)),
    )
    current_robot = getattr(request, "current_robot_state", {})
    template = template.replace(
        "{{ROBOT_STATE}}",
        _json.dumps(current_robot) if isinstance(current_robot, dict) else str(current_robot),
    )
    current_target = getattr(request, "current_target_state", {})
    template = template.replace(
        "{{TARGET_STATE}}",
        _json.dumps(current_target) if isinstance(current_target, dict) else str(current_target),
    )
    obstacle = getattr(request, "current_obstacle_state", {})
    template = template.replace(
        "{{OBSTACLE_STATE}}",
        _json.dumps(obstacle) if isinstance(obstacle, dict) else str(obstacle),
    )
    template = template.replace("{{FAILURE_SUMMARY}}", "")
    template = template.replace("{{CURRENT_CONTRACT}}", "")
    template = template.replace("{{ALLOWED_SKILLS}}", "")
    template = template.replace("{{SAFETY_CONSTRAINTS}}", "")
    return SYSTEM_PROMPT_REPLANNING + "\n\n" + template
