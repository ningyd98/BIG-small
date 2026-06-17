# BIG-small

BIG-small 是一个面向边缘智能场景的小型机械臂云边协同控制系统，采用”云端智能规划、边缘安全执行”架构。当前版本完成 Phase 0–9 core：仓库初始化、配置、数据契约、结构化错误/日志、MockRobotAdapter、技能注册表、边缘执行运行时、可追溯状态机、边缘安全盾、云端规划/监督/重规划、PCSC、ETEAC、Skill Cache、RiskEvaluator、AUTO 双模式选择、ModeTransition 持久化、Phase 8.2 周期闭环和真实检测延迟修复，以及 Phase 9 MuJoCo 物理仿真、物理指标、Domain Randomization 和 Sim2Real readiness 验证；Phase 9.1 已完成 ROS 2 runtime validation 和 MoveIt 2 safety validation，并保留 Isaac Sim 与 cross-backend 的环境阻塞状态。Phase 9.2 已新增 Isaac Sim 6.0 standalone/container 运行命令、真实 Isaac smoke artifact contract、MuJoCo-Isaac paired comparison verifier 和最终 aggregate verifier；当前主机尚未配置 Isaac Sim 6.0，因此 Phase 9.2 不能声明 accepted。

Phase 9.1 当前状态是 `PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK`：ROS 2 runtime 为 `ROS2_INTEGRATION_VALIDATED`，MoveIt 2 safety 为 `MOVEIT_SAFETY_VALIDATED`，Isaac Sim 为 `BLOCKED_BY_ENV`，cross-backend comparison 为 `BLOCKED_BY_ENV`。本仓库没有连接真实机械臂，real robot validation not started，不声明真实硬件验证完成。真实机械臂 SDK、实体急停、真实相机标定和真实物理性能验证属于 Phase 10。

Phase 9.2 当前主机状态是环境阻塞：Vulkan tooling 已可用，且本机发现 `$HOME/.venvs/bigsmall-isaacsim-6.0.0.1` Isaac venv；但 Isaac 首次启动仍需要 NVIDIA Omniverse/Isaac EULA 交互确认，因此 Isaac Sim 6.0 真实进程启动、stage 加载、physics step、robot state、RGB/depth/contact sensor 采样、Isaac benchmark 和 MuJoCo-Isaac 真实跨后端比较尚未完成。兼容主机必须使用官方 Isaac standalone runtime 或固定 digest 的官方 container 运行真实验证。

## 仓库现状

初始化审查时仓库仅包含：

- `docs/plan.md`：系统总体规划。
- `docs/面向边缘智能场景的小型机械臂云边协同控制系统的设计.docx`：设计文档。

当前新增了可运行 Python 包、测试、配置、脚本和阶段报告，并已同步到 GitHub 仓库 `ningyd98/BIG-small.git`。

## 当前能力

