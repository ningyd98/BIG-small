# R439 完整执行入口与独立校准 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline。ROOT 单写共享产品；本轮仅在整项新改动完成后做一次 fresh 独立审查。每项勾选须附原始证据，不能仅凭计划标记完成。

**Goal:** 补齐真实应用/worker 签发的完整八动作执行与采集入口，首先产生一个独立分配 FULL 组并由独立 reader 重算，为九独立组件和在线 native 三消费者提供真实来源。

**Architecture:** 新增限定 TEACHER_COLLECTION 应用，复用真实 SimulationWorker、SQLite 作业/lease、OC1、唯一 MuJoCo backend、既有 SkillExecutor/grounder/Shield。共享 full-H 执行器保持 controller 原返回，补足注册 nominal horizon；同一 recorder 保存原 D/S/COMMAND/CONTROL/PHYSICS/CAPTURE/动作与失败。独立 reader 重建八动作 G/U/L/M/C，旧 raw、UTC reader 与诊断结论不转换。

**Tech Stack:** 当前 Python 环境、MuJoCo 3.3.7、OpenCV、现有 Memory/SQLite 来源协议、R413 bounded_stage。

**Spec:** `artifacts/research/process/20261004-ced-development/astra-rounds/round91-native-full-action-support-20261007/design.md`；`docs/superpowers/plans/2026-10-07-t12-sol-execution.md` P4–P8；`docs/superpowers/plans/2026-10-22-post-opening-development-plan.md` Tasks 2/3。这是执行已选设计，不重新发起设计批准。

**身份/基准：** actual `gpt-6-astra`，2026-11-07；输入 HEAD `8534419b7e22396985f66d1b0f2714fe8e16e5fb`，main `fdb2e94d3d7bc041e7d958f2514a08406fad4668`。本次规划只读取源文件/元数据并写本目录；产品修改、测试、模型请求、physics/render 和 Git 写操作均为 0。R438/ROOT 的既有提交推送独立处理。

## Global Constraints

- 当前用户指令“推送，完整执行入口与独立校准”授权执行本计划，不额外要求设计确认。新根因、计划外失败、范围扩大仍须实际 Astra 下一轮；下列明确 RED 是预期失败。
- `CHECKPOINT_D_FULL_S` 来自固定注册工厂；future wall bound 为 NOT_REQUIRED_FOR_THIS_RECIPE/None，绝非 0 或硬完成保证。显式 FULL_FUTURE_D_REQUIRED 及旧 UTC 路径缺 H_D 仍 UNKNOWN。
- 原 5 秒观测/条件消费 TTL、接收规则、任务/lease/cancel/hard-stop 保留。等值 TTL 允许、+1ns 拒绝；deadline 等值拒绝。不得把旧帧每物理步重新消费，也不得删原消费点。
- 八技能严格为 MOVE_ABOVE、APPROACH、GRASP、LIFT、MOVE_TO_REGION、PLACE、RELEASE、RETREAT。HOME 不加入认证。capture_step=dispatch_step；重新采集后必须重新 grounding、payload/Shield，不能改旧时间。
- C=max(G,max_i(U_i+L_i+M_i))，完整控制点/八顶点及注册保持区间取最大；不能将不同点的分量最大值随意相加改配方。coverage=0.9；九独立 component 时取组件最大；缺组、缺帧、UNKNOWN、失败、缺完整 H 均 infinity。q<=0.01m 才有数值资格，单组始终没有 q 资格。
- 所有 truth 只进入离线 raw/评价器；在线参数仅像素、本体和注册常量，使用同 grounder/controller/Shield。旧 `run_teacher_episode` 直接用 truth target，不能作为本采集器的命令生成器。
- TEACHER_COLLECTION 是工厂私有能力，scope 字符串、public bool/q、caller source hashes、allow_uncertified 不授权限；收集试验不能自己启动 native VALID。旧 raw、日志、冻结文件、两个脏 gitlink 不改不扫描。无真实硬件、云调用、模型下载、九组批量或宽测授权。

## 原始问题证据与根因

完整证据定位及 SHA256 在 `intake/source-index.json`；`intake/findings.json` 保存逐项静态原始片段。R435 phase-summary 明确 full-H producer=UNAVAILABLE、完整 native guard=NOT_PROVEN、native=UNKNOWN；R437 162 PASS 和 2 步诊断是已有范围，不能代替本任务。

