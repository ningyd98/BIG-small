# OC2 single-application operational source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task under the existing root/implementer/independent-review arrangement. This Astra dispatch writes only this plan and plan.json; no implementation or actual run.

**Goal:** 建立 simulation.operational-time.v1 的真实单应用来源链：private application → SQLite job/lease/fencing → source/recipe/group preregistration → RESET → 120 SETTLE → real capture → same-domain current D → immutable originals/public reader。最多三项任务，验收仅 OC2 来源前缀。

**Architecture:** 四个新 code paths（schema、recorder、application/runner/publication/reader、CLI），一份新 policy、三份 bounded CPU tests；现有 worker 只加小型 private early branch。复用 R03 的真实 repository/lease/唯一 observer 与 RawV3 原件保存机制，另建 BOOTTIME event ledger，不改变旧 MONOTONIC+UTC pair。

**Tech Stack:** 现有 Python >=3.12、stdlib、pytest、SQLite repository、MuJoCo backend/capture/executor interfaces、OC1 Linux BOOTTIME owner，无新依赖。

**Spec:** docs/superpowers/plans/2026-10-05-operational-clock-repair-supplement.md 的 OC2；astra-repair-planning/clock-dependency-review.md；根 AGENTS.md。精确输入 SHA256/bytes 见相邻 plan.json。模型角色来自 root 明确指定 gpt-6-astra 的派单，没有独立探测运行时模型标识。用户已授权规划和后续研发，不新增设计确认流程。

## Global Constraints

- OC1 零参数 open_operational_clock() 仅计时能力；其 domain.worker_authority/lease_authority/native_authority 不升级。OC2 必须另以 private registry、实际 worker/repository/job/唯一 open attempt、原 lease/fencing、同 backend/capture/executor exact handles 建立来源；caller flags、PID strings、groupnames、descriptor/hash 相等不授权。
- D 是真实 BOOTTIME 整数 ns，1 operational second=1_000_000_000 ns。S 是同 backend/episode 的 physics step/sim time。新账本保存真实 BEGIN/MARK/END、S 状态与 event/current links；旧 MONOTONIC/UTC pair 保留原名/字段/bytes/判定，不转写成 BOOTTIME 或 UTC 零误差。
- 所有 operation/frame/失败 allocation、缺失 pair、observer/lease/persistence/publication failure 进入全分母。异常不得补 MARK/END、删除 prefix 或挑成功样本。cached read 保留原 source acquisition identity 与原采集 bracket，读取时刻不能刷新图像年龄。
- UTC/SI accuracy=null/UNVERIFIED；source positive 不是 native/adopted RawV3、consumer closure、九组/G1、未来 H_D、geometry/motion界、正式研究或机器人安全。一个 source-session group inventory 不等于独立 calibration group，独立支持组计数仍0，不造9组。
- restart/suspend/VM hostpause=NOT_TESTED_OC3_GATE；unsupported/UNKNOWN 不等于0误差。OC2 不迁移全部 lease/heartbeat/recovery/consumer 到D，原 UTC lease guard 保留，lease_clock_migration=NOT_DONE_OC3；math checkpoint 不承诺阻塞后的 dispatch。
- R03 原响应缺 draft08 NONC 的严格拒绝及 UTC/RawV3 原件完整保留。不重跑旧 actual、不网络、不换 key/draft/nonce 守卫、不选新模型。沿用云端方案、端侧 OpenCV、可见姿态标记/顶视相机/控制器；边缘型号后置。
- no planner/model/provider/network/action request；RESET/SETTLE 自带 cached CAPTURE 和 renderer 必须真实计数，不因 explicit capture=0 就称 camera=0。CPU 替身、实际来源和正式研究分别记账。完整 raw/DB、凭据、权重和 SDK 保持现有交付边界，manifest 不冒充完整远端包。

## 问题、原始失败与待验证假设

