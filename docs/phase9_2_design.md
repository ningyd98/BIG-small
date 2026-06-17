# Phase 9.2 设计

Phase 9.2 关闭的是 Phase 9 MuJoCo 核心之上的仿真验证栈，以及 Phase 9.1 ROS 2 / MoveIt 运行时验收之上的补充验证。

目标状态是 `PHASE9_2_ACCEPTED`，也就是：

- ROS 2 仍然是 `ROS2_INTEGRATION_VALIDATED`。
- MoveIt 2 仍然是 `MOVEIT_SAFETY_VALIDATED`。
- 真正的 Isaac Sim 6.0 进程产出 `ISAAC_SMOKE_VALIDATED`。
- Isaac benchmark artifact 结果是 `PASSED`。
- MuJoCo 与 Isaac 的成对 artifact 产出 `CROSS_BACKEND_VALIDATED`。
- Phase 9.1 aggregate 可以推进到 `PHASE9_1_ACCEPTED`。
- 安全压力测试保持通过，并且 artifact 溯源完整。

## 运行边界

Isaac Sim 永远不会被导入到核心 Python 或 conda 环境。唯一支持的运行路径是：

- Standalone：`ISAAC_RUNTIME_MODE=standalone`，使用 `ISAAC_SIM_ROOT/python.sh`。
- Container：`ISAAC_RUNTIME_MODE=container`，并使用固定的 Isaac Sim 6.0 镜像 tag 和记录过的 digest。

核心包通过外部 JSONL 进程协议和 Isaac 通信。源码守卫和协议 fixture 对 CI 有帮助，但不能代替运行时验证。

## 证据流

```text
兼容性检查
  -> Isaac standalone app
  -> Isaac smoke artifact
  -> Isaac benchmark artifact
  -> MuJoCo / Isaac 成对运行
  -> Phase 9.2 aggregate verifier
```

`scripts/phase9/isaac_standalone_app.py` 负责真实 Isaac `SimulationApp` 生命周期。它会创建或加载 USD stage，添加 Panda/Franka articulation、table、target、obstacle、RGB-D camera 和 contact sensor，推进物理，并写入进程溯源和传感器 artifact。

BIG-small 的边界保持不变：MoveIt 只负责规划；执行仍然经过边缘安全边界。

## 非目标

Phase 9.2 不验证真实机械臂。它不声明真实相机标定、硬件急停接线或物理机械臂性能。
