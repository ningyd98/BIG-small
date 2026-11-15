# V3 原27成功离线闭环回归 Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans 执行。用户“开始”已授权父任务阶段1–3；本 Astra 子任务只计划，不修改生产代码、测试或脚本。本文件为最终方案，`superseded-shared-core-draft/`仅保留未实施旧草案，不授予修改范围。

**Goal:** 用修复后的标记解码审计V3全40例589帧，并用冻结模型输出驱动原27成功例的新MuJoCo组件闭环，保留实际worker、安全和评价语义。

**Architecture:** 构造真实 `MolmoWorkerPlanner` 与真实 `MolmoGroundedPlannerAdapter`，只在原生PointProvider协议和云HTTP结果边界提供严格绑定的本地冻结输出。调用原 `make_worker_binding` 与 `run_worker_episode`；生产组件循环、租约、SafetyShield、物理控制和评价器全部原样使用。

**Tech Stack:** Python共享.venv、OpenCV、MuJoCo headless EGL、真实SQLite/SimulationWorker、原规划管线、两个有界冻结响应适配器、pytest。

**Spec:** 用户阶段1–3授权和父任务本轮委派。实际规划模型 **gpt-6-astra**；状态 **PLAN_ONLY_NOT_IMPLEMENTED**。无新推理、网络、付费、硬件或公开push授权。

## 已查证事实和基线

- V3目录：`/home/ningyd/Documents/Codex/2026-11-14/x20-gpu-nvidia-smi-nvml-gpu/outputs/next-round-repair-40-20261115-v3`。每例有自己的 `raw/`、`before/`、`after/`、`component/frames/`；批次根目录没有公共 `raw/`。
- 隔离源码：`/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall`。创建基点为 `5e68e2f9f1ed7d865f483f41534dec9404c83394`；本次取证时父任务已合法推进 HEAD 到 `57c4dc0d855f5410fcf497edf47b43cfd24ad74b`。必须按文件字节和批准变更判断，不把父任务已有本地提交当未知漂移。
- V3 `verification.json` 声明40例完整、27 component_success；本任务独立核对 `batch-result.json` 名单为10 fixed＋9 development＋8 held-out。原13失败为9个 RGBDModelCallFailed、3个 HARD_FINGER_LIMIT、1个 CONTROLLER_FAILURE:UNREACHABLE，不要求本轮把它们改成成功。
- 实际枚举589个 observation.json。本任务把2945个帧相关文件和1478个模型 raw 文件的实际 SHA256/大小与每例冻结 manifest 对照，全部一致。`frame-inputs.json`、`model-record-inputs.json` 记录绝对路径与 SHA；不复制全部大体积 raw。
- 父任务此前完整运行 V3 verifier，确认7041证据、594源码、11388历史冻结文件和40例物理重算 PASS；这是父任务已执行事实，本 Astra 未重复整个验证器。
- 原成功例 `fixed-042001` 的 `post-06-release`、`pre-07-retreat` 原本就是 UNKNOWN。`_ground_component` 在完整目标几何存在时无需标记；在已抓取运输阶段可使用可见支持和抓持反馈；因此 UNKNOWN 数量不等于执行回归数量。
- 真实循环在 `sol_molmo_components.py`：同一 `action_contract` 和 `step` 同时交给 SafetyShield 与 SkillExecutor；PRE 在执行前，POST 在控制器成功返回后、settle前；逐物理步 `check_component_hard_state`。旧 `verify_next_round_repairs.py::_simulate_episode` 直接调用 executor，没有该 PRE/POST，不能作为本次闭环验收。

**已知失败来源：** 上一 Astra 轮次原始合成 ID7＋ID0 断言 exit1，父任务已报告阶段2九文件348passed、pose单文件33passed及Ruff通过，全仓测试仍在运行；最终输入以parent-phase2-input-receipt.json及实施时复核为准。本轮新的问题是旧离线工具不能提供要求的安全路径与27例覆盖；该结论来自带SHA的源码检查，**不是**已经运行并失败的新27例实验。所有阶段3运行结果目前待实测。

## 输入、所有权和运行前置条件