1. OC1 final source SHA b1fa45a96837072d7bcf8cec57d1a7ae01dceeabec0131503b6aee5ab27dd90b；tests SHA ff226e9a616462c67d74d29931f8f9a7d21548f4f13f93ced64901b263229c0f。root final full60 一次：60 passed/0 failed/0 skipped，exit0，0.11s。独审 probe 19 scenarios 一次，不能与60相加。
2. 最终 source-review.md/json 已静止，PASS_SCOPED_SOFTWARE_OC1、open P1/P2=0，已读取并验证 root 给定 SHA。70-file protection 仅41 implementation+29 static-fix artifacts，非全仓；new real CPU receipt e5d702452ce7536df88159695131fbc9622f9998025ae9f0deef3593c11bbba2/1721 bytes 与原文件精确复制。旧 implementation static RED 按历史保留，不覆盖后续修复与最终 PASS。
3. R03 actual-prefix/wire-replay.json：原 returncode1，stderr “response nonce differs from original request”；原A一发一收，缺 frozen draft08 NONC，B SKIPPED_A_UNAVAILABLE，签名验证未进入。旧 prefix 的488 pairs、120 physics、2 cached frames、486 operation rows 来源完整，但 current/native UTC UNAVAILABLE。这里只读已有证据，没有重放或新 actual。
4. 本轮缺口是 OC1 counter 未绑定实际应用/capture；不是已发现其数学错误。R03 _clock_pair 和 RESET callback 用 MONOTONIC，不能改名复用为D。实际 backend 已有 sole observer BEGIN/END，可供新 recorder 在真实操作外围调用 OC1 owner。
5. 假设：不改 backend/teacher/旧 public source 行为，便可用 exact runtime handles + preregistration 形成新的 source D/S enclosure，保存所有 cached/source/failed denominators，再用公开 reader 复算。若需修改 backend 事件语义、teacher 或 consumer，超出本轮，先再次 Astra。

## 硬门与源依赖

- Gate A 已满足：上述 OC1 final independent PASS 和原始 full60/70protected/newreceipt 完整冻结。实施前仍复核 exact pins。未测真实 suspend/restart/hostpause，不能借 Gate A 跳过后续 gate。
- Gate B 尚未满足：root 消息确认 marker-v4-full 尚 freeze前、actual0。其 actual进程退出、原件冻结、公开 readout 成功或失败终态、renderer独占释放后，才允许修改 shared worker/teacher/public source。prepare_full.py::necessary_sources/source_preflight 校验完整 transitive public-import closure，依赖这些共享 bytes。CPU preflight/独审不代替 actual/readout终态。
- Gate B 前可准备不改变 shared source 的新文件；禁止导入执行新 worker branch 或改任何现有共享 source。本轮最终也不授权 teacher/backend 修改。Gate B 只要求本次 actual+readout终态，不要求 marker observability 研究通过；它自己的失败必须另按 Astra处理，不由OC2改原件。
- 实施前复核 plan.json 全部 SHA/bytes、新路径仍不存在；新增 marker gate终态文件在新 preflight 中登记 SHA/bytes，不回写本计划。source/content漂移、接口改变、新根因/范围扩大/计划外失败暂停相关修复再 Astra，不能自动更新 pins 取绿。
- actual 另需：Task1–2 bounded CPU/static GREEN，quiet source freeze/archive，独立 scoped SOFTWARE PASS，fresh exclusive output且无本recipe实际尝试，Linux BOOTTIME/proc身份能力、MuJoCo/camera资源、同线程与全队renderer串行。仅root执行一次 actual；规划者/implementer不执行。

## 文件与接口

**四个新 code paths：**

1. src/cloud_edge_robot_arm/research/operational_prefix_schema_v1.py：exact-key policy与prereg/event/prefix payload校验，纯形状/整数数学，无runtime初始化。
2. src/cloud_edge_robot_arm/research/operational_capture_v1.py：OperationalPrefixRecorderV1 继承 VisualResetClockRecorderV2 的sole-observer/原件tee/freeze/export，另记D ledger；不重写旧 _clock_pair。新增 from_application 工厂使用新app issuer，不冒用旧R03 issuer。
3. src/cloud_edge_robot_arm/research/operational_prefix_v1.py：private registry、真实SQLite job、worker runner、preregistration、guarded publication、public reader；backend/model依赖延迟加载。
4. scripts/run_operational_prefix_v1.py：默认 INPUTS_ONLY/NOT_RUN、显式 --execute-once 才实际一次；无fallback/retry。

**新增policy/tests：** configs/research/operational_prefix_v1.json；tests/test_operational_prefix_v1.py、tests/test_operational_capture_v1.py、tests/test_operational_prefix_cli_v1.py。不得改旧测试断言/bytes。policy固定 schema_version=simulation.operational-prefix.startup.v1、clock_schema=simulation.operational-time.v1、source_scope=EXCLUDED_SOURCE_ONLY_PREFIX、scenario=S01_NORMAL_STATIC、seed=0、settle_steps=120、explicit_capture_count=1、ordinary_max_age_ns=5_000_000_000、task_timeout_s=60、max_attempts=1、recipe_id=oc2-reset120-capture-v1；不接受endpoint/key/ppm/accuracy/worker/native授权或caller group inventory。

