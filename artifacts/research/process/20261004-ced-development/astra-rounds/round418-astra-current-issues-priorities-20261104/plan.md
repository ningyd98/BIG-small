# R418 当前问题与优先级 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: 实施时使用 `superpowers:executing-plans` 按任务执行；本轮仅规划，不启动实施、不请求执行方式选择。用户指定目录覆盖技能默认路径。

**Goal:** 先保证运行报告可信，再恢复有效测试覆盖与真实正常路径，最后补研究资格。

**Architecture:** 第一轮只在 Phase11 adapter 的证据读取与结果投影边界修复“内层未完成、外层却成功”，将软件完成、任务成功、论文资格分开。输入模式正常路径恢复、视觉替身、租约、API、复现、性能和研究前置分为独立根因轮，保留所有原失败。

**Tech Stack:** Python 3.12、pytest、SQLite、现有 SimulationWorker/Phase12AdapterResult；后续涉及 OpenAPI/TypeScript。

**Spec:** 根 `AGENTS.md`、本轮 `intake/assessment-baseline.json`、R413 全文开发进展与测试报告；本计划由实际 `gpt-6-astra` 生成。

**状态：PLANNED_NOT_IMPLEMENTED。本轮新测试 0、产品修改 0。**

## Global Constraints

- 每轮新问题/计划外失败先由实际 gpt-6-astra 形成计划；同根因可合并，预期 RED 不另起轮。
- 既定云方案、边缘模型选型后置、端侧 OpenCV、可见姿态标记、顶视相机及控制器方案不变。
- 不放宽 source/owner/thread/clock/lease/publication 门禁，不改历史 raw/失败/JUnit，不以软件通过替代真实研究。
- 本轮不运行测试/产品/SQL/网络/模型，不写 Git、不进入 dirty gitlink；只排他新建本计划两文件。
- 首轮修改限 adapter 一源文件及一新测试文件；范围扩大或新根因须下一 Astra 轮。

## Review Focus

- SQL SUCCEEDED 而实际 task_success=false：外层不能宣称任务成功，完整执行仍可单独记录完成（Task 1 反例）。
- 任一 main/recovery/duplicate 阻断或缺件：不能被另两条成功掩盖，保留全部原原因（Task 1 参数化）。
- 终态文件存在但为空集合、错 run/hash/attempt、发布未确认：存在性不是确认完成（Task 1 反例）。
- 同一 adapter 固定成功字段、事件条数当毫秒：先隔离资格，不把代理指标冒称真实实测（Task 2）。
- 只修改输入的真实 legacy 正对照：不得 stub worker/lease/结果，也不得将软件完成提升为 RGBD/实体/论文通过（Task 3）。

---

## 结论与证据口径

**建议第一步：先修 Phase11 回执真实性，先止住伪成功，再恢复正常运行入口。** 相对旧开发报告把 22 项前置排在第一位，这里调整顺序，是因为已确认的外层成功声明会污染运行统计和研究结论，而那 22 项当前只证明测试未走到目标断言。不是按失败数量或修复难易排序。

一次长测共 4753 唯一节点：4751 软件节点均 STARTED 恰一次，4709 PASS、35 FAIL、6 原 backend SKIP、1 INCOMPLETE；2 真实数据 NOT_RUN。35 是失败测试数，不是 35 个已确诊生产缺陷。4737 节点有 JUnit，原075超时后14个已开始节点只有阶段证据（11 PASS、2 FAIL、1 INCOMPLETE），不补造 JUnit。

