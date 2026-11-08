# R464 Reader wire serialization order Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: ROOT 使用 `superpowers:executing-plans` 按项实施；本 Astra agent 只规划。R465 独立类型比较根因已发现，ROOT 选择先规划 R465；以下五阶段保留为条件规格，在任一 R464 stage 启动前可由下一轮实际 Astra 冻结联合最终验证。本轮验证状态保持 **NOT_RUN**，不据此宣称 P0 通过。

**Goal:** 修复独立 reader 两处 expected body 的序列化插入顺序，使完整 nominal 原件复算保持生产 wire 的字节/hash 契约。

**Architecture:** 仅调整原 reader 的两个字典字面量；仍从冻结 settings 和独立编译的 messages 重建完整 body，不使用录制 body 作为 expected。沿用 R413 supervisor，并规划新的 R464 五阶段 runner/spec；旧 RED、failed GREEN、runner/spec/results 永久保留。

**Tech Stack:** 现有 Python reader、pytest/ruff/mypy、R413 bounded_stage；本次调查仅标准库 JSON/文件/哈希，无产品 import、测试或真实资源调用。

**Spec:** `AGENTS.md`；R461 `plan.md`/`plan.json`；R464 `intake/failure.json` 和原始 R461 reader-green；用户既有研发继续授权。实际规划模型 **gpt-6-astra**。当前 HEAD `fdbf481d3c843c1583d97970f8229b479363c334`，分支 `research/20261004-continuation`。

## 原始失败与静态证实

R461 原31项输入预检匹配；唯一 RED 为六项预期失败，保留其 assessment。R461 一次 import fix/format 后唯一 GREEN 在3.50s得到 **4 failed, 2 passed**，child rc1，supervisor FINISHED、reaped=True、source_drift=[]、remaining_live=[]、errors=[]。四个完整 nominal 路径均在 `verify_role_probe_evidence` 最后的 `can_accept_role_probe` 拒绝；B0 PLANNER/SUPERVISOR 两节点通过。adjacent-green、ruff、format --check、mypy 尚未启动。本轮复用该四失败作为 RED 证据，不重跑 RED 或旧 GREEN，不把旧失败改称通过。

原始日志位于 R461 `validation/reader-green/{stdout.log,stderr.log,junit.xml,pytest-events.jsonl,result.json}`，已按原字节冻结到本轮 intake。初始15项 intake 的 live及frozen SHA256全匹配。完整规划输入清单是 `intake/planning-input-pins.json`，共102项，逐项含 path、bytes、SHA256、copy；其包含必要旧输入、当前两源码和保留的四组临时原件。`intake/tmp-originals` 只冻结此次静态诊断所需 report/attempt/request 子集，不冒充完整远端复现包。

已证实链条：

1. `vision/planner.py:471` 生产 body 顺序为 `model, messages, generation..., response_format`。
2. 当前 reader 的 nominal `expected_body`（约266行）和 `_b0_expected_request_body` 尾部（约638行）先解包 `_recorded_chat_fields(settings)`，最后放 `messages`，故其顺序为 `model, generation..., response_format, messages`。
3. 字典内容比较忽略插入顺序，因此最初 `body != expected_body` 不报错。`scripts/probe_rgbd_roles.py:142` 则对默认 `json.dumps(dict(body)).encode()` 计算 `wire_sha256`，保留了插入顺序。最终 gate 约340行严格比较实际及预期 summary，所以拒绝。
4. 用标准库读取保留的 `/tmp/bigsmall-r461-reader-green` 四份 report、16份 request.raw；全部16份具有相同证据：当前构造内容相等、长度相等，但重序后的 hash 与原 raw 不同；建议顺序的序列化字节全部等于原 raw。逐条结果、输入和哈希见 `intake/static-order-diagnosis.json`。Sol示例原hash `789136fa4075425a7d4eae728663e813ec2ce651a4c69bef6193048a76e7ca64`，当前expected为 `5eb0b9c7f3cc20e2f4f64514484e87109baa5fc04be4fa41a058bd4c1a133bc6`。此诊断为隔离顶层顺序，读取录制 messages；它不是产品验证，也不授权产品 expected 复制录制 body。

B0两项已通过是因为 B0 当前只比较字典内容；本轮同步其构造顺序是相同根因的两处实现一致性，不能虚构成B0已发生的失败。尚未执行完整正向 fixture 后半段，修复此处不保证没有后续新问题。

## Global Constraints