**唯一允许修改的现有源码：** Gate A+B 后 src/cloud_edge_robot_arm/simulation_runtime/worker.py 的 _run_visual_closed_loop 增加小型 getattr(self, "_operational_prefix_application", None) exact-type/private registry early branch。旧 _native_clock_prefix_application 分支不改；两分支同时设置则拒绝。无需改 __init__、deadline/lease、teacher/backend/原publication。超出小分支先Astra。

**冻结签名：**

- validate_operational_prefix_inputs_v1(config_path: Path) -> dict[str, Any]：纯读policy/source/asset hash+bytes；no mkdir/output/DB/job/lease/app/clock-owner/backend/model/network。
- OperationalPrefixApplicationV1.from_startup(config_path: Path, *, output: Path) -> OperationalPrefixApplicationV1；prepare_once() -> Any；execute_once() -> dict[str, Any]；check_worker(worker: SimulationWorker, job: Any, *, start_monotonic: float) -> None；check_active() -> dict[str, Any]；check_recorder(recorder: OperationalPrefixRecorderV1) -> dict[str, Any]；catalog_entry() -> dict[str, Any]。工厂无backend/clock/repo/PID/source flags注入参数。
- run_operational_prefix_v1(application: OperationalPrefixApplicationV1, worker: SimulationWorker, job: Any, *, start_monotonic: float) -> tuple[dict[str, Any], list[Any], list[Any]]。start_monotonic 只核对旧worker原origin，不转D、不冒充BOOTTIME起点。
- OperationalPrefixRecorderV1.from_application(application: OperationalPrefixApplicationV1, backend: Any, capture: Any, executor: Any, *, directory: Path) -> OperationalPrefixRecorderV1：新app private runner签发一次，核对私有expected exact handles。继承capture()；新增 freeze_operational_prefix() -> dict[str, Any] 与 export_operational_prefix() -> dict[str, Any]，先保存全分母再判定。
- verify_operational_prefix_originals_v1(root: Path, catalog: dict[str, Any]) -> dict[str, Any]：历史原件integrity/prereg/source/recipe/event/frame/S/D joins和整数数学；不读现在D、不执行app、不重建live handles、不把DB快照当当前lease。只有runner在真实publication guard内可出live来源判定。

## Review Focus

1. exact-looking/copy app、foreign repo/capture/executor、lease取消/替换：Task1/2真实接口拒绝，不给caller now绕过UTC lease guard。
2. RESET BEGIN old/no episode → END new episode及nested cached CAPTURE：Task2保留转换事实，post-reset S一致，不改写BEGIN。
3. cached read、失败allocation、observer吞异常、缺END：Task2全分母对账，年龄从原capture计算，不补有效pair。
4. prereg/运行/发布间source/config/asset变化或catalog写失败：Task1/2拒绝并保留prefix，没有live catalog。
5. default CLI隐性DB/output/backend/model副作用，reader路径escape/伪造receipt/离线变live：Task1/3真实main/import/reader测试，无自动重试。

### Task 1：private startup、schema、零副作用preflight

**Files:** 新schema/app/policy、prefix tests、CLI最小默认路径及CLI tests。只准备新文件，不改shared worker。
**Interfaces:** 消费OC1 public API与现有real SQLite/read_visual_worker_lease；产出startup-owned application和immutable prereg。CPU替换只改私有raw source/backend construction，不mock最终verdict。

- [ ] 核对所有pins和新路径不存在，登记Gate A与Gate B事实；实施日志写新 astra-repair-execution/OC2/implementation/，保留旧失败。
- [ ] RED test_default_cli_is_inputs_only_without_effects：真实main输出INPUTS_ONLY/NOT_RUN；fresh output不存在；app/clock factory/SQLite/backend/model/network调用均0。malformed/extra key/noninteger settle或TTL/symlink/missing inputs先拒绝。仅缺module/interface为预期RED，完整原command/exit/stdout/stderr保存。
- [ ] RED test_startup_exact_registry_and_once_only、test_worker_authority_is_not_counter_descriptor：真实临时SQLite job/唯一lease/open attempt；未RUNNING不签source；copied/reconstructed/foreign app/worker/repo/counter descriptor拒绝；factory额外kwargs拒绝；prepare/execute二次拒绝；PID/group strings无授权效果。
- [ ] 实现exact policy/preflight/private registry，live app不可copy/serialize。先校验输入，再验证fresh exclusive no-symlink output；仅显式factory创建app/DB。source inventory包括四新paths、OC1、worker/repo/state/model、backend/camera/capture/executor/RawV3/asset和recipe的SHA/bytes，不只pin入口；preflight不得通过初始化backend生成inventory。
- [ ] check_active沿用真实job/唯一open attempt/lease/fencing join，每次调用read_visual_worker_lease不传caller now，核对frozen assignment/max_attempts=1。D owner在实际execution线程由zero-arg工厂建立；worker MONOTONIC origin只作原来源比对，lease clock migration保持NOT_DONE_OC3。
- [ ] 在任何RESET/step/CAPTURE前 create-exclusive 写入并读回核对 source inventory、recipe/scene/camera policy、真实app/job/lease/attempt、D descriptor与单source-session group inventory。group independence=UNESTABLISHED、support_group_count=0。caller preregistered=True不替代原件；写失败不触发source event，已有输出不续跑/覆盖。
- [ ] 同RED集合GREEN，真实renderer/physics/network/model为0。报告临时SQLite CPU软件事实与实际采集0；保留保护pins。

