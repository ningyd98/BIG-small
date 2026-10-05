#!/usr/bin/env bash
# 脚本说明：运行 Phase 9 Isaac smoke verifier，不连接真实控制器。
set -euo pipefail
python scripts/verify_phase9_isaac.py