- 产品只改 `src/cloud_edge_robot_arm/research/freeze_evidence.py` 的上述两个构造器；测试 `tests/test_sol_evidence_reader.py` 全字节保持 SHA256 `413fed83aab5691b245463bf932c1688271c12bc8f8fc5b210bb76e3a067f67f`。
- 修复前 reader SHA256 必须为 `ffe83bbc5192e75a82414238b6f9b7fd9203a734cba261119639972661c12ddf`。必要输入不匹配先停止相关实施，不能悄悄更新 pins。
- 不修改 summary、raw字节、hash算法、长度/成本连接、acceptance、settings参数、离线身份、旧fixtures、R461/R458 runner/spec/results。不得 sort_keys、忽略 wire_sha256 或把 expected summary 替换成 actual。
- CPU-only，实际API/physics/render/services/hardware dispatch全部 **0**；无监听端口、无真实HTTP、无引擎。保留可见标记、顶视相机、OpenCV及既定控制器，边缘模型选型后置。
- 原R461 import fix/format额度已用完；本轮两处字面量能保持当前格式，**不需要且不授权额外formatter写操作或import fix**。只保留一次新的 format --check；若失败另轮Astra。
- 任一计划外失败、范围扩大、新根因，停止相关修复并另轮实际Astra；原件不覆盖、不裁剪，不自动重跑。

## Review Focus

- 原16份raw的序列化顺序和hash一致性：六节点中完整nominal正例覆盖，静态诊断仅解释原因。
- 两种官方route、Sol非默认合法generation、Qwen think/省略：沿原六节点完整执行，不改测试语义。
- raw/response/frame/成本破坏的拒绝行为：完整正向断言之后仍须走到；此前未到达不等于已覆盖。
- B0 typed SUPERVISOR编译及相邻历史证据：原B0两节点与三文件adjacent继续核验，不能复制录制messages替代编译。
- **独立新根因**：合法冻结Sol预算1与wire `True`/`1.0`在Python字典比较中相等。现B0及CED只比较字典，helper只验证冻结settings类型。源码和标准库语义已确认比较缺口，但未运行产品失败；证据见 `intake/deferred-type-comparison.json`。这需要比较逻辑和测试语义变化，超出本轮两构造器范围，转 **R465实际Astra**。整体P0及真实阶段在其解决前不得收口。

## Task 1：两个构造器的最小顺序修复

**Files:** 修改 reader 两处字典字面量；读取现有新tests；创建本轮 implementation/报告，不改历史轮次。

**Interfaces:** 保持 `_recorded_chat_fields(settings)`、`verify_role_probe_evidence(...)`、`_b0_expected_request_body(...)` 签名和返回结构；仍使用原独立 `compatible_messages(messages)`。

- [ ] **Step 1 — 复核前置。** 重读本计划与R461范围，校核102项输入及冻结副本。保存本轮 applicability/preflight；确认R461六RED、四失败GREEN原件及临时目录仍在，新R464 validation目录/basetemp未使用。R463的先 `rg` 后读取规则继续适用；先前 `tests/conftest.py` 不存在的sed rc2属于相同只读命令发现问题，没有产品修复。本规划agent也曾猜错R461目录名，已用rg定位纠正，未据其运行产品。
- [ ] **Step 2 — 仅调整两处字面量。** 在两处均依次写显式 `"model": settings["model"]`、原 `"messages": compatible_messages(messages)`、最后 `**_recorded_chat_fields(settings)`。Python更新已存在model键不改变其首次插入位置；generation及response_format由原helper提供。这个顺序准确保持生产构造，不改变任何值、类型或比较逻辑。
- [ ] **Step 3 — 静态范围复核并冻结最终源码。** 对比intake原件，只允许这两处插入顺序变化；test必须全字节不变，无其它reader语义差异。保存 exclusive `implementation/source-ready.json`，记录最终reader/test bytes+SHA256、全运行输入pins、plan/spec/runner hash及scope review；不能在阶段之间重新采样并默认接受源码变化。

## Task 2：新的条件验证规格和runner

**Files:** 创建 `implementation/run_stage.py`，从冻结R461 runner派生；已规划 `spec-templates/{reader-green,adjacent-green,ruff,format,mypy}.json`。原R413 supervisor及事件/prerequisite插件只读。

