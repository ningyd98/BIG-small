# LIFT 保持异常停止 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for this bounded repair. Current main-agent execution and user authorization override optional delegation/approval defaults. Steps use checkbox syntax.

**Goal:** 独立 MuJoCo LIFT 适配器在保持普通异常时主动取消运动、停止并返回保留原始原因的结构化失败。

**Architecture:** 仅在 MuJoCoSkillRobot.lift 的运动成功之后建立完整保持阶段异常边界，复用 backend.emergency_stop()（内含 cancel/hold）。保留领域 guard 的既有代码/停止语义和成功路径的保留目标交接。

**Tech Stack:** Python 3.12、MuJoCo 3.3.7、pytest，identity callback 模型替身。

**Spec:** 当前用户/主进程明确委派；本目录 plan.json 给出完整输入、接口契约与验收矩阵。

## 计划身份与适用性

实际规划模型为 **gpt-6-astra**，显式委派的 Astra 计划子代理。状态 **PLANNED_NOT_IMPLEMENTED**：未改实现/测试，未运行测试、worker、付费服务或真机。工作树 `/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall`，基线 HEAD `4ed5cb50ada7b6b0ca6b3a2fd168aeca637e3cfa`，写计划前 clean。

磁盘 AGENTS.md 为 2026-11-13 按需 Astra 更新，本轮当前用户/主进程明确要求 Astra。公开推送依当前授权继续暂缓。

## 问题、原始失败与根因

已读取主进程原始 probe 和 stdout（路径/哈希见下表），规划代理未重跑。真实无渲染 MuJoCo、S01_NORMAL_STATIC seed 31、dt=1/240、identity callback。运动成功后首个保持 step 1821 observer 抛 RuntimeError('review_fault_first_lift_hold_step')：最后命令是 step 1820 joint_target，故障后命令为空，estop=false，session=SUCCEEDED，目标/反馈最大差 0.014529058112937115 rad。这仅是有界模拟故障证据。

skill_robot.py 的保持仅在逐步循环中捕获 MotionGuardViolation；step、contacts、monitor_hold 普通异常未被完整的适配器结果/停止边界覆盖。monitor_hold 已对 BaseException 执行 hold 后重抛，但没有适配器结构化结果。move_tcp 已合法结束运动并标记 SUCCEEDED，之后保持失败必须更新终态。observer 可在物理步计数已增加、held_steps 尚未增加时抛出，失败统计应依据 backend counter delta。完整 worker 外层 safe_stop 不替代独立适配器保证。

## Global Constraints

- 生产只改 `src/cloud_edge_robot_arm/simulation/mujoco/skill_robot.py`；新增测试只改 `tests/test_visual_servo_control.py`。
- visual_servo.py、backend.py、契约和 worker 只读参考，不进行通用 cleanup 重构。
- 掉物/路径判据、0.5s 保持、超时/延迟预算、轨迹、成功保留目标交接，以及标记/顶视/控制器选择不变。
- 保留历史失败、冻结字节和旧资格；九项运行闭环由主进程独立处理。
- 本地交付，不公开推送，不使用付费模型、完整 worker 或真机，不宣称正式研究验收。

## Review Focus

1. 故障发生在物理步之后：H1 验证 counter delta 包含故障步。
2. 反馈原始原因丢失：H2 验证 ValueError/RuntimeError 的 reason/type 同时存在于 details 和 error.details。
3. 取消被吞掉：H3 验证非 Exception 的 BaseException 先停止、再重抛同一对象。
4. 领域错误被通用重映射：H4 保留 GRASP_LOST/CLEARANCE_PATH_VIOLATION。
5. 无视觉及正常交接变化：H5/H6 覆盖非视觉故障和现有成功回归。

## Task 1: 完整保持阶段异常边界

**Files:** Modify `src/cloud_edge_robot_arm/simulation/mujoco/skill_robot.py`; Test `tests/test_visual_servo_control.py`。

