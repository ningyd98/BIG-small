# Phase 8.2 恢复说明

S15 重启覆盖包括：

- C1 保存 active contract。
- C2 保存风险快照。
- C3 保存 AUTO 决策。
- C4 在 commit 之前保存 transition prepared。
- C5 在 CAS apply 之前保存重规划。
- C6 在 ACK 之前完成 CAS apply。
- C7 在统计前保存执行记录。
- C8 在 ACK 之前 claim outbox。
- C9 在下一步前更新 checkpoint。

每次恢复事件都会记录 crash point、命令和计划进度。验收守卫会检查这九个点是否都存在，并确保恢复后不会重复已完成步骤。
