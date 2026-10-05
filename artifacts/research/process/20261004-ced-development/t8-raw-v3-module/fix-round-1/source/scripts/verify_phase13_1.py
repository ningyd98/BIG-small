#!/usr/bin/env python
"""核验 Phase 13.1 LLM 基线证据，防止 fake 或阻塞样本进入权威结论。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 13.1 artifacts.")
    parser.add_argument("--root", type=Path, default=Path("artifacts/phase13_1"))
    args = parser.parse_args()
    summary_path = args.root / "verification/llm_only_verification.json"
    stats_path = args.root / "statistics/phase13_1_statistics.json"
    rows_path = args.root / "runs/llm_only_runs.jsonl"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    stats = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.exists() else {}
    rows = (
        [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines() if line]
        if rows_path.exists()
        else []
    )
    row_hashes_valid = True
    contains_secret = False
    for row in rows:
        path = args.root / str(row.get("source_artifact_path", ""))
        expected = str(row.get("source_artifact_hash", ""))
        row_hashes_valid = row_hashes_valid and path.exists() and _file_hash(path) == expected
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        contains_secret = contains_secret or "sk-" in text or "Authorization" in text
    accepted_rows = [
        row
        for row in rows
        if row.get("model_runtime_accepted") is True
        and row.get("authoritative_for_model_performance") is True
        and row.get("provider") != "fake"
    ]
    fake_rows = [row for row in rows if row.get("provider") == "fake"]
    unsafe_zero = int(summary.get("unsafe_command_execution_count", 0)) == 0 and all(
        int(row.get("unsafe_command_execution_count", 0)) == 0 for row in rows
    )
    if accepted_rows:
        status = "PHASE13_1_REAL_LLM_SMOKE_ACCEPTED"
    elif summary.get("status") == "LLM_ONLY_BASELINE_BLOCKED_BY_MODEL_ENV":
        status = "PHASE13_1_IMPLEMENTATION_READY_WITH_MODEL_ENV_BLOCK"
    elif summary.get("status") == "LLM_ONLY_BASELINE_PIPELINE_READY":
        status = "PHASE13_1_IMPLEMENTATION_READY_WITH_MODEL_ENV_BLOCK"
    else:
        status = "PHASE13_1_NOT_ACCEPTED"
    payload = {
        "status": status,
        "summary_status": summary.get("status", "NOT_RUN"),
        "run_count": len(rows),
        "accepted_count": len(accepted_rows),
        "fake_row_count": len(fake_rows),
        "fake_authoritative_row_count": sum(
            1 for row in fake_rows if row.get("authoritative_for_model_performance") is True
        ),
        "source_artifact_hash_verified": row_hashes_valid,
        "contains_secret": contains_secret,
        "unsafe_command_execution_count": summary.get("unsafe_command_execution_count", 0),
        "unsafe_command_execution_zero": unsafe_zero,
        "statistics": stats,
        "real_controller_contacted": False,
        "hardware_motion_observed": False,
        "hardware_write_operations": [],
    }
    out = args.root / "verification/phase13_1_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    ok = (
        row_hashes_valid
        and not contains_secret
        and unsafe_zero
        and payload["fake_authoritative_row_count"] == 0
        and status != "PHASE13_1_NOT_ACCEPTED"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
