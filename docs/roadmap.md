# 路线图

## 当前阶段

2026-10-04 按用户要求更新为[云、边、端整体执行计划](superpowers/plans/2026-10-04-cloud-edge-device-research-roadmap.md)：云端Qwen3.8-Max规划，边缘可替换受约束判断，端侧OpenCV＋RGB-D几何与现有控制器。**边缘模型后续选型，暂不锁型号；近期先补端侧证据与云Max角色适配。** 新路径尚未实现或冻结，计划与能力验收分列。

T1/T2/T3/T4/T5/T6a/T7保留历史限定DONE，T17a已DONE；T8为IN_PROGRESS，v2全120例5成功、静态4/40，独立复算一致但初次冻结拒绝。固定机会/离线故障证明及基础B0周期筛选前移，解除原T8与T11/T13的依赖等待。实际范围以[权威状态](current_authoritative_status.md)及[阶段总结](research/process/continuation_20261004.md)为准。

下列 Phase 11—12 范围保留为历史交付说明。历史 full 为 PHASE12_REJECTED，不是新研究闭环的完成证据。

## 当前核心路线与出口

| 顺序 | 任务 | 必须完成的行为 |
|---|---|---|
| 1. 共同基础补强 | T7b／T3b | OpenCV身份、遮挡、抬升及完整放置证据；Max双图/结构化规划/角色快照；现有控制器不另造 |
| 2. 基础冻结 | T8a→T8b | 离线固定机会/200可恢复性证明、四周期B0筛选、新120基础先导、预算及INITIAL；不等待在线T13 |
| 3. 受约束决策 | T9→T10→T11→T12a | 校准风险、证据/提交复核、公平基线、规则/成本provider；模型选型T12b后置 |
| 4. 可验证恢复 | T13 | 验证后解决、有界持久预算、候选/接受/启动区分、局部修复/B4；完成动作不重放 |
| 5. 冻结与评测 | T15a/T16a→T15b→T15c→T16b | 固定完整方法/provider后用独立120估功效，FINAL后正式N、机会/恢复及全分母统计 |
| 6. 交付与扩展 | T17b、T18；可选T14等 | 三层证据与成本、复现/负结果；扩展独立，不替代核心 |

边缘先实现可替换DecisionJudge接口与规则/成本选择；后续模型先影子、再selection、启用前冻结并复验共同基线。模型概率不等于物理成功率。架构A0/A1/A2探索与B0—B5机制对照分开，详见[新版设计](superpowers/specs/2026-10-04-cloud-edge-device-research-design.md)。

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