### Task 2：真实接口D/S recorder、worker小分支、guarded publication

**Files:** 新capture/app与capture/prefix tests；仅Gate A+B满足后改worker小分支。
**Interfaces:** 消费Task1 private app/prereg+OC1 owner；产出legacy unbound originals与独立新D/S ledger/source-only receipt，不建consumer graph。

- [ ] RED test_real_interfaces_reset120_capture_current_chain_cpu：fake backend实现真实observe_operation_boundaries/BEGIN-END/ledger/capture/executor interfaces，真实app→SQLite job/lease→worker路径执行1 RESET、120 SETTLE、1 explicit capture。不能直接fake PASS；assert prereg先于首事件、sole observer=1、planner/provider/network=0、post-reset S/episode与frame来源相符。
- [ ] RED test_counter_source_is_not_old_monotonic_pair：OC1私有CPU seam给原始BOOTTIME读数；旧MONOTONIC/UTC tee另值。D ledger必须来自OC1 exact live receipt，旧tuple/字段不变、跨域/同descriptor不可替代。
- [ ] RED test_operation_brackets_capture_identity_and_denominator：真实operation BEGIN（操作开始前）调用owner.begin_event；trusted backend成功END在核对result/error及operation identity后mark_event一次再end_event。保留BEGIN/END ns、MARK因果序、operation ID/kind、S_BEGIN/S_END、step和owner/session。此bracket包围实际operation/acquisition，不宣称精确曝光瞬间。error END、缺END/observer失败只归档，不签成功receipt；RESET BEGIN原旧/空episode保存，END新episode，嵌套CAPTURE独立token。
- [ ] 实现新recorder sole _on_boundary tee：先分配D attempt分母，再保留super原逻辑，按operation ID关联token；不加第二observer，callback不调用backend/capture/network、不长持DB锁。callback异常保留；backend会吞observer exception，runner必须检查其failure ledger并fail-closed。
- [ ] 每个实际CAPTURE BEGIN有allocation与原acquisition ID。继承.capture()调用一次真正capture；若产新frame有新source bracket，若API仅回缓存则引用既有source_acquisition_id与原bracket，不按cache读取刷新。current=owner.read_current(after=原capture token)，在MARK后同owner/domain，保存n−/n+、S检查点和age=[max(0,n−−c+),n+−c−]。TTL用上端<=5_000_000_000；过期如实保存，不缩括号/挑帧。
- [ ] RED test_lease_source_or_capture_swap_fails_before_publication、test_partial_prefix_keeps_all_failures：checkpoint替换app/repo/backend/capture/executor/job/attempt/fencing/source/config/asset或lease过期/cancel，缺BEGIN/MARK/END、重复/逆序、foreign token、cached identity缺失、frame export/catalog异常。assert无source positive/live catalog、no retry；全attempt/operation/frame/pair/error原件可读。再跑同cases GREEN。
- [ ] 固定runner prereg→backend init→single borrowed capture/executor→single recorder→RESET→SETTLE120→capture一次→原capture current D→freeze/export/publish；各大操作前后与签发复验exact handles。RESET/SETTLE内部command/control/cached renderer全保存，action request=0。recorder前startup失败也写原件，partial不删除。
- [ ] publication在原repository.publication_guard内复验live lease/fencing/source/config/handles、原件hash与public reader结果，先写receipt/catalog成功才暴露private live catalog。write失败不发布；finally导出不能掩盖原异常或丢prefix。
- [ ] owned CPU完整GREEN一次、限定static与worker必要旧R03窄回归，unique tests与重复观察分开。freeze source archive/hash后停止写入，交独审；计划外failure保留并再次Astra。

### Task 3：public reader/CLI、独审与root唯一actual

