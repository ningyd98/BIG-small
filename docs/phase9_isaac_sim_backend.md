# Phase 9 Isaac Sim Backend

Isaac Sim integration is represented as an independent-process backend boundary. Core modules include `simulation.isaac.client`, `protocol`, `stage_builder`, `robot_controller`, `sensor_bridge`, and `fault_bridge`.

On this host Isaac validation is `BLOCKED_BY_ENV`: `ISAAC_SIM_ROOT` is unset and `vulkaninfo` is not available. No Isaac smoke result is claimed.

Compatible host command:

```bash
ISAAC_SIM_ROOT=/path/to/isaac-sim python scripts/verify_phase9.py
```
