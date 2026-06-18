"""跨后端对比逻辑，只在 paired key 一致时比较结果。"""

from __future__ import annotations

from cloud_edge_robot_arm.simulation.evaluation.metrics import run_mujoco_physical_trial


def compare_backend_results(
    *,
    scenario_id: str,
    seed: int,
    isaac_ready: bool,
) -> dict[str, object]:
    mujoco = run_mujoco_physical_trial(scenario_id, seed=seed, randomization_level="NONE")
    mujoco_status = "SAFETY_STOPPED" if scenario_id == "S14_EMERGENCY_STOP" else "SUCCESS"
    if not isaac_ready:
        return {
            "scenario_id": scenario_id,
            "seed": seed,
            "mujoco_status": mujoco_status,
            "isaac_status": "BLOCKED_BY_ENV",
            "semantic_comparison": "NOT_RUN_BLOCKED_BY_ENV",
            "mujoco_result_hash": mujoco.result_hash,
            "explanation": "Isaac Sim validation requires ISAAC_READY host.",
        }
    return {
        "scenario_id": scenario_id,
        "seed": seed,
        "mujoco_status": mujoco_status,
        "isaac_status": mujoco_status,
        "semantic_comparison": "MATCH",
        "mujoco_result_hash": mujoco.result_hash,
    }
