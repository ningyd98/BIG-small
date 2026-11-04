# R424 租约诊断与毕业设计下一阶段准入 Implementation Plan

> **For agentic workers:** 本计划由实际 `gpt-6-astra` 生成。主代理按 `superpowers:executing-plans` 原生执行；不再次派规划代理，不启动实现修复。用户既有授权覆盖本轮有界诊断，无额外用户批准闸门。

**Goal:** 保存原5项失败，用有限新运行分离测试注入与生产路径根因，并明确可立即继续开发及研究放行的不同门槛。

**Architecture:** 只读源码形成可证伪假设，再在独占新scope逐节点采证；原测试/生产/历史原件字节不变。准入审计按T3b/T7b→T8a/T8b/INITIAL→T9—T13→METHOD/power/FINAL分级。

**Tech Stack:** 现有`.venv/bin/python`、pytest、SQLite、multiprocessing；冻结R413 supervisor/事件插件，R422精确stage模式。

**Spec:** `docs/superpowers/specs/2026-10-04-cloud-edge-device-research-design.md`及对应2026-10-04 roadmap；根AGENTS优先。

## 决定与适用性

**APPROVE_BOUNDED_DIAGNOSIS_ONLY**。输入HEAD `78f36fbaf43d6bbe3b50c40d09097f75895d72ab`、分支 `research/20261004-continuation` 已只读核对。31项原pins全部逐一核对匹配，另21项补充输入见下表。实施前再次核对；漂移不是自动获准扩大范围。本规划者只写本轮4份计划/评估文件，未执行产品测试、API或数据库查询。

## Global Constraints

- 原5个节点各一次、新进程、零重试；每个上限45秒。最多1个独立SOFTWARE_ONLY guard握手/预初始化对照探针，各30秒。
- 串行总上限300秒（含清理）。启动前保留30秒owned清理，stage cap取min(指定上限,总剩余−30)；剩余≤30不再启动。预算不足的未开始项NOT_STARTED，不延长等待或追加重复。
- 原tests/src及原断言不改；不放宽caller/owner/lease/source/clock授权，不改生产锁、事务、busy_timeout或Queue等待；不改冻结driver/旧raw。
- 不运行真实motion、模型或服务，不查看secret，不查询旧DB；真实硬件NOT_STARTED、S3/S4 LOCKED。所有路径指向新stage/new basetemp，禁继承共享SIMULATION_RUNTIME_DB。
- R413历史4751 STARTED=4709P/35F/6skip/1INCOMPLETE保持。R419—421定向42P、R422定向47P/原22目标到原断言不能相加或减法产生新全量。
- 云Max、边缘后置、OpenCV、可见标记、顶视与现控制器保持；真实/正式资格不由软件通过替代。

## 原失败与待验证假设

原件：R413 `implementation/py-module-229`（exit 1，21.21096383398981秒，reaped=true、remaining_live=[]、source_drift=[]）；完整stdout/JUnit/events与原失败SHA保留在输入表。原`stderr.log`为空只是原观测，不推断子进程无错误。

### H1：STATIC_PATH_SUPPORTED_RUNTIME_NOT_YET_CONFIRMED

测试在父publication_guard持锁时spawn；子helper先构造repo，__init__→_initialize→publication_guard需同flock，waiting在构造完成后，因此父等待waiting、子等待父guard形成测试握手循环。

证据：`tests/test_rgbd_lease_handoff.py:149-183`；`src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py:120-125,484-510,2610-2614`。

证伪条件：新进程证据证明构造已完成/guard未阻塞却无waiting，或child启动/导入错误；不能把任意Queue.Empty归为H1。

### H2：STATIC_PATH_AND_ORIGINAL_STACK_SUPPORTED_RUNTIME_TRACE_REQUIRED

expire/request_cancel/retry先进入实际writer事务，race/_handoff测试回调在事务内嵌套公开写；caller code非登记从属身份，目标CAS不变量前被拒。

证据：`tests/test_rgbd_lease_handoff.py:14-55,464-483,516-536,559-585`；`src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py:1567-1585,1980-2057,2077-2105`。

证伪条件：新trace证明connection不存在、caller为真实登记身份仍被拒，或实际正常路径也失败；这将要求另轮生产根因调查。

### H3：STATIC_PATH_AND_ORIGINAL_STACK_SUPPORTED_RUNTIME_TRACE_REQUIRED

expire的父writer已BEGIN IMMEDIATE，回调又在第二SQLite连接同库写入并等待，父在回调返回前不能提交；所谓扫描后心跳与当前原子事务边界不相容。

证据：`tests/test_rgbd_lease_handoff.py:486-513`；`src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py:1567-1585,2077-2105`。

证伪条件：第二连接没有竞争同库、父事务不存在/已提交，或其他锁持有者存在；需新Astra轮，不猜busy_timeout原因。

