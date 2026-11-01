# 当前状态入口（2026-10-25 20:45 +08:00）

本文件是**当前状态入口**，用于替代过期快照作为阅读起点。它不覆盖、不替换任何冻结原件。

- 作者：外部 agent（用户授权），非 ROOT
- R365 已收口；`utc_memory_01` 未运行
- 机器：`ningyd@192.168.3.221`，仓库 `/home/ningyd/文档/ChatGPT/BIGsmall`

## 1. 代码身份

| 项 | 值 |
| --- | --- |
| HEAD | `dd9df375e1d372490145327bcbfee5804352fcc4`（未变，未提交） |
| 分支 | `research/20261004-continuation`，与 origin 0/0 |
| 产品 | `src/cloud_edge_robot_arm/vision/local_temporal.py`，`1695aded…`，121,321 B |
| 新测试 | `tests/test_local_temporal_copy_dispatch.py`，`51cf4261…`，8,161 B |
| runner | `R365/implementation/run-validation.py`，`a6ae068c…`，107,862 B |

产品改动仍只有一行：

```diff
-    if isinstance(value, Mapping):
+    if type(value) is dict or isinstance(value, Mapping):
```

## 2. 槽位状态（R365 终态）

| 槽位 | 状态 | ROOT 已接受 | 说明 |
| --- | --- | --- | --- |
| `copy_red_01` | SPENT 1/0 | 是 | 真实 RED，4 次精确 dict 分类 |
| `copy_green_01` | SPENT 1/0 | 是 | 真实 GREEN，0 次分类 |
| `codec_regression_01` | SPENT 1/0 | 是 | **26/26 通过**，child exit 0 |
| `utc_memory_01` | HELD 0/1 | — | **未运行**，额度保留 |

ledger `9b96d3a6…`。接受记录：`root-copy-red-acceptance.json`、`root-copy-green-acceptance.json`、
`root-copy-codec-acceptance.json`。收口说明：`r365-closure-20261025.md`。

## 3. 已证 / 未证

**已证**

- 一行候选保持严格复制语义（微测试全部断言 + 分类计数 4→0）。
- 该改动不破坏既有 codec 语义：3 个文件、26 个节点全部通过。
- 四次启动中前三次均为预检拒绝，子进程未启动；证据全部保留。

**未证**

- 历史 600 秒非完成的根因：**UNKNOWN**。
- 该改动对实际耗时的任何改善：无计时证据，且量级上界约 0.32 秒。
- 完整九节点 T3、B9/full B、C、P7/P8、D。

## 4. 过期快照（不要修改，勿据此判断现状）

| 文件 | 过期表述 | 现状 |
| --- | --- | --- |
| `R365/phase-step-report.md` | 产品未改、四槽 HELD | 已验证三轮，产品已改 |
| `R365/source-proof.json` | `product_patch_applied=false` | 准备阶段快照 |
| `20261025-green-postrun-review/green-postrun-review.json` | `not_a_ROOT_acceptance`、`applied:false` | 接受已落账，见 `root-copy-green-acceptance.json` |
| `20261025-green-postrun-review/proposed-ledger-mutation.json` | `CONFIRMED_APPLICABLE_NOT_APPLIED` | 已应用，见账本 |

## 5. 下一步：R366

1. py-spy 对 UTC 子进程采样 60 秒，判定 600 秒落点；
2. 落点在 accessor 重解析 → 产品修复（Astra 定范围）；
   落点在 fixture/SQLite/lifecycle → 拆分为单 backend 主用例 + slow 标记；
3. 门禁收敛：只绑直接输入，停止递归继承历史材料；
4. 之后再回 T3 → B9/full B → C → P7/P8 → D。

注意：提交会改变 HEAD，使现有 649 项门禁失效，因此本轮改动保持未提交，
与 R366 的门禁重建一并处理。

## 6. 2026-10-25 22:42 更正：诊断测的是 startup 节点，不是 UTC

原 §6 的结论已作废，见 `../20261025-utc-cost-diagnosis/corrigendum-20261025.md`：

