# 真实帧残余开销先导

从新封存试次抽 36 帧，覆盖 3 个动作边界、11 个执行阶段逐步帧、11 个 hold 逐步帧、11 个隐式缓存帧。核对 108 个 RGB、depth、mask 附件的 inventory 字节数及 SHA256、原 Base64 字符串摘要和完整重建 observation payload 摘要。四组 AB、BA、BA、AB 的纯计算配对完成，Ruff 通过。 [样本与原计时](residual-pilot.json) [复现代码](residual-pilot.py)

- `RGBDObservation.validate_pair` 已先解码三种附件并验证内容，`_spool_frame` 又各自解码、写原件，再重新编码进行 canonical 校验。先导 B 在记录器内只对与当帧已知 canonical 原文本完全相同的值采用同帧原字节，保留文件和字符串的分别哈希。B 的全部匹配预算节省 0.968 ms/帧，四组范围 0.865–1.520 ms/帧。仅有解码结果时无法证明原拼写 canonical。未来候选须在实际 encoder 上绑定原始 canonical 文本和字节，保留原验证和 fallback。四例验证等值、非 canonical pad bits、坏字符和等长但不同内容，比较有序写入及异常。先导未计副带对象的建立、生命周期或峰值 RSS。
- `_write_blob` 每文件都经 `application.policy` 重新 JSON 解析 77,235 字节的配方，再取 `raw_bytes`。单测 36 帧每帧 5 次查限额，预取同一不可变字节对应标量的计算预算节省 0.959 ms/帧，四组范围 0.951–0.993 ms/帧。若实施须保留每次已写字节加当前长度的比较、注册字节来源绑定、缺失或换入原配方的行为和同步写入顺序。没有测量省略任何磁盘读取、写入、验证或预算检查。
- 将两组中位按新窗口同密度 3,261 帧外推，全部命中且零引入成本约 6.28 秒。两项仍需在同配方的生产路径里验证。新实际 PRE→POST 已测 128.739 秒，距原 8 秒门槛 120.739 秒。源采集、真实控制、RawV3 PNG/深度编码本体、守卫、完整 canonical payload 摘要和证据写出均不纳入上述节省。优先另评估标量预取，比穿过 observation 和 spool 的副带对象改动更窄。当前先导量级不足以关闭 8 秒差距。 [新试次独立回执](../round-p0-teacher-active-checks-20261121/retest-measurement.json)

无产品修改、EGL、模型或新试次。原件只读。脚本 SHA256 为 `34143e20c3dcef50e8570c618ea0a6b02c198bc8d255cf71b781a364c4ca0111`，原始结果 SHA256 为 `25f4aea12dec6f61d433c96d5090fe32eb1f61ebd210ec6208a2daeb069ac63b`。
