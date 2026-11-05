# R435：真实 MuJoCo 执行守卫最小交付 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this bounded plan inline. Steps use checkbox (`- [ ]`) syntax. 本轮实际规划者为 `gpt-6-astra`；实施者复核输入后直接开展已授权常规实现，不另要求用户批准本计划。独立最终代码审查由实际 Astra 完成。

**Goal:** 将原始 BOOTTIME deadline 的拒绝能力接入实际 COMMAND、CONTROL 和每次 `mj_step`，交付一次真实无渲染小步正链及到期拒绝证据。

**Architecture:** 后端提供独立于被动 observer 的同步 pre/post 守卫；研究模块绑定单一活时钟 owner、原始事件/deadline、backend/episode 和不可刷新的一次会话。真实诊断只使用同位关节命令、开夹爪和两步物理；不调用 SkillExecutor、native admission 或模型。完整 full-H producer 是下一块，不能用本轮诊断冒充。

**Tech Stack:** 当前 Python 3.12、MuJoCo 3.3.7、已有 NumPy、pytest、Linux CLOCK_BOOTTIME；不安装依赖。

**Spec:** `round91-native-full-action-support-20261007/design.md` §4 的实际 pre/post 物理守卫，及 `docs/superpowers/plans/2026-10-22-post-opening-development-plan.md` Task 2/3。前者完整抓放设计只有本计划明示子集在本轮实现。

## 原始问题、证据与限定根因

输入 HEAD `9ce1972fa8bd9858fb48c15145b5b82d5a4bf953`，分支 `research/20261004-continuation`。38 项文件及 SHA256 在 `intake/input-pins.json` 和 `plan.json.input_pins`；完整带行号证据在 `intake/source-evidence.md`。此次规划没有运行产品、测试、渲染、模型或动作。

1. R429—433 阶段总结明确 producer `UNAVAILABLE`、guard `NOT_PROVEN`、native `UNKNOWN`；合成完整原件结构门不证明执行中的拒绝能力。
2. `backend.py:165–191,306–355` 观察路径可完全未注册，且 operation observer 异常被捕获保存；它不是取消守卫。`step:554–617` 有挂 operation observer、无 observer、仅 legacy step observer 三条路径，后两条直接调用 `mj_step`，必须全部覆盖。
3. `backend.py:765–812,975–995` 关节队列、目标、夹爪 ctrl、CONTROL 写入发生时未消费原始 OC1 deadline。`operational_time_v1.py:385–424` 已有严格 `current.upper_ns < deadline.deadline_ns`、原始 lower endpoint 和不可刷新机制，可直接复用。
4. `backend.py:814–844` STOP 依赖 HOLD，并可能嵌套 CONTROL；把所有写入一概用同一拒绝回调包裹会阻断停止。必须限定安全停止路径，原始异常保持主因。
5. `operational_prefix_v1.py:303–340,1430–1472` 是 RESET120/零动作专用入口。本轮不得将其扩成动作入口，不能借旧 prefix receipt 的权限。
6. 纠正旧判断：成功 COMMAND `_operation_result` **已有 `physics_state` 和 `command_records`**。不是此处缺字段导致 producer 缺失；失败 COMMAND 原本单独保留 command_records。不得改写旧计划字节。

根因结论是缺少独立实际执行拦截点和原始 deadline 到该拦截点的组合，不是时钟算术或离线 reader 错误。本轮把这个独立块落地；暂不声称 worker/lease、native 三消费者、全 H/TTL 已整体接通。

规划 metadata 曾因 shell 无 `python` 别名返回 127，原 stderr 和同一实际 Astra 的处理记于 `intake/intake-state.json`；改用 `python3` 生成只读元数据，产品验证固定 `.venv/bin/python`。没有借此修改环境或产品。

## Global Constraints

