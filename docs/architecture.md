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
- `edge`: `RobotAdapter`, fixed pick-and-place flow, Phase 1 skill executor, and Phase 2
  task runtime.
- `edge.runtime`: task context, explicit state machine, retry policy, condition evaluator,
  parameterized skill registry, task executor, and restart recovery.
- `repositories`: in-memory and SQLite persistence for tasks, state transitions, step
  executions, action executions, accepted commands, and audit events.
- `simulation`: deterministic mock adapter and optional MuJoCo adapter.
- `scripts`: Phase 0/1 validation and acceptance commands.
- `tests`: unit and acceptance tests for Phase 0, Phase 1, Phase 1.1, and Phase 2.

## Boundary

Phase 0-2 do not implement cloud task planning, MQTT, periodic cloud supervision,
event-triggered cloud re-planning, LLM/VLM prompt calls, ROS 2, full safety shield, or
real robot control.

Phase 3 implements the independent edge safety shield (21 rules, StopController,
Watchdog) and deterministic safety execution gate control.

Phase 3.1 integrates SafetyShield into TaskExecutor as a mandatory dependency with
fail-closed enforcement and real rule implementations using merged constraints.

Phase 3.2 adds real intent resolution (SkillSafetyIntentResolver), runtime safety data
providers (TelemetryProvider / SceneStateProvider Protocol), ALLOW_WITH_LIMITS
implementation, and comprehensive integration verification.

Phase 4 implements the cloud initial planning service: PlannerAdapter Protocol (Mock,
RuleBased, OpenAICompatible), planning pipeline with model untrusted boundary,
FastAPI API, EdgeGateway (InProcess), PromptRegistry, and cloud repositories.
Phase 4 does NOT implement MQTT, periodic supervision, event-triggered re-planning,
or real robot control.

## Phase 2 Runtime Flow

```text
TaskContract
  -> EdgeContractValidator
  -> Repository.accept_command
  -> TaskRuntimeContext
  -> TaskStateMachine
  -> SkillRegistry
  -> SkillExecutor
  -> RobotAdapter
  -> Repository
  -> AuditLog
```
