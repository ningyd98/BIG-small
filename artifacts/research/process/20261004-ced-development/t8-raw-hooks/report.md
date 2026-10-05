# T8 原始物理/执行器旁路证据

实现真实命令episode/step/单调seq/原始目标与实际裁剪目标、夹爪open与终止hold目标记录；command_records深复制，未改变驱动规则。增加不保留历史的ActuatorStepObservation逐mj_step前输出回调（真实控制值、目标、preq、bias、gain/range），与原物理步进观察器共存，回调禁止后端写入。T5教师新增可选physical_observer（入口+每步）与action_observer（原ActionResult/step范围/1-based半开command_seq范围），不新增执行器，成功与失败动作均按实记。

3项原始钩子RED、1项教师钩子RED先行；4项新测试与已有observer/motion/T5教师合计24passed，正确EGL环境，日志t8-raw-hooks-and-teacher-green.log。另16项较小覆盖套件通过，与24有重叠。Ruff及2生产文件mypy通过。失败的首轮合并渲染因漏设EGL中止；第二轮错误为测试fixture import被Ruff自动移除，已修正明确fixture wrapper；原始日志保留。

证据范围：新测试含实际MuJoCo NO_CONTACT教师失败，不为独立200组证明或在线恢复G4。真实源生产器将调用同一钩子，完整正式来源/归档/校验仍未执行；独立审查待执行。后追加hold目标日志是被动字段增量，须与producer实际集成再验证。

## 审查修复第一轮

P1教师入口先拒绝observercallback重入，不能改变已有只读状态；P2reset清除actuator观察器。两项针对性RED均复现后修正，原始钩子/物理step/targetmotion/T5教师26passed，Ruff及2源文件mypy通过；fix-round-1.diff/hashes记录精确差异。实际开发原始数据与旧sourcehash只读保留，未重写成新版本实验；还需复审。
