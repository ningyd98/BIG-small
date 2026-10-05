# 有界 capture-state 诊断独立审核

2026-10-05。初始结论：**REQUEST_FIX — 一项 qualified P2**。作者已确认源静止。独立静态审核与 fake-only CPU 检查，没有执行诊断、MuJoCo renderer、物理步、真实模型或硬件；没有修改作者源码、原 32 个执行源、旧 attempt 或既有审核报告。

**28 个 CPU 用例 PASS，0.15 秒**，日志 `independent-tests.log`。额外三个最小 journal 故障反例及正常对照保存在 `independent-probe.py` / `independent-counterexamples.json`；都仅使用 test_cpu 中的 fake backend / fake renderer。

## P2：capture journal 失败生命周期不一致

| qualified 反例 | started / completed / failed | 结果 |
| --- | --- | --- |
| 正常对照 | 1 / 1 / 0 | 正常，无异常 |
| CAPTURE_BEGIN journal OSError | 1 / 0 / 0 | 没有调用相机，但失败分母漏计 |
| CAPTURE_END journal OSError | 1 / 1 / 1 | 同一次采集同时计入完成和失败 |
| 原 camera ValueError 后 CAPTURE_FAILED journal OSError | 1 / 0 / 1 | 向外抛 journal OSError，原 camera 异常仅留在 context |

`CaptureProbe.capture` 的 BEGIN journal 位于 try 外，completed 在 END journal 成功前增加，finally 中 FAILED journal 又没有保护。这会使诊断的故障计数不一致，或者遮蔽被定位的原相机失败。最小修复是把 BEGIN 纳入失败边界，在 END 成功后计完成，并保留原异常，即使 FAILED journal 也无法写入。Allocated attempt 与真实 camera-call-start 可分开计数。不要改原 guard、旧 attempt 或原始证据。

作者和 root 已收到精确反例；该问题尚未在初始源关闭，因此暂不进入真实诊断。

## 其余限定审核

- 独立核对 **33 repository references / 440,906 字节**：manifest、live、archive-index 指向归档全部一致。继承的原 32 个源字节未变；新脚本是第 33 个引用，test_cpu 单独由 header hash 绑定。MuJoCo 3.3.7、NumPy 2.5.3 及 header 中的 **19 个 MuJoCo dependency 文件**均符合冻结检查。没有把版本号或依赖 pins 作为 native authenticity 证明。
- 原 scene/config/seed、same component/group、640 camera、zero noise 和原控制器保持。`passive_horizon` 只委托一次现有 `backend.step(steps=10)`，包含 step zero 的 callback，因此最多 11 次 live extra capture；没有 teacher/motion command。现有目录 guard 阻止重复、覆盖或恢复。
- Terminal copy 只尝试一次。检查全部公开 NumPy array inventory、shape/dtype/C-order bytes、每个 clone array 对每个 live array 无 shared memory、time 及 live state。门槛拒绝时记录拒绝、clone-call 0、retry false；没有 fallback 或 backfill。通过后至多一次 copy capture，并检查各阶段 original live state。CPU alias/bytes/shape/dtype/time/inventory 反例均拒绝。
- 逐成员 snapshot 真正 detach，记录原始 bytes、shape/dtype、hash 及 view topology。阶段包括重复 BEFORE control、update_scene、RGB/depth render 和 AFTER；wrapper 恰好委托原 bound method 一次并恢复。NaN bits、noncontiguous bytes、alias topology、storage budget、原 renderer error 保留路径均有 CPU 覆盖。额外 padded structured-array byte probe未发现字节损失。
- 新诊断记录 array differences 为 unresolved，并保留 `original_whole_step_guard_would_accept=False`；不回写或放宽旧 guard，不把 diagnostic capture completed 当作稳定性。Protected physics/model/controller/RNG/cache 的变化仍中止。保存上限为 32 MiB snapshot members / 256 MiB combined compressed snapshot-render storage，超过预算不丢字段来继续。
- Decoder 0、formal accepted false、native NOT_PROMOTED、continuous NOT_CERTIFIED、future stability UNAVAILABLE；该诊断不重跑旧动作试验，也不增加独立 calibration-group credit。

旧 attempt 的全部现有文件 hashes 已在探针前后核对未变；原始 11 / 10 / 1 失败分母保留。`diagnostic-1` 仍不存在。初始 P2 反例是软件故障注入，不是一次额外物理试验。

## 初始静止源及证据

| 项目 | SHA-256 |
| --- | --- |
| diagnosis runner | `9db5dd340f4849ef6a513d3b3730e47209ad62bb4e90f02804c909e92ec779ee` |
| CPU tests | `ee651f6acf7cf341a19486f5bbd2b4c6c70d9da703e30b083ecb0a408598b362` |
| header | `96a9556b738111a16ac6adcde8d7ae4c56eabf7d8068b8189e9c53d60bc135a3` |
| source manifest | `475dd1c55ffdc3a01f997f48984c876e75bfcca6543a3331b36f05b9da2e639a` |
| archive index | `cc4d824c595099b89e2f3f0eef466340d405c2ccc42206e50af374757ab67004` |
| independent probe | `ecd8251b8ea21b65c277573b5f2dbd6523f79e5900fc88cf889fc78860e5d01d` |
| qualified counterexamples | `7b0c778ea538377bb21b86f60f2ebb70b70c493f953187827f5e8a47a1ebb499` |

保留本 REQUEST_FIX、初始 logs/反例和源 hashes，等待作者最小修复、重新冻结以及 bounded 独立复核。没有请求新的实际执行。
