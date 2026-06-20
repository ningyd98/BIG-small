#!/usr/bin/env python
"""验证 LLM-only 基线 artifact。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify LLM-only baseline artifacts.")
    parser.add_argument("--root", type=Path, default=Path("artifacts/thesis_baselines/llm_only"))
    args = parser.parse_args()
    summary_path = args.root / "verification/llm_only_verification.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    accepted = (
        summary.get("status")
        in {"LLM_ONLY_BASELINE_PIPELINE_READY", "LLM_ONLY_BASELINE_BLOCKED_BY_MODEL_ENV"}
        and summary.get("unsafe_command_execution_count", 0) == 0
        and summary.get("contains_secret") is False
        and summary.get("real_controller_contacted") is False
        and summary.get("hardware_motion_observed") is False
    )
    payload = {
        "status": summary.get("status", "LLM_ONLY_BASELINE_NOT_RUN"),
        "runtime_status": summary.get("runtime_status", "NOT_RUN"),
        "model_runtime_accepted": summary.get("model_runtime_accepted", False),
        "fake_provider_not_model_performance": (
            summary.get("model_runtime_type") != "FAKE_PROVIDER_PIPELINE_TEST"
            or summary.get("authoritative_for_model_performance") is False
        ),
        "contains_secret": summary.get("contains_secret", False),
        "unsafe_command_execution_count": summary.get("unsafe_command_execution_count", 0),
        "verified": accepted,
    }
    out = args.root / "verification/llm_only_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