- 统一消息追踪字段：`task_id`、`plan_version`、`command_seq`、`timestamp`。
- Pydantic 数据模型：`TaskContract`、`Telemetry`、`CloudCommand`、`CommandAck`、`EdgeEvent`、`FailureSummary`、`SkillTemplate`。
- JSON Schema 由 Pydantic `model_json_schema()` 导出，并通过契约示例测试验证。
- 边缘契约校验器：支持 schema 校验、过期检查、计划版本检查、命令序号去重和未知技能拒绝。
- Phase 1 Mock 机械臂：支持统一 `RobotAdapter` 接口、动作耗时模拟、超时、故障注入和状态查询。
- 固定技能注册表：13 个原子技能均通过 `SkillName` 枚举注册，不通过字符串动态执行任意函数。
- Phase 1.1 固定流程安全收口：首个失败后短路、记录 `failed_step_id` 和 `skipped_steps`，并触发停机动作。
- Phase 2 边缘运行时：`TaskContract -> EdgeContractValidator -> TaskStateMachine -> TaskRuntimeContext -> SkillRegistry -> SkillExecutor -> RobotAdapter -> Repository -> AuditLog`。
- Repository：提供 `InMemoryRepository` 和 `SQLiteRepository`，持久化任务、状态转换、步骤执行、动作执行、已接受命令和审计事件。
- 防重放：持久化 `plan_version`、`command_seq` 和 payload hash；支持重启后 replay 拒绝和相同序号不同负载冲突检测。
- 崩溃恢复：进程重启后处于 `EXECUTING` 的任务会被标记为 `PAUSED`，并写入 `RUNTIME_RECOVERY_REQUIRED`。
- Phase 5 周期监督 API：支持 supervision capabilities、机器人状态上报、手动监督 tick、决策查询、start/stop/status。
- Phase 5 监督持久化：提供 `InMemorySupervisionRepository` 和 `SQLiteSupervisionRepository`，持久化状态快照、监督决策、任务运行状态和监督审计事件，并提供版本 CAS 防并发重复升级。
- Production 配置：`RUNTIME_PROFILE=production` 时必须显式配置数据库、MQTT、Planner、RobotAdapter、TelemetryProvider、SceneStateProvider、监督仓库和监督调度器，不会静默回落到 Mock/Fake/InMemory 默认值。
- Phase 6.2 事件触发边缘自治封板：`EventAutonomyRepository` 提供 InMemory/SQLite 实现，持久化事件、恢复预算、状态机、FailureSummary、CompletionSummary、LocalReplanningRequest/Result、Outbox、审计和计划版本；TaskExecutor 的 `RETRY_STEP` 真实重试同一步骤；SQLite 重启后可恢复 active contract、checkpoint、已完成步骤和当前步骤；`LocalReplanningService` 从仓储读取上下文；`ReplanMergeValidator` 保护已完成步骤；`ReplanApplyService` 通过 CAS 更新 active contract；CompletionEvaluator 阻止仅凭步骤耗尽或调用方声明成功；API 连接真实仓储和服务。
- Phase 7 Skill Cache：持久化高层技能模板、参数模板和执行统计，支持 InMemory/SQLite、晋升、隔离、失效、TTL、CAS、幂等和重启恢复；缓存不保存底层控制量，命中后仍必须经过 TaskContract、ContractValidator 和 SafetyShield。
- Phase 7 Risk-Aware Scheduler：`RiskEvaluator` 基于版本化 `RiskPolicy` 计算 task、scene dynamics、perception、network、execution、safety 六类风险分量；缺失输入 fail-closed，SafetyShield emergency stop 硬覆盖为 CRITICAL。
- Phase 7 AUTO Mode Selector：AUTO 不是第三种执行模式，只在 `PERIODIC_CLOUD_SUPERVISION` 与 `EVENT_TRIGGERED_EDGE_AUTONOMY` 间做确定性选择，或保持当前模式、请求观察、暂停、安全停止；切换受 dwell time、cooldown、switch limit 和安全边界约束。
- Phase 8 可复现实验：新增强类型实验模型、离散事件虚拟时钟、seed 驱动网络仿真、15 个故障场景、PCSC/ETEAC/AUTO 统一运行接口、Skill Cache 与 AUTO 信号消融、安全 shadow counterfactual、统计汇总、artifact 导出、Markdown 报告和 `scripts/verify_phase8.py`。
- Phase 8.1 实验真实性修复：`RuntimeExperimentHarness` 将 Phase 8 实验接入真实 `TaskExecutor`、`SafetyShield`、`PeriodicSupervisorService`、`EventTriggeredModeController`、`LocalReplanningService`、`ReplanApplyService` 和 `ModeTransitionService`；故障交错、命令一致性、崩溃恢复和事件溯源指标都来自正式运行证据。
- Phase 8.2 周期闭环和实验敏感性：PCSC tick 使用虚拟时钟周期调度并与步骤交错；fault detected 不再由 fault injected 直接产生；AUTO 在安全边界提交；S15 覆盖 9 个 crash point；实验 guard 检查 mode/network/seed 敏感性。
- Phase 9 MuJoCo 物理仿真：新增 `SimulatorBackend`、`MuJoCoPhysicsBackend`、`PhysicsRobotAdapter`、物理 sensor/contact/metric provenance、Domain Randomization、Phase 9 benchmark runner 和环境探测。Isaac Sim、ROS 2、MoveIt 2 路径为 guarded integration，缺环境时输出 `BLOCKED_BY_ENV`。
- Phase 9.1 ROS 2 / MoveIt runtime acceptance：ROS 2 已通过真实 rclpy runtime evidence，覆盖 QoS、namespace、timestamp、action success/timeout/cancel、stale feedback、node crash 和 reconnect；MoveIt 2 已通过真实 safety evidence，覆盖 reachability、unreachable target、joint limit rejection、PlanningScene collision object insertion、collision-path rejection/replanning、planning timeout、execution cancellation、emergency-stop boundary 和 BIG-small execution boundary。Isaac Sim 与 cross-backend comparison 仍仅因宿主环境缺失保持 `BLOCKED_BY_ENV`，不计为 pass。
- Phase 9.2 Isaac / cross-backend acceptance：新增 `scripts/verify_phase9_2_environment.py`、`scripts/verify_phase9_2_isaac_smoke.py`、`scripts/run_phase9_2_cross_backend.py` 和 `scripts/verify_phase9_2.py`。普通 CI 只验证 source/protocol/artifact contract，不声称 Isaac runtime validated；兼容 Isaac 主机必须生成真实 smoke、benchmark 和 paired-run artifacts 后才可能得到 `PHASE9_2_ACCEPTED`。
- 结构化 JSON 日志工具和 `.env.example`。

