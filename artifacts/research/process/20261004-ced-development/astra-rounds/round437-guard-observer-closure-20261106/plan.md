# R437：守卫 observer 失败关闭、停止 bypass 与诊断失败归并 Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans，在当前授权工作区由主实施者完成唯一修复 pass。步骤使用复选框。实际规划者为 gpt-6-astra；已有授权覆盖本限定计划，实施前复核输入后直接执行，不另发确认，不派第二 reviewer。

**Goal:** 修复唯一 fresh review 的三项 Important，保证 observer 失败立即封闭、停止窗口不能接纳外线程普通动作、诊断不漏报已记录失败。

**Architecture:** backend 在活 guard 下保留并消费首个 observer/source 异常；停止豁免只授予当前停止线程的必要内部 CONTROL。研究模块用一个纯 helper 把已保存 guard-event stop/snapshot 异常并入诊断 secondary，expected deadline refusal 本身仍属预期负例。

**Tech Stack:** 当前 Python 3.12 / NumPy / pytest / MuJoCo 3.3.7 / Linux CLOCK_BOOTTIME；不新增依赖。

**Spec:** R435 plan.md 的 Task 1/2、Review Focus 3/4，及 R91 design.md §4。本轮明确继承其最小诊断范围，不扩为 full-H/native。

## 原始失败、输入与根因

唯一 fresh review 是 `round435-t7b-guarded-execution-20261105/review/fresh-astra-review.md/.json`。F1/F2/F3 是已读源码的确定性控制流问题，**尚未运行新反例**；不能称为已观测测试失败。引用位置、复现顺序、影响均在报告中。原有 R435 GREEN 的157PASS/2FAIL以及静态失败日志不覆盖；R436仅修异常预期和四cast，focused 2PASS由主实施者已运行。

- F1：全局 `_guard_stop_depth` 在 closed/thread 检查前让所有非PHYSICS检查返回，停止线程设置estop之前可被普通外线程夹爪命令穿透。
- F2：operation observer/source错误只写failure ledger，正常允许的guard看不到该错误，因此仍effect并成功返回。
- F3：guard closure内部保存的stop_error/snapshot_error没有汇入诊断secondary，预期TimeoutError被捕获后可能PASS。

plan.json包含四产品/测试文件、review、R435/R436计划、历史GREEN/runner和规范的真实SHA256。四文件与主实施者提供的R436完成SHA一致。实施前复核；新根因或超范围改动再交实际Astra。

## Global Constraints

- 只修三个已接受finding；保留R436精确类型收窄和TimeoutError测试契约。未guard的observer吞异常/记录及既有控制行为保持。
- 不改变原始deadline、实际两步、固定关节同位/开夹爪、10秒预算、无渲染、无隐式settle。不得增加实际诊断次数。
- 不修改OC1、prefix120、native reader、worker/lease、控制律、模型资产、阈值、配置或历史失败字节；不更动两个脏gitlinks。
- 按明确路径提交推送，核对本地/上游/远端SHA；不得把清单当完整raw/DB远端包。
- 新测试使用软件backend/原始计数器/确定性线程事件；RED/GREEN不创建第二实际诊断。所有线程必须finally释放/有限join，不使用无界等待。

## Review Focus

1. BEGIN observer在COMMAND/CONTROL/PHYSICS独立失败，0相应effect、原异常为主因、关闭并可STOP。
2. END observer独立失败，保留真实已发生effect，禁止成功与下一步；无guard旧语义不变。
3. 关闭后的安全停止窗口有另一线程请求普通gripper/step，拒绝且无新目标/ctrl作用；内部必要CONTROL仍完成。
4. guard或effect主因已存在时，STOP observer/source再失败不能覆盖主因或阻断STOP；异常str失败仍可记录。
5. 已保存的stop/snapshot secondary即使后续恢复，也必须使诊断FAIL；expected deadline拒绝本身不使诊断FAIL。

## 精确文件边界与接口

仅四路径可改：

- `src/cloud_edge_robot_arm/simulation/mujoco/backend.py`：guard状态/失败消费、stop豁免上下文、`_emit_operation_source`/`_operation_source`在guard下的失败衔接。不要整体重构观察器或改变无guard行为。
- `src/cloud_edge_robot_arm/research/guarded_execution_v1.py`：新增纯函数 `_guard_secondary_errors(events: object) -> list[dict[str, str]]`（可收窄输入类型为既有Mapping iterable），将真实事件中的 `stop_error_type/stop_error`、`snapshot_error`（含overflow最后一条closure嵌套）转为阶段/类型/消息；在result.status计算之前并入secondary。可增加snapshot_error_type保留准确类型；不得根据任意REJECTED把预期deadline误判失败。
- 两个现有新tests文件：新增下列三个明确node与必要不变式断言。
- 本轮可新增implementation runner、validation、delivery和步骤/阶段报告；R435/R436原件不覆盖。

## Task 1：单次反例RED

