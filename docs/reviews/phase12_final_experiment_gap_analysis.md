# Phase 12 Final Experiment Gap Analysis

## 当前可用实验能力

- Phase 8 已提供 PCSC、ETEAC、AUTO、多场景、多 seed、网络故障、恢复和消融实验基础。
- Phase 9 已提供 MuJoCo 物理仿真、随机化、指标溯源和 Phase 9 benchmark 脚本。
- Phase 9.2 已提供 Isaac smoke、benchmark 和 MuJoCo/Isaac 成对 artifact 验证。
- Phase 10 已提供 Synthetic Dry-Run、MoveIt Runtime Dry-Run 和硬件门禁证据。
- Phase 11 已提供 Simulation Workbench、Batch、Sweep、LiveRun、metrics、comparison 和 export。
- Phase 11.1 已提供异步仿真任务、SQLite 持久化、lease、cancel、timeout、retry 和恢复。
- Phase 11.2 已提供 Model Control Center、OpenAI-compatible profile、fake Ollama 管理和 planner dry-run。

## 当前可用场景

`scenario_registry()` 是 S01-S15 的权威来源，覆盖正常静态、目标移动、障碍物插入、感知退化、网络退化、云端不可用、命令异常、技能缓存、模式振荡、急停和 SQLite restart。

## 当前指标

已有指标覆盖任务成功、总耗时、云端调用、通信次数、本地 retry、恢复、重规划、安全拒绝、模式切换、cache、事件数、artifact hash 和 runtime recovery。Phase 12 仍需要统一论文表格字段、effect size、置信区间和 blocked 样本统计。

## 可用 backend

- `MOCK`：CI 可运行。
- `MUJOCO`：已有 runtime evidence。
- `ISAAC_SIM`：已有 Phase 9.2 evidence，但普通 CI 可能为 `BLOCKED_BY_ENV`。
- `MOVEIT_DRY_RUN` 和 `SYNTHETIC_DRY_RUN`：只产生规划/安全证据，不执行硬件。
- `PLANNER_DRY_RUN`：只验证模型规划 contract，`dispatch=false`。

## 可用 planner/provider

- `MOCK`
- `RULE_BASED`
- `OPENAI_COMPATIBLE` fake/local test；真实云端需要用户显式配置。
- `OLLAMA` 管理 UI 已接受；当前 installed model count 为 0，真实本地模型 runtime 尚未接受。

## 当前数据缺口

- Full profile 多 seed 最终论文结论尚未运行。
- 真实 Ollama daemon 和本地模型未验收。
- 当前 Isaac 结果依赖环境，环境不可用时必须记录 `BLOCKED_BY_ENV`。
- 真实机械臂 Level 0 hardware 未开始，不能写成真实硬件实验。

## 当前论文问题

需要冻结 RQ1-RQ7，明确自变量、因变量、控制变量、统计检验、接受标准和不能推出的结论。

## 当前统计方法缺口

Phase 12 前已有均值和成功率汇总，但最终论文需要补齐中位数、分位数、95% CI、paired difference、effect size、多重比较限制和缺失样本说明。

## 当前文档状态滞后

README、project_status、roadmap、architecture、verification 和脚本索引需要纳入 Phase 11.2 与 Phase 12；不能继续只写 Phase 11.1。

## 当前不能声明的内容

- 不能声明真实机械臂验证完成。
- 不能声明 Level 1-6 或任何真实运动。
- 不能把 Mock/fake/dry-run/仿真写成真实硬件结果。
- 不能把 smoke profile 写成 full profile final accepted。
- 不能把环境阻塞写成通过。

## Phase 12 实施范围

Phase 12 只完成最终软件与仿真实验评估、统计、图表、论文表格、论文素材、答辩包和项目封板材料。真实硬件路线保持冻结。
