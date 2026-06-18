# Phase 10.2C Level 0 Read-Only Site Procedure

Phase 10.2C permits real controller contact only for read-only state sampling.
It does not authorize controller enable, servo enable, brake release, trajectory
execution, gripper commands, HOME, SAFE_STOP commands, or any API call that may
produce motion.

## Hardware Identity

The repository does not contain site hardware identity. Site staff must record
the following in an external configuration file or environment-managed secret
store before running hardware verification:

- vendor
- model
- controller type
- read-only SDK or ROS 2 driver
- firmware
- connection method

Use `configs/real_robot/level0_read_only.template.yaml` only as a template. The
real file must live outside the repository. Raw IP addresses, serial numbers,
credentials, tokens, usernames, and local absolute paths must not appear in
committed logs, Dashboard responses, or artifacts. The verifier records only
`robot_identity_hash` and `config_hash`.

## Allowed Calls

The Level 0 adapter protocol exposes only:

- `connect`
- `disconnect`
- `health`
- `get_robot_identity`
- `get_controller_state`
- `get_joint_state`
- `get_tcp_pose`
- `get_emergency_stop_state`
- `get_fault_state`
- `get_operation_mode`

No read-only adapter may expose `execute`, `move`, `command`,
`send_trajectory`, `enable_controller`, `servo_enable`, `release_brake`,
`home`, `safe_stop`, or `gripper_command`.

## Site Session

A Level 0 site session must include:

- two distinct site operator identifiers or hashes
- one safety reviewer identifier or hash
- isolated workspace confirmation
- reachable e-stop confirmation
- no-motion mode confirmation
- physical power state
- software commit
- source tree hash
- `robot_identity_hash`
- `config_hash`
- expiration time

Expired sessions, robot identity changes, and configuration changes invalidate
the session.

## Verification Commands

CI and development machines may run only the framework verifier:

```bash
python scripts/verify_phase10_2c_level0.py --fake
```

This can output only `PHASE10_LEVEL0_FRAMEWORK_ACCEPTED`; it is not hardware
acceptance.

Site staff may run the hardware verifier manually after installing the
site-specific read-only adapter and external configuration:

```bash
python scripts/verify_phase10_2c_level0.py --hardware --config /external/path/level0.yaml
```

Without a site adapter or external config, hardware mode must return
`PHASE10_LEVEL0_ENV_BLOCKED`. It must not contact a controller.

## Evidence

The verifier writes:

- `artifacts/phase10/level0/environment.json`
- `artifacts/phase10/level0/site_session.json`
- `artifacts/phase10/level0/controller_readback.jsonl`
- `artifacts/phase10/level0/joint_state_samples.jsonl`
- `artifacts/phase10/level0/tcp_pose_samples.jsonl`
- `artifacts/phase10/level0/estop_samples.jsonl`
- `artifacts/phase10/level0/fault_samples.jsonl`
- `artifacts/phase10/level0/read_only_api_audit.jsonl`
- `artifacts/phase10/level0/no_write_operation_evidence.json`
- `artifacts/phase10/level0/level0_summary.json`

`write_operation_count` must be `0`, `hardware_motion_observed` must be
`false`, and `highest_acceptance_level` remains `NONE` unless the acceptance
store is explicitly marked with complete real hardware Level 0 evidence.

Level 1 remains unauthorized after Level 0.
