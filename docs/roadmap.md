# 路线图

## 当前阶段

Phase 11 是 Simulation Workbench Frontend Toolkit。主线从真实机械臂接入转向仿真工作台、前端工具集、Batch、Sweep、指标分析、对比、复现和导出。

## Phase 11 范围

- S01-S15 场景动态浏览。
- Mock、MuJoCo、Isaac Sim 和 MoveIt Dry-Run capability 展示。
- 单次运行、批量运行、多 seed、模式比较和参数扫描。
- Live Run 事件时间线和 polling fallback。
- Metrics、ECharts 图表、comparison 和 export。
- Reproducibility hash、provenance 和 artifact bundle。

## 冻结项

Phase 11 不继续开发真实机械臂 adapter、Level 0 hardware verifier、Level 1-6 实机验收、真实控制器连接、servo enable、brake release、trajectory、MoveIt execute 或真实机械臂运动。

## 后续阶段

- Phase 11.x：完善论文图表、跨后端 paired comparison 和大规模 artifact 分析。
- Phase 12：根据实验结果整理论文、答辩演示和最终报告。

真实硬件路线需要单独重新立项和现场安全审批，不能由 Phase 11 自动恢复。