| 状态 | 现有证据 | 影响与置信度 |
| --- | --- | --- |
| 已恢复 | 原生开发 MOCK ETEAC 1.475秒、queued PCSC 1.610秒，各 attempt=1，lease/thread/FD清空；94闭环含9T3全P，另nativequeue5+legacy4全P | 高置信开发回归，均含在4751分母；不重复加总，不是实体验收 |
| 已恢复 | 浏览器42P+1原SKIP，旧19全恢复；Vitest43、TS/ESLint/build通过 | 展示与软件证据；研究页面600组4200项all blocked/actual NOT_RUN/formal=false仍保持 |
| 未解决 P0 | 5580 raw/manifests、20实验；raw声明4860调用/完成/权威，720 blocked；900内层回执不支持外层完成，含F20全部180行（supported=0） | adapter无条件成功链路高置信；不能把raw声明当研究成功数 |
| 未解决 P0 | 同adapter固定完成率1、planner_success=True、valid_contract_rate=1，100+event_count/50作毫秒并标event-derived | 源码公式属事实；作为真实时长/质量证据不充分。是否允许模拟代理指标须审契约，先隔离论文资格 |
| 未解决 P1 | 21 RuntimeSpy缺_local_mode + 1 recapture lambda拒绝completion | 22项目标断言未验证；接口失配高置信，目标产品行为尚不能结论 |
| 待定位 P1 | 5租约失败：3嵌套public mutation拒绝、1DB locked、1Queue.Empty | 产品/测试注入待分离；不能直接放宽授权或延长等待 |
| 未解决/未完成 P1 | Phase12真实性2FAIL + 1INCOMPLETE | 回执修复与accepted资格可能是不同依赖，旧断言不能为转绿改写 |
| 未解决 P1 | API生成9 schemas语义差异，包含publication/confirmed_succeeded/unconfirmed_terminal | 不是格式问题；必须保留“记录SQL终态”和“确认发布”区别 |
| 待定位 P1 | 两项seed结果hash相同但事件摘要/payload_hash不同 | 未有完整差异payload，不能先删除不稳定字段 |
| 性能未达 P1 | UTC两case语义P；2268.880+2233.629=4502.509秒 | 原合计600秒线未达；未profile，不能归因或当生产延迟；7200诊断cap不替代600 |
| 未解决 P2 | Ruff1156/42文件；format139、Prettier11；中文CLI342与4个pytest治理失败；文档18规则命中；Mypy未到源码检查 | Ruff含B02332/B9054逻辑类，非全格式；中文40docstrings/旧2330coverage与CLI口径不同；18命中非18泄露 |
| 研究外部gate | 2真实RGBD数据、模型/Isaac/ROS/控制器、CED资格/校准/B0/INITIAL/METHOD/FINAL未验收 | 当前真实外部前置缺失；软件和fixture不能补足 |
| 保持历史边界 | R407精确死因UNKNOWN；R413“计划先采集”Minor已勘误 | 不反推旧死因，不为修文案改冻结原件 |

Phase12 run/analyze/export exit0 不代表验收；verifier exit1，`PHASE12_REJECTED / THESIS_PACKAGE_INCOMPLETE / NOT_CLOSED`，门控权威行数为 **0**。`python-outcomes.json` 的内嵌 summary 是较早诊断快照（final=false），非Python最终结果采用最终测试报告/各审计；不把其 RUNNING/PENDING当当前执行仍在运行。

规划输入 HEAD=`4a82aa0c288832382ffddc8e0bb88ea532de402f`，被测源码commit=`ab18abd0f82a024b62f4423c946c6585f8d18c65`。1309 pins无漂移来自根执行者新 intake，本规划独立复核26个主要输入和13个补充输入 bytes/SHA。报告提交增加tracked路径，不等于运行源码变化，也不等于对新HEAD重新全测。

## 首轮限定计划：先让报告真实（不恢复研究资格）

首轮候选新目录：`astra-rounds/round419-phase11-receipt-truthfulness-20261104/`；实施时排他新建，存在则新唯一后缀，不能复用或清空。本轮不创建它。

**修改：** `src/cloud_edge_robot_arm/final_evaluation/adapters/simulation_runtime.py`。

**新增：** `tests/test_phase11_adapter_receipt_truthfulness.py`。

**保持不改：** `_draft` 输入路由、ExperimentDraft 默认 RGBD、worker/repository/lease/publication底层、runner/validation/models、所有旧测试断言、API生成、历史证据。当前默认MOCK→RGBD_CAMERA_REQUIRED留作原生负对照；生产正常入口恢复另轮。首轮不把全局输入切成legacy或RGBD，不通过改 verifier 变绿。

### Task 1：从每条真实内层证据投影运行结果

**接口：** 保留 `Phase11RuntimeAdapter.run(context: Phase12RunContext) -> Phase12AdapterResult` 与三个 `_run_*_job` 签名和receipt已有键。新增 `_collect_job_evidence(repo: SQLiteSimulationJobRepository, run_id: str, artifact_root: Path) -> dict[str, Any]`，由三条probe收集当前job/attempt/lease、result/metrics/consistency原件及hash；各probe添加 `execution_evidence`。新增纯投影 `_runtime_outcome(main: dict[str, Any], recovery: dict[str, Any], duplicate: dict[str, Any]) -> dict[str, Any]`，返回现有 result 的状态/成功/调用/完成/阻断/环境/失败原因字段，不执行任务。

