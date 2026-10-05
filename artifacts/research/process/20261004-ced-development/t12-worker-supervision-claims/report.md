# Step 48：持久监督与被动等待 claim

日期：2026-10-05。范围：SOFTWARE_ONLY 实现及 CPU 验证。此报告只覆盖 producer/repository 与真实 worker 桥接；execution/evaluation 集成由主代理负责。没有调用模型、渲染、发动作或进行物理验收，实际模型选择仍为 DEFERRED；cloud/edge/device 研究范围继续保留。

## 实现与证据边界

新增 `src/cloud_edge_robot_arm/repositories/event_autonomy/visual_supervision.py` 与 memory/SQLite/protocol 的监督方法、SQLite 新表 `visual_supervision`。ledger 使用原始 plan、当前 publication、实际 worker lease、exact episode/step/cursor、固定来源 hash 与原始 task/verification 截止时间。注册、重启和后续循环均不重置原始时间或已消耗配额。

监督依次 `RESERVE_CAPTURE → COMPLETE_CAPTURE → RESERVE_PLAN → COMPLETE_PLAN`，camera/provider 必须分别在对应 reserve 之后启动；WAIT 独立 reserve/complete。CAS 使用当前 ledger revision/hash 及当前来源。历史重复只返回历史 disposition，不恢复效果权限；本实例持有的 local handle 完成前即消耗，丢失 pending、失败或重启均不重放、不退款。模型 receipt 只提供来源，不授动作权限或替换合同。

首次登记须与已采纳 bootstrap 的原始 model/role/source/limits/origin 一致。worker 额外读取真实持久 job config，并冻结配置 hash。监督仅接受显式 `draft.parameter_overrides.supervision_period_ms`；无配置时为 None。WAIT 仅接受真实 `advance_physics_during_wait=True`；无配置时为 False。runtime options 与这些实际配置严格相等，不能用调用方开关制造授权。

周期候选仍以首次 job/task origin 和真实周期固定。监督 capture/provider 上限是严格落在原始有效截止时间之前的周期候选数：`max(0, ceil((effective_deadline - task_started_at) / period) - 1)`；未配置周期时为 0。该池与 reactive `max_reobservations` 分开，不改 ordinary verification/retry 池或原始 Tcap/Rcap。WAIT 总分配秒数不超过同一原始有效时间窗口；完成的实际耗时不超过该次分配。ledger 记录 WAIT 成本来源，不是物理时钟/UTC 认证，也不是第二个动作控制器。

## worker 桥接

`src/cloud_edge_robot_arm/vision/worker_runtime.py` 提供不可变 JSON-backed `VisualWorkerSupervisionClaim` / `VisualWorkerSupervisionFrame`，其嵌套 typed getter 返回 detached 数据。frame 带 publication hash、step、完整 original、RGBD/context 与 model/cloud/source snapshot；provider 线程不读 backend 或 `robot.get_state()`。

公开接口：

- `validate_runtime_options(period_s, advance_physics_during_wait)`；`validates_wait_policy(robot_state)`。
- `initialize_supervision(period_s, robot_state)`。
- `reserve_supervision_capture(cursor, robot_state)`；`complete_supervision_capture(claim, observation, context, robot_state)`。
- `reserve_supervision_plan(claim, robot_state) -> VisualWorkerSupervisionFrame`；`assert_supervision_plan_pending(frame)`；`complete_supervision_plan(frame, decision, robot_state)`。
- `reserve_wait(duration_s, robot_state)`；`complete_wait(claim, elapsed_s, robot_state)`。
- 初次 original 尚未登记时，`assert_owned_plan_wait(claim_id, robot_state)` 只读验证本实例当前 durable bootstrap PLAN_PENDING、真实 WAIT flag 与冻结 job hash，沿原始 PLAN 截止时间被动等待。
- `classify_supervision_reply(frame) -> CURRENT | EXPIRED`；`supervision_source_publication` typed property。

所有可选边界前后检查真实 job lease、配置、固定 role/source 文件、当前事件取消/关键事件及原始截止时间。provider 的前后边界均严格 join 当前 publication hash、完整 original/ledger 来源、未 exhausted verification pool、model/role/cloud/inventory；普通 CP 合法推进后旧 PLAN_PENDING 也不能进入/返回为可用来源。已实际请求的成本留在 ledger，不恢复权限。

job DB 与 event DB 不构成同一个事务；这里明确提供分开的 before/after 来源验证，没有宣称跨数据库原子性。

## observer source 与 TTL