`inputs.json` 绑定相关源码、模型资产、V3汇总、原始源码归档和上轮计划；`case-inputs.json` 绑定40例结果、component episode、物理证据、两阶段规划、scene/role/job；`episode-manifest-bindings.json` 绑定40份 manifest。快照位于 `input-snapshots/`。完整源码字节归档 `source-bytes.local.tar.gz` 仅本地保存，SHA为 `6fde448feedd3748a0943f28d01197dc66050bd65f4625767af8f3a97294061d`。

父任务独占修改 `pose_markers.py` 和 `test_pose_marker_evidence.py`；它们在 inputs 中标记 `expected_authorized_change=true`。阶段3开始前读取阶段2最终GREEN、SHA和diff，写新实施回执，不覆写本计划，不与父任务抢写。其他源先核对本计划 SHA；最终方案不重构生产执行路径，只新增下面三个文件。

共享解释器 `/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python`。`runtime-imports.json` 记录已导入版本；本任务没有启动渲染器。执行器必须先进行独立 headless 小样：`MUJOCO_GL=egl` 在导入 mujoco/OpenGL前设置，保持V3相同320×240顶视相机、资产、1/240 dt、seed、domain_randomization=False、深度噪声及采集次数。EGL/Mesa/驱动与权限必须可用；失败时保存原错并交Astra，不能切换相机、关深度噪声、改渲染参数来求通过。

所有命令 `PYTHONDONTWRITEBYTECODE=1`；pytest `-p no:cacheprovider --basetemp=/tmp/<唯一目录>`，Ruff `--no-cache`，其他缓存指向允许的/tmp目录。新隔离树写权限由父任务办理。历史V3、Gemini工作树和历史冻结目录只读；输出独占创建于新树 `artifacts/research/process/20261115-v4-marker-ambiguity/offline-regression/<run-id>/` 或/tmp，禁止在失败后覆盖同名目录。每例新进程顺序运行，保留所有退出码和错误；不得从20例旧成功集合取代原27例。


## 必须固定实际导入源码

共享 .venv 的editable安装指向原主目录，单独调用其python并不保证导入当前隔离树。父任务曾有一次临时oracle因未固定PYTHONPATH导入错误旧包而出现keyword TypeError，随后显式 `PYTHONPATH=src:.`已验证正确模块；这是已识别的运行前置问题，不能把错误环境的结果当阶段3回归。

runner必须在任何项目import之前从自身 `__file__`确定隔离根 `/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall`，将该根的src、root显式置于sys.path最前；所有子进程使用绝对 `PYTHONPATH=/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall/src:/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall`。逐一检查pose_markers、components、single_episode、grounded_planner、molmo_worker、execution、backend、evaluator的 `__file__.resolve()`归属该根，并与运行回执SHA一致。记录实际sys.executable、cwd、sys.path首项及模块路径。错误源码立即 `SOURCE_IMPORT_MISMATCH`，不得启动backend或计入执行。

阶段2最新父任务观测和实际读取SHA保存在 `parent-phase2-input-receipt.json`；它补充早先标记为可改变的输入，不覆写此前快照。实施前仍核对当前SHA及最终测试结果。

## 方案比较与选择

父任务补充的 `scripts/verify_finger_limit_fix.py::_verify_guard_ast` 用AST证明运行时代码仅含已批准finger loop及 `_visible_support/_ground_component`变化。提取共享循环会破坏这个证明，不能增加任意函数白名单让检查通过。

| 路径 | 影响 | 决定 |
|---|---|---|
| 提取共享组件核心 | 需搬移约400行、适配AST结构等价验证、重新证明线上/离线生命周期；若用本地取消代替租约还会减少实际worker覆盖 | 本轮不实施，不修改验证器 |
| 真实planner/worker，冻结两个外部输出边界 | PointProvider已有注入协议；cloud类型允许RGBDPlannerAdapter子类；原exact grounded/planner类型、角色绑定、双阶段管线和全执行路径可保留 | **采用** |
| 旧脚本直接executor | 缺SafetyShield PRE/POST且不证明真实worker路径 | 禁止作为闭环证据 |

