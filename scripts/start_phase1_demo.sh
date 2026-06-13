#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ ! -d .venv ]]; then
  "$PYTHON_BIN" -m venv .venv
fi

. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest -q

python - <<'PY'
import json

from cloud_edge_robot_arm.contracts import SkillName, TaskStep
from cloud_edge_robot_arm.edge.skill_executor import SkillExecutor
from cloud_edge_robot_arm.edge.skill_registry import SkillRegistry
from cloud_edge_robot_arm.simulation.mock_robot import MockRobotAdapter, MockScene


def step(step_id: str, skill: SkillName, **parameters: object) -> TaskStep:
    return TaskStep(
        step_id=step_id,
        skill=skill,
        parameters=parameters,
        expected_duration_ms=500,
        timeout_ms=2_000,
        retry_limit=0,
        preconditions=[],
        success_conditions=[],
    )


robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene())
executor = SkillExecutor(robot=robot, registry=SkillRegistry.default())
steps = [
    step("step-001", SkillName.HOME),
    step("step-002", SkillName.OBSERVE),
    step("step-003", SkillName.LOCATE_OBJECT, object_id="red_cube"),
    step("step-004", SkillName.MOVE_ABOVE, object_id="red_cube", z_offset_m=0.12),
    step("step-005", SkillName.APPROACH, object_id="red_cube"),
    step("step-006", SkillName.GRASP, object_id="red_cube"),
    step("step-007", SkillName.LIFT, height_m=0.16),
    step("step-008", SkillName.MOVE_TO_REGION, region_id="bin_a"),
    step("step-009", SkillName.PLACE, region_id="bin_a"),
    step("step-010", SkillName.RELEASE),
    step("step-011", SkillName.RETREAT, distance_m=0.1),
    step("step-012", SkillName.VERIFY_RESULT, object_id="red_cube", region_id="bin_a"),
]

results = [
    executor.execute_step(
        item,
        task_id="demo-red-cube",
        plan_version=1,
        command_seq=index,
        scene_version=robot.scene_version,
    )
    for index, item in enumerate(steps, start=1)
]

print(
    json.dumps(
        {
            "task_id": "demo-red-cube",
            "all_steps_success": all(result.success for result in results),
            "final_region": robot.object_region("red_cube"),
            "scene_version": robot.scene_version,
            "history": [entry.skill for entry in robot.history],
        },
        ensure_ascii=False,
        indent=2,
    )
)
PY
