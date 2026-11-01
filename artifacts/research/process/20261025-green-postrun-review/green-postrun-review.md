# R365 `copy_green_01` 独立事后审阅

- 审阅者：外部审阅 agent（DSH 会话，经用户授权）
- 时间：2026-10-25T19:57+08:00
- 对象：`R365:copy_green_01`，round `round365-p6-t3-post-diagnostic-next-action-20261024`
- 性质：**独立事后审阅记录，不是 ROOT 接受**。未更新任何账本、未运行任何项目代码、未修改任何冻结件。
- 开发状态：用户已暂停；本文件不释放执行。

## 1. 结论

**建议接受（限定范围）**：`copy_green_01` 是一次合格的 GREEN——真实 child exit 0、唯一命名断言（exact-dict 冗余 ABC 分类计数）由 4 降为 0、语义前缀断言全部完成、观察器已恢复、JUnit 1 test / 0 failure / 0 error / 0 skip、transport 真实返回 0 且无 timeout/signal、源文件运行前后字节一致、资源槽按计划标 `NOT_APPLICABLE_BY_PLAN` 且未伪造 sidecar。

**接受范围仅限**：`_copy` 的一行候选在有限微测试样本上保持严格复制语义，并消除了精确内置 dict 的冗余 `Mapping` ABC 判定。**不包含**任何性能结论、原 UTC 节点结论、codec 回归结论或 T3 结论。

## 2. 与冻结记录的字节一致性

| 对象 | 期望（`pause-state.json` / plan） | 实测 | 结果 |
| --- | --- | --- | --- |
| product `src/.../local_temporal.py` | `1695aded…`, 121,321 B | `1695aded…`, 121,321 B | 一致 |
| test `tests/test_local_temporal_copy_dispatch.py` | `51cf4261…`, 8,161 B | `51cf4261…`, 8,161 B | 一致 |
| runner `implementation/run-validation.py` | `a6ae068c…`, 107,862 B | `a6ae068c…`, 107,862 B | 一致 |
| `green-source-gate.json` | `9f68ed52…`（由 completion 声明） | 200,709 B，与 completion 一致 | 一致 |
| `result.json` | `6ce69432…`, 492,768 B | 一致 | 一致 |
| `completion.json` | `3e22b634…`, 5,022 B | 一致 | 一致 |

`source-before.json` 与 `source-after.json` 为同一 SHA256 `e45869cc…`，即运行期间源快照未被改写；`source-after-observed.json` 为带观测元数据的另一份捕获，SHA 不同属预期。

## 3. RED → GREEN 对照

| 证据 | RED `copy_red_01` | GREEN `copy_green_01` |
| --- | --- | --- |
| 产品 SHA / 字节 | `5675220d…` / 121,298 | `1695aded…` / 121,321 |
| child exit | 1（仅命名计数断言） | **0** |
| 命名 AssertionError | `R365_RED_REDUNDANT_EXACT_DICT_MAPPING_CLASSIFICATIONS` | 无 |
| `semantic_assertions_completed` | true | **true** |
| `exact_dict_classifications` | 4 | **0** |
| `classification_count_all_phases` | — | 34（子类/自定义 Mapping/虚拟 list 仍走原判定） |
| `observer_restored` | true | **true** |
| JUnit | 1 test / 1 failure | 1 test / 0 failure / 0 error / 0 skip |
| transport | exit 0，无 timeout/error | exit 0，`timed_out=false`，`signal=null` |
| 资源槽 | 纯函数，NA | `NOT_APPLICABLE_BY_PLAN`，`fabricated_sidecars=false` |

RED 由 ROOT 于 `root-copy-red-acceptance.json`（`b0e439a5…`）接受，`all_pass=true`；本次不重跑、不改写该接受。

## 4. 事后核对项

