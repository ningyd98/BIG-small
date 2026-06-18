#!/usr/bin/env bash
# 脚本说明：运行 Isaac 兼容性检查，不用 Mock 冒充 Isaac 成功。
set -euo pipefail
python scripts/phase9/check_isaac_sim.py
