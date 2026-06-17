# Phase 9 报告

状态：`PHASE9_CORE_ACCEPTED + ISAAC_VALIDATION_BLOCKED_BY_ENV`。

`verify_phase9.py` 记录的环境摘要：

- OS：Linux 7.0.0-22-generic x86_64
- CPU：AMD Ryzen 7 5800X
- GPU：NVIDIA GeForce RTX 4070 Ti SUPER
- Driver：595.71.05
- Python：3.12.7
- MuJoCo：3.9.0
- ROS 2 / MoveIt 2：环境阻塞
- Isaac Sim：环境阻塞

MuJoCo 运行：

- smoke：18
- validation：2250
- full：11250
- 固定 normal static 验收：20/20 次试验无非法碰撞

完整 benchmark 指标：

- 成功率：0.92
- 平均完成时间：972.0 ms
- 非法碰撞：0
- PCSC/GOOD：云端调用 3.0，检测延迟 100.0 ms，完成时间 845.0 ms
- ETEAC/SEVERE：云端调用 1.0，检测延迟 640.0 ms，恢复时间 840.0 ms，重传 3.0
- AUTO/NORMAL：云端调用 2.0，模式切换 1.0，完成时间 840.0 ms
- seed 0 vs seed 9：joint RMSE 平均值 0.262719 vs 0.269485；sensor latency 平均值 6.369358 ms vs 19.24065 ms

Isaac 和 ROS 结果没有被声明为通过；对应 artifact 只记录环境阻塞原因。