1. `guarded_execution_v1.OperationalExecutionGuardV1` 仅独立 OC1 deadline，固定诊断 scope，最多1024读数；backend `_check_execution_guard` 在1023项停止。正常 full-H 必然超过该诊断容量。不可复用诊断类改标签。
2. `completion_horizon_rational_v1` 已有严格整数/rational 算法；`native_completion_horizon_originals._Audit.action_window` 明确仅支持 MOVE_ABOVE/APPROACH。`native_completion_calibration` 只是公开数据纯 reduction；`native_completion_originals` 仅 observed-return，三项 provenance/full-H unavailable 是真实限制。
3. `OperationalPrefixApplicationV1` 固定 RESET120+capture，无动作；`OperationalWindowOwner._prepare_startup` 明确排除该 prefix。旧 prefix 工厂不能靠换 config/scope 变成 full collector。
4. `VisualRawRecorderV3.bind_source` exact VisualOriginalPlan；其现有 bind_worker_source 按 UTC job/lease 读取，不能直接消费 LocalVisualOriginalPlan。新 source bridge 必须验证当前真实工厂/lease，再单独保存本轮 operational envelope，不能放宽旧类型检查或伪造当前 owner。
5. `backend.step` 内控制器批量推进；观察回调禁止 backend capture 重入。完整 max gap .005S 需要后端在每次物理 END 后、下一 CONTROL 前主动采集，而不是另加推进者或在 observer 中取消重入保护。
6. controller `_move` 可提前成功，GRASP 无 target_pose，LIFT 自带 .5S hold，RELEASE 只证明 gripper open。没有正常完整窗口 wrapper/端点绑定/独立落稳检查。
7. `research/native_calibration_collection.py`、`scripts/collect_native_calibration.py` 和 operational calibration config 尚不存在。不能将工作替换为另一份离线审计报告。
8. 成功 COMMAND 的 `physics_state`/`command_records` 已存在，本轮不以该旧误判改 backend。

## Review Focus

- 早返回/异常/晚 deadline：原动作结果与已发生 effect 保留，padding 或后置失败禁止成功闭合（T1/T2）。
- chunk 内每一步采样与噪声 RNG：采集不 step、不改控制/pose；注册采样日程在 future online 同样执行，不能暗换噪声域（T1/T3）。
- 伪造/复制/跨线程/跨 episode 工厂能力与重复 assignment：零新动作、不得复活 lease 或刷新截止（T2）。
- LIFT 尾部重复计算、RELEASE 缺 PLACE binding、姿态仅中心点：严格来源/完整八顶点，失败 infinity（T1/T3）。
- 组连接、丢帧、同 seed/raw 重用及有限 caller q：完整分母与原字节独立重算，单组永无 native 权限（T3/T4）。

## 有界执行总则和工件

ROOT 新建本目录 `implementation/run_stage.py`、`implementation/commands.json`，只实现下面固定命令白名单；复用 R437 runner 和 R425 green spec 的环境约定及**不修改的** R413 supervisor。每一阶段 fresh directory、attempt=1、无 retry；无 collect-only、无额外 preflight physics/render。pytest 均加 `-p no:cacheprovider -p r413_events -p r235_startup_prerequisite --tb=short --basetemp=/tmp/bigsmall-r439-<stage> --junitxml=<stage>/junit.xml`。目录已存在即拒绝；结果要有完整 setup/call/teardown、returncode、reaped/no remaining_live/source_drift。

命令入口统一 `.venv/bin/python <R439>/implementation/run_stage.py <stage>`，其中 `<R439>` 为本目录。完整展开 argv/env 与 pin 清单在首次运行前落盘。RED 300s；每 T1/T2/T3 GREEN 600s；最终 regression 900s；每 static 120s；prepare 120s；first-full 1800s；independent-read 900s。outer 各多120s用于监督清理。阶段串行；前一失败立刻停止其依赖，不换名重跑。

输入核对：逐项比对 source-index；baseline HEAD 若只有 ROOT 的交付文档变动，用路径差异证明非重叠。product pin 变化则重新核对本计划，不静默更新 expected hash。实现后每阶段冻结所有运行 imports、配置、测试、runner、插件、资产 SHA（排除巨大历史/嵌套 checkout），测试及 actual 同一 generation；actual 前无源码再改。预期新增文件标 MISSING_BEFORE_IMPLEMENTATION，禁止用空文件伪造 pin。保存每步 report 和最后 phase-summary，区分 software、actual、formal。

