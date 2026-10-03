# RGB-D 直接输入与 MuJoCo 训练测试数据完整实施计划

> 研究开发顺序与量化验收已由 [代理开发执行计划](2026-10-03-rgbd-evidence-research-roadmap.md) 统筹；本计划保留作为输入、数据与物理执行工作包的技术细节。冲突时按新总计划及其研究设计执行。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 本次仅编制计划，不执行下列代码修改或批量作业。

**Goal:** 将 BIGsmall 切换为真实 RGB-D 输入，并在本地 MuJoCo 建立可复现、可标注、可划分的训练/测试数据生成与物理闭环评测流程。

**Architecture:** 在线链路使用相机观测驱动视觉模型和深度定位，再进入高层技能与物理执行；离线链路使用同一采集接口，配合独立真值标注器生成数据。分为三个可独立验收的工作包：A 输入与规划、B 静态数据集、C 物理执行与轨迹；静态数据生成不等待模型服务或抓取执行器。

**Tech Stack:** Python 3.12、现有 MuJoCo 3.3.7+、NumPy、Pillow、Pydantic、FastAPI、Ollama/兼容视觉 API、React/TypeScript。沿用已有虚拟环境、队列与 SQLite repository。

**Spec:** `docs/superpowers/specs/2026-10-03-rgbd-mujoco-dataset-design.md`。本计划扩展并接替 `2026-10-03-rgbd-direct-input.md`，旧文档保留作为原型历史。

## Global Constraints

- 在线模型输入必须包含 RGB 与注册深度；禁止无提示降级为文字或 Mock。
- 深度语义为 optical_z_m：光轴方向距离、米、little-endian float32；0 表示无效。
- 相机坐标为 +X 向右、+Y 向下、+Z 向前；camera_to_world 为行优先 4×4 刚体变换。
- 默认采集分辨率 320×240，数据集配置可选择 640×480；最大宽高 1280×720。
- 在线观测在接收时超过 5000 ms 或超前服务器超过 1000 ms 即拒绝；离线数据通过专用读取器处理，不修改历史时间戳伪装实时数据。
- 默认本地模型 qwen3-vl:4b-instruct，默认服务 http://127.0.0.1:11434；不承诺未经实测的速度与精度。
- 初始每个 GPU 只运行一个渲染进程，批内复用模型和渲染器。
- 训练/验证/测试按 group_id 划分为 80%/10%/10%；同一 episode、多视角、增强样本和指令改写不得跨集合。
- 数据生成默认 smoke：100 个独立场景组、每组 1 帧；validation：1000 组；full：10000 组。轨迹集默认先验收 20 个 episode，再扩展。
- 每批采样尝试上限为目标场景组数量的 5 倍；不足时报告 INCOMPLETE，不无限重试或降低质量阈值。
- 运行大文件保存在 datasets/ 或 artifacts/；配置、代码、schema 与文档进入版本管理。
- 保留用户原有 docs/README.md、两份中文文档和 output/ 改动；本计划阶段仅写设计与计划文件。
- 本轮限本地仿真；不执行真实硬件控制或付费云推理。

## Review Focus

1. 同一采集周期不同 render pass 间发生物理推进或错误的相机轴变换：RGB、深度和标签仍须对应同一状态。Task 2/5 用冻结状态、平面深度与投影测试约束。
2. 多视角/指令变体、改 seed 后重复场景泄露至测试集：必须整体分组，不能只按文件名或 seed 拆分。Task 6 用跨 split 重复样本测试约束。
3. 对象位姿、实例标签或教师状态通过提示词/文件名/缓存进入在线请求：在线输入只允许观测、指令与本体状态。Task 3/10 用带诱饵真值的请求断言约束。
4. 取消、超时、服务切换或磁盘写失败造成旧结果覆盖新任务、过期租约重复运行或半成品数据被索引：Task 4/6/7 验证恢复与幂等行为。
5. 固定轨迹、状态赋值或未经执行的模型计划被计作成功示范：Task 8/9/10 验证实际物理步数、接触/释放和真值只读评估。

