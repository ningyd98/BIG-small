# V3 原27成功离线闭环回归 Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans 按任务执行。用户已说“开始”，父任务可实施阶段1–3；本 Astra 子任务只写计划，不修改生产代码、测试或脚本，不再要求用户选择技术路线。

**Goal:** 在标记歧义修复后审计 V3 全40例、589帧，并用冻结模型输出驱动原27成功例的新 MuJoCo 组件闭环，保留原有安全与评价语义。

**Architecture:** 从 `run_component_episode` 机械提取唯一共享组件核心；线上入口继续模型、角色、租约准入，离线入口仅提供冻结规划准备器和本地取消/截止控制。新采集、解码、grounding、SafetyShield、执行器、hard-state、settle、末帧和物理评价均走同一个核心。

**Tech Stack:** Python共享 .venv、OpenCV ArUco、NumPy、Pillow、pydantic、MuJoCo headless EGL、pytest。

**Spec:** 用户“开始”授权阶段1–3及父任务本轮精确委派；实际规划模型 **gpt-6-astra**。状态 **PLAN_ONLY_NOT_IMPLEMENTED**。不授权公开推送、新付费实验、真实 Molmo/Sol 推理或硬件。

## 已查证事实和基线

- V3目录：`/home/ningyd/Documents/Codex/2026-11-14/x20-gpu-nvidia-smi-nvml-gpu/outputs/next-round-repair-40-20261115-v3`。每例有自己的 `raw/`、`before/`、`after/`、`component/frames/`；批次根目录没有公共 `raw/`。
- 隔离源码：`/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall`。创建基点为 `5e68e2f9f1ed7d865f483f41534dec9404c83394`；本次取证时父任务已合法推进 HEAD 到 `57c4dc0d855f5410fcf497edf47b43cfd24ad74b`。必须按文件字节和批准变更判断，不把父任务已有本地提交当未知漂移。
- V3 `verification.json` 声明40例完整、27 component_success；本任务独立核对 `batch-result.json` 名单为10 fixed＋9 development＋8 held-out。原13失败为9个 RGBDModelCallFailed、3个 HARD_FINGER_LIMIT、1个 CONTROLLER_FAILURE:UNREACHABLE，不要求本轮把它们改成成功。
- 实际枚举589个 observation.json。本任务把2945个帧相关文件和1478个模型 raw 文件的实际 SHA256/大小与每例冻结 manifest 对照，全部一致。`frame-inputs.json`、`model-record-inputs.json` 记录绝对路径与 SHA；不复制全部大体积 raw。
- 父任务此前完整运行 V3 verifier，确认7041证据、594源码、11388历史冻结文件和40例物理重算 PASS；这是父任务已执行事实，本 Astra 未重复整个验证器。
- 原成功例 `fixed-042001` 的 `post-06-release`、`pre-07-retreat` 原本就是 UNKNOWN。`_ground_component` 在完整目标几何存在时无需标记；在已抓取运输阶段可使用可见支持和抓持反馈；因此 UNKNOWN 数量不等于执行回归数量。
- 真实循环在 `sol_molmo_components.py`：同一 `action_contract` 和 `step` 同时交给 SafetyShield 与 SkillExecutor；PRE 在执行前，POST 在控制器成功返回后、settle前；逐物理步 `check_component_hard_state`。旧 `verify_next_round_repairs.py::_simulate_episode` 直接调用 executor，没有该 PRE/POST，不能作为本次闭环验收。

**已知失败来源：** 上一 Astra 轮次原始合成 ID7＋ID0 断言 exit1，父任务正按该计划修复。本轮新的问题是旧离线工具不能提供要求的安全路径与27例覆盖；该结论来自带SHA的源码检查，**不是**已经运行并失败的新27例实验。所有阶段3运行结果目前待实测。

## 输入、所有权和运行前置条件

`inputs.json` 绑定相关源码、模型资产、V3汇总、原始源码归档和上轮计划；`case-inputs.json` 绑定40例结果、component episode、物理证据、两阶段规划、scene/role/job；`episode-manifest-bindings.json` 绑定40份 manifest。快照位于 `input-snapshots/`。完整源码字节归档 `source-bytes.local.tar.gz` 仅本地保存，SHA为 `6fde448feedd3748a0943f28d01197dc66050bd65f4625767af8f3a97294061d`。

