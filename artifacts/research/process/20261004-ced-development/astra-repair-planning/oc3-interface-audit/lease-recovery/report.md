# OC3 静态接口审查：SQLite lease 与恢复

状态：STATIC_DEPENDENCY_EVIDENCE_ONLY。ROOT 仅读已有接口与测试源码，不实施修复、不运行产品 import/CPU probe/pytest/CLI/DB/renderer/provider/network/Git。该报告是下一份 Astra OC3 计划的输入，不能替代计划或验收。

当前 lease 的 acquire/heartbeat/expire/CAS、job/attempt 时间字段与 read_visual_worker_lease 仍使用真实 UTC datetime。OC2 新 D counter/source 前缀没有迁移这些接口；lease_clock_migration=NOT_DONE_OC3 保持。无需把所有 _now 文本一律改成 BOOTTIME：旧外部 UTC 合同必须继续保留，新增单机域要显式路由、持久来源和可复核桥接条件。

SQLite publication_guard 已有跨进程 flock 与同线程嵌套、fork PID 隔离。heartbeat_lease 在 BEGIN IMMEDIATE 取得锁后重新读 UTC，禁止 revive expired/released/cancelled/foreign-owner lease，并在同事务更新 lease/job。expiry scan 的 CAS 保留 status/lease/worker/expiry 复核。后续 D 路径应复用这些原子边界；此处仅说明复用点，不提前设计或修改域参数。

worker_owner 的真实 reader 在同锁下核对 RUNNING job、唯一未释放且未过期 lease、唯一 open attempt 与原 acquired≤started≤observed 次序。legacy optional now 只属于旧接口，不能作为新 D/current 或 caller 授权；OC2现有计划保持不传 caller now。domain/PID/hash 字符串本身不证明授权，restart/suspend/hostpause 尚无真实验收。

ArtifactRecoveryService 先 expire，再在 publication_guard 中重新核对快照 status/lease/worker 后 finish attempt/CAS。显式 requeue 与 artifact 完整性恢复继续分开，不自动续跑已完成实验。新域的 restart/expired/no-refresh 需要以后 Astra 规划，不以历史 UTC artifact 或单次 source prefix 重建 live 权限。

已有测试源码提供可复用反例：test_heartbeat_cannot_revive_inactive_lease、test_heartbeat_extends_only_current_live_lease；test_expiry_scan_cannot_interrupt_a_replacement_lease、test_expiry_scan_rechecks_current_expiration_in_atomic_update、test_recovery_scan_cannot_finish_new_owner_attempt；test_missing_live_lease_or_unique_open_attempt_rejects。此处只读取定义，不声称新运行或重算测试数量。

逐文件 SHA256/bytes 与源码定位见 report.json。检查范围是列出的9输入，不是完整OC3闭包；未pin正在修复的operational模块、worker、RW1 producer/tests、teacher及6根阶段文档。camera/marker/condition、planner/supervision、ACK/start/effect、请求等待与PCSC由其它接口审查及下一份Astra计划继续闭包。software/actual/native/9组/G1/INITIAL/METHOD/FINAL不提升，formal_accepted=false。
