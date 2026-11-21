# V10 Phase 3 Implementation Plan

> 本轮计划由 `gpt-6-astra` 根据用户明确要求生成。执行者按任务顺序实施；先记录预期 RED，再最小修改、验证和审查。计划阶段只读调查与软件边界探针已完成，未改生产代码，未提交、推送或执行正式仿真。

**Goal:** 以 `fc6520c04011cd211c4d4c2888f9e3b8fb8cf598` 为基线，打通 v10 协议读取、真实注册执行配线与相对物理步校验，保持 v9 和旧 V1 runner 行为，完成软件验证后按路径提交推送。

**Architecture:** 仅固定 v10 协议选择 `RationalCompletionHorizonV2`；原件保留绝对 dispatch/controller-return/terminal 步，超时计算使用动作派发后的相对步。LIFT 的运动截止与内置接触保持后返回分开解释；RELEASE 保留 return 后 240 步。runner、线上 POST 回执解码和 full reader 共享严格的纯算术校验，各自继续验证实际来源。

**Tech Stack:** Python 3.12.3、Pydantic 2.13.5、pytest、现有 MuJoCo 软件后端夹具及原件记录/读回接口。

**Spec:** 用户本轮明确指令：继续 Phase 3；以 fc6520c0 为基线；先 Astra 计划；接入 v10 read_protocol；按动作派发步计算相对步数；分别校验控制器截止步与保持后终步；等号和超限负控；v9 兼容；验证后提交推送；正式仿真先不跑。当前消息提供的流程指令优先于仓库较旧/不同的流程文字。

## 固定边界与关键取舍

- 当前独立公开交付分支 `research/harness-candidate-v10-phase2-20261121`；复用此交付工作树。保留私有工作树、历史日志及冻结原件，不 reset/clean/stash/rebase/amend。
- 仅 SOFTWARE_ONLY；本轮无 renderer 正式运行、无正式 collect-once、无真实机器人、无真实模型或付费调用。软件 seam 调用不能称为正式仿真或研究验收。
- 不扩大到其他协议、实机超时语义、采样频率、TTL/租约、取消、墙钟任务 watchdog、最大预算、guard 或单释放授权。固定相机、标记、控制器与 1/240 秒物理网格不变。
- 不改变 V1 horizon 配方/runner 的语义，不给 v9 添加 v10 metadata，不全局修改 SafetyContext schema。仅 v10 下现有 `physics_step` 字段表示动作相对步；其他协议保留现有字段及单调墙钟 StepTimeoutRule 行为。
- 固定 v10 config 已有字节 SHA 校验，与 v9 相同；沿用此门，且 runtime 必须通过完整 `_registered_teacher_v10_protocol()` canonical 比较。不要借机重构 source_inventory。当前 source_inventory 递归纳入所有 src Python 文件，另含配置/资产/CLI/pyproject 等；不删除、不跳过 pin。新 v10 config 由独立 `teacher_release_config_sha256` 加固定字节门约束。
- 公开只记录 repo-relative 路径、安全摘要/测试名、SHA256 和结果；不得复制本机路径、凭据、私有日志、raw、数据库、权重、SDK。派生清单不是完整远端复现包。

## 问题、原始证据和假设

基线 HEAD 已只读核对为指定 SHA，计划调查开始时工作树干净。纯软件探针原始 JSON 的 SHA256 为 `142c26d3a34e98c3c1cef6f28e72fc2555ed93f68a65cc74afe2d15287998137`；安全原始探针内容完整嵌入 plan.json，私有原文件继续保留。探针未初始化正式场景、renderer 或真实 worker。

