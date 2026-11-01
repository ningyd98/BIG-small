# R376 独立代码审查（运行终态待复核）

结论：**CHANGES_REQUIRED_RUNTIME_PENDING**。Critical 0，Important 1，Minor 1。未运行测试、产品导入、网络、信号或 Git 变更；唯一写入为本报告及 JSON。

## Strengths

- 完整 ExperimentManifest 在 create_job 之前构建并 JSON 序列化；synthetic test/hash 身份明确，draft truthiness 默认语义及任务/租约参数保留。
- 短合同三变体验证真实 SQLite 持久化与真实 service.get_run；仅抑制 dispatcher.start，不伪造公共结果；修改调用方嵌套配置及读取副本后再查库验证快照独立性。
- git diff 中原 T3 故障、公有读出、corruption、legacy、reopen 断言未删除或放宽；poll 返回值先赋值后断言等价。
- 普通路径 invalidate 委托一次并捕获 active sys.exc_info；finally 的状态查询失败独立记载且仍执行既有 cleanup。
- 运行器采用独立新 stage 目录、明确 env、阶段 monotonic timeout、剩余预算门槛及 TERM/KILL/reap 回执；无自动重试。

## Critical

无。

## Important

### R376-CR-1：交叉 MonkeyPatch 生命周期在 confirm_timeout 后残留 invalidate 诊断闭包

- 位置：`tests/test_operational_runtime_closure.py:5165`；关联行 5146, 5535, 5543, 5772, 5775, 5801。
- 问题与影响：_b_t3_exercise 的内层 scoped 将原方法 O 改成诊断 D；during_episode 经外层 fault_scope 将 D 改成故障 F。内层先 undo 恢复 O，外层随后 undo 恢复自己保存的 D，因此最终类方法是 D 而非 O。D 持有已结束 worker 和 diagnostics；重复调用会叠加诊断闭包并污染同一 pytest 进程后续案例。_b_t2_observe 的 methods 只登记自己包装的 __init__/poll_once/close，不验证 invalidate，故 observers_restored=true 不能证明这里已恢复。
- 证据：Static source proof; no test or product import performed。
- 建议：先依 AGENTS 生成新的实际 Astra 计划；让同一方法的补丁按严格 LIFO 作用域撤销（例如统一所属补丁栈或把故障作用域置于诊断作用域内部），并新增/使用短合同检查正常及异常退出后类方法 identity 恢复。不得以独立进程退出替代恢复验证。

## Minor

### R376-CR-2：清理期间的第二次终止信号可跳过清理回执

- 位置：`artifacts/research/process/20261004-ced-development/astra-rounds/round376-t3-test-input-contract-20261101/run_stage.py:140`；关联行 101, 119, 144, 146, 161, 163, 165。
- 问题与影响：SIGTERM/SIGINT handler 一直到清理循环结束后才恢复，handler 会抛 InterruptedError。首次中断进入 finally 后，若第二次信号在 wait/进程扫描/清理循环中到达，该异常会直接退出 finally，跳过后续 KILL/reap、handler 恢复及 cleanup/result JSON。当前未观察到该路径，也不否定已完成正常运行的回执；它是运行器在重复取消下的稳健性缺口。
- 证据：Static exceptional-path review only; no signals sent。
- 建议：后续运行器修订时让清理区间的取消处理幂等，确保后续信号不会阻断有界清理和最终回执；遵循新 Astra 计划，不在当前活动运行中热修改。

## Declined to judge

- 剩余四个长节点及整轮 T3 完成判定：主执行者声明仍在运行；本审查只读稳定代码，不运行或复跑测试，也不把提供的阶段状态升级为完整验收。
- commit_close 历史失败的具体产品根因：R376 计划明确为未知且需新原始异常证据；代码审查不能由 manifest 修复推出同根因或已闭合。
- 受保护 local_temporal 候选、两份未跟踪 temporal 测试和两个嵌套 workspace 的质量及交付：明确排除在本轮改动和审查范围之外；仅核对计划中的原始非编辑输入 pins，未修改或纳入交付。
- 标记版本绑定、浏览器 input_mode、资产 manifest 修复：plan.json deferred_roots 指定后续独立轮处理，本轮不据此扩大修改范围。
- 真实 MuJoCo、硬件、云端、UTC 联合 600 秒及正式研究验收：本轮是 CPU 软件 fixture 合同修复，现有代码和提供状态不能支持这些结论。
- Git 提交、推送和远端完整复现包验收：本席禁止 Git 变更及网络，尚无本轮交付终态证据。

## 验证边界

对比基线 `28ac315c2af8567b377e6e2cc3ee5acb9cda4677` 的两份测试 diff，完整读取新增合同测试、R376 plan/progress/runner，并检查相关生产模型、真实读服务、SQLite 创建和连接、invalidate 实现与 T3 故障/observer 生命周期。计划 59 个非编辑原始输入的 bytes/SHA256 全部一致。审查输入快照见 JSON。

本席仅采用主执行者提供的 RED/GREEN/smoke 与 confirm_timeout 已完成状态作为背景；没有把剩余目标计为通过。Critical/Important 修复前必须遵守根 AGENTS 的实际 Astra 新轮要求。短合同与 fixture 本身未发现需要阻断的问题；新增诊断补丁的清理恢复需要先修复。完整运行及最终交付可继续由同一 review seat 复核。

只读工具备注：系统没有 `python` 命令，之后用 `python3` 读取 JSON 并计算哈希；这不是产品/测试失败，也未因此实施修复。
