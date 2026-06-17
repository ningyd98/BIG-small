#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${ROOT_DIR}/dashboard"
npm run api:check
npm run format:check
npm run lint
npm run typecheck
npm run test
npm run build
