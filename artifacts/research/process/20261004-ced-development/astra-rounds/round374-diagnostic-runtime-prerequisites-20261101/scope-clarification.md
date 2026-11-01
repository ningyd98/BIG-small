# R374 范围解释：group05 未启动尾部的余额续跑

实际解释者：**gpt-6-astra**，2026-11-01；本记录不修改 R373/R374 原计划、旧证据或产品。

**可以有限续跑。** group05 是为执行 R374 编排恢复而被中断，未耗尽原900秒额度；这不同于已用满900秒的group01–04。仅从未出现 `started` 事件、且未被deselect的节点可以在原group05剩余额度内首次执行。这是原阶段剩余覆盖的延续，不退款、不重置900秒，也不重跑通过、失败或setup-only挂起节点。

核对原记录：group05开始于 `2026-11-01T03:37:22.585180+00:00`；停止清理完成时点为epoch `1793504272.9992769`。两时点差 **30.414097秒**。原runner未写终态monotonic duration，故这不是精确的child执行测量；为保守账法，把截至清理完成的墙钟差向上取整，先扣 **31秒**，余额至多 **869秒**。若后续发现更大的可信已用时长或时钟异常，必须采用更大的扣费或先记NOT_COMPLETED，不能反向增加余额。

原事件包含156个call通过、40个call失败；当前setup-only节点 `tests/test_operational_prefix_cli_v1.py::test_execute_once_cli_real_worker_no_retry` 保持中断，不能在本解释下重跑。当前assignment中有 **492个**未started且未deselect节点可作为续跑候选；它们不代表已经获运行或会全部完成。

账法：先冻结明确候选列表并引用原事件hash；每个新进程用 `min(API 60秒或非API 300秒, 剩余额度)` 为timeout，每次实际启动到回收的monotonic时长（含该次清理）继续扣余额。保留启动/运行/回收、失败和timeout原件，不重置累计账本。余额不足时余下节点记NOT_COMPLETED/NOT_RUN_BUDGET。原R373八小时墙钟和最后15分钟汇总保留仍优先，完整UTC/T3优先顺序不变。

本余额**不占用也不增加**group01–04各300秒新增尾部quota，不挪用其额度；不是group05额外900秒尝试。所有新输出位于新续跑目录，原group05仍记INTERRUPTED_FOR_ORCHESTRATION_RECOVERY。原40个失败保持失败；本解释不批准修复marker source hash或中文docstring，更不允许重写冻结来源来消除失败。源/golden和R374环境隔离条件保持不变。

本次只读核对并写解释，无测试、进程控制、产品修改或旧证据写入。

证据绑定：

- `artifacts/research/process/20261004-ced-development/astra-rounds/round373-full-workflow-rerun-20261101/implementation/pytest_software_05/invocation.json`：77562 B，SHA256 `e081302c50f9c3522b6d11ca0c319b50ad04fa0640e90a54e8a27984ddae3f3e`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round373-full-workflow-rerun-20261101/implementation/pytest_software_05/pytest-events.jsonl`：244600 B，SHA256 `569eccecf141be23d456899ae4bf9c89fe2da300ba40e3d27854164aa4931b5f`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round374-diagnostic-runtime-prerequisites-20261101/process/interruption-receipt.json`：79672 B，SHA256 `138bbb3e092ca488b8a5369b9fd41f42c821fa39a54f45c138a114279b2c9cf8`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round373-full-workflow-rerun-20261101/assignment-manifest.json`：538600 B，SHA256 `418dc7cd76b09162cc1ea55be631fb84520d37e9ffc26f68694fb661e9a2c171`。
