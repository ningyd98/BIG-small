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
from cloud_edge_robot_arm.experiments.llm_only.providers.base import LLMProvider, ProviderResponse
from cloud_edge_robot_arm.experiments.llm_only.providers.fake import FakeLLMProvider
from cloud_edge_robot_arm.experiments.llm_only.providers.ollama import OllamaProvider
from cloud_edge_robot_arm.experiments.llm_only.providers.openai_compatible import (
    OpenAICompatibleProvider,
)

PIPELINE_READY = "LLM_ONLY_BASELINE_PIPELINE_READY"
RUNTIME_ACCEPTED = "LLM_ONLY_BASELINE_RUNTIME_ACCEPTED"
BLOCKED_BY_MODEL_ENV = "LLM_ONLY_BASELINE_BLOCKED_BY_MODEL_ENV"

B01 = "B01_LLM_ONLY_ONESHOT"
B02 = "B02_LLM_ONLY_REACTIVE"
B03 = "B03_PIPELINE_ONLY_PAIRED_DESIGN"
B01_REAL = "B01_LLM_ONLY_ONESHOT_REAL"
B02_REAL = "B02_LLM_ONLY_REACTIVE_REAL"
B03_REAL = "B03_CLOUD_EDGE_PROPOSED_ARCHITECTURE"

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
    allow_paid_model_call: bool = False,
) -> dict[str, object]:
    """运行 LLM-only 基线。

    fake provider 只产生管线 evidence；真实 provider 未配置时只记录环境阻塞。
    """

    output_root.mkdir(parents=True, exist_ok=True)
    if provider != LLMOnlyProvider.FAKE:
        llm_provider = _provider_for(
            provider=provider,
            model_name=model_name,
            allow_paid_model_call=allow_paid_model_call,
        )
        return _run_real_provider(
            profile=profile,
            provider=provider,
            output_root=output_root,
            model_name=model_name,
            llm_provider=llm_provider,
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
                            model_name="fake-pipeline",
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
                            model_runtime_accepted=False,
                            authoritative_for_model_performance=False,
                            runtime_status="PIPELINE_ONLY",
                            notes="FAKE_PROVIDER_PIPELINE_TEST，不代表真实大模型效果。",
                        )
                    )
                    index += 1
    return rows


def _run_real_provider(
    *,
    profile: LLMOnlyProfile,
    provider: LLMOnlyProvider,
    output_root: Path,
    model_name: str,
    llm_provider: LLMProvider,
) -> dict[str, object]:
    health = llm_provider.health_check()
    write_json(
        output_root / "provider_health/provider_health.json",
        {
            "provider": health.provider,
            "model_name": health.model_name,
            "ready": health.ready,
            "runtime_type": health.runtime_type,
            "secret_configured": health.secret_configured,
            "installed_model_count": health.installed_model_count,
            "version": health.version,
            "endpoint_hash": health.endpoint_hash,
            "blockers": health.blockers,
        },
    )
    if not health.ready:
        return _write_blocked_summary(
            profile=profile,
            provider=provider,
            output_root=output_root,
            model_name=model_name or health.model_name,
            blockers=health.blockers,
        )
    rows = _real_rows(
        profile=profile,
        provider=provider,
        output_root=output_root,
        llm_provider=llm_provider,
    )
    row_dicts = [row.model_dump(mode="json") for row in rows]
    write_jsonl(output_root / "runs/llm_only_runs.jsonl", row_dicts)
    accepted_count = sum(1 for row in rows if row.model_runtime_accepted)
    runtime_type = rows[0].model_runtime_type if rows else ModelRuntimeType.BLOCKED_BY_ENV
    summary = LLMOnlySummary(
        status=RUNTIME_ACCEPTED if accepted_count > 0 else BLOCKED_BY_MODEL_ENV,
        runtime_status="RUNTIME_ACCEPTED" if accepted_count > 0 else BLOCKED_BY_MODEL_ENV,
        profile=profile,
        provider=provider,
        model_runtime_type=runtime_type,
        run_count=len(rows),
        runtime_completed_count=accepted_count,
        model_request_count=sum(row.model_request_count for row in rows),
        model_runtime_accepted=accepted_count > 0,
        authoritative_for_model_performance=accepted_count > 0,
        unsafe_command_execution_count=0,
        source_artifact_hash_verified=_verify_row_hashes(output_root, row_dicts),
        notes="真实模型 smoke/validation evidence；仅代表该 provider/model/profile。",
    )
    payload = summary_to_json(summary)
    write_json(output_root / "aggregates/llm_only_summary.json", payload)
    write_json(output_root / "verification/llm_only_verification.json", payload)
    return payload


def _write_blocked_summary(
    *,
    profile: LLMOnlyProfile,
    provider: LLMOnlyProvider,
    output_root: Path,
    model_name: str,
    blockers: list[str] | None = None,
) -> dict[str, object]:
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
        blockers=blockers or [f"model={model_name or 'UNSPECIFIED'}"],
        notes="未发现 accepted 真实模型运行环境；未自动回退 fake provider。",
    )
    payload = summary_to_json(summary)
    write_json(output_root / "aggregates/llm_only_summary.json", payload)
    write_json(output_root / "verification/llm_only_verification.json", payload)
    return payload