---

## 交付与依赖

| 里程碑 | 任务 | 独立交付 | 前置条件 |
|---|---|---|---|
| M0 基线收敛 | 1 | 可继续实施的原型基线与回归记录 | 无 |
| M1 RGB-D 输入 | 2～4 | 真实采集、视觉规划、缺模型明确阻塞 | M0；真实规划需本地视觉服务 |
| M2 数据工厂 | 5～7 | 100/1000 帧静态数据、自动标注、拆分、训练导出 | Task 2；不需要模型服务 |
| M3 物理示范 | 8～9 | 真实物理技能执行和 20 个带结果的示范 episode | Task 2、5、6 |
| M4 视觉闭环 | 10 | RGB-D 驱动执行、重新观测、独立评测 | M1、M3 |
| M5 集成验收 | 11～12 | 工作台入口、Isaac 接口、完整报告与运行文档 | 前述任务按能力分别验收 |

实施可以先完成 M1 的无模型采集部分和 M2，再部署/验证本地模型；不因模型缺失阻塞数据生产。物理控制与数据生成分包，便于单独验证。里程碑用验收结果推进，不先承诺未经测量的工期或吞吐。

## 文件责任图

| 范围 | 新增/扩展目录 | 责任 |
|---|---|---|
| 观测 | `vision/observations.py`, `vision/capture.py`, `simulation/mujoco/camera.py` | 同步 RGB-D、标定、序列化与深度定位 |
| 模型 | `vision/planner.py`, `vision/messages.py`, `vision/model_resolver.py` | 双图消息、视觉能力、配置快照、严格输出解析 |
| 数据 | `datasets/rgbd/{models,scene_sampler,labels,writer,quality,splitter,generator,exporters}.py` | 配置/场景/标签/落盘/质检/分组/任务/训练格式，各文件一个责任 |
| 物理执行 | `simulation/mujoco/{motion_controller,skill_robot,episode_evaluator}.py` | 位姿控制、现有技能协议、只读物理结果判定 |
| 示范/评测 | `datasets/rgbd/teacher.py`, `vision/{execution,evaluation,offline_reader}.py` | 教师轨迹、视觉闭环、离线评测和历史样本读取 |
| API/UI | 现有 `cloud/api`、`simulation_runtime`、`simulation_workbench`、`dashboard/src/simulation` | 配置、排队、预览、取消、进度和报告 |
| CLI/配置 | `scripts/*rgbd*.py`, `configs/rgbd/*.yaml` | 注册的可复现实验入口 |

上表除 scripts/configs/dashboard 外，均位于 `src/cloud_edge_robot_arm/` 下。目录名 `datasets` 是项目内部代码模块；生成的大文件位于仓库根 `datasets/`，二者不可混用。

## Task 1：收敛当前原型与历史回归

**Files:** 检查全部现有 RGB-D 未提交改动；修改 `scripts/verify_phase11_1_simulation_runtime.py`、必要的历史 fixture；记录 `docs/rgbd_validation.md`。

**Interfaces:** 保留 `ExperimentDraft.input_mode: Literal['RGBD','LEGACY_PIPELINE']`；历史 fixture 显式 LEGACY_PIPELINE，新用户请求默认 RGBD。

- [ ] 用 `tests/test_phase11_1_simulation_runtime.py::test_recovery_verifier_does_not_leave_sqlite_databases_in_artifacts` 重现已有失败；确认根因是旧 verifier 草稿没有显式历史模式，而非放松新默认行为。
- [ ] 记录 git diff 基线和用户原有改动；修复 verifier 草稿及发现的真实回归，避免给所有失败测试机械增加 legacy 标签。
- [ ] 整理原型格式、类型和 API schema 生成；检查 ws 先创建 service 时是否使用相同模型配置，检查 dry-run 的新字段实际传递。
- [ ] 运行相关 RGB-D、Phase 4、Phase 11 测试和 Ruff/mypy；预期相关回归全绿，环境不可用测试明确返回阻塞。
- [ ] 形成独立可审阅变更 `fix: stabilize RGB-D prototype and explicit legacy regressions`；只暂存本任务文件，提交时遵循会话授权，不混入用户文档。