### Task 1：可供实际 controller 使用的完整 H 基础（最先完整实施）

**Files:** 新 `src/cloud_edge_robot_arm/simulation/mujoco/native_horizon.py`、`tests/test_native_horizon_execution.py`；限定修改 `simulation/mujoco/backend.py` 的 guard capacity、step 内采样接缝与生命周期；新增 `tests/test_mujoco_full_horizon_sampling.py`。不改 controller/SkillExecutor、旧诊断类或 rational 配方。

**Interfaces:**
- backend `enforce_execution_guard(callback, *, event_limit: int = 1024)`：strict int，1024..500000；原默认/overflow行为不变，closed/STOP预留至少1条；limit不是授权。任务能力冻结更大的精确容量，溢出失败而非丢记录。
- backend `capture_each_physics_step(*, max_captures: int) -> context manager`：仅当前 owner thread、已有唯一 operation observer 和 active guard 内可进入一次；1..32768；退出不可重用。后端自己在每物理 END/旧step observer结束后调用现有 capture 方法，CAPTURE前后重查 guard；包括内部 chunk，禁止额外step或控制写入。frame只流入现有 recorder，不返回给 controller。采样/记录错误关闭 guard；STOP豁免仍精确为原内部 CONTROL。
- `NativeHorizonSession` 构造只由 T2 私有工厂签发；T1 暴露纯内部 `_run_registered_horizon(*, backend, robot, executor, recorder, contract, step, grounding, horizon, check_active) -> FullHorizonExecutionReceipt`，此函数不授权限，T2不可把它公开成绕过入口。receipt frozen，含controller_result、dispatch/return/terminal steps、execution/hold/tail/wait intervals、complete/reasons、original identity/hash。`check_active` 为T2私有闭包，public传入函数不能获得线上能力。
- 执行顺序：登记 span→同一 recorder.execute_attempt→成功才保持原 actuator target 并逐步补至 dispatch+N→新 terminal capture→完成 receipt。禁止 `hold_current_joints()` 重新目标化早返回动作；保持实际控制器终点 target。失败不 padding，超过 N 失败，padding 内 hold loss/expiry 保留完整部分原件。
- Horizon：先用原骨架 timeout/expected 与注册附加尾部计算 H，再由工厂在**原 plan 签发之前**冻结有效 owner requirement=H。再次计算时 `builtin_tail_included=True` 仅适用于 LIFT/RELEASE 且配方分项证明已包含；不能把 total H 又加 tail。controller既有 LIFT实做尾部单独计账；RELEASE 至少在实际打开后连续1S稳定观察，不能将打开前步数计入。无尾技能 included=False。

- [ ] 写T1两个RED API存在性测试 `test_full_horizon_session_api_required` / `test_backend_full_horizon_sampling_api_required`，用 getattr 断言而非import收集错误；运行 `t1-red`，恰好2个 assertion失败为预期。
- [ ] 实现接口与CPU假 backend 用例：early success精确补足；失败0 padding；超N失败；LIFT不重复尾部；RELEASE打开后完整tail；deadline等值拒绝/晚返回已发生step保留；chunk采样每步一次；采样不改变qpos/ctrl/target/step；observer中写入仍拒绝；limit边界与500001/bool拒绝；第二sampler/foreign thread/closed拒绝；渲染失败STOP原因保留。
- [ ] `t1-green` 一次：两个新测试文件及 `tests/test_mujoco_execution_guard_v1.py`。新测试必须全部fake engine，无MuJoCo初始化/render。本阶段 real physics=0、render=0。
- [ ] 保存步骤报告与T1差异 pin，不把此CPU结果称 producer已可用。

### Task 2：真实工厂、单一 recorder 与 collector 三入口

**Files:** 新 `research/native_collection_application.py`、`research/native_full_horizon_recorder.py`、`research/native_calibration_collection.py`、`scripts/collect_native_calibration.py`、`configs/research/native_operational_calibration.yaml`、`tests/test_native_calibration_collection.py`、`tests/test_native_collection_authority.py`。限定修改 `simulation_runtime/worker.py::_run_visual_closed_loop` 加**exact新应用**私有分派；`vision/raw_recorder_v3.py` 仅增加供新子类调用的保存/原动作跨度接缝，不放宽旧 bind_source/旧读入；T1模块内部 capability连接。旧 prefix/capture/operational_windows/lease源不改。