1. v10 builder/prepare 已存在，但 `read_protocol()` 无 v10 分支。基线探针读刚生成协议得到 `ValueError: registered operational calibration protocol required`。
2. `_check_protocol_sources()` 同样无 v10 分支，落入旧 schema/family 校验；探针得到 `ValueError: registered schema/family pair required`。不能只修 read 后绕过 live source 验证。
3. `_execute_horizon()` 固定构造 V1，runner 只接受 V1；传入正确 V2 探针得到 `ValueError: exact registered skill horizon required`。线上 `_registered_current_receipt_v2()` 调用 `_v2_receipt()`，后者也固定 V1 重建，属于本轮必修链路。
4. 当前 StepTimeoutRule 将绝对步直接比较相对 terminal。探针 `physics_step=2020`、真实 dispatch 假设 100、terminal=1920 时拒绝，尽管相对步正好为 1920；`physics_step=None` 时竟退回墙钟并 ALLOW。本轮必须 fail-closed，不能将缺失物理数据解释成 v9。
5. `MuJoCoSkillRobot.lift()` 先 `_move()` 成功，再在该调用内部保持 `ceil(0.5/dt)=120` 步，随后才返回；成功 ActionResult 的 `details.physics_steps` 包含运动+保持，`contact_hold_s=held_steps*dt`。因此 LIFT 的 `controller_return` 不是运动到达时刻。RELEASE 的保持由 runner 在返回后完成。
6. full reader 已绑定实际 executor interval、capture、原件与注册 horizon，但目前没有 v10 controller-deadline 算术，并且单释放门只枚举 v9。本轮加 v10 精确分支。独立 partial trace reader `verify_registered_occlusion_trace_v2` 明确只支持 v8，而且重建 Shield context 未传 physics_step；该已有缺口不表示可以声明 v10 partial 完整读回。除非必要测试触达，不扩展这一专用 reader。
7. Phase 2 已公布聚焦 104 passed；周边组 baseline/Phase2 同样 33 个 SQLite `teacher checkpoint database identity changed` 失败；mypy baseline/delivery 同样 53 个诊断。本轮必须实际跑前后对照，以节点/诊断内容比较，不用旧计数替代本轮验证。
8. 主任务另已记录当前基线 prepare 成功、read 拒绝和 dispatch=120/绝对终点=2040/相对1920时 Shield 误拒的实际探针。历史 v9 档案在 fc6520c0 下即使 current_sources=False 也已因现行来源规则拒绝：档案 454 项、当前 456 项，新增 native_action_timing/native_checkpoint_diagnostic 且 CLI SHA 改变。对应冻结 v9-source 的 read_protocol(current_sources=True) 与实际 `_owner_decode(original-plan.json)` 已成功。故本轮兼容必须区分当前 v9 fixture 回归和对应冻结源码读回，不承诺当前源码接受任意旧来源，不放宽 existing historical-source 门，不改历史 ZIP/原件。安全来源标题、SHA256 与字节数见 plan.json。

以上是已证实的路径不适配，同一 v10 接线根因可合并；输入清单与每个 SHA256 见 plan.json 以及本文件末尾。若后续出现新根因、额外安全边界改变或计划外失败，暂停相关修复并生成下一 Astra 轮；既有明确记载的基线失败不冒充新回归，也不在本轮掩盖或顺手修复。

## 数学与证据契约

记 `d` 为真实 backend 派发绝对步，`r` 为 executor 返回后的绝对步，`t` 为实际最终采集绝对步；`C` 为注册 controller_deadline_steps，`T` 为 terminal_steps，`B` 为 builtin_tail_steps。要求实际计数是 built-in int、非 bool、非负且单调；V2 horizon 必须为 exact type、与 skill 及注册 recipe 重建结果一致；`T == total_steps`。

| 技能 | C | T | 可验证的控制器截止 | 成功终点 |
| --- | ---: | ---: | --- | --- |
| MOVE_ABOVE / APPROACH / PLACE / RETREAT | 1920 | 1920 | `r-d <= C` | `t-d == T` |
| GRASP | 240 | 240 | `r-d <= C` | `t-d == T` |
| MOVE_TO_REGION | 2400 | 2400 | `r-d <= C` | `t-d == T` |
| LIFT | 1920 | 2040 | 严格证明内置 120 步后，以 `r-d-120 <= C` | `r-d <= T` 且 `t-d == T` |
| RELEASE | 240 | 480 | `r-d <= C`，并要求 `d+T-r >= 240` | `t-d == T` |

LIFT 最小适配不修改控制器：仅在 v10 固定网格/注册源可信的路径下，严格要求 `details.physics_steps` 为 built-in int 且等于 `r-d`，`contact_hold_s` 是有限数且精确等于 `B*registered_dt_s`，`B==120`、`r-d>=B`。由已 pin 的固定 lift 实现，成功返回前末尾 B 步就是接触保持，故运动结束相对步可推算为 `r-d-B`。这项纯计算不是独立物理证明：runner 继续实时持物/guard；reader 继续用实际 interval 和连续物理状态/末帧校验。禁止仅看到 `contact_hold_s>=0.5` 就任意减 120；禁止把 LIFT 全调用返回误比 C，或通过增大 C/T、改 timeout_ms 来让测试通过。如 source 无法支持这项证明，停止并重新规划显式运动终点证据，而非松绑。

