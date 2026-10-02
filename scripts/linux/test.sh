#!/usr/bin/env bash
# Linux 质量门禁：smoke 或完整软件检查，执行日志由调用方保留。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
export PLAYWRIGHT_MUJOCO_RUNTIME=1
cd "$BIGSMALL_ROOT"
if [[ "${1:-}" == "--smoke" ]]; then
  python -m pytest -q tests/test_phase0_contracts.py tests/test_phase1_acceptance.py tests/test_llm_only_baseline.py tests/test_sim2real_deep_pipeline.py
  exit
fi
python -m ruff format --check .
python -m ruff check .
python -m mypy .
python -m pytest -q
python -m pip check
(cd dashboard && npm run api:check && npm run format:check && npm run lint && npm run typecheck && npm test && npm run build && npm run e2e)
