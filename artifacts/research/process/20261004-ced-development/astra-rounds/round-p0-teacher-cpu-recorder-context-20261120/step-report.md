# 冻结 recorder 的原帧离线上下文

第一次 CPU 执行 run-01 在 warmup 第一帧退出 1。该次计时文件为 0 行。冻结 RawV3 读取 `operation.parameters`，辅助适配器未将已重建的原拍摄参数传入。首次 stderr SHA256 为 `9214e944f799e9077a4df8bc6c6423578698e229bfcc2f3e852641c357035d84`，原目录和启动登记保留。

## 字段来源与调用

| 原件来源 | 适配字段与消费位置 |
| --- | --- |
| 原 `source-frame.json` 的 camera_state_payload 与独立物理状态 | 按原 `_on_boundary` 传给 `operation.parameters`；RawV3 还原相机并计算 joined physical hash |
| 原 acquisition_id、interval_id、真实 operation_id、物理步、role | 先交叉校验，提供给 RawV3 的来源字段及 Native recorder 的原 capture role |
| 原输入角色与 record_seq | RawV3 建立原 SOURCE/ONLINE 标识与相同序号 |
| depth、mask、实例文件、原元数据 presence、pass hashes | 传给原 writer，保留隐式帧的空实例值和实际键存在性 |
| 原库存写出合同 | 隔离输出拥有新 inventory、bytes_written、frame buffers 与 publication 状态，调用原 `_write_blob` |

原 `joins` 只有 acquisition-124 的 `BEFORE_SUBMIT`，它是在动作提交时登记。采集本身没有 `DURING_ACTION` 或 `AFTER_RETURN` 连接。离线 recorder 的最小上下文因此保留 action=None 和空 last_returned_span，不构造 worker、owner、guard 或模拟输入。

## 验证

原 12 项软件控制继续通过。六个新定向 RED 留存，修后合计 18 项通过，Ruff 通过。三类真实原件的最早代表为隐式缓存 acquisition-1、逐步采集 acquisition-2、边界采集 acquisition-123。每个代表调用同一冻结 recorder 各级别一次，共六份不计时正控。A级的五件文件与原件逐字节一致。B级的像素、深度、mask、实例、拍摄身份与状态等值，按新编码重算并核对摘要。

RED JUnit SHA256 为 `37159811ea650c8fb8e044878c27a65c1241f2f89531b5f2538e6f84430c911c`，GREEN JUnit SHA256 为 `996c9cbef377f4067f77b346b084d33567bce1ba2ef8b6060e798979e28d22b5`。六份原帧适配与独立读回的私有清单 SHA256 为 `c1f49fea170650675b23625a352457e4204ce46bb1193069b00d5ef3b77e0389`。正控目录是 `experiments/results/phase9/p0-teacher-action-window-benchmark-20261120/recorder-context-qualification/`。CPU 配对数据在全新 run-02，按父轮独立验收。
