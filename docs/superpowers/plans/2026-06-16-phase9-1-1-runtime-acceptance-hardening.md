# Phase 9.1.1 Runtime 验收加固实施计划

> **给 agentic worker：** 必须使用 superpowers:subagent-driven-development，或使用 superpowers:executing-plans 逐项执行本计划。步骤用 checkbox（`- [ ]`）跟踪。

**状态：** 2026-06-16 完成，最终 Phase 9.1 验证已通过。

**目标：** 加固 Phase 9.1 的 ROS 2 / MoveIt runtime 验收，避免环境阻塞掩盖缺失的 runtime 证据，并让 artifact 包含可审计的 MoveIt collision、timeout、shutdown 和 log-integrity 证据。

**架构：** 保留现有 verifier 和 runner 入口，但收紧它们的契约。在 `scripts/verify_phase9_1.py` 中增加显式 aggregate helper，在 `src/cloud_edge_robot_arm/simulation/phase9_1/verification.py` 中加强 artifact 结构检查，并让 ROS 2 / MoveIt evidence runner 输出更丰富的 runtime evidence。

**技术栈：** Python、pytest、ruff、mypy、ROS 2 Jazzy / rclpy、MoveIt 2 service API、JSON artifact。

---

### Task 1：验收聚合门禁

**文件：**
- 修改：`scripts/verify_phase9_1.py`
- 测试：`tests/test_phase9_1_verifier_hardening.py`

- [x] 增加 table-driven 测试：`ros2=INCOMPLETE`、`ros2=ROS2_READY`、`moveit=INCOMPLETE`、`moveit=MOVEIT_READY`，且 Isaac blocked 时都必须返回 `PHASE9_1_REJECTED`。
- [x] 增加正向测试：ROS 2 + MoveIt validated 且 Isaac/cross-backend blocked 时返回 `PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK`；全部组件和 cross-backend validated 时返回 `PHASE9_1_ACCEPTED`。
- [x] 抽出 status aggregation helper，让测试不用运行 ROS 也能覆盖完整 decision。
- [x] 实现严格组件门禁：ROS 2 只接受 `ROS2_INTEGRATION_VALIDATED` 或真实 `BLOCKED_BY_ENV`；MoveIt 只接受 `MOVEIT_SAFETY_VALIDATED` 或真实 `BLOCKED_BY_ENV`；READY/INCOMPLETE/FAILED/未知状态全部拒绝。

### Task 2：Runtime Artifact 完整性

**文件：**
- 修改：`src/cloud_edge_robot_arm/simulation/phase9_1/verification.py`
- 修改：`scripts/phase9/run_ros2_runtime_evidence.py`
- 修改：`scripts/phase9/run_moveit_safety_evidence.py`
- 测试：`tests/test_phase9_1_runtime_evidence_contract.py`

- [x] 增加测试：日志包含 `Traceback`、`Segmentation fault`、`RCLError` 或 `process exited unexpectedly` 时，runtime evidence 必须不完整。
- [x] 增加测试：MoveIt collision evidence 必须包含 `baseline_plan`、`collision_object`、`planning_scene_confirmed`、`replanned_or_rejected`、`collision_free`、`trajectory_delta`、`moveit_error_code` 和 process provenance。
- [x] 增加测试：planning-timeout evidence 必须包含正常预算成功、timeout 预算结果、wall-clock timing、配置 timeout，且不能接受任意非成功 planning failure。
- [x] 实现共享 log issue detection 和 runtime observed-result validator，供 ROS 2 与 MoveIt verification 使用。

### Task 3：MoveIt Collision 与 Timeout 证据

**文件：**
- 修改：`scripts/phase9/run_moveit_safety_evidence.py`

- [x] 加障碍前先为同一目标生成 baseline plan。
- [x] 在 baseline path 附近插入 collision object，并通过 planning scene service/topic 确认。
- [x] 对同一目标重新规划，并把结果分类为 collision rejection 或 valid replanning。
- [x] 若成功，则检查 trajectory collision-free 状态，并与 baseline 比较 trajectory point count、joint-space path length 和 sample delta。
- [x] 对 timeout，先证明同一目标在正常预算下成功，再用极短预算重跑，并记录 timing 与 MoveIt error 语义。

### Task 4：ROS 2 关闭卫生

**文件：**
- 修改：`ros2_ws/src/bigsmall_sim_bridge/bigsmall_sim_bridge/sim_bridge_node.py`
- 修改：`scripts/phase9/run_ros2_runtime_evidence.py`
- 修改：`scripts/phase9/run_moveit_safety_evidence.py`
- 测试：`tests/test_phase9_1_runtime_evidence_contract.py`

- [x] 增加 bridge shutdown API，在 executor shutdown 前停止接受新 goal。
- [x] 在 `rclpy.shutdown()` 前显式销毁 action server。
- [x] 在销毁 parent evidence node 前停止 child process，并容忍预期 shutdown exception，不能写入 traceback。
- [x] 日志中若仍有非白名单 shutdown error，则 evidence completeness 失败。

### Task 5：文档与最终验证

**文件：**
- 修改：`README.md`
- 修改：`docs/phase9_1_acceptance.md`
- 修改：`docs/phase9_1_report.md`

- [x] 文档说明 ROS 2 runtime 和 MoveIt 2 safety 已验证，Isaac 与 cross-backend 仍受环境阻塞，真实机械臂验证未开始。
- [x] 增加 Phase 9.1 runtime 与 aggregate verifier 的准确命令。
- [x] 运行最终命令套件：ruff format check、ruff check、mypy、pytest、Phase 9 verifier、ROS 2 verifier、MoveIt verifier、aggregate verifier。
- [x] commit 并 push：`fix: harden phase9.1 runtime acceptance evidence`。