- [ ] 写 `test_current_rgbd_mock_blocker_propagates_from_native_receipts`：真实当前_draft+Worker+SQLite+recovery，原件主/恢复/重复任务阻断时外层 `BLOCKED_BY_ENV`、`task_success=false`、`runtime_completed=false`、`authoritative=false`，无completed成功事件。`worker_consumed=true`、wrapper `runtime_executed=true`不能单独证明任务executor执行。
- [ ] 写 `test_job_succeeded_with_failed_task_is_not_task_success`：SQL `SUCCEEDED` 但result `task_success=false`不得外层任务成功；若executor返回且终态证据完整，允许 `runtime_completed=true`，分清完成和成功。
- [ ] 写 `test_missing_mismatched_or_unconfirmed_receipt_fails_closed` 和 `test_each_required_probe_can_veto_outer_success`：分别缺result、错hash/run/attempt、空artifact集合、未终结attempt/FINALIZING、需确认却未确认发布；main/recovery/duplicate逐个BLOCKED/TIMEOUT/FAILED均能否决成功，保留各自原因、原计数0。
- [ ] 先运行新纯投影及原生阻断节点，确认RED来自错误成功/证据缺口断言，而非import、依赖、资源或lease错误；保存真实phase/exit。
- [ ] 最小实现证据采集与投影：只读本次新run路径内的原件，身份与hash一致；不补写缺件、不把`all([])`当成功。所有必需probe有executor实际进入/返回和有效终态才可completed；阻断/超时/缺件false；真实执行失败可以completed但不task_success。
- [ ] 状态优先级固定：证据缺失/不一致→FAILED+FINALIZATION；否则任一环境阻断→BLOCKED_BY_ENV+RUNTIME；否则TIMEOUT；否则任务/恢复/去重义务失败→FAILED；全成功才SUCCESS。保留所有原probe终态和原因，不能只留下优先级最高一条。
- [ ] `runtime_invoked`只基于实际任务executor证据（至少主任务可证），逐probe记录调用事实；部分执行不等于全完成。公开确认发布协议需要confirmation时不得以SQL终态替代；legacy路径不适用则显式NOT_APPLICABLE，不借此绕过RGBD确认门。
- [ ] 运行同组GREEN；若需要修改worker/repository确认机制或计数机制，停止扩张，交下一轮Astra。

### Task 2：隔离未经证明的成功与性能指标资格

**接口：** 保留 `_metrics_from_runtime(main, recovery, duplicate, digest)` 与 `_metric_provenance(source_artifact)` 的签名。仅调整本adapter的字段值依据/来源声明与资格；不修改统计全局规则或其它simulation适配器。

- [ ] 写 `test_proxy_metrics_are_not_measured_or_authoritative`：阻断时完成率不为1、planner_success不固定true，未知contract有效率不声称1；事件数公式和50ms不能标MEASURED/EVENT_DERIVED。缺实际测量时采用现有NOT_AVAILABLE/CONSTANT_PLACEHOLDER分类；需要保留的历史代理数值只能作为诊断且不能获得论文资格。
- [ ] 确认RED是当前无依据固定值/来源声明，再更改成功字段以真实任务结果为依据；未知质量字段用明确未测来源，不发明新测量。
- [ ] 首轮本adapter `authoritative_for_thesis=false`，理由写入新receipt：已确认代理毫秒与质量常量尚未资格化。真实软件完成仍可true；禁止用source hash、SQL SUCCEEDED或测试PASS解除隔离。
- [ ] 运行GREEN和现有 `_result_from_adapter`/`_authoritative_for_thesis`消费边界断言，证明adapter的false不会被上层提升；不改consumer为让测试通过。

这是一项有界隔离决策，不声称所有模拟指标均无效。后续独立轮必须先找出代理指标的历史规范、单位和允许使用范围；若要恢复真实时长，使用有来源的实际计时/原指标，不以`100+event_count`换另一个常量。

### Task 3：真实正对照、资源收口与第一轮交付