## Task 2：统一观测与连续相机采集

**Files:** 修改 `vision/observations.py`、`vision/capture.py`、`simulation/models.py`、`simulation/config.py`、`simulation/mujoco/{camera,backend}.py`；新增 `tests/test_rgbd_capture_session.py`；扩展 `tests/test_rgbd_observations.py`。

**Interfaces:** 保留 `RGBDObservation.world_point(pixel: tuple[int,int]) -> Pose`；在 `vision/capture.py` 新增 `MuJoCoCaptureSession(config: SimulatorConfig)` 上下文管理器、`capture() -> RGBDObservation`、`capture_with_instances() -> CapturedFrame`。`CapturedFrame` 同文件定义，含 observation、实例 ID 平面、physics_state_hash；场景应用接口在 Task 5 定义。

- [ ] 编写失败测试 `test_render_passes_share_frozen_state`、`test_depth_plane_matches_camera_projection`、`test_capture_session_reuses_renderer`：相同状态的 RGB/depth/mask 共享 sim_time/hash；无噪声平面反投影误差 ≤0.005 m；批内只初始化一次渲染器。
- [ ] 运行上述测试，确认针对缺少 session/分割接口失败；现有通过的观测校验测试不重复制造失败。
- [ ] 实现同步捕获与资源关闭；逐 pass 不推进物理；保留原始深度，不将归一化灰度当成米；完善尺寸/标定/无效值检查。存档输入与实时 freshness 校验分开。
- [ ] 执行 `MUJOCO_GL=egl .venv/bin/python -m pytest -q tests/test_rgbd_observations.py tests/test_rgbd_capture_session.py tests/test_phase9_mujoco_load.py tests/test_phase9_mujoco_physics_step.py`，预期全部通过，并人工查看一组 RGB/depth/mask。
- [ ] 独立交付 `feat: add synchronized reusable RGB-D capture sessions`。

## Task 3：视觉请求、严格定位与活跃模型配置

**Files:** 修改 `vision/planner.py`、planning models/pipeline、model-control service；新增 `vision/messages.py`、`vision/model_resolver.py`；扩展 `tests/test_rgbd_planning.py`。

**Interfaces:** `build_visual_messages(instruction: str, observation: RGBDObservation) -> list[dict[str,Any]]`；`resolve_visual_planner(config: ModelConfigSnapshot) -> RGBDPlannerAdapter`；`ModelConfigSnapshot` 定义 provider/model/endpoint/timeout，secret 保持独立存储。`VisualDecision` 包含 target_pixel、destination_pixel、confidence、skills、reason。

- [ ] 写 HTTP 集成测试：两幅不同图像实际出现在请求；放入带诱饵坐标的 SceneSummary 后请求仍不含真值；更换深度时同一像素的三维点按标定变化；错误像素、错误技能顺序、文本模型和失效模型均不能产出可执行合同。
- [ ] 运行测试观察新增断言失败；补活跃 profile 切换测试，确保下一请求使用新配置而运行中的请求保留自己的快照。
- [ ] 拆分消息构造/配置解析；限制输出 schema 和动作序列，保留不确定性拒绝；以深度点作为可见表面点，抓取偏移使用经过验证的几何参数，不把它直接当物体中心。
- [ ] 运行 RGB-D 与历史规划测试；实际本地服务可用后发送真实图像并保存结果，服务不可用时保留 BLOCKED_BY_ENV。记录两幅图像只是一种 VLM 输入适配，非原生深度编码器。
- [ ] 独立交付 `feat: ground visual decisions from paired image requests`。

## Task 4：统一默认运行、证据、取消与超时

