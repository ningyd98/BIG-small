# Real Robot Safety

No Phase 10.2A-R documentation or repository governance command may connect to a
controller or execute real hardware motion.

Physical robot motion is fail-closed.

- `enable_real_robot=false` rejects every motion command.
- `RUNTIME_PROFILE=simulation` cannot instantiate a real robot runtime.
- Missing or placeholder device configuration rejects hardware modes.
- Active emergency stop, stale telemetry, missing controller, unhealthy
  SafetyShield, missing operator token, or insufficient acceptance level rejects
  motion.
- Operator confirmation is short-lived, action-bound, and one-time use. The raw
  token is never written to artifacts.
- Mock, FakeSystem, MuJoCo, Isaac, and dry-run evidence cannot be labeled as
  `HARDWARE_EXECUTED`.

## Site Requirements

The first physical motion must not be performed by one person alone. A local
operator must verify physical emergency stop access, workspace isolation,
payload limits, clear table/obstacle layout, and that no person is inside the
workspace.

## Stop Behavior

The edge runtime must prefer controlled stop, then emergency stop if controlled
stop does not verify halt. Controller exit, communication loss, stale telemetry,
and watchdog expiration are treated as stop conditions for hardware acceptance.
