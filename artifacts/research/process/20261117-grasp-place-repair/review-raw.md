### Strengths

- 显式路径、可信上下文和执行守卫衔接完整：task/step/skill、冻结终点、1 mm 横向与回落约束均有拒绝测试；模型参数不能自行授予路径或持物授权。
- 持物丢失检查进入逐物理步循环，测试验证了首次失去接触后停止、取消轨迹且不再发送关节目标。
- 相机旋转使用当前完整外参；换视角次数和原采样期限受限，身份、标定及无效深度错误不会被重试掩盖。
- 集成验收同时检查独立物理成功、流程完成、RETREAT 和终帧标记，保留 UNKNOWN/NOT_ACCEPTED 资格边界。

### Issues

#### Critical（Must Fix）

无。

#### Important（Should Fix）

1. **保留负载平衡目标后，新动作重置指令状态，突破交接处的发送目标加速度限制。**

   **位置：** [visual_servo.py:181](/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall/src/cloud_edge_robot_arm/simulation/mujoco/visual_servo.py:181)、[visual_servo.py:289](/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall/src/cloud_edge_robot_arm/simulation/mujoco/visual_servo.py:289)。

   成功的 Cartesian 动作保留最后发送的平衡目标，但下一个控制器以实测 `qpos` 和零速度重新初始化。两者存在负载补偿差，第一条新目标因此发生未经连续限幅的跳变。

   `worker-active-camera-11` 原始 `commands.json` 已复现：MOVE_TO_REGION→PLACE 在物理步 **4192→4216→4221**，关节 2 的目标增量为 **+0.00873341545、−0.00144675926 rad**。按实际发送间隔计算，速度从 **+0.087334** 变为 **−0.069444 rad/s**，差分加速度达到 **7.52537 rad/s²**，超过配置的 **1.66667 rad/s²**。期间没有 `hold_current_joints`；这是普通发送目标的问题。LIFT→MOVE_TO_REGION 同样达到 **3.77441 rad/s²**。

   [verify_evidence.py:99](/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall/artifacts/research/process/20261117-grasp-place-repair/verify_evidence.py:99) 按动作截取指令，遗漏前一动作的最后目标，因此无法发现交接问题。

   **影响与修复：** 交接会突然移除负载补偿并造成目标反向跳变，使持物控制超出所声明的指令限制。应传递最后实际发送目标及其速度状态，明确处理首个控制周期，并加入跨动作连续指令检查及真实运输→放置回归。

2. **斜视相机下，标定深度误差传播漏掉光线的横向分量。**

   **位置：** [servo_region.py:175](/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall/src/cloud_edge_robot_arm/vision/servo_region.py:175)。

   当前 `z_footprint` 使用 `abs(R[2,2]) * bound`。对于 optical-Z 深度，世界高度对深度的导数实际为：

   ```text
   R[2,0]·(u−cx)/fx + R[2,1]·(v−cy)/fy + R[2,2]
   ```

   旋转相机的离轴像素可能具有更大的高度不确定性，导致本应无法确认正高度的侧壁像素被接受。

   已用纯 CPU 解析 RGBD 复现：24° 斜视、`fx=fy=400`、像素 `(205,151)`、深度误差界 1 mm，侧壁实测高度 **2.466501 mm**；代码采用的界为 **2.454851 mm**，完整光线传播的界为 **2.478238 mm**。函数仍返回成功、四个角点锚和 `low_object_sidewall_pixels=1`。

   **影响与修复：** 标定输入可以把不具备充分正高度证据的缺色像素解释为前景侧壁。当前未标定 worker 成功结果不因此失效，但标定分支不符合其声明的拒绝条件。应按每像素完整光线传播深度误差，保守处理像素足迹与深度误差的组合，并添加旋转、离轴、阈值附近的标定测试。

#### Minor（Nice to Have）

无额外项。实施方已发现的格式和类型检查问题仍需收尾。

### Plan alignment / deviations

扩展至 Cartesian 运输/放置、斜视相机和有界可见性恢复，均有实际失败记录、更新设计及用户相机补充支持。RETREAT 去除不消费的目标区几何条件也有合理依据。未发现未说明的重大范围扩张。

上述两项分别影响计划要求的连续指令限制和标定误差传播，应在交付前修复。

### Validation

- 审查了 `git diff HEAD` 和新增源码、测试、设计及报告；31 个输入文件 SHA256 在评审开始与结束时均匹配。
- 无物理仿真的定向检查：**66 passed**；`git diff --check HEAD` 通过。
- 从 worker11 的 **7,585** 个物理样本独立重算：抬升 **0.10522794 m**、持物 **2.825 s**、稳定放置 **9.40833 s**，物理成功；流程完成和终帧 OBSERVED 与原始记录一致。
- 本轮未启动 GPU/物理实验；完整回归、静态检查及修复后的真实运行仍须由实施方完成。

### Recommendations

修复两项 Important 后，更新连续指令验证器，保留此次发现问题的原始成功运行字节，再用修复后的源码完成正式交付所需验证。

### Declined to judge

- 真实相机执行器运动及硬件实时性：本轮仅授权仿真。
- 真实 Sol/Molmo 服务表现：当前使用协议替身，无真实付费调用证据。
- 新 seed 泛化及正式几何/native 资格：当前证据明确限定为固定场景开发验证。
- 实际接触加速度是否受发送目标数值限制：报告已明确不作此保证；问题 1 检查的是发送目标自身。
- 既有 `hold_current_joints` 停止操作的指令突变：属于既有停止语义，未纳入问题 1 的普通目标交接计算。

### Assessment

**Ready to merge? With fixes.**

实现解决了原抓放阻断，并取得可复算的完整物理成功；但普通指令交接超限和斜视标定误差低估仍需修复。收齐修复后的控制、视觉、真实 worker 和全仓验证后再交付。