既有 `get_visual_owner_publication` / `current_publication` 仍保持严格当前 grounding action TTL。新增只读 `get_visual_supervision_source_publication` 验证完整原始/active contract/checkpoint/pool/retry/ancestor 的同一当前来源与绝对截止时间，允许 observer/budget 在长原子动作期间读取 grounding 原发布来源。它不授予新的 dispatch 权限。

经主代理明确授权，runtime 的 original/verification budget 读取使用该 source-only 来源；仅 EFFECT_PHASES 且带 exact typed completion 的 route，以及 effect capture 来源验证使用它。native/普通执行 publication 继续严格。AFTER_EFFECT completion 若 started_at 已不在原 grounding validity 区间内，或者 source checkpoint 外来，仍拒绝；原区间内启动、后来返回的真实 typed receipt 可以进行效果观察。

原 ordinary TTL 未放宽。实际 integration 调试发现 memory/SQLite COMPLETE_PLAN 年龄分别约 6.30/6.55 秒，超过冻结 5 秒。`classify_supervision_reply` 先验证 current source/lease/config/cancel，再分类年龄；消耗 local handle 后仍可只读分类同一 durable PLAN_PENDING。只有确切 commit rejection 加确切 TTL 过期产生 `VisualSupervisionReplyExpired`；任意 write 异常、配置/来源/取消失效不会被年龄掩盖。迟到回复 DISCARD、pending 成本保留。

## 有界缓存

两种 repository 都只缓存每 task 当前一份已经完整 replay 验证的 immutable JSON。memory exact key 是当前原始字符串；SQLite exact key 包括 task_id/revision/definition_hash/record_hash/payload_json 全部当前 row 字节/索引字段。字节或元数据改变时重新 replay/type/hash 验证；getter 返回新的 detached frozen record。不会按 revision 累积多个大 RGBD 缓存副本，当前 publication/lease/TTL 不被缓存成权限。

## 验证记录

新增测试：`tests/test_visual_supervision_repository.py`、`tests/test_visual_worker_supervision_runtime.py`。真实 SQLite job repository + memory/SQLite event repository，synthetic SOFTWARE_ONLY RGBD/decision，不调用 provider/backend。

验证覆盖缺失 producer/bridge、sticky canonical STOP、claim commit 后 current pub 漂移、current event cancellation、TTL crossing、expired grounding 下 late-start/foreign effect，以及缓存 payload/index 篡改。已记录的 qualified RED 包括缺失 producer/bridge、sticky STOP、commit 后 pub 漂移、event cancellation、expired grounding 下 late-start，以及最后 reviewer 的真实 CP 推进 case；后者在两种 repository 都复现 `DID NOT RAISE`，修复后通过。

| 检查 | 实际结果与范围 |
| --- | --- |
| 完整 owned 两文件，在最后 provider source join 修复之前 | 79 passed，143.05s，无 skips |
| 最后 source join 修复后：真实当前 pub 推进、正向 owned receipt、TTL crossing | 6 passed，42.37s |
| 独立 effects reviewer 的 exact source/context 与真实当前边界 probe | reviewer 报告 6 passed，12.44s；独立确认 helper 无 backend 读取 |
| Ruff，5 个 owned source + 2 个新增 tests | All checks passed |
| Ruff format check，2 个新增/扩展 source + 2 个新增 tests | 4 files already formatted |
| mypy，5 个 owned source | Success: no issues found in 5 source files；既有 ament/rclpy unused-section note |
| 较早阶段相关 owner/bootstrap/verification/runtime 回归 | 396 passed、6 skipped，215.04s；这是较早阶段结果，不替代最新合并验收 |

最后新增 current-source case 为 memory/SQLite 两项，因此当前 owned collection 为 81；最终合并测试由主代理在源冻结后单次运行。没有在此重新跑全仓。较早 6 个 skip 是参数化 fixture 的 SQLite-only 写失败与 memory-only/SQLite-only publisher 测试互斥项。

可复核命令：

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_visual_supervision_repository.py tests/test_visual_worker_supervision_runtime.py -q -ra
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_visual_worker_supervision_runtime.py::test_provider_entry_requires_the_actual_current_publication_not_only_pending_claim tests/test_visual_worker_supervision_runtime.py::test_owned_capture_then_provider_receipt_bridges_once_without_reactive_pool_debit tests/test_visual_worker_supervision_runtime.py::test_commit_crossing_original_ttl_is_classifiable_after_local_handle_consumption -q
```

同目录 `source-hashes.json` 只保存这次 5 source / 2 tests 的 SHA-256，没有复制既有大量源快照。既有 frozen artifacts 未改；此报告不作模型可用性、硬件时序或正式物理验收主张。