| 原节点 | 原始失败 |
|---|---|
| `tests/test_rgbd_lease_handoff.py::test_publication_guard_is_cross_process_and_repository_reentrant` | `E   _queue.Empty` |
| `tests/test_rgbd_lease_handoff.py::test_expiry_scan_cannot_interrupt_a_replacement_lease` | `E   cloud_edge_robot_arm.simulation_runtime.operational_lease.OperationalLeaseError: nested public mutation is not a registered same-job subordinate` |
| `tests/test_rgbd_lease_handoff.py::test_expiry_scan_rechecks_current_expiration_in_atomic_update` | `E   sqlite3.OperationalError: database is locked` |
| `tests/test_rgbd_lease_handoff.py::test_cancel_racing_handoff_cancels_current_job_without_restoring_old_owner` | `E   cloud_edge_robot_arm.simulation_runtime.operational_lease.OperationalLeaseError: nested public mutation is not a registered same-job subordinate` |
| `tests/test_rgbd_lease_handoff.py::test_stale_retry_snapshot_cannot_requeue_new_owner` | `E   cloud_edge_robot_arm.simulation_runtime.operational_lease.OperationalLeaseError: nested public mutation is not a registered same-job subordinate` |

## 执行任务

### D0

- [ ] 复核52输入pins、HEAD/branch、原5失败与当前路径；冻结实际运行解释器、pytest插件及新增驱动/探针hash。
- 产物：preflight/input-verification.json、runtime-source-baseline.json、target-manifest.json；source范围至少原1310运行源基线并完整覆盖src/tests/conftest及实际导入插件。
- 验收出口：31原pins与21补充pins全匹配；新增驱动可解释；无生产/原测试写入。实际全baseline数量以新清单为准。

### D1

- [ ] 在本轮implementation/中生成单节点runner及record-only trace插件；复用冻结R413 bounded_stage.py/r413_events与R422 run_stage.py的精确节点模式，不修改冻结驱动。
- 产物：每stage create-only spec/argv/env摘要、独占basetemp及所有DB/cache路径；预先固定5个原nodeid和最多1握手探针。
- 验收出口：源hash前后核对；SIMULATION_RUNTIME_DB不得继承共享旧路径；REAL_MOTION_DISPATCH_ENABLED=false；无secret/API/旧DB访问。

### D2

- [ ] 原5节点顺序各一次新进程运行，零重试；记录setup/call/teardown、JUnit、stdout/stderr、caller/事务/线程PID及owned进程出口。
- 产物：validation/lease-01至lease-05；逐节点原失败→新观测对应表。
- 验收出口：预期3种历史失败可作为诊断证据，不要求PASS；若意外PASS仍保留并分析，不追加复现。不同根因或环境错误停止受影响路径、另Astra；未开始节点明确NOT_STARTED。

### D3

- [ ] 若H1仍缺直接子进程证据且预算足够，运行最多1个预声明SOFTWARE_ONLY guard握手/预初始化对照探针，一次30秒上限；不重复原nodeid。H2/H3使用原4节点record-only trace，不另跑SQL探针。
- 产物：validation/probe-guard-handshake；无必要时NOT_NEEDED。
- 验收出口：调用实际原_competing_guard_process，包含构造前记录与父释放后waiting/acquired；可在同一探针增加子repo预初始化完成后父持锁再请求竞争guard的合法握手对照。不能替代原节点断言通过。

### D4

- [ ] 按H1/H2/H3形成CONFIRMED_FOR_OBSERVED_PATH、REFUTED或INCONCLUSIVE；对照准入矩阵报告；记录新失败，不在本轮修复。
- 产物：diagnosis.json、step-report.md、phase-summary.md、validation-summary.json、postflight/source-integrity.json。
- 验收出口：原始失败及旧分母保留；可继续T3b/T7b受限开发与依赖阻塞分列，不用全库转绿作准入。

### D5

- [ ] 主代理按明确路径整理可交付证据与阶段汇总；按用户既有指令提交推送研发分支并核对本地/上游/远端SHA。
- 产物：精确manifest与Git交付回执。
- 验收出口：完整raw/DB/模型/SDK/凭据不混入精选包，不声称完整远端复现；本规划者不实施该步。

## Trace及一项可选探针的精确边界

**原节点trace：** R235在pytest_configure要求入口trace/profile为空；仅在pytest_sessionstart后安装，sessionfinish恢复。用本轮record-only `sys.settrace`/pytest plugin记录目标函数call/line/return/exception、monotonic、PID/thread、是否存在`_transactions.connection`及其`in_transaction`、caller文件/函数/行、操作名。不得替换被注册函数code、caller frame、参数、返回值、异常或调度；禁止`repr(locals)`、环境/凭据/载荷输出。观察器仅写自己的新JSONL，不执行SQL。`_writer_call`判断caller的原始身份必须保持。插件记录异常不能吞掉原异常；若采证自身失败，保留并停止相关任务，不静默关闭后重试。

