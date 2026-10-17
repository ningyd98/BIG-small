# R101：P5 年龄闭边界与硬期限开边界

本轮实际规划者 gpt-6-astra `/root/astra_oc2_residual`；只规划，恢复 Sol 的 R100/P5 软件任务需 ROOT 激活。未实施、导入产品、运行测试、actual、网络或 Git。

## 原证据与根因

R100 唯一 RED 为27个预期 missingmodule FAIL/0error，产品八源未改，新模块仍缺席；不是执行后发现的 OC1 产品失败。`implementation/boundary-conflict.json` 保存未运行的代数反例：event=[0,0]，paired current=[5e9,5e9]，kind budget5e9，task/verif120e9，parents空。OC1 within_age=True，但 R100 把 kind TTL 转成 deadline5e9，再要求 current.upper<deadline，必为False。

根因是计划混淆“年龄上界闭区间”和“原硬期限开区间”。OC1现有 within_age第383行<=与before_deadline第424行<无需修改；原master/P5要求5秒允许且硬期限等值拒绝。R101明确替换R100的统一kinddeadline公式，不通过+1ns、放宽硬期限、丢弃kind预算、刷新原点或全拒绝回避矛盾。

## 明确算法与导出语义

1. This R101 expressly supersedes R100 line44 universal min(event.lower+kind budget) strict deadline. It does not delete kind constraints: six evidence kinds retain the entire original kind budget as an AGE_CLOSED obligation; bootstrap task lifecycle is HARD_OPEN. Every policy/parent obligation carries its source identity and operator. No +1ns epsilon, <= hard deadline, >5s allowance, ceil conversion or origin refresh.

2. For each AGE_CLOSED obligation i, use unchanged OC1 within_age(original_event_i, genuine current paired with that event token, max_age_ns=B_i). This means current_i.upper - original_event_i.lower <= B_i, not an OperationalDeadline. B_i is a positive exact integer capped by source policy; bool/nonfinite/negative/unsupported source fails closed. Convert valid seconds conservatively (floor exact intended decimal duration*1e9) and do not enlarge; preserve original policy payload/hash.

3. For each HARD_OPEN obligation j, use unchanged OC1 start_deadline(task_key=immutable source/key, origin=original task/verified hard origin, budget_ns=B_j), then before_deadline(deadline_j, current paired with its own original origin token). Comparison remains current_j.upper < original_origin_j.lower+B_j. Hard deadline equality rejects even when every age condition is still equal-and-valid. No arbitrary caller event becomes task/verification origin.

4. All active AGE_CLOSED obligations AND all HARD_OPEN obligations AND real current UTC lease/attempt/fencing/source/revocation gates must pass. Missing authority/pair/source returns UNKNOWN; genuine exceeded applicable bound INVALID; existing consumer mappings remain conservative. Registry policy, not public descriptor or caller kind string, determines obligation type.

5. Parents are complete sets of immutable obligations, recursively inherited/deduplicated by true original identity, not collapsed to an untyped scalar deadline. TTL parent retains <=; hard parent retains <. Mixed equal endpoints are rejected if any applicable hard bound is equal. Parent source invalid/revoked blocks child; no imported/copied/cyclic parent and no parent-origin renewal.

6. Each current receipt must be genuinely paired to the specific OC1 event token; never reuse unrelated after receipt, relabel a token or inspect raw clock to fake pairing. All reads owner-thread, sameD/boot/attempt. Validate caller after as truly issued/causally relevant. Readings at distinct times are recorded as such; P5 does not claim P6 atomic dispatch/transaction closure.

7. Public APIs unchanged. Operational descriptor new schema simulation.operational-window.v1 must record kind_policy, budget_semantics (AGE_CLOSED/HARD_OPEN), original source hashes/event IDs/budget, age_constraints with max_age_ns/upper_age_inclusive and expiry_upper_ns, hard_deadlines with deadline_ns/end_exclusive/origin, parents and their immutable identities. Retain deadline_ns as minimum HARD_OPEN deadline only, explicitly labelled deadline_semantics=HARD_OPEN; NEVER place TTL cutoff there. A separate descriptive effective_upper bound includes inclusive flag (false if any equal minimum hard bound). Its scalar is not live authority and not a substitute for checking every original obligation.

8. If a concrete original policy supplies an additional strict kind cutoff, keep its hard semantics with authentic original source and domain; existing UTC binding/external cutoff remains UTC_LEGACY_VETO. Do not infer a new hard cutoff merely because a field is named budget/TTL, and do not invent a D bridge. No new D hard-kind producer other than original bootstrap/task/verification is authorized in this round; newly discovered required producer/scope is another Astra stop.