- 保留 Qwen3.8-Max 云方案、边缘模型后置、OpenCV、可见标记、顶视相机及既有控制器、模型资产和阈值。
- 不启用 dispatch/local_recover/native VALID，不改 full-H reader 的 `SOFTWARE_ONLY/UNKNOWN/UNAVAILABLE/NOT_PROVEN` 常量。
- 不改旧 prefix 的120步/零动作语义；不读取/改写历史原件、运行 DB、credentials、权重和 SDK。
- 原地限定实施获既有授权；不修改两个脏 gitlinks `workspace-baseline`、`workspace-h3`，不用宽泛 git status 或 git add。
- 无 guard 的已有行为必须保持，包括 callback 顺序、contacts 更新时机、estop 后原有 holding 行为及 observer 失败记录。guard 不改变控制律、目标裁剪、dt 或物理积分算法。
- 任意阻塞的 `mj_step` 无法被 Python 同线程硬抢占；postcheck 记录已发生效果、拒绝成功和后续步，不声称绝不跨期限。
- 普通 Python 调用者能构造 guard 描述，不获得 native 权限。只有诊断组合使用 live OC1 owner；不是防恶意进程内反射的隔离系统。
- 本轮不要求付费模型、渲染、硬件、全库4751长测。软件验证、真实无渲染仿真、完整闭环、正式研究验收分开。

## Review Focus

1. 三条 physics 分支与 COMMAND/CONTROL 的 BEGIN observer 延迟：真正 effect 前重新检查；挂钩前检查不能替代该检查。
2. effect 后和 END/legacy observer 后到期：保留真实步数/状态/命令，后续步和“成功返回”均禁止。
3. deadline/clock identity/cancel/observer异常后，退出 context、重装 guard 或 reset 不能让同一个诊断 backend 悄悄恢复。
4. STOP/HOLD/control 的拒绝递归、stop 自身失败、异常字符串失败：安全停止不被守卫或 observer 吞掉，原始失败不被覆盖。
5. guard callback 重入 step/COMMAND/reset/STOP：拒绝回调内 backend 变更，回调退出后由 backend 执行自己的安全停止。

上述五类均有以下明确测试；不存在以 audit PASS 替代 effect 检查的验收。

## 精确修改边界与接口

仅允许修改既有 `src/cloud_edge_robot_arm/simulation/mujoco/backend.py` 的 guard 状态/生命周期、三个 effect 路径及停止组合；新增：

- `src/cloud_edge_robot_arm/research/guarded_execution_v1.py`：OC1 守卫组合和限定诊断函数。
- `tests/test_mujoco_execution_guard_v1.py`：真实 backend 方法配原始软件模型/计数器 seam 的执行反例，禁止 mock verdict。
- `tests/test_guarded_execution_v1.py`：OC1 生命周期与真实诊断用例；真实诊断 node 单独执行。
- 本轮 `implementation/run_validation.py`、`implementation/run_diagnostic.py` 及 `validation/`、`review/`、`delivery/`、步骤/阶段报告。主代理负责此后证据文件。本规划代理只写 plan 与 intake。

其他已列输入只读。尤其不修改 `operational_prefix_v1.py`、`operational_capture_v1.py`、`operational_time_v1.py`、`raw_episode_v3.py`、SkillExecutor、native qualification、worker/lease、资产/配置。实现若需越界，先下一轮实际 Astra。

后端新增接口（可使用同义内部 helper；公开名按下列固定）：

- frozen `ExecutionGuardBoundaryV1(kind: str, phase: str, episode_id: str, physics_step: int, operation_id: int | None)`；kind 为 COMMAND/CONTROL/PHYSICS/RETURN，phase 为 BEFORE/AFTER；仅只读描述。
- `MuJoCoPhysicsBackend.enforce_execution_guard(callback: Callable[[ExecutionGuardBoundaryV1], None]) -> context manager`，exactly one、同线程、loaded/reset episode；callback 正常返回仅允许这一检查点，异常表示拒绝并向外传播。无 observer 时也工作。
- `execution_guard_events` 返回 detached tuple，记录每次实际检查、effect 前后步骤、拒绝/主异常、stop secondary。它是诊断，不具有 authority。不得持有可变原对象。单会话最多1024条，额度耗尽按拒绝处理，不能静默丢事件后继续。
- 独立 guard callback 重入标志，由所有既有 mutation/step/observer registration 入口检查；BEGIN/END 被动 observer 保留原异常语义。guard 不作为 operation observer 注册。

