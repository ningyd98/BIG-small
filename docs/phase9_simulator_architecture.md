# Phase 9 仿真架构

`SimulatorBackend` 暴露 reset、step、关节状态、TCP 位姿、接触、传感器帧、关节目标、夹爪命令、急停和物理故障注入。

MuJoCo 是 CI 和批量实验后端。Isaac Sim 通过 ROS 2 或 bridge protocol 作为独立进程的高保真目标。ground truth 只保留给评估指标，不能作为正式控制输入。