9. Original R100 true startup capability, one-shot late runtime handoff, real SQLite ownership, immutable origin before RESET/settle, original cost/retry/claim ordering, seven actual producer-consumer paths, revocation, public history nonauthority and all legacy UTC behavior remain required. All-UNKNOWN or all-INVALID is not completion.

## 七类别真实政策

### bootstrap — HARD_ORIGINAL_TASK_LIFECYCLE

- 原来源：Actual job.timeout_seconds and role verification_limits.deadline_s frozen by worker._execute startup; visual_bootstrap original task/verification definitions.
- 年龄：No fabricated 5s TTL on the task-origin lifecycle itself. A bootstrap reference attached to an observation must also contain its registered capture AGE_CLOSED parent; bootstrap cannot exempt that observation from5s.
- kind预算：Original task budget or an explicitly tighter positive budget bounded by it; strict deadline rooted only at exact original task receipt, never an arbitrary later event. task_window keeps its immutable originally frozen budget.
- 硬约束：Original task, verification, inherited parent hard constraints; additional tightened bootstrap budget if issued is strict and remains fixed.

### capture — AGE_CLOSED

- 原来源：P5 ordinary5s policy and original reserve/complete CPU/actual acquisition bracket; no cache-read origin.
- 年龄：budget_ns<=5e9; original acquisition enclosing bracket lower is the age origin.
- kind预算：Inclusive age budget, not strict kind deadline.
- 硬约束：Original task/verification and all applicable parent hard constraints.

### plan — AGE_CLOSED

- 原来源：Original captured observation plus original reserve-plan/send-return receipt; P5 ordinary5s, actual bound role budgets/task/verification.
- 年龄：<=5e9 from own original effect event AND original acquisition parent. A reply/new plan event cannot remove or reset acquisition TTL.
- kind预算：Inclusive age cap; actual provider/task timeouts remain independently enforced. No unsupported D conversion of provider UTC deadlines.
- 硬约束：Original task/verification/parent hard cutoffs; preserve all existing UTC publication/lease gates.

### grounding — AGE_CLOSED

- 原来源：Original binding observation and immutable binding digest; original.requirements[step_id].ordinary_ttl_s (ActionEvidenceContract default5).
- 年龄：Conservative integer minimum of5e9, frozen original ordinary TTL, requested non-enlarging cap; inherited original acquisition age remains.
- kind预算：Inclusive observation age, never issued_at/republication TTL.
- 硬约束：Original task/verification/parents; existing binding expires_at and publication UTC cutoffs remain strict UTC where applicable, not relabelled D.

### supervision — AGE_CLOSED

- 原来源：Exact original frame/reply/context; original step ordinary_ttl_s and actual maximum_age_s used by decide_supervision, each frozen/bound at genuine producer. worker_runtime:age>ttl expired; supervision:age<=maximum_age_s accepted.
- 年龄：Minimum of5e9 and applicable original ordinary TTL/maximum_age policy; request/return cannot reset captured-frame parent.
- kind预算：Inclusive age.
- 硬约束：Original task/verification/parent hard constraints, existing supervision UTC deadline/lease checks retained.

### marker — AGE_CLOSED

- 原来源：Original registered actual frame, marker/camera/object/calibration bindings; marker_association freshness currently0<=age<=5.
- 年龄：<=5e9 from acquisition parent; detect/associate time never origin.
- kind预算：Inclusive age.
- 硬约束：Original task/verification/parents; other existing source/safety guards unchanged.

### condition — AGE_CLOSED

- 原来源：Exact registered observation and ConditionSpec.tolerances[max_age_s] default5; models ordinary_ttl_s where applicable. conditions rejects age>max_age, not equality.
- 年龄：Minimum of5e9, valid positive actual frozen condition max_age_s and applicable ordinary cap. Smaller limits enforced including equality; legacy UTC caller policy remains unchanged.
- kind预算：Inclusive age, no unbound caller tolerance can enlarge frozen policy. Invalid/changed budget fails closed.
- 硬约束：Original task/verification/parents and existing external UTC constraints unchanged.

bootstrap lifecycle本身可以超过5秒但不超过原硬期限；带观测的bootstrap引用必须继承capture TTL，不能因为category=bootstrap免除新测试第470行的原观测过期断言。六类TTL只在全部适用hard/lease条件仍成立时保证“5秒允许”；硬期限先到或同时到，正确结果仍拒绝。外部UTC5000ms接收年龄/1000ms未来规则及旧证书/租约不变。

