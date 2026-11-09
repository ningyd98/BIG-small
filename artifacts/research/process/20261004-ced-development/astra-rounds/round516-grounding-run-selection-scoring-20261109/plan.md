# R516 GroundingPI explicit offline run selection Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans；本轮实际Astra只规划。用户已授权最小离线选择接口修复，禁止任何额外模型调用。

**Goal:** 让离线scorer显式选择封存的run-02/protocol-r514，并保留原三个候选的默认行为和全部科学结果。

**Architecture:** 仅将既有scorer的输入/输出路径参数化，增加来源一致性和独占输出检查；评分计算、分母、阈值、helpers及schema完全不变。可靠性累计账本作为独立provenance，不混入screen样本评分。

**Tech Stack:** 原Python/NumPy/Pydantic离线scorer及已冻结R505原始输出；无GPU、模型或网络调用。

**Spec:** 本轮request.md/inputs.json、R514 protocol-r514.json与plan.json；planner_model=gpt-6-astra；2026-11-09。

## 问题与原始证据

score_candidate.py中score(candidate)硬编码读取candidate/run-01.json，在结果中硬编码protocol.json/run-01哈希，并独占写score-03.json。GroundingPI run-01是保留的失败证据（1load、1generation、0completed），不能代表R514恢复的真实screen。代码静态证明选择缺口；无需错误地评分run-01来重现。

原4项输入bytes/SHA全部匹配。规划时run-02.json尚不存在，正在运行的progress不是封存输入，禁止从78/100或任何中间进度生成最终评分；完成后再冻结run-02及全部raw manifest。旧Lens/Molmo/Rynn各有score-03.json作为本轮科学回归基准，已纳入输入SHA。原CPU contract保持100请求及SHA `6933b444f6888ccc817edef071bc419c8ca461f4ba30498f4126216969535fe7`。

## 限定范围与接口

允许最小修改R505 `implementation/score_candidate.py`，新增 `tests/test_score_selection_r516.py`，R516 evidence/steps-report及三候选独立回归输出；GroundingPI只新增 `score-r514.json`、`score-r514.stdout`、`score-r514.stderr` 和评分输入封存manifest。原score-03、run-01、run-02、protocol、CPU/raw均只读。不改score_native.py、任何其他helper、VisualDecision、科学评估代码块、分母、阈值或oracle数据。

确定接口：

`score(candidate, *, run_json=None, protocol_json=None, output_name='score-03.json')`

CLI新增 `--run-json PATH --protocol-json PATH --output-name NAME`。省略时仍读取该candidate/run-01.json和protocol.json，仍输出score-03.json且exclusive模式；原三个候选默认路径/科学结果保持。两输入参数必须同时提供或同时省略，不能隐式混配。显式路径必须解析为该candidate目录内存在的普通JSON文件，拒绝越界/其他candidate/指向活跃progress；output-name只接受安全basename `.json`，无路径分隔符/..，并限制不能覆盖任何输入或既有文件。

新函数可将选择/核验提取为 `resolve_score_inputs(candidate, run_json, protocol_json, output_name)`，仅返回明确路径与加载元数据；不改变Path/digest行为，不用monkeypatch或复制run-02冒充run-01。默认输入也执行所选run.protocol_sha256与所选protocol真实bytes SHA一致性检查；不通过就停止，不静默回退。

## Task 1：选择与来源门禁RED/GREEN

- [ ] 重核本计划输入及工作树适用性，保存修改前scorer与三候选score-03科学投影基准，原文件只读。run-02正在运行时可做合成选择接口测试，不能提前评分其进度。
- [ ] 先写预期RED测试：默认选择原run01/protocol；显式选择run02/protocol-r514；仅一个参数拒绝；run内protocol SHA不匹配拒绝；跨candidate/路径逃逸/活跃progress拒绝；输出名非法或已存在拒绝且旧bytes不变。合成fixture自带路径/字节，不patch Path或digest。
- [ ] 最小实现路径解析与独占输出。结果原 `run_sha256`/`protocol_sha256`改为真实所选路径哈希，新增provenance记录规范化输入路径、bytes/SHA、CPU合同路径/hash（有合同绑定时）、oracle路径/hash、scorer及helper hash、输出名；不能用文件名猜协议。
- [ ] 在进行oracle扫描前预检输出不存在，在真正写出时仍保留open('x')以处理竞争；stdout/stderr在调用层同样独占创建，不以普通重定向覆写已存在输出。
- [ ] 运行新选择测试GREEN；所有异常保存原证据，未计划的算法/数据根因交下一Astra，不在本轮顺带修正。