**Interfaces:** 保持 lift(...) -> ActionResult；复用 backend.emergency_stop()/hold_current_joints()/total_physics_steps。普通错误码 `LIFT_HOLD_FAILED`；details 包含 failure_phase='LIFT_HOLD'、reason=str(exc)、exception_type=type(exc).__name__。既有 build_action_result 将 details 复制到 error.details，无需新增全局错误注册或改契约。

- [ ] **Step 1 — 复核/留证。** 核对 HEAD 和下表全部 SHA256，源有变化先记录计划适用性。将原始 probe/stdout 原字节复制至新轮次证据；不改旧 `/tmp` 文件。
- [ ] **Step 2 — 写 H1–H5。** 测试名与具体断言见 plan.json.acceptance_cases。使用真实 MuJoCo，新测试关闭 RGB/depth，只在运动已成功后触发保持故障。H1 首步 observer RuntimeError；H2 sample ValueError/RuntimeError；H3 step/sample 的同一 BaseException 对象；H4 两种 guard；H5 无 visual session。H5 可包装成功 _move 仅用于启用故障，不能替代真实物理运动。
- [ ] **Step 3 — 运行 RED。** `.venv/bin/python -m pytest tests/test_visual_servo_control.py -k lift_hold_ -v`，保留 stdout/stderr、exit status、JUnit 和选中测试清单。合格 RED 应是缺失停止/结果的语义失败，不能把 import/fixture 失败算入。
- [ ] **Step 4 — 最小实现。** 运动成功后记录 hold_start_steps，在整个 hold context、guard/step、contacts、monitor_hold、最终保持测量外建立异常边界。先处理 MotionGuardViolation 并保留 code/reason 及原 hold_current_joints 策略；其余 Exception 直接 backend.emergency_stop() 后返回 LIFT_HOLD_FAILED；其余 BaseException 停止后原样重抛。直接 backend stop 避免 safe_stop 的预先 snapshot 阻碍停止。
- [ ] **Step 5 — 诊断一致。** 失败时 session.terminal_reason='Type:message'，ActionResult visual_servo 摘要取当前 session；原始 reason/type 保留。physics_steps = movement action.physics_steps + backend.total_physics_steps - hold_start_steps。停止不能推进物理步。禁止成功路径的无条件 finally stop。
- [ ] **Step 6 — GREEN 与回归。** 运行同一新测试选择器后，执行 `.venv/bin/python -m pytest tests/test_visual_servo_control.py tests/test_rgbd_physical_skills.py tests/test_visual_servo.py -q`。已有 hold cadence、路径、双侧接触、速度/加速度、姿态、transport/place handoff 均通过；skip 不算通过。
- [ ] **Step 7 — 静态检查/有界复核。** `.venv/bin/ruff check src/cloud_edge_robot_arm/simulation/mujoco/skill_robot.py tests/test_visual_servo_control.py` 和 `git diff --check`。如复核原 probe，另写 post-fix 脚本接受结构化返回。旧 probe 预期 RuntimeError，修复后不能直接作为 GREEN 脚本，不能改旧字节让其通过。
- [ ] **Step 8 — 报告交付。** 新轮次保留 RED/GREEN/环境/清单，生成步骤报告并汇入阶段总结。区分软件验证、有界模拟、真实运行、正式研究验收；主进程按明确路径本地提交，公开 push 仍暂停。

## 红绿验收细节

H1/H2/H5：success=false，error_code=LIFT_HOLD_FAILED；action.details 与 action.error.details 保留原始 reason/type。同一故障步出现 hold_current_joints 与 emergency_stop，estop=true，pending queue 清空，目标等于当前反馈；无后续 joint_target/物理步。session 与 result.visual_servo 终态一致，不再是 SUCCEEDED，退出 context 后解除绑定。

H2：monitor_hold 本身可能先 hold，emergency_stop 再 hold；重复无物理步的 hold 允许。原始 sample reason 不能变成通用代码。存在 Python cause/context 时不以通用异常覆盖，当前范围不要求序列化完整 traceback。

