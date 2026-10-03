# 路线图

## 当前阶段

2026-10-03 起按 [RGB-D 代理执行计划](superpowers/plans/2026-10-03-rgbd-evidence-research-roadmap.md)开展分阶段改造。路线为：来源与同步观测 → 同一 episode 的真实视觉/物理执行与结果验证 → 有限候选联合决策 → 有界恢复与局部修复 → 冻结评测 → 分析与复现。T1/T2/T3/T6a/T4/T5 已分别验收；T3 已冻结限定方块规划的 Qwen3-VL 4B 配置，固定场景双图定位4/4通过，独立开发集失败保留。截至 2026-10-04，T7 为 `DONE`：同 episode 闭环、三值验证和作业入口已实施，v2 保留同一批 20 assignments，2 成功/18 失败/0 blocked/0 false completion，正常层 2/12、全分配 10%；[独立复算](../artifacts/research/process/20261003-t7-visual-closed-loop/smoke-20-v2-validation.json)为 valid/accepted=true。该开发 smoke 限当前 MuJoCo 直立有色方块，不是正式 G1。最终454项回归及30个源文件Ruff/mypy已通过，T8、T17a 为 `READY`，T6b 仍为 `TODO`。实际范围以[当前权威状态](current_authoritative_status.md)为准。

下列 Phase 11—12 范围保留为历史交付说明。历史 full 为 PHASE12_REJECTED，不是新研究闭环的完成证据。

## 当前核心路线与出口

| 顺序 | 任务 | 必须完成的行为 |
|---|---|---|
| 1. 基础能力 | T6a、T3、T4→T5 | 数据分组、真实 VLM、物理抓放和只读独立评价 |
| 2. 真实反馈闭环 | T7→T8 | T7 已实现同 backend 新帧、三值验证和有界路由，20 场景开发 smoke 已复算；最终454项回归通过，T8 的 120 场景基础先导未运行 |
| 3. 受约束决策 | T9→T10→T11→T12 | 校准风险、版本化证据、成功/失败均重新判断；规则/成本选择有限候选，执行前复核 |
| 4. 可验证恢复 | T13 | 最终验证失败接回恢复；验证后解决事件；次数/耗时/无进展预算；候选契约、边缘接受、实际启动分别记录 |
| 5. 冻结与评测 | T15a/T16a→T15b→T15c→T16b | 工具提前就绪；方法冻结后独立功效先导；正式成功/成本/风险/恢复结果与失败分母 |
| 6. 交付与扩展 | T17、T18；可选 T14/判断 provider | 决策与证据时间线、复现；扩展独立登记，不阻塞核心 |

借鉴 Jev 的有限候选判断与代码编排方式，保持云端规划、边缘判断和安全执行职责分离。先交付规则与校准风险驱动的成本选择；Jev 或其他判断模型仅作为后续可替换 provider 对照，不依赖其服务完成主路线。模型概率不等于物理成功率；远程判断请求计入云模型总成本。详见[研究设计 §4.4—4.5](superpowers/specs/2026-10-03-rgbd-evidence-research-design.md)。

G0—G5、B0—B5、样本量及冻结规则不变。T15a/T16a、T17 按详细计划的依赖穿插；成功判定、恢复和提交语义的修正对基线与新方法共同生效，不以有缺陷旧实现制造优势。

## Phase 11 范围

- S01-S15 场景动态浏览。
- Mock、MuJoCo、Isaac Sim 和 MoveIt Dry-Run capability 展示。
- 单次运行、批量运行、多 seed、模式比较和参数扫描。
- Live Run 事件时间线和 polling fallback。
- Metrics、ECharts 图表、comparison 和 export。
- Reproducibility hash、provenance 和 artifact bundle。

## Phase 11.1 范围

- API 创建 run 后立即返回 `QUEUED`。
- SQLite 作为仿真 job、batch、event、metric、attempt、lease 和 artifact 真源。
- Worker lease、heartbeat、过期恢复和重复消费防护。
- Cancel、timeout、manual retry 和 restart recovery。
- 持久 WebSocket replay。
- MuJoCo M11-01 至 M11-10 runtime acceptance。

## Phase 11.2 范围

- Model Control Center。
- OpenAI-compatible profile。
- Ollama 管理前端和 fake Ollama CI 验证。
- Planner dry-run。
- Simulation AI Console。
- 真实本地模型 runtime 仍未接受。

## Phase 12 范围

- RQ1-RQ7 研究问题冻结。
- F01-F20 最终实验注册表。
- smoke/validation/full 实验 profile；smoke 是 synthetic pipeline sample，validation 调用 actual software runners，full 才形成论文最终结论。
- 统计分析、图表、CSV/Markdown/LaTeX 表格。
- 论文实验材料和答辩演示包。
- 软件与仿真项目封板。

## 冻结项

Phase 11 之后不继续开发真实机械臂 adapter、Level 0 hardware verifier、Level 1-6 实机验收、真实控制器连接、servo enable、brake release、trajectory、MoveIt execute 或真实机械臂运动。

## 后续阶段

- Phase 12.1 validation：完成 actual software runner validation evidence，不声明 full final accepted。
- Phase 12 full：资源允许时运行完整多 seed 实验并发布 artifact bundle。
- Post-Phase 12：真实硬件路线单独立项。

真实硬件路线需要单独重新立项和现场安全审批，不能由 Phase 11 自动恢复。


**T7 最终验收（2026-10-04）：DONE。** 最终 EGL 回归454 passed、1项已有依赖警告，30个源文件Ruff/mypy通过；独立runtime审查无开放P1/P2。真实worker复查1次模型调用、4动作后因抬升保持不足如实FAILED，归档无错误且终态一致。20场景仍为2成功/18失败，未扩大分母；非正式G1。T8/T17a为READY（未实施），T6b为TODO。详见[完整验收](../artifacts/research/process/20261003-t7-visual-closed-loop/acceptance.md)。