**Interfaces:**
- `NativeCollectionApplication.from_startup(protocol: Path, *, assignment_id: str, output: Path)` → private live实例；`prepare_once()`、`execute_once()`、`check_active()`。仿照现工厂 registry、copy/pickle拒绝、同PID/thread/exact worker/SQLite/live origin/唯一RUNNING attempt/lease/job immutable核查；不继承或伪装旧 prefix。构造不执行physics；execute_once只走现 worker.poll_once。scope固定TEACHER_COLLECTION，worker启动分派互斥prefix/online/custom。
- `NativeFullHorizonRecorder` 继承 `VisualRawRecorderV3` 并用**一个**operation callback tee BOOTTIME事件；私有app签发并核对 backend/capture/executor。独立 `bind_collection_source(application)` 读取当前SQLite assignment/lease/open attempt、真实RESET和注册工厂原plan，生成新 operational envelope；不把 detached VisualOriginalPlan 当活权限。分配在操作之前，所有失败与partial都有库存；单次输出原子写、不覆盖。每action boundary保存live owner/lease/cancel/hard-stop读数；每physics/command/control/render/return检查原任务deadline、当前租约、撤销和硬停。把旧UTC lease额外veto明确记录为保留，不能称其全域迁移完成。
- OC1 clock在新应用 prepare_once 的实际 owner thread 创建；在唯一 assignment enqueue 之前真实 mark 一次 COLLECTION_TASK_ORIGIN 并签发1800s deadline，作为本次教师原合同的D预算起点（排队也计入）。后续同线程真实worker.poll_once/lease与 `_active_task_origin` 原样记录并join该既有事件，不把MONOTONIC/UTC换算或回填成BOOTTIME，不能在worker入场或第一动作重新计时。该更早D预算和原worker timeout/lease并行约束，二者任一耗尽即拒绝。development collection job预算独立1800s；观测消费仍5s。当前factory注册内能力只允许固定八动作骨架，参数由现deterministic grounder/visible marker+本体推导并过 `research_safety_shield`。不调用旧truth teacher target，也不调用 require_native_action_evidence再谎报VALID。收集器记录 `native_qualification=UNKNOWN; collection_authorized=true`，这不是在线执行权限。
- 沿总计划三函数：`prepare_native_calibration(config: Path, *, output: Path) -> dict`；`collect_native_calibration_once(protocol: Path, *, assignment_id: str, output: Path) -> dict`；`verify_native_calibration_collection(protocol: Path, *, output: Path) -> dict`。CLI互斥 `--prepare-only/--collect-once/--verify`，collect强制一个assignment，不支持batch/retry。
- prepare固定注册schema `native.calibration.operational.v2`、recipe、dt rational=1/240及float(1/240)编码、现顶视320×240/现资产标记与noise/controller/grounder hashes、全部八动作/分项/完整点/保持条件、九assignment `native-r439-0001`..`0009` seeds439001..439009、先验ancestor/pool isolation和总分母；只0001本轮能运行，其余PREASSIGNED_NOT_RUN。现有scene域常量从当前S01配置读取并冻结，不按结果调参数。model requests=0。
- 运行能力本身不让completion q、source flag、任意回调进入policy；TEACHER_COLLECTION与未来 NATIVE_EXECUTION是不同private发行者，后者仍未实现/未开放。不伪造RoleRuntimeBinding或云probe。

- [ ] 写 `test_collection_prepare_api_required`、`test_collection_factory_api_required` 两个API RED，`t2-red`恰2 assertion失败。
- [ ] 实现并测试 prepare无backend/physics、fresh输出、每assignment原子一次性登记、第二attempt/restart拒绝、public scope/伪造app/替换worker/lease/source/原deadline拒绝、正确poll入口可到共享runner、guard每effect检查、TTL新帧不重置任务deadline、truth sentinel命令生成无法读取、旧UTC/prefix保持原行为、错误/清理错误都进入partial且状态不可PASS。
- [ ] `t2-green` 一次运行两个新文件及 `tests/test_visual_raw_recorder_v3.py`、`tests/test_visual_raw_recorder_transform.py`、T1新文件。这些测试禁止新actual初始化；若既有测试存在真实初始化，运行前静态列明并从此CPU阶段排除对应节点，不静默消费actual。
- [ ] 步骤报告必须展示 source工厂→worker→live lease→唯一recorder→原grounder/Shield→既有executor→fullH 的调用链；任何缺口是产品待实现项，不能用审计sidecar替代。

