# Mode Transition

Phase 7 mode transitions are modeled as explicit records, not a string assignment.

`ModeTransitionService` supports:

- `prepare`
- `commit`
- `abort`
- idempotency key reuse
- payload conflict detection
- expected and new mode versions

`AutoModeRepository` persists transitions and mode status through InMemory and SQLite repositories. SQLite restart recovery can find a `PREPARED` transition and deterministically continue or roll it back at the orchestrator boundary.

## Safety Boundaries

Normal mode switches may occur only before task start, after an atomic step completes, in `PAUSED`, in `WAITING_CLOUD_UPDATE`, or after explicit safe stop recovery.

Transitions must not reset completed steps, checkpoint, active contract, plan version, command sequence, retry budget, failure history, or completion history.

SafetyShield rejection, emergency stop, and severe device faults have highest priority and cannot be overridden by AUTO.