研究接口：

- `OperationalExecutionGuardV1(owner, *, origin_token, deadline, backend)`：构造只接受真实 OC1 live handles。保留 exact backend/episode、owner/thread、原 deadline identity；每次 `__call__(boundary)` 用 `owner.read_current(after=origin_token)` 再 `owner.before_deadline(deadline,current)`，不能接受 caller now、布尔有效标志、可更新 deadline 或重复 setup。
- `cancel(reason: str) -> None` 为单向状态；cancel 后检查拒绝，不能清除。它只证明本诊断内取消，不宣称已接仓储取消/lease。
- `run_guarded_execution_diagnostic_v1(output: Path) -> dict[str, object]`：固定命令/步数/10秒预算，独占新目录；内部真实 `open_operational_clock()`，无传入 clock/backend/任意 action 的生产参数；CPU raw seam 只在测试 helper 使用。

## Task 1：守卫接入所有真实 effect 路径

- [ ] 写测试并先运行一次 RED。RED仅跑两个 feature-presence 测试：`test_execution_guard_api_required` 和 `test_operational_guard_api_required`，通过 `getattr/importlib.util.find_spec` 在 call 阶段断言接口存在；未实现时恰为两个预期 assertion FAIL，不能以 import/collection 错误充 RED。其余具体反例随后在同一GREEN范围执行，不为每条重复启动。
- [ ] 实现 backend guard，调用点必须满足：COMMAND 目标/队列/夹爪 ctrl 写入前后；CONTROL 包括 pending dequeue、target motion 与 ctrl 写入前后；**每一个** `mj_step` 前后。可把三条 physics 分支汇入一个原始推进 helper，但保持无 guard 的原 contacts/observer顺序。
- [ ] BEFORE 在 BEGIN observer 之后、实际 effect 之前；PHYSICS BEFORE 必须在 actuator observer 之后；AFTER 在真实 effect 后立即执行，且在对应 END observer/legacy callback 之后、对调用者返回前再执行 RETURN 检查。读取快照或通知耗时不能使检查过期后仍继续；同一操作重复检查允许，重复物理 effect 不允许。
- [ ] post 到期时先保留已完成 effect（实际总步数和 sim time、真实 command_records、尽力获得的 physics/control快照），再抛原拒绝异常，禁止下一步。即使 operation END 被标为失败，guard证据仍保留已发生作用，不能把它改写为零步或成功 receipt。快照失败另记 secondary，不覆盖主因。
- [ ] guard异常先锁定会话并离开 callback 重入区，再调用既有安全停止。HOLD 和 emergency stop 及其必要 CONTROL 不调用会失败的普通 guard；bypass 只限后端自身同步停止栈，不可开放给普通 COMMAND 或任何 mj_step，observer/guard callback 不得利用 bypass 重入。清空 pending、锁定 estop；任何 stop 异常保留 secondary，原 guard/物理/命令异常仍为主异常。
- [ ] 正常 context 退出也进入安全停止并封闭本次 backend 的 guarded lifecycle；失败/取消/关闭后不能重装、reset、initialize、step 或运动命令复活。同一个 backend 的读取、再次 STOP、shutdown 可用。对从未安装 guard 的 backend 不增加此限制。新诊断必须新 backend/新 assignment，不可用重建同任务刷新原预算。
- [ ] guard callback 或本体操作异常都永久封闭该诊断会话。活动会话下拒绝 initialize/reset/非停止 fault 注入，以防 episode/model/外力变更；STOP fault允许通过独立停止路径。不得提供通用 allow_expired/disable_guard 选项。

具体 tests（允许同名参数化）：

`test_precheck_blocks_command_control_and_all_step_paths`：COMMAND两种、CONTROL、三条physics分支分别拒绝；无新的运动接受/目标入队/mj_step，安全停止命令另计。

`test_callback_delays_rechecked_at_effect_and_return`：BEGIN、actuator、END、legacy callback 推进原始假时钟；到 effect 前过期则0 effect，到effect后过期则保留已发生且不成功/不后续步。

