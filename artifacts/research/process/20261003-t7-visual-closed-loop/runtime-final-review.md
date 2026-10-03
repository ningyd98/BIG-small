# Runtime final review

复核时间：2026-10-03T16:30:38.272596+00:00。审查者：`/root/t7_execution`。审查方式为源码只读、临时 SQLite 确定性竞态复现和 CPU 测试；没有运行模型或 GPU 验收，没有改生产源码。按实现 agent 请求新增了独立序列化回归 `tests/test_rgbd_worker_serialization.py`。

审查结论：本次租约交接、心跳、RGB-D 分 scope 文件隔离、独立终态语义、真实时间戳序列化及发布 I/O 故障收敛修复通过复核；本审查范围内没有未关闭的 P1/P2。此结论不替代 root 的真实 worker / 20 例物理验收。

## 已关闭的发现与验证边界

- **P1：旧 expiry 扫描误中断新 owner。** 初版可在旧 RUNNING 行被读取后交接到新 RUNNING 租约，旧扫描按状态 CAS 将新任务改为 INTERRUPTED。当前扫描携带 lease/worker，CAS 原子比较归属与截止时刻；原复现现在保留新 owner 和 RUNNING。额外测试覆盖扫描后同 lease 过期时间变化以及 STARTING 合法过期转换。
- **P1：取消请求恢复旧 ownership。** 初版 cancel 在刷新旧 job 后交接，会把新 job 的 worker/lease 写回旧值。当前取消持有 publication guard，CAS 比较期望归属而不写旧归属，重读收敛到当前 job；原复现得到新 owner 的 CANCEL_REQUESTED。
- **P1：恢复扫描关闭新 attempt。** 初版 recoverable 快照失效后，`finish_open_attempts` 会把新 worker 的 RUNNING attempt 关闭成 INTERRUPTED。当前每 job 在 guard 内重读并比较 snapshot 的 status/lease/worker；原复现保留新 attempt 的 RUNNING、ended_at=None。
- **重试与启动围栏。** retry 原子检查状态和归属，旧快照不能把新 RUNNING owner 重新入队；旧 worker 启动时不能创建新 attempt 或替换 owner。
- **P1：真实 episode datetime 不能发布。** 新回归首先复现 `datetime is not JSON serializable`，由生产修复将整个 outcome 转为 JSON-safe 数据后，事件与 result 中 event.occurred_at、budget_before/deadline_at、budget_after/deadline_at 均保存为可逆 ISO 时间，原 outcome 保持不变。

## 归属、scope 与结果检查

- `publication_guard` 同一数据库跨 repository / 线程可重入，并由 flock 跨进程互斥；成功及失败证据发布与 owner 交接不能交错。
- Worker 转换绑定 expected worker/lease。失权异常仅结束自身旧 attempt、记录 stale event、释放自身 lease_id；不会释放新 lease、覆盖新 metrics / artifact 索引 / shared result。
- Heartbeat 在 SQLite 写事务获取锁之后取时间，要求当前未释放、未过期、未取消的 LEASED/STARTING/RUNNING owner；过期、释放、替换、中断、取消的 lease 均不能复活，job 与 lease expiry 同事务更新。
- CAPTURE_ONLY、VISUAL_PLANNING 和 VISION_CLOSED_LOOP 中途输出均写 `rgbd-attempts/<lease_id>/`；旧 episode finally 的晚到帧不能覆盖新 owner。最终 artifact 索引只引用当前 lease；无 lease 历史作业保持原路径。CAPTURE_ONLY 和 VISUAL_PLANNING 明确 task_success=false、task_execution=NOT_RUN。
- VISION_CLOSED_LOOP 独立 S01 指令评分只用于尾评分，保留原始 online/physical/visual episode 结果并额外要求 semantic PASS 才 task_success=true。紫色不存在、否定、多任务、未知句式和其他目标区不能被末评分升级成功。
- 本审查的文件隔离断言覆盖上述三种 RGB-D scope；不把它扩称为所有历史 dataset-generation 文件写入的故障隔离保证。

## 已关闭 P2：artifact 发布失败不再保留成功终态

初版确定性探针令 `_write_artifacts` 第一次抛 `OSError('review injected transient publication failure')`、第二次正常写入，曾出现 job/attempt/result.status 全为 SUCCEEDED、result.task_success=false 的矛盾。