**Files:** 同四新paths/tests；新报告 astra-repair-execution/OC2/{implementation,independent-review,actual-prefix}/；唯一新实际输出 OC2/prefix-1/。旧raw/DB不改。
**Interfaces:** 消费Task2冻结原件，产出历史verification与独审实际来源证据，不给新live consumer权限。

- [ ] RED test_reader_recomputes_and_never_mints_authority：从原JSON/frame SHA+bytes重算prereg/source/recipe/session/RESET120/event/frame完整joins及age，不信receipt true/PASS或groupname；tamper/missing/extra allocation/缺pair/path escape/symlink/foreign schema拒绝。不得执行app/读当前D/恢复live。输出original_integrity、source_prefix_complete、recorded_source_current_age及全部限定字段。
- [ ] RED execute-once CLI tests：仅一次from_startup+execute_once；strict source_prefix_complete is True才退出0，其他退出1；保留完整receipt/partial，no retry。默认仍INPUTS_ONLY/no effect。GREEN后quiet freeze、独立reviewer通过真实接口做bounded CPU；作者自报不替代独审。
- [ ] root核对Gate A+B、资源、无本recipe已有actual、fresh output、OC2独审PASS后，先一次默认preflight并确认prefix-1不存在；再唯一一次显式actual命令：
  PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 MUJOCO_GL=egl .venv/bin/python scripts/run_operational_prefix_v1.py --config configs/research/operational_prefix_v1.json --output artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/prefix-1 --execute-once
  使用既有资源包装记录整个进程wall/peakRSS、runtime/physics/renderer/cached+explicit frames/model/network分项。本规划不执行此命令；crash/incomplete不重跑，保留证据再次Astra。
- [ ] actual完全退出和原件冻结后，独立public reader仅读本次新原件一次，不重复CPU/renderer/旧actual。核对before/after SHA/bytes、source inventory与quiet审查一致、prereg先于事件、RESET1/SETTLE120/explicit capture1、全cached/failed denominator、同D/S关联及5秒结果。DB本地保留；历史快照不冒充仍活的lease。
- [ ] 来源/因果/原件完整才登记PASS_SCOPED_OPERATIONAL_SOURCE_PREFIX；TTL是否过期与source complete分开报告，不借complete宣称consumer准入。formal_accepted=false；native/UTC/current_external_UTC/consumer_feasibility UNAVAILABLE；calibration_groups=0；H_D/geometry/motion UNKNOWN；restart/suspend/hostpause NOT_TESTED_OC3_GATE。
- [ ] 新步骤报告及阶段总结分开发软件、actual、public readout、正式研究，汇集原RED/GREEN/command/hash/全分母。root按明确路径提交推送研发分支并核对local/upstream/remote SHA；完整raw/DB不自动入Git。本dispatch不做Git或写root总结。

## 后续验证命令

- Task RED：PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider --basetemp=/tmp/bigsmall-oc2-red tests/test_operational_prefix_v1.py tests/test_operational_capture_v1.py tests/test_operational_prefix_cli_v1.py -k '<本项命名测试>'。缺新module/interface是预期RED；环境/静态/计划外行为失败先Astra，不顺手修。
- owned完整GREEN：同命令去掉-k，fresh basetemp=/tmp/bigsmall-oc2-green，一次。OC1沿用quiet独审，不重复已完成full60；需改OC1另Astra。
- worker必要窄回归仅 tests/test_native_clock_prefix_worker_v2.py、test_native_clock_publication_v2.py、test_native_reset_capture_v2.py、test_native_clock_prefix_cli_v2.py，CPU fixture无network/renderer，不跑全仓。
- Ruff check/format --check针对四新paths+三tests+实际修改worker；mypy新三个research modules、CLI及必要worker import scope，用项目配置/MYPYPATH=src，不新增ignore消除错误。
- root actual/public reader仅Task3门满足后各一次。本计划期间tests=0、实际DB/backend/model/network/physics/renderer/camera/decoder/provider/hardware=0、Git=0。

## 规划执行记录与自检

本轮只读/计划写入均require_escalated，root已知默认bwrap坏；仅新增plan.md与plan.json，没有修改源码、运行测试、真实实验或Git操作。规划工具原始失败单独保存在plan.json的planning_tool_errors；没有产品counterexample，不新增产品修复轮。

自检：三任务覆盖supplement OC2；四新codepaths+smallworkerbranch；authority/counter分离、zero-effect默认、prereg/event/S/cached/全分母、publication/reader/唯一actual有明确反例；OC1 PASS真实冻结，marker终态条件未越过。若实际接口不能满足来源合同，不缩raw分母/伪造handle/放宽native-UTC-geometry门，先再次Astra。