## 范围与有限验证

继承R100恰好十路径，核心改动仍是NEW operational_windows、既有八调用源以及NEW test。本轮无第十一路径、无OC1/worker_owner/旧测试更改。算法语义变化需受限行为proof，不称whole-AST等价；八源其余路由/签名/异常/成本/旧UTC检查应逐项差异审查。纯手工格式整理另保存前后AST(type_comments)/注释对应证明，不得借此改断言或隐藏类型差异。

- `test_five_seconds_inclusive_and_plus_one_ns_rejected`，1case：Preserve original exact5s VALID/+1ns INVALID with distant real task/verification and no tighter parent. Also verify an explicitly tighter permitted age budget accepts its exact endpoint and rejects+1ns without upgrading to hard.
- `test_deadline_equality_rejected`，3case：Replace misleading plan TTL-as-deadline setup with authentic original hard source. Each fixture is configured before actual worker startup; task/verification fields and supported role budget agree. Parent_hard uses same-original-task-receipt bootstrap budget tightened to5s within source cap; child keeps inherited parent obligation. Arrange AGE_CLOSED expiry5s simultaneous with applicable hard5s:5s-1ns VALID,5s INVALID. Do not rewrite issued owner/origin or OC1 registries. Preserve old1-case RED bytes separately.
- `test_parent_age_closed_boundary_and_no_refresh`，1case：Parent capture original0 withTTL5s; later child plan event at2s. Parent age equality5s remains VALID when hard deadlines distant,5s+1ns INVALID although child younger. Child parent hard scalar cannot erase age constraints; original IDs/budgets unchanged.
- `test_window_export_preserves_typed_boundary_constraints`，1case：Assert AGE_CLOSED vs HARD_OPEN fields/operators/immutable source IDs, deadline_ns is hard-only, effective equal tie is exclusive. JSON round-trip remains descriptive; no owner ->UNKNOWN and cannot create enlarged budget.
- `test_nonzero_bracket_age_uses_original_lower_boundary`，1case：Controlled genuine OC1 event [10,20] with completed logical mark; paired current [5000000010,5000000010] accepted against5e9 when hard far, +1 rejected. Confirms no event.upper origin shift or zero-width special-case.

其余R100测试节点保留，七类别参数各增强：原观测5秒精确边界可用、+1ns过期；bootstrap引用验证capture父TTL。更新后的新文件32case（原27，deadline1→3增加2，新增3），OC1按真实JUnit计数。测试fixture可以在这个新测试文件内提供原始任务/角色预算的启动前配置以及受控计数读数；不得篡改运行后owner状态、虚构from_worker权威或改旧helper文件。原27case RED冻结和stdout/JUnit全部保留；新边界用例尚未运行，不声称它们已有RED。没有新增RED授权。

一次性顺序：核对pins/保存before → 先调整有限测试和政策映射 → 实施R100+R101限定软件 → 保存restricted semantic proof与所有差异 → Ruff一次 → new-two format-check一次 → GREEN一次。若新目录/basetemp已存在先停，不清理旧原件。每个命令单独启动/保存returncode，非0或proof问题立即停止，不串行误消费下一额度。

- `.venv/bin/python -m ruff check src/cloud_edge_robot_arm/vision/operational_windows.py src/cloud_edge_robot_arm/vision/worker_runtime.py src/cloud_edge_robot_arm/vision/supervision.py src/cloud_edge_robot_arm/vision/marker_association.py src/cloud_edge_robot_arm/repositories/event_autonomy/visual_bootstrap.py src/cloud_edge_robot_arm/repositories/event_autonomy/visual_supervision.py src/cloud_edge_robot_arm/edge/evidence/models.py src/cloud_edge_robot_arm/edge/evidence/conditions.py src/cloud_edge_robot_arm/simulation_runtime/worker.py tests/test_operational_windows.py`
- `.venv/bin/python -m ruff format --check src/cloud_edge_robot_arm/vision/operational_windows.py tests/test_operational_windows.py`
- `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_operational_windows.py tests/test_operational_time_v1.py --basetemp=/tmp/bigsmall-p5-r101-green --junitxml=artifacts/research/process/20261004-ced-development/astra-rounds/round101-p5-age-deadline-boundary-20261008/implementation/green/junit.xml`

