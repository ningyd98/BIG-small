# R196 Local promotion / original / task binding Implementation Plan

> **For agentic workers:** Use the established sole-author workflow; implementation follows superpowers:executing-plans under ROOT gates. No additional author or review seat is authorized.

**Goal:** 修复 T1 detached history 的本地 promotion UTC getter、语义 original 关联及 route task 关联三处缺口。
**Architecture:** 仅修改现有 shared codec 三个区域，保留本地与 legacy 明确分支。新增独立测试文件，先真实 RED，再修复；全部旧证据、原51节点及原测试正文不改。
**Tech Stack:** Python/.venv、现有真实 codec/CPU fixture、pytest；元数据仅标准库。
**Spec:** 本轮 plan.json 的完整机器合同；R192/review/review.json 三项正式结论；既有 R158 T1 及 R192 已冻结合同。

实际规划者 `/root/astra_status_plan`，`gpt-6-astra`。本计划冻结后必须 ROOT 适用性/输入/角色/完整脚本门控，当前没有实施授权。

## 原始证据与判定

- R198 正式报告与原三项 issues、continuation ledger 完全一致，17/17 审查已耗尽；报告是根据既存记录新编，不是恢复不存在原稿。
- C1：完整 local promotion replay 可达刻意拒绝的 UTC getter。修复 local 分支，绝不制造 UTC、改变 getter 或跳过 compiler/source/camera/requirements/预算检查；legacy 原比较保持。
- C2：现有 `_join_audit_original` 缺完整 local_time 等于 enclosing original 的语义关联。只在明确 semantic edge 上收紧，保留任意描述参数里独立 original 的既有合法正例。
- C3：route before/after pool 只彼此同 task，缺与实际 input original 及 produced publication 的 task 关联。补该关联，保留所有原 CAS、hash、预算非退款及类型分派。
- 三项均是有源码依据、尚无新增运行反例的缺陷。原 R192 51PASS/204 Memory closure 对 f015 候选有效，不表示这三项已覆盖或 T1 完成。
- R200 可选 stored 展示错误已由 ROOT 接受放弃；零重放/替代源码读取，不将其算成功。

## Global Constraints

- 唯一产品作者 `/root/p6_stage_b_sol`（actual gpt-6.1-sol）；ROOT 只写自己的元数据/gates/settler。
- 唯一现有产品文件：/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/local_temporal.py；起始111212 B / f01520073140a08b0e15b947a00c840f486d45bd7dcc434bf44a894b6aae591c。
- 仅 `_bootstrap_promotion_source`、`_join_audit_original`、`_semantic` 的既有 route 分支；签名、15tag/outer/payload/history字段、UTC veto不变。
- 新测试：/home/ningyd/文档/ChatGPT/BIGsmall/tests/test_local_temporal_promotion_bindings.py。原两测试全文、七 T1 正文、A80556、R175 cleanup、其他24原owned源、211protected、真实16taggolden保持。
- 旧所有槽不重置；原 R17938失败、旧13及 R19251成功分别保留。无A40、Git、native/model/network/SQLprobe或T2/T3。
- 256个实际输入完整路径/bytes/SHA见 plan.json；211protected本次逐项匹配。历史/当前固定/受控mutable角色严格分开，STATE仅 planning.R196事实、PHASE仅追加，完整before归档及并发比较。

## Review Focus

1. 真正完整 local promotion 链必须能解码；不能仅让孤立 promotion record 通过。
2. Legacy promotion 与 UTC约束必须保留；本地数据不能伪装 UTC权威。
3. 语义 original 必须完整一致；描述性嵌套仍允许独立 original。
4. 内部一致但外部task不同的预算/产物必须拒绝；合法local/legacy混合仍通过。
5. 原compiler/source/camera/requirements、真实资源finally关闭和旧51回归不得因新分支变弱。

## Task 1 — 新测试及脚本准备，再取得真实 RED

