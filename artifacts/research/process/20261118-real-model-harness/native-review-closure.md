# 相机绑定两项缺陷复核

**原审查的两项 Important 已在修后源码上独立复现为拒绝。完整协议回放的验收仍未通过。** 本次使用真实 fixed-02 原帧做 CPU 检查，读取主流程已完成的 EGL 回放原件。审查本身没有启动 renderer、GPU、模型或 API。

## 原始反例

独立抽取前次审查报告中的脚本，使用组件实际传入的 `verify_mujoco_calibration=True`，保持原始采集时刻、像素、深度及几何算法。分别在调用前保存 `last_observation`、`last_accepted_marker`、`_last_target`、成功观测 ID 集和视觉记录。

| fixed-02 故障输入 | 实际拒绝 | 状态复核 |
|---|---|---|
| MOVE 采用 step-05 sample-0104 作参考，sample-0105 拒绝后请求 view-01，却收到晚 8 步且机位不同的 sample-0106 | `servo physics time advanced during camera reobservation` | 两个对象引用保持原值，目标数组、成功观测 ID 集保持原值，视觉记录空 |
| PLACE 采用 step-06 sample-0014-view-02 作参考，sample-0015 非平面后收到正确 view-01 的原图。将版本改成 1111111111111111 并重算 RGBD 封包摘要 | `servo MuJoCo calibration does not match frame intrinsics and pose` | 同上。内外参对应版本仍为 d7ed4da1b0052f10 |

拒绝尝试 ID 按设计进入独立的已采集 ID 集，阻止后续尝试重用拒绝帧。两例均未返回控制目标。组件的提案刷新位于成功视觉测量与 SafetyShield 之后，两条拒绝均无法到达刷新点。

## 新增约束

- 每次备选采集先核验同组模拟时刻和完整光学外参，外参包含 position 与 look-at 对应的朝向。普通观测错误、精确非平面错误共用这一检查及最多两个备选的循环。显式非平面 RETREAT 替代帧仍需通过当前严格区域门。
- 标定复算按四项内参和十六项行主序外参打包为小端 float64，比较 SHA256 的前 16 个十六进制字符，覆盖跟踪参考、技能参考及后续帧。显式 MuJoCo 组件开启此校验。原有调用的默认值为 False。
- 组件在采集和移机前后、返回目标前，核对模拟步、模拟时刻与命令游标。每次移机只接受一条与期望 pose 和 aim 匹配的相机命令；采集期间禁止新增命令，命令检查只访问新增后缀。该守卫检测违规并停机。视觉记录和控制接纳分别由 `visual_samples` 和 `control_samples` 记载；完成一个视觉测量后还需盾、最终守卫及控制期限通过。
- 独立短测重跑了该轮 `camera_binding_replay_test.py` 的 10 项真实帧正反例，以及 `tests/test_sol_molmo_component_safety.py::test_component_sample_guards_backend_and_only_new_camera_command` 的 5 项守卫用例，均通过。主流程冻结的完整 CPU 结果为 235 通过、3 项渲染测试未选。修后冻结清单的 50 个源文件及 4 个测试文件逐字核验通过。

## 运行记录与边界

修后唯一完整零 API 回放 `native-camera-binding-replay/green` 的 JUnit 为 **1 failed**。LIFT 在物理步 2480 以 `ValueError:servo frame not fresh` 停止，worker 为 FAILED，独立物理结果为失败。最后一个 joint_target 在 2477；2480 记录两条 hold 和一条 emergency_stop。LIFT 有 101 条已完成视觉样本和 101 条控制样本。总计 4 条本地协议响应、1 条云协议响应，实际模型加载及联网为零。回放 `result.json` 的 SHA256 为 `c8832051cdb55bc975185fa2c91185197b3dc842082df9f96db50b04131c7832`。单条拒绝消息能说明触发了 TTL，根因需由下一轮 Astra 根据当时的时序证据确定。

两项故障在代码层闭合。此轮独立复核不授予剩余 3 个真实试次的解冻许可。此前真实 fixed-02 的组件和物理成功归属修前源码，原始审查 SHA256 仍为 `46940b0e6965c1b0014b14404dd58de939583d5283699404dfd18413da37aa4f`。正式研究仍为 NOT_ACCEPTED，新增合格组 0。