- [ ] 复核plan.json输入和HEAD关系，冻结本轮源码世代；独立输入不变后开始。
- [ ] `test_operation_observer_failure_closes_guard_without_guard_rejection`：一个node内部循环COMMAND/CONTROL/PHYSICS×BEGIN/END，新backend隔离每case。安装始终允许的guard、只在指定边界抛sentinel的observer。不要以pytest.raises作为唯一证据：捕获后assert原sentinel identity、closed/estop、BEGIN时对应0 effect、END时对应1 effect、后续step拒绝。COMMAND检查records/targets，CONTROL用真实pending dequeue/ctrl变动，PHYSICS检查实际计数/时间。同一测试补无guard对照保留原吞异常行为、以及STOP观察器失败不覆盖已有guard主因。旧代码预期因未抛异常/仍effect而assert FAIL。
- [ ] `test_stop_bypass_rejects_foreign_command_and_physics`：使用真实software_backend，owner线程被guard拒绝后进入原emergency_stop；用仅暂停原hold调用前后的一层wrapper建立Event barrier，此时_stop_depth非零、estop尚False。另一线程调用公开apply_gripper_command(open=False)和step，收集异常/ctrl/command_records/step计数，finally释放并join。应两调用都在任何effect前拒绝、gripper ctrl保持0.039、无accepted gripper、physics0；owner保持原guard异常、STOP必要control可完成。旧代码预期因外线程gripper成功/ctrl变化而assert FAIL。不得从worker调用pytest断言造成未回收线程。
- [ ] `test_diagnostic_retained_failures_change_status`：先由真实software_backend guard拒绝配一次stop CONTROL失败生成真实execution_guard_events，再为snapshot失败生成第二组真实events，第三组只有预期deadline拒绝。测试通过getattr获取helper并assert callable，防止import/collection错误；helper返回的secondary接入诊断同一状态规则，应前两FAIL、第三PASS。实现后补测试overflow closure嵌套，不模拟整个真实diagnostic，不实际运行引擎。
- [ ] 一次RED运行上述3个node（cap120秒）；期望3个call阶段assert FAIL，无collection/setup/teardown错误。已有允许guard、软件clock和thread seams可复用。三项都证实才实施；若未按预期失败保留证据交实际Astra。

## Task 2：一次限定修复与合并验证

- [ ] F1：移除泛化非PHYSICS豁免。给当前同步stop线程的必要内部_apply_control授予窄豁免，普通COMMAND、step/PHYSICS和与该CONTROL无关的RETURN不得通过。普通检查必须保持closed/线程检查；STOP仍不能依赖已失败的guard。允许新增stop-thread标识/精确内部call-scope，禁止公共disable/allow_expired开关。
- [ ] F2：活guard下记录首个observer/source异常，在退出callback重入状态后的effect前或END后检查点传播并关闭；BEGIN失败不做effect，END失败保留effect，原异常不被STOP observer错误替换。保留已有observer failure ledger；stop栈中只记secondary并继续安全停止，不能因待处理observer失败递归STOP。普通无guard路径不改变。错误来自源快照构建时遵循同一fail-closed语义。
- [ ] F3：实现上述纯helper并在真实diagnostic形成status前合并，不把expected TimeoutError归作unexpected primary。记录stage/type/message，snapshot原类型无法取得时显式unknown不伪造。记录溢出closure中的secondary也不能丢。
- [ ] 一次合并GREEN执行R435原精确GREEN范围（159节点）加本轮3node，预期162PASS/1deselected。两个文件已包含新增node，不能另外追加造成重复收集。cap600秒，无skip/漂移/残留子进程。此GREEN同时验证R436与R437，**替代尚未执行的R436整批GREEN**；不再先跑独立focused GREEN。
- [ ] 一次ruff check/format --check四路径、一次mypy --follow-imports=silent两个源，各cap60秒；**替代尚未执行的R436静态**。保留原静态失败日志，不扩大格式治理。
- [ ] 软件/静态通过后，使用本轮新独占diagnostic目录消耗唯一 `R435.diagnostic.1`：原精确实际node、cap60秒，真实2步+真实BOOTTIME等待/拒绝，无第二次尝试。当前累计实际额度仍为R435旧回归2步+本次合并回归2步+唯一diagnostic2步=6步；本轮新反例0实际步。

## 运行入口与前置条件

主实施者按R435/R436 runner制作本轮 `implementation/run_validation.py`，支持red/green/diagnostic，精确argv见plan.json。直接命令为 `.venv/bin/python artifacts/research/process/20261004-ced-development/astra-rounds/round437-guard-observer-closure-20261106/implementation/run_validation.py STAGE`。复用不变的R413 bounded_stage、r413_events、r235_startup_prerequisite；独占新stage和/tmp basetemp、禁cacheprovider、禁autoload、显式JUnit、pre/post source pins、有限timeout和回收。不要修改旧runner或让R436 GREEN/diagnostic也运行。

运行前报告当前Python/MuJoCo/NumPy与BOOTTIME/proc identity、磁盘≥1GiB、无冲突同项目运行、输出不存在、输入fresh；保持REAL_MOTION_DISPATCH_ENABLED=false，不安装或检查模型凭据、无端口/渲染/GPU需求。

## 验收与交付

- [ ] 保存原始spec/stdout/stderr/JUnit/events/terminal/source pins，RED三个预期call失败、GREEN精确分母和静态通过、实际diagnostic每步/命令/拒绝/closure与所有secondary逐项核对。
- [ ] 在唯一review的三个finding下记录RED→GREEN证据；不派第二reviewer，不因旧通过数量预填成功。所有新FAIL/timeout/源漂移/超scope先下一实际Astra；预期RED失败按本计划继续。
- [ ] 总结分别写软件修复、真实无渲染诊断、本轮局部guard证明、完整native guard NOT_PROVEN、full-H producer UNAVAILABLE、native UNKNOWN、真实正常抓放与正式研究未验收。
- [ ] 按精确路径提交并推送研发分支，核对三方SHA，保存失败原件、旧计划和冻结字节；不得清理历史日志使检查通过。
