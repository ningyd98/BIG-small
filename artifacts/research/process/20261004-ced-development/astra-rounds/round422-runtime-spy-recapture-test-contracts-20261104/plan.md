# R422 RuntimeSpy 与 recapture 测试前置契约 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:executing-plans`。用户已明确继续修复，沿用当前研发checkout；不另询问执行方式，不新建worktree。

**Goal:** 只修测试替身接口，让22项原失败走到原目标断言，同时证明真实权限与安全拒绝边界未放宽。

**Architecture:** 共享RuntimeSpy明确采用原来的非local持久化预算模式；安全helper仅接受明确completion关键字。生产源码不改。精确RED后，在两共享模块、9个安全helper消费者、4个模式兼容节点与3个新增consumer测试上验证；出现新的根因立即另Astra。

**Tech Stack:** Python/pytest、现有CPU图像fixture、真实Memory/SQLite仓库与owner反例、原生research_safety_shield；无外部模型或实体硬件。

**Spec:** 根AGENTS、R418后续次序、本轮intake/observation.json与target-failures.json、R413原始失败/specs。Planner为实际`gpt-6-astra`。

**状态：PLANNED_NOT_IMPLEMENTED。Astra本轮只读规划，未测试、未改产品/测试/Git。**

## Global Constraints

- HEAD/upstream `f63e271f56a361b43d84be5538f73efe6afce226`，分支`research/20261004-continuation`；main及受保护gitlinks不变。
- 修改限两个测试helper文件，新增一个契约测试文件及本轮执行/证据文档；所有src生产源码必须字节不变。
- 不改原22输入/断言，不添加fake owner权限，不用产品getattr默认值绕过缺失mode，不改RGBD默认、TTL、原速度/安全阈值。
- 不装依赖、不联网/调用模型/硬件、不读旧运行SQL、不改旧raw；沿用既定云/边/端、OpenCV/标记/顶视/控制器方案。
- R419–421已交付的P0定向42PASS保持历史证据，本轮不重跑P0/full4751/full5580。
- 新根因/范围扩张/计划外失败必须先实际Astra再修；最后仅一次fresh Astra审查，不加每helper审查链。

## Review Focus

- `_local_mode=False`只选测试分支而非赋权：fake owner仍被ExecutionPolicy严格type检查拒绝。
- 持久化deadline不能被fresh episode预算刷新：通过真实check_active/recapture消费者验证。
- 非local路径不能调用local时间/owner API：陷阱方法+真实budget_payload/capture顺序验证。
- post安全门不能被签名错误遮挡：真实execute必须把completion=None传到明确回调，并实际调用shield.post_check拒绝超速。
- 共享helper改动影响真实repo和lift/estop/partial等控制：精确覆盖helper消费者及未知mode/伪造/租约撤销反例。

---

## 已证事实与不确定性

R413原22个精确节点保存在 `intake/target-failures.json`，含原longrepr和stage IDs；plan.json也列出完整nodeid。21项在`vision/execution.py:713`访问缺失的`RuntimeSpy._local_mode`失败；1项post超速在`:1372`调用无参recapture lambda时拒绝completion关键字。它们证明测试前置失配，未证明21个产品缺陷或post安全门已验证。

RuntimeSpy使用 `VerificationBudgetState.start`、持久化`verification_state.deadline_at`、普通publication的digest/to_payload；它没有operational handoff/local owner。实际VisualWorkerRuntime只有真实owner的`LOCAL_TEMPORAL_PUBLICATION_V1`才设local true；False继续走原UTC/durable预算。supervision模块直接共享episode，不需要复制Spy或改另一个模式。静态没有发现本轮必须新增的其它Spy成员，因此不预授权猜字段。

`ExecutionPolicy`仍要求`type(worker_runtime) is VisualWorkerRuntime`，False不能认证RuntimeSpy。当前consumer的check_active、budget_payload、plan、supervision cursor/timeout均读取mode；只在测试helper补显式False，禁止生产fallback。

`_safety_gate_run`没有真实worker owner，使用实际research_safety_shield及软件executor/joint-state。execute在该路径传`completion=None`，之后才post_check。替身应支持明确关键字；原负速度-4.0、max_joint_velocity1.5、pre/post断言及executor均不改。修完是否全部原22PASS未知，任何新目标失败另Astra，不按绿倒推权限。

