# 首动作 PNG 策略跨接口离线读回

固定源、原 242 帧及 `run-02/pair-1-A`、`pair-1-B` 完成跨接口读回。recorder 与 observation 两端同用 6 档时 242/242 一致，同用 1 档时也是 242/242。两个混合方向以及同物理步不同 acquisition 被实际反馈和 PRE 输入消费者拒绝。 [Astra 后续决策](next-development.md) [机器读回](cross-interface-readback.json)

## 帧与消费接口

全部 242 帧均经过原 reader 的 `_restore_frame` 重建和实际 `observation_from_sensor_frame` 编码。核验了 acquisition ID、观测 ID、原时间、相机标定、物理状态、RGB 像素、深度、有效 mask、实例和 pass 来源。6 档与原归档 payload 和 blob 哈希一致。1 档保留相同解码内容，242 个 PNG 对应的 observation checksum 均改变。每档输出有按原 acquisition 顺序计算的身份摘要。 [逐帧读取工具](cross-interface-readback.py) [身份摘要](cross-interface-readback.json)

其中 219 帧为注册逐物理步，21 帧为隐式缓存。这 240 帧只走归档解码与 observation 编码，无显式会话反馈。其余 2 帧为第 120 物理步的显式 acquisition-123 和 acquisition-124，分别对应 compiler bootstrap 和 dispatch reference。受控 CPU adapter 把各自已冻结的 SensorFrame、实例及 pass 元数据放回借用后端的接口。实际 `MuJoCoCaptureSession.capture_with_instances` 与 `VisualRawRecorderV3.capture` 执行返回路径，并在会话编码返回前调用真实 `NativeFullHorizonRecorder._record_frame`。两帧各覆盖 6/6、1/1、6/1、1/6。 [实际入口与离线 adapter](cross-interface-readback.py)

6/6 的两份反馈与原文件逐字节一致，通过真实 `_v2_feedback`。按原时刻用历史 tracker 重算 grounding 及 PRE，恢复了原 inputs 和候选步骤绑定。1/1 的两份反馈使用 1 档原件哈希和 checksum，在同一消费者中通过。历史 tracker 重算得到相同目标和目标区几何，并生成新的 1 档 grounding、PRE 输入和准备绑定。候选绑定保留原动作参数，绑定新的 checksum，执行权限为 false。原动作的准入记录到 PRE，随后控制器推进 99 步触发截止，未取得控制器返回或 POST。本离线回放只核原记录时刻，实时 owner、lease 和 freshness 留待新开发实例。 [反馈、PRE 与候选绑定哈希](cross-interface-readback.json)

6/1、1/6 在两个显式 acquisition 的真实 `_v2_feedback` 中各失败一次，错误为 `registered v2 source association differs`。将两档已重建的 PRE preview 分别与另一档 observation 混配，真实 `RegisteredGroundingFrameInputsV2.from_preview` 报 `current registered preview unavailable or relabelled`。在同一档内以 acquisition-123 替换同为第 120 步的 acquisition-124，两个消费者也分别拒绝。 [负控原错误](cross-interface-readback.json)

## 下一次真实开发的前置条件

真实开发发行需要冻结统一的 PNG 策略，并把该策略传到 RawV3 边界回调与 MuJoCo 会话返回两处实际编码点，现有路径默认 6。新发行还需要记录首动作互斥耗时，按同线程和 operation、guard、acquisition ID 对齐。准备、在途帧和清退单列，动作内按子区间并集核算渲染、detach、编码、写入、SQLite、owner、控制与物理。两次独立进程读回输出逐字节一致，SHA256 为 `5b6115988ac929683360e7d674343a20bb810c3a681ce00f68e82f194c704266`。EGL、模型和新试次均为 0，正式教师资格为 0/9。 [下一阶段计划依据](next-development.md)
