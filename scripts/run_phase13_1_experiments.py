#!/usr/bin/env python
"""Run Phase 13.1 LLM-only baseline experiments."""

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
    parser = argparse.ArgumentParser(description="Run Phase 13.1 experiments.")
    parser.add_argument(
        "--provider",
        choices=[item.value for item in LLMOnlyProvider],
        required=True,
    )
    parser.add_argument(
        "--profile",
        choices=[item.value for item in LLMOnlyProfile],
        required=True,
    )
    parser.add_argument("--model", default="")
    parser.add_argument("--allow-paid-model-call", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase13_1"))
    args = parser.parse_args()
    output = args.output
    payload = run_llm_only_baseline(
        profile=LLMOnlyProfile(args.profile),
        provider=LLMOnlyProvider(args.provider),
        output_root=output,
        model_name=args.model,
        allow_paid_model_call=args.allow_paid_model_call,
    )
    manifest = {
        "phase": "13.1",
        "provider": args.provider,
        "profile": args.profile,
        "model": args.model,
        "allow_paid_model_call": args.allow_paid_model_call,
        "summary": payload,
        "base_dependency": "codex/thesis-report",
        "main_not_merged": True,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
