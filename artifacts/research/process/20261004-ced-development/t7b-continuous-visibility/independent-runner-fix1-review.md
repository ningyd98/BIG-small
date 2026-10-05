# 逐步采集 runner / verifier 修复后独立复核

2026-10-05。最终限定结论：**SCOPED PASS，原三个 P2 全部关闭**。作者明确确认 source quiet 后进行独立只读审核。没有执行真实 runner、动作、MuJoCo renderer、模型或硬件；没有改动实现。原 REQUEST_FIX review 和既有 module review 均未修改。

独立执行脚本内 **10 CPU 用例，PASS，0.44 秒**（`independent-runner-fix1-tests.log`）。没有重复原 17 个模块用例。另用小型 fake-camera 合成轨迹重放原四个反例和新增绑定检查：

| 变体 | 独立结果 |
| --- | --- |
| 未改动的完整基准轨迹 | VERIFIED |
| journal saved 的 frame ID / checksum / file 改为 unrelated | 拒绝：完整 index END 不一致 |
| terminal episode 改为 unrelated | 拒绝：terminal episode/step/time 不一致 |
| terminal simulation time 改为 9.0 | 拒绝：terminal episode/step/time 不一致 |
| action `(0,2]` 内 step 1 的 BEGIN/END owner 清空 | 拒绝：完整 span 推导的归属不符 |
| outer acquisition episode 改为 unrelated | 拒绝：acquisition/raw physical identity 不符 |
| camera before/after physical step 同时改为 99 | 拒绝：camera measured step/time 不符 |
| 最终 PHYSICS payload 的 simulation time 改为 9.0 | 拒绝：PHYSICS source identity 不符 |
| 第二 action 与原 span 重叠 | 拒绝：所属不唯一 |
| 额外 camera capture BEGIN 越过 saved BEGIN 一纳秒 | 拒绝：camera/raw capture interval 不符 |

每个反例均返回 `INCOMPLETE_OR_INVALID`，同时保留原 3 个 allocated / verified RGB-D 帧，明确失败发生在关联而非丢失原始图像。新增校验将 saved 记录与 authoritative index END 做 canonical JSON 完整比较，包括 JSON 类型；将 acquisition、物理 snapshot、camera state、PHYSICS source、终点 episode/step/time 与时钟区间连接；并从所有原始 `(start_step,end_step]` 重建每步唯一 action 所属。没有缩短实际动作范围。

这次修复只改 verifier。原 runner 的单一 `attempt-1` guard、完整逐步 payload、同一相机、原控制器/零噪声、RNG/cache 保存检查和 journal fail-closed 路径保持原源字节。实际采集未开始；独立检查前后 `attempt-1` 均不存在。后续唯一实际采集由 root 执行，期间被冻结的源不得变化。

## 最终 exact source freeze

独立检查 manifest、live、archive-index 指向的归档：**32 输入，408,064 字节，全部一致**。和初始 32 输入相比，只有 `verify_offline.py` 的源 hash 改变；旧 `source-before` 的全部 32 个成员仍与初始 manifest 一致。31 个最终输入复用初始 archive，修正 verifier 指向 `fix-round-1/source-final/verify_offline.py`。header 与最终 manifest digest、source count、byte count 一致。HEAD 没有作为源冻结条件。

| 最终项目 | SHA-256 |
| --- | --- |
| unchanged runner | `addc33e7031bdeb55d03a476b9d4c1ad97a789c43251ac1be79ff53c5596537a` |
| corrected verifier | `19225d13e058cb428b8cf3a99095bde6b46bfd985bcb3290e4824fdd4b0b4e6f` |
| execution source manifest | `1b51ff53e4c40cf9943dcfcfe68e835ad95e0228315b51a3cf2285089c058aaf` |
| header | `51a1adb25759a3a9d46583cf84eb351de5bdcb72d083863bf709d15751bd387d` |
| final execution archive index | `b86086d653775eebf216c56de67deaa2df6e380f6d66a00fa2d2034ebfa2ace0` |
| new independent replay probe | `3347af9f66a2e5959de951dd4478a7f01b0958f09e9b166853111d6e23e49711` |
| new independent replay results | `95144129d7ea279a2a2f1c50e5793037c56d9dc2dc1f07ab4f9421d870ee0e8a` |

新证据：`independent-runner-fix1-probe.py`、`independent-runner-fix1-counterexamples.json`、`independent-runner-fix1-tests.log`。保留的原 review SHA 为 `2a6eee00eaf2ebfedfd5b70993baeaea6a4d43149ba930f7607da3baeffc07f2`，原 module review SHA 为 `a7ae2306bd4fd8c04c4ad0fb2d620f9b58e8489bb11f462f91c77214e8bc0847`；原 probe / counterexample hashes 也已独立确认未变。

所有基准及反例结果仍为 source authenticity UNKNOWN、native NOT_PROMOTED、continuous motion NOT_CERTIFIED、external UTC uncertainty / future stability / calibrated error bound UNAVAILABLE、formal accepted false。SCOPED PASS 仅关闭本次 CPU 关联缺陷，未产生实际采集证据、连续未来运动界或 native / INITIAL / METHOD 接受。