父任务独占修改 `pose_markers.py` 和 `test_pose_marker_evidence.py`；它们在 inputs 中标记 `expected_authorized_change=true`。阶段3开始前读取阶段2最终GREEN、SHA和diff，写新实施回执，不覆写本计划，不与父任务抢写。其他源先核对本计划 SHA；预期阶段3重构仅限下面清单。

共享解释器 `/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python`。`runtime-imports.json` 记录已导入版本；本任务没有启动渲染器。执行器必须先进行独立 headless 小样：`MUJOCO_GL=egl` 在导入 mujoco/OpenGL前设置，保持V3相同320×240顶视相机、资产、1/240 dt、seed、domain_randomization=False、深度噪声及采集次数。EGL/Mesa/驱动与权限必须可用；失败时保存原错并交Astra，不能切换相机、关深度噪声、改渲染参数来求通过。

所有命令 `PYTHONDONTWRITEBYTECODE=1`；pytest `-p no:cacheprovider --basetemp=/tmp/<唯一目录>`，Ruff `--no-cache`，其他缓存指向允许的/tmp目录。新隔离树写权限由父任务办理。历史V3、Gemini工作树和历史冻结目录只读；输出独占创建于新树 `artifacts/research/process/20261115-v4-marker-ambiguity/offline-regression/<run-id>/` 或/tmp，禁止在失败后覆盖同名目录。每例新进程顺序运行，保留所有退出码和错误；不得从20例旧成功集合取代原27例。

## 限定文件范围

| 文件 | 允许修改 |
|---|---|
| `src/cloud_edge_robot_arm/research/sol_molmo_components.py` | 机械提取共享闭环和准备结果类型；线上入口委托；不改 `_ground_component`、hard-state、安全规则或执行顺序 |
| `src/cloud_edge_robot_arm/research/sol_molmo_offline_regression.py`（新） | 严格读取冻结输入、589帧审计、冻结规划准备器、本地截止/取消、27例结果核验；不写第二个动作循环 |
| `scripts/run_v3_marker_offline_regression.py`（新） | CLI、隔离子进程、受控输出和汇总；不加载真实模型 |
| `tests/test_sol_molmo_offline_regression.py`（新） | 数据绑定、阶段分类、无网络、共享安全路径和闭环回归测试 |
| `tests/test_sol_molmo_worker_integration.py` | 增补生产入口委托与原行为保持测试，不删除/放宽已有检查 |

阶段2两个文件另由已批准计划管理。`backend.py`、`skill_robot.py`、`episode_evaluator.py`、`execution.py`、`tracking.py`、资产及SafetyShield均只读，保持控制器、0.1mm容差、39mm张开目标、所有阈值、TTL和评价标准。旧脚本保持原状且仅作对照；若还需改这些禁止文件，暂停并另请Astra规划。

## 关键设计与精确接口

新增不可变 `PreparedComponentPlan`：`contract: TaskContract`、`fresh: RGBDObservation`、`evidence: dict[str, Any]`、`pipeline_validated_contract: dict[str, Any] | None`、`provenance: dict[str, Any]`。

共享内部函数（放原 components 模块，避免再造执行器）：

```python
def _run_component_episode_core(
    *, config: SimulatorConfig, scenario: PhysicalScenarioConfig,
    family_id: str, asset_policy: dict[str, Any], output: Path,
    timeout_s: float, start_monotonic: float,
    prepare_plan: Callable[[Callable[[str], RGBDObservation]], PreparedComponentPlan],
    active: Callable[[], None], poll_active: Callable[[], None],
    abort_requested: Callable[[], bool],
    model_counters: Callable[[], dict[str, int]], scope: str,
) -> tuple[dict[str, Any], list, list]: ...
```

这是接口决策，具体import及类型前向引用按现有规范处理。`prepare_plan(frame)` 只在初始化、120步settle后调用；由准备器按顺序调用同一个 `frame("before")` 和 `frame("post-cloud")`。核心随后创建真实 `OpenCVTargetTracker(fresh,evidence)` 与 `research_safety_shield(timeout_s)`，执行原循环和原finally。不能因离线无需模型而少采一帧：深度噪声RNG每次capture消耗与V3绑定。

线上 `run_component_episode` 保留现有 exact planner type、角色绑定、policy、scene、snapshot/ledger验证。其准备器完整保留两次 `bounded_owner_model_call`、owned refresh检查、planning-stage-02验证、`grounded_contract`；`active` 与 `poll_active` 保留原具体租约/attempt/heartbeat检查及频率，`model_counters`读取真实账本。不能以新离线模式放松这条生产入口。

