#!/usr/bin/env python
"""检查 LLM provider 环境，不触发付费推理或本地大模型下载。"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cloud_edge_robot_arm.experiments.llm_only.models import LLMOnlyProvider  # noqa: E402
from cloud_edge_robot_arm.experiments.llm_only.providers.base import LLMProvider  # noqa: E402
from cloud_edge_robot_arm.experiments.llm_only.providers.fake import FakeLLMProvider  # noqa: E402
from cloud_edge_robot_arm.experiments.llm_only.providers.ollama import OllamaProvider  # noqa: E402
from cloud_edge_robot_arm.experiments.llm_only.providers.openai_compatible import (  # noqa: E402
    OpenAICompatibleProvider,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check LLM provider environment.")
    parser.add_argument(
        "--provider",
        choices=[item.value for item in LLMOnlyProvider],
        required=True,
    )
    parser.add_argument("--model", default="")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase13_1/environment"))
    args = parser.parse_args()

    provider: LLMProvider
    if args.provider == LLMOnlyProvider.FAKE.value:
        provider = FakeLLMProvider()
    elif args.provider == LLMOnlyProvider.OPENAI_COMPATIBLE.value:
        provider = OpenAICompatibleProvider.from_environment(allow_paid_model_call=False)
    else:
        provider = OllamaProvider(model_name=args.model or None)
    health = provider.health_check()
    payload = {
        "provider": args.provider,
        "model_name": health.model_name,
        "ready": health.ready,
        "runtime_type": health.runtime_type,
        "blockers": health.blockers,
        "secret_configured": health.secret_configured,
        "installed_model_count": health.installed_model_count,
        "version": health.version,
        "endpoint_hash": health.endpoint_hash,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "ollama_binary": shutil.which("ollama") or "",
        "real_controller_contacted": False,
        "hardware_motion_observed": False,
        "hardware_write_operations": [],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    out = args.output / f"{args.provider.replace('-', '_')}_environment.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
