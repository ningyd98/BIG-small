"""仅大模型基线框架测试。

测试目标是约束 fake provider 只能验证管线，不能被写成真实大模型 runtime evidence。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pytest import MonkeyPatch
from scripts.analyze_phase13_1 import main as analyze_phase13_main
from scripts.verify_phase13_1 import main as verify_phase13_main

from cloud_edge_robot_arm.experiments.llm_only.providers.fake import FakeLLMProvider
from cloud_edge_robot_arm.experiments.llm_only.providers.ollama import OllamaProvider
from cloud_edge_robot_arm.experiments.llm_only.providers.openai_compatible import (
    OpenAICompatibleProvider,
)
from cloud_edge_robot_arm.experiments.llm_only.runner import (
    LLMOnlyProfile,
    LLMOnlyProvider,
    authoritative_model_performance_rows,
    run_llm_only_baseline,
)


def test_fake_provider_smoke_is_pipeline_ready_not_runtime_accepted(tmp_path: Path) -> None:
    """fake provider smoke 只能输出 pipeline ready，并保留 simulation-only 安全声明。"""

    output = tmp_path / "llm_only"
    summary = run_llm_only_baseline(
        profile=LLMOnlyProfile.SMOKE,
        provider=LLMOnlyProvider.FAKE,
        output_root=output,
    )

    assert summary["status"] == "LLM_ONLY_BASELINE_PIPELINE_READY"
    assert summary["runtime_status"] != "LLM_ONLY_BASELINE_RUNTIME_ACCEPTED"
    assert summary["model_runtime_type"] == "FAKE_PROVIDER_PIPELINE_TEST"
    assert summary["contains_secret"] is False
    assert summary["unsafe_command_execution_count"] == 0
    assert summary["real_controller_contacted"] is False
    assert summary["hardware_motion_observed"] is False
    assert summary["hardware_write_operations"] == []

    rows = [
        json.loads(line)
        for line in (output / "runs/llm_only_runs.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert rows
    assert all(row["safety_shield_checked"] is True for row in rows)
    assert all(row["hardware_execution"] is False for row in rows)
    assert all(row["model_runtime_type"] == "FAKE_PROVIDER_PIPELINE_TEST" for row in rows)


def test_fake_provider_validation_is_not_model_performance_evidence(tmp_path: Path) -> None:
    """validation+fake 不得生成真实模型性能结论。"""

    summary = run_llm_only_baseline(
        profile=LLMOnlyProfile.VALIDATION,
        provider=LLMOnlyProvider.FAKE,
        output_root=tmp_path / "llm_only_validation",
    )

    assert summary["status"] == "LLM_ONLY_BASELINE_PIPELINE_READY"
    assert summary["model_runtime_accepted"] is False
    assert summary["authoritative_for_model_performance"] is False


def test_fake_provider_rows_are_excluded_from_authoritative_model_performance(
    tmp_path: Path,
) -> None:
    """fake、PIPELINE_ONLY 和未 accepted 的模型数据必须全部排除出性能数据集。"""

    output = tmp_path / "llm_only"
    run_llm_only_baseline(
        profile=LLMOnlyProfile.SMOKE,
        provider=LLMOnlyProvider.FAKE,
        output_root=output,
    )
    rows = [
        json.loads(line)
        for line in (output / "runs/llm_only_runs.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert authoritative_model_performance_rows(rows) == []


def test_openai_provider_requires_paid_call_authorization(monkeypatch: MonkeyPatch) -> None:
    """存在 API key 但没有显式授权时不得发起真实推理请求。"""

    monkeypatch.setenv("BIGSMALL_LLM_BASE_URL", "https://llm.example.test/v1")
    monkeypatch.setenv("BIGSMALL_LLM_API_KEY", "sk-test-secret")
    monkeypatch.setenv("BIGSMALL_LLM_MODEL", "example-model")
    called = False

    def fake_transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout: float,
    ) -> dict[str, Any]:
        assert url
        assert payload
        assert headers
        assert timeout
        nonlocal called
        called = True
        raise AssertionError("transport must not be called without authorization")

    provider = OpenAICompatibleProvider.from_environment(
        allow_paid_model_call=False,
        transport=fake_transport,
    )

    health = provider.health_check()

    assert health.ready is False
    assert "PAID_MODEL_CALL_NOT_AUTHORIZED" in health.blockers
    assert health.secret_configured is True
    assert called is False


def test_openai_provider_sanitizes_successful_response(monkeypatch: MonkeyPatch) -> None:
    """授权后 OpenAI-compatible provider 记录 hash 和 usage，但不暴露 secret。"""

    monkeypatch.setenv("BIGSMALL_LLM_BASE_URL", "https://llm.example.test/v1")
    monkeypatch.setenv("BIGSMALL_LLM_API_KEY", "sk-test-secret")
    monkeypatch.setenv("BIGSMALL_LLM_MODEL", "example-model")

    def fake_transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout: float,
    ) -> dict[str, Any]:
        assert url == "https://llm.example.test/v1/chat/completions"
        assert headers["Authorization"] == "Bearer sk-test-secret"
        assert timeout > 0
        assert payload["model"] == "example-model"
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"steps":[{"skill":"MOVE_ABOVE",'
                            '"parameters":{"object_id":"red_cube"}}]}'
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 7, "total_tokens": 17},
        }

    provider = OpenAICompatibleProvider.from_environment(
        allow_paid_model_call=True,
        transport=fake_transport,
    )

    response = provider.complete(prompt="plan safely", request_id="req-1")

    assert response.accepted is True
    assert response.model_name == "example-model"
    assert response.token_usage == {"prompt_tokens": 10, "completion_tokens": 7, "total_tokens": 17}
    assert response.prompt_hash
    assert response.response_hash
    assert "sk-test-secret" not in response.sanitized_response
    assert "Authorization" not in response.sanitized_response


def test_ollama_provider_blocks_when_model_not_installed() -> None:
    """Ollama 服务可达但模型不存在时应标记环境阻塞，不得自动下载。"""

    def fake_transport(
        method: str,
        url: str,
        payload: dict[str, object] | None,
        timeout: float,
    ) -> dict[str, Any]:
        if url.endswith("/api/version"):
            return {"version": "0.9.0"}
        if url.endswith("/api/tags"):
            return {"models": [{"name": "llama3.2:1b", "digest": "digest-a"}]}
        raise AssertionError(f"unexpected request: {method} {url} {payload} {timeout}")

    provider = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        model_name="missing:latest",
        transport=fake_transport,
    )

    health = provider.health_check()

    assert health.ready is False
    assert health.installed_model_count == 1
    assert "OLLAMA_MODEL_NOT_INSTALLED" in health.blockers


def test_real_provider_accepted_rows_can_enter_authoritative_filter() -> None:
    """非 fake 且 accepted 的真实模型行可进入正式性能数据集。"""

    rows = [
        {
            "provider": "openai-compatible",
            "model_runtime_accepted": True,
            "authoritative_for_model_performance": True,
            "model_runtime_type": "REAL_LLM_RUNTIME",
            "runtime_status": "RUNTIME_ACCEPTED",
        },
        {
            "provider": "fake",
            "model_runtime_accepted": False,
            "authoritative_for_model_performance": False,
            "model_runtime_type": "FAKE_PROVIDER_PIPELINE_TEST",
            "runtime_status": "PIPELINE_ONLY",
        },
    ]

    assert authoritative_model_performance_rows(rows) == [rows[0]]


def test_fake_provider_adapter_never_accepts_runtime() -> None:
    """fake adapter 可以返回响应，但不能被标记为真实模型 runtime。"""

    provider = FakeLLMProvider(model_name="fake-pipeline")
    health = provider.health_check()
    response = provider.complete(prompt="plan safely", request_id="fake-1")

    assert health.ready is True
    assert response.accepted is False
    assert response.runtime_type == "FAKE_PROVIDER_PIPELINE_TEST"


def test_phase13_fake_artifact_verifies_as_env_block(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Phase13 fake smoke 只能成为 implementation-ready/env-block 状态。"""

    root = tmp_path / "phase13"
    run_llm_only_baseline(
        profile=LLMOnlyProfile.SMOKE,
        provider=LLMOnlyProvider.FAKE,
        output_root=root,
    )
    monkeypatch.setattr("sys.argv", ["analyze_phase13_1.py", "--root", str(root)])
    assert analyze_phase13_main() == 0
    monkeypatch.setattr("sys.argv", ["verify_phase13_1.py", "--root", str(root)])
    assert verify_phase13_main() == 0

    summary = json.loads((root / "verification/phase13_1_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "PHASE13_1_IMPLEMENTATION_READY_WITH_MODEL_ENV_BLOCK"
    assert summary["accepted_count"] == 0
    assert summary["fake_authoritative_row_count"] == 0