离线入口 `run_frozen_component_case(case_id, manifest, output)` 仅调用上述核心：本地取消文件/进程终止与原timeout预算代替不存在的分布式租约，其结果明确 `lease_scope=LOCAL_OFFLINE_NO_WORKER_LEASE_CERTIFICATION`。不得假造MolmoWorkerPlanner、账本、角色校验通过或模型调用记录。离线scope为 `OFFLINE_FROZEN_MODEL_OUTPUT_MUJOCO_COMPONENT_REGRESSION`，不借用真实模型实验标签。

### 冻结规划准备器

1. 从该例两阶段 draft、`raw/cloud/response.json` 和 `native_results`对应raw响应解析历史**技能意图及点**，以sha绑定来源。27例历史cloud输出必须与stage2 raw_text/技能列表一致；不会查询任何endpoint，不加载权重。禁止取 `actions[].resolved_step` 或旧动作坐标执行。
2. 新before/post-cloud帧必须为真实capture。比较新post-cloud RGB内容哈希与冻结模型point输入RGB，并比较尺寸、intrinsics、camera_to_world、calibration、scene和采集序列；旧与新observation_id/episode_id/timestamp不同是应有语义，不做整体observation checksum相等要求。初始RGB不一致则 `FROZEN_MODEL_INPUT_MISMATCH`，该例记未通过，不能重新点选、移点或调用模型补救。记录depth/mask差异；不凭旧depth替代新depth、不改变噪声；若差异影响几何或27例结果则保存并停止相关修复。
3. 用历史 `native_original_pixel_target` 对**新fresh**调用原 `associate_target_point`，再调用 `ground_observation`，destination用历史原始点；grasp_profile/资产由原snapshot核对。所有当前几何、`resolved_top_grasp_tcp`、destination、support及tracker均从新fresh生成。旧geometry仅比较报告，不作控制输入。
4. 直接验证并复用历史 `component/episode.json.contract` 的原始模板技能/参数/条件/约束，绑定新episode ID和新时钟；只重置 `task_id`、`timestamp`、`issued_at`、`valid_until`（保持V3 contract有效时长；按当前剩余预算取更小者），不改scene version/step/retry/constraint。使用 `TaskContract.model_validate`，记录重绑定字段diff；原pipeline contract作为 `source_pipeline_validated_contract`历史引用，不标成新模型验证结果。fresh grounding结果也必须通过原资产/校准检查。调用 `grounded_contract` 若需真实role/model receipt，只能复用已验证原receipt并明确为历史；不得伪造新 receipt。推荐上述严格模板重绑定，避免侵入生产准入。
5. `model_counters`返回新运行实际零调用；历史40次cloud、模型tokens等只写 `reused_historical_model_provenance`。新代码不导入真实推理启动器；进程内网络连接拒绝守卫作为最后检查，计数/日志记录所有拒绝尝试。测试注入一个外联请求必须被挡住。不能把拦截后的请求算作“没有尝试调用”。

## Task 1：冻结输入与589帧阶段化审计

**接口：** `load_v3_manifest(v3_root: Path, baseline_snapshot: Path)`；`audit_frozen_frames(manifest, output: Path) -> dict`。

- [ ] **1.1 绑定与拒绝测试（RED→GREEN）。** 检查40例与589帧无遗漏无重复、27名单严格相等、sha/大小不符立即拒绝、路径逃逸拒绝、只读V3保护、新输出不覆盖。测试使用小型受控夹具，不复制大raw；实际manifest校验另作运行证据。
- [ ] **1.2 全帧marker复查。** 重建RGBDObservation只用保存的RGB、depth.f32、valid_mask及校准元数据，保留原时间和checksum；逐589帧运行新解码，记录旧/新status、reason、IDs、角点和姿态。再在独立子进程用归档V3解码器做配对对照以区分版本变化与环境变化，不能在新执行器全局猴补丁换解码器。V3 decoder只从sha匹配的归档提取到/tmp，只读使用。
- [ ] **1.3 全帧geometry/grounding评估。** 每帧必须有geometry评估状态；有成功post-cloud grounding的例，以该历史fresh建立tracker，对每帧计算target/region `_geometry`、当前visible support以及marker所影响的分支。历史时间检查仅在独立冻结审计子进程以冻结帧时间＋100ms提供显式历史时钟上下文（参照原脚本 `_ReplayTracker`）；不改文件时间、观测字段或生产TTL，不把旧帧送入新闭环。初始grounding本来失败的9例保留 `INITIAL_GROUNDING_UNAVAILABLE`原理由和当前重算理由，不能伪造完整tracker；其每帧marker仍需完成。
- [ ] **1.4 动作语义。** 对已有动作的 `pre-NN-skill`，用同动作 `controller_result.action_result.state_before` 解析为真实历史 `RobotState`，复算 `_ground_component`；没有配对状态的失败pre/非动作帧仅报告geometry分支和 `ACTION_STATE_NOT_RECORDED`，不可猜holding或用物体真值充当机器人状态。POST和terminal无新的待执行动作，不套用前一个动作的抓持前置条件。用旧/新相同输入配对，分别列“诊断marker变化”“当前完整几何接管”“已抓取阶段允许未知”“新安全拒绝/抓取几何丢失”“历史失败不变”“不可比较”。
- [ ] **1.5 阶段分类测试。** 钉住原成功 `fixed-042001 post-06-release/pre-07-retreat UNKNOWN`不自动归为回归；`MOVE_ABOVE/APPROACH`在无完整几何且marker未知时必须停止；`LIFT/MOVE_TO_REGION/PLACE/RELEASE`还需真实闭合gripper与holding_object；任一混合ID不能提供marker抓取分支。不可用新分类掩盖任何新增执行失败。