**Files:** 修改 `cloud/api/{app,vision,model_control,simulation_workbench}.py`、`simulation_runtime/{worker,dispatcher,service}.py`、`simulation_workbench/{models,service}.py`；扩展 `tests/test_rgbd_runtime.py`。

**Interfaces:** 增加受控 `execution_scope: Literal['CAPTURE_ONLY','VISUAL_PLANNING','VISION_CLOSED_LOOP']`，默认 VISUAL_PLANNING；DATASET_GENERATION 通过 Task 7 的独立 job_type 表示，避免与该枚举混用。每个运行保存模型快照、观测哈希及 `task_execution` 状态。

- [ ] 写测试：缺模型仍可 CAPTURE_ONLY；VISUAL_PLANNING 缺模型阻塞并保存观测；只有合同不能 task_success；长请求持续 heartbeat；取消后返回的模型结果不能提交为成功；ws 先访问不会改变模型配置来源。
- [ ] 运行测试观察失败，检查现有 lease TTL=30 秒与模型/相机启动耗时之间的冲突。
- [ ] 实现独立心跳与有界调用、取消后丢弃迟到结果、超时归因、终态一致性；对未实现的随机化/故障模式明确拒绝或显示能力限制，不能静默忽略。
- [ ] 运行 runtime、workbench、model-control 相关测试；检查 job、attempt、result、artifact 的终态一致。
- [ ] 独立交付 `feat: make RGB-D runtime evidence and cancellation consistent`。

## Task 5：场景采样、实例标注与任务标签

**Files:** 新增 `datasets/__init__.py`、`datasets/rgbd/{__init__,models,scene_sampler,labels}.py`、`configs/rgbd/dataset_smoke.yaml`、`tests/test_rgbd_dataset_labels.py`；扩展 `simulation/mujoco/spec_randomization.py` 和 Task 2 session。

**Interfaces:** 在 models 定义 `DatasetConfig`、`SceneSpec`、`GroundTruthSnapshot`、`SampleLabels`；`sample_scene(config: DatasetConfig, seed: int) -> SceneSpec`；`MuJoCoCaptureSession.apply_scene(scene: SceneSpec) -> None`；`capture_ground_truth() -> GroundTruthSnapshot` 仅供离线标注器/教师；`label_frame(frame: CapturedFrame, truth: GroundTruthSnapshot, instruction: str) -> SampleLabels`。

- [ ] 写测试：同配置同种子产生同 SceneSpec；改变物体/相机/光照参数会改变实际渲染；遮挡后的 bbox 与可见 mask 对齐；选点在可见 mask 且深度有效；不可见目标生成负例；不把隐藏中心当可见点。
- [ ] 运行并观察缺失模块/行为失败；以现有单方块场景作为固定基准。
- [ ] 实现单目标+0～3 干扰物的白名单场景采样、落物稳定性/边界/穿透拒绝；复用物理随机化与独立视觉随机种子。默认正例目标可见像素≥100、有效深度比例≥95%，具体范围写入 YAML 并记录到 manifest。
- [ ] 通过真实分割 pass 将 geom ID 映射到语义实例；生成指令、可见表面选点、目的地区域和真实位姿分层标签；测试 target/destination 的深度与投影一致。
- [ ] 运行 `MUJOCO_GL=egl .venv/bin/python -m pytest -q tests/test_rgbd_dataset_labels.py tests/test_rgbd_capture_session.py`，预期通过；交付 `feat: generate labeled randomized MuJoCo scenes`。

## Task 6：数据落盘、分组拆分、质检与恢复

**Files:** 新增 `datasets/rgbd/{writer,quality,splitter}.py`、`tests/test_rgbd_dataset_integrity.py`、`tests/test_rgbd_dataset_splits.py`。

**Interfaces:** models 增加 `SampleRecord`、`DatasetManifest`、`QualityReport`、`SplitManifest`；`DatasetWriter(root: Path, config: DatasetConfig).write_episode(records: Sequence[SampleRecord]) -> None`；`validate_dataset(root: Path) -> QualityReport`；`assign_splits(records: Sequence[SampleRecord], seed: int) -> SplitManifest`。