- [ ] ROOT复核完整输入/原件，建立本轮六槽全0/1HELD，归档before。
- [ ] 同一Sol创建12节点新测试和 prepare-evidence.py/run-command.py；ROOT创建独立 root-settlement.py。所有完整源、argv/env、slot和fixture先全文门控。
- [ ] 所有新节点各调用一次冻结的真实 `_r179_fixture`；禁止新无记录的repo/issuer分配。负例必须先解码完整baseline与内部合法child，再实施单一目标mutation。
- [ ] prepare_red 120s once；ROOT接受后 RED8 600s once。精确节点/命令见JSON，不使用collector。
- [ ] RED预期8节点：local完整promotion在明确UTCgetter失败1；C2/C3六例DID NOT RAISE；legacy完整promotion阳性1PASS；合计7FAIL1PASS、0error/skip。不同原因/fixture失败立即STOP，不能篡改预期。

| 新测试 | 参数节点 | RED |
|---|---:|---|
| test_r196_full_promotion_history | local, legacy（2） | 两者纳入 |
| test_r196_semantic_original_join_rejects | route_input, supervision_definition, supervision_transition（3） | 全部 |
| test_r196_route_task_join_rejects | local_pair, legacy_pair, produced_publication（3） | 全部 |
| test_r196_route_task_join_positive | local, legacy（2） | 仅GREEN |
| test_r196_promotion_source_rejects | compiler_policy, original_time（2） | 仅GREEN |

完整promotion必须含 definition→initial→capture reserve/complete→plan reserve/complete→PROMOTE，真实源/编译策略/提案/历史事件全关联，不可只设置terminal字段。新12测试在RED前冻结；修复时不改断言。

## Task 2 — 仅三处修复

- [ ] ROOT先接受真实合法RED，才放行产品。
- [ ] C1用真实已解码local类型/tag分支；完整local original/provenance及archived contract保持。Legacy保留 timestamp/issued_at/valid_until 对原UTC accessor比较。本地不调用这些getter，其他source/编译/预算检查逐项不动。
- [ ] C2在现有join中对local prior.local_time.to_payload()与enclosing original做整个对象精确比较；legacy分支保持；不扩成generic recursive parent强制绑定。
- [ ] C3从真实input original解码得到task，before/after与produced identity/budgets都绑定它；可复用现有 `_audit_publication` 的实际prior完整source检查。不能额外强求跨revision预算全文相等。
- [ ] ROOT完整diff/source gate后运行 prepare_green 120s once。用唯一锚定区域/完整outside bytes证明scope，无AST，原测试/脚本不变。

## Task 3 — 新候选验证与同席续审

- [ ] 窄Ruff120s once，仅 F821,F822,F823 检查shared与新测试；不宣称全scope mypy零错。
- [ ] GREEN63 600s once，精确原51+新12在同一新候选，63 unique PASS/0FAIL/ERROR/SKIP。不是重置旧13/38/51槽。
- [ ] 所有原始stdout/stderr/JUnit/result/tool-return与真实资源sidecar先保存，再判期望；实际分母逐对象，不硬编码4每节点或252。
- [ ] ROOT自己的 consolidated settlement 120s once：全pins/历史档/六slot/合法RED/63结果/资源closure/proof齐全才记录软件证据。
- [ ] 同一原reviewer `/root/t1_fresh_astra_review` 新增有限6批、每批≤600行；旧17已用不变，累计上限23，不开新席。覆盖diff/新fixture/RED/GREEN/资源/历史证据；不够则明确不完整并STOP。

## 六个独立新槽与验收

prepare_red120 → RED8 600 →（ROOT合法RED门、三处修复）→ prepare_green120 → Ruff120 → GREEN63 600 → ROOTsettlement120。共六个可执行槽，各once/no retry；脚本源准备和普通元数据全文门控不暗藏产品执行。命令精确argv、finite env、输出路径和每节点断言以 plan.json为准。

新root/author脚本必须在首次运行前全文固定；报告历史input脚本/gate仅对精确物理before档核验，不能blanket跳过。当前gate的hash放reservation ledger，不能自引用。

ROOT仅在全部新证据及同席审查通过后另作 bounded T1决定。现在 T1/T12/native/formal/Git均未获验收，T2/T3与原R158剩12保持HELD。任何新根因/意外失败/超范围均STOP，交实际Astra下一轮。
