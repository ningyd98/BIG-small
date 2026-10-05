"""Exercise the real default HTTP -> factory -> worker -> v2 terminal evidence path."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from fastapi.testclient import TestClient

from cloud_edge_robot_arm.cloud.api.app import create_app
from cloud_edge_robot_arm.vision.defaults import DEFAULT_FROZEN_DIR
from cloud_edge_robot_arm.vision.top_grasp import calibration_asset_sha256

OUTPUT = Path(__file__).resolve().parent


def main() -> None:
    workbench = OUTPUT / "workbench-v2"
    workbench.mkdir(exist_ok=False)
    for name in (
        "BIGSMALL_VLM_FROZEN_DIR", "BIGSMALL_VLM_PROVIDER", "BIGSMALL_VLM_MODEL",
        "BIGSMALL_VLM_BASE_URL", "BIGSMALL_VLM_API_KEY",
    ):
        os.environ.pop(name, None)
    os.environ.update(
        DASHBOARD_AUTH_MODE="LOCAL_ONLY", MODEL_CONTROL_DB=str(workbench / "model.db"),
        SIMULATION_RUNTIME_DB=str(workbench / "runtime.db"),
        DASHBOARD_ARTIFACT_ROOT=str(workbench / "artifacts"), MUJOCO_GL="egl",
    )
    draft = {
        "backend": "MUJOCO", "input_mode": "RGBD", "execution_scope": "VISION_CLOSED_LOOP",
        "run_type": "SINGLE", "scenarios": ["S01_NORMAL_STATIC"], "control_modes": ["PCSC"],
        "seeds": [0], "repetitions": 1, "user_instruction": "将红色方块放到绿色区域",
        "parameter_overrides": {"timeout_ms": 90000},
        "domain_randomization": {"enabled": False, "level": "NONE"},
        "tags": ["gripper-project-migration"], "description": "Default v2 workbench verification",
    }
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/simulation/runs", json=draft,
            headers={"x-dashboard-role": "EXPERIMENT_OPERATOR"},
        )
        assert response.status_code == 202, response.text
        submitted = response.json()
        run_id = submitted["run_id"]
        (workbench / "submitted.json").write_text(json.dumps(submitted, indent=2) + "\n")
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            run = client.get(f"/api/v1/simulation/runs/{run_id}").json()
            result_path = run.get("artifact_paths", {}).get("result")
            if run["status"] in {"SUCCEEDED", "FAILED", "BLOCKED_BY_ENV", "CANCELLED", "TIMED_OUT"}:
                if result_path and (workbench / "artifacts" / result_path).is_file():
                    break
            time.sleep(0.1)
        else:
            raise TimeoutError("workbench did not publish its terminal evidence")
        result = json.loads((workbench / "artifacts" / result_path).read_text())
        assert run["status"] != "BLOCKED_BY_ENV", result
        assert result["model_calls"] > 0, result
        assert result["semantic_criteria_version"] == "s01-task-semantics-v2"
        reference = result["semantic_reference"]
        assert reference["grasp_profile"] == "mujoco_upright_box_v2"
        assert reference["asset_sha256"] == calibration_asset_sha256("mujoco_upright_box_v2")
        summary = {
            "valid": True, "default_frozen_dir": str(DEFAULT_FROZEN_DIR),
            "run_id": run_id, "runtime_status": run["status"],
            "task_success": result["task_success"], "physical_success": result["physical_success"],
            "model_calls": result["model_calls"], "executed_actions": result["executed_actions"],
            "semantic_criteria_version": result["semantic_criteria_version"],
            "semantic_reference": reference, "result_path": str(result_path),
            "failure_reason": result.get("failure_reason"),
            "terminal_reason": result.get("terminal_reason"),
        }
        (workbench / "run.json").write_text(json.dumps(run, indent=2) + "\n")
        (OUTPUT / "workbench-validation.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
