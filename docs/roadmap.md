# 路线图

## 当前阶段

Phase 12 是 Final Experimental Evaluation, Thesis Evidence Consolidation and Project Closure。主线停止无边界功能扩展，集中完成最终实验、统计分析、论文素材、答辩包和软件/仿真项目封板。

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