### Task 3：全八动作原字节独立 reader

**Files:** 新 `research/native_full_horizon_originals.py`、`tests/test_native_full_horizon_originals.py`；限定修改 `research/native_calibration_collection.py` 的verify衔接。复用不修改现 `native_completion_horizon`、metric/reduction与旧reader。

**Interfaces:** `read_native_full_horizon_group(protocol: Path, *, assignment_id: str, root: Path) -> FullHorizonGroupDiagnostics`；`reconstruct_native_full_horizon_registry(protocol: Path, *, roots: Mapping[str, Path]) -> CompletionCalibrationDiagnosticsV2`。只读bytes，不导入collector工厂、不读live DB、不执行backend、不接受缓存分数/给定PASS。新增schema分别保留 `source_complete`、`horizon_complete`、`geometry_complete`、`physical_outcome`、`group_score`，不把UNKNOWN换为COMPLETE。

- 原件从预登记inventory开始，验证全部哈希/独占分配/RESET、OC1 domain与原期限、lease/owner/episode、每COMMAND/CONTROL/PHYSICS/CAPTURE、所有action/hold/wait/terminal及精确join。旧RawV3结构/物理一致性仍验证；其UTC unknown保留在legacy_utc字段，新operational链单独重建，不屏蔽旧reason来伪造通过。
- 所有分配帧重新decode，max gap<=.005S，不能只读terminal。已有geometry helper可以复用但不继承observed-return的资格。GRASP p来自同capture本体；固定参考LIFT/RETREAT/region必须核对exact payload；RELEASE从对应已成功PLACE binding+注册grasp刚体变换重建八顶点，任何缺口infinity。
- 每一分量逐点算、保持区间逐物理步取max；LIFT独立物体高度>=50mm持续>=.5S，RELEASE目标区稳定>=1S。动作success/夹爪开闭不替代这些。G全帧、命令/真值分离、所有失败保留。fingerprints/ancestor共享必须连接，未运行八组仍保留分母；九components下rank=9，单组joint_bound=None。

- [ ] `test_full_group_reader_api_required` 为 `t3-red` 唯一预期assertion失败。
- [ ] 实现最小完整八动作原字节fixture与反例：每一必需原件删除/改字节、owner错序/expired、padding混入下一动作、one-step缺口、tail重复/不足、缺PLACE/旋转八顶点、truth进payload、帧UNKNOWN、缺组/祖先/原始图复用、caller q无效、单组不可认证。
- [ ] `t3-green` 一次：新reader测试、`tests/test_native_completion_v2.py`、`tests/test_native_completion_calibration_v2.py`、`tests/test_native_completion_horizon_v1.py`、`tests/test_native_completion_horizon_originals_v1.py`、`tests/test_native_completion_originals_v2.py`。全部CPU原件fixture，actual=0。

### Task 4：完整入口软件收口与第一个真实 FULL 组

- [ ] final-regression一次只跑本轮全部新测试+旧 `test_mujoco_execution_guard_v1.py` / `test_guarded_execution_v1.py`（排除 `test_actual_mujoco_guarded_diagnostic_no_render`）+T3列出的五文件+T2两个raw recorder文件。禁止整仓suite。用最终已固定测试选择清单核算真实engine初始化数量；未声明actual节点不得混入。R437诊断不重跑。
- [ ] static各一次：`.venv/bin/ruff check <全部本轮产品和测试py>`；`.venv/bin/ruff format --check <相同清单>`；`.venv/bin/mypy --follow-imports=silent <本轮产品py>`。实施期间可format这些文件一次，静态失败属于新计划外失败。
- [ ] 一次fresh reviewer审查整个新差异、scope、authority/fullH/observer/reader和完整命令；发现新根因进入下一Astra，不为每个小步骤重复独审。
- [ ] prepare一次：`.venv/bin/python scripts/collect_native_calibration.py --config configs/research/native_operational_calibration.yaml --output <R439>/actual/protocol --prepare-only`。必须先写source hashes和九组完整assignment，再创建actual。prepare没有physics/render。
- [ ] first-full唯一一次：`MUJOCO_GL=egl .venv/bin/python scripts/collect_native_calibration.py --protocol <R439>/actual/protocol --assignment-id native-r439-0001 --output <R439>/actual/native-r439-0001 --collect-once`。
- [ ] 独立read唯一一次（失败partial也读，但不扩组）：`.venv/bin/python scripts/collect_native_calibration.py --protocol <R439>/actual/protocol --output <R439>/actual/readout --verify`，在新进程、collector关闭后读取冻结原bytes；没有q/scoring缓存输入。

