**2026-10-05：T9 点运动校准输入的软件准备**

新增纯离线 `prepare_point_motion_residuals`。它重新校验完整 raw-v3 图，按原始 `BEFORE_SUBMIT` 帧及其紧邻的前一份 ONLINE 采集计算既有深度运动观测量，并保留每个分配动作的实际完整物理步、原始预计时长和半开 command 范围。缺帧、缺物理步、时钟映射不可用或判据不兼容时，保留该动作及不可用原因，不补零、不缩短分母。

物体参考点仅从登记 hash 匹配的标记资产解析。独立物理位姿及旋转只进入离线标签；每段点位移除以原始采集/物理区间的单调时钟时间括号，得到**采样割线速度区间**。残差为采样段最大割线速度上端减既有视觉运动观测量后取非负值。没有使用模拟时间速度与墙钟观测速度直接相减，也不接收调用者自选参考点、校准残差列表或缩短后的动作区间。

- 13 个新增软件测试覆盖中段往返运动、旋转引起的点位移、前序帧来源、缺证据、完整动作分母、严格布尔数值拒绝、完整判据脱离别名、资产字节及物体身份。
- 两轮限定 RED 已保存：[缺模块](red-qualified.log) 8 个预期失败；[判据与动作区间](red-criterion-and-horizon.log) 5 个预期行为失败。
- 新模块及既有 raw-v3/风险监督回归共 **129 passed in 47.97s**，见 [GREEN](green-controlled.log)。[Ruff](ruff.log) 与 [mypy](mypy.log) 通过；既有 mypy 未使用配置提示原样保留。
- [软件重建示例](software-example.json) 与 [完整就绪记录](readiness.json) 保存数值来源、判据 hash、源码 hash、验证范围与限制。未运行全仓、实际相机、物理或 provider 实验。

本步仅为 `CALIBRATION_INPUT`。时间括号及完整采样不能排除样本之间的运动，连续运动仍为 `NOT_CERTIFIED`，实际来源准入仍为 `UNKNOWN`。没有拟合或启用风险模型，没有登记独立校准、分组隔离、INITIAL/METHOD/FINAL，也不授予完整物体范围、原生几何/运动界或动作执行权限。原有 reader、recorder、风险登记及在线执行路径未改，未创建 commit。

**独审修复追加：标记登记的嵌套契约边界。** 独立审查在初版中复现了 P2 问题：`RawCaseRegistration` 可持有可变的替代 marker，导致相同登记/raw 图及资产随外部 marker 别名变化而改变输入可用性。初版 129 PASS 日志及其源码 hash 按历史证据原样保留，不能代替这条反例。

本模块现在在读取字段前要求精确的 `PoseMarkerRegistration` 类型，再重建并重新校验该冻结对象。追加的 3 条回归先分别复现可变 `SimpleNamespace`、子类与真实类上伪造 dictionary 的 [RED](red-marker-contract-fix.log)，然后与原 13 项一同得到 **16 passed in 9.66s**，见 [修复 GREEN](green-marker-contract-fix.log)。限定 [Ruff](ruff-marker-contract-fix.log) 和 [mypy](mypy-marker-contract-fix.log) 通过；原始完整动作区间、不可用分母及 UNKNOWN/NOT_CERTIFIED 边界保留。最终源码 hash 与修复元数据见 [修复记录](marker-contract-fix.json)，独立复审待补；未扩大为风险监督接入或真实性验收。

**修复后独立复审：PASS。** 独立运行原 13 项及新增 3 项得到 **16 passed in 9.25s**，并重新执行相同可变别名反例：外部变化前后均为 UNAVAILABLE、原因相同、全部运动数值为空，实际动作及 command 范围保留。当前源码及测试 hash 独立复核一致，原 P2 已关闭，见 [独审追加记录](independent-review.md)、[独审测试](independent-review-fix1-tests.log) 和 [精确反例复核](independent-review-fix1-counterexample.json)。这条 PASS 仅接受本步限定的软件准备，不改变 UNKNOWN/NOT_CERTIFIED 或任何实际研究/执行准入状态。
