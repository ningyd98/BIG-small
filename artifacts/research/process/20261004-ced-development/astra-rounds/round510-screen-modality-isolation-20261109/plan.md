# R510 Native modality isolation Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans。用户已授权本轮最小修复，无需再次确认。实际规划模型 gpt-6-astra；尚未实施。

**Goal:** 修复离线 scorer 跨模态请求覆盖，按模态分别计算覆盖和延迟，输出独占的新 score-03，保留所有旧结果。

**Architecture:** 对每个 mode 从非重复 native rows 中只选择含该 mode 的行，再构造 (id,query) lookup。延迟也使用相同模态成员关系，重复请求单列；共用一次调用返回多模态时允许该观测在对应模态分列展示，但调用总数仍按原始唯一请求计数。

**Tech Stack:** 现有 Python 3 / NumPy / pytest；只改研究 scorer，不安装依赖。

**Spec:** R510 failure.json、R505 plan.md/json、R506 严格标量序列化计划、Rynn 冻结 protocol.json。

## 问题、原始证据与根因

failure.json 记录对真实 production lookup 表达式作 AST 复现：先box行、后point-only行具有相同(id,query)，预期box hit=true，实际box lookup={}。源SHA 9e640d35d6f3c4e52be3a32e258ab127da91ca1485618c8dbab4659045691d67 已核验匹配。根因是所有native行都加入每个mode的dict comprehension，后行get(mode,{})覆盖早先正确结果；其他mode同时会虚增本mode coverage。相同集合也将不同模态延迟混算。

Lens每个原生请求同时包含box/mask，Molmo只含point，因此旧两者定位指标不受此覆盖根因影响；实施仍须用真实离线结果回归，不能仅凭推断。Rynn冻结box/point分开请求、最多100生成、1次加载；GPU已由原计划启动。本轮不得改其提示、协议、调用预算或干预独立推理，只在完整原始记录封存后评分。

所有规划读取的输入 bytes/SHA记录于plan.json；Rynn进行中的run不冻结为完成证据，待结束后另存实际输入快照。CPU100请求合约通过为父任务报告，不替代GPU完成证明。

## 限定范围

唯一允许修改运行代码：R505 implementation/score_candidate.py。

允许：(1) mode lookup仅纳入 `mode in r['modes']` 的非重复native行，值取 `r['modes'][mode]`；(2) 将聚合native延迟替换为按模态的结构；(3) 独占输出文件名由score-02.json改为score-03.json。允许在该文件提取小型本地聚合函数以直接测试生产逻辑，但不重写无关代码。

新增R510 tests/test_modality_isolation.py、diagnostic/旧scorer精确副本/RED-GREEN/哈希与语义比较证据、step-report.md；允许为03-lens、04-molmoer、05-rynn独占新建score-03.json/stdout/stderr和退出码证据，更新R505阶段总结说明版本和结果。原score-01/02全部保留。

不改模型输出、数据、点/框/mask转换、阈值、分母12/4、筛选门槛、JSON评分、common helper、冻结protocol/schema或GPU runner。R506 `_json_scalar`白名单及两条输出allow_nan=False必须保持。不得重跑Lens/Molmo GPU，不能为Rynn补调用或换prompt。

## 精确聚合与延迟接口

每个mode的mode_rows按原始rows顺序，条件stage.startswith('NATIVE')、not repeat、mode in modes。lookup仅来自mode_rows；coverage=len(lookup)，expected_coverage=32继续固定，其他模态的缺失键不能计入本mode。INVALID/EMPTY的本mode行仍是覆盖观测，按原规则计无效；重复行始终不进入准确率/coverage。无有效mode数据时不得伪造32覆盖。

输出 `latency` 改为 `{'native_by_mode': {mode: ...}}`，不保留容易误用的混合native warm统计。每个mode内容：
- `first_request_s`：mode_rows首条延迟，无则null。
- `first_is_process_cold`：该首条是否就是全部非重复native中的首条；布尔，无行false。
- `cold_first_request_s`：仅上述条件为true时等于first_request_s，否则null。不能把后运行point阶段的首条称作新进程冷启动。
- `warm_excluding_first`：stats(mode_rows[1:]的end_to_end_s)，n/p50_s/p90_s均沿用现有stats精确定义；它明确排除本mode首条，即使该首条已经暖态。
- `fixed_repetitions`：stats(仅stage为NATIVE且repeat为true且含本mode的行)。保留实际n，完整已登记运行通常每mode2条，不把其他mode或JSON的repeat混入。

同一次Lens请求同时含box/mask，两组延迟值相同且first_is_process_cold均可为true，这是共享原始观测，不代表两次调用。rows、completed_calls、generation_calls_started、load_s、JSON分阶段latency、GPU资源与cap计数保持原有唯一调用语义，不把分模态n相加冒充调用数。

## 前置条件与 Review Focus

实施前重核输入SHA，保存当前scorer精确副本于R510 diagnostic/score_candidate.before.py。使用现有可运行pytest/scorer的解释器，记录路径，不升级依赖。修改后新scorer的SHA真实更新，冻结副本仍为旧SHA。

