# 唯一实际 attempt 的失败审查

2026-10-05。结论：**FAILED / INCOMPLETE HORIZON**。本审查只读取 root 已结束的 `attempt-1`，运行被冻结的离线 verifier，并做隔离的只读 CPU 原始前缀重放。没有运行 renderer、物理步、真实动作、模型或硬件；没有重试旧 attempt，没有修改原始证据、32 个执行源、header、manifest 或之前的 PASS / module review。

## 实际失败和分母

- Episode `d96b64b19efc4b908ce329f202f2da8b` 停于真实 step 10，simulation time `0.04166666700000001`；只完成原 settling **10/120**。`evaluation_start_step=None`、outcome None、teacher actions / commands 均为 0。完整动作 horizon 根本没有开始。
- Whole-step allocated / attempted / capture-started 均为 **11**；steps 0–9 的 **10 帧保存成功**，step 10 的 **1 次采集失败**。Index 为 11 BEGIN、10 END、1 FAILED；nominal journal 有相同 acquisition 分母。另有 setup 1、bootstrap 1、teacher-boundary 0 次采集，不能混入逐步帧的成功计数。
- 冻结 verifier 命令为 `verify_offline.py --attempt .../attempt-1`，未请求 decoder；**exit 1**。结果为 `INCOMPLETE_OR_INVALID`，11 allocated、10 verified、1 failed-or-missing。原 payload gzip / JSON / member hashes 和 lengths 已读取验证；保存前缀最大 simulation gap `0.004166666700000002`，原控制仍为 0.005。
- 77 个 nominal event 的 sequence、monotonic bracket / 顺序及 UTC 读数顺序有效。失败采集的 camera begin/end 被保留，并位于 ACQUISITION_BEGIN / FAILED 的 nominal 区间内。最后 PHYSICS source、terminal 与失败状态中的 step/time/episode 一致。UTC uncertainty 仍为 UNAVAILABLE，不将这些读数作为外部校准时钟。

## Guard 触发项：只定位到 aggregate data hash

唯一变化的已记录组件是 `data_arrays_sha256`：

| 项目 | SHA-256 |
| --- | --- |
| before | `7343675517cde1552a64951346ac9a3a95c97dcfdef1d16f0f709a638d4d7547` |
| after | `d78506f5efab121f638580ce35c9cf75636d711b9ea88bd6e0d42f95a25ff2a4` |

Model arrays / options、controller、RNG、sensor cache / camera identity、step/time、command count 和零噪声设置都没有变化。两次 RGB / depth pass 的选择性 physics hashes 均为 `dcfef59fc6f8c844b3414b3482b95c2272cf887e2ac3326fccb0044ba7397e79`。这些 pass hashes 只覆盖 camera 源中的 time/qpos/qvel/act/ctrl；不能代替全部 data array 检查。

现有 aggregate digest 没有记录变化的成员名或值，因此**无法确定具体数组或根因，也不能认定 guard 假阳性或放宽它**。已向作者和 root 发送精确 before/after 项；后续定位应使用有源依据的逐成员证据，不能通过重跑旧 attempt 补写本次证据。

## 新的 actual-source P2：ACTUATOR step 语义

冻结 verifier 还错误地报告成功前缀的 step 1 CONTROL/PHYSICS mismatch 和 step 2–9 clock mismatch。这与 guard 失败是两个问题。

真实 backend `_build_actuator_observation`（`backend.py:723`）明确写入 `physics_step=self._total_physics_steps+1`，即 **upcoming step n**。CONTROL boundary / PHYSICS BEGIN 的 step 是 n−1，ACTUATOR / PHYSICS END 的 step 是 n。冻结 reader 使用 `actuators.get(step-1)`；其合成 fixture 也误用 preceding step。

真实 step 1 证据为 CONTROL operation 2、ACTUATOR source step 1/control 2、PHYSICS operation 3，按正确顺序记录：

| 事件 | nominal monotonic ns |
| --- | --- |
| CONTROL END before | 312615856252708 |
| ACTUATOR before | 312615856427177 |
| PHYSICS BEGIN before | 312615856565817 |
| PHYSICS END before | 312615857056716 |
| ACQUISITION BEGIN before | 312615857554044 |

Step 2 同样为 ACTUATOR 2/control 4、PHYSICS 5。独立原始重放确认全部十个已执行步均符合 upcoming-step 语义和 nominal clock 顺序。

已保存 `fix-round-2/independent-actuator-replay.py` / `.json`：从原 frozen reader 源构造**仅在内存中**将 `actuators.get(step-1)` 改为 `actuators.get(step)` 的诊断 reader；旧 reader 产生 9 条错误 prefix join 报错，新 reader为 0。源 AST 只替换这一处；两个 reader 都读取隔离目录中指向同一原始数据的只读链接，输出写入临时目录。

这构成 qualified 旧 reader 错误 → 修正 reader 正确的 CPU 反例。**两份报告的整个 attempt 仍为 INCOMPLETE_OR_INVALID、11 allocated / 10 verified / 1 failed。** 修正前缀 join 不能补齐 step 10 帧、110 个尚未执行的 settling 步或任何 teacher action，也不能提升权限。后续正式 reader / fixture 修复应单独冻结，不修改旧执行的 32 pins 或旧 actual raw。Task 2 native calibration agent 已获知 upcoming-step 源语义。

## 保持的冻结与证据

独立检查 **32 源 / 408,064 字节**全部 live / 最终归档 hash 一致。原冻结为：

| 项目 | SHA-256 |
| --- | --- |
| runner | `addc33e7031bdeb55d03a476b9d4c1ad97a789c43251ac1be79ff53c5596537a` |
| verifier | `19225d13e058cb428b8cf3a99095bde6b46bfd985bcb3290e4824fdd4b0b4e6f` |
| execution manifest | `1b51ff53e4c40cf9943dcfcfe68e835ad95e0228315b51a3cf2285089c058aaf` |
| header | `51a1adb25759a3a9d46583cf84eb351de5bdcb72d083863bf709d15751bd387d` |
| preserved runner fix1 PASS review | `d8aab41c9e95a24f488ffc53a97db1e6c307f114732f9db9a5bce51bf34dd307` |
| preserved module review | `a7ae2306bd4fd8c04c4ad0fb2d620f9b58e8489bb11f462f91c77214e8bc0847` |

新增审查证据为 `independent-actual-failure-probe.py`、`independent-actual-failure-audit.json`、`independent-actual-failure-verifier.log` 及上述 fix-round-2 CPU replay。原 journal SHA-256 `6d5e2101d487054f7eacb11cc83f5b158fe54e85db791cbc0b4c9e95487c0e95`；terminal SHA-256 `5010f3bdf4b7cd142845728059758604ab4de834f665e0377f2fdcf618462f35`。隔离重放后，全部实际文件 hashes 再次检查未变。

本次实际结果保持 source authenticity UNKNOWN、native NOT_PROMOTED、continuous motion NOT_CERTIFIED、external UTC uncertainty / future stability / calibrated error bound UNAVAILABLE、formal accepted false。失败保留与正确源语义检查均不等于完整 horizon、native calibration、INITIAL 或 METHOD 接受。