- 四组计时（572.65 / 607.00 / 452.75 / 322.19 s）跑的是
  `test_private_startup_to_transaction_grounding`（每 backend 1 个 exercise），
  **不是** UTC 节点 `test_local_new_schema_ignores_utc_jump_but_external_does_not`（每 backend 3 个 exercise）；
- fast-sha 探针跳过了 `_text()`，与候选补丁不等价；两个探针均为 FAILED（侧车写入问题）；
- 因此 **21% 提速与 24.5% 余量未在候选补丁或原 UTC 上得到验证**。

按 startup 的单价粗略外推，UTC 双 backend 约在 1,300–1,700 s 量级（未实测），
R367 的 600 秒预算很可能不足。

## 7. 2026-10-25 22:06 更新：R366 已立项（待 Astra 出计划）

立项包：`../20261025-r366-sha-fastpath/`（`intake.md`、`intake.json`、`astra-request.md`、`r366-candidate.patch`）。

- 变更：`_sha` 正则化，3 行 + 1 常量，语义等价；
- 实测：572.65 s → 452.75 s（-20.9%）；
- 治理：R365 的 `utc_memory_01` 在改动后失效，需 R366 自建预算或显式作废；
- 状态：**尚未应用补丁**，等实际 Astra 计划。

## 8. 2026-10-25 22:44 独立复核 R367 计划（只读）

| 项 | 结果 |
| --- | --- |
| `plan.json` 的 44 项输入 | **44/44** bytes + SHA256 全部匹配，0 缺失 |
| 源码计数 | `src` 406 tracked + `tests` 287 tracked + 1 untracked = **694**（新增合同测试后 695），与计划一致 |
| UTC nodeid | 存在于 `tests/test_operational_runtime_closure.py:5629` |
| 产品 | `1695aded…`，未改 |
| R365 账本 | `9b96d3a6…`，未改 |

未应用补丁、未运行测试、未改账本、未推送。开发仍暂停。

## 9. 2026-10-25 23:05 R367 执行结果（已交回 Astra）

| 命令 | 结果 |
| --- | --- |
| `sha_contract_before_01` | 31/31 PASS，0.264 s |
| `sha_contract_after_01` | 31/31 PASS，0.264 s |
| `codec_regression_01` | 26/26 PASS，14.25 s |
| `utc_both_01` | **NONCOMPLETION**，child −15，600.016 s，无 JUnit/case |

关键事实：600 秒内只创建了 `persistent-basetemp/.../memory-1`，**第一个 exercise 都没跑完**；完整节点估计 2,400–3,600 s。

- 产品：`c8a5a5a4…`（121,341 B，`_copy` + `_sha`），未提交；
- 合同测试：`tests/test_local_temporal_sha_contract.py`，未提交；
- R367 账本 4 项全 SPENT，UTC 项不退款；
- R365 `utc_memory_01` 保持 HELD 0/1 并已写退役记录；
- 交回文档：`../20261004-ced-development/astra-rounds/round367-.../astra-handback-20261025.md`。

## 10. 2026-10-26 00:00 R368 sizing 结果（发现测试自身缺陷）

- `utc_memory_sizing_01`（memory 单节点，cap 3,600 s）：**未通过，但不是超时**。
- pytest 耗时 **1,113.62 s**，跑到第一个 exercise 结尾时抛出
  `ValidationError: SceneSummary.updated_at Field required`（`tests/test_operational_runtime_closure.py:5612`）。
- 产品模型 `cloud/planning/models.py:46` 自 2026-06-13 起就要求 `updated_at`；测试自 2026-10-24 起仍未传。
- **该 UTC 节点在当前产品上不可能通过**，与 600 秒预算和 `_sha` 改动均无关；此前的 600 秒超时掩盖了它。
- 成本外推：1 exercise ≈ 1,113 s → memory backend ≈ 3,300 s，双 backend ≈ 6,600 s（未实测，后两个 exercise 未执行）。
- 报告：`../20261004-ced-development/astra-rounds/round368-.../sizing-report-20261025.md`；
- 交回文档：`../20261004-ced-development/astra-rounds/round368-.../astra-handback-20261026.md`。
- 账本：R368 两项均 SPENT，sizing `validation_pass=false`。