## 精确文件与接口

Modify：

- `tests/test_visual_worker_execution.py`：只在`RuntimeSpy.__init__(self, calls)`增加`self._local_mode = False`，注释说明SOFTWARE_ONLY非local durable orchestration。
- `tests/test_rgbd_closed_loop.py`：只把`_safety_gate_run`的`run.recapture = lambda: run.observation`改为明确`(*, completion=None)`可调用对象，返回同一observation。可使用`lambda *, completion=None: run.observation`；不接受任意`**kwargs/*args`，不改tuple/输入/断言。

Create：`tests/test_visual_worker_test_contracts.py`，三个消费者契约测试。

只读：`test_visual_worker_supervision_execution.py`及实际runtime/owner/模式兼容测试、`vision/execution.py`/`worker_runtime.py`/`evaluation.py`等所有产品代码。若这些文件必须改，已超本轮范围。

### Task 1：新测试和有界RED

- [ ] 复核42个输入pins及当前1310源基线文件；新增本轮`run_stage.py`和`preflight/target-manifest.json`，静态锁定plan.json中的25RED/47GREEN精确node映射。不全量collect。
- [ ] 新建`test_nonlocal_spy_enforces_runtime_deadline_before_capture`：runtime持久化deadline过期，而run.budget另设新预算；调用真实`recapture()`须抛`VERIFICATION_TIMEOUT`，budget来自runtime，reserve/capture/complete均没发生。改前应在缺_local_mode处失败；不改宿主时钟。
- [ ] 新建`test_nonlocal_spy_uses_durable_budget_and_capture_order`：只在本测试实例把remaining_app_seconds设成一旦调用即失败的陷阱，调用真实check_active/budget_payload/recapture；陷阱不触发，payload等于dataclasses.asdict(runtime.verification_state)，claim→capture→source复核→completion顺序成立，observation安装。不能只断言flag等于False。
- [ ] 新建`test_recapture_completion_keyword_reaches_real_postcheck`：用原post helper，外包一层同样只接受completion的转发器记录传值并调用原recapture；实际execute必须记录`[None]`、pre允许、SKILL_RETURN后post实际REJECT，返回False且dispatch恰1。额外未知关键字必须TypeError，不能通过宽泛kwargs消失错误。不替换shield或真实consumer。
- [ ] 原22+新3共25精确RED节点各一次，预期均在两种已证接口错误处call FAIL而setup/teardownPASS；记录STARTED/JUnit/原退出。其它失败或不预期PASS先解释，不冒充RED，不自动重跑。

### Task 2：只补已证测试接口

- [ ] RuntimeSpy补False及范围注释；不增加owner/session/认证来源或local clock facade，不在产品使用getattr默认值。
- [ ] recapture补completion关键字接口；原overspeed输入、真实shield、executor和原期待保持字节语义。
- [ ] 检查supervision仍共享同一episode，未复制/改造替身；新测试之外所有原测试断言保持。确认src全部字节不变。

### Task 3：目标断言、权限反例和交付

- [ ] 各一次执行47个精确GREEN节点：execution模块16、supervision模块15、RGBD安全helper消费者9、模式兼容4、新contract3。原22包含在内，不另重复运行。
- [ ] 两共享模块包含真实repository memory/sqlite6case；模式兼容4case覆盖真实owner正常、伪造、UTC租约撤销、未知mode拒绝。fake-owner两个原控制和STOP/CONTINUE未知action反例必须保持拒绝，不把False解释为新权限。
- [ ] 安全helper9节点包含pre/post、部分动作计数、estop、模型等待上限，以及lift正常/遮挡/未抬起/失接触；只选择实际helper消费者，不扩大整个RGBD模块28项。
- [ ] 逐原目标记录“原错误消失、目标原断言到达、最终三阶段结果”。若新缺成员/target assertion/授权错误出现，保留失败、停止相关组并下一实际Astra；绝不改旧期待、追加假权限或用skip换绿。
- [ ] 做明确修改文件diff-check、新contract文件静态检查和source范围核对；既有全项目格式/中文等问题不在本轮批量处理。
- [ ] 一次fresh最终实际Astra审查diff、覆盖、原/新失败、sources和owned cleanup。按精确清单提交推送并核对local/upstream/exactremote SHA，不force、不目录宽选。