当前 worker 只在本次成功发布阶段启用修正分支：在 publication guard 内核对 owner，带 expected worker/lease 将刚提交的 SUCCEEDED 改为 RECOVERY_PENDING，先把 attempt、错误、完整结果证据持久化并清空旧 artifact 索引，再最多尝试一次失败档案写入。数据库可用而磁盘持续不可写时，job/attempt 仍为 RECOVERY_PENDING、无虚假成功文件索引，实际已执行动作及原 verification_records 保留在数据库失败事件中，不自动重新执行。

原 OSError 探针现得到 job/attempt/result 一致 RECOVERY_PENDING、task_success=false。独立测试同时覆盖一次失败、持续失败、正常成功、交接后旧 owner 写失败；最后一种不得降级新任务、改写新结果、关闭新 attempt 或释放新 lease。生产状态机只新增 SUCCEEDED→RECOVERY_PENDING 恢复边界，物理 episode 引擎和 CLI 未改。

## 测试与限制

最终命令：

```bash
.venv/bin/python -m pytest -q tests/test_rgbd_publication_failure.py tests/test_rgbd_worker_serialization.py tests/test_rgbd_lease_handoff.py tests/test_rgbd_lease_control.py tests/test_rgbd_task_semantics.py tests/test_rgbd_runtime_control.py -k 'not capture_works_without_model'
```

结果：**79 passed, 1 deselected, 1 warning，26.23 s**。日志：`runtime-final-review-tests.txt`。warning 为现有 Starlette/AnyIO alias deprecation。6 个生产源文件的 ruff / mypy 通过，新增序列化测试 ruff 通过。

被排除项是实际渲染测试 `test_capture_works_without_model`：首次未排除运行得到 67 passed / 1 failed，失败为当前 headless 环境没有 DISPLAY，GLFW 无法初始化。没有据此判为功能通过，也没有切 EGL 占用 GPU；真实渲染和 worker 验收由 root 串行负责。序列化测试曾有 `asdict` deepcopy 导致的测试对象身份断言问题，已改为比较 record 内原对象身份；最终 79 项统一重跑通过。

以下 hashes 对应本报告实际复核版本。后续生产源码改动需要重新核对受影响结论。

| 文件 | SHA-256 |
|---|---|
| `src/cloud_edge_robot_arm/simulation_runtime/worker.py` | `6d5366279422582049726b0c11843597c83459ba16fcfbe0698b6aaea189a28e` |
| `src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py` | `8497625d14b8610e5eb1717a93c1f8cfc9802b2696dc1eedad42fb9b73e6ba96` |
| `src/cloud_edge_robot_arm/simulation_runtime/repository.py` | `d53ff8b09227d01c5c728f543c4ae818cb230fc98990fd80fea460589011c980` |
| `src/cloud_edge_robot_arm/simulation_runtime/recovery.py` | `e93613d272ee9960701508225fdcb2ccb7ad7e964f083941871b7d70448a3e88` |
| `src/cloud_edge_robot_arm/simulation_runtime/state_machine.py` | `45710623b67839f6bbc3ec94433416a04d56bc3a0fe2c8d5e71cad95c14a5ed2` |
| `src/cloud_edge_robot_arm/vision/task_semantics.py` | `209f7682b3a192880218322efbcffdad891b017edbe9ed88d53d5b0c67010b29` |
| `src/cloud_edge_robot_arm/vision/execution.py` | `5e341862000de281cebfe0981acf781eb23b2cd135e8e51db93e730dbeaddb5a` |
| `tests/test_rgbd_worker_serialization.py` | `f59c08a3bc3f47135f5b66d3c4c08ba283fcddade8730d1637388b5287469676` |
| `tests/test_rgbd_lease_handoff.py` | `2eea572c84097366671b22a9ca75e044a1a732ce45554dad252ae16d2fb13987` |
| `tests/test_rgbd_lease_control.py` | `54ca60069914b222a3f558da5b807310f41bdde489cbff494ad4a43539eedaad` |
| `tests/test_rgbd_task_semantics.py` | `c5a4dcf3683317dfd9e46377c01ad8879a1d11165eb0e8184576097dd05d86e7` |
| `tests/test_rgbd_runtime_control.py` | `72136d76774b668a1b39d2ffcb1f072d5a791282388cbd6040e5fb94f3df6449` |
| `tests/test_rgbd_publication_failure.py` | `db0e075d9d88e7d75acfe0c007fa15cf07a9beb1916d26ffa06077cdcb2f011d` |
