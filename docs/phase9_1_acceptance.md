# Phase 9.1 验收

Phase 9.1 收紧 Phase 9 引入的 ROS 2、MoveIt 2、Isaac Sim 和跨后端验证边界。

当前主机已经完成 ROS 2 和 MoveIt 2 runtime 验证，但因为 Isaac Sim、Isaac benchmark 验证和跨后端对比仍受环境阻塞，Phase 9.1 只能接受为 `PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK`。

## 状态词汇

- `PHASE9_1_ACCEPTED`：核心 Phase 9 检查通过，并且 ROS 2、MoveIt 2、Isaac Sim、Isaac benchmark、跨后端验证都在兼容主机上真实运行，运行证据完整。
- `PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK`：核心 Phase 9 检查通过，ROS 2 为 `ROS2_INTEGRATION_VALIDATED`，MoveIt 2 为 `MOVEIT_SAFETY_VALIDATED`，只有 Isaac Sim 和依赖 Isaac 的跨后端对比受主机环境阻塞。
- `PHASE9_1_REJECTED`：核心回归、安全压力、artifact 完整性或验证器执行失败。

## 必需命令

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
scripts/phase9/install_ros2_jazzy.sh --artifact-dir artifacts/phase9_1/install
scripts/phase9/install_vulkan_runtime.sh --artifact-dir artifacts/phase9_1/install
ARTIFACT_DIR=artifacts/phase9_1/install python scripts/phase9/check_isaac_sim.py
python scripts/verify_phase9_1.py
python scripts/verify_phase9_1_ros2_integration.py
python scripts/verify_phase9_1_moveit_safety.py
python scripts/verify_phase9_1_isaac_smoke.py
python scripts/verify_phase9_1_cross_backend.py
```

完整本地 Phase 9.1 runtime 验收顺序：

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
python -m ruff format --check .
python -m ruff check .
python -m mypy .
python -m pytest -q
python scripts/verify_phase9.py
source scripts/phase9/activate_ros2_moveit_env.sh
python scripts/verify_phase9_1_ros2_integration.py --output artifacts/phase9_1/ros2
python scripts/verify_phase9_1_moveit_safety.py --output artifacts/phase9_1/moveit
python scripts/verify_phase9_1.py --output artifacts/phase9_1
```

只在 CI 中检查 artifact 结构、不重跑 Phase 9 历史时：

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
python scripts/verify_phase9_1.py --skip-history
```

## 守卫规则

- ROS 2、MoveIt 2 或 Isaac Sim 检查被环境阻塞时，命令可以成功退出，但这只表示验证器本身正常工作。
- artifact 仍必须写入 `status=BLOCKED_BY_ENV` 和 `validation_claimed=false`。
- `ROS2_INTEGRATION_VALIDATED` 需要 `ros2_runtime_evidence.json`，其中 QoS、namespace、timestamp、action timeout、cancel 和 node crash/reconnect 证据都通过。
- `MOVEIT_SAFETY_VALIDATED` 需要 `moveit_safety_evidence.json`，其中可达性、关节限制、碰撞场景、规划失败、执行取消和急停边界证据都通过。
- 主机可用 ROS 2 时，只有 `ROS2_INTEGRATION_VALIDATED` 能满足核心验收；`ROS2_READY`、`INCOMPLETE`、`FAILED` 和未知状态都会导致 `PHASE9_1_REJECTED`。
- 主机可用 MoveIt 2 时，只有 `MOVEIT_SAFETY_VALIDATED` 能满足核心验收；`MOVEIT_READY`、`INCOMPLETE`、`FAILED` 和未知状态都会导致 `PHASE9_1_REJECTED`。
- `BLOCKED_BY_ENV` 只允许用于确实缺少主机 runtime 依赖的组件。Isaac 的 `BLOCKED_BY_ENV` 不能掩盖缺失的 ROS 2 或 MoveIt runtime 证据。
- MoveIt 碰撞证据必须包含 baseline plan、插入的 collision object、带对象 ID/位置/尺寸的 PlanningScene 确认、重规划或拒绝结果、collision-free 依据、trajectory delta、MoveIt error code、观测结果、进程溯源和干净日志。
- 规划超时证据必须先证明同一目标在正常预算下成功，再使用极短预算；普通不可达目标或无效约束失败不能冒充超时证据。
- runtime 证据日志如果包含非白名单的 `Traceback`、`Segmentation fault`、`RCLError` 或 `process exited unexpectedly`，则证据不完整。
- `ISAAC_SMOKE_VALIDATED` 需要 `isaac_smoke_evidence.json` 证明独立 Isaac 进程加载 stage、推进物理、返回机器人状态，并产生 RGB、depth 和 contact sensor 样本。
- 软件可用性本身只能产生 `NOT_RUN`、`MOVEIT_READY`、`ISAAC_READY` 或 `INCOMPLETE`，绝不能设置 `validation_claimed=true`。
- 每个受阻组件都要记录确认阻塞的实际命令、退出码、stdout 和 stderr。
- 安装准备默认 dry-run，并必须记录核心 Python 未被修改。
- 独立进程协议测试只能证明 JSONL handshake 和 replay 拒绝，不能证明 Isaac 验证。
- Isaac 后端守卫只能证明 JSONL 上的 `SimulatorBackend` 协议适配，不能证明 Isaac runtime 验证。
- Isaac benchmark 守卫必须运行 `--backend isaac` 入口；主机受阻时不能回退到 MuJoCo。
- `scripts/phase9/isaac_standalone_app.py --check-imports` 必须在选定 Python 环境中运行，并记录 Isaac runtime import 和 `SimulationApp` startup 是否可用。
- ROS 2 接口源码守卫只能证明 message/action/service 覆盖，不能证明 ROS build 或 runtime 验证。
- ROS 2 bridge 源码守卫只能证明 rclpy node、action timeout/cancel、feedback stale、reconnect state 和 frame-conversion 源码覆盖，不能证明 ROS runtime 验证。
- MoveIt 源码守卫只能证明 planning-boundary 源码覆盖，不能证明 MoveIt 2 规划或执行验证。
- Isaac Sim 验证必须有大于 0 的真实 Isaac run count，才允许 `validation_claimed=true`。
- 跨后端验证需要真实 MuJoCo 和 Isaac artifact，包含 `backend_name`、`run_id`、`process_provenance`、`validation_claimed=true` 和可比较指标。只有 `env.level=ISAAC_READY` 不够。
- `PHASE9_1_ACCEPTED` 还要求已验证的 Isaac benchmark artifact、完整 cross-backend deltas、完整 artifact 溯源、安全压力 `trial_count>=500`、`illegal_collision_count=0`、`emergency_stop_post_command_count=0`，以及非静态 result hashes。

## 当前主机结果

当前结果是：

```text
PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK
```

阻塞组件：

- Isaac Sim：`ISAAC_SIM_ROOT` 未设置，Vulkan 工具不可用。
- 跨后端对比：同样缺少 Isaac runtime 和真实 Isaac artifact。

已验证组件：

- ROS 2：`ROS2_INTEGRATION_VALIDATED`，证据为 `ros2_runtime_evidence.json`。
- MoveIt 2：`MOVEIT_SAFETY_VALIDATED`，证据为 `moveit_safety_evidence.json`。

真实机械臂验证尚未开始。MoveIt 仍是规划和安全证据 runtime；执行仍经过 BIG-small 边缘安全边界。
