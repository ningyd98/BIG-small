# Phase 6 阶段汇总

首组 `native-p0-v10-20261121-0001` 的隔离 RGB-D 和 r593 预检通过。正式仿真执行 1 次，耗时 567.965 秒，在 LIFT 的后置准入处停止。正式 claim 已消费，原始失败及冻结原件均保留。[步骤报告](step-report.public.md) · [验证清单](validation.public.json)

| 验证范围 | 实际结果 |
| --- | --- |
| 隔离采集 | 1 帧 RGB-D，唯一标记 ID 7，0 次教师尝试 |
| v10 物理步窗口 | 四份已返回回执符合登记，首动作等于 1,920 步且通过 |
| 正式采集 | `COLLECTION_PARTIAL`，3 个动作通过后置准入，LIFT POST STOP |
| 完整组读回 | CLI 与 Python 结果一致，11,109 帧重建，完整组门限未通过 |
| 逐条复算 | 八条 PRE／POST 准入和八次 SafetyShield 决策均与原记录相符 |
| 正式研究资格 | v10 `UNKNOWN`，其余八组 `NOT_RUN`，九组联合界为空 |

视觉跟踪器在 LIFT 末帧找到两个颜色候选，目标的升高与稳定条件均为 `UNKNOWN`，SafetyShield 的同一条 POST 决策为 ALLOW。离线物理样本记录物体中心升高 85.217 mm。采集输出、日志、claim 和 SQLite 保存在本地，冻结 v9 指纹维持一致。