- [ ] 写 `test_explicit_legacy_input_uses_native_receipts_without_formal_acceptance`：测试专属wrapper只把 `_draft` 返回值的 `input_mode` 明确设为 `LEGACY_PIPELINE`，保持 `execution_scope=VISUAL_PLANNING`，记录 `TEST_ONLY_INPUT_OVERRIDE`。不得stub `_run`/`poll_once`、SQLite、恢复、lease、结果或artifact。真实运行主任务、恢复、去重，核对原result实际成功、三probe终态、duplicate调用1、恢复转换、attempt、释放lease与hash；外层软件完成可true但研究资格和硬件声明false。
- [ ] 若正对照实际任务失败、恢复超时或lease拒绝，保留失败，不能改输入/断言直到绿；这构成新增根因，停止该正常路径并另Astra。P0已有负路径修复证据单列，不夸称完整首轮通过。
- [ ] 各阶段独立新DB/basetemp，禁共享`SIMULATION_RUNTIME_DB`覆盖。执行绝对`.venv/bin/python`，纯投影每node cap120秒，原生每node cap600秒，零自动重试；job timeout30秒/原TTL/恢复1.05秒不改。cap是保护预算，不是时长承诺。保存node STARTED、setup/call/teardown、exit、JUnit及原始stdout/stderr/source pins。
- [ ] 自然退出优先；超时仅TERM已确认PID+start_time+新scope的owned树，清理cap30秒，必要KILL同身份。核对lease释放、heartbeat线程和本run FD归零；不全局pkill、不碰旧进程/旧DB、不补造JUnit。
- [ ] 针对性检查仅新增/修改文件；复核差异未越界、旧pins未变、旧证据不动。第一轮报告区分“真实性修复完成”“生产正常入口未恢复”“研究资格未恢复”。按明确文件交付、normal push并核对三处commit SHA，不能目录宽选。

未来运行命令形式（本轮未执行）：以仓库绝对`.venv/bin/python -m pytest`指定上述新文件的精确node，`--basetemp`和`--junitxml`指向该轮独占阶段目录，由已有有界owned runner记录真实退出/阶段事件。先创建输出父目录。不得把所有旧Phase12模块打包再用1800秒预算碰运气。

**第一轮验收：** 当前真实阻断被如实传播；完整软件执行与任务失败分开；缺件/未确认不被接受；原生正对照有效且清理完成；未证实时长/质量不获研究资格。首轮不要求原2FAIL立即全绿、不重跑5580、不要求4751全绿或UTC达600，更不意味着实体机器人通过。

## 后续分轮与依赖

| 次序/根因 | 目标与最小验证 | 停止条件/依赖 |
| --- | --- | --- |
| P1 测试前置 | 共享RuntimeSpy与recapture签名匹配原声明模式；原22精确节点+helper模块/安全门反例确实到断言 | 不在产品用getattr或默认值放宽未知runtime；新增失败另Astra。可独立于adapter推进 |
| P1 租约5项 | 分开诊断嵌套注入、双连接事务、跨进程队列；保留child exit/stderr/owner时序；验证旧owner不能覆盖新owner及跨线程/进程边界 | 不延长等待/换锁/删guard掩盖；若真实正常路径依赖此层，先修相应根因 |
| P1 输入意图+真实性复验 | 单独决定固定MOCK的Phase11 adapter应否显式legacy软件路径；覆盖F04/F05/F06/F20；原主/恢复/去重正负例 | 全局RGBD默认不变，legacy不冒充RGBD；指标资格另审，不靠mode切换恢复论文资格 |
| P1 原2FAIL+1INCOMPLETE | 原F20回执、paired acceptance、missing receipt verifier三节点分别新scope/JUnit；保留原失败。再最小validation | accepted取决于provenance/指标资格；不得改verifier或旧期待换绿。原INCOMPLETE仍是历史INCOMPLETE |
| P1 API语义 | schema稳定后生成OpenAPI/TS两次一致；confirmed/unconfirmed/blocked消费反例、TS/Vitest及必要浏览器节点 | 只读核对可独立；写入等对应publication语义稳定，不手改生成文件掩盖漂移 |
| P1 事件复现 | 两场景先输出完整原payload、首个不同字段；原同seed两例+不同seed反例 | 未证明身份/时钟语义前不删事件/UUID/time，不仅比较result_hash；与接口轮可独立 |
| P1 UTC诊断 | 一次有界代表段profile，区分wall/CPU/IO/observer；确诊后另Astra修复，无profile完整两case验原600秒 | 7200每case诊断cap、零重试，不改TTL/缩场景；避免与重负载并发，不承诺墙钟 |
| P2 静态治理 | B023/B905逻辑先分类；Mypy用CI实际`python -m mypy .`/明确源码范围先建立有效检查；治理路径重新快照 | 不仅加py.typed宣称完成；新类型/逻辑失败另轮。中文覆盖不能沿用2330作当前计数 |
| P2 格式/文档 | 精确文件小批格式；18docs命中本地裁定与脱敏；新tracked证据覆盖/排除政策先定 | 不全目录autoformat后沿用旧长测；不删冻结证据让治理通过 |
| 研究gate | 真实RGBD数据/模型/Isaac/ROS/控制器及CED资格、校准、B0/INITIAL/METHOD/FINAL逐门实证 | 前置/授权未齐保持NOT_RUN/BLOCKED；准备可独立，实际外部执行本轮未授权 |

