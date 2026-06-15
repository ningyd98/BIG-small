# Phase 9 Design

Phase 9 adds a simulator boundary below the existing `TaskExecutor`, `SafetyShield`, and skill registry:

`TaskContract -> EdgeContractValidator -> SafetyShield -> TaskExecutor -> SkillExecutor -> PhysicsRobotAdapter -> SimulatorBackend -> physics state / contacts / sensors`.

The formal backend protocol is `cloud_edge_robot_arm.simulation.backend.SimulatorBackend`. The MuJoCo implementation owns `mujoco.MjModel`, `mujoco.MjData`, actuator targets, simulation time, contact extraction, and sensor-frame generation. The adapter maps the 13 high-level skills to backend commands without exposing MuJoCo types to the upper stack.

Isaac Sim is intentionally decoupled. The core package provides protocol/client/stage/sensor/fault bridge modules and environment checks, but does not import Isaac private modules at package import time.