**实际运行前置与计数：** 冻结的原八动作配方/完整geometry/grasp transform/相机和现可见标记必须有可定位注册来源；未找到的常量禁止猜测，返回确切缺失source并下一Astra限定补齐。ROOT静态读现有registration/config即可，无probe模型/renderer。全部软件+独审通过、fresh SQLite/current worker lease/OC1 BOOTTIME可用、EGL/既有依赖可用、无并行GPU/physics任务、剩余磁盘>=32GiB。主限额 wall1800s，outer1920s，原始输出<=16GiB，进程RSS<=8GiB；读出900s、RSS8GiB。无网络/云请求，无重试/补样。

physical预算由prepare计算，必须冻结具体数：`120 settle + Σ(八动作N_total) + 已登记非动作推进`，上限32768步；未登记等待0。每步恰一个原RGB-D acquisition，额外capture仅八次pre-dispatch及八次terminal；pre帧可复用同step刚采frame但必须登记明确身份，不重复伪造capture。总 acquisition上限 `physics_budget+16`，各capture内部RGB/depth/instance pass分别计数，backend `_update_sensor_frame` 隐含渲染也要静态纳入预预算并记录真实计数；不得把三pass写成一次物理step。超过任一资源或真实action/guard/source/geometry失败立即停，保存raw/partial；未执行项缺失作为infinity，不执行其余八组。真实组正常结束后仍只有 source/fullH/单组数据证据，不是9组件校准/native VALID/G1。

### Task 5：本轮之后完成标准（不可默认为本轮批量授权）

这是完整目标的依赖出口，不是虚构已实现路径。首组reader source/horizon/geometry全成立且物理结果符合注册条件后，依据其**真实**wall/render/字节/RSS制定下一 actual Astra 有界扩组计划；最多八个剩余预分配组，source/recipe变化则旧组保留并明确注册世代，不能静默混合。finite joint q<=.01还要所有独立组件条件满足；不满足保持UNKNOWN。

随后按R91/P8实现 private `CertifiedNativeArtifacts`/启动完整认证、当前活app/worker/registry generation、共享fullH runner与PRE_SAFETY/PRE_SKILL/POST_EFFECT统一consumer；分别固定Memory/SQLite正链的新assignment实际验证。此处源码涉及 native_calibration/action_evidence/execution/worker_runtime/operational_windows，**不在本轮允许修改集合**，须拿本轮完整source证据制定限定计划；不从teacher capability强转native。验收必须含正常观测→资格→提交→启动→完整H→视觉效果和独立物理效果，成功率≥90%与正式实验另立分母。

## 交付、停止条件与自审

每T1/T2/T3报告列原失败、改动、验证、实际计数和剩余依赖。T4保存assignment、原件清单、独立reader、source-generation、resource report、phase-summary。明确远端只交显式源码/测试/计划/小型派生证据，完整raw/运行DB按既有本地边界，不声称可远端完整复现。ROOT按明确路径提交/推送研发分支并核对local/upstream/remote SHA，不改main或gitlinks。

本计划自审：八动作/R91联合metric/完整H/旧未知/真实source/教师与native隔离/逐步记录/单组先行都有任务；第一实现T1具有明确接口、测试和0actual界限；T2明确实现source而非只审计；T3不重写旧reader；T4只有一个FULL assignment，异常保留；九组/P8正链明确未授权批量且未完成。实现前可整理同范围内部命名，但不得将私有工厂权限变公开flag、改变源码范围/注册常量/测试额度；不再以重复宽测或仅新增报告当成完整入口。

### T2 补充：pilot 原合同、角色与首帧来源（不是未实现前置）

新增 `research/native_collection_grounding.py` 与 `tests/test_native_collection_grounding.py`，归入T2同一次GREEN/最终检查。它是需要本轮实现的 bootstrap adapter，不依赖旧role清单“恰好仍有效”。

