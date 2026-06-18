# 路线图

## 当前阶段

Phase 11.1 是 Simulation Runtime Orchestration and Persistence。主线从真实机械臂接入转向仿真工作台和仿真任务运行时，补齐异步队列、SQLite 持久化、恢复、cancel、timeout、retry 和 MuJoCo runtime acceptance。

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

## 冻结项

Phase 11 不继续开发真实机械臂 adapter、Level 0 hardware verifier、Level 1-6 实机验收、真实控制器连接、servo enable、brake release、trajectory、MoveIt execute 或真实机械臂运动。

## 后续阶段

- Phase 11.x：完善论文图表、跨后端 paired comparison、大规模 artifact 分析和可选自托管 MuJoCo runtime CI。
- Phase 12：根据实验结果整理论文、答辩演示和最终报告。

真实硬件路线需要单独重新立项和现场安全审批，不能由 Phase 11 自动恢复。