`test_post_expiry_retains_one_effect_and_stops_chunk`：第一步内原始假时钟跨deadline，step(3)只发生1次积分；计数/状态保留1，不能返回成功。

`test_stop_survives_guard_and_observer_failures`：guard拒绝、被动observer失败、stop附加失败组合；pending清除/estop可达或stop明确失败，主异常不被替换。

`test_guard_reentry_duplicate_and_closed_session_reject`：重入、第二注册、退出后 step/reset/initialize/重装拒绝，shutdown可用。

`test_no_guard_preserves_operation_order_and_state`：对照无guard现有顺序/命令结果physics_state+records，三条physics分支不多step。

## Task 2：原始 OC1 deadline 组合与一次真实诊断

- [ ] 实现 `OperationalExecutionGuardV1` 和 CPU 反例 `test_deadline_equality_identity_and_cancel_fail_closed`：<通过、=拒绝、+1拒绝、foreign receipt/current、owner关闭、clock倒退/identity变更、换backend/episode、cancel、重复/刷新deadline均拒绝；引用既有clock raw source，不改时钟模块。
- [ ] `test_diagnostic_scope_cannot_mint_native_authority`：仅输出独立 `guarded-execution-diagnostic.v1`，不存在 native可消费 receipt；固定scope、native UNKNOWN/full_horizon_producer UNAVAILABLE；既有读者常量不变。
- [ ] 写固定诊断入口并冻结命令/config/source pins后运行**一次**真实 node `tests/test_guarded_execution_v1.py::test_actual_mujoco_guarded_diagnostic_no_render`（不进入RED/GREEN节点集）。用实际MuJoCo、实际backend、真实BOOTTIME，禁止 monkeypatch engine/clock/guard verdict。

真实诊断精确顺序：

1. 创建独占新输出目录、预登记本计划SHA与当前源/asset SHA、固定 scene `S01_NORMAL_STATIC` seed0、headless、render_rgb=false、render_depth=false、record_video=false、domain_randomization=false、`physics_dt_s=1/240`。这只是显式诊断 dt，不声称旧默认浮点值等于精确1/240。
2. 真实owner `begin_event('diagnostic_allocation')`，写实际分配记录后 MARK/END，`start_deadline(task_key=唯一分配ID,origin=receipt,budget_ns=10_000_000_000)`。起点在初始化之前，初始化耗时计入，不能重置预算。
3. initialize/reset（无隐式settle）；记录episode/model pins。注册被动 operation observer 记录原始BEGIN/END，安装活guard。当前关节本体读取，提交一次等于当前测量的7关节targets，提交一次 `GripperCommand(open=True)`；不得以对象truth选动作，不关闭夹爪、不抬升/抓放、不调用IK。
4. `step(2)`，应真实2步、无CAPTURE/渲染、正常CONTROL/PHYSICS记录与live checks。最多两步，原始physics state/commands/guard事件原样保存。
5. 让真实BOOTTIME到达原deadline（有限轮sleep，每次≤20ms，最多到origin+11秒，进程总cap60秒；期间0物理步）。随后普通关节COMMAND应到期拒绝，再尝试 `step(1)` 应在执行前拒绝。总真实步数保持2；不要注入假时钟来“证明”到期。
6. 退出guard仍封闭；在外再一次 `step(1)` 拒绝、再次 STOP 可达，保存固定scope诊断结果、两次拒绝和终态。finally shutdown/close owner；主失败和持久化/cleanup secondary分列。

任何初始10秒耗尽、observer记录失败、步骤不等于2、意外渲染/额外命令、持久化不完整、环境漂移或异常均保留本次失败并停止，不加预算、不重跑。该node的“预期deadline拒绝”是诊断成功条件，不是新产品缺陷；任何非预期失败进入下一实际 Astra。

## 验证命令、额度和环境

