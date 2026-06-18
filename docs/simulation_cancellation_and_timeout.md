# Simulation Cancellation And Timeout

Cancellation is cooperative:

1. API sets `cancel_requested`.
2. Worker observes the flag.
3. State advances `RUNNING -> CANCEL_REQUESTED -> CANCELLING -> CANCELLED`.
4. Partial events and artifacts are preserved.

Timeout is separate:

1. Each job stores `timeout_seconds`.
2. Worker checks elapsed runtime.
3. A constrained run advances to `TIMED_OUT`.
4. Timeout evidence and prior events remain queryable.

Cancel does not mean timeout. Timeout does not imply operator cancellation. Neither path deletes partial evidence.
