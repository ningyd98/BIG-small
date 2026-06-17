# 真实机械臂配置

真实机械臂配置和仿真配置分开维护。不要把 `configs/phase9/*` 或 `configs/safety/test.yaml` 里的值复制到硬件 profile。

`configs/real_robot/example.yaml` 只能作为模板。它里面是占位值，加载器会故意拒绝，直到现场人员替换成真实配置。

必填字段包括：

- 厂商、型号和序列号。
- 控制器地址。
- ROS namespace。
- planning group、link、joint 名称。
- 低速速度/加速度比例。
- 工作空间边界和负载限制。
- 急停 topic。
- 硬件状态 topic。

加载器会记录配置来源和稳定配置哈希。仓库不提交真实 IP、序列号、secret 或凭据。
