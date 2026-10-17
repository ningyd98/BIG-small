# R204 T2 Preparation and Runner Applicability Plan

> 唯一源码作者：原 /root/p6_stage_b_sol（gpt-6.1-sol）；ROOT 负责元数据与门禁。按既定 SDD 执行，不另派作者。本文由实际 gpt-6-astra（/root/astra_status_plan）制定，仅计划。

**目标：** 修正 T2 夹具出处和运行记录适用性，恢复可审核的 T2 准备；不重写 R158 的产品合同。
**合同：** R158 plan.json tasks[1]、dual_database_protocol、fixture、T2 七节点和原两命令。20 条路径、两个 600 秒单次命令不变。

已确认原 runner 将 fixture_map 固定写成 T1 路径。T2 尚未运行；新模式和私有接口缺失是原合同预期，不是新的产品失败。R205 已处理规划 reader 的 Markdown 分类错误，原错误保存不动。

## 本轮差异

- T2 分支选择真正 implementation/t2/fixture-map.json，并绑定其 SHA；增加明确 T2 资源输出环境和实际 sidecar 汇总。非 T2 行为和历史回执不变。
- T2 子进程仍最多 600 秒；一次结束清理总期限不超过 15 秒，记录真实 reap/残留/错误，不再以无界 wait 或 caps 代替实测。
- 七个节点先执行分配前 _b_t2_api 明确缺失合同断言。此 RED 仅为接口 RED；GREEN 必须走全部真实锁、双库、预算和 writer 正反例，不得只通过 callable/hasattr。
- Memory/SQLite 指事件仓库，job 一直是实际 SQLite。18 是七节点 worker 生命周期上限，不是实际分母；所有分配和部分初始化必须 finally 关闭并留证。

## 准备步骤与门禁

- [ ] ROOT 全读计划并核输入，独占保存完整 before；只释放 runner/测试/报告准备。
- [ ] Sol 保留测试当前 168003 字节前缀，追加原七节点与 T2 helpers；修改 runner 仅限 JSON 合同列出的 T2 分支。
- [ ] ROOT 全文核七正文、runner、精确 diff、T2 fixture-map、真实等待进入和四 COMMIT seam。证据 sink/线程/锁/连接关闭必须具体可检查。
- [ ] 单独预留并运行原 RED 一次；若为七个明确缺失合同断言，按接口 RED 接受，随后才允许原 T2 产品实现。
- [ ] 完整实现后重新全文/输入门控原 GREEN 一次；七正文和真实资源必须完成。再走原 fresh T2 review，不能据准备计划宣称完成。

四 COMMIT seam：event PENDING、job receipt、event COMPLETE、job COMPLETE；均在真实 SQLite 提交后故障，保留实际持久历史，精确私人 owner continuation 与重启 UNKNOWN 区分。只有 job BEGIN 或意图标记不能证明真正等待 event lock；最终具体无权限替代的观察 seam 必须经 ROOT 审核。

## 保护与预算

正常元数据核对已确认 20 个当前 baseline、211 个保护项、4 个 T3-only 文件及 2 个 T1 追加测试。八项已接受 T1 delta 不写回原 pin。所有原 raw/goldens/计划/预算保留；受控角色/gate 更新先全量归档、CAS，只动对应 T2 项。

零新增产品/测试/静态/Git/审查槽；两原 t2_red/t2_green 各 0/1 HELD。当前仅计划冻结，实际执行仍须 ROOT 逐门释放。T1 受限接受保留，T2/B9/T12/native/formal 不晋升。

精确输入 SHA、20 路径、原 argv/env、fixture/runner 变更区、CAS 输出路径及停止规则见 plan.json；当前观察和完整实际输入清单见 input-observation.json。MD 不重复大段 JSON。