等号一律允许：controller 相对步恰好 C，LIFT 运动恰好 C 且返回 C+B，终帧恰好 T。`> C` 或 `> T` 必须拒绝；成功终点早于 T 亦拒绝。v9 租约/墙钟截止的原有等号规则不受此物理步等号约定影响。

共享纯校验建议置于现有 `vision/native_completion_horizon.py`，避免新模块和跨层循环导入；确切函数名可由实施者确定。至少拆清“返回窗口已合法”与“完整终点已合法”，返回可检查的失败理由/计算值，不读 backend、不授予 authority。严禁从自报 receipt 推导来源可信。

## 任务 1：协议读取、固定释放与来源配线

**Files:** `research/native_calibration_collection.py`、`research/native_collection_application.py`；优先扩展 `tests/test_native_registered_teacher_release.py`。

- [ ] 先写/运行 RED：prepare v10→read→from_startup；固定 FIRST 可构造、SECOND/重放拒绝；全程不进入真实 worker/render。复用已可通过的 v9 SQLite 工厂夹具。
- [ ] read_protocol 加 exact v10 schema 分支，用 `_registered_teacher_v10_protocol(historical_sources=None if current_sources else protocol.get('source_hashes'))` 比较完整 canonical，保持 v9 分支不动。历史来源模式仍校验 recipe、固定 config、source_generation 自洽，不把协议自报 hash 当 live trusted source。
- [ ] `_check_protocol_sources()` 加 v10 完整固定 builder 比较；from_startup 和 prepare_once 都保留 read/claim 门。`_execute_horizon()` 仅 exact v10 选择 V2 builder，其他 schema 仍 V1。
- [ ] 负控分别改 release assignment/status、第二释放、deadline/terminal、timeout_basis、wall-clock 标记、source_hash/生成摘要和 fixed config 内容；不得建 runtime 或派发。live source current 模式拒绝旧 hash；historical 模式不可被当作实际启动门。
- [ ] 公共 CLI 用 `--prepare-only --config configs/research/native_registered_single_teacher_p0_v10_20261121.yaml --output <fresh-temp>` 做 smoke，正常 prepare 不建 physics backend。collect-once 仅以 spy/seam 验证分发至同一 from_startup 门，不执行实际采集。若 CLI 无需变更则不修改。

## 任务 2：V2 runner 相对步、LIFT/RELEASE 边界与终帧

**Files:** `simulation/mujoco/native_horizon.py`、`vision/native_completion_horizon.py`；优先扩展 `tests/test_native_horizon_execution.py`。

- [ ] RED 从现有 run_fixture 扩展真实非零 dispatch（至少 100 与累计前序动作后），加入 V2，并使 LIFT 软件返回提供真实一致的 physics_steps/contact_hold_s；原 V1 用例保持。
- [ ] runner exact type 接受 V1 或 V2，skill/recipe 防伪不放松。V2 对 `r-d` 和 `t-d` 校验；回执 d/r/t 仍绝对。V1 保留原错误理由和行为，不悄然套用新 deadline。
- [ ] 采用上述 LIFT 推算规则；RELEASE 保证返回后至少 240 步；普通动作 C/T 同步。返回超限不得进入 padding/terminal capture，失败回执保留实际 r/t 和 controller result 并 close guard。
- [ ] padding 仍不发新目标，逐物理步 capture 和 check_active 保持；捕获终帧后再验证 backend 未推进且恰好 d+T。异常仍落盘 failure receipt，保存原异常，原件写失败 fail-closed。
- [ ] 参数化等号与 +1：普通动作 C/C+1，LIFT r=d+C+120/r+1，RELEASE r=d+C/r+1；LIFT 缺失/浮点/布尔 physics_steps、伪造 hold 长度、过短返回、错误 dt、hold 声明与 r-d 不符必须拒绝。终帧 t=d+T 通过，提前/多推进一帧、无完整终帧或采图异常不能 complete。
- [ ] 复跑失去持物、release closed、执行取消/墙钟租约到期、guard 已关闭、记录失败等现有保护用例；仅物理动作超时转相对步，不屏蔽外层限制。

## 任务 3：SafetyContext 最小相对步适配与 fail-closed

**Files:** `research/native_collection_application.py`、`edge/safety/rules.py`，如解释字段含义仅注释 `edge/safety/models.py`；测试 `tests/test_native_collection_context_steps.py`、`tests/test_phase3_safety_shield.py`。