本任务输出是历史帧反事实审计，不能替代动态闭环，不能将589帧全覆盖写成589次grounding均成功。

## Task 2：提取共享闭环，证明原安全语义不变

- [ ] **2.1 先写行为测试。** 新离线接口使用真实MuJoCo、真实capture与executor，仅在测试中记录真实方法调用；验证PRE→execute→POST→settle→post-capture顺序，PRE拒绝时executor从未调用，POST拒绝时不继续settle/后续动作，逐物理步hard-state可中断。拒绝故障仅在测试注入，不能修改运行安全规则。
- [ ] **2.2 机械提取。** 移动既有backend/capture/frame/collect/loop/finally实现到上述核心，不复制循环。原 `_SETTLE_STEPS`、16000步上限、5秒frame TTL、0.05秒poll、120初始化、288终末、side pregrasp −0.005m/retreat −0.100m、safe_stop、异常后after capture及物理评价均保持；两入口只能委托同一个核心。
- [ ] **2.3 生产回归。** 运行现有真实SQLite/worker/MuJoCo集成测试，其已有外部模型fixture仅用于软件验证；确保租约、attempt变化、heartbeat、policy binding、after capture失败语义不变。不得为离线免模型而删除exact类型或owned refresh检查。
- [ ] **2.4 小样闭环。** `fixed-042001`先新进程跑通，验证所有新帧和8动作、16 PRE/POST、连续物理证据、零外联。小样是正式27清单中的一例，可纳入正式结果且不可因失败重跑覆盖；调试重跑另起run-id并保留失败，不把调试结果冒充预先承诺的首跑。新增失败保存后由Astra计划，其他独立帧审计可继续。

## Task 3：冻结模型输出驱动全部27新闭环

- [ ] **3.1 输入准备器和无调用测试。** 原始意图/点sha、RGB绑定、重新association/grounding、严格模板重绑定、过期历史contract不能直接执行，外联拒绝、零模型loads/generations/cloud、禁止消费旧resolved动作。修改或删失raw点/意图必须停止。
- [ ] **3.2 配对路径自检。** 小样与V3比较初始scene/相机及capture序列、技能、有效时长、安全约束、采样量；浮点结果变化记录实际值，不为相等修改容差。源码hash证明controller/backend/evaluator等不变。新的核心与旧真实执行语义的等价由生产集成测试和关键调用/contract证据支撑；不用旧 `_simulate_episode`结果证明等价。
- [ ] **3.3 固定清单新进程顺序执行。** 完整清单在 `success-27.json`：

```text
fixed-042001
fixed-042002
fixed-042003
fixed-042004
fixed-042005
fixed-042006
fixed-042007
fixed-042008
fixed-042009
fixed-042010
development-043001
development-043002
development-043005
development-043006
development-043007
development-043010
development-043013
development-043014
development-043015
held-out-044001
held-out-044002
held-out-044003
held-out-044005
held-out-044006
held-out-044010
held-out-044013
held-out-044015
```

每例使用对应seed和 `scene_application.requested_scene`，启动真实MuJoCo；每个动作前新capture经新marker与 `_ground_component`，再 `resolved_step`、相同action_contract的PRE、真实executor、POST、settle及post capture。物体真值只能进独立物理评价/离线scene审计，不能输入grounding或控制。

