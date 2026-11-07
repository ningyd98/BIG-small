# R452 — observer失败边界的首步拒绝与已发生render计账

实际 gpt-6-astra，2026-11-08；仅规划，0产品修改/测试/actual。主证据为冻结 whole-change-review F2/F5；27pins与副本同R451冻结时刻。

F2/F5合并理由：同一source observer callback边界在不可逆effect已经发生之后才可能失败，现逻辑把“effect发生”“记录成功”“继续许可”混为一体。F2是RESET期间吞下观察者失败后仍继续；F5是返回的render先经过可失败写盘才计账。两者都应先保留事实，再判断来源完整性/拒绝继续；不修改旧backend吞异常或camera渲染语义。F1、F3/F4另有独立计划。

## 适用性与精确范围

先完成R451及2PASS报告。重验27原pins，reader/helper的R451批准diff是唯一预期共享漂移；将原SHA、当前SHA、批准plan/step-report/diff SHA写入新的implementation/applicability.json。原inputs和intake不覆盖。允许新app/recorder/reader、共享CPUhelper、新tests/test_native_observer_failures.py，以及旧新authority测试中与新增counter字段相关的显式SOFTWARE_ONLY stub；禁止修改旧backend/camera/RawV3/guard实现或阈值。

## 实施

1. 新recorder提供 `require_clean_reset()`（或同等明确私有入口），app在真实backend.reset返回后的**下一步**调用，且在enforce_execution_guard、capture_each_physics_step、SETTLE/step120之前。检查实际reset_count=1、reset_result/metadata/episode/config/scenario/asset完整一致、total_physics_steps=0、无recorder.failures/_audit_failures/backend.operation_observer_failures、无pending operation/失败或未完成操作。要求原RESET与其隐式2pass CAPTURE返回、原件库存和frame_source完成、accounting exact；不能只看reset()没抛异常。对应op/采集来源必须实际存在，不能用布尔ready假字段代替。

   backend guard要求已有reset且reset后不允许再重置，故不得把reset搬入旧guard或改旧限制。veto抛出的原错误沿现try/finally记录为collection_body/reset_source，保留PARTIAL、原失败/原件及关闭失败；physics准确为0，已经发生的RESET render照实计。不得为满足STOP证明而在此未入guard失败分支补发无授权物理操作。成功路径才安装原guard并进入SETTLE。清理仍执行，但不能吞掉第一错误或以晚期freeze成功改回COMPLETE。

2. 新recorder在CAPTURE END一进入callback、任何_pending.pop/父类写盘/owner.end_event之前处理本次事实计数。每operation_id最多一次，重复END标失败且不重复计账；BEGIN先分配capture attempt的有界accounting记录。successful实际result中完整pass_state_hashes给出的已返回passes是已知事实，无论之后RGB/depth/instances/source-frame写盘、OC1 mark/end、freeze是否失败都计入。不要从metadata成功数量推算已render数。

   暴露 `render_accounting` 结构：schema_version、known_completed_passes（下界）、exact_passes（int或null）、status（EXACT或LOWER_BOUND/UNAVAILABLE）、attempt_count、unknown_operation_ids与每次operation的returned_pass_count/expected_pass_count/结果来源。现render_passes若保留int只代表known下界，不可再直接当总数。元数据记录规模有界≤原explicit+implicit capture预算，溢出fail closed，不截断/无上限list。

   CAPTURE异常且旧camera没有返回完整pass列表时，真实已完成数未知：该次lower=0只是保守下界、exact=null，不能声称0次render。已完整返回3passes而后写盘失败，仍是已知3；此前完成的其他2/3pass加到下界。没有实际return的预期pass数仅用于预算上界/解释，不当作observed。成功2pass与3pass原样计数，禁止用请求次数冒充实测。BEGIN未到END同样unknown。源观察者/转换失败可能没有complete metadata，仍保留attempt和失败。

3. freeze中保存accounting原件，原render_passes_observed可保留已知下界供历史读取，但新明确exact字段为权威计数精度；新app body/final结果同时保存render_passes=exact（未知时null）、render_passes_lower_bound、render_count_status、计数取自实际CAPTURE END且在shutdown前的provenance。NOT_STARTED确实0，初始化尝试后无可知source则null/UNAVAILABLE。禁止旧BEFORE_SHUTDOWN文字把未知数冒充精确值。完整成功路径exact等于原2/3pass求和和预算；reader几何/lifecycle只接受EXACT且各原件一致，partial保留lower/unknown诊断不得纳入finite/native资格。

4. 不增加实际CAPTURE/physics/render来修计数，不给旧camera中途异常添加假pass数。新collector可在失败结尾从已保留backend operation ledger核对unknown/pending状态，但不能删掉已发生操作以变EXACT。即使freeze无法落盘，能写出的body/final结果也应携带现内存计数和首因；若整个输出介质不可写，则明确report unavailable，不能编造receipt。

## 有界软件验证

使用R451共享SOFTWARE_ONLY helper，真实NativeFullHorizonRecorder callbacks、backend operation wrapper和app失败清理；仅引擎/render本体为假数据，无实际engine初始化。三个节点/完整spec见plan.json：

- RESET source veto：通过真实RESET wrapper/implicitCAPTURE安排一次性source写入失败及observer failure变体，故障随后可恢复；真实app相邻检查必须拒绝，记录调用序列证明没有guard/sampler/step120/dispatch、physics0、PARTIAL且原错误保留。正常RESET也走一次软件基线，证明没有一律拒绝。
- returned-pass/write失败：实际CAPTURE END带3返回hash后让_write_blob失败，断言known/exact保留3，不因后写盘/OC1失败变0；再包含成功2/3pass基线及重复END不会双计。测试应真走父类_record_frame失败点，不只手工调用counter函数。
- midcapture无返回列表：软件camera在中途抛异常，真实wrapper给error END但无完整hash；unknown exact=null，已完成其他capture下界保留，PARTIAL且reader拒绝完整资格；不能借fixture知道的内部模拟次数填进产品原件。

唯一observer-red预期3FAIL（缺reset-veto/写失败少计/未知计数API），不要import崩溃。先以明确assert检查新增API存在可避免无关异常；GREEN必须运行后续真实callback断言。唯一observer-green预期3PASS。child180s/outer300s，fresh目录/basetemp，R413监督及events/prerequisite。无额外probe或宽回归；静态与受影响旧测试统一R453最终gate。任何计划外失败停止并新Astra。

完成后保存实施diff、前后SHA、3PASS结果和phase step-report。R453将只接受本轮明确source记录/计数变化作为共享漂移；不得以“observer修复”扩展控制/guard验证。

实际额度完全不变。软件验收不是actual证明，原R44986PASS与历史失败继续保留。R450服务授权不使本修复获得额外实际许可。
