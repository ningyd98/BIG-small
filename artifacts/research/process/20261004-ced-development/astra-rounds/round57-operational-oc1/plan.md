# OC1 operational-time v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Preserve the user-authorized execution arrangement and independent review. This dispatch creates only the plan; it performs no implementation or actual run.

**Goal:** 新增 simulation.operational-time.v1 的整数域类型、真实 Linux startup reader、live receipt 校验及保守年龄/固定截止数学，交付仅 OC1 SOFTWARE。

**Architecture:** 两个新 Python 文件；生产工厂从当前进程实际 BOOTTIME/boot/进程启动/time namespace 取值，私有 CPU fixture 控制反例。同 owner 签发活句柄，reader 核实原始事件因果点后计算。旧 UTC、RawV3、native、consumer 和 R07 producer 均不修改或导入本模块。

**Tech Stack:** 项目 Python >=3.12、stdlib time.clock_gettime_ns(time.CLOCK_BOOTTIME)、Linux procfs、pytest、现有 Ruff/mypy；无新依赖。

**Spec:** docs/superpowers/plans/2026-10-05-operational-clock-repair-supplement.md 的 OC1；astra-repair-planning/clock-dependency-review.md §3、§6。相邻 plan.json 固定输入 SHA256/bytes、外部访问和失败证据。用户已授权此设计；不再新增设计确认阻断。模型角色来自指定 Astra 派单，未独立探测运行时模型元数据。

## Global Constraints

- D 是平台真实操作计数，1 operational second=1_000_000_000 整数 D ns；S 仍是同 backend/episode 的仿真量。本模块不处理S，不把D写入datetime/UTC。UTC/SI accuracy、future H_D、geometry/motion仍未知，不造零误差、ppm或精度padding。
- 5秒ordinary/condition及5000ms receipt上界等值接受，+1ns拒绝；固定deadline等值拒绝。1000ms外部未来规则留在旧路径；本地D仅已证实event-before-current可计算age，不能把未来/逆因果用该容差放行。
- deadline=原起点下端+固定budget_ns。重观测、回包、新event、重试、重启不刷新。OC1同owner/key绑定原截止；跨进程恢复与真实任务key/lease/fencing闭包仍为OC3，当前拒绝恢复旧能力。
- startup工厂只授予本进程计时能力，不授予worker/lease、native或机器人准入。活对象注册防普通复制/外来来源，不承诺抗同进程恶意代码、管理员、改内核或虚拟时钟攻击。
- 只新增下述两源；不改__init__、CLI、config、teacher/backend、旧UTC/native/consumer。无actual/provider/renderer/physics/decoder/hardware，无九组生成。报告另写新目录，旧raw与失败不变。

## Review Focus

1. 合法重叠因END seq被误拒：Task1用owner登记的事件发生点和current因果关联，不要求c+≤n−。
2. PID复用、namespace/offset变化、fork、copy越域：Task1/3绑定真实启动身份和活对象。
3. 5秒与deadline边界混同或float丢1ns：Task2使用整数及大于2**53的基点。
4. production factory有caller clock/source捷径，resolution冒认准确度：Task3零参数工厂及单一白名单。
5. 过期后新event/重建deadline重获有效：Task2绑定原key/起点/预算；Task3关闭或新进程拒收旧能力。

## 原失败、根因与待验证假设

旧UTC守卫拒绝正确：R03实际A原包缺冻结draft08必需NONC。actual-prefix/wire-replay.json原重放returncode=1、stderr为“response nonce differs from original request”。独审记录response SHA 06e256a2b95a36e251783f4a63a2f9b1434d94518e739ef1f853021eecb4a512；A一发一收，B SKIPPED_A_UNAVAILABLE，未进入签名验证。本计划仅读既有失败，不重放、不改协议，不推断全部外部UTC不可用。旧current/nativeUTC UNAVAILABLE与RawV3原判定保持。

本轮问题是已授权operational scope尚无独立类型/reader/startup能力，不能用历史UTC slab外推now，也不能直接把ExperimentClock的monotonic或模拟步当完整wall source。验证假设是在可信Linux同进程同namespace的BOOTTIME域，依API顺序合同可计算保守操作年龄/截止，不依赖UTC偏差或SI精度；能力缺失则拒绝，不fallback。

