# Phase 6 首组正式仿真与离线读回

2026-11-22，以 `6a26ac812f1c215c35031a80e3848252ce3c52e7` 为基线。实施、LIFT 停止诊断及正式读回复核计划均由 `gpt-6.2-astra` 制定。[实施计划](plan.md) · [LIFT 复核计划](../round-v10-phase6-lift-stop-20261122/plan.md) · [读回复核计划](../round-v10-phase6-readback-20261122/plan.md)

## 隔离放行与单次启动

用登记场景 `S01_NORMAL_STATIC`、seed `11921001`、MuJoCo 3.3.7 和 EGL llvmpipe 隔离采集 1 帧 RGB-D。120 个物理步后，RGB 和深度各渲染 1 次，应用回读确认 320 × 240、40,309 个有效深度像素和相机校准版本 `f33940579c533afe`。r593 标记检出唯一 ID 7，最短边 14.25 px，平面中心残差 0.843 mm，小于 2 mm 阈值。同帧通过正式采集用的 bootstrap 校验。预检期间的控制器派发、教师尝试和正式 claim 均为 0。

启动前核对唯一释放组以及登记的 456 项来源文件与基线 Git blob。正式 CLI 为 `native-p0-v10-20261121-0001` 创建唯一 claim、SQLite 作业和租约，由 worker 尝试 1 次。首组输出保存在 `experiments/results/phase-v10-formal-20261122/`。登记文件 SHA256 为 `da431fdb96f8b2672fb621d4ca4c87b673835f26ce874c7ce03da8fb043a7972`，来源 SHA256 为 `186e76435e7dc470175190622e4f3658eaaad4298e6fab214e08110d0e9112b0`。[登记](../round-v10-phase5-20261122/registration/protocol.json)

## 正式采集

北京时间 01:16:31 启动，01:25:59 退出，耗时 567.965 秒，进程退出码为 1。采集为 `COLLECTION_PARTIAL`，worker 终态为 `BLOCKED_BY_ENV`。记录了 6,240 个物理步、28,464 次渲染（精确计数）、11,109 帧、73,394 条 guard 事件。owner、录制器、采集和后端均完成关闭，原件已冻结。核对清单中 55,583 个文件的长度及 SHA256，清单条目合计 6,578,143,222 字节。SQLite 只读快照确认 1 个作业、1 次尝试、1 个租约。

| 动作 | 派发／返回／终步 | 相对返回／截止 | 相对终步／登记额度 | POST 准入 |
| --- | --- | --- | --- | --- |
| `MOVE_ABOVE` | 120 ／ 835 ／ 2,040 | 715 ／ 1,920 | 1,920 ／ 1,920 | ALLOW |
| `APPROACH` | 2,040 ／ 2,600 ／ 3,960 | 560 ／ 1,920 | 1,920 ／ 1,920 | ALLOW |
| `GRASP` | 3,960 ／ 4,200 ／ 4,200 | 240 ／ 240 | 240 ／ 240 | ALLOW |
| `LIFT` | 4,200 ／ 5,155 ／ 6,240 | 955 ／ 1,920 | 2,040 ／ 2,040 | STOP |

四份回执的控制器返回与终步均符合各自动作的 v10 窗口。首动作在 1,920 相对步的等号边界通过，相当于 8.000 秒模拟时间，Shield 记录的墙钟耗时为 164.445 秒。GRASP 的控制器截止与终步也都踩在等号边界。累计 4 个控制器返回，3 个动作通过后置准入，共 8 条 PRE／POST 记录。后续四个动作均未派发，运行未生成 TERMINAL 准入。

## LIFT 停止原因

LIFT 的 POST SafetyShield 记录为 ALLOW，抓持反馈为 PASS，TCP 目标距离为 15.397 mm，容差为 20 mm。以活动 tracker 的 `acquisition-124` 为颜色基准，在末帧 `acquisition-11109` 按原阈值重现两个各 9 像素的候选。编译用的 bootstrap 帧 `acquisition-123` 在目标像素的 RGB 值与活动帧一致。`object_lifted` 和 `object_stable` 因无法确认目标身份而为 `UNKNOWN`，两项均未获准入，决策为 STOP。两个候选的成因尚未确定。

离线物理样本显示物体中心在派发到终步之间升高 85.217 mm。控制器内部 0.5 秒接触保持期间的物体线速度峰值为 0.03484 m/s，终步前 0.5 秒的峰值为 0.00528 m/s。在线 RGB-D 稳定性判定缺少已确认目标的区间估计。

## 离线读回

正式 `--verify` 退出 0，首组重建全部 11,109 帧。完整组的来源、几何、动作窗口与生命周期均未通过。读回诊断记录了已保留的采集失败、命令父区间不可用、guard 来源失败、部分帧标记不可见，以及完整八动作和十七条准入均缺失。组评分和联合界为空，首组与登记册的研究资格均为 `UNKNOWN`，其余八组为 `NOT_RUN`。

Python 登记册入口独立读回同一组原件，调用首组读取入口 1 次，九组结果和登记册诊断均与 CLI 的 JSON 一致。离线物理结果为 `FAILED`，理由为 `PLACE_NOT_STABLE`，实际轨迹停在 LIFT，未到达放置动作。

第 6,240 步结束后，`hold_current_joints` 和 `emergency_stop` 均有原始命令区间与 BEGIN/END 记录。两条记录的父区间为 `unbracketed-operations`，原区间表中无此项。两条命令完成后，外层 `TERMINATION` 区间才启动。guard 的最后一条原记录为 LIFT 准入异常引发的 `FAILURE`。几何读回最先报告第 2,089 步的 `acquisition-3451` 未见标记，诊断仅列出前 12 项几何失败。

完整物理入口按原父区间要求拒绝。只读组件重算复用已核验的原清单，另对选用原文件复核指纹，保留原命令和失败。它对照全部 4 对 PRE／POST，重算 8 次 SafetyShield 和 8 条准入，从原 B／E、grounding、RGB-D、反馈、回执和记录时钟复现 7 条允许及 LIFT POST 的 STOP。共核对 14 条 tracker 时钟。完整判定仍要求 8 个动作和 TERMINAL 原件。

正式前后的两份冻结 v9 协议和 v9 原件清单的 SHA256 均一致。正式 v10 原件、claim、SQLite 及原始日志原位保存在本机。研发分支交付核验摘要、指纹与计划。[验证清单](validation.public.json) · [阶段汇总](stage-summary.public.md)