- [ ] RED v10 非零 backend 下 PRE=0、POST=实际末步−已绑定真实 receipt.dispatch_step；PRE 采样锚须与 dispatch 对应。v9 仍保持 Phase2 测试所断言的绝对 PRE 120 / POST 2041，不增加全局字段。
- [ ] v10 应用在 PRE 构造时记真实派发锚，POST 必须使用持有的真实回执和 live registered_execution 的 dispatch 并核对顺序；不从调用方任意 metadata 取得 d。
- [ ] StepTimeoutRule 仅在 contract metadata 明确 PHYSICS_STEPS 时进入物理路径，要求 context 相对 physics_step 为非负 built-in int，horizon 为完整固定 V2 并与 skill/timeout 配方相符；缺字段/类型错/负值/非有限/未知 schema 都 fail-closed，绝不回退墙钟。physics_step==T 允许、T+1 拒绝。
- [ ] 没有 PHYSICS_STEPS 的 v9/旧契约继续用 monotonic_now−step_started_at。保持 TaskDeadline/Watchdog/lease/cancel 的墙钟约束，不以物理 timeout 绕过它们。
- [ ] 严格序列化/字段集合回归：不增 SafetyContext model 字段；Pydantic 原件完整上下文形状按原协议继续可读。

## 任务 4：线上回执与 full reader 的必要原件配线

**Files:** `research/native_full_horizon_recorder.py`、`research/native_full_horizon_originals.py`；测试复用 `tests/test_native_full_horizon_originals.py`、`tests/test_native_registered_teacher_release.py`，必要时在同组新增窄测试。

- [ ] `_v2_receipt()` 按可信 action row 的注册 horizon schema 选择 V1/V2 builder，然后比对 action horizon 与 receipt horizon_json 的完整 canonical，不单凭 receipt 自报版本选择。V2 调用共享窗口/终点校验；V1 保留已有兼容语义。线上 POST 因此能接受真实完整 V2，不允许未满 T 的 complete receipt。
- [ ] full reader `read_native_full_horizon_group()` 的单释放门纳入 exact v10；`_Audit.horizons()` 在已验证 interval、span、返回 ActionResult、末帧/连续状态来源的基础上再验证 v10 相对 deadline 与完整终点。不能只跑共享 helper 就宣称原件读回完成。
- [ ] 用软件记录真实 `FullHorizonExecutionReceipt`、序列化 horizon_json 和 controller_result_json，经实际 `_v2_receipt` 解码；篡改 d/r/t、horizon、physics_steps、tail、terminal capture 或返回间隔时拒绝。至少验证 runner→真实回执→真实严格解码链，而非伪造 SimpleNamespace 成功结果。
- [ ] v10 原计划在 build→freeze→to_payload→实际 owner decoder/JSON roundtrip 后，contract timeout_basis 和每个 step horizon 保留且 digest 一致；source_hashes 当前来源、worker original binding、grounded full contract 比较继续有效。通常无需修改 worker_owner/owner_registration，先用测试证明，禁止为通过而丢 metadata。
- [ ] 公共 verify 的空/未运行组报告 UNKNOWN/NOT_RUN、不产 joint bound；v10 第二组拒绝直接 read。正式完整 raw 不存在就明确未验证完整真实 run，不能制造或复制冻结 raw 来完成证明。
- [ ] 记录后续缺口：专用 v8 partial trace reader 的 exact v8 gate 与既有上下文 physics_step 重建缺失；本轮不扩展其协议授权。若当前 full path 实际必需触达并失败，留原始证据交下一 Astra 轮，不混称已完成 full/partial 的所有读回。

## 任务 5：验证、报告与交付

