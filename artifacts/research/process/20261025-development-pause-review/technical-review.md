# 暂停期独立技术审阅

审阅者：`/root/pause_technical_review`；2026-10-25。结论：当前一行优化是合理的有限候选，但完整 UTC-memory 仍未完成，600 秒未完成的根因仍未知。最小后续是完成已有验证链，而不是立即叠加 accessor/cache 重构。

本次仅读取源码、JSON、日志和标准库文件元数据；未导入项目、运行候选/测试/探针、打开数据库、修改源码或历史证据。本报告不是 Astra 修复计划，也不授权恢复运行。读取的 product/test/runner SHA256 与 `pause-state.json` 一致。以下源码路径均相对仓库根 `/home/ningyd/文档/ChatGPT/BIGsmall`；R350/R363/R365 分别指 `artifacts/research/process/20261004-ced-development/astra-rounds/` 下对应 `round350-p6-t3-successor-lineage-execution-20261024`、`round363-p6-t3-next-evidence-decision-20261024`、`round365-p6-t3-post-diagnostic-next-action-20261024`。

## 1. 按优先级排列的实际堵点

1. **完整原节点尚无成功行为证据。** R350 `implementation/t3_03/result.json` 是约 600 秒后 child −15，存在 `child/monitor bounded deadline` 的 `DeadlineExpired`；其 `timed_out:false` 不能抹去原始 deadline 错误。R363 `implementation/utc_no_sigusr2_01/result.json` 明确 child-wall 600 秒触发、child −15、600.018 秒（含 cleanup），leader 已 reap、group 已空。两次均缺完整 JUnit/case/资源证据；这证明非完成，不能证明具体业务断言失败。R365 的 `utc_memory_01` 尚未执行，不能说这行改动已让原节点变快或通过。
2. **根因定位证据不足，且诊断改变了成本。** R363 `diagnostic/observer-profile.jsonl` 最后完整 checkpoint（sequence 142）记录 `_copy` 329744 次、`_object` 2555 次、LocalEnvelope 52 call/51 return；sequence 149 在启动后约 61 秒报告 30 CPU 秒观察器预算耗尽，后续覆盖 UNKNOWN。递归 inclusive 时间不可相加当独占成本，调用总数也不是 exact-dict ABC 次数。末尾 OS sample 中主线程仍为 R，累计约 591.54 CPU 秒（SC_CLK_TCK=100），支持该诊断运行持续消耗 CPU；不能据此排除间歇等待，或把 CPU 成本全部归给 `_copy`。无再次 SIGSEGV 也不能证明 SIGUSR2 是旧崩溃原因。R365 `root-r363-diagnostic-disposition.json` 保持 root cause UNKNOWN 是正确的。
3. **当前验证链停在 GREEN 观测后。** `pause-state.json`、R365 `root-copy-green-paused-settlement.json` 表明用户暂停；RED 已独立接受，GREEN 已花费且观测通过，但 ROOT postrun acceptance 尚未完成。codec/UTC 两槽仍 HELD，输出目录不存在。这是当前运行前置缺口，不是新的产品故障；无需重做 RED/GREEN 来“补进度”。
4. **即使节点成功，测试覆盖和后续研究门槛仍独立存在。** 完整节点包含两个偏移场景及 late-return，最多三次 poll；原两项 T3 接受属于旧源码世代，不能拼成当前九节点完成，更不能替代 B/C/P7/P8/D 或真实研究验收。

## 2. 一行候选、RED/GREEN 究竟证明什么

`src/cloud_edge_robot_arm/vision/local_temporal.py:60` 从 `isinstance(value, Mapping)` 改为 `type(value) is dict or isinstance(value, Mapping)`。在模块正常导入的 `collections.abc.Mapping` 契约下，精确内置 dict 必然为 Mapping；改动只短路这一次分类，原 `items()`、严格字符串键、重复键拒绝、递归复制不变。dict 子类/自定义 Mapping 仍走原判定和自定义 `items()`；list 分支仍在 Mapping 后，保留虚拟 Mapping 优先级。它不引入共享副本或可信绕过，范围合理。

`tests/test_local_temporal_copy_dispatch.py:15` 的同一测试先检查数字边界、有限值、严格键、别名分离及双向修改、Mapping/子类的 items 顺序和异常，再检查一个四 dict 小树的分类计数。已核对两槽 `result.json`、`completion.json`、`cases.json` 及 `author-original-transport-return.json`：

| 证据 | RED | GREEN |
|---|---|---|
| child exit | 1，仅命名计数断言 | 0 |
| 已完成语义断言 | true | true |
| 小树 exact-dict 分类数 | 4 | 0 |
| observer restored | true | true |
| JUnit | 1 test / 1 failure | 1 test / 0 failure |
| transport | exit 0，无 timeout/error | exit 0，无 timeout/error |
| cleanup | reaped、group empty | reaped、group empty |

RED 是为“减少冗余分类”制定的工作量契约，旧实现原先的语义断言也通过；它不是原 UTC 失败的最小重现。GREEN 支持有限样本语义保持及删除分类，不能证明性能提升幅度、完整 codec 语义、原 UTC 完成、资源正确或 T3 接受。两个 JUnit 时间均约 0.002 秒，不宜作性能比较。资源 `NOT_APPLICABLE_BY_PLAN` 仅适用于这些纯函数槽位，不能挪给 UTC。

## 3. 已证实的源码工作量与未证实的因果