## 验证范围与时间策略

原spec215/279/283分别28/16/15节点，原模块cap均1800秒，原阶段实耗约2.128/20.175/36.684秒；这些不是新节点耗时保证。新计划每stage一个精确node，pure cap120秒、实际repo/owner case cap600秒、owned cleanup30秒，零自动重试。

最多25RED（全部pure）+47GREEN（37pure、10native）。这里native指真实仓库/worker owner软件路径，不是实体机器人。plan.json `validation.jobs`固定全部72个唯一阶段ID、node、cap及期望；GREEN去重覆盖原22。出现新问题可停未启动节点并标NOT_RUN，不为凑47而继续相同坏前置。

GREEN组合：

| 组 | case数 | 作用 |
| --- | ---: | --- |
| test_visual_worker_execution原模块 | 16 | 共享Spy及真实repo/假owner拒绝 |
| test_visual_worker_supervision_execution原模块 | 15 | supervision共享helper及真实owner/cancel |
| RGBD安全helper精确消费者 | 9 | pre/post/partial/estop/wait/lift |
| test_legacy_reference_mode_compatibility | 4 | owner、伪造、lease撤销、未知mode |
| 新consumer contract | 3 | deadline、非local调用、completion→postcheck |

## 执行runner与实际前置

本轮允许新建`run_stage.py`，接口只收一个plan-listed stage ID；从manifest取精确node/kind/cap，不接受任意shell、testpath或argv。冻结R419 runner不改。导入原R413 `bounded_stage.py`，仅绑定module.ROUND到该stage，继续原有owned回收/sourcecheck。

runner基线采用本轮`preflight/runtime-source-baseline.json`的1310文件。仅两个指定旧测试hash可合法变化，再追加新contract测试hash；所有src和其它基线文件不变，每stage写fresh实际pins并核对结束后来源。

显式使用项目绝对`.venv/bin/python -m pytest`，保留R413 event/prerequisite plugins、noautoload/no-cache，禁止barepytest。按spec中首个实际node边界提取argv前缀，不硬编码旧Phase12 node。将原输出/env/resource路径全部映射到本轮；移除共享`SIMULATION_RUNTIME_DB`，保持`REAL_MOTION_DISPATCH_ENABLED=false`。

`validation/red-001..025`、`validation/green-001..047`排他新建；资源父目录先准备，basetemp固定新`/tmp/bigsmall-r422-{stage-id}`，存在即记录管理冲突并换新唯一后缀，不删除/复用旧目录。每次保存精确命令、source、STARTED、setup/call/teardown、JUnit、真实exit及owned身份。超时只按PID+start_ticks+scope回收owned树30秒，不全局kill、不补造JUnit。

不新建worktree、不装依赖、不联网、无真实模型/相机/机器人；真实repo写新owned tmp DB，不查询旧DB。缺环境插件是未满足前置，不能换provider/缩场景/调TTL。按序运行，相关组首个新根因就停；独立未受影响的组可按既定计划继续并单列分母。

## 验收与停止边界

只有原22确实到达原断言且通过，才称22前置恢复；仅不再报AttributeError/TypeError不够。若出现后续失败，则报告“前置已恢复、目标行为出现新失败”并另Astra，不能宣布本轮全通过。完整验收需47GREEN唯一节点三阶段PASS、无新增skip/xfail/incomplete/重复STARTED，source和cleanup合格。

fake owner仍拒绝、未知action不获授权、真实默认mode与UTC撤销不松动；post确实由shield拒绝原负超速。生产源码全不变，软件结果不升级成实体/正式研究验收。任何产品修改需求、未证Spy新成员、guard异常、超时、资源/来源/采集异常都超出当前预期RED，先保留原件交下一Astra。

## 精确Git交付边界

代码仅2旧测试+1新contract。本轮固定文档与逐stage可选文件的完整**精确路径数组**在plan.json `delivery_boundary`：包括plan/intake、baseline/target-manifest、runner、step/phase报告、validation-summary/final-integrity、单次review及selected-manifest；各stage仅spec、pins、source-before、result/raw-exit、pytest-events、JUnit。不存在/未运行文件不得伪造或暂存占位；如唯一后缀改变，先在manifest记录确切路径再选择。

