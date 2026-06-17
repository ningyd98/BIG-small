# Dashboard Security

The Phase 10.2B dashboard security model is intentionally narrow: local evidence review and software experiment execution only.

## Authentication Modes

`DASHBOARD_AUTH_MODE=LOCAL_ONLY` is the default. It accepts local clients from loopback/test clients and is used for development and CI.

`DASHBOARD_AUTH_MODE=TOKEN` requires `DASHBOARD_TOKEN`. HTTP requests can send `Authorization: Bearer <token>`. Browser WebSockets cannot reliably set custom headers, so the WebSocket path also accepts a same-origin `dashboard_token` cookie. Query-string tokens are not accepted.

## Roles

The API uses `x-dashboard-role` for coarse dashboard actions:

- `VIEWER`: read-only pages and APIs.
- `EXPERIMENT_OPERATOR`: start and cancel allowlisted software experiments.
- `SAFETY_REVIEWER`: record safety review notes.

Roles do not grant hardware motion. Hardware write operations remain empty in capabilities.

## Evidence Safety

Evidence browsing is mediated by the backend index:

- Absolute paths and `..` traversal are rejected.
- Root-escaping symlinks are skipped.
- Oversized files are skipped.
- Only `.json`, `.jsonl`, `.md`, `.txt`, and `.log` files are indexed.
- Evidence detail responses are redacted for token, password, secret, controller address, robot serial, and local home path patterns.

## Experiment Safety

Experiment creation rejects unexpected fields. The browser cannot provide shell commands, scripts, executables, environment variables, or arbitrary paths.

Allowlisted kinds are:

- `MOCK_SOFTWARE`
- `MUJOCO_SMOKE`
- `SYNTHETIC_DRY_RUN`
- `MOVEIT_RUNTIME_DRY_RUN`

All adapters set `sent_to_hardware=false` and `hardware_motion_observed=false`. MoveIt runtime dry-run failures are classified as environment blockers, not hardware readiness.

## Non-Goals

Phase 10.2B does not connect to real controllers, subscribe to real controller status, execute hardware motion, or advance real-robot acceptance beyond `NONE`.