原普通exec在shell前失败：bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted，exit1；改用限定require_escalated只读/计划写入。另一次计划写入functions.exec在工具编排解析前SyntaxError: Invalid or unexpected token，未执行shell/写文件，后以安全raw字符串重发；这是规划工具字符串错误，保留记录，没有源码修复。kernel time_namespaces猜测网页返回Internal Error，未当支持证据；namespace语义取自已读本地Linux header。

## 来源合同、官文和实际验收边界

production白名单只有Linux time.clock_gettime_ns(CLOCK_BOOTTIME)，无MONOTONIC、RAW、perf_counter、REALTIME、CPU clock、caller ns/callable或source flags兜底。

[Python 3.12 time官方文档](https://docs.python.org/3.12/library/time.html#time.CLOCK_BOOTTIME)说明BOOTTIME包含系统suspend、clock_gettime_ns返回整数ns，clock_getres描述resolution。[Linux ktime官方文档](https://docs.kernel.org/core-api/timekeeping.html)区分MONOTONIC暂停与BOOTTIME包含suspend。实际访问记录点 **2026-10-05 17:53:28 UTC**，由读取后clock工具记录，不是来源发布时间或计量校准。

本地/usr/include/linux/time.h固定CLOCK_BOOTTIME ID；安装Linux timekeeping.h注释确认suspend语义，time_namespace.h定义boottime offset及frozen_offsets。完整路径/SHA在JSON。安装header不替代运行内核；实施需记录实际os.uname/Python、能力读数、boot ID、PID及进程启动ticks、线程、namespace/offset。/proc/self/stat解析要跳过可能含空格/右括号的comm再取field22，不能全行split。

用/proc/thread-self/ns/time实际st_dev/st_ino及/proc/self/timens_offsets；仅同owner线程，创建前后及每次使用校验，缺字段或漂移则吊销。resolution仅诊断、不进入数学，UTC/SI accuracy为null/UNVERIFIED。同值连续计数可以合法，下降/负数/非int拒绝；不能宣称一次读或resolution能识别所有停止/加倍。API包含suspend合同不等于该VM hostpause、实际suspend/restart已测，这些保留OC3 gate。

## 两个owned文件与冻结接口

Create **src/cloud_edge_robot_arm/research/operational_time_v1.py**：值类型、最小Linux源、live registry和reader同一模块。
Create **tests/test_operational_time_v1.py**：真实公开接口CPU测试，私有源seam控制原始读数/身份，不mock最终verdict。

- OperationalDomain：只读schema、API、boot_id、pid、process_start_ticks、owner线程、namespace/offset、factory startup nonce、OS/Python、resolution诊断。descriptor/hash相等不授权。
- OperationalBracket：不可变domain/event identity、lower_ns:int、upper_ns:int；严格type(x)is int、0≤lower≤upper。普通构造/反序列化值不可替代registry中的exact object。
- OperationalAge：lower_ns:int、upper_ns:int；判断仅ns，若显示秒用exact Fraction，不以float判门。
- OperationalDeadline：原origin活receipt、task_key、固定budget_ns、deadline_ns及首次发行identity。
- open_operational_clock() -> OperationalClockOwner：零参数生产startup入口；读取真实Linux身份与source，每次创建新startup域。缺能力/procfs抛OperationalTimeError，不导入backend/provider，不接收app/PID/domain字符串冒认worker。
- owner.begin_event(kind:str) -> OperationalEventToken；owner.mark_event(token) -> None；owner.end_event(token) -> OperationalBracket。BEGIN读c−，真实事件发生点mark一次，END读c+；缺任一步无有效pair。OC2负责接入真实acquisition；本轮CPU mark不证明摄像头事件。
- owner.read_current(*, after:OperationalEventToken) -> OperationalBracket：after已MARK；读n−、内部登记current因果点、读n+。允许原事件END晚于current，因此保留合法嵌套/重叠。每读重验身份与非递减性。
- owner.age_bounds(event:OperationalBracket,current:OperationalBracket) -> OperationalAge；owner.within_age(event,current,*,max_age_ns:int=5_000_000_000) -> bool：先查本owner exact receipts、完整pair、after链接、mark-before-current。非法来源/结构抛OperationalTimeError；合法过期False。负max_age、bool/float拒绝。
- owner.start_deadline(*,task_key:str,origin:OperationalBracket,budget_ns:int) -> OperationalDeadline；owner.before_deadline(deadline,current) -> bool。task_key首次固定origin及正整数budget，相同重复返回原对象，改origin/budget拒绝；current直接after原origin，OC1不做通用因果图。
- owner.close() -> None：幂等吊销。owner/token/receipt/deadline浅复制、深复制、pickle不能获授权，可拒绝复制或使用时exact-object检查，不用dataclass equality充当身份。

元数据/读数锁不跨真实operation持有。仅单owner线程，异线程明确拒绝，不建multiworker服务、DB或通用journal。BEGIN/MARK/END原始顺序保留，异常不补完整receipt。

### Task 1：live类型、来源和合法重叠

- [ ] 实施前复核所有输入pins与两新文件仍不存在。活动无关源漂移只由root复核相关语义；根因/接口/范围改变先Astra下一轮，不对过期pins宣称当前版本已审。
- [ ] RED test_pair_and_causal_receipts_required：缺BEGIN/MARK/END、current-before-mark、错token、重复mark/end、负数/bool/float、逆pair均拒绝；初始ImportError/接口不存在为本计划预期RED。
- [ ] RED test_legal_overlap_uses_occurrence_not_end_order：BEGIN c−=100，MARK，current=[150,180]，END c+=200，经实际接口得age=[0,80]ns。缺mark/after或复制receipt拒绝。正常c=[100,110]、n=[120,130]得[10,30]。
- [ ] RED test_future_and_reverse_causality_rejected：私有fixture给c−>n+（+1ns与+1_000_000_001ns）、逆causal link、下降读数；不能clamp成有效0。另一owner同descriptor、crossdomain、copied owner/token/receipt拒绝。
- [ ] 保存限定pytest RED原日志/exit；只在新模块实现最小类型/source/registry及上述接口，production无注入参数。重跑同集合GREEN，原始失败不覆盖。

### Task 2：整数年龄、截止和不刷新

- [ ] RED test_age_exact_five_seconds_and_plus_one_ns：c=[100,200]、n=[5_000_000_099,5_000_000_100]上端5秒通过；n+增加1拒绝；中点<5秒但上端>5秒拒绝。只证明ordinary/condition/receipt共有数学，不声称旧consumer接线完成。
- [ ] RED test_deadline_is_origin_lower_and_equality_rejects：b=[100,200]、budget=5_000_000_000，d=5_000_000_100；n+=d−1通过、等值/+1拒绝。不用b+；2**60大基点仍精确+1ns。budget≤0/bool/float拒绝，无浮点秒转换接口。
- [ ] RED test_original_deadline_never_refreshes：同key同参数原对象不变，换origin/更大预算拒绝；4.9秒检查通过、5.1秒新current拒绝。重观测/晚回包其他event不改原d；close/new owner拒收原deadline。真实retry/restart ledger不在本轮假装完成。
- [ ] GREEN age_lower=max(0,n−−c+)、age_upper=n+−c−，仅因果校验后用max；deadline=b−+budget_ns，接受n+<d；TTL接受age_upper≤max_age。Python整数，不用float/midpoint；身份/因果错误先拒绝。
- [ ] test_diagnostics_cannot_create_precision_or_authority：改变UTC诊断而D不变，D数学不变；resolution或caller claimed ppm/zero accuracy无授权入口。受控加倍/停止读数不产生SI/UTC/native证书；相同计数值可合法，不能假装已识别所有冻结。
- [ ] 同集合GREEN。before_deadline只证明当前检查点，不承诺任意阻塞后的动作或未知完整future H_D。

### Task 3：真实startup CPU能力、报告与独审

- [ ] RED test_startup_binds_real_process_boot_and_time_namespace：私有身份seam覆盖PID相同启动ticks变化、boot、namespace/offset、fork身份、线程漂移、clock异常/缺BOOTTIME/procfs失败，全部fail-closed且不fallback。stat parser用含空格/右括号comm固定field22。
- [ ] GREEN实现实际Linux读取，创建前后与每个事件/current/reader边界重验identity，记录API/运行版本/startup nonce；未做真实restart/suspend/hostpause要显式保留。
- [ ] test_real_linux_startup_factory_cpu_only：真实零参数工厂读一次event/current，核对实际boot/PID-start/namespace与非负age，scope=SOFTWARE_ONLY。不sleep/settime/fork/unshare/suspend，不导入backend。若能力不支持，测试明确拒绝并报告SUPPORT_UNAVAILABLE，不能skip后称真实正分支通过。
- [ ] test_factory_has_no_caller_clock_or_source_flags：public签名及clock/ns/domain/source/PID kwargs拒绝；同值对象/反序列化payload/copied句柄不能绕过reader，无新CLI。
- [ ] CPU命令：PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider --basetemp=/tmp/bigsmall-oc1-tests tests/test_operational_time_v1.py。Task1/2 RED用相应-k子集；完整GREEN一次；环境用require_escalated，不运行全仓/actual测试。
- [ ] owned静态：.venv/bin/python -m ruff check src/cloud_edge_robot_arm/research/operational_time_v1.py tests/test_operational_time_v1.py；同路径ruff format --check；mypy仅新source。新计划外失败先保留并Astra下一轮，不顺手扩大范围。
- [ ] 写astra-repair-execution/OC1/implementation/下report.md/json、source-hashes.json、logs/：输入/输出SHA、RED/GREEN/static命令exit原日志、CPU运行事实、不支持/失败分母、actual分类0。既有UTC/RawV3/consumer只做所需SHA不变检查，不跑actual链；无旧路径导入，无全仓回归。
- [ ] 一次静止独审两源码及报告；重跑唯一新pytest，独立经公开接口构造重叠、5秒+1ns、deadline等值、copied/foreign、namespace漂移。测试数不把作者/审者重复相加。最高PASS_SCOPED_SOFTWARE_OC1，真实startup CPU正分支另列。
- [ ] 交root步骤/阶段总结及显式路径commit/push；root当前push审批仍由root处理，本派单不改Stage/Git或绕过待批push。报告/清单不等于完整raw远端复现包。

## 验收与后续actual前置

本轮最多OC1 SOFTWARE：native_authority=UNAVAILABLE，UTC/SI accuracy=UNVERIFIED，formal_accepted=false；OC2/3/4、R4/5/G1未完成。真实工厂读取host counter仍是CPU能力检查，physics/provider等actual=0，但不能写“没有读取系统时间”。

OC2 actual须另有限定计划/独审，复用R03 single recorder/live handle、实际worker/job/lease/fencing、预注册source/recipe/group库存、RESET→原120 SETTLE→实际acquisition/current，保存同S状态/原始D pair及全分母。startup nonce/字符串不能替代worker授权；读缓存的D不能替换采集时间；首次来源非九组或正式验收。

OC3再闭合全部consumer/lease/publication/事务与dispatch重读及完整future D/S horizon，并取得真实restart/suspend/所用VM hostpause证据。不可恢复旧能力时终止原attempt并保留deadline/失败，不重置预算；该回退不是恢复功能已验收。外部UTC期限/JWT/证书/远端图像保留旧严格路由。

R07的r07.recovery-wall.development.v1私有owner与此计划共享BOOTTIME/suspend及deadline等值拒绝合同，文件/scope/准入独立；本轮不重构或互发handle，不冒认正式OC1—OC4/200教师通过。9独立组、coverage .9、10mm、0.005模拟gap、B0→INITIAL→METHOD→120功效→FINAL及其他门不变。

## 自审与停止条件

已自查spec覆盖、接口一致、整数边界、合法重叠、来源/生命周期、不刷新、production/fixture隔离、API/SI/实证分级和R07无冲突。只创建本目录plan.md/json；未跑项目代码/测试/static/actual，不写源码/旧raw/Stage/Git。新根因、范围扩大、第三个代码文件或计划外实现失败须先Astra下一轮，不能边改边扩大OC1。
