# Simulation Job State Machine

Phase 11.1 runtime states:

`CREATED`, `QUEUED`, `VALIDATING`, `LEASED`, `STARTING`, `RUNNING`, `CANCEL_REQUESTED`, `CANCELLING`, `FINALIZING`, `SUCCEEDED`, `FAILED`, `CANCELLED`, `TIMED_OUT`, `BLOCKED_BY_ENV`, `INTERRUPTED`, `RECOVERY_PENDING`.

Representative legal transitions:

- `CREATED -> QUEUED`
- `QUEUED -> VALIDATING -> LEASED -> STARTING -> RUNNING`
- `RUNNING -> FINALIZING -> SUCCEEDED`
- `RUNNING -> CANCEL_REQUESTED -> CANCELLING -> CANCELLED`
- `RUNNING -> TIMED_OUT`
- `RUNNING -> FAILED`
- `LEASED/RUNNING -> INTERRUPTED -> RECOVERY_PENDING`
- `RECOVERY_PENDING -> QUEUED` or `RECOVERY_PENDING -> FAILED`

Every persisted transition records previous status, next status, reason code, timestamp, worker id, lease id, attempt, source, and event sequence. Invalid transitions are rejected.
