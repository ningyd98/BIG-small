#!/usr/bin/env python
"""Phase 12 验收入口。

smoke 只输出 PHASE12_EXPERIMENT_SUITE_READY；full 样本不足或环境阻塞时不会输出最终封板。
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

from cloud_edge_robot_arm.final_evaluation.models import Phase12Profile  # noqa: E402
from cloud_edge_robot_arm.final_evaluation.validation import verify_phase12  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 12 final evaluation artifacts.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--smoke", action="store_true")
    mode.add_argument("--validation", action="store_true")
    mode.add_argument("--full", action="store_true")
    mode.add_argument("--analysis-only", action="store_true")
    parser.add_argument("--skip-isaac", action="store_true")
    parser.add_argument("--skip-model-runtime", action="store_true")
    parser.add_argument("--artifact-root", type=Path, default=Path("artifacts/phase12"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase12/verification"))
    args = parser.parse_args()
    profile = (
        Phase12Profile.FULL
        if args.full
        else Phase12Profile.VALIDATION
        if args.validation
        else Phase12Profile.SMOKE
    )
    payload = verify_phase12(
        profile=profile,
        artifact_root=args.artifact_root,
        output_dir=args.output,
        require_full=bool(args.full),
    )
    payload["skip_isaac"] = bool(args.skip_isaac)
    payload["skip_model_runtime"] = bool(args.skip_model_runtime)
    payload["analysis_only"] = bool(args.analysis_only)
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0 if payload["status"] != "PHASE12_REJECTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
