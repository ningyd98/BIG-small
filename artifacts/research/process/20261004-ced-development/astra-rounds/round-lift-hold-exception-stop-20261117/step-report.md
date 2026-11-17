# LIFT 保持异常停止实施记录

基线 `4ed5cb50ada7b6b0ca6b3a2fd168aeca637e3cfa`。本轮源码提交 `41bb33344c0463a979327d0c78e2acd1088b458f`。实际 Astra 规划见本轮 [plan.md](plan.md) 和 [plan.json](plan.json)。实施前复核 12 个输入 SHA256 均匹配；旧探针和原始输出逐字节保留于 [input-evidence](input-evidence/)。

原始故障发生在运动成功后的保持首步：物理步 1821 抛出 RuntimeError，仍保留步 1820 的关节目标，仿真未标急停，会话仍为 SUCCEEDED。修复将保持初始化、物理步、持物反馈、视觉采样及最终测量纳入适配器的异常处理。普通异常先用现有 backend 急停取消轨迹，再返回 `LIFT_HOLD_FAILED`，记录 `failure_phase`、原始异常类型和原因；计步包含已完成但观察器报错的物理步。取消类 BaseException 停止后按原对象传播。领域守卫仍按原错误码和 hold 策略停止。正常保持和交接无额外停止。

八项预期 RED 和换版 GREEN 使用真实无渲染 MuJoCo；覆盖有/无视觉会话、物理步、反馈、取消、双侧持物及脱离路径错误。最终相关回归 76 passed、0 skipped；Ruff、单源码 mypy 与 diff 检查通过。静态检查先发现本轮新增排版和局部变量名冲突，修正后重新验证，未扩大控制逻辑范围。独立审查没有发现新增阻断项。

- [故障测试 RED](../../../20261117-grasp-lift-stop/evidence/lift-red.log)
- [相关回归 GREEN](../../../20261117-grasp-lift-stop/evidence/lift-green-final.log)
- [实际命令、源码及原始证据摘要](../../../20261117-grasp-lift-stop/implementation-receipt.json)
- [审查记录](../../../20261117-grasp-lift-stop/independent-review.md)
- [阶段总结](../../../20261117-grasp-lift-stop/report.md)

本项动态注入证明独立仿真适配器契约；完整 worker 的同类故障处理另由静态审查确认。没有测量真机停止时延与实际停止加速度，不授予正式安全资格。
