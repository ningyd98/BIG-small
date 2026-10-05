#!/usr/bin/env bash
# 脚本说明：本地综合回归入口，只运行软件验证和仿真检查，不连接真实硬件。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ ! -d .venv ]]; then
  "$PYTHON_BIN" -m venv .venv
fi

. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,sim-mujoco,sim-analysis]"
python -m compileall src scripts tests
python -m ruff format --check .
python -m ruff check .
python -m mypy .
python -m pytest -q
python scripts/check_docs.py
python scripts/validate_contract_examples.py
python scripts/run_fixed_pick_place.py --adapter mock
python scripts/run_fixed_pick_place.py --adapter mock --repeat 20
python scripts/run_fault_injection_suite.py
python scripts/run_phase2_task.py --repository sqlite
python scripts/run_phase2_failure_case.py --fault GRASP_FAILED
python scripts/run_phase2_replay_test.py
python scripts/run_phase2_restart_recovery_test.py
python scripts/verify_phase2.py
python scripts/run_phase3_safe_task.py
python scripts/run_phase3_workspace_violation.py
python scripts/run_phase3_velocity_limit.py
python scripts/run_phase3_collision_case.py
python scripts/run_phase3_obstacle_case.py
python scripts/run_phase3_stale_scene_case.py
python scripts/run_phase3_watchdog_timeout.py
python scripts/verify_phase3.py
python scripts/run_phase3_integrated_safe_task.py
python scripts/run_phase3_integrated_workspace_reject.py
python scripts/run_phase3_integrated_path_collision.py
python scripts/run_phase3_integrated_pause.py
python scripts/run_phase3_integrated_emergency_stop.py
python scripts/verify_phase3_1.py
python scripts/run_phase3_integrated_velocity_limit.py
python scripts/run_phase3_integrated_stale_telemetry.py
python scripts/verify_phase3_2.py
python scripts/run_phase4_api_smoke.py
python scripts/run_phase4_mock_plan.py
python scripts/run_phase4_rule_based_plan.py
python scripts/run_phase4_request_more_observation.py
python scripts/run_phase4_malformed_output_repair.py
python scripts/run_phase4_idempotency.py
python scripts/run_phase4_edge_dispatch.py
python scripts/verify_phase4.py
python scripts/verify_phase5.py
python scripts/verify_phase6.py
python scripts/verify_phase6_2.py
python scripts/verify_phase7.py
python scripts/verify_phase8.py
python scripts/verify_phase8_1.py
python scripts/verify_phase8_2.py
python scripts/verify_phase9.py
python scripts/verify_phase9_1.py --skip-history
python scripts/verify_phase10_0.py
python scripts/verify_phase10_1.py
python scripts/verify_phase10_2a.py --skip-runtime
python -m pip check