- [ ] 写测试：float32 深度往返无损；无 pickle/object dtype；100 个独立组分为80/10/10；同 episode/增强/指令变体不跨集合；改 seed 但场景相同仍识别重复；图像损坏、非法相对路径、缺标定不能进入有效索引。
- [ ] 增加崩溃恢复失败测试：落盘一半时不发布 sample；恢复后无重复计数；不同配置不能覆盖原 dataset_id。执行测试确认新行为缺失。
- [ ] 实现设计目录、schema_version=rgbd.dataset.v1、逐 episode 原子发布、checksum 索引、拒绝清单和资源统计；manifest 内容哈希不依赖墙钟时间。
- [ ] 实现基础场景先分组后增广、固定配额拆分、跨 split 内容重复检查和近重复报告；域外测试集单独冻结。运行两份相同配置生成结果比较可复现字段及数据哈希。
- [ ] 运行两个数据完整性/拆分测试文件，预期全部通过；交付 `feat: persist reproducible leak-resistant RGB-D datasets`。

## Task 7：批量生成、训练导出与离线回放

**Files:** 新增 `datasets/rgbd/{generator,exporters}.py`、`vision/offline_reader.py`、`scripts/{generate_rgbd_dataset,validate_rgbd_dataset,export_rgbd_training,replay_rgbd_sample}.py`、`configs/rgbd/{dataset_validation,dataset_full}.yaml`、`tests/test_rgbd_dataset_generation.py`、`tests/test_rgbd_training_export.py`。

**Interfaces:** `generate_dataset(config: DatasetConfig, output: Path, cancel: Callable[[],bool]) -> DatasetManifest`；`export_grounding_sft(root: Path, split: Literal['train','val'], output: Path) -> int`；`load_offline_observation(record: SampleRecord) -> RGBDObservation`；注册 job_type=DATASET_GENERATION。

- [ ] 写端到端测试：模型服务离线仍生成数据；达到采样5倍上限返回 INCOMPLETE；磁盘不足/取消保留有效 episode；训练导出拒绝 test split、只输出合格样本、标签没有混入用户消息；离线回放不伪造 captured_at。
- [ ] 运行失败测试后实现批内资源复用、预算估算、checkpoint、统计与默认单渲染进程；取消最多在当前有界样本完成后生效。
- [ ] 实现通用 JSONL SFT 导出：user 为指令+RGB路径+深度图路径，assistant 为目标像素/结构化技能标签；保留原始深度/标定路径。SKILL_PLAN 模板记录 execution_verified=false，不混入经过执行的 TRAJECTORY 导出。
- [ ] 用 smoke 配置生成100组，运行 validator 并导出80个训练组、10个验证组；再用 validation 配置1000组检查资源和质量；CLI 所有异常退出码和取消状态可区分。
- [ ] 交付 `feat: generate and export local RGB-D training datasets`，此时 M2 可在没有大模型和动作执行器时独立验收。

## Task 8：物理位姿控制与高层技能适配

**Files:** 新增 `simulation/mujoco/{motion_controller,skill_robot,episode_evaluator}.py`、`tests/test_rgbd_physical_skills.py`；修改 backend、参考 scene.xml、必要的 `edge/safety/context_builder.py`，保持 `edge/runtime/skill_registry.py::RuntimeSkillRobot` 协议。

**Interfaces:** `MuJoCoMotionController(backend).move_tcp(target: MotionTarget, timeout_s: float) -> MotionResult`；`motion_controller.py` 定义 MotionTarget(position: Pose, orientation_wxyz: tuple[float,float,float,float]) 和 MotionResult（实际位置/朝向误差、步数、状态），因现有 contracts.Pose 只有 xyz，不能用于表达完整抓取朝向；`MuJoCoSkillRobot` 实现 RuntimeSkillRobot；`episode_evaluator.py` 定义 CompletionCriteria、EpisodeOutcome 和 `evaluate_episode(backend, criteria: CompletionCriteria) -> EpisodeOutcome`，只读评估不向控制器提供真值。

