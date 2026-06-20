"""仅大模型决策基线 runner。

当前默认只运行 fake-provider 管线验证。真实 OpenAI-compatible 或 Ollama provider 未显式
配置时返回 BLOCKED_BY_ENV，不会静默回退到 fake，也不会触发硬件执行。
"""

from __future__ import annotations

from pathlib import Path

from cloud_edge_robot_arm.experiments.llm_only.evidence import (
    file_hash,
    stable_hash,
    write_json,
    write_jsonl,
)
from cloud_edge_robot_arm.experiments.llm_only.models import (
    LLMOnlyProfile,
    LLMOnlyProvider,
    LLMOnlyRunRecord,
    LLMOnlySummary,
    ModelRuntimeType,
    summary_to_json,
)

PIPELINE_READY = "LLM_ONLY_BASELINE_PIPELINE_READY"
RUNTIME_ACCEPTED = "LLM_ONLY_BASELINE_RUNTIME_ACCEPTED"
BLOCKED_BY_MODEL_ENV = "LLM_ONLY_BASELINE_BLOCKED_BY_MODEL_ENV"

B01 = "B01_LLM_ONLY_ONESHOT"
B02 = "B02_LLM_ONLY_REACTIVE"
B03 = "B03_PROPOSED_ARCHITECTURE_PAIRED_COMPARISON"

SCENARIOS = [
    "S01_NORMAL_STATIC",
    "S02_TARGET_MOVED",
    "S03_OBSTACLE_INSERTED",
    "S04_GRASP_FAILURE",
    "S06_PERCEPTION_DEGRADED",
    "S07_NETWORK_DEGRADED",
    "S08_NETWORK_OUTAGE",
    "S09_CLOUD_UNAVAILABLE",
    "S14_EMERGENCY_STOP",
]


def run_llm_only_baseline(
    *,
    profile: LLMOnlyProfile,
    provider: LLMOnlyProvider,
    output_root: Path,
    model_name: str = "",
) -> dict[str, object]:
    """运行 LLM-only 基线。

    fake provider 只产生管线 evidence；真实 provider 未配置时只记录环境阻塞。
    """

    output_root.mkdir(parents=True, exist_ok=True)
    if provider != LLMOnlyProvider.FAKE:
        return _write_blocked_summary(
            profile=profile,
            provider=provider,
            output_root=output_root,
            model_name=model_name,
        )
    rows = _fake_rows(profile=profile, provider=provider, output_root=output_root)
    row_dicts = [row.model_dump(mode="json") for row in rows]
    write_jsonl(output_root / "runs/llm_only_runs.jsonl", row_dicts)
    summary = LLMOnlySummary(
        status=PIPELINE_READY,
        runtime_status="PIPELINE_ONLY",
        profile=profile,
        provider=provider,
        model_runtime_type=ModelRuntimeType.FAKE_PROVIDER_PIPELINE_TEST,
        run_count=len(rows),
        runtime_completed_count=len(rows),
        model_request_count=sum(row.model_request_count for row in rows),
        model_runtime_accepted=False,
        authoritative_for_model_performance=False,
        unsafe_command_execution_count=0,
        notes=("fake provider 仅验证 LLM-only baseline 管线；不能用于真实大模型性能结论。"),
    )
    payload = summary_to_json(summary)
    write_json(output_root / "aggregates/llm_only_summary.json", payload)
    write_json(
        output_root / "verification/llm_only_verification.json",
        {
            **payload,
            "source_artifact_hash_verified": _verify_row_hashes(output_root, row_dicts),
        },
    )
    return payload


def _fake_rows(
    *,
    profile: LLMOnlyProfile,
    provider: LLMOnlyProvider,
    output_root: Path,
) -> list[LLMOnlyRunRecord]:
    seeds = [0] if profile == LLMOnlyProfile.SMOKE else [0, 1, 2]
    repetitions = 1 if profile == LLMOnlyProfile.SMOKE else 2
    scenarios = SCENARIOS[:3] if profile == LLMOnlyProfile.SMOKE else SCENARIOS
    rows: list[LLMOnlyRunRecord] = []
    index = 1
    for baseline_id in (B01, B02, B03):
        for scenario in scenarios:
            for seed in seeds:
                for repetition in range(repetitions):
                    prompt = f"{baseline_id}|{scenario}|{seed}|{repetition}|fake"
                    response = f"fake-contract:{stable_hash(prompt)[:16]}"
                    response_path = output_root / "responses" / f"llm-only-{index:05d}.json"
                    write_json(
                        response_path,
                        {
                            "baseline_id": baseline_id,
                            "model_runtime_type": ModelRuntimeType.FAKE_PROVIDER_PIPELINE_TEST,
                            "prompt_hash": stable_hash(prompt),
                            "response_hash": stable_hash(response),
                            "sanitized": True,
                            "raw_response_saved": False,
                        },
                    )
                    rows.append(
                        LLMOnlyRunRecord(
                            run_id=f"llm-only-{index:05d}",
                            baseline_id=baseline_id,
                            profile=profile,
                            provider=provider,
                            model_runtime_type=ModelRuntimeType.FAKE_PROVIDER_PIPELINE_TEST,
                            scenario_id=scenario,
                            seed=seed,
                            repetition=repetition,
                            status="SUCCESS",
                            task_success=True,
                            model_request_count=1 if baseline_id != B03 else 0,
                            valid_contract_rate=1.0,
                            schema_validation_failure_count=0,
                            semantic_validation_failure_count=0,
                            repair_count=0,
                            refusal_rate=0.0,
                            unsafe_proposed_action_count=0,
                            prompt_hash=stable_hash(prompt),
                            response_hash=stable_hash(response),
                            source_artifact_path=str(response_path.relative_to(output_root)),
                            source_artifact_hash=file_hash(response_path),
                            notes="FAKE_PROVIDER_PIPELINE_TEST，不代表真实大模型效果。",
                        )
                    )
                    index += 1
    return rows


def _write_blocked_summary(
    *,
    profile: LLMOnlyProfile,
    provider: LLMOnlyProvider,
    output_root: Path,
    model_name: str,
) -> dict[str, object]:
    runtime_type = (
        ModelRuntimeType.REAL_LLM_RUNTIME
        if provider == LLMOnlyProvider.OPENAI_COMPATIBLE
        else ModelRuntimeType.LOCAL_LLM_RUNTIME
    )
    summary = LLMOnlySummary(
        status=BLOCKED_BY_MODEL_ENV,
        runtime_status=BLOCKED_BY_MODEL_ENV,
        profile=profile,
        provider=provider,
        model_runtime_type=ModelRuntimeType.BLOCKED_BY_ENV,
        run_count=0,
        runtime_completed_count=0,
        model_request_count=0,
        model_runtime_accepted=False,
        authoritative_for_model_performance=False,
        blockers=[f"{runtime_type.value}_NOT_CONFIGURED", f"model={model_name or 'UNSPECIFIED'}"],
        notes="未发现 accepted 真实模型运行环境；未自动回退 fake provider。",
    )
    payload = summary_to_json(summary)
    write_json(output_root / "aggregates/llm_only_summary.json", payload)
    write_json(output_root / "verification/llm_only_verification.json", payload)
    return payload


def _verify_row_hashes(output_root: Path, rows: list[dict[str, object]]) -> bool:
    for row in rows:
        rel = str(row.get("source_artifact_path", ""))
        expected = str(row.get("source_artifact_hash", ""))
        if not rel or not expected:
            return False
        path = output_root / rel
        if not path.exists() or file_hash(path) != expected:
            return False
    return True
