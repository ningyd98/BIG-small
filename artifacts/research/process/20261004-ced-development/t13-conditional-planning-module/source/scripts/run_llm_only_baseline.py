#!/usr/bin/env python
"""运行仅大模型决策基线。

默认 fake provider 只验证管线，不代表真实大模型性能。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cloud_edge_robot_arm.experiments.llm_only.runner import (  # noqa: E402
    LLMOnlyProfile,
    LLMOnlyProvider,
    run_llm_only_baseline,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LLM-only baseline.")
    parser.add_argument("--profile", choices=[item.value for item in LLMOnlyProfile], required=True)
    parser.add_argument(
        "--provider",
        choices=[item.value for item in LLMOnlyProvider],
        required=True,
    )
    parser.add_argument("--model", default="")
    parser.add_argument(
        "--allow-paid-model-call",
        action="store_true",
        help="Allow OpenAI-compatible provider to issue a paid inference request.",
    )
    parser.add_argument("--output", type=Path, default=Path("artifacts/thesis_baselines/llm_only"))
    args = parser.parse_args()
    payload = run_llm_only_baseline(
        profile=LLMOnlyProfile(args.profile),
        provider=LLMOnlyProvider(args.provider),
        output_root=args.output,
        model_name=args.model,
        allow_paid_model_call=args.allow_paid_model_call,
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