H3：停止后重抛同一 BaseException，不转普通 ActionResult。H4：领域代码/原停止策略保持，不强制新 estop。H6：成功无新停止，0.5s 接触保持、反馈 cadence、retained equilibrium handoff 保持。

## 实际运行前置条件与验收边界

只读检查到 Python 3.12.3、MuJoCo 3.3.7、NumPy 2.5.3、pytest 8.4.2、ruff 0.14.14。使用本工作树 .venv/PYTHONPATH=src。新故障测试无渲染，现有 render-enabled 回归用既有可用 headless GL，不改生产默认。无需网络/凭据。

结构化 ActionResult 的前提是已有 backend stop 与 snapshot 接口可用。若它们本身失败，不得伪称停止或丢弃初始异常链；这是需下一轮计划的新根因，不在本轮建立通用恢复框架。输入变化先复核；范围超出 skill_robot.py、新根因或非预期 RED 失败时停止受影响修复并按当前用户流程交 Astra 再计划，独立工作可继续。

通过仅证明独立适配器局部异常契约及邻接仿真回归，不证明视觉模型质量、完整 worker、真机安全或研究资格。

## 输入路径与 SHA256

| 路径 | SHA256 |
|---|---|
| `AGENTS.md` | `7f4f8b080b2f1e99b53d24aeebf62f51815315c69a40dc9223d2e974c3c40cdb` |
| `pyproject.toml` | `42fdefae6dff25d26e3ded9ab39c7910ee8116f4aed2e9d8f60eee23809e0933` |
| `src/cloud_edge_robot_arm/simulation/mujoco/skill_robot.py` | `db59243b66f0279948cd4f3df7e57587494a26f7df7ae719b5904fd640e045b2` |
| `src/cloud_edge_robot_arm/simulation/mujoco/visual_servo.py` | `71218ee666b8b90772cc9e3a03bab93c45c57d3ae6017c8ec734e9dd3fb13ff8` |
| `src/cloud_edge_robot_arm/simulation/mujoco/backend.py` | `c4f8104b39f2f0d4d489f1b4e105bf98f129bc7b9bbf6ae99c4804aeac307445` |
| `src/cloud_edge_robot_arm/edge/robot_adapter.py` | `f488086f82b32156a68409760ab6407b69bf2ddda0434524971143bfb8711f01` |
| `src/cloud_edge_robot_arm/contracts/models.py` | `448be02bb26ca7546624c8a5ceece12b430ab423b94d28a2b6aac7741318fc9c` |
| `src/cloud_edge_robot_arm/research/sol_molmo_components.py` | `9b43e32204a80c3b2f6ecf1c5c3f28fc9aa7e5579a96636a2bc0726034d36af8` |
| `tests/test_visual_servo_control.py` | `ca1c79a2e40c55c1cc65364bd7778cf0ef7006c989e68111459753f5cb3f6489` |
| `tests/test_rgbd_physical_skills.py` | `83752e289c6c6156c1952511d949c3e2f067d3f1bac4ca69a971a31716e74b57` |
| `/tmp/bigsmall-grasp-audit-20261117/lift-hold-exception-probe.py` | `ed58efcc42c198fbfad1cac91266c2ee4392058230141dd13307850b6f1e20b6` |
| `/tmp/bigsmall-grasp-audit-20261117/lift-hold-exception-probe.stdout.json` | `1593f3aa73bb341970e7e9060ba3df90caf0994c95a3a2a500595b8eb6fb719a` |

## 计划自检与操作记录

已覆盖 step、feedback、BaseException、原始原因、领域代码、无视觉及成功交接；接口与源码一致。未执行 RED/GREEN，无实施通过声明。首次计划写入命令使用不存在的 unqualified python，启动前即失败，未产生修改；已改用检查过的 .venv/bin/python，不涉及应用根因或实施范围变化。