- [ ] 实施前重新核对 HEAD、branch、输入 SHA、工作树差异和计划适用性；明确 Python 导入都来自交付工作树。可以用已有受控解释器，但 `PYTHONPATH` 显式为该 worktree 的 src 与根，不能误测 editable 私有源。
- [ ] 在改动前保存本轮 focused/broader/mypy 基线和原始失败；按上面新增预期 RED 保存节点与理由。修复后执行同样命令、实际比对节点/诊断，保存不经改写的原始日志；公开只存安全派生摘要与 SHA。
- [ ] 聚焦至少覆盖 `test_contract_timeout_metadata.py`、`test_native_collection_grounding.py`、`test_native_collection_context_steps.py`、`test_native_registered_teacher_release.py`、`test_phase3_safety_shield.py`、`test_native_horizon_execution.py`、`test_native_completion_horizon_v1.py`、`test_phase0_contracts.py`、`test_native_full_horizon_originals.py`、`test_native_active_checkpoint_equivalence.py`、`test_native_whole_action_diagnostic.py`，另加入本轮新增 V2 算术/严格读回测试。
- [ ] v9 周边兼容组和 mypy 使用 Phase2 同一清单/参数重跑并做前后对照。53 诊断只是历史基线；如本轮加查文件改变诊断范围，分组报告而非比较不相同口径总数。已知 33 SQLite 失败要节点+异常同根因证据，不使用 skip/xfail/monkeypatch 生产边界掩盖。
- [ ] 受影响文件 compile、ruff；mypy 至少原 Phase2 三文件 `contracts/models.py`、`research/native_collection_grounding.py`、`research/native_collection_application.py`，新增文件诊断单列。历史 v9 原件仅本地只读验证 bytes/payload/digest 不变，公开仅样本安全标识和哈希。
- [ ] 生成本轮 `step-report.public.md`、`validation.public.json`、`stage-summary.public.md`、`source-manifest.public.json`，分别记录开发验证/真实运行未执行/正式研究 UNKNOWN。按实际完成的步骤和真实结果填写，禁止把未跑项标 PASS。
- [ ] 提交前复核 diff，精确 stage 实际变动的允许路径（本计划允许文件清单见 plan.json）；禁止 `git add .`、`git add -A`、整 artifacts 递归添加。计划目录 sparse 外用 exact `git add --sparse -- <path>`。检查新增提交所有可达路径/blob，不带入私有祖先或日志。
- [ ] 验证通过后在当前研发分支提交并显式推送该分支，不 force、不 all/tags/mirror。远端漂移先停止推送并调查。推送后核对 local HEAD、upstream、remote 分支 SHA 三者一致；记录最终 SHA。交付报告不得声称已有真实仿真或研究通过。

## 实际前置条件与验收边界

已有独立公开工作树、指定 Git 基线与受控 Python 环境；运行前需确认依赖/资产齐备、磁盘可写、无无关修改、origin 权限与远端仍对齐。新测试沿用现有软件夹具，不启动正式 renderer/真实采集。任务 1–4 的必要路径、等号/+1/缺证据负控和 v9 focused 回归必须通过，广域已知失败与静态既有诊断须有本轮真实前后等价证据。输入变化、计划外失败或新增根因按用户当前流程重新交 Astra；不得改原件/删日志使检查通过。

本轮验收仅为软件接线正确、相对步边界正确、真实序列化接口能校验、v9 未回归、公开交付增量可审查及 Git SHA 对齐。完整原始仿真、完整远端复现包、物理成功率、native authority 或正式研究资格均不在本轮完成声明之内。

## 输入 SHA256

