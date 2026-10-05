#!/usr/bin/env bash
# 脚本说明：构建 Dashboard 前端并执行格式、lint、类型和测试检查。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${ROOT_DIR}/dashboard"
npm run api:check
npm run format:check
npm run lint
npm run typecheck
npm run test
npm run build