统一环境PYTHONDONTWRITEBYTECODE=1、PYTHONPATH=src:.；stdout/stderr/start/result/JUnit与before/after、budget、步骤报告存新R101/implementation目录。GREEN是R100原剩余一次，非新增或重置：32新case+原OC1均无fail/error/skip才通过。Ruff原剩余一次覆盖十源，format-check原剩余一次仅两NEW。formatter/mypy/collect-only/其他旧套件/RED重跑均0；保留已经消费RED1。

## 实际前置与验收界

ROOT复核本计划MD链接、有限pins及R100冻结owned适用，独占Sol写窗口后派单；不要求全仓静止，也不pin后续P6活动总表或P4当前源为不可变。八源尚未实施，恢复时只对本轮十路径核对。既有R100原证据不可改写；R101明确记代数计划矛盾而非新增运行失败。

软件验收须有真正normal worker startup→late runtime→七producer/consumer正链，原点不刷新、TTL闭/硬期限开、父约束保留、UTC veto与public replay无权限、全部新32+OC1 GREEN、静态与不同作者独审。所有未实现的R100要求继续必需，不因修边界就提前通过。缺真实source/authority仍UNKNOWN，不接受全UNKNOWN/INVALID交付。

本轮actual/model/renderer/网络/Git均0。P4来源正分支只作已有机制依据，不借旧活句柄；P6真正D租约/提交/dispatch闭合、后续ROOT独占actual冻结与正式native研究门仍独立。新根因/范围扩展/非预期失败保留原件后下一Astra；不自动重试。

## 输入SHA256

