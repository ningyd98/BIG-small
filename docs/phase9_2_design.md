# Phase 9.2 Design

Phase 9.2 closes the simulation validation stack above the Phase 9 MuJoCo core and Phase 9.1 ROS 2 / MoveIt runtime acceptance.

The target success state is `PHASE9_2_ACCEPTED`, meaning:

- ROS 2 remains `ROS2_INTEGRATION_VALIDATED`.
- MoveIt 2 remains `MOVEIT_SAFETY_VALIDATED`.
- A real Isaac Sim 6.0 process produces `ISAAC_SMOKE_VALIDATED`.
- Isaac benchmark artifacts are `PASSED`.
- MuJoCo and Isaac paired artifacts produce `CROSS_BACKEND_VALIDATED`.
- Phase 9.1 aggregate can advance to `PHASE9_1_ACCEPTED`.
- Safety pressure remains passed with complete artifact provenance.

## Runtime Boundaries

Isaac Sim is never imported into the core Python or conda environment. The only supported runtime paths are:

- Standalone: `ISAAC_RUNTIME_MODE=standalone` and `ISAAC_SIM_ROOT/python.sh`.
- Container: `ISAAC_RUNTIME_MODE=container` and a fixed Isaac Sim 6.0 image tag plus recorded digest.

The core package talks to Isaac through an external JSONL process protocol. Source guards and protocol fixtures are useful for CI, but they are not runtime validation.

## Evidence Flow

```text
Compatibility check
  -> Isaac standalone app
  -> Isaac smoke artifacts
  -> Isaac benchmark artifacts
  -> MuJoCo / Isaac paired runs
  -> Phase 9.2 aggregate verifier
```

`scripts/phase9/isaac_standalone_app.py` owns the real Isaac `SimulationApp` lifecycle. It creates or loads a USD stage, adds a Panda/Franka articulation, table, target, obstacle, RGB-D camera, and contact sensor, advances physics, and writes process provenance plus sensor artifacts.

The BIG-small boundary remains unchanged: MoveIt plans; execution continues through the edge safety boundary.

## Non-Goals

Phase 9.2 does not validate a real robot. It does not claim real camera calibration, hardware emergency-stop wiring, or physical manipulator performance.