## 目录结构

```text
.
├── configs/                  # 可复现实验和本地运行配置
├── contracts/                # 契约 JSON 示例与 schema 说明
├── data/                     # SQLite 等本地运行数据目录
├── docs/                     # 设计文档、阶段报告和差距分析
├── edge/                     # 边缘模块顶层说明
├── scripts/                  # 一键检查和 Phase 1 demo 脚本
├── shared/                   # Phase 0/1 冻结路线说明
├── simulation/               # 仿真模块顶层说明
├── src/cloud_edge_robot_arm/
│   ├── cloud/                # 云端规划、监督、重规划模块目录
│   ├── contracts/            # 任务契约和消息模型
│   ├── edge/                 # 边缘校验、技能注册表、技能执行器
│   ├── risk/                 # Phase 7 确定性风险评估
│   ├── skill_cache/          # Phase 7 高层技能缓存
│   ├── auto_mode/            # Phase 7 AUTO 选择和模式切换
│   ├── experiments/          # Phase 8 实验模型、runner、统计和 artifact
│   └── simulation/           # Mock、MuJoCo backend、PhysicsRobotAdapter、ROS/Isaac guards
└── tests/                    # Phase 0/1 单元测试
```

## 本地运行

推荐使用一键脚本：

```bash
./scripts/start_phase1_demo.sh
```

该脚本会创建 `.venv`、安装开发依赖、运行测试，并执行一次 Mock pick-and-place 技能序列。

单独运行检查：

```bash
./scripts/run_checks.sh
```