- [ ] 写失败物理测试：move_tcp 必须增加物理步数且实际 TCP 到达目标（固定 fixture 位置误差≤0.005 m、朝向误差≤5°）；未接触时闭合不能成功 GRASP；不可达目标失败；执行期间 object qpos 不得被控制逻辑直接赋值。
- [ ] 检查当前简化机器人夹爪行程、碰撞、关节与 TCP 定义，先验收自由空间定位，再验收抓取；将发现的资产限制记录为模型版本变化。
- [ ] 实现基于 MuJoCo 运动学/Jacobian 的有界迭代 IK、关节限位、速度限制和执行超时；夹爪通过 actuator+step 驱动。三维表面点到夹爪位姿的变换只针对第一版已知方块/顶抓任务，不能假定支持任意物体。
- [ ] 通过物理状态检查离桌举升、移动、释放、目标区域包含和连续0.5秒稳定；失败保留接触与轨迹证据。机器人模型不支持时修正参考资产并重新跑物理测试，不替换成软件状态赋值。
- [ ] 执行 `MUJOCO_GL=egl .venv/bin/python -m pytest -q tests/test_rgbd_physical_skills.py`，所有固定成功/失败 fixture 通过后交付 `feat: execute high-level skills through MuJoCo physics`。

## Task 9：教师示范与轨迹数据

**Files:** 新增 `datasets/rgbd/teacher.py`、`scripts/generate_rgbd_trajectories.py`、`configs/rgbd/trajectory_smoke.yaml`、`tests/test_rgbd_trajectory_dataset.py`；扩展 models/writer/generator。

**Interfaces:** `run_teacher_episode(scene: SceneSpec, robot: MuJoCoSkillRobot, recorder: EpisodeRecorder) -> EpisodeOutcome`；writer 定义 `EpisodeRecorder` 记录时间一致的 observation/state/action/next_observation、技能边界与结果。teacher_mode 固定 GROUND_TRUTH_TEACHER。

- [ ] 写测试：每段动作来自真实执行命令；完整轨迹 sim_time 单调；失败抓取不进入成功 SFT；同轨迹全部帧只属于一个 split；教师标签含 source 和 execution_verified。
- [ ] 运行失败测试，完成教师控制器调用与按 sensor_dt_s 记录；记录频率配置与 physics/control 网格对齐，不能为补帧复制同一观测冒充新帧。
- [ ] 生成20个教师 episode，包括已知成功和失败 fixture；从真实接触/释放/落位判定结果，不按脚本跑完自动成功。
- [ ] 校验动作/下一帧对应关系、质量报告与完整状态重放；失败轨迹独立导出用于诊断或失败识别训练。
- [ ] 交付 `feat: record verified RGB-D demonstration trajectories`，M3 与模型精度解耦验收。

## Task 10：视觉闭环、模型评测与性能

**Files:** 新增 `vision/{execution,evaluation}.py`、`scripts/{run_rgbd_smoke,evaluate_rgbd_model}.py`、`configs/rgbd/evaluation.yaml`、`tests/test_rgbd_closed_loop.py`；修改 worker 的 VISION_CLOSED_LOOP 分支。

**Interfaces:** `run_visual_episode(planner: RGBDPlannerAdapter, robot: MuJoCoSkillRobot, capture: MuJoCoCaptureSession, policy: ExecutionPolicy) -> EpisodeOutcome`；`evaluate_model(dataset: Path, split: Literal['val','test'], planner, output: Path) -> EvaluationReport`。ExecutionPolicy/EvaluationReport 在 vision/evaluation.py 定义，统一记录评测分母与环境阻塞。

