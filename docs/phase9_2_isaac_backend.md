# Phase 9.2 Isaac Backend

The Isaac backend has two parts:

- `scripts/phase9/isaac_standalone_app.py`: runs inside Isaac Python and owns `SimulationApp`.
- `IsaacSimBackend`: remains in core Python and communicates through the JSONL protocol.

The standalone app supports:

- `--check-imports`: starts Isaac `SimulationApp` and reports readiness without claiming validation.
- JSONL handshake and commands for `reset_world`, `step`, `follow_joint_trajectory`, `sensor_request`, `emergency_stop`, and `shutdown`.
- `--smoke --output artifacts/phase9_2/isaac`: executes a real minimal smoke sequence and writes artifacts.

Required smoke artifacts:

- `isaac_smoke_evidence.json`
- `isaac_verification.json`
- `isaac_commands.log`
- `process_stdout.log`
- `process_stderr.log`
- `stage_metadata.json`
- `robot_state_sample.json`
- `rgb_sample.png`
- `depth_sample.npy`
- `contact_sample.json`

`ISAAC_SMOKE_VALIDATED` is only emitted when a real Isaac run loaded the stage, advanced physics, sampled robot state, RGB, depth, and contact data, completed reset and emergency stop, and left clean logs. Missing sensors, zero physics steps, missing provenance, forbidden log markers, or replay/static runtime evidence produce `INCOMPLETE`.

Ordinary CI tests cover the source and protocol contract. Real runtime tests must use `pytest -m isaac_runtime` on an Isaac-compatible runner.
