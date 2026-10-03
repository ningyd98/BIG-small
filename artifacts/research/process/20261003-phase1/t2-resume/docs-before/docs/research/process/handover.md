# 当前交接

**截至 2026-10-03：P1 已完成，P2 的 T6a、T3、T4 就绪但尚未执行。** T1 来源审计及 T2 同步 RGB-D 已通过软件、真实采集和独立审查门槛；本轮无真实 VLM 验收、研究物理抓放或新正式实验结果。历史 `PHASE12_REJECTED`、旧 5,580 行排除边界与权威论文运行数 0 保持不变。

## 先读

- [机器可读阶段报告](../../../artifacts/research/process/20261003-phase1/phase1-report.json)：完成项、65 项回归、2.728 mm 平面误差、审查和剩余边界。
- [执行计划](../../superpowers/plans/2026-10-03-rgbd-evidence-research-roadmap.md)：按依赖和验收推进，不按十二周排代理工作。
- [执行日志](execution_log.md)、[验证矩阵](validation_matrix.md)、[决策风险](decisions_and_risks.md)、[变更记录](change_record.md)：实际命令、原始证据和责任范围。
- [本轮补丁](../../../artifacts/research/process/20261003-phase1/implementation.patch)及[源码摘要](../../../artifacts/research/process/20261003-phase1/source-manifest.json)：区分本批改动与已有未提交原型。

## 下一批按依赖执行

1. **T6a 静态数据工厂**：先定义共享 SceneSpec，再完成随机化、离线标签、原子落盘、组划分和导出；验收 100 组后再做 1000 组。不能把单场景捕获样本当训练/测试集；多 geom 物体须合并为对象实例。该任务不依赖 VLM。
2. **T3 真实视觉模型**：双图输入、严格输出、像素映射、模型快照及本机延迟/显存。候选模型尚未验收，不可用记 BLOCKED；同时处理已知 planner.py 类型检查问题。保持在线模型与离线实例/真值隔离。
3. **T4 物理技能**：IK、关节与夹爪驱动、接触抓放；动作必须产生 actuator/step 记录和独立可检查结果。先自由空间，再接触；无成功证据不能用脚本完成代替。

上述任务可以按文件责任并行；共享 backend.py 单写者，GPU/渲染任务串行。T6a 创建的 SceneSpec 由后续 T5 消费；T5 等待 T4/T6a，T7 等待 T3/T5/T6a，T8 等待 T6a/T7。模型受阻时继续独立物理/数据分支。

## 继续工作边界

当前功能分支保留大量先前未提交改动，本轮未提交、未推送。继续前读取工作区差异与[权威状态](../../current_authoritative_status.md)，禁止覆盖或统一暂存无关文件。TestClient 在受限环境曾挂起，同测主机通过；后续异步/EGL 回归使用本机验证路径并保留真实失败记录。

静态平面采集通过不能替代动态场景几何、G1 定位、物理任务成功或 G2—G5 研究结果。阶段定向 Ruff/mypy 与过程文档检查不代表全仓检查通过；旧文档检查和 planner 类型问题已在决策风险登记。本轮未改开题报告 Word/Markdown，也未启动真实硬件。