**Probe G（可选）：构造/guard握手。** 新数据库与新spawn进程，使用原`_competing_guard_process`函数。独立子入口在调用原函数前记录before_constructor，record-only trace记录`__init__/_initialize/publication_guard/flock`前后；原队列`waiting/acquired`语义不变。父持guard期间观测before_constructor与guard入口，再主动释放自己的guard，核对after_constructor、waiting、acquired及child出口。明确该释放是独立探针的预定时序，不是对原测试的修复。等待均短且总≤30秒；没有child进度证据不能仅凭队列空断言循环锁。不得延长原测试5秒或改原helper。

**H2/H3：** 原4竞态节点用record-only trace证明真实事务与caller；本轮不增加SQL探针。Probe G可在同一30秒内另建新DB，增加先完成子repo构造、再由父持guard发竞争请求的预初始化对照；只有明确握手和子正常出口才计有效对照，不更改原测试。

## 驱动、证据与实际运行前提

1. 固定解释器`.venv/bin/python`存在且可执行；读R413原invocation，只取已知精确argv/env白名单。R413 `r413_events.py`/`r235_startup_prerequisite`及实际导入依赖在preflight补pin，新增驱动也冻结。系统`python`不可用仅是本规划的只读hash工具别名问题，已用`python3`完成；不安装或切换运行环境。
2. 仿R422 runner逐stage create-only，旧spec目录字符串只映射到新目录，原多节点列表换为唯一原nodeid；`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、`-p no:cacheprovider`保持，所有DB/model/cache路径新scope；不复制或打印secret。
3. `.venv/bin/python -m pytest -q -p no:cacheprovider -p r413_events -p r235_startup_prerequisite [record-only-trace-plugin] --tb=short --junitxml=<new-stage>/junit.xml --basetemp=<unique-new-temp> <exact-one-nodeid>`，由冻结owned supervisor启动，不裸跑。probe若用pytest同样使用事件插件；若脚本，则保留完整命令/出口/三阶段不适用的明示记录。
4. 保留invocation/spec、source-before/after、stdout/stderr、collection/start/setup/call/teardown/sessionfinish、JUnit（实际未产生记ABSENT，不补造）、raw-exit/terminal/result、resource-observations、owned-process-identities、exit-before-cleanup与全部signal。自然退出优先；仅PID+starttime+scope确认的owned树允许TERM/KILL，不碰旧进程。
5. 冻结源码前后核对至少所有src/tests与实际导入driver/fixture；原节点只运行一次。预期失败是诊断产物，不能以pytest非零自动重试。驱动、环境、新根因失败先另Astra，独立未受影响项可在预算内继续。
6. 不保证所有测试创建basetemp；结束时实际不存在仅记ABSENT_OBSERVED，不造目录或从旧scope拼入。

## Review Focus与验收边界

- Queue.Empty可能来自spawn/import/worker异常：必须保留child出口和真实握手trace，不能仅复述源码。（D2、Probe G）
- 被拒的测试callback不能证明生产CAS不变量：记录真正事务与caller，保留原目标断言未达事实。（D2原节点trace）
- 其他连接/锁持有者会混淆H3：独占新DB、父in_transaction与第二连接时序一并记录。（D1/D2）
- wrapper/trace改变caller身份会制造假阳性：trace不包裹注册函数、不改控制流，源pin前后核对。（D1/D4）
- 旧快照和软件PASS易误放行研究：准入矩阵与当前缺证单单独记录；power未集成明确列开发缺口。（D4）

本轮完成的标准是可审查的诊断及准入判断，**不是5项转绿**。不确定仍可交付INCONCLUSIVE，不能凭计划修生产或改测试；后续修复须新的实际Astra计划。原失败、历史全量和原始实验字节只读保留。精确Git交付遵循根AGENTS，完整raw/DB/凭据/权重/SDK不混作远端精选包。

## 输入SHA256

完整52项path/bytes/SHA256见同轮`plan.json.input_pins`：原31项已逐一核验，新增21项全部核验。新增清单含`intake/additional-source-pins.json`及`intake/native-source-observation.json`，R235前置插件及native实际入口也已pin。缺失应用索引作为ABSENT_OBSERVED记录，不给不存在文件伪造SHA，不创建该索引。

## Self-review

- [x] 31原输入及21补充源逐项核验；HEAD/branch匹配。
- [x] 5原失败均入manifest；三类假设有原路径及证伪条件。
- [x] 本轮只诊断、明确全局预算和owned清理；修复另轮。
- [x] T3b/T7b开发与实际/INITIAL/FINAL分层，不以旧日期状态替代当前证据。
- [x] 当前native两界None及power未集成已写入准入审计，不把所有积债当共同前提。
