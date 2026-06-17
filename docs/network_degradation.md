# 网络退化与 Outbox

Phase 6.1 对事件自治消息使用事务性 outbox 模式。

## 消息生命周期

已实现的状态流转如下：

```text
PENDING → SENDING → SENT
PENDING → SENDING → RETRY_WAIT → SENDING
PENDING → SENDING → DEAD_LETTER
```

`RETRY_WAIT` 消息带 `next_retry_at`。进程重启后，到期的重试消息仍可以被重新 claim。

## 持久化字段

`PendingMessage` 和 SQLite `event_outbox` 表记录：

- message ID。
- 幂等 key。
- 消息类型。
- task ID。
- payload JSON。
- 重试次数。
- 最大重试次数。
- 下次尝试时间。
- claim 时间。
- 最后错误。
- 状态。
- 创建和更新时间。

## 原子 Claim

`SQLiteEventAutonomyRepository.claim_outbox_message` 在 repository 写锁下，把到期的 `PENDING` 或 `RETRY_WAIT` 行改为 `SENDING`。更新语句带状态条件，避免两个发送者通过 repository API claim 同一条消息。

## 重试和重启

`mark_outbox_failed` 会增加重试次数。未达到重试上限时，状态变为 `RETRY_WAIT` 并记录 backoff；达到上限后，状态变为 `DEAD_LETTER`。

验证来源：

- `scripts/verify_phase6.py` 第 14 和第 15 项检查。
- `tests/test_phase6_e2e_executor.py::test_sqlite_outbox_retry_wait_survives_restart_and_reclaims`。
- `tests/test_phase6_e2e_executor.py::test_outbox_cas_prevents_double_claim`。

该实现提供 at-least-once 投递语义。消费者必须使用幂等 key 去重。