复用冻结 R413 `bounded_stage.py` 及 r413_events/r235_startup_prerequisite，不改 supervisor。从已读 R429 `implementation/run_validation.py` 适配本轮runner：只换轮次、精确argv、新路径、pins；删除其自动追加的旧节点。所有阶段显式 `--junitxml`、禁cacheprovider、plugin autoload off、各自新basetemp、源pre/post核对和进程回收。无秘密env，保留 REAL_MOTION_DISPATCH_ENABLED=false；无服务端口。

**命令入口（工作目录项目根）**：

- `.venv/bin/python artifacts/research/process/20261004-ced-development/astra-rounds/round435-t7b-guarded-execution-20261105/implementation/run_validation.py red`
- 同命令尾参 `green`。
- 同命令尾参 `diagnostic`。

每阶段一次、不重试：RED cap120秒、GREEN cap600秒、DIAGNOSTIC cap60秒（实际物理2步）。固定argv见plan.json。GREEN包括已有 raw recorder 的真实无渲染2步 regression，此外全部为软件fixtures；两次真实无渲染backend会话累计4步，不把回归冒充新诊断。不得将新真实node隐式夹入整个测试文件运行两遍。

GREEN精确范围：新backend test全文件、新研究test排除actual node；旧 `test_operational_time_v1.py` 全文件、`test_visual_raw_recorder_v3.py` 全文件、`test_native_reset_capture_v2.py` 全文件；`test_operational_capture_v1.py`仅三node（real_interfaces_reset120_capture_current_chain_cpu、operation_brackets_capture_identity_and_denominator、cached_capture_preserves_empty_instance_sidecars_cpu）；`test_native_completion_horizon_originals_v1.py` 全文件；已有 `test_unsupported_native_bounds_stay_unknown_despite_claimed_valid` node。这里RESET120均为CPU raw seam，不是真实动作。

静态每项一次cap60秒：ruff check新/修改两个源与两个tests；ruff format --check相同四路径；mypy --follow-imports=silent两个源。runner也需按代码审查检查但不扩大到全仓格式治理。若旧backend整文件存在未变静态问题，保留准确基线、交下一Astra，不自动格式化历史代码。实施中可在首次正式静态前正常保持代码格式；正式失败后不静默反复跑。

前置：复核38输入SHA和HEAD关系；归档backend原件；保存当前源码/测试全量受控清单而不扫描gitlinks/日志；阶段pins明确old/new source世代，不覆盖旧清单的旧hash。检查Python/MuJoCo/NumPy依赖、Linux BOOTTIME/proc identity、磁盘≥1GiB、无冲突同项目测试/运行、source fresh、输出不存在。无需GPU/显示器/渲染库资源独占，不检查模型credentials。已有环境只读报告在intake，不能代替运行时检查。

## 完成、证据与剩余工作

- [ ] 三阶段原始spec/stdout/stderr/JUnit/events/exit/terminal/source pins都保留，setup/call/teardown与预期相符、无skip/额外node/残留子进程。不预填固定通过数量；从实际collected inventory核算。
- [ ] 逐项审阅Task1反例与真实2步/到期后的0额外步、命令denominator。保存primary/secondary、expected negative、已发生effect、stop/closure结果。
- [ ] 独立实际Astra审查精确diff、测试与诊断原件；有新根因/扩范围/计划外失败先下一轮计划再修。
- [ ] 输出step-report与phase-summary：软件通过、本轮实际无渲染diagnostic通过/失败、native UNKNOWN、full-H producer UNAVAILABLE、完整native执行guard NOT_PROVEN、几何/运动来源缺失、正常抓放链未完成、正式研究未验收分别列明。可称“本轮诊断 COMMAND/CONTROL/PHYSICS deadline守卫已实测”，不能改reader正式guard状态。
- [ ] 已验证交付明确路径commit/push研发分支，核对本地/上游/远端SHA；保护历史与gitlinks。无完整raw/DB远端包则如实区分，清单不能冒充复现包。

下一块是在此执行接缝上由真实应用/worker owner签发完整H会话，接通原lease/cancel/hard-stop、观测消费TTL、真实单一recorder和真实controller动作/补足H，再完成独立几何与联合误差校准。本轮不把未知写成VALID，也不再新建一个仅离线审计器当作实际执行交付。