## Task 2：GroundingPI封存与完整合同核验

- [ ] 等run-02进程终止且最终run-02.json存在，核status==ALL_REQUESTS_COMPLETED、generation_calls_started=100、completed长度100、model_loads_started=1；未全部完成则记录NOT_READY，不将部分记录补零评分或写最终score-r514。
- [ ] 验证run-02.protocol_sha256==所选protocol-r514.json真实SHA；协议cpu_contract_sha256==实际cpu-contract-r511.json SHA且该合同status PASS、requests长度100。所选run/raw路径须为run-02，与原run-01完全分开。逐项核完成请求id/query/mode/stage/repeat与CPU100顺序一一对应，无缺失、重复或额外项；原始processor/prompt证据与合同features/rendered hash对应。此为输入一致性门禁，不重新预处理模型或改提示。
- [ ] 验证每completed行对应raw实际存在并沿用原scorer所有raw-response SHA、token长度与oracle hash校验；冻结最终run及raw清单bytes/SHA。评分结束再次核选定run/protocol/CPU未变化，发现变化不发布最终评分。
- [ ] 原run-01 SHA必须等于protocol-r514.prior_run_sha256，原load1/gen1/completed0；新run为load1/gen100/completed100。累计可靠性单独记录 `reliability={prior_loads:1,prior_generation:1,prior_completed:0,current_loads:1,current_generation:100,current_completed:100,cumulative_loads:2,cumulative_generation:101,cumulative_completed:100}`，同时核run-02已有累计字段一致。不得硬编码这些数值掩盖真实账本不符。
- [ ] screen字段仍来自选定run02：model_loads_started1、generation_calls_started100、completed_calls100；原生box/point重复调用保留原排除规则，12正例/4缺目标与各阶段分母不改。原失败1仅进入可靠性账本，不充当空预测、JSON失败或额外样本，不混入screen延迟或准确率。

## Task 3：旧科学结果回归与选定run离线评分

- [ ] 用新增接口分别对Lens/Molmo/Rynn省略--run-json/--protocol-json，仅指定新独占output-name（如score-r516-regression.json），重新读取既有raw离线评分。禁止覆写原score-03或重跑GPU。
- [ ] 对照原score-03，要求所有科学内容严格相同：native、json、latency、gpu、cap_reached_calls、rows全部深度相等；candidate/run_status、原run/protocol/oracle hash、load_s、模型load/generation/completed计数和acceptance/hardware_dispatch相同。仅允许scorer_sha256与新增provenance/输出路径不同；不能用宽泛删除数字字段或容差掩盖差异。helper哈希必须不变。
- [ ] 新测试增加：未封存run拒绝、99或101请求拒绝、顺序/请求字段不符拒绝、CPU SHA不符拒绝、原失败账本不符拒绝、reliability与screen分列且原失败不进入分母。测试只使用合成fixture或冻结结果，不调用模型。
- [ ] 所有回归和选择门禁PASS，且GroundingPI封存门禁PASS后执行：`<既有离线评分Python> <R505>/implementation/score_candidate.py 06-groundingpi --run-json <candidate>/run-02.json --protocol-json <candidate>/protocol-r514.json --output-name score-r514.json`。记录确切argv/runtime版本、输入manifest SHA及独占stdout/stderr。使用原评分runtime，不新装包。
- [ ] 验证最终score-r514的provenance选择run02而非run01，科学screen完成100，可靠性累计2load/101generation；重新核原run01、三个score03、protocol及raw未变。写步骤报告并汇入阶段总结。

## 前置、验收与停止边界

实现可与正在运行的GPU独立进行，但不得改runner、协议、输入、模型进程或任何其正在使用的文件。正式评分必须等待封存，无额外模型load/generate、无新GPU调用。新增评分选择接口不得被用于伪造已完成状态。