跨组针对性验证、源码与契约稳定后，再规划 **一次** 全量长测。正式full矩阵需研究前置齐备再独立计划；不要立即重复4小时56分测试或5580矩阵作为定位工具。

## 来源与交付边界

本轮仅两计划文件由Astra写。根执行者可排他新建step-report/phase-summary，连同intake按精确5文件做文档交付；只记录“建议已形成、未实施、0新测试/产品修改”。Git回执local-only，normal push后三处SHA核对；规划提交不代表源码行为复测。完整raw、运行DB、凭据、模型权重、SDK及dirty gitlink内部不进入计划包；清单不是完整远端复现包。

旧R407 UNKNOWN与review Minor保持原件，已恢复ETEAC/浏览器不再列未解决。主报告、审计与关键回执已静态阅读；未运行仓库解析器/报告生成器，未打开SQL。以下全部输入已逐项 bytes/SHA复核，完整结构也在plan.json。

## 输入 pins

| 路径 | bytes | SHA256 |
| --- | ---: | --- |
| `AGENTS.md` | 1774 | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/reports/development-progress.md` | 7267 | `87d9f0f34d2a909456cbe16b01a2d9d097c18dc7b769fd778bec9fc8f4e5909e` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/reports/test-report.md` | 34747 | `10f9104b5912cd60e7611c53d2a3c4a315f9f39985c2b76afaa0dc1a3fe85d9b` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/reports/summary.json` | 910 | `fa2bf04260bd8e2e99e0441985fc410943255cee2f4ec1f4998f1137b4b4b926` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/reports/python-outcomes.json` | 68580 | `dd6615ccc58f2886d7c0e848f2e79c371d25c910e0e8c104545e1f957a775978` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/reports/phase12-audit.json` | 669501 | `71fdf73fc03cfa6d9641ad91d83dc477fffc60d48685dbe04fa7746efa10d170` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/reports/f20-receipt-audit.json` | 3260 | `f3368e5b3f3e3f7f5cd9e2a236d828a8c95d1374282040d948ea1097eb64a5a7` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/reports/static-frontend-audit.json` | 13397 | `300adcbfaa6ee26d8bdf9d91ade5190912b68d88ba18faf32d417c4b8dbdfd8a` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/reports/utc-audit.json` | 3558 | `1a6ebe67b77d6f1d845b81542c7aebbce45d96c0d3443fcd8af587050efeda8b` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/reports/native-queue-audit.json` | 1308 | `1f50a59c1814c86688c797f3e074b02d8b18dc58bbae94eb8cd26922306f1a08` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/reports/browser-audit.json` | 22350 | `aedfa726e572d24e3bf79c875ed72539587b2cef0a204ab5d6f6393ca52f819a` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/review/whole-evidence-review.json` | 12348 | `27cc3a604940e4c2e1b9e92dc7e7a8f2c03fdd2d3483598a2b6c067ba84e4e3a` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/delivery/selected-manifest.json` | 1923564 | `3cef46eb416a921353d46e2bd5c208121e77f9598a4b80f2c8d59965120957d0` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/preflight/runtime-source-pins.json` | 240489 | `4cc95e6ab8fc6435cd3a1931709ec66aa687fed0119d24880723e1b4c69198c7` |
| `src/cloud_edge_robot_arm/final_evaluation/adapters/simulation_runtime.py` | 18365 | `e63c8278ae26015d2aad360cf289a45000c4e137989257e9f20d1aa115769089` |
| `src/cloud_edge_robot_arm/vision/execution.py` | 104819 | `69f2c1b7dabc0106697eb656bff67da331d4b5386433ae62b9f4f9ff094189f0` |
| `tests/test_visual_worker_execution.py` | 13280 | `45ae3e30cd2b338227512e138429c5636fc46552f5f484ea8226f8c4375f5c5e` |
| `tests/test_visual_worker_supervision_execution.py` | 14808 | `aaaa535392f728227e4ceb900cd57c5d7f004c36f82da7d159357b09f76d5432` |
| `tests/test_rgbd_closed_loop.py` | 27689 | `10aa14e399ecfdcaa1f54f6b09f811fe90b5ab32309c0cd9bb88291ffecda77f` |
| `tests/test_rgbd_lease_handoff.py` | 23788 | `2eea572c84097366671b22a9ca75e044a1a732ce45554dad252ae16d2fb13987` |
| `tests/test_phase12_2_runtime_authenticity.py` | 82002 | `2a74f64daec33ce722d418dbecaa7c68a84b18c7250b1cf22ea141495965ddfa` |
| `tests/test_phase8_1_reproducibility.py` | 1893 | `ac33c2a984dbf0c72422e158106421d55a60ea408c6c33ba2190cb830136f137` |
| `tests/test_phase8_reproducibility.py` | 1748 | `72e4c62696fcecade84c98da969d490f18c5afbc607df19b5b011674f1b34926` |
| `pyproject.toml` | 2458 | `b2bf5c4042d568eaf9def415ae7b2f08f0fa541a01f970b7e68e6d950035bb6c` |
| `.github/workflows/ci.yml` | 11143 | `21604e167326da8b0f40a9f5dee18b57a9f017b51609504fbc688d2f4b851eb7` |
| `dashboard/package.json` | 1639 | `1c68084539ee59484c222b49e92d9f44e00d8766d16f9eb2d312fda263e4edb8` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round418-astra-current-issues-priorities-20261104/intake/assessment-baseline.json` | 7402 | `acf85edce57953ea4ed2f137c6cce23d0dee112e3a7442cdc0b95891ad2148d2` |
| `src/cloud_edge_robot_arm/final_evaluation/adapters/base.py` | 3569 | `fc8b03c4a47246eb5951262c780c631be370f77dffd91eea909e0418733724dd` |
| `src/cloud_edge_robot_arm/final_evaluation/models.py` | 11295 | `875d039814a307169516fc339e7d9f375f7b8bd54e61e6f535a21424fe6cd931` |
| `src/cloud_edge_robot_arm/final_evaluation/runner.py` | 32406 | `862470958f99138cfca3da2efe6f398b9e19461e9c77e11f7e064a3e1face0f2` |
| `src/cloud_edge_robot_arm/final_evaluation/validation.py` | 40695 | `86dc6a65f8d101caa3ea7def9e27691ae940aa85a68231dc1a9953333c7de786` |
| `src/cloud_edge_robot_arm/final_evaluation/adapters/phase8.py` | 10673 | `c06585911891438f29e7af4e5b337da7bb004200840afbd41a2d7386007d4aa6` |
| `src/cloud_edge_robot_arm/simulation_runtime/worker.py` | 94282 | `2eff68be6887b2b5d1b891b57dd522ff7bd420231288047e5fdee57fbca0b974` |
| `src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py` | 138430 | `6e1ae6471e5d75c195057e1f8e1f90854b1efcfe21f21660bd0a7d75a6d21eb2` |
| `src/cloud_edge_robot_arm/simulation_workbench/models.py` | 19539 | `8c15b971b36438f888af01bed083ab950bd350e9a1e566d7d2513e84b28ceae2` |
| `tests/test_legacy_reference_mode_compatibility.py` | 3938 | `36025b4d870e307f5a6cbe3588fcd207c893a05aa0ce82ff622d3da2554b6e01` |
| `tests/test_operational_runtime_closure.py` | 316555 | `4faa09f6701241acd2316571595ff023a636653ccd3356f3133276efc4806440` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/reports/evidence/f20-first-runtime-receipt.json` | 5033 | `f012a94317586138cd644a8e501e735e8140f1f722bb0684f39c16cab0f43274` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/reports/evidence/f20-first-duplicate-result.json` | 450 | `8d9f88c694b5b44db113c15632f34d1b4988ead11db99ed72278f3e69c8db2b9` |

## Self-review

- [x] 自审计数/单位与原事实一致，35FAIL未当35产品缺陷，旧2NOT_RUN/1INCOMPLETE/6SKIP均保留。
- [x] 区分事实、推断、待验证假设，初轮限定adapter/新测试，不放宽既有门禁或研究资格。
- [x] 每项Review Focus均有具体测试；正对照运行真实worker/SQLite，明确测试输入覆盖不等于生产路由恢复。
- [x] 后续根因独立、依赖明确，未即刻重跑长测/全矩阵；新根因/范围扩大/计划外失败回Astra。
- [x] 本轮只计划、未实施，根交付仅精确5文件，未另派agent/helper审查。