这不是伪造真实神经网络结果：每次本地响应明确标记 `OFFLINE_FROZEN_OUTPUT_REPLAY`，绑定历史原文与当前匹配RGB/请求；真实生成计数为0，replay计数另列。

## 限定文件范围

仅新增三个文件：

- `src/cloud_edge_robot_arm/research/sol_molmo_offline_regression.py`：冻结输入、帧审计、两种响应适配器、真实worker组装和逐例结果验证。
- `scripts/run_v3_marker_offline_regression.py`：CLI、受控输出、每例新进程、汇总。
- `tests/test_sol_molmo_offline_regression.py`：严格绑定、零外联、阶段分类和真实安全路径测试。

阶段2的 `pose_markers.py`及聚焦测试由父任务和另轮Astra管理，待其GREEN后再绑定最终SHA。所有其他已有生产、测试和验证器文件只读，尤其 `sol_molmo_components.py`、`verify_finger_limit_fix.py`、planner、worker、SafetyShield、backend/controller/evaluator。0.1mm容差、39mm张开目标、相机、资产、几何和安全阈值均保持。若两边界方案不能满足原接口，保存失败并交新Astra计划，不自动切回重构或放宽AST。

## 精确接口和实施决策

新增接口如下；已有函数不得重写：

```python
class FrozenPointProvider:
    def point(self, observation: RGBDObservation, phrase: str) -> BoundPointResult: ...

class FrozenCloudReplayAdapter(RGBDPlannerAdapter):
    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]: ...

def build_frozen_worker(case, manifest, output: Path) -> tuple[
    MolmoWorkerPlanner, RoleRuntimeBinding, FrozenPointProvider, FrozenCloudReplayAdapter
]: ...

def load_v3_manifest(v3_root: Path, baseline_snapshot: Path): ...
def audit_frozen_frames(manifest, output: Path) -> dict: ...
def run_frozen_component_case(case_id: str, manifest, output: Path) -> dict: ...
```

### PointProvider：只回放同一RGB、同一短语的已存模型输出

27例每例依顺序消费 `raw/molmo/request-0001..0004`：before目标/区域，post-cloud目标/区域。实际短语从各 `started.json.phrase`读，例如 `visible top center of red block`；不要擅自改成简写。逐次核对本轮observation RGB SHA、宽高、相机校准、阶段、phrase及query SHA与冻结原输入相符，raw-response与result的raw SHA也相符；拒绝多调用、漏调用、乱序、错RGB/错phrase。

用原 `parse_native_point(raw_text)`解析冻结原文；构造原 `BoundPointResult`，其中 observation_checksum绑定**当前新观测**，rgb_sha与query_sha通过验证后绑定，evidence明确historical source path/hash、原checksum、新checksum和replay scope。不把旧checksum伪装为新checksum，也不从图像重新挑点、不从scene truth取点、不截断/修理raw。

`replay_calls`计本地消费次数；`model_loads_started`、`generation_calls_started`、`generation_calls_completed`恒为0（本适配器确实不加载/生成），历史token/耗时/生成计数只写 `reused_historical_provenance`。provider没有真实MolmoPointProvider实例或权重路径。

### 云响应：完整请求匹配后只读返回冻结JSON

`FrozenCloudReplayAdapter`继承现有RGBDPlannerAdapter，只覆盖 `_post`；其余 `plan_skills`、请求构造、解析和决策schema沿用原实现。`_post`先保留原route/model校验，再要求path及**完整解析后的body**等于该例冻结 `raw/cloud/request.json`，最多一次。27原成功例均为文本意图请求；消息包括当前实测数值几何，不允许删掉geometry再比较，不允许数值容差比较、替换新geometry为旧值或手工接受不同提示。若新初始渲染/深度使请求不同，记 `FROZEN_CLOUD_REQUEST_MISMATCH`，不返回历史response、不发网络，保留差异后交Astra。