**已证实：访问路径反复复制/解析。** `local_temporal.py:1925` 的 `to_payload()` 执行 `json.loads` 后又 `_object` 全树复制；`:1932` 的 `semantic` 再复制 payload；`:1952` 的标量 accessor 也经过整份 semantic；`:1958` 的 object accessor 再复制目标子树。`:1988` 的 `_from_local_payload` 先 `_object`，`:1999` 又调用 `LocalEnvelope.from_payload`，后者 `:1874` 再复制并 canonicalize；校验 tag 又经 `to_payload`。这是确定的重复遍历，而“各路径合计占原 600 秒多少”“删哪一层足够”均未证实。

**已证实：legacy 缓存不能代替 local 路径分析。** 实际装饰器在 `repositories/event_autonomy/protocol.py:199`，并不存在 brief 假设的同名独立文件；它优先调用 `vision/worker_runtime.py:149` 的 `_local_read_record`。`protocol.py:106` 从 `_local_tasks`/local 表读取并 `json.loads`，再交 `VisualSupervisionRecord.from_payload` 等 decoder。`memory.py:158` 的 `_visual_supervision_verified_bytes` 属于 legacy `_visual_supervision_locked`，不能据此否认 local 的解码/验证成本。另一方面，`local_temporal.py:1865` 确实已有 128 项/8 MiB、限定 Context/外层生命周期的 decode memo；命中前仍需 copy/canonical，且它不是跨独立读取的 parsed cache。因此“完全无缓存”和“已有缓存所以无需重验”都过度。

**候选而非已批准修复：** 单次解析/减少内部重复复制比扩大缓存更易限定，但必须另有 Astra 范围和严格输入、脱别名、上下文所有权证据。共享可变 parsed structure、放宽外部校验、跳过历史验证不能从本次计数推出。当前不应为这些候选扩大 R365。

## 4. UTC 测试覆盖与另一个独立源码边界

`tests/test_operational_runtime_closure.py:5574` 把多个模块的 datetime 一起替换；`:5640` 在每次新 `_b_t2_exercise` 前设置 ±1 天，而不是在同一已建立任务中前后改变 UTC。`:5599` 的外部检查重写 captured_at 为相对 shifted-now 的边界值，并检查一个明确过期 decision；它支持外部 UTC 边界仍受检查，不能单独证明“同一外部对象随时钟跳变而改变判定”。`:5254` 对 route 检查 disposition/transaction/schema 等，没有断言业务 route 必须为某个成功值。

所以 DeepSeek 提醒证据边界有价值，但仅凭 `visual_verification` 和 `conditions` 一起 patch，不能断言本地路由存在 UTC bug。当前源码 `visual_verification.py:744` 的 local `online()` 注入 operational reference，`conditions.py:134` 在该 reference 有效时跳过 UTC age 分支。`:1189` 仍传 UTC 给 phase evaluator，其中 native 阶段刻意保留外部校验；“看到 datetime.now 就说明 local freshness 错误”也不成立。恢复后若要宣称运行中跳变独立性，需要在另行批准的覆盖工作中区分这些场景，不能现在改原节点。

源码另有**确定的条件性 UTC 依赖**：`vision/owner_registration.py:1114` 的 longer-duration 分支，对 local original 也检查 `observation.captured_at <= check.checked_at <= now`（`:1125`）。若 local 的完整要求包含该分支不受 UTC 跳变影响，它是待单独验证的缺口；当前测试和 `vision/execution.py:961` 均未传 `required_duration_s`/`duration_check`，因此不是已证实的当前超时根因。本次未发现可由静态阅读证实、能直接解释当前 600 秒非完成的额外产品缺陷。

## 5. 明确恢复后的最小可区分下一步

1. 保持暂停直到用户明确恢复。先只对已有 GREEN 做 ROOT 独立 postrun 核对/接受，不重跑已 SPENT 槽位；复核当前字节和计划适用性。当前产品 SHA256 为 `1695aded2b2e1e5c21d677bd4d445184537aabc84310cf14474ace91b1ca15d3`，不是旧 baseline `5675220d…`。
2. 按 R365 原顺序，用相应精确源码 gate 和逐次 reservation 完成 `codec_regression_01`，再运行原完整 `utc_memory_01`。运行前必须补齐各槽 gate/接受/reservation，确认解释器链、依赖/seed pins、无竞争写入/运行、独占输出、至少 3 GiB 空间；这里没有执行这些动态前置检查。codec 的三原文件共静态展开 26 节点已记录于 `implementation/source-proof.json`，仍须实际运行。
3. 最小判别是：当前一行源码能否在原 600 秒和原资源侧车下完整完成 UTC-memory。完整通过才支持“此候选满足此节点边界”，仍不证明根因；未完成/新异常则保留原始材料，停止相关修复/重跑，交实际 Astra 下一轮选择能够区分剩余成本的有限方案。不要加时、删断言或默认再加观察器。

## 6. 应纠正或保持限定的表述

- DeepSeek 文本中“R365 未实施、test/runner/ledgers/gates 不存在”已过时；HEAD 适用性已有 `astra-post-commit-applicability-20261025.json`（`APPLICABLE_AT_EXACT_NEW_HEAD_WITH_FRESH_GATES`）和 ROOT 接续记录。`source-proof.json` 的 `product_patch_applied:false` 是准备时快照，不是当前状态。
- “每次全量重放 6–8 次”“缓存已解决 local 重放”都缺该实际路径的充分证据；应分别陈述已知复制路径与尚未量化的验证成本。
- “GREEN 已验收”“600 秒根因已修复”“无 SIGSEGV 证明信号因果”“资源为零”均不成立。现有暂停记录和 R363 disposition 的 UNKNOWN/未接受表述是正确的，应继续保留。

审阅操作备注：一次只读元数据命令因系统无 `python` 名称退出 127，随后改用系统 `python3` 读取 JSON；没有安装或修复环境，也没有运行项目代码。较长工具输出发生显示截断的部分已按选定字段重新读取；结论来自磁盘原文件，不把截断显示当完整证据。