- [ ] 写测试：目标在规划后移动触发重新观测/暂停；投放诱饵真值也不改变视觉请求；模型超时后不执行旧目标；只有实际成功才 task_success；离线历史图像不被当作当前控制输入。
- [ ] 使用 Task 8 的技能执行器，关键技能前校验新观测；感知图像以实际捕获尺寸解释像素，服务若有缩放须显式映射；闭环控制器不依赖离线标签。
- [ ] 离线评测先跑 val，使用专用 evaluator 调用图像推理和解析，保留历史 captured_at，结果禁止进入在线 dispatch；冻结提示/配置后跑20个独立 test 场景的视觉闭环。分别输出像素/三维误差、无效深度率、JSON/技能有效率、执行成功率和失败原因，不排除失败样本抬高成功率。
- [ ] 测量冷/热启动、采集/编码/完整有效决策延迟、p50/p95与显存。流式模式单独测 TTFT；非流式明确 NOT_MEASURED。写明硬件、模型量化和运行版本，形成实测后才设性能预算。
- [ ] 交付 `feat: evaluate vision-driven MuJoCo episodes`；本地模型未安装/不可达时 M4 标记 BLOCKED_BY_ENV，M2/M3 结果仍有效，不能伪造模型通过。

## Task 11：工作台、数据入口与 Isaac 兼容

**Files:** 修改现有 dashboard 工作台/模型页、`cloud/api/vision.py`、simulation job 模型；新增 `cloud/api/rgbd_datasets.py`、`dashboard/src/simulation/pages/RGBDDatasetPage.tsx`、`tests/test_rgbd_dataset_api.py`；修改 `simulation/isaac/backend.py`、`scripts/phase9/isaac_standalone_app.py`、`tests/test_rgbd_isaac_transport.py`；重生成 OpenAPI。

**Interfaces:** `/api/v1/vision/observations` 延续采集；新增 `POST /api/v1/rgbd-datasets/jobs`、`GET /api/v1/rgbd-datasets/jobs/{job_id}`、`POST .../{job_id}/cancel` 与按 dataset_id/sample_id 读取预览的接口。API 只接受配置 allowlist、样本数量/种子/分辨率，无自由脚本、任意导出路径或 shell。

- [ ] 写 API/前端测试：默认视觉输入；服务缺失可采集数据；输入方式/执行范围清晰；图片预览与深度范围匹配；进度来自真实索引；只读用户无法启动任务；路径穿越与跨数据集访问拒绝。
- [ ] 写 Isaac 传输测试：实际 RGB bytes、米制深度、ROS optical camera pose 和标定完整；像素缺失/不同步不能返回正常 RGBD；runtime 不存在时明确阻塞。
- [ ] 实现数据生成页、训练/验证/测试统计与拒绝原因、模型像素叠加预览；共用现有 runtime 队列和模型配置解析，按能力展示 CAPTURE_ONLY/VISUAL_PLANNING/VISION_CLOSED_LOOP。
- [ ] 运行 API 测试、生成 schema、前端 typecheck/lint/test/build；E2E 用实际 MuJoCo采集及模型不可用路径验收。Isaac 仅在实际 runtime 可用时验收相机采集；不把协议测试称为 Isaac 物理任务通过。
- [ ] 交付 `feat: expose RGB-D datasets and execution evidence in workbench`。

## Task 12：完整验收、文档与发布前审查

**Files:** 新增/补充 `docs/rgbd_setup.md`、`docs/rgbd_dataset_format.md`、`docs/rgbd_validation.md`、必要的 README 链接；维护本计划复选框和运行证据。模型目录优先列出视觉模型，文本模型保留明确 legacy 说明。

**Interfaces:** 所有报告区分 software tests / actual rendering / model inference / physics execution；最终提供可复现 CLI 与产物路径。