匹配后深复制冻结 `raw/cloud/response.json`返回，记录actual body哈希、source request/response哈希、replay_calls。**不得调用 `super()._post`、urllib opener、网络injector、真实model service或CostLedger.record_request。** 原response token用量为历史值，不能计入新推理。新增本地replay日志放专用 `replay/`目录，不冒充新的远端raw响应/付费账单。

复用历史 `ModelConfigSnapshot`配置，endpoint从已允许官方route候选中按历史endpoint_hash唯一匹配，校验digest一致；api_key为空，不读取用户密钥。现有compatible接口要求 `allow_paid=True`才能构造请求，离线适配器仅保持这一已冻结协议配置以通过原设置绑定；这不触发付费： `_post`完全本地且进程另设外联拒绝守卫，任何真实网络路径尝试都使该例失败。该字段与离线约束的区别写入回执，不能把此字段当新付费授权。`cost_ledger=CostLedger()`真实空账本，未发请求所以真实cloud计数0。

### 真实planner、角色绑定、worker

用历史cloud配置/role snapshot构造真实 `FrozenCloudReplayAdapter`；cloud source hashes逐项验证仍匹配当前只读源码。构造**精确类型** `MolmoGroundedPlannerAdapter(point_provider=frozen_points, cloud=frozen_cloud, task=原GroundingTaskDescriptor, worker_owned_refresh=True, component_diagnostic=True, cloud_vision_fallback=原True)`，然后精确 `MolmoWorkerPlanner(grounded, output=新目录/planning)`。不要用fake planner对象绕过type检查。

使用 `make_worker_binding`从实际当前源码重新生成device绑定；marker修复源码哈希进入新绑定，历史角色绑定另存source provenance，不能把旧设备hash声称为新代码。原perception asset manifest哈希仅作为历史输出来源绑定，并明确本轮未验证/加载本地权重。另将新增离线模块和脚本SHA纳入运行回执，因为原make_worker_binding列表不包含新入口。

使用每例原 `scene-assignment.json`（seed、component_scene、instruction、marker_family、相机、grasp_profile完整核对）调用原 `run_worker_episode(assignment, output, result, planner=planner, binding=binding)`。它会创建真实SQLite、job/attempt/lease、SimulationWorker并进入原 `run_component_episode`；保留heartbeat、timeout=120、真实两阶段PlanningPipeline及owned refresh。合同由该管线用新RGBD重建，**不再手工重发旧contract或执行旧resolved_step**。

每步新capture、新解码、`_ground_component`、`resolved_step`、同一action_contract的PRE/execute/POST、hard-state、settle/terminal/after/evaluator全是现有代码。禁止猴补丁这些生产函数；测试中的单点拒绝注入只用于证明门禁。在实际27运行中唯一离线替代是上述两个模型I/O边界。

本地响应无真实推理等待，故旧/新墙钟时刻不相同是正常；保留真实新时钟、原TTL和120秒budget，不能冻结新闭环时钟。before/post-cloud采集仍由原程序进行，RNG消耗不因离线省略capture。初始RGB/请求不匹配如实失败，不能减少采样或改变噪声。

## Task 1：冻结输入与589帧阶段化审计

**接口：** `load_v3_manifest(v3_root: Path, baseline_snapshot: Path)`；`audit_frozen_frames(manifest, output: Path) -> dict`。