真实重评分前确认旧Lens/Molmo输入raw可读且hash一致；Rynn必须结束并封存run/protocol/raw，不能在持续写入时评分。保持既有scorer raw/schema断言，保存本次全部实际评分输入bytes/SHA快照。Rynn未完整完成不能标100/100或借本轮增加调用，按原计划记录终止或缺失。

新score-03.*必须不存在，全部独占创建。临时捕获旧/新结果时显式绑定module.HERE=R505、ROOT=项目根（继承R508教训），不改module.__file__；输出重定向临时文件，不触碰旧score-01/02。

重点测试：相同id/query跨mode覆盖、缺失mode虚增coverage、重复/JSON混入、共享多mode调用重复计数、后mode首条被误称冷启动。

## Task 1 — RED、最小修复和GREEN

- [ ] 新增行为回归测试，必须调用生产聚合逻辑或从生产AST精确提取聚合表达式，不只验证测试自行复制的公式。先在未修复source上运行并保留RED：相同(id,query)box hit=true随后point hit=false，box结果仍须true；当前预期失败为box变{}。
- [ ] 构造固定12正例+4缺目标×target/destination的两组独立mode rows。box所有正例hit、point部分hit，断言两mode各coverage32、各自target/destination/joint计数正确，交换两组先后或交错顺序不改评分。减掉box的一条但保留point对应行，box coverage31，不能32，screening_signal不应通过覆盖门槛。
- [ ] 构造极易区分延迟：box首次10、其余31条1；point首次20、其余31条2；box两repeat3、point两repeat4。断言warm n31各p50/p90为1/2，repeat n2各为3/4，first分别10/20，仅box首条是process cold；加入JSON行和重复行不能改变主coverage/命中或native其他模态延迟。
- [ ] 同行box/mask fixture断言每mode观测均有效、共享延迟值一致，唯一总调用数未加倍；INVALID/EMPTY仍计本modecoverage与invalid_outputs；无mode行的n=0/null遵循现有stats。
- [ ] 实现限定改动，保持严格JSON白名单和allow_nan=False。测试输出目标score-03独占存在时拒绝，原score-01/02字节不变。
- [ ] 执行R510 tests、R505既有合约与R506 scalar tests；必要时仅更新已有测试中硬编码输出版本的预期路径，不改变其序列化/防覆盖断言，记录该测试适配。预期RED可继续，新根因失败交新Astra。

## Task 2 — 真实旧候选回归与Rynn离线评分

- [ ] 捕获冻结旧scorer与新scorer对Lens/Molmo相同已封存输入的内存结果。除scorer_sha256和本计划明确替换的latency结构外，其余字段逐值精确一致，包括native/json指标、coverage、rows、调用总数、资源、run/protocol/oracle哈希；不允许额外容差或字段忽略。独立核旧/新scorer_sha256与真实代码字节相符。
- [ ] 对Lens/Molmo新分mode延迟逐条由原run独立计算验证；其各mode的first/warm/repeat统计应对应原score-02聚合值，因为此前没有分离mode请求，允许结构变化但不允许值漂移。保存可复核比较报告。
- [ ] 用修复后scorer离线生成Lens/Molmo score-03.*并严格解析；不重新生成模型输出。每次完成后保存退出码、产物SHA和全部冻结输入前后核验。
- [ ] Rynn结束后冻结其实际run/raw快照；确认调用数符合原protocol最多100，若完整100条则两mode各32非重复+2repeat，JSON_RGB和JSON_DUAL各16；只按实际记录确认，绝不补齐。离线生成05-rynn/score-03.*。用独立按mode筛行的oracle计算核coverage、命中计数和分模态延迟；未经本mode观测不得填预测。
- [ ] 核stdout严格JSON等于文件去rows摘要，allow_nan=False，hardware_dispatch=false，acceptance仍为DEV screen only；新scorer_sha256正确，所有旧结果和原始输入未变。本轮离线验证新增模型加载/生成调用为0；Rynn正在运行的原计划调用不能误记为本轮新增。
- [ ] 写step-report并汇入阶段总结：明确旧Lens/Molmo定位分数不变、延迟结构版本变化、Rynn实测覆盖与结果、失败原件、输入/输出SHA、命令/退出码；按既有显式研究分支流程提交推送并三方SHA核验，不带大raw/权重/SDK。

## 验收及停止边界

开发通过=RED再GREEN，跨mode评分/coverage/latency隔离且strict JSON保持。实际通过=旧两候选指标逐值一致，Rynn仅对已完成记录评分、模态分列、原始文件未改。低分、空输出或screening_signal=false均为允许负结果，不能据此改prompt/门槛。正式heldout/3D/控制/实机验收仍NOT_PERFORMED。

输入漂移、旧候选指标差异、raw缺失、新异常、需要更改协议/common helper或增加模型调用时暂停相关修复并调用新实际Astra。运行尚未完成时等待或记录NOT_READY，不能用软件测试冒充真实100次完成。本计划本身不执行任何评分或GPU调用。
