# 当前净空运行代下 t01 的真实首次横向拒绝

在一个新训练标签下，只领取 `cvfix-t01` 一次。冻结 `442202ab` 原完整 worker 按原分配、ActionClock、Shield 和真实视觉调度执行四个技能，MOVE_ABOVE、APPROACH、GRASP 三个 POST 通过。共封存 186 张原顶视图及 1,747 个积分步。与旧 `train-full-04` 相同的第 1640 步，新实拍反馈得到局部 CLEAR，最小制停净空下界 +7.172 mm。LIFT 共接受 15 次真实反馈，采图至局部判定的最大实测为 53.349 ms，最后一张第 1744 步反馈的制停净空下界为 +7.468 mm。

真实 LIFT 从第 1632 步开始。第 1746 步横偏为 0.999669 mm，第 1747 步达到 1.006545 mm，原控制器返回 `CLEARANCE_PATH_VIOLATION`。当时 TCP 比原起点高 0.684846 mm，两指仍接触工件，工件从第 1734 步起持续离开台面。首拒后只有两条 `motion_terminated` 保持和一次成功急停，MOVE_TO_REGION、PLACE、RELEASE、RETREAT 均未派发。LIFT 完整窗口未建立。旧固定参考的 1.005805 mm 与本次真实 owner 实测分别保存。

原 scorer 的第一冷读进程在第 1392 步 `GRASP/PRE` 因 RGB-D 载物观测结果不一致退出。该日志与原生封包独立保留。本轮不把未完成的原冷读写作完整评分。实拍前曾因手录旧 local-clearance seal 的 SHA 缺一位而在输入检查停止，复核原件后修正登记，再签发批次；此前未领取或复位。t02 为未领取的训练分配。保留组、正式、独立正式评分、独立开发评估、远程与硬件均为零。[采集与首停止数据](t01-current-owner.public.json) · [Astra 计划](plan.md)

另轮以原 scorer 及包外启动双来源清单完成两次独立冷读，确认三个 POST 与完整抓放失败。恢复没有改变原封包。[恢复评分](../round-g1-t01-score-scene-binding-20261126/step-report.md)