- 固定教师角色描述 `native.teacher.collection.role.v1`：instruction=`Move the red block to the green region.`，object=`object`，region=`target_region`，scope=TEACHER_COLLECTION，model/provider为None、模型调用0，current source inventory、完整geometry/grounding/Shield版本和八技能骨架。描述digest作为本轮 original 的 role_bundle_hash；它不实例化/冒用 RoleRuntimeBinding，不宣称云角色资格。真正权限来自上节actual app/worker/lease私有发行。未来P8使用真实RoleRuntimeBinding另行接通，不能复用此教师角色授native资格。
- `build_collection_contract(*, assignment, current_owner, geometry, source_hashes) -> VisualOriginalPlan`：使用产品 TaskContract/TaskStep 与 `freeze_original_visual_plan`，不从测试fixture导入对象。task/plan/job/worker/lease/attempt/episode IDs由实际source生成。固定八技能顺序同上，retry_limit=0；timeout_ms与expected_duration_ms均为 `[8000,8000,1000,8000,10000,8000,1000,8000]`，沿既有teacher时域并为RETREAT用同运动预算；禁止取teacher truth target。LIFT额外.5S、RELEASE额外1S，wait=0、settle=120。dt=1/240，原始基础8动作和=52S，尾部1.5S，动作总12840步，加settle=12960步；derived owner full-H逐动作冻结且验证无重复tail。这些是新collect assignment自己的原预算，绝非修改旧运行deadline。
- 预/后置条件来自原 canonical 条件模型：可见目标/有效深度/夹爪与持物/对应上方、接近、抬升、放置、释放等完整要求，保留required sensor rgbd和allowed_error=.01，消费max_age=5s。调用同 `research_safety_shield` 构造其已有hard_limits；不得通过清空条件/降低安全限值将UNKNOWN改成功。教师允许缺**校准数值资格**，不允许缺像素身份/可见性/真实必要条件。无法满足就保留该组失败。
- `collection_grounding_inputs(observation, robot_state, registration, *, tracker) -> GroundingFrameInputs`：首次 marker7检测和注册marker_to_object变换给对象几何估计，将估计对象中心投影回当前RGB-D选择真实可见内部像素；目标区按注册绿色身份在同帧识别，使用现OpenCVTargetTracker几何/身份判定及 `resolve_top_grasp`。支持平面由注册桌面高度/当前RGB-D核对，绝不从physics object pose读取。后续沿 `execution.prepare_worker_step` 同一 OpenCVTargetTracker `_geometry`、像素身份、top-grasp固定offset和本体pose，再调用现 `_resolved_parameters` / `bind_step_grounding`。注册policy参数保持现实现：tcp_velocity=min(.15,contract safety max)、acceleration=.5、clearance=.10、minimum_height=max(.16,safety minimum)。GRASP参考本体，RELEASE绑定真实PLACE receipt。
- 实际 geometry registration 由现资产 `assets/robots/franka_panda/scene.xml`（已注册v2 SHA）、`top_grasp.CURRENT_GRASP_PROFILE`、marker/相机MJCF常量生成并由 `NativeGeometryRegistration.validate_asset`重验。注册值object half extent=.035各轴、marker7/size=.045、marker_to_object平移(.1,0,.03505)、object_to_tcp=(0,0,.01)、tool_to_tcp=(.105,0,0)，完整contact/八顶点从此几何生成；这些值须与当前asset/profile严格匹配，不将测试fixture当来源。camera intrinsics/extrinsics由既有camera配置/注册公式推导预登记，第一真实frame逐项比对，不能事后把frame内容回填成事前注册。若现资产真实不匹配，停止并报告确切冲突；不是预先以“缺现有registry”停止实现。
- 为防首次像素bootstrap偷读truth，T2新增测试：backend truth属性/instance segmentation/scene object坐标全部设为抛错sentinel，fixture RGB-D与固定registration仍可生成grounding；移动/旋转输入像素仅按像素几何变化，真实状态只供应TCP/夹爪。本模块无动作执行权、无新controller。
- 固定12960步可在本轮32768上限内执行；每步capture加16边界capture=12976预算，backend隐含sensor更新渲染额外真实计数由prepare从控制器调用图逐项上界计算并写protocol，不能遗漏后隐式加跑。全程保存全部原帧，若内存/磁盘/wall cap不足则partial/infinity，下一轮据实处理，不降低采样频率。