手动命令：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev,sim-mujoco,sim-analysis]"
python -m compileall src scripts tests
python -m ruff format --check .
python -m ruff check .
python -m mypy .
python -m pytest -q
python scripts/verify_phase6.py
python scripts/verify_phase6_2.py
python scripts/verify_phase7.py
python scripts/verify_phase8.py
python scripts/verify_phase8_1.py
python scripts/verify_phase8_2.py
python scripts/verify_phase9.py
source scripts/phase9/activate_ros2_moveit_env.sh
python scripts/verify_phase9_1_ros2_integration.py --output artifacts/phase9_1/ros2
python scripts/verify_phase9_1_moveit_safety.py --output artifacts/phase9_1/moveit
python scripts/verify_phase9_1.py --output artifacts/phase9_1
python scripts/verify_phase9_2_environment.py --output artifacts/phase9_2/environment
python scripts/verify_phase9_2_isaac_smoke.py --output artifacts/phase9_2/isaac
python scripts/run_phase9_2_isaac_benchmark.py --output artifacts/phase9_2/isaac_benchmark
python scripts/run_phase9_2_cross_backend.py --output artifacts/phase9_2/cross_backend
python scripts/verify_phase9_2.py --output artifacts/phase9_2/final
python -m pip check
```

阶段验收命令：

```bash
ruff check .
mypy .
pytest -q
python scripts/validate_contract_examples.py
python scripts/run_fixed_pick_place.py --adapter mock
python scripts/run_fixed_pick_place.py --adapter mock --repeat 20
python scripts/run_fault_injection_suite.py
python scripts/run_phase2_task.py --repository sqlite
python scripts/run_phase2_failure_case.py --fault GRASP_FAILED
python scripts/run_phase2_replay_test.py
python scripts/run_phase2_restart_recovery_test.py
python scripts/verify_phase2.py
python scripts/verify_phase3.py
python scripts/verify_phase3_1.py
python scripts/verify_phase3_2.py
python scripts/verify_phase4.py
python scripts/verify_phase5.py
python scripts/verify_phase6.py
python scripts/verify_phase6_2.py
python scripts/verify_phase7.py
python scripts/verify_phase8.py
python scripts/verify_phase8_1.py
python scripts/verify_phase8_2.py
python scripts/verify_phase9.py
source scripts/phase9/activate_ros2_moveit_env.sh
python scripts/verify_phase9_1_ros2_integration.py --output artifacts/phase9_1/ros2
python scripts/verify_phase9_1_moveit_safety.py --output artifacts/phase9_1/moveit
python scripts/verify_phase9_1.py --output artifacts/phase9_1
python scripts/verify_phase9_2_environment.py --output artifacts/phase9_2/environment
python scripts/verify_phase9_2_isaac_smoke.py --output artifacts/phase9_2/isaac
python scripts/run_phase9_2_isaac_benchmark.py --output artifacts/phase9_2/isaac_benchmark
python scripts/run_phase9_2_cross_backend.py --output artifacts/phase9_2/cross_backend
python scripts/verify_phase9_2.py --output artifacts/phase9_2/final
python -m pip check
```

## 阶段状态

- Phase 0：已完成，见 `docs/phase0_acceptance.md`。
- Phase 1：已完成，见 `docs/phase1_acceptance.md`。
- Phase 1.1：已完成，见 `docs/phase1_1_report.md`。
- Phase 2：已完成，见 `docs/phase2_design.md`、`docs/phase2_acceptance.md` 和 `docs/phase2_report.md`。
- Phase 3：已完成，见 `docs/phase3_design.md`、`docs/phase3_acceptance.md` 和 `docs/phase3_report.md`。
- Phase 3.1：已完成，见 `docs/phase3_1_design.md`、`docs/phase3_1_acceptance.md` 和 `docs/phase3_1_report.md`。
- Phase 3.2：已完成，见 `docs/phase3_2_design.md`、`docs/phase3_2_acceptance.md` 和 `docs/phase3_2_report.md`。
- Phase 4：已完成，见 `docs/phase4_design.md`、`docs/phase4_acceptance.md` 和 `docs/phase4_report.md`。
- Phase 5：已完成并已回顾性加固，见 `docs/phase5_report.md` 和 `docs/reviews/phase5_retrospective_review.md`。
- Phase 6.1：已完成事件触发边缘自治闭环真实性修复与生产持久化收口，见 `docs/event_triggered_autonomy.md`、`docs/local_recovery.md`、`docs/local_replanning.md`、`docs/network_degradation.md` 和 `docs/phase6_1_closure_report.md`。
- Phase 6.2：已完成最终验收与封板，明确 checkpoint 权威来源、重规划合并规则、CAS/幂等语义、SQLite 崩溃恢复流程、完成证据模型和 InMemory/SQLite 使用边界，见 `docs/phase6_2_design.md`、`docs/phase6_2_acceptance.md` 和 `docs/phase6_2_report.md`。
- Phase 7：已完成 Skill Cache、风险感知调度、AUTO 双模式选择、ModeTransition 持久化和生产配置门禁，见 `docs/skill_cache.md`、`docs/risk_policy.md`、`docs/auto_mode_selection.md`、`docs/mode_transition.md`、`docs/phase7_acceptance.md` 和 `docs/phase7_report.md`。
- Phase 8：已完成可复现仿真实验框架、双模式/AUTO 对比、故障注入、消融、统计和 artifact 导出；当前仍没有真实硬件、真实相机模型、生产 LLM CI 或真实物理 benchmark。
- Phase 8.1：已完成实验真实性和生产执行链路接入修复，Phase 8 实验现在通过真实 runtime chain 产出 evidence；当前仍是 mock/sim 证据，不是硬件验证。
- Phase 8.2：已完成周期闭环、真实故障检测延迟、安全边界切换、多 crash point 恢复和实验敏感性 guard，见 `docs/phase8_2_design.md`、`docs/phase8_2_acceptance.md` 和 `docs/phase8_2_report.md`。
- Phase 9：已完成 MuJoCo core readiness，见 `docs/phase9_design.md`、`docs/phase9_mujoco_backend.md`、`docs/phase9_experiment_design.md`、`docs/phase9_report.md` 和 `docs/phase9_sim2real_readiness.md`。
- Phase 9.1：已完成 ROS 2 runtime validation 和 MoveIt 2 safety validation；当前主机因 Isaac Sim 与 cross-backend comparison 环境缺失保持 `PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK`，见 `docs/phase9_1_acceptance.md` 和 `docs/phase9_1_report.md`。
- Phase 9.2：已完成 Isaac Sim 6.0 runtime/cross-backend verifier contract 与运行入口；当前主机仍因缺 Isaac runtime 保持环境阻塞，见 `docs/phase9_2_design.md`、`docs/phase9_2_environment.md`、`docs/phase9_2_isaac_backend.md`、`docs/phase9_2_cross_backend.md`、`docs/phase9_2_acceptance.md` 和 `docs/phase9_2_report.md`。
