# RGB-D 研究开发过程文档

本目录记录本轮分阶段实施的**过程与证据边界**。2026-10-03 首批 P1（T1/T2）已完成：88 项合并回归通过，真实采集平面高度误差最大 2.728 mm，独立审查无未关闭实质问题。验收摘要见[阶段报告](../../../artifacts/research/process/20261003-phase1/phase1-report.json)。实施依据是[研究设计](../../superpowers/specs/2026-10-03-rgbd-evidence-research-design.md)和[依赖驱动执行计划](../../superpowers/plans/2026-10-03-rgbd-evidence-research-roadmap.md)；历史事实以[当前权威状态](../../current_authoritative_status.md)为准。计划中的接口、命令和产物不因写入本文档而成为已实现功能。

| 文档 | 用途 |
|---|---|
| [phase_progress.md](phase_progress.md) | 六阶段任务覆盖、依赖与状态 |
| [execution_log.md](execution_log.md) | 授权、实际执行记录及原始日志入口 |
| [validation_matrix.md](validation_matrix.md) | 关键能力、验证命令、证据门槛与状态 |
| [decisions_and_risks.md](decisions_and_risks.md) | 已裁定事项、资源与模型风险 |
| [change_record.md](change_record.md) | 本轮文件变更与实际实施结果 |
| [handover.md](handover.md) | 当前交接边界与下一步 |

记录口径：`planned` 只表示计划；`SOFTWARE` 是软件测试；`REAL_CAPTURE` 是 MuJoCo 同步 RGB-D 实际采集；`REAL_VLM` 是真实本地视觉模型调用；`PHYSICS` 是 actuator/step 物理执行；`HARDWARE` 是真实硬件。一个层级不能替代下一个层级。提前阻塞后的阶段记 `NOT_EXECUTED`，保留预分配任务分母；无法运行的真实阶段记 `BLOCKED` 并给原因。真实硬件实验不在本轮范围。历史 `PHASE12_REJECTED` 与权威论文运行数 0 保持原口径，旧 5,580 行不纳入新物理评测分母。

更新规则：只在命令实际执行、原始证据可定位且审查通过后，把相应任务或能力改成 `DONE`。新任务入口及未来产物以代码格式标为“待生成”，避免把未存在的路径写成可点击证据链接。