- `AGENTS.md` — 1774B — `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649`
- `pyproject.toml` — 2458B — `b2bf5c4042d568eaf9def415ae7b2f08f0fa541a01f970b7e68e6d950035bb6c`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round100-p5-worker-startup-authority-20261008/plan.md` — 15571B — `521200276ccbed5c7c6c97d0c91cd019094e572b2b6f59ff1e8a705652b71ade`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round100-p5-worker-startup-authority-20261008/plan.json` — 11261B — `2af805437645c401af738b7f19bd62de6124a443e3cb80a502df27404344c5ce`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round100-p5-worker-startup-authority-20261008/input-pins.json` — 4440B — `78e3948371ac765e4598e480ab2cc38c542c4b6f7661b858d51d223ef0932707`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round100-p5-worker-startup-authority-20261008/root-activation.json` — 2952B — `78fe56ce0a8fcef5c136bcaf3fa4100b8da3b7b11eb09b6e60e69937e8c9dd1a`
- `artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/p5-executor-brief.md` — 6563B — `c48678fa788c8d9a0116952dbe1e1d9673e5002a0805eed9f61b85d343632694`
- `artifacts/research/process/20261004-ced-development/astra-rounds/t12-convergence-repair-20261006/plan.md` — 71264B — `d5c3d6b1ffa6f51f3a2785af5f5ab9fedf506f81080a3bea311644fff7c70219`
- `artifacts/research/process/20261004-ced-development/astra-rounds/t12-convergence-repair-20261006/plan.json` — 61014B — `7abb0157cf37a6d7988cac36a86a0c49bcef8d3d175f9be7aaf3623f92be96fc`
- `docs/superpowers/plans/2026-10-07-t12-sol-execution.md` — 77523B — `5a1358f0397edbc54c301edb63e934b1d2ba15ee79d64c9ae36248749b6af0f8`
- `src/cloud_edge_robot_arm/research/operational_time_v1.py` — 20734B — `b1fa45a96837072d7bcf8cec57d1a7ae01dceeabec0131503b6aee5ab27dd90b`
- `src/cloud_edge_robot_arm/vision/worker_owner.py` — 23511B — `ffce1cedb2cc9962ade0c5845d6ce92127372fa2248c0f4bc5f215706f5be86b`
- `tests/test_operational_time_v1.py` — 24211B — `ff226e9a616462c67d74d29931f8f9a7d21548f4f13f93ced64901b263229c0f`
- `tests/test_visual_worker_factory.py` — 15847B — `5f99a6bf6e9850875423a5a9eca5f47bbe88e4ff12b97048f218de19b76c57f9`
- `tests/test_visual_worker_runtime.py` — 21851B — `e2c0e9db9aec5426997bd2c615f1838c7625452446e8400319cc266269987de7`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round100-p5-worker-startup-authority-20261008/implementation/boundary-conflict.json` — 4297B — `44581092f06cc4ae56d09d4f42bfbad71c0377b0003ca02132eb728bdc4abf18`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round100-p5-worker-startup-authority-20261008/implementation/step-report.md` — 2224B — `a8d5e1078ada8063aeac3b6d4f731d51c4194d6a15b7960475c23907e3d4f231`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round100-p5-worker-startup-authority-20261008/implementation/step-report.json` — 4964B — `5920cd9791df5eab164654844408ae737adb03a88289f3016c39c46d3a2e6d90`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round100-p5-worker-startup-authority-20261008/implementation/budget.json` — 379B — `e97da099eb940db9b38410110fbdc6eeee39768ae11c2fe3950d985f6943ad87`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round100-p5-worker-startup-authority-20261008/implementation/source-freeze.json` — 7912B — `293b84a694970513caecb3bd0b7c66f68acf4a9b4c1f01ed4580fa77f37c0420`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round100-p5-worker-startup-authority-20261008/implementation/call-site-map.md` — 2851B — `660cd233e24ee15845cce2290cd1b94aa7ae7230a90aeb1e908455255355fef0`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round100-p5-worker-startup-authority-20261008/implementation/call-site-map.json` — 4061B — `a6de5c855679c6772a927bf2e691f8973bc70e896256b1f4617f5a0900cd0876`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round100-p5-worker-startup-authority-20261008/implementation/full-owned.diff` — 24656B — `753c70bc495d6f032c24173863ed57bdb482296bc49beaa69c6c1cd50f054805`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round100-p5-worker-startup-authority-20261008/implementation/finite-evidence-pins.json` — 4279B — `2f5b4820b55dab729213a55cac5b7e84c5f287871d93e039dd03c48e4227a898`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round100-p5-worker-startup-authority-20261008/implementation/red-node-freeze.json` — 2742B — `660f90b085e394dcda9abeed4c0d0ebc50ef3ca407ad7823ce3c7dfc7f7e0df4`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round100-p5-worker-startup-authority-20261008/implementation/red/command-start.json` — 590B — `2b4e80e8dfb1ce823c7d324ad91c33aaeca3a01c167d60c2b97d60162acf8fdb`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round100-p5-worker-startup-authority-20261008/implementation/red/command-result.json` — 901B — `97c46d5fd4df3e104cf289d0e77fc9c89cab37e3580330db36e070056d3aa97f`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round100-p5-worker-startup-authority-20261008/implementation/red/stdout.txt` — 95853B — `ca5534ad8f69883f9fac708520eb0563c304f264a14650280b95879e02d123fd`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round100-p5-worker-startup-authority-20261008/implementation/red/stderr.txt` — 0B — `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round100-p5-worker-startup-authority-20261008/implementation/red/junit.xml` — 98648B — `34304ad10822fe9fb66c83166f84242cb8abf55307922bbe75b1be55d9da97d6`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round100-p5-worker-startup-authority-20261008/implementation/red/junit-summary.json` — 6579B — `9485e965f53c236464bcc260bd61b26340381ef35cd26e26f2d07f40ba2fd7e0`
- `src/cloud_edge_robot_arm/vision/worker_runtime.py` — 62580B — `84ea21214453537e0c0d39ebf2da1a8ea3aa8539354089318e6d6398181fdfa1`
- `src/cloud_edge_robot_arm/vision/supervision.py` — 2486B — `8f5cab1e2beca0633465686fcd51fe594af599bf5f506f75c83d2931d5662429`
- `src/cloud_edge_robot_arm/vision/marker_association.py` — 26835B — `f538c6b751ab560b2523cfbe2d237f8956b092931af276bfcda744d10ee4f426`
- `src/cloud_edge_robot_arm/repositories/event_autonomy/visual_bootstrap.py` — 42649B — `465dfe42aca7e005933cb6d163344b3b5ebdfec6106cf9ce0295f1c910770584`
- `src/cloud_edge_robot_arm/repositories/event_autonomy/visual_supervision.py` — 34216B — `c73908964542d843c8bc28cc230dc651403dcfdb7c843be500f6644c21f7d162`
- `src/cloud_edge_robot_arm/edge/evidence/models.py` — 3448B — `0e631704afcf1544382f401434828dcf7b2d9587469049bbb4954e73070c8277`
- `src/cloud_edge_robot_arm/edge/evidence/conditions.py` — 11931B — `8298f504df482fbabba720b058f2595eb0a6e1c76f9d2febff7eade01e44d8ab`
- `src/cloud_edge_robot_arm/simulation_runtime/worker.py` — 80239B — `31cea6501ee9286ee933335f013422314985726036c8029844929cc96be2fdb4`
- `tests/test_operational_windows.py` — 24054B — `d99938e42bfa9b4dc4fbf0c9d7260f99c19f5b9b9d12b1c80f4376dc510a901f`
