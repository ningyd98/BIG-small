#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ ! -d .venv ]]; then
  "$PYTHON_BIN" -m venv .venv
fi

. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m ruff format --check .
python -m ruff check .
python -m mypy .
python -m pytest -q
python scripts/validate_contract_examples.py
python scripts/run_fixed_pick_place.py --adapter mock
python scripts/run_fixed_pick_place.py --adapter mock --repeat 20
python scripts/run_fault_injection_suite.py
