# RGB-D 研究开发过程文档

本目录记录本轮分阶段实施的**过程与证据边界**。2026-10-03 首批 P1（T1/T2）已完成：88 项合并回归通过，真实采集平面高度误差最大 2.728 mm，独立审查无未关闭实质问题。验收摘要见[阶段报告](../../../artifacts/research/process/20261003-phase1/phase1-report.json)。实施依据是[研究设计](../../superpowers/specs/2026-10-03-rgbd-evidence-research-design.md)和[依赖驱动执行计划](../../superpowers/plans/2026-10-03-rgbd-evidence-research-roadmap.md)；历史事实以[当前权威状态](../../current_authoritative_status.md)为准。计划中的接口、命令和产物不因写入本文档而成为已实现功能。

当前 T6a/T4/T5 均为 `DONE`。T6a 的真实100/1000静态组通过四入口和分组校验，见[原验收](../../../artifacts/research/process/20261003-t6a/acceptance.json)；T4 在当前物理控制器 v2 下六类真实验收6/6通过，见[因果复验](../../../artifacts/research/process/20261003-t4-physical-skills-v2/README.md)；T5 的新协议20例离线教师为7成功、12失败、1安全违规，逐条重评通过，见[验收](../../../artifacts/research/process/20261003-t5-teacher-accepted/acceptance.md)。

T3 已按预先规定的固定 S01 门槛验收为 `DONE`：沿用已安装的 Qwen3-VL 4B，经 normalized_1000 坐标协议和 RGB-D 几何优化，在 320×240 双图探针中 4/4 通过并冻结；见[本轮验收](../../../artifacts/research/process/20261003-t3-small-model-optimization/acceptance.md)。该结论仅限当前资产中高 5–10 cm 的竖直方块和显式顶抓配置，未执行物理动作；未配置抓取标定时默认拒绝规划。两批独立开发验证合计29/32符合各自判据：有目标定位23/24、目标缺失时模型明确拒绝6/8；其余两条缺失幻觉均被几何校验阻断，一条有目标误拒绝，三条契约均为0步。`all_cases_pass=false`，不把阻断记作定位成功或明确拒绝。上述为 T3 验收时点；截至 2026-10-04，T7 已实施并为 `DONE`，最终454项回归及30个源文件Ruff/mypy已通过，T8/T17a 为 `READY`。本轮是协议与几何优化，未训练或更换更大模型、未下载新权重；仅经 localhost 直连调用，未走代理。原两候选失败产物保留。T6b的10000组仍未运行，不将静态感知或离线教师当作正式在线成功率；最新入口见[当前交接](handover.md)。

当前 T7 同 episode 新帧、三值条件、安全前后检查、有界验证、三种 scope 和独立 DATASET_GENERATION 已落地。v2 同 20 assignments 全保留，2 成功/18 失败/0 blocked/0 false completion，正常 2/12、全分配 10%；[复算](../../../artifacts/research/process/20261003-t7-visual-closed-loop/smoke-20-v2-validation.json)覆盖 34,353 样本、154 帧、52 动作，valid/accepted=true。v1 全失败及源码快照保留；这是当前 MuJoCo 直立有色方块开发 smoke，非正式 G1。[T7 证据目录](../../../artifacts/research/process/20261003-t7-visual-closed-loop/)保存新 4/4 模型冻结、历史来源归档和审查，95 runtime/277 prerequisite 为阶段测试数，最终质量门已由454项回归和独立审查关闭。

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


**T7 最终验收（2026-10-04）：DONE。** 最终 EGL 回归454 passed、1项已有依赖警告，30个源文件Ruff/mypy通过；独立runtime审查无开放P1/P2。真实worker复查1次模型调用、4动作后因抬升保持不足如实FAILED，归档无错误且终态一致。20场景仍为2成功/18失败，未扩大分母；非正式G1。T8/T17a为READY（未实施），T6b为TODO。详见[完整验收](../../../artifacts/research/process/20261003-t7-visual-closed-loop/acceptance.md)。