| # | 检查 | 依据 | 结果 |
| --- | --- | --- | --- |
| 1 | transport 真实 exit 0 | `author-original-transport-return.json`: `returncode=0`, `timed_out=false`, `signal=null`, `elapsed=0.884 s` | PASS |
| 2 | transport 身份与计划一致 | `launcher_argv` 指向 `implementation/run-validation.py copy_green_01`；`cwd`、`env`、`reservation_id=62341119…` 与账本一致 | PASS |
| 3 | 槽位仅消耗一次 | 账本 `copy_green_01`: `used=1`, `remaining=0`, `retry=false` | PASS |
| 4 | 无并发竞争者 | 运行前后 `live_candidate_process_scan.competing_pids=[]` | PASS |
| 5 | completion 引用完整 | 7 个 stage receipt 全部 pin，`finalization_complete=true`, `final_summary_state=COMPLETE` | PASS |
| 6 | 终端记录合格 | `validation_pass=true`, `test_observed_pass=true`, `expected_red_observed=false`, `behavior_acceptance_credit=0` | PASS |
| 7 | 源快照精确 | `source-before` 与 `source-after` 同 SHA `e45869cc…` | PASS |
| 8 | 产品仍为冻结字节 | 运行后产品 SHA `1695aded…`，与 case 记录一致 | PASS |
| 9 | 阶段状态完整 | `raw-process-ledger`/`source-after-observed`/`persistent-inventory`/`junit`/`cases` = COMPLETE；`resources`/`prerequisite-observation` = `NOT_APPLICABLE_BY_PLAN` | PASS |
| 10 | 流保留 | stdout 315 B（`1 passed in 0.13s`），stderr 0 B | PASS |
| 11 | missingness 全部 present | `missingness.json` 各 pin 存在且可核 | PASS |
| 12 | 提交前时序合理 | `capture_elapsed_seconds_before_commit=0.223`，早于 19:24:12 的 transport 结束 | PASS |
| 13 | JUnit 单一绿色 | `junit.json`: tests=1, failures=0, errors=0, skips=0 | PASS |
| 14 | case 真实 | `copy-dispatch-case.json`: `semantic_assertions_completed=true`、`exact_dict_classifications=0`、`observer_restored=true` | PASS |
| 15 | 语义前缀先于断言 | `test_exit_exception=null`，`custom_items_effects` 保留 13 条子类/自定义 items 调用 | PASS |
| 16 | 纯 NA 未伪填 | `resources.json`: `actual_resource_counts=NOT_APPLICABLE_BY_PLAN` | PASS |

未通过项：无。

## 5. 明确不能从本次得到的东西

1. **不能证明性能**：JUnit `time=0.002 s`，是纯函数微测试；无任何计时对比可支持"更快"。
2. **不能解释 600 秒**：见第 6 节算术。
3. **不能替代原 UTC 节点**：`utc_memory_01` 仍未运行，槽位 HELD 0/1。
4. **不能替代 codec 回归**：`codec_regression_01` 仍未运行。
5. **不构成 T3 或研究验收**：`behavior_acceptance_credit=0`，`formal_accepted=false`。

## 6. 关于"这行改动是否是 600 秒解法"的数量级判断（供后续增量参考）

R363 最后完整 checkpoint 记录 `_copy` 329,744 次调用，发生在约 61 秒处。Python 3.12 中 `isinstance(x, Mapping)` 命中 ABC 缓存约 60–120 ns；取 100 ns：

- 已观测调用量：329,744 × 100 ns ≈ **33 ms**
- 线性外推到 600 秒（≈320 万次）：≈ **0.32 s**
- 再悲观 10 倍（1 µs/次）：≈ 3.2 s，占 600 秒的 0.5%

结论：该改动**在数量级上不可能是 600 秒非完成的原因或解法**。它是正确的冗余消除，但 UTC 槽位是否值得直接投给它，应在运行前单独判断；本节不改变任何计划约束。

## 7. 建议的账本变更（未执行）

`root-command-ledger.json` 的 `commands.copy_green_01` 目前为：

```text
ROOT_accepted=false
acceptance_state="PENDING_INDEPENDENT_POSTRUN_REVIEW_USER_PAUSE"
accepted_result=<absent>
ROOT_disposition=<absent>
```

建议由 ROOT 在 CAS 下补充（字段与取值见同目录 `proposed-ledger-mutation.json`）：

- `ROOT_accepted = true`
- `accepted_result = {result: <pin>, completion: <pin>}`
- `ROOT_disposition = <指向本审阅记录>`
- `acceptance_state = "ROOT_ACCEPTED_INDEPENDENT_POSTRUN"`
- 其余字段不变；`codec_regression_01` / `utc_memory_01` 保持 HELD，不因本次接受而自动释放。

## 8. 只读复核命令（可重放）

```bash
cd "/home/ningyd/文档/ChatGPT/BIGsmall"
sha256sum src/cloud_edge_robot_arm/vision/local_temporal.py \
          tests/test_local_temporal_copy_dispatch.py \
          artifacts/research/process/20261004-ced-development/astra-rounds/round365-p6-t3-post-diagnostic-next-action-20261024/implementation/run-validation.py
```

本次审阅只读取了上述文件与 `result.json` / `completion.json` / `cases.json` / `junit.json` / `junit.xml` / `stage-status.json` / `resources.json` / `missingness.json` / `author-original-transport-return.json` / `raw-process-ledger.json` / `root-command-ledger.json`，未 import 项目、未运行 pytest 或 runner、未打开数据库、未写入任何既有文件。
