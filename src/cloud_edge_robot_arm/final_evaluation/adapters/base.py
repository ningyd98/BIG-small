"""Phase 12 runner adapter 基础协议。

Adapter 是 final evaluation 调用真实软件 runner 的唯一入口；它只接收结构化上下文，
不接受任意 shell、脚本路径、URL、环境变量或真实硬件配置。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from cloud_edge_robot_arm.final_evaluation.models import (
    EnvironmentStatus,
    ExecutionSource,
    HardwareClaims,
    Phase12Backend,
    Phase12RunStatus,
)


@dataclass(frozen=True)
class Phase12RunContext:
    """单次 final evaluation runner 调用上下文。"""

    run_id: str
    experiment_id: str
    scenario_id: str
    backend: Phase12Backend
    control_mode: str
    seed: int
    repetition: int
    output_root: Path


@dataclass(frozen=True)
class Phase12AdapterResult:
    """Adapter 归一化输出，供 runner 转成 Phase12Result。"""

    status: Phase12RunStatus
    task_success: bool
    metrics: dict[str, float | int | bool | str]
    events: list[dict[str, Any]]
    execution_source: ExecutionSource
    actual_runner_invoked: bool
    authoritative_for_thesis: bool
    source_artifact_path: str
    source_artifact_hash: str
    source_verifier: str
    environment_status: EnvironmentStatus
    failure_type: str = ""
    hardware_claims: HardwareClaims = field(default_factory=HardwareClaims)


class Phase12RunnerAdapter(Protocol):
    """固定 allowlist runner adapter 协议。"""

    runner_kind: str

    def capability(self) -> dict[str, Any]: ...

    def validate_environment(self, context: Phase12RunContext) -> EnvironmentStatus: ...

    def run(self, context: Phase12RunContext) -> Phase12AdapterResult: ...

    def collect_evidence(self, context: Phase12RunContext) -> dict[str, Any]: ...

    def cancel(self, run_id: str) -> None: ...

    def result_source(self) -> ExecutionSource: ...


def artifact_path(context: Phase12RunContext, filename: str) -> Path:
    """返回单次 run 的相对 evidence 文件路径。"""

    return context.output_root / "source_evidence" / context.run_id / filename


def write_source_artifact(
    context: Phase12RunContext, name: str, payload: dict[str, Any]
) -> tuple[str, str]:
    """写入 adapter source evidence 并返回相对路径和 hash。"""

    path = artifact_path(context, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8"
    )
    rel = path.relative_to(context.output_root).as_posix()
    return rel, sha256_path(path)


def sha256_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
