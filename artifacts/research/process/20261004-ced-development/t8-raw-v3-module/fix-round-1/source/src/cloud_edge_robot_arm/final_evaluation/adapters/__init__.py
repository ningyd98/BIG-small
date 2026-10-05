"""Phase 12 固定 allowlist runner adapter 注册表。"""

from __future__ import annotations

from cloud_edge_robot_arm.final_evaluation.adapters.base import Phase12RunnerAdapter
from cloud_edge_robot_arm.final_evaluation.adapters.isaac import Phase9IsaacAdapter
from cloud_edge_robot_arm.final_evaluation.adapters.moveit_dry_run import Phase10MoveItDryRunAdapter
from cloud_edge_robot_arm.final_evaluation.adapters.mujoco import Phase9MujocoAdapter
from cloud_edge_robot_arm.final_evaluation.adapters.phase8 import Phase8ExperimentRunnerAdapter
from cloud_edge_robot_arm.final_evaluation.adapters.planner_dry_run import (
    Phase112PlannerDryRunAdapter,
)
from cloud_edge_robot_arm.final_evaluation.adapters.simulation_runtime import Phase11RuntimeAdapter
from cloud_edge_robot_arm.final_evaluation.adapters.synthetic_dry_run import (
    Phase10SyntheticDryRunAdapter,
)


def runner_adapter_registry() -> dict[str, Phase12RunnerAdapter]:
    """返回固定 allowlist adapter 映射，不接受客户端提供 runner 名称。"""

    return {
        "PHASE8_EXPERIMENT_RUNNER": Phase8ExperimentRunnerAdapter(),
        "PHASE9_MUJOCO": Phase9MujocoAdapter(),
        "PHASE9_2_ISAAC": Phase9IsaacAdapter(),
        "PHASE10_SYNTHETIC_DRY_RUN": Phase10SyntheticDryRunAdapter(),
        "PHASE10_MOVEIT_RUNTIME_DRY_RUN": Phase10MoveItDryRunAdapter(),
        "PHASE11_SIMULATION_RUNTIME": Phase11RuntimeAdapter(),
        "PHASE11_2_PLANNER_DRY_RUN": Phase112PlannerDryRunAdapter(),
    }