全stdout/stderr、进程/资源详单、DB/WAL/SHM、basetemp/fixture复制、凭据/模型/SDK/cache及Git事务回执默认local-only；必要失败摘要在报告脱敏引用。明确git add文件清单、normal commit/push、local/upstream/remote SHA相等；main/gitlinks不变。清单不冒充完整远端复现包。

## 输入pins

| 路径 | bytes | SHA256 |
| --- | ---: | --- |
| `AGENTS.md` | 1774 | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round418-astra-current-issues-priorities-20261104/plan.md` | 24864 | `2cbd27f4fd9494a262d880257366f971109d82a7339f5bbe55504faec8b41606` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round418-astra-current-issues-priorities-20261104/plan.json` | 35801 | `a6b4994721984d52866b668d54c60f160109583eea8153855498dde4453739b8` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round419-phase11-receipt-truthfulness-20261104/phase-summary.md` | 2608 | `ba84d97afc7613d282b581d9c156fae72a58467a7c16092bb4def6e8edc91fbc` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round419-phase11-receipt-truthfulness-20261104/delivery/delivery-complete.json` | 1823 | `7dcc571d80b1686f204891f6966db2ca0e673725d5ac1cfbe4ec621f6c942553` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/reports/failures.json` | 35383 | `07ce00cf820759d36129171a8d7428d2edd600dcfef1723c0f9c2ef42d6501da` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round422-runtime-spy-recapture-test-contracts-20261104/intake/target-failures.json` | 18637 | `c9e4cedede5108a8297a9f56dca12732ee218cf22877eb78cc229919cd94e53b` |
| `tests/test_visual_worker_execution.py` | 13280 | `45ae3e30cd2b338227512e138429c5636fc46552f5f484ea8226f8c4375f5c5e` |
| `tests/test_visual_worker_supervision_execution.py` | 14808 | `aaaa535392f728227e4ceb900cd57c5d7f004c36f82da7d159357b09f76d5432` |
| `tests/test_rgbd_closed_loop.py` | 27689 | `10aa14e399ecfdcaa1f54f6b09f811fe90b5ab32309c0cd9bb88291ffecda77f` |
| `tests/test_legacy_reference_mode_compatibility.py` | 3938 | `36025b4d870e307f5a6cbe3588fcd207c893a05aa0ce82ff622d3da2554b6e01` |
| `tests/test_visual_worker_runtime.py` | 21851 | `e2c0e9db9aec5426997bd2c615f1838c7625452446e8400319cc266269987de7` |
| `tests/test_visual_worker_supervision_runtime.py` | 18113 | `92badeeccd889b629a161081fccf19c5377505fd52a758097289cdbec5dc612e` |
| `tests/test_visual_worker_owner.py` | 18025 | `2c3d8a142239ef4799c60696f179201fcc70bbff3c46f3fcd92434e4248b3685` |
| `src/cloud_edge_robot_arm/vision/execution.py` | 104819 | `69f2c1b7dabc0106697eb656bff67da331d4b5386433ae62b9f4f9ff094189f0` |
| `src/cloud_edge_robot_arm/vision/evaluation.py` | 13863 | `7f9e255b9d35dbec1226c60ea81f2c0b593225a4930c976bd8f17aa38e9b64f4` |
| `src/cloud_edge_robot_arm/vision/worker_runtime.py` | 155168 | `7c1ad5a70c65b5b20be6552dc04fbfbb4ce4aa5ecb39bf965ceb23dab98ccb3c` |
| `pyproject.toml` | 2458 | `b2bf5c4042d568eaf9def415ae7b2f08f0fa541a01f970b7e68e6d950035bb6c` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/implementation/py-module-215/pytest-events.jsonl` | 30592 | `9ab59453c68e83a5a631c9fcda37afd84fdcf58fa021cbcc2520ea4b094f3c8a` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/implementation/py-module-215/junit.xml` | 4592 | `d15eaf74d4ae5c186916059fe340b6fa500bf9d6f1383547292c2bc1c63b8a46` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/implementation/py-module-215/stdout.log` | 1087 | `ceaa205a8b1a5f84d60bc7007d1ae0612d4c64f367d25bf20c9ce00881cc4ee8` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/implementation/py-module-215/stderr.log` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/implementation/py-module-215/result.json` | 401 | `6906915469b0d78b410779cb0c96398f17abb6c97cdf94d4907da124517455ae` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/implementation/py-module-279/pytest-events.jsonl` | 23549 | `9a43c5a498379536db036d1dcee8aa8d359785a95c6d2818698be27103a3deb1` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/implementation/py-module-279/junit.xml` | 8655 | `7cec1243539ce92d8a7405052cab47631ff784445d25273a1c9576dc3ed48d19` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/implementation/py-module-279/stdout.log` | 7408 | `c70dab30ae1cb5b9d0e6829e3675ebbef659eb3b170390e1633f810dc3f25ae3` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/implementation/py-module-279/stderr.log` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/implementation/py-module-279/result.json` | 400 | `2bfae5d52fc13e18d83bb93945fafb8a1b14a997e39f4e09a9c9ee2eb225207a` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/implementation/py-module-283/pytest-events.jsonl` | 24490 | `d9940472b20948d60bdd867128aa0b31b79fdca9f413b731a2c70f6efee946f5` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/implementation/py-module-283/junit.xml` | 9798 | `6c3a00f7232110a664f9d371ca77692c6d073e7f9026b74230d861eb807c2338` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/implementation/py-module-283/stdout.log` | 8684 | `7d70ad8bc3042a3b90236a4d65bf7e350a7721b2d5d397b6594c7c2a96e9da84` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/implementation/py-module-283/stderr.log` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/implementation/py-module-283/result.json` | 400 | `ce8dcc0dfe03514034e0eefbff5528037437a6a8f39f9b05535d444843287b2d` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/bounded_stage.py` | 9291 | `d1565de800982ccdc9223b7636a93de0bd99f8aae56131d74ccb8bc320fb085c` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round419-phase11-receipt-truthfulness-20261104/run_stage.py` | 3173 | `fd82af588f9341da6ef93a6a91bbca3dce11de1ea22b01e70244cd116d0aa69b` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round419-phase11-receipt-truthfulness-20261104/validation/final-new-module/preflight/runtime-source-pins.json` | 240496 | `9149662ef2079f5d2a04a9e4c55de6f287624cc75aae4110a704b98aaa4f529c` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round422-runtime-spy-recapture-test-contracts-20261104/intake/observation.json` | 11607 | `9ef4c94b468751f9b1678ec3bd5e7337dce7c8caa203e3adf4506f4a41e3f65d` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round422-runtime-spy-recapture-test-contracts-20261104/preflight/runtime-source-baseline.json` | 240833 | `f9906bcace0b4c893cbac236db49c682ea4c09bf2cd8d0e2c43e66cc54032d7f` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/specs/py-module-215.json` | 11724 | `abde54330bf73e5b59c241190bdc5077fb8e7845da617ef2e5ee061207e85dad` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/specs/py-module-279.json` | 9784 | `f4994b56efabd137cc2c2441fd5822089fa28d579a7ba953bb19c2d5d93ff022` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round413-full-long-validation-20261103/specs/py-module-283.json` | 10002 | `5f473e6896ed329843ef4da88e9bc095856dc07d5d6dc41052e132f28706857c` |

## Self-review

- [x] 读取并分类全部22原longrepr，42个输入bytes/SHA核对一致；1310源匹配采用执行者冻结前置。
- [x] False来自原durable fixture语义，非试绿猜值；仅补两helper接口，产品权限不变。
- [x] 新测试真实经过consumer/shield，含过期/禁止local调用/明确completion，不只断常量。
- [x] 原22为47GREEN子集；25RED与47GREEN无阶段内重复，native10/pure37、caps和停止线明确。
- [x] 单次最终审查和精确Git路径边界；本轮仅写两计划文件，未执行测试/SQL/Git。

### 补充断言保护输入（规划收尾前已冻结）

`intake/target-assertions.json`记录原22节点对应19个函数的完整AST哈希；实施结束复核这些业务函数逻辑不变。该派生文件列入本轮精确文档交付，不扩大修复范围。

| 输入 | bytes | SHA256 |
|---|---:|---|
| `artifacts/research/process/20261004-ced-development/astra-rounds/round422-runtime-spy-recapture-test-contracts-20261104/intake/target-assertions.json` | 13757 | `21ad49f099bcce8df6cfce6d91329e3d76a88985d3f9d77cb716ce92658649db` |
