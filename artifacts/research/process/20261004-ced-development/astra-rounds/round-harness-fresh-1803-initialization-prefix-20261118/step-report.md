# 2026-11-18 1803 终止前缀与 1804 放行核验

GPT-6.2 Astra 制定方案，GPT-6.2 Sol 实施。冻结产品为 `5103e7f483b9fccd40cf2e49d4bd5ef8979f64d2`。41 个计划输入的摘要在实施前全匹配。1803 原 worker 保留 `ValueError` 类型，父、wrapper、child 均退出 2。初次研究审计因动作未记录控制器返回步，单独发生 `KeyError` 并生成 `AUDIT_REJECTED`。原 worker、已启动槽、模型费率和首次审计原件均留存。 [方案](plan.md) · [输入摘要](verified-inputs.json) · [原审计复现](archived-audit-red.log)

原记录有一次 MOVE_ABOVE 尝试，控制器初始化时在第 120 步终止，开始与结束步相同。真正执行动作和普通 joint_target 均为 0。仅有同刻持位与急停操作，PRE 已通过。SQLite 原件显示唯一尝试失败、无剩余重试和租约释放。新只读报告保留返回步和返回结果为 null，独立物理复算仍为失败。 [1803 复核](1803-reverified.json)

隔离历史复算绑定原 stage-02/post-cloud、动作参考帧、after、目标 Pose 与标记登记。两个标记都实际观测到。规划 TCP 与登记估计分别相距 30.882 mm 与 31.130 mm，超过原 10 mm 门。在 0 和 30.199 ms 两端调用原生产构造器均复现“初始目标与登记标记身份不可用”。原 worker 的详细异常消息未知。 [Astra 独立旧帧复算](prior-and-readback.json) · [1802 正对照与 1803 测量](../round-harness-four-fresh-positions-20261118/initialization-stop-readback-2026111803.json)

配对放行仅用于绑定原索引、episode、worker 和冻结摘要的 1803→1804。其它 ValueError 仍拒绝后继。实际入口在写 1804 的开始回执之前，重新核前三槽、退出状态、累计额度、SQLite 租约、原共享 GPU 锁及外部 GPU 计算进程。独立复核阶段零试次调用。 [负控 RED](prefix-red.log) · [70 个通过项](prefix-green.log) · [未启动的实际门复核](1804-before-begin.json) · [时钟后续验证](../round-harness-fresh-1803-clock-binding-20261118/step-report.md)