- [ ] **1.1 绑定与拒绝测试（RED→GREEN）。** 检查40例与589帧无遗漏无重复、27名单严格相等、sha/大小不符立即拒绝、路径逃逸拒绝、只读V3保护、新输出不覆盖。测试使用小型受控夹具，不复制大raw；实际manifest校验另作运行证据。
- [ ] **1.2 全帧marker复查。** 重建RGBDObservation只用保存的RGB、depth.f32、valid_mask及校准元数据，保留原时间和checksum；逐589帧运行新解码，记录旧/新status、reason、IDs、角点和姿态。再在独立子进程用归档V3解码器做配对对照以区分版本变化与环境变化，不能在新执行器全局猴补丁换解码器。V3 decoder只从sha匹配的归档提取到/tmp，只读使用。
- [ ] **1.3 全帧geometry/grounding评估。** 每帧必须有geometry评估状态；有成功post-cloud grounding的例，以该历史fresh建立tracker，对每帧计算target/region `_geometry`、当前visible support以及marker所影响的分支。历史时间检查仅在独立冻结审计子进程以冻结帧时间＋100ms提供显式历史时钟上下文（参照原脚本 `_ReplayTracker`）；不改文件时间、观测字段或生产TTL，不把旧帧送入新闭环。初始grounding本来失败的9例保留 `INITIAL_GROUNDING_UNAVAILABLE`原理由和当前重算理由，不能伪造完整tracker；其每帧marker仍需完成。
- [ ] **1.4 动作语义。** 对已有动作的 `pre-NN-skill`，用同动作 `controller_result.action_result.state_before` 解析为真实历史 `RobotState`，复算 `_ground_component`；没有配对状态的失败pre/非动作帧仅报告geometry分支和 `ACTION_STATE_NOT_RECORDED`，不可猜holding或用物体真值充当机器人状态。POST和terminal无新的待执行动作，不套用前一个动作的抓持前置条件。用旧/新相同输入配对，分别列“诊断marker变化”“当前完整几何接管”“已抓取阶段允许未知”“新安全拒绝/抓取几何丢失”“历史失败不变”“不可比较”。
- [ ] **1.5 阶段分类测试。** 钉住原成功 `fixed-042001 post-06-release/pre-07-retreat UNKNOWN`不自动归为回归；`MOVE_ABOVE/APPROACH`在无完整几何且marker未知时必须停止；`LIFT/MOVE_TO_REGION/PLACE/RELEASE`还需真实闭合gripper与holding_object；任一混合ID不能提供marker抓取分支。不可用新分类掩盖任何新增执行失败。

本任务输出是历史帧反事实审计，不能替代动态闭环，不能将589帧全覆盖写成589次grounding均成功。


## Task 2：实现两个冻结边界，证明实际worker安全路径

- [ ] **2.1 RED→GREEN绑定测试。** 每个raw/manifest字节变化、错phase、错RGB、错query、四次点乱序/超限、云完整请求任一数值/消息/模型改变、第二次cloud replay，全部在消费前失败。正确输入解析历史原文并绑定新observation。测试确认没有 `super._post`或真实Molmo实例；即使调用者误入真实socket连接，独立拒绝守卫记录并停止。
- [ ] **2.2 组装真实类型。** 按上述构造实际snapshot、角色、ledger、两个真实planner及binding；运行前验证 `type(planner) is MolmoWorkerPlanner`和`type(planner.grounded) is MolmoGroundedPlannerAdapter`，调用原binding.validate，不伪造该检查。源码和历史配置不匹配时停止。
- [ ] **2.3 原安全路径测试。** 新测试使用真实MuJoCo、capture、SQLite/worker/lease/executor，记录实际SafetyShield调用，断言PRE→execute→POST→settle→post-capture；仅测试故障注入PRE拒绝必须零执行，POST拒绝必须无后续settle/动作，hard-state违规必须中断。确认shield和executor使用完全相同的step/action_contract；不通过AST字符串镜像测试冒充行为证明。
- [ ] **2.4 既有验证。** 原 `tests/test_sol_molmo_worker_integration.py`及component_safety测试保持原样运行，原finger guard验证器保持原样运行；components.py、backend、skill_robot、evaluator、guard脚本SHA必须与输入相等。无需重构或扩大白名单。

## Task 3：原27新闭环和验收

- [ ] **3.1 独立headless小样。** 首例 `fixed-042001`在新进程用原worker执行；EGL初始化和输出写权限实际验证。纳入正式27首跑或明确标成开发小样，后续不得双算。任何失败保留原输出，不自动调整阈值或覆盖重跑。
- [ ] **3.2 固定全部清单。** 顺序新进程执行以下27例，不能选择20旧成功替代。每例只消费自身冻结输出，不共享planner/provider状态。

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

