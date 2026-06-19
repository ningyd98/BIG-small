# Phase 10.2B Acceptance

The accepted status for this phase is `PHASE10_2B_CONSOLE_ACCEPTED`.

## Required Evidence

- Backend dashboard API tests pass.
- WebSocket authentication, replay, heartbeat, and message-size guard tests pass.
- Generated OpenAPI schema is current.
- Frontend format, lint, typecheck, unit tests, and build pass.
- Playwright E2E cases `E2E-01` through `E2E-10` pass against the real local backend and Vite proxy.
- CI runs the Phase 10.2B verifier.

## Required Safety Properties

- `hardware_write_operations=[]`
- `hardware_motion_authorized=false`
- `real_robot_validation=NOT_STARTED`
- `highest_acceptance_level=NONE`
- Browser routes do not expose ROS 2, MoveIt execute, `ros2_control`, vendor SDK, or real controller write paths.
- Software experiment start rejects unexpected command/path/environment fields.
- Safety review notes do not change hardware authorization.

## Acceptance Command

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
python scripts/verify_phase10_2b.py
```

The command writes:

```text
artifacts/phase10/phase10_2b/phase10_2b_verification.json
```

The phase is accepted when that JSON reports `status=PHASE10_2B_CONSOLE_ACCEPTED` and `validation_claimed=true`.
