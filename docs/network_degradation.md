# Network degradation and outbox

Phase 6.1 uses a transactional outbox pattern for event-autonomy messages.

## Message lifecycle

The implemented lifecycle is:

```text
PENDING → SENDING → SENT
PENDING → SENDING → RETRY_WAIT → SENDING
PENDING → SENDING → DEAD_LETTER
```

`RETRY_WAIT` messages carry `next_retry_at`; due retry messages can be claimed after restart.

## Persistence fields

`PendingMessage` and the SQLite `event_outbox` table track:

- message ID;
- idempotency key;
- message type;
- task ID;
- payload JSON;
- retry count;
- max retries;
- next attempt time;
- claimed time;
- last error;
- status;
- created and updated timestamps.

## Atomic claim

`SQLiteEventAutonomyRepository.claim_outbox_message` claims a message by changing a due `PENDING` or `RETRY_WAIT` row to `SENDING` under the repository write lock and with a status condition in the update. This prevents two senders from claiming the same message through the repository API.

## Retry and restart behavior

`mark_outbox_failed` increments retry count. Before retry exhaustion it sets status to `RETRY_WAIT` and records backoff. At the retry limit it sets status to `DEAD_LETTER`.

Verified by:

- `scripts/verify_phase6.py` checks 14 and 15.
- `tests/test_phase6_e2e_executor.py::test_sqlite_outbox_retry_wait_survives_restart_and_reclaims`.
- `tests/test_phase6_e2e_executor.py::test_outbox_cas_prevents_double_claim`.

The implementation provides at-least-once delivery semantics. Consumers must use idempotency keys to deduplicate repeated sends.