- [ ] **Step 4 — runner准备。** 新runner精确校验本plan.json SHA256及五模板。只声明下表五项，删除新阶段链中的reader-red入口/例外；旧R461 RED/GREEN只作为冻结原始证据，不能要求旧failed GREEN rc0，也不能改其状态。每次新的stage及basetemp目录必须未存在；每阶段用全新runner进程，串行且仅一次。全部环境/cache/database/tmp/resource输出均换成本轮路径，保留显式白名单环境。
- [ ] **Step 5 — 资源和原始退出证据。** 保留R413 `module.run`及原收尾逻辑。每child前后以标准库 `resource.getrusage(RUSAGE_CHILDREN)`记录，前值证明runner没有先前child，后 `ru_maxrss * 1024`（Linux KiB）核对≤4GiB。这是已等待child的最大RSS口径，不宣称并发进程树合计峰值；原20s采样保留且不冒称精确峰值。child回收后统计本stage目录加本stage独立basetemp的regular-file逻辑字节和、文件计数与清单，去重，不跟随越界symlink；总≤2GiB，预算报告自身计入或保守预留≤64KiB，保留测量时刻及磁盘可用前置。写新 `resource-budget.json`，不改supervisor result。缺失/歧义/超预算均停止后续。这里是退出后的证据核对，不冒称未修改的R413已连续硬性限制RSS/磁盘。
- [ ] **Step 6 — 仅在未被R465替代时按序验证。** 执行 `.venv/bin/python <本轮>/implementation/run_stage.py <stage>`。每次启动前校验source-ready及所有runtime pins，退出后必须 `returncode=0,state=FINISHED,reaped=True,source_drift=[],remaining_live=[],errors=[],cancellations=[]`，资源报告也通过，才允许下一项。六节点GREEN额外核验collection恰为声明六项、六个call全部passed、无collection/setup/teardown错误。此前阶段只要失败，不再执行后续。

| stage | 冻结检查 | child / outer上限 |
|---|---|---|
| reader-green | 原六个精确节点，完整nominal/B0/generation/route/Qwen，顺序见plan.json；新`/tmp/bigsmall-r464-reader-green` | 180s / 210s |
| adjacent-green | `tests/test_ced_initial_freeze.py`、`tests/test_rgbd_role_models.py`、`tests/test_openai_sol_visual_migration.py`；新`/tmp/bigsmall-r464-adjacent-green` | 180s / 210s |
| ruff | `.venv/bin/ruff check src/cloud_edge_robot_arm/research/freeze_evidence.py tests/test_sol_evidence_reader.py` | 120s / 150s |
| format | `.venv/bin/ruff format --check` 上述两文件 | 120s / 150s |
| mypy | `.venv/bin/mypy --follow-imports=silent src/cloud_edge_robot_arm/research/freeze_evidence.py` | 120s / 150s |

每项精确argv、env、nodes、输出路径以plan.json.verification_specs及一致模板为准；不运行全仓测试。无新RED额度，不覆盖旧 `/tmp/bigsmall-r461-reader-green`。实际资源额度仍为0。

**已决定的后续安排：** 为避免已知类型比较缺口下重复消耗全套检查，ROOT先让实际Astra制定R465。在任一R464 stage启动前，R465可显式引用本计划和两个顺序修复，重新冻结联合最终源码及针对类型缺口的RED、最终GREEN/adjacent/static新规格。届时本轮五项均记 `NOT_RUN_SUPERSEDED_BEFORE_LAUNCH`，保留模板，不执行或改写它们；R465承担最终验证。新阶段预算不能在两轮重复使用。R465写成前不得先补测、先改类型比较后补计划。

## Task 3：证据与验收边界

- [ ] **Step 7 — 保存step-report并汇入阶段总结。** 保留原始失败、静态16份诊断、实施diff及输入复核、每项实际状态。若被R465接管，明确本轮NOT_RUN，不能把规格、静态hash一致或派生报告当成测试通过。完整正向路径后半段的新失败仍须下一实际Astra计划。
- [ ] **Step 8 — 按验证完成的实际交付范围提交推送。** 遵循既有明确路径交付，核对本地、上游、远端commit SHA；不提交完整bulk raw、运行DB、凭据、权重或SDK。若本轮未验证，产品最终交付归R465验证后的明确范围，不能用本计划成功写出代替软件验收。

R464局部验收仅在其五个新阶段实际通过、资源证据满足口径、两处scope正确且测试/原门槛不变时成立；当前为 **NOT_RUN**。即使局部通过，R465比较缺口未解决也不能整体P0收口。fresh role、full实际仍NOT_RUN，native UNKNOWN，正式研究NOT_ACCEPTED。P1/P2/P3沿R461条件路线图，本轮不释放实际额度。

自查：单一序列化根因有16份原件字节证据；仅两处literal修复；没有摘要/hash宽松化；102项输入和原始失败冻结；五阶段均新路径串行一次且可在启动前正式转交R465；已知独立类型根因公开保留；没有编造测试通过或真实资格。本规划调用pytest/产品import/API/physics/render/services均0，未改产品、测试或runner。
