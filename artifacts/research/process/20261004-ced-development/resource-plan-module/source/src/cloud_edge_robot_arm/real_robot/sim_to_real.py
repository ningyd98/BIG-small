"""Sim-to-real 准入检查模型。

该模块只比较仿真与真实证据指标是否具备进入下一阶段的条件，不执行硬件动作。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

REQUIRED_SIM_TO_REAL_METRICS = {
    "planning_time_ms",
    "actual_execution_time_ms",
    "tcp_trajectory_length_m",
    "final_position_error_m",
    "skill_duration_ms",
    "safety_interventions",
    "retry_count",
    "success_rate",
}


class SimToRealPair(BaseModel):
    model_config = ConfigDict(frozen=True)

    pair_id: str = Field(min_length=1)
    task_contract_hash: str = Field(min_length=1)
    simulation_backend: str = Field(min_length=1)
    real_backend: str = Field(min_length=1)
    software_commit: str = Field(min_length=1)
    metrics: dict[str, Any]
    gap_labels: list[str]

    @model_validator(mode="after")
    def validate_pair(self) -> SimToRealPair:
        if self.real_backend.lower() in {"mock", "fake", "mujoco", "isaac", "simulation"}:
            raise ValueError("sim-to-real pair requires real hardware backend identity")
        missing = sorted(REQUIRED_SIM_TO_REAL_METRICS - set(self.metrics))
        if missing:
            raise ValueError(f"missing sim-to-real metrics: {', '.join(missing)}")
        return self


def summarize_pairs(pairs: list[SimToRealPair]) -> dict[str, Any]:
    return {
        "pair_count": len(pairs),
        "required_metrics": sorted(REQUIRED_SIM_TO_REAL_METRICS),
        "validation_claimed": bool(pairs),
    }
