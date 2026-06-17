# 术语表

- `PCSC`：周期云端监督控制。云端按周期检查边缘执行状态，并在需要时给出监督决策。
- `ETEAC`：事件触发边缘自治控制。边缘端先处理本地事件和恢复，确实无法继续时再请求云端。
- `AUTO`：在 PCSC 和 ETEAC 之间做确定性选择的策略层，不是第三套执行引擎。
- `TaskContract`：云端下发、边缘端接受的高层任务契约，带版本和任务标识。
- `SafetyShield`：边缘安全层。每次技能执行前后都检查运行上下文，发现风险就拒绝或停止。
- `HardwareExecutionGate`：Phase 10 的硬件执行门。真实硬件条件不全时默认关闭。
- `Synthetic Dry-Run`：只走软件框架的 dry-run，使用合成规划摘要，不声明 MoveIt 碰撞验证。
- `MoveIt Runtime Dry-Run`：通过 ROS 2 / MoveIt 做“只规划不执行”的运行，证据中必须有 `sent_to_hardware=false`。
- `Hardware Read-Only`：只读取真实控制器状态，不让机械臂运动。
- `Hardware Motion`：真实机械臂发生物理运动。只有分级验收和操作员确认都满足后才允许声明。
- `artifact`：验证脚本或实验生成的文件。
- `evidence`：用于支撑某个状态结论的证据内容。
- `provenance`：说明证据如何生成的来源、命令、环境和哈希信息。
- `source tree hash`：源码树哈希，用来把证据和当时的实现绑定起来。
- `acceptance level`：真实硬件准备等级，从 `NONE` 到 `LEVEL_6` 逐级推进。
- `operator confirmation`：面向具体硬件动作的一次性、短时有效本地确认。
- `sim-to-real gap`：仿真和真实硬件之间在时序、感知、控制、接触和安全指标上的差距。
