# BIG-small Architecture

## Phase 0/1 Scope

BIG-small uses a cloud-edge architecture, but Phase 0 and Phase 1 deliberately stop before cloud planning, MQTT, model prompts, and real robot control.

Frozen technical route:

- Runtime: Python with an `asyncio`-compatible package layout.
- Deterministic execution: `MockRobotAdapter`.
- Physics simulation target: MuJoCo through an optional adapter.
- Cloud models: not connected.
- Real robot SDKs: not connected.

## Current Components

- `contracts`: Pydantic models, JSON Schema exports, and example validation.
- `shared`: frozen Phase 0/1 route constants.
- `edge`: `RobotAdapter`, skill registry, fixed pick-and-place flow, and skill executor.
- `simulation`: deterministic mock adapter and optional MuJoCo adapter.
- `scripts`: Phase 0/1 validation and acceptance commands.
- `tests`: unit and acceptance tests for Phase 0/1 only.

## Boundary

Phase 0/1 does not implement cloud task planning, MQTT, periodic cloud supervision, event-triggered re-planning, LLM/VLM prompt calls, ROS 2, or real robot control.