- [ ] **3.4 逐例验收。** 原27成功预期全部保持：8动作完成、16 PRE/POST允许且没有参数被隐式限制、hard-state全程未失败、末端稳定采样和after存档成功，`diagnostic_complete=true`且原 `evaluate_episode`物理success且无安全违规；结合V3原 `component_success`判定，不以marker端点或controller返回单独宣布成功。每例输出原case、输入sha、源delta、动作/帧/检查/物理证据manifest、零调用记录、停止原因和退出码。
- [ ] **3.5 全量汇总和冻结核验。** 明确完成数/27、成功数/27、10/9/8分组、新失败和不可比较例；任何27中失败仍计入分母，最终状态非PASS。40例589帧审计与27闭环分表，不能混为40次新实验。运行结束再核对V3原始文件和历史冻结基线完整性（沿用父任务只读验证方法，避免原verifier默认写回V3报告），源码diff仅在两轮允许范围。没有新的模型成功率结论。

## 验证命令与预期

以下CLI为本计划要实现的接口，并非声称当前已存在。命令在新隔离树执行，环境使用共享 .venv；每次选一个全新输出目录，命令日志也在新目录的外部唯一文件或其预先约定父目录。

```bash
PYTHONDONTWRITEBYTECODE=1 MUJOCO_GL=egl .venv/bin/python -m pytest -p no:cacheprovider --basetemp=/tmp/v4-offline-tests-20261115 tests/test_sol_molmo_offline_regression.py tests/test_sol_molmo_worker_integration.py tests/test_sol_molmo_component_safety.py tests/test_pose_marker_evidence.py tests/test_pose_marker_visibility.py -q
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ruff check --no-cache src/cloud_edge_robot_arm/research/sol_molmo_components.py src/cloud_edge_robot_arm/research/sol_molmo_offline_regression.py scripts/run_v3_marker_offline_regression.py tests/test_sol_molmo_offline_regression.py tests/test_sol_molmo_worker_integration.py
PYTHONDONTWRITEBYTECODE=1 MUJOCO_GL=egl .venv/bin/python scripts/run_v3_marker_offline_regression.py --v3-root /home/ningyd/Documents/Codex/2026-11-14/x20-gpu-nvidia-smi-nvml-gpu/outputs/next-round-repair-40-20261115-v3 --baseline-snapshot artifacts/research/process/20261115-v4-marker-ambiguity/v3-baseline/snapshot.json --output artifacts/research/process/20261115-v4-marker-ambiguity/offline-regression/run-01 --phase all
```

RED应是新行为或安全顺序断言不满足/尚未实现接口，不是环境import错误。GREEN为上述测试、lint通过以及真实589帧/27闭环结果达到验收。小样命令可加 `--phase closed-loop --case fixed-042001`但须与批量协调成清单中的首例，不能双算。全部已知父任务9文件回归在阶段2完成后按最终改动范围补跑一次即可，不重复无关全面测试。

## 验收边界与停机规则

- **目标是27/27保留，不保证其将发生。** 任何新增失败、RGB不可比、headless前置条件失败都原样记录；不调整控制器、物理、0.1mm/39mm、准入、容差、seed、计划或评价器求绿色，不剔除困难例。
- 新问题/根因/范围扩展或计划外失败暂停相关修复并再次请实际gpt-6-astra规划；同轮明确预期RED按计划处理，不把脚本路径探索的不存在文件误写成实验失败。
- 本轮仅软件与MuJoCo离线冻结模型输出回归；没有新真实Sol/Molmo推理，没有真实机械臂，不授予正式研究、T10、未见held-out泛化或连续可见性资格。新结果不能更新为“新的Sol/Molmo端到端成功率”。
- 用户未授权公开push；按项目策略可以对已验证交付明确路径本地提交，禁止顺手推送。原始raw、DB、凭据、权重、SDK、源码归档保持本地边界；本计划及派生清单不冒充完整远端复现包。
- 实施后保存步骤报告、RED/GREEN、原始失败、运行依赖和证据hash，汇入阶段总结。本计划自身不可改写为已完成；另写实施回执，记录父任务阶段2输入更新和实际阶段3结果。

## 尚未实测

EGL渲染准入、阶段2最终SHA、共享核心提取的生产等价测试、589帧新解码与分支结果、27新闭环结果均待父任务实施。当前仅已完成读源码、绑定原始输入、独立核对27名单与589帧文件完整性、制定本计划。