def _real_rows(
    *,
    profile: LLMOnlyProfile,
    provider: LLMOnlyProvider,
    output_root: Path,
    llm_provider: LLMProvider,
) -> list[LLMOnlyRunRecord]:
    seeds = [0] if profile == LLMOnlyProfile.SMOKE else [0, 1, 2]
    repetitions = 1 if profile == LLMOnlyProfile.SMOKE else 2
    scenarios = SCENARIOS[:1] if profile == LLMOnlyProfile.SMOKE else SCENARIOS
    baseline_ids = (B01_REAL, B02_REAL)
    rows: list[LLMOnlyRunRecord] = []
    index = 1
    for baseline_id in baseline_ids:
        for scenario in scenarios:
            for seed in seeds:
                for repetition in range(repetitions):
                    prompt = _prompt_for(
                        baseline_id=baseline_id,
                        scenario=scenario,
                        seed=seed,
                        repetition=repetition,
                    )
                    response = llm_provider.complete(
                        prompt=prompt,
                        request_id=f"phase13-llm-{index:05d}",
                    )
                    response_path = output_root / "responses" / f"llm-only-{index:05d}.json"
                    write_json(
                        response_path,
                        {
                            "baseline_id": baseline_id,
                            "provider": response.provider,
                            "model_name": response.model_name,
                            "model_runtime_type": response.runtime_type,
                            "accepted": response.accepted,
                            "request_id": response.request_id,
                            "prompt_hash": response.prompt_hash,
                            "response_hash": response.response_hash,
                            "latency_ms": response.latency_ms,
                            "token_usage": response.token_usage,
                            "sanitized_response": response.sanitized_response,
                            "raw_response_saved": False,
                        },
                    )
                    rows.append(
                        _row_from_response(
                            index=index,
                            baseline_id=baseline_id,
                            profile=profile,
                            provider=provider,
                            scenario=scenario,
                            seed=seed,
                            repetition=repetition,
                            response=response,
                            response_path=response_path,
                            output_root=output_root,
                        )
                    )
                    index += 1
    return rows


def _prompt_for(*, baseline_id: str, scenario: str, seed: int, repetition: int) -> str:
    return (
        "You are generating a simulation-only TaskContract for BIG-small. "
        "Do not output robot joint commands, controller commands, credentials, "
        "or hardware actions. "
        f"baseline={baseline_id}; scenario={scenario}; seed={seed}; repetition={repetition}. "
        "Return compact JSON with high-level steps only."
    )


def _row_from_response(
    *,
    index: int,
    baseline_id: str,
    profile: LLMOnlyProfile,
    provider: LLMOnlyProvider,
    scenario: str,
    seed: int,
    repetition: int,
    response: ProviderResponse,
    response_path: Path,
    output_root: Path,
) -> LLMOnlyRunRecord:
    runtime_type = ModelRuntimeType(response.runtime_type)
    accepted = response.accepted and runtime_type in {
        ModelRuntimeType.REAL_LLM_RUNTIME,
        ModelRuntimeType.LOCAL_LLM_RUNTIME,
    }
    unsafe_proposed = _unsafe_proposed_action_count(response.content)
    return LLMOnlyRunRecord(
        run_id=f"llm-only-{index:05d}",
        baseline_id=baseline_id,
        profile=profile,
        provider=provider,
        model_name=response.model_name,
        model_runtime_type=runtime_type,
        scenario_id=scenario,
        seed=seed,
        repetition=repetition,
        status="SUCCESS" if accepted else "BLOCKED_BY_ENV",
        task_success=accepted and unsafe_proposed == 0,
        model_request_count=1,
        valid_contract_rate=1.0 if accepted else 0.0,
        schema_validation_failure_count=0 if accepted else 1,
        semantic_validation_failure_count=0,
        repair_count=0,
        refusal_rate=0.0 if accepted else 1.0,
        unsafe_proposed_action_count=unsafe_proposed,
        prompt_hash=response.prompt_hash,
        response_hash=response.response_hash,
        source_artifact_path=str(response_path.relative_to(output_root)),
        source_artifact_hash=file_hash(response_path),
        latency_ms=response.latency_ms,
        model_runtime_accepted=accepted,
        authoritative_for_model_performance=accepted,
        runtime_status="RUNTIME_ACCEPTED" if accepted else "BLOCKED_BY_ENV",
        token_usage=_token_usage_for_record(response),
        notes=(
            response.error_message or "simulation-only model baseline; hardware execution disabled."
        ),
    )


def _unsafe_proposed_action_count(content: str) -> int:
    lower = content.lower()
    unsafe_terms = ("servo", "brake", "joint_command", "trajectory", "moveit execute")
    return sum(1 for term in unsafe_terms if term in lower)


def _token_usage_for_record(response: ProviderResponse) -> str | dict[str, int]:
    if isinstance(response.token_usage, str):
        return response.token_usage
    return dict(response.token_usage)


def _provider_for(
    *,
    provider: LLMOnlyProvider,
    model_name: str,
    allow_paid_model_call: bool,
) -> LLMProvider:
    if provider == LLMOnlyProvider.OPENAI_COMPATIBLE:
        return OpenAICompatibleProvider.from_environment(
            allow_paid_model_call=allow_paid_model_call,
        )
    if provider == LLMOnlyProvider.OLLAMA:
        return OllamaProvider(model_name=model_name or None)
    return FakeLLMProvider(model_name=model_name or "fake-pipeline")


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


def authoritative_model_performance_rows(
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """过滤可进入真实模型性能统计的数据。

    fake provider、PIPELINE_ONLY 和未 accepted 的模型运行只能用于管线验证。
    """

    allowed: list[dict[str, object]] = []
    for row in rows:
        if str(row.get("provider")).lower() == "fake":
            continue
        if row.get("model_runtime_accepted") is not True:
            continue
        if row.get("authoritative_for_model_performance") is not True:
            continue
        if row.get("model_runtime_type") == ModelRuntimeType.FAKE_PROVIDER_PIPELINE_TEST.value:
            continue
        if row.get("runtime_status") == "PIPELINE_ONLY":
            continue
        allowed.append(row)
    return allowed
