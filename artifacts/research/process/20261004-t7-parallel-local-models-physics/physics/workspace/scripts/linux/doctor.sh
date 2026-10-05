#!/usr/bin/env bash
# 只读 doctor 入口：不执行任何控制器探测或硬件写操作。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
exec python "$BIGSMALL_ROOT/scripts/linux/doctor.py" "$@"