- `AGENTS.md` — `7f4f8b080b2f1e99b53d24aeebf62f51815315c69a40dc9223d2e974c3c40cdb`
- `pyproject.toml` — `034a85388f25f1aedfb856f1783e6d3c6a3413f00d4a1825b907fe3749399565`
- `scripts/collect_native_calibration.py` — `e3473e3c65c8bec145b4f7c5c0f7a30edad45320155ddb97985465f37854255e`
- `configs/research/native_registered_single_teacher_p0_v10_20261121.yaml` — `2b893cbcd1b959703ceada3663433eebb975adbcf8278a522967f2ad12131cf8`
- `configs/research/native_registered_single_teacher_p0_20261119.yaml` — `94dc78d497f3a5e2bbbedea5b6bfc4ae20f945203a1a83c8796bb46b47753fcf`
- `src/cloud_edge_robot_arm/contracts/models.py` — `d9b3888fca6bb46c62326c9bf5fd49cf4c646ce21cf29994315107bf41d79464`
- `src/cloud_edge_robot_arm/edge/safety/models.py` — `9597cecf9ff02c1909f705353820901aaa4219b5f71083e89b082f11f1c2d135`
- `src/cloud_edge_robot_arm/edge/safety/context_builder.py` — `4615404f4259210fca1b7218cc9e5a1dc683721f0218367083a957bf41396bed`
- `src/cloud_edge_robot_arm/edge/safety/rules.py` — `be5911abef6b85b9f11b07c2ddf80adfc9f91b7f1837dd80692c78f9f8c99b01`
- `src/cloud_edge_robot_arm/research/native_calibration_collection.py` — `2ee3f55bfd4e0ed0d4c186197e26dc5b489f23994d2d9df8f0225de8d81cf5cc`
- `src/cloud_edge_robot_arm/research/native_collection_application.py` — `bac18e903699ffbd70f76ccc048481c806b5d6a2f554f20c3b124f5b395f8168`
- `src/cloud_edge_robot_arm/research/native_collection_grounding.py` — `720a999f2e7b349eca2adad055fd69eb31e634c013aa8dee3cf4c208ac188204`
- `src/cloud_edge_robot_arm/research/native_full_horizon_recorder.py` — `d60973276b3d2826c565854743e608adcece38bc4b682be79c09f5a472f27f9a`
- `src/cloud_edge_robot_arm/research/native_full_horizon_originals.py` — `c023bed818a11c1302bb55d4de56634412933e08f98d4891338375107cebdb10`
- `src/cloud_edge_robot_arm/simulation/mujoco/native_horizon.py` — `19f71847b740f8b5226d6c166e31e4dfd0cef833c6d58e15f6c52407237cf4ec`
- `src/cloud_edge_robot_arm/simulation/mujoco/skill_robot.py` — `ab0755515ea49b1d27d38ff0022df6ba99a08a8465c0577756278573be397cc0`
- `src/cloud_edge_robot_arm/vision/native_completion_horizon.py` — `163c603016096529a78117167b62cb0f68d589498ba6ff88f29379271ecfa157`
- `src/cloud_edge_robot_arm/vision/worker_owner.py` — `8128f8253e82deef5fab75fe5d24e79cd896c5588b9548b5ea4afe563731a21c`
- `src/cloud_edge_robot_arm/vision/owner_registration.py` — `17ccc6ea0c6e3095e77a37880b4fcbc7448eef88ecf94813369e5daaff28a43a`
- `src/cloud_edge_robot_arm/simulation_runtime/worker.py` — `35844661596f08b704ee4b5a04a16c487f2d708e8283918e4353208e318b433e`
- `tests/test_native_horizon_execution.py` — `01f5cfe416061e1af9f405560c035e39ac9f4cd921c773b83b448dbf0c3905ff`
- `tests/test_native_registered_teacher_release.py` — `7f76566430f68ffcf8079d84d02306b75f37f591eff783b05eb868235cd7118d`
- `tests/test_native_collection_context_steps.py` — `1e010dabe0e5f57d8ee90daf9a301c3c799c38ae49e96328f29376a4c558cb3f`
- `tests/test_native_full_horizon_originals.py` — `ffb3adbe0442916eba5d1fdcebcff213c7f752373f447b908c91170f1a4d8792`
- `tests/test_phase3_safety_shield.py` — `ddbca94ed58e45d37903812fbaca3ac114a5a83b5d5502671da7616c6c7a9914`
- `tests/test_contract_timeout_metadata.py` — `b34ecfd7c2a257c43c464bc5b0cd7e6934b5c5fcee1f87ea12af8ecb8bf17fc5`
- `tests/test_native_collection_grounding.py` — `bc02f9f4c7f5e439c3932e84baa13bfaa41ffae9df0ab20de6092c8d20f0209b`
- `tests/test_native_completion_horizon_v1.py` — `1a962a4b37706d9508320bae005510e945283326e657eac21ec7579194ca8d8e`
- `tests/test_native_single_teacher_release.py` — `5145bd85a50e4904e496b39da19ebaa1a9f7378958401ccb6453d1adf08d9444`
- `tests/test_native_active_checkpoint_equivalence.py` — `898a637e29df2abf8ad2bf0fa45aeed5021926e41a9a36872f4608c136e1a27b`
- `tests/test_native_whole_action_diagnostic.py` — `0e6a49399d5b88f557378007f08560e901ae25b7f9fa43de47174c97d827ee67`
- `tests/test_phase0_contracts.py` — `9eefb9267a2eaecf4f2b5979f7439452ddfc5d63fb6f85d0ab25a782fdd049b2`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round-v10-phase2-public-delivery-20261121/plan.md` — `d51981341aa6e65988757fda0a662ec953de8e7159ea4a8de81e06a5c4f94f9a`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round-v10-phase2-public-delivery-20261121/validation.public.json` — `4d762141343f4d20981cc1cb179992cd81814e3dabf9c390725fa61910698148`