- [ ] **3.3 完整性和动态证据。** 每例保存新before/post-cloud/pre/post/terminal/after帧、marker审计、grounding、16个实际PRE/POST、8动作、每物理步hard-state和独立physical samples、worker lease/attempt终态、新planning-stage01/02、replay映射、空真实推理账本及输出manifest。原模板技能顺序与原27来源相同，新action坐标来自新RGBD。
- [ ] **3.4 成功标准。** 每例真实worker终态符合原组件路径，8动作完成、PRE/POST均允许且无被限制参数、无hard-state失败、diagnostic_complete、after存档完整，原evaluate_episode判物理成功且无安全违规；按V3原component_success语义汇总。目标是 **27/27，10/9/8**，任何更少都不算阶段通过。marker端点/动作返回不能单独代替组件＋物理验收。
- [ ] **3.5 如实报告。** 单列 `model_loads=0, local_generations=0, cloud_transmissions=0, network_attempts=0`和`point_replays=4, cloud_replays=1`（成功例）；原response tokens仅历史。40例589帧审计与27新闭环分表；新增失败/不可比仍保留在27分母。原13失败的历史分类不被改写成新实验结果。
- [ ] **3.6 冻结和交付。** 结束后核对V3、历史冻结和禁止变更源码未变；父任务完整只读验证方法可复用，但原verifier会写报告则应重定向新输出，不能写回V3。保留步骤报告/阶段总结、测试和运行日志、计划输入更新回执。只明确路径本地提交，不公开push。

## 命令与预期

以下新CLI是要实现的接口，非已经存在或通过。cwd为新隔离树，每次使用唯一输出目录；新模型请求永远不能由该CLI触发。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. MUJOCO_GL=egl .venv/bin/python -m pytest -p no:cacheprovider --basetemp=/tmp/v4-offline-tests-20261115 tests/test_sol_molmo_offline_regression.py tests/test_sol_molmo_worker_integration.py tests/test_sol_molmo_component_safety.py tests/test_pose_marker_evidence.py tests/test_pose_marker_visibility.py -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python -m ruff check --no-cache src/cloud_edge_robot_arm/research/sol_molmo_offline_regression.py scripts/run_v3_marker_offline_regression.py tests/test_sol_molmo_offline_regression.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. MUJOCO_GL=egl .venv/bin/python scripts/run_v3_marker_offline_regression.py --v3-root /home/ningyd/Documents/Codex/2026-11-14/x20-gpu-nvidia-smi-nvml-gpu/outputs/next-round-repair-40-20261115-v3 --baseline-snapshot artifacts/research/process/20261115-v4-marker-ambiguity/v3-baseline/snapshot.json --output artifacts/research/process/20261115-v4-marker-ambiguity/offline-regression/run-01 --phase all
```

finger verifier按其已有CLI参数先只读核对后运行，禁止发明新的跳过flag；保留其原baseline输入和完整退出码。新behavior tests的预期RED（尚无适配器或严格绑定未实现）可继续本计划；环境错或新根因不是预期RED，需Astra下一轮。阶段2若仍有计划外14px角度失败，必须等待父任务对应Astra纠正与GREEN，阶段3可先做不依赖新解码的输入保全/只读枚举。

## 验收边界、假设与停机

**事实：** 原27成功、589帧、原执行器含SafetyShield、旧脚本无shield、PointProvider可注入、cloud不要求exact class而两个planner要求exact class、finger验证器不准重构，均已读源码/证据确认。

**假设待实测：** 同环境seed及原capture顺序会产生相同模型RGB输入与原cloud完整请求；若不相等，禁止无条件回放/调容差，保留失败交Astra。EGL准入、新冻结适配器、589帧新解码和27闭环均未由本任务运行。

任何新根因、范围扩大、未计划失败暂停相关修复并再次调用实际Astra，独立审计可继续。通过只说明**冻结模型输出条件下的软件/MuJoCo闭环回归**，不产生新真实Sol/Molmo端到端成功率、硬件/正式研究/连续可见性或未见held-out泛化资格。原raw、DB、凭据、权重、SDK和源码归档维持本地边界，本计划清单不是完整远端复现包。

最终计划包保存输入绝对路径/SHA、只读必要快照、case/frame/model索引与SHA256SUMS；未来另写实施回执，不把此计划修改为已运行结果。