开发验收=选择接口测试PASS+原三候选全部科学数值/逐行结果严格回归一致；GroundingPI评分验收=封存100请求与CPU合同及raw完全对应、显式来源哈希正确、可靠性账本独立；正式研究/实机验收=NOT_PERFORMED。DEV16仍非heldout，深度因果使用与硬件执行边界不变。

任何新算法/解析器问题、数据缺失、hash不一致或范围扩大先下一实际Astra；本轮只修输入选择，不改变科学结论。已验证交付按明确artifact路径提交推送研发分支并核本地/上游/远端SHA；完整raw留存边界不变，provenance不是完整远端复现包。

## Review Focus

1. run02误配protocol.json：按run保存的protocol SHA核所选原字节。
2. 用progress部分结果评分：最终状态及CPU100逐项完整性门禁。
3. 覆写历史结果：输出安全basename及exclusive创建，旧hash回验。
4. 重构改变科学数值：三候选完整rows与聚合结果严格回归。
5. 将失败1次算入预测分母：reliability累计101与screen100分别呈现。

## 输入SHA清单

规划时run02尚未封存，不能预编其SHA；执行时必须新增最终manifest。

| Path | Bytes | SHA256 |
|---|---:|---|
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/implementation/score_candidate.py` | 11795 | `05b5414ad80804c308179fbc96ced67a9da4480634180cc442790b3ea7a40a49` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/06-groundingpi/run-01.json` | 17042 | `ffa025ffd76ec71e24b9b5f9d5f29456cef9465fed3751cc1f0bfe3c2d2f1c9a` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/06-groundingpi/protocol-r514.json` | 5509 | `f10b4f12c0b277ffa2c19794239a7d65ac58ed4c200001ab14e937ea8f572e8f` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round514-groundingpi-jit-headers-20261109/plan.json` | 58767 | `cc178edd58d1366bffce0d48b256ebaa803e1f8d20113333cbe9ca77996a3bf6` |
| `AGENTS.md` | 1774 | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round516-grounding-run-selection-scoring-20261109/inputs.json` | 1060 | `1a1f7913af24097bff93e2c19f83fefed15c1a60df96b718b87672ed9e72d68e` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round516-grounding-run-selection-scoring-20261109/request.md` | 818 | `f5c4fac525398d3f596a58fb6f8de0d0c6b00afcea47f6a1272acc3bbc7e80d7` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/implementation/score_native.py` | 5848 | `3db283b482d83b3caa87d24efa3b9d3151f10986442f62136d05b130e47202c5` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/implementation/run_groundingpi_r514.py` | 9280 | `cb90deffa30701361abd7afb43e327095b500c5c98808623b5dbcd81ed4cd6c2` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/06-groundingpi/cpu-contract-r511.json` | 204606 | `6933b444f6888ccc817edef071bc419c8ca461f4ba30498f4126216969535fe7` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/diagnostic/oracle-inputs.json` | 53101 | `3c00d41266bc1b8d6977395f1d870c7c65301252f0c37547225fda05193e330b` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/03-lens/score-03.json` | 72386 | `c8119ce4685a842612fa4b28b530030ae86d275ff3e4e94c01deb4ae7e747d64` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/03-lens/run-01.json` | 72000 | `fb9e8ed3cd5e1c78826891b733a5d48fd86ad4d95c95c84a38bc0447ac9f15d4` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/03-lens/protocol.json` | 4620 | `326eaf193a702904ca3aca843339cc2f2182f72ced11732c170a2a4808cb4a67` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/04-molmoer/score-03.json` | 28363 | `1bd76a48be5906609321a8c65dc38979a37291beca204ab220389c85672bcf5d` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/04-molmoer/run-01.json` | 41115 | `0f10414c605513b6fedc1bc7af37643f665208caaecff53c1c1e034a37bb2cb5` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/04-molmoer/protocol.json` | 4223 | `316d4764b090ac78975db00ab976dce37022494f229ce544cf959447a91867c4` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/05-rynn/score-03.json` | 133940 | `d758f02364ff2d23225ed399e430f5d0447d3d48d6a40d555dbf60d996a35545` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/05-rynn/run-01.json` | 141768 | `e629fb1dd24fc8d637678b610b29556bdd876c540bce963d4a6a5631e1f184ef` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/05-rynn/protocol.json` | 3553 | `9df3cb8bf1d9b61367ab37b18f5abdd030b24afd32af2c1be781153898d57351` |