- [ ] 运行完整软件测试与静态检查：`.venv/bin/python -m ruff check src tests scripts`、`.venv/bin/python -m mypy src`、`MUJOCO_GL=egl .venv/bin/python -m pytest -q -m 'not isaac and not isaac_runtime and not real_robot_runtime and not ros2 and not benchmark'`。硬件/重型标记测试单独列明，不能报告“全量通过”。
- [ ] 执行前端 `api:generate`、`typecheck`、`lint`、`test`、`build` 及 RGB-D E2E；核对生成 schema 与新字段完全一致。
- [ ] 核验100/1000组数据报告、20个教师 episode、20个视觉测试场景（服务可用时）；通过资源预算后才执行10000组 full。保存失败样本和未通过里程碑，不能以未执行替代通过。
- [ ] 按执行技能要求做一次完整独立代码审查，重点检查真值泄露、RGB-D 对齐、拆分泄露、任务状态与物理真实性；实质问题补回归后修复。
- [ ] 文档注明安装/启动、接口、数据读取、split、SFT导出、恢复、性能实测、资产限制和验收范围。只整理本次变更，未经用户要求不推送/部署或覆盖已有数据。

## 计划中的命令入口（实施后提供，当前不可视为已可运行）

```bash
source scripts/linux/env.sh
python scripts/run_rgbd_smoke.py --scope capture --output artifacts/rgbd/capture
python scripts/generate_rgbd_dataset.py --config configs/rgbd/dataset_smoke.yaml --output datasets/rgbd-smoke-v1
python scripts/validate_rgbd_dataset.py --dataset datasets/rgbd-smoke-v1
python scripts/export_rgbd_training.py --dataset datasets/rgbd-smoke-v1 --split train --format grounding-sft
python scripts/generate_rgbd_trajectories.py --config configs/rgbd/trajectory_smoke.yaml --output datasets/rgbd-trajectories-v1
python scripts/run_rgbd_smoke.py --scope planning --output artifacts/rgbd/planning
python scripts/evaluate_rgbd_model.py --dataset datasets/rgbd-smoke-v1 --split val --output artifacts/rgbd/eval-val
```

CLI 的 --scope capture/planning 分别映射 CAPTURE_ONLY/VISUAL_PLANNING，闭环另设 --scope closed-loop；不会从请求中接受未知枚举。开启模型前先完成 Ollama视觉能力探测；数据生成不依赖该探测成功。

## 数据量与资源预算

仅原始 float32 深度：320×240 每帧307200字节，10000帧约3.072 GB；640×480 每帧1228800字节，10000帧约12.288 GB（十进制）。RGB、实例 mask、轨迹、重放状态与索引额外占用空间，不能把上述数值当总大小。先用100帧测实际每帧磁盘、样本/秒与显存峰值，再计算 full 的磁盘/时间预算；不预先承诺“实时”或具体生成速度。

## 总体验收清单

- [ ] 采集文件确实来自 MuJoCo 渲染且 RGB/深度/分割同步，标定与米制深度验证通过。
- [ ] 在线模型请求包含两幅图像，未包含仿真真值；目标变动能改变视觉定位结果。
- [ ] 大模型离线也能生成、恢复、质检、拆分和导出数据集。
- [ ] train/val/test 无同组泄露或已知内容重复，测试集不进入训练导出。
- [ ] 正例、负例、模板计划、物理成功/失败示范都有明确来源与不同状态。
- [ ] 物理动作由 actuator+step 产生，未通过状态赋值伪造运动或抓取成功。
- [ ] 任务取消、超时、模型缺失、磁盘不足均保留一致状态与可检查证据。
- [ ] 工作台默认RGBD，历史软件模式显式选择，所有验收结论对应实际运行。

## 计划自审

需求覆盖映射：直接视觉输入→Tasks 2～4；本地无模型数据生成→Tasks 5～7；真值仅标签/教师/评估→Tasks 3/5/9/10；真实动作示范→Tasks 8～9；默认工作台→Tasks 4/11；闭环与性能→Task 10；Isaac兼容→Task 11；回归/文档→Tasks 1/12。类型先在 Interfaces 指定责任文件，再由后续任务消费；工作包 B 不依赖工作包 C。关键设计选择和精度/数量阈值均在 spec 固定或明确为待实测结果，不用生成计划替代功能验收。
